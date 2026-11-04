/* Source $80:A44C/$A287/$A343/$A3F1/$A511 for the observed scene $1F.
 * Caller owns task arrays, renderer/audio acknowledgements and whole-frame
 * rollback. Existing scene allocator/decompressor and collision helpers share
 * authoritative WRAM; the new-game world decoder is deliberately not called.
 * status: 0 unsupported, 1 complete, 2 request, 3 continue iterating.
 * request: 1 close cursor, 2 C176 reset, 3 zone presentation/A772 sprite
 * reset, 4 C336 task creation, 5 room presentation after static construction.
 */
u8 transition_status,transition_request,transition_stage,transition_party_pending;
u16 transition_scene,transition_party_index,transition_actor,transition_task;
u16 transition_kind,transition_entity,transition_persist,transition_properties;
u16 transition_zone,transition_zone_length,transition_zone_end;
u8 transition_graphics_status;
u16 transition_graphics_target,transition_graphics_length;
u32 transition_graphics_stream;

/* $80:9E01 decodes complete runs until at least 128 bytes, regardless of
 * the stream's full-length header. The caller must derive stream/destination
 * from the real $81:A1E1 cache allocator and roll back unsupported inputs. */
void shadowrun_snes_transition_graphics_block(u8 unused) {
 u16 i,j,n,out,width,ref,more;
 transition_graphics_status=0U;transition_graphics_length=0U;scene_decode_error=0U;
 if(transition_graphics_stream>1015806UL || transition_graphics_target>65407U ||
    transition_graphics_stream+4UL+(65536UL-(u32)transition_graphics_target)>1048576UL)return;
 scene_stream=transition_graphics_stream;scene_decode_target=transition_graphics_target;scene_decode_bank=0U;
 scene_bit_at=scene_rom16(scene_stream+2UL)+2U;scene_literal_at=4U;
 scene_bit_count=0U;scene_bit_word=0U;out=0U;
 for(i=0U;i<256U;i+=1U) {
  n=scene_gamma();if(scene_decode_error || !n || (u32)transition_graphics_target+(u32)out+(u32)n>65536UL)return;
  for(j=0U;j<n;j+=1U) {scene_decoded_write(out,rom8(0U,scene_stream+(u32)scene_literal_at));scene_literal_at+=1U;out+=1U;}
  if(out>=128U) {transition_graphics_length=out;transition_graphics_status=1U;return;}
  for(more=0U;more<256U;more+=1U) {
   if(out>=256U)width=8U+(u16)rom8(0U,0x1fb6UL+(u32)(out>>8));
   else width=(u16)rom8(0U,0x1fb6UL+(u32)out);
   if(!width || width>16U)return;
   ref=0U;for(j=0U;j<width;j+=1U)ref=(ref<<1)|scene_bit();
   n=scene_gamma()+2U;
   if(scene_decode_error || ref>=out || (u32)transition_graphics_target+(u32)out+(u32)n>65536UL)return;
   for(j=0U;j<n;j+=1U) {scene_decoded_write(out,scene_decoded_read(ref+j));out+=1U;}
   if(out>=128U) {transition_graphics_length=out;transition_graphics_status=1U;return;}
   if(!scene_bit())break;
  }
 }
}

