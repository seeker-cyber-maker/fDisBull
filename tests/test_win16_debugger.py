"""Source/selector identity contracts; native acceptance remains explicitly opt-in."""
import hashlib
import os
from pathlib import Path
import struct

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.ne import load_ne
from fdisbull.win16_debugger import RemotePEExports, Win16DebugSession
from test_ne_loader import ne_file


def mapped_exports(name='K32WOWCallback16Ex',forward=None):
    data=bytearray(0x2000)
    data[:2]=b'MZ';struct.pack_into('<I',data,60,0x80)
    data[0x80:0x84]=b'PE\0\0';struct.pack_into('<H',data,0x84,0x14c)
    struct.pack_into('<H',data,0x98,0x10b)
    struct.pack_into('<II',data,0x98+96,0x300,0x300)
    struct.pack_into('<IIHHIIIIIII',data,0x300,0,0,0,0,0x390,1,1,1,0x340,0x344,0x348)
    struct.pack_into('<I',data,0x340,0x3c0 if forward else 0x1000)
    struct.pack_into('<I',data,0x344,0x360);struct.pack_into('<H',data,0x348,0)
    data[0x360:0x360+len(name)+1]=name.encode()+b'\0'
    if forward:data[0x3c0:0x3c0+len(forward)+1]=forward.encode()+b'\0'
    return bytes(data)


def test_actual_mapped_i386_export_lookup_and_forwarder_use_observed_generation():
    modules=[dict(base='0x100000',size=0x2000,bits=32,generation=4,name='kernel32.dll'),
             dict(base='0x200000',size=0x2000,bits=32,generation=5,name='krnl386.exe16'),
             dict(base='0x600000000',size=0x2000,bits=64,generation=6,name='kernel32.dll')]
    memory={0x100000:mapped_exports(forward='krnl386.exe16.K32WOWCallback16Ex'),0x200000:mapped_exports()}
    reads=[]
    def read(address,length):
        reads.append((address,length))
        base=next(b for b in memory if b<=address<b+0x2000)
        return memory[base][address-base:address-base+length]
    exports=RemotePEExports(read,modules)
    assert exports.resolve(modules[0],'K32WOWCallback16Ex')==dict(address=0x201000,module='krnl386.exe16',module_base='0x200000',module_generation=5,symbol='K32WOWCallback16Ex')
    assert exports.callback()['address']==0x201000
    assert all(length<=256 for _,length in reads)
    assert exports.resolve(modules[1],'Missing') is None


def test_loader_export_rejects_out_of_module_reads_and_forwarder_cycles():
    module=dict(base='0x100000',size=0x2000,bits=32,generation=1,name='krnl386.exe16')
    data=mapped_exports(forward='krnl386.exe16.K32WOWCallback16Ex')
    exports=RemotePEExports(lambda a,n:data[a-0x100000:a-0x100000+n],[module])
    with pytest.raises(DebuggerError,match='forwarding cycle'):exports.callback()
    with pytest.raises(DebuggerError,match='exceeds'):exports._read(module,0x1fff,2)
    malformed=bytearray(data);struct.pack_into('<I',malformed,60,0x1fff)
    exports=RemotePEExports(lambda a,n:bytes(malformed[a-0x100000:a-0x100000+n]),[module])
    with pytest.raises(DebuggerError,match='exceeds'):exports.callback()


def source_session():
    session=Win16DebugSession.__new__(Win16DebugSession)
    session.source=ne_file();session.ne=load_ne(session.source).metadata['ne']
    session._segments={s['index']:s for s in session.ne['segments']}
    session.bindings={};session._binding_epoch=0;session.version={'id':7};session.run_id='owned-ne'
    session.metadata={'source_sha256':hashlib.sha256(session.source).hexdigest()}
    session._event=lambda *a:None
    return session


