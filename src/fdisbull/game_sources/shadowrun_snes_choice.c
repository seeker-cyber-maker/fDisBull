/* Bounded logical projection of $80:996E and $80:A632-A7C1.
 * The containing program supplies task_shared and owns window rendering.
 * Status: 0 refused, 1 waiting for a source input poll, 2 final same-input
 * poll due, 3 selected, 4 cancelled, 5 no actionable entries. The final
 * poll may see a new NMI-published held word while drawing or sound runs.
 * A refusal
 * requires the caller to roll back its containing transaction. */
u16 choice_mask,choice_input,choice_event;
u8 choice_status,choice_count,choice_cancelled;
u16 choice_get(u16 a) {
 return (u16)((u16)task_shared[a]|((u16)task_shared[a+1U]<<8));
}
void choice_put(u16 a,u16 v) {
 task_shared[a]=(u8)v;task_shared[a+1U]=(u8)(v>>8);
}
void choice_entry(u16 n,u16 label,u16 hotkey,u16 event) {
 choice_put(0x1f86U+n*2U,label);
 choice_put(0x1f9eU+n*2U,hotkey);
 choice_put(0x1fb4U+n*2U,event);
}
void shadowrun_snes_choice_begin(u8 unused) {
 u16 mask,n;
 choice_status=0U;choice_event=0U;choice_count=0U;choice_cancelled=0U;
 mask=choice_get(0x1fc2U);
 if(!mask)mask=choice_mask;
 if(mask&0x980dU)return;
 n=1U;
 if(mask&0x0080U)n+=1U;
 if(mask&0x0010U)n+=1U;
 if(mask&0x0002U)n+=1U;
 if(mask&0x0020U)n+=1U;
 if(mask&0x0040U)n+=1U;
 if(mask&0x0100U)n+=1U;
 if(mask&0x0600U)n+=1U;
 if(mask&0x2000U)n+=1U;
 if(mask&0x4000U)n+=1U;
 /* Scrolling and its renderer are outside this bounded component. */
 if(n>8U)return;
 choice_put(0x0065U,mask);
 choice_entry(0U,0x70c8U,0U,0U);n=1U;
 if(mask&0x0080U) {choice_entry(n,0x7117U,0x0020U,0x0080U);n+=1U;}
 if(mask&0x0010U) {choice_entry(n,0x7104U,0x0010U,0x0010U);n+=1U;}
 if(mask&0x0002U) {choice_entry(n,0x70ccU,0U,0x0002U);n+=1U;}
 if(mask&0x0020U) {choice_entry(n,0x7110U,0U,0x0020U);n+=1U;}
 if(mask&0x0040U) {choice_entry(n,0x7113U,0U,0x0040U);n+=1U;}
 if(mask&0x0100U) {choice_entry(n,0x7121U,0U,0x0100U);n+=1U;}
 if((mask&0x0600U)==0x0600U) {choice_entry(n,0x7147U,0U,0x0600U);n+=1U;}
 else if(mask&0x0200U) {choice_entry(n,0x7124U,0x0010U,0x0200U);n+=1U;}
 else if(mask&0x0400U) {choice_entry(n,0x712fU,0x0010U,0x0400U);n+=1U;}
 if(mask&0x2000U) {choice_entry(n,0x713bU,0U,0x2000U);n+=1U;}
 if(mask&0x4000U) {choice_entry(n,0x7141U,0U,0x4000U);n+=1U;}
 choice_count=(u8)n;
 if(n==1U) {choice_status=5U;return;}
 choice_put(0x1f86U+n*2U,0U);
 choice_put(0x1dc3U,0xffffU);choice_put(0x1dc1U,0U);
 choice_put(0x1db3U,0U);choice_put(0x1db1U,0U);
 choice_put(0x1dbdU,0U);choice_put(0x1db5U,1U);choice_put(0x1db7U,0U);
 choice_status=1U;
}
void shadowrun_snes_choice_poll(u8 unused) {
 u16 held,old,edge,repeat,move,at,i,hot;
 if(choice_status!=1U) {choice_status=0U;return;}
 held=choice_input;
 /* $9D9D has a separate reset chord whose side effects are not projected. */
 if((held&0x000fU) || ((held&0x3030U)==0x3030U)) {choice_status=0U;return;}
 old=choice_get(0x01e8U);edge=(held^old)&held;
 choice_put(0x01e6U,held);choice_put(0x01e8U,held);choice_put(0x01eaU,edge);
 choice_put(0x1dbfU,edge);repeat=choice_get(0x1dbdU);
 if(held&0x0c00U) {
  repeat+=1U;
  if(repeat==20U) {repeat=19U;choice_put(0x1dbfU,held);}
 } else repeat=0U;
 choice_put(0x1dbdU,repeat);
 if(edge&0x2000U) {choice_event=0U;choice_cancelled=1U;choice_status=2U;return;}
 at=choice_get(0x1db3U);
 if((at&1U) || at>=((u16)choice_count*2U)) {choice_status=0U;return;}
 if(edge&0xd0c0U) {choice_event=choice_get(0x1fb4U+at);choice_status=2U;return;}
 move=choice_get(0x1dbfU);
 if(move&0x0400U) {if(at+2U<((u16)choice_count*2U))at+=2U;}
 else if(move&0x0800U) {if(at>=2U)at-=2U;}
 choice_put(0x1db3U,at);
 if(choice_get(0x1dc3U)) {
  for(i=0U;i<(u16)choice_count;i+=1U) {
   hot=choice_get(0x1f9eU+i*2U);
   if(hot&edge) {choice_put(0x1db3U,i*2U);choice_event=choice_get(0x1fb4U+i*2U);choice_status=2U;return;}
  }
 }
}
void shadowrun_snes_choice_finish(u8 unused) {
 u16 held,old;
 if(choice_status!=2U) {choice_status=0U;return;}
 held=choice_input;
 if((held&0x000fU) || ((held&0x3030U)==0x3030U)) {choice_status=0U;return;}
 old=choice_get(0x01e8U);choice_put(0x01e6U,held);
 choice_put(0x01eaU,(held^old)&held);choice_put(0x01e8U,held);
 if(choice_cancelled)choice_status=4U;else choice_status=3U;
}
