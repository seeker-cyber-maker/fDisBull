"""Assisted wrapper refuses unsupported progression and passes damage through."""
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_assisted_arena import SOURCE, CONTROLLER_SOURCE


def machine():
    prefix='''typedef unsigned char u8;typedef unsigned int u16;typedef unsigned long u32;
    u16 shadowrun_player_x,shadowrun_player_y,shadowrun_player_kind,shadowrun_player_heading,shadowrun_play_shot_timer;
    u8 shadowrun_player_flags,shadowrun_player_flags_low;
    u16 shadowrun_reaction_kind,shadowrun_reaction_x,shadowrun_reaction_y,shadowrun_reaction_heading,shadowrun_reaction_action_timer;
    u8 shadowrun_reaction_flags,shadowrun_reaction_hp,shadowrun_reaction_max_hp,shadowrun_reaction_flags_low,shadowrun_reaction_supported;
    void shadowrun_reaction_start(void){shadowrun_reaction_supported=1;}
    u16 shadowrun_hostile_x,shadowrun_hostile_y,shadowrun_hostile_player_x,shadowrun_hostile_player_y;
    u16 shadowrun_hostile_timer,shadowrun_hostile_cooldown,shadowrun_hostile_rng;
    u16 shadowrun_hostile_projectile_x,shadowrun_hostile_projectile_y,shadowrun_hostile_velocity_x,shadowrun_hostile_velocity_y;
    u8 shadowrun_hostile_profile,shadowrun_hostile_supported,shadowrun_hostile_pursuit_required,shadowrun_play_shot_eligible;
    u8 shadowrun_play_actor_hp[7],shadowrun_target_flags[7],shadowrun_target_flags_low[7],shadowrun_target_backlink[7];
    u8 shadowrun_target_selected,shadowrun_target_player_backlink;
    u16 shadowrun_target_x[7],shadowrun_target_y[7],shadowrun_target_marker[7];
    u8 shadowrun_hostile_fired,shadowrun_hostile_lifetime,shadowrun_hostile_effect;
    u32 shadowrun_hostile_motion_x,shadowrun_hostile_motion_y;
    u16 shadowrun_hostile_motion_vx,shadowrun_hostile_motion_vy,shadowrun_hostile_motion_player_x,shadowrun_hostile_motion_player_y;
    u8 shadowrun_hostile_motion_profile,shadowrun_hostile_motion_supported,shadowrun_hostile_motion_state;
    u8 shadowrun_hostile_motion_lifetime,shadowrun_hostile_motion_effect,shadowrun_hostile_motion_steps,shadowrun_hostile_motion_continuation_required;
    u8 shadowrun_player_damage_profile,shadowrun_player_damage_item,shadowrun_player_damage_effect;
    u8 shadowrun_player_damage_armor,shadowrun_player_damage_hp,shadowrun_player_damage_supported,shadowrun_player_damage_depleted,shadowrun_player_damage_amount;
    u16 shadowrun_player_damage_rng;
    void shadowrun_hostile_tick(void){shadowrun_hostile_supported=1;shadowrun_hostile_fired=1;
        shadowrun_hostile_projectile_x=400;shadowrun_hostile_projectile_y=500;shadowrun_hostile_effect=5;}
    void shadowrun_hostile_motion_tick(void){shadowrun_hostile_motion_supported=1;shadowrun_hostile_motion_state=2;}
    void shadowrun_player_hit(void){shadowrun_player_damage_supported=1;shadowrun_player_damage_hp-=3;shadowrun_player_damage_amount=3;}
    '''
    return GameMachine(author_program(prefix+SOURCE.read_text()),{})


