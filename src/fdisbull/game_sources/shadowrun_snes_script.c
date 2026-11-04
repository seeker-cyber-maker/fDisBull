/* Bounded task signaling and wakeup from $80:C8C9-C8E2 and $80:C399-C3D0.
 * Task identities are byte offsets into 48 word slots, not actor slots.
 * A caller must roll back the containing frame on task_supported == 0.
 * Script operations and callbacks below remain an explicit bounded whitelist. */
typedef unsigned char u8;
typedef unsigned int u16;
typedef unsigned long u32;
u8 rom8(u8 region,u32 offset);
u8 task_shared[65536],task_rng_tainted,task_audio_tainted,task_visual_tainted;
/* Unknown source timing-dependent state cannot feed script or native logic. */
u8 task_readable(u16 at,u16 length) {
 u32 end;
 if(!length)return 0U;
 end=(u32)at+(u32)length-1UL;
 if(end>65535UL)return 0U;
 if(task_rng_tainted && at<=7428U && end>=7428UL)return 0U;
 if(task_audio_tainted && at<=7424U && end>=7420UL)return 0U;
 if(task_visual_tainted) {
  if(at<=0x0205U && end>=0x0204UL)return 0U;
  if(at<=0x0cf3U && end>=0x0ce8UL)return 0U;
  if(at<=0x022dU && end>=0x0226UL)return 0U;
  if(at<=0x14cbU && end>=0x1474UL)return 0U;
  if(at<=0x157fU && end>=0x157eUL)return 0U;
  if(at<=0x2adfU && end>=0x2300UL)return 0U;
 }
 return 1U;
}
u16 task_wait[48],task_link[48],task_flags[48],task_delay[48];
u16 task_index,task_signal_mask,task_vm_resume_value;
u8 task_vm_resume_known;
u8 task_supported,task_ready;
void shadowrun_snes_task_signal_mask(u8 unused) {
 u16 cursor,i,n;
 task_supported=0U;
 cursor=task_index;
 if(cursor&32768U) {task_supported=1U;return;}
 /* Source follows negative-wait links. Limit and validate before any write. */
 for(n=0U;n<48U;n+=1U) {
  if((cursor&1U) || cursor>=96U)return;
  i=cursor>>1;
  if(!(task_wait[i]&32768U)) {
   task_flags[i]|=task_signal_mask;
   task_supported=1U;return;
  }
  cursor=task_link[i];
 }
}
void shadowrun_snes_task_signal(u8 unused) {
 task_signal_mask=4U;shadowrun_snes_task_signal_mask(0U);
}
void shadowrun_snes_task_check(u8 unused) {
 u16 i,wait,matched,delay;
 task_supported=0U;task_ready=0U;task_vm_resume_known=0U;
 if((task_index&1U) || task_index>=96U)return;
 i=task_index>>1;wait=task_wait[i];
 if(!wait) {task_ready=1U;task_supported=1U;return;}
 if(wait&32768U) {task_supported=1U;return;}
 if(wait&4096U) {task_supported=1U;return;}
 matched=(wait&28670U)&task_flags[i];
 if(wait&1U) {
  delay=task_delay[i]-1U;task_delay[i]=delay;
  if(!delay)matched|=1U;
 }
 task_shared[0U]=(u8)matched;task_shared[1U]=(u8)(matched>>8);
 if(matched) {task_wait[i]=0U;task_ready=1U;
  task_vm_resume_value=matched;task_vm_resume_known=1U;}
 task_supported=1U;
}

/* $80:C76C/$C771 consume source parameters in game units and seed the
 * coordinate controller. This is a setter only; it does not execute a script. */
u16 task_command_control,task_command_x,task_command_y,task_command_timer;
u16 task_command_arg_x,task_command_arg_y;
u8 task_command_kind,task_command_supported;
void shadowrun_snes_task_set_coordinate(u8 unused) {
 task_command_supported=0U;
 if(task_command_kind>1U)return;
 task_command_control=task_command_kind;
 task_command_x=task_command_arg_x<<2;
 task_command_y=task_command_arg_y<<2;
 task_command_timer=1U;
 task_command_supported=1U;
}

/* $80:F342/F353/F495/F4D3 restricted interpreter. Task frame bytes cover
 * the source heap $03F2-$0BBD; code remains in hash-bound external ROM.
 * Callback yields preserve PC/stack; the caller must execute the indicated
 * source operation against shared state before resuming. Status 1 is a source
 * wait, 2 requests a native callback, 4 is script return, 5 requests a
 * child task, 0 refuses, and 3 is an instruction-budget stop.
 * Any status 0/3 requires rollback of the containing transaction. */
