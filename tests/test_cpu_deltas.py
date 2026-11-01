"""Selected-state delta contracts against a stopped RAM/register collaborator.

These are control/provenance tests, not proof of native device restoration.
"""
import base64
from copy import deepcopy
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest

from fdisbull.debug_cpu_deltas import CpuDeltaSessionMixin
from fdisbull.debug_rewind import RewindSessionMixin


def cpu():
    return dict(cpu_mode='real', instruction_pointer='0x0', flags='0x202',
                general={name: '0x0' for name in ('eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp')},
                segments={name: '0x1000' for name in ('cs', 'ds', 'es', 'ss', 'fs', 'gs')})


class Session(CpuDeltaSessionMixin, RewindSessionMixin):
    def __init__(self):
        self.closed = False
        self.run_id, self.version = 'owned-run', {'id': 1}
        self.metadata = dict(source_sha256='source', version_sha256='version', emulator_sha256='backend',
                             runtime_profile='real-normal-v1', runtime_load_segment=0x1100, game_dir='/private/game')
        self.static_base, self.module_size, self.delta = 0x10000, 64, 0x1000
        self.cpu, self.ram = cpu(), bytearray(64)
        self.manifest = [{'path': 'target.exe', 'sha256': 'original'}]
        self.rpc = SimpleNamespace(capabilities={'save_states': True, 'register_edit': True,
            'input': {'keyboard': 'controller'}})
        db = sqlite3.connect(':memory:')
        db.row_factory = sqlite3.Row
        db.executescript('CREATE TABLE debug_runs(id TEXT,version INTEGER);'
            'CREATE TABLE debug_artifacts(id TEXT,run TEXT,kind TEXT,sha256 TEXT,data BLOB,metadata TEXT);'
            "INSERT INTO debug_runs VALUES ('owned-run',1);")
        self.project = SimpleNamespace(db=db, _dos_parse_address=self.parse)
        self.events, self.calls, self.saved, self.mutations = [], [], {}, []
        self.trace_calls = 0
        self._layers, self._hooks, self._ram_applied = [], {}, {}
        self.mouse_pending = False
        self.keyboard_pending, self.keyboard_owned = [], []
        self.trace_change = lambda document: None
        self.trace_effect = lambda: None
        self.fail_mutation = None
        self.bad_readback = False

    @staticmethod
    def parse(address, cs=None):
        if ':' in str(address):
            segment, offset = address.split(':')
            return int(segment, 16) * 16 + int(offset, 16), int(segment, 16)
        value = int(address, 16) if isinstance(address, str) else address
        return (cs * 16 + value if cs is not None else value), cs

    def _event(self, operation, evidence):
        self.events.append((operation, deepcopy(evidence)))

    def _disk_manifest(self):
        return deepcopy(self.manifest)

    def _layer_state(self):
        return dict(active=self._layers, ram_applied=self._ram_applied)

    def call(self, method, params=None):
        self._cpu_delta_before_call(method, params)
        self._rewind_before_call(method)
        self.calls.append(method)
        params = params or {}
        if method == 'session.status':
            return {'state': 'stopped'}
        if method == 'input.mouse.state':
            return {'mouse': {'release_pending': self.mouse_pending}}
        if method in ('memory.write', 'state.set_register'):
            self.mutations.append((method, deepcopy(params)))
            if len(self.mutations) == self.fail_mutation:
                raise TimeoutError('unknown write outcome')
            if method == 'memory.write':
                # Match the native wire contract, including leading zeroes.
                assert len(params['address']['offset']) == 10
                assert params['address']['offset'] == f"0x{int(params['address']['offset'], 16):08X}"
                data = base64.b64decode(params['data_base64'])
                address = int(params['address']['offset'], 16) - self.static_base - self.delta
                old = bytes(self.ram[address:address + len(data)])
                if hashlib.sha256(old).hexdigest() != params['expected_sha256']:
                    raise ValueError('CAS hash mismatch')
                self.ram[address:address + len(data)] = data
            else:
                name = params['register'].lower()
                value = hex(params['value'])
                if name == 'eip':
                    self.cpu['instruction_pointer'] = value
                elif name == 'flags':
                    self.cpu['flags'] = value
                else:
                    self.cpu['general' if name.startswith('e') else 'segments'][name] = value
            if self.bad_readback:
                self.ram[-1] = 255
        return {}

    def keyboard_state(self):
        self.call('input.keyboard.state')
        return {'keyboard': {'pending_events': self.keyboard_pending, 'owned_keys': self.keyboard_owned}}

    def registers(self):
        self.call('state.get_registers')
        return deepcopy(self.cpu)

    def memory(self, address, *, length, cs=None):
        self.call('memory.read')
        address, _ = self.parse(address, cs)
        offset = address - self.static_base
        data = bytes(self.ram[offset:offset + length])
        return dict(hex=data.hex(), sha256=hashlib.sha256(data).hexdigest(),
                    address=dict(space='linear', offset=hex(address + self.delta)))

    def _artifact(self, name, kind, data, metadata):
        identifier = 'artifact-' + str(self.project.db.execute('SELECT COUNT(*) FROM debug_artifacts').fetchone()[0])
        digest = hashlib.sha256(data).hexdigest()
        self.project.db.execute('INSERT INTO debug_artifacts VALUES (?,?,?,?,?,?)',
            (identifier, self.run_id, kind, digest, data, json.dumps(metadata)))
        return dict(artifact=identifier, sha256=digest, size=len(data), metadata=deepcopy(metadata))

    def save_state(self, name, *, max_bytes):
        self.call('state.save')
        data = json.dumps(dict(cpu=self.cpu, ram=list(self.ram))).encode()
        if len(data) > max_bytes:
            raise ValueError('Native state exceeds remaining rewind byte budget')
        artifact = self._artifact(name, 'state', data,
            dict(registers=deepcopy(self.cpu), disk_manifest=deepcopy(self.manifest), **self.metadata))
        self.saved[artifact['artifact']] = deepcopy((self.cpu, self.ram, self.manifest))
        return artifact

    def load_state(self, artifact):
        with self._cpu_delta_full_load():
            saved_cpu, ram, manifest = self.saved[artifact]
            if manifest != self.manifest:
                raise ValueError('Mounted game files differ')
            self.call('state.load')
            self.cpu, self.ram = deepcopy(saved_cpu), deepcopy(ram)
            self.call('layers.configure')  # Native-load restoration is permitted while frozen.
            self._cpu_delta_loaded()
            return dict(artifact=artifact, registers=self.registers())

    def trace(self, name='trace.json', *, count, timeout_ms=10000, fast_forward=True):
        self.call('execution.continue')
        self.trace_calls += 1
        before = deepcopy(self.cpu)
        self.cpu['instruction_pointer'] = hex(int(self.cpu['instruction_pointer'], 16) + 1)
        self.cpu['general']['eax'] = hex(int(self.cpu['general']['eax'], 16) + 7)
        # Two separated changed runs; the unmodified byte at offset 1 must also be guarded.
        self.ram[0] += 1
        self.ram[2] += 3
        self.trace_effect()
        def event(snapshot, completed):
            return dict(address=dict(space='segmented', segment=snapshot['segments']['cs'],
                        offset=snapshot['instruction_pointer']), observation={'instruction_completed': completed})
        document = dict(version=1, requested_count=2, complete=True,
            events=[event(before, None), event(self.cpu, False)],
            run=dict(run=self.run_id, outcome='pause', timed_out=False, hook_hits=[],
                     session=dict(state='stopped', stop_reason={'kind': 'pause'})))
        self.trace_change(document)
        return self._artifact(name, 'trace', json.dumps(document).encode(), {})

    def close(self):
        self.call('session.close')
        self.closed = True


