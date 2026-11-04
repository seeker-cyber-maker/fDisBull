/* Source $80:BC06-BC4F and $80:BE3D-BF0A. Shared WRAM belongs to caller.
 * Requests: 0 none, 1 run $BC8E hit scan, 2 close selected-target window.
 * The caller owns those operations and the enclosing frame transaction. */
u8 target_status,target_request,target_pending,target_globals_known,target_geometry_known[44];
u8 target_carry;
u16 target_candidate,target_kind,target_name_pointer,target_dx,target_dy;
u8 target_dispatch_status,target_dispatch_request;
u16 target_dispatch_actor,target_dispatch_task,target_dispatch_wait,target_dispatch_pressed;
u16 target_facing_direction;
u8 target_facing_status;
u16 scene_read(u16 at);
void scene_write(u16 at,u16 value);
u8 rom8(u8 region,u32 offset);

u16 target_sbc(u16 left,u16 right) {
 u32 sub;
 sub=(u32)right;if(!target_carry)sub+=1UL;
 target_carry=(u8)((u32)left>=sub);
 return (u16)((u32)left-sub);
}

void shadowrun_snes_target_begin(u8 unused) {
 u16 actor,x,y;
 target_status=0U;target_request=0U;actor=scene_read(0x0cdeU);
 if(!target_globals_known || (actor&1U) || actor>=88U)return;
 target_carry=1U;y=target_sbc(0x0c00U,scene_read(0x0f4cU+actor));
 y=target_sbc(y,scene_read(0x0ef4U+actor));y=target_sbc(y,scene_read(0x0ce2U));
 y=target_sbc(y,0x0048U);
 x=(u16)(0x0600U+scene_read(0x0e9cU+actor));target_carry=1U;
 x=target_sbc(x,scene_read(0x0e44U+actor));x=target_sbc(x,scene_read(0x0ce0U));
 x=target_sbc(x,0x0010U);
 y>>=2;x>>=2;
 scene_write(0x01f2U,(u16)((y<<8)|(y>>8)));
 scene_write(0x01f0U,(u16)((x<<8)|(x>>8)));
 scene_write(0x0200U,0x0600U);scene_write(0x0202U,0x0c00U);
 scene_write(0x0204U,65535U);scene_write(0x01f4U,65535U);target_status=1U;
}

/* $BC82 after caller has completed the conditional $BE2B name close.
 * Cursor velocity and controller latches are not cleared by this routine. */
void shadowrun_snes_target_end(u8 unused) {
 target_status=0U;target_request=0U;
 if(!(scene_read(0x01f6U)&32768U))return;
 scene_write(0x01f4U,0U);target_status=1U;
}

u16 target_velocity(u16 value,u8 positive,u8 negative) {
 if(positive) {
  if(value&32768U)value=0U;
  value+=48U;if(value>=768U)value=768U;
 } else if(negative) {
  if(!(value&32768U))value=0U;
  value-=48U;if(value<64768U)value=64768U;
 } else value=0U;
 return value;
}

void shadowrun_snes_target_cursor(u8 unused) {
 u16 held,v,x,y;
 target_status=0U;target_request=0U;
 if(!scene_read(0x01f4U)) {target_status=1U;return;}
 held=(scene_read(0x01e6U)>>8)&15U;
 v=target_velocity(scene_read(0x01ecU),(held&1U)!=0U,(held&2U)!=0U);
 scene_write(0x01ecU,v);
 v=target_velocity(scene_read(0x01eeU),(held&4U)!=0U,(held&8U)!=0U);
 scene_write(0x01eeU,v);
 x=(u16)(scene_read(0x01f0U)+scene_read(0x01ecU));
 if(x<0x0300U)x=0x0300U;if(x>=0xef01U)x=0xef00U;
 y=(u16)(scene_read(0x01f2U)+scene_read(0x01eeU));
 if(y<0x0300U)y=0x0300U;if(y>=0xce01U)y=0xce00U;
 scene_write(0x01f0U,x);scene_write(0x01f2U,y);
 if(!held)target_request=1U;
 else if(!(scene_read(0x01f6U)&32768U))target_request=2U;
 target_status=1U;if(target_request)target_status=2U;
}

/* $DF35-$DFDD computes facing from cursor and projected player coordinates.
 * Caller supplies this result to the source $AA3C direction setter. */
