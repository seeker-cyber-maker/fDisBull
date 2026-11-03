import pytest

from fdisbull.shadowrun_dialogue import UnsupportedPrompt, read_prompt, select_prompt
from fdisbull.shadowrun_world import WorldFormatError, read_scene


def record(*words):
    data = bytearray(512)
    for index, word in enumerate(words):
        data[index * 4:index * 4 + 4] = word.to_bytes(4, 'big')
    return bytes(data)


def test_prompt_choices_and_priority():
    prompt = read_prompt(record(100, 101, 102, 103, 5, 200, 9), 0)
    assert prompt.options == (101, 102, 103)
    assert select_prompt(prompt, (1 << 14) | (1 << 12)).kind == 'command'
    assert select_prompt(prompt, 1 << 12).value == 200
    assert select_prompt(prompt, 1 << 13).value == 9
    assert select_prompt(prompt, 0).kind == 'wait'


def test_optional_choice_and_terminal():
    prompt = read_prompt(record(100, 101, 0, 0, 0xe9), 0)
    assert select_prompt(prompt, 1 << 12).kind == 'wait'
    assert select_prompt(prompt, 1 << 14).value == 0xe9
    assert select_prompt(read_prompt(record(100, 0xffffffff), 0), 0).value == 0xfb


def test_prompt_fails_closed_on_invalid_and_truncated_records():
    with pytest.raises(UnsupportedPrompt):
        read_prompt(record(100, 101, 0, 103, 5), 0)
    with pytest.raises(UnsupportedPrompt):
        read_prompt(b'\0' * 7, 0)
    with pytest.raises(UnsupportedPrompt):
        select_prompt(read_prompt(record(100, 101, 0, 0, 0xffffffff), 0), 1 << 14)


def test_world_rejects_unidentified_bytes():
    with pytest.raises(WorldFormatError, match='identity'):
        read_scene(b'not the selected cartridge', 2)


def test_game_il_prompt_selection_and_negative_boundary():
    from fdisbull.game_il import GameMachine, author_program
    from fdisbull.shadowrun_dialogue import SOURCE
    machine = GameMachine(author_program(SOURCE.read_text()), {})
    machine.set_state({'shadowrun_dialogue_buttons': 0x70,
        'shadowrun_dialogue_option_count': 2, 'shadowrun_dialogue_target_a': 0xe9,
        'shadowrun_dialogue_target_b': 0xf4b2c})
    machine.call('shadowrun_dialogue_select')
    assert (machine.snapshot()['shadowrun_dialogue_result'], machine.snapshot()['shadowrun_dialogue_value']) == (1, 0xe9)
    machine.set_state({'shadowrun_dialogue_buttons': 0x10, 'shadowrun_dialogue_target_b': 0x80000000})
    machine.call('shadowrun_dialogue_select')
    assert machine.snapshot()['shadowrun_dialogue_result'] == 4


def test_source_stream_literals_runs_and_backreferences():
    from fdisbull.shadowrun_world import decode_stream
    # Three literal bytes, a repeated byte run, then overlapping backreference.
    source = bytes([0, 8, 0x18, 65, 66, 67, 0, 88, 0x90, 0])
    assert decode_stream(source, 0) == (b'ABCXXXXXX', len(source))
    with pytest.raises(WorldFormatError, match='backreference'):
        decode_stream(bytes([0, 2, 0x80, 0x80, 0]), 0)
    with pytest.raises(WorldFormatError, match='budget'):
        decode_stream(bytes([0, 9]), 0, max_output=9)


