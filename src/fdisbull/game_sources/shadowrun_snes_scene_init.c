/* Source $80:986C/9DE8-9ECA/9590, $81:A772 and $80:A44C/A287/A343/A7C2.
 * Bounded new-game scene 3 actor construction; each nonnegative script ID
 * yields to the caller's real $C336 task allocator. The caller must seed the
 * shared low WRAM from the selected title state, complete every pending task,
 * and roll back on unsupported status. Room graphics/collision loading,
 * camera, and task execution are separate dependencies. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 rom8(u8 region,u32 offset);
u8 task_shared[65536];
u8 scene_7f[65536];
u8 scene_status,scene_pending;
u16 scene_entry,scene_count,scene_actor,scene_task_id,scene_task_result;
u16 scene_entity,scene_properties,scene_persist;
u16 scene_spawn_kind,scene_spawn_x,scene_spawn_y,scene_spawn_z;
u16 scene_party_kind,scene_party_x,scene_party_y,scene_party_z;
u16 scene_party_direction,scene_party_entity,scene_party_extra;
u8 scene_party_pending;
u16 scene_room_id,scene_room_offset,scene_room_bank,scene_initial_direction;
u16 scene_initial_x,scene_initial_y,scene_initial_z;
u16 scene_bit_at,scene_literal_at,scene_bit_count,scene_bit_word;
u16 scene_decode_target,scene_decode_length;
u8 scene_decode_error,scene_decode_bank;
u32 scene_stream;
u32 scene_room_rom;
u16 scene_read(u16 at) {
 return (u16)((u16)task_shared[at]|((u16)task_shared[at+1U]<<8));
}
void scene_write(u16 at,u16 value) {
 task_shared[at]=(u8)value;task_shared[at+1U]=(u8)(value>>8);
}
u16 scene_rom16(u32 at) {
 return (u16)((u16)rom8(0U,at)|((u16)rom8(0U,at+1UL)<<8));
}
u16 scene_bit(void) {
 u16 v;
 if(!scene_bit_count) {
  if(scene_bit_at>=32766U) {scene_decode_error=1U;return 0U;}
  scene_bit_word=((u16)rom8(0U,scene_stream+(u32)scene_bit_at)<<8)|
                 (u16)rom8(0U,scene_stream+(u32)scene_bit_at+1UL);
  scene_bit_at+=2U;scene_bit_count=16U;
 }
 v=scene_bit_word>>15;scene_bit_word<<=1;scene_bit_count-=1U;return v;
}
u16 scene_gamma(void) {
 u16 n,i;
 n=1U;
 for(i=0U;i<16U;i+=1U) {
  if(scene_bit())return n;
  if(n&32768U) {scene_decode_error=1U;return 0U;}
  n=(n<<1)|scene_bit();
 }
 scene_decode_error=1U;return 0U;
}
/* The $986C source stream is a bounded single-ROM profile, not a general
 * decompressor. Backreferences address the already emitted output. */
