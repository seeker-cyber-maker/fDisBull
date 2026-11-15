"""Native selected CPU/RAM inverse is frozen partial state, not machine rewind."""
from copy import deepcopy
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, mz_exit, prepare_dos_baseline
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch


def _fixture(kind):
    # Actual executed instructions write selected AX/RAM and excluded BX/RAM.
    if kind == 'com':
        code = bytes.fromhex('b81111a32001bb2222891e220190ebfe').ljust(0x24,b'\0')
        return code,dict(filename='UNDO.COM',image='com',ready=0,selected=0x20,excluded=0x22)
    data,_ = mz_exit()
    data = bytearray(data)
    # Preserve DOS relocation at module 22h: relocated AX establishes DS=module+70h.
    code = bytes.fromhex('90b807008ed8b81111a30000bb2222891e020090ebfe')
    data[64+0x20:64+0x20+len(code)] = code
    return bytes(data),dict(filename='UNDO.EXE',image=None,ready=0x26,selected=0x70,excluded=0x72)


def _regs(debug):
    return {key:int(value,16) for key,value in debug.registers()['registers'].items()}


def _word(debug,address):
    return int.from_bytes(bytes.fromhex(debug.memory(address,length=2,space='physical')['hex']),'little')


@pytest.mark.parametrize('kind',['com','mz'])
def test_native_cpu_projection_partial_undo_freezes_then_full_anchor_recovers(tmp_path,kind):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE']); boot_sha = digest(boot)
    disk = prepare_dos_baseline(boot,tmp_path / 'baseline.img',runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n'+BASELINE_CONFIG)
    data, marker = _fixture(kind)
    source = tmp_path / marker['filename']; source.write_bytes(data)
    with Project.create(tmp_path / 'undo.fdb',source,image=marker['image']) as project:
        static = project.regions(1)[0].start
        with _launch(project,runtime,tmp_path,disk,clock_profile='virtual') as debug:
            base = debug.dos_process_info()['source_mapping']['runtime_base']
            ready = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=30000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(ready['breakpoint_id'])
            initial_regs = _regs(debug)
            assert _word(debug,base + marker['selected']) == 0
            assert _word(debug,base + marker['excluded']) == 0
            started = debug.cpu_delta_start([dict(address=hex(static + marker['selected']),length=2)],
                                           registers=['rax','rip'],max_steps=8,timeout_ms=60000)
            assert started['anchor']['artifact']
            forward = debug.cpu_delta_record(count=4,timeout_ms=50000)
            assert forward['outcome'] == 'completed' and forward['recorded_count'] == 4
            later = _regs(debug)
            assert later['rax'] & 0xffff == 0x1111 and later['rbx'] & 0xffff == 0x2222
            assert _word(debug,base + marker['selected']) == 0x1111
            assert _word(debug,base + marker['excluded']) == 0x2222
            restored = debug.cpu_delta_rewind(count=4,timeout_ms=60000)
            assert restored['partial_restored'] and not restored['full_machine_restored']
            assert not restored['devices_restored'] and not restored['resume_safe'] and not restored['execution_allowed']
            partial = _regs(debug)
            assert partial['rax'] == initial_regs['rax'] and partial['rip'] == initial_regs['rip']
            assert partial['rbx'] == later['rbx']
            assert _word(debug,base + marker['selected']) == 0
            assert _word(debug,base + marker['excluded']) == 0x2222
            assert debug.cpu_delta_status()['frozen']
            for operation in (lambda:debug.step(timeout_ms=5000),lambda:debug.run(timeout_ms=5000),
                              lambda:debug.save_state(),lambda:debug.cpu_delta_record()):
                with pytest.raises(ValueError,match='frozen|partial'):
                    operation()
            old = debug.vm.process
            recovered = debug.cpu_delta_recover(timeout_ms=60000)
            assert recovered['full_native_anchor_loaded'] and old.poll() is not None
            assert not debug.cpu_delta_status()['frozen']
            assert _regs(debug) == initial_regs
            assert _word(debug,base + marker['selected']) == 0 and _word(debug,base + marker['excluded']) == 0
            assert debug.step(timeout_ms=5000)['outcome'] == 'step'
    assert source.read_bytes() == data and digest(boot) == boot_sha


def test_native_cpu_projection_preserves_held_keys_private_irq_and_recovers(tmp_path):
    from support.qemu_dos_irq_fixture import ANCHOR, MONITOR_UUID, irq_fixture
    from test_qemu_dos_irq_preemption_native import _hit, _number
    from test_qemu_dos_history_native import _state, _assert_state
    from test_qemu_frame_keys_native import MAKE, _proof

    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE']); boot_sha = digest(boot)
    disk = prepare_dos_baseline(boot,tmp_path / 'baseline.img',runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n'+BASELINE_CONFIG)
    data, marker = irq_fixture(tmp_path,runtime['NASM'],fpu=True)
    source = tmp_path / 'IRQ.COM'; source.write_bytes(data)
    assert data[marker['irq_hook']:marker['irq_hook']+6] == bytes.fromhex('909c5883e001')
    with Project.create(tmp_path / 'private-undo.fdb',source,image='com') as project:
        static = project.regions(1)[0].start
        with _launch(project,runtime,tmp_path,disk,clock_profile='virtual') as debug:
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=45000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            binding = debug.dos_task_bind(anchor_address=ANCHOR,expected_monitor=MONITOR_UUID)
            debug.dos_task_switching()
            names = ('scratch','irq_count','return_ip','carry','irq_data','irq_fetch','fp_result','loop_count')
            addresses = [base + marker[name] for name in names]
            for name in ('b_stack','ring0_stack','vm_stack'):
                addresses.extend((base + marker[name]-64,base + marker[name]-1))
            addresses.extend((base + marker['return_ip']+3,base + marker['loop_count']+3,
                              base + marker['fp_result']+7))
            pages = sorted({address & ~4095 for address in addresses})
            a = debug.dos_task_register(cookie=0xa1,incarnation=1,pages=pages)['task_id']
            b = debug.dos_task_register(cookie=0xb2,incarnation=2,pages=pages)['task_id']
            assert a == binding['task_id'] and a != b
            scratch,fetch,carry = base + marker['scratch'],base + marker['irq_fetch'],base + marker['carry']
            stacks = {}
            for task,ram_hex,code_hex in ((a,'3412','f8'),(b,'7856','f9')):
                ram = debug.dos_task_layer_patch('undo-ram-'+task[-8:],scratch,expected_hex='0000',
                    data_hex=ram_hex,kind='ram',task=task,activate=False)['layer']
                code = debug.dos_task_layer_patch('undo-code-'+task[-8:],fetch,expected_hex='90',
                    data_hex=code_hex,kind='execute',task=task,activate=False)['layer']
                stacks[task] = [ram,code]
                debug.dos_task_layers(stacks[task],task=task)
            debug.dos_task_scheduler()
            flags = debug.dos_task_context(task=a)['eflags'] & ~0x200
            debug.dos_task_fork(task=b,entry=hex(static + marker['b_entry']),
                                stack=base + marker['b_stack'],eflags=flags)
            debug.dos_task_preemption(irq=0,quantum=1,enabled=True)
            upper = _number(debug.registers()['registers']['rbx']) & ~0xffff
            hook_a = debug.hook(hex(static + marker['irq_hook']),task=a,space='source',once=False,max_hits=3,
                actions=[dict(op='registers',registers={'rbx':dict(expected=upper|0xa11a,value=upper|0xa11a)})])['hook']
            _hit(debug,hook_a,1,0xa11a,0x1111,0,False)
            point = debug.breakpoint(base + marker['b_entry'])
            assert debug.run(timeout_ms=45000,stop_on_hook=True)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            hook_b = debug.hook(hex(static + marker['irq_hook']),task=b,space='source',once=False,max_hits=3,
                actions=[dict(op='registers',registers={'rbx':dict(expected=upper|0xb22b,value=upper|0xb22b)})])['hook']
            _hit(debug,hook_b,1,0xb22b,0x2222,1,True)
            _hit(debug,hook_a,2,0xa11a,0x1111,0,False)
            # Step over the pending hook to the verified AND EAX,1, without
            # executing an EOI, IRET, or an SP-changing instruction in the projection.
            point = debug.breakpoint(base + marker['irq_hook'] + 3)
            assert debug.run(timeout_ms=45000,stop_on_hook=True)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            carry_layer = debug.dos_task_layer_patch('undo-a-carry',carry,expected_hex='0000',
                data_hex='7777',kind='ram',task=a,activate=False)['layer']
            debug.dos_task_layers(stacks[a] + [carry_layer],task=a)
            control = dict(a=a,b=b,hook_a=hook_a,hook_b=hook_b,scratch=scratch,fetch=fetch,
                irq_count=base + marker['irq_count'],return_ip=base + marker['return_ip'])
            native = debug.frame_inputs(MAKE)['native']
            proof = _proof(native)
            before = _state(debug,control,task=a,cookie=0xa1,count=2)
            assert before['preemption']['pic-mask'] & 2
            assert debug.dos_task_memory(carry,length=2,task=a,view='ram')['hex'] == '7777'
            b_carry = debug.dos_task_memory(carry,length=2,task=b,view='ram')['hex']
            assert b_carry == '0100'  # B's earlier STC was recorded by the genuine IRQ handler.
            debug.cpu_delta_start([dict(address=hex(static+marker['carry']),length=2)],
                                  registers=['rax','rip'],max_steps=4,timeout_ms=60000)
            recorded = debug.cpu_delta_record(count=2,timeout_ms=50000)
            assert recorded['outcome'] == 'completed' and recorded['recorded_count'] == 2
            assert debug.dos_task_memory(carry,length=2,task=a,view='ram')['hex'] == '0000'
            after = _state(debug,control,task=a,cookie=0xa1,count=2)
            after_keys = _proof(debug.keyboard_state()['keyboard']['native'])
            inverse = debug.cpu_delta_rewind(count=2,timeout_ms=60000)
            assert inverse['partial_restored'] and not inverse['full_machine_restored']
            assert not inverse['devices_restored'] and not inverse['execution_allowed']
            assert debug.cpu_delta_status()['frozen']
            assert debug.dos_task_memory(carry,length=2,task=a,view='ram')['hex'] == '7777'
            assert debug.dos_task_memory(carry,length=2,task=b,view='ram')['hex'] == b_carry
            assert debug.memory(carry,length=2,space='physical')['hex'] == '0000'
            partial = _state(debug,control,task=a,cookie=0xa1,count=2)
            for key in ('preemption','frame','hooks','ram_a','ram_b','code_a','code_b','base_ram','base_code','clock_ns'):
                assert partial[key] == after[key]
            assert _proof(debug.keyboard_state()['keyboard']['native']) == after_keys
            with pytest.raises(ValueError,match='frozen|partial'): debug.run(timeout_ms=5000)
            old = debug.vm.process
            assert debug.cpu_delta_recover(timeout_ms=60000)['full_native_anchor_loaded']
            assert old.poll() is not None and not debug.cpu_delta_status()['frozen']
            _assert_state(debug,control,before,task=a,cookie=0xa1,count=2)
            assert debug.dos_task_memory(carry,length=2,task=b,view='ram')['hex'] == b_carry
            keys = debug.keyboard_state()['keyboard']['native']
            assert _proof(keys) == proof and keys['token'] != native['token'] and keys['epoch'] != native['epoch']
            _hit(debug,hook_b,2,0xb22b,0x2222,1,True)
    assert source.read_bytes() == data and digest(boot) == boot_sha


@pytest.mark.parametrize('storage',['full','delta'])
def test_native_cpu_projection_full_timeline_restore_clears_freeze(tmp_path,storage):
    from test_qemu_memory_rules_native import _case
    with _case(tmp_path) as (project,debug,marker,base,_,_):
        timeline = debug.timeline_start(storage_mode=storage,keyframe_interval=3,
                                        period_ns=20_000_000,timeout_ms=60000)
        completed = debug.timeline_advance(frames=1,timeout_ms=60000)
        assert completed['completed_frames'] == 1
        node = next(node for node in completed['nodes'] if node['id'] == completed['point'])
        if storage == 'delta': assert node['checkpoint']['storage']['kind'] == 'delta'
        before_regs = _regs(debug)
        static = project.regions(1)[0].start
        debug.cpu_delta_start([dict(address=hex(static + marker['counter']),length=4)],
                              registers=['rip'],max_steps=4,timeout_ms=60000)
        recorded = debug.cpu_delta_record(count=1,timeout_ms=50000)
        assert recorded['outcome'] == 'completed' and recorded['recorded_count'] == 1
        assert debug.cpu_delta_rewind(count=1,timeout_ms=60000)['partial_restored']
        assert debug.cpu_delta_status()['frozen']
        old = debug.vm.process
        restored = debug.timeline_rewind(timeline=completed['timeline'],point=completed['point'],timeout_ms=60000)
        assert old.poll() is not None and restored['point'] == completed['point']
        assert not debug.cpu_delta_status()['frozen'] and _regs(debug) == before_regs
        assert debug.step(timeout_ms=5000)['outcome'] == 'step'
