/* Shared-state adapter for the bounded $92EF coroutine. Display and audio
 * delivery remain typed, tainted projections; no future WRAM seeds enter it.
 * opening_phase 4/5 are selector/final polls; 6 is the exit $9D9D poll. */
u8 conversation_ui_active,conversation_origin,opening_scheduler_resume;
u16 conversation_native_task,conversation_ui_count,conversation_ui_mode;
u16 conversation_ui_lengths[9],conversation_ui_labels[2304];
u16 conversation_ui_length,conversation_ui_text[256];
u16 conversation_display_waits,conversation_audio_requests,conversation_completed;
u16 conversation_bridge_fault;
void opening_callback(void);

void conversation_bridge_reply(u16 value) {
 conversation_value=value;conversation_reply_request=conversation_request;
 conversation_reply_success=1U;shadowrun_snes_conversation_reply(0U);
}
void conversation_bridge_taint(void) {
 task_visual_tainted=1U;task_audio_tainted=1U;task_dialogue_tainted=1U;
 opening_window_display_tainted=1U;opening_window_scratch_tainted=1U;
}
/* C19A executes one head task, with immediate child/parent continuations,
 * then restores the suspended scheduler pointer. It never visits siblings. */
void conversation_bridge_child(void) {
 u16 saved,current,n,dispatch;
 saved=task_list_current;task_init_script=conversation_arg1;
 if(rom8(0U,92176UL+(u32)task_init_script)!=2U) {opening_failure=45U;return;}
 task_init_args[0]=(u8)conversation_arg0;task_init_args[1]=(u8)(conversation_arg0>>8);
 shadowrun_snes_task_create(0U);if(!task_init_supported) {opening_failure=18U;return;}
 current=task_list_head;task_vm_pending=0U;
 for(n=0U;n<96U;n+=1U) {
  if((current&1U) || current>=96U) {opening_failure=45U;return;}
  task_index=current;task_list_current=current;
  for(dispatch=0U;dispatch<64U;dispatch+=1U) {
   shadowrun_snes_task_vm(0U);
   if(task_vm_status==1U)break;
   if(task_vm_status==2U) {
    if(task_vm_callback==148U) {opening_failure=45U;return;}
    opening_callback();if(opening_failure)return;continue;
   }
   if(task_vm_status==5U) {
    shadowrun_snes_task_create_child(0U);if(!task_init_supported) {opening_failure=18U;return;}
    current=task_init_result;break;
   }
   if(task_vm_status==4U) {
    shadowrun_snes_task_terminate(0U);if(!task_supported) {opening_failure=18U;return;}
    current=task_list_current;
    if(!(current&32768U) && (task_wait[current>>1]&32768U)) {
     task_wait[current>>1]=0U;break;
    }
    n=96U;break;
   }
   opening_failure=11U;return;
  }
  if(dispatch==64U) {opening_failure=16U;return;}
  if(task_vm_status==1U || n==96U)break;
 }
 if(n==96U && task_vm_status!=4U) {opening_failure=45U;return;}
 task_list_current=saved;
 if(conversation_origin) {
  task_index=conversation_native_task;task_vm_pending=1U;
  task_vm_pending_task=conversation_native_task;task_vm_callback=148U;task_vm_return=0U;
 }
}

void conversation_bridge_marker(u16 row,u16 pointer) {
 interaction_pointer(pointer);if(!interaction_status)return;
 interaction_text(conversation_arg0,conversation_arg3+row,conversation_arg2-1U);
}
void conversation_bridge_menu(void) {
 u16 i,j,pointer,slot;
 interaction_status=1U;slot=conversation_arg0;
 dialogue_select_count=conversation_arg1;dialogue_select_rows=3U;
 if(conversation_arg4)dialogue_select_rows=9U;
 dialogue_select_column=conversation_arg2;dialogue_select_row=conversation_arg3;
 shadowrun_snes_dialogue_select_begin(0U);
 if(dialogue_select_status!=1U) {opening_failure=45U;return;}
 conversation_ui_count=dialogue_select_count;conversation_ui_mode=conversation_arg4;
 for(i=0U;i<dialogue_select_count;i+=1U) {
  if(conversation_arg4)pointer=scene_read(0x0154U+(i<<1));
  else pointer=conversation_rom16(0x11b8UL+(i<<1));
  interaction_pointer(pointer);if(!interaction_status) {opening_failure=45U;return;}
  conversation_ui_lengths[i]=shadowrun_snes_text_length;
  for(j=0U;j<=shadowrun_snes_text_length;j+=1U)
   conversation_ui_labels[(i<<8)+j]=shadowrun_snes_text_output[j];
  interaction_text(slot,conversation_arg3+i,conversation_arg2);
  if(!interaction_status) {opening_failure=45U;return;}
 }
 scene_write(0x1db9U,dialogue_select_count);
 if(dialogue_select_count<dialogue_select_rows)scene_write(0x1db9U,dialogue_select_count+1U);
 scene_write(0x1dbbU,dialogue_select_rows-dialogue_select_count);
 conversation_bridge_marker(0U,0x70b4U);
 if(!interaction_status) {opening_failure=45U;return;}
 opening_phase=4U;
}

