"""Independent authored scene-census acceptance cases; no Sierra game data.

The byte programs below are constructed from the documented AGI instruction
contract. Expectations describe control/data-flow properties, not private
implementation helpers. This suite does not assert original-game execution.
"""
from hashlib import sha256
import json

import pytest

from fdisbull.agi_scenes import inspect_scenes


def _logic(code, messages=()):
    strings = b''
    offsets = []
    for message in messages:
        if message is None:
            offsets.append(0)
        else:
            offsets.append(2 + 2 * len(messages) + len(strings))
            strings += message + b'\0'
    encrypted = bytes(c ^ b'Avis Durgan'[i % 11] for i, c in enumerate(strings))
    return (len(code).to_bytes(2, 'little') + code + bytes([len(messages)])
            + (2 + 2 * len(messages) + len(strings)).to_bytes(2, 'little')
            + b''.join(x.to_bytes(2, 'little') for x in offsets) + encrypted)


def _game(root, logics, *, pictures=None, views=None, sounds=None, reverse=False):
    root.mkdir(exist_ok=True)
    volume = bytearray()
    files = {}
    groups = (('LOGDIR', logics), ('PICDIR', pictures or {}),
              ('VIEWDIR', views or {}), ('SNDDIR', sounds or {}))
    for filename, entries in groups:
        directory = bytearray(b'\xff\xff\xff' * (max(entries, default=-1) + 1))
        for number in sorted(entries):
            payload = entries[number]
            directory[3 * number:3 * number + 3] = len(volume).to_bytes(3, 'big')
            volume += b'\x12\x34\x00' + len(payload).to_bytes(2, 'little') + payload
        files[filename] = bytes(directory)
    files['VOL.0'] = bytes(volume)
    for filename in sorted(files, reverse=reverse):
        (root / filename).write_bytes(files[filename])
    return root


def _inspect(root, code, *, messages=(), **options):
    _game(root, {0: _logic(code, messages)})
    return inspect_scenes(root, profile='2.917', **options)


def _refs(result, operation, logic=0):
    row = next(x for x in result['logics'] if x['logic'] == logic)
    return [r for r in row['references'] if r['operation'] == operation]


def _choice(when_true, when_false):
    # if isset(f1): true; else: false. Neither side can establish f1.
    return (b'\xff\x07\x01\xff' + (len(when_true) + 3).to_bytes(2, 'little')
            + when_true + b'\xfe' + len(when_false).to_bytes(2, 'little') + when_false)


def test_sparse_all_logic_census_preserves_error_and_semantic_claim_boundary(tmp_path):
    _game(tmp_path, {0: _logic(b'\0'), 3: _logic(b'\x12\x07\0'),
                     7: _logic(b'\xfe\xff\x7f')})
    result = inspect_scenes(tmp_path, profile='2.917', include_ir=True)
    assert [r['logic'] for r in result['logics']] == [0, 3, 7]
    assert [r['status'] for r in result['logics']] == ['decoded', 'decoded', 'layout_error']
    assert result['coverage']['present_logics'] == 3
    assert result['coverage']['decoded_logics'] == 2
    assert result['coverage']['layout_errors'] == 1
    assert result['coverage']['resource_census_complete'] is True
    assert result['coverage']['logic_layout_complete'] is False
    assert result['coverage']['scene_discovery_complete'] is False
    assert result['coverage']['accepted_uil_interactions'] == 0
    assert result['executable'] is False
    assert all(r['qualification'] == 'unrecovered_game_intent' for r in result['logics'])
    assert result['scenes'][0]['room'] == 7
    assert result['scenes'][0]['logic_status'] == 'layout_error'


@pytest.mark.parametrize('directory', [None, b'', b'x'])
def test_no_logics_never_establishes_whole_scene_success(tmp_path, directory):
    _game(tmp_path, {})
    if directory is None:
        (tmp_path / 'LOGDIR').unlink()
    else:
        (tmp_path / 'LOGDIR').write_bytes(directory)
    result = inspect_scenes(tmp_path, profile='2.917')
    assert result['coverage']['present_logics'] == 0
    assert result['coverage']['logic_layout_complete'] is False
    assert result['coverage']['value_analysis_complete'] is False
    assert result['coverage']['scene_discovery_complete'] is False
    assert not result['executable']
    if directory != b'':
        assert result['coverage']['resource_census_complete'] is False


