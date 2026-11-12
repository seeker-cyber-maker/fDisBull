"""Authored QEMU CHIP-8 60 Hz sample history witnesses."""
from contextlib import contextmanager
from io import BytesIO
import hashlib
import os
import pytest
from PIL import Image
from fdisbull.project import Project


def _inputs():
    binary=os.environ.get('FDISBULL_CHIP8_FRAMES_QEMU')
    tool=os.environ.get('FDISBULL_CHIP8_FRAMES_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_FRAMES')=='1':pytest.fail('CHIP-8 sample runtime and qemu-img required')
        pytest.skip('Set FDISBULL_CHIP8_FRAMES_QEMU and FDISBULL_CHIP8_FRAMES_QEMU_IMG')
    return binary,tool


@contextmanager
def _machine(tmp_path,words):
    binary,tool=_inputs();rom=tmp_path/'sample.ch8';source=bytes.fromhex(words);rom.write_bytes(source)
    with Project.create(tmp_path/'project.fdb',rom,arch='chip8') as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            yield project,d
    assert rom.read_bytes()==source


def _regs(d):return {k:int(v,16) for k,v in d.registers()['registers'].items()}


def _step(d,pc):
    result=d.step(timeout_ms=5000);assert result['outcome']=='step',result
    assert _regs(d)['pc']==pc


def _png(project,receipt):
    row=project.db.execute('select data,sha256 from debug_artifacts where id=?',(receipt['artifact'],)).fetchone()
    raw=bytes(row['data']);assert hashlib.sha256(raw).hexdigest()==row['sha256']==receipt['sha256']
    with Image.open(BytesIO(raw)) as image:
        assert image.size==(64,32)
        return image.convert('RGBA').tobytes()


def _layer(d,name,address,before,after,kind):
    return d.layer_patch(name,address,expected_hex=before,data_hex=after,kind=kind,activate=False)['layer']


def test_sample_timeline_exact_tick_branch_cached_image_pin_and_cold_restore(tmp_path):
    binary,tool=_inputs();db=tmp_path/'project.fdb'
    with _machine(tmp_path,'6000 6100 a300 d011 1208') as (project,d):
        d.write_memory(0x300,'80',expected_hex='00')
        for pc in (0x202,0x204,0x206,0x208):_step(d,pc)
        rgba=d.frame_rgba()['rgba'];assert rgba[:4]==bytes.fromhex('ffffffff')
        start=d.timeline_start(max_frames=8,timeout_ms=60000)
        assert start['format']=='fdisbull-qemu-chip8-frames-v1' and start['unit']=='native 60 Hz sample'
        assert start['completed_guest_frame'] is None
        root=start['point'];before=d.chip8_environment()
        first=d.timeline_advance(frames=1,timeout_ms=60000);assert first['outcome']=='completed' and first['completed_frames']==1
        node1=first['point'];after=d.chip8_environment()
        assert after['virtual-ticks']==before['virtual-ticks']+1
        frame=next(row['frame'] for row in first['nodes'] if row['id']==node1)
        assert frame['kind']=='native-60hz-sample' and frame['virtual_ticks']==after['virtual-ticks']
        assert frame['sampled_ns']<=after['virtual-now-ns'] and frame['completed_guest_frame'] is None
        state=d.registers(),d.chip8_environment(),d.memory(0x300,length=1)
        cached=d.timeline_image(point=node1);assert _png(project,cached)==rgba
        assert (d.registers(),d.chip8_environment(),d.memory(0x300,length=1))==state
        pinned=d.timeline_pin();assert pinned['kind']=='state'
        second=d.timeline_advance(frames=1);node2=second['point']
        old=d.vm.process;d.timeline_rewind(frames=1);assert old.poll() is not None
        assert d.chip8_environment()['virtual-ticks']==after['virtual-ticks']
        branch=d.timeline_advance(frames=1);new=branch['point']
        status=d.timeline_status();nodes={row['id']:row for row in status['nodes']}
        assert {root,node1,node2,new}<=set(nodes) and nodes[node2]['parent']==nodes[new]['parent']==node1
        assert _png(project,d.timeline_image(point=node2))==rgba
        timeline=status['timeline']
    with Project(db) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            d.timeline_start(timeline=timeline)
            old=d.vm.process;d.timeline_rewind(timeline=timeline,point=node1,frames=0);assert old.poll() is not None
            assert d.chip8_environment()['virtual-ticks']==after['virtual-ticks']
            assert d.frame_rgba()['rgba']==rgba and _png(project,d.timeline_image(timeline=timeline,point=node1))==rgba


