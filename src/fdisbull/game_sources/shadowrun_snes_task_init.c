/* $80:C176, C212-C28C, C298-C335. Append to the source task VM: the first
 * four heap bytes are separate because the existing task_heap starts at $03F2.
 * Failure is transactional. Allocation corruption/exhaustion, unsupported
 * ROM tables or argument layouts refuse rather than emulate unsafe writes. */
u8 task_init_args[256];
u16 task_init_script,task_init_result;
u8 task_init_supported;
u8 task_init_read(u16 offset) {
 if(offset<4U)return task_heap_first_header[offset];
 return task_heap[offset-4U];
}
void task_init_write(u16 offset,u8 value) {
 if(offset<4U)task_heap_first_header[offset]=value;
 else task_heap[offset-4U]=value;
}
u16 task_init_word(u16 offset) {
 return (u16)((u16)task_init_read(offset)|((u16)task_init_read(offset+1U)<<8));
}
void task_init_put_word(u16 offset,u16 value) {
 task_init_write(offset,(u8)value);task_init_write(offset+1U,(u8)(value>>8));
}
void shadowrun_snes_task_reset(u8 unused) {
 u16 i;
 task_list_free=0U;task_list_head=65535U;task_list_current=65535U;
 task_link[0]=65535U;
 for(i=0U;i<47U;i+=1U)task_next[i]=(i+1U)<<1;
 task_next[47]=65535U;
 task_init_put_word(0U,1996U);task_init_put_word(2U,0U);
 task_init_supported=1U;
}
void shadowrun_snes_task_create(u8 unused) {
 u16 id,slot,head,bank,code,argc,size,sum,offset,block,tail,next,merged;
 u16 n,frame,stack,newhead,oldnext,idx,active,prior;
 u32 addr;
 task_init_supported=0U;
 id=task_init_script;
 if(id>=936U)return;
 bank=(u16)rom8(0U,88432UL+(u32)id);
 addr=89368UL+((u32)id<<1);
 code=(u16)((u16)rom8(0U,addr)|((u16)rom8(0U,addr+1UL)<<8));
 argc=(u16)rom8(0U,92176UL+(u32)id);
 if((bank&127U)>31U || code<32768U || code>65533U || (argc&1U))return;
 addr=((u32)(bank&127U)<<15)+(u32)(code&32767U);
 sum=(u16)rom8(0U,addr)+(u16)rom8(0U,addr+1UL);
 size=(sum&255U)+23U;
 if(sum>255U)size+=1U;
 size&=255U;
 if(size<23U || argc>size-19U)return;
 slot=task_list_free;head=task_list_head;
 if((slot&1U) || slot>=96U)return;
 if(!(head&32768U) && ((head&1U) || head>=96U))return;
 active=head;prior=65535U;
 for(n=0U;n<48U;n+=1U) {
  if(active&32768U)break;
  if((active&1U) || active>=96U || active==slot || task_link[active>>1]!=prior)return;
  prior=active;active=task_next[active>>1];
 }
 if(!(active&32768U))return;
 oldnext=task_next[slot>>1];
 if(!(oldnext&32768U) && ((oldnext&1U) || oldnext>=96U || oldnext==slot))return;
 offset=0U;merged=0U;block=0U;tail=0U;next=0U;
 /* Check the whole candidate chain before changing headers. */
 for(n=0U;n<500U;n+=1U) {
  if(offset>1996U)return;
  block=task_init_word(offset);
  next=task_init_word(offset+2U);
  if((u32)offset+4UL+(u32)(block&32767U)>2000UL)return;
  if(next && ((u32)offset+4UL+(u32)(block&32767U)!=(u32)next))return;
  if(!(block&32768U)) {
   merged=block;tail=offset;
   for(idx=0U;idx<500U;idx+=1U) {
    if(merged>=size)break;
    next=task_init_word(tail+2U);
    if(!next)break;
    if(next>1996U)return;
    block=task_init_word(next);
    if((u32)next+4UL+(u32)(block&32767U)>2000UL)return;
    if(block&32768U)break;
    if((u32)merged+4UL+(u32)block>1996UL)return;
    merged+=block+4U;tail=next;
   }
   if(merged>=size)break;
  }
  next=task_init_word(offset+2U);
  if(!next)return;
  offset=next;
 }
 if(n==500U || merged<size)return;
 oldnext=task_init_word(tail+2U);
 frame=1010U+offset;
 if((u32)frame+(u32)size>3006UL)return;
 stack=frame+size-1U-argc;
 if(stack<frame+18U)return;
 /* Equivalent to merge, then split or mark the complete block allocated. */
 if(merged-size>=5U) {
  newhead=offset+size+4U;
  task_init_put_word(offset,(u16)(size|32768U));
  task_init_put_word(offset+2U,newhead);
  task_init_put_word(newhead,merged-size-4U);
  task_init_put_word(newhead+2U,oldnext);
 } else {
  task_init_put_word(offset,(u16)(merged|32768U));
  task_init_put_word(offset+2U,oldnext);
 }
 for(n=0U;n<argc;n+=1U)task_heap[stack+1U-1010U+n]=task_init_args[n];
 task_heap[frame-1010U]=(u8)(code+2U);
 task_heap[frame-1009U]=(u8)((code+2U)>>8);
 task_heap[frame-1008U]=(u8)bank;
 task_init_put_word(offset+7U,0U); /* frame + 3 */
 task_init_put_word(offset+9U,frame+17U); /* frame + 5 */
 task_init_put_word(offset+11U,stack); /* frame + 7 */
 task_callback[slot>>1]=0U;task_wait[slot>>1]=0U;
 task_vm_resume[slot>>1]=0U;
 task_list_free=task_next[slot>>1];task_frame[slot>>1]=frame;
 task_next[slot>>1]=head;task_link[slot>>1]=65535U;
 if(!(head&32768U))task_link[head>>1]=slot;
 task_list_head=slot;task_init_result=slot;
 /* Observable direct-page/table and allocator scratch from $C29C-C2C8. */
 task_shared[113U]=(u8)code;task_shared[114U]=(u8)(code>>8);
 task_shared[115U]=(u8)bank;
 task_shared[116U]=(u8)frame;task_shared[117U]=(u8)(frame>>8);
 task_shared[610U]=(u8)size;task_shared[611U]=(u8)(size>>8);
 task_shared[612U]=(u8)argc;task_shared[613U]=(u8)(argc>>8);
 task_shared[614U]=(u8)size;task_shared[615U]=(u8)(size>>8);
 task_init_supported=1U;
}

