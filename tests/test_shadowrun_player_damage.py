"""Regression values observed at the controlled original damage boundary."""
import hashlib

import pytest

from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_player_damage import SOURCE, lift_player_damage
from fdisbull.shadowrun_player_attack import SOURCE as ATTACK_SOURCE


@pytest.fixture(scope='module')
def model_inputs():
    # Synthetic carrier for semantic weapon/armor facts, not a game image.
    data = bytearray(0x166AD8)
    weapons = {2: (0, 6), 6: (1, 9), 10: (1, 6), 12: (2, 9)}
    for item, (grade, power) in weapons.items():
        row = 0xD4540 + (item - 1) * 48
        data[row + 37], data[row + 38] = grade, power
    for armor, reduction in ((1, 2), (3, 5)):
        data[0xD4D50 + (armor - 1) * 48 + 37] = reduction
    data[0x166AD4:0x166AD7] = bytes((255, 253, 250))
    data = bytes(data)
    program = author_program(SOURCE.read_text(),
        [{'id': 0, 'length': len(data), 'sha256': hashlib.sha256(data).hexdigest()}])
    return program, data


@pytest.mark.parametrize('values,expected', [
    ((2, 1, 10, 0, 0), (10, 3499, 1)),
    ((6, 3, 5, 4, 21845), (4, 13372, 1)),
    ((10, 0, 10, 5, 2), (5, 52579, 3)),
    ((10, 1, 10, 5, 2), (7, 52579, 3)),
    ((12, 0, 1, 12, 65535), (0, 33118, 0)),
])
def test_original_defense_outcomes(model_inputs, values, expected):
    program, data = model_inputs
    machine = GameMachine(program, {0: data})
    item, armor, hp, effect, seed = values
    machine.set_state(dict(zip(
        ('shadowrun_player_damage_item', 'shadowrun_player_damage_armor',
         'shadowrun_player_damage_hp', 'shadowrun_player_damage_effect',
         'shadowrun_player_damage_rng'), values)))
    machine.set_state({'shadowrun_player_damage_profile': 1})
    machine.call('shadowrun_player_hit')
    state = machine.snapshot()
    assert state['shadowrun_player_damage_supported'] == 1
    assert tuple(state['shadowrun_player_damage_' + name]
                 for name in ('hp', 'rng', 'successes')) == expected
    assert state['shadowrun_player_damage_amount'] == hp - expected[0]
    assert state['shadowrun_player_damage_depleted'] == int(expected[0] == 0)


@pytest.mark.parametrize('field,value', [
    ('profile', 0), ('item', 0), ('item', 13), ('armor', 8), ('hp', 0),
    ('effect', 13),
])
def test_outside_profile_refuses_without_hp_rng_mutation(model_inputs, field, value):
    program, data = model_inputs
    machine = GameMachine(program, {0: data})
    machine.set_state({'shadowrun_player_damage_profile': 1,
        'shadowrun_player_damage_item': 2, 'shadowrun_player_damage_armor': 1,
        'shadowrun_player_damage_hp': 10, 'shadowrun_player_damage_effect': 5,
        'shadowrun_player_damage_rng': 2})
    machine.set_state({'shadowrun_player_damage_' + field: value})
    before = machine.snapshot()
    machine.call('shadowrun_player_hit')
    state = machine.snapshot()
    assert state['shadowrun_player_damage_supported'] == 0
    for name in ('hp', 'rng'):
        assert state['shadowrun_player_damage_' + name] == before['shadowrun_player_damage_' + name]


def test_damage_lifter_rejects_wrong_source():
    with pytest.raises(ValueError, match='exact reviewed'):
        lift_player_damage(bytes(2097152))


@pytest.mark.parametrize('hp,alternate,difficulty', [
    (10, 10, 4), (8, 8, 4), (7, 10, 5), (5, 7, 6), (4, 10, 6), (1, 1, 8),
])
def test_source_wound_modifier_changes_attack_difficulty(hp, alternate, difficulty):
    machine = GameMachine(author_program(ATTACK_SOURCE.read_text()), {})
    machine.set_state({'shadowrun_player_attack_hp': hp,
                       'shadowrun_player_attack_alternate_hp': alternate})
    machine.call('shadowrun_player_attack_threshold')
    state = machine.snapshot()
    assert state['shadowrun_player_attack_supported'] == 1
    assert state['shadowrun_player_attack_difficulty'] == difficulty