def test_segment_binding_masks_only_explicit_ne_fixups_and_rechecks_live_descriptor():
    session=source_session();segment=session._segments[1]
    original=session.source[segment['file_offset']:segment['file_offset']+segment['file_size']]
    live=bytearray(original)
    for fixup in session.ne['fixups']:
        if fixup['source_segment_index']==1:
            for source in fixup['sources']:
                live[source['offset']:source['offset']+fixup['source_width']]=bytes([0xa5])*fixup['source_width']
    descriptor=dict(selector=0x2ef,base=0xa30000,limit=segment['allocation_size']-1,present=True,default_big=False,type=0x1a,dpl=3,thread=12,module_revision=4)
    session.call=lambda method,params:dict(descriptor)
    session._read_runtime=lambda address,length:bytes(live[:length])
    binding=session._bind(1,0x2ef,reason='test observed callback')
    assert binding['unrelocated_bytes_verified']>=16
    assert session._resolve('ne:1:0x0000',3)[2]==0xa30000
    assert session.scene_memory_key('ne:1:0x0000',3)=='ne/owned-ne/7/10000/3/2ef/1/unqualified-task'
    assert session.project_address('0xa30000')=='ne:1:0x0000'
    assert session.project_address(0,selector=0x2ef)=='ne:1:0x0000'
    with pytest.raises(ValueError,match='no observed'):session._resolve('ne:2:0')
    with pytest.raises(ValueError,match='not DOS'):session._resolve('ne:1:0',cs=0x2ef)
    with pytest.raises(ValueError,match='exceeds'):session._resolve('ne:1:0xffff',2)
    descriptor['base']+=0x10000
    with pytest.raises(DebuggerError,match='Stale'):session._resolve('ne:1:0')
    with pytest.raises(DebuggerError,match='Stale'):session.project_address('0xa30000')


def test_binding_refuses_unexplained_code_changes_and_flat_or_32bit_selectors():
    session=source_session();segment=session._segments[1]
    original=session.source[segment['file_offset']:segment['file_offset']+segment['file_size']]
    descriptor=dict(selector=0x2ef,base=0x800000,limit=65535,present=True,default_big=False,type=0x1a,dpl=3,thread=12)
    session.call=lambda *a,**k:dict(descriptor)
    session._read_runtime=lambda address,length:bytes([original[0]^1])+original[1:]
    with pytest.raises(DebuggerError,match='differ outside'):session._bind(1,0x2ef,reason='untrusted')
    with pytest.raises(ValueError,match='LDT'):session._selector(0x23)
    descriptor['default_big']=True
    with pytest.raises(DebuggerError,match='16-bit'):session._selector(0x2ef)


def test_source_binding_refuses_task_or_loader_generation_reuse():
    session=source_session()
    code=dict(selector=0x2ef,base=0xa30000,limit=65535,present=True,default_big=False,type=27,dpl=3,thread=12,module_revision=4)
    psp=dict(code,selector=0x2d7,base=0x900000,limit=255,type=19)
    session.bindings[1]=dict(selector=0x2ef,descriptor=code)
    session.metadata['task_identity']=dict(epoch='task-one',psp_selector=0x2d7,psp_descriptor=psp,
        loader_module_base='0x7b3b0000',loader_module_generation=10,validated_module_revision=4)
    observed=dict(psp)
    session._selector=lambda selector:dict(observed if selector==0x2d7 else code)
    assert session._binding(1)['selector']==0x2ef
    observed['base']+=4096
    with pytest.raises(DebuggerError,match='Stale Win16 task'):session._binding(1)
    observed=dict(psp,module_revision=5)
    session.call=lambda method:{'module_revision':5,'modules':[dict(bits=32,base='0x7b3b0000',generation=11)]}
    with pytest.raises(DebuggerError,match='loader module generation'):session._binding(1)


def test_foreign_sixteen_bit_code_does_not_trigger_a_whole_selector_read():
    session=source_session()
    def unexpected(*args):pytest.fail('An unrelated descriptor must not provoke a speculative whole-segment read')
    session._read_runtime=unexpected
    session._bind_observed_code(0x10f,dict(limit=65535,base=0x7b000000))
    assert session.bindings=={}


def test_only_declared_export_prologs_receive_exact_loader_expectations():
    source=ne_file(code=bytes.fromhex('1e5890')+bytes([0x90])*26,fixups=[])
    session=source_session();session.source=source;session.ne=load_ne(source).metadata['ne']
    session._segments={s['index']:s for s in session.ne['segments']}
    session.ne['entries']=[dict(ordinal=1,flags=1,segment_index=1,offset=0)]
    session.ne['module_flags']|=2
    expected,receipts=session._source_expected(1)
    assert expected[:3]==b'\x90'*3 and receipts[0]['source_hex']=='1e5890'
    session.ne['entries'][0]['flags']=3;session._loader_ds_selector=0x3ef
    assert session._source_expected(1)[0][:3]==bytes.fromhex('b8ef03')
    session.ne['entries']=[]
    assert session._source_expected(1)==(bytes.fromhex('1e5890')+bytes([0x90])*26,[])


