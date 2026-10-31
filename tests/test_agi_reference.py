"""Keep the independently authored source model inspectable and exercised."""
from fdisbull.interaction_il import execute_il
from tests.agi_scalar_reference import oracle, oracle_selftest
from tests.test_agi_control import loaded, lift, source_trace


def test_reference_authored_semantic_controls():
    oracle_selftest()


def test_reference_matches_shared_state_and_trace_after_callee_return(tmp_path):
    caller=bytes.fromhex('160104030200')
    callee=bytes.fromhex('ff0701ff040003020a0003021400')
    program=loaded(tmp_path,{0:caller,1:callee},callee_entries={1:0})
    projection=lift(program,{'$agi_f1':False,'$agi_v2':0,'$agi_v3':0})
    for flag in (False,True):
        before={'$agi_f1':flag,'$agi_v2':77,'$agi_v3':99}
        expected,trace,frames,kind=oracle({0:caller,1:callee},0,0,set(),{1:0},before)
        actual=execute_il(projection['uil'],before)
        assert actual['complete'] and actual['state']==expected
        assert source_trace(projection,actual)==trace
        assert not frames and kind=='return'