RANGES = [{'address': '1000:0000', 'length': 8}]


@pytest.mark.parametrize('ranges', [
    [], {}, [RANGES[0]] * 65, [None], [{'address': '1000:0000'}],
    [{'address': '1000:0000', 'length': True}],
    [{'address': '1000:0000', 'length': 0}],
    [{'address': '1000:0000', 'length': 65537}],
    [{'address': '1000:0000', 'length': 32769}] * 2,
    [{'address': '$position', 'length': 0}],
    ['$range', {'address': '1000:0000', 'length': 0}],
])
def test_invalid_later_literal_delta_ranges_reject_before_script_execution(ranges):
    from fdisbull.debug_script import execute_script
    debug = Session()
    before = deepcopy((debug.cpu, debug.ram))
    with pytest.raises(ValueError, match='CPU delta|range length'):
        execute_script(debug, {'format': 'fdisbull-script-1', 'steps': [
            {'op': 'trace', 'count': 2}, {'op': 'delta-start', 'ranges': ranges}]})
    assert (debug.cpu, debug.ram) == before
    assert debug.trace_calls == 0 and debug.calls == []
    assert debug.project.db.execute('SELECT COUNT(*) FROM debug_artifacts').fetchone()[0] == 0


def test_delta_range_references_defer_only_dynamic_values():
    from fdisbull.debug_script import execute_script, validate_script
    for ranges in ('$ranges', ['$range'], [{'address': '$position', 'length': '$length'}]):
        assert validate_script({'format': 'fdisbull-script-1', 'steps': [
            {'op': 'delta-start', 'ranges': ranges}]})
        debug = Session()
        result = execute_script(debug, {'format': 'fdisbull-script-1', 'steps': [
            {'op': 'delta-start', 'ranges': ranges}]}, bindings={
                'ranges': RANGES, 'range': RANGES[0], 'position': '1000:0000', 'length': 8})
        assert result['ok'], result
        assert debug.cpu_delta_status()['ranges'] == [{'address': '0x10000', 'length': 8}]


