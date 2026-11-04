"""Owned, bounded JSON-lines connection to a patched ScummVM engine backend.

The bridge uses one inherited bidirectional socket. A failed or ambiguous
request closes the connection; a mutating request is never sent twice.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import select
import socket
import subprocess
import tempfile
import threading
import time

from .output_artifacts import _private_directory


class ScummVMError(ValueError):
    """A backend request failed or its result cannot be trusted."""


class _PendingResponse:
    def __init__(self):
        self.ready = threading.Event()
        self.value = None


_GAME_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_LAUNCH_OPTION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
# These IDs select ScummVM's Lost in Time Inter_v3 factory. The experimental
# Gob bridge profile does not qualify other Gob interpreter families.
_GOB_GAME_IDS = frozenset(('lit', 'lit1', 'lit2'))
_KYRA_GAME_IDS = frozenset(('kyra1', 'lol'))


class ScummVMRPC:
    """Own exactly one ScummVM process and its private config/save directory."""

    limit = 8 * 1024 * 1024

    def __init__(self, executable, game_dir, *, game_id, runtime_parent,
                 boot_timeout_ms=240000, on_spawn=None, engine='agi',
                 language=None, platform=None):
        executable = Path(executable).expanduser().resolve(strict=True)
        game_dir = Path(game_dir).expanduser().resolve(strict=True)
        runtime_parent = Path(runtime_parent).expanduser().resolve(strict=True)
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ScummVMError('Expected an executable patched ScummVM backend')
        if not game_dir.is_dir() or not runtime_parent.is_dir():
            raise ScummVMError('Expected existing game and private runtime directories')
        if engine not in ('agi', 'gob', 'kyra'):
            raise ValueError('ScummVM engine must be agi, gob or kyra')
        if isinstance(game_id, str) and game_id.startswith(engine + ':'):
            game_id = game_id[len(engine) + 1:]
        if not isinstance(game_id, str) or not _GAME_ID.fullmatch(game_id):
            raise ValueError(f'ScummVM {engine.upper()} game_id must be a simple ID or {engine}:<ID>')
        if engine == 'gob' and game_id not in _GOB_GAME_IDS:
            raise ValueError('ScummVM Gob agent profile supports only Lost in Time (lit, lit1, lit2)')
        if engine == 'kyra' and game_id not in _KYRA_GAME_IDS:
            raise ValueError('ScummVM Kyra agent supports only Kyrandia I and Lands of Lore I')
        for name, value in (('language', language), ('platform', platform)):
            if value is not None and (not isinstance(value, str) or not _LAUNCH_OPTION.fullmatch(value)):
                raise ValueError(f'ScummVM {name} must be a simple option value')
        if type(boot_timeout_ms) is not int or not 1 <= boot_timeout_ms <= 600000:
            raise ValueError('boot_timeout_ms must be 1..600000')

        self.executable = executable
        self.game_dir = game_dir
        self.game_id = game_id
        self.engine = engine
        self.language = language
        self.platform = platform
        self.process = None
        self.sock = None
        self.sequence = 0
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._cleanup_lock = threading.Lock()
        self._pending = {}
        self._failure = None
        self._receiver = None
        self.temporary = tempfile.TemporaryDirectory(prefix='fdisbull-scummvm-', dir=runtime_parent)
        try:
            self.root = _private_directory(self.temporary.name)
        except BaseException:
            self.temporary.cleanup()
            self.temporary = None
            raise
        self.save_dir = self.root / 'saves'
        self.save_dir.mkdir(mode=0o700)
        parent = child = None
        try:
            parent, child = socket.socketpair()
            parent.setblocking(False)
            environment = os.environ.copy()
            environment['FDISBULL_SCUMMVM_FD'] = str(child.fileno())
            environment['SDL_VIDEODRIVER'] = 'dummy'
            environment['SDL_AUDIODRIVER'] = 'dummy'
            environment['XDG_CONFIG_HOME'] = str(self.root / 'config')
            arguments = [str(executable), '--config=' + str(self.root / 'scummvm.ini'),
                         '--savepath=' + str(self.save_dir), '--path=' + str(game_dir),
                         '--no-fullscreen']
            if language is not None:
                arguments.append('--language=' + language)
            if platform is not None:
                arguments.append('--platform=' + platform)
            arguments.append(engine + ':' + game_id)
            with (self.root / 'scummvm.log').open('wb') as log:
                self.process = subprocess.Popen(arguments, cwd=self.root, env=environment,
                                                stdin=subprocess.DEVNULL, stdout=log,
                                                stderr=subprocess.STDOUT,
                                                pass_fds=(child.fileno(),))
            if on_spawn is not None:
                on_spawn(self.process)
            child.close()
            child = None
            self.sock = parent
            parent = None
            self._receiver = threading.Thread(target=self._receive_loop,
                                              name='fdisbull-scummvm-rpc', daemon=True)
            self._receiver.start()
            hello = self.call('hello', timeout_ms=boot_timeout_ms)
            if (hello.get('engine') != engine or not isinstance(hello.get('capabilities'), list)
                    or any(not isinstance(item, str) for item in hello['capabilities'])):
                raise ScummVMError(f'Backend did not advertise the {engine.upper()} agent protocol')
            if engine == 'kyra' and (hello.get('protocol') != 'fdisbull-scummvm-agent'
                    or type(hello.get('protocol_version')) is not int or hello['protocol_version'] != 1
                    or type(hello.get('bridge_version')) is not int or hello['bridge_version'] != 1
                    or hello.get('profile') != 'kyra-emc2-v1'):
                raise ScummVMError('Backend lacks the supported Kyra/EMC2 agent protocol')
            if engine == 'kyra' and (not isinstance(hello.get('variant'), dict)
                    or hello['variant'].get('recognized_detection') is not True
                    or hello['variant'].get('game_id') != game_id):
                raise ScummVMError('Kyra backend did not bind the exact requested game')
            if engine == 'gob' and (hello.get('protocol') != 'fdisbull-scummvm-agent'
                    or type(hello.get('protocol_version')) is not int or hello['protocol_version'] != 1
                    or type(hello.get('bridge_version')) is not int or hello['bridge_version'] != 1
                    or hello.get('profile') != 'gob-inter-v3'):
                raise ScummVMError('Backend did not advertise a supported Gob protocol/profile')
            if engine == 'gob':
                variant = hello.get('variant')
                if (not isinstance(variant, dict) or variant.get('game_id') != game_id
                        or variant.get('recognized_detection') is not True
                        or any(not isinstance(variant.get(key), str) or
                               variant[key].casefold() in ('', 'unknown', 'unk')
                               for key in ('detected_language', 'detected_platform'))):
                    raise ScummVMError('Gob backend did not bind an unambiguous detected game variant')
                if language is not None and language.casefold() != variant['detected_language'].casefold():
                    raise ScummVMError('Gob detected language differs from the requested language')
                if platform is not None:
                    wanted = 'pc' if platform.casefold() == 'dos' else platform.casefold()
                    detected = variant['detected_platform'].casefold()
                    if wanted != ('pc' if detected == 'dos' else detected):
                        raise ScummVMError('Gob detected platform differs from the requested platform')
            self.hello = hello
            features = list(hello['capabilities'])
            try:
                self.call('pause', timeout_ms=min(5000, boot_timeout_ms))
            except ScummVMError:
                with self._state_lock:
                    failed_channel = self._failure is not None
                if failed_channel:
                    raise
                features = [feature for feature in features if feature != 'pause']
            else:
                if 'pause' not in features:
                    features.append('pause')
            self.capabilities = {'features': features,
                                 'virtual_time': hello.get('virtual_clock') is True}
        except BaseException:
            if child is not None:
                child.close()
            if parent is not None:
                parent.close()
            self.close()
            raise

    def call(self, op, params=None, *, timeout_ms=15000, on_sent=None):
        if not isinstance(op, str) or not op:
            raise ValueError('Expected a backend operation')
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
            raise ValueError('timeout_ms must be 1..600000')
        if params is None:
            params = {}
        if not isinstance(params, dict) or 'id' in params or 'op' in params:
            raise ValueError('Backend parameters must be a separate object')
        if on_sent is not None and not callable(on_sent):
            raise ValueError('on_sent must be callable')
        deadline = time.monotonic() + timeout_ms / 1000
        if not self._send_lock.acquire(timeout=max(0, deadline - time.monotonic())):
            self._fail_closed('Timed out waiting to send ScummVM request; channel closed without replay')
            raise ScummVMError(self._failure)
        try:
            with self._state_lock:
                if self._failure is not None or self.sock is None:
                    raise ScummVMError(self._failure or 'ScummVM channel is closed')
                self.sequence += 1
                request_id = self.sequence
            message = json.dumps({'id': request_id, 'op': op, **params},
                                 separators=(',', ':'), allow_nan=False).encode() + b'\n'
            if len(message) > self.limit:
                raise ScummVMError('ScummVM request exceeds message budget')
            waiter = _PendingResponse()
            with self._state_lock:
                if self._failure is not None or self.sock is None:
                    raise ScummVMError(self._failure or 'ScummVM channel is closed')
                self._pending[request_id] = waiter
                sock = self.sock
            sent = 0
            try:
                while sent < len(message):
                    self._ready(sock, True, deadline)
                    count = sock.send(message[sent:sent + 65536])
                    if count == 0:
                        raise ScummVMError('ScummVM closed its agent channel')
                    sent += count
                if on_sent is not None:
                    on_sent()
            except BaseException as exc:
                self._fail_closed(f'ScummVM send was interrupted: {exc}; channel closed without replay')
                raise
        finally:
            self._send_lock.release()

        if not waiter.ready.wait(max(0, deadline - time.monotonic())):
            self._fail_closed('Timed out waiting for ScummVM response; channel closed without replay')
        with self._state_lock:
            failure = self._failure
            result = waiter.value
        if failure is not None:
            raise ScummVMError(failure)
        if result is None:
            self._fail_closed('Missing ScummVM response; channel closed without replay')
            raise ScummVMError(self._failure)
        if not result['ok']:
            code = result.get('error', 'BACKEND_ERROR')
            detail = result.get('message', 'ScummVM operation refused')
            raise ScummVMError(f'{detail} ({code})')
        return {key: value for key, value in result.items() if key not in ('id', 'ok')}

    def _ready(self, sock, writing, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ScummVMError('Timed out waiting to send ScummVM request')
        readable, writable, _ = select.select([] if writing else [sock],
                                               [sock] if writing else [], [], remaining)
        if not (writable if writing else readable):
            raise ScummVMError('Timed out waiting to send ScummVM request')

    def _receive_loop(self):
        sock = self.sock
        buffer = bytearray()
        try:
            while True:
                with self._state_lock:
                    if self._failure is not None:
                        return
                readable, _, _ = select.select([sock], [], [], 0.25)
                if not readable:
                    continue
                chunk = sock.recv(65536)
                if not chunk:
                    raise ScummVMError('ScummVM closed its agent channel')
                buffer.extend(chunk)
                replies = []
                while True:
                    newline = buffer.find(b'\n')
                    if newline < 0:
                        break
                    if newline + 1 > self.limit:
                        raise ScummVMError('ScummVM response exceeds message budget')
                    line = bytes(buffer[:newline])
                    del buffer[:newline + 1]
                    replies.append(json.loads(line, parse_constant=self._invalid_constant))
                if len(buffer) > self.limit:
                    raise ScummVMError('ScummVM response exceeds message budget')
                if not replies:
                    continue
                with self._state_lock:
                    if self._failure is not None:
                        return
                    seen = set()
                    for reply in replies:
                        if (not isinstance(reply, dict) or type(reply.get('id')) is not int
                                or type(reply.get('ok')) is not bool
                                or reply['id'] in seen or reply['id'] not in self._pending):
                            raise ScummVMError('Invalid, duplicate, or unknown ScummVM response')
                        seen.add(reply['id'])
                    for reply in replies:
                        waiter = self._pending.pop(reply['id'])
                        waiter.value = reply
                        waiter.ready.set()
        except BaseException as exc:
            self._fail_closed(f'ScummVM response channel failed: {exc}; channel closed without replay')

    @staticmethod
    def _invalid_constant(value):
        raise ValueError(f'Non-finite JSON constant {value}')

    def _fail_closed(self, message):
        with self._state_lock:
            if self._failure is None:
                self._failure = message
            waiters = list(self._pending.values())
            self._pending.clear()
        try:
            self._shutdown()
        finally:
            for waiter in waiters:
                waiter.ready.set()

    def _shutdown(self):
        with self._cleanup_lock:
            if self.sock is not None:
                sock = self.sock
                self.sock = None
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
            if self.process is not None:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                self.process.wait(timeout=1)
            if self.temporary is not None:
                self.temporary.cleanup()
                self.temporary = None
        if self._receiver is not None and self._receiver is not threading.current_thread():
            self._receiver.join(timeout=0.5)

    def close(self):
        self._fail_closed('ScummVM channel is closed')