void shadowrun_snes_target_facing(u8 unused) {
 u16 actor,x,y,ax,ay,sx,sy,cursorx,cursory;
 target_facing_status=0U;actor=scene_read(0x0cdeU);
 if(!target_globals_known || (actor&1U) || actor>=88U || !target_geometry_known[actor>>1])return;
 cursorx=scene_read(0x01f0U)>>2;cursory=scene_read(0x01f2U)>>2;
 y=(u16)(0x0becU-scene_read(0x0f4cU+actor));
 y=(u16)(y-scene_read(0x0ef4U+actor));y=(u16)(y-scene_read(0x0ce2U));
 /* Source executes CLC immediately before SBC #$0040. */
 y=(u16)((u16)(y-0x0041U)<<4);y=(u16)(y-cursory);
 x=(u16)(0x05ecU+scene_read(0x0e9cU+actor));
 x=(u16)(x-scene_read(0x0e44U+actor));x=(u16)(x-scene_read(0x0ce0U));
 x=(u16)((u16)(x<<4)-cursorx);
 sx=x&32768U;sy=y&32768U;ax=x;ay=y;
 if(sx)ax=(u16)(0U-x);if(sy)ay=(u16)(0U-y);
 if((ay>>1)>=ax) {
  target_facing_direction=1U;if(sy)target_facing_direction=5U;
 } else if((ax>>1)>=ay) {
  target_facing_direction=3U;if(sx)target_facing_direction=7U;
 } else if(sx) {
  target_facing_direction=0U;if(sy)target_facing_direction=6U;
 } else {
  target_facing_direction=2U;if(sy)target_facing_direction=4U;
 }
 target_facing_status=1U;
}

u16 target_rom16(u32 offset) {
 return (u16)((u16)rom8(0U,offset)|((u16)rom8(0U,offset+1UL)<<8));
}
void shadowrun_snes_target_resume(u8 unused) {
 target_status=0U;
 if(target_request==2U) {target_request=0U;target_status=1U;return;}
 if(target_request==3U && target_pending) {
  scene_write(0x01fcU,target_dx);scene_write(0x01feU,target_dy);
  scene_write(0x01f6U,target_kind);scene_write(0x01faU,target_candidate);
  target_request=4U;target_status=2U;return;
 }
 if(target_request==4U && target_pending) {
  target_pending=0U;target_request=0U;target_status=1U;return;
 }
}

/* $BC8E: reverse painter order, rectangle tests, and retained target offsets.
 * A new name window is caller-owned; target_name_pointer is source DP $02.
 * Party-specific names use another table and deliberately refuse for now. */
void shadowrun_snes_target_scan(u8 unused) {
 u16 count,slot,kind,visible,screenx,screeny,centerx,centery,v,t,i;
 u32 name_at;
 target_status=0U;target_request=0U;target_pending=0U;
 if(!target_globals_known)return;
 count=scene_read(0x14ccU);
 if(count&32768U) {target_status=1U;return;}
 if((count&1U) || count>=88U)return;
 screenx=(scene_read(0x01f0U)>>8)&255U;screeny=(scene_read(0x01f2U)>>8)&255U;
 for(i=count+2U;i>0U;) {
  i-=2U;count=i;
  slot=scene_read(0x14ceU+count);if((slot&1U) || slot>=88U)return;
  if(!target_geometry_known[slot>>1])return;
  visible=scene_read(0x10acU+slot);kind=scene_read(0x3f04U+slot);
  if(!visible)continue;
  if(kind==11U && scene_read(0x01f4U)!=65533U &&
     !(scene_read(0x1d7bU)|scene_read(0x1d89U)))continue;
  if(kind>=256U)return;
  name_at=0x66fb0UL+(u32)kind*6UL;
  if(target_rom16(name_at)==65535U)continue;
  v=(u16)(scene_read(0x0202U)-scene_read(0x0f4cU+slot)-scene_read(0x0ef4U+slot)-scene_read(0x0ce2U));
  if(v&32768U)continue;
  centery=v>>2;
  v=(u16)((centery<<1)-scene_read(0x421cU+slot)-scene_read(0x42ccU+slot));
  if((v&32768U) || (v>>1)<screeny)continue;
  v=(u16)(((u16)(centery-scene_read(0x437cU+slot))<<1)-scene_read(0x4274U+slot)-scene_read(0x4324U+slot));
  if(!(v&32768U) && (v>>1)>=screeny)continue;
  v=(u16)(scene_read(0x0200U)+scene_read(0x0e9cU+slot)-scene_read(0x0e44U+slot)-scene_read(0x0ce0U));
  if(v&32768U)v=(u16)((v>>2)|0xc000U);
  centerx=v>>2;
  v=(u16)(centerx-scene_read(0x421cU+slot)+scene_read(0x4324U+slot));
  if((v&32768U) || v<screenx)continue;
  v=(u16)(centerx+scene_read(0x42ccU+slot)-scene_read(0x4274U+slot));
  if(!(v&32768U) && v>=screenx)continue;
  if(scene_read(0x01f6U)==kind && scene_read(0x01faU)==slot) {
   v=(u16)(centerx-scene_read(0x01fcU));t=(u16)(centery-scene_read(0x01feU));
   if(v>=255U || t>=255U) {target_request=2U;target_status=2U;return;}
   scene_write(0x01f0U,(u16)(v<<8));scene_write(0x01f2U,(u16)(t<<8));target_status=1U;return;
  }
  if((scene_read(0x1474U+slot)&3U)==3U)return;
  target_candidate=slot;target_kind=kind;target_name_pointer=target_rom16(name_at);
  target_dx=(u16)(centerx-screenx);target_dy=(u16)(centery-screeny);target_pending=1U;
  if(!(scene_read(0x01f6U)&32768U)) {target_request=3U;target_status=2U;return;}
  target_request=3U;shadowrun_snes_target_resume(0U);return;
 }
 if(!(scene_read(0x01f6U)&32768U)) {target_request=2U;target_status=2U;return;}
 target_status=1U;
}

