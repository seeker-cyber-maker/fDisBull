/* Source-derived title/new-game/scene/task composition. The source video,
 * renderer and APU delivery clocks remain separate from logical loop steps.
 * A status-2 result requires whole-update rollback by the containing runtime. */
u8 shadowrun_snes_view=4,shadowrun_snes_frame_status;
u8 opening_stage,opening_failure,opening_pad,opening_previous_pad;
u16 opening_passes,opening_fault_task,opening_fault_native;
u16 opening_rotation;
u16 shadowrun_snes_player_x,shadowrun_snes_player_y,shadowrun_snes_player_z;
u16 opening_actor_count,opening_actor_id[44],opening_x[44],opening_y[44],opening_z[44];
u16 opening_action[44],opening_kind[44];
u8 opening_text_buffers[4096];
u16 opening_text_lengths[16],opening_text_ids[16],opening_message_count;
u16 opening_audio_projection_events;
u16 opening_refresh_events;

void opening_load(u16 slot);
void opening_save(u16 slot);

/* $8000-$80B1 checks two ROM volume lists before actor physics. Executing
 * a new trigger script or loading another room is outside this profile. */
void opening_scene_gate(void) {
 u16 actor,x,y,z,group,count,i,ptr,bank;
 u32 at;
 if(scene_read(0x1d05U)!=65535U) {opening_failure=37U;return;}
 actor=scene_read(0x0cdeU);if(actor&32768U)return;
 if((actor&1U) || actor>=88U) {opening_failure=12U;return;}
 x=scene_read(0x0e44U+actor)>>2;y=scene_read(0x0e9cU+actor)>>2;
 z=scene_read(0x0ef4U+actor)>>2;
 ptr=scene_read(0x009dU);bank=(u16)task_shared[0x009fU];
 if(ptr<32768U || (bank&127U)>31U) {opening_failure=37U;return;}
 at=((u32)(bank&127U)<<15)+(u32)(ptr&32767U);
 for(group=0U;group<2U;group+=1U) {
  if(at>=1048576UL) {opening_failure=37U;return;}
  count=(u16)rom8(0U,at);at+=1UL;
  for(i=0U;i<count;i+=1U) {
   if(at+13UL>=1048576UL) {opening_failure=37U;return;}
   if(x>=scene_rom16(at) && y>=scene_rom16(at+2UL) && z>=scene_rom16(at+4UL) &&
      x<=scene_rom16(at+6UL) && y<=scene_rom16(at+8UL) && z<=scene_rom16(at+10UL)) {
    opening_failure=37U;return;
   }
   at+=14UL;
  }
 }
}

/* $DE5E: the original forced-motion countdown precedes actor physics.
 * Do not zero its preserved title-state value before source $87 resets it. */
void opening_forced_motion(void) {
 u16 actor,value,remaining;
 actor=scene_read(0x0cdeU);if(actor&32768U)return;
 if((actor&1U) || actor>=88U) {opening_failure=12U;return;}
 value=scene_read(0x1d81U);if(!value)return;
 remaining=value-1U;scene_write(0x1d81U,remaining);
 if(!remaining) {scene_write(0x0d3cU+actor,0U);scene_write(0x0d94U+actor,0U);}
 else if(value&1U) {scene_write(0x0d3cU+actor,65532U);scene_write(0x0d94U+actor,4U);}
 else {scene_write(0x0d3cU+actor,4U);scene_write(0x0d94U+actor,65532U);}
}

/* $DFDE neutral/cardinal branch through $DE91 and $E17A. Menu, combat and
 * interaction edges refuse; movement consumes HELD input, not press edges. */
