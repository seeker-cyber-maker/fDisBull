/* Source $80:B7E8-B82E, one actor's flag merge after actor-stage scanning.
 * The caller must supply the flags at this exact stage and the intermediate
 * $1C90 word produced by the original actor scan. This is not the scan or a
 * complete frame update. */
typedef unsigned int u16;
typedef unsigned char u8;
typedef unsigned long u32;
u8 rom8(u8 region,u32 offset);
u16 shadowrun_snes_flags_in,shadowrun_snes_flags_scratch,shadowrun_snes_flags_out;
void shadowrun_snes_flags_merge(void) {
 u16 low,bits;
 low=shadowrun_snes_flags_scratch&3U;
 if(!low) bits=shadowrun_snes_flags_scratch;
 else {
  bits=shadowrun_snes_flags_scratch&65532U;
  if(low==2U)bits|=512U;
  else if(low==3U)bits|=2048U;
 }
 shadowrun_snes_flags_out=shadowrun_snes_flags_in|bits;
}

/* Bounded flag-only projection of $80:B1DE-B72C. Region 1 is a caller-
 * qualified live 128 KiB WRAM read set. Queue writes and the scratch matrix
 * are excluded from the projection; queue_effect records nonzero tile calls.
 * The caller must supply the source's current sprite pointer, not a guessed
 * animation frame. Sprite geometry and unsupported sign/overflow paths are
 * guarded. The generated cells are local to this projection. */
u16 shadowrun_snes_flag_x,shadowrun_snes_flag_y,shadowrun_snes_flag_z;
u16 shadowrun_snes_flag_depth,shadowrun_snes_flag_camera_x,shadowrun_snes_flag_camera_y;
u16 shadowrun_snes_flag_sprite;
u16 shadowrun_snes_flag_phase,shadowrun_snes_flag_timer,shadowrun_snes_flag_selector;
u16 shadowrun_snes_flag_direction,shadowrun_snes_flag_requested_direction;
u8 shadowrun_snes_flag_animation_status;
u8 shadowrun_snes_flag_status,shadowrun_snes_flag_queue_effect;
u16 shadowrun_snes_flag_cells[48],shadowrun_snes_flag_tiles[48];
u16 shadowrun_snes_flag_read(u32 at) {
 return (u16)(rom8(1,at)|((u16)rom8(1,at+1UL)<<8));
}
void shadowrun_snes_flags_project(void) {
 u16 hsize,wsize,py,px,rows,cols,index,sub,group,row,col,base,ptr,remain;
 u16 a,b,c,value,tile,scratch,iy,ix,yy,xx,hit,queue;
 shadowrun_snes_flag_status=0;
 shadowrun_snes_flag_queue_effect=0;
 if(shadowrun_snes_flag_x>3000U || shadowrun_snes_flag_y>3000U ||
    shadowrun_snes_flag_z>3072U || shadowrun_snes_flag_depth>3072U ||
    shadowrun_snes_flag_camera_x>2048U || shadowrun_snes_flag_camera_y>2048U)return;
 if(shadowrun_snes_flag_sprite<0x1e00U || shadowrun_snes_flag_sprite>0x2100U)return;
 wsize=(u16)rom8(0,884736UL+(u32)shadowrun_snes_flag_sprite)*2U;
 if((wsize!=16U && wsize!=32U && wsize!=36U && wsize!=48U) ||
    rom8(0,884738UL+(u32)shadowrun_snes_flag_sprite)!=33U)return;
 hsize=(u16)rom8(0,884737UL+(u32)shadowrun_snes_flag_sprite)*2U;
 if(hsize!=92U && hsize!=96U)return;
 if(shadowrun_snes_flag_depth+shadowrun_snes_flag_z+hsize>3072U ||
    1536U+shadowrun_snes_flag_y<shadowrun_snes_flag_x+wsize)return;
 py=(3072U-shadowrun_snes_flag_depth-shadowrun_snes_flag_z-hsize)>>2;
 px=(1536U+shadowrun_snes_flag_y-shadowrun_snes_flag_x-wsize)>>2;
 if(py>=2048U || px>=2048U || shadowrun_snes_flag_depth>=32768U)return;
 if(py>=shadowrun_snes_flag_camera_y && py-shadowrun_snes_flag_camera_y>=216U)return;
 if(px>=shadowrun_snes_flag_camera_x && px-shadowrun_snes_flag_camera_x>=248U)return;
 /* $B297-$B2C1 also rejects sprites beyond the negative screen edge. */
 if(shadowrun_snes_flag_camera_y>py+40U || shadowrun_snes_flag_camera_x>px+24U)return;
 rows=2U;if(px&7U)rows+=1U;
 cols=4U;if(py&7U)cols+=1U;
 index=((px&65528U)<<2)|((py&65504U)>>4);
 sub=((py&24U)>>2)*3U;group=(16U-((py&24U)>>1))>>2;
 scratch=4U;
 for(row=0U;row<rows;row+=1U) {
  base=index+row*32U;if(base>3068U)return;
  ptr=shadowrun_snes_flag_read(65536UL+(u32)base);remain=group;
  if(ptr<32768U) {if(ptr>32767U-sub)return;ptr+=sub;}
  for(col=0U;col<cols;col+=1U) {
   if(col && !remain) {base+=2U;if(base>3070U)return;ptr=shadowrun_snes_flag_read(65536UL+(u32)base);remain=4U;}
   value=0U;tile=0U;
   if(ptr<32768U) {
    if(ptr>38400U)return;
    a=shadowrun_snes_flag_read(68608UL+(u32)ptr);
    b=shadowrun_snes_flag_read(68610UL+(u32)ptr);
    c=shadowrun_snes_flag_read(68612UL+(u32)ptr);
    if(a<32768U) {
     if(a<(shadowrun_snes_flag_depth>>2)) {scratch|=1U;tile=shadowrun_snes_flag_read(92608UL+(u32)ptr);}
     else if(b>=32768U) {value=65535U;scratch|=2U;}
     else if(b<(shadowrun_snes_flag_depth>>2)) {value=65535U;tile=shadowrun_snes_flag_read(92610UL+(u32)ptr);}
     else if(c<32768U && c<(shadowrun_snes_flag_depth>>2)) {value=65535U;tile=shadowrun_snes_flag_read(92612UL+(u32)ptr);}
     else {value=65535U;scratch|=2U;}
    }
    if(ptr>32761U)return;
    ptr+=6U;
   }
   shadowrun_snes_flag_cells[row*16U+col]=value;
   shadowrun_snes_flag_tiles[row*16U+col]=tile;
   remain-=1U;
  }
 }
 hit=0U;queue=0U;
 for(ix=0U;ix<2U;ix+=1U) {
  a=0U;
  for(yy=0U;yy<rows;yy+=1U)for(xx=0U;xx<2U+(u16)((py&7U)!=0U);xx+=1U) {
   iy=yy*16U+ix*2U+xx;a|=shadowrun_snes_flag_cells[iy];
  }
  if(a) {
   hit=1U;
   for(yy=0U;yy<rows;yy+=1U)for(xx=0U;xx<2U+(u16)((py&7U)!=0U);xx+=1U) {
    iy=yy*16U+ix*2U+xx;if(shadowrun_snes_flag_tiles[iy])queue=1U;
   }
  }
 }
 if(hit)scratch|=2048U;
 shadowrun_snes_flags_scratch=scratch;
 shadowrun_snes_flags_in &= 62971U;
 shadowrun_snes_flags_merge();
 shadowrun_snes_flag_queue_effect=(u8)queue;
 shadowrun_snes_flag_status=1U;
}

