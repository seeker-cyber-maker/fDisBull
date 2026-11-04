/* Bounded logical projection of $80:9123 and $80:908C. The caller owns
 * the conversation window, sound, text rendering and optional child task.
 * Status 0 refuses, 1 selects an entry, 2 finds no entry or fallback. */
u16 dialogue_record,dialogue_selector,dialogue_text,dialogue_script;
u8 dialogue_status,dialogue_has_script,dialogue_keyword_count;
u8 dialogue_added_count,dialogue_last_keyword,dialogue_skip_known,dialogue_skip_length,dialogue_fallback;
u8 dialogue_no_fallback;
u8 dialogue_keywords[256];
void shadowrun_snes_dialogue_entry(u8 unused) {
 u16 i,j,n,pos,first,limit,selector,control,count,key,at,script,text,needed;
 u8 found;
 u32 base;
 dialogue_status=0U;dialogue_has_script=0U;dialogue_added_count=0U;dialogue_skip_known=0U;dialogue_fallback=0U;
 if(dialogue_record<0x8000U || dialogue_record>0xfffbU)return;
 base=(13UL<<15)+(u32)(dialogue_record&0x7fffU);
 /* The source keyword list is ascending, unique and $FF terminated. */
 n=0U;
 for(i=0U;i<255U;i+=1U) {
  key=task_shared[0x3ca3U+i];
  if(key==255U)break;
  if(n && key<=dialogue_keywords[n-1U])return;
  dialogue_keywords[n]=(u8)key;n+=1U;
 }
 if(i==255U)return;
 selector=dialogue_selector&255U;found=0U;
 for(j=0U;j<2U;j+=1U) {
  pos=4U;
  for(i=0U;i<256U;i+=1U) {
   if((u32)dialogue_record+(u32)pos>65535UL)return;
   key=rom8(0U,base+pos);
   if(key==0xf8U)break;
   if((u32)dialogue_record+(u32)pos+1UL>65535UL)return;
   limit=(u16)rom8(0U,base+pos+1U);
   if(!limit || (u32)dialogue_record+(u32)pos+1UL+(u32)limit>65535UL)return;
   if(key==selector) {found=1U;break;}
   dialogue_skip_known=1U;dialogue_skip_length=(u8)limit;pos+=1U+limit;
  }
  if(i==256U)return;
  if(found)break;
  if(dialogue_no_fallback)break;
  if(selector==0xfdU)break;
  selector=0xfdU;dialogue_fallback=1U;
 }
 if(!found) {dialogue_status=2U;return;}
 first=pos+2U;limit=pos+1U+limit;
 if(first>=limit)return;
 control=rom8(0U,base+first);count=control&15U;at=first+1U;
 needed=2U;if(control&128U)needed+=2U;
 if((u32)at+(u32)count+(u32)needed>(u32)limit)return;
 for(i=0U;i<count;i+=1U) {
  key=rom8(0U,base+at+i);
  dialogue_last_keyword=(u8)key;
  if(key==255U)return;
  for(j=0U;j<n;j+=1U) {if(dialogue_keywords[j]>=key)break;}
  if(j<n && dialogue_keywords[j]==key)continue;
  if(n>=254U)return;
  for(pos=n;pos>j;pos-=1U)dialogue_keywords[pos]=dialogue_keywords[pos-1U];
  dialogue_keywords[j]=(u8)key;n+=1U;
 }
 at+=count;script=0U;
 if(control&128U) {
  script=(u16)((u16)rom8(0U,base+at)|((u16)rom8(0U,base+at+1U)<<8));at+=2U;
 }
 text=(u16)((u16)rom8(0U,base+at)|((u16)rom8(0U,base+at+1U)<<8));
 for(i=0U;i<n;i+=1U)task_shared[0x3ca3U+i]=dialogue_keywords[i];
 task_shared[0x3ca3U+n]=255U;
 dialogue_keyword_count=(u8)n;dialogue_added_count=(u8)count;
 dialogue_script=script;dialogue_text=text;
 dialogue_has_script=(u8)((control&128U)!=0U);dialogue_status=1U;
}
