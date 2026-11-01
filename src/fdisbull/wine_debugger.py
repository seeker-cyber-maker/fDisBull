"""Project-address PE64 debugging through Wine inside an offline QEMU guest."""
from __future__ import annotations
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import time
import uuid

from .debugger import DebugSession, bounded, stamp
from .dosbox_rpc import DebuggerError
from .external_files import _file_name
from .wine_rpc import WineQemuRPC
from .wine_layers import PELayerSessionMixin
from .wine_execution import PEExecutionMixin
from .wine_state import PEStateSessionMixin,get_state,file_hash
from .debug_experiments import ExperimentSessionMixin


class PEDebugSession(ExperimentSessionMixin,PELayerSessionMixin,PEExecutionMixin,PEStateSessionMixin):
    rpc_type=WineQemuRPC
    backend_name='wine-qemu'
    script_operations={'run','click','click-frame','screenshot','trace','breakpoint',
        'delete-breakpoint','registers','memory','write-memory','status','assert',
        'layer-stack','layer-enable','layer-patch','code','capture-code','branch','save-state','load-state','save-anchor-stone','load-anchor-stone','write-registers'}
    # Share artifact persistence, offline grids, and declarative script execution.
    _artifact=DebugSession._artifact
    _event=DebugSession._event
    script=DebugSession.script
    __enter__=DebugSession.__enter__
    __exit__=DebugSession.__exit__
    click_frame=DebugSession.click_frame
    contexts=DebugSession.contexts
    context=DebugSession.context
    machine=DebugSession.machine

    def __init__(self, project, executable, game_dir, *, kernel, initramfs,
                 version=None, files=None, boot_timeout_ms=240000,state=None):
        self.project=project;self.rpc=None;self.closed=False;self.run_id=uuid.uuid4().hex
        self.version=project.version(version)
        if project.meta['format']!='PE' or project.bits!=64 or project.meta['arch']!='x86' or self.version['parent'] is not None:
            raise ValueError('Wine launch requires the original unpatched x86-64 PE version; select version=1 explicitly')
        bounded(boot_timeout_ms,'boot_timeout_ms',1000,600000)
        directory=Path(game_dir).expanduser().resolve(strict=True)
        target=project.meta['filename']
        if not directory.is_dir() or not re.fullmatch(r'[A-Za-z0-9_. -]{1,128}\.exe',target,re.I):
            raise ValueError('PE target must be an ordinary EXE filename inside game_dir')
        from .guest_assets import uploads as prepare_uploads
        uploads=prepare_uploads(project,directory,target,files)
        self.static_base=int(project.meta['loader_metadata']['imagebase'],16)
        self.regions=project.regions(self.version['id'])
        self.module_size=max((r.start+len(r.data)) for r in self.regions)-self.static_base
        self._expected={r.start:bytearray(r.data) for r in self.regions}
        self.breakpoints={};self.watchpoints={};self.mode_id=0;self._frame=None
        try:
            saved=None;native=None
            if state is not None:
                _,saved,native=get_state(project,state,self.version['id'])
                for name,path in zip(('qemu','kernel','initramfs'),(executable,kernel,initramfs)):
                    if file_hash(Path(path).expanduser().resolve(strict=True))!=saved['metadata']['runtime_inputs'][name]['sha256']:
                        raise ValueError('Native state backend identity mismatch: '+name)
                if [{'path':f['path'],'sha256':f['sha256']} for f in uploads]!=saved['metadata']['files']:
                    raise ValueError('Native state program inputs mismatch')
            self.rpc=self.rpc_type(executable,kernel,initramfs,boot_timeout_ms=boot_timeout_ms,restore=native)
            if saved is None:
                launched=self.rpc.call('session.start',{'target':target,'entry_rva':project.meta['entry']-self.static_base,
                    'files':uploads,**getattr(self,'engine_start',{})},timeout_ms=300000)
            else:
                launched={'image_base':saved['metadata']['runtime_image_base'],'pid':saved['metadata']['target_pid'],
                          'session':self.rpc.call('status'),'restored_from':state}
            self.runtime_base=int(launched['image_base'],16);self.delta=self.runtime_base-self.static_base
            self._relocate_expected()
            self.metadata={'backend':self.backend_name,'runtime_profile':'pe64-win32-debug-2',
                'source_sha256':project.meta['source_sha256'],'version_sha256':self.version['sha256'],
                'static_image_base':hex(self.static_base),'runtime_image_base':hex(self.runtime_base),
                'address_mapping':'observed main-module base + project RVA','capabilities':self.rpc.capabilities,
                'runtime_inputs':self.rpc.inputs,'files':[{'path':f['path'],'sha256':f['sha256']} for f in uploads],
                'target_pid':launched['pid'],'qemu_pid':self.rpc.process.pid}
            if 'remote_server' in launched:self.metadata['remote_server']=launched['remote_server']
            self.metadata['guest_runtime']={key:self.rpc.hello[key] for key in
                ('wine_version','guest_kernel','agent_binary_sha256','resources')}
            if saved is not None:self._load_state_host(saved['host'])
            regs=self.registers()
            if saved is None and regs['project_address']!=hex(project.meta['entry']):raise DebuggerError('Observed PE entry differs from project entry')
            if saved is not None:
                for field in ('rip','rflags','general'):
                    if regs[field]!=saved['metadata']['registers'][field]:raise DebuggerError('Native restored registers differ: '+field)
            with project.transaction(True):
                project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',(self.run_id,self.version['id'],stamp(),None,'stopped',json.dumps(self.metadata)))
            self._event('launch',launched);project._live_debuggers.append(self)
        except BaseException:
            if self.rpc:self.rpc.close()
            raise

    def _relocate_expected(self):
        if not self.delta:return
        import lief
        source=bytes(self.project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?',(self.version['id'],)).fetchone()[0])
        binary=lief.PE.parse(list(source))
        for block in binary.relocations:
            for item in block.entries:
                kind=int(item.type)
                if kind==0:continue
                if kind!=10:raise DebuggerError('Unsupported PE relocation type for code verification')
                address=self.static_base+block.virtual_address+item.position
                for start,data in self._expected.items():
                    if start<=address and address+8<=start+len(data):
                        offset=address-start;value=struct.unpack_from('<Q',data,offset)[0]
                        struct.pack_into('<Q',data,offset,(value+self.delta)&((1<<64)-1));break
                else:raise DebuggerError('PE relocation lies outside mapped bytes')

    def call(self, method, params=None, *, timeout_ms=30000):
        if self.closed:raise DebuggerError('Debugger session is closed')
        if method=='layers.configure':return self._configure_pe_layers(params)
        return self.rpc.call(method,params,timeout_ms=timeout_ms)

    def _address(self,address,length=1,executable=False):
        value=self.project._address(address)
        if not any(r.start<=value and value+length<=(r.start+len(r.data)) and (r.executable or not executable) for r in self.regions):
            raise ValueError('Address range is outside the selected PE mapped region')
        return value

    def project_address(self,runtime):
        runtime=int(runtime,16) if isinstance(runtime,str) else runtime
        value=runtime-self.delta
        return hex(value) if any(r.start<=value<(r.start+len(r.data)) for r in self.regions) else None

    def status(self):
        from .debug_semantics import contract
        return {'run':self.run_id,'version':self.version['id'],'live':not self.closed,
                **self.call('status'),'mapping':self.metadata,'semantics':contract(self.backend_name)}

    def registers(self):
        result=self.call('registers');result['project_address']=self.project_address(result['rip'])
        self._layer_setup()
        if self._pending_exec:
            result['native_rip']=result['rip'];result['rip']=self._pending_exec['before']['rip']
            result['project_address']=self.project_address(result['rip']);result['execution_location']='relocated-layer-instruction'
        result['cpu_mode']='long64';return result

    def memory(self,address,*,cs=None,length=16):
        if cs is not None:raise ValueError('PE64 addresses are flat virtual addresses')
        bounded(length,'length',1,65536);value=self._address(address,length)
        result=self.call('read',dict(address=value+self.delta,length=length))
        data=base64.b64decode(result['data_base64'],validate=True)
        if len(data)!=length:raise DebuggerError('Incomplete PE memory read')
        return {**result,'project_address':hex(value),'runtime_address':hex(value+self.delta),'hex':data.hex(),
                'view':'logical-memory-with-owned-INT3-bytes-restored'}

    def write_memory(self,address,data_hex,*,expected_hex):
        self._layer_setup()
        data=bytes.fromhex(data_hex);expected=bytes.fromhex(expected_hex)
        if not 1<=len(data)<=65536 or len(data)!=len(expected):raise ValueError('Memory edit requires equally sized guarded bytes, at most 65536')
        value=self._address(address,len(data));before=self.memory(address,length=len(data))
        if any(value<=a<value+len(data) for a in set(self._ram_applied)|set(self._execution)):
            raise ValueError('Disable overlapping code layers before direct memory editing')
        if any(value<=bp<value+len(data) for bp in self.breakpoints.values()):
            raise ValueError('Delete overlapping execution breakpoints before editing memory')
        if before['hex']!=expected.hex():raise DebuggerError('Memory edit expected bytes differ; edit refused')
        result=self.call('write',dict(address=value+self.delta,data_hex=data.hex()))
        after=self.memory(address,length=len(data))
        if after['hex']!=data.hex():self.close();raise DebuggerError('Memory edit readback mismatch')
        result.update(project_address=hex(value),runtime_address=hex(value+self.delta),before_hex=expected.hex(),after_hex=data.hex(),static_version_unchanged=True)
        self._event('write-memory',result);return result

    def breakpoint(self,address,*,cs=None,access='x',length=1,view='static'):
        if access in ('r','w','rw'):
            if cs is not None or view!='static':raise ValueError('PE64 watchpoints use flat project addresses')
            bounded(length,'length',1,65536);value=self._address(address,length)
            result=self.call('watch',dict(address=value+self.delta,length=length,access=access))
            result.update(run=self.run_id,version=self.version['id'],project_address=hex(value),
                          runtime_address=hex(value+self.delta),access=access,length=length,bytes_verified=False)
            self.watchpoints[result['breakpoint_id']]=dict(address=value,length=length,access=access)
            self._event('watchpoint',result)
            return self._remember_breakpoints(dict(address=address,cs=cs,access=access,length=length,view=view),result)
        if cs is not None or access!='x' or length!=1 or view!='static':
            raise ValueError('PE64 supports x, r, w and rw breakpoints at flat project addresses')
        value=self._address(address,executable=True)
        if value in self.breakpoints.values():raise ValueError('An owned breakpoint already exists at this address')
        snapshot=self.project.disassembly(address=value,version=self.version['id'],lines=1)['instructions']
        if not snapshot or int(snapshot[0]['address'],16)!=value:raise ValueError('Analyze this PE address before setting a disassembly breakpoint')
        size=snapshot[0]['size'];self._address(value,size,True)
        expected=next(bytes(data[value-start:value-start+size]) for start,data in self._expected.items() if start<=value<start+len(data))
        observed=self.memory(value,length=size)['hex']
        if observed!=expected.hex():raise DebuggerError('Runtime code differs from the selected static instruction; breakpoint refused')
        result=self.call('bp',{'address':value+self.delta})
        result.update(run=self.run_id,version=self.version['id'],project_address=hex(value),runtime_bytes=observed,bytes_verified=True)
        self.breakpoints[result['breakpoint_id']]=value;self._event('breakpoint',result)
        return self._remember_breakpoints(dict(address=address,cs=cs,access=access,length=length,view=view),result)

    def delete_breakpoint(self,breakpoint_id):
        if breakpoint_id in self.watchpoints:
            result=self.call('unwatch',{'id':int(breakpoint_id[3:])})
            del self.watchpoints[breakpoint_id];self._forget_breakpoint(breakpoint_id)
            self._event('delete-watchpoint',result);return result
        if breakpoint_id not in self.breakpoints:raise ValueError('Unknown owned PE breakpoint')
        result=self.call('del',{'id':int(breakpoint_id[3:])});del self.breakpoints[breakpoint_id]
        self._forget_breakpoint(breakpoint_id)
        self._event('delete-breakpoint',result);return result

    def run(self,*,timeout_ms=10000,guest_ms=None,fast_forward=False):
        bounded(timeout_ms,'timeout_ms',1,600000)
        if guest_ms is not None or fast_forward is not False:raise ValueError('PE uses host timeout_ms; DOS guest time and fast-forward are unsupported')
        start=time.monotonic();deadline=start+timeout_ms/1000
        result=self._continue_native(deadline)
        stop=result['stop_reason'];stop['project_address']=self.project_address(stop['address'])
        evidence={'run':self.run_id,'outcome':stop['kind'],'timed_out':stop['kind']=='timeout','session':result,
                  'host_elapsed_ms':round((time.monotonic()-start)*1000,3)}
        from .debug_semantics import normalize_stop
        evidence['stop']=normalize_stop(self.backend_name,stop,outcome=evidence['outcome'])
        self._event('run',evidence);return evidence

    def trace(self,name='trace.json',*,count=512,timeout_ms=10000,fast_forward=False):
        from .decoder import decode
        _file_name(name);bounded(count,'count',1,10000);bounded(timeout_ms,'timeout_ms',1,600000)
        if fast_forward is not False:raise ValueError('DOS fast-forward is unsupported for PE')
        result=self._trace_native(count,time.monotonic()+timeout_ms/1000)
        for event in result['events']:
            event['project_address']=self.project_address(event['address'])
            decoded=decode(bytes.fromhex(event['bytes']),int(event['address'],16),'x86',64)
            if decoded:event['instruction']=decoded
        result.update(run=self.run_id,version=self.version['id'],mapping=self.metadata,requested_count=count,
                      semantics='instructions completed by the selected stopped thread; pre-instruction registers; peer threads held per step')
        from .debug_semantics import normalize_trace,contract
        normalize_trace(self.backend_name,result['events'],version=self.version['id'],delta=self.delta)
        result['observation_contract']=contract(self.backend_name)
        if len(result['events'])>count:raise DebuggerError('PE trace exceeds requested count')
        return self._artifact(name,'trace',json.dumps(result,indent=2).encode(),
                              {'event_count':len(result['events']),'complete':result['complete']})

    def screenshot(self,name='screenshot.png',*,grid=False,grid_step=32):
        from PIL import Image
        from .screenshot_grid import validate_step
        _file_name(name);validate_step(grid_step)
        if type(grid) is not bool:raise ValueError('grid must be boolean')
        result=self.call('screenshot');width=result['width'];height=result['height']
        if not (1<=width<=1920 and 1<=height<=1080):raise DebuggerError('Invalid PE frame dimensions')
        pixels=base64.b64decode(result.pop('bgra_base64'),validate=True)
        if len(pixels)!=width*height*4:raise DebuggerError('Invalid PE frame buffer length')
        image=Image.frombytes('RGB',(width,height),pixels,'raw','BGRX');out=io.BytesIO();image.save(out,format='PNG');data=out.getvalue()
        identity=(result['window'],width,height)
        if identity!=self._frame:self.mode_id+=1;self._frame=identity
        result.update(mode_id=self.mode_id,coordinate_space='client-native-pixels',capture='Win32 desktop BitBlt of visible target client rectangle',
                      sha256=hashlib.sha256(data).hexdigest(),backend=self.backend_name)
        raw=self._artifact(name if not grid else name[:248]+'.raw.png','screenshot',data,result)
        return self.project.debug_grid(raw['artifact'],name=name,step=grid_step) if grid else raw

    def click(self,x,y,*,button='left',hold_ms=80,mode_id=None):
        bounded(x,'x',0,1919);bounded(y,'y',0,1079);bounded(hold_ms,'hold_ms',1,1000)
        if button not in ('left','right','middle'):raise ValueError('Invalid mouse button')
        if mode_id is not None and (type(mode_id) is not int or mode_id!=self.mode_id):raise ValueError('Stale PE frame mode')
        # Verify current window identity/dimensions without saving another artifact.
        frame=self.call('screenshot')
        if mode_id is not None and (frame['window'],frame['width'],frame['height'])!=self._frame:raise ValueError('Target client frame changed')
        if x>=frame['width'] or y>=frame['height']:raise ValueError('Click outside client frame')
        result=self.call('click',dict(x=x,y=y,button=button))
        result.update(x=x,y=y,button=button,mode_id=self.mode_id,delivery='Win32 SendInput; down and up queued together',hold_ms_applied=False)
        self._event('click',result);return result

    def close(self):
        if self.closed:return
        result={'state':'interrupted'}
        try:result=self.call('close')
        except Exception as error:result['error']=str(error)
        finally:
            self.rpc.close();self.closed=True;result['process_reaped']=self.rpc.process.poll() is not None
            self._event('close',result)
            with self.project.transaction(True):self.project.db.execute('UPDATE debug_runs SET ended=? WHERE id=?',(stamp(),self.run_id))
            if self in self.project._live_debuggers:self.project._live_debuggers.remove(self)

    def __getattr__(self,name):
        if name in ('save_state','load_state','layers','layer_enable','layer_patch','code','capture_code','branch','cave','hook','hooks','delete_hook'):
            raise ValueError('This DOS-only operation is unsupported by the PE64 backend')
        raise AttributeError(name)