def test_explicit_steps_apply_damage_and_refuse_unsupported_cooldown():
    m=machine();m.set_state({'shadowrun_arena_profile':1,'shadowrun_arena_hp':10,'shadowrun_arena_armor':1,'shadowrun_play_actor_hp':[10,0,0,0,0,0,0],
                              'shadowrun_target_flags':[5,0,0,0,0,0,0],
                              'shadowrun_arena_player_ready':1,'shadowrun_arena_player_sprite_current':1,'shadowrun_play_shot_eligible':1,
                              'shadowrun_hostile_cooldown':2})
    m.call('shadowrun_arena_launch');s=m.snapshot()
    assert s['shadowrun_arena_supported']==0 and s['shadowrun_hostile_fired']==0
    m.set_state({'shadowrun_hostile_cooldown':0});m.call('shadowrun_arena_launch')
    assert m.snapshot()['shadowrun_hostile_motion_state']==1
    m.call('shadowrun_arena_projectile_step');s=m.snapshot()
    assert (s['shadowrun_arena_hp'],s['shadowrun_player_damage_item'],s['shadowrun_arena_supported'])==(7,10,1)
    assert (s['shadowrun_arena_player_ready'],s['shadowrun_play_shot_eligible'])==(0,0)


def controller_machine():
    prefix='''typedef unsigned char u8;typedef unsigned int u16;
    u8 shadowrun_arena_profile,shadowrun_play_refused,shadowrun_play_menu,shadowrun_arena_armor,shadowrun_inventory_equipped_armor,shadowrun_arena_depleted;
    u8 shadowrun_arena_player_ready,shadowrun_arena_player_sprite_current,shadowrun_reaction_step_supported,shadowrun_reaction_step_result,shadowrun_reaction_held_supported;
    u8 shadowrun_reaction_resume_supported,shadowrun_play_shot_eligible,shadowrun_player_flags_low,shadowrun_reaction_flags_low;
    u8 shadowrun_arena_burst_active,shadowrun_reaction_sprite_supported,shadowrun_hostile_fired,shadowrun_burst_flags_low;
    u8 shadowrun_arena_hostile_pose_ready,shadowrun_arena_player_hit_event,shadowrun_attack_hp,shadowrun_attack_ammo,shadowrun_attack_counter;
    u8 shadowrun_hostile_ammo,shadowrun_attack_supported,shadowrun_attack_positive_supported,shadowrun_hostile_idle_supported,shadowrun_play_actor_hp[7];
    u16 shadowrun_attack_x,shadowrun_attack_y,shadowrun_attack_player_x,shadowrun_attack_player_y;
    u16 shadowrun_hostile_x,shadowrun_hostile_y,shadowrun_player_x,shadowrun_player_y,shadowrun_attack_animation,shadowrun_burst_anim_word;
    unsigned long shadowrun_attack_callback;
    u16 shadowrun_reaction_action_timer,shadowrun_reaction_input_flags,shadowrun_reaction_global_e6;unsigned long shadowrun_player_callback,shadowrun_reaction_callback;
    u8 shadowrun_linked_motion_state,shadowrun_hostile_motion_state,shadowrun_hostile_motion_continuation_required;
    u8 shadowrun_arena_player_supported,shadowrun_arena_supported;u16 shadowrun_play_shot_timer;
    u8 shadowrun_arena_moving_profile,shadowrun_arena_pursuit_started,shadowrun_party_flags_low,shadowrun_party_clock_supported,shadowrun_player_combat_walk_supported,shadowrun_moving_pose_supported,shadowrun_moving_idle_supported;
    u16 shadowrun_pursuit_route_service_timer,shadowrun_party_kind,shadowrun_party_heading,shadowrun_party_transition_heading,shadowrun_party_speed;
    u16 shadowrun_player_heading,shadowrun_player_transition_heading,shadowrun_player_step_timer,shadowrun_reaction_speed;
    u16 shadowrun_reaction_increment,shadowrun_reaction_accumulator,shadowrun_reaction_threshold,shadowrun_reaction_index;
    u16 shadowrun_anim_increment,shadowrun_anim_accumulator,shadowrun_anim_threshold,shadowrun_anim_index;
    u16 shadowrun_reaction_input_heading,shadowrun_reaction_target_heading,shadowrun_player_target_heading,shadowrun_reaction_normal_sprite_speed;
    u8 shadowrun_reaction_direction_supported,shadowrun_reaction_idle_walk_supported;
    unsigned long shadowrun_party_callback;
    void shadowrun_party_pose_tick(void){} void shadowrun_party_clock_tick(void){} void shadowrun_arena_pursuit_step(void){}
    u16 shadowrun_camera_x,shadowrun_camera_y,shadowrun_x_min,shadowrun_x_max,shadowrun_y_min,shadowrun_y_max;
    u8 shadowrun_terrain_map[2816],shadowrun_opening_status,shot_admitted;
    u8 play_calls,hostile_calls;
    void shadowrun_play_frame(u8 p){play_calls++;} void shadowrun_opening_frame(u8 p){play_calls++;}
    void shadowrun_arena_player_step(void){} void shadowrun_arena_player_launch(void){shadowrun_arena_player_supported=shot_admitted;}
    void shadowrun_arena_projectile_step(void){} void shadowrun_arena_same_loop(void){hostile_calls++;shadowrun_arena_supported=1;}
    void shadowrun_reaction_step(void){} void shadowrun_reaction_resume_idle(void){}
    void shadowrun_reaction_resume_held(void){}
    void shadowrun_reaction_resume_direction(void){}
    void shadowrun_reaction_resume_idle_walk(void){}
    void shadowrun_arena_burst_step(void){} void shadowrun_arena_burst_prepare(void){}
    void shadowrun_arena_burst_first_sprite(void){} void shadowrun_reaction_sprite_only(void){}
    void shadowrun_hostile_attack_step(void){} void shadowrun_hostile_idle_actor_pass(void){}
    void shadowrun_hostile_attack_expired_step(void){}
    void shadowrun_hostile_moving_pose_step(void){}
    void shadowrun_hostile_moving_idle_step(void){}
    void shadowrun_hostile_attack_zero_counter_step(void){} void shadowrun_hostile_idle_zero_counter_step(void){}
    void shadowrun_hostile_attack_positive_step(void){} void shadowrun_hostile_positive_reentry_step(void){} void shadowrun_arena_hostile_relaunch(void){}
    void shadowrun_hostile_idle_sprite_pass(void){} void shadowrun_arena_hostile_first_pose(void){}
    '''
    return GameMachine(author_program(prefix+CONTROLLER_SOURCE.read_text()),{})