def test_root_cached_image_remains_immutable_after_unrecorded_cls(tmp_path):
    with _machine(tmp_path,'6000 6100 a300 d011 00e0 120a') as (project,d):
        d.write_memory(0x300,'80',expected_hex='00')
        for pc in (0x202,0x204,0x206,0x208):_step(d,pc)
        root=d.timeline_start(max_frames=4);image=d.timeline_image(point=root['point']);old=_png(project,image)
        _step(d,0x20a);assert d.frame_rgba()['rgba']!=old
        assert _png(project,d.timeline_image(timeline=root['timeline'],point=root['point']))==old
        restored=d.timeline_rewind(timeline=root['timeline'],point=root['point'],frames=0)
        assert restored['point']==root['point'] and d.frame_rgba()['rgba']==old


@pytest.mark.parametrize('word,outcome',[('f00a','key_wait'),('ffff','exception')])
def test_nonordinary_native_stop_never_creates_a_sample_node(tmp_path,word,outcome):
    with _machine(tmp_path,word) as (_,d):
        before=d.timeline_start(max_frames=3)
        result=d.timeline_advance(frames=1,timeout_ms=60000)
        assert result['completed_frames']==0 and result['stop']['outcome']==outcome
        status=d.timeline_status();assert not status['valid'] and status['head']==before['head']
        assert len(status['nodes'])==len(before['nodes']) and _regs(d)['pc']==0x200


def test_user_breakpoint_precedes_unrecorded_sample_and_is_not_consumed(tmp_path):
    with _machine(tmp_path,'6001 1202') as (_,d):
        point=d.breakpoint(0x202)
        result=d.advance_frames(frames=1,timeout_ms=60000)
        assert result['completed_frames']==0 and result['stop']['outcome']=='breakpoint'
        assert result['stop']['session']['stop_reason']['breakpoint_ids']==[point['breakpoint_id']]
        assert _regs(d)['pc']==0x202 and _regs(d)['v0']==1


def test_hook_layer_action_cancels_sample_fence_before_dispatch(tmp_path):
    with _machine(tmp_path,'6001 7001 1202') as (_,d):
        layer=_layer(d,'hook-fetch',0x203,'01','02','execute')
        hook=d.hook(0x202,actions=[{'op':'layers','layers':[layer]}],once=False,max_hits=2)
        root=d.timeline_start(max_frames=3)
        result=d.timeline_advance(frames=1,timeout_ms=60000)
        assert result['completed_frames']==0 and result['stop']['outcome']=='hook'
        assert result['stop']['hook_hits'][0]['hook']==hook['hook']
        assert d.layers()['active']==[layer] and d.code(0x202,length=2,view='execute')['hex']=='7002'
        assert not d.timeline_status()['valid'] and len(d.timeline_status()['nodes'])==len(root['nodes'])
        assert _regs(d)['pc']==0x202 and _regs(d)['v0']==1


