"""Launch and control an explicitly patched, separate ScummVM Z-code engine.

The native build is described in docs/SCUMMVM_ZCODE_BACKEND.md. Stock ScummVM
cannot satisfy this protocol. Game text, memory and traces remain private.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import threading
import time

from .scummvm_rpc import ScummVMError, ScummVMRPC
from .zmachine import inspect_story_bytes


def _int(value, name, low=0, high=2**53-1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


class ScummVMZCodeSession:
    """One owned native interpreter. Does not invoke the in-house word16 VM."""

    def __init__(self, executable, story, *, runtime_parent, game_id='zork1',
                 extra_path=None, boot_timeout_ms=30000, on_spawn=None):
        path = Path(story).expanduser()
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024*1024:
            raise ValueError('Expected a regular raw v3 story of at most 1 MiB')
        with path.open('rb') as stream:
            raw = stream.read(1024*1024+1)
        if len(raw) > 1024*1024:
            raise ValueError('Story changed or exceeded its input bound')
        self.info = inspect_story_bytes(raw)
        if self.info['version'] != 3:
            raise ValueError('This native profile only supports Z-machine v3')
        image = raw[:self.info['declared_bytes']]
        self.closed, self.rpc, self.temporary = False, None, None
        self.revision = -1
        self._lock = threading.RLock()
        self._deadline = None
        parent = Path(runtime_parent).expanduser().resolve(strict=True)
        binary = Path(executable).expanduser().resolve(strict=True)
        self.metadata = {'backend': 'scummvm-zcode', 'execution_context': 'zmachine-v3',
                         'replacement_engine': True, 'original_x86_executed': False,
                         'story_sha256': sha256(raw).hexdigest(),
                         'story_version': self.info['version'], 'story_release': self.info['release'],
                         'story_serial': self.info['serial_text'],
                         'declared_image_sha256': sha256(image).hexdigest(),
                         'runtime_sha256': sha256(binary.read_bytes()).hexdigest(),
                         'intended_upstream_pin': '750f2373fb100efe08c6444e36b68c01387fc307',
                         'profile': 'glk-zcode-v3', 'text_only': True,
                         'source_binding': 'pending', 'bytecode_interpreter': 'ScummVM',
                         'extra_path': str(extra_path) if extra_path is not None else None,
                         'source_provenance': 'caller-owned bytes; authenticity not established',
                         'runtime_provenance': 'caller-selected executable; hash identity is not build attestation'}
        try:
            self.temporary = tempfile.TemporaryDirectory(prefix='fdisbull-zcode-', dir=parent)
            root = Path(self.temporary.name)
            inputs = root / 'inputs'
            inputs.mkdir(mode=0o700)
            self.staged_story = inputs / 'story.z3'
            self.staged_story.write_bytes(raw)
            self.staged_story.chmod(0o400)
            self._deadline = time.monotonic() + boot_timeout_ms / 1000
            self.rpc = ScummVMRPC(binary, inputs, game_id=game_id, engine='glk',
                                  runtime_parent=root, extra_path=extra_path,
                                  boot_timeout_ms=boot_timeout_ms, on_spawn=on_spawn)
            hello = self.rpc.hello
            needed = {'state.get', 'source.read', 'memory.read', 'run', 'step',
                      'break.add', 'break.remove', 'input', 'text.get', 'trace.get'}
            if (not needed <= set(hello['capabilities']) or
                    type(hello.get('source_size')) is not int or hello['source_size'] != len(image)):
                raise ScummVMError('Z-code native source extent/capabilities do not match')
            # Compare actual native bytes captured immediately after loadMemory,
            # before header adaptation. A hello echo is not source verification.
            deadline = self._deadline
            first = self.state()
            for offset in range(0, len(image), 4096):
                remaining = int((deadline-time.monotonic())*1000)
                if remaining < 1:
                    raise TimeoutError('Native source readback exhausted its host budget')
                length = min(4096, len(image)-offset)
                observed = self._read('source.read', offset, length, first['revision'], remaining)
                if observed != image[offset:offset+length]:
                    raise ScummVMError('Native loaded story differs from the selected source')
            if self.state()['revision'] != first['revision']:
                raise ScummVMError('Interpreter advanced during source readback')
            self.metadata.update(source_binding='all declared original bytes compared',
                                 native_source_bytes=len(image), file_padding_executed=False,
                                 game_id=self.rpc.game_id, pid=self.rpc.process.pid)
            self._deadline = None
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @contextmanager
    def _budget(self, timeout_ms):
        """One wall-time allowance for the entire compound operation."""
        _int(timeout_ms, 'timeout_ms', 100, 600000)
        previous = self._deadline
        deadline = time.monotonic() + timeout_ms / 1000
        self._deadline = min(previous, deadline) if previous is not None else deadline
        try:
            yield
        finally:
            self._deadline = previous

    def _remaining(self, cap):
        if self._deadline is None:
            return cap
        remaining = int((self._deadline - time.monotonic()) * 1000)
        if remaining < 1:
            raise TimeoutError('Shared Z-code operation budget expired')
        return min(cap, remaining)

    def _call(self, op, params=None, *, timeout_ms=10000):
        if self.closed or self.rpc is None:
            raise ScummVMError('Z-code session is closed')
        try:
            if sha256(self.staged_story.read_bytes()).hexdigest() != self.metadata['story_sha256']:
                raise ScummVMError('Private input image changed')
            return self.rpc.call(op, params, timeout_ms=self._remaining(timeout_ms))
        except BaseException:
            self.close()
            raise

    def _invalid(self, message):
        self.close()
        raise ScummVMError(message)

    def state(self):
        """Passive state; no parser command, opcode read or stack pop."""
        with self._lock:
            s = self._call('state.get').get('state')
            try:
                if not isinstance(s, dict) or s.get('paused') is not True:
                    raise ValueError('Native state is not confirmed paused')
                if s.get('phase') not in ('before_opcode', 'after_opcode', 'input_pending', 'exited'):
                    raise ValueError('Unknown native execution phase')
                rev = _int(s.get('revision'), 'revision')
                _int(s.get('pc'), 'pc', 0, self.info['declared_bytes'])
                _int(s.get('input_request'), 'input_request')
                _int(s.get('input_max'), 'input_max', 0, 4096)
                if s.get('input_kind') not in ('', 'line', 'char'):
                    raise ValueError('Invalid input request kind')
                if s['phase'] == 'input_pending' and (s['input_request'] < 1 or not s['input_kind']):
                    raise ValueError('Input boundary has no request identity')
                if s['phase'] != 'input_pending' and (s['input_request'] or s['input_kind'] or s.get('input_queued')):
                    raise ValueError('Non-input state retains an input request')
                if type(s.get('input_queued')) is not bool or type(s.get('faulted')) is not bool:
                    raise ValueError('Missing typed queue/fault state')
                if rev < self.revision:
                    raise ValueError('Native revision moved backwards')
                self.revision = rev
                return {**s, 'backend': 'scummvm-zcode', 'address_space': 'story-byte',
                        'original_x86_executed': False}
            except (TypeError, ValueError) as e:
                self._invalid(str(e))

    def _read(self, op, offset, length, revision, timeout_ms=10000):
        params = {'offset': offset, 'length': length, 'revision': revision}
        r = self._call(op, params, timeout_ms=timeout_ms)
        value = r.get('hex')
        if (any(type(r.get(k)) is not type(v) or r.get(k) != v for k,v in params.items()) or
                not isinstance(value,str) or len(value)!=2*length or
                any(c not in '0123456789abcdef' for c in value)):
            self._invalid('Invalid native memory identity/range/content')
        return bytes.fromhex(value)

    def memory(self, offset, length=16):
        with self._lock:
            _int(offset, 'offset', 0, self.info['declared_bytes']-1)
            _int(length, 'length', 1, 4096)
            if offset+length > self.info['declared_bytes']:
                raise ValueError('Read exceeds declared story memory')
            s = self.state()
            return self._read('memory.read', offset, length, s['revision'])

    def breakpoint(self, pc, *, expected_hex=None):
        with self._lock:
            _int(pc, 'pc', 64, self.info['declared_bytes']-1)
            if expected_hex is None:
                expected_hex = self.memory(pc, 1).hex()
            if (not isinstance(expected_hex,str) or not 2<=len(expected_hex)<=32 or len(expected_hex)%2 or
                    any(c not in '0123456789abcdef' for c in expected_hex)):
                raise ValueError('Expected 1..16 exact guard bytes as lowercase hex')
            r = self._call('break.add', {'pc': pc, 'expected_hex': expected_hex})
            if type(r.get('breakpoint_id')) is not int or r['breakpoint_id']<1 or r.get('pc')!=pc:
                self._invalid('Native breakpoint registration was not confirmed')
            return {**r, 'scope':'before actual Z-code operand loading', 'reachability':'not_established'}

    def delete_breakpoint(self, identifier):
        with self._lock:
            _int(identifier, 'breakpoint_id', 1)
            r = self._call('break.remove', {'breakpoint_id':identifier})
            if r.get('removed') is not True:
                self._invalid('Native breakpoint removal was not confirmed')
            return r

    def output(self):
        """Drain captured narrative/status characters once, without running VM."""
        with self._lock:
            r = self._call('text.get')
            events = r.get('events')
            if not isinstance(events,list) or len(events)>16384:
                self._invalid('Invalid native text events')
            for e in events:
                if (not isinstance(e,dict) or type(e.get('window')) is not int or
                        not isinstance(e.get('text'),str) or len(e['text'])>4):
                    self._invalid('Invalid native text event')
            return {'text': ''.join(e['text'] for e in events if e['window']==0),
                    'events': events, 'scope':'text-only screen stream, not pixels or all GLK UI'}

    def _execute(self, op, count, timeout_ms):
        _int(count, 'count', 1, 1000000)
        _int(timeout_ms, 'timeout_ms', 100, 600000)
        with self._lock, self._budget(timeout_ms):
            s = self.state()
            if s['faulted'] or s['phase']=='exited':
                raise ValueError('Native session is faulted or exited')
            remaining = self._remaining(timeout_ms)
            if remaining < 75:
                raise TimeoutError('Z-code budget expired before execution dispatch')
            r = self._call(op, {'max_instructions':count, 'max_ms':remaining-50}, timeout_ms=remaining)
            stop = r.get('stop')
            try:
                if (not isinstance(stop,dict) or stop.get('paused') is not True or
                        stop.get('reason') not in ('budget','breakpoint','input_pending','host_timeout',
                                                   'pause','quit','code_changed','unsupported_save_restore')):
                    raise ValueError('Native execution omitted a structured stop')
                _int(stop.get('completed_dispatches'), 'completed_dispatches', 0, count)
                rev = _int(stop.get('revision'), 'revision', s['revision'])
                if stop.get('phase') not in ('before_opcode','after_opcode','input_pending','exited'):
                    raise ValueError('Invalid native stop phase')
                if (stop['reason']=='quit') != (stop['phase']=='exited'):
                    raise ValueError('Exit reason/phase mismatch')
                _int(stop.get('pc'), 'pc', 0, self.info['declared_bytes'])
                self.revision = rev
            except (TypeError,ValueError) as e:
                self._invalid(str(e))
            return {**stop, **self.output(), 'starting_dispatch_completed':None,
                    'unit':'completed ScummVM Z-code dispatch', 'original_x86_executed':False}

    def run(self, *, max_instructions=100000, timeout_ms=10000):
        return self._execute('run', max_instructions, timeout_ms)

    def step(self, *, timeout_ms=10000):
        return self._execute('step', 1, timeout_ms)

    def command(self, text, *, expected_revision, max_instructions=100000, timeout_ms=10000):
        with self._lock, self._budget(timeout_ms):
            _int(expected_revision,'expected_revision')
            _int(max_instructions,'max_instructions',1,1000000)
            _int(timeout_ms,'timeout_ms',100,600000)
            s = self.state()
            if s['revision']!=expected_revision:
                raise ValueError('Stale input revision; command was not submitted')
            if s['phase']!='input_pending' or s['input_queued'] or s['input_request']<1:
                raise ValueError('No fresh native input request')
            if (not isinstance(text,str) or len(text)>s['input_max'] or
                    any(ord(c)<32 or ord(c)>126 for c in text) or
                    s['input_kind']=='char' and len(text)!=1):
                raise ValueError('Input must fit the native request and contain printable ASCII')
            r = self._call('input', {'text':text, 'request':s['input_request'], 'revision':s['revision']})
            if (r.get('queued') is not True or r.get('consumed') is not False or
                    type(r.get('revision')) is not int or r['revision'] <= s['revision'] or
                    type(r.get('request')) is not int or r['request'] != s['input_request']):
                self._invalid('Native input queue receipt missing')
            try:
                result = self.run(max_instructions=max_instructions,timeout_ms=timeout_ms)
            except BaseException:
                # The command is already queued; never leave an unknown prefix
                # available for a caller to replay as a second command.
                self.close()
                raise
            return {**result, 'input_receipt':r}

    def trace(self):
        with self._lock:
            r = self._call('trace.get')
            if (not isinstance(r.get('events'),list) or len(r['events'])>2048 or
                    type(r.get('dropped')) is not int or r['dropped']<0):
                self._invalid('Invalid native trace')
            for event in r['events']:
                if not isinstance(event, dict) or event.get('kind') not in ('before', 'after'):
                    self._invalid('Invalid native trace event')
                pos = event.get('position')
                if (not isinstance(pos, dict) or
                        any(type(pos.get(k)) is not int or pos[k] < 0
                            for k in ('pc', 'span_id', 'parent_span_id')) or
                        pos['pc'] >= self.info['declared_bytes'] or pos['span_id'] < 1 or
                        type(event.get('revision')) is not int or event['revision'] < 0):
                    self._invalid('Invalid native trace position')
            return {**r, 'whole_run_complete':False, 'unit':'actual Z-code before/after dispatch spans'}

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.rpc is not None:
                self.rpc.close()
        finally:
            if self.temporary is not None:
                self.temporary.cleanup()
                self.temporary = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',required=True)
    parser.add_argument('--story',required=True)
    parser.add_argument('--runtime-parent',required=True)
    parser.add_argument('--extra-path')
    parser.add_argument('--game-id',default='zork1')
    parser.add_argument('--commands',help='Private JSON array of command strings')
    parser.add_argument('--max-instructions',type=int,default=100000)
    args = parser.parse_args()
    commands = []
    if args.commands:
        with Path(args.commands).open('rb') as stream:
            encoded = stream.read(2*1024*1024+1)
        if len(encoded)>2*1024*1024:
            parser.error('Command file exceeds 2 MiB')
        commands = json.loads(encoded)
    if not isinstance(commands,list) or len(commands)>1024 or any(not isinstance(x,str) for x in commands):
        parser.error('Commands must be a bounded JSON array of strings')
    with ScummVMZCodeSession(args.executable,args.story,runtime_parent=args.runtime_parent,
                            game_id=args.game_id,extra_path=args.extra_path) as session:
        result = session.run(max_instructions=args.max_instructions)
        print(json.dumps({'metadata':session.metadata,'result':result}),flush=True)
        for command in commands:
            state = session.state()
            result = session.command(command,expected_revision=state['revision'],
                                     max_instructions=args.max_instructions)
            print(json.dumps({'result':result}),flush=True)


if __name__=='__main__':
    main()