u8 scene_decoded_read(u16 index) {
 if(scene_decode_bank)return scene_7f[scene_decode_target+index];
 return task_shared[scene_decode_target+index];
}
void scene_decoded_write(u16 index,u8 value) {
 if(scene_decode_bank)scene_7f[scene_decode_target+index]=value;
 else task_shared[scene_decode_target+index]=value;
}
void scene_decode(void) {
 u16 total,out,i,j,n,width,ref,more;
 scene_status=0U;scene_decode_error=0U;
 total=scene_rom16(scene_stream);
 if(total!=scene_decode_length || (u32)scene_decode_target+(u32)total>65536UL)return;
 scene_bit_at=scene_rom16(scene_stream+2UL)+2U;
 scene_literal_at=4U;scene_bit_count=0U;scene_bit_word=0U;out=0U;
 for(i=0U;i<3515U;i+=1U) {
  n=scene_gamma();if(scene_decode_error || !n || n>total-out)return;
  for(j=0U;j<n;j+=1U) {
   scene_decoded_write(out,rom8(0U,scene_stream+(u32)scene_literal_at));
   scene_literal_at+=1U;out+=1U;
  }
  if(out==total) {scene_status=1U;return;}
  for(more=0U;more<3515U;more+=1U) {
   if(out>=256U)width=8U+(u16)rom8(0U,0x1fb6UL+(u32)(out>>8));
   else width=(u16)rom8(0U,0x1fb6UL+(u32)out);
   if(!width || width>16U)return;
   ref=0U;
   for(j=0U;j<width;j+=1U)ref=(ref<<1)|scene_bit();
   n=scene_gamma()+2U;
   if(scene_decode_error || ref>=out || n>total-out)return;
   for(j=0U;j<n;j+=1U) {
    scene_decoded_write(out,scene_decoded_read(ref+j));out+=1U;
   }
   if(out==total) {scene_status=1U;return;}
   if(!scene_bit())break;
  }
 }
}
void shadowrun_snes_scene_world(u8 unused) {
 scene_stream=0x5fc42UL;scene_decode_target=0x2e00U;
 scene_decode_length=3515U;scene_decode_bank=0U;scene_decode();
}
/* $986C/$9878-$9918: New Game's persistent tail, after world decode.
 * Untouched gaps retain their incoming bytes; room changes never call this. */
void shadowrun_snes_scene_newgame_extension(u8 unused) {
 u16 i;
 for(i=0U;i<64U;i+=1U)task_shared[0x3bbbU+i]=0U;
 for(i=0U;i<104U;i+=1U)task_shared[0x3c2eU+i]=rom8(0U,0x172cUL+(u32)i);
 for(i=0U;i<13U;i+=1U)task_shared[0x3c96U+i]=rom8(0U,0x171fUL+(u32)i);
 task_shared[0x3bfbU]=3U;task_shared[0x3bfdU]=3U;task_shared[0x3bffU]=3U;
 task_shared[0x3c00U]=30U;task_shared[0x3c01U]=1U;task_shared[0x3c04U]=1U;
 task_shared[0x3bfcU]=0U;task_shared[0x3c02U]=0U;task_shared[0x3c03U]=0U;
 task_shared[0x3c05U]=0U;task_shared[0x3c06U]=0U;task_shared[0x3c07U]=0U;
 task_shared[0x3c08U]=0U;task_shared[0x3c09U]=0U;task_shared[0x3c0aU]=0U;
 task_shared[0x3c0bU]=0U;task_shared[0x3c0cU]=0U;task_shared[0x3c17U]=0U;
 task_shared[0x3c18U]=0U;task_shared[0x3c19U]=0U;
 scene_write(0x3c0dU,0U);scene_write(0x3c0fU,0U);scene_write(0x3c11U,0U);
 scene_write(0x3c13U,0U);scene_write(0x3c1cU,0U);scene_write(0x3c15U,0x716cU);
}
/* $81:A117 chooses zone 100's compressed stream from $8B:FA53 and expands
 * it into $7F:DA14; the later tile/collision interpretation is separate. */
