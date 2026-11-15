"""Guest-only serial bridge. No host mounts, networking, shell commands or paths."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import termios
import time
import tty
import zlib

LIMIT = 96 * 1024 * 1024
AGENT_HASH = hashlib.sha256(Path('/opt/fdisbull/agent.c').read_bytes()).hexdigest()
serial = os.open('/dev/ttyS1', os.O_RDWR | os.O_NOCTTY)
tty.setraw(serial, termios.TCSANOW)
attributes=termios.tcgetattr(serial)
attributes[4]=attributes[5]=termios.B4000000
termios.tcsetattr(serial,termios.TCSANOW,attributes)
channel = io.BufferedRWPair(os.fdopen(os.dup(serial),'rb',buffering=0),
                            os.fdopen(serial,'wb',buffering=0),65536)
process = None

# A fast serial upload must not race Xvfb's asynchronous startup.
display_deadline=time.monotonic()+15
while True:
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as display:
        try:
            display.connect('/tmp/.X11-unix/X99')
            break
        except (FileNotFoundError,ConnectionRefusedError):
            if time.monotonic()>=display_deadline:raise RuntimeError('Guest Xvfb did not become ready')
            time.sleep(.05)
for directory_name in ('prefix','runtime','cache'):
    Path('/work',directory_name).mkdir(mode=0o700,exist_ok=True)


def send(value):
    data = json.dumps(value, separators=(',', ':'), allow_nan=False).encode() + b'\n'
    if len(data) > LIMIT:
        raise ValueError('Response exceeds message budget')
    channel.write(data)
    channel.flush()


def response(timeout=30, *, unavailable_capture=False):
    data = bytearray()
    deadline = time.monotonic() + timeout
    while b'\n' not in data:
        remaining = deadline-time.monotonic()
        if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
            raise TimeoutError('Windows agent response deadline')
        chunk = os.read(process.stdout.fileno(), 65536)
        if not chunk:
            raise RuntimeError('Windows agent closed its channel')
        data.extend(chunk)
        if len(data) > 16*1024*1024:
            raise ValueError('Windows agent response exceeds budget')
    if data.find(b'\n') != len(data)-1:
        raise ValueError('Unsolicited Windows agent output')
    result = json.loads(data)
    if 'error' in result:
        # These two screenshot outcomes are complete, read-only observations.
        # No HWND exists at a normal entry stop; retaining that session is safe.
        if unavailable_capture and result['error'] in ('no-visible-client-window','capture-failed'):
            return {'available':False,'reason':result['error']}
        raise RuntimeError(str(result))
    return result


def number(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid integer parameter')
    return value


def screenshot_payload(result):
    """Bound and losslessly compress one fresh native BGRA observation."""
    if not isinstance(result,dict):raise ValueError('Invalid Windows capture response')
    if result.get('available') is False:
        if 'bgra_base64' in result or 'bgra_zlib_base64' in result:
            raise ValueError('Unavailable Windows capture contains pixels')
        return result
    width=number(result.get('width'),1,1920);height=number(result.get('height'),1,1080)
    size=width*height*4
    encoded=result.get('bgra_base64')
    if ('bgra_zlib_base64' in result or not isinstance(encoded,str)
            or len(encoded)!=4*((size+2)//3)):
        raise ValueError('Invalid Windows capture BGRA encoding or size')
    try:raw=base64.b64decode(encoded,validate=True)
    except (ValueError,UnicodeError):raise ValueError('Invalid Windows capture BGRA encoding') from None
    if len(raw)!=size:raise ValueError('Incomplete Windows client capture')
    compressed=zlib.compress(raw,1)
    if len(compressed)>=size:return result
    compact=dict(result)
    del compact['bgra_base64']
    compact['bgra_zlib_base64']=base64.b64encode(compressed).decode('ascii')
    return compact


def stage_files(params):
    """Stage the explicit target allowlist, shared by the debugger engines."""
    files = params['files']
    if not isinstance(files, list) or not 1 <= len(files) <= 1024:
        raise ValueError('Invalid file list')
    directory = Path('/work/game');directory.mkdir(mode=0o700)
    total = 0;seen = set()
    for item in files:
        name = item['path']
        path = directory / name
        if not isinstance(name, str) or not name or '\\' in name or ':' in name or '\x00' in name or Path(name).is_absolute() or '..' in Path(name).parts or name in seen:
            raise ValueError('Non-local or duplicate guest filename')
        seen.add(name)
        data = base64.b64decode(item['data_base64'], validate=True)
        total += len(data)
        if total > 64*1024*1024 or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Upload budget or hash mismatch')
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as out:out.write(data)
    target = params['target']
    if target not in seen or '/' in target:
        raise ValueError('Target must be a supplied top-level file')
    return directory, target


def invoke(method, params):
    global process
    if method=='identity':return identity()
    if method=='selftest.image':
        if process is not None or set(params)-{'bits'}:raise ValueError('Self-test image requires an idle VM and optional bits')
        bits=params.get('bits',64)
        if type(bits) is not int or bits not in (32,64):raise ValueError('Self-test bits must be 32 or 64')
        stem='selftest32' if bits==32 else 'selftest'
        data=Path('/opt/fdisbull/'+stem+'.exe').read_bytes()
        return {'data_base64':base64.b64encode(data).decode(),'sha256':hashlib.sha256(data).hexdigest(),
                'source_sha256':hashlib.sha256(Path('/opt/fdisbull/'+stem+'.c').read_bytes()).hexdigest()}
    if method == 'session.start':
        if process is not None:
            raise ValueError('This VM already owns a target')
        profile=params.get('profile','pe')
        if profile not in ('pe','ne'):raise ValueError('Unsupported Windows launch profile')
        early=params.get('stop_before_loader',False)
        if type(early) is not bool:raise ValueError('stop_before_loader must be boolean')
        if early and (profile!='pe' or params.get('bits',64)!=64):
            raise ValueError('Early loader observation requires the PE64 launch profile')
        directory, target = stage_files(params)
        entry='ne' if profile=='ne' else hex(number(params['entry_rva'],1,0xffffffff))
        for name in ('prefix', 'runtime', 'cache'):
            Path('/work', name).mkdir(mode=0o700, exist_ok=True)
        with open('/work/wine.log', 'ab', buffering=0) as log:
            # Cold prefixes under translated QEMU can exceed three minutes.
            # Keep setup bounded and fail before launching any target on error.
            subprocess.run(['wineboot', '-u'], stdin=subprocess.DEVNULL, stdout=log, stderr=log, timeout=300, check=True)
            command=['wine', '/opt/fdisbull/agent.exe', 'Z:\\work\\game\\'+target, entry]
            if early:command.append('--stop-before-loader')
            process = subprocess.Popen(command,
                cwd=directory, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log)
        return response(90)
    if process is None:
        raise ValueError('No live target')
    if method in ('status','registers','screenshot','close','scratch','bp-check','guard-arm','keyboard-state','modules','thread-info'):
        command = method
    elif method=='loader-control':
        if set(params)!={'stop_on_load'} or type(params['stop_on_load']) is not bool:
            raise ValueError('Loader control requires only boolean stop_on_load')
        command='loader-control '+str(int(params['stop_on_load']))
    elif method=='loader-events':
        if set(params)-{'after','limit'}:raise ValueError('Invalid loader history options')
        command=f"loader-events {number(params.get('after',0),0,2**64-1)} {number(params.get('limit',256),1,256)}"
    elif method=='control-inventory':
        if params:raise ValueError('Control inventory accepts no parameters')
        command='control-inventory'
    elif method=='selector':
        command=f"selector {number(params['selector'],0,65535):x}"
    elif method=='context-diagnostics':
        if set(params)-{'record_setters'} or ('record_setters' in params and type(params['record_setters']) is not bool):
            raise ValueError('Context diagnostics accepts an optional Boolean record_setters')
        command='context-diagnostics'
        if 'record_setters' in params:command+=' record '+str(int(params['record_setters']))
    elif method=='setregs':
        values=params['values']
        names={'rax','rbx','rcx','rdx','rsi','rdi','rbp','rsp','r8','r9','r10','r11','r12','r13','r14','r15','rip','rflags',
               'eax','ebx','ecx','edx','esi','edi','ebp','esp','eip','eflags'}
        if not isinstance(values,dict) or not values or set(values)-names:raise ValueError('Invalid register map')
        command='setregs '+' '.join(f'{name} {number(value,0,2**64-1):x}' for name,value in values.items())
    elif method=='overlay':
        ranges=params['ranges']
        if not isinstance(ranges,list) or len(ranges)>64:raise ValueError('Invalid execution ranges')
        command='overlay '+str(len(ranges))+' '+' '.join(f"{number(r['address'],0,2**64-1):x} {number(r['length'],1,65536)}" for r in ranges)
    elif method in ('run','slice'):
        command = f"{method} {number(params['timeout_ms'],1,600000)}"
    elif method == 'step':
        command = f"step {number(params['timeout_ms'],1,600000)}"
    elif method == 'watch':
        if params['access'] not in ('r','w','rw'):raise ValueError('Invalid watch access')
        command = f"watch {number(params['address'],0,2**64-1):x} {number(params['length'],1,65536)} {params['access']}"
    elif method == 'unwatch':
        command = f"unwatch {number(params['id'],0,63)}"
    elif method == 'trace':
        command = f"trace {number(params['count'],1,10000)} {number(params['timeout_ms'],1,600000):x}"
    elif method == 'read':
        command = f"read {number(params['address'],0,2**64-1):x} {number(params['length'],1,65536)}"
    elif method=='code':
        command=f"code {number(params['address'],0,2**64-1):x}"
    elif method == 'write':
        data = bytes.fromhex(params['data_hex'])
        if not 1 <= len(data) <= 65536:raise ValueError('Invalid write size')
        command = f"write {number(params['address'],0,2**64-1):x} {data.hex()}"
    elif method == 'bp':
        command = f"bp {number(params['address'],0,2**64-1):x}"
    elif method == 'del':
        command = f"del {number(params['id'],1,255)}"
    elif method=='keyboard':
        events=params['events']
        if not isinstance(events,list) or not 1<=len(events)<=1024:raise ValueError('Invalid keyboard event batch')
        parts=[];elapsed=0
        for event in events:
            if not isinstance(event,dict) or set(event)!={'scan_code','down','extended','delay_ms'}:
                raise ValueError('Keyboard events require physical scan, down, extended and delay')
            if type(event['down']) is not bool or type(event['extended']) is not bool:
                raise ValueError('Keyboard edges require Boolean state')
            scan=number(event['scan_code'],1,0x7f);delay=number(event['delay_ms'],0,60000)
            # Offsets are absolute within this batch, as in the native queue.
            # Equal offsets preserve modifier/make/break ordering.
            if delay<elapsed:raise ValueError('Keyboard event offsets must be nondecreasing')
            elapsed=delay
            flags=(0 if event['down'] else 1)|(2 if event['extended'] else 0)
            parts.extend((f'{scan:x}',str(flags),str(delay)))
        duration=number(params.get('duration_ms',elapsed),elapsed,60000)
        command='keyboard '+str(len(events))+' '+str(duration)+' '+' '.join(parts)
    elif method == 'click':
        button = params['button']
        if button not in ('left','right','middle'):raise ValueError('Invalid mouse button')
        command = f"click {number(params['x'],0,1919):x} {number(params['y'],0,1079)} {button}"
        if 'hold_ms' in params:command+=' '+str(number(params['hold_ms'],1,5000))
    else:
        raise ValueError('Unsupported PE operation')
    process.stdin.write(command.encode()+b'\n');process.stdin.flush()
    result=response(params.get('timeout_ms', 15000)/1000+10, unavailable_capture=method=='screenshot')
    return screenshot_payload(result) if method=='screenshot' else result


def identity():
    return {'protocol':'fdisbull-wine-qemu-1','agent_sha256':AGENT_HASH,
      'resources':{name:hashlib.sha256(Path(path).read_bytes()).hexdigest()
                   for name,path in {'init':'/init','opt/fdisbull/agent.c':'/opt/fdisbull/agent.c',
                                     'opt/fdisbull/selftest.c':'/opt/fdisbull/selftest.c',
                                     'opt/fdisbull/selftest32.c':'/opt/fdisbull/selftest32.c',
                                     'opt/fdisbull/broker.py':__file__}.items() if Path(path).is_file()},
      'wine_version':subprocess.check_output(['wine','--version'],stderr=subprocess.DEVNULL,text=True,timeout=10).strip(),
      'guest_kernel':os.uname().release,
      'capabilities':{'windows_ui':True,'keyboard':True,'execution_slices':True,'frame_revision':True,'context_diagnostics':True,'control_inventory':True,
                      'early_loader':True,'loader_events':True,'thread_info':True,'win16_integer_pair':True,'process_profiles':['pe32','pe64']},
      'agent_binary_sha256':hashlib.sha256(Path('/opt/fdisbull/agent.exe').read_bytes()).hexdigest()}

def main():
    send(identity())
    try:
        while True:
            line = channel.readline(LIMIT+1)
            if not line:break
            if len(line)>LIMIT or not line.endswith(b'\n'):raise ValueError('Request budget exceeded')
            request = json.loads(line)
            try:
                result = invoke(request['method'], request.get('params', {}))
                send({'id':request['id'], 'result':result})
            except Exception as error:
                log=Path('/work/wine.log')
                diagnostics=''
                if log.exists():
                    with log.open('rb') as stream:
                        stream.seek(max(0,log.stat().st_size-4096))
                        diagnostics=stream.read(4096).decode(errors='replace')
                send({'id':request.get('id'), 'error':str(error), 'wine_log_tail':diagnostics})
                # Failed native operations may leave uncertain process state. Never resume.
                break
            if request['method']=='close':break
    finally:
        if process is not None:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        channel.close()


if __name__ == '__main__':
    main()
