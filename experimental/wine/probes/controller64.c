/* Finite Win32 debug-API qualification, not the fDisBull PE adapter. */
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static void fail(const char *operation)
{
    fprintf(stderr,"{\"result\":\"fail\",\"operation\":\"%s\",\"win32_error\":%lu}\n",
            operation,GetLastError());
    fflush(stderr);
    ExitProcess(2); /* Windows kills the child owned by this debugger. */
}

int main(int argc,char **argv)
{
    STARTUPINFOA si={0}; PROCESS_INFORMATION pi={0}; DEBUG_EVENT event;
    uintptr_t base=0, counter_rva; DWORD initial_tid=0;
    int saw_break=0,saw_step=0,module_count=0;
    DWORD64 step_pc=0; ULONGLONG deadline;
    char command[2048];
    if(argc!=3) return 64;
    counter_rva=(uintptr_t)strtoull(argv[2],NULL,0);
    if(counter_rva>0x1000000 || snprintf(command,sizeof(command),"\"%s\"",argv[1])>=sizeof(command)) return 64;
    si.cb=sizeof(si);
    if(!CreateProcessA(NULL,command,NULL,NULL,TRUE,DEBUG_ONLY_THIS_PROCESS,NULL,NULL,&si,&pi)) fail("CreateProcessA");
    initial_tid=pi.dwThreadId;
    deadline=GetTickCount64()+20000;
    while(GetTickCount64()<deadline) {
        DWORD continuation=DBG_CONTINUE;
        if(!WaitForDebugEvent(&event,1000)) {
            if(GetLastError()==ERROR_SEM_TIMEOUT) continue;
            fail("WaitForDebugEvent");
        }
        if(event.dwDebugEventCode==CREATE_PROCESS_DEBUG_EVENT) {
            base=(uintptr_t)event.u.CreateProcessInfo.lpBaseOfImage;
            if(event.u.CreateProcessInfo.hFile) CloseHandle(event.u.CreateProcessInfo.hFile);
            printf("{\"event\":\"process\",\"image_base\":\"0x%llx\",\"thread\":%lu}\n",
                   (unsigned long long)base,event.dwThreadId);
        } else if(event.dwDebugEventCode==LOAD_DLL_DEBUG_EVENT) {
            ++module_count;
            if(event.u.LoadDll.hFile) CloseHandle(event.u.LoadDll.hFile);
        } else if(event.dwDebugEventCode==EXCEPTION_DEBUG_EVENT) {
            DWORD code=event.u.Exception.ExceptionRecord.ExceptionCode;
            uintptr_t address=(uintptr_t)event.u.Exception.ExceptionRecord.ExceptionAddress;
            printf("{\"event\":\"exception\",\"code\":\"0x%lx\",\"address\":\"0x%llx\",\"first_chance\":%lu}\n",
                   code,(unsigned long long)address,event.u.Exception.dwFirstChance);
            fflush(stdout);
            /* Loader breakpoints need continuation, not a context round trip. */
            if(code==EXCEPTION_BREAKPOINT && !(address>=base && address<base+0x1000000)) {
                if(!ContinueDebugEvent(event.dwProcessId,event.dwThreadId,DBG_CONTINUE)) fail("ContinueDebugEvent-loader");
                continue;
            }
            HANDLE thread=OpenThread(THREAD_GET_CONTEXT|THREAD_SET_CONTEXT|THREAD_QUERY_INFORMATION,FALSE,event.dwThreadId);
            CONTEXT context={0}; context.ContextFlags=CONTEXT_FULL;
            if(!thread || !GetThreadContext(thread,&context)) fail("GetThreadContext");
            if(code==EXCEPTION_BREAKPOINT && address>=base && address<base+0x1000000 && !saw_break) {
                LONG original=0,changed=41,check=0; SIZE_T got=0; BYTE instruction[5];
                if(event.dwThreadId!=initial_tid) fail("unexpected-fixture-thread");
                if(!ReadProcessMemory(pi.hProcess,(void*)(base+counter_rva),&original,4,&got) || got!=4 || original!=7) fail("ReadProcessMemory-counter");
                if(!WriteProcessMemory(pi.hProcess,(void*)(base+counter_rva),&changed,4,&got) || got!=4) fail("WriteProcessMemory-counter");
                if(!ReadProcessMemory(pi.hProcess,(void*)(base+counter_rva),&check,4,&got) || got!=4 || check!=41) fail("ReadProcessMemory-readback");
                if(!ReadProcessMemory(pi.hProcess,(void*)(uintptr_t)context.Rip,instruction,5,&got) || got!=5 ||
                   instruction[0]!=0xb8 || instruction[1]!=0x78 || instruction[2]!=0x56 || instruction[3]!=0x34 || instruction[4]!=0x12) fail("fixture-instruction-bytes");
                step_pc=context.Rip;
                context.EFlags|=0x100;
                if(!SetThreadContext(thread,&context)) fail("SetThreadContext-trap-flag");
                saw_break=1;
                printf("{\"event\":\"fixture-breakpoint\",\"rip\":\"0x%llx\",\"counter_before\":%ld,\"counter_after_edit\":%ld}\n",
                       (unsigned long long)step_pc,original,check);
            } else if(code==EXCEPTION_SINGLE_STEP && saw_break && !saw_step) {
                if(context.Rip!=step_pc+5 || (DWORD)context.Rax!=0x12345678) fail("single-step-oracle");
                context.EFlags&=~0x100;
                if(!SetThreadContext(thread,&context)) fail("SetThreadContext-clear-trap");
                saw_step=1;
                printf("{\"event\":\"single-step\",\"rip\":\"0x%llx\",\"eax\":\"0x%lx\"}\n",
                       (unsigned long long)context.Rip,(DWORD)context.Rax);
            } else if(code!=EXCEPTION_BREAKPOINT) continuation=DBG_EXCEPTION_NOT_HANDLED;
            CloseHandle(thread);
        } else if(event.dwDebugEventCode==EXIT_PROCESS_DEBUG_EVENT) {
            DWORD exit_code=event.u.ExitProcess.dwExitCode;
            if(!ContinueDebugEvent(event.dwProcessId,event.dwThreadId,DBG_CONTINUE)) fail("ContinueDebugEvent-exit");
            CloseHandle(pi.hThread);CloseHandle(pi.hProcess);
            printf("{\"result\":\"%s\",\"breakpoint\":%s,\"single_step\":%s,\"modules\":%d,\"exit_code\":%lu}\n",
                saw_break&&saw_step&&exit_code==0?"pass":"fail",saw_break?"true":"false",saw_step?"true":"false",module_count,exit_code);
            return saw_break&&saw_step&&exit_code==0?0:1;
        }
        fflush(stdout);
        if(!ContinueDebugEvent(event.dwProcessId,event.dwThreadId,continuation)) fail("ContinueDebugEvent");
    }
    TerminateProcess(pi.hProcess,124);
    fprintf(stderr,"{\"result\":\"timeout\"}\n");
    return 124;
}
