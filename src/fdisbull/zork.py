"""Bounded, isolated Jericho sessions for Z-machine stories."""
import hashlib
import base64
import copy
import re
import json
import os
from pathlib import Path
import secrets
import selectors
import subprocess
import tempfile
import threading
from .zmachine import inspect_story

MAX_MESSAGE = 8_000_000

def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

class ZorkError(RuntimeError):
    pass

class ZorkSession:
    def __init__(self, story, *, python, timeout_ms=10000, seed=123, expected=None):
        self.story = str(Path(story).resolve(strict=True))
        self.story_info = inspect_story(self.story)
        self._story_hash = self.story_info['sha256']
        self.python = str(Path(python).resolve(strict=True))
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 300000:
            raise ValueError('invalid timeout')
        self.timeout_ms = timeout_ms
        if type(seed) is not int or not 1 <= seed < 2**31:
            raise ValueError('invalid seed')
        self.seed = seed
        self.expected = copy.deepcopy(expected)
        self._identity = None
        self._transcript = []
        self._revision = 0
        self._lock = threading.RLock()
        self._process = None
        self._worker_dir = None
        self._poisoned = False
        self._start()

    @property
    def identity(self):
        return copy.deepcopy(self._identity)

    @property
    def transcript(self):
        return copy.deepcopy(self._transcript)

    def _start(self):
        story_hash = _sha(self.story)
        if story_hash != self._story_hash:
            raise ZorkError('story file changed')
        worker = str(Path(__file__).with_name('zork_worker.py'))
        self._worker_dir = tempfile.TemporaryDirectory(prefix='fdisbull-zork-')
        try:
            environment = os.environ.copy()
            environment['PYTHONDONTWRITEBYTECODE'] = '1'
            self._process = subprocess.Popen([self.python, '-u', worker, self.story, str(self.seed), story_hash, self._worker_dir.name], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0, cwd=self._worker_dir.name, env=environment)
            response = self._read()
            identity = response.get('identity')
            fields = {'python', 'python_sha256', 'jericho_version', 'jericho_sha256', 'jericho_module_sha256', 'native_sha256', 'story_sha256'}
            layout = response.get('layout')
            protected = response.get('protected_paths')
            valid_digest = lambda x: isinstance(x, str) and re.fullmatch(r'[0-9a-f]{64}', x) is not None
            if (response.get('complete') is not True or response.get('outcome') != 'ready'
                or not isinstance(identity, dict) or set(identity) != fields
                or any(not valid_digest(identity[k]) for k in fields if k.endswith('_sha256'))
                or identity.get('jericho_version') != '3.3.1'
                or identity.get('story_sha256') != story_hash or identity.get('python') != self.python
                or identity.get('python_sha256') != _sha(self.python)
                or not isinstance(response.get('observation'), str)
                or not isinstance(protected, list) or not protected or any(not isinstance(p, str) or not os.path.isabs(p) for p in protected)
                or not isinstance(layout, dict) or set(layout) != {'ram', 'stack', 'story'}
                or any(type(v) is not int or not 0 < v <= 16_000_000 for v in layout.values())
                or layout['stack'] % 2 or layout['story'] != os.path.getsize(self.story)
                or (self.expected is not None and identity != self.expected)
                or (self._identity is not None and identity != self._identity)):
                raise ZorkError('worker identity or startup failed: ' + str(response.get('error', 'mismatch')))
            self._identity = copy.deepcopy(identity)
            self._layout = copy.deepcopy(layout)
            self._protected_paths = {os.path.realpath(p) for p in protected} | {self.story, self.python, os.path.realpath(worker), os.path.realpath(__file__)}
            self._poisoned = False
            self._revision += 1
            self._observation = response['observation']
            self._mode = 'unknown'
            self._transcript = [{'seq': 0, 'kind': 'observation', 'text': self._observation}]
        except Exception:
            self._fail()
            raise

    def _fail(self):
        self._poisoned = True
        if self._process:
            self._process.kill() if self._process.poll() is None else None
            self._process.wait()
            for stream in (self._process.stdin, self._process.stdout):
                if stream: stream.close()
            self._process = None
        if self._worker_dir is not None:
            self._worker_dir.cleanup()
            self._worker_dir = None

    def _read(self, deadline=None):
        import time
        if deadline is None: deadline = time.monotonic() + self.timeout_ms / 1000
        data = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(self._process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise ZorkError('worker deadline exceeded')
                chunk = os.read(self._process.stdout.fileno(), min(65536, MAX_MESSAGE + 1 - len(data)))
                if not chunk:
                    raise ZorkError('worker exited before complete response')
                data.extend(chunk)
                if len(data) > MAX_MESSAGE:
                    raise ZorkError('worker response exceeds limit')
                if b'\n' in data:
                    line, rest = bytes(data).split(b'\n', 1)
                    if rest: raise ZorkError('unexpected worker output')
                    try: result = json.loads(line)
                    except (ValueError, UnicodeError) as exc: raise ZorkError('invalid worker response') from exc
                    if not isinstance(result, dict): raise ZorkError('invalid worker response')
                    return result

    def _request(self, op, **args):
        if self._poisoned or self._process is None:
            raise ZorkError('session requires reset or restore')
        try:
            if _sha(self.story) != self._identity['story_sha256']:
                raise ZorkError('story file changed')
            msg = json.dumps({'op': op, **args}, separators=(',', ':')).encode() + b'\n'
            if len(msg) > MAX_MESSAGE: raise ZorkError('request exceeds limit')
            import time
            deadline = time.monotonic() + self.timeout_ms / 1000
            os.set_blocking(self._process.stdin.fileno(), False)
            with selectors.DefaultSelector() as selector:
                selector.register(self._process.stdin, selectors.EVENT_WRITE)
                offset = 0
                while offset < len(msg):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining): raise ZorkError('worker deadline exceeded')
                    offset += os.write(self._process.stdin.fileno(), msg[offset:offset + 65536])
            response = self._read(deadline)
            if response.get('complete') is not True or response.get('outcome') != 'ok':
                raise ZorkError('worker incomplete: ' + str(response.get('error', 'unexpected response')))
            return response
        except Exception:
            self._fail()
            raise

    def observe(self):
        with self._lock:
            if self._poisoned or self._process is None or self._process.poll() is not None:
                self._fail()
                raise ZorkError('session requires reset or restore')
            return {'complete': True, 'outcome': 'observed', 'observation': self._observation, 'mode': self._mode, 'identity': copy.deepcopy(self._identity), 'transcript': copy.deepcopy(self._transcript)}

    def command(self, text):
        if not isinstance(text, str) or not text or any(not 32 <= ord(c) <= 126 for c in text) or len(text) > 198:
            raise ValueError('command must be printable ASCII and at most 198 characters')
        with self._lock:
            response = self._request('command', text=text)
            if not isinstance(response.get('observation'), str) or type(response.get('done')) is not bool:
                self._fail(); raise ZorkError('malformed command response')
            self._revision += 1
            self._observation = response['observation']; self._mode = response.get('mode', 'unknown')
            self._transcript.append({'seq': len(self._transcript), 'kind': 'command', 'text': text})
            self._transcript.append({'seq': len(self._transcript), 'kind': 'observation', 'text': self._observation})
            return response

    def save_checkpoint(self, path):
        with self._lock:
            destination = os.path.realpath(path)
            if (self._worker_dir is not None and os.path.commonpath((destination, os.path.realpath(self._worker_dir.name))) == os.path.realpath(self._worker_dir.name)) or destination in self._protected_paths or (os.path.exists(destination) and any(os.path.exists(p) and os.path.samefile(destination, p) for p in self._protected_paths)):
                raise ZorkError('checkpoint destination is protected')
            response = self._request('state')
            try:
                state = response['state']
                self._validate_state(state)
            except (KeyError, ValueError, TypeError) as exc:
                self._fail()
                raise ZorkError('invalid worker state') from exc
            payload = {'format': 'fdisbull-zork-1', 'identity': self._identity, 'seed': self.seed, 'state': state, 'observation': self._observation, 'mode': self._mode, 'transcript': self._transcript}
            raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
            wrapper = json.dumps({'sha256': hashlib.sha256(raw).hexdigest(), 'payload': payload}, sort_keys=True, separators=(',', ':')).encode()
            if len(wrapper) > MAX_MESSAGE: raise ZorkError('checkpoint exceeds limit')
            dest = Path(path); dest.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix='.zork-')
            try:
                with os.fdopen(fd, 'wb') as f: f.write(wrapper); f.flush(); os.fsync(f.fileno())
                os.replace(tmp, dest)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)
            return {'complete': True, 'outcome': 'saved', 'sha256': hashlib.sha256(wrapper).hexdigest()}

    def restore_checkpoint(self, path):
        with self._lock:
            with open(path, 'rb') as source:
                raw = source.read(MAX_MESSAGE + 1)
            if len(raw) > MAX_MESSAGE: raise ZorkError('checkpoint exceeds limit')
            try:
                wrapper = json.loads(raw); payload = wrapper['payload']
                encoded = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
                if set(wrapper) != {'sha256', 'payload'} or set(payload) != {'format', 'identity', 'seed', 'state', 'observation', 'mode', 'transcript'} or wrapper['sha256'] != hashlib.sha256(encoded).hexdigest() or payload['format'] != 'fdisbull-zork-1' or payload['identity'] != self._identity or type(payload['seed']) is not int or payload['seed'] != self.seed or not isinstance(payload['observation'], str) or not isinstance(payload['transcript'], list) or payload['mode'] != 'unknown':
                    raise ValueError('checkpoint identity or contents mismatch')
                transcript = payload['transcript']
                if not transcript or len(transcript) % 2 != 1:
                    raise ValueError('invalid transcript')
                for i, entry in enumerate(transcript):
                    if not isinstance(entry, dict) or set(entry) != {'seq', 'kind', 'text'} or type(entry['seq']) is not int or entry['seq'] != i or entry['kind'] != ('observation' if i % 2 == 0 else 'command') or not isinstance(entry['text'], str):
                        raise ValueError('invalid transcript entry')
                if transcript[-1]['text'] != payload['observation']:
                    raise ValueError('observation mismatch')
                self._validate_state(payload['state'])
            except (ValueError, TypeError, KeyError) as exc: raise ZorkError('invalid checkpoint') from exc
            if self._poisoned: self._start()
            self._request('restore', state=payload['state'])
            self._revision += 1
            self._observation = payload['observation']; self._mode = payload['mode']; self._transcript = payload['transcript']
            return {'complete': True, 'outcome': 'restored'}

    def _validate_state(self, state):
        if not isinstance(state, list) or len(state) != 9:
            raise ValueError('invalid state')
        for index, size in ((0, self._layout['ram']), (1, self._layout['stack'])):
            if not isinstance(state[index], str) or len(state[index]) > MAX_MESSAGE:
                raise ValueError('invalid state array')
            if len(base64.b64decode(state[index], validate=True)) != size:
                raise ValueError('invalid state array size')
        pc, sp, fp, frames, opcode = state[2:7]
        if any(type(n) is not int for n in (pc, sp, fp, frames, opcode)):
            raise ValueError('invalid state numbers')
        words = self._layout['stack'] // 2
        if not (0 <= pc < self._layout['story'] and 0 <= sp <= words and 0 <= fp <= words and 0 <= frames <= words and 0 <= opcode <= 255):
            raise ValueError('invalid native state pointers')
        rng = state[7]
        if not isinstance(rng, list) or len(rng) != 3 or any(type(x) is not int or not -(2**63) <= x < 2**63 for x in rng) or any(not -(2**31) <= x < 2**31 for x in rng[1:]):
            raise ValueError('invalid rng')
        if not isinstance(state[8], str) or len(state[8]) > 1000000 or b'\x00' in base64.b64decode(state[8], validate=True):
            raise ValueError('invalid narrative')

    def reset(self):
        with self._lock:
            self.close(); self._start()
            return self.observe()

    def close(self):
        with self._lock: self._fail()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()