def test_dos_script_rejects_wine_only_byte_budget_before_execution():
    from fdisbull.debug_script import execute_script, validate_script
    script = {'format': 'fdisbull-script-1', 'steps': [
        {'op': 'trace', 'count': 2},
        {'op': 'delta-start', 'ranges': RANGES, 'max_bytes': 512 * 1024**2}]}
    assert validate_script(script)  # Backend-independent storage can author PE routes.
    debug = Session()
    initial = deepcopy((debug.cpu, debug.ram))
    with pytest.raises(ValueError, match='max_bytes'):
        execute_script(debug, script)
    assert (debug.cpu, debug.ram) == initial
    assert debug.calls == [] and debug.trace_calls == 0
    assert debug.project.db.execute('SELECT COUNT(*) FROM debug_artifacts').fetchone()[0] == 0


def test_records_only_net_deltas_and_composes_multiple_reverse_intervals():
    debug = Session()
    initial = deepcopy((debug.cpu, debug.ram))
    start = debug.cpu_delta_start(RANGES, max_steps=4)
    assert start['anchor_bytes_used'] > 0 and start['delta_bytes_used'] == 0
    assert start['ranges'] == [{'address': '0x10000', 'length': 8}]
    recorded = debug.cpu_delta_record(3)
    assert recorded['cursor'] == recorded['recorded_count'] == 3
    assert len(debug.saved) == 1
    assert [entry['changed_bytes'] for entry in recorded['records']] == [2, 2, 2]
    assert debug.cpu['general']['eax'] == '0x15'
    row = debug.project.db.execute("SELECT data FROM debug_artifacts WHERE kind='cpu-ram-delta' LIMIT 1").fetchone()
    document = json.loads(row['data'])
    assert document['registers'] == {'eax': {'before': 0, 'after': 7}, 'eip': {'before': 0, 'after': 1}}
    assert len(document['memory']) == 2 and 'initial_ram' not in document
    undone = debug.cpu_delta_rewind(2)
    assert undone['cursor'] == 1 and undone['partial_restored'] and not undone['resume_safe']
    assert debug.cpu['general']['eax'] == '0x7' and debug.ram[:3] == bytes([1, 0, 3])
    debug.cpu_delta_rewind()
    assert (debug.cpu, debug.ram) == initial and debug.trace_calls == 3
    assert debug.cpu_delta_status()['frozen'] and debug.cpu_delta_status()['valid']


