"""Native CHIP-8 owned frame-key witnesses; no keyboard-device emulation."""
from contextlib import contextmanager
import os
import pytest
from fdisbull.project import Project
from fdisbull.dosbox_rpc import DebuggerError


def _inputs():
    binary=os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU')
    tool=os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_FRAME_KEYS')=='1':
            pytest.fail('CHIP-8 frame-key runtime and qemu-img required')
        pytest.skip('Set CHIP-8 frame-key runtime and qemu-img')
    return binary,tool


@contextmanager
def _machine(tmp_path,words='1200'):
    binary,tool=_inputs();rom=tmp_path/'keys.ch8';original=bytes.fromhex(words);rom.write_bytes(original)
    with Project.create(tmp_path/'keys.fdb',rom,arch='chip8') as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            yield project,d
    assert rom.read_bytes()==original


def _edge(key,pressed):return {'key':key,'pressed':pressed}
def _native(d):return d.vm.qmp.call('query-chip8-frame-keys')
def _regs(d):return {k:int(v,16) for k,v in d.registers()['registers'].items()}


def test_native_owned_edges_cas_and_manual_keypad_exclusion(tmp_path):
    with _machine(tmp_path) as (_,d):
        before=d.registers(),d.chip8_environment(),_native(d)
        old=before[2]
        with pytest.raises(DebuggerError):
            d.vm.qmp.call('x-chip8-apply-frame-key-edges',{'token':'a'*32,'expected-generation':old['generation']+1,
                'expected-state-generation':old['state-generation'],'edges':[_edge('0',True)]})
        assert (d.registers(),d.chip8_environment(),_native(d))==before
        receipt=d.frame_inputs([_edge('0',True),_edge('f',True)])
        assert receipt['held']==['0','f']
        owned=_native(d);assert owned['active'] and owned['valid'] and owned['held-mask']==0x8001
        assert owned['accepted-edges']==old['accepted-edges']+2 and not owned['repeat-supported']
        with pytest.raises(ValueError):d.chip8_keypad([1])
        with pytest.raises(ValueError):d.frame_inputs([_edge('0',True)])
        assert _native(d)==owned
        d.frame_inputs([_edge('0',False),_edge('f',False)])
        d.chip8_keypad([1]);assert d.chip8_environment()['key-mask']==2
        with pytest.raises(ValueError):d.frame_inputs([_edge('2',True)])
        d.chip8_keypad([]);d.frame_inputs([_edge('2',True)])
        assert _native(d)['held-mask']==4


def test_native_schedule_branch_dirty_and_zero_rewind(tmp_path):
    with _machine(tmp_path) as (_,d):
        root=d.timeline_start(max_frames=10)
        one=d.timeline_advance(frames=3,inputs=[{'frame':0,'edges':[_edge('0',True)]},
                                                  {'frame':2,'edges':[_edge('0',False)]}])
        assert one['outcome']=='completed' and one['completed_frames']==3
        nodes={row['id']:row for row in one['nodes']};old=one['point']
        assert nodes[one['frames'][0]['point']]['frame']['keys']==['0']
        assert nodes[old]['frame']['keys']==[]
        d.timeline_rewind(frames=3);assert d.timeline_status()['point']==root['point']
        branch=d.timeline_advance(frames=1,inputs=[{'frame':0,'edges':[_edge('f',True)]}])
        assert branch['point']!=old and old in {n['id'] for n in branch['nodes']}
        d.frame_inputs([_edge('f',False)])
        with pytest.raises(ValueError,match='dirty'):d.timeline_pin()
        d.timeline_rewind(frames=0)
        assert d.keyboard_state()['keyboard']['frame_keys']==['f']


def test_native_invalid_future_schedule_has_no_prefix_effect(tmp_path):
    with _machine(tmp_path) as (_,d):
        d.timeline_start(max_frames=5)
        before=d.timeline_status(),d.registers(),d.chip8_environment(),_native(d)
        with pytest.raises(ValueError):
            d.timeline_advance(frames=2,inputs=[{'frame':0,'edges':[_edge('0',True)]},
                {'frame':1,'edges':[_edge('0',True)]}])
        assert (d.timeline_status(),d.registers(),d.chip8_environment(),_native(d))==before


def test_native_wait_zero_key_requires_explicit_resume(tmp_path):
    with _machine(tmp_path,'f00a 1202') as (_,d):
        assert d.step()['outcome']=='key_wait' and _regs(d)['pc']==0x200
        d.frame_inputs([_edge('0',True)])
        assert _regs(d)['pc']==0x200 and d.chip8_environment()['key-wait']
        assert d.step()['outcome']=='step' and _regs(d)['v0']==0 and _regs(d)['pc']==0x202
        d.frame_inputs([_edge('0',False)])


