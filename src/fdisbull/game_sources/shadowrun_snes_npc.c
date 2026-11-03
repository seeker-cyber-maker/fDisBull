/* Source $80:C7DC-C8E2, bounded coordinate-target NPC control.
 * The containing frame must roll back on npc_supported == 0. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 rom8(u8 region,u32 offset);
u16 npc_x,npc_y,npc_z,npc_target_x,npc_target_y;
u16 npc_timer,npc_control,npc_flags,npc_direction,npc_action,npc_task;
u16 npc_velocity_x,npc_velocity_y,npc_velocity_z,npc_depth;
u16 npc_anim_table,npc_anim_reload,npc_anim_selector,npc_anim_phase;
u16 npc_anim_increment,npc_anim_timer,npc_anim_pending;
u16 npc_anim_kind,npc_anim_mode,npc_anim_dx,npc_anim_dy,npc_anim_dz,npc_anim_dh,npc_anim_extra;
u16 npc_requested_direction,npc_requested_action;
u8 npc_animation_completion_pending;
u16 npc_completion_task;
u8 npc_completion_pending;
u8 npc_supported,npc_arrived;
u8 shadowrun_snes_npc_frame_status;
u16 npc_rom16(u32 at) {
 return (u16)((u16)rom8(0U,at)|((u16)rom8(0U,at+1UL)<<8));
}
u16 npc_signed_byte(u32 at) {
 u16 v;v=(u16)rom8(0U,at);if(v&128U)v|=65280U;return v;
}
/* $A912: observed kind-3/36 action 0 and kind-24 action 2/6 records. */
void shadowrun_snes_npc_action(u8 unused) {
 u16 record;
 npc_supported=0U;
 if(npc_direction>7U)return;
 if(npc_anim_kind==3U && npc_requested_action==0U)record=0x81e0U;
 else if(npc_anim_kind==36U && npc_requested_action==0U)record=0x9b1eU;
 else if(npc_anim_kind==24U && npc_requested_action==6U)record=0x9472U;
 else if(npc_anim_kind==24U && npc_requested_action==2U)record=0x941aU;
 else return;
 if(npc_action==npc_requested_action) {npc_supported=1U;return;}
 npc_action=npc_requested_action;npc_anim_table=record+8U;
 npc_anim_selector=(u16)rom8(0U,360448UL+(u32)npc_anim_table+(u32)npc_direction);
 npc_anim_increment=(u16)rom8(0U,360448UL+(u32)record);
 npc_anim_reload=(u16)rom8(0U,360449UL+(u32)record)^128U;
 npc_anim_timer=1U;npc_anim_mode=(u16)rom8(0U,360450UL+(u32)record);
 npc_anim_dx=npc_signed_byte(360451UL+(u32)record);npc_anim_dy=npc_signed_byte(360452UL+(u32)record);
 npc_anim_dz=npc_signed_byte(360453UL+(u32)record);npc_anim_dh=npc_signed_byte(360454UL+(u32)record);
 npc_anim_extra=(u16)rom8(0U,360455UL+(u32)record);
 npc_anim_phase=128U;npc_anim_pending=65535U;npc_supported=1U;
}
/* $AA3C/$AA6C in the observed looping action-1 regime. A912 fallback
 * and directions outside the source's eight-entry table are unsupported. */
