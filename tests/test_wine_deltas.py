"""Wine delta safety at real PE entry points, using a stopped RPC collaborator.

These checks qualify control, artifact and failure contracts. They do not model
Win32 instruction execution or establish whole-machine restoration.
"""
import base64
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from types import SimpleNamespace

import pytest

from fdisbull.ida_debugger import IDAPEDebugSession
from fdisbull.model import Region
from fdisbull.qemu_machine import MachineContext
from fdisbull.wine_debugger import PEDebugSession
from fdisbull.wine_state import FORMAT, PEStateSessionMixin


BASE = 0x140000000
TEXT = BASE + 0x1000
DATA = BASE + 0x3000
ASLR = 0x10000000
GPRS = ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp',
        'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15')
RANGES = [{'address': hex(DATA), 'length': 16}]


def digest(data):
    return hashlib.sha256(data).hexdigest()


class StoppedRPC:
    def __init__(self, debug, inputs):
        self.debug = debug
        self.inputs = inputs
        self.capabilities = dict(backend='wine-qemu', architecture='x86-64',
            save_states=True, register_edit=True, instruction_trace=True)
        self.lock = threading.RLock()
        self.calls = []
        self.mutations = []
        self.fail_write = False
        self.bad_readback = False
        self.trace_calls = 0
        self.qmp_calls = []
        self.vm = SimpleNamespace(lock=self.lock, machine_stopped=False, gdb=None)
        self.vm.qmp = SimpleNamespace(call=self.qmp_call)
        self.vm.context = MachineContext(self.vm)

    @property
    def machine(self):
        return self.vm.context

    def qmp_call(self, method, params=None):
        self.qmp_calls.append(method)
        return dict(running=not self.vm.machine_stopped)

    def call(self, method, params=None, timeout_ms=30000):
        self.calls.append(method)
        params = params or {}
        debug = self.debug
        if method == 'status':
            return dict(state='stopped', stop_reason=dict(kind='step',
                thread=debug.cpu['thread'], address=debug.cpu['rip']))
        if method == 'registers':
            return deepcopy(debug.cpu)
        if method == 'read':
            offset = params['address'] - DATA - ASLR
            data = bytes(debug.ram[offset:offset + params['length']])
            return dict(data_base64=base64.b64encode(data).decode())
        if method == 'step':
            self.trace_calls += 1
            debug.cpu['rip'] = hex(int(debug.cpu['rip'], 16) + 1)
            debug.cpu['general']['rax'] = hex(int(debug.cpu['general']['rax'], 16) + 7)
            debug.ram[0] += 1
            debug.ram[2] += 3
            return self.call('status')
        if method in ('write', 'setregs'):
            self.mutations.append((method, deepcopy(params)))
            if self.fail_write:
                raise TimeoutError('uncertain native write')
            if method == 'write':
                offset = params['address'] - DATA - ASLR
                value = bytes.fromhex(params['data_hex'])
                debug.ram[offset:offset + len(value)] = value
            else:
                for name, value in params['values'].items():
                    if name in ('rip', 'rflags'):
                        debug.cpu[name] = hex(value)
                    else:
                        debug.cpu['general'][name] = hex(value)
            if self.bad_readback:
                debug.ram[15] = 255
            return {}
        if method == 'close':
            return dict(state='closed')
        raise AssertionError('Unexpected native operation: ' + method)


