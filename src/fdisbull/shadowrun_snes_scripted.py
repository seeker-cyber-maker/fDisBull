"""Prepared source-seeded task scheduler and bounded actors on logical passes.

The active task list is interpreted with guarded callbacks. Slots $44, $46 and
$4E have noncolliding motion and animation; slot $42 has action-0 setup and
animation after that action is selected. Other actor effects, presentation,
and room changes remain outside the projection.
"""
import hashlib

from .game_il import GameMachine, author_program
from .shadowrun_snes_field import ROM_SHA256, SAVE_SHA256
from .shadowrun_snes_npc import FIELDS, SOURCE as NPC_SOURCE
from .shadowrun_snes_script import SOURCE as SCRIPT_SOURCE, tasks_from_capture


_DECL = '''
u8 shadowrun_snes_view=3,shadowrun_snes_frame_status;
u16 shadowrun_snes_player_x,shadowrun_snes_player_y,shadowrun_snes_player_z;
u16 demo_actor_id[2],demo_x[2],demo_y[2],demo_z[2];
u16 scripted_passes,scripted_failure,scripted_callback_count;
u8 scripted_task_terminated;
u16 scripted_read(u16 at) {return (u16)((u16)task_shared[at]|((u16)task_shared[at+1U]<<8));}
void scripted_write(u16 at,u16 value) {task_shared[at]=(u8)value;task_shared[at+1U]=(u8)(value>>8);}
'''

_LOAD = 'void scripted_load(u16 slot) {' + ''.join(
    f'{name}=scripted_read({base}U+slot);' for name, base in FIELDS.items()) + '}'
_SAVE = 'void scripted_save(u16 slot) {' + ''.join(
    f'scripted_write({base}U+slot,{name});' for name, base in FIELDS.items()) + '}'

_FRAME = '''
/* The source task wait pass runs before the actor pass. */
void scripted_dispatch(u16 id) {
 u16 count,actor;
 scripted_task_terminated=0U;task_index=id;task_list_current=id;
 shadowrun_snes_task_check(0U);
 if(!task_supported) {scripted_failure=10U;return;}
 if(!task_ready)return;
 if(task_vm_resume[id>>1] && !task_vm_resume_known) {scripted_failure=17U;return;}
 for(count=0U;count<16U;count+=1U) {
  shadowrun_snes_task_vm(0U);
  if(task_vm_status==1U)return;
  if(task_vm_status==4U) {
   shadowrun_snes_task_terminate(0U);
   if(!task_supported) {scripted_failure=18U;return;}
   scripted_task_terminated=1U;return;
  }
  if(task_vm_status!=2U) {scripted_failure=11U;return;}
  scripted_callback_count+=1U;
  if(task_vm_callback==209U || task_vm_callback==208U) {
   actor=task_vm_arg0;
   if(actor!=66U && actor!=68U && actor!=70U && actor!=78U) {scripted_failure=12U;return;}
   scripted_load(actor);
   npc_requested_action=task_vm_arg1;shadowrun_snes_npc_action(0U);
   if(!npc_supported) {scripted_failure=13U;return;}
   if(task_vm_callback==209U) {
    npc_requested_direction=task_vm_arg2;shadowrun_snes_npc_direction(0U);
    if(!npc_supported) {scripted_failure=14U;return;}
   }
   scripted_save(actor);task_callback_success=1U;shadowrun_snes_task_callback_complete(0U);
  } else {
   shadowrun_snes_task_native(0U);
   if(!task_native_supported) {scripted_failure=15U;return;}
  }
 }
 scripted_failure=16U;
}
void scripted_actor(u16 slot) {
 scripted_load(slot);
 if(npc_flags&1024U)return;
 if((npc_flags&96U) || npc_velocity_z) {scripted_failure=20U;return;}
 npc_supported=1U;npc_completion_pending=0U;
 if(npc_timer)shadowrun_snes_npc_control(0U);
 if(!npc_supported) {scripted_failure=21U;return;}
 if(npc_completion_pending) {
  task_index=npc_completion_task;shadowrun_snes_task_signal(0U);
  if(!task_supported) {scripted_failure=22U;return;}
 }
 npc_flags&=65527U;npc_x+=npc_velocity_x;npc_y+=npc_velocity_y;
 npc_depth=(u16)(npc_x+npc_y)>>1;
 scripted_save(slot);
}
void scripted_animation(u16 slot) {
 scripted_load(slot);
 if(npc_flags&1024U)return;
 shadowrun_snes_npc_animate();
 if(!npc_supported) {scripted_failure=23U;return;}
 if(npc_animation_completion_pending) {
  task_index=npc_task;task_signal_mask=8U;shadowrun_snes_task_signal_mask(0U);
  if(!task_supported) {scripted_failure=24U;return;}
 }
 scripted_save(slot);
}
void shadowrun_snes_frame(u8 pad) {
 u16 current,visited;
 shadowrun_snes_frame_status=2U;scripted_failure=0U;
 if(pad) {scripted_failure=1U;return;}
 if(scripted_passes>=60U) {scripted_failure=2U;return;}
 current=task_list_head;
 for(visited=0U;visited<48U;visited+=1U) {
  if(current&32768U)break;
  if((current&1U) || current>=96U) {scripted_failure=19U;return;}
  scripted_dispatch(current);if(scripted_failure)return;
  if(scripted_task_terminated)current=task_list_current;
  else current=task_next[current>>1];
 }
 if(!(current&32768U)) {scripted_failure=19U;return;}
 /* These independent noncolliding actor updates commute within the slice;
  * the complete source actor ordering is not projected. */
 scripted_actor(70U);if(scripted_failure)return;
 scripted_actor(78U);if(scripted_failure)return;
 scripted_actor(68U);if(scripted_failure)return;
 scripted_animation(70U);if(scripted_failure)return;
 scripted_animation(78U);if(scripted_failure)return;
 scripted_animation(68U);if(scripted_failure)return;
 /* Slot $42's unset action has an unprojected animation before setup. */
 scripted_load(66U);
 if(npc_action==0U) {scripted_animation(66U);if(scripted_failure)return;}
 demo_x[0]=scripted_read(3652U+68U);demo_y[0]=scripted_read(3740U+68U);demo_z[0]=scripted_read(3828U+68U);
 demo_x[1]=scripted_read(3652U+70U);demo_y[1]=scripted_read(3740U+70U);demo_z[1]=scripted_read(3828U+70U);
 shadowrun_snes_player_x=demo_x[0];shadowrun_snes_player_y=demo_y[0];shadowrun_snes_player_z=demo_z[0];
 scripted_passes+=1U;shadowrun_snes_frame_status=1U;
}
'''


