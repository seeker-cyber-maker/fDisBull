/* Source $80:FE9B-FE86 and $81:AEC0, bounded text-pointer table reads.
 * The ROM pointer table, compressed bitstream and Huffman tree remain in the
 * caller's verified ROM. The output is private runtime state; this does not
 * execute FB03 window layout or claim a character mapping beyond emitted bytes. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 rom8(u8 region,u32 offset);
u8 shadowrun_snes_text_output[256],shadowrun_snes_text_status;
u16 shadowrun_snes_text_id,shadowrun_snes_text_length;
u16 shadowrun_snes_text_encoded_pointer;
u16 shadowrun_snes_text_pointer,shadowrun_snes_text_bank;
u16 shadowrun_snes_text_bitcount,shadowrun_snes_text_bitword;
u32 shadowrun_snes_text_offset;
u8 shadowrun_snes_text_failed;
u16 shadowrun_snes_text_word(u32 at) {
 return (u16)((u16)rom8(0U,at)|((u16)rom8(0U,at+1UL)<<8));
}
u16 shadowrun_snes_text_bit(void) {
 u16 value;
 shadowrun_snes_text_bitcount-=1U;
 if(shadowrun_snes_text_bitcount&32768U) {
  if(shadowrun_snes_text_pointer>65533U) {shadowrun_snes_text_failed=1U;return 0U;}
  shadowrun_snes_text_bitcount=15U;
  shadowrun_snes_text_offset=((u32)(shadowrun_snes_text_bank&127U)<<15)+
                             (u32)(shadowrun_snes_text_pointer&32767U);
  shadowrun_snes_text_bitword=((u16)rom8(0U,shadowrun_snes_text_offset)<<8)|
                              (u16)rom8(0U,shadowrun_snes_text_offset+1UL);
  shadowrun_snes_text_pointer+=2U;
 }
 value=shadowrun_snes_text_bitword>>15;shadowrun_snes_text_bitword<<=1;return value;
}
/* $FE33 accepts an encoded compressed-text pointer directly. It is not a
 * CPU address or an index into the $D980 text-ID table. */
void shadowrun_snes_text_decode_pointer(u8 unused) {
 u16 ptr,index,leaf,depth,symbol,high,low;
 shadowrun_snes_text_status=0U;shadowrun_snes_text_failed=0U;
 shadowrun_snes_text_length=0U;
 ptr=shadowrun_snes_text_encoded_pointer;
 shadowrun_snes_text_bank=157U;if(ptr&32768U)shadowrun_snes_text_bank=158U;
 shadowrun_snes_text_pointer=ptr|32768U;
 shadowrun_snes_text_bitcount=0U;shadowrun_snes_text_bitword=0U;
 for(symbol=0U;symbol<256U;symbol+=1U) {
  index=0U;leaf=0U;
  for(depth=0U;depth<32U;depth+=1U) {
   index+=shadowrun_snes_text_bit()<<1;
   if(shadowrun_snes_text_failed || index>32766U)return;
   leaf=shadowrun_snes_text_word(0xe8000UL+(u32)index);
   if(leaf&32768U)break;
   index=leaf;
  }
  if(depth==32U)return;
  high=(leaf>>8)&127U;low=leaf&127U;
  if(high==10U) {shadowrun_snes_text_output[shadowrun_snes_text_length]=0U;shadowrun_snes_text_status=1U;return;}
  if(shadowrun_snes_text_length>=255U)return;
  shadowrun_snes_text_output[shadowrun_snes_text_length]=(u8)high;shadowrun_snes_text_length+=1U;
  if(low==10U) {shadowrun_snes_text_output[shadowrun_snes_text_length]=0U;shadowrun_snes_text_status=1U;return;}
  if(low) {
   if(shadowrun_snes_text_length>=255U)return;
   shadowrun_snes_text_output[shadowrun_snes_text_length]=(u8)low;shadowrun_snes_text_length+=1U;
  }
 }
}

void shadowrun_snes_text_decode(u8 unused) {
 shadowrun_snes_text_status=0U;shadowrun_snes_text_failed=0U;
 shadowrun_snes_text_length=0U;
 /* Do not let $D980 + 2*ID wrap out of bank $80. */
 if(shadowrun_snes_text_id>4927U)return;
 shadowrun_snes_text_encoded_pointer=shadowrun_snes_text_word(
     0x5980UL+((u32)shadowrun_snes_text_id<<1));
 shadowrun_snes_text_decode_pointer(0U);
}

/* $FAA7 uses the source font advances, including controller-icon glyphs.
 * The FB03 pipe/style transformation is a separate unsupported producer. */
