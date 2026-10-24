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


def response(timeout=30):
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
        raise RuntimeError(str(result))
    return result


def number(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid integer parameter')
    return value


def invoke(method, params):
    global process
    if method == 'session.start':
        if process is not None:
            raise ValueError('This VM already owns a target')
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
        entry = number(params['entry_rva'], 1, 0xffffffff)
        for name in ('prefix', 'runtime', 'cache'):
            Path('/work', name).mkdir(mode=0o700, exist_ok=True)
        with open('/work/wine.log', 'ab', buffering=0) as log:
            subprocess.run(['wineboot', '-u'], stdin=subprocess.DEVNULL, stdout=log, stderr=log, timeout=180, check=True)
            process = subprocess.Popen(['wine', '/opt/fdisbull/agent.exe', 'Z:\\work\\game\\'+target, hex(entry)],
                cwd=directory, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log)
        return response(90)
    if process is None:
        raise ValueError('No live target')
    if method in ('status','registers','screenshot','close'):
        command = method
    elif method == 'run':
        command = f"run {number(params['timeout_ms'],1,600000)}"
    elif method == 'trace':
        command = f"trace {number(params['count'],1,10000)} {number(params['timeout_ms'],1,600000):x}"
    elif method == 'read':
        command = f"read {number(params['address'],0,2**64-1):x} {number(params['length'],1,65536)}"
    elif method == 'write':
        data = bytes.fromhex(params['data_hex'])
        if not 1 <= len(data) <= 65536:raise ValueError('Invalid write size')
        command = f"write {number(params['address'],0,2**64-1):x} {data.hex()}"
    elif method == 'bp':
        command = f"bp {number(params['address'],0,2**64-1):x}"
    elif method == 'del':
        command = f"del {number(params['id'],1,255)}"
    elif method == 'click':
        button = params['button']
        if button not in ('left','right','middle'):raise ValueError('Invalid mouse button')
        command = f"click {number(params['x'],0,1919):x} {number(params['y'],0,1079)} {button}"
    else:
        raise ValueError('Unsupported PE operation')
    process.stdin.write(command.encode()+b'\n');process.stdin.flush()
    return response(params.get('timeout_ms', 15000)/1000+10)


send({'protocol':'fdisbull-wine-qemu-1','agent_sha256':AGENT_HASH,
      'resources':{name:hashlib.sha256(Path(path).read_bytes()).hexdigest()
                   for name,path in {'init':'/init','opt/fdisbull/agent.c':'/opt/fdisbull/agent.c',
                                     'opt/fdisbull/broker.py':__file__}.items()},
      'wine_version':subprocess.check_output(['wine','--version'],stderr=subprocess.DEVNULL,text=True,timeout=10).strip(),
      'guest_kernel':os.uname().release,
      'agent_binary_sha256':hashlib.sha256(Path('/opt/fdisbull/agent.exe').read_bytes()).hexdigest()})
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
