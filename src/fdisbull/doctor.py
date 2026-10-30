"""Real, disposable debugger acceptance tests using authored fixture source only."""
from __future__ import annotations
import base64
import hashlib
import importlib
import json
from pathlib import Path
import platform
import struct
import sys
import tempfile


def _require(condition,message):
    if not condition:raise RuntimeError(message)


def _dos_image():
    # Mode 13h, DS=CS, read immediate as data, initialize counter at 0100h.
    # Poll INT 33h; while left held increment counter and save CX/DX at 0102h.
    code=bytes.fromhex('b81300cd100e1fb811118b1e0800891e000190b80300cd33f7c301007404ff060001890e020189160401ebe7')
    header=bytearray(64)
    struct.pack_into('<14H',header,0,0x5a4d,64,2,0,4,0,0xffff,0,0x200,0,0,0,28,0)
    return bytes(header)+code+bytes(512-len(code))


def _dos_test(project,debug,step):
    bp=debug.breakpoint('1000:0012')
    stopped=step('execution breakpoint',lambda:debug.run(timeout_ms=10000))
    _require(stopped['stop']['instruction_completed'] is False,'Execution breakpoint stage mismatch')
    _require(debug.memory('1000:0100',length=2)['hex']=='1111','Authored counter not initialized')
    debug.delete_breakpoint(bp['breakpoint_id'])
    layer=debug.layer_patch('doctor fetch','1000:0012',expected_hex='90',data_hex='40',kind='execute')
    capture=debug.capture_code('1000:0012',length=4)
    step('execution overlay',lambda:debug.trace('overlay-trace.json',count=2,timeout_ms=10000))
    _require(debug.memory('1000:0012',length=1)['hex']=='90','Overlay changed source RAM')
    _require(int(debug.registers()['general']['eax'],16)&0xffff==0x1112,'Alternate INC AX did not execute')
    debug.layers([])
    debug.run(guest_ms=100,timeout_ms=10000,fast_forward=True)
    state=step('native save',lambda:debug.save_state('private.sav'))
    frame=step('screenshot',lambda:debug.screenshot('frame.png',grid=True,grid_step=8))
    watch=debug.breakpoint('1000:0100',access='w',length=2)
    click=step('click with coordinate frame',lambda:debug.click_frame(80,80,name='click.png',grid_step=8,hold_ms=30))
    stopped=step('data watch',lambda:debug.run(timeout_ms=10000,fast_forward=True))
    _require(stopped['stop']['trigger']=='watchpoint' and
             stopped['stop']['registers_stage']=='after-access' and
             stopped['stop']['instruction_completed'] is None,'Expected a post-access DOS watch with completion unreported')
    _require(int.from_bytes(bytes.fromhex(debug.memory('1000:0100',length=2)['hex']),'little')>0x1111,'Click did not increment counter')
    for item in watch['breakpoints']:debug.delete_breakpoint(item['breakpoint_id'])
    trace=step('bounded instruction trace',lambda:debug.trace('trace.json',count=96,timeout_ms=10000))
    _require(trace['metadata']['complete'],'Incomplete authored DOS trace')
    _require(debug.memory('1000:0102',length=4)['hex']=='a0005000','Mouse coordinates were not observed by authored DOS code')
    step('native restore',lambda:debug.load_state(state['artifact']))
    _require(debug.memory('1000:0100',length=2)['hex']=='1111','Native restore did not restore counter')
    return {'frame.png':frame['artifact'],'click.png':click['frame']['artifact'],'trace.json':trace['artifact']},capture


def _pe_test(project,debug,exports,step):
    debug.breakpoint(exports['checkpoint'])
    stopped=step('execution breakpoint',lambda:debug.run(timeout_ms=60000))
    _require(stopped['outcome']=='breakpoint','Authored PE did not reach GUI checkpoint')
    state=step('native save',lambda:debug.save_state('private.sav'))
    frame=step('screenshot',lambda:debug.screenshot('frame.png',grid=True,grid_step=8))
    debug.layer_patch('doctor increment','0x%x'%(exports['experiment_value']+1),expected_hex='01000000',data_hex='03000000',kind='execute')
    capture=debug.capture_code(exports['experiment_value'],length=6)
    watch=debug.breakpoint(exports['counter'],access='rw',length=4)
    click=step('click with coordinate frame',lambda:debug.click_frame(80,80,name='click.png',grid_step=8))
    stopped=step('data watch',lambda:debug.run(timeout_ms=60000))
    _require(stopped['stop']['trigger']=='watchpoint' and stopped['stop']['instruction_completed'] is False,'Expected a pre-access PE watch')
    _require(debug.memory(exports['counter'],length=4)['hex']=='07000000','PE watch must stop before access')
    debug.delete_breakpoint(watch['breakpoint_id'])
    _require(debug.run(timeout_ms=60000)['outcome']=='breakpoint','PE did not reach post-click checkpoint')
    _require(debug.memory(exports['counter'],length=4)['hex']=='0a000000','Alternate increment did not execute')
    _require(debug.memory(exports['experiment_value'],length=6)['hex']=='b801000000c3','Overlay changed PE source RAM')
    trace=step('bounded instruction trace',lambda:debug.trace('trace.json',count=4,timeout_ms=20000))
    _require(trace['metadata']['complete'],'Incomplete PE trace')
    step('guarded memory editing',lambda:debug.write_memory(exports['counter'],'29000000',expected_hex='0a000000'))
    step('native restore',lambda:debug.load_state(state['artifact']))
    _require(debug.memory(exports['counter'],length=4)['hex']=='07000000','PE native restore did not restore counter')
    _require(debug.layers()['active']==[],'PE native restore did not restore layer stack')
    return {'frame.png':frame['artifact'],'click.png':click['frame']['artifact'],'trace.json':trace['artifact']},capture


