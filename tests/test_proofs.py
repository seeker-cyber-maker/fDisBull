import copy

import pytest

from fdisbull import proofs
from fdisbull.project import Project


def op(name, *args):
    return {'op':name, 'args':list(args)}


def spec(left, right, assumptions=None):
    return {'format':'fdisbull-proof-1', 'scope':'authored 8-bit model',
            'variables':{'x':8}, 'assumptions':assumptions or [], 'left':left, 'right':right}


X = {'var':'x'}
ZERO = {'const':0, 'width':8}
ONE = {'const':1, 'width':8}


def needs_z3():
    if proofs._load_z3() is None: pytest.skip('optional z3-solver is not installed')


def test_real_solver_counterexample_and_identity():
    needs_z3()
    result = proofs.check_equivalence(spec(op('add', X, ONE), X))
    assert result['status'] == 'counterexample'
    x = result['inputs']['x']['unsigned']
    assert (x + 1) % 256 != x
    assert proofs.check_equivalence(spec(op('add', X, ONE), op('add', ONE, X)))['status'] == 'equivalent_under_assumptions'


def test_signedness_and_nonvacuity():
    needs_z3()
    result = proofs.check_equivalence(spec(op('slt', X, ZERO), op('ult', X, ZERO)))
    assert result['status'] == 'counterexample'
    assert result['inputs']['x']['unsigned'] >= 128
    contradictory = [op('eq', X, ZERO), op('eq', X, ONE)]
    assert proofs.check_equivalence(spec(X, X, contradictory))['status'] == 'vacuous'


def test_assumptions_limit_scope_and_budget_expiry(monkeypatch):
    needs_z3()
    restricted = [op('eq', X, ZERO)]
    assert proofs.check_equivalence(spec(X, ZERO, restricted))['status'] == 'equivalent_under_assumptions'
    assert proofs.check_equivalence(spec(X, ZERO))['status'] == 'counterexample'
    times = iter([0.0, 1.0])
    monkeypatch.setattr(proofs.time, 'monotonic', lambda:next(times))
    result = proofs.check_equivalence(spec(X, X), timeout_ms=1)
    assert result['status'] == 'unknown'
    assert 'budget' in result['reason']


def test_missing_dependency_and_invalid_semantics(monkeypatch):
    monkeypatch.setattr(proofs, '_load_z3', lambda:None)
    assert proofs.check_equivalence(spec(X, X))['status'] == 'unavailable'
    for expression in (op('sdiv', X, ONE), op('shl', X, ONE), op('signed_c_add', X, ONE)):
        with pytest.raises(ValueError, match='Unsupported'):
            proofs.check_equivalence(spec(expression, X))
    with pytest.raises(ValueError): proofs.check_equivalence(spec(X, {'const':256, 'width':8}))
    with pytest.raises(ValueError): proofs.check_equivalence(spec(X, X), timeout_ms=0)


def test_project_restart_version_isolation_and_tamper(tmp_path):
    path = tmp_path / 'input.bin'; path.write_bytes(b'\x90\xc3')
    db = tmp_path / 'project.fdb'
    # Also works before the mixin is integrated into Project.
    cls = Project if issubclass(Project, proofs.ProofProjectMixin) else type('ProofProject', (proofs.ProofProjectMixin, Project), {})
    with cls.create(db, path, arch='x86', base=0x1000) as project:
        project.db.executescript(proofs.PROOF_DDL)
        saved = project.proof_check(spec(X, X), version=1, evidence=[{'kind':'authored model'}])
        proof_id = saved['id']
        project.patch(0x1000, 'c3')
        assert project.proofs(version=2)['proofs'] == []
        with pytest.raises(ValueError): project.proof_info(proof_id, version=2)
    with cls(db) as project:
        assert project.proof_info(proof_id, version=1) == saved
        project.db.execute("UPDATE bounded_proofs SET author='changed' WHERE id=?", (proof_id,))
        project.db.commit()
        with pytest.raises(ValueError, match='hash mismatch'): project.proof_info(proof_id, version=1)


