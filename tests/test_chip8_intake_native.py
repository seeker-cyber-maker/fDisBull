"""A pinned G0 intake remains usable by the retained v6 debugger machinery."""
import hashlib
import json
import os

import pytest

from fdisbull.chip8_intake import create_intake
from fdisbull.project import Project


def test_intake_v6_trials_frozen_undo_and_lossless_history_recovery(tmp_path):
    binary=os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU')
    tool=os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_FRAME_KEYS')=='1':
            pytest.fail('CHIP-8 v6 runtime and checkpoint tool required')
        pytest.skip('Set CHIP-8 v6 runtime and checkpoint tool')
    raw=bytes.fromhex('c00f a350 f055 1200')
    rom=tmp_path/'original.ch8';rom.write_bytes(raw)
    manifest={'source_repo':'https://example.invalid/authored-intake',
        'source_commit':'1'*40,'source_metadata_blob_sha':'2'*40,
        'source_license':'homegrown test fixture, not an external title',
        'programs':[dict(key='authored',title='Authored RNG loop',author='fDisBull tests',
            platform='chip8',size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
            git_blob_sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest())]}
    source_manifest=tmp_path/'manifest.json';source_manifest.write_text(json.dumps(manifest))
    pin=hashlib.sha256(source_manifest.read_bytes()).hexdigest();database=tmp_path/'intake.fdb'
    with create_intake(database,rom,manifest_path=source_manifest,manifest_sha256=pin,member='authored') as project:
        intake=project.chip8_intake_info()
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            ram=d.layer_patch('ram',0x350,expected_hex='00',data_hex='7a',kind='ram',activate=False)['layer']
            code=d.layer_patch('rng-mask',0x201,expected_hex='0f',data_hex='07',kind='execute',activate=False)['layer']
            d.layers([ram,code]);d.chip8_seed_rng(123)
            d.frame_inputs([{'key':'f','pressed':True}])
            hook=d.hook(0x230,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
            frames=d.timeline_start(storage_mode='delta',keyframe_interval=4,max_frames=4)
            child=d.timeline_advance(frames=1)
            point=child['point'];timeline=child['timeline']
            node=next(n for n in child['nodes'] if n['id']==point)
            assert node['checkpoint']['storage']['kind']=='delta'
            d.timeline_rewind(timeline=timeline,point=frames['point'],frames=0)
            before=d.registers(),d.chip8_environment(),d.memory(0, length=4096)['hex']
            keys=d.keyboard_state()['keyboard']['native']
            route={'format':'fdisbull-script-1','backend':'qemu-chip8','steps':[
                {'op':'step'},{'op':'step'},{'op':'step'},{'op':'registers'},
                {'op':'memory','address':0x350,'length':1},{'op':'screenshot'}]}
            saved=d.save_experiment('g0-trial.json',script=route,observations=[{'address':0x350,'length':1}])
            compared=d.compare_experiment(saved['artifact'],layers=[ram])
            assert compared['ok'] and compared['baseline_restored'] and compared['comparison']['observed_difference'],compared
            assert (d.registers(),d.chip8_environment(),d.memory(0,length=4096)['hex'])==before
            assert d.layers()['active']==[ram,code] and d.hooks()['hooks'][0]['hook']==hook['hook']
            assert d.keyboard_state()['keyboard']['native']['accepted-edges']==keys['accepted-edges']
            d.cpu_delta_start([{'address':0x350,'length':1}],registers=['v0','i','pc'],max_steps=4)
            assert d.cpu_delta_record(count=3)['recorded_count']==3
            assert d.cpu_delta_rewind(count=3)['partial_restored'] and d.cpu_delta_status()['frozen']
            with pytest.raises(ValueError,match='frozen|partial'):
                d.compare_experiment(saved['artifact'],layers=[ram])
            d.restore_experiment(saved['artifact'])
            assert not d.cpu_delta_status()['frozen']
            assert (d.registers(),d.chip8_environment(),d.memory(0,length=4096)['hex'])==before
            assert d.keyboard_state()['keyboard']['native']['held']==['f']
            assert d.keyboard_state()['keyboard']['native']['accepted-edges']==keys['accepted-edges']
            assert point in {n['id'] for n in d.timeline_status(timeline=timeline)['nodes']}
            assert d.timeline_image(timeline=timeline,point=point)['stored_frame']
            image=d.screenshot()['artifact'];project.debug_export(image,tmp_path/'stored.png')
            assert (tmp_path/'stored.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    with Project(database) as reopened:
        assert reopened.chip8_intake_info(expected_manifest_sha256=pin,
            expected_intake_sha256=intake['intake_sha256'])==intake
    assert rom.read_bytes()==raw