class Session(PEDebugSession):
    """Keep PE call/read/write/trace wrappers; replace only emulator/storage edges."""
    def __init__(self, tmp_path):
        self.closed = False
        self.run_id = 'owned-wine-run'
        self.version = {'id': 1, 'sha256': 'b' * 64}
        self.static_base, self.runtime_base, self.delta = BASE, BASE + ASLR, ASLR
        self.regions = [Region('.text', TEXT, b'\x90' * 64, True),
                        Region('.data', DATA, bytes(64), False, True)]
        self.module_size = DATA + 64 - BASE
        self.breakpoints, self.watchpoints = {}, {}
        self._layers, self._ram_applied, self._execution, self._execute_guards = [], {}, {}, {}
        self._pending_exec, self._scratch = None, None
        self.mode_id, self._frame = 0, None
        self.cpu = dict(rip=hex(TEXT + ASLR), rflags='0x202', thread=7,
                        general={name: '0x0' for name in GPRS})
        self.ram = bytearray(64)
        self.saved, self.events = {}, []
        self.game_dir = (tmp_path / 'game').resolve()
        self.game_dir.mkdir()
        target = self.game_dir / 'oracle.exe'
        target.write_bytes(b'authored PE input identity, not an executable')
        inputs = {}
        for name in ('qemu', 'kernel', 'initramfs'):
            path = tmp_path / name
            path.write_bytes(('authored ' + name).encode())
            inputs[name] = dict(path=str(path), sha256=digest(path.read_bytes()))
        self.metadata = dict(backend='wine-qemu', runtime_profile='pe64-win32-debug-2',
            source_sha256=digest(target.read_bytes()), version_sha256='b' * 64,
            static_image_base=hex(BASE), runtime_image_base=hex(BASE + ASLR),
            runtime_inputs=inputs, target_pid=11,
            files=[dict(path='oracle.exe', sha256=digest(target.read_bytes()))])
        db = sqlite3.connect(':memory:')
        db.row_factory = sqlite3.Row
        db.executescript('CREATE TABLE debug_runs(id TEXT,version INTEGER);'
            'CREATE TABLE debug_artifacts(id TEXT,run TEXT,kind TEXT,sha256 TEXT,data BLOB,metadata TEXT);'
            "INSERT INTO debug_runs VALUES ('owned-wine-run',1);")
        self.project = SimpleNamespace(db=db, path=tmp_path / 'analysis.fdb',
            meta=dict(source_sha256=self.metadata['source_sha256'], format='PE', entry=TEXT),
            _address=lambda value: int(value, 0) if isinstance(value, str) else value,
            version=lambda value=None: self.version)
        self.rpc = StoppedRPC(self, inputs)
        self._cpu_delta_bind_rpc(self.rpc)
        self.manifest = deepcopy(self.metadata['files'])
        self.load_error = None

    def _layer_setup(self):
        pass

    def _layer_state(self):
        return dict(active=self._layers, ram_applied=self._ram_applied)

    def _event(self, operation, evidence):
        self.events.append((operation, deepcopy(evidence)))

    def _artifact(self, name, kind, data, metadata):
        identifier = 'artifact-' + str(self.project.db.execute('SELECT COUNT(*) FROM debug_artifacts').fetchone()[0])
        sha = digest(data)
        self.project.db.execute('INSERT INTO debug_artifacts VALUES (?,?,?,?,?,?)',
            (identifier, self.run_id, kind, sha, data, json.dumps(metadata)))
        return dict(artifact=identifier, sha256=sha, size=len(data), metadata=deepcopy(metadata))

    def _trace_native(self, count, deadline):
        assert count == 1
        before = self.registers()
        state = self.call('step')
        return dict(events=[dict(address=before['rip'], registers=before,
            bytes='90', ram_bytes='90', execution_bytes='90', active_layers=[],
            layer_generation=0)], complete=True, session=state)

    def save_state(self, name='checkpoint.sav', *, max_bytes=None):
        self._cpu_delta_before_call('capture')
        registers = self.registers()
        metadata = dict(self.metadata, format=FORMAT, registers=registers,
                        disk_manifest=deepcopy(self.manifest))
        native = gzip.compress(b'authored native-machine collaborator' * 64)
        sha = digest(native)
        directory = Path(str(self.project.path) + '.fdisbull-states')
        directory.mkdir(exist_ok=True)
        document = dict(format=FORMAT, machine_sha256=sha, machine_size=len(native),
                        metadata=metadata, host={})
        data = json.dumps(document, sort_keys=True).encode()
        if max_bytes is not None and len(data) + len(native) > max_bytes:
            raise ValueError('Native Anchor Stone exceeds byte budget')
        (directory / (sha + '.mig.gz')).write_bytes(native)
        result = self._artifact(name, 'state', data, metadata)
        result['native_size'] = len(native)
        self.saved[result['artifact']] = deepcopy((self.cpu, self.ram))
        return result

    def _load_native_state(self, artifact):
        if self.load_error:
            raise self.load_error
        self.cpu, self.ram = deepcopy(self.saved[artifact])
        return dict(artifact=artifact, registers=self.registers(), state='stopped')

    def close(self):
        self.closed = True


