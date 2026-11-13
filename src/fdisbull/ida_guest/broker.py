"""Private serial controller for IDA's server and an independent GUI helper."""
import base64
import hashlib
from pathlib import Path
import socket
import subprocess
import time

import broker as base
from remote.ida_remote import RemoteDebugger
from remote.ida_trace import collect_trace, pe_registers

client = None
ui = None
server_hash = None
base_identity = base.identity
RESOURCE_NAMES = ('init', 'opt/fdisbull/agent.c', 'opt/fdisbull/broker.py',
    'opt/fdisbull/ida_broker.py', 'opt/fdisbull/ui.c', 'opt/fdisbull/remote/__init__.py',
    'opt/fdisbull/remote/ida_wire.py', 'opt/fdisbull/remote/ida_remote.py', 'opt/fdisbull/remote/ida_trace.py')


def identity():
    result = base_identity()
    result.update(protocol='fdisbull-ida-wine-qemu-1', engine='ida-interface-31', server_sha256=server_hash,
        resources={name: hashlib.sha256(Path('/'+name).read_bytes()).hexdigest() for name in RESOURCE_NAMES},
        ui_binary_sha256=hashlib.sha256(Path('/opt/fdisbull/ui.exe').read_bytes()).hexdigest())
    return result


def registers():
    return pe_registers(client)


def invoke(method, params):
    global client, ui, server_hash
    if method == 'identity':
        return identity()
    if method == 'session.start':
        if base.process is not None:
            raise ValueError('This VM already owns a target')
        directory, target = base.stage_files(params)
        server = params['remote_server']
        data = base64.b64decode(server['data_base64'], validate=True)
        if not 1 <= len(data) <= 32*1024*1024 or hashlib.sha256(data).hexdigest() != server['sha256']:
            raise ValueError('Remote server budget/hash mismatch')
        server_hash = server['sha256']
        server_path = Path('/work/win64_remote.exe')
        with server_path.open('xb') as stream:
            stream.write(data)
        with open('/work/wine.log', 'ab', buffering=0) as log:
            subprocess.run(['wineboot','-u'], stdin=subprocess.DEVNULL, stdout=log, stderr=log, timeout=180, check=True)
            base.process = subprocess.Popen(['wine',str(server_path),'-p23946'], stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        deadline = time.monotonic()+30
        while True:
            try:
                stream = socket.create_connection(('127.0.0.1',23946), timeout=1)
                break
            except OSError:
                if base.process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('IDA server did not become ready')
                time.sleep(.05)
        client = RemoteDebugger(stream,execution_mechanism='page')
        started = client.start('Z:\\work\\game\\'+target, directory='Z:\\work\\game')
        entry = client.image_base + base.number(params['entry_rva'],1,0xffffffff)
        entry_bp = client.breakpoint(entry)
        stopped = client.run(60000)
        if stopped['stop_reason']['kind'] != 'breakpoint' or int(registers()['rip'],16) != entry:
            raise ValueError('IDA failed to stop at the verified PE entry: '+str(stopped))
        client.delete_breakpoint(entry_bp)
        client.displaced = None
        with open('/work/wine.log', 'ab', buffering=0) as log:
            ui = subprocess.Popen(['wine','/opt/fdisbull/ui.exe',str(started['pid'])],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log)
        return dict(image_base=hex(client.image_base), pid=started['pid'], session=stopped,
                    remote_server=dict(sha256=server_hash,interface=client.interface,flags=hex(client.flags)))
    if client is None:
        raise ValueError('No live IDA target')
    if method == 'status':
        return client.last_state
    if method == 'overlay' and params['ranges'] == []:
        return dict(configured=True)
    if method == 'bp-check':
        return client.breakpoint_boundary(client.registers()['rip'])
    if method == 'trace-batch':
        return collect_trace(client, params['count'], params['timeout_ms'])
    if method == 'registers':
        return registers()
    if method == 'setregs':
        values = params['values']
        allowed = {'rax','rbx','rcx','rdx','rsi','rdi','rbp','rsp','rip','rflags', *(f'r{i}' for i in range(8,16))}
        if not isinstance(values,dict) or not values or set(values)-allowed:
            raise ValueError('Invalid register map')
        for name, value in values.items():
            client.set_register('efl' if name=='rflags' else name, base.number(value,0,2**64-1))
        return registers()
    if method in ('read','code'):
        address = base.number(params['address'],0,2**64-1)
        size = 15 if method=='code' else base.number(params['length'],1,65536)
        data = client.read_code(address) if method=='code' else client.read(address,size)
        return dict(data_base64=base64.b64encode(data).decode())
    if method == 'write':
        data = bytes.fromhex(params['data_hex'])
        client.write(base.number(params['address'],0,2**64-1),data)
        return dict(written=len(data))
    if method in ('bp','watch'):
        address = base.number(params['address'],0,2**64-1)
        identifier = client.breakpoint(address,access=params.get('access','x'),length=params.get('length',1))
        return dict(breakpoint_id=identifier,runtime_address=hex(address),
                    mechanism='page' if client.breakpoints[identifier]['page'] else 'hardware', guest_code_modified=False)
    if method in ('del','unwatch'):
        client.delete_breakpoint('bp-'+str(base.number(params['id'],1,2**31-1)))
        return dict(deleted=True)
    if method in ('step','run'):
        return getattr(client,method)(base.number(params['timeout_ms'],1,600000))
    if method in ('screenshot','click'):
        if method=='screenshot':
            command='screenshot'
        else:
            if params['button'] not in ('left','right','middle'):
                raise ValueError('Invalid mouse button')
            command=f"click {base.number(params['x'],0,1919):x} {base.number(params['y'],0,1079)} {params['button']}"
        ui.stdin.write(command.encode()+b'\n')
        ui.stdin.flush()
        owner = base.process
        try:
            base.process = ui
            return base.response()
        finally:
            base.process = owner
    if method == 'close':
        if not client.exited:
            client.checked(14)
        client.close()
        return dict(state='closed')
    raise ValueError('Unsupported IDA engine operation: '+method)


base.identity = identity
base.invoke = invoke
try:
    base.main()
finally:
    if client is not None:
        client.close()
    if ui is not None:
        ui.terminate()
        try:
            ui.wait(timeout=3)
        except subprocess.TimeoutExpired:
            ui.kill()
            ui.wait()
