/* PE32/PE64 debugger. All target control stays on this Win32 debug-event thread. */
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
static DWORD stepping_tid;
static uintptr_t image_base;
static struct { uintptr_t address; BYTE original; int used, armed; } bp[MAX_BP];
static struct { DWORD id; HANDLE handle; int suspended; } threads[MAX_THREADS];
static char reason[32]="entry";
static uintptr_t stop_address, raw_stop_address;
static uintptr_t access_address, scratch;
static ULONG_PTR access_code;
#define MAX_WATCH 64
#define MAX_GUARDS 512
static struct {uintptr_t address;SIZE_T length;int used;char access[3];} watches[MAX_WATCH], overlays[MAX_WATCH];
static struct {uintptr_t address;DWORD protection;int armed;} pages[MAX_GUARDS];
static int page_count, guard_pending;
static unsigned target_bits;
static int ne_carrier;
static DWORD image_entry_rva;
#define MAX_MODULES 256
static struct {uintptr_t base;DWORD size;unsigned bits;ULONGLONG generation;int loaded;char name[256];} modules[MAX_MODULES];
static ULONGLONG module_revision;
static ULONGLONG state_revision;
typedef struct {uintptr_t address;int module;ULONGLONG generation;} RemoteExport;
static RemoteExport pause_entry32,pause_break32;
static DWORD pause_thread;
static ULONGLONG pause_sequence;
static int pause_pending,pause_verified;
typedef struct { CONTEXT native; WOW64_CONTEXT wow; int native_ldt; } TargetContext;
#define MAX_CONTEXT_CHANGES 4
#define DIAGNOSTIC_STACK_BYTES 128
typedef struct {
    CONTEXT native;
    WOW64_CONTEXT wow;
    DWORD native_error,wow_error;
    int native_ok,wow_ok,wow_attempted;
    ULONGLONG observed_ms;
} ContextObservation;
typedef struct {
    ULONGLONG sequence,state_revision,module_revision;
    DWORD thread,event,bits,submitted_flags,set_error;
    int internal_control,set_ok,native_api;
    TargetContext submitted;
    ContextObservation before,after;
} ContextChange;
static ContextChange context_changes[MAX_CONTEXT_CHANGES];
static unsigned context_change_count,context_change_next;
static ULONGLONG context_change_sequence;
static int context_recording;
static DWORD64 context_ip(const TargetContext *c);
static void context_set_ip(TargetContext *c,DWORD64 value);
static int query_selector(DWORD selector,WOW64_LDT_ENTRY *entry);
static DWORD context_flags(const TargetContext *c) { return target_bits==32?c->wow.EFlags:c->native.EFlags; }
static void context_set_flags(TargetContext *c,DWORD value) {
    if(target_bits==32) {c->wow.EFlags=value;if(c->native_ldt) c->native.EFlags=value;}
    else c->native.EFlags=value;
}
#define MAX_INPUT 1024
static struct { INPUT value; ULONGLONG due; } input_queue[MAX_INPUT];
static unsigned input_count;
static BYTE input_held[512];
static ULONGLONG input_clock_ms,input_started_ms,input_delivered,input_revision,input_tail_due;
static int input_running;
static int owned_foreground(void);
static ULONGLONG input_now(void) {
    return input_clock_ms+(input_running?GetTickCount64()-input_started_ms:0);
}
static void input_pause(void) {
    if(input_running) {input_clock_ms=input_now();input_running=0;}
}

static void fatal(const char *op) {
    printf("{\"error\":\"%s\",\"win32_error\":%lu,\"fatal\":true}\n",op,GetLastError());
    fflush(stdout); if(pi.hProcess) TerminateProcess(pi.hProcess,125); ExitProcess(2);
}
static void json_text(const char *value) {
    putchar('"');
    for(const unsigned char *p=(const unsigned char*)value;*p;p++) {
        if(*p=='"' || *p=='\\') {putchar('\\');putchar(*p);}
        else if(*p<32 || *p>=127) printf("\\u%04x",*p);
        else putchar(*p);
    }
    putchar('"');
}
static void module_loaded(uintptr_t base,HANDLE file) {
    int slot=-1;
    for(int i=0;i<MAX_MODULES;i++) {
        if(modules[i].loaded && modules[i].base==base) {slot=i;break;}
        if(!modules[i].loaded && slot<0) slot=i;
    }
    if(slot<0) fatal("loaded-module-budget");
    memset(&modules[slot],0,sizeof(modules[slot]));modules[slot].base=base;
    modules[slot].loaded=1;modules[slot].generation=++module_revision;
    char path[1024];DWORD length=file?GetFinalPathNameByHandleA(file,path,sizeof(path),0):0;
    if(length && length<sizeof(path)) {
        char *name=path;for(char *p=path;*p;p++) if(*p=='/' || *p=='\\') name=p+1;
        if(strlen(name)<sizeof(modules[slot].name)) strcpy(modules[slot].name,name);
    }
    IMAGE_DOS_HEADER dos;DWORD signature,size;WORD machine,magic;SIZE_T got;
    if(ReadProcessMemory(pi.hProcess,(void*)base,&dos,sizeof(dos),&got) && dos.e_magic==IMAGE_DOS_SIGNATURE &&
       dos.e_lfanew>=64 && dos.e_lfanew<=1048576 &&
       ReadProcessMemory(pi.hProcess,(void*)(base+dos.e_lfanew),&signature,4,&got) && signature==IMAGE_NT_SIGNATURE &&
       ReadProcessMemory(pi.hProcess,(void*)(base+dos.e_lfanew+4),&machine,2,&got) &&
       ReadProcessMemory(pi.hProcess,(void*)(base+dos.e_lfanew+24),&magic,2,&got) &&
       ReadProcessMemory(pi.hProcess,(void*)(base+dos.e_lfanew+24+56),&size,4,&got)) {
        if(machine==IMAGE_FILE_MACHINE_I386 && magic==IMAGE_NT_OPTIONAL_HDR32_MAGIC) modules[slot].bits=32;
        if(machine==IMAGE_FILE_MACHINE_AMD64 && magic==IMAGE_NT_OPTIONAL_HDR64_MAGIC) modules[slot].bits=64;
        if(modules[slot].bits) modules[slot].size=size;
    }
}
static void module_unloaded(uintptr_t base) {
    for(int i=0;i<MAX_MODULES;i++) if(modules[i].loaded && modules[i].base==base) {
        modules[i].loaded=0;module_revision++;return;
    }
}
static void module_state(void) {
    printf("{\"module_revision\":%llu,\"state_revision\":%llu,\"modules\":[",module_revision,state_revision);
    unsigned count=0;
    for(int i=0;i<MAX_MODULES;i++) if(modules[i].loaded) {
        printf("%s{\"base\":\"0x%llx\",\"size\":%lu,\"bits\":%u,\"generation\":%llu,\"name\":",count++?",":"",(unsigned long long)modules[i].base,modules[i].size,modules[i].bits,modules[i].generation);
        json_text(modules[i].name);putchar('}');
    }
    puts("]}");
}
/* Read only bounded, actually loaded I386 PE exports. A host ntdll pointer is
 * not a valid WOW64 thread entry: Wine11 truncates that 64-bit start address. */