/* Source $A912 action 2 setup for the qualified kind-11 actor, followed by
 * $AA3C direction selection. Caller establishes the scene/action transition. */
void shadowrun_snes_flag_walk_start(void) {
 u16 record,table,dir;
 shadowrun_snes_flag_animation_status=0;
 dir=shadowrun_snes_flag_requested_direction;
 if(dir!=1U && dir!=3U && dir!=5U && dir!=7U)return;
 record=(u16)(rom8(0,395466UL)|((u16)rom8(0,395467UL)<<8));
 if(record!=0x88f8U || rom8(0,395512UL)!=17U || rom8(0,395513UL)!=132U)return;
 table=record+8U;if(table!=0x8900U)return;
 shadowrun_snes_flag_direction=dir;
 shadowrun_snes_flag_selector=(u16)rom8(0,395520UL+(u32)dir);
 shadowrun_snes_flag_timer=1U;
 shadowrun_snes_flag_phase=128U;
 shadowrun_snes_flag_animation_status=1U;
}

/* Action 0 setup and its one source-timed update ($A912, $ABCD-AD52).
 * The captured idle record has increment zero and a one-shot reload; later
 * idle frames do not advance these animation fields. */
void shadowrun_snes_flag_walk_stop(void) {
 u16 dir,record,index,descriptor,count,sprite;
 shadowrun_snes_flag_animation_status=0;
 dir=shadowrun_snes_flag_direction;
 if(dir!=1U && dir!=3U && dir!=5U && dir!=7U)return;
 record=(u16)(rom8(0,395462UL)|((u16)rom8(0,395463UL)<<8));
 if(record!=0x88d8U || rom8(0,395480UL)!=0U || rom8(0,395481UL)!=1U)return;
 index=(u16)rom8(0,395488UL+(u32)dir);
 if(index>22U || (index&1U))return;
 descriptor=(u16)(rom8(0,395488UL+(u32)index)|((u16)rom8(0,395489UL+(u32)index)<<8));
 if(descriptor<0x1d00U || descriptor>0x2100U)return;
 count=(u16)rom8(0,884736UL+(u32)descriptor);if(count!=2U)return;
 sprite=descriptor+1U+count*4U;
 if(sprite<0x1e00U || sprite>0x2100U)return;
 shadowrun_snes_flag_phase=0U;shadowrun_snes_flag_timer=1U;
 shadowrun_snes_flag_selector=index+2U;shadowrun_snes_flag_sprite=sprite;
 shadowrun_snes_flag_animation_status=1U;
}

