"""Source-derived bounded Shadowrun SNES new-game actor construction."""
import hashlib
from pathlib import Path

from .game_il import GameMachine, author_program
from .shadowrun_snes_field import ROM_SHA256

SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_snes_scene_init.c'
COLLISION_SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_snes_scene_collision.c'


def scene_from_title_capture(rom, title_wram):
    """Seed source room construction from caller-provided title-phase WRAM.

    The caller must resolve each yielded script ID using the real task
    allocator. This is not a completed scene, task run, graphics, or collision
    projection. The caller establishes title-state identity and ordering.
    """
    if len(rom) != 1048576 or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('wrong SNES source')
    if len(title_wram) != 131072:
        raise ValueError('128 KiB title-phase WRAM required')
    raw = SOURCE.read_bytes()
    program = author_program(raw.decode(), [{'id': 0, 'length':len(rom), 'sha256':ROM_SHA256}], evidence={
        'kind':'new-game-source-scene-actor-construction', 'source_sha256':ROM_SHA256,
        'title_wram_sha256':hashlib.sha256(title_wram).hexdigest(),
        'authoring_sha256':hashlib.sha256(raw).hexdigest(),
        'source_range':'80:9590,81:A772,80:A44C/A287/A343/A7C2',
        'scope':'scene 3 actor records and task-allocator handoff; no scene presentation, collision or script execution'})
    machine = GameMachine(program,{0:rom})
    machine.set_state({'task_shared':list(title_wram[:65536]),
                       'scene_7f':list(title_wram[65536:])})
    if SOURCE.read_bytes()!=raw:raise ValueError('scene source changed')
    return machine


SCENE_TASK_WRAPPER = '''
u8 scene_construct_status;
void shadowrun_snes_scene_construct(u8 unused) {
 u16 i;
 scene_construct_status=2U;
 shadowrun_snes_scene_begin(0U);if(scene_status!=1U)return;
 shadowrun_snes_scene_room_data(0U);if(scene_status!=1U)return;
 shadowrun_snes_task_reset(0U);if(!task_init_supported)return;
 for(i=0U;i<22U;i+=1U) {
  shadowrun_snes_scene_next(0U);
  if(scene_status==2U) {
   shadowrun_snes_scene_camera(0U);if(scene_status!=1U)return;
   shadowrun_snes_scene_collision_init(0U);if(!scene_static_supported)return;
   scene_construct_status=1U;return;
  }
  if(scene_status==3U) {
   /* Every scene-3 actor script declares exactly one word argument. */
   if(rom8(0U,92176UL+(u32)scene_task_id)!=2U)return;
   task_init_script=scene_task_id;
   task_init_args[0]=(u8)scene_actor;task_init_args[1]=(u8)(scene_actor>>8);
   shadowrun_snes_task_create(0U);if(!task_init_supported)return;
   scene_task_result=task_init_result;shadowrun_snes_scene_task_complete(0U);
  }
  if(scene_status!=1U)return;
 }
}
'''


def constructed_from_title_capture(rom, title_wram):
    """Compose ROM world expansion, actor creation, and source task allocation.

    The caller chooses and qualifies the title-phase state. This captures a
    source initialization slice only; scene tables, rendering and later task
    execution remain outside the projection.
    """
    from .shadowrun_snes_script import SOURCE as SCRIPT_SOURCE, tasks_from_capture
    task_init = Path(__file__).parent / 'game_sources' / 'shadowrun_snes_task_init.c'
    scene = SOURCE.read_text().replace(
        'typedef unsigned char u8;\ntypedef unsigned int u16;\n'
        'typedef unsigned long u32;\nu8 rom8(u8 region,u32 offset);\n'
        'u8 task_shared[65536];\n', '')
    text = (SCRIPT_SOURCE.read_text() + '\n' + task_init.read_text() + '\n' + scene + '\n' +
            COLLISION_SOURCE.read_text() + '\n' + SCENE_TASK_WRAPPER)
    # tasks_from_capture checks the pinned ROM and initializes task arrays and
    # heap from the caller's state; source C176 then resets its own fields.
    seed = tasks_from_capture(rom,title_wram)
    program = author_program(text,[{'id':0,'length':len(rom),'sha256':ROM_SHA256}], evidence={
        'kind':'source-new-game-world-actor-task-construction','source_sha256':ROM_SHA256,
        'title_wram_sha256':hashlib.sha256(title_wram).hexdigest(),
        'authoring_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'scope':'ROM-derived scene 3 world, actors, root tasks and static collision; no task execution, dynamic collision or rendering'})
    machine=GameMachine(program,{0:rom})
    machine.set_state(seed.snapshot())
    machine.set_state({'scene_7f':list(title_wram[65536:])})
    return machine


SCENE_PARTY_WRAPPER = '''
u8 scene_party_status;
void shadowrun_snes_party_construct(u8 unused) {
 scene_party_status=2U;
 shadowrun_snes_party_begin(0U);if(!scene_status)return;
 if(scene_status==3U) {
  if(rom8(0U,92176UL+(u32)scene_task_id)!=2U)return;
  task_init_script=scene_task_id;
  task_init_args[0]=(u8)scene_actor;task_init_args[1]=(u8)(scene_actor>>8);
  shadowrun_snes_task_create(0U);if(!task_init_supported)return;
  scene_task_result=task_init_result;shadowrun_snes_actor_task_complete(0U);
  if(!scene_status)return;
 }
 shadowrun_snes_party_direction(0U);if(!scene_status)return;
 shadowrun_snes_party_finish(0U);if(!scene_status)return;
 scene_party_status=1U;
}
'''


def party_from_source_capture(rom, source_wram):
    """Source-fed diagnostic at $A173; never a substitute for a live producer."""
    from .shadowrun_snes_script import SOURCE as SCRIPT_SOURCE, tasks_from_capture
    task_init=Path(__file__).parent/'game_sources'/'shadowrun_snes_task_init.c'
    scene=SOURCE.read_text().replace(
        'typedef unsigned char u8;\ntypedef unsigned int u16;\n'
        'typedef unsigned long u32;\nu8 rom8(u8 region,u32 offset);\n'
        'u8 task_shared[65536];\n','')
    text=SCRIPT_SOURCE.read_text()+'\n'+task_init.read_text()+'\n'+scene+'\n'+SCENE_PARTY_WRAPPER
    seed=tasks_from_capture(rom,source_wram)
    program=author_program(text,[{'id':0,'length':len(rom),'sha256':ROM_SHA256}], evidence={
        'kind':'source-fed-first-party-insertion','source_sha256':ROM_SHA256,
        'snapshot_sha256':hashlib.sha256(source_wram).hexdigest(),
        'authoring_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'scope':'one source-fed $A173 party insertion; no preceding title or script execution'})
    m=GameMachine(program,{0:rom});m.set_state(seed.snapshot())
    w=lambda x:int.from_bytes(source_wram[x:x+2],'little')
    m.set_state({'scene_7f':list(source_wram[65536:]),
                 'task_heap_first_header':list(source_wram[0x3ee:0x3f2]),
                 'scene_party_kind':w(0),'scene_party_x':w(2),'scene_party_y':w(4),
                 'scene_party_z':w(6),'scene_party_direction':w(8),
                 'scene_party_entity':w(10),'scene_party_extra':w(12)})
    return m
