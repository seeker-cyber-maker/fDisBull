"""Bounded actual-QEMU comparative trials over authored DOS programs."""
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from test_qemu_cpu_deltas_native import _fixture, _regs
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch


def _route(*steps):
    return dict(format='fdisbull-script-1',backend='qemu-dos',steps=list(steps))


@pytest.mark.parametrize('kind,space',[('com','source'),('mz','source'),('com','physical')])
def test_native_experiment_compares_source_fetch_and_exports_real_frame(tmp_path,kind,space):
    runtime=_inputs()
    boot=Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE']); boot_sha=digest(boot)
    disk=prepare_dos_baseline(boot,tmp_path/'disk.img',runtime['FDISBULL_QEMU_DOS_MCOPY'],
                              config=b'SWITCHES=/F\r\n'+BASELINE_CONFIG)
    data,marker=_fixture(kind); source=tmp_path/marker['filename']; source.write_bytes(data)
    path=tmp_path/'trial.fdb'
    with Project.create(path,source,image=marker['image']) as project:
        static=project.regions(1)[0].start
        with _launch(project,runtime,tmp_path,disk,clock_profile='virtual') as debug:
            base=debug.dos_process_info()['source_mapping']['runtime_base']
            stop=debug.breakpoint(base+marker['ready'])
            assert debug.run(timeout_ms=30000)['outcome']=='breakpoint'
            debug.delete_breakpoint(stop['breakpoint_id'])
            address=(static if space=='source' else base)+marker['ready']+1
            layer=debug.layer_patch('candidate',address,expected_hex='1111',
                data_hex='2222',kind='execute',space=space,activate=False)['layer']
            original_layer_sha=project.debug_layer_info(layer)['sha256']
            debug.breakpoint(base+marker['ready']+13)
            saved=debug.save_experiment('trial.json',script=_route(
                dict(op='step'),dict(op='step'),dict(op='trace',count=1,timeout_ms=10000),
                dict(op='run',expect='breakpoint',timeout_ms=10000),dict(op='registers'),
                dict(op='memory',address=hex(base+marker['selected']),space='physical',length=2),
                dict(op='screenshot')),observations=[dict(address=hex(static+marker['selected']),length=2)])
            same=debug.compare_experiment(saved['artifact'],layers=[],timeout_ms=60000)
            assert same['ok'] and same['baseline_restored'] and same['comparison']['complete'],same
            assert same['comparison']['observed_difference'] is False
            result=debug.compare_experiment(saved['artifact'],layers=[layer],timeout_ms=60000)
            assert project.debug_layer_info(layer)['sha256']==original_layer_sha
            assert result['ok'] and result['baseline_restored'] and result['comparison']['complete'],result
            assert result['comparison']['observed_difference'] is True
            assert result['baseline']['memory'][0]['hex']=='1111'
            assert result['layer']['memory'][0]['hex']=='2222'
            assert result['baseline']['registers']['registers']['rax']&0xffff==0x1111
            assert result['layer']['registers']['registers']['rax']&0xffff==0x2222
            assert result['baseline']['traces'] and result['layer']['traces']
            image=result['baseline']['screenshots'][0]['artifact']
            report=result['artifact']
    with Project(path) as project:
        assert project.debug_experiment_info(saved['artifact'])
        project.debug_export(image,tmp_path/'actual.png')
        project.debug_export(report,tmp_path/'comparison.json')
        assert (tmp_path/'actual.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        with _launch(project,runtime,tmp_path,disk,clock_profile='virtual') as debug:
            restored=debug.restore_experiment(saved['artifact'])
            assert restored['source_binding_restored']
    assert source.read_bytes()==data and digest(boot)==boot_sha


def test_native_failed_baseline_skips_candidate_and_restores_controls(tmp_path):
    runtime=_inputs(); boot=Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE']); original=digest(boot)
    disk=prepare_dos_baseline(boot,tmp_path/'disk.img',runtime['FDISBULL_QEMU_DOS_MCOPY'],
                              config=b'SWITCHES=/F\r\n'+BASELINE_CONFIG)
    data,marker=_fixture('com'); source=tmp_path/'FAIL.COM'; source.write_bytes(data)
    with Project.create(tmp_path/'failure.fdb',source,image='com') as project:
        static=project.regions(1)[0].start
        with _launch(project,runtime,tmp_path,disk,clock_profile='virtual') as debug:
            base=debug.dos_process_info()['source_mapping']['runtime_base']
            ready=debug.breakpoint(base+marker['ready'])
            assert debug.run(timeout_ms=30000)['outcome']=='breakpoint'
            debug.delete_breakpoint(ready['breakpoint_id'])
            bx=_regs(debug)['rbx']
            hook=debug.hook(hex(static+marker['ready']),space='source',once=False,max_hits=3,
                actions=[dict(op='registers',registers={'rbx':dict(expected=bx,value=bx)})])['hook']
            assert debug.run(stop_on_hook=True,timeout_ms=30000)['outcome']=='hook'
            passed=debug.breakpoint(base+marker['ready']+3)
            assert debug.run(stop_on_hook=True,timeout_ms=30000)['outcome']=='breakpoint'
            debug.delete_breakpoint(passed['breakpoint_id'])
            bp=debug.breakpoint(base+marker['ready']+6)
            route=_route(dict(op='delete-breakpoint',breakpoint_id=f"$controls.breakpoints.{bp['breakpoint_id']}.breakpoint_id"),
                         dict(op='assert',value=1,equals=2))
            saved=debug.save_experiment('fail.json',script=route)
            result=debug.compare_experiment(saved['artifact'],layers=[],timeout_ms=60000)
            assert not result['ok'] and result['baseline_restored'] and result['layer'] is None,result
            assert result['error']['type']=='ScriptFailure'
            controls=debug.controls()
            assert controls['breakpoints'] and any(h['hook']==hook and h['hits']==1 for h in controls['hooks'])
    assert source.read_bytes()==data and digest(boot)==original


def test_native_experiment_restores_private_irq_and_held_keys(tmp_path):
    from support.qemu_dos_irq_fixture import ANCHOR, MONITOR_UUID, irq_fixture
    from test_qemu_dos_irq_preemption_native import _hit, _number
    from test_qemu_dos_history_native import _state, _assert_state

    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    original_boot = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    data, marker = irq_fixture(tmp_path, runtime['NASM'], fpu=True)
    source = tmp_path / 'IRQ.COM'; source.write_bytes(data)
    with Project.create(tmp_path / 'irq-frame.fdb', source, image='com') as project:
        static = project.regions(1)[0].start
        with _launch(project, runtime, tmp_path, disk, clock_profile='virtual') as debug:
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            ready = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=45000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(ready['breakpoint_id'])
            binding = debug.dos_task_bind(anchor_address=ANCHOR, expected_monitor=MONITOR_UUID)
            debug.dos_task_switching()
            names = ('scratch','irq_count','return_ip','carry','irq_data','irq_fetch','fp_result','loop_count')
            addresses = [base + marker[name] for name in names]
            for name in ('b_stack','ring0_stack','vm_stack'):
                addresses.extend((base + marker[name] - 64,base + marker[name] - 1))
            addresses.extend((base + marker['return_ip'] + 3,base + marker['loop_count'] + 3,
                              base + marker['fp_result'] + 7))
            pages = sorted({address & ~4095 for address in addresses})
            a = debug.dos_task_register(cookie=0xa1,incarnation=1,pages=pages)['task_id']
            b = debug.dos_task_register(cookie=0xb2,incarnation=2,pages=pages)['task_id']
            assert a == binding['task_id'] and a != b
            scratch, fetch = base + marker['scratch'], base + marker['irq_fetch']
            for task, ram_hex, code_hex in ((a,'3412','f8'),(b,'7856','f9')):
                ram = debug.dos_task_layer_patch('frame-irq-ram-' + task[-8:],scratch,
                    expected_hex='0000',data_hex=ram_hex,kind='ram',task=task,activate=False)['layer']
                code = debug.dos_task_layer_patch('frame-irq-fetch-' + task[-8:],fetch,
                    expected_hex='90',data_hex=code_hex,kind='execute',task=task,activate=False)['layer']
                debug.dos_task_layers([ram,code],task=task)
            debug.dos_task_scheduler()
            flags = debug.dos_task_context(task=a)['eflags'] & ~0x200
            debug.dos_task_fork(task=b,entry=hex(static + marker['b_entry']),
                                stack=base + marker['b_stack'],eflags=flags)
            debug.dos_task_preemption(irq=0,quantum=1,enabled=True)
            upper = _number(debug.registers()['registers']['rbx']) & ~0xffff
            hook_a = debug.hook(hex(static + marker['irq_hook']),task=a,space='source',once=False,
                max_hits=3,actions=[dict(op='registers',registers={
                    'rbx':dict(expected=upper | 0xa11a,value=upper | 0xa11a)})])['hook']
            _hit(debug,hook_a,1,0xa11a,0x1111,0,False)
            point = debug.breakpoint(base + marker['b_entry'])
            assert debug.run(timeout_ms=45000,stop_on_hook=True)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            hook_b = debug.hook(hex(static + marker['irq_hook']),task=b,space='source',once=False,
                max_hits=3,actions=[dict(op='registers',registers={
                    'rbx':dict(expected=upper | 0xb22b,value=upper | 0xb22b)})])['hook']
            _hit(debug,hook_b,1,0xb22b,0x2222,1,True)
            _hit(debug,hook_a,2,0xa11a,0x1111,0,False)
            control = dict(a=a,b=b,hook_a=hook_a,hook_b=hook_b,scratch=scratch,fetch=fetch,
                irq_count=base + marker['irq_count'],return_ip=base + marker['return_ip'])
            from test_qemu_frame_keys_native import MAKE, _proof
            keys = debug.frame_inputs(MAKE)['native']
            key_proof = _proof(keys)
            saved = _state(debug,control,task=a,cookie=0xa1,count=2)
            old_stack = debug.dos_task_layers(task=a)['active']
            assert debug.dos_task_memory(scratch,length=2,task=a,view='ram')['hex'] == '3412'
            candidate = debug.dos_task_layer_patch('trial-a-scratch',scratch,
                expected_hex='0000',
                data_hex='abcd',kind='ram',task=a,activate=False)['layer']
            experiment = debug.save_experiment('irq-trial.json',script=_route(dict(op='registers')),
                observations=[dict(address=hex(static + marker['scratch']),length=2)])
            result = debug.compare_experiment(experiment['artifact'],layers=old_stack+[candidate],timeout_ms=60000)
            assert result['ok'] and result['baseline_restored'] and result['comparison']['complete'],result
            assert result['comparison']['observed_difference'] is True
            assert result['layer']['memory'][0]['hex']=='abcd'
            _assert_state(debug,control,saved,task=a,cookie=0xa1,count=2)
            restored_keys=debug.keyboard_state()['keyboard']['native']
            assert _proof(restored_keys)==key_proof and restored_keys['token']!=keys['token']
            _hit(debug,hook_b,2,0xb22b,0x2222,1,True)
    assert source.read_bytes() == data and digest(boot) == original_boot



def test_native_experiment_full_restore_recovers_frozen_projection_and_keeps_frame_dag(tmp_path):
    from test_qemu_memory_rules_native import _case
    with _case(tmp_path) as (project,debug,marker,base,_,_):
        timeline=debug.timeline_start(storage_mode='delta',keyframe_interval=3,period_ns=20_000_000,timeout_ms=60000)
        frame=debug.timeline_advance(frames=1,timeout_ms=60000)
        assert frame['completed_frames']==1
        image=debug.timeline_image('retained.png',point=frame['point'])['artifact']
        experiment=debug.save_experiment('frozen-trial.json',script=_route(dict(op='registers')))
        static=project.regions(1)[0].start
        debug.cpu_delta_start([dict(address=hex(static+marker['counter']),length=4)],registers=['rip'],max_steps=4)
        assert debug.cpu_delta_record(count=1,timeout_ms=50000)['recorded_count']==1
        assert debug.cpu_delta_rewind(count=1)['partial_restored']
        assert debug.cpu_delta_status()['frozen']
        with pytest.raises(ValueError,match='frozen|partial'):
            debug.compare_experiment(experiment['artifact'],layers=[])
        restored=debug.restore_experiment(experiment['artifact'])
        assert restored['source_binding_restored'] and not debug.cpu_delta_status()['frozen']
        status=debug.timeline_status(timeline=timeline['timeline'])
        assert any(n['id']==frame['point'] for n in status['nodes'])
        project.debug_export(image,tmp_path/'retained.png')
        assert (tmp_path/'retained.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
