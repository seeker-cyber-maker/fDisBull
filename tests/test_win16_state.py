"""Stopped Win16 checkpoint evidence must be requalified, without a guest VM."""
from copy import deepcopy
import hashlib
import gzip
import json
import threading
from contextlib import nullcontext
from types import SimpleNamespace
import pytest
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull import win16_state
from fdisbull.win16_state import checkpoint_observation, requalify


def session():
    source_sha = hashlib.sha256(b'a'*16).hexdigest()
    descriptor = dict(selector=0x2ef, base=0x10000, limit=31, present=True, default_big=False, type=27, dpl=3, thread=12, module_revision=4)
    task_desc = dict(descriptor, selector=0x2d7, base=0x20000, type=19)
    task = dict(epoch='one', thread=12, psp_selector=0x2d7, psp_descriptor=task_desc,
                loader_module_base='0x30000', loader_module_generation=3, validated_module_revision=4)
    binding = dict(segment_index=1, selector=0x2ef, base=0x10000, limit=31, descriptor=descriptor,
                   generation=1, source_sha256=source_sha, source_segment_sha256=source_sha, task_epoch='one')
    control = dict(pending=True, event=1, process=9, thread=12, target_bits=32, state_revision=7,
                   module_revision=4, continuation=0, stepping_thread=0, breakpoint_hit=-1, guard_pending=False)
    observed = {'status': dict(state='stopped', state_revision=7, stop_reason=dict(kind='breakpoint',thread=12)),
                'context-diagnostics': {'pending_event': control},
                'registers': dict(thread=12, context_source='native-ldt-low32', cs='0x2ef', ds='0x2d7',
                                  ss='0x2d7', es='0x0', fs='0x0', gs='0x0', eip='0x4', eflags='0x202',
                                  general={'eax':'0x1'}),
                'modules': {'module_revision':4,'modules':[dict(bits=32,base='0x30000',generation=3)]}}
    observed['control-inventory'] = {'format':'fdisbull-debug-controls-1', 'pending_event':deepcopy(control),
                                    'breakpoints':[], 'watchpoints':[], 'overlays':[], 'pages':[], 'threads':[]}
    s = SimpleNamespace(source=b'a'*16, bindings={1:binding}, _segments={1:{'file_offset':0,'file_size':16,'allocation_size':32}},
                        breakpoints={}, watchpoints={}, _edits={0x10002:42}, _binding_epoch=1,
                        metadata={'source_sha256':source_sha,'task_identity':task},
                        rpc=SimpleNamespace(capabilities={'context_diagnostics':True,'control_inventory':True}),
                        observed=observed, live={0x10000:b'\xcc'+b'x'*31},
                        descriptors={0x2ef:descriptor,0x2d7:task_desc})
    s.call=lambda name, params=None:deepcopy(s.observed[name])
    s._selector=lambda selector:deepcopy(s.descriptors[selector])
    s._read_runtime=lambda address,length:s.live[address][:length]
    return s


def test_requalifies_checkpoint_current_bytes_not_original_source():
    old=session(); saved=checkpoint_observation(old)
    replacement=session()
    requalify(replacement,saved)
    assert replacement.bindings[1]['source_segment_sha256']==hashlib.sha256(b'a'*16).hexdigest()
    assert replacement._edits=={0x10002:42}


@pytest.mark.parametrize('fault', ['pending', 'thread', 'selector', 'bytes', 'loader', 'registers', 'source'])
def test_unqualified_restoration_refuses_before_continuation(fault):
    saved=checkpoint_observation(session()); changed=session()
    if fault=='pending': changed.observed['context-diagnostics']['pending_event']['pending']=False
    elif fault=='thread': changed.observed['context-diagnostics']['pending_event']['thread']=99
    elif fault=='selector': changed.descriptors[0x2ef]['base']+=1
    elif fault=='bytes': changed.live[0x10000]=b'different bytes!'
    elif fault=='loader': changed.observed['modules']['modules'][0]['generation']=99
    elif fault=='registers': changed.observed['registers']['eip']='0x5'
    else: changed.source=b'b'*16
    with pytest.raises((ValueError, DebuggerError)): requalify(changed,saved)


def test_unknown_control_inventory_refuses_save_before_snapshot():
    s=session();s.rpc.capabilities['control_inventory']=False
    with pytest.raises(ValueError,match='control inventory'):checkpoint_observation(s)