u8 task_heap_first_header[4],task_heap[1996];
u16 task_frame[48],task_callback[48],task_next[48];
u16 task_list_head,task_list_free,task_list_current,task_return_value;
u16 task_vm_pc,task_vm_sp,task_vm_fault_pc;
u8 task_vm_fault_op,task_vm_fault_fn;
u16 task_vm_arg0,task_vm_arg1,task_vm_arg2,task_vm_arg3,task_vm_arg4,task_vm_arg5,task_vm_arg6,task_vm_arg7;
u16 task_callback_result,task_vm_pending_task;
u8 task_vm_status,task_vm_callback,task_vm_pending,task_callback_success,task_vm_return,task_vm_argc;
u8 task_vm_resume[48],task_vm_child_args[256];
u16 task_vm_child_id,task_vm_child_argc;
u16 task_heap_read16(u16 a) {
 return (u16)((u16)task_heap[a-1010U]|((u16)task_heap[a-1009U]<<8));
}
void task_heap_write16(u16 a,u16 v) {
 task_heap[a-1010U]=(u8)v;task_heap[a-1009U]=(u8)(v>>8);
}
void shadowrun_snes_task_vm(u8 unused) {
 u16 frame,pc,sp,code,bank,index,steps,op,v,a,b,argc,fn;
 u32 offset;
 task_vm_status=0U;
 if(task_vm_pending || (task_index&1U) || task_index>=96U)return;
 index=task_index>>1;frame=task_frame[index];
 if(frame<1010U || frame>2987U)return;
 code=task_heap_read16(frame);
 bank=task_heap[frame-1008U];
 if((bank&127U)>31U || code<32768U)return;
 pc=task_heap_read16(frame+3U);sp=task_heap_read16(frame+7U);
 if(sp<1011U || sp>3004U)return;
 if(task_vm_resume[index]==2U || task_vm_resume[index]>3U)return;
 if(task_vm_resume[index]==3U) {
  /* Child returns through $F45F; $E468 decides whether to push its result. */
  a=task_heap_read16(frame+9U);
  if(a>=936U)return;
  if(rom8(0U,91240UL+(u32)a)) {
   if(sp<1012U)return;
   task_heap_write16(sp-1U,task_return_value);sp-=2U;
  }
  task_vm_resume[index]=0U;
 }
 if(task_vm_resume[index]==1U) {
  if((u32)code+(u32)pc>=65536UL)return;
  offset=((u32)(bank&127U)<<15)+(u32)(code&32767U)+(u32)pc;
  /* Unknown direct-page $00 is harmless only when the next source op
   * discards the returned word without examining it. */
  if(!task_vm_resume_known && rom8(0U,offset)!=188U)return;
  if(sp<1012U)return;
  task_heap_write16(sp-1U,task_vm_resume_value);sp-=2U;
  task_vm_resume[index]=0U;
 }
 for(steps=0U;steps<256U;steps+=1U) {
  if((u32)code+(u32)pc>=65536UL)return;
  offset=((u32)(bank&127U)<<15)+(u32)(code&32767U)+(u32)pc;
  op=rom8(0U,offset);task_vm_fault_pc=pc;task_vm_fault_op=(u8)op;
  task_vm_fault_fn=0U;pc+=1U;
  if(op==188U) {
   if(sp>3003U)return;
   sp+=2U;
  } else if(op==192U || op==194U || op==0U || op==2U || op==10U || op==12U || op==20U || op==22U) {
   if(sp<1012U)return;
   v=0U;
   if(op==194U) {
    if(frame+19U>=3006U)return;
    v=task_heap[frame-991U];
   }
   if(op==2U || op==12U || op==22U) {
    if((u32)code+(u32)pc>=65536UL)return;
    a=(u16)rom8(0U,offset+1UL);pc+=1U;
    if((u32)frame+19UL+(u32)a>=3006UL)return;
    if(op==22U) {
     if((u32)frame+20UL+(u32)a>=3006UL)return;
     v=task_heap_read16(frame+19U+a);
    } else {
     v=task_heap[frame-991U+a];
     if(op==12U && (v&128U))v|=65280U;
    }
   }
   if(op==0U || op==10U || op==20U) {
    if((u32)code+(u32)pc>=65536UL)return;
    v=rom8(0U,offset+1UL);pc+=1U;
    if(op==10U && (v&128U))v|=65280U;
    if(op==20U) {
     if((u32)code+(u32)pc>=65536UL)return;
     v|=(u16)rom8(0U,offset+2UL)<<8;pc+=1U;
    }
   }
   task_heap_write16(sp-1U,v);sp-=2U;
  } else if(op==4U || op==14U || op==24U || op==46U || op==54U) {
   /* $F89E/$F8D9/$F8AE and $F8BB/$F8CC access fixed $7E WRAM. */
   if((u32)code+(u32)pc+1UL>=65536UL)return;
   a=(u16)((u16)rom8(0U,offset+1UL)|((u16)rom8(0U,offset+2UL)<<8));pc+=2U;
   if((op==24U || op==54U) && a==65535U)return;
   if(op==46U || op==54U) {
    if(sp>3003U)return;
    v=task_heap_read16(sp+1U);sp+=2U;
    task_shared[a]=(u8)v;if(op==54U)task_shared[a+1U]=(u8)(v>>8);
   } else {
    if(sp<1012U)return;
    if(op==24U) {if(!task_readable(a,2U))return;}
    else if(!task_readable(a,1U))return;
    v=task_shared[a];
    if(op==24U)v|=(u16)task_shared[a+1U]<<8;
    if(op==14U && (v&128U))v|=65280U;
    task_heap_write16(sp-1U,v);sp-=2U;
   }
  } else if(op==44U || op==52U) {
   /* $F390/$F3A1: store byte/word in frame local indexed by ROM. */
   if(sp>3003U || (u32)code+(u32)pc>=65536UL)return;
   a=(u16)rom8(0U,offset+1UL);pc+=1U;
   if((u32)frame+19UL+(u32)a>=3006UL)return;
   if(op==52U && (u32)frame+20UL+(u32)a>=3006UL)return;
   v=task_heap_read16(sp+1U);sp+=2U;
   if(op==44U)task_heap[frame-991U+a]=(u8)v;
   else task_heap_write16(frame+19U+a,v);
  } else if(op==68U || op==70U) {
   if(sp>3003U || (u32)code+(u32)pc+1UL>=65536UL)return;
   v=task_heap_read16(sp+1U);sp+=2U;
   a=(u16)((u16)rom8(0U,offset+1UL)|((u16)rom8(0U,offset+2UL)<<8));
   if((op==68U && v) || (op==70U && !v))pc+=2U;else pc=a;
  } else if(op==72U) {
   /* $F406: absolute bytecode-PC jump. */
   if((u32)code+(u32)pc+1UL>=65536UL)return;
   pc=(u16)((u16)rom8(0U,offset+1UL)|((u16)rom8(0U,offset+2UL)<<8));
  } else if(op==76U) {
   /* $F40C: branch to source subroutine, pushing return PC on frame stack. */
   if((u32)code+(u32)pc+1UL>=65536UL)return;
   a=(u16)((u16)rom8(0U,offset+1UL)|((u16)rom8(0U,offset+2UL)<<8));pc+=2U;
   b=task_heap_read16(frame+5U);
   if(b<1012U || b>3004U)return;
   task_heap_write16(b,pc);task_heap_write16(frame+5U,b-2U);pc=a;
  } else if(op==80U) {
   /* $F41E: restore return PC from the frame's private call stack. */
   b=task_heap_read16(frame+5U);
   if(b<1008U || b>3002U)return;
   b+=2U;pc=task_heap_read16(b);task_heap_write16(frame+5U,b);
  } else if(op==186U) {
   if(sp<1012U || sp>3003U)return;
   v=task_heap_read16(sp+1U);task_heap_write16(sp-1U,v);sp-=2U;
  } else if(op==190U) {
   if(sp>3003U)return;
   v=task_heap_read16(sp+1U);
   if(v)task_heap_write16(sp+1U,65535U);
  } else if(op==154U) {
   /* $F786: unsigned top stack word less than the following word. */
   if(sp>3001U)return;
   a=task_heap_read16(sp+1U);b=task_heap_read16(sp+3U);v=0U;
   if(a<b)v=65535U;
   task_heap_write16(sp+3U,v);sp+=2U;
  } else if(op==170U) {
   /* $F80D: source equality returns $FFFF or zero. */
   if(sp>3001U)return;
   a=task_heap_read16(sp+1U);b=task_heap_read16(sp+3U);v=0U;
   if(a==b)v=65535U;
   task_heap_write16(sp+3U,v);sp+=2U;
  } else if(op==132U) {
   /* $F6F7: invert the top 16-bit stack word. */
   if(sp>3003U)return;
   v=task_heap_read16(sp+1U);task_heap_write16(sp+1U,v^65535U);
  } else if(op==138U) {
   /* $F6FF: unsigned comparison after decrement, preserving 16-bit wrap. */
   if(sp>3001U)return;
   a=task_heap_read16(sp+1U);b=task_heap_read16(sp+3U);a-=1U;
   v=0U;if(a>=b)v=65535U;
   task_heap_write16(sp+3U,v);sp+=2U;
  } else if(op==128U || op==126U) {
   if(sp>3001U)return;
   a=task_heap_read16(sp+1U);b=task_heap_read16(sp+3U);
   if(op==128U)v=a|b;else v=a&b;
   task_heap_write16(sp+3U,v);sp+=2U;
  } else if(op==82U) {
   /* $F42A: suspend parent and expose the real child ID/stack arguments. */
   if((u32)code+(u32)pc+1UL>=65536UL)return;
   a=(u16)((u16)rom8(0U,offset+1UL)|((u16)rom8(0U,offset+2UL)<<8));pc+=2U;
   if(a>=936U)return;
   argc=(u16)rom8(0U,92176UL+(u32)a);
   if((argc&1U) || (u32)sp+(u32)argc>3004UL)return;
   task_vm_child_id=a;task_vm_child_argc=argc;
   for(b=0U;b<argc;b+=2U) {
    v=task_heap_read16(sp+1U);sp+=2U;
    task_vm_child_args[b]=(u8)v;task_vm_child_args[b+1U]=(u8)(v>>8);
    task_shared[b]=(u8)v;task_shared[b+1U]=(u8)(v>>8);
   }
   task_heap_write16(frame+3U,pc);task_heap_write16(frame+7U,sp);
   task_heap_write16(frame+9U,a);task_vm_pc=pc;task_vm_sp=sp;
   task_vm_status=5U;return;
  } else if(op==86U) {
   if(sp>3003U)return;
   task_return_value=task_heap_read16(sp+1U);
   task_vm_pc=pc;task_vm_sp=sp+2U;task_vm_status=4U;return;
  } else if(op==88U) {
   if((u32)code+(u32)pc>=65536UL)return;
   fn=rom8(0U,offset+1UL);task_vm_fault_fn=(u8)fn;pc+=1U;
   /* $F495/F4E7 use source ROM metadata for argument-word count and return. */
   argc=(u16)rom8(0U,88213UL+(u32)fn);
   if(argc>8U || (u32)sp+(u32)(argc<<1)>3004UL)return;
   task_vm_argc=(u8)argc;
   task_vm_arg0=0U;task_vm_arg1=0U;task_vm_arg2=0U;task_vm_arg3=0U;
   task_vm_arg4=0U;task_vm_arg5=0U;task_vm_arg6=0U;task_vm_arg7=0U;
   if(argc>0U) {task_vm_arg0=task_heap_read16(sp+1U);sp+=2U;}
   if(argc>1U) {task_vm_arg1=task_heap_read16(sp+1U);sp+=2U;}
   if(argc>2U) {task_vm_arg2=task_heap_read16(sp+1U);sp+=2U;}
   if(argc>3U) {task_vm_arg3=task_heap_read16(sp+1U);sp+=2U;}
   if(argc>4U) {task_vm_arg4=task_heap_read16(sp+1U);sp+=2U;}
   if(argc>5U) {task_vm_arg5=task_heap_read16(sp+1U);sp+=2U;}
   if(argc>6U) {task_vm_arg6=task_heap_read16(sp+1U);sp+=2U;}
   if(argc>7U) {task_vm_arg7=task_heap_read16(sp+1U);sp+=2U;}
   if(argc>0U) {task_shared[0U]=(u8)task_vm_arg0;task_shared[1U]=(u8)(task_vm_arg0>>8);}
   if(argc>1U) {task_shared[2U]=(u8)task_vm_arg1;task_shared[3U]=(u8)(task_vm_arg1>>8);}
   if(argc>2U) {task_shared[4U]=(u8)task_vm_arg2;task_shared[5U]=(u8)(task_vm_arg2>>8);}
   if(argc>3U) {task_shared[6U]=(u8)task_vm_arg3;task_shared[7U]=(u8)(task_vm_arg3>>8);}
   if(argc>4U) {task_shared[8U]=(u8)task_vm_arg4;task_shared[9U]=(u8)(task_vm_arg4>>8);}
   if(argc>5U) {task_shared[10U]=(u8)task_vm_arg5;task_shared[11U]=(u8)(task_vm_arg5>>8);}
   if(argc>6U) {task_shared[12U]=(u8)task_vm_arg6;task_shared[13U]=(u8)(task_vm_arg6>>8);}
   if(argc>7U) {task_shared[14U]=(u8)task_vm_arg7;task_shared[15U]=(u8)(task_vm_arg7>>8);}
   /* Zero/negative wait flags take different scheduler edges. */
   if(fn==158U && (!task_vm_arg0 || (task_vm_arg0&32768U)))return;
   task_heap_write16(frame+3U,pc);task_heap_write16(frame+7U,sp);
   task_heap_write16(frame+9U,fn);
   task_vm_pc=pc;task_vm_sp=sp;
   if(fn==158U) {
    task_wait[index]=task_vm_arg0;task_delay[index]=task_vm_arg1;
    task_flags[index]=0U;task_callback[index]=62674U;task_vm_resume[index]=1U;task_vm_status=1U;return;
   }
   task_vm_callback=(u8)fn;task_vm_pending=1U;task_vm_pending_task=task_index;
   task_vm_return=0U;if(rom8(0U,87994UL+(u32)fn))task_vm_return=1U;
   task_vm_status=2U;return;
  } else return;
 }
 task_vm_status=3U;
}
/* Caller uses this only after its shared-state handler completed the callback. */
void shadowrun_snes_task_callback_complete(u8 unused) {
 u16 frame,sp;
 if(!task_vm_pending || !task_callback_success || task_vm_pending_task!=task_index ||
    (task_index&1U) || task_index>=96U)return;
 if(task_vm_return) {
  frame=task_frame[task_index>>1];
  if(frame<1010U || frame>2997U)return;
  sp=task_heap_read16(frame+7U);
  if(sp<1012U || sp>3004U)return;
  task_shared[0U]=(u8)task_callback_result;task_shared[1U]=(u8)(task_callback_result>>8);
  task_heap_write16(sp-1U,task_callback_result);sp-=2U;
  task_heap_write16(frame+7U,sp);
 }
 task_vm_pending=0U;task_callback_success=0U;task_vm_return=0U;
}