static int module_span(int index,DWORD rva,SIZE_T length) {
    return index>=0 && index<MAX_MODULES && modules[index].loaded && modules[index].bits==32 &&
        modules[index].base<=0xffffffffULL && modules[index].size &&
        (DWORD64)modules[index].base+modules[index].size<=0x100000000ULL &&
        rva<=modules[index].size && length<=modules[index].size-rva;
}
static int module_read(int index,DWORD rva,void *data,SIZE_T length) {
    SIZE_T got=0;
    return module_span(index,rva,length) &&
        ReadProcessMemory(pi.hProcess,(void*)(modules[index].base+rva),data,length,&got) && got==length;
}
static int module_string(int index,DWORD rva,char *text,SIZE_T capacity) {
    for(SIZE_T n=0;n<capacity;n++) {
        if((DWORD64)rva+n>0xffffffffULL || !module_read(index,rva+(DWORD)n,text+n,1)) return 0;
        if(!text[n]) return 1;
    }
    return 0;
}
static int module_named32(const char *name) {
    int selected=-1;char dll[260];
    if(snprintf(dll,sizeof(dll),"%s.dll",name)>=(int)sizeof(dll)) return -1;
    for(int i=0;i<MAX_MODULES;i++) if(module_span(i,0,1) &&
        (!_stricmp(modules[i].name,name) || !_stricmp(modules[i].name,dll))) {
        if(selected>=0) return -1;
        selected=i;
    }
    return selected;
}
static int export32(int index,const char *symbol,unsigned depth,RemoteExport *result) {
    IMAGE_DOS_HEADER dos;IMAGE_NT_HEADERS32 nt;IMAGE_EXPORT_DIRECTORY exports;
    if(depth>=8 || !module_read(index,0,&dos,sizeof(dos)) || dos.e_magic!=IMAGE_DOS_SIGNATURE ||
       dos.e_lfanew<64 || dos.e_lfanew>1048576 || !module_read(index,(DWORD)dos.e_lfanew,&nt,sizeof(nt)) ||
       nt.Signature!=IMAGE_NT_SIGNATURE || nt.FileHeader.Machine!=IMAGE_FILE_MACHINE_I386 ||
       nt.FileHeader.SizeOfOptionalHeader<sizeof(nt.OptionalHeader) ||
       nt.OptionalHeader.Magic!=IMAGE_NT_OPTIONAL_HDR32_MAGIC ||
       nt.OptionalHeader.SizeOfImage!=modules[index].size ||
       nt.OptionalHeader.NumberOfRvaAndSizes<=IMAGE_DIRECTORY_ENTRY_EXPORT) return 0;
    IMAGE_DATA_DIRECTORY directory=nt.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT];
    if(directory.Size<sizeof(exports) || !module_span(index,directory.VirtualAddress,directory.Size) ||
       !module_read(index,directory.VirtualAddress,&exports,sizeof(exports)) ||
       !exports.NumberOfFunctions || exports.NumberOfFunctions>65536 || exports.NumberOfNames>65536 ||
       !module_span(index,exports.AddressOfFunctions,(SIZE_T)exports.NumberOfFunctions*4) ||
       !module_span(index,exports.AddressOfNames,(SIZE_T)exports.NumberOfNames*4) ||
       !module_span(index,exports.AddressOfNameOrdinals,(SIZE_T)exports.NumberOfNames*2)) return 0;
    DWORD ordinal=0xffffffff;
    if(symbol[0]=='#') {
        char *end;unsigned long number=strtoul(symbol+1,&end,10);
        if(end==symbol+1 || *end || number<exports.Base || number-exports.Base>=exports.NumberOfFunctions) return 0;
        ordinal=(DWORD)(number-exports.Base);
    } else {
        DWORD low=0,high=exports.NumberOfNames;
        while(low<high) {
            DWORD middle=low+(high-low)/2,rva;WORD entry;char name[256];
            if(!module_read(index,exports.AddressOfNames+middle*4,&rva,4) ||
               !module_string(index,rva,name,sizeof(name))) return 0;
            int comparison=strcmp(name,symbol);
            if(comparison<0) low=middle+1;
            else if(comparison>0) high=middle;
            else {
                if(!module_read(index,exports.AddressOfNameOrdinals+middle*2,&entry,2)) return 0;
                ordinal=entry;break;
            }
        }
    }
    DWORD address;
    if(ordinal>=exports.NumberOfFunctions ||
       !module_read(index,exports.AddressOfFunctions+ordinal*4,&address,4) || !address) return 0;
    if(address>=directory.VirtualAddress && address-directory.VirtualAddress<directory.Size) {
        char forward[256];
        if(!module_string(index,address,forward,sizeof(forward))) return 0;
        char *separator=strrchr(forward,'.');
        if(!separator || separator==forward || !separator[1]) return 0;
        *separator++=0;
        return export32(module_named32(forward),separator,depth+1,result);
    }
    MEMORY_BASIC_INFORMATION memory;
    uintptr_t absolute=modules[index].base+address;
    if(!module_span(index,address,1) || !VirtualQueryEx(pi.hProcess,(void*)absolute,&memory,sizeof(memory)) ||
       memory.State!=MEM_COMMIT || memory.Protect&(PAGE_NOACCESS|PAGE_GUARD) ||
       !(memory.Protect&(PAGE_EXECUTE|PAGE_EXECUTE_READ|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY))) return 0;
    result->address=absolute;result->module=index;result->generation=modules[index].generation;return 1;
}
static int export_current(const RemoteExport *value) {
    return module_span(value->module,0,1) && modules[value->module].generation==value->generation &&
        value->address>=modules[value->module].base &&
        value->address-modules[value->module].base<modules[value->module].size;
}
static void prepare_pause32(void) {
    int ntdll=module_named32("ntdll.dll");BYTE byte=0;
    if(!export32(ntdll,"DbgUiRemoteBreakin",0,&pause_entry32) ||
       !export32(ntdll,"DbgBreakPoint",0,&pause_break32) ||
       !module_read(pause_break32.module,(DWORD)(pause_break32.address-modules[pause_break32.module].base),&byte,1) ||
       byte!=0xcc) fatal("pause32-exports-unavailable");
}
static int request_pause(void) {
    if(target_bits!=32) return DebugBreakProcess(pi.hProcess);
    if(pause_pending || !export_current(&pause_entry32) || !export_current(&pause_break32)) return 0;
    DWORD id=0;
    HANDLE handle=CreateRemoteThread(pi.hProcess,NULL,0,(LPTHREAD_START_ROUTINE)pause_entry32.address,
                                    NULL,CREATE_SUSPENDED,&id);
    if(!handle) return 0;
    pause_thread=id;pause_pending=1;pause_verified=0;pause_sequence++;
    DWORD resumed=ResumeThread(handle);CloseHandle(handle);
    return resumed!=(DWORD)-1;
}
static void guards_temporarily(int restore) {
    DWORD ignored;
    for(int i=0;i<page_count;i++) if(pages[i].armed &&
        !VirtualProtectEx(pi.hProcess,(void*)pages[i].address,4096,
            pages[i].protection|(restore?PAGE_GUARD:0),&ignored)) fatal("guard-debugger-access");
}
static void rearm_guards(void) {
    DWORD ignored;
    for(int i=0;i<page_count;i++) {
        if(!VirtualProtectEx(pi.hProcess,(void*)pages[i].address,4096,pages[i].protection|PAGE_GUARD,&ignored)) fatal("guard-rearm");
        pages[i].armed=1;
    }
    guard_pending=0;
}
static void rebuild_guards(void) {
    int pending_guard=guard_pending;
    DWORD ignored;
    for(int i=0;i<page_count;i++)
        if(!VirtualProtectEx(pi.hProcess,(void*)pages[i].address,4096,pages[i].protection,&ignored)) fatal("guard-remove");
    page_count=0;
    for(int kind=0;kind<2;kind++) for(int n=0;n<MAX_WATCH;n++) {
        uintptr_t start=kind?overlays[n].address:watches[n].address;
        SIZE_T length=kind?overlays[n].length:watches[n].length;
        if(!(kind?overlays[n].used:watches[n].used)) continue;
        if(!length || start+length<start) fatal("guard-range");
        for(uintptr_t p=start&~(uintptr_t)4095;p<start+length;p+=4096) {
            int found=0;for(int j=0;j<page_count;j++) if(pages[j].address==p) found=1;
            if(found) continue;
            MEMORY_BASIC_INFORMATION region;
            if(page_count==MAX_GUARDS || !VirtualQueryEx(pi.hProcess,(void*)p,&region,sizeof(region)) ||
               region.State!=MEM_COMMIT || region.Protect&(PAGE_NOACCESS|PAGE_GUARD)) fatal("guard-page-unavailable");
            pages[page_count].address=p;pages[page_count].protection=region.Protect;pages[page_count].armed=0;page_count++;
        }
    }
    rearm_guards();
    if(pending_guard) {
        for(int i=0;i<page_count;i++) if(pages[i].address==(access_address&~(uintptr_t)4095)) {
            if(!VirtualProtectEx(pi.hProcess,(void*)pages[i].address,4096,pages[i].protection,&ignored)) fatal("guard-pending-protection");
            pages[i].armed=0;
        }
        guard_pending=1;
    }
}
static int readmem(uintptr_t addr,void *data,SIZE_T n) {
    SIZE_T got=0;guards_temporarily(0);
    int ok=ReadProcessMemory(pi.hProcess,(void*)addr,data,n,&got) && got==n;
    guards_temporarily(1);return ok;
}
static int writemem(uintptr_t addr,const void *data,SIZE_T n) {
    DWORD protection,ignored; SIZE_T wrote=0;
    MEMORY_BASIC_INFORMATION region;
    guards_temporarily(0);
    if(!VirtualQueryEx(pi.hProcess,(void*)addr,&region,sizeof(region)) ||
       addr+n<addr || addr+n>(uintptr_t)region.BaseAddress+region.RegionSize) {guards_temporarily(1);return 0;}
    if(!VirtualProtectEx(pi.hProcess,(void*)addr,n,PAGE_EXECUTE_READWRITE,&protection)) {guards_temporarily(1);return 0;}
    int ok=WriteProcessMemory(pi.hProcess,(void*)addr,data,n,&wrote) && wrote==n;
    if(!VirtualProtectEx(pi.hProcess,(void*)addr,n,protection,&ignored)) fatal("restore-page-protection");
    if(!FlushInstructionCache(pi.hProcess,(void*)addr,n)) fatal("flush-instruction-cache");
    guards_temporarily(1);
    return ok;
}
static void addthread(DWORD id,HANDLE h) {
    for(int i=0;i<MAX_THREADS;i++) if(!threads[i].handle) {
        threads[i].id=id;threads[i].handle=h;
        if(stepping_tid && id!=stepping_tid) {
            if(SuspendThread(h)==(DWORD)-1) fatal("suspend-new-thread");
            threads[i].suspended=1;
        }
        return;
    }
    fatal("thread-budget");
}
static HANDLE thread(DWORD id) {
    for(int i=0;i<MAX_THREADS;i++) if(threads[i].handle && threads[i].id==id) return threads[i].handle;
    fatal("unknown-thread"); return NULL;
}
static TargetContext context(void) {
    TargetContext c;memset(&c,0,sizeof(c));
    if(!pending || exited) fatal("get-context-unpaused");
    if(target_bits==32) {
        c.wow.ContextFlags=WOW64_CONTEXT_FULL;
        if(!Wow64GetThreadContext(thread(ev.dwThreadId),&c.wow)) fatal("get-wow64-context");
        if(c.wow.SegCs&4) {
            WOW64_LDT_ENTRY descriptor;c.native.ContextFlags=CONTEXT_ALL;
            if(!GetThreadContext(thread(ev.dwThreadId),&c.native)) fatal("get-ldt-native-context");
            if(c.native.SegCs!=c.wow.SegCs || !query_selector(c.wow.SegCs,&descriptor) ||
               !descriptor.HighWord.Bits.Pres || !(descriptor.HighWord.Bits.Type&8)) fatal("ldt-native-context-mismatch");
            if(!descriptor.HighWord.Bits.Default_Big) {
                DWORD required=CONTEXT_CONTROL|CONTEXT_INTEGER|CONTEXT_SEGMENTS;
                if((c.native.ContextFlags&required)!=required) fatal("ldt-native-context-groups");
                /* Wine's stopped16-bit signal context is native. A deferred
                 * WOW CONTROL overlay would truncate its full native RSP. */
                c.native_ldt=1;
                c.wow.Eip=(DWORD)c.native.Rip;c.wow.EFlags=c.native.EFlags;
                c.wow.SegCs=c.native.SegCs;c.wow.SegSs=c.native.SegSs;
                c.wow.SegDs=c.native.SegDs;c.wow.SegEs=c.native.SegEs;
                c.wow.SegFs=c.native.SegFs;c.wow.SegGs=c.native.SegGs;
                c.wow.Eax=(DWORD)c.native.Rax;c.wow.Ebx=(DWORD)c.native.Rbx;
                c.wow.Ecx=(DWORD)c.native.Rcx;c.wow.Edx=(DWORD)c.native.Rdx;
                c.wow.Esi=(DWORD)c.native.Rsi;c.wow.Edi=(DWORD)c.native.Rdi;
                c.wow.Ebp=(DWORD)c.native.Rbp;c.wow.Esp=(DWORD)c.native.Rsp;
            }
        }
    } else {
        c.native.ContextFlags=CONTEXT_FULL;
        if(!GetThreadContext(thread(ev.dwThreadId),&c.native)) fatal("get-context");
    }
    return c;
}
/* Diagnostic reads never choose one architecture as a substitute for another. */
static void observe_context(HANDLE handle,ContextObservation *observed) {
    memset(observed,0,sizeof(*observed));observed->observed_ms=GetTickCount64();
    observed->native.ContextFlags=CONTEXT_ALL;
    SetLastError(0);observed->native_ok=GetThreadContext(handle,&observed->native);
    observed->native_error=observed->native_ok?0:GetLastError();
    if(target_bits==32) {
        observed->wow_attempted=1;observed->wow.ContextFlags=WOW64_CONTEXT_ALL;
        SetLastError(0);observed->wow_ok=Wow64GetThreadContext(handle,&observed->wow);
        observed->wow_error=observed->wow_ok?0:GetLastError();
    }
}
static void setcontext_api(TargetContext *c,int native_api,int internal_control) {
    ContextChange *change=NULL;HANDLE handle=thread(ev.dwThreadId);
    DWORD submitted_flags=native_api?c->native.ContextFlags:c->wow.ContextFlags;
    if(context_recording) {
        change=&context_changes[context_change_next];memset(change,0,sizeof(*change));
        change->sequence=++context_change_sequence;change->state_revision=state_revision;
        change->module_revision=module_revision;change->thread=ev.dwThreadId;
        change->event=ev.dwDebugEventCode;change->bits=target_bits;
        change->submitted_flags=submitted_flags;change->submitted=*c;
        change->internal_control=internal_control;change->native_api=native_api;
        observe_context(handle,&change->before);
        context_change_next=(context_change_next+1)%MAX_CONTEXT_CHANGES;
        if(context_change_count<MAX_CONTEXT_CHANGES) context_change_count++;
    }
    SetLastError(0);int ok;
    if(native_api) ok=SetThreadContext(handle,&c->native);
    else ok=Wow64SetThreadContext(handle,&c->wow);
    DWORD error=ok?0:GetLastError();
    if(change) {change->set_ok=ok;change->set_error=error;observe_context(handle,&change->after);}
    if(!ok) {SetLastError(error);fatal(native_api?"set-context":"set-wow64-context");}
}
static void setcontext(TargetContext *c) {
    setcontext_api(c,target_bits!=32,0);
}
/* Internal IP/TF edits must not rewrite unrelated integer/segment state. */
static void setcontrolcontext(const TargetContext *c) {
    TargetContext control=*c;
    if(target_bits==32 && c->native_ldt) {
        /* A stopped Win16 event exposes a native signal context and a WOW
         * projection. Both control views must agree before continuation. */
        control.native.ContextFlags=CONTEXT_CONTROL;
        setcontext_api(&control,1,1);
        control.wow.ContextFlags=WOW64_CONTEXT_CONTROL;
        setcontext_api(&control,0,1);
        return;
    }
    int native_api=target_bits!=32 || c->native_ldt;
    if(!native_api) control.wow.ContextFlags=WOW64_CONTEXT_CONTROL;
    else control.native.ContextFlags=CONTEXT_CONTROL;
    setcontext_api(&control,native_api,1);
}
/* A Win16 integer edit must update both server views without submitting the
 * WOW control group, which would replace the native 16-bit resume stack. */