def test_pending_hook_root_checkpoint_restores_layers_keys_and_rng(tmp_path):
    with _machine(tmp_path,'c0ff 1200') as (_,d):
        ram=_layer(d,'saved-ram',0x300,'00','7a','ram')
        fetch=_layer(d,'masked-rng',0x201,'ff','0f','execute');d.layers([ram,fetch])
        d.chip8_seed_rng(123);d.chip8_keypad([0,15]);d.chip8_tick(2)
        hook=d.hook(0x200,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
        assert d.run(timeout_ms=5000,stop_on_hook=True)['hook_hits'][0]['hit']==1
        root=d.timeline_start(max_frames=4);before=d.registers(),d.chip8_environment(),d.hooks()
        with pytest.raises(ValueError,match='pending.*hook'):d.timeline_advance(frames=1)
        assert (d.registers(),d.chip8_environment(),d.hooks())==before
        _step(d,0x202);expected=d.chip8_environment();assert _regs(d)['v0']==8 and expected['rng-draws']==1
        old=d.vm.process;d.timeline_rewind(timeline=root['timeline'],point=root['point'],frames=0);assert old.poll() is not None
        assert d.layers()['active']==[ram,fetch] and d.memory(0x300,length=1)['hex']=='7a'
        assert d.hooks()['pending']==hook['hook'] and d.hooks()['hooks'][0]['hits']==1
        assert d.chip8_environment()['key-mask']==0x8001
        _step(d,0x202);actual=d.chip8_environment()
        assert _regs(d)['v0']==8 and actual['rng-state']==expected['rng-state'] and actual['rng-draws']==1
        assert d.hooks()['hooks'][0]['hits']==1


def test_guest_backing_conflict_interrupts_before_sample(tmp_path):
    with _machine(tmp_path,'a209 6009 f055 1208 6001 1208') as (_,d):
        fetch=_layer(d,'guarded-fetch',0x209,'01','02','execute');d.layers([fetch])
        root=d.timeline_start(max_frames=3)
        result=d.timeline_advance(frames=1,timeout_ms=60000)
        assert result['completed_frames']==0 and result['stop']['outcome']=='layer_conflict'
        assert _regs(d)['pc']==0x206 and d.memory(0x209,length=1)['hex']=='09'
        assert d.chip8_environment()['rng-draws']==0 and len(d.timeline_status()['nodes'])==len(root['nodes'])


@pytest.mark.parametrize('target',['checkpoint-data','checkpoint-metadata','image-data'])
def test_corrupt_stored_sample_refuses_before_owner_swap(tmp_path,target):
    import json
    with _machine(tmp_path,'1200') as (project,d):
        root=d.timeline_start(max_frames=3);node=root['nodes'][0]
        checkpoint=node['checkpoint']['artifact'];image=node['frame']['image']['artifact']
        if target=='checkpoint-metadata':
            row=project.db.execute('select metadata from debug_artifacts where id=?',(checkpoint,)).fetchone()
            metadata=json.loads(row['metadata']);metadata['host_files_restored']=True
            with project.transaction(True):
                project.db.execute('update debug_artifacts set metadata=? where id=?',(json.dumps(metadata),checkpoint))
        else:
            ident=checkpoint if target=='checkpoint-data' else image
            with project.transaction(True):
                project.db.execute('update debug_artifacts set data=? where id=?',(b'corrupt',ident))
        owner=d.vm.process;before=d.registers();env=d.chip8_environment()
        with pytest.raises(ValueError):d.timeline_rewind(timeline=root['timeline'],point=root['point'],frames=0)
        assert d.vm.process is owner and owner.poll() is None and not d.closed
        assert d.registers()==before and d.chip8_environment()==env


def test_sample_budget_and_contended_lock_refuse_without_effect(tmp_path):
    import threading,time
    with _machine(tmp_path,'1200') as (_,d):
        start=d.timeline_start(max_frames=1);before=d.timeline_status();regs=d.registers();env=d.chip8_environment()
        with pytest.raises(ValueError,match='budget'):d.timeline_advance(frames=1)
        assert d.timeline_status()==before and d.registers()==regs and d.chip8_environment()==env
        acquired=threading.Event();release=threading.Event();owner=d.vm.process
        def hold():
            with d.vm.lock:acquired.set();release.wait(3)
        thread=threading.Thread(target=hold);thread.start();assert acquired.wait(1)
        started=time.monotonic()
        try:
            with pytest.raises(TimeoutError):d.timeline_advance(frames=1,timeout_ms=30)
            assert time.monotonic()-started<0.5
        finally:
            release.set();thread.join(timeout=2)
        assert not thread.is_alive() and owner.poll() is None and d.vm.process is owner and not d.closed
        assert d.timeline_status()==before and d.registers()==regs and d.chip8_environment()==env
        assert start['point']==before['point']


def test_sample_timeline_json_and_saved_script_routes(tmp_path):
    from fdisbull.cli import respond
    from fdisbull.debugger import DebugWorkspace
    with _machine(tmp_path,'1200') as (project,d):
        workspace=DebugWorkspace();workspace.sessions[d.run_id]=d
        def call(method,**params):
            reply=respond({'method':method,'params':{'project':str(project.path),'run':d.run_id,**params}},debugger=workspace)
            assert reply['ok'],reply
            return reply['result']
        try:
            root=call('debug-timeline-start',max_frames=5)
            program={'format':'fdisbull-script-1','backend':'qemu-chip8','steps':[
                {'op':'timeline-advance','frames':1},
                {'op':'timeline-rewind','timeline':root['timeline'],'point':root['point'],'frames':0}]}
            saved=project.debug_save_script('sample-route',program)
            report=d.script(script_id=saved['script_id'],timeout_ms=60000)
            assert report['ok'] and report['completed_steps']==2
            assert call('debug-timeline-status')['point']==root['point']
        finally:workspace.sessions.clear()


def test_v4_instruction_history_is_retained_without_sample_timeline(tmp_path):
    binary=os.environ.get('FDISBULL_CHIP8_LAYERS_QEMU')
    tool=os.environ.get('FDISBULL_CHIP8_LAYERS_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_FRAMES')=='1':pytest.fail('Retained v4 runtime and qemu-img required')
        pytest.skip('Set FDISBULL_CHIP8_LAYERS_QEMU and FDISBULL_CHIP8_LAYERS_QEMU_IMG')
    rom=tmp_path/'legacy.ch8';rom.write_bytes(bytes.fromhex('6001 1200'))
    with Project.create(tmp_path/'legacy.fdb',rom,arch='chip8') as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            started=d.rewind_start(max_steps=3);before=d.rewind_status();owner=d.vm.process
            with pytest.raises(ValueError,match='v5|timeline|sample'):d.timeline_start(max_frames=2)
            assert d.rewind_status()==before and d.vm.process is owner and not d.closed
            assert d.rewind_record(count=1)['recorded_count']==1 and _regs(d)['v0']==1
            assert started['valid']


def _frame_arm(d,token='a'*32):
    env=d.chip8_environment()
    return {'token':token,'expected-state-generation':env['state-generation'],
            'expected-virtual-ticks':env['virtual-ticks'],
            'expected-deadline-ns':env['next-deadline-ns']}


def test_raw_frame_arm_preconditions_are_atomic(tmp_path):
    from fdisbull.dosbox_rpc import DebuggerError
    with _machine(tmp_path,'1200') as (_,d):
        args=_frame_arm(d);control=d.vm.qmp.call('query-chip8-frame')
        baseline=(d.registers(),d.memory(0,length=4096),d.chip8_environment(),control)
        for field in ('expected-state-generation','expected-virtual-ticks','expected-deadline-ns'):
            bad=dict(args);bad[field]+=1
            with pytest.raises(DebuggerError):d.vm.qmp.call('x-chip8-arm-frame',bad)
            assert (d.registers(),d.memory(0,length=4096),d.chip8_environment(),d.vm.qmp.call('query-chip8-frame'))==baseline
        bad=dict(args,token='z'*32)
        with pytest.raises(DebuggerError):d.vm.qmp.call('x-chip8-arm-frame',bad)
        assert (d.registers(),d.memory(0,length=4096),d.chip8_environment(),d.vm.qmp.call('query-chip8-frame'))==baseline
        assert not d.closed and d.vm.process.poll() is None


def test_active_frame_fence_blocks_public_checkpoints_until_cancel(tmp_path):
    from fdisbull.dosbox_rpc import DebuggerError
    with _machine(tmp_path,'1200') as (_,d):
        saved=d.save_state(timeout_ms=30000);args=_frame_arm(d)
        before=(d.registers(),d.memory(0,length=4096),d.chip8_environment());owner=d.vm.process
        armed=d.vm.qmp.call('x-chip8-arm-frame',args)
        assert armed['state']=='armed' and armed['token']==args['token']
        with pytest.raises(ValueError,match='frame|fence'):d.save_state(timeout_ms=30000)
        with pytest.raises(ValueError,match='frame|fence'):d.load_state(saved['artifact'],timeout_ms=30000)
        assert d.vm.process is owner and owner.poll() is None and not d.closed
        assert (d.registers(),d.memory(0,length=4096),d.chip8_environment())==before
        assert d.vm.qmp.call('query-chip8-frame',{'token':args['token']})==armed
        cancel={'token':args['token'],'expected-control-generation':armed['control-generation']}
        with pytest.raises(DebuggerError):
            d.vm.qmp.call('x-chip8-cancel-frame',dict(cancel,**{'expected-control-generation':armed['control-generation']+1}))
        assert d.vm.qmp.call('query-chip8-frame',{'token':args['token']})==armed
        idle=d.vm.qmp.call('x-chip8-cancel-frame',cancel)
        assert idle['state']=='idle' and idle['control-generation']==armed['control-generation']+1
        assert d.vm.qmp.call('x-chip8-cancel-frame',cancel)==idle
        assert d.vm.qmp.call('query-chip8-frame')==idle
        fresh=d.save_state(timeout_ms=30000);old=d.vm.process
        d.load_state(fresh['artifact'],timeout_ms=30000);assert old.poll() is not None
        assert d.vm.qmp.call('query-chip8-frame')['state']=='idle'
        assert (d.registers(),d.memory(0,length=4096),d.chip8_environment())==before
