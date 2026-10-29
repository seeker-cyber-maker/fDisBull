import copy
import pytest

from fdisbull.interaction_il import execute_il
from fdisbull.udl_blocks import lift_asm_block, lift_c_block, verify_block
from fdisbull import proofs


def asm():
    # mov ax, 0xffff; add ax, 2; dec ax -> 0 (modulo 65536).
    return lift_asm_block(bytes.fromhex('b8ffff05020048'), {'ax':'$score'}, inputs=[], outputs=['ax'])


def test_asm_and_c_independent_lifts_execute_same_u16_result():
    a = asm()
    c = lift_c_block('ax = 65535; ax += 2; ax -= 1;', {'ax':'$score'}, inputs=[], outputs=['ax'])
    assert execute_il(a['uil'])['state']['$score'] == 0
    assert execute_il(c['uil'])['state']['$score'] == 0
    assert a['sha256'] != c['sha256']
    assert verify_block(a, c['uil'])['status'] in ('equivalent_under_assumptions', 'unavailable')


def test_unsupported_truncation_inputs_flags_effects_and_c_octal():
    for code in (b'\xb8\x01', b'\x90', b'\xcd\x21'):
        with pytest.raises(ValueError): lift_asm_block(code, {'ax':'$x'}, inputs=[], outputs=['ax'])
    with pytest.raises(ValueError): lift_asm_block(b'\x40', {'ax':'$x'}, inputs=[], outputs=['ax'])
    with pytest.raises(ValueError): lift_asm_block(b'\x40', {'ax':'$x'}, inputs=['ax'], outputs=['ax'], flags='observed')
    with pytest.raises(ValueError): lift_asm_block(b'\x40', {'ax':'$x'}, inputs=['ax'], outputs=['ax'], pointer_assumptions=['safe'])
    with pytest.raises(ValueError): lift_c_block('ax = 010;', {'ax':'$x'}, inputs=[], outputs=['ax'])
    with pytest.raises(ValueError): lift_asm_block(b'\x41', {'ax':'$x','cx':'$y'}, inputs=['cx'], outputs=['ax'])


def test_source_digest_and_unmodelled_candidate_rejected():
    a = asm(); bad = copy.deepcopy(a); bad['source'] = 'b80000'
    with pytest.raises(ValueError, match='digest'): verify_block(bad, a['uil'])
    candidate = copy.deepcopy(a['uil']); candidate['body'].append({'id':'host','op':'click','target':'door'})
    with pytest.raises(ValueError, match='effects'): verify_block(a, candidate)


def test_counterexample_and_unavailable(monkeypatch):
    a = lift_asm_block(b'\x40', {'ax':'$x'}, inputs=['ax'], outputs=['ax'])
    candidate = copy.deepcopy(a['uil']); candidate['body'][0]['value'] = 2
    result = verify_block(a, candidate)
    if proofs._load_z3() is not None:
        assert result['status'] == 'counterexample'
        assert result['outputs']['ax']['inputs']['ax']['width'] == 16
    else:
        assert result['status'] == 'unavailable'
    monkeypatch.setattr(proofs, '_load_z3', lambda: None)
    assert verify_block(a, a['uil'])['status'] == 'unavailable'


def test_result_retains_model_and_unknown(monkeypatch):
    import fdisbull.udl_blocks as blocks
    a = lift_asm_block(b'\x40', {'ax':'$x'}, inputs=['ax'], outputs=['ax'])
    monkeypatch.setattr(blocks, 'check_equivalence', lambda spec, timeout_ms: {'status':'unknown', 'reason':'budget'})
    result = verify_block(a, a['uil'])
    assert result['status'] == 'unknown'
    assert result['outputs']['ax']['reason'] == 'budget'
    assert result['outputs']['ax']['spec']['variables'] == {'ax': 16}
    assert result['outputs']['ax']['spec']['left'] == result['outputs']['ax']['spec']['right']


def test_asm_c_view_roundtrip_and_changed_defaults_rejected():
    from fdisbull.udl_blocks import asm_to_c
    a = lift_asm_block(bytes.fromhex('05c80048'), {'ax':'$x'}, inputs=['ax'], outputs=['ax'])
    view = asm_to_c(a)
    assert view['text'] == 'ax += 200;\nax -= 1;'
    assert view['source_sha256'] == a['sha256']
    assert 'same bounded ASM decoder' in view['assumptions'][0]
    c = lift_c_block(view['text'], a['bindings'], inputs=a['inputs'], outputs=a['outputs'])
    expected = 'equivalent_under_assumptions' if proofs._load_z3() is not None else 'unavailable'
    assert verify_block(a, c['uil'])['status'] == expected
    changed = copy.deepcopy(c['uil']); changed['variables']['$x']['initial'] = 1
    with pytest.raises(ValueError, match='interface'): verify_block(a, changed)
    wrong = copy.deepcopy(c['uil']); wrong['body'][0]['value'] = 201
    expected_wrong = 'counterexample' if proofs._load_z3() is not None else 'unavailable'
    assert verify_block(a, wrong)['status'] == expected_wrong


def test_native_decoder_disagreement_refuses(monkeypatch):
    import fdisbull.udl_blocks as blocks
    class EmptyDecoder:
        detail = False
        def disasm(self, code, address): return []
    monkeypatch.setattr(blocks.capstone, 'Cs', lambda *args: EmptyDecoder())
    with pytest.raises(ValueError, match='native decoder'):
        lift_asm_block(b'\x40', {'ax':'$x'}, inputs=['ax'], outputs=['ax'])


def test_proof_expression_budgets_reject_exponential_and_deep_inputs():
    a = lift_asm_block(b'\x40', {'ax':'$x'}, inputs=['ax'], outputs=['ax'])
    candidate = copy.deepcopy(a['uil'])
    candidate['body'] = [{'id': f'd{i}', 'op':'add', 'var':'$x', 'value':{'var':'$x'}} for i in range(30)]
    with pytest.raises(ValueError, match='expression budget'):
        verify_block(a, candidate)
    deep = lift_asm_block(b'\x40' * 40, {'ax':'$x'}, inputs=['ax'], outputs=['ax'])
    with pytest.raises(ValueError, match='expression budget'):
        verify_block(deep, deep['uil'])
