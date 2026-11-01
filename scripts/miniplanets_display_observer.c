#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef void (*writer)(uint32_t,uint8_t);
typedef struct { uint32_t frame,stamp; int32_t start_count; uint16_t addr,refresh; uint8_t value,mask; } Event;
static writer *table, old[9]; static uint32_t *stamp; static uint8_t *ppu; static uint16_t *refresh; static uint32_t frame; static int32_t count; static Event *events; static size_t n, cap; static int overflow;
static int idx(uint32_t a){return a==0x4014?8:(int)(a-0x2000);}
static uint8_t *sram,*ram,*spr,*nt,*plane,*hud,*attrs,*active,*oam; static uint8_t **pages; static int last=-1; static uint32_t warmup, flips, badplane, badhud, badattrs, badoam, badcontrol, activewrites;
void coherence(void *sr,void *rm,void *sp,void *pg,uint32_t po,uint32_t ho,uint32_t ao,uint32_t no,uint32_t oo,uint32_t w){sram=sr;ram=rm;spr=sp;pages=pg;plane=sram+po;hud=sram+ho;attrs=sram+ao;active=sram+no;oam=sram+oo;warmup=w;}
static void check_view(void){int n=*active;if(last<0){last=n;return;}if(n==last)return;last=n;if(frame<warmup)return;flips++;nt=pages[n&1];for(int y=0;y<16;y++)for(int x=0;x<16;x++)if(nt[0x188+y*32+x]!=plane[y*16+x])badplane++;for(int x=0;x<24;x++)if(nt[0x104+x]!=hud[x])badhud++;for(int y=0;y<4;y++)for(int x=0;x<4;x++)if(nt[0x3da+y*8+x]!=attrs[y*4+x])badattrs++;if(*oam>7){badoam+=256;return;}for(int i=0;i<256;i++)if(spr[i]!=ram[*oam*256+i])badoam++;}
uint32_t coherence_result(int i){switch(i){case 0:return flips;case 1:return badplane;case 2:return badhud;case 3:return badattrs;case 4:return badoam;case 5:return badcontrol;case 6:return activewrites;default:return 0;}}
static void hook(uint32_t a,uint8_t v){if(active && frame>=warmup){if(a==0x2007 && (ppu[1]&0x18) && (*refresh&0x3fff)>=0x2000 && (*refresh&0x3fff)<0x3000 && pages[(*refresh>>10)&3]==pages[ppu[0]&3])activewrites++;if(a==0x2000 && ((*active)&3)!=(v&3))badcontrol++;}if(a==0x2000 && active)check_view();int i=idx(a); if(n<cap) events[n++]=(Event){frame,*stamp,count,(uint16_t)a,*refresh,v,ppu[1]}; else overflow=1; old[i](a,v);}
void setup(void *t,void *ts,void *p,void *r){table=t;stamp=ts;ppu=p;refresh=r;cap=4000000;events=calloc(cap,sizeof(Event));if(!events)abort();for(int i=0;i<9;i++){int a=i==8?0x4014:0x2000+i;old[i]=table[a];table[a]=hook;}}
/* The pinned core's DMCDMA performs four X6502_DMR calls to one sample
 * address on consecutive CPU cycles. Forward every read unchanged and retain
 * only that complete four-read signature; this is a lower bound on fetches. */
typedef uint8_t (*reader)(uint32_t);
typedef struct {uint32_t frame,stamp;int32_t start_count;uint32_t address;} DMCEvent;
static reader oldread[65536];static DMCEvent *dmc_events;static size_t dmc_n,dmc_cap;static uint32_t dmc_address,dmclast,dmcrun;static int dmc_overflow;
static uint8_t observe_read(uint32_t address){
 uint8_t result=oldread[address](address);uint32_t now=*stamp;
 if(address==dmc_address && now==dmclast+1)dmcrun++;else{dmc_address=address;dmcrun=1;}
 dmclast=now;
 if(dmcrun==4){if(dmc_n<dmc_cap)dmc_events[dmc_n++]=(DMCEvent){frame,now,count,address};else dmc_overflow=1;dmcrun=0;}
 return result;
}
void dmc_setup(void *p){reader *t=p;dmc_cap=2000000;dmc_events=calloc(dmc_cap,sizeof(DMCEvent));if(!dmc_events)abort();for(unsigned i=0x8000;i<65536;i++){oldread[i]=t[i];t[i]=observe_read;}}
int dmc_dump(const char *path){FILE*f=fopen(path,"wb");if(!f)return -1;fwrite(dmc_events,sizeof(DMCEvent),dmc_n,f);fclose(f);return dmc_overflow?-2:(int)dmc_n;}
typedef void (*cyclehook)(int);
static cyclehook savedcycle; static uint8_t *stackp; static uint32_t stackwarmup, stackmin=255, stackwraps, stacksamples; static int stackprev=-1;
static void sample_stack(int cycles){if(frame>=stackwarmup){unsigned x=*stackp;if(x<stackmin)stackmin=x;if(stackprev>=0 && stackprev<=2 && x>=253)stackwraps++;stackprev=x;stacksamples++;}if(savedcycle)savedcycle(cycles);}
void stack_setup(void *hookptr,void *sp,uint32_t w){cyclehook *h=hookptr;savedcycle=*h;*h=sample_stack;stackp=sp;stackwarmup=w;}
uint32_t stack_result(int i){switch(i){case 0:return stackmin;case 1:return stackwraps;case 2:return stacksamples;default:return 0;}}
void start_frame(uint32_t f,int32_t c){frame=f;count=c;}
int dump(const char *path){FILE *f=fopen(path,"wb");if(!f)return -1;fwrite(events,sizeof(Event),n,f);fclose(f);return overflow?-2:(int)n;}