void shadowrun_snes_transition_begin(u8 unused) {
 u16 ptr;u32 desc;
 transition_status=0U;transition_request=0U;transition_stage=0U;
 if((transition_scene!=0x001fU && transition_scene!=1U) || scene_pending)return;
 desc=0x692afUL+(u32)transition_scene*9UL;
 ptr=scene_rom16(desc);
 if((transition_scene==0x001fU && ptr!=0xa07eU) || (transition_scene==1U && ptr!=0x012aU))return;
 scene_room_id=transition_scene;scene_room_bank=153U+(ptr>>15);
 scene_room_offset=ptr|32768U;
 scene_room_rom=((u32)(scene_room_bank&127U)<<15)+(u32)(ptr&32767U);
 scene_initial_direction=(u16)rom8(0U,desc+2UL);
 scene_initial_x=scene_rom16(desc+3UL);scene_initial_y=scene_rom16(desc+5UL);
 scene_initial_z=scene_rom16(desc+7UL);
 transition_zone=(u16)rom8(0U,scene_room_rom);
 if(scene_initial_direction>7U || (transition_scene==0x001fU && transition_zone!=87U) ||
    (transition_scene==1U && transition_zone!=9U))return;
 scene_write(0x2de2U,transition_scene);scene_write(0x0086U,scene_room_offset);
 task_shared[0x0088U]=(u8)scene_room_bank;
 task_shared[0x0cf8U]=(u8)scene_room_bank;
 task_shared[0x009cU]=(u8)scene_room_bank;task_shared[0x009fU]=(u8)scene_room_bank;
 task_shared[0x00f5U]=(u8)scene_room_bank;task_shared[0x00feU]=(u8)scene_room_bank;
 transition_stage=1U;transition_request=1U;transition_status=2U;
}

/* Caller invokes only after completing the indicated source operation. */
void shadowrun_snes_transition_resume(u8 unused) {
 u16 i,ptr,bank;
 transition_status=0U;
 if(transition_stage==1U && transition_request==1U) {
  transition_stage=2U;transition_request=2U;transition_status=2U;return;
 }
 if(transition_stage==2U && transition_request==2U) {
  scene_write(0x0cf6U,scene_rom16(scene_room_rom+2UL)-1U);
  ptr=scene_rom16(0x5fa53UL+(u32)transition_zone*3UL);
  bank=(u16)rom8(0U,0x5fa55UL+(u32)transition_zone*3UL);
  if((transition_scene==0x001fU && (ptr!=0xf8d7U || bank!=0x8bU)) ||
     (transition_scene==1U && (ptr!=0xce98U || bank!=0x8aU)))return;
  scene_stream=((u32)(bank&127U)<<15)+(u32)(ptr&32767U);
  transition_zone_length=scene_rom16(scene_stream);
  if((transition_scene==0x001fU && transition_zone_length!=86U) ||
     (transition_scene==1U && transition_zone_length!=1084U))return;
  transition_zone_end=0xda14U+transition_zone_length;
  scene_decode_target=0xda14U;scene_decode_length=transition_zone_length;
  scene_decode_bank=1U;scene_decode();if(scene_status!=1U)return;
  transition_stage=3U;transition_request=3U;transition_status=2U;return;
 }
 if(transition_stage==3U && transition_request==3U) {
  /* A772 actor-list/kind reset; caller already performed its sprite reset. */
  scene_write(0x157eU,0U);scene_write(0x14ccU,65534U);
  for(i=0U;i<88U;i+=2U)scene_write(0x3f04U+i,65535U);
  scene_write(0x0cdeU,65535U);scene_write(0x1d7dU,65535U);
  transition_party_index=scene_read(0x2de6U);
  if(transition_party_index!=0U && transition_party_index!=65534U)return;
  transition_stage=4U;transition_request=0U;transition_status=3U;return;
 }
 if(transition_request==4U && transition_party_pending) {
  scene_task_result=transition_task;shadowrun_snes_actor_task_complete(0U);
  if(!scene_status)return;
  transition_request=0U;transition_status=3U;return;
 }
 if(transition_stage==7U && transition_request==5U) {
  /* $81:8BD9 arrival presentation ends with zero camera velocities. */
  scene_write(0x0ce4U,0U);scene_write(0x0ce6U,0U);
  transition_stage=8U;transition_request=0U;transition_status=1U;return;
 }
}

