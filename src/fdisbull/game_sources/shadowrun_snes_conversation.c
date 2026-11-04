/* Bounded $80:92EF conversation coroutine. The adapter must execute each
 * typed source service and reply with the matching request ID. Status 0
 * refuses, 1 requests a service, 2 completes. A refusal requires rollback.
 * Text and keyword selection use the independently authored $9123 and $A654
 * helpers. No original frames, future snapshots or hardcoded responses feed it. */
u16 conversation_actor,conversation_tag,conversation_record;
u16 conversation_window_text,conversation_window_menu,conversation_window_keyword;
u16 conversation_request,conversation_reply_request,conversation_value;
u16 conversation_arg0,conversation_arg1,conversation_arg2,conversation_arg3,conversation_arg4;
u16 conversation_selector,conversation_text,conversation_script,conversation_keyword_count;
u16 conversation_original_music;
u8 conversation_status,conversation_reply_success,conversation_phase;
u8 conversation_text_present,conversation_text_script,conversation_after_text;
u8 conversation_music_restore,conversation_keyword_cancelled;
u8 conversation_graphics_tainted,conversation_scratch_tainted;

u16 conversation_rom16(u32 at) {
 return (u16)((u16)rom8(0U,at)|((u16)rom8(0U,at+1UL)<<8));
}
void conversation_emit(u16 request,u8 phase) {
 conversation_request=request;conversation_phase=phase;conversation_status=1U;
 conversation_reply_request=0U;conversation_reply_success=0U;
}
void conversation_open(u16 x,u16 y,u16 w,u16 h,u16 style,u8 phase) {
 conversation_arg0=x;conversation_arg1=y;conversation_arg2=w;
 conversation_arg3=h;conversation_arg4=style;conversation_emit(5U,phase);
}
void conversation_main_menu(void) {
 conversation_arg0=conversation_window_menu;conversation_arg1=3U;
 conversation_arg2=2U;conversation_arg3=4U;conversation_arg4=0U;
 conversation_emit(13U,14U);
}
void conversation_after_response(void);
void conversation_exit(void) {conversation_emit(15U,20U);}
void conversation_text_request(void) {
 scene_write(0x001dU,conversation_selector);
 conversation_arg0=conversation_window_text;conversation_emit(16U,24U);
}
void conversation_text_decode(void) {
 dialogue_record=conversation_record;dialogue_selector=conversation_selector;
 dialogue_no_fallback=1U;
 shadowrun_snes_dialogue_entry(0U);
 dialogue_no_fallback=0U;
 if(!dialogue_status) {conversation_status=0U;return;}
 if(dialogue_fallback)scene_write(0x001dU,65533U);
 if(dialogue_skip_known)scene_write(0x0023U,(u16)dialogue_skip_length);
 if(dialogue_added_count) {task_shared[0x001dU]=dialogue_last_keyword;task_shared[0x0020U]=0U;}
 conversation_text_present=0U;conversation_text_script=0U;
 if(dialogue_status==1U) {
  conversation_text_present=1U;conversation_text=dialogue_text;
  conversation_text_script=dialogue_has_script;conversation_script=dialogue_script;
 }
 if(!conversation_text_present) {
  if(conversation_selector!=65533U) {
   conversation_selector=65533U;conversation_text_request();return;
  }
  conversation_after_response();return;
 }
 conversation_arg0=conversation_window_text;conversation_arg1=conversation_text;
 conversation_arg2=conversation_text_present;conversation_emit(10U,11U);
}
void conversation_after_response(void) {
 if(!conversation_after_text) {
  conversation_arg0=61U;conversation_emit(12U,13U);return;
 }
 if(scene_read(0x1d7fU)) {conversation_exit();return;}
 conversation_main_menu();
}
void shadowrun_snes_conversation_begin(u8 unused) {
 u32 table;u16 ptr;
 conversation_status=0U;conversation_music_restore=0U;
 if((conversation_actor&1U) || conversation_actor>=88U || conversation_tag>=256U)return;
 table=0x147aUL+((u32)conversation_tag<<1);
 ptr=conversation_rom16(table);
 if(ptr<0x8000U || ptr>0xfffbU)return;
 conversation_record=ptr;conversation_emit(1U,1U);
}
void shadowrun_snes_conversation_reply(u8 unused) {
 u16 req,phase,meta,music,i,key,ptr,count,held,old;
 u32 at;
 if(conversation_status!=1U || !conversation_reply_success ||
    conversation_reply_request!=conversation_request) {conversation_status=0U;return;}
 req=conversation_request;phase=conversation_phase;
 conversation_reply_success=0U;conversation_reply_request=0U;
 if(phase==1U && req==1U) {
  scene_write(0x1d7fU,0U);scene_write(0x0026U,conversation_actor);
  conversation_emit(2U,2U);return;
 }
 if(phase==2U && req==2U) {
  scene_write(0x0011U,conversation_record);task_shared[0x0013U]=0x8dU;
  conversation_emit(3U,3U);return;
 }
 if(phase==3U && req==3U) {
  at=0x68000UL+(u32)(conversation_record&0x7fffU);
  meta=(u16)rom8(0U,at+3UL);scene_write(0x01d6U,meta);
  meta=scene_read(0x01d6U)&127U;
  if(meta && (scene_read(0x1ff2U)&1U)) {
   music=conversation_rom16(0x146bUL+((u32)meta<<1));
   conversation_arg0=music;
   if(task_audio_tainted) {conversation_music_restore=2U;conversation_arg1=2U;conversation_emit(4U,4U);return;}
   old=scene_read(0x1cfaU);
   if(music!=old) {conversation_original_music=old;conversation_music_restore=1U;
    conversation_arg1=1U;conversation_emit(4U,4U);return;}
  }
  conversation_open(1U,1U,30U,13U,0U,5U);return;
 }
 if(phase==4U && req==4U) {conversation_open(1U,1U,30U,13U,0U,5U);return;}
 if(phase==5U && req==5U) {
  if((conversation_value&1U) || conversation_value>=32U) {conversation_status=0U;return;}
  conversation_window_text=conversation_value;scene_write(0x0014U,conversation_value);
  /* $FA5C: source window shift writes, before the display service. */
  scene_write(0U,conversation_value);scene_write(2U,0x0054U);scene_write(4U,0xfff8U);
  scene_write(0x2100U+conversation_value,0x0054U);
  scene_write(0x2120U+conversation_value,(u16)(scene_read(0x2020U+conversation_value)-10U));
  conversation_arg0=conversation_value;conversation_arg1=0x0054U;conversation_arg2=0xfff8U;
  conversation_emit(6U,6U);return;
 }
 if(phase==6U && req==6U) {conversation_open(1U,14U,30U,13U,0U,7U);return;}
 if(phase==7U && req==5U) {
  if((conversation_value&1U) || conversation_value>=32U || conversation_value==conversation_window_text)
   {conversation_status=0U;return;}
  conversation_window_menu=conversation_value;scene_write(0x0017U,conversation_value);
  scene_write(0x17f0U,0U);conversation_arg0=0x004bU;
  if(task_shared[0x3c17U])conversation_arg0=0x004cU;
  ptr=conversation_rom16(0x147aUL+((u32)conversation_arg0<<1));
  if(ptr<0x8000U || ptr>0xfffcU) {conversation_status=0U;return;}
  conversation_arg1=ptr;conversation_graphics_tainted=1U;conversation_scratch_tainted=1U;
  conversation_emit(7U,8U);return;
 }
 if(phase==8U && req==7U) {
  /* $9022 updates sprite staging after the first portrait transfer. */
  scene_write(0x0142U,0x0091U);
  for(i=1U;i<510U;i+=4U)task_shared[0x3ce4U+i]=0xf0U;
  for(i=0U;i<32U;i+=2U)scene_write(0x3ee4U+i,0U);
  scene_write(0x3ce8U,0x83a6U);scene_write(0x3ceaU,0x3200U);
  conversation_arg0=conversation_record;conversation_arg1=conversation_actor;
  conversation_emit(8U,9U);return;
 }
 if(phase==9U && req==8U) {
  /* $905E and $8F3A: known staging words; NMI/HDMA delivery is tainted. */
  scene_write(0x0142U,0x00a1U);scene_write(0x3cecU,0x1a1aU);
  meta=0x3480U;if(scene_read(0x01d6U)&128U)meta|=0x4000U;
  scene_write(0x3ceeU,meta);scene_write(0x3ee4U,0x0028U);
  scene_write(0x01deU,15U);task_shared[0x01e0U]|=1U;
  for(i=0U;i<16U;i+=1U)task_shared[0x0144U+i]=rom8(0U,0x0f87UL+(u32)i);
  conversation_arg0=11U;conversation_emit(9U,10U);return;
 }
 if(phase==10U && req==9U) {
  /* Final $8EFE update with X=$20 after eleven waits. */
  task_shared[0x0149U]=0x59U;task_shared[0x014fU]=0xe5U;
  task_shared[0x0148U]=0x1aU;task_shared[0x014eU]=0xa6U;
  conversation_selector=65535U;conversation_after_text=0U;conversation_text_request();return;
 }
 if(phase==11U && req==10U) {
  if(conversation_text_script) {
   conversation_arg0=conversation_actor;conversation_arg1=conversation_script;
   conversation_emit(11U,12U);return;
  }
  conversation_after_response();return;
 }
 if(phase==12U && req==11U) {conversation_after_response();return;}
 if(phase==13U && req==12U) {conversation_main_menu();return;}
 if(phase==14U && req==13U) {
  if(conversation_value==65535U) {scene_write(0x1d7fU,65535U);conversation_exit();return;}
  if(conversation_value>2U) {conversation_status=0U;return;}
  if(!conversation_value || scene_read(0x1d7fU)) {conversation_exit();return;}
  if(conversation_value==1U) {
   conversation_selector=65534U;conversation_after_text=1U;conversation_text_request();return;
  }
  if(task_shared[0x3ca3U]==255U) {conversation_main_menu();return;}
  count=0U;
  for(i=0U;i<10U;i+=1U) {
   key=(u16)task_shared[0x3ca3U+i];if(key==255U)break;
   if(i==9U) {conversation_status=0U;return;}
   ptr=conversation_rom16(0x68000UL+((u32)key<<1));
   if(!ptr) {conversation_status=0U;return;}
   scene_write(0x0154U+(i<<1),ptr);count+=1U;
  }
  if(i==10U || !count) {conversation_status=0U;return;}
  scene_write(0x0154U+(count<<1),0U);conversation_keyword_count=count;
  conversation_open(6U,15U,14U,11U,0U,15U);return;
 }
 if(phase==15U && req==5U) {
  if((conversation_value&1U) || conversation_value>=32U) {conversation_status=0U;return;}
  conversation_window_keyword=conversation_value;conversation_arg0=conversation_value;
  conversation_arg1=conversation_keyword_count;conversation_arg2=1U;
  conversation_arg3=0U;conversation_arg4=1U;conversation_emit(13U,16U);return;
 }
 if(phase==16U && req==13U) {
  conversation_keyword_cancelled=0U;
  if(conversation_value==65535U) {conversation_keyword_cancelled=1U;scene_write(0x1d7fU,65535U);}
  else if(conversation_value>=conversation_keyword_count) {conversation_status=0U;return;}
  else conversation_selector=(u16)task_shared[0x3ca3U+conversation_value];
  conversation_arg0=conversation_window_keyword;conversation_emit(14U,17U);return;
 }
 if(phase==17U && req==14U) {
  if(conversation_keyword_cancelled || scene_read(0x1d7fU)) {conversation_exit();return;}
  conversation_after_text=1U;conversation_text_request();return;
 }
 if(phase==20U && req==15U) {
  /* $8F97 final $8EFE update (X=$01), then its HDMA disable. */
  task_shared[0x0149U]=0x3aU;task_shared[0x014fU]=0xc6U;
  task_shared[0x0148U]=0x39U;task_shared[0x014eU]=0xc5U;
  scene_write(0x01deU,0U);task_shared[0x01e0U]&=0xfeU;
  held=conversation_value;
  if((held&15U) || held==0x3030U) {conversation_status=0U;return;}
  old=scene_read(0x01e8U);scene_write(0x01e6U,held);
  scene_write(0x01eaU,(held^old)&held);scene_write(0x01e8U,held);
  conversation_emit(17U,25U);return;
 }
 if(phase==25U && req==17U) {
  conversation_arg0=conversation_window_menu;conversation_emit(14U,21U);return;
 }
 if(phase==21U && req==14U) {
  conversation_arg0=conversation_window_text;conversation_emit(14U,22U);return;
 }
 if(phase==22U && req==14U) {
  if(conversation_music_restore) {
   conversation_arg0=conversation_original_music;conversation_arg1=3U;
   if(conversation_music_restore==2U) {conversation_arg0=0U;conversation_arg1=4U;}
   conversation_emit(4U,23U);return;
  }
  conversation_request=0U;conversation_status=2U;return;
 }
 if(phase==23U && req==4U) {conversation_request=0U;conversation_status=2U;return;}
 if(phase==24U && req==16U) {conversation_text_decode();return;}
 conversation_status=0U;
}
