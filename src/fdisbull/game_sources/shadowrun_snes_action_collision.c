/* $80:8371-$8495 and $81:8686 dynamic prospective-action overlap.
 * The containing program supplies task_shared, scene_7f, scene_read/write,
 * and ROM region 0. A zero supported flag requires transaction rollback. */
u16 action_collision_actor,action_collision_action,action_collision_result;
u8 action_collision_supported,action_collision_flags_known;
u16 action_collision_rom16(u32 at) {
 return (u16)((u16)rom8(0U,at)|((u16)rom8(0U,at+1UL)<<8));
}
u16 action_collision_sext(u8 x) {
 if(x&128U)return 0xff00U|(u16)x;
 return (u16)x;
}
void shadowrun_snes_action_collision(u8 unused) {
 u16 actor,kind,action,table,record,x,y,z,left,right,top,bottom,high;
 u16 xlo,xhi,ylo,yhi,cells[4],i,j,node,rec,n,owner,player,flags;
 u16 l,t,lo,r,b,hi,delta,hit,addr;
 u32 at;
 action_collision_supported=0U;actor=action_collision_actor;action=action_collision_action;
 if((actor&1U) || actor>=88U || action>=128U)return;
 kind=scene_read(0x3f04U+actor);if(kind>=256U)return;
 table=action_collision_rom16(0x66d8aUL+((u32)kind<<1));
 if(table<0x8000U || (u32)table+((u32)action<<1)+1UL>65535UL)return;
 record=action_collision_rom16(0x60000UL+(u32)(table&0x7fffU)+((u32)action<<1));
 if(record<0x8000U || record>0xfff8U)return;
 at=0x60000UL+(u32)(record&0x7fffU);
 x=scene_read(0x0e44U+actor)>>2;y=scene_read(0x0e9cU+actor)>>2;
 z=scene_read(0x0ef4U+actor)>>2;
 left=(x+action_collision_sext(rom8(0U,at+3UL)))&65535U;
 right=(x+action_collision_sext(rom8(0U,at+4UL)))&65535U;
 top=(y+action_collision_sext(rom8(0U,at+5UL)))&65535U;
 bottom=(y+action_collision_sext(rom8(0U,at+6UL)))&65535U;
 high=(z+(u16)rom8(0U,at+7UL))&65535U;
 xlo=(left&0x03c0U)>>5;xhi=(right&0x03c0U)>>5;
 ylo=(top&0x03c0U)>>1;yhi=(bottom&0x03c0U)>>1;
 cells[0]=xlo|yhi;cells[1]=xlo|ylo;cells[2]=xhi|ylo;cells[3]=xhi|yhi;
 player=scene_read(0x0cdeU);flags=scene_read(0x1474U+actor);hit=0U;
 for(i=0U;i<4U;i+=1U) {
  for(j=0U;j<i;j+=1U)if(cells[j]==cells[i])break;
  if(j<i)continue;
  node=scene_read(0xe088U+cells[i]);
  for(n=0U;node<32768U;n+=1U) {
   if(n>=128U || node>0x0860U || (node&1U))return;
   rec=scene_read(0xef18U+node);
   if(rec>0x0c84U || (rec&3U))return;
   l=scene_read(0xe288U+rec);t=scene_read(0xe28aU+rec);
   lo=scene_read(0xe28cU+rec);r=scene_read(0xe28eU+rec);
   b=scene_read(0xe290U+rec);hi=scene_read(0xe292U+rec);
   if(right>=l && r>=left && bottom>=t && b>=top && high>=lo && hi>=z) {
    delta=hi-z;
    if(delta>=hit) {
     addr=0xe214U+(rec>>2);
     owner=(u16)((u16)scene_7f[addr]|((u16)scene_7f[addr+1U]<<8));
     if(owner!=actor) {
      if(owner==player) {
       if(!action_collision_flags_known)return;
       if((flags&3U)!=3U)hit=delta;
      } else hit=delta;
     }
    }
   }
   node=scene_read(0xf778U+node);
  }
  if(hit)break;
 }
 /* Known direct-page writes from $8371-$8480; actor low flag bits above are
  * caller-qualified even when other presentation bits are tainted. */
 scene_write(0x003eU,actor);scene_write(0x0002U,0x008cU);
 scene_write(0x0004U,record);scene_write(0x0006U,0x008cU);
 scene_write(0x0011U,left);scene_write(0x0014U,right);
 scene_write(0x0017U,top);scene_write(0x001aU,bottom);
 scene_write(0x001dU,z);scene_write(0x0020U,high);
 scene_write(0x0023U,xlo);scene_write(0x0026U,xhi);
 scene_write(0x0029U,ylo);scene_write(0x002cU,yhi);
 scene_write(0x002fU,cells[2]);scene_write(0x0032U,cells[0]);
 scene_write(0x0035U,cells[3]);scene_write(0x0038U,cells[1]);
 scene_write(0x003bU,hit);action_collision_result=0U;
 if(hit)action_collision_result=65535U;
 scene_write(0U,action_collision_result);action_collision_supported=1U;
}
