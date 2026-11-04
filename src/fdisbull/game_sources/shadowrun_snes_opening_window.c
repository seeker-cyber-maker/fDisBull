/* Bounded $80:F92D/$FE8B/$FEDE window state. task_shared and scene_read/write
 * are authoritative low WRAM. The caller must roll back a refused transaction.
 * Text decoding and FB03 presentation completion are separate producer edges. */
u16 opening_window_arg0,opening_window_arg1,opening_window_arg2,opening_window_arg3;
u16 opening_window_arg4,opening_window_arg5,opening_window_arg6;
u16 opening_window_slot,opening_window_area,opening_window_priority;
u16 opening_window_layout_cursor,opening_window_layout_subpixel;
u8 opening_window_status,opening_window_phase;
u8 opening_window_text_complete,opening_window_present_complete;
u8 opening_window_rng_tainted,opening_window_audio_tainted;
u8 opening_window_scratch_tainted,opening_window_display_tainted;
u16 opening_window_ambient_attempts,opening_window_close_events;
/* Source 81:AB7D-ABC3 and its 81:AA58/A99D display setup, observed on the
 * selected new-game route. Graphics buffers remain an adapted projection. */
void opening_window_reset(void) {
 u16 i;
 opening_window_status=0U;
 for(i=0U;i<32U;i+=2U)scene_write(0x0242U+i,0U);
 for(i=0U;i<8U;i+=2U)scene_write(0x0232U+i,65535U);
 scene_write(0x0210U,0x0084U);scene_write(0x0212U,0U);
 scene_write(0x0214U,0U);scene_write(0x0216U,0U);
 scene_write(0x0218U,0U);scene_write(0x021cU,0U);
 scene_write(0x021eU,0U);scene_write(0x0220U,65534U);
 scene_write(0x022eU,0x2027U);scene_write(0x0230U,0U);
 opening_window_phase=0U;opening_window_text_complete=0U;
 opening_window_present_complete=0U;opening_window_display_tainted=1U;
 opening_window_status=1U;
}
void opening_window_begin(void) {
 u16 slot,x,y,w,h,style,area,base,next;
 opening_window_status=0U;
 if(opening_window_phase==1U || opening_window_phase>2U)return;
 slot=scene_read(0x0220U)+2U;
 if((slot&1U) || slot>=32U)return;
 x=opening_window_arg0;y=opening_window_arg1;
 w=opening_window_arg2;h=opening_window_arg3;style=opening_window_arg4;
 /* Reject unqualified signed/degenerate dimensions and allocator wrap. */
 if(x>=32768U || y>=32768U || w<2U || w>30U || h<2U || h>26U)return;
 if(!x)x=1U;else if(x>31U-w)x=31U-w;
 if(!y)y=1U;else if(y>27U-h)y=27U-h;
 area=(w-2U)*(h-2U);base=scene_read(0x022eU);next=base+area;
 if(next<base)return;
 if(next>=0x2400U) {base=0x2027U;next=base+area;}
 if(next>=0x2400U)return;
 if(style==1024U)scene_write(0x021eU,30U);
 scene_write(0x0220U,slot);
 scene_write(0x2000U+slot,((y<<5)+x)<<1);
 scene_write(0x2020U+slot,w);scene_write(0x2120U+slot,(w-2U)<<3);
 scene_write(0x2040U+slot,h);scene_write(0x2180U+slot,style);
 scene_write(0x20e0U+slot,0U);scene_write(0x2100U+slot,0U);
 scene_write(0x2140U+slot,0U);scene_write(0x2160U+slot,0U);
 scene_write(0x0242U+slot,scene_read(0x0242U+slot)-1U);
 scene_write(0x20a0U+slot,area);scene_write(0x022eU,next);
 scene_write(0x2060U+slot,base);scene_write(0x2080U+slot,base);
 scene_write(0x20c0U+slot,base);
 opening_window_slot=slot;opening_window_area=area;
 opening_window_text_complete=0U;opening_window_present_complete=0U;
 opening_window_phase=1U;opening_window_status=1U;
}
void opening_window_finish(void) {
 u16 i,slot,base;
 opening_window_status=0U;
 /* These attest separately implemented, source-qualified producers; do not
  * set them merely to acknowledge a pending callback. */
 if(opening_window_phase!=1U || !opening_window_text_complete ||
    !opening_window_present_complete)return;
 base=scene_read(0x2060U+opening_window_slot);
 if(opening_window_layout_cursor<base ||
    opening_window_layout_cursor>base+opening_window_area ||
    opening_window_layout_subpixel>7U)return;
 slot=65535U;
 for(i=8U;i>0U;i-=2U)if(scene_read(0x0232U+i-2U)&32768U) {slot=i-2U;break;}
 /* Full priority queue needs the original eviction/close path. */
 if(slot==65535U)return;
 scene_write(0x20c0U+opening_window_slot,opening_window_layout_cursor);
 scene_write(0x20e0U+opening_window_slot,opening_window_layout_subpixel);
 scene_write(0x023aU+slot,opening_window_arg6);
 scene_write(0x0232U+slot,opening_window_slot);
 opening_window_display_tainted=1U;
 opening_window_priority=slot;opening_window_phase=2U;opening_window_status=1U;
}
void opening_window_tick(void) {
 u16 i,j,value,slot,head,cursor;
 opening_window_status=0U;
 /* Validate every expiry before touching any of the priority records. */
 for(i=0U;i<8U;i+=2U) {
  if(!(scene_read(0x0232U+i)&32768U)) {
   value=scene_read(0x023aU+i);
   slot=scene_read(0x0232U+i);head=scene_read(0x0220U);
   if(value==1U && ((slot&1U) || slot>=32U || (head&1U) || head>=32U || slot>head))return;
  }
 }
 /* FEDE scans 6,4,2,0; FA08 releases logical window ownership. */
 for(i=8U;i>0U;i-=2U) {
  if(!(scene_read(0x0232U+i-2U)&32768U)) {
   value=scene_read(0x023aU+i-2U)-1U;
   scene_write(0x023aU+i-2U,value);
   if(!value) {
    slot=scene_read(0x0232U+i-2U);head=scene_read(0x0220U);
    scene_write(0x0242U+slot,0U);
    if(slot==head) {
     cursor=slot;
     for(j=0U;j<16U;j+=1U) {
      if(!cursor || scene_read(0x0242U+cursor-2U))break;
      cursor-=2U;
     }
     scene_write(0x022eU,scene_read(0x2060U+cursor));
     scene_write(0x0220U,cursor-2U);
    }
    scene_write(0x0232U+i-2U,65535U);
    opening_window_close_events+=1U;opening_window_display_tainted=1U;
   }
  }
 }
 /* C530's beam-derived result and the conditional sound request are unknown;
  * keep their latches untouched and require the owner to guard later reads. */
 value=scene_read(0x021eU);
 if(value) {
  scene_write(0x021eU,value-1U);
  opening_window_ambient_attempts+=1U;
  opening_window_rng_tainted=1U;opening_window_audio_tainted=1U;
  opening_window_scratch_tainted=1U;
 }
 opening_window_status=1U;
}