void shadowrun_snes_scene_room_data(u8 unused) {
 u16 ptr,bank;
 scene_status=0U;
 ptr=scene_rom16(0x5fb7fUL);bank=(u16)rom8(0U,0x5fb81UL);
 if(ptr!=0xdee2U || bank!=0x8bU)return;
 scene_stream=((u32)(bank&127U)<<15)+(u32)(ptr&32767U);
 scene_decode_target=0xda14U;scene_decode_length=263U;scene_decode_bank=1U;
 scene_decode();
}
/* $81:8926/$8929 initialize camera motion before scene construction. */
void shadowrun_snes_scene_reset_camera_motion(u8 unused) {
 scene_write(0x0ce4U,0U);scene_write(0x0ce6U,0U);
}
void shadowrun_snes_scene_begin(u8 unused) {
 u16 i,ptr;
 scene_status=0U;scene_pending=0U;
 shadowrun_snes_scene_world(0U);if(!scene_status)return;
 shadowrun_snes_scene_newgame_extension(0U);
 shadowrun_snes_scene_reset_camera_motion(0U);
 /* $9590 selects scene 3; no carried-over party actor is present. */
 scene_write(0x3ca3U,65535U);scene_write(0x2de4U,1U);
 scene_write(0x2de6U,65534U);scene_write(0x2de2U,3U);
 scene_room_id=3U;
 /* $81:A772 resets the actor allocator and active list. */
 scene_write(0x157eU,0U);scene_write(0x14ccU,65534U);
 for(i=0U;i<88U;i+=2U)scene_write(0x3f04U+i,65535U);
 /* $A287 intentionally skips party creation when $2DE6 is negative. */
 scene_write(0x0cdeU,65535U);scene_write(0x1d7dU,65535U);
 ptr=scene_rom16(0x692caUL);
 scene_room_bank=153U+(ptr>>15);scene_room_offset=ptr|32768U;
 if(scene_room_bank!=153U || scene_room_offset!=0x8432U)return;
 scene_room_rom=((u32)(scene_room_bank&127U)<<15)+(u32)(scene_room_offset&32767U);
 scene_initial_direction=(u16)rom8(0U,0x692ccUL);
 scene_initial_x=scene_rom16(0x692cdUL);
 scene_initial_y=scene_rom16(0x692cfUL);
 scene_initial_z=scene_rom16(0x692d1UL);
 scene_write(0x0cf6U,scene_rom16(scene_room_rom+2UL)-1U);
 task_shared[0x0cf8U]=(u8)scene_room_bank;
 scene_count=(u16)rom8(0U,scene_room_rom+4UL);
 if(scene_count!=21U)return;
 scene_entry=0U;scene_status=1U;
}
/* $A3F1/$81:8A05 camera for the initial scene-3 rectangle. */
void shadowrun_snes_scene_camera(u8 unused) {
 u16 cx,cy,a,b,u,v,changed,lo,hi;
 u32 bounds;
 scene_status=0U;
 if(scene_room_id!=3U || scene_room_bank!=153U)return;
 bounds=((u32)(scene_room_bank&127U)<<15)+(u32)scene_read(0x0cf6U)-32768UL+1UL;
 if(bounds+9UL>=1048576UL || scene_rom16(bounds+8UL)!=65535U)return;
 cy=(u16)(1160U-scene_initial_x-scene_initial_y);
 cy=(cy>>1)<<2;
 cx=(u16)(256U+scene_initial_y-scene_initial_x)<<2;
 a=cx-1024U;b=(u16)(2368U-cy)<<1;
 u=(u16)(b-a)>>3;v=(u16)(b+a)>>3;changed=0U;
 lo=scene_rom16(bounds);hi=scene_rom16(bounds+2UL);
 if(u<lo) {u=lo;changed=1U;}
 if(u>=hi) {u=hi;changed=1U;}
 lo=scene_rom16(bounds+4UL);hi=scene_rom16(bounds+6UL);
 if(v<lo) {v=lo;changed=1U;}
 if(v>=hi) {v=hi;changed=1U;}
 if(changed) {cx=((u16)(v-u)<<2)+1024U;cy=2368U-((u16)(v+u)<<1);}
 cy+=256U;cy-=(u16)(scene_initial_z<<2);
 if(cx&32768U)cx=0U;else if(cx>=2048U)cx=2048U;
 if(cy&32768U)cy=0U;else if(cy>=1148U)cy=1148U;
 scene_write(0x0ce0U,cx);scene_write(0x0ce2U,cy);scene_status=1U;
}
void scene_finish_actor(void) {
 u16 flags;
 scene_write(0x1526U+scene_actor,scene_entity);
 flags=((scene_properties&192U)<<9)|((scene_properties&128U)>>7);
 scene_write(0x141cU+scene_actor,flags);
 scene_write(0x13c4U+scene_actor,scene_persist);
}
/* $A7C2: allocate and initialize one actor. The caller supplies source
 * arguments in game units and resolves a nonnegative task ID via $C336. */
