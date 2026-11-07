"""Bounded conditional rules using real private Project storage and authored RAM."""
from copy import deepcopy
import json
import struct

import pytest

from fdisbull import memory_rules
from fdisbull.memory_rules import MemoryRuleProjectMixin, MemoryRuleSessionMixin
from fdisbull.project import Project
from test_memory_search_runtime import CaptureSession, paged, snap


# Root wires the production MRO independently. Keep these tests useful both
# before that integration and after Project already includes the new mixin.
RuleProject = Project if issubclass(Project, MemoryRuleProjectMixin) else type(
    'RuleProject', (MemoryRuleProjectMixin, Project), {})


class RuleSession(MemoryRuleSessionMixin, CaptureSession):
    backend_name = 'dosbox'

    def __init__(self, project):
        super().__init__(project)
        self.guest_runs = []
        self.guest_outcomes = []
        self.next_values = []
        self.run_error = None

    def run(self, **options):
        self.guest_runs.append(dict(options))
        assert options['stop_on_hook'] is True
        if self.run_error:
            raise self.run_error
        if self.next_values:
            self.ram[0x3000] = self.next_values.pop(0)
        self.revision += 1
        outcome = self.guest_outcomes.pop(0) if self.guest_outcomes else 'guest_time'
        return dict(outcome=outcome, guest_elapsed_ms=options['guest_ms'],
                    session=dict(state='exited' if outcome == 'guest_exit' else 'stopped',
                                 stop_reason=dict(kind='pause' if outcome == 'guest_time' else outcome)))


@pytest.fixture
def captured(tmp_path):
    binary = tmp_path / 'counter.com'
    binary.write_bytes(bytes.fromhex('90ebfd'))
    with RuleProject.create(tmp_path / 'counter.fdb', binary, image='com') as project:
        session = RuleSession(project)
        session.ram[0x3000:0x3008] = bytes([7, 7, 3, 5, 9, 0, 0, 0])
        yield project, session


def create_rule(project, session, *, offset=0, value=99, mode='equal', search_value=7, **options):
    snapshot = snap(session)
    search = project.memory_search_start(snapshot, mode=mode,
        **({'value': search_value} if mode == 'equal' else {}))['artifact']
    return project.memory_rule_create(search, offset=offset, value=value, **options)['artifact'], search


def progress(project, rule):
    return project.memory_rule_info(rule)['progress']


def test_rule_changes_fresh_values_only_at_the_original_selected_candidate(captured):
    project, session = captured
    rule, original_search = create_rule(project, session, offset=1, condition='less', compare_value=10)
    session.ram[0x3001] = 5
    first = session.memory_rule_tick(rule)
    assert first['applied'] and first['status'] == 'active'
    assert session.writes == [(0x3001, bytes([99]))]
    session.ram[0x3001] = 4
    second = session.memory_rule_tick(rule)
    assert second['applied'] and len(session.writes) == 2
    assert first['plan_artifact'] != second['plan_artifact']
    assert session.ram[0x3000] == 7 and session.ram[0x3002] == 3
    assert project.memory_search_results(original_search)['candidate_count'] == 2
    assert progress(project, rule)['applications'] == 2
    with pytest.raises(ValueError, match='already dispatched'):
        session.memory_apply(first['plan_artifact'])


def test_false_predicate_can_later_become_true_without_reusing_old_expected_bytes(captured):
    project, session = captured
    rule, _ = create_rule(project, session, condition='less', compare_value=5)
    first = session.memory_rule_tick(rule)
    assert first['applied'] is False and first['reason'] == 'condition_not_satisfied'
    assert progress(project, rule)['ticks'] == 1 and progress(project, rule)['attempts'] == 0
    session.ram[0x3000] = 2
    second = session.memory_rule_tick(rule)
    assert second['applied'] and second['observed_value'] == 2
    assert session.writes == [(0x3000, bytes([99]))]
    assert progress(project, rule)['ticks'] == 2 and progress(project, rule)['applications'] == 1


def test_already_matching_value_is_a_noop_that_consumes_only_a_tick(captured):
    project, session = captured
    rule, _ = create_rule(project, session, value=7)
    result = session.memory_rule_tick(rule)
    assert result['applied'] is False and result['reason'] == 'already_value'
    assert progress(project, rule)['ticks'] == 1 and progress(project, rule)['attempts'] == 0
    assert not session.writes


