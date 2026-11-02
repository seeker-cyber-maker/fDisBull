"""Contract checks without private ROM data; native qualification is separate."""
import pytest
from fdisbull.game_il import GameMachine, author_program
from fdisbull import shadowrun_combat as combat, shadowrun_inventory as inventory

@pytest.fixture
def inv():
    return GameMachine(author_program(inventory.SOURCE.read_text()), {})

@pytest.fixture
def fight():
    return GameMachine(author_program(combat.SOURCE.read_text()), {})

def test_inventory_selection_and_invalid_cursor(inv):
    inv.set_state({'shadowrun_inventory_row':3,'shadowrun_inventory_column':1,'shadowrun_inventory_cell7':49})
    inv.call('shadowrun_inventory_select')
    assert inv.snapshot()['shadowrun_inventory_item'] == 49
    inv.set_state({'shadowrun_inventory_row':4,'shadowrun_inventory_item':49})
    inv.call('shadowrun_inventory_select')
    assert inv.snapshot()['shadowrun_inventory_valid'] == 0
    assert inv.snapshot()['shadowrun_inventory_item'] == 49

def test_armor_branch_and_stat_boundary(inv, fight):
    inv.set_state({'shadowrun_inventory_item':44,'shadowrun_inventory_equipped_armor':0})
    inv.call('shadowrun_inventory_armor_branch')
    assert inv.snapshot()['shadowrun_inventory_equipped_armor'] == 1
    assert inv.snapshot()['shadowrun_inventory_selected_phase'] == 1
    inv.call('shadowrun_inventory_armor_branch')
    assert inv.snapshot()['shadowrun_inventory_equipped_armor'] == 0
    assert inv.snapshot()['shadowrun_inventory_selected_phase'] == 0
    fight.set_state({'shadowrun_combat_baseline':8,'shadowrun_combat_skill':3})
    fight.call('shadowrun_combat_skill_stat')
    assert fight.snapshot()['shadowrun_combat_attack_stat'] == 6
    fight.set_state({'shadowrun_combat_baseline':32768})
    fight.call('shadowrun_combat_skill_stat')
    assert fight.snapshot()['shadowrun_combat_supported'] == 0

def test_posture_clamp_and_refusal(fight):
    fight.set_state({'shadowrun_combat_posture':0,'shadowrun_combat_posture_delta':255})
    fight.call('shadowrun_combat_change_posture')
    assert fight.snapshot()['shadowrun_combat_posture'] == 0
    fight.set_state({'shadowrun_combat_posture':4,'shadowrun_combat_posture_delta':1})
    fight.call('shadowrun_combat_change_posture')
    assert fight.snapshot()['shadowrun_combat_posture'] == 4
    fight.set_state({'shadowrun_combat_posture_delta':2})
    fight.call('shadowrun_combat_change_posture')
    assert fight.snapshot()['shadowrun_combat_posture_supported'] == 0

def test_profiles_reject_unreviewed_rom():
    for module in (combat, inventory):
        with pytest.raises(ValueError):
            getattr(module, 'lift_' + ('combat' if module is combat else 'inventory'))(b'')

def test_effect_adjust_preserves_early_return_byte(fight):
    fight.set_state({'shadowrun_combat_effect_input':10,'shadowrun_combat_effect_reference':16,'shadowrun_combat_effect_value':5})
    fight.call('shadowrun_combat_effect_adjust')
    state=fight.snapshot()
    assert (state['shadowrun_combat_effect_supported'],state['shadowrun_combat_effect_value'],state['shadowrun_combat_effect_proceeds']) == (1,255,0)
    fight.set_state({'shadowrun_combat_effect_input':20,'shadowrun_combat_effect_reference':10,'shadowrun_combat_effect_value':5})
    fight.call('shadowrun_combat_effect_adjust')
    state=fight.snapshot()
    assert (state['shadowrun_combat_effect_value'],state['shadowrun_combat_effect_proceeds']) == (10,1)

def test_hp_application_and_depletion_boundary(fight):
    fight.set_state({'shadowrun_combat_hp_primary':8,'shadowrun_combat_hp_alternate':3,'shadowrun_combat_hp_selector':1,'shadowrun_combat_hp_target_flags':0,'shadowrun_combat_hp_damage':5})
    fight.call('shadowrun_combat_apply_hp')
    state=fight.snapshot()
    assert (state['shadowrun_combat_hp_primary'],state['shadowrun_combat_hp_alternate'],state['shadowrun_combat_hp_selector'],state['shadowrun_combat_hp_depleted']) == (8,0,0,1)
    fight.set_state({'shadowrun_combat_hp_primary':8,'shadowrun_combat_hp_target_flags':128,'shadowrun_combat_hp_damage':5})
    fight.call('shadowrun_combat_apply_hp')
    assert fight.snapshot()['shadowrun_combat_hp_primary'] == 7
