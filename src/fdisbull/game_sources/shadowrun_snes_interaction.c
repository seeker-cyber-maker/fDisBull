/* Source cursor, directly owned windows and suspended verb-menu integration.
 * Each modal step is a source controller poll, not an actor/physics pass. */
u8 interaction_status,opening_phase,interaction_fault;
u8 interaction_cursor_display_tainted;
u16 interaction_choice_window,interaction_choice_selected;
u16 interaction_target_length,interaction_target_text[256];
u16 interaction_choice_lengths[8],interaction_choice_text[2048];
u16 interaction_action_count,interaction_last_actor,interaction_last_event;
u16 interaction_audio_events;
u16 interaction_item_pointer,interaction_item_task,interaction_item_name_length,interaction_item_name[256];

/* The placed actor and the inventory type need not share an entity record.
 * Follow the actual count/reference writer after its source-native effect. */
void interaction_item_written(u16 fn,u16 argument) {
 u16 pointer;
 if(interaction_last_event!=16U)return;
 if((fn==38U || fn==116U) && task_index==interaction_item_task) {
  if(argument>=15228U)return;
  pointer=target_rom16(0x6b032UL+(u32)argument);
 } else if(fn==111U && argument==interaction_last_actor) {
  pointer=scene_read(0x13c4U+argument);
 } else return;
 if(pointer && pointer<65531U)interaction_item_pointer=pointer;
}