def test_ne_checkpoint_capability_refuses_unqualified_restore():
    session=Win16DebugSession.__new__(Win16DebugSession)
    for operation in (session.save_state,session.load_state):
        with pytest.raises(ValueError,match='selector restoration'):operation('arbitrary')


@pytest.mark.parametrize('changes',[None,{}, {'eax':{'expected':0,'value':1}}])
def test_ne_general_register_writes_refuse_without_paired_runtime_before_rpc(changes):
    session=Win16DebugSession.__new__(Win16DebugSession);session.closed=False
    assert session.register_edits_available is False
    def unexpected(*args,**kwargs):pytest.fail('Unavailable paired runtime must refuse before any RPC or state change')
    session.registers=session.call=session._event=session._windows_state_changed=unexpected
    with pytest.raises(ValueError,match='paired native/WOW integer runtime'):
        session.write_registers(changes)
    assert session.closed is False


def test_ne_checked_six_register_edit_validates_before_mutation_and_reads_back():
    session=Win16DebugSession.__new__(Win16DebugSession);session.register_edits_available=True
    before={'context_source':'native-ldt-low32','cpu_mode':'protected16','eip':'0xa568',
            'eflags':'0x202','cs':'0x2ef','ds':'0x2ff','ss':'0x2ff','es':'0x2ff',
            'fs':'0x23','gs':'0x23','project_address':'ne:2:0xa568',
            'general':{k:'0x10' for k in ('eax','ebx','ecx','edx','esi','edi','ebp','esp')}}
    after={**before,'general':{**before['general'],'eax':'0x11'}}
    reads=iter([before,after]);calls=[];events=[]
    session.registers=lambda:next(reads)
    session.call=lambda method,params:calls.append((method,params))
    session._windows_state_changed=lambda:events.append('changed')
    session._event=lambda name,result:events.append(name)
    session.close=lambda:events.append('closed')
    with pytest.raises(ValueError,match='only six checked'):
        session.write_registers({'esp':{'expected':16,'value':17}})
    with pytest.raises(ValueError,match='expected and value'):
        session.write_registers({'eax':{'value':17}})
    assert not calls and not events
    result=session.write_registers({'eax':{'expected':16,'value':17}})
    assert calls==[('setregs',{'values':{'eax':17}})]
    assert events==['changed','write-registers']
    assert result['before']==before and result['after']==after


def test_ne_register_edit_closes_on_control_readback_mismatch():
    session=Win16DebugSession.__new__(Win16DebugSession);session.register_edits_available=True
    before={'context_source':'native-ldt-low32','cpu_mode':'protected16','eip':'0xa568',
            'eflags':'0x202','cs':'0x2ef','ds':'0x2ff','ss':'0x2ff','es':'0x2ff',
            'fs':'0x23','gs':'0x23','project_address':'ne:2:0xa568',
            'general':{k:'0x10' for k in ('eax','ebx','ecx','edx','esi','edi','ebp','esp')}}
    after={**before,'eip':'0xa569','general':{**before['general'],'eax':'0x11'}}
    reads=iter([before,after]);events=[]
    session.registers=lambda:next(reads)
    session.call=lambda method,params:events.append(method)
    session.close=lambda:events.append('closed')
    session._windows_state_changed=lambda:pytest.fail('Changed context must not commit')
    with pytest.raises(DebuggerError,match='control or selector context'):
        session.write_registers({'eax':{'expected':16,'value':17}})
    assert events==['setregs','closed']


@pytest.mark.parametrize('context_source',['native-ldt-low32','wow64',None])
def test_win16_ldt_registers_require_native_api_provenance(context_source):
    session=source_session()
    native={'architecture':'x86-32','bits':32,'context_source':context_source,
            'cs':'0x2ef','eip':'0x4','eflags':'0x212','general':{'esp':'0x1045100'}}
    session.call=lambda method:dict(native)
    session._selector=lambda selector:{'base':0xa30000,'limit':0xffff,'present':True,'default_big':False}
    session._bind_observed_code=lambda *args:None
    session.project_address=lambda *args,**kwargs:'ne:1:0x0004'
    if context_source!='native-ldt-low32':
        with pytest.raises(DebuggerError,match='native-qualified context reader'):session.registers()
    else:
        result=session.registers()
        assert result['context_source']=='native-ldt-low32' and result['cpu_mode']=='protected16'
        assert result['linear_ip']=='0xa30004' and result['project_address']=='ne:1:0x0004'
        assert 'GetThreadContext low32 projection' in session.register_context_contract