void transition_finish_party(void) {
 u16 flags,index,i,found,character,reload,selector,old_direction;
 if(scene_pending || !transition_party_pending)return;
 /* $A2C9 calls $AA3C on the freshly allocated actor. $A7C2 clears the
  * animation-table pointer, but leaves its previous reload/selector words. */
 scene_write(2U,scene_initial_direction);
 old_direction=scene_read(0x11b4U+scene_actor);
 if(old_direction!=scene_initial_direction) {
  scene_write(0x11b4U+scene_actor,scene_initial_direction);
  reload=scene_read(0x1104U+scene_actor);
  if(reload && reload<128U) {
   if(old_direction>7U || scene_initial_direction>7U || scene_read(0x10acU+scene_actor))return;
   scene_write(8U,0U);scene_write(10U,0x008cU);
   selector=scene_read(0x120cU+scene_actor);
   selector=(selector&65280U)|((selector-(u16)task_shared[old_direction]+
                                (u16)task_shared[scene_initial_direction])&255U);
   scene_write(0x120cU+scene_actor,selector);
   scene_write(0x400cU+scene_actor,128U);scene_write(0x115cU+scene_actor,65535U);
  }
 }
 if(transition_kind==11U)scene_write(0x0cdeU,scene_actor);
 scene_write(0x1526U+scene_actor,transition_entity);
 flags=((transition_properties&192U)<<9)|((transition_properties&128U)>>7);
 scene_write(0x141cU+scene_actor,flags);scene_write(0x13c4U+scene_actor,transition_persist);
 index=26U;found=0U;
 for(i=0U;i<13U;i+=1U) {index-=2U;if(scene_rom16(0x1683UL+(u32)index)==transition_entity) {found=1U;break;}}
 if(!found)return;
 character=(u16)task_shared[0x3c30U+(index<<2)];
 if(transition_kind==11U && task_shared[0x3c18U])character+=2U;
 scene_write(0x43d4U+scene_actor,character);
 if(transition_kind!=11U)scene_write(0x1474U+scene_actor,scene_read(0x1474U+scene_actor)|3U);
 scene_write(0x1fc4U+transition_party_index,scene_actor);
 transition_party_pending=0U;transition_party_index=65534U;
}

/* Same source clamp as $A3F1/$8A05; the bounds are room-owned ROM data. */
void transition_camera(void) {
 u16 cx,cy,a,b,u,v,changed,lo,hi;u32 bounds;
 transition_status=0U;
 bounds=((u32)(scene_room_bank&127U)<<15)+(u32)(scene_read(0x0cf6U)&32767U)+1UL;
 if(bounds+9UL>=1048576UL)return;
 cy=(u16)(1160U-scene_initial_x-scene_initial_y);cy=(cy>>1)<<2;
 cx=(u16)(256U+scene_initial_y-scene_initial_x)<<2;
 a=cx-1024U;b=(u16)(2368U-cy)<<1;
 u=(u16)(b-a)>>3;v=(u16)(b+a)>>3;changed=0U;
 if(scene_rom16(bounds)!=65535U) {
  if(scene_rom16(bounds+8UL)!=65535U)return;
  lo=scene_rom16(bounds);hi=scene_rom16(bounds+2UL);
  if(u<lo) {u=lo;changed=1U;}if(u>=hi) {u=hi;changed=1U;}
  lo=scene_rom16(bounds+4UL);hi=scene_rom16(bounds+6UL);
  if(v<lo) {v=lo;changed=1U;}if(v>=hi) {v=hi;changed=1U;}
 }
 if(changed) {cx=((u16)(v-u)<<2)+1024U;cy=2368U-((u16)(v+u)<<1);}
 cy+=256U;cy-=(u16)(scene_initial_z<<2);
 if(cx&32768U)cx=0U;else if(cx>=2048U)cx=2048U;
 if(cy&32768U)cy=0U;else if(cy>=1148U)cy=1148U;
 scene_write(0x0ce0U,cx);scene_write(0x0ce2U,cy);transition_status=1U;
}