def test_attempt_and_tick_budgets_are_persistent_and_cannot_be_reset_by_retry(captured):
    project, session = captured
    rule, _ = create_rule(project, session, max_applications=2, max_ticks=7)
    session.memory_rule_tick(rule)
    session.ram[0x3000] = 3
    last = session.memory_rule_tick(rule)
    assert last['status'] == 'exhausted'
    session.ram[0x3000] = 1
    again = session.memory_rule_tick(rule)
    assert again['status'] == 'exhausted' and not again['applied']
    assert len(session.writes) == 2 and progress(project, rule)['ticks'] == 2
    with RuleProject(project.path) as reopened:
        assert reopened.memory_rule_info(rule)['progress']['applications'] == 2
        assert reopened.memory_rule_info(rule)['progress']['status'] == 'exhausted'


def test_false_conditions_are_still_bounded_by_maximum_ticks(captured):
    project, session = captured
    rule, _ = create_rule(project, session, condition='less', compare_value=0, max_ticks=2)
    session.memory_rule_tick(rule)
    second = session.memory_rule_tick(rule)
    assert second['status'] == 'exhausted' and second['reason'] == 'tick_budget'
    assert progress(project, rule)['ticks'] == 2 and progress(project, rule)['attempts'] == 0
    assert session.memory_rule_tick(rule)['status'] == 'exhausted'
    assert not session.writes


@pytest.mark.parametrize('fault', ['epoch', 'source', 'version', 'cpu_mode', 'running'])
def test_stale_or_unavailable_context_disables_the_rule_before_any_write(captured, fault):
    project, session = captured
    rule, _ = create_rule(project, session)
    if fault == 'epoch':
        session._runtime_epoch = 'different-epoch'
    elif fault == 'source':
        session.metadata['source_sha256'] = 'ab' * 32
    elif fault == 'version':
        session.metadata['version_sha256'] = 'cd' * 32
    elif fault == 'cpu_mode':
        session.context.update(cpu_mode='v86', cr0='0x1')
    else:
        session.stopped = False
    result = session.memory_rule_tick(rule)
    assert result['status'] == 'disabled' and not result['applied']
    assert not session.writes
    assert session.memory_rule_tick(rule)['status'] == 'disabled'
    assert progress(project, rule)['ticks'] == 1


def test_remap_at_same_cr3_disables_the_rule_even_when_value_is_unchanged(captured):
    project, session = captured
    paged(session)
    rule, _ = create_rule(project, session, search_value=1)
    session.ram[0x6000:0x6008] = session.ram[0x5000:0x5008]
    struct.pack_into('<I', session.ram, 0x2000 + 3 * 4, 0x6007)
    result = session.memory_rule_tick(rule)
    assert result['status'] == 'disabled'
    assert not session.writes


def test_remap_between_whole_region_and_scalar_capture_is_not_adopted(captured, monkeypatch):
    project, session = captured
    paged(session)
    rule, _ = create_rule(project, session, search_value=1)
    session.ram[0x6000:0x6008] = session.ram[0x5000:0x5008]
    original = memory_rules._capture
    captures = 0

    def remap_after_whole_region(*args, **kwargs):
        nonlocal captures
        result = original(*args, **kwargs)
        captures += 1
        if captures == 1:
            struct.pack_into('<I', session.ram, 0x2000 + 3 * 4, 0x6007)
        return result

    monkeypatch.setattr(memory_rules, '_capture', remap_after_whole_region)
    result = session.memory_rule_tick(rule)
    assert result['status'] == 'disabled' and progress(project, rule)['attempts'] == 0
    assert not session.writes and 'Selected scalar mapping changed' in result['error']


def test_page_activity_between_captures_is_not_a_remap(captured, monkeypatch):
    project, session = captured
    paged(session)
    rule, _ = create_rule(project, session, search_value=1, value=1)
    original = memory_rules._capture
    captures = 0

    def activity_after_whole_region(*args, **kwargs):
        nonlocal captures
        result = original(*args, **kwargs)
        captures += 1
        if captures == 1:
            struct.pack_into('<I', session.ram, 0x1000, 0x2027)
            struct.pack_into('<I', session.ram, 0x2000 + 3 * 4, 0x5067)
        return result

    monkeypatch.setattr(memory_rules, '_capture', activity_after_whole_region)
    result = session.memory_rule_tick(rule)
    assert result['status'] == 'active' and result['reason'] == 'already_value'
    assert progress(project, rule)['attempts'] == 0


