"""Native paired CHIP-8 trials over authored programs and complete anchors."""
from contextlib import contextmanager
from pathlib import Path
import os
import pytest
from fdisbull.project import Project


def _inputs():
    binary=os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU');tool=os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_FRAME_KEYS')=='1':pytest.fail('CHIP-8 v6 runtime and qemu-img required')
        pytest.skip('Set CHIP-8 v6 runtime and qemu-img')
    return binary,tool


@contextmanager
def _machine(tmp_path,words='6001 a300 f055 1206'):
    binary,tool=_inputs();rom=tmp_path/'trial.ch8';original=bytes.fromhex(words);rom.write_bytes(original)
    with Project.create(tmp_path/'trial.fdb',rom,arch='chip8') as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            yield project,d
    assert rom.read_bytes()==original


def _script(*steps):return {'format':'fdisbull-script-1','backend':'qemu-chip8','steps':list(steps)}
def _route():return _script({'op':'step'},{'op':'step'},{'op':'step'},
    {'op':'registers'},{'op':'memory','address':0x300,'length':1},{'op':'screenshot'})
def _obs():return [{'address':0x300,'length':1}]


def test_native_equal_and_fetch_candidate_full_restore_and_export(tmp_path):
    binary,tool=_inputs();db=tmp_path/'trial.fdb'
    with _machine(tmp_path) as (project,d):
        patch=d.layer_patch('candidate',0x201,expected_hex='01',data_hex='02',kind='execute',activate=False)['layer']
        layer_sha=project.debug_layer_info(patch)['sha256']
        start=d.save_experiment('trial.json',script=_route(),observations=_obs())
        assert start['format']=='fdisbull-chip8-experiment-1'
        same=d.compare_experiment(start['artifact'],layers=[])
        assert same['ok'] and same['baseline_restored'] and same['comparison']['complete'],same
        assert same['comparison']['observed_difference'] is False
        result=d.compare_experiment(start['artifact'],layers=[patch])
        assert result['ok'] and result['baseline_restored'] and result['comparison']['complete'],result
        assert result['comparison']['observed_difference'] is True
        assert result['baseline']['memory'][0]['hex']=='01' and result['layer']['memory'][0]['hex']=='02'
        assert result['baseline']['registers']['v0']==1 and result['layer']['registers']['v0']==2
        assert project.debug_layer_info(patch)['sha256']==layer_sha
        image=result['baseline']['screenshots'][0]['artifact'];comparison=result['artifact'];experiment=start['artifact']
        assert int(d.registers()['linear_pc'],16)==0x200 and d.memory(0x300,length=1)['hex']=='00'
    with Project(db) as project:
        assert project.debug_experiment_info(experiment)
        project.debug_export(image,tmp_path/'actual.png');project.debug_export(comparison,tmp_path/'comparison.json')
        assert (tmp_path/'actual.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            result=d.compare_experiment(experiment,layers=[patch])
            assert result['ok'] and result['baseline_restored'] and result['comparison']['observed_difference'] is True


def test_native_failed_baseline_skips_candidate_but_restores_anchor(tmp_path):
    with _machine(tmp_path) as (_,d):
        patch=d.layer_patch('candidate',0x201,expected_hex='01',data_hex='02',kind='execute',activate=False)['layer']
        start=d.save_experiment('failure.json',script=_script({'op':'step'},{'op':'assert','value':1,'equals':2}),observations=_obs())
        before=d.registers(),d.memory(0x300,length=1),d.chip8_environment()
        result=d.compare_experiment(start['artifact'],layers=[patch])
        assert not result['ok'] and result['baseline_restored'] and result['layer'] is None
        assert result['comparison'] is None and result['error']['type']=='ScriptFailure'
        assert (d.registers(),d.memory(0x300,length=1),d.chip8_environment())==before


def test_native_anchor_restores_keys_layers_hook_and_rng(tmp_path):
    with _machine(tmp_path,'c0ff 1200') as (_,d):
        ram=d.layer_patch('ram',0x350,expected_hex='00',data_hex='7a',kind='ram',activate=False)['layer']
        code=d.layer_patch('fetch',0x201,expected_hex='ff',data_hex='0f',kind='execute',activate=False)['layer']
        d.layers([ram,code]);d.frame_inputs([{'key':'f','pressed':True}]);d.chip8_seed_rng(123)
        hook=d.hook(0x230,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
        before=d.registers(),d.chip8_environment();keys=d.keyboard_state()['keyboard']['native']
        saved=d.save_experiment('owned.json',script=_script({'op':'step'},{'op':'registers'}),observations=_obs())
        out=d.compare_experiment(saved['artifact'],layers=[ram,code])
        assert out['ok'] and out['baseline_restored'] and out['comparison']['observed_difference'] is False,out
        assert (d.registers(),d.chip8_environment())==before and d.layers()['active']==[ram,code]
        assert d.hooks()['hooks'][0]['hook']==hook['hook'] and d.hooks()['hooks'][0]['hits']==0
        after=d.keyboard_state()['keyboard']['native']
        assert after['held']==['f'] and after['accepted-edges']==keys['accepted-edges']
        assert d.step()['outcome']=='step' and int(d.registers()['registers']['v0'],16)==8
        assert d.chip8_environment()['rng-draws']==1


def test_native_invalid_candidate_and_observation_refuse_without_owner_change(tmp_path):
    with _machine(tmp_path) as (project,d):
        original=d.registers(),d.chip8_environment(),d.memory(0x300,length=1);owner=d.vm.process
        with pytest.raises(ValueError):d.save_experiment('invalid.json',script=_route(),observations=[{'address':4095,'length':2}])
        with pytest.raises(ValueError):d.save_experiment('invalid.json',script=_script({'op':'write-memory','address':0x300,'data_hex':'01','expected_hex':'00'}))
        saved=d.save_experiment('valid.json',script=_route(),observations=_obs())
        bad=d.layer_patch('bad',0x201,expected_hex='ff',data_hex='02',kind='execute',activate=False)['layer']
        with pytest.raises(ValueError):d.compare_experiment(saved['artifact'],layers=[bad])
        assert d.vm.process is owner and owner.poll() is None and not d.closed
        assert (d.registers(),d.chip8_environment(),d.memory(0x300,length=1))==original


def test_native_experiment_restore_thaws_cpu_undo_and_retains_frame_dag(tmp_path):
    with _machine(tmp_path) as (_,d):
        timeline=d.timeline_start(storage_mode='delta',max_frames=4);point=timeline['point']
        experiment=d.save_experiment('anchor.json',script=_route(),observations=_obs())
        d.cpu_delta_start([{'address':0x300,'length':1}],registers=['v0','pc'],max_steps=4)
        assert d.cpu_delta_record(count=3)['recorded_count']==3
        assert d.cpu_delta_rewind(count=3)['partial_restored'] and d.cpu_delta_status()['frozen']
        with pytest.raises(ValueError,match='frozen|partial'):d.compare_experiment(experiment['artifact'],layers=[])
        with pytest.raises(ValueError,match='frozen|partial'):d.save_experiment('bad.json',script=_route())
        d.restore_experiment(experiment['artifact']);assert not d.cpu_delta_status()['frozen']
        assert point in {n['id'] for n in d.timeline_status(timeline=timeline['timeline'])['nodes']}
        assert d.timeline_image(timeline=timeline['timeline'],point=point)['stored_frame']


def test_native_control_reference_deletes_hook_only_within_each_arm(tmp_path):
    with _machine(tmp_path) as (_,d):
        hook=d.hook(0x200,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
        assert d.run(stop_on_hook=True)['outcome']=='hook'
        original=d.hooks();assert original['pending']==hook['hook'] and original['hooks'][0]['hits']==1
        route=_script({'op':'delete-hook','hook':'$controls.hooks.'+hook['hook']+'.hook'},
                      {'op':'step'},{'op':'registers'})
        saved=d.save_experiment('hook.json',script=route,observations=_obs())
        result=d.compare_experiment(saved['artifact'],layers=[])
        assert result['ok'] and result['baseline_restored'] and result['comparison']['complete']
        assert result['comparison']['observed_difference'] is False
        now=d.hooks();assert now['pending']==hook['hook'] and now['hooks'][0]['hits']==1


@pytest.mark.parametrize('kind',['document','anchor'])
def test_native_corrupt_trial_evidence_refuses_before_owner_swap(tmp_path,monkeypatch,kind):
    import fdisbull.qemu_chip8 as module
    with _machine(tmp_path) as (project,d):
        saved=d.save_experiment('corrupt.json',script=_route(),observations=_obs())
        target=saved['artifact'] if kind=='document' else saved['checkpoint']['artifact']
        with project.transaction(True):project.db.execute('update debug_artifacts set data=? where id=?',(b'bad',target))
        before=d.registers(),d.chip8_environment(),d.memory(0x300,length=1);owner=d.vm.process;allocated=[]
        def forbidden(*args,**kwargs):allocated.append(True);raise AssertionError('corrupt evidence must not allocate')
        monkeypatch.setattr(module,'_Owner',forbidden)
        with pytest.raises(ValueError):d.compare_experiment(saved['artifact'],layers=[])
        assert not allocated and d.vm.process is owner and owner.poll() is None and not d.closed
        assert (d.registers(),d.chip8_environment(),d.memory(0x300,length=1))==before


def test_native_comparison_preflight_preserves_prior_state_on_transaction_and_bad_script(tmp_path):
    with _machine(tmp_path) as (project,d):
        before=d.registers(),d.chip8_environment(),d.memory(0x300,length=1);owner=d.vm.process
        count=project.db.execute('select count(*) from debug_artifacts').fetchone()[0]
        bad=_script({'op':'step'},{'op':'trace','count':1})
        with pytest.raises(ValueError):d.save_experiment('bad-script.json',script=bad)
        with project.transaction(True):
            with pytest.raises(ValueError):d.save_experiment('bad-transaction.json',script=_route())
        assert project.db.execute('select count(*) from debug_artifacts').fetchone()[0]==count
        assert d.vm.process is owner and owner.poll() is None and not d.closed
        assert (d.registers(),d.chip8_environment(),d.memory(0x300,length=1))==before


def test_native_once_hook_trial_dispatches_once_and_restores_control(tmp_path):
    with _machine(tmp_path) as (project,d):
        hook=d.hook(0x200,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':1}}}],once=True)
        before=d.registers(),d.hooks(),d.chip8_environment();owner=d.vm.process
        artifacts=project.db.execute('select count(*) from debug_artifacts').fetchone()[0]
        unsafe=_script({'op':'run','stop_on_hook':False,'expect':'breakpoint'})
        with pytest.raises(ValueError):d.save_experiment('unsafe.json',script=unsafe,observations=_obs())
        assert d.vm.process is owner and owner.poll() is None and not d.closed
        assert (d.registers(),d.hooks(),d.chip8_environment())==before
        assert project.db.execute('select count(*) from debug_artifacts').fetchone()[0]==artifacts
        route=_script({'op':'run','stop_on_hook':True,'expect':'hook'},
                      {'op':'registers'},{'op':'memory','address':0x300,'length':1})
        saved=d.save_experiment('once-hook.json',script=route,observations=_obs())
        result=d.compare_experiment(saved['artifact'],layers=[])
        assert result['ok'] and result['baseline_restored'] and result['comparison']['complete'],result
        assert result['comparison']['observed_difference'] is False
        for arm in ('baseline','layer'):
            stops=[item for item in result[arm]['observations'] if item['op']=='run']
            assert len(stops)==1 and stops[0]['value']['outcome']=='hook'
            hits=stops[0]['value']['hook_hits']
            assert len(hits)==1 and hits[0]['hook']==hook['hook'] and hits[0]['hit']==1
            assert len(hits[0]['actions'])==1 and hits[0]['actions'][0]['op']=='registers'
            assert hits[0]['actions'][0]['result']['i']==1
        after=d.hooks();assert after['pending'] is None and len(after['hooks'])==1
        assert after['hooks'][0]['hook']==hook['hook'] and after['hooks'][0]['hits']==0
        assert d.registers()==before[0] and d.chip8_environment()==before[2]


def test_native_draw_screenshots_capture_distinct_glyph_pixels(tmp_path):
    import io
    from PIL import Image
    with _machine(tmp_path,'6000 6100 a20a d015 1208 f090 9090 f000') as (project,d):
        candidate=d.layer_patch('shift-glyph',0x201,expected_hex='00',data_hex='08',kind='execute',activate=False)['layer']
        route=_script({'op':'step'},{'op':'step'},{'op':'step'},{'op':'step'},{'op':'screenshot'})
        before=d.frame_rgba()['rgba'];assert before==bytes.fromhex('000000ff')*(64*32)
        saved=d.save_experiment('glyph.json',script=route)
        result=d.compare_experiment(saved['artifact'],layers=[candidate])
        assert result['ok'] and result['baseline_restored'] and result['comparison']['complete'],result
        assert result['comparison']['observed_difference'] is True
        assert result['comparison']['screenshots'][0]['different'] is True
        expected_rows=('1111','1001','1001','1001','1111')
        for arm,offset in (('baseline',0),('layer',8)):
            artifact=result[arm]['screenshots'][0]['artifact']
            row=project.db.execute('select data from debug_artifacts where id=?',(artifact,)).fetchone()
            with Image.open(io.BytesIO(bytes(row['data']))) as image:
                assert image.size==(64,32);pixels=image.convert('RGBA')
                for y in range(32):
                    for x in range(64):
                        lit=y<5 and offset<=x<offset+4 and expected_rows[y][x-offset]=='1'
                        assert pixels.getpixel((x,y))==((255,255,255,255) if lit else (0,0,0,255))
        assert d.frame_rgba()['rgba']==before
