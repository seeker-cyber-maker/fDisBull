"""Source-constructed assisted arena and bounded player/enemy controller.

The caller chooses the stationary or moving assisted preset. The shared frame
controller models supported inputs and source-qualified combat branches, and
stops on unmodeled states; it is not a naturally reached encounter or general AI.
"""
import hashlib
from pathlib import Path
from .game_il import GameMachine, author_program, emit_c
from .shadowrun_ai_play import lift_actor_service, actor_service_from_capture
from .shadowrun_hostile import lift_hostile, SOURCE as HOSTILE_SOURCE
from .shadowrun_hostile_motion import lift_hostile_motion, SOURCE as MOTION_SOURCE
from .shadowrun_player_damage import lift_player_damage, SOURCE as DAMAGE_SOURCE
from .shadowrun_hostile_received_hit import SOURCE as RECEIVED_SOURCE
from .shadowrun_hostile_linked import lift_hostile_linked, SOURCE as LINKED_SOURCE
from .shadowrun_player_attack import lift_player_attack, SOURCE as ATTACK_SOURCE
from .shadowrun_player_reaction import lift_player_reaction, SOURCE as REACTION_SOURCE
from .shadowrun_player_reaction_step import lift_player_reaction_step, SOURCE as REACTION_STEP_SOURCE
from .shadowrun_player_reaction_resume import lift_player_reaction_resume, SOURCE as REACTION_RESUME_SOURCE
from .shadowrun_player_reaction_held import lift_player_reaction_held, SOURCE as REACTION_HELD_SOURCE
from .shadowrun_hostile_stationary import lift_hostile_stationary, SOURCE as HOSTILE_STATIONARY_SOURCE
from .shadowrun_hostile_attack_first import lift_hostile_attack_first, SOURCE as HOSTILE_FIRST_SOURCE
from .shadowrun_hostile_idle_service import lift_hostile_idle_service, SOURCE as HOSTILE_IDLE_SOURCE
from .shadowrun_hostile_relaunch import lift_hostile_relaunch, SOURCE as HOSTILE_RELAUNCH_SOURCE
from .shadowrun_hostile_expired_pose import lift_hostile_expired_pose, SOURCE as HOSTILE_EXPIRED_SOURCE
from .shadowrun_hostile_zero_counter import lift_hostile_zero_counter, SOURCE as HOSTILE_ZERO_SOURCE
from .shadowrun_hostile_animation import SOURCE as ANIMATION_SOURCE
from .shadowrun_hostile_burst import SOURCE as BURST_SOURCE
from .shadowrun_hostile_self_hit import SOURCE as SELF_HIT_SOURCE
from .shadowrun_hostile_cycle import lift_hostile_cycle, SOURCE as CYCLE_SOURCE, TRANSACTION_SOURCE
from .shadowrun_replay import _source_capture
from .udl_shadowrun import ROM_SHA256

SOURCE=Path(__file__).parent/'game_sources/shadowrun_assisted_arena.c'
PLAYER_SOURCE=SOURCE.with_name('shadowrun_assisted_player.c')
CONTROLLER_SOURCE=SOURCE.with_name('shadowrun_assisted_controller.c')
ASSISTED_BURST_SOURCE=SOURCE.with_name('shadowrun_assisted_burst.c')
ASSISTED_POSE_SOURCE=SOURCE.with_name('shadowrun_assisted_hostile_pose.c')
PURSUIT_SOURCES=tuple(SOURCE.with_name('shadowrun_'+name+'.c') for name in
    ('hostile_pursuit','hostile_move','hostile_pursuit_route','assisted_pursuit','animation','party_clock','hostile_moving_attack','hostile_moving_attack_reentry','player_combat_walk','player_combat_wall','player_combat_slide','player_reaction_direction','player_reaction_direction_expired','player_reaction_direction_down','hostile_moving_pose','hostile_moving_pose_58','player_reaction_idle_walk','hostile_moving_idle','hostile_moving_idle_18','hostile_moving_relaunch','hostile_moving_relaunch_repeat','hostile_expiry_cycle'))


