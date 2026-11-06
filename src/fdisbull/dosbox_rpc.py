"""Local JSON-lines transport for an explicitly supplied DOSBox agent build."""
from __future__ import annotations

import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import threading
import time
import weakref


class DebuggerError(ValueError):
    """A debugger operation failed; uncertain requests are never replayed."""


class DOSBoxRPC:
    limit = 8 * 1024 * 1024

    def __init__(self, executable, game_dir, *, window=False, on_spawn=None):
        if type(window) is not bool:
            raise ValueError('window must be boolean')
        if window:
            driver = os.environ.get('SDL_VIDEODRIVER', '').strip().lower()
            if any(item.strip() in ('dummy', 'offscreen') for item in driver.split(',')):
                raise DebuggerError('Window requires a visible SDL video driver; SDL_VIDEODRIVER is '+driver)
            if sys.platform.startswith('linux') and not driver and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
                raise DebuggerError('Window requires an available display (DISPLAY or WAYLAND_DISPLAY)')
        if os.name != 'posix':
            raise DebuggerError('Inherited-pipe debugger currently requires macOS or Linux')
        executable = Path(executable).expanduser().resolve(strict=True)
        game_dir = Path(game_dir).expanduser().resolve(strict=True)
        if not executable.is_file() or not os.access(executable, os.X_OK) or not game_dir.is_dir():
            raise DebuggerError('Expected an executable DOSBox agent and a game directory')
        if any(c in str(executable) + str(game_dir) for c in '\r\n\0'):
            raise DebuggerError('Paths cannot contain configuration line breaks or NUL')
        self.process = None
        self.reader = self.writer = None
        self.sequence = 0
        self.lock = threading.Lock()
        self.temporary = tempfile.TemporaryDirectory(prefix='fdisbull-dosbox-')
        temp_finalizer = getattr(self.temporary, '_finalizer', None)
        if temp_finalizer is not None:
            temp_finalizer.detach()
        self._cleanup_state = {
            'reader': None,
            'writer': None,
            'process': None,
            'temporary': self.temporary,
        }
        self._finalizer = weakref.finalize(self, self._finalize_unclosed, self._cleanup_state)
        directory = Path(self.temporary.name)
        descriptors = []
        try:
            child_read, self.writer = os.pipe()
            self._cleanup_state['writer'] = self.writer
            descriptors.append(child_read)
            self.reader, child_write = os.pipe()
            self._cleanup_state['reader'] = self.reader
            descriptors.append(child_write)
            config = directory / 'agent.env'
            config.write_text(
                f'transport=pipe\nendpoint=fd:{child_read}:{child_write}\n'
                f'dosbox_executable={executable}\ndosbox_workdir={game_dir}\n'
                'profile=production\nrequest_timeout_ms=15000\n'
                f'max_message_bytes={self.limit}\nmax_memory_read_bytes=65536\nmax_trace_events=10000\n')
            config.chmod(0o600)
            environment = {k:v for k,v in os.environ.items() if not k.upper().startswith('DOSBOX_')}
            environment['XDG_CONFIG_HOME'] = str(directory / 'config')
            # Owned sessions must never block on a host quit-confirmation dialog.
            arguments = [str(executable), '--defaultconf', '--noautoexec', '--noconfig',
                         '-set', 'dosbox quit warning=false',
                         '-set', 'render doublescan=false', '-set', 'cpu core=normal', '--agent-config', str(config)]
            if window:
                arguments.append('-agent-window')
            else:
                # Default no-pop-ups mode: force dummy SDL video/audio and software
                # surface rendering so neither patched nor stock DOSBox-X can open a
                # desktop window, menu bar, cursor grab, or audio output device.
                environment['SDL_VIDEODRIVER'] = 'dummy'
                environment['SDL_AUDIODRIVER'] = 'dummy'
                environment['SDL_RENDER_DRIVER'] = 'software'
                arguments.extend([
                    '--nogui', '--nomenu', '--noconsole', '--fastlaunch',
                    '-set', 'sdl videodriver=dummy',
                    '-set', 'sdl output=surface',
                    '-set', 'sdl showmenu=false',
                    '-set', 'sdl usesystemcursor=false',
                    '-set', 'mixer nosound=true',
                    '-set', 'midi mididevice=none',
                ])
            with (directory / 'emulator.log').open('wb') as log:
                self.process = subprocess.Popen(
                    arguments,
                    cwd=directory, env=environment, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT, pass_fds=(child_read,child_write))
                self._cleanup_state['process'] = self.process
            if on_spawn is not None:on_spawn(self.process)
            os.close(child_read); descriptors.remove(child_read)
            os.close(child_write); descriptors.remove(child_write)
            os.set_blocking(self.reader, False)
            os.set_blocking(self.writer, False)
            self.capabilities = self.call('agent.capabilities')
            video = self.capabilities.get('video')
            if window and (not isinstance(video, dict) or video.get('headless') is not False or
                           video.get('controlled_window') is not True):
                raise DebuggerError('Backend does not advertise a safe controlled window; rebuild with a compatible agent backend')
        except BaseException:
            for fd in descriptors:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                self.close()
            except Exception:
                pass  # Preserve the original startup error while attempting cleanup.
            raise

    def call(self, method, params=None, timeout_ms=15000):
        deadline = time.monotonic() + timeout_ms / 1000
        if not self.lock.acquire(timeout=max(0, deadline-time.monotonic())):
            raise DebuggerError('Timed out waiting for RPC channel ownership')
        try:
            if self.reader is None or self.writer is None:
                raise DebuggerError('Debugger channel is closed')
            self.sequence += 1
            request_id = f'fdisbull-{self.sequence}'
            data = json.dumps({'jsonrpc':'2.0','id':request_id,'method':method,'params':params or {}},
                              allow_nan=False,separators=(',',':')).encode() + b'\n'
            if len(data) > self.limit:
                raise DebuggerError('RPC request exceeds message budget')
            sent = 0
            while sent < len(data):
                self._ready(self.writer, True, deadline)
                try:
                    written = os.write(self.writer, data[sent:sent+4096])
                except (BlockingIOError,InterruptedError):
                    continue
                if not written:
                    raise OSError('RPC write made no progress')
                sent += written
            response = bytearray()
            while b'\n' not in response:
                self._ready(self.reader, False, deadline)
                try:
                    chunk = os.read(self.reader, min(65536,self.limit+1-len(response)))
                except (BlockingIOError,InterruptedError):
                    continue
                if not chunk:
                    raise OSError('Emulator closed the RPC channel')
                response.extend(chunk)
                if len(response) > self.limit:
                    raise OSError('RPC response exceeds message budget')
            if response.find(b'\n') != len(response)-1:
                raise OSError('Unsolicited data after RPC response')
            result = json.loads(response)
            if not isinstance(result,dict) or result.get('id') != request_id or result.get('jsonrpc') != '2.0':
                raise OSError('Invalid RPC response identity')
        except BaseException:
            self._close_pipes()
            raise
        finally:
            self.lock.release()
        if 'error' in result:
            error = result['error']
            raise DebuggerError(f"{error.get('message','DOSBox error')} ({error.get('data',{}).get('reason',error.get('code'))})")
        if not isinstance(result.get('result'),dict):
            self._close_pipes()
            raise DebuggerError('RPC result must be an object')
        return result['result']

    @staticmethod
    def _ready(fd, writing, deadline):
        while True:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('RPC deadline expired; channel closed without replay')
            try:
                readable,writable,_ = select.select([] if writing else [fd], [fd] if writing else [], [], remaining)
                if readable or writable:
                    return
            except InterruptedError:
                continue

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @staticmethod
    def _finalize_unclosed(state):
        for name in ('reader', 'writer'):
            fd = state.get(name)
            if fd is not None:
                state[name] = None
                try:
                    os.close(fd)
                except BaseException:
                    pass
        process = state.get('process')
        if process is not None:
            state['process'] = None
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                process.wait(timeout=2)
            except BaseException:
                pass
        temporary = state.get('temporary')
        if temporary is not None:
            state['temporary'] = None
            try:
                temporary.cleanup()
            except BaseException:
                pass

    def _close_pipes(self):
        failure = None
        state = getattr(self, '_cleanup_state', None)
        for name in ('reader','writer'):
            fd = getattr(self,name,None)
            if fd is not None:
                setattr(self,name,None)
                if state is not None:
                    state[name] = None
                try:
                    os.close(fd)
                except BaseException as error:
                    if failure is None:
                        failure = error
        if failure is not None:
            raise failure

    def close(self):
        finalizer = getattr(self, '_finalizer', None)
        if finalizer is not None:
            finalizer.detach()
        state = getattr(self, '_cleanup_state', None)
        failure = None
        try:
            self._close_pipes()
        except BaseException as error:
            failure = error
        try:
            if self.process is not None:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                self.process.wait(timeout=2)
                if state is not None:
                    state['process'] = None
        except BaseException as error:
            if failure is None:
                failure = error
        finally:
            if self.temporary is not None:
                try:
                    self.temporary.cleanup()
                except BaseException as error:
                    if failure is None:
                        failure = error
                else:
                    self.temporary = None
                    if state is not None:
                        state['temporary'] = None
        if failure is not None:
            raise failure
