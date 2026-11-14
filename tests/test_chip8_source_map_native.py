"""Source-map correlation and original/live fetch separation on actual v6."""
import hashlib
import json
import os

import pytest

from fdisbull.chip8_intake import create_intake
from fdisbull.project import Project


def test_native_contexts_original_map_and_preserved_layers_trials_undo(tmp_path):
    binary=os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU');tool=os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_FRAME_KEYS')=='1':pytest.fail('CHIP-8 v6 and checkpoint tool required')
        pytest.skip('Set CHIP-8 v6 runtime and checkpoint tool')
    # Two nested calls; 206 is unreached, and the final byte is an unknown tail.
    raw=bytes.fromhex('2208 6007 1204 ffff 220e 7001 00ee c00f 00ee')+b'\x7f'
    rom=tmp_path/'original.ch8';rom.write_bytes(raw)
    manifest={'source_repo':'https://example.invalid/authored-g2','source_commit':'1'*40,
        'source_metadata_blob_sha':'2'*40,'source_license':'homegrown test fixture',
        'programs':[dict(key='authored',title='Nested source fixture',author='fDisBull tests',platform='chip8',
            size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
            git_blob_sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest())]}
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest));pin=hashlib.sha256(path.read_bytes()).hexdigest()
    database=tmp_path/'mapping.fdb'
    with create_intake(database,rom,manifest_path=path,manifest_sha256=pin,member='authored') as project:
        intake=project.chip8_intake_info();project.analyze(max_instructions=32)
        closure=project.chip8_closure_resolve(environment='env:chip8-qemu-v6:1',include_analysis=True)
        count=project.db.execute('select count(*) from instructions').fetchone()[0]
        mapping=project.chip8_source_map(closure['closure'],max_instructions=32,max_states=64,max_call_depth=4)
        assert project.db.execute('select count(*) from instructions').fetchone()[0]==count
        assert mapping['coverage']['instructions']==8 and mapping['coverage']['unclassified_bytes']==3
        assert {(s['offset'],s['length']) for s in mapping['unclassified_spans']}=={(6,2),(18,1)}
        contexts={(s['pc'],tuple(s['return_stack'])) for s in mapping['states']}
        by_pc={i['pc']:i for i in mapping['instructions']}
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            d.chip8_seed_rng(123)
            for expected in (0x200,0x208,0x20e,0x210,0x20a,0x20c):
                regs=d.registers()['registers'];pc=int(regs['pc'],16);depth=int(regs['sp'],16)
                stack=tuple(int(regs['stack%d'%k],16) for k in range(depth))
                assert pc==expected and (pc,stack) in contexts
                assert d.code(pc,length=2,view='execute')['hex']==by_pc[pc]['word_hex']
                assert d.step()['outcome']=='step'
            regs=d.registers()['registers'];assert int(regs['pc'],16)==0x202
            assert int(regs['sp'],16)==0 and int(regs['stack0'],16)==int(regs['stack1'],16)==0
            ram=d.layer_patch('ram',0x350,expected_hex='00',data_hex='7a',kind='ram',activate=False)['layer']
            code=d.layer_patch('fetch',0x203,expected_hex='07',data_hex='09',kind='execute',activate=False)['layer']
            d.layers([ram,code]);d.frame_inputs([{'key':'f','pressed':True}])
            hook=d.hook(0x230,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
            assert d.code(0x202,length=2,view='execute')['hex']=='6009'
            assert by_pc[0x202]['word_hex']=='6007'
            assert project.chip8_source_map_info(mapping['mapping'])==mapping
            frames=d.timeline_start(storage_mode='delta',keyframe_interval=4,max_frames=4)
            child=d.timeline_advance(frames=1);point=child['point'];timeline=child['timeline']
            assert next(n for n in child['nodes'] if n['id']==point)['checkpoint']['storage']['kind']=='delta'
            d.timeline_rewind(timeline=timeline,point=frames['point'],frames=0)
            before=d.registers(),d.chip8_environment(),d.memory(0,length=4096)['hex'];keys=d.keyboard_state()['keyboard']['native']
            route={'format':'fdisbull-script-1','backend':'qemu-chip8','steps':[{'op':'step'},{'op':'step'},{'op':'registers'}]}
            saved=d.save_experiment('g2-trial.json',script=route)
            compared=d.compare_experiment(saved['artifact'],layers=[ram])
            assert compared['ok'] and compared['baseline_restored'] and compared['comparison']['observed_difference'],compared
            d.cpu_delta_start([{'address':0x350,'length':1}],registers=['v0','pc'],max_steps=4)
            assert d.cpu_delta_record(count=2)['recorded_count']==2
            assert d.cpu_delta_rewind(count=2)['partial_restored'] and d.cpu_delta_status()['frozen']
            assert project.chip8_source_map_info(mapping['mapping'])==mapping
            d.restore_experiment(saved['artifact']);assert not d.cpu_delta_status()['frozen']
            assert (d.registers(),d.chip8_environment(),d.memory(0,length=4096)['hex'])==before
            assert d.layers()['active']==[ram,code] and d.hooks()['hooks'][0]['hook']==hook['hook']
            after=d.keyboard_state()['keyboard']['native'];assert after['held']==['f'] and after['accepted-edges']==keys['accepted-edges']
            assert d.timeline_image(timeline=timeline,point=point)['stored_frame']
            image=d.screenshot()['artifact'];project.debug_export(image,tmp_path/'stored.png')
            assert (tmp_path/'stored.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            assert project.chip8_closure_info(closure['closure'])==closure
    with Project(database) as project:
        assert project.chip8_intake_info()==intake
        assert project.chip8_closure_info(closure['closure'])==closure
        assert project.chip8_source_map_info(mapping['mapping'])==mapping
    assert rom.read_bytes()==raw
