"""Opt-in context recording stays passive and bounded at the native C seam.

The authored host harness uses mock Windows APIs to exercise the current C
functions. It proves recorder and memory-read invariants; native API/runtime
context compatibility remains a separate real-guest acceptance gate.
"""
from pathlib import Path
import shutil
import subprocess

import pytest


def _function(source, signature):
    begin = source.index('static ' + signature)
    return source[begin:source.index('\n}', begin) + 2]


def test_context_diagnostics_preserve_target_setters_and_bound_passive_reads(tmp_path):
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('C compiler required for the diagnostic contract')
    source = (Path(__file__).resolve().parents[1] / 'src/fdisbull/wine_guest/agent.c').read_text()
    begin = source.index('typedef struct {\n    CONTEXT native;\n    WOW64_CONTEXT wow;\n    DWORD native_error')
    declarations = source[begin:source.index('static DWORD64 context_ip(')]
    functions = '\n'.join(_function(source, signature) for signature in (
        'void observe_context(', 'void setcontext_api(', 'void setcontext(',
        'void setcontrolcontext(', 'int diagnostic_read(',
    ))
    harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t DWORD;
typedef uint64_t ULONGLONG;
typedef uintptr_t HANDLE;
typedef size_t SIZE_T;
typedef unsigned char BYTE;
typedef struct { DWORD ContextFlags; uint64_t hidden; } CONTEXT;
typedef struct { DWORD ContextFlags; uint64_t value; } WOW64_CONTEXT;
typedef struct { CONTEXT native; WOW64_CONTEXT wow; int native_ldt; } TargetContext;
#define CONTEXT_CONTROL 0x100001u
#define CONTEXT_ALL 0x10001fu
#define WOW64_CONTEXT_CONTROL 0x10001u
#define WOW64_CONTEXT_ALL 0x1003fu
#define MAX_CONTEXT_CHANGES 4
#define DIAGNOSTIC_STACK_BYTES 128
#define ERROR_INVALID_PARAMETER 87u
#define ERROR_NOACCESS 998u
#define ERROR_PARTIAL_COPY 299u
#define MEM_COMMIT 0x1000u
#define PAGE_NOACCESS 1u
#define PAGE_READONLY 2u
#define PAGE_READWRITE 4u
#define PAGE_WRITECOPY 8u
#define PAGE_EXECUTE_READ 32u
#define PAGE_EXECUTE_READWRITE 64u
#define PAGE_EXECUTE_WRITECOPY 128u
#define PAGE_GUARD 256u
''' + declarations + r'''
static unsigned target_bits=32;
static ULONGLONG state_revision=11,module_revision=12;
static struct { DWORD dwThreadId,dwDebugEventCode; } ev={7,1};
static struct { HANDLE hProcess; } pi={17};
static DWORD last_error;
static unsigned native_reads,wow_reads,native_writes,wow_writes;
static int fail_native,fail_wow;
static CONTEXT actual_native={CONTEXT_ALL,0x123456789abcdef0ULL};
static WOW64_CONTEXT actual_wow={WOW64_CONTEXT_ALL,9};
static ULONGLONG GetTickCount64(void) { static ULONGLONG t;return ++t; }
static void SetLastError(DWORD value) {last_error=value;}
static DWORD GetLastError(void) {return last_error;}
static HANDLE thread(DWORD id) {assert(id==7);return id;}
static void fatal(const char *op) {fprintf(stderr,"unexpected fatal %s\n",op);abort();}
static int GetThreadContext(HANDLE handle,CONTEXT *c) {
 assert(handle==7);assert(c->ContextFlags==CONTEXT_ALL);native_reads++;
 if(fail_native) {SetLastError(123);return 0;}
 *c=actual_native;return 1;
}
static int Wow64GetThreadContext(HANDLE handle,WOW64_CONTEXT *c) {
 assert(handle==7);assert(c->ContextFlags==WOW64_CONTEXT_ALL);wow_reads++;
 if(fail_wow) {SetLastError(234);return 0;}
 *c=actual_wow;return 1;
}
static int SetThreadContext(HANDLE handle,const CONTEXT *c) {
 assert(handle==7);actual_native=*c;native_writes++;return 1;
}
static int Wow64SetThreadContext(HANDLE handle,const WOW64_CONTEXT *c) {
 assert(handle==7);actual_wow=*c;wow_writes++;
 /* Deliberately expose an unrelated native effect: the recorder must retain
    the API observation rather than hide it or change the requested setter. */
 actual_native.hidden^=0x100000000ULL;
 return 1;
}
typedef struct { void *BaseAddress;SIZE_T RegionSize;DWORD State,Protect; } MEMORY_BASIC_INFORMATION;
static unsigned queries,memory_reads;
static int guarded,query_fail,partial_read;
static BYTE memory[256];
static SIZE_T VirtualQueryEx(HANDLE process,void *pointer,MEMORY_BASIC_INFORMATION *region,SIZE_T size) {
 assert(process==17);assert(size==sizeof(*region));queries++;
 if(query_fail) {SetLastError(345);return 0;}
 uintptr_t address=(uintptr_t)pointer;
 assert(address>=0x1000 && address<0x1100);
 region->BaseAddress=(void*)(address&~(uintptr_t)63);region->RegionSize=64;
 region->State=MEM_COMMIT;region->Protect=PAGE_READWRITE|(guarded?PAGE_GUARD:0);
 return sizeof(*region);
}
static int ReadProcessMemory(HANDLE process,void *pointer,void *dest,SIZE_T count,SIZE_T *got) {
 assert(process==17);memory_reads++;
 if(partial_read) {*got=count-1;return 0;}
 uintptr_t address=(uintptr_t)pointer;
 assert(address>=0x1000 && address+count<=0x1100);
 memcpy(dest,memory+address-0x1000,count);*got=count;return 1;
}
''' + functions + r'''int main(void) {
 TargetContext submitted;memset(&submitted,0,sizeof(submitted));
 submitted.wow.ContextFlags=WOW64_CONTEXT_ALL;submitted.wow.value=1;
 setcontext(&submitted);
 assert(native_reads==0 && wow_reads==0 && wow_writes==1);
 assert(context_change_count==0 && context_change_sequence==0);
 context_recording=1;
 for(unsigned i=1;i<=6;i++) {
  submitted.wow.ContextFlags=i==6?WOW64_CONTEXT_CONTROL:WOW64_CONTEXT_ALL;
  submitted.wow.value=i+20;
  TargetContext original=submitted;
  uint64_t before=actual_native.hidden;
  if(i==6) setcontrolcontext(&submitted);else setcontext(&submitted);
  assert(!memcmp(&original,&submitted,sizeof(original)));
  const ContextChange *change=&context_changes[(context_change_next+3)%4];
  assert(change->sequence==i && change->thread==7 && change->state_revision==11 && change->module_revision==12);
  assert(change->before.native.hidden==before && change->after.native.hidden==(before^0x100000000ULL));
  assert(change->after.wow.value==i+20 && change->submitted.wow.value==i+20);
  assert(change->submitted_flags==submitted.wow.ContextFlags && change->set_ok && !change->set_error);
  assert(change->internal_control==(i==6));
 }
 assert(wow_writes==7 && native_writes==0 && native_reads==12 && wow_reads==12);
 assert(context_change_count==4 && context_change_sequence==6);
 unsigned first=(context_change_next+4-context_change_count)%4;
 for(unsigned i=0;i<4;i++) assert(context_changes[(first+i)%4].sequence==i+3);
 ContextObservation observation;
 fail_native=1;observe_context(7,&observation);
 assert(!observation.native_ok && observation.native_error==123 && observation.wow_ok && !observation.wow_error);
 fail_native=0;fail_wow=1;observe_context(7,&observation);
 assert(observation.native_ok && !observation.native_error && !observation.wow_ok && observation.wow_error==234);
 fail_wow=0;target_bits=64;unsigned old_wow_reads=wow_reads;
 observe_context(7,&observation);assert(observation.native_ok && !observation.wow_attempted && wow_reads==old_wow_reads);
 context_recording=0;submitted.native=actual_native;setcontext(&submitted);assert(native_writes==1 && wow_writes==7);
 for(unsigned i=0;i<256;i++) memory[i]=(BYTE)i;
 BYTE data[128];DWORD error;
 assert(diagnostic_read(0x1020,data,sizeof(data),&error));
 assert(!error && queries==3 && memory_reads==3 && !memcmp(data,memory+32,128));
 guarded=1;queries=memory_reads=0;
 assert(!diagnostic_read(0x1020,data,16,&error));assert(error==ERROR_NOACCESS && queries==1 && memory_reads==0);
 guarded=0;queries=0;
 assert(!diagnostic_read(UINTPTR_MAX-7,data,16,&error));assert(error==ERROR_INVALID_PARAMETER && queries==0);
 assert(!diagnostic_read(0x1020,data,129,&error));assert(error==ERROR_INVALID_PARAMETER && queries==0);
 query_fail=1;assert(!diagnostic_read(0x1020,data,16,&error));assert(error==345 && memory_reads==0);
 query_fail=0;partial_read=1;assert(!diagnostic_read(0x1020,data,16,&error));assert(error==ERROR_PARTIAL_COPY);
 puts("PASS: dormant recorder, exact setters, paired context/error observations, four-entry retention, bounded guard-preserving reads");
}
'''
    c_source = tmp_path / 'context-diagnostics.c'
    c_source.write_text(harness)
    binary = tmp_path / 'context-diagnostics'
    subprocess.run([compiler, '-std=c99', '-Wall', '-Wextra', '-Werror',
                    str(c_source), '-o', str(binary)], check=True, timeout=30)
    subprocess.run([str(binary)], check=True, timeout=5, capture_output=True, text=True)