void opening_player_control(void) {
 u16 actor,joy,dir,walking;
 actor=scene_read(0x0cdeU);
 if((actor&1U) || actor>=88U ||
    (scene_read(0x01eaU)&28912U)) {opening_failure=26U;return;}
 if(scene_read(0x01f4U)) {
  if(scene_read(0x1d79U)|scene_read(0x1d7bU)) {opening_failure=26U;return;}
  shadowrun_snes_target_facing(0U);
  if(!target_facing_status) {opening_failure=41U;return;}
  opening_load(actor);npc_requested_direction=target_facing_direction;
  shadowrun_snes_npc_direction(0U);
  if(!npc_supported) {opening_failure=14U;return;}
  if((scene_read(0x01f6U)&32768U) && (scene_read(0x01eaU)&32768U)) {
   scene_write(0x1d79U,0U);scene_write(0x1d7bU,0U);scene_write(2U,0U);
   npc_requested_action=0U;shadowrun_snes_npc_action(0U);
   if(!npc_supported) {opening_failure=13U;return;}
   interaction_status=1U;interaction_target_close();shadowrun_snes_target_end(0U);
   if(!interaction_status || !target_status) {opening_failure=40U;return;}
  }
  opening_save(actor);
  task_callback_result=0U;scene_write(0U,0U);
  task_callback_success=1U;shadowrun_snes_task_callback_complete(0U);return;
 }
 if(scene_read(0x01eaU)&32768U) {
  opening_load(actor);
  if(!scene_read(0x1d77U)) {
   scene_write(0x1d77U,65535U);npc_velocity_x=0U;npc_velocity_y=0U;
  }
  shadowrun_snes_target_begin(0U);
  if(!target_status) {opening_failure=40U;return;}
  interaction_cursor_display_tainted=1U;
  scene_write(2U,0U);npc_requested_action=0U;shadowrun_snes_npc_action(0U);
  if(!npc_supported) {opening_failure=13U;return;}
  opening_save(actor);task_callback_result=0U;scene_write(0U,0U);
  task_callback_success=1U;shadowrun_snes_task_callback_complete(0U);return;
 }
 opening_load(actor);joy=(scene_read(0x01e6U)&3840U)>>8;
 dir=npc_rom16(0x5f15UL+((u32)joy<<1));
 if(dir<16U)dir=(dir-opening_rotation-opening_rotation)&14U;
 if(dir>16U || (dir&1U)) {opening_failure=26U;return;}
 npc_velocity_x=npc_rom16(0x5ef1UL+(u32)dir);
 npc_velocity_y=npc_rom16(0x5f03UL+(u32)dir);
 walking=scene_read(0x1d77U);
 if(dir==16U) {
  if(!walking) {
   npc_requested_action=0U;shadowrun_snes_npc_action(0U);
   if(!npc_supported) {opening_failure=13U;return;}
   scene_write(0x1d77U,65535U);
  }
 } else {
  if(walking) {
   npc_requested_action=2U;shadowrun_snes_npc_action(0U);
   if(!npc_supported) {opening_failure=13U;return;}
   scene_write(0x1d77U,0U);
  }
  npc_requested_direction=dir>>1;shadowrun_snes_npc_direction(0U);
  if(!npc_supported) {opening_failure=14U;return;}
 }
 opening_save(actor);opening_stage=2U;scene_write(0U,0U);
 task_callback_result=0U;task_callback_success=1U;shadowrun_snes_task_callback_complete(0U);
}

void opening_publish(void) {
 u16 i,slot,count;
 count=scene_read(0x14ccU);
 opening_actor_count=0U;
 if(count&32768U)return;
 if((count&1U) || count>=88U) {opening_failure=30U;return;}
 for(i=0U;i<=count;i+=2U) {
  slot=scene_read(0x14ceU+i);
  if((slot&1U) || slot>=88U) {opening_failure=30U;return;}
  opening_actor_id[i>>1]=slot;
  opening_x[i>>1]=scene_read(0x0e44U+slot);
  opening_y[i>>1]=scene_read(0x0e9cU+slot);
  opening_z[i>>1]=scene_read(0x0ef4U+slot);
  opening_action[i>>1]=scene_read(0x1054U+slot);
  opening_kind[i>>1]=scene_read(0x3f04U+slot);
  opening_actor_count+=1U;
 }
 slot=scene_read(0x0cdeU);
 if(slot==65535U)slot=68U;
 if((slot&1U) || slot>=88U) {opening_failure=30U;return;}
 shadowrun_snes_player_x=scene_read(0x0e44U+slot);
 shadowrun_snes_player_y=scene_read(0x0e9cU+slot);
 shadowrun_snes_player_z=scene_read(0x0ef4U+slot);
}