void shadowrun_snes_npc_direction(u8 unused) {
 u16 dir;
 npc_supported=0U;dir=npc_requested_direction;
 if(dir>7U || npc_direction>7U)return;
 if(dir!=npc_direction) {
  if(npc_action==0U && (npc_anim_reload==0U || npc_anim_reload>=128U)) {
   npc_direction=dir;npc_action=65535U;npc_requested_action=0U;
   shadowrun_snes_npc_action(0U);return;
  }
  if(npc_action!=1U || npc_anim_reload!=4U || npc_anim_increment!=14U ||
     npc_anim_table!=0x8208U)return;
  npc_anim_selector=(npc_anim_selector&65280U)|
   ((npc_anim_selector-(u16)rom8(0U,360448UL+(u32)npc_anim_table+(u32)npc_direction)+
     (u16)rom8(0U,360448UL+(u32)npc_anim_table+(u32)dir))&255U);
  npc_direction=dir;npc_anim_phase=128U;npc_anim_pending=65535U;
 }
 npc_supported=1U;
}
void shadowrun_snes_npc_control(u8 unused) {
 u16 dx,dy,ax,ay,nx,ny,dir,axis,at;
 npc_supported=0U;npc_arrived=0U;npc_completion_pending=0U;
 npc_timer-=1U;
 if(npc_timer) {npc_supported=1U;return;}
 /* A zero X target selects actor-following, a distinct source edge. */
 if(!npc_target_x)return;
 dx=npc_target_x-npc_x;dy=npc_target_y-npc_y;
 nx=dx&32768U;ny=dy&32768U;
 if(nx)ax=0U-dx;else ax=dx;
 if(ny)ay=0U-dy;else ay=dy;
 if((u16)(ax+ay)<16U) {
  npc_velocity_x=0U;npc_velocity_y=0U;
  /* The caller resolves $0BBE/$038E links and sets $0C7E|4. */
  if(!(npc_task&32768U)) {npc_completion_task=npc_task;npc_completion_pending=1U;}
  npc_arrived=1U;npc_supported=1U;return;
 }
 axis=npc_control&2U;
 if(npc_flags&8U) {
  npc_timer=30U;axis^=2U;
 } else {
  npc_timer=2U;
  if((!axis && ax<12U) || (axis && ay<12U)) {
   npc_control^=2U;axis=npc_control&2U;
  }
 }
 if(axis) {if(ny)dir=4U;else dir=0U;}
 else {if(nx)dir=6U;else dir=2U;}
 npc_requested_direction=dir;shadowrun_snes_npc_direction(0U);
 if(!npc_supported)return;
 at=dir<<1;
 if(npc_action==2U) {
  npc_velocity_x=npc_rom16(0x47bcUL+(u32)at);
  npc_velocity_y=npc_rom16(0x47ccUL+(u32)at);
 } else {
  npc_velocity_x=npc_rom16(0x479cUL+(u32)at);
  npc_velocity_y=npc_rom16(0x47acUL+(u32)at);
 }
 npc_supported=1U;
}

/* $ABCD-AC58 animation timing/selector projection. Presentation allocation,
 * sprite records and one-shot completion are excluded and guarded. */