void shadowrun_snes_actor_allocate(u8 unused) {
 u16 slot,depth,count,i;
 scene_status=0U;
 /* Scene $01 includes source actor kind $98; other high kinds remain unqualified. */
 if(scene_pending || (scene_spawn_kind>=128U && !(scene_room_id==1U && scene_spawn_kind==152U)))return;
 slot=88U;
 for(i=0U;i<44U;i+=1U) {
  slot-=2U;
  if(scene_read(0x3f04U+slot)&32768U)break;
 }
 if(!(scene_read(0x3f04U+slot)&32768U))return;
 scene_actor=slot;
 scene_write(0x3f04U+slot,scene_spawn_kind);
 scene_write(0x0d3cU+slot,0U);scene_write(0x0d94U+slot,0U);scene_write(0x0decU+slot,0U);
 scene_write(0x0fa4U+slot,0U);scene_write(0x421cU+slot,0U);scene_write(0x4274U+slot,0U);
 scene_write(0x42ccU+slot,0U);scene_write(0x4324U+slot,0U);scene_write(0x437cU+slot,0U);
 scene_write(0x43d4U+slot,0U);scene_write(0x442cU+slot,0U);scene_write(0x40bcU+slot,0U);
 scene_write(0x115cU+slot,0U);scene_write(0x3f5cU+slot,0U);
 scene_write(0x0e44U+slot,scene_spawn_x<<2);
 scene_write(0x0e9cU+slot,scene_spawn_y<<2);
 depth=(u16)((scene_spawn_x<<2)+(scene_spawn_y<<2));scene_write(0x0f4cU+slot,depth>>1);
 scene_write(0x0ef4U+slot,scene_spawn_z<<2);
 scene_write(0x10acU+slot,0U);scene_write(0x12bcU+slot,0U);scene_write(0x1314U+slot,0U);
 scene_write(0x11b4U+slot,0U);scene_write(0x13c4U+slot,0U);scene_write(0x141cU+slot,0U);
 scene_write(0x1054U+slot,65535U);scene_write(0x1526U+slot,65535U);
 scene_write(0x400cU+slot,128U);scene_write(0x3fb4U+slot,1U);
 scene_write(0x1474U+slot,scene_rom16(0x66fb4UL+(u32)scene_spawn_kind*6UL));
 count=scene_read(0x14ccU)+2U;
 if((count&1U) || count>=88U)return;
 scene_write(0x14ccU,count);scene_write(0x14ceU+count,slot);
 scene_write(0U,slot);
 if(!(scene_task_id&32768U)) {scene_pending=1U;scene_status=3U;return;}
 scene_status=1U;
}
void shadowrun_snes_scene_next(u8 unused) {
 u16 xpack,ypack,entity,props,persist;
 u32 entry,meta;
 scene_status=0U;
 if(scene_pending || scene_room_id!=3U || scene_entry>scene_count)return;
 if(scene_entry==scene_count) {scene_status=2U;return;}
 entry=scene_room_rom+5UL+(u32)scene_entry*6UL;
 xpack=scene_rom16(entry);ypack=scene_rom16(entry+2UL);entity=scene_rom16(entry+4UL);
 meta=438321UL+(u32)entity;
 if(meta+6UL>=1048576UL)return;
 props=(u16)rom8(0U,meta);persist=scene_rom16(meta+1UL);
 if(!(props|scene_read(0x2de4U))) {scene_entry+=1U;scene_status=1U;return;}
 if(persist) {
  if(persist>65531U)return;
  if(scene_read(persist+3U)!=65535U) {scene_entry+=1U;scene_status=1U;return;}
 }
 scene_spawn_kind=scene_rom16(meta+3UL);scene_task_id=scene_rom16(meta+5UL);
 scene_spawn_x=xpack&2047U;scene_spawn_y=ypack&2047U;
 scene_spawn_z=((xpack&63488U)>>11)|((ypack&63488U)>>6);
 scene_entity=entity;scene_properties=props;scene_persist=persist;
 shadowrun_snes_actor_allocate(0U);if(!scene_status)return;
 scene_entry+=1U;if(scene_pending)return;
 scene_finish_actor();
 scene_status=1U;
}
void shadowrun_snes_actor_task_complete(u8 unused) {
 scene_status=0U;
 if(!scene_pending || (scene_task_result&1U) || scene_task_result>=96U)return;
 scene_write(0x136cU+scene_actor,scene_task_result);
 scene_pending=0U;scene_status=1U;
}
/* $A173-$A1C4: the first observed party insertion. The task allocator and
 * source $AA3C direction setter run between begin and finish. */