/* $AA6C direction change and $ABCD-AC58 animation dispatch. Walking only;
 * caller refuses other actions until their source setup is modeled. */
void shadowrun_snes_flag_walk_tick(void) {
 u16 phase,timer,selector,index,descriptor,count,sprite,dir,next,oldbase,newbase;
 shadowrun_snes_flag_animation_status=0;
 dir=shadowrun_snes_flag_direction;next=shadowrun_snes_flag_requested_direction;
 if((dir!=1U && dir!=3U && dir!=5U && dir!=7U) ||
    (next!=1U && next!=3U && next!=5U && next!=7U))return;
 phase=shadowrun_snes_flag_phase;timer=shadowrun_snes_flag_timer;
 selector=shadowrun_snes_flag_selector;sprite=shadowrun_snes_flag_sprite;
 oldbase=(u16)rom8(0,395520UL+(u32)dir);
 newbase=(u16)rom8(0,395520UL+(u32)next);
 if(timer<1U || timer>4U || phase>128U || selector<oldbase || selector>oldbase+8U || (selector&1U))return;
 if(dir!=next) {selector=(selector-oldbase+newbase)&255U;phase=128U;dir=next;}
 phase+=17U;
 if(phase>=128U) {
  phase &=127U;timer-=1U;
  if(!timer) {timer=4U;index=newbase;}else index=selector;
  if(index<newbase || index>newbase+6U || (index&1U))return;
  descriptor=(u16)(rom8(0,395520UL+(u32)index)|((u16)rom8(0,395521UL+(u32)index)<<8));
  if(descriptor<0x1d00U || descriptor>0x2100U)return;
  count=(u16)rom8(0,884736UL+(u32)descriptor);
  if(count!=2U)return;
  sprite=descriptor+1U+count*4U;
  if(sprite<0x1e00U || sprite>0x2100U)return;
  selector=index+2U;
 }
 shadowrun_snes_flag_phase=phase;shadowrun_snes_flag_timer=timer;
 shadowrun_snes_flag_selector=selector;shadowrun_snes_flag_sprite=sprite;
 shadowrun_snes_flag_direction=dir;shadowrun_snes_flag_animation_status=1U;
}

/* $80:ABCD-AC58, AD4E-AD52: captured LEFT walking animation regime.
 * Caller establishes this regime (table $8C:8900, direction index 3,
 * increment $11, reload 4) and stops on a change in that source state.
 * Start with the actual post-frame phase/timer/selector/sprite. */
void shadowrun_snes_flag_animate_left(void) {
 u16 phase,timer,selector,index,descriptor,count,sprite;
 shadowrun_snes_flag_animation_status=0;
 phase=shadowrun_snes_flag_phase;
 timer=shadowrun_snes_flag_timer;
 selector=shadowrun_snes_flag_selector;
 sprite=shadowrun_snes_flag_sprite;
 if(phase>127U || timer<1U || timer>4U || selector<34U || selector>40U ||
    (selector&1U) || (sprite!=0x1f5cU && sprite!=0x1f6aU &&
    sprite!=0x1f78U && sprite!=0x1f86U))return;
 phase+=17U;
 if(phase>=128U) {
  phase &=127U;
  timer-=1U;
  if(!timer) {timer=4U;index=(u16)rom8(0,395523UL);}
  else index=selector;
  if(index<32U || index>38U || (index&1U))return;
  descriptor=(u16)(rom8(0,395520UL+(u32)index)|((u16)rom8(0,395521UL+(u32)index)<<8));
  if(descriptor<0x1f53U || descriptor>0x1f7dU)return;
  count=(u16)rom8(0,884736UL+(u32)descriptor);
  if(count!=2U)return;
  sprite=descriptor+1U+count*4U;
  if(sprite!=0x1f5cU && sprite!=0x1f6aU && sprite!=0x1f78U && sprite!=0x1f86U)return;
  selector=index+2U;
 }
 shadowrun_snes_flag_phase=phase;
 shadowrun_snes_flag_timer=timer;
 shadowrun_snes_flag_selector=selector;
 shadowrun_snes_flag_sprite=sprite;
 shadowrun_snes_flag_animation_status=1U;
}
