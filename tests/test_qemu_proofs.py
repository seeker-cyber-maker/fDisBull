"""Host-only QEMU proof routing, shared solver parity and script admission."""
from copy import deepcopy
import json
import time
from types import SimpleNamespace

import pytest

from fdisbull import proofs
from fdisbull.cli import respond
from fdisbull.debugger import DebugSession, DebugWorkspace, stamp
from fdisbull.debug_script import validate_script
from fdisbull.project import Project
from test_qemu_dos_source_admission import owned
from test_qemu_runtime_memory import ram, ADDRESS
from test_proofs import X, ONE, ZERO, op, spec


@pytest.fixture
def models(owned):
    s, project = owned.session, owned.project
    s.capabilities = dict(code_layers=False, bounded_model_proofs=True)
    legacy = DebugSession.__new__(DebugSession)
    legacy.project, legacy.version = project, deepcopy(s.version)
    legacy.run_id, legacy.metadata = 'dosbox-model-run', dict(backend='dosbox')
    with project.transaction(True):
        project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
            (legacy.run_id, legacy.version['id'], stamp(), None, 'stopped', json.dumps(legacy.metadata)))
    owned.legacy = legacy
    return owned


def assert_no_native(o):
    assert not o.peer.qmp_calls and not o.peer.reads
    assert not o.peer.register_reads and not o.peer.monitor_reads and not o.closed


@pytest.mark.parametrize(('model', 'status'), [
    (spec(op('add', X, ONE), op('add', ONE, X)), 'equivalent_under_assumptions'),
    (spec(op('add', X, ONE), X), 'counterexample'),
    (spec(X, X, [op('eq', X, ZERO), op('eq', X, ONE)]), 'vacuous'),
])
def test_public_qemu_proof_matches_real_dosbox_host_solver_contract(models, model, status):
    assert proofs._load_z3() is not None, 'The paired contract gate requires the actual optional Z3 solver'
    workspace = DebugWorkspace()
    workspace.sessions[models.session.run_id] = models.session
    facts = [{'kind': 'authored model, not native CPU evidence'}]
    try:
        reply = respond(dict(method='debug-proof-check', params=dict(project=str(models.project.path),
            run=models.session.run_id, spec=model, author='parity witness', evidence=facts)), debugger=workspace)
    finally:
        workspace.sessions.clear()
    assert reply['ok'], reply
    native = reply['result']
    legacy = models.legacy.proof_check(model, author='parity witness', evidence=facts)
    assert set(native) == set(legacy)
    assert native['spec'] == legacy['spec'] == model
    assert native['result']['status'] == legacy['result']['status'] == status
    assert set(native['result']) == set(legacy['result'])
    assert native['result']['semantics'] == legacy['result']['semantics']
    assert native['result']['spec_sha256'] == legacy['result']['spec_sha256']
    assert native['source_sha256'] == legacy['source_sha256']
    assert native['version_sha256'] == legacy['version_sha256'] == models.session.version['sha256']
    assert native['evidence'] == [{'run': models.session.run_id}, *facts]
    assert legacy['evidence'] == [{'run': models.legacy.run_id}, *facts]
    if status == 'counterexample':
        for result in (native, legacy):
            x = result['result']['inputs']['x']['unsigned']
            assert (x + 1) % 256 != x
    event = models.project.db.execute(
        "SELECT evidence FROM debug_events WHERE run=? AND operation='proof-check'",
        (models.session.run_id,)).fetchone()
    assert json.loads(event['evidence']) == {'id': native['id'], 'status': status}
    assert_no_native(models)


@pytest.mark.parametrize('status', ['unknown', 'unavailable'])
def test_shared_unknown_and_unavailable_results_are_not_reinterpreted(models, monkeypatch, status):
    real = proofs._load_z3()
    if status == 'unavailable':
        monkeypatch.setattr(proofs, '_load_z3', lambda: None)
    else:
        assert real is not None
        class UncertainSolver:
            def __init__(self): self.delegate = real.Solver()
            def add(self, *values): self.delegate.add(*values)
            def set(self, **values): self.delegate.set(**values)
            def check(self): return real.unknown
            def reason_unknown(self): return 'authored solver-unknown boundary'
        class SolverBoundary:
            Solver = UncertainSolver
            def __getattr__(self, key): return getattr(real, key)
        monkeypatch.setattr(proofs, '_load_z3', lambda: SolverBoundary())
    native = models.session.proof_check(spec(X, X))
    legacy = models.legacy.proof_check(spec(X, X))
    assert native['result']['status'] == legacy['result']['status'] == status
    assert native['result']['reason'] == legacy['result']['reason']
    assert native['result']['solver'] == legacy['result']['solver']
    assert_no_native(models)


