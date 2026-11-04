/* Mutable source banks are owned by scene_init/task VM. The containing frame
 * must restore its whole transaction when any supported flag is zero. */
u8 opening_rebuild_supported,opening_sort_supported,opening_collision_supported;
u16 opening_col_actor,opening_col_player,opening_col_z,opening_col_flags;
u16 opening_col_left,opening_col_right,opening_col_top,opening_col_bottom,opening_col_height;

u16 opening_bank_read16(u8 region,u32 at) {
 u16 lo,hi;
 if(region!=1U || at>=131071UL)return 0U;
 if(at<65536UL)lo=(u16)task_shared[(u16)at];else lo=(u16)scene_7f[(u16)(at-65536UL)];
 at+=1UL;
 if(at<65536UL)hi=(u16)task_shared[(u16)at];else hi=(u16)scene_7f[(u16)(at-65536UL)];
 return lo|(hi<<8);
}
void opening_load_order(void) {
 u16 i,count;
 live_order_count=0U;
 count=scene_read(0x14ccU);
 if(count==65534U)return;
 if(count&32768U) {live_order_count=65535U;return;}
 if((count&1U) || count>=88U) {live_order_count=65535U;return;}
 live_order_count=(count>>1)+1U;
 for(i=0U;i<live_order_count;i+=1U)live_order[i]=scene_read(0x14ceU+(i<<1));
}
void opening_load_actor_tables(void) {
 u16 i,s;
 for(i=0U;i<44U;i+=1U) {
  s=i<<1;
  live_x[i]=scene_read(0x0e44U+s);live_y[i]=scene_read(0x0e9cU+s);
  live_z[i]=scene_read(0x0ef4U+s);live_flags[i]=scene_read(0x1474U+s);
  live_left[i]=scene_read(0x421cU+s);live_right[i]=scene_read(0x4274U+s);
  live_top[i]=scene_read(0x42ccU+s);live_bottom[i]=scene_read(0x4324U+s);
  live_height[i]=scene_read(0x437cU+s);live_depth[i]=scene_read(0x0f4cU+s);
  live_sort_mode[i]=scene_read(0x0fa4U+s);live_sort_delta[i]=scene_read(0x0ffcU+s);
 }
}
void opening_rebuild(void) {
 u16 i;
 opening_rebuild_supported=0U;opening_load_order();opening_load_actor_tables();
 if(live_order_count>44U)return;
 live_first_node=scene_read(0xde86U);
 for(i=0U;i<256U;i+=1U)live_heads[i]=scene_read(0xe088U+(i<<1));
 for(i=0U;i<264U;i+=1U)live_records[i]=scene_read(0xecfcU+(i<<1));
 for(i=0U;i<1072U;i+=1U)live_node_record[i]=scene_read(0xef18U+(i<<1));
 for(i=0U;i<1073U;i+=1U)live_node_next[i]=scene_read(0xf778U+(i<<1));
 for(i=0U;i<1584U;i+=1U)live_owners[i]=scene_7f[0xe214U+i];
 shadowrun_snes_rebuild();if(!live_status)return;
 for(i=0U;i<256U;i+=1U)scene_write(0xe088U+(i<<1),live_heads[i]);
 for(i=0U;i<264U;i+=1U)scene_write(0xecfcU+(i<<1),live_records[i]);
 for(i=0U;i<1072U;i+=1U)scene_write(0xef18U+(i<<1),live_node_record[i]);
 for(i=0U;i<1073U;i+=1U)scene_write(0xf778U+(i<<1),live_node_next[i]);
 for(i=0U;i<1584U;i+=1U)scene_7f[0xe214U+i]=live_owners[i];
 opening_rebuild_supported=1U;
}
void opening_sort(void) {
 u16 i;
 opening_sort_supported=0U;opening_load_order();opening_load_actor_tables();
 if(live_order_count>44U)return;
 shadowrun_snes_sort();if(!live_sort_supported)return;
 for(i=0U;i<live_order_count;i+=1U)scene_write(0x14ceU+(i<<1),live_order[i]);
 opening_sort_supported=1U;
}
u16 opening_collision_at(u16 actor,u16 x,u16 y,u8 axis) {
 opening_collision_supported=0U;opening_col_actor=actor;opening_col_player=scene_read(0x0cdeU);
 if((actor&1U) || actor>=88U || axis>3U)return 0U;
 opening_col_z=scene_read(0x0ef4U+actor);opening_col_flags=scene_read(0x1474U+actor);
 opening_col_left=scene_read(0x421cU+actor);opening_col_right=scene_read(0x4274U+actor);
 opening_col_top=scene_read(0x42ccU+actor);opening_col_bottom=scene_read(0x4324U+actor);
 opening_col_height=scene_read(0x437cU+actor);
 return opening_collision_impl(x,y,axis);
}