def test_active_controls_require_exact_guest_inventory_and_survive_requalification():
    s=session()
    s.breakpoints={'bp-1':{'address':65536,'runtime_address':65536,'binding_generation':1}}
    s.observed['control-inventory']['breakpoints']=[{'id':'bp-1','address':'0x10000','original_hex':'90','armed':True}]
    saved=checkpoint_observation(s)
    replacement=session()
    replacement.observed['control-inventory']['breakpoints']=deepcopy(s.observed['control-inventory']['breakpoints'])
    requalify(replacement,saved)
    assert replacement.breakpoints==s.breakpoints
    replacement.observed['control-inventory']['breakpoints'][0]['armed']=False
    with pytest.raises(DebuggerError,match='differ'):requalify(replacement,saved)


def test_same_session_restore_requalifies_before_committing_metadata(tmp_path, monkeypatch):
    s=session(); saved=checkpoint_observation(s); calls=[]
    class RPC:
        def __init__(self, *paths, restore=None, memory_mib=4096):
            self.lock=threading.RLock();self.inputs={n:{'path':str(tmp_path/n),'sha256':'x'} for n in ('qemu','kernel','initramfs')}
            self.capabilities={'context_diagnostics':True,'control_inventory':True}
            self.process=SimpleNamespace(pid=500);self.closed=False
            calls.append(('created',restore,memory_mib))
        def close(self):self.closed=True;calls.append(('closed',))
    original=RPC();calls.clear();s.rpc=original;s.rpc_type=RPC
    s.project=SimpleNamespace(transaction=lambda _:nullcontext(),db=SimpleNamespace(execute=lambda *a:calls.append(('update',))))
    s.version={'id':7};s.run_id='r';s.mode_id=3;s._frame='old';s.backend_name='wine-ne-qemu'
    s.register_edits_available=True;s.register_context_contract='observed'
    s._windows_invalidate_input_leases=lambda:calls.append(('invalidated',))
    s._event=lambda *a:calls.append(('event',))
    metadata={'memory_mib':8192,'runtime_inputs':deepcopy(original.inputs)}
    doc={'metadata':metadata,'host':{'win16_context':saved},'machine_size':123}
    monkeypatch.setattr(win16_state,'get_state',lambda *args:({'sha256':'a'*64},doc,tmp_path/'state'))
    monkeypatch.setattr(win16_state,'_verify_inputs',lambda *args:None)
    result=win16_state.load_state(s,'artifact')
    assert original.closed and result['source_selector_requalified'] is True
    assert result['target_execution_during_requalification'] is False
    assert calls[0]==('closed',) and calls[1][0]=='created' and calls[1][2]==8192
    assert s.mode_id==4 and ('update',) in calls


def test_failed_requalification_closes_replacement_without_commit(tmp_path, monkeypatch):
    s=session(); saved=checkpoint_observation(s); s.observed['registers']['eip']='0x5'; calls=[]
    class RPC:
        def __init__(self,*args,**kwargs):
            self.lock=threading.RLock();self.inputs={n:{'path':str(tmp_path/n),'sha256':'x'} for n in ('qemu','kernel','initramfs')}
            self.capabilities={'context_diagnostics':True,'control_inventory':True}
        def close(self):calls.append('rpc-close')
    s.rpc=RPC();s.rpc_type=RPC;s.version={'id':7};s.project=SimpleNamespace();s.close=lambda:calls.append('session-close')
    doc={'metadata':{'runtime_inputs':deepcopy(s.rpc.inputs)},'host':{'win16_context':saved}}
    monkeypatch.setattr(win16_state,'get_state',lambda *args:({'sha256':'a'*64},doc,tmp_path/'state'))
    monkeypatch.setattr(win16_state,'_verify_inputs',lambda *args:None)
    with pytest.raises(DebuggerError,match='differ'):win16_state.load_state(s,'artifact')
    assert calls==['rpc-close','session-close']


def test_checkpoint_captures_current_bytes_and_hash_bound_sidecar(tmp_path, monkeypatch):
    s=session(); captured=[]
    class RPC:
        capabilities={'context_diagnostics':True,'control_inventory':True}
        lock=threading.RLock()
        def capture(self,path):
            with gzip.open(path,'wb') as stream:stream.write(b'owned machine data')
            return {'qmp_status':'completed'}
    s.rpc=RPC();s.project=SimpleNamespace(path=tmp_path/'project.fdb');s.close=lambda:captured.append('closed')
    s.metadata.update(version_sha256='b'*64)
    def artifact(name,kind,data,metadata):
        captured.append((name,kind,json.loads(data)));return {'artifact':'saved'}
    s._artifact=artifact
    monkeypatch.setattr(win16_state,'_verify_inputs',lambda *args:None)
    monkeypatch.setattr(win16_state.shutil,'disk_usage',lambda _:SimpleNamespace(free=10*1024**3))
    result=win16_state.save_state(s)
    document=captured[0][2];sidecar=tmp_path/'project.fdb.fdisbull-states'/(document['machine_sha256']+'.mig.gz')
    assert result['artifact']=='saved' and sidecar.is_file()
    assert hashlib.sha256(sidecar.read_bytes()).hexdigest()==document['machine_sha256']
    assert document['host']['win16_context']['segments']['1']['sha256']==hashlib.sha256(s.live[0x10000]).hexdigest()