@pytest.fixture
def debug(tmp_path):
    result = Session(tmp_path)
    yield result
    result.project.db.close()


def start_and_record(debug, count=2):
    debug.cpu_delta_start(RANGES, max_steps=8)
    return debug.cpu_delta_record(count)


def test_selected_pe_projection_uses_aslr_and_counts_native_sidecar(debug):
    initial = deepcopy((debug.cpu, debug.ram))
    start = debug.cpu_delta_start(RANGES, max_steps=4)
    assert start['max_bytes'] == 2 * 1024**3
    assert start['anchor_bytes_used'] == start['anchor']['size'] + start['anchor']['native_size']
    debug.cpu_delta_record(3)
    assert debug.cpu['general']['rax'] == '0x15' and debug.ram[:3] == bytes([3, 0, 9])
    undone = debug.cpu_delta_rewind(3)
    assert (debug.cpu, debug.ram) == initial
    assert undone['partial_restored'] and not undone['resume_safe']
    assert not undone['full_machine_restored'] and debug.cpu_delta_status()['frozen']
    assert any(call[0] == 'write' and call[1]['address'] == DATA + ASLR for call in debug.rpc.mutations)


def test_tampered_unchanged_selected_byte_blocks_before_any_native_write(debug):
    start_and_record(debug)
    debug.ram[15] = 255
    before = deepcopy((debug.cpu, debug.ram))
    with pytest.raises(ValueError):
        debug.cpu_delta_rewind()
    assert debug.rpc.mutations == [] and (debug.cpu, debug.ram) == before


@pytest.mark.parametrize('kind', ['cpu-ram-delta', 'trace'])
def test_artifact_hash_corruption_blocks_before_any_native_write(debug, kind):
    start_and_record(debug)
    debug.project.db.execute('UPDATE debug_artifacts SET data=? WHERE kind=?', (b'corrupted', kind))
    with pytest.raises(ValueError):
        debug.cpu_delta_rewind()
    assert debug.rpc.mutations == []


def test_changed_selected_thread_refuses_before_native_write(debug):
    start_and_record(debug)
    debug.cpu['thread'] = 8
    with pytest.raises(ValueError):
        debug.cpu_delta_rewind()
    assert debug.rpc.mutations == []


def test_hash_valid_wrong_parent_is_not_an_accepted_history(debug):
    start_and_record(debug)
    history = debug._cpu_delta_history
    entry = history['entries'][-1]
    row = debug.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                   (entry['delta']['artifact'],)).fetchone()
    document = json.loads(row['data'])
    document['parent_sha256'] = '0' * 64
    data = json.dumps(document, sort_keys=True, separators=(',', ':')).encode()
    sha = digest(data)
    debug.project.db.execute('UPDATE debug_artifacts SET data=?,sha256=? WHERE id=?',
                            (data, sha, entry['delta']['artifact']))
    # Simulate an internally misproduced receipt to reach the parent-chain
    # invariant independently of the outer byte-hash check.
    entry['delta'].update(sha256=sha, size=len(data))
    with pytest.raises(ValueError):
        debug.cpu_delta_rewind()
    assert debug.rpc.mutations == []


@pytest.mark.parametrize('ranges', [
    [{'address': hex(TEXT), 'length': 8}],
    [{'address': hex(DATA), 'length': 65}],
    [{'address': hex(DATA), 'length': 8, 'cs': 0}],
    [{'address': hex(DATA), 'length': 8}, {'address': hex(DATA + 4), 'length': 8}],
])
def test_non_ram_segmented_and_overlapping_ranges_refuse_before_capture(debug, ranges):
    with pytest.raises(ValueError):
        debug.cpu_delta_start(ranges)
    assert debug.saved == {} and debug.rpc.mutations == []


@pytest.mark.parametrize('attribute,value', [('_layers', ['layer']),
    ('_ram_applied', {DATA: 1}), ('_execution', {TEXT: 0x90}),
    ('_pending_exec', {'scratch': 0x1000}), ('breakpoints', {'bp': TEXT}),
    ('watchpoints', {'watch': {'address': DATA}})])