class NamedZorkHarness:
    """Qualify caller-defined actions using only public text observations.

    Each scene has a nonempty ``match`` substring and an ``actions`` mapping;
    every action specifies a full ``command`` and nonempty ``expect`` substring.
    An unexpected response requires explicit ``reacquire`` before another action.
    """
    def __init__(self, session, scenes):
        if not isinstance(scenes, dict) or not scenes:
            raise ValueError('scenes must be a nonempty mapping')
        for scene, spec in scenes.items():
            if not isinstance(scene, str) or not isinstance(spec, dict) or set(spec) != {'match', 'actions'} or not isinstance(spec['match'], str) or not spec['match'] or not isinstance(spec['actions'], dict) or not spec['actions']:
                raise ValueError('invalid scene definition')
            for name, action in spec['actions'].items():
                if not isinstance(name, str) or not isinstance(action, dict) or set(action) != {'command', 'expect'} or any(not isinstance(action[k], str) or not action[k] for k in ('command', 'expect')):
                    raise ValueError('invalid action definition')
        self.session, self.scenes = session, copy.deepcopy(scenes)
        self._lock = threading.Lock(); self._token = None; self._latched = False

    def _acquire(self, scene):
        if scene not in self.scenes: raise ValueError('unknown scene')
        observation = self.session.observe()
        if self.scenes[scene]['match'] not in observation['observation']:
            raise ZorkError('public observation does not match scene')
        self._token = secrets.token_urlsafe(24)
        self._scene = scene
        self._sequence = self.session._revision
        return {'scene': scene, 'actions': list(self.scenes[scene]['actions']), 'token': self._token, 'observation': observation}

    def observe(self, scene):
        with self._lock, self.session._lock:
            if self._latched: raise ZorkError('route requires explicit reacquire')
            return self._acquire(scene)

    def reacquire(self, scene):
        with self._lock, self.session._lock:
            result = self._acquire(scene)
            self._latched = False
            return result

    def act(self, scene, action, token):
        with self._lock, self.session._lock:
            if self._latched: raise ZorkError('route requires explicit reacquire')
            if not isinstance(token, str) or not self._token or scene != self._scene or self._sequence != self.session._revision or not secrets.compare_digest(self._token, token): raise ZorkError('stale action token')
            self._token = None
            if scene not in self.scenes or action not in self.scenes[scene]['actions']: raise ValueError('unknown action')
            spec = self.scenes[scene]['actions'][action]
            try:
                response = self.session.command(spec['command'])
            except Exception:
                self._latched = True
                raise
            matched = spec['expect'] in response['observation']
            self._latched = not matched
            return {'complete': response['complete'], 'outcome': 'expected' if matched else 'unexpected', 'raw_command': spec['command'], 'response': response}
