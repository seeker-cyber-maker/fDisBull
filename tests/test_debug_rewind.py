"""History/cursor contracts with an explicit stopped-state/trace collaborator.

These tests exercise bookkeeping and admission, not native rewind equivalence.
"""
from copy import deepcopy
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest

from fdisbull.debug_rewind import RewindSessionMixin


class Session(RewindSessionMixin):
    def __init__(self):
        self.closed = False
        self.run_id = 'owned-run'
        self.version = {'id': 1}
        self.metadata = dict(source_sha256='source', version_sha256='version', emulator_sha256='backend',
                             runtime_profile='real-normal-v1', game_dir='/private/game')
        self.rpc = SimpleNamespace(capabilities={'save_states': True})
        db = sqlite3.connect(':memory:')
        db.row_factory = sqlite3.Row
        db.executescript('CREATE TABLE debug_runs(id TEXT,version INTEGER);'
            'CREATE TABLE debug_artifacts(id TEXT,run TEXT,kind TEXT,sha256 TEXT,data BLOB);'
            "INSERT INTO debug_runs VALUES ('owned-run',1);")
        self.project = SimpleNamespace(db=db)
        self.cpu = dict(cpu_mode='real', instruction_pointer='0x0', segments={'cs': '0x1000'},
                        general={'eax': '0x0'}, flags='0x202')
        self.events, self.calls, self.saved, self.trace_calls = [], [], {}, 0
        self.target_state = 'stopped'
        self.manifest = [{'path': 'target', 'sha256': 'original'}]
        self.trace_change = lambda document: None
        self.restore_bad = False

    def _event(self, operation, evidence):
        self.events.append((operation, deepcopy(evidence)))

    def call(self, method, params=None):
        self._rewind_before_call(method)
        self.calls.append(method)
        return {'state': self.target_state}

    def registers(self):
        self.call('state.get_registers')
        return deepcopy(self.cpu)

    def save_state(self, name, max_bytes):
        self.call('state.save')
        if max_bytes < 8:
            raise ValueError('State exceeds max_bytes')
        identifier = 'state-' + str(len(self.saved))
        self.saved[identifier] = (deepcopy(self.cpu), deepcopy(self.manifest))
        return dict(artifact=identifier, size=8, sha256=hashlib.sha256(identifier.encode()).hexdigest(),
                    metadata=dict(registers=deepcopy(self.cpu), disk_manifest=deepcopy(self.manifest)))

    def load_state(self, artifact):
        self.call('state.load')
        cpu, manifest = self.saved[artifact]
        if manifest != self.manifest:
            raise ValueError('Mounted game files differ')
        self.cpu = deepcopy(cpu)
        if self.restore_bad:
            self.cpu['general']['eax'] = '0xbad'
        return dict(artifact=artifact, registers=self.registers(), framebuffer='invalidated_until_next_completed_frame')

    def trace(self, name, count, timeout_ms, fast_forward):
        assert count == 2 and 1 <= timeout_ms <= 600000 and fast_forward
        self.call('execution.continue')
        self.trace_calls += 1
        before = deepcopy(self.cpu)
        self.cpu['instruction_pointer'] = hex(int(self.cpu['instruction_pointer'], 16) + 1)
        self.cpu['general']['eax'] = hex(int(self.cpu['general']['eax'], 16) + 1)
        def event(cpu, completed):
            return dict(address=dict(space='segmented', segment=cpu['segments']['cs'],
                                     offset=cpu['instruction_pointer']),
                        observation={'instruction_completed': completed})
        document = dict(version=1, requested_count=2, complete=True,
            events=[event(before, None), event(self.cpu, False)],
            run=dict(run=self.run_id, outcome='pause', timed_out=False, hook_hits=[],
                     session=dict(state='stopped', stop_reason={'kind': 'pause'})))
        self.trace_change(document)
        raw = json.dumps(document).encode()
        identifier = 'trace-' + str(self.trace_calls)
        self.project.db.execute('INSERT INTO debug_artifacts VALUES (?,?,?,?,?)',
            (identifier, self.run_id, 'trace', hashlib.sha256(raw).hexdigest(), raw))
        return dict(artifact=identifier)

    def close(self):
        self.closed = True