void shadowrun_snes_party_begin(u8 unused) {
 u16 multiplier,scaled;
 u32 meta;
 scene_status=0U;
 if(scene_party_pending || scene_pending || scene_read(0x2de6U)!=65534U ||
    scene_party_kind!=11U || scene_party_entity!=0x08b2U || scene_party_direction>7U)return;
 meta=438321UL+(u32)scene_party_entity;
 if(scene_rom16(meta+3UL)!=scene_party_kind)return;
 scene_write(0x2de6U,0U);scene_write(0x2de8U,scene_party_kind);
 multiplier=(u16)task_shared[0x3c05U];scaled=scene_party_extra>>3;
 scene_write(0x2df8U,(u16)(scene_party_extra+scaled*multiplier));
 scene_write(0x2df0U,scene_party_entity);
 scene_spawn_kind=scene_party_kind;scene_spawn_x=scene_party_x;
 scene_spawn_y=scene_party_y;scene_spawn_z=scene_party_z;
 scene_task_id=scene_rom16(meta+5UL);
 shadowrun_snes_actor_allocate(0U);if(!scene_status)return;
 scene_party_pending=1U;
}
/* $AA3C: freshly allocated actors have action $FFFF, so a direction change
 * writes only $11B4 and returns without animation/action setup. */
void shadowrun_snes_party_direction(u8 unused) {
 scene_status=0U;
 if(!scene_party_pending || scene_pending || scene_party_direction>7U ||
    scene_read(0x1054U+scene_actor)!=65535U)return;
 scene_write(0x11b4U+scene_actor,scene_party_direction);scene_status=1U;
}
void shadowrun_snes_party_finish(u8 unused) {
 u16 flags,i,index,found;
 u32 meta;
 scene_status=0U;
 if(!scene_party_pending || scene_pending || scene_read(0x2de6U)!=0U ||
    scene_read(0x11b4U+scene_actor)!=scene_party_direction)return;
 meta=438321UL+(u32)scene_party_entity;
 scene_write(0x0cdeU,scene_actor);
 scene_write(0x1526U+scene_actor,scene_party_entity);
 flags=(u16)rom8(0U,meta);flags=((flags&192U)<<9)|((flags&128U)>>7);
 scene_write(0x141cU+scene_actor,flags);
 scene_write(0x13c4U+scene_actor,scene_rom16(meta+1UL));
 scene_write(0x1474U+scene_actor,scene_read(0x1474U+scene_actor)|3U);
 scene_write(0x1fc4U,scene_actor);
 found=0U;index=26U;
 for(i=0U;i<13U;i+=1U) {
  index-=2U;
  if(scene_rom16(0x1683UL+(u32)index)==scene_party_entity) {found=1U;break;}
 }
 if(!found)return;
 scene_write(0x43d4U+scene_actor,(u16)task_shared[0x3c30U+(index<<2)]);
 scene_party_pending=0U;scene_status=1U;
}
void shadowrun_snes_scene_task_complete(u8 unused) {
 shadowrun_snes_actor_task_complete(0U);if(!scene_status)return;
 scene_finish_actor();
}
