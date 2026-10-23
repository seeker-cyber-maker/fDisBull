extern void *memcpy(void *,const void *,unsigned long);
extern void *memset(void *,int,unsigned long);
__attribute__((visibility("hidden"))) const unsigned char platform_src[64]="source";
__attribute__((visibility("hidden"))) unsigned char platform_dst[64];
void platform_entry(void) {
  memcpy(platform_dst,platform_src,12);
  memset(platform_dst+16,42,8);
}