/* $84DE shape groups, bounded by the current decoded zone length. */
void transition_static_group(void) {
 u16 count,i,spec,z,x,y,mirror,ptr,n,j,shape,rx,ry,rz,w,h,d,owner;
 u32 rec,at;
 scene_static_supported=0U;
 if(scene_static_cursor>=transition_zone_end)return;
 count=scene_7f[scene_static_cursor];scene_static_cursor+=1U;
 if((u32)scene_static_cursor+(u32)count*5UL>(u32)transition_zone_end)return;
 for(i=0U;i<count;i+=1U) {
  spec=(u16)((u16)scene_7f[scene_static_cursor]|((u16)scene_7f[scene_static_cursor+1U]<<8));
  z=(u16)scene_7f[scene_static_cursor+2U];x=(u16)scene_7f[scene_static_cursor+3U];
  y=(u16)scene_7f[scene_static_cursor+4U];scene_static_cursor+=5U;
  if((spec&0x6000U) || (z&128U))continue;
  mirror=spec&32768U;at=0x5436aUL+(u32)((spec<<1)&65535U);
  if(at+1UL>=1048576UL)return;
  ptr=scene_rom16(at);if(ptr<32768U)return;
  rec=327680UL+(u32)(ptr&32767U);
  n=(u16)rom8(0U,rec+7UL);shape=8U+(u16)rom8(0U,rec)*5U;
  if((u32)shape+(u32)n*6UL>32768UL)return;
  for(j=0U;j<n;j+=1U) {
   at=rec+(u32)shape+(u32)j*6UL;
   rx=scene_sext(rom8(0U,at));w=(u16)rom8(0U,at+1UL);
   ry=scene_sext(rom8(0U,at+2UL));h=(u16)rom8(0U,at+3UL);
   rz=scene_sext(rom8(0U,at+4UL));d=(u16)rom8(0U,at+5UL);
   if(mirror) {
    scene_static_store(2U,(y<<2)+rx);scene_static_store(8U,(y<<2)+rx+w);
    scene_static_store(0U,(x<<2)+ry);scene_static_store(6U,(x<<2)+ry+h);
   } else {
    scene_static_store(0U,(x<<2)+rx);scene_static_store(6U,(x<<2)+rx+w);
    scene_static_store(2U,(y<<2)+ry);scene_static_store(8U,(y<<2)+ry+h);
   }
   scene_static_store(4U,(z<<3)+rz);scene_static_store(10U,(z<<3)+rz+d);
   owner=0xe214U+(scene_static_record>>2);
   scene_7f[owner]=0U;scene_7f[owner+1U]=0U;
   scene_static_insert();if(!scene_static_supported)return;
  }
 }
 scene_static_supported=1U;
}

void transition_collision(void) {
 u16 i,j,group,count,value,owner,commands,op;u32 addr;
 transition_status=0U;
 /* $8DE2 skips the decoded tile commands before the two collision groups. */
 commands=scene_7f[0xda17U];scene_static_cursor=0xda18U;
 for(i=0U;i<commands;i+=1U) {
  if((u32)scene_static_cursor+2UL>transition_zone_end)return;
  op=(u16)((u16)scene_7f[scene_static_cursor]|((u16)scene_7f[scene_static_cursor+1U]<<8));
  if(op&32768U)scene_static_cursor+=5U;else scene_static_cursor+=4U;
  if(scene_static_cursor>transition_zone_end)return;
 }
 scene_static_record=0U;scene_static_node=0U;
 for(i=0U;i<256U;i+=1U)scene_write(0xde88U+(i<<1),65535U);
 transition_static_group();if(!scene_static_supported)return;
 transition_static_group();if(!scene_static_supported || scene_static_cursor!=transition_zone_end)return;
 addr=scene_room_rom+5UL+(u32)scene_count*6UL;
 scene_write(0x009aU,(u16)((addr&32767UL)|32768UL));task_shared[0x009cU]=(u8)scene_room_bank;
 for(group=0U;group<3U;group+=1U) {
  if(addr>=1048576UL)return;
  count=(u16)rom8(0U,addr);addr+=1UL;
  for(i=0U;i<count;i+=1U) {
   if(addr+13UL>=1048576UL)return;
   for(j=0U;j<6U;j+=1U) {value=scene_rom16(addr);addr+=2UL;scene_static_store(j<<1,value);}
   if(group)addr+=2UL;
   owner=0xe214U+(scene_static_record>>2);
   if(group) {scene_7f[owner]=255U;scene_7f[owner+1U]=255U;}
   else {scene_7f[owner]=0U;scene_7f[owner+1U]=0U;}
   scene_static_insert();if(!scene_static_supported)return;
  }
  if(!group) {scene_write(0x009dU,(u16)((addr&32767UL)|32768UL));task_shared[0x009fU]=(u8)scene_room_bank;}
 }
 scene_write(0x00f3U,(u16)((addr&32767UL)|32768UL));task_shared[0x00f5U]=(u8)scene_room_bank;
 scene_write(0xde84U,scene_static_record);scene_write(0xde86U,scene_static_node);
 transition_status=1U;
}

