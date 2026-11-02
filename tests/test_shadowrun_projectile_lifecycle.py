from fdisbull.game_il import GameMachine,author_program
from fdisbull.shadowrun_projectile_lifecycle import SOURCE

def test_primary_retirement_and_refusal():
    m=GameMachine(author_program(SOURCE.read_text()),{})
    m.set_state({'shadowrun_lifecycle_animation':0x8000,'shadowrun_lifecycle_flags':9,'shadowrun_lifecycle_repeat':0})
    m.call('shadowrun_lifecycle_primary');s=m.snapshot()
    assert (s['shadowrun_lifecycle_supported'],s['shadowrun_lifecycle_flags'],s['shadowrun_lifecycle_repeat'])==(1,8,255)
    m.set_state({'shadowrun_lifecycle_flags':9,'shadowrun_lifecycle_repeat':1})
    m.call('shadowrun_lifecycle_primary');s=m.snapshot()
    assert (s['shadowrun_lifecycle_supported'],s['shadowrun_lifecycle_flags'],s['shadowrun_lifecycle_repeat'])==(0,9,1)

def test_secondary_waits_for_animation_and_clears_only_active_bit():
    m=GameMachine(author_program(SOURCE.read_text()),{})
    m.set_state({'shadowrun_lifecycle_animation':0x7fff,'shadowrun_lifecycle_flags':9})
    m.call('shadowrun_lifecycle_secondary');assert m.snapshot()['shadowrun_lifecycle_flags']==9
    m.set_state({'shadowrun_lifecycle_animation':0x8000});m.call('shadowrun_lifecycle_secondary')
    assert m.snapshot()['shadowrun_lifecycle_flags']==8

def test_captured_impact_animation_reaches_source_retirement_gate():
    m=GameMachine(author_program(SOURCE.read_text()),{})
    m.set_state({'shadowrun_lifecycle_profile':1,'shadowrun_lifecycle_animation':0,
      'shadowrun_lifecycle_accumulator':14,'shadowrun_lifecycle_frame':0,
      'shadowrun_lifecycle_flags_low':9,'shadowrun_lifecycle_flags':9,'shadowrun_lifecycle_repeat':0})
    for _ in range(6):m.call('shadowrun_lifecycle_animate')
    s=m.snapshot()
    assert (s['shadowrun_lifecycle_supported'],s['shadowrun_lifecycle_animation'],
            s['shadowrun_lifecycle_frame'],s['shadowrun_lifecycle_accumulator']) == (1,0x8000,2,14)
    m.call('shadowrun_lifecycle_primary');s=m.snapshot()
    assert (s['shadowrun_lifecycle_flags'],s['shadowrun_lifecycle_repeat']) == (8,255)
