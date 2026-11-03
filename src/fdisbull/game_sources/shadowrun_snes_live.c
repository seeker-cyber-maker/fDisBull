/* Bounded reconstruction of the dynamic collision rebuild at 81:8799 and
 * 81:846e. This is a component, not an actor-script or frame simulator. */
typedef unsigned char u8;
typedef unsigned int u16;
u16 live_x[44],live_y[44],live_z[44],live_flags[44];
u16 live_left[44],live_right[44],live_top[44],live_bottom[44],live_height[44];
u16 live_order[44],live_order_count,live_first_node;
u16 live_heads[256],live_records[264],live_node_record[1072],live_node_next[1073];
u8 live_owners[1584];
u8 live_status;
void live_insert(u16 cell,u16 record,u16 node) {
 live_node_record[node>>1]=record;
 live_node_next[node>>1]=live_heads[cell>>1];
 live_heads[cell>>1]=node;
}
void shadowrun_snes_rebuild(void) {
 u16 i,j,s,r,n,x,y,z,l,t,rr,b,c0,c1,c2,c3;
 live_status=0;
 if(live_order_count>44U || (live_first_node&1U) || live_first_node>0x860U)return;
 /* Preflight makes unsupported layouts fail before mutating collision state. */
 n=live_first_node;r=0x0a74U;
 for(i=0;i<live_order_count;i+=1U) {
  s=live_order[i];if((s&1U) || s>=88U)return;
  j=s>>1;
  if((live_flags[j]&256U) && live_height[j]) {
   if(r>0x0c84U || n>0x0858U)return;
   r+=12U;n+=8U;
  }
 }
 for(i=0;i<256U;i+=1U)live_heads[i]=65535U;
 n=live_first_node;r=0x0a74U;
 for(i=live_order_count;i>0U;i-=1U) {
  s=live_order[i-1U];j=s>>1;
  if((live_flags[j]&256U) && live_height[j]) {
   x=live_x[j]>>2;y=live_y[j]>>2;z=live_z[j]>>2;
   l=x+live_left[j];t=y+live_top[j];rr=x+live_right[j];b=y+live_bottom[j];
   live_records[(r-0x0a74U)>>1]=l;live_records[((r-0x0a74U)>>1)+1U]=t;
   live_records[((r-0x0a74U)>>1)+2U]=z;live_records[((r-0x0a74U)>>1)+3U]=rr;
   live_records[((r-0x0a74U)>>1)+4U]=b;live_records[((r-0x0a74U)>>1)+5U]=z+live_height[j];
   c0=((l&960U)>>5)|((t&960U)>>1);c1=((rr&960U)>>5)|((b&960U)>>1);
   c2=((rr&960U)>>5)|((t&960U)>>1);c3=((l&960U)>>5)|((b&960U)>>1);
   live_insert(c0,r,n);n+=2U;
   if(c1!=c0) {
    live_insert(c1,r,n);n+=2U;
    if(c1!=c2 && c1!=c3) {live_insert(c2,r,n);n+=2U;live_insert(c3,r,n);n+=2U;}
   }
   live_owners[r>>2]=(u8)s;live_owners[(r>>2)+1U]=(u8)(s>>8);r+=12U;
  }
 }
 live_status=1;
}

/* Two adjacent compare passes at 80:AF89-B031, with 80:B032/B07A
 * conditional depth adjustments. Unknown jump-table cases fail closed. */
u16 live_depth[44],live_sort_mode[44],live_sort_delta[44];
u8 live_sort_supported;
u16 live_sort_swap(u16 a,u16 b) {
 u16 x,y,ma,mb,da,db,k,add;
 x=a>>1;y=b>>1;ma=live_sort_mode[x];mb=live_sort_mode[y];
 da=live_depth[x];db=live_depth[y];
 if(ma || mb) {
  if(mb&32768U) {
   k=mb&32767U;if(k<1U || k>4U){live_sort_supported=0;return 0;}
   add=0;
   if(k==1U && live_y[x]<live_y[y])add=1;
   if(k==2U && live_x[x]<live_x[y])add=1;
   if(k==3U && live_x[x]>=live_x[y])add=1;
   if(k==4U && live_y[x]>=live_y[y])add=1;
   if(add)db+=live_sort_delta[y];
  } else {
   k=ma&32767U;if(k<1U || k>4U){live_sort_supported=0;return 0;}
   add=0;
   if(k==1U && live_y[x]>=live_y[y])add=1;
   if(k==2U && live_x[x]>=live_x[y])add=1;
   if(k==3U && live_x[x]<live_x[y])add=1;
   if(k==4U && live_y[x]<live_y[y])add=1;
   if(add)da+=live_sort_delta[x];
  }
 }
 return da<db;
}
void shadowrun_snes_sort(void) {
 u16 i,n,a,b,order[44];
 live_sort_supported=0;n=live_order_count;
 if(n>44U)return;
 for(i=0;i<n;i+=1U){a=live_order[i];if((a&1U) || a>=88U)return;order[i]=a;}
 live_sort_supported=1;
 if(n<2U)return;
 for(i=n-1U;i>0U;i-=1U) {
  a=order[i-1U];b=order[i];
  if(live_sort_swap(a,b)){order[i-1U]=b;order[i]=a;}
  if(!live_sort_supported)return;
 }
 for(i=1U;i+1U<n;i+=1U) {
  a=order[i];b=order[i+1U];
  if(live_sort_swap(a,b)){order[i]=b;order[i+1U]=a;}
  if(!live_sort_supported)return;
 }
 for(i=0;i<n;i+=1U)live_order[i]=order[i];
}
