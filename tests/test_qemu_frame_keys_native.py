"""Native owned frame-key edges, guest consumption and checkpoint identity.

QEMU hardware typematic is explicitly unsupported; held keys are never assumed
or tested to repeat. All target programs and expected scan codes are authored.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_io_fixture import bios_keyboard_display, raw_keyboard_mouse
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch


MAKE = [dict(key='shift',pressed=True),dict(key='a',pressed=True)]
BREAK = [dict(key='a',pressed=False),dict(key='shift',pressed=False)]
PROOF = ('generation','accepted-edges','held','device-path','device-type','scan-enabled',
    'scancode-set','translated','modifier-mask','fifo-count','fifo-sha256',
    'fifo-read-pointer','fifo-write-pointer','fifo-command-pointer','write-command',
    'controller-status','controller-mode','controller-pending','controller-obsrc',
    'controller-obdata','throttle-deadline-ns')


def _bytes(debug, address, size):
    return bytes.fromhex(debug.memory(address,length=size,space='physical')['hex'])


def _word(debug,address):
    return int.from_bytes(_bytes(debug,address,2),'little')


def _guest(debug, symbols, kind):
    if kind == 'bios':
        return dict(count=_word(debug,symbols['key_count_ip']),
                    last=_word(debug,symbols['last_key_ip']),shift=_bytes(debug,0x417,1)[0])
    count = _word(debug,symbols['keyboard_count_ip'])
    assert count <= 64
    return dict(count=count,scans=_bytes(debug,symbols['keyboard_bytes_ip'],count).hex())


def _proof(state):
    return {name:state[name] for name in PROOF}


def _consume(debug, symbols, kind):
    result = debug.advance_frames(frames=3,timeout_ms=60000)
    assert result['completed_frames'] == 3 and result['completed_guest_frame'] is None
    guest = _guest(debug,symbols,kind)
    if kind == 'bios':
        assert guest['count'] == 1 and guest['last'] == 0x1e41
        assert guest['shift'] & 0x02
    else:
        assert guest == dict(count=2,scans='2a1e')
    return guest


def _release(debug,symbols,kind):
    receipt = debug.frame_inputs(BREAK,timeout_ms=5000)
    assert receipt['held'] == []
    assert debug.advance_frames(frames=3,timeout_ms=60000)['completed_frames'] == 3
    guest = _guest(debug,symbols,kind)
    if kind == 'bios':
        assert guest['count'] == 1 and guest['shift'] & 0x03 == 0
    else:
        assert guest == dict(count=4,scans='2a1e9eaa')
    return guest


def _cold(control):
    runtime = _inputs()
    with Project(control['db']) as project:
        with _launch(project,runtime,control['dir'],{'image':control['disk']},clock_profile='virtual') as debug:
            fresh = debug.vm.process
            restored = debug.load_state(control['checkpoint'])
            assert fresh.poll() is not None and restored['source_binding_restored']
            native = debug.keyboard_state()['keyboard']['native']
            assert native['token'] != control['token'] and native['epoch'] != control['epoch']
            assert native['active'] and native['valid'] and not native['repeat-supported']
            assert _proof(native) == control['proof']
            assert sorted(debug.keyboard_state()['keyboard']['frame_keys']) == ['a','shift']
            symbols = control['symbols']
            assert _consume(debug,symbols,control['kind']) == control['consumed']
            assert _release(debug,symbols,control['kind']) == control['released']
    return {'passed':True}


@pytest.mark.parametrize('kind',['bios','raw'])
def test_native_held_key_checkpoint_before_consumption_restores_without_reinject(tmp_path,kind):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE']); boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot,tmp_path / 'baseline.img',runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n'+BASELINE_CONFIG)
    data, offsets = (bios_keyboard_display if kind == 'bios' else raw_keyboard_mouse)(tmp_path,runtime['NASM'])
    source = tmp_path / 'KEYS.COM'; source.write_bytes(data)
    db = tmp_path / 'keys.fdb'
    with Project.create(db,source,image='com') as project:
        with _launch(project,runtime,tmp_path,disk,clock_profile='virtual') as debug:
            base = debug.dos_process_info()['source_mapping']['runtime_base']
            symbols = {key:base + value - 0x100 for key,value in offsets.items() if key.endswith('_ip')}
            point = debug.breakpoint(symbols['ready_ip'])
            assert debug.run(timeout_ms=30000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            if kind == 'raw': assert _word(debug,symbols['setup_status_ip']) == 1
            debug.timeline_start(period_ns=20_000_000,timeout_ms=60000)
            before_regs = debug.registers()['registers']; before_clock = debug.clock_observe()['virtual_ns']
            receipt = debug.frame_inputs(MAKE,timeout_ms=5000)
            native = receipt['native']
            assert receipt['held'] == ['a','shift'] and receipt['guest_consumed'] is None
            assert native['active'] and native['valid'] and not native['repeat-supported']
            assert native['accepted-edges'] == 2 and native['generation'] == 1
            assert native['fifo-count'] > 0 or native['controller-status'] & 1
            assert debug.registers()['registers'] == before_regs and debug.clock_observe()['virtual_ns'] == before_clock
            saved = debug.save_state()
            control = dict(db=str(db),dir=str(tmp_path),disk=str(disk['image']),kind=kind,symbols=symbols,
                checkpoint=saved['artifact'],token=native['token'],epoch=native['epoch'],proof=_proof(native))
            control['consumed'] = _consume(debug,symbols,kind)
            control['released'] = _release(debug,symbols,kind)
        assert debug.vm.process.poll() is not None
    path = tmp_path / 'keys-control.json'; path.write_text(json.dumps(control))
    child = subprocess.run([sys.executable,str(Path(__file__).resolve()),str(path)],
        capture_output=True,text=True,env=os.environ.copy(),timeout=240)
    assert child.returncode == 0, child.stderr[-6000:]
    assert json.loads(child.stdout)['passed'] is True
    assert source.read_bytes() == data and digest(boot) == boot_hash


if __name__ == '__main__':
    print(json.dumps(_cold(json.loads(Path(sys.argv[1]).read_text()))))


def test_native_timeline_frame_keys_schedule_branch_and_dirty_rewind(tmp_path):
    from test_qemu_memory_rules_native import _case
    with _case(tmp_path) as (project,debug,_,_,_,_):
        root = debug.timeline_start(max_frames=12,period_ns=20_000_000,timeout_ms=60000)
        original = debug.timeline_advance(frames=3,inputs=[
            dict(frame=0,edges=MAKE),dict(frame=2,edges=BREAK)],timeout_ms=60000)
        assert original['completed_frames'] == 3 and original['completed_guest_frame'] is None
        old_head = original['point']
        nodes = {row['id']:row for row in original['nodes']}
        assert sorted(nodes[original['frames'][0]['point']]['frame']['keys']) == ['a','shift']
        assert nodes[old_head]['frame']['keys'] == []
        assert debug.keyboard_state()['keyboard']['frame_keys'] == []
        debug.timeline_rewind(frames=3,timeout_ms=60000)
        assert debug.timeline_status()['point'] == root['point']
        branch = debug.timeline_advance(frames=3,inputs=[
            dict(frame=0,edges=[dict(key='shift',pressed=True),dict(key='b',pressed=True)]),
            dict(frame=2,edges=[dict(key='b',pressed=False),dict(key='shift',pressed=False)])],timeout_ms=60000)
        assert branch['completed_frames'] == 3 and branch['point'] != old_head
        assert old_head in {row['id'] for row in branch['nodes']}
        point = branch['point']
        debug.frame_inputs([dict(key='shift',pressed=True)])
        assert debug.keyboard_state()['keyboard']['frame_keys'] == ['shift']
        with pytest.raises(ValueError,match='dirty'):
            debug.timeline_pin('dirty.qcow2')
        restored = debug.timeline_rewind(frames=0,timeout_ms=60000)
        assert restored['point'] == point
        assert debug.keyboard_state()['keyboard']['frame_keys'] == []


def test_native_frame_key_cas_capacity_and_external_input_guards(tmp_path):
    import uuid
    from fdisbull.dosbox_rpc import DebuggerError
    from test_qemu_memory_rules_native import _case
    with _case(tmp_path) as (project,debug,_,_,_,_):
        debug.timeline_start(period_ns=20_000_000,timeout_ms=60000)
        before = debug.registers()['registers'],debug.clock_observe()['virtual_ns']
        native = debug.vm.qmp.call('x-fdisbull-query-frame-keys')
        assert native['repeat-supported'] is False and native['edge-capacity'] == 2
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call('x-fdisbull-apply-frame-key-edges',{
                'token':uuid.uuid4().hex,'expected-generation':native['generation'] + 1,
                'edges':[dict(key='a',pressed=True)]})
        assert debug.vm.qmp.call('x-fdisbull-query-frame-keys') == native
        with pytest.raises(ValueError,match='capacity'):
            debug.frame_inputs([dict(key='shift',pressed=True),dict(key='a',pressed=True),
                                dict(key='b',pressed=True)])
        assert debug.vm.qmp.call('x-fdisbull-query-frame-keys') == native
        debug.frame_inputs(MAKE)
        held = debug.keyboard_state()['keyboard']['native']
        assert held['edge-capacity'] == 0
        with pytest.raises(ValueError): debug.frame_inputs([dict(key='a',pressed=True)])
        with pytest.raises(ValueError,match='frame|owned|keyboard'):
            debug.keyboard_key_down('b')
        with pytest.raises(DebuggerError):
            debug.vm.qmp.call('x-fdisbull-apply-frame-key-edges',{
                'token':uuid.uuid4().hex,'expected-generation':held['generation'],
                'edges':[dict(key='b',pressed=True)]})
        assert debug.keyboard_state()['keyboard']['native'] == held
        assert (debug.registers()['registers'],debug.clock_observe()['virtual_ns']) == before


@pytest.mark.parametrize('route',['python','json','script'])
def test_native_frame_input_public_routes_dispatch_once(tmp_path,route):
    from fdisbull.cli import respond
    from fdisbull.debug_script import execute_script
    from fdisbull.debugger import DebugWorkspace
    from test_qemu_memory_rules_native import _case
    with _case(tmp_path) as (project,debug,_,_,_,_):
        workspace = DebugWorkspace(); workspace.sessions[debug.run_id] = debug
        def invoke(name,**options):
            if route == 'python': return getattr(debug,name.replace('-','_'))(**options)
            if route == 'json':
                reply = respond(dict(method='debug-'+name,params=dict(project=str(project.path),
                    run=debug.run_id,context='machine',**options)),debugger=workspace)
                assert reply['ok'], reply
                return reply['result']
            report = execute_script(debug,dict(format='fdisbull-script-1',backend='qemu-dos',
                steps=[dict(op=name,**options)]),timeout_ms=60000)
            assert report['ok'] and report['completed_steps'] == 1, report
            return report['steps'][0]['result']
        try:
            before = debug.registers()['registers'],debug.clock_observe()['virtual_ns']
            made = invoke('frame-inputs',edges=MAKE,timeout_ms=5000)
            assert made['held'] == ['a','shift'] and made['native']['accepted-edges'] == 2
            assert (debug.registers()['registers'],debug.clock_observe()['virtual_ns']) == before
            assert debug.advance_frames(frames=2,timeout_ms=60000)['completed_frames'] == 2
            released = invoke('frame-inputs',edges=BREAK,timeout_ms=5000)
            assert released['held'] == [] and released['native']['accepted-edges'] == 4
        finally:
            workspace.sessions.clear()


@pytest.mark.parametrize('new_hold',[False,True])
def test_native_failed_script_preserves_entry_holds_or_closes_new_hold(tmp_path,new_hold):
    from fdisbull.debug_script import execute_script
    from test_qemu_memory_rules_native import _case
    with _case(tmp_path) as (project,debug,_,_,_,_):
        if not new_hold:
            debug.frame_inputs([dict(key='shift',pressed=True)])
        steps = [dict(op='frame-inputs',edges=MAKE if new_hold else []),
                 dict(op='assert',value=1,equals=2)]
        report = execute_script(debug,dict(format='fdisbull-script-1',backend='qemu-dos',steps=steps),timeout_ms=60000)
        assert not report['ok']
        if new_hold:
            assert debug.closed and report['input_cleanup']['closed'] is True
        else:
            assert not debug.closed and debug.keyboard_state()['keyboard']['frame_keys'] == ['shift']
            assert report['input_cleanup'] is None


def test_native_held_keys_preserve_task_private_irq_checkpoint(tmp_path):
    from support.qemu_dos_irq_fixture import ANCHOR, MONITOR_UUID, irq_fixture
    from test_qemu_dos_irq_preemption_native import _hit, _number
    from test_qemu_dos_history_native import _state, _assert_state
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE']); boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot,tmp_path / 'baseline.img',runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n'+BASELINE_CONFIG)
    data, marker = irq_fixture(tmp_path,runtime['NASM'],fpu=True)
    source = tmp_path / 'IRQ.COM'; source.write_bytes(data)
    with Project.create(tmp_path / 'irq-keys.fdb',source,image='com') as project:
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
            scratch,fetch = base + marker['scratch'],base + marker['irq_fetch']
            for task,ram_hex,code_hex in ((a,'3412','f8'),(b,'7856','f9')):
                ram = debug.dos_task_layer_patch('keys-ram-'+task[-8:],scratch,expected_hex='0000',
                    data_hex=ram_hex,kind='ram',task=task,activate=False)['layer']
                code = debug.dos_task_layer_patch('keys-code-'+task[-8:],fetch,expected_hex='90',
                    data_hex=code_hex,kind='execute',task=task,activate=False)['layer']
                debug.dos_task_layers([ram,code],task=task)
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
            control = dict(a=a,b=b,hook_a=hook_a,hook_b=hook_b,scratch=scratch,fetch=fetch,
                irq_count=base + marker['irq_count'],return_ip=base + marker['return_ip'])
            debug.timeline_start(period_ns=20_000_000,timeout_ms=60000)
            native = debug.frame_inputs(MAKE)['native']
            proof = _proof(native)
            # Capture the actual post-make PIC state: IRQ1 may be pending in IRR
            # even though it is masked and the guest has not consumed the bytes.
            saved = _state(debug,control,task=a,cookie=0xa1,count=2)
            assert saved['preemption']['pic-mask'] & 2  # IRQ1 masked; no consumption claim.
            checkpoint = debug.save_state()['artifact']
            old = debug.vm.process
            debug.load_state(checkpoint,timeout_ms=60000)
            assert old.poll() is not None
            after = debug.keyboard_state()['keyboard']['native']
            assert after['epoch'] != native['epoch'] and after['token'] != native['token']
            assert _proof(after) == proof
            _assert_state(debug,control,saved,task=a,cookie=0xa1,count=2)
            _hit(debug,hook_b,2,0xb22b,0x2222,1,True)
    assert source.read_bytes() == data and digest(boot) == boot_hash


def test_native_frame_input_hook_stop_preserves_owned_keys_without_replay(tmp_path):
    from test_qemu_dos_frames_native import _source
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    disk = prepare_dos_baseline(boot,tmp_path / 'baseline.img',runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n'+BASELINE_CONFIG)
    data, marker = _source(tmp_path,runtime['NASM'])
    source = tmp_path / 'FRAME.COM'; source.write_bytes(data)
    with Project.create(tmp_path / 'early-input.fdb',source,image='com') as project:
        with _launch(project,runtime,tmp_path,disk,clock_profile='virtual') as debug:
            base = debug.dos_process_info()['source_mapping']['runtime_base']
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            registers = debug.registers()['registers']
            name = 'rbx' if 'rbx' in registers else 'ebx'
            value = int(registers[name],16)
            hook = debug.hook(hex(project.regions(1)[0].start + marker['interrupt']),space='source',
                once=False,max_hits=3,actions=[dict(op='registers',registers={
                    name:dict(expected=value,value=value)})])['hook']
            root = debug.timeline_start(period_ns=100_000_000,timeout_ms=60000)
            result = debug.timeline_advance(frames=1,inputs=[dict(frame=0,edges=MAKE)],timeout_ms=60000)
            assert result['completed_frames'] == 0 and result['stop']['outcome'] == 'hook'
            assert result['stop']['hook_hits'][0]['hook'] == hook and result['stop']['hook_hits'][0]['hit'] == 1
            state = debug.keyboard_state()['keyboard']['native']
            assert state['accepted-edges'] == 2 and sorted(state['held']) == ['a','shift']
            assert result['valid'] is False and result['point'] is None
            assert root['point'] in {node['id'] for node in result['nodes']}
            assert debug.keyboard_state()['keyboard']['native']['accepted-edges'] == 2
            with pytest.raises(ValueError,match='dirty|cursor'):
                debug.timeline_pin('no-pending-input.qcow2')
            assert debug.vm.process.poll() is None


def test_native_failed_script_closes_when_restore_introduces_held_keys(tmp_path):
    from fdisbull.debug_script import execute_script
    from test_qemu_memory_rules_native import _case
    with _case(tmp_path) as (project,debug,_,_,_,_):
        debug.frame_inputs(MAKE)
        root = debug.timeline_start(period_ns=20_000_000,timeout_ms=60000)
        assert debug.advance_frames(frames=3,timeout_ms=60000)['completed_frames'] == 3
        debug.frame_inputs(BREAK)
        assert debug.advance_frames(frames=3,timeout_ms=60000)['completed_frames'] == 3
        assert debug.keyboard_state()['keyboard']['frame_keys'] == []
        report = execute_script(debug,dict(format='fdisbull-script-1',backend='qemu-dos',steps=[
            dict(op='timeline-rewind',timeline=root['timeline'],point=root['point']),
            dict(op='assert',value=1,equals=2)]),timeout_ms=60000)
        assert not report['ok'] and report['completed_steps'] == 1
        assert debug.closed and report['input_cleanup']['closed'] is True


def test_native_legacy_release_after_detach_then_frame_owner_reinitializes(tmp_path):
    from test_qemu_memory_rules_native import _case
    with _case(tmp_path) as (project,debug,_,_,_,_):
        debug.timeline_start(period_ns=20_000_000,timeout_ms=60000)
        original = debug.frame_inputs([dict(key='a',pressed=True)])['native']
        assert debug.advance_frames(frames=2,timeout_ms=60000)['completed_frames'] == 2
        released = debug.frame_inputs([dict(key='a',pressed=False)])['native']
        assert debug.advance_frames(frames=2,timeout_ms=60000)['completed_frames'] == 2
        assert released['active'] and released['held'] == []
        highwater, old_token = released['generation'], original['token']
        assert highwater > 0
        lease = debug.keyboard_key_down('b')['lease']
        detached = debug.keyboard_state()['keyboard']['native']
        assert not detached['active'] and detached['held'] == []
        assert debug.run(timeout_ms=1000)['outcome'] == 'timeout'
        physical_down = debug.keyboard_state()['keyboard']['native']
        assert 'b' in physical_down['foreign-held']
        debug.keyboard_key_up(lease)
        assert debug.run(timeout_ms=1000)['outcome'] == 'timeout'
        physical_up = debug.keyboard_state()['keyboard']['native']
        assert physical_up['foreign-held'] == [] and not physical_up['active']
        assert not debug.input_state()['leases'] and not debug.input_state()['pending']
        fresh = debug.frame_inputs([dict(key='c',pressed=True)])['native']
        assert fresh['active'] and fresh['held'] == ['c']
        assert fresh['generation'] > highwater and fresh['token'] != old_token
        assert debug.advance_frames(frames=2,timeout_ms=60000)['completed_frames'] == 2
        assert debug.frame_inputs([dict(key='c',pressed=False)])['held'] == []
        assert debug.advance_frames(frames=2,timeout_ms=60000)['completed_frames'] == 2
        assert debug.keyboard_state()['keyboard']['frame_keys'] == []


def test_native_foreign_running_input_invalidates_frame_owner(tmp_path):
    """A single real QMP input event must not join an active frame owner."""
    import time
    from fdisbull.dosbox_rpc import DebuggerError
    from test_qemu_memory_rules_native import _case

    with _case(tmp_path) as (project,debug,_,_,_,_):
        owned = debug.frame_inputs([dict(key='shift',pressed=True)])['native']
        qmp = debug.vm.qmp
        event = dict(type='key',data=dict(key=dict(type='qcode',data='b'),down=True))
        remote = debug.vm.debugger()
        original_execute = remote.execute
        delivered = []
        def execute_with_foreign_input(command, timeout_ms, *, after_send=None):
            def inject(deadline):
                if after_send is not None:
                    after_send(deadline)
                deadline = min(deadline,time.monotonic() + 5)
                while time.monotonic() < deadline:
                    if qmp.call('query-status',timeout_ms=1000)['running']:
                        break
                    time.sleep(.005)
                else:
                    raise AssertionError('Did not observe QEMU running before native clock stop')
                # Exactly one unowned event; acknowledgment does not prove consumption.
                qmp.call('input-send-event',{'events':[event]},timeout_ms=1000)
                delivered.append(True)
            return original_execute(command,timeout_ms,after_send=inject)
        remote.execute = execute_with_foreign_input
        try:
            result = debug.clock_advance(5_000_000_000,timeout_ms=50000)
        finally:
            remote.execute = original_execute
        assert delivered == [True]
        assert result['clock_budget']['deadline_reached'] is True
        invalid = qmp.call('x-fdisbull-query-frame-keys')
        assert invalid['active'] and not invalid['valid']
        assert invalid['token'] == owned['token'] and invalid['generation'] == owned['generation']
        assert invalid['held'] == owned['held'] and invalid['accepted-edges'] == owned['accepted-edges']
        before_state_rows = project.db.execute(
            "SELECT id FROM debug_artifacts WHERE kind='state' ORDER BY rowid").fetchall()
        with pytest.raises(DebuggerError):
            qmp.call('x-fdisbull-instrumented-checkpoint-export')
        with pytest.raises(DebuggerError):
            qmp.call('x-fdisbull-apply-frame-key-edges',{'token':owned['token'],
                'expected-generation':owned['generation'],'edges':[dict(key='a',pressed=True)]})
        after = qmp.call('x-fdisbull-query-frame-keys')
        assert after['active'] and not after['valid'] and after['token'] == owned['token']
        assert after['generation'] == owned['generation'] and after['held'] == owned['held']
        assert project.db.execute("SELECT id FROM debug_artifacts WHERE kind='state' ORDER BY rowid").fetchall() == before_state_rows