void conversation_bridge_draw(void) {
 u16 slot,i;
 interaction_status=1U;slot=conversation_arg0;
 scene_write(2U,conversation_arg1);
 interaction_pointer(conversation_arg1);if(!interaction_status) {opening_failure=45U;return;}
 for(i=0U;i<=shadowrun_snes_text_length;i+=1U)task_shared[0x21a0U+i]=shadowrun_snes_text_output[i];
 shadowrun_snes_text_layout_base=scene_read(0x2060U+slot);
 shadowrun_snes_text_layout_width=scene_read(0x2020U+slot);
 shadowrun_snes_text_layout_height=scene_read(0x2040U+slot);
 shadowrun_snes_text_layout_style=scene_read(0x2140U+slot);
 shadowrun_snes_text_layout_left_margin=scene_read(0x2100U+slot);
 shadowrun_snes_text_layout_controls=1U;
 shadowrun_snes_text_layout_cursor_in=scene_read(0x20c0U+slot);
 shadowrun_snes_text_layout_subpixel_in=scene_read(0x20e0U+slot);
 shadowrun_snes_text_layout(0U);
 shadowrun_snes_text_layout_controls=0U;shadowrun_snes_text_layout_left_margin=0U;
 if(!shadowrun_snes_text_layout_status) {opening_failure=45U;conversation_bridge_fault=10U;return;}
 scene_write(0x00aeU,shadowrun_snes_text_layout_style_out);
 for(i=0U;i<=shadowrun_snes_text_length;i+=1U)task_shared[0x21a0U+i]=shadowrun_snes_text_output[i];
 scene_write(0x20c0U+slot,shadowrun_snes_text_layout_cursor);
 scene_write(0x20e0U+slot,shadowrun_snes_text_layout_subpixel);
 conversation_ui_length=shadowrun_snes_text_length;
 for(i=0U;i<=shadowrun_snes_text_length;i+=1U)conversation_ui_text[i]=shadowrun_snes_text_output[i];
}