def test_records_previous_states_and_rewinds_selected_count_without_reexecution():
    debug = Session()
    start = debug.rewind_start(max_steps=8)
    assert start['valid'] and start['cursor'] == 0 and start['instruction_completion'] == 'unknown'
    result = debug.rewind_record(count=3)
    assert result['recorded_count'] == 3 and result['cursor'] == 3
    assert [r['before_pc']['offset'] for r in result['records']] == ['0x0', '0x1', '0x2']
    assert debug.cpu['general']['eax'] == '0x3'
    restored = debug.rewind(count=2)
    assert restored['cursor'] == 1 and debug.cpu['general']['eax'] == '0x1'
    assert restored['target_checkpoint']['artifact'] == result['records'][1]['checkpoint']['artifact']
    assert restored['restore']['framebuffer'] == 'invalidated_until_next_completed_frame'
    debug.rewind()
    assert debug.cpu['instruction_pointer'] == '0x0' and debug.trace_calls == 3
    assert debug.rewind_status()['valid']


def test_branch_retains_artifacts_and_charges_discarded_future_captures():
    debug = Session(); debug.rewind_start(max_steps=4, max_bytes=32)
    debug.rewind_record(3); debug.rewind(2)
    old = set(debug.saved)
    result = debug.rewind_record()
    status = result['history']
    assert status['cursor'] == status['retained_steps'] == 2
    assert status['captures_used'] == 4 and status['state_bytes_used'] == 32
    assert old <= set(debug.saved)
    before = deepcopy(debug.cpu)
    with pytest.raises(ValueError, match='capture budget'):
        debug.rewind_record()
    assert debug.cpu == before and debug.trace_calls == 4 and debug.rewind_status()['valid']
    debug.rewind(2)
    assert debug.cpu['general']['eax'] == '0x0'


def test_returned_receipts_cannot_edit_the_private_cursor_target():
    debug = Session(); debug.rewind_start()
    result = debug.rewind_record(2)
    result['records'][1]['checkpoint']['artifact'] = 'state-0'
    result['records'][1]['before_pc']['offset'] = '0xbad'
    debug.rewind()
    assert debug.cpu['general']['eax'] == '0x1' and debug.rewind_status()['valid']


def test_count_preflight_and_oversized_snapshot_never_execute_a_forward_interval():
    debug = Session(); debug.rewind_start(max_steps=1)
    with pytest.raises(ValueError, match='capture budget'):
        debug.rewind_record(2)
    assert not debug.saved and debug.trace_calls == 0
    debug.rewind_start(max_bytes=7)
    with pytest.raises(ValueError, match='max_bytes'):
        debug.rewind_record()
    assert not debug.saved and debug.trace_calls == 0 and debug.cpu['instruction_pointer'] == '0x0'
    assert not debug.rewind_status()['valid']


@pytest.mark.parametrize('method', ['execution.continue', 'state.load', 'memory.write', 'input.mouse.click',
    'input.keyboard.press', 'breakpoints.create', 'layers.configure', 'unknown.future.mutation'])
def test_unrecorded_mutation_invalidates_before_attempt_and_cannot_replay(method):
    debug = Session(); debug.rewind_start(); debug.rewind_record()
    debug._rewind_before_call(method)
    assert not debug.rewind_status()['valid']
    with pytest.raises(ValueError, match='No valid'):
        debug.rewind()
    assert debug.trace_calls == 1 and len(debug.saved) == 1
    assert any(operation == 'rewind-invalidated' for operation, _ in debug.events)


def test_observations_and_manual_save_preserve_history_and_new_start_keeps_old_artifacts():
    debug = Session(); debug.rewind_start(); debug.rewind_record()
    old = set(debug.saved); history = debug.rewind_status()['history']
    for method in ('session.status', 'state.get_registers', 'memory.read', 'input.keyboard.state',
                   'breakpoints.list', 'video.screenshot', 'state.save'):
        debug._rewind_before_call(method)
        assert debug.rewind_status()['valid']
    debug.rewind_start()
    assert debug.rewind_status()['history'] != history and debug.rewind_status()['cursor'] == 0
    assert old == set(debug.saved)


