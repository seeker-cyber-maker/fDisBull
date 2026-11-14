/* $80:82BC-$8370 vertical proposal against $81:85FE/$8686 spatial lists.
 * Candidate coordinates/flags are supplied by the actor controller because
 * horizontal changes may not yet have been published to shared WRAM.
 * The caller owns actor position/velocity, rollback and geometry provenance. */
u16 vertical_actor,vertical_x,vertical_y,vertical_z,vertical_flags;
u16 vertical_hit;
u8 vertical_supported,vertical_blocked,vertical_geometry_known,vertical_flags_known;
void shadowrun_snes_vertical_collision(u8 unused) {
 u16 actor,x,y,z,left,right,top,bottom,high,xlo,xhi,ylo,yhi,cells[4];
 u16 i,j,kind,node,n,rec,owner,player,l,t,lo,r,b,hi,delta,hit,last68,addr;
 vertical_supported=0U;actor=vertical_actor;
 if((actor&1U) || actor>=88U || !vertical_geometry_known)return;
 x=vertical_x>>2;y=vertical_y>>2;z=vertical_z>>2;
 left=(x+scene_read(0x421cU+actor))&65535U;
 right=(x+scene_read(0x4274U+actor))&65535U;
 top=(y+scene_read(0x42ccU+actor))&65535U;
 bottom=(y+scene_read(0x4324U+actor))&65535U;
 high=(z+scene_read(0x437cU+actor))&65535U;
 xlo=(left&0x03c0U)>>5;xhi=(right&0x03c0U)>>5;
 ylo=(top&0x03c0U)>>1;yhi=(bottom&0x03c0U)>>1;
 cells[0]=xlo|yhi;cells[1]=xlo|ylo;cells[2]=xhi|ylo;cells[3]=xhi|yhi;
 player=scene_read(0x0cdeU);hit=0U;last68=scene_read(0x0068U);
 for(i=0U;i<4U;i+=1U) {
  for(j=0U;j<i;j+=1U)if(cells[j]==cells[i])break;
  if(j<i)continue;
  for(kind=0U;kind<2U;kind+=1U) {
   if(!kind)node=scene_read(0xde88U+cells[i]);
   else node=scene_read(0xe088U+cells[i]);
   for(n=0U;node<32768U;n+=1U) {
    if(n>=128U || node>0x085eU || (node&1U))return;
    rec=scene_read(0xef18U+node);
    if(rec>0x0c84U || (rec%12U))return;
    l=scene_read(0xe288U+rec);t=scene_read(0xe28aU+rec);
    lo=scene_read(0xe28cU+rec);r=scene_read(0xe28eU+rec);
    b=scene_read(0xe290U+rec);hi=scene_read(0xe292U+rec);
    if(right>=l && r>=left && bottom>=t && b>=top && high>=lo && hi>=z) {
     delta=hi-z;
     if(delta>=hit) {
      addr=0xe214U+(rec>>2);
      owner=(u16)((u16)scene_7f[addr]|((u16)scene_7f[addr+1U]<<8));
      if(!kind) {
       last68=rec;
       if(!owner)hit=delta;
       else {
        if(!vertical_flags_known)return;
        if((vertical_flags&3U)==3U && x>=l && x<r && y>=t && y<b && z>=lo)hit=64U;
       }
      } else if(owner!=actor) {
       if(owner==player) {
        if(!vertical_flags_known)return;
        if((vertical_flags&3U)!=3U)hit=delta;
       } else hit=delta;
      }
     }
    }
    node=scene_read(0xf778U+node);
   }
  }
  if(hit)break;
 }
 /* $82BC constructs these source scratch words before traversing. */
 scene_write(0x003eU,actor);scene_write(0x003bU,hit);scene_write(0x0068U,last68);
 scene_write(0x0011U,left);scene_write(0x0014U,right);
 scene_write(0x0017U,top);scene_write(0x001aU,bottom);
 scene_write(0x001dU,z);scene_write(0x0020U,high);
 scene_write(0x0023U,xlo);scene_write(0x0026U,xhi);
 scene_write(0x0029U,ylo);scene_write(0x002cU,yhi);
 scene_write(0x002fU,cells[2]);scene_write(0x0032U,cells[0]);
 scene_write(0x0035U,cells[3]);scene_write(0x0038U,cells[1]);
 vertical_hit=hit;vertical_blocked=0U;if(hit)vertical_blocked=1U;
 vertical_supported=1U;
}