@pytest.mark.parametrize('fault', ['timeout', 'corrupt'])
def test_uncertain_dispatch_is_terminal_and_has_persisted_progress(captured, fault):
    project, session = captured
    rule, _ = create_rule(project, session)
    session.write_fault = fault
    result = session.memory_rule_tick(rule)
    assert result['status'] == 'uncertain' and result['dispatch_outcome'] == 'unknown'
    assert session.closed and len(session.writes) == 1
    saved = progress(project, rule)
    assert saved['status'] == 'uncertain' and saved['attempts'] == 1
    assert session.memory_rule_tick(rule)['status'] == 'uncertain'
    assert len(session.writes) == 1
    assert any(name == 'memory-rule-progress' for name, _ in session.events)


def test_lost_tick_completion_reservation_cannot_be_replayed(captured, monkeypatch):
    project, session = captured
    rule, _ = create_rule(project, session)
    original = memory_rules._capture

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt('authored interruption after the persisted reservation')

    monkeypatch.setattr(memory_rules, '_capture', interrupted)
    with pytest.raises(KeyboardInterrupt):
        session.memory_rule_tick(rule)
    monkeypatch.setattr(memory_rules, '_capture', original)
    assert progress(project, rule)['status'] == 'pending'
    result = session.memory_rule_tick(rule)
    assert result['status'] == 'uncertain' and not session.writes
    assert progress(project, rule)['ticks'] == 1


def test_readback_success_with_progress_storage_failure_does_not_replay(captured, monkeypatch):
    project, session = captured
    rule, _ = create_rule(project, session)
    original = project._debug_artifact

    def failure(run, name, kind, data, metadata):
        if kind == 'memory-rule-progress' and json.loads(data).get('phase') == 'write-complete':
            raise OSError('authored completion storage failure')
        return original(run, name, kind, data, metadata)

    monkeypatch.setattr(project, '_debug_artifact', failure)
    result = session.memory_rule_tick(rule)
    assert result['status'] == 'uncertain' and session.closed
    assert len(session.writes) == 1
    assert session.memory_rule_tick(rule)['status'] == 'uncertain'
    assert len(session.writes) == 1


def test_fresh_rule_snapshots_store_only_the_selected_scalar(captured):
    project, session = captured
    rule, _ = create_rule(project, session)
    result = session.memory_rule_tick(rule)
    info = project.memory_snapshot_info(result['snapshot_artifact'])
    assert info['snapshot']['length'] == 1
    assert info['snapshot']['context']['region'] == {'start': 0x3000, 'length': 1}
    assert progress(project, rule)['last']['origin_search_artifact']


def test_rule_run_uses_bounded_guest_slices_and_fresh_values_each_time(captured):
    project, session = captured
    rule, _ = create_rule(project, session)
    session.next_values = [2, 3]
    result = session.memory_rule_run(rule, ticks=3, interval_ms=100, timeout_ms=2000)
    assert result['complete'] and result['outcome'] == 'tick_budget_complete'
    assert result['completed_ticks'] == 3
    assert len(session.writes) == 3 and len(session.guest_runs) == 2
    assert [entry['guest_ms'] for entry in session.guest_runs] == [100, 100]
    assert all(1 <= entry['timeout_ms'] <= 2000 for entry in session.guest_runs)
    assert progress(project, rule)['applications'] == 3


@pytest.mark.parametrize('outcome', ['breakpoint', 'hook', 'watchpoint', 'guest_exit', 'guest_tsr', 'timeout'])
def test_rule_run_stops_without_an_extra_edit_on_non_time_stop(captured, outcome):
    project, session = captured
    rule, _ = create_rule(project, session)
    session.guest_outcomes = [outcome]
    session.next_values = [2]
    result = session.memory_rule_run(rule, ticks=3, interval_ms=100, timeout_ms=2000)
    assert not result['complete'] and result['outcome'] == outcome
    assert len(session.guest_runs) == 1 and len(session.writes) == 1
    assert session.ram[0x3000] == 2
    assert progress(project, rule)['ticks'] == 1


def test_rule_run_does_not_advance_guest_after_an_application_budget_stop(captured):
    project, session = captured
    rule, _ = create_rule(project, session, max_applications=1)
    result = session.memory_rule_run(rule, ticks=3)
    assert result['outcome'] == 'rule_exhausted'
    assert result['completed_ticks'] == 1 and not session.guest_runs