def test_returned_receipts_do_not_mutate_history_or_trusted_anchor():
    debug = Session(); start = debug.cpu_delta_start(RANGES); recorded = debug.cpu_delta_record(2)
    start['anchor']['artifact'] = 'wrong'
    start['ranges'][0]['length'] = 64
    recorded['records'][0]['delta']['sha256'] = '0' * 64
    recorded['history']['anchor']['artifact'] = 'wrong'
    debug.cpu_delta_rewind(2)
    recovered = debug.cpu_delta_recover()
    assert recovered['full_native_anchor_loaded'] and not recovered['history']['frozen']
    assert not recovered['history']['valid'] and debug.cpu['general']['eax'] == '0x0'
    assert len(debug.saved) == 1


@pytest.mark.parametrize('method', ['execution.continue', 'memory.write', 'state.set_register',
    'input.keyboard.press', 'input.mouse.click', 'layers.configure', 'breakpoints.create',
    'video.screenshot', 'video.probe', 'video.capture', 'state.save', 'state.load', 'unknown.future'])
def test_frozen_history_blocks_mutation_capture_and_raw_load_before_rpc(method):
    debug = Session(); debug.cpu_delta_start(RANGES); debug.cpu_delta_record(); debug.cpu_delta_rewind()
    before = deepcopy((debug.cpu, debug.ram)); calls = list(debug.calls)
    with pytest.raises(ValueError, match='frozen'):
        debug.call(method)
    assert debug.calls == calls and (debug.cpu, debug.ram) == before
    for operation in (lambda: debug.cpu_delta_start(RANGES), lambda: debug.cpu_delta_record()):
        with pytest.raises(ValueError, match='frozen'):
            operation()
    debug.registers(); debug.memory('0x10000', length=8); debug.call('session.status')
    debug.cpu_delta_recover()
    debug.call('execution.continue')


def test_native_load_failure_keeps_freeze_and_success_clears_it():
    debug = Session(); start = debug.cpu_delta_start(RANGES); debug.cpu_delta_record(); debug.cpu_delta_rewind()
    with pytest.raises(RuntimeError):
        with debug._cpu_delta_full_load():
            debug.call('layers.configure')
            raise RuntimeError('failed native load')
    assert debug.cpu_delta_status()['frozen'] and not debug.cpu_delta_status()['valid']
    debug.load_state(start['anchor']['artifact'])
    assert not debug.cpu_delta_status()['frozen'] and not debug.cpu_delta_status()['valid']


@pytest.mark.parametrize('change', [lambda d: d.ram.__setitem__(1, 99),
                                  lambda d: d.cpu['general'].update(ebx='0x1')])
def test_preflight_guards_unchanged_selected_ram_and_every_exposed_register(change):
    debug = Session(); debug.cpu_delta_start(RANGES); debug.cpu_delta_record(2)
    change(debug); before = deepcopy((debug.cpu, debug.ram))
    with pytest.raises(ValueError, match='expected-after'):
        debug.cpu_delta_rewind()
    assert not debug.mutations and (debug.cpu, debug.ram) == before
    assert not debug.cpu_delta_status()['valid'] and not debug.closed
    debug.cpu_delta_recover()
    assert debug.cpu['general']['ebx'] == '0x0' and debug.ram[1] == 0