void interaction_input(u16 held) {
 u16 old;old=scene_read(0x01e8U);
 scene_write(0x01e6U,held);scene_write(0x01eaU,(held^old)&held);scene_write(0x01e8U,held);
}
void interaction_pointer(u16 pointer) {
 shadowrun_snes_text_encoded_pointer=pointer;shadowrun_snes_text_decode_pointer(0U);
 if(shadowrun_snes_text_status!=1U)interaction_status=0U;
}
void interaction_text(u16 slot,u16 row,u16 column) {
 u16 i,base,width;
 if(!interaction_status)return;
 width=scene_read(0x2020U+slot);
 if(width<3U || column>=width-2U) {interaction_status=0U;interaction_fault=1U;return;}
 for(i=0U;i<=shadowrun_snes_text_length;i+=1U)task_shared[0x21a0U+i]=shadowrun_snes_text_output[i];
 base=scene_read(0x2060U+slot)+row*(width-2U)+column;
 shadowrun_snes_text_layout_base=base;shadowrun_snes_text_layout_cursor_in=base;
 shadowrun_snes_text_layout_width=width-column;shadowrun_snes_text_layout_height=3U;
 shadowrun_snes_text_layout_style=0U;shadowrun_snes_text_layout_subpixel_in=0U;
 shadowrun_snes_text_layout_icon_glyphs=1U;shadowrun_snes_text_layout(0U);
 shadowrun_snes_text_layout_icon_glyphs=0U;
 if(shadowrun_snes_text_layout_status!=1U) {interaction_status=0U;interaction_fault=2U;return;}
 scene_write(0x20c0U+slot,shadowrun_snes_text_layout_cursor);
 scene_write(0x20e0U+slot,shadowrun_snes_text_layout_subpixel);
 scene_write(0U,slot);scene_write(2U,shadowrun_snes_text_encoded_pointer);
 opening_window_display_tainted=1U;opening_window_scratch_tainted=1U;
}
void interaction_window_begin(u16 x,u16 y,u16 width,u16 height,u16 flags) {
 opening_window_arg0=x;opening_window_arg1=y;opening_window_arg2=width;
 opening_window_arg3=height;opening_window_arg4=flags;
 scene_write(0U,x);scene_write(2U,y);scene_write(4U,width);scene_write(6U,height);scene_write(8U,flags);
 opening_window_begin();
 if(opening_window_status!=1U) {interaction_status=0U;interaction_fault=3U;return;}
 /* A direct owner supplies its own text and lifetime; no FE8B timeout entry. */
 opening_window_phase=2U;scene_write(0U,opening_window_slot);
}
void interaction_target_close(void) {
 if(!(scene_read(0x01f6U)&32768U)) {
  scene_write(0U,scene_read(0x01f8U));opening_window_close(scene_read(0x01f8U));
  if(opening_window_status!=1U) {interaction_status=0U;interaction_fault=4U;return;}
  scene_write(0x01f6U,65535U);scene_write(0x01faU,65535U);
 }
}
void interaction_targets(void) {
 u16 i,n,width,slot;
 interaction_status=1U;interaction_fault=0U;
 shadowrun_snes_target_cursor(0U);
 for(n=0U;n<5U;n+=1U) {
  if(!target_status) {interaction_status=0U;interaction_fault=5U;return;}
  if(target_status==1U)return;
  if(target_request==1U)shadowrun_snes_target_scan(0U);
  else if(target_request==2U || target_request==3U) {
   interaction_target_close();if(!interaction_status)return;
   shadowrun_snes_target_resume(0U);
  } else if(target_request==4U) {
   interaction_pointer(target_name_pointer);if(!interaction_status)return;
   shadowrun_snes_text_measure(0U);
   if(!shadowrun_snes_text_measure_status) {interaction_status=0U;interaction_fault=6U;return;}
   width=(shadowrun_snes_text_measured_pixels+24U)>>3;
   if(width<3U || width>30U) {interaction_status=0U;interaction_fault=6U;return;}
   interaction_window_begin(30U-width,23U,width,3U,2048U);if(!interaction_status)return;
   slot=opening_window_slot;scene_write(0x01f8U,slot);
   interaction_target_length=shadowrun_snes_text_length;
   for(i=0U;i<=shadowrun_snes_text_length;i+=1U)interaction_target_text[i]=shadowrun_snes_text_output[i];
   interaction_text(slot,0U,0U);if(!interaction_status)return;
   shadowrun_snes_target_resume(0U);
  } else {interaction_status=0U;interaction_fault=7U;return;}
 }
 interaction_status=0U;interaction_fault=8U;
}
void interaction_choice_marker(u16 row,u16 pointer) {
 interaction_pointer(pointer);if(!interaction_status)return;
 interaction_text(interaction_choice_window,row,0U);
}
void interaction_menu_begin(void) {
 u16 i,j,pointer,slot;
 choice_mask=target_dispatch_wait;shadowrun_snes_choice_begin(0U);
 if(choice_status!=1U) {interaction_status=0U;interaction_fault=9U;return;}
 interaction_window_begin(12U,3U,11U,(u16)choice_count+2U,0U);if(!interaction_status)return;
 slot=opening_window_slot;interaction_choice_window=slot;scene_write(0x0068U,slot);
 scene_write(0x1dafU,slot);
 for(i=0U;i<(u16)choice_count;i+=1U) {
  pointer=choice_get(0x1f86U+(i<<1));interaction_pointer(pointer);if(!interaction_status)return;
  interaction_choice_lengths[i]=shadowrun_snes_text_length;
  for(j=0U;j<=shadowrun_snes_text_length;j+=1U)interaction_choice_text[(i<<8)+j]=shadowrun_snes_text_output[j];
  interaction_text(slot,i,1U);if(!interaction_status)return;
 }
 scene_write(0x1db9U,(u16)choice_count);
 if(choice_count<8U)scene_write(0x1db9U,(u16)choice_count+1U);
 scene_write(0x1dbbU,8U-(u16)choice_count);
 interaction_choice_selected=0U;interaction_choice_marker(0U,0x70b4U);
 if(!interaction_status)return;
 opening_phase=1U;
}
void interaction_dispatch_begin(void) {
 interaction_status=1U;interaction_fault=0U;
 shadowrun_snes_target_dispatch(0U);
 if(!target_dispatch_status) {interaction_status=0U;interaction_fault=10U;return;}
 if(target_dispatch_status==1U)return;
 if(target_dispatch_request==1U) {interaction_menu_begin();return;}
 /* Out-of-range warning needs its own source window and input continuation. */
 interaction_status=0U;interaction_fault=11U;
}
void interaction_poll(u16 held) {
 u16 old,slot,i;
 interaction_status=1U;interaction_fault=0U;
 if(opening_phase==1U) {
  old=choice_get(0x1db3U);choice_input=held;shadowrun_snes_choice_poll(0U);
  if(!choice_status) {interaction_status=0U;interaction_fault=12U;return;}
  if(choice_status==2U) {
   /* $A78C/$A7B3 erase the selected marker before the final input poll. */
   interaction_choice_marker(choice_get(0x1db3U)>>1,0x70bdU);if(!interaction_status)return;
   if(!choice_cancelled) {
    /* $A792-$A7AC: known confirmation request, opaque APU delivery. */
    scene_write(2U,76U);scene_write(4U,64U);scene_write(6U,3U);
    interaction_audio_events+=1U;scene_write(0U,choice_get(0x1db3U)>>1);
   } else scene_write(0U,65535U);
   opening_phase=2U;return;
  }
  if(old!=choice_get(0x1db3U)) {
   interaction_choice_marker(old>>1,0x70bdU);if(!interaction_status)return;
   interaction_choice_marker(choice_get(0x1db3U)>>1,0x70b4U);if(!interaction_status)return;
  }
  interaction_choice_selected=choice_get(0x1db3U)>>1;return;
 }
 if(opening_phase==2U) {
  choice_input=held;shadowrun_snes_choice_finish(0U);
  if(choice_status!=3U && choice_status!=4U) {interaction_status=0U;interaction_fault=12U;return;}
  scene_write(0U,interaction_choice_window);opening_window_close(interaction_choice_window);
  if(opening_window_status!=1U) {interaction_status=0U;interaction_fault=13U;return;}
  scene_write(0x1fc2U,0U);
  if(choice_event==2U && scene_read(0x442cU+target_dispatch_actor)) {interaction_status=0U;interaction_fault=14U;return;}
  slot=target_dispatch_task;
  if((slot&1U) || slot>=96U) {interaction_status=0U;interaction_fault=15U;return;}
  task_flags[slot>>1]|=choice_event;
  if(choice_event) {
   interaction_last_actor=target_dispatch_actor;interaction_last_event=choice_event;interaction_action_count+=1U;
  }
  if(choice_event==16U) {
   interaction_item_task=target_dispatch_task;
   interaction_item_pointer=scene_read(0x13c4U+target_dispatch_actor);
   interaction_item_name_length=interaction_target_length;
   for(i=0U;i<=interaction_target_length;i+=1U)interaction_item_name[i]=interaction_target_text[i];
  }
  interaction_target_close();if(!interaction_status)return;
  shadowrun_snes_target_end(0U);
  if(!target_status) {interaction_status=0U;interaction_fault=16U;return;}
  opening_phase=3U;return;
 }
 if(opening_phase==3U) {interaction_input(held);opening_phase=0U;return;}
 interaction_status=0U;interaction_fault=17U;
}