void opening_callback(void) {
 u16 actor,i,count,found,slot;
 opening_fault_native=task_vm_callback;
 if(task_vm_callback==199U) {
  opening_window_arg0=task_vm_arg0;opening_window_arg1=task_vm_arg1;
  opening_window_arg2=task_vm_arg2;opening_window_arg3=task_vm_arg3;
  opening_window_arg4=task_vm_arg4;opening_window_arg5=task_vm_arg5;
  opening_window_arg6=task_vm_arg6;opening_window_begin();
  if(opening_window_status!=1U) {opening_failure=31U;return;}
  shadowrun_snes_text_id=task_vm_arg5;shadowrun_snes_text_decode(0U);
  if(shadowrun_snes_text_status!=1U) {opening_failure=32U;return;}
  for(i=0U;i<=shadowrun_snes_text_length;i+=1U)
   task_shared[0x21a0U+i]=shadowrun_snes_text_output[i];
  slot=opening_window_slot;
  shadowrun_snes_text_layout_base=scene_read(0x2060U+slot);
  shadowrun_snes_text_layout_width=scene_read(0x2020U+slot);
  shadowrun_snes_text_layout_height=scene_read(0x2040U+slot);
  shadowrun_snes_text_layout_style=scene_read(0x2140U+slot);
  shadowrun_snes_text_layout_cursor_in=scene_read(0x20c0U+slot);
  shadowrun_snes_text_layout_subpixel_in=scene_read(0x20e0U+slot);
  shadowrun_snes_text_layout(0U);
  if(shadowrun_snes_text_layout_status!=1U) {opening_failure=33U;return;}
  opening_window_layout_cursor=shadowrun_snes_text_layout_cursor;
  opening_window_layout_subpixel=shadowrun_snes_text_layout_subpixel;
  opening_window_text_complete=1U;opening_window_present_complete=1U;
  opening_window_finish();if(opening_window_status!=1U) {opening_failure=31U;return;}
  opening_text_lengths[slot>>1]=shadowrun_snes_text_length;
  opening_text_ids[slot>>1]=shadowrun_snes_text_id;
  for(i=0U;i<=shadowrun_snes_text_length;i+=1U)
   opening_text_buffers[(slot<<7)+i]=shadowrun_snes_text_output[i];
  opening_message_count+=1U;
  task_callback_success=1U;shadowrun_snes_task_callback_complete(0U);
 } else if(task_vm_callback==193U) {
  /* CD78 returns the selected target, then AD4E redraws and waits for its
   * display handshake. Only the observed no-cursor branch is recovered.
   * The native view redraw is adapted; original raster/scratch stay tainted. */
  if(scene_read(0x1d7dU)!=65535U || !(scene_read(0x01f0U)&32768U) ||
     !(scene_read(0x01f2U)&32768U)) {opening_failure=36U;return;}
  opening_refresh_events+=1U;opening_window_display_tainted=1U;
  opening_window_scratch_tainted=1U;
  task_callback_result=scene_read(0x1d7dU);scene_write(0U,task_callback_result);
  task_callback_success=1U;shadowrun_snes_task_callback_complete(0U);
 } else if(task_vm_callback==177U) {
  if((task_vm_arg0&1U) || task_vm_arg0>=88U) {opening_failure=43U;return;}
  action_collision_actor=task_vm_arg0;action_collision_action=task_vm_arg1;
  action_collision_flags_known=target_geometry_known[task_vm_arg0>>1];
  shadowrun_snes_action_collision(0U);
  if(!action_collision_supported) {opening_failure=43U;return;}
  task_callback_result=action_collision_result;
  task_callback_success=1U;shadowrun_snes_task_callback_complete(0U);
 } else if(task_vm_callback==76U && task_audio_tainted) {
  /* The source request is known; beam/APU-derived delivery and latches are
   * outside this opening projection. No random value or latch is invented. */
  if(task_audio_count>=64U || !task_vm_arg3 || task_vm_arg1>=15228U) {opening_failure=34U;return;}
  i=task_audio_count;task_audio_actor[i]=task_vm_arg0;task_audio_id[i]=task_vm_arg1;
  task_audio_volume[i]=task_vm_arg2;task_audio_mode[i]=task_vm_arg3;
  task_audio_count+=1U;opening_audio_projection_events+=1U;
  task_callback_success=1U;shadowrun_snes_task_callback_complete(0U);
 } else if(task_vm_callback==209U || task_vm_callback==208U || task_vm_callback==106U) {
  actor=task_vm_arg0;
  if((actor&1U) || actor>=88U) {opening_failure=12U;return;}
  opening_load(actor);
  if(task_vm_callback!=106U) {
   npc_requested_action=task_vm_arg1;shadowrun_snes_npc_action(0U);
   if(!npc_supported) {opening_failure=13U;return;}
  }
  if(task_vm_callback!=208U) {
   if(task_vm_callback==106U)npc_requested_direction=task_vm_arg1;
   else npc_requested_direction=task_vm_arg2;
   shadowrun_snes_npc_direction(0U);
   if(!npc_supported) {opening_failure=14U;return;}
  }
  opening_save(actor);
  task_callback_success=1U;shadowrun_snes_task_callback_complete(0U);
 } else if(task_vm_callback==207U) {
  opening_player_control();
 } else if(task_vm_callback==120U) {
  scene_party_kind=task_vm_arg0;scene_party_x=task_vm_arg1;
  scene_party_y=task_vm_arg2;scene_party_z=task_vm_arg3;
  scene_party_direction=task_vm_arg4;scene_party_entity=task_vm_arg5;
  scene_party_extra=task_vm_arg6;shadowrun_snes_party_construct(0U);
  if(scene_party_status!=1U) {opening_failure=27U;return;}
  task_callback_success=1U;shadowrun_snes_task_callback_complete(0U);
 } else if(task_vm_callback==184U) {
  /* A882/A9D9 logical actor teardown and shared sprite-node release. */
  actor=task_vm_arg0;
  if((actor&1U) || actor>=88U) {opening_failure=12U;return;}
  count=scene_read(0x14ccU);found=65535U;
  if((count&1U) || count>=88U) {opening_failure=30U;return;}
  for(i=0U;i<=count;i+=2U)if(scene_read(0x14ceU+i)==actor)found=i;
  if(found==65535U) {opening_failure=30U;return;}
  opening_animation_metadata_cleanup(actor);
  if(!opening_anim_supported) {opening_failure=35U;return;}
  scene_write(0x421cU+actor,0U);scene_write(0x4274U+actor,0U);
  scene_write(0x42ccU+actor,0U);scene_write(0x4324U+actor,0U);
  scene_write(0x437cU+actor,0U);scene_write(0x40bcU+actor,0U);
  scene_write(0x115cU+actor,0U);scene_write(0x3f5cU+actor,0U);
  scene_write(0x10acU+actor,0U);scene_write(0x1054U+actor,65535U);
  scene_write(0x400cU+actor,128U);scene_write(0x3fb4U+actor,1U);
  scene_write(0x12bcU+actor,0U);scene_write(0x3f04U+actor,65535U);
  for(i=found;i<count;i+=2U)scene_write(0x14ceU+i,scene_read(0x14d0U+i));
  scene_write(0x14ccU,count-2U);
  task_callback_success=1U;shadowrun_snes_task_callback_complete(0U);
 } else {
  shadowrun_snes_task_native(0U);
  if(!task_native_supported) {opening_failure=15U;return;}
  interaction_item_written((u16)task_vm_callback,task_vm_arg0);
 }
}

