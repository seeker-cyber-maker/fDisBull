"""Authored camera contracts; original-ROM CPU comparisons are separate."""
import hashlib
import pytest
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_camera import SOURCE, lift_camera


def machine():
    # Zero vectors are deliberately authored inputs, not retained game data.
    raw = bytes(0x15f56)
    program = author_program(SOURCE.read_text(), [
        {'id': 0, 'length': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}])
    return GameMachine(program, {0: raw})


@pytest.mark.parametrize(('freeze', 'expected'), [('', 3968), ('a', 4000),
                                                ('b', 4000), ('c', 4000)])
def test_freeze_updates_hysteresis_but_preserves_camera(freeze, expected):
    model = machine()
    state = {f'shadowrun_camera_{k}': v for k, v in {
        'player_x': 5000, 'player_y': 5000, 'x': 4000, 'y': 4000,
        'max_x': 0x7fff, 'max_y': 0x7fff}.items()}
    if freeze:
        state['shadowrun_camera_freeze_' + freeze] = 1
    model.set_state(state)
    model.call('shadowrun_camera_tick')
    result = model.snapshot()
    assert result['shadowrun_camera_x'] == expected
    assert result['shadowrun_camera_y'] == expected
    assert result['shadowrun_camera_previous_x'] == 254
    assert result['shadowrun_camera_previous_y'] == 254
    assert result['shadowrun_camera_supported'] == 1


def test_scripted_camera_fails_closed_before_reading_external_table():
    model = GameMachine(author_program(SOURCE.read_text()))
    model.set_state({'shadowrun_camera_mode': 3, 'shadowrun_camera_x': 17,
                     'shadowrun_camera_request_x': 1})
    model.call('shadowrun_camera_tick')
    result = model.snapshot()
    assert result['shadowrun_camera_x'] == 17
    assert result['shadowrun_camera_supported'] == 0
    assert result['shadowrun_camera_request_x'] == 0


def test_hysteresis_boundaries_and_direction_reversal():
    harness = SOURCE.read_text() + '''
i16 result;
void check(u16 center, u16 target, u8 previous) {
    result = shadowrun_camera_axis_step(center, target, previous);
}
'''
    model = GameMachine(author_program(harness))
    for center, target, prior, expected in [
        (1000, 1000, 0, 0), (1000, 1001, 1, 1), (1000, 999, 1, 0),
        (1000, 1383, 2, 0), (1000, 1384, 2, 2), (1000, 1384, 0, 1),
        (1000, 1767, 1, 1), (1000, 1768, 0, 2),
        (1000, 616, 254, -2), (1000, 616, 0, -1)]:
        model.call('check', center, target, prior)
        assert model.snapshot()['result'] == expected


def test_camera_lift_rejects_unqualified_input():
    with pytest.raises(ValueError, match='exact reviewed'):
        lift_camera(bytes(2097152))