u16 shadowrun_snes_text_measured_pixels;
u8 shadowrun_snes_text_measure_status;
void shadowrun_snes_text_measure(u8 unused) {
 u16 i,glyph,total,next;
 shadowrun_snes_text_measure_status=0U;shadowrun_snes_text_measured_pixels=0U;
 if(shadowrun_snes_text_status!=1U || shadowrun_snes_text_length>=256U)return;
 total=0U;
 for(i=0U;i<shadowrun_snes_text_length;i+=1U) {
  glyph=(u16)shadowrun_snes_text_output[i];
  if(!glyph || glyph>127U || glyph==124U)return;
  next=total+(u16)rom8(0U,0xabc8UL+(u32)glyph);
  if(next<total)return;total=next;
 }
 shadowrun_snes_text_measured_pixels=total;shadowrun_snes_text_measure_status=1U;
}

/* Bounded logical cursor projection of $80:FB03-$FD41 and $81:AD76-AE5B.
 * This is the source plain-ASCII, zero text-style, fresh-window branch.
 * Rasterization, DMA, style controls and scrolling/eviction are not modeled. */
u16 shadowrun_snes_text_layout_base,shadowrun_snes_text_layout_width;
u16 shadowrun_snes_text_layout_height,shadowrun_snes_text_layout_style;
u16 shadowrun_snes_text_layout_cursor_in,shadowrun_snes_text_layout_subpixel_in;
u16 shadowrun_snes_text_layout_cursor,shadowrun_snes_text_layout_subpixel;
u16 shadowrun_snes_text_layout_line,shadowrun_snes_text_layout_pixels;
u8 shadowrun_snes_text_layout_status;
u8 shadowrun_snes_text_layout_icon_glyphs;
void shadowrun_snes_text_layout(u8 unused) {
 u16 width,height,row_pixels,line,column,pos,end,word_width,glyph,i,result;
 shadowrun_snes_text_layout_status=0U;
 width=shadowrun_snes_text_layout_width;height=shadowrun_snes_text_layout_height;
 if(shadowrun_snes_text_status!=1U || shadowrun_snes_text_layout_style ||
    shadowrun_snes_text_layout_cursor_in!=shadowrun_snes_text_layout_base ||
    shadowrun_snes_text_layout_subpixel_in ||
    width<3U || width>30U || height<3U || height>26U ||
    !shadowrun_snes_text_length || shadowrun_snes_text_length>=256U)return;
 width-=2U;row_pixels=width<<3;line=0U;column=0U;pos=0U;
 /* The selector erases its marker using one source space glyph. */
 if(shadowrun_snes_text_layout_icon_glyphs && shadowrun_snes_text_length==1U &&
    shadowrun_snes_text_output[0]==32U) {
  column=(u16)rom8(0U,0xabe8UL);
  if(column>=row_pixels)return;
  shadowrun_snes_text_layout_cursor=shadowrun_snes_text_layout_base+((column+7U)>>3);
  shadowrun_snes_text_layout_subpixel=column&7U;shadowrun_snes_text_layout_line=0U;
  shadowrun_snes_text_layout_pixels=column;shadowrun_snes_text_layout_status=1U;return;
 }
 for(i=0U;i<256U;i+=1U) {
  if(pos==shadowrun_snes_text_length)break;
  glyph=shadowrun_snes_text_output[pos];
  if(!glyph || glyph==32U || glyph>127U || glyph==124U ||
     (!shadowrun_snes_text_layout_icon_glyphs && (glyph<32U || glyph==127U)))return;
  end=pos;word_width=0U;
  for(;end<shadowrun_snes_text_length;end+=1U) {
   glyph=shadowrun_snes_text_output[end];
   if(glyph==32U)break;
   if(!glyph || glyph>127U || glyph==124U ||
      (!shadowrun_snes_text_layout_icon_glyphs && (glyph<32U || glyph==127U)))return;
   word_width+=(u16)rom8(0U,0xabc8UL+(u32)glyph);
  }
  if(!word_width || word_width>=row_pixels)return;
  if(word_width>=row_pixels-column) {
   line+=1U;column=0U;
   /* $AE09 scrolls/reuses a row beyond this range; keep that edge explicit. */
   if(line>height-3U)return;
  }
  column+=word_width;pos=end;
  if(pos<shadowrun_snes_text_length) {
   if(pos+1U>=shadowrun_snes_text_length || shadowrun_snes_text_output[pos+1U]==32U)return;
   glyph=(u16)rom8(0U,0xabe8UL); /* font advance for ASCII space */
   if(column+glyph>row_pixels)return;
   column+=glyph;pos+=1U;
  }
 }
 if(pos!=shadowrun_snes_text_length)return;
 /* $AE84/$FD31-FD3B advances past a partially occupied final tile; $20E0
  * retains the subpixel count independently. */
 result=shadowrun_snes_text_layout_base+line*width+((column+7U)>>3);
 if(result<shadowrun_snes_text_layout_base)return;
 shadowrun_snes_text_layout_cursor=result;
 shadowrun_snes_text_layout_subpixel=column&7U;
 shadowrun_snes_text_layout_line=line;
 shadowrun_snes_text_layout_pixels=column;
 shadowrun_snes_text_layout_status=1U;
}