/* C1B3 starts with $026C, not $0268. Its first pass after C176 primes the
 * current pointer; a child may run immediately and resume its parent. */
void opening_scheduler(void) {
 u16 current,n,dispatch,bypass;
 current=task_list_current;bypass=0U;
 for(n=0U;n<256U;n+=1U) {
  if(current&32768U) {task_list_current=task_list_head;return;}
  if((current&1U) || current>=96U) {opening_failure=19U;return;}
  task_index=current;task_list_current=current;opening_fault_task=current;
  if(!bypass) {
   shadowrun_snes_task_check(0U);
   if(!task_supported) {opening_failure=10U;return;}
   if(!task_ready) {current=task_next[current>>1];continue;}
  }
  bypass=0U;
  for(dispatch=0U;dispatch<64U;dispatch+=1U) {
   shadowrun_snes_task_vm(0U);
   if(task_vm_status==1U) {current=task_next[current>>1];break;}
   if(task_vm_status==2U) {opening_callback();if(opening_failure)return;continue;}
   if(task_vm_status==5U) {
    shadowrun_snes_task_create_child(0U);
    if(!task_init_supported) {opening_failure=18U;return;}
    current=task_init_result;bypass=1U;break;
   }
   if(task_vm_status==4U) {
    shadowrun_snes_task_terminate(0U);
    if(!task_supported) {opening_failure=18U;return;}
    current=task_list_current;
    if(!(current&32768U) && (task_wait[current>>1]&32768U)) {
     task_wait[current>>1]=0U;bypass=1U;
    }
    break;
   }
   opening_failure=11U;return;
  }
  if(dispatch==64U) {opening_failure=16U;return;}
 }
 opening_failure=19U;
}