def test_same_bytes_produce_same_results_independent_of_creation_order(tmp_path):
    payload = _logic(b'\x03\x28\x07\x18\x28\x12\x07\0', [b'Authored text'])
    first = _game(tmp_path / 'first', {0: payload, 7: _logic(b'\0')}, pictures={7: b'picture'})
    second = _game(tmp_path / 'second', {0: payload, 7: _logic(b'\0')}, pictures={7: b'picture'}, reverse=True)
    a = inspect_scenes(first, profile='2.917', include_ir=True, include_text=True)
    assert a == inspect_scenes(first, profile='2.917', include_ir=True, include_text=True)
    assert a == inspect_scenes(second, profile='2.917', include_ir=True, include_text=True)
    assert str(first) not in json.dumps(a)
    assert a['logics'][0]['source']['sha256'] == sha256(payload).hexdigest()
    assert (first / 'VOL.0').read_bytes() == (second / 'VOL.0').read_bytes()


def test_typed_reference_collision_does_not_merge_domains(tmp_path):
    # v40=7; load.pic(v40); load.view(7); load.sound(7); print(7); new.room(7).
    code = bytes.fromhex('03280718281e0762076507120700')
    messages = [None] * 6 + [b'Test message']
    _game(tmp_path, {0: _logic(code, messages), 7: _logic(b'\0')},
          pictures={7: b'p'}, views={7: b'v'}, sounds={7: b's'})
    result = inspect_scenes(tmp_path, profile='2.917')
    refs = result['logics'][0]['references']
    assert [r['target']['kind'] for r in refs] == ['picture', 'view', 'sound', 'message', 'room']
    assert all(r['target']['values'] == [7] for r in refs)
    assert refs[3]['target']['owner_logic'] == 0
    assert refs[0]['target']['mode'] == 'variable'
    assert all(r['resource_status'] == [{'number': 7, 'status': 'ok'}] for r in refs)


def test_unknown_entry_variable_is_not_initialized_to_zero(tmp_path):
    result = _inspect(tmp_path, b'\x13\x28\0')
    ref = _refs(result, 'new.room.v')[0]
    assert ref['target']['values'] is None
    assert ref['target']['resolution'] == 'unresolved'
    assert result['scenes'] == []


def test_join_has_all_finite_targets_and_missing_definition_stays_unknown(tmp_path):
    complete = _choice(b'\x03\x28\x05', b'\x03\x28\x09') + b'\x13\x28\0'
    result = _inspect(tmp_path, complete)
    assert _refs(result, 'new.room.v')[0]['target']['values'] == [5, 9]
    partial = _choice(b'\x03\x28\x05', b'\x0c\x01') + b'\x13\x28\0'
    result = _inspect(tmp_path, partial)
    assert _refs(result, 'new.room.v')[0]['target']['values'] is None


@pytest.mark.parametrize('start, operation, answer', [
    (255, b'\x01\x28', 255), (0, b'\x02\x28', 0),
    (255, b'\x05\x28\x01', 0), (0, b'\x07\x28\x01', 255),
    (200, b'\xa5\x28\x02', 144), (255, b'\xa7\x28\x02', 127),
])
def test_numeric_contract_at_byte_boundaries(tmp_path, start, operation, answer):
    code = bytes([3, 40, start]) + operation + b'\x13\x28\0'
    result = _inspect(tmp_path, code)
    assert _refs(result, 'new.room.v')[0]['target']['values'] == [answer]


def test_undefined_division_never_invents_a_destination(tmp_path):
    result = _inspect(tmp_path, bytes.fromhex('032805a72800132800'))
    assert _refs(result, 'new.room.v')[0]['target']['values'] is None


@pytest.mark.parametrize('barrier', [b'\x16\x02', b'\x65\x01', b'\x80', b'\x27\x00\x32\x33'])
def test_unqualified_effect_barriers_discard_preceding_facts(tmp_path, barrier):
    # Direct helper call, modal print, restart, and engine object query.
    result = _inspect(tmp_path, b'\x03\x28\x07' + barrier + b'\x13\x28\0')
    assert _refs(result, 'new.room.v')[0]['target']['values'] is None


def test_call_variable_target_is_observed_before_call_effects(tmp_path):
    result = _inspect(tmp_path, bytes.fromhex('0328071728132800'))
    assert _refs(result, 'call.v')[0]['target']['values'] == [7]
    assert _refs(result, 'new.room.v')[0]['target']['values'] is None


@pytest.mark.parametrize('variable', [11, 12, 13, 14, 19])
def test_engine_volatile_values_do_not_become_constant_targets(tmp_path, variable):
    result = _inspect(tmp_path, bytes([3, variable, 7, 19, variable, 0]))
    assert _refs(result, 'new.room.v')[0]['target']['values'] is None