def test_scalar_watch_translates_sixteen_bit_offset_through_live_ds_not_paragraph_math():
    session=source_session()
    descriptor=dict(selector='0x2f7',base='0xa40000',limit='0xffff',present=True,default_big=False)
    session.call=lambda method,params:dict(descriptor)
    registers=dict(cpu_mode='protected16',eip='0x10',cs='0x2ef',ds='0x2f7',ss='0x2f7',es='0x2f7',
        general=dict(eax='0',ebx='0x50002',esi='0x10003',edi='0',ebp='0',ecx='0',edx='0',esp='0'))
    facts=session._operand_ranges(bytes.fromhex('8b4004'),registers) # mov ax,[bx+si+4]
    assert facts['ranges']==[dict(address=0xa40009,length=2,selector='0x2f7',offset='0x9',read=True,write=False)]
    registers['general']['ebx']='0xffff'
    assert session._operand_ranges(bytes.fromhex('8b4004'),registers)['ranges'][0]['address']==0xa40006
    with pytest.raises(ValueError,match='non-repeated'):session._operand_ranges(bytes.fromhex('f3a4'),registers)


def test_watch_requires_actual_fault_range_and_reports_before_matching_access():
    session=source_session();session.watchpoints={'wp-0':dict(runtime_address=0xa40009,length=2,access='r')}
    session.registers=lambda:dict(cpu_mode='protected16',linear_ip='0xa30010',eip='0x10',selector_descriptor={'limit':65535})
    session._read_runtime=lambda *a:bytes.fromhex('8b4004')
    session._operand_ranges=lambda *a:dict(instruction='mov ax,[bx+si+4]',ranges=[dict(address=0xa40009,length=2,read=True,write=False)])
    state={'stop_reason':dict(kind='memory-access',access_address='0xa4000a',access_code=0,before_access=True)}
    assert session._watch_stop(state)
    assert state['stop_reason']['kind']=='watchpoint' and state['stop_reason']['breakpoint_ids']==['wp-0']
    closed=[];session.close=lambda:closed.append(True)
    with pytest.raises(ValueError,match='cannot be classified'):
        session._watch_stop({'stop_reason':dict(kind='memory-access',access_address='0xa40011',access_code=0)})
    assert closed==[True]


def test_ambiguous_guard_refusal_closes_session_before_a_later_continuation():
    session=Win16DebugSession.__new__(Win16DebugSession);session.closed=False
    def refuse(state):raise ValueError('Repeated operand stopped before access')
    session._classify_watch_stop=refuse
    session.close=lambda:setattr(session,'closed',True)
    with pytest.raises(ValueError,match='Repeated operand'):session._watch_stop({})
    with pytest.raises(DebuggerError,match='closed'):session.call('run',{'timeout_ms':1})


def test_shared_scene_slice_validates_controls_and_classifies_before_access_stops():
    session=Win16DebugSession.__new__(Win16DebugSession);validated=[];calls=[]
    session._validate_controls=lambda:validated.append(True)
    states=[{'stop_reason':{'kind':'memory-access','access_address':'0x1234'}},
            {'stop_reason':{'kind':'slice'}}]
    def call(method,params,**kwargs):
        calls.append(method);return states.pop(0)
    session.call=call;session._watch_stop=lambda state:False
    assert session._scene_slice(1000)['stop_reason']['kind']=='slice'
    assert calls==['slice','slice'] and len(validated)==2
    states.append({'stop_reason':{'kind':'memory-access'}})
    def matched(state):state['stop_reason']['kind']='watchpoint';return True
    session._watch_stop=matched
    assert session._scene_slice(1000)['stop_reason']['kind']=='watchpoint'