void shadowrun_snes_npc_animate(void) {
 u16 phase,index;
 npc_supported=0U;npc_animation_completion_pending=0U;
 if(npc_anim_kind==36U && npc_action==0U && npc_anim_table==0x9b26U &&
    !npc_anim_increment && (npc_anim_reload==0U || npc_anim_reload==129U) &&
    npc_anim_timer==1U && npc_anim_phase<=128U && npc_direction<=7U &&
    (!npc_anim_pending || npc_anim_pending==65535U)) {
  npc_anim_pending=0U;
  if(npc_anim_phase==128U) {
   npc_anim_phase=0U;npc_anim_reload=0U;
   npc_anim_selector=(u16)rom8(0U,360448UL+(u32)npc_anim_table+(u32)npc_direction)+2U;
  }
  npc_supported=1U;return;
 }
 if(npc_anim_kind==24U && npc_action==0U && npc_anim_table==0x93feU &&
    !npc_anim_increment && !npc_anim_phase && !npc_anim_reload &&
    !npc_anim_pending && npc_anim_timer==1U) {npc_supported=1U;return;}
 if(npc_anim_kind==24U && npc_action==2U && npc_anim_table==0x9422U &&
    !npc_anim_increment && (npc_anim_reload==0U || npc_anim_reload==129U) &&
    npc_anim_timer==1U && npc_anim_phase<=128U && npc_direction<=7U &&
    (!npc_anim_pending || npc_anim_pending==65535U)) {
  npc_anim_pending=0U;
  if(npc_anim_phase==128U) {
   npc_anim_phase=0U;npc_anim_reload=0U;
   npc_anim_selector=(u16)rom8(0U,360448UL+(u32)npc_anim_table+(u32)npc_direction)+2U;
  }
  npc_supported=1U;return;
 }
 if(npc_anim_kind==24U && npc_action==6U && npc_anim_table==0x947aU &&
    npc_anim_increment==24U && (npc_anim_reload==0U || npc_anim_reload==133U) &&
    npc_anim_timer>=1U && npc_anim_timer<=5U && npc_anim_phase<=128U &&
    npc_direction<=7U && (!npc_anim_pending || npc_anim_pending==65535U)) {
  npc_anim_pending=0U;phase=npc_anim_phase+24U;npc_anim_phase=phase&127U;
  if(phase>=128U) {
   npc_anim_timer-=1U;
   if(!npc_anim_timer) {
    if(npc_anim_reload==133U) {
     npc_anim_reload=0U;npc_anim_timer=5U;
     index=(u16)rom8(0U,360448UL+(u32)npc_anim_table+(u32)npc_direction);
    } else {
     npc_anim_increment=0U;npc_action|=32768U;
     if(!(npc_task&32768U))npc_animation_completion_pending=1U;
     npc_supported=1U;return;
    }
   } else index=npc_anim_selector;
   npc_anim_selector=index+2U;
  }
  npc_supported=1U;return;
 }
 if(npc_action==0U && npc_anim_table==0x81e8U && npc_anim_increment==0U &&
    (npc_anim_reload==0U || npc_anim_reload==129U) && npc_anim_timer==1U &&
    npc_direction<=7U && npc_anim_phase<=128U &&
    (!npc_anim_pending || npc_anim_pending==65535U)) {
  npc_anim_pending=0U;
  if(npc_anim_phase==128U) {
   npc_anim_phase=0U;npc_anim_reload=0U;
   npc_anim_selector=(u16)rom8(0U,0x601e8UL+(u32)npc_direction)+2U;
  }
  npc_supported=1U;return;
 }
 if(npc_action!=1U || npc_anim_table!=0x8208U || npc_anim_reload!=4U ||
    npc_anim_increment!=14U || npc_direction>7U || !npc_anim_timer ||
    npc_anim_timer>npc_anim_reload || npc_anim_increment>=128U || npc_anim_phase>128U)return;
 if(npc_anim_pending && npc_anim_pending!=65535U)return;
 npc_anim_pending=0U;
 phase=npc_anim_phase+npc_anim_increment;
 npc_anim_phase=phase&127U;
 if(phase>=128U) {
  npc_anim_timer-=1U;
  if(!npc_anim_timer) {
   npc_anim_timer=npc_anim_reload;
   index=(u16)rom8(0U,360448UL+(u32)npc_anim_table+(u32)npc_direction);
  } else index=npc_anim_selector;
  npc_anim_selector=index+2U;
 }
 npc_supported=1U;
}

/* $80:AAB3-ABBB projected to noncolliding kinematics; source dispatch and
 * presentation are excluded. A pending completion requires the composed caller. */
void shadowrun_snes_npc_frame(u8 pad) {
 shadowrun_snes_npc_frame_status=2U;
 if(pad || (npc_flags&96U) || npc_velocity_z)return;
 npc_supported=1U;npc_completion_pending=0U;
 if(npc_timer)shadowrun_snes_npc_control(0U);
 if(!npc_supported)return;
 if(npc_completion_pending)return;
 npc_flags&=65527U;
 npc_x+=npc_velocity_x;npc_y+=npc_velocity_y;
 npc_depth=(u16)(npc_x+npc_y)>>1;
 shadowrun_snes_npc_animate();if(!npc_supported)return;
 shadowrun_snes_npc_frame_status=1U;
}