@pytest.mark.parametrize('failure', ['timeout-first', 'timeout-second', 'bad-readback'])
def test_partial_or_unknown_application_closes_and_never_advances_cursor(failure):
    debug = Session(); debug.cpu_delta_start(RANGES); debug.cpu_delta_record(2)
    debug.fail_mutation = 1 if failure == 'timeout-first' else 2 if failure == 'timeout-second' else None
    debug.bad_readback = failure == 'bad-readback'
    # Observe an extra byte so a late, unrelated write must fail complete readback.
    if failure == 'bad-readback':
        debug.bad_readback = False
        debug.cpu_delta_recover(); debug.cpu_delta_start([{'address': '0x10000', 'length': 64}])
        debug.cpu_delta_record(2); debug.bad_readback = True
    with pytest.raises((ValueError, TimeoutError)):
        debug.cpu_delta_rewind()
    assert debug.closed and debug.cpu_delta_status()['cursor'] == 2
    assert not debug.cpu_delta_status()['valid'] and debug.cpu_delta_status()['frozen']
    if failure != 'bad-readback':
        assert 'state.load' not in debug.calls


@pytest.mark.parametrize('close_raises', [False, True])
def test_failed_error_receipt_cannot_skip_close_or_mask_partial_write_failure(close_raises):
    debug = Session(); debug.cpu_delta_start(RANGES); debug.cpu_delta_record(2)
    debug.fail_mutation = 2  # First range changed; second write has unknown outcome.
    log_event = debug._event
    close_session = debug.close
    def broken_log(operation, evidence):
        if operation == 'cpu-delta-invalidated':
            raise sqlite3.OperationalError('error log unavailable')
        log_event(operation, evidence)
    def close_then_fail():
        close_session()
        if close_raises:
            raise RuntimeError('cleanup also failed')
    debug._event = broken_log
    debug.close = close_then_fail
    with pytest.raises(TimeoutError, match='unknown write outcome'):
        debug.cpu_delta_rewind()
    status = debug.cpu_delta_status()
    assert debug.closed and not status['valid'] and status['frozen']
    assert status['cursor'] == 2 and not status['resume_safe']
    assert debug.ram[0] == 1 and debug.ram[2] == 6
    assert debug.calls[-1] == 'session.close'


def test_capacity_is_reserved_before_execution_and_anchor_is_charged():
    debug = Session(); start = debug.cpu_delta_start(RANGES, max_steps=1)
    with pytest.raises(ValueError, match='capture budget'):
        debug.cpu_delta_record(2)
    assert debug.trace_calls == 0 and debug.cpu_delta_status()['valid']
    debug.cpu_delta_start(RANGES, max_bytes=start['anchor_bytes_used'] + 1)
    with pytest.raises(ValueError, match='byte budget'):
        debug.cpu_delta_record()
    assert debug.trace_calls == 0
    debug.cpu_delta_start(RANGES); recorded = debug.cpu_delta_record(2)
    status = recorded['history']
    sizes = debug.project.db.execute("SELECT SUM(LENGTH(data)) FROM debug_artifacts WHERE kind='cpu-ram-delta'").fetchone()[0]
    assert status['delta_bytes_used'] == sizes
    assert status['total_bytes_used'] == status['anchor_bytes_used'] + sizes
    debug.cpu_delta_rewind()
    assert debug.cpu_delta_status()['captures_used'] == 2
    assert debug.cpu_delta_status()['delta_bytes_used'] == sizes
    tiny = Session()
    with pytest.raises(ValueError, match='byte budget'):
        tiny.cpu_delta_start(RANGES, max_bytes=1)
    assert not tiny.saved and tiny.trace_calls == 0


@pytest.mark.parametrize('column,value', [('data', b'{}'), ('sha256', '0' * 64), ('run', 'other-run')])
def test_artifact_tampering_refuses_undo_without_any_write(column, value):
    debug = Session(); debug.cpu_delta_start(RANGES); recorded = debug.cpu_delta_record(2)
    identifier = recorded['records'][0]['delta']['artifact']
    debug.project.db.execute(f'UPDATE debug_artifacts SET {column}=? WHERE id=?', (value, identifier))
    with pytest.raises(ValueError, match='artifact'):
        debug.cpu_delta_rewind()
    assert not debug.mutations and not debug.cpu_delta_status()['valid']
    debug.cpu_delta_recover()


