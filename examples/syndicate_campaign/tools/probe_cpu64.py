"""Linux/i386 single-step diagnostic execution, not a DOS/DOS4GW runtime.
Only exact original instruction bytes in the selected RX range execute.
Interrupts, port I/O and out-of-range fetches stop BEFORE dispatch.
No game source or initialized guest snapshot is distributed by this script.
"""
import ctypes as C,os,signal,subprocess,struct,time,resource,hashlib,json,tempfile,platform
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_32
ROOT=Path(__import__('os').environ['SYNDICATE_PRIVATE']).resolve()
LIB=C.CDLL(None,use_errno=True);LIB.ptrace.restype=C.c_long;LIB.ptrace.argtypes=[C.c_uint,C.c_int,C.c_void_p,C.c_void_p]
FIELDS='r15 r14 r13 r12 rbp rbx r11 r10 r9 r8 rax rcx rdx rsi rdi orig_rax rip cs eflags rsp ss fs_base gs_base ds es fs gs'.split()
class Regs(C.Structure):_fields_=[(n,C.c_ulonglong) for n in FIELDS]
REGS={'eax':'rax','ebx':'rbx','ecx':'rcx','edx':'rdx','esi':'rsi','edi':'rdi','ebp':'rbp','esp':'rsp','eip':'rip','eflags':'eflags'}
CS=Cs(CS_ARCH_X86,CS_MODE_32)
REGIONS={int(p.stem.split('-')[1],16):p.read_bytes() for p in ROOT.glob('region-*.bin')}
CODE=REGIONS[0x10000];RETURN=0x08049063
if platform.system()!='Linux' or platform.machine()!='x86_64':
 raise RuntimeError('requires Linux x86-64 with ptrace and compatibility execution')
if any((p/'.git').exists() for p in (ROOT,*ROOT.parents)):
 raise ValueError('private work directory must be outside Git')
manifest=json.loads((ROOT/'region-manifest.json').read_text())
if manifest['original_sha256']!='bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078':
 raise ValueError('this study supports only its pinned original MAIN.EXE')
if any(hashlib.sha256(data).hexdigest()!=manifest['regions'][hex(base)]['sha256'] for base,data in REGIONS.items()):
 raise ValueError('region identity mismatch')
RW=[(0x50000,0x64000),(0x70000,0x71000),(0x80000,0x9d000),(0x1000000,0x1100000),(0x2000000,0x2010000)]
def covered(a,n,ranges):
 return type(a) is int and type(n) is int and n>=0 and any(lo<=a and a+n<=hi for lo,hi in ranges)


def pt(req,pid,addr=0,data=0):
 C.set_errno(0)
 val=LIB.ptrace(req,pid,C.c_void_p(addr),C.cast(data,C.c_void_p) if not isinstance(data,int) else C.c_void_p(data))
 if val==-1:
  e=C.get_errno()
  if e:raise OSError(e,os.strerror(e))
 return val

def get(pid):
 r=Regs();pt(12,pid,0,C.byref(r));return r

def _deadline_signal(signum, frame):
 raise TimeoutError("wall limit")