def test_unknown_indirect_write_invalidates_aliases(tmp_path):
    # v40=7; v[v50]=9; room=v40. v50 can be 40.
    result = _inspect(tmp_path, bytes.fromhex('0328070b3209132800'))
    assert _refs(result, 'new.room.v')[0]['target']['values'] is None


def test_indirect_multi_target_store_is_a_weak_update(tmp_path):
    # Either v30 or v31 changes to 42; the unselected variable keeps its value.
    code = (bytes.fromhex('031e01031f02')
            + _choice(b'\x03\x28\x1e', b'\x03\x28\x1f')
            + bytes.fromhex('0b282a181e1f1f00'))
    result = _inspect(tmp_path, code)
    assert _refs(result, 'load.pic')[0]['target']['values'] == [1, 42]
    assert _refs(result, 'load.view.v')[0]['target']['values'] == [2, 42]


def test_indirect_read_follows_known_index_and_source(tmp_path):
    # v30=42; v40=30; v50=v[v40]; load.pic(v50).
    result = _inspect(tmp_path, bytes.fromhex('031e2a03281e0a3228183200'))
    assert _refs(result, 'load.pic')[0]['target']['values'] == [42]


@pytest.mark.parametrize('terminator', [b'\0', b'\x12\x03'])
def test_termination_keeps_dead_ir_without_claiming_entry_flow(tmp_path, terminator):
    result = _inspect(tmp_path, terminator + b'\x12\x07\0', include_ir=True)
    later = _refs(result, 'new.room')[-1]
    assert later['target']['values'] == [7]
    assert later['entry_flow'] == 'outside_known_entries'
    candidate = next(c for c in result['scenes'] if c['room'] == 7)
    assert candidate['incoming'][0]['entry_flow'] == 'outside_known_entries'
    assert result['logics'][0]['ir']['instruction_count'] == 3


def test_scan_start_reentry_cannot_reuse_initial_prefix_assignment(tmp_path):
    # Prefix assigns v40, but the saved next-cycle entry begins after it.
    result = _inspect(tmp_path, bytes.fromhex('03280791132800'), include_ir=True)
    assert result['logics'][0]['entry_offsets'] == [2, 6]
    assert _refs(result, 'new.room.v')[0]['target']['values'] is None
    assert result['logics'][0]['value_analysis']['fixed_point'] is True


def test_ordered_condition_tokens_include_not_or_and_stateful_said(tmp_path):
    tokens = bytes.fromhex('0702fcfd0128070e0234122143fc')
    code = b'\xff' + tokens + b'\xff\x01\x00\0\0'
    result = _inspect(tmp_path, code, include_ir=True)
    condition = result['logics'][0]['conditions'][0]
    ordered = condition['ordered_tokens']
    assert [x.get('operation', x.get('marker')) for x in ordered] == [
        'isset', 'or', 'not', 'equaln', 'said', 'or']
    assert ordered[4]['word_groups'] == [0x1234, 0x4321]
    assert ordered[4]['stateful'] is True
    assert [x['offset'] for x in ordered] == sorted(x['offset'] for x in ordered)
    assert condition['qualification'] == 'low_level_ir'
    ir = result['logics'][0]['ir']['instructions'][0]
    assert bytes(ir['operands']) == tokens + b'\xff\x01\x00'
    assert condition['successors'] == [
        {'kind': 'true', 'offset': 2 + len(code) - 2},
        {'kind': 'false', 'offset': 2 + len(code) - 1}]


def test_budget_stop_withholds_partially_resolved_targets(tmp_path):
    result = _inspect(tmp_path, bytes.fromhex('0328071828132800'), max_updates=1)
    assert result['coverage']['budget_stops'] == 1
    assert result['coverage']['value_analysis_complete'] is False
    for ref in result['logics'][0]['references']:
        assert ref['target']['values'] is None
        assert ref['target']['reason'] == 'analysis_budget'
        assert ref['entry_flow'] == 'unknown_budget'


def test_growing_loop_reaches_conservative_fixed_point(tmp_path):
    # Initial zero joins a backedge increment; finite set cap must widen to top.
    code = bytes.fromhex('0328000128ff0701ff0300fef5ff132800')
    result = _inspect(tmp_path, code)
    assert result['logics'][0]['status'] == 'decoded'
    assert result['logics'][0]['value_analysis']['fixed_point'] is True
    assert _refs(result, 'new.room.v')[0]['target']['values'] is None