void opening_actor(u16 slot) {
 u16 z,next,previous,col;u8 axis;
 opening_load(slot);
 if(npc_flags&1024U)return;
 npc_supported=1U;npc_completion_pending=0U;
 if(npc_timer) {
  if(npc_control&1U)shadowrun_snes_npc_control(0U);
  else shadowrun_snes_npc_diagonal(0U);
  if(npc_control_direction_called) {
   scene_write(0U,slot);scene_write(2U,npc_requested_direction);
  }
 }
 if(!npc_supported) {opening_failure=21U;return;}
 if(npc_completion_pending) {
  task_index=npc_completion_task;shadowrun_snes_task_signal(0U);
  if(!task_supported) {opening_failure=22U;return;}
 }
 npc_flags&=65527U;
 if(npc_velocity_x) {
  previous=npc_x;npc_x+=npc_velocity_x;
  if(npc_flags&64U) {
   axis=2U;if(npc_velocity_x&32768U)axis=0U;
   col=opening_collision_at(slot,npc_x,npc_y,axis);
   if(!opening_collision_supported) {opening_failure=25U;return;}
   if(col>=5U) {npc_x=previous;npc_flags|=8U;}
   else if(col) {npc_z+=col<<2;npc_velocity_z=0U;scene_write(0x0ef4U+slot,npc_z);}
  }
 }
 if(npc_velocity_y) {
  previous=npc_y;npc_y+=npc_velocity_y;
  if(npc_flags&64U) {
   axis=1U;if(npc_velocity_y&32768U)axis=3U;
   col=opening_collision_at(slot,npc_x,npc_y,axis);
   if(!opening_collision_supported) {opening_failure=25U;return;}
   if(col>=5U) {npc_y=previous;npc_flags|=8U;}
   else if(col) {npc_z+=col<<2;npc_velocity_z=0U;scene_write(0x0ef4U+slot,npc_z);}
  }
 }
 z=npc_z;
 if(npc_flags&32U)npc_velocity_z-=1U;
 next=z+npc_velocity_z;
 if(next<256U)npc_velocity_z=0U;
 else if(next!=z) {
  if(npc_flags&64U) {opening_failure=25U;return;}
  npc_z=next;
 }
 npc_depth=(u16)(npc_x+npc_y)>>1;
 opening_save(slot);
}
void opening_animation(u16 slot) {
 opening_load(slot);
 if(npc_flags&1024U)return;
 shadowrun_snes_npc_animate();
 if(!npc_supported) {opening_failure=23U;return;}
 if(npc_animation_completion_pending) {
  task_index=npc_task;task_signal_mask=8U;shadowrun_snes_task_signal_mask(0U);
  if(!task_supported) {opening_failure=24U;return;}
 }
 opening_save(slot);
 if(npc_animation_frame_pending) {
  opening_animation_metadata(slot,npc_animation_frame_word);
  if(!opening_anim_supported) {opening_failure=35U;return;}
 }
}

