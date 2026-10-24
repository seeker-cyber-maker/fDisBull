/* PE64 debugger. All target control stays on this Win32 debug-event thread. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wincrypt.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_BP 256
#define MAX_THREADS 256
static PROCESS_INFORMATION pi;
static DEBUG_EVENT ev;
static int pending=0, exited=0, hit=-1, initializing=1;
static DWORD continuation=DBG_CONTINUE, exit_code=0;
static uintptr_t image_base;
static struct { uintptr_t address; BYTE original; int used, armed; } bp[MAX_BP];
static struct { DWORD id; HANDLE handle; int suspended; } threads[MAX_THREADS];
static char reason[32]="entry";
static uintptr_t stop_address;

static void fatal(const char *op) {
    printf("{\"error\":\"%s\",\"win32_error\":%lu,\"fatal\":true}\n",op,GetLastError());
    fflush(stdout); if(pi.hProcess) TerminateProcess(pi.hProcess,125); ExitProcess(2);
}
static int readmem(uintptr_t addr,void *data,SIZE_T n) {
    SIZE_T got=0; return ReadProcessMemory(pi.hProcess,(void*)addr,data,n,&got) && got==n;
}
static int writemem(uintptr_t addr,const void *data,SIZE_T n) {
    DWORD protection,ignored; SIZE_T wrote=0;
    MEMORY_BASIC_INFORMATION region;
    if(!VirtualQueryEx(pi.hProcess,(void*)addr,&region,sizeof(region)) ||
       addr+n<addr || addr+n>(uintptr_t)region.BaseAddress+region.RegionSize) return 0;
    if(!VirtualProtectEx(pi.hProcess,(void*)addr,n,PAGE_EXECUTE_READWRITE,&protection)) return 0;
    int ok=WriteProcessMemory(pi.hProcess,(void*)addr,data,n,&wrote) && wrote==n;
    if(!VirtualProtectEx(pi.hProcess,(void*)addr,n,protection,&ignored)) fatal("restore-page-protection");
    if(!FlushInstructionCache(pi.hProcess,(void*)addr,n)) fatal("flush-instruction-cache");
    return ok;
}
static void addthread(DWORD id,HANDLE h) {
    for(int i=0;i<MAX_THREADS;i++) if(!threads[i].handle) { threads[i].id=id;threads[i].handle=h;return; }
    fatal("thread-budget");
}
static HANDLE thread(DWORD id) {
    for(int i=0;i<MAX_THREADS;i++) if(threads[i].handle && threads[i].id==id) return threads[i].handle;
    fatal("unknown-thread"); return NULL;
}
static CONTEXT context(void) {
    CONTEXT c={0};c.ContextFlags=CONTEXT_FULL;
    if(!pending || exited || !GetThreadContext(thread(ev.dwThreadId),&c)) fatal("get-context");
    return c;
}
static void setcontext(CONTEXT *c) { if(!SetThreadContext(thread(ev.dwThreadId),c)) fatal("set-context"); }
static void hold_others(int hold) {
    for(int i=0;i<MAX_THREADS;i++) if(threads[i].handle && threads[i].id!=ev.dwThreadId) {
        if(hold && !threads[i].suspended) {
            if(SuspendThread(threads[i].handle)==(DWORD)-1) fatal("suspend-thread");
            threads[i].suspended=1;
        } else if(!hold && threads[i].suspended) {
            if(ResumeThread(threads[i].handle)==(DWORD)-1) fatal("resume-thread");
            threads[i].suspended=0;
        }
    }
}
static void resume_event(void) {
    if(!pending || !ContinueDebugEvent(ev.dwProcessId,ev.dwThreadId,continuation)) fatal("continue-event");
    pending=0;
}
static int install(uintptr_t addr,int slot) {
    BYTE cc=0xcc;
    if(!readmem(addr,&bp[slot].original,1) || bp[slot].original==0xcc) return 0;
    if(!writemem(addr,&cc,1)) return 0;
    bp[slot].address=addr;bp[slot].used=bp[slot].armed=1;return 1;
}
/* Return a stopped exception/exit. Administrative events are always drained. */
static int wait_event(DWORD timeout,int pausing) {
    ULONGLONG deadline=GetTickCount64()+timeout;
    do {
        if(!WaitForDebugEvent(&ev,(DWORD)min(100,deadline>GetTickCount64()?deadline-GetTickCount64():0))) {
            if(GetLastError()==ERROR_SEM_TIMEOUT) continue;
            fatal("wait-debug-event");
        }
        pending=1;continuation=DBG_CONTINUE;
        switch(ev.dwDebugEventCode) {
        case CREATE_PROCESS_DEBUG_EVENT:
            image_base=(uintptr_t)ev.u.CreateProcessInfo.lpBaseOfImage;
            pi.hProcess=ev.u.CreateProcessInfo.hProcess;
            addthread(ev.dwThreadId,ev.u.CreateProcessInfo.hThread);
            if(ev.u.CreateProcessInfo.hFile) CloseHandle(ev.u.CreateProcessInfo.hFile);
            /* Entry breakpoint slot zero is installed by main using observed base. */
            return 2;
        case CREATE_THREAD_DEBUG_EVENT:addthread(ev.dwThreadId,ev.u.CreateThread.hThread);break;
        case EXIT_THREAD_DEBUG_EVENT:
            for(int i=0;i<MAX_THREADS;i++) if(threads[i].handle && threads[i].id==ev.dwThreadId) {
                CloseHandle(threads[i].handle);memset(&threads[i],0,sizeof(threads[i]));
            } break;
        case LOAD_DLL_DEBUG_EVENT:if(ev.u.LoadDll.hFile) CloseHandle(ev.u.LoadDll.hFile);break;
        case EXIT_PROCESS_DEBUG_EVENT:
            exited=1;exit_code=ev.u.ExitProcess.dwExitCode;strcpy(reason,"exited");resume_event();return 1;
        case EXCEPTION_DEBUG_EVENT: {
            DWORD code=ev.u.Exception.ExceptionRecord.ExceptionCode;
            stop_address=(uintptr_t)ev.u.Exception.ExceptionRecord.ExceptionAddress;
            if(code==EXCEPTION_BREAKPOINT) {
                for(int i=0;i<MAX_BP;i++) if(bp[i].used && bp[i].armed && bp[i].address==stop_address) {
                    CONTEXT c=context();
                    if(!writemem(stop_address,&bp[i].original,1)) fatal("restore-breakpoint-byte");
                    bp[i].armed=0;c.Rip=stop_address;setcontext(&c);hit=i;
                    strcpy(reason,initializing?"entry":"breakpoint");return 1;
                }
                if(pausing) {strcpy(reason,"timeout");return 1;}
                if(initializing) break; /* Wine loader's initial break. */
            }
            if(code==EXCEPTION_SINGLE_STEP) {strcpy(reason,"step");return 1;}
            continuation=DBG_EXCEPTION_NOT_HANDLED;strcpy(reason,"exception");return 1;
        }
        default:break;
        }
        resume_event();
    } while(GetTickCount64()<deadline);
    return 0;
}
static void logical_read(uintptr_t addr,BYTE *data,int n) {
    if(!readmem(addr,data,n)) fatal("read-memory");
    for(int i=0;i<MAX_BP;i++) if(bp[i].used && bp[i].armed && bp[i].address>=addr && bp[i].address<addr+n)
        data[bp[i].address-addr]=bp[i].original;
}
/* Displaced breakpoint bytes execute with peer threads held, then rearm. */
static int single_step(DWORD timeout) {
    int displaced=hit;DWORD tid=ev.dwThreadId;CONTEXT c=context();
    hold_others(1);c.EFlags|=0x100;setcontext(&c);resume_event();
    int ok=wait_event(timeout,0);
    if(!ok) fatal("single-step-timeout");
    if(!exited && ev.dwThreadId==tid) {
        c=context();c.EFlags&=~0x100;setcontext(&c);
    }
    /* Release exactly the threads suspended above, regardless of stopping tid. */
    for(int i=0;i<MAX_THREADS;i++) if(threads[i].handle && threads[i].suspended) {
        if(ResumeThread(threads[i].handle)==(DWORD)-1) fatal("resume-thread");
        threads[i].suspended=0;
    }
    if(displaced>=0 && bp[displaced].used && !exited) {
        BYTE cc=0xcc;
        if(!writemem(bp[displaced].address,&cc,1)) fatal("rearm-breakpoint");
        bp[displaced].armed=1;
    }
    if(hit==displaced) hit=-1;
    return !exited && ev.dwThreadId==tid && strcmp(reason,"step")==0;
}
static void state(void) {
    printf("{\"state\":\"%s\",\"stop_reason\":{\"kind\":\"%s\",\"address\":\"0x%llx\",\"thread\":%lu,\"exception_code\":%lu,\"first_chance\":%lu},\"exit_code\":%lu}",
        exited?"exited":"stopped",reason,(unsigned long long)stop_address,ev.dwThreadId,
        ev.dwDebugEventCode==EXCEPTION_DEBUG_EVENT?ev.u.Exception.ExceptionRecord.ExceptionCode:0,
        ev.dwDebugEventCode==EXCEPTION_DEBUG_EVENT?ev.u.Exception.dwFirstChance:0,exit_code);
}
static void registers(CONTEXT c) {
    printf("{\"rip\":\"0x%llx\",\"rflags\":\"0x%lx\",\"thread\":%lu,\"general\":{",c.Rip,c.EFlags,ev.dwThreadId);
    const char *names[]={"rax","rbx","rcx","rdx","rsi","rdi","rbp","rsp","r8","r9","r10","r11","r12","r13","r14","r15"};
    DWORD64 vals[]={c.Rax,c.Rbx,c.Rcx,c.Rdx,c.Rsi,c.Rdi,c.Rbp,c.Rsp,c.R8,c.R9,c.R10,c.R11,c.R12,c.R13,c.R14,c.R15};
    for(int i=0;i<16;i++) printf("%s\"%s\":\"0x%llx\"",i?",":"",names[i],vals[i]);
    printf("}}");
}
static void b64(const BYTE *data,DWORD n) {
    DWORD size=0;
    if(!CryptBinaryToStringA(data,n,CRYPT_STRING_BASE64|CRYPT_STRING_NOCRLF,NULL,&size)) fatal("encode-size");
    char *encoded=malloc(size);if(!encoded) fatal("allocation");
    if(!CryptBinaryToStringA(data,n,CRYPT_STRING_BASE64|CRYPT_STRING_NOCRLF,encoded,&size)) fatal("encode");
    printf("\"%s\"",encoded);free(encoded);
}
static HWND window;static LONG best_area;
static BOOL CALLBACK findwindow(HWND h,LPARAM unused) {
    DWORD pid;RECT r;(void)unused;GetWindowThreadProcessId(h,&pid);
    if(pid==pi.dwProcessId && IsWindowVisible(h) && GetClientRect(h,&r) && r.right*r.bottom>best_area) {
        best_area=r.right*r.bottom;window=h;
    }return TRUE;
}
static int frame(RECT *r,POINT *p) {
    window=NULL;best_area=0;EnumWindows(findwindow,0);
    if(!window || !GetClientRect(window,r) || r->right<1 || r->bottom<1 || r->right>1920 || r->bottom>1080) return 0;
    p->x=p->y=0;return ClientToScreen(window,p);
}
int main(int argc,char **argv) {
    if(argc!=3) return 64;
    STARTUPINFOA si={0};si.cb=sizeof(si);char command[2048];
    if(snprintf(command,sizeof(command),"\"%s\"",argv[1])>=(int)sizeof(command)) return 64;
    setvbuf(stdout,NULL,_IONBF,0);
    SECURITY_ATTRIBUTES security={sizeof(security),NULL,TRUE};
    HANDLE nul=CreateFileA("NUL",GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_WRITE,&security,OPEN_EXISTING,0,NULL);
    if(nul==INVALID_HANDLE_VALUE) fatal("open-null");
    SetHandleInformation(GetStdHandle(STD_INPUT_HANDLE),HANDLE_FLAG_INHERIT,0);
    SetHandleInformation(GetStdHandle(STD_OUTPUT_HANDLE),HANDLE_FLAG_INHERIT,0);
    SetHandleInformation(GetStdHandle(STD_ERROR_HANDLE),HANDLE_FLAG_INHERIT,0);
    si.dwFlags=STARTF_USESTDHANDLES;si.hStdInput=si.hStdOutput=si.hStdError=nul;
    if(!CreateProcessA(NULL,command,NULL,NULL,TRUE,DEBUG_ONLY_THIS_PROCESS,NULL,NULL,&si,&pi)) fatal("create-process");
    CloseHandle(nul);
    if(wait_event(10000,0)!=2 || !install(image_base+strtoull(argv[2],NULL,0),0)) fatal("install-entry-breakpoint");
    resume_event();if(!wait_event(30000,0) || hit!=0) fatal("entry-breakpoint");
    bp[0].used=0;hit=-1;initializing=0;
    printf("{\"image_base\":\"0x%llx\",\"pid\":%lu,\"session\":",(unsigned long long)image_base,pi.dwProcessId);state();printf("}\n");
    static char line[140000];
    while(fgets(line,sizeof(line),stdin)) {
        char op[32]={0},arg[131074]={0};unsigned long long addr=0;unsigned n=0;
        if(sscanf(line,"%31s",op)!=1) continue;
        if(!strcmp(op,"close")) {TerminateProcess(pi.hProcess,0);printf("{\"state\":\"closed\"}\n");break;}
        if(!strcmp(op,"status")) {state();puts("");continue;}
        if(exited) {puts("{\"error\":\"process-exited\"}");continue;}
        if(!strcmp(op,"registers")) {registers(context());puts("");}
        else if(!strcmp(op,"read") && sscanf(line,"%*s %llx %u",&addr,&n)==2 && n && n<=65536) {
            BYTE *data=malloc(n);if(!data) fatal("allocation");
            if(!readmem(addr,data,n)) puts("{\"error\":\"unreadable-memory\"}");
            else {logical_read(addr,data,n);printf("{\"data_base64\":");b64(data,n);puts("}");}free(data);
        } else if(!strcmp(op,"write") && sscanf(line,"%*s %llx %131073s",&addr,arg)==2) {
            size_t len=strlen(arg);int ok=len>0 && len%2==0 && len<=131072;
            BYTE *data=malloc(len/2);if(!data) fatal("allocation");
            for(size_t i=0;ok && i<len/2;i++) {unsigned byte;if(sscanf(arg+i*2,"%2x",&byte)!=1) ok=0;else data[i]=(BYTE)byte;}
            /* An armed INT3 must never be overwritten by a user edit. */
            for(int i=0;i<MAX_BP;i++) if(bp[i].used && bp[i].address>=addr && bp[i].address<addr+len/2) ok=0;
            if(!ok || !writemem(addr,data,len/2)) puts("{\"error\":\"write-failed-or-breakpoint-overlap\"}");
            else {BYTE *check=malloc(len/2);if(!check || !readmem(addr,check,len/2) || memcmp(check,data,len/2)) fatal("write-readback");free(check);printf("{\"written\":%zu}\n",len/2);}free(data);
        } else if(!strcmp(op,"bp") && sscanf(line,"%*s %llx",&addr)==1) {
            int slot=-1;for(int i=1;i<MAX_BP;i++) if(bp[i].used && bp[i].address==addr) {slot=-2;break;} else if(!bp[i].used && slot==-1) slot=i;
            if(slot<0 || !install(addr,slot)) puts("{\"error\":\"breakpoint-unavailable\"}");
            else printf("{\"breakpoint_id\":\"bp-%d\",\"runtime_address\":\"0x%llx\"}\n",slot,addr);
        } else if(!strcmp(op,"del") && sscanf(line,"%*s %u",&n)==1 && n>0 && n<MAX_BP && bp[n].used) {
            if(bp[n].armed && !writemem(bp[n].address,&bp[n].original,1)) fatal("delete-breakpoint");
            bp[n].used=bp[n].armed=0;if(hit==(int)n) hit=-1;puts("{\"deleted\":true}");
        } else if(!strcmp(op,"run") && sscanf(line,"%*s %u",&n)==1 && n && n<=600000) {
            ULONGLONG deadline=GetTickCount64()+n;
            int proceed=hit<0 || single_step(n);
            if(proceed && !exited) {
                resume_event();DWORD remaining=deadline>GetTickCount64()?(DWORD)(deadline-GetTickCount64()):1;
                if(!wait_event(remaining,0)) {
                    if(!DebugBreakProcess(pi.hProcess) || !wait_event(5000,1)) fatal("timeout-pause");
                }
            }state();puts("");
        } else if(!strcmp(op,"trace") && sscanf(line,"%*s %u %llx",&n,&addr)==2 && n && n<=10000 && addr && addr<=600000) {
            ULONGLONG deadline=GetTickCount64()+addr;unsigned count=0;printf("{\"events\":[");
            while(count<n && !exited && GetTickCount64()<deadline) {
                CONTEXT c=context();BYTE bytes[15];SIZE_T got=0;
                /* Partial reads near an unmapped page still preserve real bytes. */
                for(got=15;got>0 && !readmem(c.Rip,bytes,got);got--) {}
                if(!got) break;
                logical_read(c.Rip,bytes,(int)got);
                ULONGLONG now=GetTickCount64();
                if(now>=deadline || !single_step((DWORD)(deadline-now))) break;
                printf("%s{\"address\":\"0x%llx\",\"bytes\":\"",count?",":"",c.Rip);
                for(SIZE_T j=0;j<got;j++) printf("%02x",bytes[j]);
                printf("\",\"registers\":");registers(c);printf("}");count++;
                /* Honor a breakpoint at the next instruction before stepping it. */
                CONTEXT next=context();int found=-1;
                for(int i=1;i<MAX_BP;i++) if(bp[i].used && bp[i].armed && bp[i].address==next.Rip) found=i;
                if(found>=0) {if(!writemem(next.Rip,&bp[found].original,1)) fatal("trace-breakpoint");bp[found].armed=0;hit=found;strcpy(reason,"breakpoint");stop_address=next.Rip;break;}
            }
            printf("],\"complete\":%s,\"session\":",count==n?"true":"false");state();puts("}");
        } else if(!strcmp(op,"screenshot")) {
            RECT r;POINT p;
            if(!frame(&r,&p)) {puts("{\"error\":\"no-visible-client-window\"}");continue;}
            HDC screen=GetDC(NULL),dc=CreateCompatibleDC(screen);HBITMAP bitmap=CreateCompatibleBitmap(screen,r.right,r.bottom);
            HGDIOBJ old=SelectObject(dc,bitmap);BITMAPINFO info={0};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
            info.bmiHeader.biWidth=r.right;info.bmiHeader.biHeight=-r.bottom;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
            DWORD size=r.right*r.bottom*4;BYTE *pixels=malloc(size);
            int ok=pixels && BitBlt(dc,0,0,r.right,r.bottom,screen,p.x,p.y,SRCCOPY|CAPTUREBLT);
            SelectObject(dc,old);if(ok) ok=GetDIBits(dc,bitmap,0,r.bottom,pixels,&info,DIB_RGB_COLORS)==r.bottom;
            if(ok) {printf("{\"width\":%ld,\"height\":%ld,\"window\":\"0x%llx\",\"bgra_base64\":",r.right,r.bottom,(unsigned long long)(uintptr_t)window);b64(pixels,size);puts("}");}
            else puts("{\"error\":\"capture-failed\"}");
            free(pixels);DeleteObject(bitmap);DeleteDC(dc);ReleaseDC(NULL,screen);
        } else if(!strcmp(op,"click") && sscanf(line,"%*s %llx %u %131073s",&addr,&n,arg)==3) {
            RECT r;POINT p;
            if(!frame(&r,&p) || addr>=(unsigned)r.right || n>=(unsigned)r.bottom) {puts("{\"error\":\"click-outside-client\"}");continue;}
            DWORD down=0,up=0;
            if(!strcmp(arg,"left")) {down=MOUSEEVENTF_LEFTDOWN;up=MOUSEEVENTF_LEFTUP;}
            if(!strcmp(arg,"right")) {down=MOUSEEVENTF_RIGHTDOWN;up=MOUSEEVENTF_RIGHTUP;}
            if(!strcmp(arg,"middle")) {down=MOUSEEVENTF_MIDDLEDOWN;up=MOUSEEVENTF_MIDDLEUP;}
            INPUT input[3];memset(input,0,sizeof(input));for(int i=0;i<3;i++) input[i].type=INPUT_MOUSE;
            input[0].mi.dwFlags=MOUSEEVENTF_MOVE|MOUSEEVENTF_ABSOLUTE;
            input[0].mi.dx=(p.x+(LONG)addr)*65535/(GetSystemMetrics(SM_CXSCREEN)-1);
            input[0].mi.dy=(p.y+(LONG)n)*65535/(GetSystemMetrics(SM_CYSCREEN)-1);
            input[1].mi.dwFlags=down;input[2].mi.dwFlags=up;
            if(!down || SendInput(3,input,sizeof(INPUT))!=3) puts("{\"error\":\"send-input-failed\"}");
            else printf("{\"queued\":true,\"window\":\"0x%llx\"}\n",(unsigned long long)(uintptr_t)window);
        } else puts("{\"error\":\"unsupported-or-invalid-command\"}");
    }
    if(!exited) TerminateProcess(pi.hProcess,0);
    return 0;
}
