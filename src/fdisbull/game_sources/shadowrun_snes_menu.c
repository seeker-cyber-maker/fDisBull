/* Title choice controller, $81:E274-E30C. The input is the source's already
 * computed $01EA edge word, not a physical joypad sample. Drawing, sound,
 * repeat generation and the NEW/SAVED/OPTIONS continuations are separate edges.
 * Source $0E is a direct-page word; $1CD2 was only an NMI stack copy of Y. */
typedef unsigned char u8;
typedef unsigned int u16;
u16 menu_selection,menu_pressed,menu_disabled[3];
u8 menu_supported,menu_confirmed;
void shadowrun_snes_menu_control(u8 unused) {
 u16 selected,n,eligible;
 menu_supported=0U;
 if(menu_selection>=3U || menu_confirmed)return;
 selected=menu_selection;
 if(menu_pressed&36864U) {
  menu_confirmed=1U;menu_supported=1U;return;
 }
 if(menu_pressed&2048U) {
  eligible=0U;
  for(n=0U;n<3U;n+=1U) {
   if(!selected)selected=3U;
   selected-=1U;
   if(!menu_disabled[selected]) {eligible=1U;break;}
  }
  if(!eligible)return;
 }
 if(menu_pressed&9216U) {
  eligible=0U;
  for(n=0U;n<3U;n+=1U) {
   selected+=1U;if(selected==3U)selected=0U;
   if(!menu_disabled[selected]) {eligible=1U;break;}
  }
  if(!eligible)return;
 }
 menu_selection=selected;menu_supported=1U;
}
