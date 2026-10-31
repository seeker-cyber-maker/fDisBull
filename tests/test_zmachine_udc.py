"""Authored v3 stories only; these tests do not contain game data."""
import hashlib
import pytest

from fdisbull.zmachine import inspect_story_bytes
from fdisbull.zmachine_udc import capture_zmachine_definition, compile_zmachine_definition


def story(code=bytes.fromhex('14010210ba'), padding=b'pad'):
    data = bytearray(1024)
    def word(at, value):
        data[at:at+2] = value.to_bytes(2, 'big')
    data[0] = 3
    for at, value in ((2, 1), (4, 900), (6, 900), (8, 810), (10, 544),
                      (12, 64), (14, 800), (24, 606), (26, 512)):
        word(at, value)
    data[18:24] = b'261030'
    data[810:814] = b'\x00\x04\x00\x00'
    data[900:900+len(code)] = code
    word(28, sum(data[64:]) & 0xffff)
    return bytes(data) + padding


def edit(offset=900, old='14010210', new='14010310'):
    return {'offset': offset, 'expected_hex': old, 'replacement_hex': new}


def test_exact_snapshot_and_scalar_experiment_preserve_other_bytes():
    source = story()
    definition = capture_zmachine_definition(source)
    exact = compile_zmachine_definition(definition)
    assert bytes.fromhex(exact['bytes']) == source
    assert exact['byte_identity'] and exact['qualification'] == 'original_bytes_only'
    result = compile_zmachine_definition(definition, mode='experiment', edits=[edit()],
                                         assumptions={'no_code_data_alias': True, 'scalar_values_not_addresses': True})
    output = bytes.fromhex(result['bytes'])
    assert {i for i, (a,b) in enumerate(zip(source,output)) if a != b} <= {28,29,902}
    assert output[900:904] == bytes.fromhex('14010310')
    assert output[1024:] == b'pad'
    assert inspect_story_bytes(output)['checksum_status'] == 'matched'
    assert result['output_sha256'] == hashlib.sha256(output).hexdigest()
    assert result['qualification'] == 'unverified_experiment' and not result['equivalence_proven']
    assert not result['native_execution'] and bytes.fromhex(compile_zmachine_definition(definition)['bytes']) == source


def test_definition_hash_binds_json_types_not_python_numeric_equality():
    definition = capture_zmachine_definition(story())
    definition['version'] = 3.0
    with pytest.raises(ValueError, match='corrupt'):
        compile_zmachine_definition(definition)


@pytest.mark.parametrize('change', [lambda d: d.update(source_sha256='0'*64),
    lambda d: d['instructions'].clear(), lambda d: d.update(story_hex='00'+d['story_hex'][2:]),
    lambda d: d.update(sha256='0'*64)])
def test_corrupt_definitions_rejected(change):
    d = capture_zmachine_definition(story()); change(d)
    with pytest.raises(ValueError): compile_zmachine_definition(d)


@pytest.mark.parametrize('bad', [edit(28), edit(810), edit(901), edit(1024),
    edit(old='14010211'), edit(new='140103'), edit(new='15010310'),
    edit(new='14010311'), edit(new='14010210')])
def test_unrecognized_stale_and_encoding_edits_rejected(bad):
    with pytest.raises(ValueError):
        compile_zmachine_definition(capture_zmachine_definition(story()), mode='experiment', edits=[bad],
                                    assumptions={'no_code_data_alias': True, 'scalar_values_not_addresses': True})


def test_no_silent_assumptions_duplicate_or_mode_change():
    d = capture_zmachine_definition(story())
    with pytest.raises(ValueError): compile_zmachine_definition(d, edits=[])
    with pytest.raises(ValueError): compile_zmachine_definition(d, mode='relayout')
    with pytest.raises(ValueError): compile_zmachine_definition(d, mode='experiment', edits=[edit()])
    with pytest.raises(ValueError): compile_zmachine_definition(d, mode='experiment', edits=[edit(),edit()], assumptions={'no_code_data_alias': True, 'scalar_values_not_addresses': True})


def test_variable_operand_and_address_op_refused():
    # 2OP add with first operand a variable; changing that selector is not scalar.
    d = capture_zmachine_definition(story(bytes.fromhex('54010210ba')))
    with pytest.raises(ValueError, match='scalar'):
        compile_zmachine_definition(d, mode='experiment', edits=[edit(old='54010210',new='54020210')], assumptions={'no_code_data_alias': True, 'scalar_values_not_addresses': True})
    d = capture_zmachine_definition(story(bytes.fromhex('8c0002')))
    with pytest.raises(ValueError):
        compile_zmachine_definition(d, mode='experiment', edits=[edit(old='8c0002',new='8c0003')], assumptions={'no_code_data_alias': True, 'scalar_values_not_addresses': True})


def test_budget_and_stop_do_not_admit_uncaptured_bytes():
    d = capture_zmachine_definition(story(bytes.fromhex('b414010210ba')), max_instructions=1)
    assert [x['offset'] for x in d['instructions']] == [900]
    with pytest.raises(ValueError):
        compile_zmachine_definition(d, mode='experiment', edits=[edit(offset=901)], assumptions={'no_code_data_alias': True, 'scalar_values_not_addresses': True})
    with pytest.raises(ValueError): capture_zmachine_definition(story(), max_instructions=0)
