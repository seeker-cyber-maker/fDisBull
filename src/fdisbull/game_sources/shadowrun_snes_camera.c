/* Behavioral camera projection of $81:8C2E-$8CB8 and $8A91-$8AE0.
 * Called after actor/animation updates, in source main-loop order. Tile-stream
 * writes from the rest of $8A91 are presentation effects, not modeled here. */
u8 camera_status,camera_visual_tainted;
u16 scene_read(u16 at);
void scene_write(u16 at,u16 value);
u8 rom8(u8 region,u32 offset);

u16 camera_rom16(u32 at) {
 return (u16)((u16)rom8(0U,at)|((u16)rom8(0U,at+1UL)<<8));
}
u16 camera_velocity(u16 delta) {
 delta&=65528U;
 if(!delta)return 0U;
 if(delta&32768U) {
  delta=(delta>>2)|49152U;
  if(delta<65504U)delta=65504U;
 } else {
  delta>>=2;if(delta>=33U)delta=32U;
 }
 return delta&65532U;
}
u16 camera_apply(u16 current,u16 velocity,u16 limit) {
 u16 result;
 result=current+velocity;
 if(result&32768U)return 0U;
 if(result>=limit)return limit;
 return result;
}
void shadowrun_snes_live_camera(u8 unused) {
 u16 actor,x,y,a,b,u,v,changed,lo,hi,cx,cy,vx,vy,pointer,bank,rawx,rawy;
 u32 bounds;
 camera_status=0U;actor=scene_read(0x0cdeU);
 if(actor&32768U) {camera_status=1U;return;}
 if((actor&1U) || actor>=88U)return;
 y=(u16)(0x0910U-scene_read(0x0f4cU+actor));
 x=(u16)(0x0400U+scene_read(0x0e9cU+actor)-scene_read(0x0e44U+actor));
 /* $8A05's long room-bounds pointer; qualify the observed LoROM table. */
 pointer=scene_read(0x0cf6U);bank=scene_read(0x0cf8U)&255U;
 if(pointer<32768U || pointer>65524U || (bank!=153U && bank!=154U))return;
 bounds=((u32)(bank&127U)<<15)+(u32)(pointer&32767U)+1UL;
 if(bounds+9UL>=1048576UL)return;
 a=(u16)(x-1024U);b=(u16)((u16)(2368U-y)<<1);
 u=(u16)(b-a)>>3;v=(u16)(b+a)>>3;changed=0U;
 if(camera_rom16(bounds)!=65535U) {
  if(camera_rom16(bounds+8UL)!=65535U)return;
  lo=camera_rom16(bounds);hi=camera_rom16(bounds+2UL);
  if(u<lo) {u=lo;changed=1U;}if(u>=hi) {u=hi;changed=1U;}
  lo=camera_rom16(bounds+4UL);hi=camera_rom16(bounds+6UL);
  if(v<lo) {v=lo;changed=1U;}if(v>=hi) {v=hi;changed=1U;}
 }
 if(changed) {x=(u16)(((u16)(v-u)<<2)+1024U);y=(u16)(2368U-((u16)(v+u)<<1));}
 cx=scene_read(0x0ce0U);cy=scene_read(0x0ce2U);
 vy=camera_velocity((u16)(y+256U-scene_read(0x0ef4U+actor)-cy));
 vx=camera_velocity((u16)(x-cx));
 rawx=(u16)(cx+vx);rawy=(u16)(cy+vy);
 x=camera_apply(cx,vx,2048U);y=camera_apply(cy,vy,1148U);
 if((rawx&32768U) || rawx>=2048U)vx=0U;
 if((rawy&32768U) || rawy>=1148U)vy=0U;
 scene_write(0x0ce4U,vx);scene_write(0x0ce6U,vy);
 scene_write(0x0ce0U,x);scene_write(0x0ce2U,y);
 if((cx>>5)!=(x>>5) || (cy>>5)!=(y>>5))camera_visual_tainted=1U;
 camera_status=1U;
}
