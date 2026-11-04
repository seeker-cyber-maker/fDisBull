/* $80:A654/$A65A-$A7C1 selector with hotkeys disabled. The caller owns
 * text, cursor erasure, sound and the source-published held input word.
 * Status: 0 refused, 1 awaits selector poll, 2 awaits final poll,
 * 3 selected, 4 cancelled. Roll back the containing transaction on 0. */
u16 dialogue_select_count,dialogue_select_rows,dialogue_select_column,dialogue_select_row;
u16 dialogue_select_input,dialogue_select_index;
u8 dialogue_select_status,dialogue_select_moved,dialogue_select_cancelled;
void shadowrun_snes_dialogue_select_begin(u8 unused) {
 dialogue_select_status=0U;dialogue_select_moved=0U;dialogue_select_cancelled=0U;
 if(!dialogue_select_count || !dialogue_select_rows || dialogue_select_rows>9U ||
    dialogue_select_count>dialogue_select_rows)return;
 scene_write(0x1dc3U,0U);scene_write(0x1dc1U,0U);
 scene_write(0x1db3U,0U);scene_write(0x1db1U,0U);scene_write(0x1dbdU,0U);
 scene_write(0x1db5U,dialogue_select_column);scene_write(0x1db7U,dialogue_select_row);
 dialogue_select_index=0U;dialogue_select_status=1U;
}
void shadowrun_snes_dialogue_select_poll(u8 unused) {
 u16 held,old,edge,repeat,move,at,prior;
 dialogue_select_moved=0U;
 if(dialogue_select_status!=1U) {dialogue_select_status=0U;return;}
 held=dialogue_select_input;
 /* L/R page navigation and the reset chord are not projected. */
 if((held&0x003fU) || ((held&0x3030U)==0x3030U)) {dialogue_select_status=0U;return;}
 old=scene_read(0x01e8U);edge=(held^old)&held;
 scene_write(0x01e6U,held);scene_write(0x01e8U,held);scene_write(0x01eaU,edge);
 scene_write(0x1dbfU,edge);repeat=scene_read(0x1dbdU);
 if(held&0x0c00U) {
  repeat+=1U;
  if(repeat==20U) {repeat=19U;scene_write(0x1dbfU,held);}
 } else repeat=0U;
 scene_write(0x1dbdU,repeat);
 if(edge&0x2000U) {
  dialogue_select_cancelled=1U;dialogue_select_index=65535U;
  scene_write(0U,65535U);dialogue_select_status=2U;return;
 }
 at=scene_read(0x1db3U);
 if((at&1U) || at>=dialogue_select_count*2U) {dialogue_select_status=0U;return;}
 if(edge&0xd0c0U) {
  dialogue_select_index=at>>1;scene_write(0U,dialogue_select_index);
  dialogue_select_status=2U;return;
 }
 move=scene_read(0x1dbfU);prior=at;
 if(move&0x0400U) {if(at+2U<dialogue_select_count*2U)at+=2U;}
 else if(move&0x0800U) {if(at>=2U)at-=2U;}
 if(at!=prior) {scene_write(0x1db3U,at);dialogue_select_moved=1U;}
}
void shadowrun_snes_dialogue_select_finish(u8 unused) {
 u16 held,old;
 if(dialogue_select_status!=2U) {dialogue_select_status=0U;return;}
 held=dialogue_select_input;
 if((held&0x003fU) || ((held&0x3030U)==0x3030U)) {dialogue_select_status=0U;return;}
 old=scene_read(0x01e8U);scene_write(0x01e6U,held);
 scene_write(0x01eaU,(held^old)&held);scene_write(0x01e8U,held);
 if(dialogue_select_cancelled)dialogue_select_status=4U;else dialogue_select_status=3U;
}