def test_opcode_bytes_in_operands_and_messages_do_not_form_scene_edges(tmp_path):
    # position(object=0,x=18,y=7), return; same bytes also occur in message text.
    result = _inspect(tmp_path, bytes.fromhex('2500120700'), messages=[b'\x12\x07'], include_ir=True)
    assert result['scenes'] == []
    assert result['logics'][0]['references'] == []
    assert [i['operation'] for i in result['logics'][0]['ir']['instructions']] == ['position', 'return']


@pytest.mark.parametrize('code', [
    bytes.fromhex('ff0701ff010003280700'),  # Branch enters assignn operands.
    bytes.fromhex('ff0e023412'),           # Truncated variable-length said.
    bytes.fromhex('ae00'),                 # Beyond the admitted profile.
    bytes.fromhex('fffcfc0701ff000000'),   # Empty OR group.
])
def test_invalid_layout_keeps_opaque_resource_without_spurious_scene(tmp_path, code):
    payload = _logic(code)
    result = _inspect(tmp_path, code, include_ir=True)
    logic = result['logics'][0]
    assert logic['status'] == 'layout_error'
    assert logic['opaque_resource'] is True
    assert logic['source']['sha256'] == sha256(payload).hexdigest()
    assert logic['references'] == []
    assert result['coverage']['logic_layout_complete'] is False


def test_hold_key_last_profile_opcode_is_retained(tmp_path):
    result = _inspect(tmp_path, b'\xad\0', include_ir=True)
    assert result['logics'][0]['status'] == 'decoded'
    assert [i['operation'] for i in result['logics'][0]['ir']['instructions']] == ['hold.key', 'return']
    assert result['coverage']['instructions'] == 2


def test_detailed_ir_accounts_for_all_source_instruction_spans(tmp_path):
    code = bytes.fromhex('032807182800120900')
    compact = _inspect(tmp_path, code)
    full = inspect_scenes(tmp_path, profile='2.917', include_ir=True)
    a = compact['logics'][0]['ir']
    b = full['logics'][0]['ir']
    assert a['sha256'] == b['sha256']
    assert a['instruction_count'] == b['instruction_count'] == 5
    assert a['body_included'] is False and 'instructions' not in a
    body = b['instructions']
    assert body[0]['offset'] == 2 and body[-1]['end_offset'] == 2 + len(code)
    assert all(left['end_offset'] == right['offset'] for left, right in zip(body, body[1:]))
    rebuilt = b''.join(bytes([i['opcode']]) + bytes(i['operands']) for i in body)
    assert rebuilt == code
    assert b['semantic_status'] == 'all_operations_retained_as_low_level_ir'


def test_outline_does_not_run_propagation_and_explicit_text_is_opt_in(tmp_path):
    result = _inspect(tmp_path, bytes.fromhex('032807132800'), messages=[b'Private template'], stage='outline')
    assert result['coverage']['updates'] == 0
    assert result['coverage']['value_analysis_complete'] is False
    assert _refs(result, 'new.room.v')[0]['target']['reason'] == 'outline_stage'
    assert 'text' not in result['logics'][0]['messages'][0]
    assert 'Private template' not in json.dumps(result)
    text = inspect_scenes(tmp_path, profile='2.917', include_text=True)
    assert text['logics'][0]['messages'][0]['text'] == 'Private template'


def test_unreadable_message_table_is_unknown_not_absent(tmp_path):
    payload = _logic(b'\x65\x01\0', [b'Exists'])[:-1]
    _game(tmp_path, {0: payload})
    result = inspect_scenes(tmp_path, profile='2.917')
    assert result['logics'][0]['message_status'] == 'error'
    status = _refs(result, 'print')[0]['resource_status'][0]['status']
    assert status in ('unknown', 'error', 'not_decoded')


def test_malformed_picture_directory_cannot_prove_picture_absent(tmp_path):
    _game(tmp_path, {0: _logic(bytes.fromhex('032807182800'))})
    (tmp_path / 'PICDIR').write_bytes(b'x')
    result = inspect_scenes(tmp_path, profile='2.917')
    assert result['coverage']['resource_census_complete'] is False
    status = _refs(result, 'load.pic')[0]['resource_status'][0]['status']
    assert status in ('unknown', 'error', 'not_decoded')


@pytest.mark.parametrize('options', [
    {'profile': '2.936'}, {'profile': 'SCI'}, {'profile': True},
    {'stage': 'execute'}, {'max_updates': 0}, {'max_updates': True},
    {'max_updates': 1.0}, {'max_updates': 2000001},
    {'include_ir': 1}, {'include_text': 'yes'},
])
def test_invalid_profiles_modes_and_numeric_types_are_refused(tmp_path, options):
    with pytest.raises(ValueError):
        inspect_scenes(tmp_path, **{'profile': '2.917', **options})
