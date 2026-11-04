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

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_snes_opening.c'
TITLE_SHA256 = '15caaf78faed99408c783119ac5e1703da066b904e5570dd895b7bcb49db9d93'


def machine_from_title(rom, title, save_ram):
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
    prefix = ('typedef unsigned char u8;\ntypedef unsigned int u16;\n'
              'typedef unsigned long u32;\nu8 rom8(u8 region,u32 offset);\n')
    inputs = {p: p.read_text() for p in (VM_SOURCE, TASK_SOURCE, SCENE_SOURCE, COLLISION_SOURCE,
              NPC_SOURCE, MENU_SOURCE, MOTION_SOURCE, LIVE_SOURCE, FIELD_SOURCE, TEXT_SOURCE, WINDOW_SOURCE, ANIM_SOURCE, SOURCE)}
    scene = inputs[SCENE_SOURCE].replace(prefix + 'u8 task_shared[65536];\n', '')
    npc = inputs[NPC_SOURCE].replace(prefix, '')
    menu = inputs[MENU_SOURCE].replace('typedef unsigned char u8;\ntypedef unsigned int u16;\n', '')
    text_source = inputs[TEXT_SOURCE].replace(prefix, '')
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
                       SCENE_TASK_WRAPPER, SCENE_PARTY_WRAPPER, source_fragment(), text_source,
                       inputs[WINDOW_SOURCE], inputs[ANIM_SOURCE], inputs[SOURCE], load, save))
    program = author_program(text, [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}], evidence={
        'kind': 'source-title-scene-task-opening', 'source_sha256': ROM_SHA256,
        'title_sha256': TITLE_SHA256, 'authoring_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'clock': 'menu input updates followed by logical source main-loop passes',
        'scope': 'source-derived scene 3 initialization and guarded task/actor execution; presentation, audio delivery and unsupported transitions excluded'})
    m = GameMachine(program, {0: rom})
    m.set_state(tasks_from_capture(rom, title).snapshot())
    word = lambda at: int.from_bytes(title[at:at + 2], 'little')
    m.set_state({'scene_7f': list(title[65536:]), 'menu_selection': word(0xe),
                 'menu_disabled': [word(0x11c0 + i * 2) for i in range(3)],
                 'opening_rotation': int.from_bytes(save_ram[0x1ffd:0x1fff], 'little')})
    if any(p.read_text() != s for p, s in inputs.items()):
        raise ValueError('opening sources changed')
    return m, {0: rom}
