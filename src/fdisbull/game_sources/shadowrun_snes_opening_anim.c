/* Source 81:A7D3-A7FA, 80:AC5B-AD80 sprite allocation and sort metadata.
 * task_shared/scene_7f are authoritative. The owner rolls back on refusal.
 * Sprite pixel/OAM transfer is excluded; node ownership and gating are not. */
u8 opening_anim_supported,opening_anim_deferred;
u16 opening_anim_descriptor,opening_anim_count,opening_anim_mode,opening_anim_delta;
u8 opening_anim_seen[128];
u16 opening_anim_rom16(u32 at) {
 return (u16)((u16)rom8(0U,at)|((u16)rom8(0U,at+1UL)<<8));
}
void opening_animation_metadata_reset(void) {
 u16 i,next;
 scene_write(0x0d38U,64U);scene_write(0x0d3aU,2U);scene_write(0x0082U,65534U);
 for(i=0U;i<240U;i+=2U) {
  next=i+2U;if(next&16U)next+=16U;
  scene_write(0x1580U+i,next);
 }
 opening_anim_supported=1U;opening_anim_deferred=0U;
}
/* Source $81:A947 writes X=FFFE after sprite presentation. */
void opening_animation_metadata_pass_finish(void) {scene_write(0x0082U,65534U);}
/* entry is the frame word loaded by $AC5B or restored from pending $115C. */
void opening_animation_metadata(u16 actor,u16 entry) {
 u16 ptr,bank,count,old,used,sum,carry,freecount,freehead,head,diff,i,node,mode,delta,flip;
 u32 at,tail;
 opening_anim_supported=0U;opening_anim_deferred=0U;
 if((actor&1U) || actor>=88U)return;
 ptr=entry|32768U;
 bank=27U;if(entry&32768U)bank=28U;
 if(ptr==32768U)return;
 at=((u32)bank<<15)+(u32)ptr-32768UL;
 if(at>=1048576UL)return;
 count=(u16)rom8(0U,at);tail=at+1UL+(u32)count*4UL;
 if(count>64U || tail+4UL>=1048576UL || ((u32)ptr+1UL+(u32)count*4UL+4UL)>65535UL)return;
 used=scene_read(0x0082U);sum=used+(count<<2);carry=0U;
 if(sum<used)carry=1U;
 old=scene_read(0x12bcU+actor);freecount=scene_read(0x0d38U);
 freehead=scene_read(0x0d3aU);head=scene_read(0x1314U+actor);
 if(old>64U || freecount>64U || (old+freecount)>64U)return;
 flip=(entry&32768U)^32768U;
 if(!carry && sum>=80U) {
  scene_write(0x115cU+actor,ptr^flip);
  opening_anim_deferred=1U;opening_anim_supported=1U;return;
 }
 if(count>old) {
  diff=count-old;
  if(diff>=freecount) {
   scene_write(0x115cU+actor,ptr^flip);
   opening_anim_deferred=1U;opening_anim_supported=1U;return;
  }
  node=freehead;
 } else {diff=old-count;node=head;}
 /* Validate list traversal before mutating the shared allocator. */
 for(i=0U;i<128U;i+=1U)opening_anim_seen[i]=0U;
 for(i=0U;i<diff;i+=1U) {
  if((node&1U) || node>=256U || opening_anim_seen[node>>1])return;
  opening_anim_seen[node>>1]=1U;node=scene_read(0x1580U+node);
 }
 if(count>old) {
  freecount-=diff;
  for(i=0U;i<diff;i+=1U) {
   node=freehead;freehead=scene_read(0x1580U+node);
   scene_write(0x1580U+node,head);head=node;
  }
 } else {
  freecount+=diff;
  for(i=0U;i<diff;i+=1U) {
   node=head;head=scene_read(0x1580U+node);
   scene_write(0x1580U+node,freehead);freehead=node;
  }
 }
 scene_write(0x0d38U,freecount);scene_write(0x0d3aU,freehead);
 scene_write(0x1314U+actor,head);scene_write(0x12bcU+actor,count);
 scene_write(0x0082U,sum);
 mode=opening_anim_rom16(tail+3UL)&7U;if(mode)mode|=32768U;
 delta=(u16)rom8(0U,at-1UL);if(delta&128U)delta|=65280U;delta<<=2;
 scene_write(0x0fa4U+actor,mode);scene_write(0x0ffcU+actor,delta);
 scene_write(0x3f5cU+actor,(ptr+1U+(count<<2))^flip);
 opening_anim_descriptor=entry;opening_anim_count=count;
 opening_anim_mode=mode;opening_anim_delta=delta;opening_anim_supported=1U;
}
/* Return the actor's existing sprite-node chain before source $A882 teardown. */
void opening_animation_metadata_cleanup(u16 actor) {
 u16 count,freecount,freehead,head,node,i;
 opening_anim_supported=0U;
 if((actor&1U) || actor>=88U)return;
 count=scene_read(0x12bcU+actor);freecount=scene_read(0x0d38U);
 freehead=scene_read(0x0d3aU);head=scene_read(0x1314U+actor);node=head;
 if(count>64U || freecount>64U || count+freecount>64U)return;
 for(i=0U;i<128U;i+=1U)opening_anim_seen[i]=0U;
 for(i=0U;i<count;i+=1U) {
  if((node&1U) || node>=256U || opening_anim_seen[node>>1])return;
  opening_anim_seen[node>>1]=1U;node=scene_read(0x1580U+node);
 }
 for(i=0U;i<count;i+=1U) {
  node=head;head=scene_read(0x1580U+node);
  scene_write(0x1580U+node,freehead);freehead=node;
 }
 scene_write(0x0d38U,freecount+count);scene_write(0x0d3aU,freehead);
 scene_write(0x1314U+actor,head);scene_write(0x12bcU+actor,0U);
 opening_anim_supported=1U;
}
