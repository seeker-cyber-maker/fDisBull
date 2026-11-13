"""Real CHIP-8 sample checkpoints: exact opaque delta reconstruction."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
from fdisbull.project import Project


def _inputs():
    binary=os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU');tool=os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_FRAME_KEYS')=='1':pytest.fail('CHIP-8 v6 runtime and qemu-img required')
        pytest.skip('Set CHIP-8 v6 runtime and qemu-img')
    return binary,tool


@contextmanager
def _machine(tmp_path,words='1200'):
    binary,tool=_inputs();rom=tmp_path/'delta.ch8';original=bytes.fromhex(words);rom.write_bytes(original)
    with Project.create(tmp_path/'delta.fdb',rom,arch='chip8') as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            yield project,d
    assert rom.read_bytes()==original


def _row(project,identifier):
    row=project.db.execute('select * from debug_artifacts where id=?',(identifier,)).fetchone()
    assert row is not None and hashlib.sha256(bytes(row['data'])).hexdigest()==row['sha256']
    return row


def _state_count(project):return project.db.execute("select count(*) from debug_artifacts where kind='state'").fetchone()[0]


def test_real_delta_oracle_keyframes_fork_and_cold_restore(tmp_path,monkeypatch):
    import fdisbull.qemu_chip8 as module
    binary,tool=_inputs();db=tmp_path/'delta.fdb';captures=[];original=module.Chip8DebugSession._capture_state
    def capture(self,*args,**kwargs):
        result=original(self,*args,**kwargs)
        assert hashlib.sha256(result['data']).hexdigest()==result['sha256'] and len(result['data'])==result['size']
        captures.append(deepcopy(result));return result
    monkeypatch.setattr(module.Chip8DebugSession,'_capture_state',capture)
    with _machine(tmp_path) as (project,d):
        baseline=_state_count(project);root=d.timeline_start(storage_mode='delta',keyframe_interval=2,max_frames=8)
        assert root['format']=='fdisbull-qemu-chip8-frames-v3' and root['storage_mode']=='delta'
        rootid=root['point'];oracles={rootid:captures[-1]};points=[rootid]
        for i in range(3):
            count=_state_count(project);prior=len(captures)
            out=d.timeline_advance(frames=1);assert out['completed_frames']==1 and len(captures)==prior+1
            point=out['point'];points.append(point);oracles[point]=captures[-1]
            cp=next(n['checkpoint'] for n in out['nodes'] if n['id']==point)
            assert cp['sha256']==oracles[point]['sha256'] and cp['size']==oracles[point]['size']
            stored=_row(project,cp['artifact']);storage=cp['storage']
            assert len(stored['data'])==storage['payload_size'] and stored['sha256']==storage['payload_sha256']
            assert stored['kind']==('state' if storage['kind']=='full' else 'chip8-frame-state-delta')
            if storage['kind']=='delta':
                wrapper=json.loads(stored['metadata'])
                assert wrapper['format']=='fdisbull-chip8-frame-state-1'
                assert wrapper['full_metadata']==oracles[point]['metadata']
            assert _state_count(project)==count+(storage['kind']=='full')
            before_pin=len(captures);pin=d.timeline_pin('point-%d.qcow2'%i);row=_row(project,pin['artifact'])
            assert len(captures)==before_pin
            assert bytes(row['data'])==oracles[point]['data']
            assert json.loads(row['metadata'])==oracles[point]['metadata']
            frame=next(n['frame'] for n in out['nodes'] if n['id']==point)
            image=_row(project,frame['image']['artifact']);assert len(image['data'])==frame['image']['size']
            from io import BytesIO
            from PIL import Image
            with Image.open(BytesIO(bytes(image['data']))) as png:
                assert png.size==(64,32)
                assert hashlib.sha256(png.convert('RGBA').tobytes()).hexdigest()==frame['image']['pixel_sha256']
        status=d.timeline_status();nodes={n['id']:n for n in status['nodes']}
        assert nodes[rootid]['checkpoint']['storage']['kind']=='full'
        assert any(nodes[p]['checkpoint']['storage']['kind']=='delta' for p in points[1:])
        assert all(nodes[p]['checkpoint']['storage']['depth']<2 for p in points)
        old=points[-1];d.timeline_rewind(timeline=status['timeline'],point=rootid,frames=0)
        branch=d.timeline_advance(frames=1);assert branch['point']!=old
        branch_nodes={n['id']:n for n in branch['nodes']}
        assert branch_nodes[branch['point']]['parent']==rootid and old in branch_nodes
        target=points[1];timeline=branch['timeline'];expected=oracles[target]
    with Project(db) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            d.timeline_start(timeline=timeline);d.timeline_rewind(timeline=timeline,point=target,frames=0)
            pin=d.timeline_pin('cold.qcow2');row=_row(project,pin['artifact'])
            assert bytes(row['data'])==expected['data'] and json.loads(row['metadata'])==expected['metadata']


@pytest.mark.parametrize('corruption',['payload','metadata','base-payload','image'])
def test_corrupt_delta_refuses_before_advance_or_owner_swap(tmp_path,monkeypatch,corruption):
    import fdisbull.qemu_chip8 as module
    with _machine(tmp_path) as (project,d):
        root=d.timeline_start(storage_mode='delta',keyframe_interval=4,max_frames=4)
        out=d.timeline_advance(frames=1);node=next(n for n in out['nodes'] if n['id']==out['point'])
        cp=node['checkpoint'];assert cp['storage']['kind']=='delta'
        root_node=next(n for n in root['nodes'] if n['id']==root['point'])
        target=(root_node['checkpoint']['artifact'] if corruption=='base-payload' else
                node['frame']['image']['artifact'] if corruption=='image' else cp['artifact'])
        with project.transaction(True):
            project.db.execute('update debug_artifacts set '+('metadata' if corruption=='metadata' else 'data')+'=? where id=?',
                               ('{}' if corruption=='metadata' else b'bad',target))
        owner=d.vm.process;before=d.registers(),d.chip8_environment(),d.keyboard_state()
        events=project.db.execute('select count(*) from debug_events').fetchone()[0]
        artifacts=project.db.execute('select count(*) from debug_artifacts').fetchone()[0]
        execution=[];created=[]
        monkeypatch.setattr(d,'_execute',lambda *a,**k:execution.append((a,k)))
        def forbidden_owner(*a,**k):created.append(True);raise AssertionError('new VM before validation')
        monkeypatch.setattr(module,'_Owner',forbidden_owner)
        with pytest.raises(ValueError):d.timeline_advance(frames=1)
        with pytest.raises(ValueError):d.timeline_rewind(timeline=out['timeline'],point=out['point'],frames=0)
        assert d.vm.process is owner and owner.poll() is None and not d.closed
        assert (d.registers(),d.chip8_environment(),d.keyboard_state())==before
        assert not execution and not created
        assert project.db.execute('select count(*) from debug_events').fetchone()[0]==events
        assert project.db.execute('select count(*) from debug_artifacts').fetchone()[0]==artifacts


def test_delta_checkpoint_cold_pending_hook_keys_layers_and_rng(tmp_path):
    binary,tool=_inputs();db=tmp_path/'delta.fdb'
    with _machine(tmp_path,'c0ff 1200') as (_,d):
        ram=d.layer_patch('ram',0x300,expected_hex='00',data_hex='7a',kind='ram',activate=False)['layer']
        code=d.layer_patch('fetch',0x201,expected_hex='ff',data_hex='0f',kind='execute',activate=False)['layer']
        d.layers([ram,code]);d.chip8_seed_rng(123);d.frame_inputs([{'key':'0','pressed':True}])
        hook=d.hook(0x200,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
        assert d.run(stop_on_hook=True)['outcome']=='hook'
        root=d.timeline_start(storage_mode='delta',max_frames=4);timeline=root['timeline'];point=root['point']
        assert d.step()['outcome']=='step';future=d.chip8_environment()['rng-state']
    with Project(db) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            d.timeline_start(timeline=timeline);d.timeline_rewind(timeline=timeline,point=point,frames=0)
            assert d.keyboard_state()['keyboard']['frame_keys']==['0'] and d.layers()['active']==[ram,code]
            assert d.hooks()['pending']==hook['hook'] and d.hooks()['hooks'][0]['hits']==1
            assert d.step()['outcome']=='step'
            assert int(d.registers()['registers']['v0'],16)==8 and d.chip8_environment()['rng-state']==future
            assert d.hooks()['hooks'][0]['hits']==1


def test_delta_budget_refusal_precedes_input_or_execution(tmp_path):
    with _machine(tmp_path) as (_,d):
        root=d.timeline_start(storage_mode='delta',max_frames=1)
        before=d.registers(),d.chip8_environment(),d.keyboard_state(),d.timeline_status()
        with pytest.raises(ValueError,match='budget|capture'):
            d.timeline_advance(frames=1,inputs=[{'frame':0,'edges':[{'key':'0','pressed':True}]}])
        assert (d.registers(),d.chip8_environment(),d.keyboard_state(),d.timeline_status())==before
        assert d.timeline_status()['point']==root['point'] and not d.closed


def test_delta_saved_script_options_dispatch_and_restore(tmp_path):
    with _machine(tmp_path) as (project,d):
        program={'format':'fdisbull-script-1','backend':'qemu-chip8','steps':[
            {'op':'timeline-start','storage_mode':'delta','keyframe_interval':2,'max_frames':4,'as':'root'},
            {'op':'timeline-advance','frames':1,'inputs':[{'frame':0,'edges':[{'key':'a','pressed':True}]}]},
            {'op':'timeline-rewind','timeline':'$root.timeline','point':'$root.point','frames':0}]}
        stored=project.debug_save_script('delta-route',program)
        result=d.script(script_id=stored['script_id'],timeout_ms=60000)
        assert result['ok'] and result['completed_steps']==3
        assert d.keyboard_state()['keyboard']['frame_keys']==[]


def _cold_delta(control):
    binary,tool=_inputs()
    with Project(control['db']) as project:
        with project.debugger(binary,control['directory'],backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            d.timeline_start(timeline=control['timeline']);d.timeline_rewind(timeline=control['timeline'],point=control['point'],frames=0)
            assert d.registers()==control['registers'] and d.memory(0,length=4096)==control['ram']
            assert d.chip8_environment()==control['environment']
            assert d.keyboard_state()['keyboard']['frame_keys']==['f'] and d.layers()['active']==control['layers']
            assert d.hooks()['hooks'][0]['hook']==control['hook'] and d.hooks()['hooks'][0]['hits']==0
            pin=d.timeline_pin('cold-child.qcow2');row=_row(project,pin['artifact'])
            assert bytes(row['data'])==Path(control['oracle']).read_bytes()
            assert json.loads(row['metadata'])==control['metadata']
            image=d.timeline_image(point=control['point']);assert bytes(_row(project,image['artifact'])['data'])==Path(control['png']).read_bytes()
            assert d.step()['outcome']=='step' and d.step()['outcome']=='step'
            assert d.registers()==control['future_registers']
            env=d.chip8_environment();assert env['rng-state']==control['future_rng_state'] and env['rng-draws']==control['future_rng_draws']
    return {'passed':True}


def test_actual_delta_child_cold_restore_preserves_owned_keys_layers_hook_rng(tmp_path):
    binary,tool=_inputs();db=tmp_path/'delta.fdb'
    with _machine(tmp_path,'c0ff 1200') as (project,d):
        ram=d.layer_patch('ram-child',0x300,expected_hex='00',data_hex='7a',kind='ram',activate=False)['layer']
        code=d.layer_patch('fetch-child',0x201,expected_hex='ff',data_hex='0f',kind='execute',activate=False)['layer']
        d.layers([ram,code]);d.chip8_seed_rng(123);d.frame_inputs([{'key':'f','pressed':True}])
        hook=d.hook(0x300,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
        d.timeline_start(storage_mode='delta',keyframe_interval=4,max_frames=4)
        child=d.timeline_advance(frames=1);assert child['completed_frames']==1
        node=next(n for n in child['nodes'] if n['id']==child['point'])
        assert node['checkpoint']['storage']['kind']=='delta'
        pin=d.timeline_pin('oracle-child.qcow2');row=_row(project,pin['artifact'])
        oracle=tmp_path/'oracle.qcow2';oracle.write_bytes(bytes(row['data']))
        png=tmp_path/'oracle.png';png.write_bytes(bytes(_row(project,node['frame']['image']['artifact'])['data']))
        control=dict(db=str(db),directory=str(tmp_path),timeline=child['timeline'],point=child['point'],
            registers=d.registers(),ram=d.memory(0,length=4096),environment=d.chip8_environment(),
            layers=[ram,code],hook=hook['hook'],oracle=str(oracle),png=str(png),metadata=json.loads(row['metadata']))
        assert d.keyboard_state()['keyboard']['frame_keys']==['f'] and d.hooks()['hooks'][0]['hits']==0
        assert d.step()['outcome']=='step' and d.step()['outcome']=='step'
        env=d.chip8_environment();control.update(future_registers=d.registers(),future_rng_state=env['rng-state'],future_rng_draws=env['rng-draws'])
    control_path=tmp_path/'cold-control.json';control_path.write_text(json.dumps(control))
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(control_path)],capture_output=True,text=True,timeout=180,env=os.environ.copy())
    assert result.returncode==0,result.stderr[-8000:]
    assert json.loads(result.stdout)['passed'] is True


if __name__=='__main__':
    print(json.dumps(_cold_delta(json.loads(Path(sys.argv[1]).read_text()))))
