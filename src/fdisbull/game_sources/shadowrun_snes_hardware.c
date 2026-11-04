/* Explicit environmental input for $80:C530 and $80:C4EF. The supplied
 * NMI low/high bytes are separate reads: an NMI may occur between them.
 * Recorded mode consumes only raw external readings in caller/task order.
 * Seeded mode is an adapted reproducible input policy, not SNES timing.
 * A refused whole update must restore this queue, ordinal, PRNG and WRAM. */
u8 hardware_mode,hardware_status;
u16 hardware_input_count,hardware_input_index;
u32 hardware_ordinal,hardware_input_ordinal,hardware_prng_state=1UL;
u16 hardware_callers[128],hardware_contexts[128];
u8 hardware_nmi_lows[128],hardware_nmi_highs[128];
u8 hardware_beam_hs[128],hardware_beam_vs[128];
u16 hardware_result,hardware_bound;
u16 hardware_last_caller,hardware_last_context;
void opening_hardware_begin(void) {
 hardware_status=0U;
 if(hardware_mode>2U || hardware_input_count>128U || hardware_input_index)return;
 if(hardware_mode==1U) {
  if(hardware_input_ordinal!=hardware_ordinal || task_rng_tainted)return;
 } else if(hardware_input_count)return;
 if(hardware_mode==2U && (!hardware_prng_state || task_rng_tainted))return;
 hardware_status=1U;
}
void opening_hardware_finish(void) {
 hardware_status=0U;
 if(hardware_mode==1U && hardware_input_index!=hardware_input_count)return;
 hardware_status=1U;
}
u8 opening_hardware_seeded_byte(void) {
 u32 state;
 state=hardware_prng_state;
 state^=state<<13;state^=state>>17;state^=state<<5;
 hardware_prng_state=state;return (u8)state;
}
void opening_hardware_rng(u16 caller,u16 context) {
 u16 index;
 hardware_status=0U;
 if(!hardware_mode || hardware_mode>2U || task_rng_tainted ||
    hardware_ordinal==4294967295UL)return;
 if(caller<1U || caller>3U)return;
 if(caller<3U) {if(context!=65535U)return;}
 else if((context&1U) || context>=96U)return;
 if(hardware_mode==1U) {
  index=hardware_input_index;
  if(index>=hardware_input_count || index>=128U ||
     hardware_input_ordinal+(u32)index!=hardware_ordinal ||
     hardware_callers[index]!=caller || hardware_contexts[index]!=context)return;
  rng_nmi_low=hardware_nmi_lows[index];rng_nmi_high=hardware_nmi_highs[index];
  rng_beam_h=hardware_beam_hs[index];rng_beam_v=hardware_beam_vs[index];
  hardware_input_index+=1U;
 } else {
  if(!hardware_prng_state)return;
  rng_nmi_low=opening_hardware_seeded_byte();rng_nmi_high=opening_hardware_seeded_byte();
  rng_beam_h=opening_hardware_seeded_byte();rng_beam_v=opening_hardware_seeded_byte();
 }
 rng_seed=task_shared[0x1d04U];shadowrun_snes_rng_transform(0U);
 if(!rng_supported)return;
 hardware_result=rng_result;task_shared[0x1d04U]=rng_next_seed;
 scene_write(0U,rng_result);
 hardware_last_caller=caller;hardware_last_context=context;
 hardware_ordinal+=1UL;hardware_status=1U;
}
/* $C4EF rejects masked words until the result is below the requested bound.
 * Its mask includes the bound's highest set bit, even for powers of two. */
void opening_hardware_bounded(u16 context) {
 u16 mask,n,bound;
 hardware_status=0U;bound=hardware_bound;
 if(!bound) {hardware_result=scene_read(0U);hardware_status=1U;return;}
 mask=1U;
 for(n=0U;n<15U;n+=1U) {if(mask>=bound)break;mask=(mask<<1)|1U;}
 scene_write(2U,bound);scene_write(4U,mask);
 for(n=0U;n<128U;n+=1U) {
  opening_hardware_rng(2U,context);if(!hardware_status)return;
  hardware_result&=mask;
  if(hardware_result<bound) {
   scene_write(0U,hardware_result);hardware_status=1U;return;
  }
 }
 hardware_status=0U;
}
