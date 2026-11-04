"""Native16 control keeps its full native stack, with an observed low32 view."""
from pathlib import Path
import shutil
import subprocess

import pytest


def _function(source, signature):
    begin = source.index('static ' + signature + ' {')
    return source[begin:source.index('\n}', begin) + 2]


def test_live_ldt_native_context_projection_and_control_preserve_full_native_state(tmp_path):
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('C compiler required for the LDT context contract')
    source = (Path(__file__).resolve().parents[1] / 'src/fdisbull/wine_guest/agent.c').read_text()
    functions = '\n'.join(_function(source, signature) for signature in (
        'TargetContext context(void)',
        'void context_set_flags(TargetContext *c,DWORD value)',
        'void context_set_ip(TargetContext *c,DWORD64 value)',
        'void setcontrolcontext(const TargetContext *c)',
    ))
    harness = r'''
#include <assert.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t DWORD;
typedef uint64_t DWORD64;
typedef uintptr_t HANDLE;
typedef struct {
    DWORD ContextFlags,EFlags,SegCs,SegDs,SegSs,SegEs,SegFs,SegGs;
    DWORD64 Rip,Rax,Rbx,Rcx,Rdx,Rsi,Rdi,Rbp,Rsp,R8,R9,R10,R11,R12,R13,R14,R15;
} CONTEXT;
typedef struct {
    DWORD ContextFlags,EFlags,SegCs,SegDs,SegSs,SegEs,SegFs,SegGs;
    DWORD Eip,Eax,Ebx,Ecx,Edx,Esi,Edi,Ebp,Esp;
} WOW64_CONTEXT;
typedef struct { CONTEXT native; WOW64_CONTEXT wow; int native_ldt; } TargetContext;
typedef struct { struct { struct { unsigned Pres,Type,Default_Big; } Bits; } HighWord; } WOW64_LDT_ENTRY;
enum { CONTEXT_CONTROL=0x100001,CONTEXT_INTEGER=0x100002,CONTEXT_SEGMENTS=0x100004,
       CONTEXT_FULL=0x10000b,CONTEXT_ALL=0x10001f,
       WOW64_CONTEXT_CONTROL=0x10001,WOW64_CONTEXT_FULL=0x10007 };
static unsigned target_bits=32;
static int pending=1,exited,native_reads,wow_reads,setters,delivered_native,delivered_internal;
static struct { DWORD dwThreadId; } ev={9};
static CONTEXT actual_native;
static WOW64_CONTEXT stale_wow;
static TargetContext delivered;
static jmp_buf failure;
static int expect_failure,descriptor_big,descriptor_valid=1,missing_groups;
static const char *last_failure;
static void fatal(const char *reason) {
    last_failure=reason;
    if(expect_failure) longjmp(failure,1);
    abort();
}
static HANDLE thread(DWORD id) {assert(id==9);return id;}
static int GetThreadContext(HANDLE handle,CONTEXT *context) {
    assert(handle==9 && (context->ContextFlags==CONTEXT_ALL || context->ContextFlags==CONTEXT_FULL));
    DWORD requested=context->ContextFlags;native_reads++;*context=actual_native;
    context->ContextFlags=missing_groups?CONTEXT_CONTROL:requested;return 1;
}
static int Wow64GetThreadContext(HANDLE handle,WOW64_CONTEXT *context) {
    assert(handle==9 && context->ContextFlags==WOW64_CONTEXT_FULL);
    wow_reads++;*context=stale_wow;return 1;
}
static int query_selector(DWORD selector,WOW64_LDT_ENTRY *entry) {
    assert(selector==0x2ef);memset(entry,0,sizeof(*entry));
    entry->HighWord.Bits.Pres=descriptor_valid;
    entry->HighWord.Bits.Type=27;entry->HighWord.Bits.Default_Big=descriptor_big;return 1;
}
static DWORD descriptor_base(const WOW64_LDT_ENTRY *entry) {(void)entry;return 0x40000;}
static DWORD descriptor_limit(const WOW64_LDT_ENTRY *entry) {(void)entry;return 0xffff;}
static void setcontext_api(TargetContext *context,int native,int internal) {
    delivered=*context;delivered_native=native;delivered_internal=internal;setters++;
    if(native) actual_native=context->native;
    else stale_wow=context->wow;
}
''' + functions + r'''
int main(void) {
    memset(&actual_native,0,sizeof(actual_native));
    actual_native.ContextFlags=CONTEXT_ALL;
    actual_native.SegCs=0x2ef;actual_native.SegSs=actual_native.SegDs=0x2ff;
    actual_native.SegEs=0x2d7;actual_native.SegGs=0x2b;
    actual_native.Rip=0x121;actual_native.EFlags=0x212;
    actual_native.Rsp=0xffffff68010451bcULL;actual_native.Rbp=0x1234567887654321ULL;
    actual_native.Rax=0x1111222233334444ULL;actual_native.Rbx=0x2222333344445555ULL;
    actual_native.Rcx=0x3333444455556666ULL;actual_native.Rdx=0x4444555566667777ULL;
    actual_native.Rsi=0x5555666677778888ULL;actual_native.Rdi=0x6666777788889999ULL;
    actual_native.R8=0x8000000000000008ULL;actual_native.R14=0x7ffffe3ff5f0ULL;
    memset(&stale_wow,0,sizeof(stale_wow));stale_wow.ContextFlags=WOW64_CONTEXT_FULL;
    stale_wow.SegCs=0x2ef;stale_wow.Eip=0x999;stale_wow.EFlags=0x202;stale_wow.Esp=0x777;
    CONTEXT initial_native=actual_native;
    TargetContext observed=context();
    assert(native_reads==1 && wow_reads==1 && observed.native_ldt && !setters);
    assert(!memcmp(&actual_native,&initial_native,sizeof(actual_native)));
    assert(observed.wow.Eip==0x121 && observed.wow.EFlags==0x212);
    assert(observed.wow.Esp==0x10451bc && observed.wow.Ebp==0x87654321);
    assert(observed.wow.Eax==0x33334444 && observed.wow.Ebx==0x44445555);
    assert(observed.wow.Ecx==0x55556666 && observed.wow.Edx==0x66667777);
    assert(observed.wow.Esi==0x77778888 && observed.wow.Edi==0x88889999);
    assert(observed.wow.SegSs==0x2ff && observed.wow.SegEs==0x2d7);
    context_set_ip(&observed,0x40120);context_set_flags(&observed,0x312);
    assert(observed.wow.Eip==0x120 && observed.native.Rip==0x120);
    assert(observed.wow.EFlags==0x312 && observed.native.EFlags==0x312);
    TargetContext unchanged=observed;
    setcontrolcontext(&observed);
    assert(setters==2 && !delivered_native && delivered_internal);
    assert(delivered.native.ContextFlags==CONTEXT_CONTROL);
    assert(delivered.wow.ContextFlags==WOW64_CONTEXT_CONTROL);
    assert(!memcmp(&observed,&unchanged,sizeof(observed)));
    CONTEXT expected=initial_native;expected.ContextFlags=CONTEXT_CONTROL;
    expected.Rip=0x120;expected.EFlags=0x312;
    assert(!memcmp(&delivered.native,&expected,sizeof(expected)));
    assert(delivered.native.Rsp==0xffffff68010451bcULL);
    assert(delivered.native.Rbp==0x1234567887654321ULL);
    assert(delivered.native.R8==0x8000000000000008ULL && delivered.native.R14==0x7ffffe3ff5f0ULL);
    /* Both views agree before continuation; the native RSP remains intact. */
    observed=context();assert(observed.wow.Eip==0x120 && observed.wow.EFlags==0x312);
    assert(stale_wow.Eip==0x120 && stale_wow.Esp==0x10451bc);
    expect_failure=1;actual_native.SegCs=0x23;
    if(!setjmp(failure)) {context();abort();}
    assert(!strcmp(last_failure,"ldt-native-context-mismatch") && setters==2);
    actual_native=initial_native;missing_groups=1;
    if(!setjmp(failure)) {context();abort();}
    assert(!strcmp(last_failure,"ldt-native-context-groups") && setters==2);
    expect_failure=0;missing_groups=0;descriptor_big=1;
    observed=context();assert(!observed.native_ldt && observed.wow.Eip==0x120);
    descriptor_big=0;stale_wow.SegCs=0x23;int prior_native_reads=native_reads;
    observed=context();assert(!observed.native_ldt && !observed.native.ContextFlags);
    assert(native_reads==prior_native_reads && observed.wow.Eip==stale_wow.Eip);
    setcontrolcontext(&observed);assert(!delivered_native && delivered_internal);
    assert(delivered.wow.ContextFlags==WOW64_CONTEXT_CONTROL);
    return 0;
}
'''
    c_source = tmp_path / 'ldt-context.c'
    c_source.write_text(harness)
    binary = tmp_path / 'ldt-context'
    subprocess.run([compiler, '-std=c99', '-Wall', '-Wextra', '-Werror',
                    str(c_source), '-o', str(binary)], check=True, timeout=30)
    subprocess.run([str(binary)], check=True, timeout=5, capture_output=True, text=True)
