"""Finite Codex worker for the isolated CI recovery source canary."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time

LIMIT = 2 * 1024 * 1024
ALLOWED = 'scripts/ci/recovery_probe_logic.py'
PROBE = 'scripts/ci/recovery-probe.py'
CODEX = '/Users/tiga/.local/bin/codex'
REMOTES = {'local-hub': '/Volumes/GitHub/GitHub/fDisBull-hub/fDisBull.git',
           'gitlab': 'https://gitlab.com/brewster-jennings-group/fdisbull.git'}


def run_command(argv, *, cwd, env=None, input_bytes=None, timeout=30):
    """Bound the complete subprocess lifetime, including a blocked stdin pipe."""
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('finite positive command timeout required')
    if input_bytes is not None and not isinstance(input_bytes, bytes):
        raise ValueError('command input must be bytes')
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    buffers = [bytearray(), bytearray()]
    timed_out = overflow = False
    selector = selectors.DefaultSelector()
    streams = [process.stdout, process.stderr]
    pending = memoryview(input_bytes or b''); written = 0
    def kill_owned():
        # The session leader is not reaped until after I/O ends. Its PID cannot
        # be reused while this call still refers to its owned process group.
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
    try:
        for index, stream in enumerate(streams):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, index)
        if process.stdin is not None:
            streams.append(process.stdin)
            if pending:
                os.set_blocking(process.stdin.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, 'input')
            else:
                process.stdin.close()
        while selector.get_map():
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                timed_out = True; kill_owned(); break
            for key, event in selector.select(min(0.1, remaining_time)):
                stream = key.fileobj
                if key.data == 'input':
                    try:
                        written += os.write(stream.fileno(), pending[written:written+65536])
                    except BlockingIOError:
                        continue
                    except BrokenPipeError:
                        written = len(pending)
                    if written == len(pending):
                        selector.unregister(stream); stream.close()
                else:
                    try: chunk = os.read(stream.fileno(), 65536)
                    except BlockingIOError: continue
                    if not chunk:
                        selector.unregister(stream); stream.close(); continue
                    buffer = buffers[key.data]; available = LIMIT - len(buffer)
                    buffer.extend(chunk[:max(0, available)])
                    if len(chunk) > available:
                        overflow = True; kill_owned(); break
            if overflow: break
        try:
            process.wait(timeout=5 if (timed_out or overflow) else max(0, deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True; kill_owned(); process.wait(timeout=5)
    except BaseException:
        kill_owned()
        process.wait(timeout=5)
        raise
    finally:
        selector.close()
        for stream in streams:
            if not stream.closed: stream.close()
    return {'returncode': process.returncode, 'stdout': bytes(buffers[0]), 'stderr': bytes(buffers[1]),
            'timed_out': timed_out, 'overflow': overflow}


def _atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.source-repair-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(name): os.unlink(name)


def _json(path, value):
    _atomic(path, (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode())


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SourceRepair:
    def __init__(self, repo_root, state_dir, ref, *, runner=None, codex_bin=CODEX):
        self.repo = Path(repo_root).resolve()
        self.state_dir = Path(state_dir).resolve()
        if self.state_dir == self.repo or self.repo in self.state_dir.parents:
            raise ValueError('private source repair state must be outside the checkout')
        self.ref = ref
        self.runner = runner or run_command
        self.codex_bin = codex_bin
        if not isinstance(ref, str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,200}', ref) or '..' in ref:
            raise ValueError('invalid branch ref')
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _directory(self, key):
        if not isinstance(key, str) or not key: raise ValueError('invalid action key')
        return self.state_dir / ('source-' + hashlib.sha256(key.encode()).hexdigest())

    def _run(self, argv, *, timeout=30, env=None, input_bytes=None):
        result = self.runner(argv, cwd=str(self.repo), env=env, input_bytes=input_bytes, timeout=timeout)
        if not isinstance(result, dict) or result.get('timed_out') or result.get('overflow'):
            raise RuntimeError('command timeout, overflow or invalid result')
        if not isinstance(result.get('stdout'), bytes) or not isinstance(result.get('stderr'), bytes):
            raise RuntimeError('invalid command streams')
        return result

    def _git(self, *args):
        result = self._run(['git', *args])
        if result['returncode'] != 0: raise RuntimeError('git command failed')
        return result['stdout'].decode('utf-8', 'strict').strip()

    def _identity(self, sha, *, require_clean=True):
        if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}', sha): raise ValueError('invalid sha')
        if self._git('rev-parse', 'HEAD') != sha or self._git('branch', '--show-current') != self.ref:
            raise RuntimeError('source head or branch mismatch')
        if require_clean and self._git('status', '--porcelain', '--untracked-files=all'):
            raise RuntimeError('source worktree is not clean')

    def _remotes(self):
        for name, expected in REMOTES.items():
            value = self._git('remote', 'get-url', '--push', '--all', name)
            if value != expected: raise RuntimeError('remote push identity mismatch')

    def _remote_heads(self, sha):
        ref = 'refs/heads/' + self.ref
        for remote in REMOTES:
            rows = self._git('ls-remote', '--heads', remote, ref).splitlines()
            if rows != [sha + '\t' + ref]: raise RuntimeError('remote branch readback mismatch')

    def _check(self):
        result = self._run([sys.executable, PROBE, '--source-check'], timeout=30)
        try: doc = json.loads(result['stdout'])
        except (ValueError, UnicodeError): raise RuntimeError('source check produced invalid output') from None
        if not isinstance(doc, dict) or doc.get('reason') != 'incomplete_capture_accepted' or type(doc.get('passed')) is not bool:
            raise RuntimeError('source check did not produce expected evidence')
        if result['returncode'] != (0 if doc['passed'] else 1):
            raise RuntimeError('source check exit disagrees with evidence')
        return doc

    def __call__(self, key, payload, backend):
        directory = self._directory(key)
        directory.mkdir(mode=0o700, parents=False, exist_ok=False)
        sha = payload['target']['source_sha']
        _json(directory / 'intent.json', {'key': key, 'source_sha': sha, 'ref': self.ref})
        self._identity(sha)
        self._remotes()
        probe_sha = _digest(self.repo / PROBE)
        before = self._check()
        if before['passed']: raise RuntimeError('expected source failure was not reproduced')
        _json(directory / 'before.json', before)
        schema = {'type': 'object', 'properties': {'summary': {'type': 'string'}},
                  'required': ['summary'], 'additionalProperties': False}
        _json(directory / 'schema.json', schema)
        schema_path, last_path = directory / 'schema.json', directory / 'last-message.json'
        prompt = ("Repair only scripts/ci/recovery_probe_logic.py so the existing "
                  "scripts/ci/recovery-probe.py --source-check truth table passes. "
                  "Do not modify any other file, commit, push, run network operations, or alter the check. "
                  "Return a short summary.\n")
        secret_markers = ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL')
        env = {name: value for name, value in os.environ.items()
               if not any(marker in name.upper() for marker in secret_markers)}
        argv = [self.codex_bin, 'exec', '--ignore-user-config', '--sandbox', 'workspace-write', '--json',
                '--output-schema', str(schema_path), '--output-last-message', str(last_path), '--cd', str(self.repo), '-']
        deadline = getattr(backend, 'config', {}).get('deadline_epoch')
        worker_timeout = 300 if deadline is None else min(300, int(deadline - time.time() - 30))
        if worker_timeout < 1: raise RuntimeError('source worker deadline exhausted')
        try:
            result = self.runner(argv, cwd=str(self.repo), timeout=worker_timeout, env=env, input_bytes=prompt.encode())
        except Exception as exc:
            _json(directory / 'exit.json', {'status': 'unknown', 'error': type(exc).__name__})
            raise
        if not isinstance(result, dict) or not isinstance(result.get('stdout'), bytes) or not isinstance(result.get('stderr'), bytes):
            _json(directory / 'exit.json', {'status': 'unknown', 'error': 'invalid_result'})
            raise RuntimeError('invalid worker result')
        events, invalid_stream = [], False
        try:
            for line in result['stdout'].splitlines(): events.append(json.loads(line))
        except (ValueError, UnicodeError):
            invalid_stream = True
        # Keep only event types: event payloads may contain commands or environment data.
        event_types = {'thread.started', 'turn.started', 'turn.completed', 'turn.failed',
                       'item.started', 'item.updated', 'item.completed', 'error'}
        safe_events = [{'type': event.get('type') if isinstance(event, dict) and
                        isinstance(event.get('type'), str) and event['type'] in event_types
                        else 'unknown'} for event in events]
        _atomic(directory / 'stdout.jsonl', b''.join((json.dumps(event) + '\n').encode() for event in safe_events))
        _json(directory / 'stderr.json', {'bytes': len(result['stderr']), 'sha256': hashlib.sha256(result['stderr']).hexdigest()})
        _json(directory / 'exit.json', {'returncode': result.get('returncode'), 'timed_out': result.get('timed_out'),
                                         'overflow': result.get('overflow')})
        if result.get('timed_out') is not False or result.get('overflow') is not False:
            raise RuntimeError('worker timeout or output overflow')
        if invalid_stream: raise RuntimeError('worker event stream malformed')
        if result['returncode'] != 0 or not any(isinstance(e, dict) and e.get('type') == 'turn.completed' for e in events):
            raise RuntimeError('worker did not complete')
        try:
            if last_path.is_symlink() or not last_path.is_file() or last_path.stat().st_size > LIMIT:
                raise ValueError('invalid worker output file')
            last = json.loads(last_path.read_text())
        except (OSError, ValueError): raise RuntimeError('worker final output missing') from None
        if not isinstance(last, dict) or set(last) != {'summary'} or not isinstance(last['summary'], str):
            raise RuntimeError('worker final output invalid')
        self._identity(sha, require_clean=False)
        if _digest(self.repo / PROBE) != probe_sha: raise RuntimeError('source check changed')
        if self._git('status', '--porcelain', '--untracked-files=all') != 'M ' + ALLOWED:
            # _git strips leading whitespace, so the only accepted worktree change is unstaged M.
            raise RuntimeError('worker changed files outside allowlist or index')
        if self._git('diff', '--cached', '--name-only'):
            raise RuntimeError('unexpected staged changes')
        after = self._check()
        if not after['passed'] or _digest(self.repo / PROBE) != probe_sha:
            raise RuntimeError('source repair did not pass unchanged check')
        _json(directory / 'after.json', after)
        if callable(getattr(backend, 'ensure_lease', None)): backend.ensure_lease()
        self._git('add', '--', ALLOWED)
        if self._git('diff', '--cached', '--name-only') != ALLOWED:
            raise RuntimeError('staged source differs from allowlist')
        self._git('commit', '-m', 'Fix CI recovery source canary', '--', ALLOWED)
        new_sha = self._git('rev-parse', 'HEAD')
        if not re.fullmatch(r'[0-9a-f]{40}', new_sha) or new_sha == sha:
            raise RuntimeError('repair commit identity invalid')
        self._identity(new_sha)
        if _digest(self.repo / PROBE) != probe_sha: raise RuntimeError('source check changed after commit')
        if callable(getattr(backend, 'ensure_lease', None)): backend.ensure_lease()
        self._git('push', 'local-hub', 'HEAD:refs/heads/' + self.ref)
        self._git('push', '--push-option=ci.skip', 'gitlab', 'HEAD:refs/heads/' + self.ref)
        self._remote_heads(new_sha)
        value = {'status': 'completed', 'source_sha': new_sha, 'base_sha': sha,
                 'source_check_sha256': probe_sha, 'branch': self.ref}
        receipt = backend._action_receipt(key, value)
        if not isinstance(receipt, str) or not receipt: raise RuntimeError('remote repair receipt missing')
        result = {'status': 'completed', 'source_sha': new_sha, 'receipt_path': receipt}
        _json(directory / 'final.json', result)
        return result

    def reconcile(self, key, payload, backend):
        directory = self._directory(key)
        try:
            intent = json.loads((directory / 'intent.json').read_text())
            result = json.loads((directory / 'final.json').read_text())
            if intent != {'key': key, 'source_sha': payload['target']['source_sha'], 'ref': self.ref}:
                return None
            if result.get('status') != 'completed' or not isinstance(result.get('receipt_path'), str) or not result['receipt_path']:
                return None
            self._identity(result['source_sha'])
            self._remotes()
            self._remote_heads(result['source_sha'])
            return result
        except (OSError, ValueError, KeyError, RuntimeError):
            return None