def lift_assisted_arena(rom):
    world=lift_actor_service(rom)
    hostile=lift_hostile(rom);motion=lift_hostile_motion(rom);damage=lift_player_damage(rom)
    linked=lift_hostile_linked(rom)
    attack=lift_player_attack(rom)
    reaction=lift_player_reaction(rom)
    reaction_step=lift_player_reaction_step(rom)
    reaction_resume=lift_player_reaction_resume(rom)
    reaction_held=lift_player_reaction_held(rom)
    stationary=lift_hostile_stationary(rom);first=lift_hostile_attack_first(rom);idle=lift_hostile_idle_service(rom)
    relaunch=lift_hostile_relaunch(rom)
    expired=lift_hostile_expired_pose(rom)
    zero=lift_hostile_zero_counter(rom)
    cycle=lift_hostile_cycle(rom)
    paths=(HOSTILE_SOURCE,MOTION_SOURCE,DAMAGE_SOURCE,RECEIVED_SOURCE,LINKED_SOURCE,SOURCE,PLAYER_SOURCE,ATTACK_SOURCE,CONTROLLER_SOURCE,REACTION_SOURCE,
           ANIMATION_SOURCE,BURST_SOURCE,SELF_HIT_SOURCE,CYCLE_SOURCE,TRANSACTION_SOURCE,REACTION_STEP_SOURCE,ASSISTED_BURST_SOURCE,REACTION_RESUME_SOURCE,
           HOSTILE_STATIONARY_SOURCE,HOSTILE_FIRST_SOURCE,HOSTILE_IDLE_SOURCE,ASSISTED_POSE_SOURCE,HOSTILE_RELAUNCH_SOURCE,REACTION_HELD_SOURCE,HOSTILE_EXPIRED_SOURCE,HOSTILE_ZERO_SOURCE)
    raw=[p.read_bytes() for p in paths]
    for component,content in zip((hostile,motion,damage),raw):
        if component['evidence']['authoring_sha256']!=hashlib.sha256(content).hexdigest():
            raise ValueError('Arena component changed between lifts')
    if linked['evidence']['authoring_sha256'][-2:]!=[hashlib.sha256(x).hexdigest() for x in raw[3:5]]:
        raise ValueError('Player projectile component changed between lifts')
    if attack['evidence']['authoring_sha256']!=hashlib.sha256(raw[7]).hexdigest():
        raise ValueError('Player attack source changed between lifts')
    if reaction['evidence']['authoring_sha256'][-1]!=hashlib.sha256(raw[9]).hexdigest():
        raise ValueError('Player reaction source changed between lifts')
    if (cycle['evidence']['authoring_sha256']!=hashlib.sha256(raw[13]).hexdigest() or
        cycle['evidence']['transaction_sha256']!=hashlib.sha256(raw[14]).hexdigest()):
        raise ValueError('Hostile cycle source changed between lifts')
    if reaction_step['evidence']['authoring_sha256'][-1]!=hashlib.sha256(raw[15]).hexdigest():
        raise ValueError('Reaction step source changed between lifts')
    if reaction_resume['evidence']['authoring_sha256'][-1]!=hashlib.sha256(raw[17]).hexdigest():
        raise ValueError('Reaction resume source changed between lifts')
    if any(prog['evidence']['authoring_sha256'][-1]!=hashlib.sha256(content).hexdigest()
           for prog,content in zip((stationary,first,idle),raw[18:21])):
        raise ValueError('Hostile stationary source changed between lifts')
    if relaunch['evidence']['authoring_sha256'][-1]!=hashlib.sha256(raw[22]).hexdigest():
        raise ValueError('Hostile relaunch source changed between lifts')
    if reaction_held['evidence']['authoring_sha256'][-1]!=hashlib.sha256(raw[23]).hexdigest():
        raise ValueError('Held recovery source changed between lifts')
    if expired['evidence']['authoring_sha256'][-1]!=hashlib.sha256(raw[24]).hexdigest():
        raise ValueError('Expired hostile pose source changed between lifts')
    if zero['evidence']['authoring_sha256'][-1]!=hashlib.sha256(raw[25]).hexdigest():
        raise ValueError('Hostile zero-counter source changed between lifts')
    world_source=emit_c(world)
    old='total >= 4';typedef='typedef unsigned char u8;'
    if world_source.count(old)!=1 or world_source.count(typedef)!=1:
        raise ValueError('Captured attack roll source changed')
    world_source=world_source.replace(typedef,typedef+'\nu8 shadowrun_player_attack_difficulty,shadowrun_arena_moving_profile,shadowrun_player_combat_attribute,shadowrun_player_combat_walk_supported,shadowrun_player_combat_wall_supported,shadowrun_player_combat_slide_supported;\nvoid shadowrun_player_combat_walk(void);void shadowrun_player_combat_wall_stop(void);void shadowrun_player_combat_slide(void);',1)
    world_source=world_source.replace(old,'total >= shadowrun_player_attack_difficulty',1)
    walk='shadowrun_player_walk_bounded();'
    if world_source.count(walk)!=1:raise ValueError('Opening walk source changed')
    world_source=world_source.replace(walk,'if (shadowrun_arena_moving_profile) { shadowrun_player_combat_walk(); if (!shadowrun_player_combat_walk_supported) { shadowrun_player_combat_wall_stop(); if (shadowrun_player_combat_wall_supported) shadowrun_player_combat_walk_supported=1; else { shadowrun_player_combat_slide(); if (shadowrun_player_combat_slide_supported) shadowrun_player_combat_walk_supported=1; } } shadowrun_player_walk_result=shadowrun_player_combat_walk_supported; } else shadowrun_player_walk_bounded();',1)
    pursuit_raw=[p.read_bytes() for p in PURSUIT_SOURCES]
    ordered=raw[:5]+raw[9:16]+raw[17:21]+raw[22:26]+raw[5:6]+raw[7:8]+raw[6:7]+pursuit_raw+raw[16:17]+raw[21:22]+raw[8:9]
    extra='\n'.join(line for content in ordered for line in content.decode().splitlines()
                    if not line.startswith(('typedef ','extern ')) and line not in ('u8 shadowrun_player_attack_difficulty;','u8 shadowrun_player_combat_attribute,shadowrun_player_combat_walk_supported;','u8 shadowrun_player_combat_wall_supported;','u8 shadowrun_player_combat_slide_supported;'))
    result=author_program(world_source+'\n'+extra,
        [{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
            'kind':'source-constructed-assisted-arena-diagnostic',
            'components':[world['evidence'],hostile['evidence'],motion['evidence'],damage['evidence'],linked['evidence'],attack['evidence'],reaction['evidence'],cycle['evidence'],reaction_step['evidence'],reaction_resume['evidence'],stationary['evidence'],first['evidence'],idle['evidence'],relaunch['evidence'],reaction_held['evidence'],expired['evidence'],zero['evidence']],
            'adapter_sha256':[hashlib.sha256(x).hexdigest() for x in (raw[5],raw[6],raw[8],raw[16],raw[21],*pursuit_raw)],
            'attack_roll_rewrite':'captured roll threshold4 replaced by qualified health-derived difficulty',
            'scope':'bounded assisted controller with source-qualified actor, projectile and captured-player damage branches',
            'excluded':['natural encounter','general actor AI','scene loading','player death continuation']})
    if (any(p.read_bytes()!=content for p,content in zip(paths,raw)) or
        any(p.read_bytes()!=content for p,content in zip(PURSUIT_SOURCES,pursuit_raw))):
        raise ValueError('Arena sources changed during lifting')
    return result


def assisted_arena_from_capture(rom, snapshot_path, *, moving=False):
    """Prepare an independent assisted scene-2 arena state.

    The original scene-54 actor is relocated and other NPCs are removed. This
    is an assisted setup, not a natural route or a game save. ``moving=True``
    selects the separately checked initial cooldown and moving-hostile branch.
    """
    baseline=actor_service_from_capture(rom,snapshot_path)
    _,arrays,_=_source_capture(snapshot_path,ROM_SHA256)
    raw=arrays['ram'];memory=bytes(raw[i^1] for i in range(len(raw)))
    word=lambda offset:int.from_bytes(memory[offset:offset+2],'big')
    machine=GameMachine(lift_assisted_arena(rom),{0:rom})
    machine.set_state(baseline.snapshot())
    state=machine.snapshot()
    if (state['shadowrun_player_x'],state['shadowrun_player_y'],state['shadowrun_camera_x'],state['shadowrun_camera_y'])!=(15584,11210,13312,10016):
        raise ValueError('Unexpected assisted arena source geometry')
    machine.set_state({'shadowrun_arena_profile':1,'shadowrun_arena_hp':10,'shadowrun_arena_armor':1,
        'shadowrun_arena_player_ready':1,'shadowrun_arena_player_sprite_current':1,'shadowrun_player_attack_difficulty':4,
        'shadowrun_reaction_increment':word(0x118),'shadowrun_reaction_accumulator':word(0x11a),
        'shadowrun_reaction_threshold':word(0x11c),'shadowrun_reaction_index':word(0x11e),
        'shadowrun_reaction_cursor':memory[0x143],'shadowrun_reaction_attr_a':memory[0x178],
        'shadowrun_reaction_attr_b':memory[0x17b],'shadowrun_reaction_gear':word(0x190),
        'shadowrun_reaction_speed':word(0x1ca),'shadowrun_reaction_input_flags':word(0xdd22),
        'shadowrun_reaction_input_heading':word(0xdd04),'shadowrun_reaction_global_e6':word(0xdfe6),
        'shadowrun_reaction_global_3a':word(0xdf3a),'shadowrun_reaction_global_18a':memory[0xe18a],
        'shadowrun_reaction_global_18b':memory[0xe18b],
        'shadowrun_hostile_x':16096,'shadowrun_hostile_y':11210,'shadowrun_hostile_contact':203,
        'shadowrun_hostile_timer':0,'shadowrun_hostile_cooldown':0,'shadowrun_hostile_ammo':48,'shadowrun_hostile_rng':2,
        'shadowrun_target_flags':[5,0,0,0,0,0,0], 'shadowrun_target_flags_low':[0]*7,
        'shadowrun_target_x':[16096,0,0,0,0,0,0], 'shadowrun_target_y':[11210,0,0,0,0,0,0],
        'shadowrun_target_index':[3,0,0,0,0,0,0], 'shadowrun_play_actor_hp':[10,0,0,0,0,0,0],
        'shadowrun_ai_slot_status':[0]*7})
    if moving:
        machine.set_state({'shadowrun_arena_moving_profile':1,'shadowrun_hostile_cooldown':2,
            'shadowrun_ai_kind':8,'shadowrun_ai_flags':5,'shadowrun_ai_attribute':5,
            'shadowrun_ai_combat_global':1,'shadowrun_ai_distance':65535,'shadowrun_ai_speed':65535,
            'shadowrun_ai_callback':0xb45c,'shadowrun_pursuit_route_sprite_increment':4096,
            'shadowrun_pursuit_route_sprite_threshold':4096,
            'shadowrun_player_combat_attribute':3,'shadowrun_player_combat_global':1,
            'shadowrun_anim_increment':word(0x118),'shadowrun_anim_accumulator':word(0x11a),
            'shadowrun_anim_threshold':word(0x11c),'shadowrun_anim_index':word(0x11e)})
    return machine
