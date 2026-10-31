"""Public authored semantic fixtures; original-game CPU replay is separate.

No game bytes, downloads, original processes or private evidence required.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
import itertools
import pytest
from fdisbull.interaction_il import execute_il, validate_il

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('colonization_shared_helpers', ROOT / 'scripts/colonization_shared_helpers.py')
helpers = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helpers)

def run(doc, **inputs):
    result = execute_il(doc, helpers.initial_state(doc, **inputs))
    assert result['status'] == 'complete'
    return result['state']

def wrap(x): return ((x + 32768) & 65535) - 32768

def test_documents_use_existing_v1_and_symbolic_variables():
    for doc in (helpers.balance_uil(), helpers.net_uil()):
        assert validate_il(doc)
        assert doc['format'] == 'fdisbull-il-1'
        assert all(name.startswith('$') for name in doc['variables'])
        assert 'evidence' not in doc  # Source and executor authority stay external.

def test_balance_boundary_product_and_scratch_reset():
    for supply, demand, available in itertools.product((-32768, -1, 0, 1, 100, 32767), repeat=3):
        s = run(helpers.balance_uil(), supply=supply, demand=demand, available=available,
                consumed=123, shortage=456, unmet=789)
        assert s['$consumed'] == demand
        assert s['$shortage'] == (wrap(demand-supply) if demand>supply else 0)
        total = wrap(supply+available)
        assert s['$unmet'] == (wrap(demand-available-supply) if total<demand else 0)

def test_nonnegative_balances_have_expected_interpretation():
    s = run(helpers.balance_uil(), supply=4, demand=7, available=2)
    assert (s['$consumed'],s['$shortage'],s['$unmet']) == (7,3,1)
    s = run(helpers.balance_uil(), supply=4, demand=7, available=5)
    assert (s['$consumed'],s['$shortage'],s['$unmet']) == (7,3,0)

def test_wrapping_before_signed_test_is_observable():
    s = run(helpers.balance_uil(), supply=32767, demand=0, available=1)
    assert s['$unmet'] == -32768
    assert max(0, 0-(32767+1)) != s['$unmet']

def test_net_all_mapping_values_and_optional_output():
    for mapping, target in itertools.product(range(-128,128), (False,True)):
        s = run(helpers.net_uil(), produced=10,consumed=3,has_mapped_adjustment=(mapping>=0),
                mapped_adjustment=2,has_report_target=target,reported_adjustment=99)
        assert s['$net'] == (7 if mapping<0 else 5)
        written = mapping>=0 and target
        assert s['$report_written'] is written
        assert s['$reported_adjustment'] == (2 if written else 99)

def test_changed_operand_is_not_ignored():
    doc = helpers.net_uil()
    altered = deepcopy(doc)
    altered['body'][3]['then'][0]['op'] = 'add'
    inputs = dict(produced=10,consumed=3,has_mapped_adjustment=True,mapped_adjustment=2)
    assert run(doc,**inputs)['$net'] == 5
    assert run(altered,**inputs)['$net'] == 9

def test_udl_role_does_not_silently_acquire_native_authority():
    doc = helpers.net_uil(); udl = deepcopy(doc);udl['role']='udl'
    assert run(doc,produced=10) == run(udl,produced=10)

def test_unsupported_input_refuses():
    doc = helpers.net_uil()
    s = helpers.initial_state(doc,has_mapped_adjustment=1)
    result=execute_il(doc,s)
    assert result['status']=='refused' and result['state']==s

def test_model_difference_in_subtraction_orders_is_equivalent():
    z3 = pytest.importorskip('z3')
    supply,demand,available = z3.BitVecs('supply demand available',16)
    # Only the source expressions, not a machine-code proof.
    solver = z3.Solver();solver.set(timeout=5000)
    solver.add(demand-available-supply != demand-(supply+available))
    assert solver.check()==z3.unsat

def test_signed_comparison_expansion_for_all_i16_pairs():
    z3 = pytest.importorskip('z3')
    left,right = z3.BitVecs('left right',16)
    ls,rs = z3.Extract(15,15,left)==1,z3.Extract(15,15,right)==1
    different = z3.Extract(15,15,left-right)==1
    expanded = z3.Or(z3.And(ls,z3.Not(rs)),z3.And(ls==rs,different))
    solver=z3.Solver();solver.set(timeout=5000)
    solver.add(expanded != (left<right))
    assert solver.check()==z3.unsat