def test_unacknowledged_guest_run_disables_rule_and_closes_the_guest(captured):
    project, session = captured
    rule, _ = create_rule(project, session)
    session.run_error = TimeoutError('authored lost guest-run acknowledgment')
    result = session.memory_rule_run(rule, ticks=3)
    assert result['outcome'] == 'uncertain' and session.closed
    assert progress(project, rule)['status'] == 'uncertain'
    assert len(session.writes) == 1 and len(session.guest_runs) == 1


def test_full_machine_backend_cannot_invent_a_guest_millisecond_timer(captured):
    project, session = captured
    rule, _ = create_rule(project, session)
    session.backend_name = 'qemu-machine'
    with pytest.raises(ValueError, match='DOSBox'):
        session.memory_rule_run(rule, ticks=2)
    assert not session.writes and not session.guest_runs


def test_ordinary_dosbox_without_an_explicit_backend_name_is_supported(captured):
    project, session = captured
    rule, _ = create_rule(project, session)
    session.backend_name = None
    assert 'backend' not in session.metadata
    result = session.memory_rule_run(rule, ticks=1)
    assert result['complete'] and len(session.writes) == 1


@pytest.mark.parametrize('outer', [None, 10.5])
def test_every_capture_rpc_shares_the_request_deadline_and_restores_the_outer_budget(captured, monkeypatch, outer):
    project, session = captured
    rule, _ = create_rule(project, session)
    monkeypatch.setattr(memory_rules.time, 'monotonic', lambda: 10.0)
    session._rpc_deadline = outer
    observed = []
    call = session.call

    def check_budget(method, params=None):
        observed.append(session._rpc_deadline)
        assert session._rpc_deadline == (10.5 if outer else 12.0)
        return call(method, params)

    session.call = check_budget
    result = session.memory_rule_run(rule, ticks=2, interval_ms=100, timeout_ms=2000)
    assert result['complete'] and observed
    assert session._rpc_deadline == outer


def test_capture_timeout_under_the_shared_deadline_never_advances_or_edits_the_guest(captured):
    project, session = captured
    rule, _ = create_rule(project, session)
    call = session.call

    def timeout_read(method, params=None):
        if method == 'memory.read':
            assert session._rpc_deadline is not None
            raise TimeoutError('authored read timeout under the operation deadline')
        return call(method, params)

    session.call = timeout_read
    result = session.memory_rule_run(rule, ticks=3, timeout_ms=50)
    assert result['outcome'] == 'rule_disabled'
    assert result['progress']['last']['error_type'] == 'TimeoutError'
    assert not session.writes and not session.guest_runs
    assert session._rpc_deadline is None


@pytest.mark.parametrize('options', [
    {'ticks': 0}, {'ticks': 4097}, {'ticks': True},
    {'ticks': 1, 'interval_ms': 0}, {'ticks': 1, 'interval_ms': True},
    {'ticks': 1, 'timeout_ms': 0}, {'ticks': 1, 'timeout_ms': 60001},
])
def test_invalid_periodic_budgets_have_no_target_effect(captured, options):
    project, session = captured
    rule, _ = create_rule(project, session)
    with pytest.raises(ValueError):
        session.memory_rule_run(rule, **options)
    assert not session.writes and not session.guest_runs


@pytest.mark.parametrize('options', [
    {'max_applications': 0}, {'max_applications': 4097}, {'max_applications': True},
    {'max_ticks': 0}, {'max_ticks': 4097}, {'max_ticks': True},
    {'name': ''}, {'name': 'x\n'}, {'condition': 'mystery'}, {'value': 256}, {'offset': 2},
])
def test_invalid_rule_creation_and_non_candidates_are_rejected(captured, options):
    project, session = captured
    with pytest.raises(ValueError):
        create_rule(project, session, **options)
    assert not session.writes


def test_other_live_run_cannot_consume_rule_or_alter_its_budget(captured):
    project, session = captured
    rule, _ = create_rule(project, session)
    session.run_id = 'other-run'
    with pytest.raises(ValueError, match='run'):
        session.memory_rule_tick(rule)
    assert progress(project, rule)['ticks'] == 0 and not session.writes


def test_independent_rules_keep_independent_progress(captured):
    project, session = captured
    first, _ = create_rule(project, session, offset=0)
    second, _ = create_rule(project, session, offset=1)
    session.memory_rule_tick(first)
    assert progress(project, first)['applications'] == 1
    assert progress(project, second)['applications'] == 0
