"""Source-derived title-to-scene composition; every continuation is qualified separately."""
import hashlib
from pathlib import Path

from .game_il import GameMachine, author_program
from .shadowrun_snes_field import ROM_SHA256, SAVE_SHA256
from .shadowrun_snes_npc import FIELDS, SOURCE as NPC_SOURCE
from .shadowrun_snes_script import SOURCE as VM_SOURCE, tasks_from_capture
from .shadowrun_snes_task_init import SOURCE as TASK_SOURCE
from .shadowrun_snes_scene_init import SOURCE as SCENE_SOURCE, COLLISION_SOURCE, SCENE_TASK_WRAPPER, SCENE_PARTY_WRAPPER
from .shadowrun_snes_menu import SOURCE as MENU_SOURCE
from .shadowrun_snes_opening_collision import source_fragment, SOURCE as MOTION_SOURCE
from .shadowrun_snes_live import SOURCE as LIVE_SOURCE
from .shadowrun_snes_field import SOURCE as FIELD_SOURCE
from .shadowrun_snes_text import SOURCE as TEXT_SOURCE
from .shadowrun_snes_opening_window import SOURCE as WINDOW_SOURCE
from .shadowrun_snes_opening_anim import SOURCE as ANIM_SOURCE
from .shadowrun_snes_target import SOURCE as TARGET_SOURCE
from .shadowrun_snes_choice import SOURCE as CHOICE_SOURCE
from .shadowrun_snes_interaction import SOURCE as INTERACTION_SOURCE
from .shadowrun_snes_camera import SOURCE as CAMERA_SOURCE
from .shadowrun_snes_action_collision import SOURCE as ACTION_COLLISION_SOURCE
from .shadowrun_snes_transition import SOURCE as TRANSITION_SOURCE
from .shadowrun_snes_dialogue import SOURCE as DIALOGUE_SOURCE
from .shadowrun_snes_dialogue_select import SOURCE as DIALOGUE_SELECT_SOURCE
from .shadowrun_snes_conversation import SOURCE as CONVERSATION_SOURCE
from .shadowrun_snes_vertical import SOURCE as VERTICAL_SOURCE
from .shadowrun_snes_rng import SOURCE as RNG_SOURCE
from .shadowrun_snes_hardware import SOURCE as HARDWARE_SOURCE, configuration

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_snes_opening.c'
CONVERSATION_BRIDGE_SOURCE = Path(__file__).parent / 'game_sources/shadowrun_snes_conversation_bridge.c'
TITLE_SHA256 = '15caaf78faed99408c783119ac5e1703da066b904e5570dd895b7bcb49db9d93'