def test_run_version_provenance_survives_fdb_reopen(models):
    source = dict(kind='caller-authored transition', sha256='a' * 64, node='entry/counter')
    model = proofs.guarded_transition_model({'x': 8}, op('eq', X, ZERO),
        op('add', X, ONE), ONE, scope='one explicit finite-width transition', source=source)
    result = models.session.proof_check(model, evidence=[source])
    with Project(models.project.path) as reopened:
        assert reopened.proof_info(result['id'], version=1) == result
        assert result['result']['provenance_status'] == 'caller_asserted_not_independently_verified'
        row = reopened.db.execute("SELECT evidence FROM debug_events WHERE run=? AND operation='proof-check'",
                                  (models.session.run_id,)).fetchone()
        assert json.loads(row['evidence'])['id'] == result['id']
    assert_no_native(models)


@pytest.mark.parametrize('field', ['run', 'version', 'metadata_version', 'source'])
def test_wrong_session_identity_refuses_before_solver_or_persistence(models, monkeypatch, field):
    s = models.session
    if field == 'run': s.run_id = 'unrelated-run'
    if field == 'version': s.version = dict(s.version, sha256='a' * 64)
    if field == 'metadata_version': s.metadata['version_sha256'] = 'b' * 64
    if field == 'source': s.metadata['source_sha256'] = 'c' * 64
    monkeypatch.setattr(proofs, '_load_z3', lambda: pytest.fail('Invalid identity reached the solver'))
    with pytest.raises(ValueError, match='exact project'):
        s.proof_check(spec(X, X))
    assert models.project.proofs(version=1)['proofs'] == []
    assert_no_native(models)


def test_model_check_does_not_touch_native_history_input_or_frozen_cpu(models):
    s = models.session
    state = dict(id='native-selected-history', valid=False, frozen=True, cursor='selected-node')
    s._qemu_cpu_delta_history = deepcopy(state)
    s._dos_history = {'current': 'native-node', 'valid': True}
    s._input_leases = {'owned-key': 'a'}
    def no_controls(*args, **kwargs): pytest.fail('Host model check touched native ownership')
    s.vm.lock = SimpleNamespace(acquire=no_controls, release=no_controls)
    s.vm.operation_guard = s.vm.history_operation_guard = no_controls
    before = deepcopy((s._qemu_cpu_delta_history, s._dos_history, s._input_leases, s._process))
    assert s.proof_check(spec(X, X))['result']['status'] == 'equivalent_under_assumptions'
    assert (s._qemu_cpu_delta_history, s._dos_history, s._input_leases, s._process) == before
    assert_no_native(models)


def test_shared_inherited_deadline_caps_solver_and_leaves_all_bounds_unchanged(models):
    s, vm, peer = models.session, models.session.vm, models.peer
    now = time.monotonic()
    s._rpc_deadline, s._deadline, vm.operation_deadline, peer.operation_deadline = now + 4, now + 3, now + 2, now + 0.4
    before = (s._rpc_deadline, s._deadline, vm.operation_deadline, peer.operation_deadline)
    result = s.proof_check(spec(X, X), timeout_ms=60000)
    assert 1 <= result['result']['timeout_ms'] <= 400
    assert (s._rpc_deadline, s._deadline, vm.operation_deadline, peer.operation_deadline) == before
    assert_no_native(models)


def test_expired_host_deadline_refuses_without_solver_record_or_native_cleanup(models, monkeypatch):
    models.session._rpc_deadline = time.monotonic() - 1
    monkeypatch.setattr(proofs, '_load_z3', lambda: pytest.fail('Expired request reached solver'))
    with pytest.raises(TimeoutError, match='before solver'):
        models.session.proof_check(spec(X, X))
    assert models.project.proofs()['proofs'] == []
    assert_no_native(models)