static void setintegercontext(const TargetContext *c) {
    TargetContext integer=*c;
    if(!c->native_ldt || target_bits!=32) fatal("integer-context-requires-native-ldt");
    integer.native.ContextFlags=CONTEXT_INTEGER;
    setcontext_api(&integer,1,0);
    integer.wow.ContextFlags=WOW64_CONTEXT_INTEGER;
    setcontext_api(&integer,0,0);
}
static void verify_ldt_integer_context(const TargetContext *before,const TargetContext *requested) {
    ContextObservation observed;observe_context(thread(ev.dwThreadId),&observed);
    const CONTEXT *n=&observed.native;const WOW64_CONTEXT *w=&observed.wow;
    if(!observed.native_ok || !observed.wow_ok ||
       n->Rip!=before->native.Rip || n->Rsp!=before->native.Rsp ||
       n->Rbp!=before->native.Rbp || n->EFlags!=before->native.EFlags ||
       n->SegCs!=before->native.SegCs || n->SegSs!=before->native.SegSs ||
       n->SegDs!=before->native.SegDs || n->SegEs!=before->native.SegEs ||
       n->SegFs!=before->native.SegFs || n->SegGs!=before->native.SegGs ||
       n->R8!=before->native.R8 || n->R9!=before->native.R9 ||
       n->R10!=before->native.R10 || n->R11!=before->native.R11 ||
       n->R12!=before->native.R12 || n->R13!=before->native.R13 ||
       n->R14!=before->native.R14 || n->R15!=before->native.R15 ||
       n->Rax!=requested->native.Rax || n->Rbx!=requested->native.Rbx ||
       n->Rcx!=requested->native.Rcx || n->Rdx!=requested->native.Rdx ||
       n->Rsi!=requested->native.Rsi || n->Rdi!=requested->native.Rdi ||
       w->Eip!=before->wow.Eip || w->Esp!=before->wow.Esp ||
       w->Ebp!=before->wow.Ebp || w->EFlags!=before->wow.EFlags ||
       w->SegCs!=before->wow.SegCs || w->SegSs!=before->wow.SegSs ||
       w->SegDs!=before->wow.SegDs || w->SegEs!=before->wow.SegEs ||
       w->SegFs!=before->wow.SegFs || w->SegGs!=before->wow.SegGs ||
       w->Eax!=requested->wow.Eax || w->Ebx!=requested->wow.Ebx ||
       w->Ecx!=requested->wow.Ecx || w->Edx!=requested->wow.Edx ||
       w->Esi!=requested->wow.Esi || w->Edi!=requested->wow.Edi)
        fatal("ldt-integer-context-mismatch");
}
static int query_selector(DWORD selector,WOW64_LDT_ENTRY *entry) {
    typedef LONG (WINAPI *SelectorQuery)(HANDLE,PVOID,ULONG,PULONG);
    SelectorQuery query=(SelectorQuery)(uintptr_t)GetProcAddress(GetModuleHandleA("ntdll.dll"),"RtlWow64GetThreadSelectorEntry");
    struct {ULONG Selector;WOW64_LDT_ENTRY Entry;} descriptor;memset(&descriptor,0,sizeof(descriptor));
    descriptor.Selector=selector;ULONG returned=0;
    /* Wine11 fills Entry but leaves ReturnLength at zero. Entry fields are the observation. */
    if(!query || query(thread(ev.dwThreadId),&descriptor,sizeof(descriptor),&returned)!=0) return 0;
    *entry=descriptor.Entry;return 1;
}
static DWORD descriptor_base(const WOW64_LDT_ENTRY *entry) {
    return (DWORD)entry->BaseLow|((DWORD)entry->HighWord.Bytes.BaseMid<<16)|((DWORD)entry->HighWord.Bytes.BaseHi<<24);
}
static DWORD descriptor_limit(const WOW64_LDT_ENTRY *entry) {
    DWORD limit=(DWORD)entry->LimitLow|((DWORD)entry->HighWord.Bits.LimitHi<<16);
    return entry->HighWord.Bits.Granularity?(limit<<12)|4095:limit;
}
static DWORD64 context_ip(const TargetContext *c) {
    if(target_bits!=32) return c->native.Rip;
    if(c->wow.SegCs&4) {
        WOW64_LDT_ENTRY entry;
        if(!query_selector(c->wow.SegCs,&entry) || !entry.HighWord.Bits.Pres || !(entry.HighWord.Bits.Type&8) ||
           c->wow.Eip>descriptor_limit(&entry)) fatal("unbound-code-selector");
        return (DWORD64)descriptor_base(&entry)+c->wow.Eip;
    }
    return c->wow.Eip;
}
static void context_set_ip(TargetContext *c,DWORD64 value) {
    if(target_bits!=32) {c->native.Rip=value;return;}
    if(c->wow.SegCs&4) {
        WOW64_LDT_ENTRY entry;
        if(!query_selector(c->wow.SegCs,&entry) || !entry.HighWord.Bits.Pres || !(entry.HighWord.Bits.Type&8) ||
           value<descriptor_base(&entry) || value-descriptor_base(&entry)>descriptor_limit(&entry)) fatal("unbound-code-selector-edit");
        value-=descriptor_base(&entry);
    }
    if(value>0xffffffffULL) fatal("instruction-address-width");
    c->wow.Eip=(DWORD)value;
    if(c->native_ldt) c->native.Rip=value;
}
static unsigned process_bits(void) {
    IMAGE_DOS_HEADER dos;DWORD signature;IMAGE_FILE_HEADER file;WORD magic;SIZE_T got;BOOL wow;
    if(!ReadProcessMemory(pi.hProcess,(void*)image_base,&dos,sizeof(dos),&got) || got!=sizeof(dos) ||
       dos.e_magic!=IMAGE_DOS_SIGNATURE || dos.e_lfanew<64 || dos.e_lfanew>1048576 ||
       !ReadProcessMemory(pi.hProcess,(void*)(image_base+dos.e_lfanew),&signature,sizeof(signature),&got) ||
       signature!=IMAGE_NT_SIGNATURE ||
       !ReadProcessMemory(pi.hProcess,(void*)(image_base+dos.e_lfanew+4),&file,sizeof(file),&got) ||
       !ReadProcessMemory(pi.hProcess,(void*)(image_base+dos.e_lfanew+4+sizeof(file)),&magic,sizeof(magic),&got) ||
       !ReadProcessMemory(pi.hProcess,(void*)(image_base+dos.e_lfanew+24+16),&image_entry_rva,sizeof(image_entry_rva),&got) ||
       !image_entry_rva || !IsWow64Process(pi.hProcess,&wow)) fatal("process-architecture");
    if(file.Machine==IMAGE_FILE_MACHINE_I386 && magic==IMAGE_NT_OPTIONAL_HDR32_MAGIC && wow) return 32;
    if(file.Machine==IMAGE_FILE_MACHINE_AMD64 && magic==IMAGE_NT_OPTIONAL_HDR64_MAGIC && !wow) return 64;
    fatal("unsupported-or-mismatched-process-architecture");return 0;
}
static void input_flush(void) {
    ULONGLONG now=input_now();
    while(input_count && input_queue[0].due<=now) {
        if(!owned_foreground()) fatal("input-target-not-foreground");
        if(SendInput(1,&input_queue[0].value,sizeof(INPUT))!=1) fatal("send-queued-input");
        if(input_queue[0].value.type==INPUT_KEYBOARD) {
            KEYBDINPUT *key=&input_queue[0].value.ki;
            input_held[(key->wScan&255)+((key->dwFlags&KEYEVENTF_EXTENDEDKEY)?256:0)]=(key->dwFlags&KEYEVENTF_KEYUP)?0:1;
        }
        memmove(input_queue,input_queue+1,(--input_count)*sizeof(input_queue[0]));
        input_delivered++;input_revision++;
    }
}
static void input_resume(void) {
    if(!input_running) {input_started_ms=GetTickCount64();input_running=1;}
    input_flush();
}
static void input_state(void) {
    printf("{\"pending\":%u,\"delivered_to_OS\":%llu,\"clock_ms\":%llu,\"revision\":%llu,\"scheduled_until_ms\":%llu,\"idle\":%s,\"application_consumption_observed\":false,\"held\":[",
        input_count,input_delivered,input_now(),input_revision,input_tail_due,(!input_count && input_now()>=input_tail_due)?"true":"false");
    unsigned count=0;
    for(unsigned i=0;i<512;i++) if(input_held[i]) printf("%s{\"scan_code\":%u,\"extended\":%s}",count++?",":"",i&255,i>=256?"true":"false");
    printf("]}");
}
static unsigned input_cleanup(void) {
    unsigned released=0;input_count=0;input_tail_due=input_now();
    for(unsigned i=0;i<512;i++) if(input_held[i]) {
        INPUT event;memset(&event,0,sizeof(event));event.type=INPUT_KEYBOARD;event.ki.wScan=(WORD)(i&255);
        event.ki.dwFlags=KEYEVENTF_SCANCODE|KEYEVENTF_KEYUP|(i>=256?KEYEVENTF_EXTENDEDKEY:0);
        if(SendInput(1,&event,sizeof(event))==1) released++;
        input_held[i]=0;
    }
    input_revision++;return released;
}
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
    pending=0;if(!exited) input_resume();else {input_pause();input_count=0;input_tail_due=input_now();}
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
        input_flush();
        if(!WaitForDebugEvent(&ev,(DWORD)min(10,deadline>GetTickCount64()?deadline-GetTickCount64():0))) {
            if(GetLastError()==ERROR_SEM_TIMEOUT) continue;
            fatal("wait-debug-event");
        }
        input_pause();pending=1;continuation=DBG_CONTINUE;
        switch(ev.dwDebugEventCode) {
        case CREATE_PROCESS_DEBUG_EVENT:
            image_base=(uintptr_t)ev.u.CreateProcessInfo.lpBaseOfImage;
            pi.hProcess=ev.u.CreateProcessInfo.hProcess;
            target_bits=process_bits();
            module_loaded(image_base,ev.u.CreateProcessInfo.hFile);
            addthread(ev.dwThreadId,ev.u.CreateProcessInfo.hThread);
            if(ev.u.CreateProcessInfo.hFile) CloseHandle(ev.u.CreateProcessInfo.hFile);
            /* Entry breakpoint slot zero is installed by main using observed base. */
            return 2;
        case CREATE_THREAD_DEBUG_EVENT:addthread(ev.dwThreadId,ev.u.CreateThread.hThread);break;
        case EXIT_THREAD_DEBUG_EVENT:
            if(pause_pending && ev.dwThreadId==pause_thread) fatal("pause-helper-exited-before-breakpoint");
            for(int i=0;i<MAX_THREADS;i++) if(threads[i].handle && threads[i].id==ev.dwThreadId) {
                CloseHandle(threads[i].handle);memset(&threads[i],0,sizeof(threads[i]));
            } break;
        case LOAD_DLL_DEBUG_EVENT:module_loaded((uintptr_t)ev.u.LoadDll.lpBaseOfDll,ev.u.LoadDll.hFile);if(ev.u.LoadDll.hFile) CloseHandle(ev.u.LoadDll.hFile);break;
        case UNLOAD_DLL_DEBUG_EVENT:module_unloaded((uintptr_t)ev.u.UnloadDll.lpBaseOfDll);break;
        case EXIT_PROCESS_DEBUG_EVENT:
            exited=1;exit_code=ev.u.ExitProcess.dwExitCode;strcpy(reason,"exited");resume_event();return 1;
        case EXCEPTION_DEBUG_EVENT: {
            DWORD code=ev.u.Exception.ExceptionRecord.ExceptionCode;
            raw_stop_address=stop_address=(uintptr_t)ev.u.Exception.ExceptionRecord.ExceptionAddress;
            if(target_bits==32) {
                TargetContext current=context();
                if(current.wow.SegCs&4) {
                    WOW64_LDT_ENTRY entry;
                    if(!query_selector(current.wow.SegCs,&entry) || !entry.HighWord.Bits.Pres) fatal("exception-code-selector");
                    /* Wine16 debug events report the code offset, not the LDT linear address. */
                    if(stop_address<=descriptor_limit(&entry)) stop_address+=descriptor_base(&entry);
                }
            }
            if(code==STATUS_GUARD_PAGE_VIOLATION && ev.u.Exception.ExceptionRecord.NumberParameters>=2) {
                uintptr_t fault=(uintptr_t)ev.u.Exception.ExceptionRecord.ExceptionInformation[1];
                for(int i=0;i<page_count;i++) if((fault&~(uintptr_t)4095)==pages[i].address) {
                    pages[i].armed=0;guard_pending=1;access_address=fault;
                    access_code=ev.u.Exception.ExceptionRecord.ExceptionInformation[0];
                    strcpy(reason,"memory-access");return 1;
                }
            }
            if(code==EXCEPTION_BREAKPOINT) {
                if(target_bits==32 && pause_pending && ev.dwThreadId==pause_thread &&
                   export_current(&pause_break32) && stop_address==pause_break32.address) {
                    pause_pending=0;pause_verified=1;strcpy(reason,"timeout");return 1;
                }
                for(int i=0;i<MAX_BP;i++) if(bp[i].used && bp[i].armed && bp[i].address==stop_address) {
                    TargetContext c=context();
                    if(!writemem(stop_address,&bp[i].original,1)) fatal("restore-breakpoint-byte");
                    bp[i].armed=0;context_set_ip(&c,stop_address);setcontrolcontext(&c);hit=i;
                    strcpy(reason,initializing?(ne_carrier?"carrier-entry":"entry"):"breakpoint");return 1;
                }
                if(pausing && target_bits!=32) {strcpy(reason,"timeout");return 1;}
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
    int displaced=hit;DWORD tid=ev.dwThreadId;TargetContext c=context();
    stepping_tid=tid;
    hold_others(1);context_set_flags(&c,context_flags(&c)|0x100);setcontrolcontext(&c);resume_event();
    int ok=wait_event(timeout,0);
    if(!ok) fatal("single-step-timeout");
    stepping_tid=0;
    if(!exited && ev.dwThreadId!=tid) fatal("step-thread-mismatch");
    if(!exited && ev.dwThreadId==tid) {
        c=context();context_set_flags(&c,context_flags(&c)&~0x100);setcontrolcontext(&c);
    }
    /* Release exactly the threads suspended above, regardless of stopping tid. */
    for(int i=0;i<MAX_THREADS;i++) if(threads[i].handle && threads[i].suspended) {
        if(ResumeThread(threads[i].handle)==(DWORD)-1) fatal("resume-thread");
        threads[i].suspended=0;
    }
    int completed=!exited && ev.dwThreadId==tid && strcmp(reason,"step")==0;
    if(completed && displaced>=0 && bp[displaced].used) {
        BYTE cc=0xcc;
        if(!writemem(bp[displaced].address,&cc,1)) fatal("rearm-breakpoint");
        bp[displaced].armed=1;
    }
    if(completed) {if(hit==displaced) hit=-1;rearm_guards();}
    return completed;
}
static void state(void) {
    printf("{\"architecture\":\"x86-%u\",\"bits\":%u,\"state_revision\":%llu,\"state\":\"%s\",\"stop_reason\":{\"kind\":\"%s\",\"address\":\"0x%llx\",\"raw_address\":\"0x%llx\",\"thread\":%lu,\"exception_code\":%lu,\"first_chance\":%lu,\"access_address\":\"0x%llx\",\"access_code\":%llu,\"before_access\":%s},\"exit_code\":%lu",
        target_bits,target_bits,state_revision,exited?"exited":"stopped",reason,(unsigned long long)stop_address,(unsigned long long)raw_stop_address,ev.dwThreadId,
        ev.dwDebugEventCode==EXCEPTION_DEBUG_EVENT?ev.u.Exception.ExceptionRecord.ExceptionCode:0,
        ev.dwDebugEventCode==EXCEPTION_DEBUG_EVENT?ev.u.Exception.dwFirstChance:0,
        (unsigned long long)access_address,(unsigned long long)access_code,!strcmp(reason,"memory-access")?"true":"false",exit_code);
    if(target_bits==32 && pause_sequence) {
        printf(",\"pause_helper\":{\"mechanism\":\"observed-target32-ntdll-export\",\"sequence\":%llu,\"thread\":%lu,\"entry\":\"0x%llx\",\"breakpoint\":\"0x%llx\",\"module_base\":\"0x%llx\",\"module_generation\":%llu,\"pending\":%s,\"verified_breakpoint\":%s}",
            pause_sequence,pause_thread,(unsigned long long)pause_entry32.address,(unsigned long long)pause_break32.address,
            (unsigned long long)modules[pause_entry32.module].base,pause_entry32.generation,
            pause_pending?"true":"false",pause_verified?"true":"false");
    }
    putchar('}');
}
static void registers(TargetContext c) {
    if(target_bits==32) {
        printf("{\"architecture\":\"x86-32\",\"bits\":32,\"context_source\":\"%s\",\"eip\":\"0x%lx\",\"eflags\":\"0x%lx\",\"cs\":\"0x%lx\",\"ds\":\"0x%lx\",\"ss\":\"0x%lx\",\"es\":\"0x%lx\",\"fs\":\"0x%lx\",\"gs\":\"0x%lx\",\"thread\":%lu,\"general\":{",c.native_ldt?"native-ldt-low32":"wow64",c.wow.Eip,c.wow.EFlags,c.wow.SegCs,c.wow.SegDs,c.wow.SegSs,c.wow.SegEs,c.wow.SegFs,c.wow.SegGs,ev.dwThreadId);
        const char *names[]={"eax","ebx","ecx","edx","esi","edi","ebp","esp"};
        DWORD vals[]={c.wow.Eax,c.wow.Ebx,c.wow.Ecx,c.wow.Edx,c.wow.Esi,c.wow.Edi,c.wow.Ebp,c.wow.Esp};
        for(int i=0;i<8;i++) printf("%s\"%s\":\"0x%lx\"",i?",":"",names[i],vals[i]);
    } else {
        printf("{\"architecture\":\"x86-64\",\"bits\":64,\"context_source\":\"native64\",\"rip\":\"0x%llx\",\"rflags\":\"0x%lx\",\"thread\":%lu,\"general\":{",c.native.Rip,c.native.EFlags,ev.dwThreadId);
        const char *names[]={"rax","rbx","rcx","rdx","rsi","rdi","rbp","rsp","r8","r9","r10","r11","r12","r13","r14","r15"};
        DWORD64 vals[]={c.native.Rax,c.native.Rbx,c.native.Rcx,c.native.Rdx,c.native.Rsi,c.native.Rdi,c.native.Rbp,c.native.Rsp,c.native.R8,c.native.R9,c.native.R10,c.native.R11,c.native.R12,c.native.R13,c.native.R14,c.native.R15};
        for(int i=0;i<16;i++) printf("%s\"%s\":\"0x%llx\"",i?",":"",names[i],vals[i]);
    }
    printf("}}");
}
static int change_register(TargetContext *c,const char *name,unsigned long long value) {
    if(target_bits==32) {
        if(value>0xffffffffULL) return 0;
        if(c->native_ldt) {
#define LDT_REG32(n,wfield,nfield) if(!strcmp(name,n)) { \
            c->wow.wfield=(DWORD)value; \
            c->native.nfield=(c->native.nfield&~0xffffffffULL)|(DWORD)value;return 1;}
            LDT_REG32("eax",Eax,Rax) LDT_REG32("ebx",Ebx,Rbx)
            LDT_REG32("ecx",Ecx,Rcx) LDT_REG32("edx",Edx,Rdx)
            LDT_REG32("esi",Esi,Rsi) LDT_REG32("edi",Edi,Rdi)
#undef LDT_REG32
            return 0;
        }
#define REG32(n,field) if(!strcmp(name,n)) {c->wow.field=(DWORD)value;return 1;}
        REG32("eax",Eax) REG32("ebx",Ebx) REG32("ecx",Ecx) REG32("edx",Edx)
        REG32("esi",Esi) REG32("edi",Edi) REG32("ebp",Ebp) REG32("esp",Esp)
        REG32("eip",Eip) REG32("eflags",EFlags)
#undef REG32
        return 0;
    }
#define REG(n,field) if(!strcmp(name,n)) {c->native.field=value;return 1;}
    REG("rax",Rax) REG("rbx",Rbx) REG("rcx",Rcx) REG("rdx",Rdx)
    REG("rsi",Rsi) REG("rdi",Rdi) REG("rbp",Rbp) REG("rsp",Rsp)
    REG("r8",R8) REG("r9",R9) REG("r10",R10) REG("r11",R11)
    REG("r12",R12) REG("r13",R13) REG("r14",R14) REG("r15",R15) REG("rip",Rip)
#undef REG
    if(!strcmp(name,"rflags") && value<=0xffffffff) {c->native.EFlags=(DWORD)value;return 1;}
    return 0;
}
static void b64(const BYTE *data,DWORD n) {
    DWORD size=0;
    if(!CryptBinaryToStringA(data,n,CRYPT_STRING_BASE64|CRYPT_STRING_NOCRLF,NULL,&size)) fatal("encode-size");
    char *encoded=malloc(size);if(!encoded) fatal("allocation");
    if(!CryptBinaryToStringA(data,n,CRYPT_STRING_BASE64|CRYPT_STRING_NOCRLF,encoded,&size)) fatal("encode");
    /* Keep small protocol replies unbuffered; transfer the already encoded
     * ASCII body in bounded writes instead of formatted character output. */
    DWORD length=(DWORD)strlen(encoded);
    putchar('"');
    for(DWORD offset=0;offset<length;) {
        DWORD count=length-offset;if(count>4096) count=4096;
        if(fwrite(encoded+offset,1,count,stdout)!=count) fatal("encode-output");
        offset+=count;
    }
    putchar('"');free(encoded);
}
static void diagnostic_native(const ContextObservation *observed) {
    printf("{\"api\":\"GetThreadContext\",\"attempted\":true,\"available\":%s,\"requested_flags\":%lu,\"win32_error\":%lu",
        observed->native_ok?"true":"false",(DWORD)CONTEXT_ALL,observed->native_error);
    if(observed->native_ok) {
        const CONTEXT *c=&observed->native;
        printf(",\"returned_flags\":%lu,\"rip\":\"0x%llx\",\"rflags\":\"0x%lx\",\"cs\":%u,\"ds\":%u,\"ss\":%u,\"es\":%u,\"fs\":%u,\"gs\":%u,\"general\":{",
            c->ContextFlags,c->Rip,c->EFlags,c->SegCs,c->SegDs,c->SegSs,c->SegEs,c->SegFs,c->SegGs);
        const char *names[]={"rax","rbx","rcx","rdx","rsi","rdi","rbp","rsp","r8","r9","r10","r11","r12","r13","r14","r15"};
        DWORD64 values[]={c->Rax,c->Rbx,c->Rcx,c->Rdx,c->Rsi,c->Rdi,c->Rbp,c->Rsp,c->R8,c->R9,c->R10,c->R11,c->R12,c->R13,c->R14,c->R15};
        for(unsigned i=0;i<16;i++) printf("%s\"%s\":\"0x%llx\"",i?",":"",names[i],values[i]);
        printf("},\"raw_layout\":\"win64-CONTEXT\",\"raw_bytes\":%zu,\"raw_base64\":",sizeof(*c));
        b64((const BYTE*)c,(DWORD)sizeof(*c));
    }
    putchar('}');
}
static void diagnostic_wow(const ContextObservation *observed) {
    printf("{\"api\":\"Wow64GetThreadContext\",\"attempted\":%s,\"available\":%s,\"requested_flags\":%lu,\"win32_error\":%lu",
        observed->wow_attempted?"true":"false",observed->wow_ok?"true":"false",(DWORD)WOW64_CONTEXT_ALL,observed->wow_error);
    if(observed->wow_ok) {
        const WOW64_CONTEXT *c=&observed->wow;
        printf(",\"returned_flags\":%lu,\"eip\":\"0x%lx\",\"eflags\":\"0x%lx\",\"cs\":%lu,\"ds\":%lu,\"ss\":%lu,\"es\":%lu,\"fs\":%lu,\"gs\":%lu,\"general\":{",
            c->ContextFlags,c->Eip,c->EFlags,c->SegCs,c->SegDs,c->SegSs,c->SegEs,c->SegFs,c->SegGs);
        const char *names[]={"eax","ebx","ecx","edx","esi","edi","ebp","esp"};
        DWORD values[]={c->Eax,c->Ebx,c->Ecx,c->Edx,c->Esi,c->Edi,c->Ebp,c->Esp};
        for(unsigned i=0;i<8;i++) printf("%s\"%s\":\"0x%lx\"",i?",":"",names[i],values[i]);
        printf("},\"raw_layout\":\"WOW64_CONTEXT\",\"raw_bytes\":%zu,\"raw_base64\":",sizeof(*c));
        b64((const BYTE*)c,(DWORD)sizeof(*c));
    } else if(!observed->wow_attempted) printf(",\"reason\":\"target-is-not-wow64\"");
    putchar('}');
}
static void diagnostic_observation(const ContextObservation *observed) {
    printf("{\"observed_tick_ms\":%llu,\"native64\":",observed->observed_ms);
    diagnostic_native(observed);printf(",\"wow32\":");diagnostic_wow(observed);putchar('}');
}
/* Do not call readmem(): an observation must not disarm or rearm guard pages. */
static int diagnostic_read(uintptr_t address,BYTE *data,SIZE_T length,DWORD *error) {
    *error=0;
    if(!length || length>DIAGNOSTIC_STACK_BYTES || address+length<address) {*error=ERROR_INVALID_PARAMETER;return 0;}
    for(SIZE_T copied=0;copied<length;) {
        MEMORY_BASIC_INFORMATION region;uintptr_t current=address+copied;
        SetLastError(0);
        if(!VirtualQueryEx(pi.hProcess,(void*)current,&region,sizeof(region))) {*error=GetLastError();return 0;}
        uintptr_t end=(uintptr_t)region.BaseAddress+region.RegionSize;
        DWORD readable=PAGE_READONLY|PAGE_READWRITE|PAGE_WRITECOPY|PAGE_EXECUTE_READ|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY;
        if(region.State!=MEM_COMMIT || region.Protect&(PAGE_NOACCESS|PAGE_GUARD) ||
           !(region.Protect&readable) || end<=current) {*error=ERROR_NOACCESS;return 0;}
        SIZE_T count=length-copied;if(count>end-current) count=end-current;
        SIZE_T got=0;SetLastError(0);
        if(!ReadProcessMemory(pi.hProcess,(void*)current,data+copied,count,&got) || got!=count) {
            *error=GetLastError();if(!*error) *error=ERROR_PARTIAL_COPY;return 0;
        }
        copied+=count;
    }
    return 1;
}
static void diagnostic_flat_stack(const ContextObservation *observed) {
    if(!observed->native_ok ||
       (observed->native.ContextFlags&CONTEXT_CONTROL)!=CONTEXT_CONTROL) {
        printf("{\"available\":false,\"reason\":\"native-control-context-unavailable\"}");return;
    }
    uintptr_t address=(uintptr_t)observed->native.Rsp;BYTE bytes[DIAGNOSTIC_STACK_BYTES];DWORD error;
    int ok=diagnostic_read(address,bytes,sizeof(bytes),&error);
    printf("{\"address_space\":\"raw-native-rsp\",\"address\":\"0x%llx\",\"requested_bytes\":%u,\"available\":%s,\"win32_error\":%lu",
        (unsigned long long)address,DIAGNOSTIC_STACK_BYTES,ok?"true":"false",error);
    if(ok) {printf(",\"bytes\":%zu,\"data_base64\":",sizeof(bytes));b64(bytes,sizeof(bytes));}
    putchar('}');
}
static void diagnostic_wow_stack(const ContextObservation *observed) {
    if(!observed->wow_ok || (observed->wow.ContextFlags&WOW64_CONTEXT_CONTROL)!=WOW64_CONTEXT_CONTROL ||
       !observed->wow.SegSs || observed->wow.SegSs>65535) {
        printf("{\"available\":false,\"reason\":\"wow64-stack-context-unavailable\"}");return;
    }
    WOW64_LDT_ENTRY descriptor,after;DWORD selector=observed->wow.SegSs;
    if(!query_selector(selector,&descriptor) || !descriptor.HighWord.Bits.Pres ||
       !(descriptor.HighWord.Bits.Type&16) || descriptor.HighWord.Bits.Type&8 || !(descriptor.HighWord.Bits.Type&2)) {
        printf("{\"available\":false,\"reason\":\"stack-descriptor-unavailable-or-invalid\",\"selector\":%lu}",selector);return;
    }
    DWORD base=descriptor_base(&descriptor),limit=descriptor_limit(&descriptor);
    DWORD maximum=descriptor.HighWord.Bits.Default_Big?0xffffffff:0xffff;
    DWORD offset=observed->wow.Esp&maximum;int expand_down=(descriptor.HighWord.Bits.Type&4)!=0;
    printf("{\"address_space\":\"observed-ss-descriptor\",\"selector\":%lu,\"base\":\"0x%lx\",\"limit\":\"0x%lx\",\"default_big\":%s,\"type\":%lu,\"offset\":\"0x%lx\"",
        selector,base,limit,descriptor.HighWord.Bits.Default_Big?"true":"false",(DWORD)descriptor.HighWord.Bits.Type,offset);
    if((expand_down && offset<=limit) || (!expand_down && offset>limit)) {
        printf(",\"available\":false,\"reason\":\"stack-offset-outside-descriptor\"}");return;
    }
    DWORD bound=expand_down || limit>maximum?maximum:limit;
    DWORD64 available=(DWORD64)bound-offset+1;
    DWORD length=available<DIAGNOSTIC_STACK_BYTES?(DWORD)available:DIAGNOSTIC_STACK_BYTES;
    DWORD64 address=(DWORD64)base+offset;
    if(address+length>0x100000000ULL) {
        printf(",\"available\":false,\"reason\":\"stack-linear-address-overflow\"}");return;
    }
    BYTE bytes[DIAGNOSTIC_STACK_BYTES];DWORD error;
    int ok=diagnostic_read((uintptr_t)address,bytes,length,&error);
    int stable=query_selector(selector,&after) && !memcmp(&descriptor,&after,sizeof(descriptor));
    printf(",\"address\":\"0x%llx\",\"requested_bytes\":%lu,\"descriptor_stable\":%s,\"available\":%s,\"win32_error\":%lu",
        address,length,stable?"true":"false",ok&&stable?"true":"false",error);
    if(ok && stable) {printf(",\"bytes\":%lu,\"data_base64\":",length);b64(bytes,length);}
    else if(!stable) printf(",\"reason\":\"stack-descriptor-changed\"");
    putchar('}');
}
static void context_diagnostics(void) {
    if(!pending || exited) {puts("{\"error\":\"context-diagnostics-requires-pending-event\"}");return;}
    ContextObservation observed;observe_context(thread(ev.dwThreadId),&observed);
    printf("{\"format\":\"fdisbull-context-diagnostics-1\",\"observation_contract\":\"API observations; runtime conversion and returned context flags remain authoritative\",\"recording_setters\":%s,\"ring_limit\":%u,\"pending_event\":{\"pending\":true,\"event\":%lu,\"process\":%lu,\"thread\":%lu,\"target_bits\":%u,\"state_revision\":%llu,\"module_revision\":%llu,\"continuation\":%lu,\"stepping_thread\":%lu,\"breakpoint_hit\":%d,\"guard_pending\":%s",
        context_recording?"true":"false",MAX_CONTEXT_CHANGES,ev.dwDebugEventCode,ev.dwProcessId,ev.dwThreadId,target_bits,state_revision,module_revision,continuation,stepping_tid,hit,guard_pending?"true":"false");
    unsigned tracked=0,suspended=0;
    for(int i=0;i<MAX_THREADS;i++) if(threads[i].handle) {tracked++;if(threads[i].suspended) suspended++;}
    printf(",\"tracked_threads\":%u,\"owned_suspended_threads\":%u",tracked,suspended);
    if(ev.dwDebugEventCode==EXCEPTION_DEBUG_EVENT) {
        const EXCEPTION_RECORD *record=&ev.u.Exception.ExceptionRecord;
        printf(",\"exception\":{\"code\":%lu,\"flags\":%lu,\"first_chance\":%lu,\"raw_address\":\"0x%llx\",\"nested_record\":\"0x%llx\",\"parameter_count\":%lu,\"parameters\":[",
            record->ExceptionCode,record->ExceptionFlags,ev.u.Exception.dwFirstChance,
            (unsigned long long)(uintptr_t)record->ExceptionAddress,(unsigned long long)(uintptr_t)record->ExceptionRecord,record->NumberParameters);
        for(DWORD i=0;i<record->NumberParameters && i<EXCEPTION_MAXIMUM_PARAMETERS;i++)
            printf("%s\"0x%llx\"",i?",":"",(unsigned long long)record->ExceptionInformation[i]);
        printf("],\"parameters_truncated\":%s}",record->NumberParameters>EXCEPTION_MAXIMUM_PARAMETERS?"true":"false");
    }
    printf("},\"session\":");state();printf(",\"observed_tick_ms\":%llu,\"native64\":",observed.observed_ms);
    diagnostic_native(&observed);printf(",\"wow32\":");diagnostic_wow(&observed);
    printf(",\"stack\":{\"native64\":");diagnostic_flat_stack(&observed);printf(",\"wow32\":");diagnostic_wow_stack(&observed);
    printf("},\"setters\":[");
    unsigned first=(context_change_next+MAX_CONTEXT_CHANGES-context_change_count)%MAX_CONTEXT_CHANGES;
    for(unsigned n=0;n<context_change_count;n++) {
        const ContextChange *change=&context_changes[(first+n)%MAX_CONTEXT_CHANGES];
        printf("%s{\"sequence\":%llu,\"thread\":%lu,\"event\":%lu,\"bits\":%lu,\"state_revision\":%llu,\"module_revision\":%llu,\"kind\":\"%s\",\"setter_api\":\"%s\",\"submitted_flags\":%lu,\"set_succeeded\":%s,\"set_win32_error\":%lu,\"submitted\":{\"raw_layout\":\"%s\",\"raw_bytes\":%zu,\"raw_base64\":",
            n?",":"",change->sequence,change->thread,change->event,change->bits,change->state_revision,change->module_revision,
            change->internal_control?"internal-control":"explicit-registers",change->native_api?"SetThreadContext":"Wow64SetThreadContext",change->submitted_flags,change->set_ok?"true":"false",change->set_error,
            change->native_api?"win64-CONTEXT":"WOW64_CONTEXT",change->native_api?sizeof(change->submitted.native):sizeof(change->submitted.wow));
        if(change->native_api) b64((const BYTE*)&change->submitted.native,sizeof(change->submitted.native));
        else b64((const BYTE*)&change->submitted.wow,sizeof(change->submitted.wow));
        printf("},\"before\":");diagnostic_observation(&change->before);printf(",\"after\":");diagnostic_observation(&change->after);putchar('}');
    }
    puts("]}");
}
static HWND window;static LONG best_area;
static int owned_foreground(void) {
    DWORD pid=0;HWND h=GetForegroundWindow();
    if(h) GetWindowThreadProcessId(h,&pid);
    return pid==pi.dwProcessId;
}
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
    ne_carrier=!strcmp(argv[2],"ne");
    if(!ne_carrier && (!strtoull(argv[2],NULL,0) || strtoull(argv[2],NULL,0)>0xffffffffULL)) return 64;
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
    if(wait_event(10000,0)!=2 || !install(image_base+(ne_carrier?image_entry_rva:strtoull(argv[2],NULL,0)),0)) fatal("install-entry-breakpoint");
    resume_event();if(!wait_event(30000,0) || hit!=0) fatal("entry-breakpoint");
    bp[0].used=0;hit=-1;initializing=0;
    if(target_bits==32) prepare_pause32();
    printf("{\"image_base\":\"0x%llx\",\"pid\":%lu,\"architecture\":\"x86-%u\",\"bits\":%u,\"launch_profile\":\"%s\",\"session\":",(unsigned long long)image_base,pi.dwProcessId,target_bits,target_bits,ne_carrier?"win16-ne-carrier":"pe-original");state();printf("}\n");
    static char line[140000];
    while(fgets(line,sizeof(line),stdin)) {
        char op[32]={0},arg[131074]={0};unsigned long long addr=0;unsigned n=0;
        if(sscanf(line,"%31s",op)!=1) continue;
        if(!strcmp(op,"close")) {unsigned released=input_cleanup();TerminateProcess(pi.hProcess,0);printf("{\"state\":\"closed\",\"released_to_OS\":%u}\n",released);break;}
        if(!strcmp(op,"status")) {state();puts("");continue;}
        if(!strcmp(op,"keyboard-state")) {input_state();puts("");continue;}
        if(exited) {puts("{\"error\":\"process-exited\"}");continue;}
        if(!strcmp(op,"context-diagnostics")) {
            char action[16];unsigned enabled;int consumed=0;
            if(sscanf(line,"%*s %15s %u%n",action,&enabled,&consumed)==2 && !strcmp(action,"record") && enabled<=1 &&
               strspn(line+consumed," \r\n\t")==strlen(line+consumed)) {
                context_recording=(int)enabled;
                if(enabled) {memset(context_changes,0,sizeof(context_changes));context_change_count=context_change_next=0;context_change_sequence=0;}
            } else if(strspn(line+strlen(op)," \r\n\t")!=strlen(line+strlen(op))) {
                puts("{\"error\":\"invalid-context-diagnostics-command\"}");continue;
            }
            context_diagnostics();
        }
        else if(!strcmp(op,"registers")) {registers(context());puts("");}
        else if(!strcmp(op,"modules")) {module_state();}
        else if(!strcmp(op,"selector") && sscanf(line,"%*s %llx",&addr)==1 && addr && addr<=65535 && target_bits==32) {
            WOW64_LDT_ENTRY entry;
            if(!query_selector((DWORD)addr,&entry)) {puts("{\"error\":\"selector-query-unavailable\"}");continue;}
            DWORD base=descriptor_base(&entry),limit=descriptor_limit(&entry);
            printf("{\"selector\":\"0x%llx\",\"base\":\"0x%lx\",\"limit\":\"0x%lx\",\"present\":%s,\"default_big\":%s,\"granularity\":%s,\"type\":%lu,\"dpl\":%lu,\"thread\":%lu,\"module_revision\":%llu,\"state_revision\":%llu}\n",addr,base,limit,
                entry.HighWord.Bits.Pres?"true":"false",entry.HighWord.Bits.Default_Big?"true":"false",entry.HighWord.Bits.Granularity?"true":"false",
                (DWORD)entry.HighWord.Bits.Type,(DWORD)entry.HighWord.Bits.Dpl,ev.dwThreadId,module_revision,state_revision);
        }
        else if(!strcmp(op,"keyboard")) {
            char *cursor=line+strlen(op),*end;
            unsigned long count=strtoul(cursor,&end,10);cursor=end;
            if(!count || count>MAX_INPUT || count>MAX_INPUT-input_count) {puts("{\"error\":\"input-queue-budget\"}");continue;}
            unsigned long duration=strtoul(cursor,&end,10);
            if(end==cursor || duration>60000) {puts("{\"error\":\"invalid-keyboard-duration\"}");continue;}cursor=end;
            INPUT values[MAX_INPUT];DWORD delays[MAX_INPUT];int ok=1;
            memset(values,0,count*sizeof(values[0]));
            for(unsigned long i=0;i<count;i++) {
                unsigned long scan=strtoul(cursor,&end,16);if(end==cursor || !scan || scan>255) {ok=0;break;}cursor=end;
                unsigned long flags=strtoul(cursor,&end,10);if(end==cursor || flags>3) {ok=0;break;}cursor=end;
                unsigned long delay=strtoul(cursor,&end,10);if(end==cursor || delay>60000 || (i && delay<delays[i-1])) {ok=0;break;}cursor=end;
                values[i].type=INPUT_KEYBOARD;values[i].ki.wScan=(WORD)scan;
                values[i].ki.dwFlags=KEYEVENTF_SCANCODE|((flags&1)?KEYEVENTF_KEYUP:0)|((flags&2)?KEYEVENTF_EXTENDEDKEY:0);
                delays[i]=(DWORD)delay;
            }
            if(!ok || duration<delays[count-1] || strspn(cursor," \r\n\t")!=strlen(cursor)) {puts("{\"error\":\"invalid-keyboard-events\"}");continue;}
            ULONGLONG base=input_now();if(input_tail_due>base) base=input_tail_due;
            for(unsigned long i=0;i<count;i++) {input_queue[input_count].value=values[i];input_queue[input_count++].due=base+delays[i];}
            input_tail_due=base+duration;input_revision++;state_revision++;
            printf("{\"queued\":%lu,\"pending\":%u,\"revision\":%llu,\"scheduled_until_ms\":%llu,\"delivery\":\"queued-native-execution-clock\",\"application_consumption_observed\":false}\n",count,input_count,input_revision,input_tail_due);
        }
        else if(!strcmp(op,"guard-arm")) {rearm_guards();puts("{\"armed\":true}");}
        else if(!strcmp(op,"bp-check")) {
            TargetContext c=context();
            for(int i=1;i<MAX_BP;i++) if(bp[i].used && bp[i].armed && bp[i].address==context_ip(&c)) {
                if(!writemem(context_ip(&c),&bp[i].original,1)) fatal("trace-breakpoint-restore");
                bp[i].armed=0;hit=i;strcpy(reason,"breakpoint");stop_address=context_ip(&c);break;
            }
            state();puts("");
        }
        else if(!strcmp(op,"setregs")) {
            TargetContext c=context(),before=c;char *cursor=line+strlen(op),name[16];int consumed,ok=1,count=0;
            while(sscanf(cursor," %15s %llx%n",name,&addr,&consumed)==2) {
                if(++count>18 || !change_register(&c,name,addr)) {ok=0;break;}
                cursor+=consumed;
            }
            if(!ok || !count || strspn(cursor," \r\n\t")!=strlen(cursor)) puts("{\"error\":\"invalid-register-edit\"}");
            else {
                if(c.native_ldt) {setintegercontext(&c);verify_ldt_integer_context(&before,&c);}
                else setcontext(&c);
                state_revision++;stop_address=context_ip(&c);registers(context());puts("");
            }
        } else if(!strcmp(op,"scratch")) {
            if(!scratch) for(unsigned i=0;i<1024 && !scratch;i++) {
                uintptr_t requested=(image_base+0x10000000ULL+i*65536ULL)&~(uintptr_t)65535;
                scratch=(uintptr_t)VirtualAllocEx(pi.hProcess,(void*)requested,4096,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE);
            }
            if(!scratch) puts("{\"error\":\"no-near-execution-buffer\"}");
            else printf("{\"address\":\"0x%llx\",\"size\":4096}\n",(unsigned long long)scratch);
        } else if(!strcmp(op,"overlay")) {
            char *cursor=line+strlen(op);unsigned long count=strtoul(cursor,&cursor,10);
            if(count>MAX_WATCH) {puts("{\"error\":\"overlay-range-budget\"}");continue;}
            memset(overlays,0,sizeof(overlays));int ok=1;
            for(unsigned long i=0;i<count;i++) {
                char *end;uintptr_t start=(uintptr_t)strtoull(cursor,&end,16);if(end==cursor) {ok=0;break;}cursor=end;
                unsigned long length=strtoul(cursor,&end,10);if(end==cursor || !length || length>65536 || start+length<start) {ok=0;break;}cursor=end;
                overlays[i].address=start;overlays[i].length=length;overlays[i].used=1;
            }
            if(!ok || strspn(cursor," \r\n\t")!=strlen(cursor)) fatal("invalid-overlay-ranges");
            rebuild_guards();puts("{\"configured\":true}");
        }
        else if(!strcmp(op,"step") && sscanf(line,"%*s %u",&n)==1 && n && n<=600000) {
            single_step(n);state_revision++;state();puts("");
        } else if(!strcmp(op,"watch") && sscanf(line,"%*s %llx %u %2s",&addr,&n,arg)==3 && n && n<=65536 &&
                (!strcmp(arg,"r") || !strcmp(arg,"w") || !strcmp(arg,"rw"))) {
            int slot=-1;for(int i=0;i<MAX_WATCH;i++) if(!watches[i].used) {slot=i;break;}
            if(slot<0) {puts("{\"error\":\"watchpoint-budget\"}");continue;}
            watches[slot].address=addr;watches[slot].length=n;watches[slot].used=1;strcpy(watches[slot].access,arg);
            rebuild_guards();printf("{\"breakpoint_id\":\"wp-%d\",\"before_access\":true}\n",slot);
        } else if(!strcmp(op,"unwatch") && sscanf(line,"%*s %u",&n)==1 && n<MAX_WATCH && watches[n].used) {
            watches[n].used=0;rebuild_guards();puts("{\"deleted\":true}");
        }
        else if(!strcmp(op,"read") && sscanf(line,"%*s %llx %u",&addr,&n)==2 && n && n<=65536) {
            BYTE *data=malloc(n);if(!data) fatal("allocation");
            if(!readmem(addr,data,n)) puts("{\"error\":\"unreadable-memory\"}");
            else {logical_read(addr,data,n);printf("{\"data_base64\":");b64(data,n);puts("}");}free(data);
        } else if(!strcmp(op,"code") && sscanf(line,"%*s %llx",&addr)==1) {
            BYTE bytes[15];int got;
            for(got=15;got>0 && !readmem(addr,bytes,got);got--) {}
            if(!got) puts("{\"error\":\"unreadable-code\"}");
            else {logical_read(addr,bytes,got);printf("{\"data_base64\":");b64(bytes,got);puts("}");}
        } else if(!strcmp(op,"write") && sscanf(line,"%*s %llx %131073s",&addr,arg)==2) {
            size_t len=strlen(arg);int ok=len>0 && len%2==0 && len<=131072;
            BYTE *data=malloc(len/2);if(!data) fatal("allocation");
            for(size_t i=0;ok && i<len/2;i++) {unsigned byte;if(sscanf(arg+i*2,"%2x",&byte)!=1) ok=0;else data[i]=(BYTE)byte;}
            /* An armed INT3 must never be overwritten by a user edit. */
            for(int i=0;i<MAX_BP;i++) if(bp[i].used && bp[i].address>=addr && bp[i].address<addr+len/2) ok=0;
            if(!ok || !writemem(addr,data,len/2)) puts("{\"error\":\"write-failed-or-breakpoint-overlap\"}");
            else {BYTE *check=malloc(len/2);if(!check || !readmem(addr,check,len/2) || memcmp(check,data,len/2)) fatal("write-readback");free(check);state_revision++;printf("{\"written\":%zu}\n",len/2);}free(data);
        } else if(!strcmp(op,"bp") && sscanf(line,"%*s %llx",&addr)==1) {
            int slot=-1;for(int i=1;i<MAX_BP;i++) if(bp[i].used && bp[i].address==addr) {slot=-2;break;} else if(!bp[i].used && slot==-1) slot=i;
            if(slot<0 || !install(addr,slot)) puts("{\"error\":\"breakpoint-unavailable\"}");
            else printf("{\"breakpoint_id\":\"bp-%d\",\"runtime_address\":\"0x%llx\"}\n",slot,addr);
        } else if(!strcmp(op,"del") && sscanf(line,"%*s %u",&n)==1 && n>0 && n<MAX_BP && bp[n].used) {
            if(bp[n].armed && !writemem(bp[n].address,&bp[n].original,1)) fatal("delete-breakpoint");
            bp[n].used=bp[n].armed=0;if(hit==(int)n) hit=-1;puts("{\"deleted\":true}");
        } else if((!strcmp(op,"run") || !strcmp(op,"slice")) && sscanf(line,"%*s %u",&n)==1 && n && n<=600000) {
            ULONGLONG deadline=GetTickCount64()+n;
            int proceed=(hit<0 && !guard_pending) || single_step(n);
            if(proceed && !exited) {
                resume_event();DWORD remaining=deadline>GetTickCount64()?(DWORD)(deadline-GetTickCount64()):1;
                if(!wait_event(remaining,0)) {
                    if(!request_pause() || !wait_event(5000,1)) fatal("timeout-pause");
                }
            }
            if(!strcmp(op,"slice") && !strcmp(reason,"timeout")) strcpy(reason,"slice");
            state_revision++;state();puts("");
        } else if(!strcmp(op,"trace") && sscanf(line,"%*s %u %llx",&n,&addr)==2 && n && n<=10000 && addr && addr<=600000) {
            ULONGLONG deadline=GetTickCount64()+addr;unsigned count=0;printf("{\"events\":[");
            while(count<n && !exited && GetTickCount64()<deadline) {
                TargetContext c=context();BYTE bytes[15];SIZE_T got=0;
                /* Partial reads near an unmapped page still preserve real bytes. */
                for(got=15;got>0 && !readmem(context_ip(&c),bytes,got);got--) {}
                if(!got) break;
                logical_read(context_ip(&c),bytes,(int)got);
                ULONGLONG now=GetTickCount64();
                if(now>=deadline || !single_step((DWORD)(deadline-now))) break;
                printf("%s{\"address\":\"0x%llx\",\"bytes\":\"",count?",":"",context_ip(&c));
                for(SIZE_T j=0;j<got;j++) printf("%02x",bytes[j]);
                printf("\",\"registers\":");registers(c);printf("}");count++;
                /* Honor a breakpoint at the next instruction before stepping it. */
                TargetContext next=context();int found=-1;
                for(int i=1;i<MAX_BP;i++) if(bp[i].used && bp[i].armed && bp[i].address==context_ip(&next)) found=i;
                if(found>=0) {if(!writemem(context_ip(&next),&bp[found].original,1)) fatal("trace-breakpoint");bp[found].armed=0;hit=found;strcpy(reason,"breakpoint");stop_address=context_ip(&next);break;}
            }
            state_revision++;printf("],\"complete\":%s,\"session\":",count==n?"true":"false");state();puts("}");
        } else if(!strcmp(op,"screenshot")) {
            RECT r;POINT p;
            if(!frame(&r,&p)) {puts("{\"error\":\"no-visible-client-window\"}");continue;}
            HDC screen=GetDC(NULL),dc=CreateCompatibleDC(screen);HBITMAP bitmap=CreateCompatibleBitmap(screen,r.right,r.bottom);
            HGDIOBJ old=SelectObject(dc,bitmap);BITMAPINFO info={0};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
            info.bmiHeader.biWidth=r.right;info.bmiHeader.biHeight=-r.bottom;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
            DWORD size=r.right*r.bottom*4;BYTE *pixels=malloc(size);
            int ok=pixels && BitBlt(dc,0,0,r.right,r.bottom,screen,p.x,p.y,SRCCOPY|CAPTUREBLT);
            SelectObject(dc,old);if(ok) ok=GetDIBits(dc,bitmap,0,r.bottom,pixels,&info,DIB_RGB_COLORS)==r.bottom;
            if(ok) {printf("{\"width\":%ld,\"height\":%ld,\"window\":\"0x%llx\",\"pid\":%lu,\"state_revision\":%llu,\"frame_revision\":%llu,\"bgra_base64\":",r.right,r.bottom,(unsigned long long)(uintptr_t)window,pi.dwProcessId,state_revision,state_revision);b64(pixels,size);puts("}");}
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
            unsigned hold=0;int consumed=0;
            int fields=sscanf(line,"%*s %llx %u %131073s %u%n",&addr,&n,arg,&hold,&consumed);
            if(fields==4) {
                if(!down || hold>5000 || !hold || input_count>MAX_INPUT-3 || strspn(line+consumed," \r\n\t")!=strlen(line+consumed)) {puts("{\"error\":\"invalid-click-queue\"}");continue;}
                ULONGLONG base=input_now();if(input_tail_due>base) base=input_tail_due;
                for(unsigned i=0;i<3;i++) {input_queue[input_count].value=input[i];input_queue[input_count++].due=base+(i==2?hold:0);}
                input_tail_due=base+hold;input_revision++;state_revision++;
                printf("{\"queued\":3,\"pending\":%u,\"window\":\"0x%llx\",\"revision\":%llu,\"delivery\":\"queued-native-execution-clock\",\"hold_ms\":%u}\n",input_count,(unsigned long long)(uintptr_t)window,input_revision,hold);
            } else if(!down || !owned_foreground() || SendInput(3,input,sizeof(INPUT))!=3) puts("{\"error\":\"send-input-failed\"}");
            else {state_revision++;printf("{\"queued\":true,\"window\":\"0x%llx\"}\n",(unsigned long long)(uintptr_t)window);}
        } else puts("{\"error\":\"unsupported-or-invalid-command\"}");
    }
    input_cleanup();if(!exited) TerminateProcess(pi.hProcess,0);
    return 0;
}
