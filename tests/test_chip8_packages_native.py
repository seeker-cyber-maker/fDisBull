"""G1 declarations remain separate from preserved native v6 debugger state."""
import hashlib
import json
import os

import pytest

from fdisbull.chip8_intake import create_intake
from fdisbull.project import Project


def test_native_closure_keeps_trials_undo_layers_keys_and_lossless_history(tmp_path):
    binary=os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU')
    tool=os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_FRAME_KEYS')=='1':
            pytest.fail('CHIP-8 v6 runtime and checkpoint tool required')
        pytest.skip('Set CHIP-8 v6 runtime and checkpoint tool')
    raw=bytes.fromhex('c00f a350 f055 1200');rom=tmp_path/'original.ch8';rom.write_bytes(raw)
    manifest={'source_repo':'https://example.invalid/authored-g1',
        'source_commit':'1'*40,'source_metadata_blob_sha':'2'*40,'source_license':'homegrown test fixture',
        'programs':[dict(key='authored',title='Authored RNG loop',author='fDisBull tests',platform='chip8',
            size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
            git_blob_sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest())]}
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest))
    pin=hashlib.sha256(path.read_bytes()).hexdigest();database=tmp_path/'closure.fdb'
    with create_intake(database,rom,manifest_path=path,manifest_sha256=pin,member='authored') as project:
        intake=project.chip8_intake_info();project.analyze(max_instructions=32)
        base=project.chip8_closure_resolve(environment='env:chip8-qemu-v6:1')
        assert base['runtime'] is None and base['analysis'] is None
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            fields=('profile','cpu_subset','env_model','machine','memory','qemu_sha256','qemu_version','checkpoint_tool_sha256')
            runtime={k:d.identity[k] for k in fields}
            closure=project.chip8_closure_resolve(environment='env:chip8-qemu-v6:1',runtime=runtime,include_analysis=True,
                requirements={'architecture':{'quirks':{'shift_source':'vy','logic_vf':'clear','load_store_i':'increment'}},
                              'environment':{'clock':{'timer_hz':60},'rng':{'model':'fdisbull-lcg32-high8-v1'}}},
                expected_intake_sha256=intake['intake_sha256'])
            assert closure['runtime']['verification']=='caller-declared-unverified'
            assert closure['runtime']['declaration']['qemu_sha256']==d.identity['qemu_sha256']
            assert closure['analysis']['tables']['instructions']['count']>0
            ram=d.layer_patch('ram',0x350,expected_hex='00',data_hex='7a',kind='ram',activate=False)['layer']
            code=d.layer_patch('rng-mask',0x201,expected_hex='0f',data_hex='07',kind='execute',activate=False)['layer']
            d.layers([ram,code]);d.chip8_seed_rng(123);d.frame_inputs([{'key':'f','pressed':True}])
            hook=d.hook(0x230,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
            frames=d.timeline_start(storage_mode='delta',keyframe_interval=4,max_frames=4)
            child=d.timeline_advance(frames=1);point=child['point'];timeline=child['timeline']
            assert next(n for n in child['nodes'] if n['id']==point)['checkpoint']['storage']['kind']=='delta'
            d.timeline_rewind(timeline=timeline,point=frames['point'],frames=0)
            before=d.registers(),d.chip8_environment(),d.memory(0,length=4096)['hex']
            keys=d.keyboard_state()['keyboard']['native']
            route={'format':'fdisbull-script-1','backend':'qemu-chip8','steps':[
                {'op':'step'},{'op':'step'},{'op':'step'},{'op':'registers'},
                {'op':'memory','address':0x350,'length':1},{'op':'screenshot'}]}
            saved=d.save_experiment('g1-trial.json',script=route,observations=[{'address':0x350,'length':1}])
            compared=d.compare_experiment(saved['artifact'],layers=[ram])
            assert compared['ok'] and compared['baseline_restored'] and compared['comparison']['observed_difference'],compared
            d.cpu_delta_start([{'address':0x350,'length':1}],registers=['v0','i','pc'],max_steps=4)
            assert d.cpu_delta_record(count=3)['recorded_count']==3
            assert d.cpu_delta_rewind(count=3)['partial_restored'] and d.cpu_delta_status()['frozen']
            assert project.chip8_closure_info(closure['closure'])==closure
            d.restore_experiment(saved['artifact'])
            assert not d.cpu_delta_status()['frozen']
            assert (d.registers(),d.chip8_environment(),d.memory(0,length=4096)['hex'])==before
            assert d.layers()['active']==[ram,code] and d.hooks()['hooks'][0]['hook']==hook['hook']
            after=d.keyboard_state()['keyboard']['native']
            assert after['held']==['f'] and after['accepted-edges']==keys['accepted-edges']
            assert point in {n['id'] for n in d.timeline_status(timeline=timeline)['nodes']}
            assert d.timeline_image(timeline=timeline,point=point)['stored_frame']
            assert project.chip8_closure_info(closure['closure'])==closure
    with Project(database) as project:
        assert project.chip8_intake_info()==intake
        assert project.chip8_closure_info(base['closure'])==base
        assert project.chip8_closure_info(closure['closure'])==closure
    assert rom.read_bytes()==raw
