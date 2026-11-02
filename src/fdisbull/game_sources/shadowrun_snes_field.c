/* SNES captured morgue actor, source $80:DE91 and $80:AAB3–AB73.
 * Region 0 is the caller's verified LoROM; region 1 is the caller's captured
 * WRAM collision read set. Unsupported collision side effects fail closed. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 rom8(u8 region,u32 offset);
u16 shadowrun_snes_player_x,shadowrun_snes_player_y,shadowrun_snes_player_z;
u16 shadowrun_snes_velocity_x,shadowrun_snes_velocity_y,shadowrun_snes_flags;
u16 shadowrun_snes_rotation,shadowrun_snes_left,shadowrun_snes_right;
u16 shadowrun_snes_top,shadowrun_snes_bottom,shadowrun_snes_height;
u8 shadowrun_snes_frame_status,shadowrun_snes_collision_supported;
u16 shadowrun_snes_read16(u8 region,u32 at) {
 return (u16)((u16)rom8(region,at)|((u16)rom8(region,at+1UL)<<8));
}
u16 shadowrun_snes_collision(u16 x,u16 y,u8 axis) {
 u16 lx,rx,ty,by,z,high,xlo,xhi,ylo,yhi,cells[2];
 u16 cell,kind,node,record,left,top,zlo,right,bottom,zhi,owner,hit,n,i,k;
 shadowrun_snes_collision_supported=0;hit=0;z=shadowrun_snes_player_z>>2;
 high=z+shadowrun_snes_height;lx=(x>>2)+shadowrun_snes_left;rx=(x>>2)+shadowrun_snes_right;
 ty=(y>>2)+shadowrun_snes_top;by=(y>>2)+shadowrun_snes_bottom;
 xlo=(lx&960U)>>5;xhi=(rx&960U)>>5;ylo=(ty&960U)>>1;yhi=(by&960U)>>1;
 if (axis==0U) {cells[0]=xlo|yhi;cells[1]=xlo|ylo;}
 else if(axis==1U) {cells[0]=xhi|yhi;cells[1]=xlo|yhi;}
 else if(axis==2U) {cells[0]=xhi|yhi;cells[1]=xhi|ylo;}
 else {cells[0]=xhi|ylo;cells[1]=xlo|ylo;}
 for(i=0;i<2U;i+=1U) {
  cell=cells[i];if(i && cells[0]==cell)continue;
  for(kind=0;kind<2U;kind+=1U) {
   if(!kind)node=shadowrun_snes_read16(1,0xde88UL+(u32)cell);
   else node=shadowrun_snes_read16(1,0xe088UL+(u32)cell);
   for(n=0;node<32768U;n+=1U) {
    if(n>=128U || node>0x0860U)return 0;
    record=shadowrun_snes_read16(1,0xef18UL+(u32)node);
    if(record>0x0c84U || (u32)(record>>2)+0x1e215UL>=131072UL)return 0;
    left=shadowrun_snes_read16(1,0xe288UL+(u32)record);
    top=shadowrun_snes_read16(1,0xe28aUL+(u32)record);
    zlo=shadowrun_snes_read16(1,0xe28cUL+(u32)record);
    right=shadowrun_snes_read16(1,0xe28eUL+(u32)record);
    bottom=shadowrun_snes_read16(1,0xe290UL+(u32)record);
    zhi=shadowrun_snes_read16(1,0xe292UL+(u32)record);
    if(rx>=left && right>=lx && by>=top && bottom>=ty && high>=zlo && zhi>=z && zhi-z>=hit) {
     owner=shadowrun_snes_read16(1,0x1e214UL+(u32)(record>>2));
     if(!kind) {
      if(!owner)hit=zhi-z;
      else if((shadowrun_snes_flags&3U)==3U && (x>>2)>=left && (x>>2)<right &&
              (y>>2)>=top && (y>>2)<bottom && z>=zlo) hit=64U;
     } else if(owner!=0x42U) {
      /* The source's other live-actor special branch has not been qualified. */
      if(owner==shadowrun_snes_read16(1,0x0cdeUL) && (shadowrun_snes_flags&3U)==3U) { }
      else hit=zhi-z;
     }
    }
    node=shadowrun_snes_read16(1,0xf778UL+(u32)node);
   }
  }
 }
 shadowrun_snes_collision_supported=1;return hit;
}
void shadowrun_snes_frame(u8 pad) {
 u16 dir,idx,vx,vy,x,y,z,flags,col,joy;
 shadowrun_snes_frame_status=2;
 if(pad==8U)joy=1U;else if(pad==4U)joy=2U;else if(pad==2U)joy=4U;else if(pad==1U)joy=8U;
 else if(pad==0U)joy=0U;else return;
 /* Source joy nibble lookup $DF15 and rotation $70:1FFD. */
 dir=shadowrun_snes_read16(0,0x5f15UL+(u32)(joy<<1));
 if(dir<16U)dir=(dir-shadowrun_snes_rotation-shadowrun_snes_rotation)&14U;
 idx=dir; if(idx>16U || (idx&1U))return;
 vx=shadowrun_snes_read16(0,0x5ef1UL+(u32)idx);
 vy=shadowrun_snes_read16(0,0x5f03UL+(u32)idx);
 x=shadowrun_snes_player_x;y=shadowrun_snes_player_y;z=shadowrun_snes_player_z;
 flags=shadowrun_snes_flags&65527U;
 if(!(flags&64U) || (vx!=0U && vx!=65533U && vx!=3U) || (vy!=0U && vy!=65533U && vy!=3U) || x<3U || x>65532U || y<3U || y>65532U)return;
 if(vx) {x+=vx;if(vx&32768U)col=shadowrun_snes_collision(x,y,0U);else col=shadowrun_snes_collision(x,y,2U);if(!shadowrun_snes_collision_supported)return;
 if(col) {if(col<5U)return;x-=vx;flags|=8U;}}
 if(vy) {y+=vy;if(vy&32768U)col=shadowrun_snes_collision(x,y,3U);else col=shadowrun_snes_collision(x,y,1U);if(!shadowrun_snes_collision_supported)return;
 if(col) {if(col<5U)return;y-=vy;flags|=8U;}}
 /* Captured source comparison domain; wider scene dynamics remain unknown. */
 if(x<1356U || x>1581U || y<1795U || y>2023U)return;
 shadowrun_snes_player_x=x;shadowrun_snes_player_y=y;shadowrun_snes_player_z=z;
 shadowrun_snes_velocity_x=vx;shadowrun_snes_velocity_y=vy;shadowrun_snes_flags=flags;
 shadowrun_snes_frame_status=1;
}