def doctor(*,backend,executable,kernel=None,initramfs=None,output=None,boot_timeout_ms=240000):
    """No user target is accepted. Output contains JSON/PNG only; private DB/state are temporary."""
    if backend not in ('dosbox','dosbox-qemu','wine-qemu'):
        raise ValueError('Doctor supports dosbox, dosbox-qemu and wine-qemu; other backends lack this authored self-test')
    destination=None
    if output is not None:
        destination=Path(output).expanduser().resolve()
        destination.mkdir(parents=True,exist_ok=False)
    from . import __version__
    report={'format':'fdisbull-doctor-1','version':__version__,'backend':backend,'status':'running',
            'python':platform.python_version(),'platform':sys.platform,'architecture':platform.machine(),
            'checks':[],'native_state_restored':False,'artifacts':{},
            'scope':'Authored disposable target; finite debugger acceptance; no game compatibility or timing parity claim'}
    def step(name,action):
        check={'name':name,'status':'running'};report['checks'].append(check)
        try:value=action()
        except Exception as error:
            check.update(status='failed',error=type(error).__name__+': '+str(error));raise
        check['status']='passed';return value
    try:
        def dependencies():
            modules={};failures=[]
            for name in ('capstone','iced_x86','lief','PIL'):
                try:
                    module=importlib.import_module(name)
                    modules[name]={'status':'available','version':getattr(module,'__version__',None)}
                except (ImportError,OSError) as error:
                    modules[name]={'status':'failed','error':type(error).__name__+': '+str(error)}
                    failures.append(name)
            report['dependencies']=modules
            _require(not failures,'Missing or unusable dependencies: '+', '.join(failures))
            from .decoder import decode
            _require(decode(b'\x90',0x1000,'x86',16)['mnemonic']=='nop','Native decoder did not decode NOP')
        step('genuine dependencies and native decoding',dependencies)
        def inputs():
            names={'executable':executable}
            if backend!='dosbox':names.update(kernel=kernel,initramfs=initramfs)
            if any(value is None for value in names.values()):raise ValueError('QEMU doctor requires kernel and initramfs')
            result={}
            for name,value in names.items():
                with Path(value).expanduser().open('rb') as stream:result[name]=hashlib.file_digest(stream,'sha256').hexdigest()
            return result
        report['input_sha256']=step('backend inputs',inputs)
        with tempfile.TemporaryDirectory(prefix='fdisbull-doctor-',dir='/tmp') as private:
            root=Path(private);exports=None
            if backend=='wine-qemu':
                from .wine_rpc import WineQemuRPC
                def authored_image():
                    rpc=WineQemuRPC(executable,kernel,initramfs,boot_timeout_ms=boot_timeout_ms)
                    try:return rpc.call('selftest.image',timeout_ms=30000)
                    finally:rpc.close()
                image=step('compile and retrieve fixed authored source',authored_image)
                raw=base64.b64decode(image['data_base64'],validate=True)
                from .wine_runtime import resources
                _require(hashlib.sha256(raw).hexdigest()==image['sha256'],'Authored PE image hash mismatch')
                _require(hashlib.sha256(resources()['opt/fdisbull/selftest.c'].read_bytes()).hexdigest()==image['source_sha256'],'Authored PE source mismatch')
                binary=root/'SELFTEST.exe';binary.write_bytes(raw)
                import lief
                parsed=lief.PE.parse(str(binary));base=parsed.optional_header.imagebase
                exports={e.name:base+e.address for e in parsed.get_export().entries}
            else:
                binary=root/'SELFTEST.EXE';binary.write_bytes(_dos_image())
            report['authored_target_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
            from .project import Project
            database=root/'private.fdb'
            with Project.create(database,binary) as project:
                project.analyze(start=exports['checkpoint'] if exports else None,max_instructions=128)
                options=dict(backend=backend)
                if backend!='dosbox':options.update(kernel=kernel,initramfs=initramfs,boot_timeout_ms=boot_timeout_ms)
                with step('launch authored target',lambda:project.debugger(executable,root,**options)) as debug:
                    report['capabilities']=debug.rpc.capabilities
                    report['observation_contract']=debug.status()['semantics']
                    artifacts,capture=(_pe_test(project,debug,exports,step) if exports else _dos_test(project,debug,step))
                    report['native_state_restored']=True
                report['temporal_promotion']=step('offline temporal interpretation',lambda:project.debug_promote_code(capture['artifact'],max_instructions=32))
            with Project(database) as project:
                def export():
                    for name,identifier in artifacts.items():
                        path=(destination or root)/name
                        project.debug_export(identifier,path)
                        data=path.read_bytes();report['artifacts'][name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
                    trace=json.loads(((destination or root)/'trace.json').read_text())
                    _require(trace['events'] and 'observation' in trace['events'][0],'Trace lacks normalized observations')
                step('restart and export stored evidence',export)
            _require(hashlib.sha256(binary.read_bytes()).hexdigest()==report['authored_target_sha256'],'Authored input mutated')
        report['status']='passed'
    except Exception as error:
        report['status']='failed'
        if not report['checks'] or report['checks'][-1]['status']!='failed':
            report['checks'].append({'name':'acceptance assertions','status':'failed','error':type(error).__name__+': '+str(error)})
    if destination:(destination/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