def machine_from_title(rom, title, save_ram, *, hardware_mode='disabled', hardware_seed=1):
    """Seed once at the qualified title state; derive subsequent state from ROM.

    The initial projection explicitly refuses unsupported callbacks/physics.
    It does not accept a later scene snapshot as a substitute for initialization.
    """
    if len(rom) != 1048576 or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('wrong SNES source')
    if len(title) != 131072 or hashlib.sha256(title).hexdigest() != TITLE_SHA256:
        raise ValueError('wrong source title checkpoint')
    if len(save_ram) != 8192 or hashlib.sha256(save_ram).hexdigest() != SAVE_SHA256:
        raise ValueError('wrong captured save RAM')
    hardware_configuration = configuration(hardware_mode, hardware_seed)
    prefix = ('typedef unsigned char u8;\ntypedef unsigned int u16;\n'
              'typedef unsigned long u32;\nu8 rom8(u8 region,u32 offset);\n')
    inputs = {p: p.read_text() for p in (VM_SOURCE, TASK_SOURCE, SCENE_SOURCE, COLLISION_SOURCE,
              NPC_SOURCE, MENU_SOURCE, MOTION_SOURCE, LIVE_SOURCE, FIELD_SOURCE, TEXT_SOURCE, WINDOW_SOURCE, ANIM_SOURCE, TARGET_SOURCE, CHOICE_SOURCE, INTERACTION_SOURCE, CAMERA_SOURCE, ACTION_COLLISION_SOURCE, TRANSITION_SOURCE, DIALOGUE_SOURCE, DIALOGUE_SELECT_SOURCE, CONVERSATION_SOURCE, CONVERSATION_BRIDGE_SOURCE, VERTICAL_SOURCE, RNG_SOURCE, HARDWARE_SOURCE, SOURCE)}
    scene = inputs[SCENE_SOURCE].replace(prefix + 'u8 task_shared[65536];\n', '')
    npc = inputs[NPC_SOURCE].replace(prefix, '')
    menu = inputs[MENU_SOURCE].replace('typedef unsigned char u8;\ntypedef unsigned int u16;\n', '')
    text_source = inputs[TEXT_SOURCE].replace(prefix, '')
    rng_source = inputs[RNG_SOURCE].replace(prefix, '')
    load = 'void opening_load(u16 slot){u16 i;npc_actor_id=slot;' + ''.join(
        f'{name}=scene_read({at}U+slot);' for name, at in FIELDS.items()) + '''
        npc_low_table_known=0U;
        if(npc_anim_table<=8184U){
          for(i=0U;i<8U;i+=1U)npc_low_table[i]=task_shared[npc_anim_table+i];
          npc_low_table_known=1U;
        }
        npc_follow_known=0U;
        if(!npc_target_x && !(npc_target_y&1U) && npc_target_y<88U){
          npc_follow_x=scene_read(0x0e44U+npc_target_y);
          npc_follow_y=scene_read(0x0e9cU+npc_target_y);npc_follow_known=1U;
        }}'''
    save = 'void opening_save(u16 slot){' + ''.join(
        f'scene_write({at}U+slot,{name});' for name, at in FIELDS.items()) + '}'
    text = '\n'.join((inputs[VM_SOURCE], inputs[TASK_SOURCE], scene, inputs[COLLISION_SOURCE], npc, menu,
                       SCENE_TASK_WRAPPER, SCENE_PARTY_WRAPPER, source_fragment(), text_source, rng_source, inputs[HARDWARE_SOURCE],
                       inputs[WINDOW_SOURCE], inputs[ANIM_SOURCE], inputs[TARGET_SOURCE],
                       inputs[CHOICE_SOURCE], inputs[INTERACTION_SOURCE], inputs[CAMERA_SOURCE],
                       inputs[ACTION_COLLISION_SOURCE], inputs[TRANSITION_SOURCE], inputs[DIALOGUE_SOURCE],
                       inputs[DIALOGUE_SELECT_SOURCE], inputs[CONVERSATION_SOURCE], inputs[VERTICAL_SOURCE], inputs[SOURCE],
                       load, save, inputs[CONVERSATION_BRIDGE_SOURCE]))
    program = author_program(text, [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}], evidence={
        'kind': 'source-title-room-task-conversation', 'source_sha256': ROM_SHA256,
        'title_sha256': TITLE_SHA256, 'authoring_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'clock': 'title input, logical source main-loop passes and typed suspended interaction/conversation polls; display waits adapted',
        'hardware_policy': hardware_mode,
        'hardware_seed': hardware_seed if hardware_mode == 'seeded' else None,
        'scope': 'source-derived scenes 3, 1F and 1, guarded movement/targeting/pickups, scripted responses and bounded keyword conversation; unobserved continuations, original raster and APU delivery excluded'})
    m = GameMachine(program, {0: rom})
    m.set_state(tasks_from_capture(rom, title).snapshot())
    m.set_state(hardware_configuration | {'task_counter_tainted': int(hardware_mode != 'disabled')})
    word = lambda at: int.from_bytes(title[at:at + 2], 'little')
    m.set_state({'scene_7f': list(title[65536:]), 'menu_selection': word(0xe),
                 'menu_disabled': [word(0x11c0 + i * 2) for i in range(3)],
                 'opening_rotation': int.from_bytes(save_ram[0x1ffd:0x1fff], 'little')})
    if any(p.read_text() != s for p, s in inputs.items()):
        raise ValueError('opening sources changed')
    return m, {0: rom}