def test_failed_trace_and_mode_switch_keep_recovery_anchor_without_auto_restore():
    debug = Session(); debug.cpu_delta_start(RANGES)
    debug.trace_change = lambda document: document.update(complete=False)
    with pytest.raises(ValueError, match='two fetches'):
        debug.cpu_delta_record()
    assert not debug.cpu_delta_status()['valid'] and 'state.load' not in debug.calls
    assert len(debug.saved) == 1 and debug.cpu_delta_status()['captures_used'] == 1
    debug.cpu['cpu_mode'] = 'protected'
    debug.cpu_delta_recover()
    assert debug.cpu['cpu_mode'] == 'real'


def test_identity_and_disk_changes_veto_undo_and_recovery_before_mutations():
    debug = Session(); debug.cpu_delta_start(RANGES); debug.cpu_delta_record()
    debug.manifest[0]['sha256'] = 'changed'
    with pytest.raises(ValueError, match='game files'):
        debug.cpu_delta_rewind()
    with pytest.raises(ValueError, match='game files'):
        debug.cpu_delta_recover()
    assert not debug.mutations and 'state.load' not in debug.calls
    debug.manifest[0]['sha256'] = 'original'
    debug.run_id = 'replacement'
    with pytest.raises(ValueError, match='identity'):
        debug.cpu_delta_recover()


def test_external_mutation_invalidates_before_attempt_but_observations_preserve_history():
    debug = Session(); debug.rewind_start(); debug.cpu_delta_start(RANGES)
    assert not debug.rewind_status()['valid']
    debug.cpu_delta_record()
    for method in ('state.get_registers', 'memory.read', 'session.status', 'state.save', 'video.probe'):
        debug._cpu_delta_before_call(method)
        assert debug.cpu_delta_status()['valid']
    debug._cpu_delta_before_call('unknown.mutator')
    assert not debug.cpu_delta_status()['valid']
    debug.cpu_delta_recover()


@pytest.mark.parametrize('ranges', [[], RANGES * 65,
    [{'address': '0x10000', 'length': True}], [{'address': '0x10000', 'length': 0}],
    [{'address': '0x1003f', 'length': 2}],
    [{'address': '0x10000', 'length': 8}, {'address': '1000:0007', 'length': 2}],
    [{'address': '0x10000', 'length': 8, 'unknown': 0}]])
def test_bad_ranges_do_not_touch_guest(ranges):
    debug = Session()
    with pytest.raises(ValueError):
        debug.cpu_delta_start(ranges)
    assert not debug.calls and not debug.saved


@pytest.mark.parametrize('mode', ['backend', 'registers', 'layers', 'hooks', 'ram-layer', 'mouse', 'keyboard'])
def test_unsupported_admission_never_saves_anchor_or_executes(mode):
    debug = Session()
    if mode == 'backend': debug.backend_name = 'dosbox-qemu'
    if mode == 'registers': debug.rpc.capabilities['register_edit'] = False
    if mode == 'layers': debug._layers = ['layer']
    if mode == 'hooks': debug._hooks = {'breakpoint': 'hook'}
    if mode == 'ram-layer': debug._ram_applied = {0: 1}
    if mode == 'mouse': debug.mouse_pending = True
    if mode == 'keyboard': debug.keyboard_owned = ['a']
    with pytest.raises(ValueError):
        debug.cpu_delta_start(RANGES)
    assert not debug.saved and debug.trace_calls == 0


@pytest.mark.parametrize('field,value', [('instruction_pointer', '0x10000'), ('flags', '0x10000'),
                                       ('eax', '0x100000000'), ('cs', '0x10000')])
def test_cpu_widths_are_validated_before_anchor(field, value):
    debug = Session()
    if field in ('eax',): debug.cpu['general'][field] = value
    elif field == 'cs': debug.cpu['segments'][field] = value
    else: debug.cpu[field] = value
    with pytest.raises(ValueError):
        debug.cpu_delta_start(RANGES)
    assert not debug.saved and debug.trace_calls == 0