def test_game_il_payment_success_and_failure():
    from fdisbull.game_il import GameMachine, author_program
    from fdisbull.shadowrun_dialogue import SOURCE
    machine = GameMachine(author_program(SOURCE.read_text()), {})
    for wallet, charge, expect in [(20, 20, (0, 255, 0xf5ab8)), (19, 20, (19, 20, 0xf5af8))]:
        machine.set_state({'shadowrun_dialogue_wallet': wallet, 'shadowrun_dialogue_charge': charge})
        machine.call('shadowrun_dialogue_pay')
        state = machine.snapshot()
        assert tuple(state[k] for k in ('shadowrun_dialogue_wallet', 'shadowrun_dialogue_charge', 'shadowrun_dialogue_response')) == expect


def test_game_il_command_dispatch_flags_and_unknown():
    from fdisbull.game_il import GameMachine, author_program
    from fdisbull.shadowrun_dialogue import SOURCE
    machine = GameMachine(author_program(SOURCE.read_text()), {})
    machine.set_state({'shadowrun_dialogue_result': 1, 'shadowrun_dialogue_value': 0x30,
                       'shadowrun_dialogue_flag30': 0xa0})
    machine.call('shadowrun_dialogue_dispatch')
    s = machine.snapshot()
    assert (s['shadowrun_dialogue_flag30'], s['shadowrun_dialogue_result'], s['shadowrun_dialogue_value']) == (0xa2, 2, 0xf4e8c)
    machine.set_state({'shadowrun_dialogue_result': 1, 'shadowrun_dialogue_value': 0x31,
                       'shadowrun_dialogue_flag27': 0xa0})
    machine.call('shadowrun_dialogue_dispatch')
    s = machine.snapshot()
    assert (s['shadowrun_dialogue_flag27'], s['shadowrun_dialogue_result'], s['shadowrun_dialogue_value']) == (0xa1, 2, 0xf5ab0)
    machine.set_state({'shadowrun_dialogue_result': 1, 'shadowrun_dialogue_value': 0xe9})
    machine.call('shadowrun_dialogue_dispatch')
    assert machine.snapshot()['shadowrun_dialogue_result'] == 4


def test_payment_dispatch_handoff():
    from fdisbull.game_il import GameMachine, author_program
    from fdisbull.shadowrun_dialogue import SOURCE
    machine = GameMachine(author_program(SOURCE.read_text()), {})
    machine.set_state({'shadowrun_dialogue_result': 1, 'shadowrun_dialogue_value': 6,
        'shadowrun_dialogue_wallet': 20, 'shadowrun_dialogue_charge': 20})
    machine.call('shadowrun_dialogue_dispatch')
    state = machine.snapshot()
    assert (state['shadowrun_dialogue_result'], state['shadowrun_dialogue_value'],
            state['shadowrun_dialogue_wallet'], state['shadowrun_dialogue_charge']) == (2, 0xf5ab8, 0, 255)


@pytest.mark.parametrize('scene_id', [True, False, 2.0, '2', None, -1, 56])
def test_world_rejects_noninteger_or_out_of_range_scene_id(scene_id):
    with pytest.raises(WorldFormatError, match='scene ID'):
        read_scene(b'', scene_id)


@pytest.mark.parametrize('budget', [True, False, 1.0, '1', None, -1, 0, 65537])
def test_stream_rejects_invalid_output_budget(budget):
    from fdisbull.shadowrun_world import decode_stream
    with pytest.raises(WorldFormatError, match='output budget'):
        decode_stream(bytes([0, 0, 0, 65]), 0, max_output=budget)


@pytest.mark.parametrize('address', [True, False, 0.0, '0', None, -1])
def test_stream_rejects_invalid_address_type_or_range(address):
    from fdisbull.shadowrun_world import decode_stream
    with pytest.raises(WorldFormatError, match='stream address'):
        decode_stream(bytes([0, 0, 0, 65]), address)


def test_stream_accepts_valid_budget_boundaries():
    from fdisbull.shadowrun_world import decode_stream
    data = bytes([0, 0, 0, 65])
    assert decode_stream(data, 0, max_output=1)[0] == b'A'
    assert decode_stream(data, 0, max_output=65536)[0] == b'A'