/* Source callbacks use the caller's coherent WRAM byte view. D12C is left
 * pending for the actor adapter, which owns A912/AA3C and their state. */
u8 task_native_supported,task_audio_count;
u16 task_audio_actor[64],task_audio_id[64],task_audio_volume[64],task_audio_mode[64];
void shadowrun_snes_task_native(u8 unused) {
 u16 actor,ptr,at,sample,previous,other,dx,dy,base,bank,waypoint,carry;u8 commands;u32 offset;
 task_native_supported=0U;
 if(!task_vm_pending || task_vm_pending_task!=task_index ||
    (task_index&1U) || task_index>=96U)return;
 if(task_vm_callback==2U || task_vm_callback==8U || task_vm_callback==10U || task_vm_callback==40U || task_vm_callback==79U || task_vm_callback==87U || task_vm_callback==186U || task_vm_callback==195U || task_vm_callback==197U) {
  if(task_vm_return!=1U)return;
 } else if(task_vm_return)return;
 task_callback_result=0U;
 if(task_vm_callback==116U) {
  /* $CBC7: set the source item record's reference word. */
  if(task_vm_argc!=2U)return;
  offset=438322UL+(u32)task_vm_arg0;
  if(offset+1UL>=1048576UL)return;
  ptr=(u16)((u16)rom8(0U,offset)|((u16)rom8(0U,offset+1UL)<<8));
  if(ptr) {
   if(ptr>65531U)return;
   task_shared[ptr+3U]=(u8)task_vm_arg1;
   task_shared[ptr+4U]=(u8)(task_vm_arg1>>8);
  }
 } else if(task_vm_callback==38U) {
  /* $9D6F: add to the source item-record count byte, capped at six. */
  if(task_vm_argc!=2U)return;
  offset=438322UL+(u32)task_vm_arg0;
  if(offset+1UL>=1048576UL)return;
  ptr=(u16)((u16)rom8(0U,offset)|((u16)rom8(0U,offset+1UL)<<8));
  if(ptr) {
   if(ptr>65533U || !task_readable(ptr+2U,1U))return;
   sample=(u8)(task_shared[ptr+2U]+(u8)task_vm_arg1);
   if(sample>=7U)sample=6U;
   task_shared[ptr+2U]=(u8)sample;
  }
 } else if(task_vm_callback==40U) {
  /* $D15A: return the currently selected player actor slot. */
  if(task_vm_argc || !task_readable(0x0cdeU,2U))return;
  task_callback_result=(u16)((u16)task_shared[0x0cdeU]|((u16)task_shared[0x0cdfU]<<8));
 } else if(task_vm_callback==79U) {
  /* $A8E6: return the actor X coordinate in source game units. */
  actor=task_vm_arg0;
  if(task_vm_argc!=1U || (actor&1U) || actor>=88U)return;
  at=0x0e44U+actor;if(!task_readable(at,2U))return;
  task_callback_result=((u16)task_shared[at]|((u16)task_shared[at+1U]<<8))>>2;
 } else if(task_vm_callback==59U) {
  actor=task_vm_arg0;
  if((actor&1U) || actor>=88U)return;
  task_shared[16572U+actor]=0U;task_shared[16573U+actor]=0U;
 } else if(task_vm_callback==51U || task_vm_callback==122U || task_vm_callback==2U) {
  actor=task_vm_arg0;
  if((actor&1U) || actor>=88U)return;
  at=5060U+actor;ptr=(u16)((u16)task_shared[at]|((u16)task_shared[at+1U]<<8));
  if(ptr==65535U || !task_readable(ptr+1U,1U))return;
  if(task_vm_callback==2U) {
   task_callback_result=task_shared[ptr+1U];
  } else if(ptr) {
   if(task_vm_callback==51U)task_shared[ptr+1U]|=(u8)task_vm_arg1;
   else task_shared[ptr+1U]&=(u8)task_vm_arg1;
  }
 } else if(task_vm_callback==195U) {
  /* $E22C: Boolean query of the two shared dialogue-control words. */
  if(!task_readable(0x1da3U,2U) || !task_readable(0x1da5U,2U))return;
  previous=(u16)((u16)task_shared[0x1da3U]|((u16)task_shared[0x1da4U]<<8));
  previous|=(u16)((u16)task_shared[0x1da5U]|((u16)task_shared[0x1da6U]<<8));
  if(previous)task_callback_result=65535U;
 } else if(task_vm_callback==135U) {
  /* $DE48: reset the source player-control state; zero arguments. */
  task_shared[0x1d77U]=255U;task_shared[0x1d78U]=255U;
  task_shared[0x1d79U]=0U;task_shared[0x1d7aU]=0U;
  task_shared[0x1d7bU]=0U;task_shared[0x1d7cU]=0U;
  task_shared[0x1d81U]=0U;task_shared[0x1d82U]=0U;
  task_shared[0x1d87U]=0U;task_shared[0x1d88U]=0U;
  task_shared[0x1d89U]=0U;task_shared[0x1d8aU]=0U;
 } else if(task_vm_callback==121U) {
  /* $A8BC-$A8CB: set the three source velocity words, without moving. */
  actor=task_vm_arg0;
  if((actor&1U) || actor>=88U)return;
  at=3388U+actor;task_shared[at]=(u8)task_vm_arg1;task_shared[at+1U]=(u8)(task_vm_arg1>>8);
  at=3476U+actor;task_shared[at]=(u8)task_vm_arg2;task_shared[at+1U]=(u8)(task_vm_arg2>>8);
  at=3564U+actor;task_shared[at]=(u8)task_vm_arg3;task_shared[at+1U]=(u8)(task_vm_arg3>>8);
 } else if(task_vm_callback==8U) {
  /* $CA19: source actor's entity record byte at offset two. */
  actor=task_vm_arg0;
  if((actor&1U) || actor>=88U)return;
  at=5060U+actor;ptr=(u16)((u16)task_shared[at]|((u16)task_shared[at+1U]<<8));
  if(ptr>65533U || !task_readable(ptr+2U,1U))return;
  task_callback_result=task_shared[ptr+2U];
 } else if(task_vm_callback==186U) {
  /* $CAFB: return byte 1 from a source entity record. */
  offset=438322UL+(u32)task_vm_arg0;
  if(offset+1UL>=1048576UL)return;
  ptr=(u16)((u16)rom8(0U,offset)|((u16)rom8(0U,offset+1UL)<<8));
  if(ptr==65535U || !task_readable(ptr+1U,1U))return;
  task_callback_result=task_shared[ptr+1U];
 } else if(task_vm_callback==87U) {
  /* $CBD7: read the source-indexed $7E:3BBB word. */
  if(task_vm_arg0>50243U)return;
  at=15291U+task_vm_arg0;
  if(!task_readable(at,2U))return;
  task_callback_result=(u16)((u16)task_shared[at]|((u16)task_shared[at+1U]<<8));
 } else if(task_vm_callback==18U) {
  /* $CBE0: write the source-indexed $7E:3BBB word. */
  if(task_vm_arg0>50243U)return;
  at=15291U+task_vm_arg0;
  task_shared[at]=(u8)task_vm_arg1;task_shared[at+1U]=(u8)(task_vm_arg1>>8);
 } else if(task_vm_callback==111U || task_vm_callback==196U || task_vm_callback==197U) {
  /* $9CED stores the party entity; $9CFD stores $1538; $9D1B tests it. */
  actor=task_vm_arg0;
  if(task_vm_callback==111U && task_vm_argc!=1U)return;
  if((actor&1U) || actor>=88U)return;
  at=5060U+actor;ptr=(u16)((u16)task_shared[at]|((u16)task_shared[at+1U]<<8));
  if(ptr>65531U)return;
  if(ptr) {
   if(task_vm_callback==111U) {
    if(!task_readable(0x2df0U,2U))return;
    previous=(u16)((u16)task_shared[0x2df0U]|((u16)task_shared[0x2df1U]<<8));
    task_shared[ptr+3U]=(u8)previous;task_shared[ptr+4U]=(u8)(previous>>8);
   } else if(task_vm_callback==196U) {
    task_shared[ptr+3U]=56U;task_shared[ptr+4U]=21U;
   } else {
    if(!task_readable(ptr+3U,2U))return;
    previous=(u16)((u16)task_shared[ptr+3U]|((u16)task_shared[ptr+4U]<<8));
    if(!(previous&32768U))task_callback_result=65535U;
   }
  }
 } else if(task_vm_callback==206U || task_vm_callback==44U) {
  /* $C9E5/$C9F0 OR/AND the actor's $1474 flags word. */
  actor=task_vm_arg0;
  if((actor&1U) || actor>=88U)return;
  at=5236U+actor;
  previous=(u16)((u16)task_shared[at]|((u16)task_shared[at+1U]<<8));
  if(task_vm_callback==206U)previous|=task_vm_arg1;else previous&=task_vm_arg1;
  task_shared[at]=(u8)previous;task_shared[at+1U]=(u8)(previous>>8);
 } else if(task_vm_callback==29U || task_vm_callback==128U || task_vm_callback==181U) {
  /* $C68F/$C694: resolve source waypoint index through live $F3 pointer. */
  actor=task_vm_arg0;waypoint=task_vm_arg1;
  if((actor&1U) || actor>=88U)return;
  base=(u16)((u16)task_shared[243U]|((u16)task_shared[244U]<<8));
  bank=(u16)task_shared[245U];
  if((bank&127U)>31U || base<32768U)return;
  at=(u16)(waypoint<<3);carry=0U;if(at>=waypoint)carry=1U;
  at-=waypoint;at=(u16)(at-waypoint-(1U-carry));at+=1U;
  if((u32)base+(u32)at+3UL>=65536UL)return;
  if(task_vm_callback==181U && (u32)base+(u32)at+5UL>=65536UL)return;
  offset=((u32)(bank&127U)<<15)+(u32)(base&32767U)+(u32)at;
  dx=(u16)((u16)rom8(0U,offset)|((u16)rom8(0U,offset+1UL)<<8));
  dy=(u16)((u16)rom8(0U,offset+2UL)|((u16)rom8(0U,offset+3UL)<<8));
  dx<<=2;dy<<=2;
  if(task_vm_callback==181U) {
   previous=(u16)((u16)rom8(0U,offset+4UL)|((u16)rom8(0U,offset+5UL)<<8));
   previous<<=2;
   at=3652U+actor;task_shared[at]=(u8)dx;task_shared[at+1U]=(u8)(dx>>8);
   at=3740U+actor;task_shared[at]=(u8)dy;task_shared[at+1U]=(u8)(dy>>8);
   at=3828U+actor;task_shared[at]=(u8)previous;task_shared[at+1U]=(u8)(previous>>8);
   at=16572U+actor;task_shared[at]=0U;task_shared[at+1U]=0U;
  } else {
  at=16660U+actor;task_shared[at]=0U;
  if(task_vm_callback==29U)task_shared[at]=1U;
  task_shared[at+1U]=0U;
  at=16748U+actor;task_shared[at]=(u8)dx;task_shared[at+1U]=(u8)(dx>>8);
  at=16836U+actor;task_shared[at]=(u8)dy;task_shared[at+1U]=(u8)(dy>>8);
  at=16572U+actor;task_shared[at]=1U;task_shared[at+1U]=0U;
  }
 } else if(task_vm_callback==47U || task_vm_callback==185U) {
  /* $C76C/$C771: direct coordinate setter. */
  actor=task_vm_arg0;
  if((actor&1U) || actor>=88U)return;
  at=16660U+actor;task_shared[at]=0U;
  if(task_vm_callback==185U)task_shared[at]=1U;
  task_shared[at+1U]=0U;
  dx=task_vm_arg1<<2;dy=task_vm_arg2<<2;
  at=16748U+actor;task_shared[at]=(u8)dx;task_shared[at+1U]=(u8)(dx>>8);
  at=16836U+actor;task_shared[at]=(u8)dy;task_shared[at+1U]=(u8)(dy>>8);
  at=16572U+actor;task_shared[at]=1U;task_shared[at+1U]=0U;
 } else if(task_vm_callback==10U) {
  /* $C65D-C68E: maximum wrapped axis distance to the current player,
   * divided by four. Both actors and their positions are shared scene state. */
  actor=task_vm_arg0;
  other=(u16)((u16)task_shared[3294U]|((u16)task_shared[3295U]<<8));
  if((actor&1U) || actor>=88U)return;
  if(other!=65535U && ((other&1U) || other>=88U))return;
  at=3652U+actor;ptr=(u16)(3652U+other);
  dx=(u16)((u16)task_shared[at]|((u16)task_shared[at+1U]<<8));
  dx-=(u16)((u16)task_shared[ptr]|((u16)task_shared[ptr+1U]<<8));
  at=3740U+actor;ptr=(u16)(3740U+other);
  dy=(u16)((u16)task_shared[at]|((u16)task_shared[at+1U]<<8));
  dy-=(u16)((u16)task_shared[ptr]|((u16)task_shared[ptr+1U]<<8));
  if(dx&32768U)dx=0U-dx;
  if(dy&32768U)dy=0U-dy;
  if(dx>dy)dy=dx;
  task_callback_result=dy>>2;
 } else if(task_vm_callback==76U) {
  /* $C43E: retain the source latch and count emitted SPC commands, while
   * exporting a semantic request instead of driving the APU. Sample loads
   * requiring $81:F0F1, zero mode and event overflow remain unsupported. */
  if(task_audio_tainted || task_audio_count>=64U || !task_vm_arg3 || task_vm_arg1>=15228U)return;
  offset=17539UL+(u32)task_vm_arg1;
  sample=(u16)((u16)rom8(0U,offset)|((u16)rom8(0U,offset+1UL)<<8));
  if(sample&32768U)return;
  previous=(u16)((u16)task_shared[7422U]|((u16)task_shared[7423U]<<8));
  commands=2U;
  if(previous!=task_vm_arg3) {
   task_shared[7422U]=(u8)task_vm_arg3;task_shared[7423U]=(u8)(task_vm_arg3>>8);
   commands=3U;
  }
  task_shared[7424U]+=(u8)commands;
  at=task_audio_count;task_audio_actor[at]=task_vm_arg0;
  task_audio_id[at]=task_vm_arg1;task_audio_volume[at]=task_vm_arg2;
  task_audio_mode[at]=task_vm_arg3;task_audio_count+=1U;
 } else if(task_vm_callback==13U) {
  offset=438322UL+(u32)task_vm_arg0;
  if(offset+1UL>=1048576UL)return;
  ptr=(u16)((u16)rom8(0U,offset)|((u16)rom8(0U,offset+1UL)<<8));
  if(ptr==65535U)return;
  if(ptr && !task_readable(ptr+1U,1U))return;
  if(ptr)task_shared[ptr+1U]|=(u8)task_vm_arg1;
 } else return;
 task_callback_success=1U;shadowrun_snes_task_callback_complete(0U);
 if(!task_vm_pending)task_native_supported=1U;
}