def test_debugger_control_state_refuses_before_capture(debug, attribute, value):
    setattr(debug, attribute, value)
    with pytest.raises(ValueError):
        debug.cpu_delta_start(RANGES)
    assert debug.saved == {} and debug.rpc.trace_calls == 0


def test_changed_host_input_refuses_undo_before_any_write(debug):
    start_and_record(debug)
    (debug.game_dir / 'oracle.exe').write_bytes(b'changed host input')
    with pytest.raises(ValueError):
        debug.cpu_delta_rewind()
    assert debug.rpc.mutations == []


@pytest.mark.parametrize('name,value', [('rax', 2**64), ('rflags', 2**32), ('rax', -1)])
def test_cpu_register_widths_are_not_silently_truncated(debug, name, value):
    with pytest.raises(ValueError):
        debug._cpu_delta_value(name, value)


def test_reserved_flags_are_validated_before_ram_application(debug):
    # A native interval can expose flag changes that SetThreadContext must not
    # manufacture during undo. Build that valid recording, then reject restore.
    debug.cpu_delta_start(RANGES)
    original = debug._trace_native
    def trace(count, deadline):
        result = original(count, deadline)
        debug.cpu['rflags'] = hex(int(debug.cpu['rflags'], 16) ^ 0x10000)
        return result
    debug._trace_native = trace
    debug.cpu_delta_record()
    before = deepcopy((debug.cpu, debug.ram))
    with pytest.raises(ValueError):
        debug.cpu_delta_rewind()
    assert debug.rpc.mutations == [] and (debug.cpu, debug.ram) == before


def test_capture_budget_preflight_refuses_before_execution(debug):
    debug.cpu_delta_start(RANGES, max_bytes=32768)
    with pytest.raises(ValueError):
        debug.cpu_delta_record(4)
    assert debug.rpc.trace_calls == 0 and debug.rpc.mutations == []


@pytest.mark.parametrize('failure', ['write', 'readback'])
def test_uncertain_undo_closes_and_never_resumes(debug, failure):
    start_and_record(debug)
    debug.rpc.fail_write = failure == 'write'
    debug.rpc.bad_readback = failure == 'readback'
    with pytest.raises((ValueError, TimeoutError, RuntimeError)):
        debug.cpu_delta_rewind()
    assert debug.closed
    assert debug.cpu_delta_status()['frozen']
    assert 'run' not in debug.rpc.calls


@pytest.mark.parametrize('method', ['run', 'step', 'screenshot', 'click', 'write', 'setregs', 'overlay'])
def test_actual_pe_call_gate_blocks_frozen_mutation_and_capture(debug, method):
    start_and_record(debug)
    debug.cpu_delta_rewind()
    calls = list(debug.rpc.calls)
    with pytest.raises(ValueError, match='frozen'):
        PEDebugSession.call(debug, method, {})
    assert debug.rpc.calls == calls


def test_actual_native_save_entry_refuses_frozen_state_before_capture(debug):
    start_and_record(debug)
    debug.cpu_delta_rewind()
    calls = list(debug.rpc.calls)
    with pytest.raises(ValueError, match='frozen'):
        PEStateSessionMixin.save_state(debug)
    assert debug.rpc.calls == calls


@pytest.mark.parametrize('scripted', [False, True])
def test_runtime_code_capture_refuses_partial_state_and_allows_full_recovery(debug, scripted):
    debug.project.arch, debug.project.bits = 'x86', 64
    debug._layer_generation = 0
    start_and_record(debug)
    history = debug.cpu_delta_status()
    assert debug.capture_code(DATA, length=4, view='ram')['artifact']
    assert debug.cpu_delta_status() == history
    debug.cpu_delta_rewind()
    before = deepcopy((debug.cpu, debug.ram))
    calls = list(debug.rpc.calls)
    if scripted:
        result = debug.script({'format': 'fdisbull-script-1', 'steps': [
            {'op': 'capture-code', 'address': DATA, 'length': 4, 'view': 'ram'}]})
        assert not result['ok'] and result['completed_steps'] == 0
        assert 'frozen' in result['error']['message']
    else:
        with pytest.raises(ValueError, match='frozen'):
            debug.capture_code(DATA, length=4, view='ram')
    assert debug.rpc.calls == calls
    assert (debug.cpu, debug.ram) == before
    assert debug.project.db.execute(
        "SELECT COUNT(*) FROM debug_artifacts WHERE kind='code-snapshot'").fetchone()[0] == 1
    assert debug.cpu_delta_status()['frozen'] and not debug.closed
    debug.cpu_delta_recover()
    capture = debug.capture_code(DATA, length=4, view='ram')
    assert capture['artifact']
    assert debug.project.db.execute(
        "SELECT COUNT(*) FROM debug_artifacts WHERE kind='code-snapshot'").fetchone()[0] == 2