void opening_conversation_advance(void) {
 u16 n,i,slot,request;
 for(n=0U;n<128U;n+=1U) {
  if(conversation_status==2U) {
   conversation_completed+=1U;conversation_ui_active=0U;
   if(conversation_origin) {
    task_index=conversation_native_task;task_vm_pending=1U;
    task_vm_pending_task=conversation_native_task;task_vm_return=0U;
    task_callback_success=1U;shadowrun_snes_task_callback_complete(0U);
    opening_phase=0U;opening_scheduler_resume=1U;
   } else {interaction_status=1U;interaction_dispatch_finish(0U);}
   return;
  }
  if(conversation_status!=1U) {opening_failure=45U;return;}
  request=conversation_request;conversation_bridge_fault=request;
  if(request==13U) {conversation_bridge_menu();return;}
  if(request==15U) {
   /* AD81's pending-frame drain precedes the final input poll. */
   slot=scene_read(0x14ccU);
   if((slot&32769U) || slot>=88U) {opening_failure=45U;return;}
   for(i=0U;i<=slot;i+=2U) {
    if(scene_read(0x115cU+scene_read(0x14ceU+i))) {opening_failure=45U;return;}
   }
   opening_phase=6U;return;
  }
  if(request==1U || request==6U || request==7U || request==8U) {
   conversation_bridge_taint();
  } else if(request==2U) {
   interaction_status=1U;interaction_target_close();
   if(!interaction_status) {opening_failure=40U;return;}
   shadowrun_snes_target_end(0U);if(!target_status) {opening_failure=40U;return;}
  } else if(request==3U) {
   for(i=8U;i>0U;i-=2U) {
    slot=scene_read(0x0232U+i-2U);
    if(!(slot&32768U)) {
     scene_write(0U,slot);
     opening_window_close(slot);if(!opening_window_status) {opening_failure=31U;return;}
     scene_write(0x0232U+i-2U,65535U);
    }
   }
   scene_write(0x021cU,0U);
  } else if(request==4U) {
   conversation_audio_requests+=1U;conversation_bridge_taint();
  } else if(request==5U) {
   interaction_status=1U;
   interaction_window_begin(conversation_arg0,conversation_arg1,conversation_arg2,conversation_arg3,conversation_arg4);
   if(!interaction_status) {opening_failure=31U;return;}
   conversation_bridge_reply(opening_window_slot);continue;
  } else if(request==9U || request==12U) {
   conversation_display_waits+=conversation_arg0;conversation_bridge_taint();
  } else if(request==10U) {
   conversation_bridge_draw();if(opening_failure)return;
  } else if(request==11U) {
   conversation_bridge_child();if(opening_failure)return;
  } else if(request==14U) {
   opening_window_close(conversation_arg0);if(!opening_window_status) {opening_failure=31U;return;}
  } else if(request==16U) {
   conversation_ui_length=0U;
   slot=conversation_arg0;scene_write(0U,slot);scene_write(2U,0U);scene_write(4U,0U);
   scene_write(0x20c0U+slot,scene_read(0x2060U+slot));scene_write(0x20e0U+slot,0U);
   /* AC79's adapted wait completes only after this queue counter clears. */
   scene_write(0x0212U,0U);
   conversation_bridge_taint();
  } else if(request==17U) {
   opening_sort();if(!opening_sort_supported) {opening_failure=29U;return;}
   opening_animation_metadata_pass_finish();conversation_bridge_taint();
  } else {opening_failure=45U;return;}
  conversation_bridge_reply(0U);
 }
 opening_failure=45U;
}

void opening_conversation_begin(u16 actor,u16 tag,u8 origin) {
 conversation_actor=actor;conversation_tag=tag;conversation_origin=origin;
 conversation_native_task=task_index;conversation_ui_active=1U;
 shadowrun_snes_conversation_begin(0U);opening_conversation_advance();
}
void opening_conversation_poll(u16 held) {
 u16 old;
 if(opening_phase==6U) {
  conversation_display_waits+=12U;conversation_bridge_taint();
  conversation_bridge_reply(held);opening_conversation_advance();return;
 }
 if(opening_phase==4U) {
  old=scene_read(0x1db3U);dialogue_select_input=held;
  shadowrun_snes_dialogue_select_poll(0U);
  if(!dialogue_select_status) {opening_failure=45U;return;}
  interaction_status=1U;
  if(dialogue_select_status==2U) {
   conversation_bridge_marker(old>>1,0x70bdU);
   if(!interaction_status) {opening_failure=45U;return;}
   if(!dialogue_select_cancelled) {
    interaction_audio_events+=1U;
    scene_write(2U,0x004cU);scene_write(4U,0x0040U);scene_write(6U,3U);
   }
   scene_write(0U,dialogue_select_index);
   opening_phase=5U;return;
  }
  if(dialogue_select_moved) {
   conversation_bridge_marker(old>>1,0x70bdU);
   if(!interaction_status) {opening_failure=45U;return;}
   conversation_bridge_marker(scene_read(0x1db3U)>>1,0x70b4U);
   if(!interaction_status) {opening_failure=45U;return;}
   scene_write(2U,0x004aU);scene_write(4U,0x0040U);
  }
  return;
 }
 if(opening_phase==5U) {
  dialogue_select_input=held;shadowrun_snes_dialogue_select_finish(0U);
  if(dialogue_select_status!=3U && dialogue_select_status!=4U) {opening_failure=45U;return;}
  conversation_bridge_reply(dialogue_select_index);opening_conversation_advance();return;
 }
 opening_failure=45U;
}