/* $C366: unlink a completed task and release its source heap block.
 * Validate every identity before writing so invalid links refuse atomically. */
void shadowrun_snes_task_terminate(u8 unused) {
 u16 i,frame,next,prev;
 task_supported=0U;
 if(task_vm_status!=4U || (task_index&1U) || task_index>=96U)return;
 i=task_index>>1;frame=task_frame[i];next=task_next[i];prev=task_link[i];
 if(frame==1010U) {if(!(task_heap_first_header[1]&128U))return;}
 else {
  if(frame<1014U || frame>3005U)return;
  if(!(task_heap[frame-1013U]&128U))return;
 }
 if(next==task_index || prev==task_index)return;
 if(!(task_list_free&32768U) && ((task_list_free&1U) || task_list_free>=96U))return;
 if(!(next&32768U) && ((next&1U) || next>=96U))return;
 if(!(prev&32768U) && ((prev&1U) || prev>=96U))return;
 if(!(next&32768U) && task_link[next>>1]!=task_index)return;
 if(!(prev&32768U) && task_next[prev>>1]!=task_index)return;
 if((prev&32768U) && task_list_head!=task_index)return;
 if(frame==1010U)task_heap_first_header[1]&=127U;
 else task_heap[frame-1013U]&=127U;
 task_next[i]=task_list_free;task_list_free=task_index;
 if(task_list_current==task_index)task_list_current=next;
 if(!(next&32768U))task_link[next>>1]=prev;
 if(!(prev&32768U))task_next[prev>>1]=next;else task_list_head=next;
 task_shared[0U]=(u8)task_return_value;task_shared[1U]=(u8)(task_return_value>>8);
 task_supported=1U;
}

/* $80:BBEA-$BC05: source scene-entry input state, preserving $1D81. */
void shadowrun_snes_input_reset(u8 unused) {
 task_shared[0x01ecU]=0U;task_shared[0x01edU]=0U;
 task_shared[0x01eeU]=0U;task_shared[0x01efU]=0U;
 task_shared[0x01f0U]=0U;task_shared[0x01f1U]=128U;
 task_shared[0x01f2U]=0U;task_shared[0x01f3U]=128U;
 task_shared[0x01f4U]=0U;task_shared[0x01f5U]=0U;
 task_shared[0x0204U]=0U;task_shared[0x0205U]=0U;
 task_shared[0x01f6U]=255U;task_shared[0x01f7U]=255U;
}