void shadowrun_snes_transition_next(u8 unused) {
 u16 xpack,ypack;u32 entry,meta;
 transition_status=0U;transition_request=0U;
 if(transition_stage==4U) {
  if(transition_party_pending) {
   transition_finish_party();if(transition_party_pending)return;
  }
  if(transition_party_index&32768U) {
   scene_count=(u16)rom8(0U,scene_room_rom+4UL);
   if((transition_scene==0x001fU && scene_count!=3U) ||
      (transition_scene==1U && scene_count!=13U))return;
   scene_entry=0U;transition_stage=5U;transition_status=3U;return;
  }
  if(transition_party_index!=0U || scene_pending)return;
  transition_kind=scene_read(0x2de8U);transition_entity=scene_read(0x2df0U);
  if(transition_kind!=11U || transition_entity!=0x08b2U)return;
  meta=0x6b031UL+(u32)transition_entity;
  transition_properties=(u16)rom8(0U,meta);transition_persist=scene_rom16(meta+1UL);
  if(scene_rom16(meta+3UL)!=transition_kind)return;
  scene_spawn_kind=transition_kind;scene_spawn_x=scene_initial_x;
  scene_spawn_y=scene_initial_y;scene_spawn_z=scene_initial_z;
  scene_write(2U,scene_spawn_x);scene_write(4U,scene_spawn_y);scene_write(6U,scene_spawn_z);
  scene_task_id=scene_rom16(meta+5UL);shadowrun_snes_actor_allocate(0U);
  if(!scene_status)return;
  transition_actor=scene_actor;transition_party_pending=1U;
  if(scene_pending) {transition_request=4U;transition_status=2U;return;}
  transition_status=3U;return;
 }
 if(transition_stage==5U) {
  if(scene_pending)return;
  if(transition_party_pending) {scene_finish_actor();transition_party_pending=0U;}
  if(scene_entry==scene_count) {transition_stage=6U;transition_status=3U;return;}
  if(scene_entry>scene_count)return;
  entry=scene_room_rom+5UL+(u32)scene_entry*6UL;
  xpack=scene_rom16(entry);ypack=scene_rom16(entry+2UL);scene_entity=scene_rom16(entry+4UL);
  meta=0x6b031UL+(u32)scene_entity;if(meta+6UL>=1048576UL)return;
  scene_properties=(u16)rom8(0U,meta);scene_persist=scene_rom16(meta+1UL);
  scene_entry+=1U;
  if(!(scene_properties|scene_read(0x2de4U))) {transition_status=3U;return;}
  if(scene_persist) {
   if(scene_persist>65531U)return;
   if(scene_read(scene_persist+3U)!=65535U) {transition_status=3U;return;}
  }
  scene_spawn_kind=scene_rom16(meta+3UL);scene_task_id=scene_rom16(meta+5UL);
  scene_spawn_x=xpack&2047U;scene_spawn_y=ypack&2047U;
  scene_spawn_z=((xpack&63488U)>>11)|((ypack&63488U)>>6);
  shadowrun_snes_actor_allocate(0U);if(!scene_status)return;
  transition_actor=scene_actor;transition_party_pending=1U;
  if(scene_pending) {transition_request=4U;transition_status=2U;return;}
  transition_status=3U;return;
 }
 if(transition_stage==6U) {
  transition_camera();if(!transition_status)return;
  transition_collision();if(!transition_status)return;
  transition_stage=7U;transition_request=5U;transition_status=2U;return;
 }
}