@pytest.mark.parametrize('operation', ['layers', 'write-registers'])
def test_high_level_frozen_edit_refusal_preserves_native_recovery(debug, operation):
    debug.rpc.capabilities['code_layers'] = True
    debug._layer_generation = 0
    initial = deepcopy((debug.cpu, debug.ram))
    start_and_record(debug)
    debug.cpu_delta_rewind()
    writes = deepcopy(debug.rpc.mutations)
    before = deepcopy((debug.cpu, debug.ram))
    with pytest.raises(ValueError, match='frozen'):
        if operation == 'layers':
            debug.layers([])
        else:
            debug.write_registers({'rax': {'expected': 7, 'value': 0}})
    assert not debug.closed
    assert debug.rpc.mutations == writes and (debug.cpu, debug.ram) == before
    assert debug.cpu_delta_status()['frozen']
    recovered = debug.cpu_delta_recover()
    assert recovered['full_native_anchor_loaded']
    assert not recovered['history']['frozen']
    assert (debug.cpu, debug.ram) == initial


def test_actual_pe_script_cannot_execute_after_partial_undo(debug):
    start_and_record(debug)
    debug.cpu_delta_rewind()
    trace_calls = debug.rpc.trace_calls
    result = debug.script({'format': 'fdisbull-script-1', 'steps': [{'op': 'trace', 'count': 1}]})
    assert not result['ok']
    assert debug.rpc.trace_calls == trace_calls
    assert debug.cpu_delta_status()['frozen']


@pytest.mark.parametrize('operation,params', [
    ('resume', {}), ('pause', {}), ('step', {}), ('run', {}),
    ('write_memory', dict(address=DATA, data_hex='01', expected_hex='00')),
    ('write_registers', dict(registers={'rax': {'expected': 0, 'value': 1}})),
    ('breakpoint', dict(address=TEXT)),
])
def test_cached_outer_machine_handle_cannot_mutate_frozen_partial_state(debug, operation, params):
    cached = debug.machine
    start_and_record(debug)
    debug.cpu_delta_rewind()
    before = list(debug.rpc.qmp_calls)
    with pytest.raises(ValueError, match='frozen'):
        getattr(cached, operation)(**params)
    assert debug.rpc.qmp_calls == before


def test_full_native_load_clears_guard_only_after_successful_readback(debug):
    start_and_record(debug)
    anchor = debug.cpu_delta_status()['anchor']['artifact']
    debug.cpu_delta_rewind()
    debug.load_error = ValueError('deliberate native restore refusal')
    with pytest.raises(ValueError, match='deliberate'):
        debug.load_state(anchor)
    assert debug.cpu_delta_status()['frozen']
    debug.load_error = None
    debug.load_state(anchor)
    assert not debug.cpu_delta_status()['frozen']
    assert debug.cpu['general']['rax'] == '0x0' and debug.ram == bytearray(64)
    assert not debug.cpu_delta_status()['valid']


def test_recovery_uses_verified_native_anchor_and_clears_guard(debug):
    initial = deepcopy((debug.cpu, debug.ram))
    start_and_record(debug)
    debug.cpu_delta_rewind()
    result = debug.cpu_delta_recover()
    assert result['full_native_anchor_loaded']
    assert not result['history']['frozen']
    assert (debug.cpu, debug.ram) == initial


def test_corrupt_native_anchor_sidecar_does_not_clear_frozen_guard(debug):
    start_and_record(debug)
    debug.cpu_delta_rewind()
    sidecar = next(Path(str(debug.project.path) + '.fdisbull-states').glob('*.mig.gz'))
    sidecar.write_bytes(sidecar.read_bytes() + b'corrupt')
    with pytest.raises(ValueError):
        debug.cpu_delta_recover()
    assert debug.cpu_delta_status()['frozen']


