/* Source $80:C7DC-C8E2, bounded coordinate-target NPC control.
 * A direction change calls the animation setter at $80:AA3C; that edge is
 * refused here until the caller supplies a qualified animation adapter.
 * The containing frame must roll back on npc_supported == 0. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 rom8(u8 region,u32 offset);
u16 npc_x,npc_y,npc_z,npc_target_x,npc_target_y;
u16 npc_timer,npc_control,npc_flags,npc_direction,npc_action,npc_task;
u16 npc_velocity_x,npc_velocity_y,npc_velocity_z,npc_depth;
u8 npc_supported,npc_arrived;
u8 shadowrun_snes_npc_frame_status;
u16 npc_rom16(u32 at) {
 return (u16)((u16)rom8(0U,at)|((u16)rom8(0U,at+1UL)<<8));
}
void shadowrun_snes_npc_control(u8 unused) {
 u16 dx,dy,ax,ay,nx,ny,dir,axis,at;
 npc_supported=0U;npc_arrived=0U;
 npc_timer-=1U;
 if(npc_timer) {npc_supported=1U;return;}
 /* A zero X target selects actor-following, a distinct source edge. */
 if(!npc_target_x)return;
 dx=npc_target_x-npc_x;dy=npc_target_y-npc_y;
 nx=dx&32768U;ny=dy&32768U;
 if(nx)ax=0U-dx;else ax=dx;
 if(ny)ay=0U-dy;else ay=dy;
 if((u16)(ax+ay)<16U) {
  /* Nonnegative task IDs signal the source script task at $0C7E,Y. */
  if(!(npc_task&32768U))return;
  npc_velocity_x=0U;npc_velocity_y=0U;
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
 if(dir!=npc_direction)return;
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

/* $80:AAB3-ABBB projected to coordinate-target control and noncolliding
 * kinematics. Rendering flags/animation, script callbacks and task completion
 * are not modeled. A new direction or a colliding/gravity actor refuses. */
void shadowrun_snes_npc_frame(u8 pad) {
 shadowrun_snes_npc_frame_status=2U;
 if(pad || (npc_flags&96U) || npc_velocity_z)return;
 npc_supported=1U;
 if(npc_timer)shadowrun_snes_npc_control(0U);
 if(!npc_supported)return;
 npc_flags&=65527U;
 npc_x+=npc_velocity_x;npc_y+=npc_velocity_y;
 npc_depth=(u16)(npc_x+npc_y)>>1;
 shadowrun_snes_npc_frame_status=1U;
}