/* $C33A: allocate the requested child and insert it just before the current
 * parent. Parent becomes redirected until the scheduler completes the child. */
void shadowrun_snes_task_create_child(u8 unused) {
 u16 parent,prev,head,child,i;
 task_init_supported=0U;
 parent=task_index;head=task_list_head;
 if(task_vm_status!=5U || parent!=task_list_current || (parent&1U) || parent>=96U)return;
 if(task_vm_child_id>=936U || task_vm_child_argc>255U || (task_vm_child_argc&1U))return;
 if((u16)rom8(0U,92176UL+(u32)task_vm_child_id)!=task_vm_child_argc)return;
 prev=task_link[parent>>1];
 if(prev&32768U) {if(head!=parent)return;}
 else if((prev&1U) || prev>=96U || task_next[prev>>1]!=parent)return;
 if((head&1U) || head>=96U || task_link[head>>1]!=65535U)return;
 task_init_script=task_vm_child_id;
 for(i=0U;i<task_vm_child_argc;i+=1U)task_init_args[i]=task_vm_child_args[i];
 shadowrun_snes_task_create(0U);
 if(!task_init_supported)return;
 child=task_init_result;
 /* Undo the temporary root prepend, then apply the observed insertion. */
 task_list_head=head;task_link[head>>1]=65535U;
 task_next[child>>1]=parent;task_link[child>>1]=prev;
 task_link[parent>>1]=child;
 if(prev&32768U)task_list_head=child;else task_next[prev>>1]=child;
 task_wait[parent>>1]=65535U;task_callback[parent>>1]=62558U;
 task_vm_resume[parent>>1]=3U;
}