def test_native_cold_restore_owned_keys_pending_hook_layers_rng(tmp_path):
    binary,tool=_inputs();db=tmp_path/'keys.fdb'
    with _machine(tmp_path,'c0ff 1200') as (_,d):
        ram=d.layer_patch('ram',0x300,expected_hex='00',data_hex='7a',kind='ram',activate=False)['layer']
        fetch=d.layer_patch('fetch',0x201,expected_hex='ff',data_hex='0f',kind='execute',activate=False)['layer']
        d.layers([ram,fetch]);d.chip8_seed_rng(123)
        hook=d.hook(0x200,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
        assert d.run(stop_on_hook=True)['outcome']=='hook'
        d.frame_inputs([_edge('0',True),_edge('f',True)])
        root=d.timeline_start(max_frames=4);saved=d.save_state();prior=_native(d)
        assert d.step()['outcome']=='step' and _regs(d)['v0']==8
        future=d.chip8_environment()['rng-state']
    with Project(db) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            d.load_state(saved['artifact']);now=_native(d)
            assert now['active'] and now['held-mask']==0x8001 and now['accepted-edges']==prior['accepted-edges']
            assert now['token'] and (now['epoch'],now['token'])!=(prior['epoch'],prior['token'])
            assert d.layers()['active']==[ram,fetch] and d.memory(0x300,length=1)['hex']=='7a'
            assert d.hooks()['pending']==hook['hook'] and d.hooks()['hooks'][0]['hits']==1
            assert d.step()['outcome']=='step' and _regs(d)['v0']==8
            assert d.chip8_environment()['rng-state']==future and d.hooks()['hooks'][0]['hits']==1


def test_native_hook_interrupt_retains_accepted_edges_without_sample(tmp_path):
    with _machine(tmp_path,'6001 7001 1202') as (_,d):
        hook=d.hook(0x202,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
        root=d.timeline_start(max_frames=4)
        result=d.timeline_advance(frames=1,inputs=[{'frame':0,'edges':[_edge('0',True)]}])
        assert result['completed_frames']==0 and result['stop']['outcome']=='hook'
        assert result['stop']['hook_hits'][0]['hook']==hook['hook']
        assert d.keyboard_state()['keyboard']['frame_keys']==['0']
        assert len(d.timeline_status()['nodes'])==len(root['nodes']) and d.hooks()['pending']==hook['hook']
        accepted=_native(d)['accepted-edges']
        assert d.step()['outcome']=='step' and _native(d)['accepted-edges']==accepted


def test_retained_v5_rejects_owned_keys_without_affecting_frame_history(tmp_path):
    binary=os.environ.get('FDISBULL_CHIP8_FRAMES_QEMU');tool=os.environ.get('FDISBULL_CHIP8_FRAMES_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_FRAME_KEYS')=='1':pytest.fail('Retained v5 runtime required')
        pytest.skip('Set retained CHIP-8 frames runtime and qemu-img')
    rom=tmp_path/'v5.ch8';rom.write_bytes(bytes.fromhex('1200'))
    with Project.create(tmp_path/'v5.fdb',rom,arch='chip8') as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            root=d.timeline_start(max_frames=3);before=d.timeline_status(),d.registers(),d.chip8_environment()
            with pytest.raises(ValueError):d.frame_inputs([_edge('0',True)])
            assert (d.timeline_status(),d.registers(),d.chip8_environment())==before
            assert d.timeline_advance(frames=1)['completed_frames']==1 and root['valid']


def test_native_bad_wire_batches_and_foreign_owner_are_atomic(tmp_path):
    with _machine(tmp_path) as (_,d):
        d.frame_inputs([_edge('0',True)])
        info=_native(d);token=info['token']
        args={'token':token,'expected-generation':info['generation'],
              'expected-state-generation':info['state-generation'],'edges':[_edge('1',True)]}
        baseline=(d.registers(),d.memory(0,length=4096),d.chip8_environment(),info,d.vm.qmp.call('query-chip8-frame'))
        bad=[dict(args,token='z'*32),dict(args,token='b'*32),
             dict(args,**{'expected-generation':info['generation']+1}),
             dict(args,**{'expected-state-generation':info['state-generation']+1}),
             dict(args,edges=[_edge('g',True)]),dict(args,edges=[_edge('1',True),_edge('1',False)]),
             dict(args,edges=[_edge('1',1)])]
        for attempt in bad:
            with pytest.raises(DebuggerError):d.vm.qmp.call('x-chip8-apply-frame-key-edges',attempt)
            assert (d.registers(),d.memory(0,length=4096),d.chip8_environment(),_native(d),
                    d.vm.qmp.call('query-chip8-frame'))==baseline
        assert not d.closed and d.vm.process.poll() is None


def test_native_active_fence_refuses_key_edges_and_checkpoint_without_effect(tmp_path):
    with _machine(tmp_path) as (_,d):
        saved=d.save_state();env=d.chip8_environment();keys=_native(d)
        args={'token':'a'*32,'expected-state-generation':env['state-generation'],
              'expected-virtual-ticks':env['virtual-ticks'],'expected-deadline-ns':env['next-deadline-ns']}
        armed=d.vm.qmp.call('x-chip8-arm-frame',args);owner=d.vm.process
        with pytest.raises((ValueError,DebuggerError)):d.frame_inputs([_edge('0',True)])
        with pytest.raises(ValueError):d.save_state()
        with pytest.raises(ValueError):d.load_state(saved['artifact'])
        assert d.vm.process is owner and owner.poll() is None and not d.closed
        assert _native(d)==keys and d.chip8_environment()==env
        assert d.vm.qmp.call('query-chip8-frame',{'token':args['token']})==armed
        d.vm.qmp.call('x-chip8-cancel-frame',{'token':args['token'],'expected-control-generation':armed['control-generation']})


def test_native_scheduled_zero_key_resumes_wait_only_on_frame_advance(tmp_path):
    with _machine(tmp_path,'f00a 1202') as (_,d):
        assert d.step()['outcome']=='key_wait' and _regs(d)['pc']==0x200
        root=d.timeline_start(max_frames=4)
        before=d.timeline_status(),d.registers(),d.chip8_environment(),_native(d)
        with pytest.raises(ValueError):d.timeline_advance(frames=1)
        assert (d.timeline_status(),d.registers(),d.chip8_environment(),_native(d))==before
        advance=d.timeline_advance(frames=1,inputs=[{'frame':0,'edges':[_edge('0',True)]}])
        assert advance['completed_frames']==1 and _regs(d)['v0']==0 and _regs(d)['pc']==0x202
        assert _native(d)['held-mask']==1 and root['valid']


@pytest.mark.parametrize('field,value',[('held-mask',0x8000),('generation',-1),('active','true')])
def test_bad_key_sidecar_refused_before_new_owner(tmp_path,monkeypatch,field,value):
    import json
    import fdisbull.qemu_chip8 as module
    with _machine(tmp_path) as (project,d):
        d.frame_inputs([_edge('0',True)]);saved=d.save_state();owner=d.vm.process
        row=project.db.execute('select metadata from debug_artifacts where id=?',(saved['artifact'],)).fetchone()
        metadata=json.loads(row['metadata']);metadata['key_state'][field]=value
        with project.transaction(True):
            project.db.execute('update debug_artifacts set metadata=? where id=?',(json.dumps(metadata),saved['artifact']))
        before=d.registers(),d.chip8_environment(),_native(d);created=[]
        def reject_new_owner(*args,**kwargs):created.append(True);raise AssertionError('new owner must not start')
        monkeypatch.setattr(module,'_Owner',reject_new_owner)
        with pytest.raises(ValueError):d.load_state(saved['artifact'])
        assert not created and d.vm.process is owner and owner.poll() is None and not d.closed
        assert (d.registers(),d.chip8_environment(),_native(d))==before


def test_native_json_and_saved_script_edges_dispatch_once(tmp_path):
    from fdisbull.cli import respond
    from fdisbull.debugger import DebugWorkspace
    with _machine(tmp_path) as (project,d):
        ws=DebugWorkspace();ws.sessions[d.run_id]=d
        try:
            reply=respond({'method':'debug-frame-inputs','params':{'project':str(project.path),'run':d.run_id,
                'edges':[_edge('0',True)]}},debugger=ws)
            assert reply['ok'] and reply['result']['held']==['0'],reply
            count=_native(d)['accepted-edges'];d.timeline_start(max_frames=4)
            program={'format':'fdisbull-script-1','backend':'qemu-chip8','steps':[
                {'op':'timeline-advance','frames':1,'inputs':[{'frame':0,'edges':[_edge('0',False)]}]}]}
            stored=project.debug_save_script('chip8-frame-keys',program)
            report=d.script(script_id=stored['script_id'],timeout_ms=60000)
            assert report['ok'] and report['completed_steps']==1
            assert _native(d)['accepted-edges']==count+1 and _native(d)['held-mask']==0
        finally:ws.sessions.clear()


@pytest.mark.parametrize('scenario',['new','untouched','reacquired','restored'])
def test_native_failed_script_key_cleanup_ownership(tmp_path,scenario):
    with _machine(tmp_path) as (_,d):
        if scenario!='new':d.frame_inputs([_edge('0',True)])
        root=d.timeline_start(max_frames=4)
        if scenario=='new':steps=[{'op':'frame-inputs','edges':[_edge('0',True)]}]
        elif scenario=='untouched':steps=[]
        elif scenario=='reacquired':steps=[{'op':'frame-inputs','edges':[_edge('0',False)]},
                                           {'op':'frame-inputs','edges':[_edge('0',True)]}]
        else:steps=[{'op':'timeline-rewind','timeline':root['timeline'],'point':root['point'],'frames':0}]
        steps.append({'op':'assert','value':1,'equals':2})
        report=d.script(script={'format':'fdisbull-script-1','backend':'qemu-chip8','steps':steps})
        assert not report['ok']
        if scenario=='untouched':assert not d.closed and d.keyboard_state()['keyboard']['frame_keys']==['0']
        else:assert d.closed and report['input_cleanup']['closed']