def test_trusted_anchor_hash_guard_refuses_modified_state_file():
    debug = Session(); start = debug.cpu_delta_start(RANGES); debug.cpu_delta_record(); debug.cpu_delta_rewind()
    debug.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?', (b'changed', start['anchor']['artifact']))
    with pytest.raises(ValueError, match='anchor'):
        debug.cpu_delta_recover()
    assert debug.cpu_delta_status()['frozen'] and 'state.load' not in debug.calls


def test_trace_evidence_hash_is_pinned_by_its_delta_document():
    debug = Session(); debug.cpu_delta_start(RANGES); result = debug.cpu_delta_record()
    debug.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',
        (b'changed', result['records'][0]['trace_artifact']))
    with pytest.raises(ValueError, match='trace artifact'):
        debug.cpu_delta_rewind()
    assert not debug.mutations
    debug.cpu_delta_recover()


def test_every_selected_range_is_preflighted_before_the_first_write():
    debug = Session(); debug.cpu_delta_start([
        {'address': '0x10000', 'length': 8}, {'address': '0x10020', 'length': 8}])
    debug.cpu_delta_record(2)
    debug.ram[0x24] = 42
    before = deepcopy((debug.cpu, debug.ram))
    with pytest.raises(ValueError, match='expected-after'):
        debug.cpu_delta_rewind()
    assert not debug.mutations and (debug.cpu, debug.ram) == before


def test_unsupported_registers_after_forward_execution_can_recover():
    debug = Session(); debug.cpu_delta_start(RANGES)
    debug.trace_effect = lambda: debug.cpu['general'].pop('eax')
    with pytest.raises(ValueError):
        debug.cpu_delta_record()
    assert not debug.cpu_delta_status()['valid'] and len(debug.saved) == 1
    debug.cpu_delta_recover()
    assert debug.cpu['general']['eax'] == '0x0'


def test_manifest_failure_preserves_partial_freeze_until_matching_files_return():
    debug = Session(); debug.cpu_delta_start(RANGES); debug.cpu_delta_record(); debug.cpu_delta_rewind()
    debug.manifest[0]['sha256'] = 'changed'
    with pytest.raises(ValueError, match='game files'):
        debug.cpu_delta_recover()
    assert debug.cpu_delta_status()['frozen']
    with pytest.raises(ValueError, match='frozen'):
        debug.call('execution.continue')
    debug.manifest[0]['sha256'] = 'original'
    debug.cpu_delta_recover()
    assert not debug.cpu_delta_status()['frozen']


@pytest.mark.parametrize('options', [dict(max_steps=True), dict(max_steps=0), dict(max_steps=129),
                                   dict(max_bytes=True), dict(max_bytes=0), dict(max_bytes=268435457)])
def test_bad_start_limits_do_not_touch_guest(options):
    debug = Session()
    with pytest.raises(ValueError):
        debug.cpu_delta_start(RANGES, **options)
    assert not debug.calls


@pytest.mark.parametrize('count', [True, 0, -1, 129, 1.5])
def test_bad_record_and_undo_counts_do_not_execute_or_write(count):
    debug = Session(); debug.cpu_delta_start(RANGES)
    with pytest.raises(ValueError):
        debug.cpu_delta_record(count)
    with pytest.raises(ValueError):
        debug.cpu_delta_rewind(count)
    assert debug.trace_calls == 0 and not debug.mutations and debug.cpu_delta_status()['valid']


@pytest.mark.parametrize('timeout', [True, 0, 600001, 1.5])
def test_bad_timeout_is_rejected_before_forward_execution(timeout):
    debug = Session(); debug.cpu_delta_start(RANGES)
    with pytest.raises(ValueError, match='timeout_ms'):
        debug.cpu_delta_record(timeout_ms=timeout)
    assert debug.trace_calls == 0 and debug.cpu_delta_status()['valid']