def test_post_solver_deadline_error_keeps_exact_persisted_result_without_native_close(models, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
    original = models.project.proof_check
    def proof(*args, **kwargs):
        result = original(*args, **kwargs)
        clock[0] = 102.0
        return result
    models.project.proof_check = proof
    with pytest.raises(TimeoutError, match='exceeded') as caught:
        models.session.proof_check(spec(X, X))
    result = caught.value.result
    assert result['result']['status'] == 'equivalent_under_assumptions'
    assert models.project.proof_info(result['id']) == result
    assert_no_native(models)


def malformed_steps():
    def step(model=None, **changes):
        return dict(op='proof-check', spec=spec(X, X) if model is None else model, **changes)
    for width in (0, 257):
        yield step(spec({'const': '$before.constant', 'width': width}, '$before.right'))
        model = spec('$before.left', X); model['variables'] = {'x': width}
        yield step(model)
    for value, width in ((-1, '$before.width'), (256, 8), (1 << 256, '$before.width')):
        yield step(spec({'const': value, 'width': width}, '$before.right'))
    yield step(spec(op('unknown', '$before.left', X), '$before.right'))
    yield step(spec(op('add', '$before.left'), '$before.right'))
    yield step(spec(op('add', {'const': 0, 'width': 8}, {'const': 0, 'width': 16}), '$before.right'))
    yield step(spec(op('add', '$before.left', {'bool': True}), '$before.right'))
    yield step(spec(op('add', '$before.left', '$before.right'), {'bool': True}))
    yield step(spec(op('$before.operator', {'bool': True}, ZERO), '$before.right'))
    yield step(spec(op('$before.operator', ZERO, {'const': 0, 'width': 16}), '$before.right'))
    yield step(spec(op('$before.operator', ZERO, '$before.left', '$before.right'), '$before.result'))
    yield step(spec(op('$before.operator', '$before.condition', ZERO, {'const': 0, 'width': 16}), '$before.result'))
    yield step(spec(op('add', op('$before.operator', {'bool': True}, '$before.arg'), '$before.other'), '$before.result'))
    yield step(spec({'var': 'x', 'extra': '$before.extra'}, '$before.right'))
    model = spec('$before.left', X); del model['assumptions']; yield step(model)
    model = spec('$before.left', X); model['extra'] = '$before.extra'; yield step(model)
    yield step('$before.spec', timeout_ms=0)
    yield step('$before.spec', author='')
    yield step('$before.spec', evidence={'unsupported': '$before.evidence'})
    yield step('$before.spec', evidence=['x' * 65525])


@pytest.mark.parametrize('later', list(malformed_steps()))
def test_all_known_proof_literals_are_checked_before_earlier_guest_write(ram, monkeypatch, later):
    monkeypatch.setattr(proofs, '_load_z3', lambda: pytest.fail('Script admission loaded solver'))
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='write-memory', address=ADDRESS + 2, data_hex='aabb', expected_hex='1234'), later])
    with pytest.raises((ValueError, TypeError)):
        ram.session.script(script=script)
    assert not ram.writes and bytes(ram.ram[2:4]) == b'\x12\x34'
    assert_no_native(ram)


def test_partial_references_are_passive_and_concrete_dispatch_still_validates(models, monkeypatch):
    model = spec(op('add', '$earlier.left', {'const': 1, 'width': 8}), '$earlier.right')
    model['variables'] = {'x': '$earlier.width'}
    route = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='proof-check', spec=model, author='$earlier.author', timeout_ms='$earlier.budget')])
    monkeypatch.setattr(proofs, '_load_z3', lambda: pytest.fail('Partial admission loaded solver'))
    assert validate_script(route, session=models.session) == route['steps']
    with pytest.raises(ValueError): models.session.proof_check(model)
    with pytest.raises(ValueError): proofs.check_equivalence(model)
    assert_no_native(models)


@pytest.mark.parametrize('expression', [
    op('$earlier.op', ZERO),
    op('$earlier.op', {'bool': True}),
    op('$earlier.op', ZERO, '$earlier.arg'),
    op('$earlier.op', {'bool': True}, '$earlier.arg'),
    op('$earlier.op', '$earlier.left', '$earlier.right'),
    op('$earlier.op', '$earlier.condition', ZERO, '$earlier.branch'),
    op('$earlier.op', {'bool': True}, '$earlier.left', '$earlier.right'),
])
def test_referenced_operator_keeps_potentially_valid_unknown_operands(models, monkeypatch, expression):
    model = spec(expression, '$earlier.expected')
    route = dict(format='fdisbull-script-1', backend='qemu-dos',
                 steps=[dict(op='proof-check', spec=model)])
    monkeypatch.setattr(proofs, '_load_z3', lambda: pytest.fail('Partial admission loaded solver'))
    assert validate_script(route, session=models.session) == route['steps']
    assert_no_native(models)


def test_saved_script_resolves_model_references_and_preserves_default_solver_budget(models):
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='proof-check', spec=spec(X, X), **{'as': 'first'}),
        dict(op='proof-check', spec='$first.spec', author='$first.author', evidence=[{'parent': '$first.id'}])])
    result = models.session.script(script=script, timeout_ms=90000)
    assert result['ok'] and result['completed_steps'] == 2, result
    saved = models.project.proofs()['proofs']
    assert len(saved) == 2
    assert saved[1]['evidence'] == [{'run': models.session.run_id}, {'parent': saved[0]['id']}]
    assert all(1 <= item['result']['timeout_ms'] <= 1000 for item in saved)
    assert_no_native(models)


def test_bad_resolved_model_stops_script_suffix_without_model_or_native_effects(models):
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='proof-check', spec=spec(X, X), **{'as': 'first'}),
        dict(op='proof-check', spec='$first.result'),
        dict(op='proof-check', spec=spec(X, X))])
    result = models.session.script(script=script)
    assert not result['ok'] and result['completed_steps'] == 1
    assert len(models.project.proofs()['proofs']) == 1
    assert_no_native(models)