def test_invalid_query_does_not_persist(tmp_path):
    path = tmp_path / 'input.bin'; path.write_bytes(b'\xc3')
    cls = Project if issubclass(Project, proofs.ProofProjectMixin) else type('ProofProject', (proofs.ProofProjectMixin, Project), {})
    with cls.create(tmp_path / 'p.fdb', path, arch='x86', base=0x1000) as project:
        project.db.executescript(proofs.PROOF_DDL)
        bad = copy.deepcopy(spec(X, X)); bad['left'] = op('signed_c_add', X, ONE)
        with pytest.raises(ValueError): project.proof_check(bad)
        assert project.proofs()['proofs'] == []


def test_arithmetic_adapter_wrap_and_unmodeled_c_undefined_behavior():
    needs_z3()
    model = proofs.arithmetic_model({'x':8}, op('add', X, ONE), ZERO,
                                    scope='unsigned 8-bit increment')
    result = proofs.check_equivalence(model)
    assert result['status'] == 'counterexample'
    assert result['inputs']['x']['unsigned'] != 255
    assert proofs.check_equivalence(proofs.arithmetic_model(
        {'x':8}, op('add', X, ONE), ZERO, scope='increment at maximum',
        assumptions=[op('eq', X, {'const':255,'width':8})]))['status'] == 'equivalent_under_assumptions'
    with pytest.raises(ValueError, match='undefined behavior'):
        proofs.arithmetic_model({'x':8}, op('add', X, ONE), ZERO,
                                scope='signed C', semantics='signed_c')


def test_readiness_implication_and_vacuous_guard():
    needs_z3()
    ready = op('ult', X, {'const':10,'width':8})
    requirement = op('ult', X, {'const':20,'width':8})
    assert proofs.check_equivalence(proofs.readiness_model(
        {'x':8}, ready, requirement, scope='readiness entails requirement'))['status'] == 'equivalent_under_assumptions'
    result = proofs.check_equivalence(proofs.readiness_model(
        {'x':8}, requirement, ready, scope='inverse implication'))
    assert result['status'] == 'counterexample'
    assert 10 <= result['inputs']['x']['unsigned'] < 20
    assert proofs.check_equivalence(proofs.readiness_model(
        {'x':8}, {'bool':False}, requirement, scope='unreachable readiness'))['status'] == 'vacuous'
    with pytest.raises(ValueError):
        proofs.readiness_model({'x':8}, X, requirement, scope='invalid readiness')
    with pytest.raises(ValueError):
        proofs.readiness_model({'x':8}, ready, X, scope='invalid requirement')


def test_guarded_transition_provenance_and_restart(tmp_path):
    needs_z3()
    source = {'kind':'candidate-rule', 'sha256':'a'*64, 'node':'room/door/open'}
    guard = op('eq', X, ZERO)
    model = proofs.guarded_transition_model({'x':8}, guard, op('add', X, ONE), ONE,
                                             scope='guarded door state model', source=source)
    result = proofs.check_equivalence(model)
    assert result['status'] == 'equivalent_under_assumptions'
    assert result['provenance'] == source
    assert result['provenance_status'] == 'caller_asserted_not_independently_verified'
    wrong = proofs.guarded_transition_model({'x':8}, guard, X, ONE,
                                             scope='guarded wrong transition', source=source)
    assert proofs.check_equivalence(wrong)['inputs']['x']['unsigned'] == 0
    unreachable = proofs.guarded_transition_model({'x':8}, {'bool':False}, X, X,
                                                   scope='unreachable transition', source=source)
    assert proofs.check_equivalence(unreachable)['status'] == 'vacuous'
    for bad in (None, {'kind':'rule','sha256':'bad','node':'door'}, {'kind':'rule','sha256':'a'*64,'node':''}):
        with pytest.raises(ValueError):
            proofs.guarded_transition_model({'x':8}, guard, X, X, scope='bad source', source=bad)
    binary = tmp_path/'program.bin'; binary.write_bytes(b'\xc3')
    path = tmp_path/'project.fdb'
    cls = Project if issubclass(Project, proofs.ProofProjectMixin) else type('ProofProject', (proofs.ProofProjectMixin, Project), {})
    with cls.create(path, binary, arch='x86', base=0x1000) as project:
        project.db.executescript(proofs.PROOF_DDL)
        record = project.proof_check(model, evidence=[source])
    with cls(path) as project:
        assert project.proof_info(record['id'], version=1) == record
        assert record['spec']['provenance'] == source