/* $BF0B-$BFD9 source action gate. task_wait/link are the scheduler's
 * authoritative byte-indexed task arrays. Request 1 is the $996E action menu;
 * request 2 is the FE8B out-of-range warning, followed by $BC82/$9D9D.
 * The caller owns those blocking effects and transactional continuation. */
void shadowrun_snes_target_dispatch(u8 unused) {
 u16 actor,player,task,wait,edge,override,dx,dy,dz,i;
 target_dispatch_status=0U;target_dispatch_request=0U;
 if(!target_globals_known)return;
 if(scene_read(0x1d79U)|scene_read(0x1d7bU)) {target_dispatch_status=1U;return;}
 if(scene_read(0x01f6U)&32768U) {target_dispatch_status=1U;return;}
 edge=scene_read(0x01eaU)&0x8030U;
 if(!edge) {target_dispatch_status=1U;return;}
 actor=scene_read(0x01faU);player=scene_read(0x0cdeU);
 if((actor&1U) || actor>=88U || (player&1U) || player>=88U ||
    !target_geometry_known[actor>>1] || !target_geometry_known[player>>1])return;
 task=scene_read(0x136cU+actor);
 if(task&32768U) {target_dispatch_status=1U;return;}
 for(i=0U;i<48U;i+=1U) {
  if((task&1U) || task>=96U)return;
  wait=task_wait[task>>1];if(!(wait&32768U))break;
  task=task_link[task>>1];
 }
 if(i==48U)return;
 override=0U;
 if(edge==0x8000U && (wait&0x6002U))override=wait&0x6682U;
 scene_write(0x1fc2U,override);
 dx=(u16)(scene_read(0x0e44U+player)-scene_read(0x0e44U+actor));
 dy=(u16)(scene_read(0x0e9cU+player)-scene_read(0x0e9cU+actor));
 dz=(u16)(scene_read(0x0ef4U+player)-scene_read(0x0ef4U+actor));
 if(dx&32768U)dx=(u16)(0U-dx);
 if(dy&32768U)dy=(u16)(0U-dy);
 if(dz&32768U)dz=(u16)(0U-dz);
 if(((u16)(dx+dy)>=0x00a1U || dz>=0x0081U) && !override) {
  target_dispatch_request=2U;target_dispatch_status=2U;return;
 }
 if(!(wait&0x67f2U)) {target_dispatch_status=1U;return;}
 target_dispatch_actor=actor;target_dispatch_task=task;target_dispatch_wait=wait&0x67f2U;
 target_dispatch_pressed=edge;
 if(edge&0x8000U) {target_dispatch_request=1U;target_dispatch_status=2U;return;}
 /* $BFEB/$C010 direct combat/action branches are not yet qualified. */
}