def test_scene_host_deadline_does_not_forge_a_native_budget_pause(monkeypatch):
    import fdisbull.win16_debugger as module
    session=Win16DebugSession.__new__(Win16DebugSession);calls=[]
    session._validate_controls=lambda:None
    def status(method):
        calls.append(method);return {'stop_reason':{'kind':'entry','address':'0x100000'}}
    session.call=status
    times=iter([0,2]);monkeypatch.setattr(module.time,'monotonic',lambda:next(times))
    result=session._scene_slice(1000,2000)
    assert calls==['status']
    assert result['stop_reason']['kind']=='timeout'
    assert result['stop_reason']['native_kind']=='entry'
    assert result['stop_reason']['native_budget_pause'] is False


def test_ne_public_contexts_include_only_the_owned_outer_machine():
    from types import SimpleNamespace
    session=Win16DebugSession.__new__(Win16DebugSession);session.run_id='owned-ne'
    session.project=SimpleNamespace(meta={'format':'NE'})
    bound=object();calls=[]
    machine=SimpleNamespace(capabilities={'architecture':'x86-64'},bind=lambda project,run:calls.append((project,run)) or bound)
    session.rpc=SimpleNamespace(machine=machine)
    assert session.contexts()['selected']=='process'
    assert session.context('process') is session
    assert session.context('machine') is bound and calls==[(session.project,'owned-ne')]
    with pytest.raises(ValueError,match='Unknown'):session.context('invented-task')


def test_ne_rpc_intersects_shared_script_budget_and_refuses_before_dispatch(monkeypatch):
    from types import SimpleNamespace
    import fdisbull.win16_debugger as module
    session=Win16DebugSession.__new__(Win16DebugSession);session.closed=False;session._rpc_deadline=2
    calls=[]
    session.rpc=SimpleNamespace(call=lambda method,params,timeout_ms:calls.append((method,params,timeout_ms)) or {})
    monkeypatch.setattr(module.time,'monotonic',lambda:1)
    session.call('selector',{'selector':0x2ef},timeout_ms=30000)
    assert calls==[('selector',{'selector':0x2ef},1000)]
    session._rpc_deadline=1
    with pytest.raises(TimeoutError,match='Shared debugger'):session.call('run',{'timeout_ms':1})
    assert len(calls)==1 and session.closed is False


def test_native_mutation_with_missing_readback_closes_before_future_execution():
    session=source_session();session.breakpoints={};closed=[];calls=[]
    session._resolve=lambda *args,**kwargs:(0x10000,{'selector':0x2ef},0xa30000)
    reads=iter([dict(hex='90',project_address='ne:1:0'),TimeoutError('shared readback deadline')])
    def memory(*args,**kwargs):
        result=next(reads)
        if isinstance(result,Exception):raise result
        return result
    session.memory=memory;session.call=lambda *a,**k:calls.append((a,k)) or {'written':1}
    session.close=lambda:closed.append(True)
    with pytest.raises(TimeoutError,match='readback deadline'):session.write_memory('ne:1:0','91',expected_hex='90')
    assert calls[0][0][0]=='write' and closed==[True]


def test_real_original_ne_entry_registers_memory_and_completed_instructions(tmp_path):
    names=('FDISBULL_NE_QEMU','FDISBULL_NE_KERNEL','FDISBULL_NE_INITRAMFS','FDISBULL_NE_FIXTURE')
    missing=[n for n in names if not os.environ.get(n)]
    if missing:
        if os.environ.get('FDISBULL_REQUIRE_NE')=='1':pytest.fail('Missing native NE inputs: '+', '.join(missing))
        pytest.skip('Set FDISBULL_NE_* for actual Wine16 selector acceptance')
    from fdisbull.project import Project
    qemu,kernel,runtime,fixture=[os.environ[n] for n in names];source=Path(fixture)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    with Project.create(tmp_path/'native.fdb',source,image='ne') as project:
        project.analyze(max_instructions=32)
        with project.debugger(qemu,source.parent,kernel=kernel,initramfs=runtime,files=[source.name],window=True) as session:
            assert session.metadata['original_entry_verified'] is True
            assert session.registers()['cpu_mode']=='protected16'
            assert session.registers()['project_address']==session.ne['logical_entry']['address']
            assert session.memory(session.ne['logical_entry']['address'],length=1)['selector'].startswith('0x')
            assert session.step(count=1,timeout_ms=20000)['completed'] is True
            spectator=session.dot_mode()
            assert spectator['view_only'] and not spectator['host_input_capture']
        assert session.rpc.process.poll() is not None
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
