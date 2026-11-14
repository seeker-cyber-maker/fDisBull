/* Scene-3 static collision from $81:A117/$8DE2/$84DE/$8701/$840E.
 * Appended after scene_init.c: task_shared and scene_7f are the authoritative
 * mutable banks. Source static records, owners and linked cell heads are
 * derived from ROM and the just-decoded room stream, not a later capture. */
u16 scene_static_record,scene_static_node,scene_static_cursor;
u8 scene_static_supported;
u16 scene_sext(u8 value) {
 if(value&128U)return 65280U|(u16)value;
 return (u16)value;
}
void scene_static_store(u16 at,u16 value) {
 scene_write(0xe288U+scene_static_record+at,value);
}
void scene_static_insert(void) {
 u16 left,right,top,bottom,x0,x1,y0,y1,x,y,cell,head,owner;
 scene_static_supported=0U;
 if(scene_static_record>0x0c78U)return;
 left=scene_read(0xe288U+scene_static_record);
 top=scene_read(0xe28aU+scene_static_record);
 right=scene_read(0xe28eU+scene_static_record);
 bottom=scene_read(0xe290U+scene_static_record);
 x0=(left&960U)>>5;x1=(right&960U)>>5;
 y0=(top&960U)>>1;y1=(bottom&960U)>>1;
 if(x1<x0 || y1<y0)return;
 for(y=y0;y<=y1;y+=32U)for(x=x0;x<=x1;x+=2U) {
  if(scene_static_node>0x085eU)return;
  cell=x|y;head=scene_read(0xde88U+cell);
  scene_write(0xef18U+scene_static_node,scene_static_record);
  scene_write(0xf778U+scene_static_node,head);
  scene_write(0xde88U+cell,scene_static_node);
  scene_static_node+=2U;
 }
 owner=0xe214U+(scene_static_record>>2);
 if(owner>=65535U)return;
 scene_static_record+=12U;scene_static_supported=1U;
}
void scene_static_group(void) {
 u16 count,i,spec,z,x,y,mirror,ptr,n,j,shape,rx,ry,rz,w,h,d,owner;
 u32 rec,at;
 scene_static_supported=0U;
 if(scene_static_cursor>=0xdb1bU)return;
 count=scene_7f[scene_static_cursor];scene_static_cursor+=1U;
 for(i=0U;i<count;i+=1U) {
  if((u32)scene_static_cursor+5UL>0xdb1bUL)return;
  spec=(u16)((u16)scene_7f[scene_static_cursor]|((u16)scene_7f[scene_static_cursor+1U]<<8));
  z=(u16)scene_7f[scene_static_cursor+2U];x=(u16)scene_7f[scene_static_cursor+3U];
  y=(u16)scene_7f[scene_static_cursor+4U];scene_static_cursor+=5U;
  if((spec&0x6000U) || (z&128U))continue;
  mirror=spec&32768U;
  at=0x5436aUL+(u32)((spec<<1)&65535U);
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
void shadowrun_snes_scene_collision_init(u8 unused) {
 u16 i,commands,op,group,count,j,k,value,owner;
 u32 addr;
 scene_static_supported=0U;
 if(scene_room_rom!=0xc8432UL || scene_7f[0xda17U]!=5U)return;
 /* $8DE2 advances past bounded room tile commands before saving $77. */
 scene_static_cursor=0xda18U;commands=scene_7f[0xda17U];
 for(i=0U;i<commands;i+=1U) {
  op=(u16)((u16)scene_7f[scene_static_cursor]|((u16)scene_7f[scene_static_cursor+1U]<<8));
  if(op&32768U)scene_static_cursor+=5U;else scene_static_cursor+=4U;
 }
 if(scene_static_cursor!=0xda2eU)return;
 scene_static_record=0U;scene_static_node=0U;
 for(i=0U;i<256U;i+=1U)scene_write(0xde88U+(i<<1),65535U);
 scene_static_group();if(!scene_static_supported)return;
 scene_static_group();if(!scene_static_supported)return;
 addr=scene_room_rom+5UL+(u32)scene_count*6UL;
 scene_write(0x009aU,(u16)((addr&32767UL)|32768UL));
 task_shared[0x009cU]=(u8)scene_room_bank;
 for(group=0U;group<3U;group+=1U) {
  count=(u16)rom8(0U,addr);addr+=1UL;
  for(i=0U;i<count;i+=1U) {
   if(addr+12UL>=1048576UL)return;
   for(j=0U;j<6U;j+=1U) {
    value=scene_rom16(addr);addr+=2UL;scene_static_store(j<<1,value);
   }
   if(group)addr+=2UL;
   owner=0xe214U+(scene_static_record>>2);
   if(group) {scene_7f[owner]=255U;scene_7f[owner+1U]=255U;}
   else {scene_7f[owner]=0U;scene_7f[owner+1U]=0U;}
   scene_static_insert();if(!scene_static_supported)return;
  }
  if(!group) {
   scene_write(0x009dU,(u16)((addr&32767UL)|32768UL));
   task_shared[0x009fU]=(u8)scene_room_bank;
  }
 }
 /* $A518-$A53B traverses both remaining source lists to form $F3. */
 scene_write(0x00f3U,(u16)((addr&32767UL)|32768UL));
 task_shared[0x00f5U]=(u8)scene_room_bank;
 scene_write(0xde84U,scene_static_record);
 scene_write(0xde86U,scene_static_node);
 scene_static_supported=1U;
}
