/* Pure arithmetic of $80:C530-$C55B. The caller supplies the source NMI
 * counter bytes at their separate reads and the actual latched $213C/$213D
 * read bytes after a $2137 latch. An NMI can occur between counter reads.
 * This fragment never obtains, guesses or publishes hardware inputs and is
 * connected to the opening VM only through the explicit hardware-input
 * owner. ROM region 0 is caller-owned. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 rom8(u8 region,u32 offset);
u8 rng_seed,rng_nmi_low,rng_nmi_high,rng_beam_h,rng_beam_v,rng_next_seed,rng_supported;
u16 rng_result;
void shadowrun_snes_rng_transform(u8 unused) {
 u8 low,index,high,next;
 rng_supported=0U;
 low=(u8)(rom8(0U,0x455dUL+(u32)rng_seed)^rng_nmi_low);
 index=(u8)(low^rng_beam_h);
 high=(u8)(rom8(0U,0x455dUL+(u32)index)^rng_nmi_high);
 next=(u8)(high^rng_beam_v);
 if(next==rng_seed)next+=1U;
 rng_result=(u16)low|((u16)high<<8);rng_next_seed=next;rng_supported=1U;
}