def run(entry,registers=None,writes=None,observe=None,stop_at=(),max_steps=20000,seconds=3.0):
 registers=registers or {};writes=writes or {};observe=observe or []
 if not 1<=max_steps<=200000 or not 0<seconds<=30:raise ValueError('invalid probe budget')
 if any(k not in REGS for k in registers):raise ValueError('unknown register')
 if any(not covered(a,len(b),RW) for a,b in writes.items()):raise ValueError('write outside writable profile')
 if any(not covered(a,n,[(0x10000,0x50000)]+RW) for a,n in observe):raise ValueError('observation outside mapped profile')
 fd,temporary=tempfile.mkstemp(prefix='probe-',dir=ROOT);path=Path(temporary);f=os.fdopen(fd,'w+b');f.truncate(0x2010000)
 for base,b in REGIONS.items():f.seek(base);f.write(b)
 f.seek(0x200ff00);f.write(struct.pack('<I',RETURN))
 for a,b in writes.items():f.seek(a);f.write(b)
 f.flush();before={a:os.pread(f.fileno(),n,a) for a,n in observe}
 def limits():
  resource.setrlimit(resource.RLIMIT_CPU,(2,2));resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 p=subprocess.Popen([str(ROOT/'slice_loader64'),str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,preexec_fn=limits)
 result={'entry':hex(entry),'registers_supplied':registers,'steps':0,'trace':[],'source_unchanged':True,'execution':'native Linux/i386 diagnostic; not DOS','reason':None}
 try:
  deadline=time.monotonic()+seconds
  old_handler=signal.signal(signal.SIGALRM,_deadline_signal);signal.setitimer(signal.ITIMER_REAL,seconds)
  while True:
   pid,status=os.waitpid(p.pid,os.WNOHANG)
   if pid:break
   if time.monotonic()>deadline:raise TimeoutError('loader startup limit')
   time.sleep(.001)
  if not os.WIFSTOPPED(status):raise RuntimeError(f'loader startup {status}')
  r=get(p.pid)
  for n in ['rax','rbx','rcx','rdx','rsi','rdi','rbp']:setattr(r,n,0)
  r.cs=0x23;r.ss=0x2b;r.ds=0x2b;r.es=0x2b;r.fs=0;r.gs=0;r.fs_base=0;r.gs_base=0;r.rip=entry;r.rsp=0x200ff00;r.eflags=0x202
  for k,v in registers.items():setattr(r,REGS[k],v&0xffffffff)
  pt(13,p.pid,0,C.byref(r));deadline=time.monotonic()+seconds
  for count in range(max_steps):
   r=get(p.pid);ip=r.rip
   if ip==RETURN:result['reason']='returned';break
   if ip in stop_at:result['reason']='selected_stop';break
   if not 0x10000<=ip<0x10000+len(CODE):result['reason']='outside_original_code';break
   ins=next(CS.disasm(CODE[ip-0x10000:ip-0x10000+15],ip,count=1),None)
   if ins is None:result['reason']='invalid_instruction';break
   if ins.mnemonic in ['int','int3','syscall','sysenter','in','out','insb','insw','insd','outsb','outsw','outsd','hlt','cli','sti','iret','iretd']:
    result['reason']='blocked_environment_instruction';break
   result['trace'].append(hex(ip));pt(9,p.pid)
   pid,status=os.waitpid(p.pid,0)
   if time.monotonic()>deadline:raise TimeoutError('wall limit')
   result['steps']=count+1
   if not os.WIFSTOPPED(status):result['reason']='guest_exited';break
   if os.WSTOPSIG(status)!=signal.SIGTRAP:
    result['reason']='signal';result['signal']=os.WSTOPSIG(status);r=get(p.pid);break
  else:result['reason']='instruction_budget';r=get(p.pid)
  result['final_regs']={k:hex(getattr(r,v)) for k,v in REGS.items()}
 except Exception as e:result['reason']='harness_error';result['error']=str(e)
 finally:
  signal.setitimer(signal.ITIMER_REAL,0)
  if 'old_handler' in locals():signal.signal(signal.SIGALRM,old_handler)
  try:os.kill(p.pid,signal.SIGKILL)
  except ProcessLookupError:pass
  try:os.waitpid(p.pid,0)
  except ChildProcessError:pass
 result['observations']={hex(a):{'before':before[a].hex(),'after':os.pread(f.fileno(),n,a).hex()} for a,n in observe};f.close();path.unlink(missing_ok=True)
 result['harness_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 result['loader_sha256']=hashlib.sha256((ROOT/'slice_loader64').read_bytes()).hexdigest()
 return result
if __name__=='__main__':
 # Ret-only original target tests actual loader, ptrace, mapped code and sentinel return.
 print(json.dumps(run(0x3d640),indent=2))