@pytest.mark.parametrize('change', [
    lambda d: d.update(complete=False),
    lambda d: d.update(events=d['events'][:1]),
    lambda d: d['run'].update(outcome='breakpoint'),
    lambda d: d['run'].update(outcome='timeout', timed_out=True),
    lambda d: d['run']['session'].update(state='exited'),
    lambda d: d['run']['session']['stop_reason'].update(kind='watchpoint'),
    lambda d: d['run'].update(hook_hits=[{'hook': 'changed-layer'}]),
    lambda d: d['events'][-1]['observation'].update(instruction_completed=None),
    lambda d: d['events'][-1]['address'].update(offset='0x999'),
    lambda d: d['events'][0]['address'].update(offset='0x999'),
])
def test_ambiguous_or_early_trace_stop_invalidates_without_automatic_rollback(change):
    debug = Session(); debug.rewind_start(); debug.trace_change = change
    with pytest.raises(ValueError):
        debug.rewind_record()
    status = debug.rewind_status()
    assert not status['valid'] and status['cursor'] == 0
    assert debug.trace_calls == 1 and len(debug.saved) == 1 and status['captures_used'] == 1
    assert 'state.load' not in debug.calls


def test_trace_hash_and_run_identity_are_checked():
    for mode in ('hash', 'run'):
        debug = Session(); debug.rewind_start()
        trace = debug.trace
        def corrupt(*args, **kwargs):
            artifact = trace(*args, **kwargs)
            column, value = ('sha256', '0'*64) if mode == 'hash' else ('run', 'other-run')
            debug.project.db.execute(f'UPDATE debug_artifacts SET {column}=? WHERE id=?',
                                     (value, artifact['artifact']))
            return artifact
        debug.trace = corrupt
        with pytest.raises(ValueError, match='trace'):
            debug.rewind_record()
        assert not debug.rewind_status()['valid'] and 'state.load' not in debug.calls


def test_changed_disk_refuses_restore_and_bad_cpu_readback_does_not_commit_cursor():
    debug = Session(); debug.rewind_start(); debug.rewind_record(2)
    debug.manifest[0]['sha256'] = 'changed'
    with pytest.raises(ValueError, match='game files'):
        debug.rewind()
    assert debug.rewind_status()['cursor'] == 2 and not debug.rewind_status()['valid']
    other = Session(); other.rewind_start(); other.rewind_record(2); other.restore_bad = True
    with pytest.raises(ValueError, match='CPU readback'):
        other.rewind()
    assert other.rewind_status()['cursor'] == 2 and not other.rewind_status()['valid']
    assert other.closed


def test_history_is_bound_to_live_run_and_close_disables_navigation():
    debug = Session(); debug.rewind_start(); debug.rewind_record()
    debug.run_id = 'replacement-run'
    with pytest.raises(ValueError, match='identity'):
        debug.rewind()
    assert not debug.rewind_status()['valid']
    debug = Session(); debug.rewind_start(); debug.rewind_record(); debug.close()
    assert not debug.rewind_status()['active'] and not debug.rewind_status()['valid']
    with pytest.raises(ValueError, match='closed'):
        debug.rewind()


@pytest.mark.parametrize('options', [dict(max_steps=True), dict(max_steps=0), dict(max_steps=129),
                                   dict(max_bytes=0), dict(max_bytes=256*1024*1024+1)])
def test_invalid_start_limits_do_not_touch_guest(options):
    debug = Session()
    with pytest.raises(ValueError):
        debug.rewind_start(**options)
    assert debug.calls == []


@pytest.mark.parametrize('backend', ['wine-qemu', 'dosbox-qemu', 'qemu-machine'])
def test_other_backends_cannot_borrow_native_dos_rewind_claim(backend):
    debug = Session(); debug.metadata['backend'] = backend
    with pytest.raises(ValueError, match='native DOSBox'):
        debug.rewind_start()
    assert not debug.calls


def test_missing_capability_running_target_and_nonreal_mode_are_rejected():
    debug = Session(); debug.rpc.capabilities['save_states'] = False
    with pytest.raises(ValueError, match='save_states'):
        debug.rewind_start()
    debug.rpc.capabilities['save_states'] = True; debug.target_state = 'running'
    with pytest.raises(ValueError, match='stopped'):
        debug.rewind_start()
    debug.target_state = 'stopped'; debug.cpu['cpu_mode'] = 'protected'
    with pytest.raises(ValueError, match='real-mode'):
        debug.rewind_start()