def machine_from_scripted_capture(rom, snapshot, save_ram):
    """Seed the qualified checkpoint once; permit 60 logical main-loop passes."""
    if len(rom) != 1048576 or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('wrong SNES source')
    if (len(snapshot) != 131072 or hashlib.sha256(snapshot).hexdigest() !=
            'e4cf82bc4d2d58d28cda9ae9d90d51cf4287e9e8bf0d3c860097a1a5ce2f0ca9'):
        raise ValueError('wrong source main-loop checkpoint')
    if len(save_ram) != 8192 or hashlib.sha256(save_ram).hexdigest() != SAVE_SHA256:
        raise ValueError('wrong captured save RAM')
    word = lambda a: int.from_bytes(snapshot[a:a+2], 'little')
    if (word(0x136c+0x44), word(0x136c+0x46)) != (0x12, 0x10):
        raise ValueError('unsupported actor task bindings')
    scripts = SCRIPT_SOURCE.read_text()
    npc = NPC_SOURCE.read_text().replace('typedef unsigned char u8;\ntypedef unsigned int u16;\ntypedef unsigned long u32;\nu8 rom8(u8 region,u32 offset);\n', '')
    text = scripts + '\n' + npc + '\n' + _DECL + '\n' + _LOAD + '\n' + _SAVE + '\n' + _FRAME
    program = author_program(text, [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}], evidence={
        'kind': 'bounded-source-seeded-two-npc-task-slice', 'source_sha256': ROM_SHA256,
        'snapshot_sha256': hashlib.sha256(snapshot).hexdigest(),
        'authoring_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'clock': 'one source main-loop pass',
        'scope': '60 logical passes; bounded active task scheduler, actor slots 44/46/4E and slot 42 action-0 animation; other actor effects and rendering excluded'})
    m = GameMachine(program, {0: rom})
    m.set_state(tasks_from_capture(rom, snapshot).snapshot())
    xs=[word(0x0e44+s) for s in (0x44,0x46)]
    ys=[word(0x0e9c+s) for s in (0x44,0x46)]
    zs=[word(0x0ef4+s) for s in (0x44,0x46)]
    m.set_state({'demo_actor_id':[0x44,0x46], 'demo_x':xs,'demo_y':ys,'demo_z':zs,
                 'shadowrun_snes_player_x':xs[0], 'shadowrun_snes_player_y':ys[0],
                 'shadowrun_snes_player_z':zs[0]})
    return m,{0:rom}
