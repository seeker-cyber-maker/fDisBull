"""Guest serial bridge to one owned DOSBox. Target files are explicitly uploaded."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import termios
import tty

from remote.dosbox_rpc import DOSBoxRPC, DebuggerError

LIMIT=96*1024*1024
NATIVE='/opt/fdisbull/dosbox-x'
RESOURCES=('init','opt/fdisbull/dos_broker.py','opt/fdisbull/remote/__init__.py','opt/fdisbull/remote/dosbox_rpc.py')
client=None;target=None


def identity():
    return dict(protocol='fdisbull-dosbox-qemu-1',guest_kernel=os.uname().release,
                resources={name:hashlib.sha256(Path('/'+name).read_bytes()).hexdigest() for name in RESOURCES},
                emulator_sha256=hashlib.sha256(Path(NATIVE).read_bytes()).hexdigest())


def stage(params):
    files=params['files'];seen=set();total=0
    if not isinstance(files,list) or not 1<=len(files)<=1024:raise ValueError('Invalid DOS file allowlist')
    directory=Path('/work/game');directory.mkdir(mode=0o700)
    for item in files:
        name=item['path']
        if not isinstance(name,str) or not name or '\\' in name or ':' in name or '\0' in name or Path(name).is_absolute() or '..' in Path(name).parts or Path(name).as_posix()!=name or name.casefold() in seen:
            raise ValueError('Invalid guest path')
        if Path(name).suffix.lower() in ('.fdb','.db','.sqlite','.sqlite3','.sav','.state'):raise ValueError('Excluded state/database asset')
        seen.add(name.casefold());data=base64.b64decode(item['data_base64'],validate=True);total+=len(data)
        if total>64*1024*1024 or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('DOS upload budget/hash mismatch')
        path=directory/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(data)
    if params['target'].casefold() not in seen or '/' in params['target']:raise ValueError('Target must be a supplied top-level file')
    return directory


def invoke(method,params):
    global client,target
    if method=='identity':return identity()
    if method=='dos.start':
        if client is not None:raise ValueError('Guest already owns DOSBox')
        directory=stage(params);target=params['target'];client=DOSBoxRPC(NATIVE,directory)
        return dict(capabilities=client.capabilities,pid=client.process.pid,emulator_sha256=identity()['emulator_sha256'])
    if client is None:raise ValueError('No live DOSBox')
    if method=='dos.manifest':
        files=[];total=0
        for p in sorted(Path('/work/game').rglob('*')):
            if p.is_symlink():raise ValueError('Guest file symlink is not allowed')
            if p.is_file():
                total+=p.stat().st_size
                if total>256*1024*1024 or len(files)>=4096:raise ValueError('Guest disk manifest exceeds budget')
                files.append(dict(path=p.relative_to('/work/game').as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        return dict(files=files)
    if method=='dos.rpc':
        operation=params['method'];arguments=params.get('params',{})
        if operation=='session.start':
            if arguments.get('target')!={'command':target,'arguments':[]} or arguments.get('break_at')!='entry':raise ValueError('Target launch differs from uploaded program')
            arguments=dict(arguments,mounts=[dict(drive='C',host_path='/work/game')])
        if operation in ('state.save','state.load'):raise ValueError('Use bounded state transfer')
        if not operation.startswith(('agent.','session.','execution.','state.','memory.','breakpoints.','trace.','video.','input.','layers.')):
            raise ValueError('Unsupported DOS operation: '+operation)
        try:return dict(native=client.call(operation,arguments,timeout_ms=params.get('timeout_ms',15000)))
        except DebuggerError as error:
            # A valid native rejection (for example, a framebuffer invalidated
            # by state restore) retains the same recoverability as direct DOS.
            if client.reader is None or client.writer is None:raise
            return dict(rejected=str(error))
    if method in ('dos.save','dos.load'):
        path=Path('/work/native-state.sav');path.unlink(missing_ok=True)
        try:
            if method=='dos.load':
                data=base64.b64decode(params['data_base64'],validate=True)
                if not 1<=len(data)<=64*1024*1024 or hashlib.sha256(data).hexdigest()!=params['sha256']:raise ValueError('State transfer budget/hash mismatch')
                path.write_bytes(data)
            result=client.call('state.load' if method=='dos.load' else 'state.save',dict(params['params'],path=str(path)),timeout_ms=120000)
            if method=='dos.save':
                if not 1<=path.stat().st_size<=64*1024*1024:raise ValueError('Native DOS state exceeds transfer budget')
                data=path.read_bytes();return dict(native=result,data_base64=base64.b64encode(data).decode(),sha256=hashlib.sha256(data).hexdigest())
            return result
        finally:path.unlink(missing_ok=True)
    raise ValueError('Unsupported DOS bridge operation')


def main():
    serial=os.open('/dev/ttyS1',os.O_RDWR|os.O_NOCTTY);tty.setraw(serial,termios.TCSANOW)
    attributes=termios.tcgetattr(serial);attributes[4]=attributes[5]=termios.B4000000;termios.tcsetattr(serial,termios.TCSANOW,attributes)
    channel=io.BufferedRWPair(os.fdopen(os.dup(serial),'rb',buffering=0),os.fdopen(serial,'wb',buffering=0),65536)
    def send(value):
        data=json.dumps(value,separators=(',',':'),allow_nan=False).encode()+b'\n'
        if len(data)>LIMIT:raise ValueError('Guest reply exceeds budget')
        channel.write(data);channel.flush()
    try:
        send(identity())
        while True:
            line=channel.readline(LIMIT+1)
            if not line:break
            if len(line)>LIMIT or not line.endswith(b'\n'):raise ValueError('Guest request exceeds budget')
            request=json.loads(line)
            try:send(dict(id=request['id'],result=invoke(request['method'],request.get('params',{}))))
            except Exception as error:
                send(dict(id=request.get('id'),error=str(error)));break
    finally:
        if client is not None:client.close()
        channel.close()


if __name__=='__main__':main()
