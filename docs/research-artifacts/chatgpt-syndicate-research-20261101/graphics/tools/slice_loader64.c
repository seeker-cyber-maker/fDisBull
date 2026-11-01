#define _GNU_SOURCE
#include <sys/mman.h>
#include <sys/ptrace.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
/* Authored helper: privately mapped memory, initial ptrace stop, no game bytes. */
int main(int argc,char **argv){
 if(argc!=2)return 110;int fd=open(argv[1],O_RDWR);if(fd<0)return 111;
 uint32_t maps[][3]={{0x10000,0x40000,5},{0x50000,0x14000,3},{0x70000,0x1000,3},{0x80000,0x1d000,3},{0x1000000,0x100000,3},{0x2000000,0x10000,3}};
 for(unsigned i=0;i<sizeof(maps)/sizeof(maps[0]);i++)if(mmap((void*)(uintptr_t)maps[i][0],maps[i][1],maps[i][2],MAP_SHARED|MAP_FIXED,fd,maps[i][0])==MAP_FAILED)return 112;
 if(ptrace(PTRACE_TRACEME,0,0,0)<0)return 113;
 __asm__("int3");return 0;
}