def test_controller_stops_before_advancing_unknown_projectile():
    m=controller_machine()
    m.set_state({'shadowrun_arena_profile':1,'shadowrun_hostile_motion_continuation_required':1})
    m.call('shadowrun_arena_frame',8);s=m.snapshot()
    assert (s['shadowrun_arena_frame_status'],s['shadowrun_play_refused'],s['play_calls'],s['hostile_calls'])==(2,1,0,0)


def test_z_firing_boundary_is_atomic_and_admitted_shot_advances(monkeypatch):
    import hashlib
    from fdisbull import shadowrun_world, shadowrun_city
    from fdisbull.shadowrun_z import ShadowrunRuntime
    m=controller_machine()
    m.regions[0]=b'controller fixture'
    monkeypatch.setattr(shadowrun_world,'SOURCE_SHA256',hashlib.sha256(m.regions[0]).hexdigest())
    monkeypatch.setattr(shadowrun_city,'SOURCE_SHA256',hashlib.sha256(m.regions[0]).hexdigest())
    m.set_state({'shadowrun_arena_profile':1,'shadowrun_arena_player_ready':1,
                 'shadowrun_play_shot_timer':65535,'shadowrun_arena_player_pending':1,
                 'shadowrun_x_max':1876,'shadowrun_y_max':1304})
    runtime=ShadowrunRuntime(m);before=runtime.machine.snapshot()
    rejected=runtime.advance(64)
    assert rejected['status']=='unsupported' and rejected['frames_executed']==0
    assert runtime.machine.snapshot()==before
    direct=controller_machine();direct.set_state(before);direct.call('shadowrun_arena_frame',64)
    state=direct.snapshot()
    assert (state['shadowrun_arena_frame_status'],state['shadowrun_play_shot_timer'],state['shadowrun_arena_player_pending'])==(2,65535,1)
    m.set_state({'shot_admitted':1});runtime=ShadowrunRuntime(m);accepted=runtime.advance(64)
    assert accepted['status']=='advanced'
    assert (runtime.machine.snapshot()['shadowrun_play_shot_timer'],runtime.machine.snapshot()['shadowrun_arena_player_pending'])==(51,0)