void shadowrun_snes_frame(u8 pad) {
 u16 raw,previous,i,count,slot,resuming;
 shadowrun_snes_frame_status=2U;opening_failure=0U;opening_pad=pad;
 if(pad&128U) {opening_failure=1U;return;}
 raw=0U;previous=0U;
 if(pad&1U)raw|=2048U;if(pad&2U)raw|=1024U;
 if(pad&4U)raw|=512U;if(pad&8U)raw|=256U;
 if(pad&16U)raw|=4096U;if(pad&32U)raw|=32768U;if(pad&64U)raw|=8192U;
 resuming=0U;
 if(opening_phase) {
  interaction_poll(raw);
  if(!interaction_status) {opening_failure=40U;return;}
  if(opening_phase) {shadowrun_snes_frame_status=1U;return;}
  resuming=1U;
 }
 if(!resuming) {
 previous=scene_read(0x01e8U);
 scene_write(0x01e6U,raw);scene_write(0x01eaU,(raw^previous)&raw);scene_write(0x01e8U,raw);
 opening_previous_pad=pad;
 if(!opening_stage) {
  menu_pressed=scene_read(0x01eaU);shadowrun_snes_menu_control(0U);
  if(!menu_supported) {opening_failure=3U;return;}
  if(menu_confirmed) {
   if(menu_selection) {opening_failure=4U;return;}
   shadowrun_snes_input_reset(0U);
   /* $E218, called by the title transition, requests the initial HUD refresh. */
   scene_write(0x1da5U,65535U);
   /* $CC14 initializes the scene-request word, adjacent to the byte PRNG. */
   scene_write(0x1d05U,65535U);
   opening_animation_metadata_reset();
   if(!opening_anim_supported) {opening_failure=35U;return;}
   shadowrun_snes_scene_construct(0U);
   if(scene_construct_status!=1U) {opening_failure=5U;return;}
   target_globals_known=1U;
   for(i=0U;i<44U;i+=1U)target_geometry_known[i]=1U;
   opening_window_reset();if(opening_window_status!=1U) {opening_failure=31U;return;}
   task_audio_tainted=1U;opening_window_audio_tainted=1U;
   task_visual_tainted=1U;
   opening_stage=1U;opening_publish();if(opening_failure)return;
  }
  shadowrun_snes_frame_status=1U;return;
 }
 if(opening_stage==2U) {
  interaction_targets();if(!interaction_status) {opening_failure=40U;return;}
  interaction_dispatch_begin();if(!interaction_status) {opening_failure=40U;return;}
  if(opening_phase) {shadowrun_snes_frame_status=1U;return;}
 }
 }
 opening_scheduler();if(opening_failure)return;
 opening_scene_gate();if(opening_failure)return;
 opening_forced_motion();if(opening_failure)return;
 opening_rebuild();if(!opening_rebuild_supported) {opening_failure=28U;return;}
 count=scene_read(0x14ccU);
 if(count&32768U) {opening_failure=30U;return;}
 if((count&1U) || count>=88U) {opening_failure=30U;return;}
 i=count;
 for(;;) {
  slot=scene_read(0x14ceU+i);
  if((slot&1U) || slot>=88U) {opening_failure=30U;return;}
  opening_actor(slot);if(opening_failure)return;
  if(!i)break;i-=2U;
 }
 i=count;
 for(;;) {
  slot=scene_read(0x14ceU+i);
  opening_animation(slot);if(opening_failure)return;
  if(!i)break;i-=2U;
 }
 shadowrun_snes_live_camera(0U);
 if(!camera_status) {opening_failure=42U;return;}
 opening_sort();if(!opening_sort_supported) {opening_failure=29U;return;}
 opening_animation_metadata_pass_finish();
 opening_window_tick();if(opening_window_status!=1U) {opening_failure=31U;return;}
 if(opening_window_rng_tainted)task_rng_tainted=1U;
 if(opening_window_audio_tainted)task_audio_tainted=1U;
 /* $E23A returns directly through $E2D8 while this HUD request is negative. */
 if(!(scene_read(0x1da5U)&32768U)) {opening_failure=38U;return;}
 opening_passes+=1U;opening_publish();if(opening_failure)return;
 shadowrun_snes_frame_status=1U;
}