def test_constructor_restore_never_bootstraps_or_starts_target(tmp_path, monkeypatch):
    from fdisbull.project import Project
    from fdisbull.win16_debugger import Win16DebugSession
    from fdisbull import wine_state
    from test_win16_debugger import ne_file
    game=tmp_path/'game';game.mkdir();(game/'fixture.exe').write_bytes(ne_file())
    paths=[]; inputs={}
    for name in ('qemu','kernel','initramfs'):
        path=tmp_path/name;path.write_bytes(name.encode());paths.append(path)
        inputs[name]={'path':str(path),'sha256':hashlib.sha256(name.encode()).hexdigest()}
    calls=[]
    class RPC:
        def __init__(self,*args,**kwargs):
            calls.append(('restore',kwargs.get('restore')));self.inputs=inputs;self.hello={};self.process=SimpleNamespace(pid=1)
            self.capabilities={'context_diagnostics':True,'control_inventory':True};self.lock=threading.RLock()
        def call(self,*args,**kwargs):raise AssertionError('constructor must not execute target or bootstrap')
        def close(self):pass
    with Project.create(tmp_path/'project.fdb',game/'fixture.exe',image='ne') as project:
        metadata={'backend':'wine-ne-qemu','runtime_profile':'wine11-ne-selector-1',
                  'target_pid':2,'carrier_image_base':'0x1000','memory_mib':8192,
                  'files':[{'path':'fixture.exe','sha256':project.meta['source_sha256']}],
                  'runtime_inputs':inputs}
        saved={'metadata':metadata,'host':{'win16_context':{'task':{}}}}
        monkeypatch.setattr(wine_state,'get_state',lambda *a:({},saved,tmp_path/'state.mig.gz'))
        monkeypatch.setattr(Win16DebugSession,'rpc_type',RPC)
        monkeypatch.setattr(win16_state,'_verify_inputs',lambda *a:None)
        monkeypatch.setattr(win16_state,'requalify',lambda *a:calls.append(('requalified',)))
        monkeypatch.setattr(Win16DebugSession,'_bootstrap_ne',lambda *a:pytest.fail('startup binding was invoked'))
        with project.debugger(paths[0],game,kernel=paths[1],initramfs=paths[2],state='saved') as restored:
            assert restored.metadata['restored_from']=='saved' and restored.metadata['memory_mib']==8192
        assert calls==[('restore',tmp_path/'state.mig.gz'),('requalified',)]


def test_constructor_rejects_changed_runtime_before_vm_creation(tmp_path, monkeypatch):
    from fdisbull.project import Project
    from fdisbull.win16_debugger import Win16DebugSession
    from fdisbull import wine_state
    from test_win16_debugger import ne_file
    game=tmp_path/'game';game.mkdir();(game/'fixture.exe').write_bytes(ne_file())
    paths=[]
    for name in ('qemu','kernel','initramfs'):
        path=tmp_path/name;path.write_bytes(name.encode());paths.append(path)
    with Project.create(tmp_path/'project.fdb',game/'fixture.exe',image='ne') as project:
        metadata={'backend':'wine-ne-qemu','runtime_profile':'wine11-ne-selector-1',
                  'files':[{'path':'fixture.exe','sha256':project.meta['source_sha256']}],
                  'runtime_inputs':{n:{'sha256':'0'*64} for n in ('qemu','kernel','initramfs')}}
        saved={'metadata':metadata,'host':{'win16_context':{}}}
        monkeypatch.setattr(wine_state,'get_state',lambda *a:({},saved,tmp_path/'state.mig.gz'))
        monkeypatch.setattr(Win16DebugSession,'rpc_type',lambda *a,**k:pytest.fail('VM creation on identity mismatch'))
        with pytest.raises(ValueError,match='backend identity mismatch'):
            project.debugger(paths[0],game,kernel=paths[1],initramfs=paths[2],state='saved')