def test_native_reload_rechecks_actual_runtime_bytes_before_replacing_vm(debug):
    anchor = debug.save_state()
    Path(debug.rpc.inputs['qemu']['path']).write_bytes(b'replacement executable')
    def unexpected():
        pytest.fail('Runtime identity mismatch reached VM replacement')
    debug.rpc.close = unexpected
    with pytest.raises(ValueError, match='identity|hash|input'):
        PEStateSessionMixin._load_native_state(debug, anchor['artifact'])


def test_ida_deltas_are_not_admitted_or_enabled_in_scripts():
    session = IDAPEDebugSession.__new__(IDAPEDebugSession)
    session.closed = False
    session.rpc = SimpleNamespace(capabilities=dict(save_states=True, register_edit=True))
    with pytest.raises(ValueError):
        session._cpu_delta_native()
    assert not {'delta-start', 'delta-record', 'delta-rewind', 'delta-recover', 'delta-status'} & session.script_operations


@pytest.fixture
def delta_clock(monkeypatch):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr('time.monotonic', lambda: clock.now)
    return clock


def test_expired_shared_deadline_refuses_pe_rpc_before_dispatch(debug, delta_clock):
    debug._rpc_deadline = delta_clock.now - 0.001
    calls = list(debug.rpc.calls)
    with pytest.raises(TimeoutError, match='budget|deadline'):
        debug.call('status')
    assert debug.rpc.calls == calls
    assert not debug.closed


@pytest.mark.parametrize('requested,expected', [(30000, 125), (50, 50)])
def test_pe_rpc_timeout_respects_remaining_shared_budget(debug, delta_clock, monkeypatch, requested, expected):
    debug._rpc_deadline = delta_clock.now + 0.125
    native_call = debug.rpc.call
    observed_timeouts = []

    def observed_call(method, params=None, timeout_ms=30000):
        observed_timeouts.append(timeout_ms)
        return native_call(method, params, timeout_ms=timeout_ms)

    monkeypatch.setattr(debug.rpc, 'call', observed_call)
    assert debug.call('status', timeout_ms=requested)['state'] == 'stopped'
    assert observed_timeouts == [expected]


@pytest.mark.parametrize('scripted', [False, True])
def test_post_step_deadline_expiry_never_dispatches_more_rpcs_or_claims_success(
        debug, delta_clock, monkeypatch, scripted):
    initial = deepcopy((debug.cpu, debug.ram))
    debug.cpu_delta_start(RANGES)
    native_call = debug.rpc.call
    dispatches = []

    def completed_step_after_deadline(method, params=None, timeout_ms=30000):
        dispatches.append((method, delta_clock.now, getattr(debug, '_rpc_deadline', None)))
        result = native_call(method, params, timeout_ms=timeout_ms)
        if method == 'step':
            # Model an already-dispatched native step returning after the
            # operation budget. Later RPCs still must not be dispatched.
            delta_clock.now += 0.125
        return result

    monkeypatch.setattr(debug.rpc, 'call', completed_step_after_deadline)
    if scripted:
        result = debug.script({'format': 'fdisbull-script-1', 'steps': [
            {'op': 'delta-record', 'count': 1}]}, timeout_ms=100)
        assert not result['ok']
        assert result['completed_steps'] == 0
        assert result['error']['type'] == 'TimeoutError'
    else:
        with pytest.raises(TimeoutError, match='budget|deadline'):
            debug.cpu_delta_record(timeout_ms=100)
    assert not [(method, now, deadline) for method, now, deadline in dispatches
                if deadline is not None and now >= deadline]
    assert debug.rpc.trace_calls == 1
    assert debug._rpc_deadline is None
    status = debug.cpu_delta_status()
    assert not status['valid'] and status['cursor'] == 0
    assert not debug.closed
    assert debug.project.db.execute(
        "SELECT COUNT(*) FROM debug_artifacts WHERE kind='cpu-ram-delta'").fetchone()[0] == 0
    # The failed recording retained its complete Anchor Stone. Once the
    # deadline scope exits, explicit recovery can safely restore it.
    recovered = debug.cpu_delta_recover()
    assert recovered['full_native_anchor_loaded']
    assert not recovered['history']['frozen']
    assert (debug.cpu, debug.ram) == initial

