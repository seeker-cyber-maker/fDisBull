"""Real QEMU renderer-publication timeline; never a completed guest frame."""
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

from PIL import Image
import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, assemble, digest, prepare_dos_baseline
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch


_SOURCE = r'''
bits 16
org 100h
    jmp start
    db 'FTL1'
    dw ready-$$, counter-$$, loop_start-$$, interrupt_site-$$
counter: dw 0
start:
    push cs
    pop ds
    mov ax,13h
    int 10h
    mov dx,3c8h
    xor al,al
    out dx,al
    inc dx
    xor bx,bx
palette:
    mov al,bl
    and al,63
    out dx,al
    xor al,al
    out dx,al
    out dx,al
    inc bl
    jnz palette
    mov ax,0a000h
    mov es,ax
    cld
ready:
    nop
loop_start:
    inc word [cs:counter]
    mov ax,[cs:counter]
    or al,1
    xor di,di
    mov cx,0fa00h
    rep stosb
interrupt_site:
    nop
    jmp loop_start
'''


def _source(tmp_path, nasm):
    data = assemble(tmp_path, 'renderer-timeline', _SOURCE, nasm)
    offset = data.index(b'FTL1')
    marker = dict(zip(('ready', 'counter', 'loop', 'interrupt'), struct.unpack_from('<4H', data, offset+4)))
    return data, marker


def _image(project, receipt):
    identifier = receipt['artifact']
    row = project.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?', (identifier,)).fetchone()
    raw = bytes(row['data'])
    assert hashlib.sha256(raw).hexdigest() == row['sha256']
    with Image.open(io.BytesIO(raw)) as image:
        assert image.width > 0 and image.height > 0
        pixels = image.convert('RGB').tobytes()
    return hashlib.sha256(pixels).hexdigest(), row['sha256']


def _counter(debug, address):
    return int.from_bytes(bytes.fromhex(debug.memory(address, length=2)['hex']), 'little')


def _assert_mode13_pixels(project, debug, receipt, frame):
    row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                             (receipt['artifact'],)).fetchone()
    with Image.open(io.BytesIO(bytes(row['data']))) as stored:
        rgb = stored.convert('RGB')
        assert rgb.width % 320 == 0 and rgb.height % 200 == 0
        sx, sy = rgb.width // 320, rgb.height // 200
        assert sx >= 1 and sy >= 1
        assert hashlib.sha256(rgb.tobytes()).hexdigest() == frame['pixel_sha256']
        # QEMU VGA c6_to_8 in hw/display/vga_int.h expands v to
        # (v << 2) | ((v & 1) * 3). The authored DAC makes G=B=0.
        vram = bytes.fromhex(debug.memory(0xa0000, length=64000, space='physical')['hex'])
        assert len(vram) == 64000
        samples = [(0,0), (10,10), (79,27), (160,100), (250,160), (319,199)]
        reds = []
        for x,y in samples:
            palette_value = vram[y * 320 + x] & 63
            expected_red = (palette_value << 2) | ((palette_value & 1) * 3)
            pixel = rgb.getpixel((x * sx, y * sy))
            assert pixel == (expected_red,0,0), (x,y,pixel,expected_red)
            reds.append(expected_red)
        assert any(reds), 'Authored guest has not produced nonblack pixels'


def _cold(control):
    runtime = _inputs()
    with Project(control['db']) as project:
        with _launch(project, runtime, control['dir'], {'image':control['disk']}, clock_profile='virtual') as debug:
            fresh = debug.vm.process
            before_epoch = debug.dos_process_info()['capture_epoch']
            restored = debug.timeline_rewind(timeline=control['timeline'], point=control['point'], timeout_ms=60000)
            assert fresh.poll() is not None and debug.dos_process_info()['capture_epoch'] != before_epoch
            assert debug.registers()['registers'] == control['registers']
            assert debug.clock_observe()['virtual_ns'] == control['clock_ns']
            image = debug.timeline_image('cold.png', timeline=control['timeline'], point=control['point'])
            assert _image(project, image) == tuple(control['image'])
            next_frame = debug.timeline_advance(frames=1, timeout_ms=60000)
            assert next_frame['completed_frames'] == 1
    return {'passed':True}


def test_native_renderer_timeline_record_branch_and_cold_restore(tmp_path):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    original_boot = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    data, marker = _source(tmp_path, runtime['NASM'])
    source = tmp_path / 'FRAME.COM'; source.write_bytes(data)
    original_source = hashlib.sha256(data).hexdigest()
    db = tmp_path / 'frames.fdb'
    with Project.create(db, source, image='com') as project:
        with _launch(project, runtime, tmp_path, disk, clock_profile='virtual') as debug:
            base = debug.dos_process_info()['source_mapping']['runtime_base']
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            root = debug.timeline_start(period_ns=20_000_000, timeout_ms=60000)
            first = debug.timeline_advance(frames=1, timeout_ms=60000)
            assert first['completed_frames'] == 1
            assert first['unit'] == 'completed synchronous renderer update'
            assert first['completed_guest_frame'] is None
            frame1 = first['point']
            image1 = debug.timeline_image('frame1.png', point=frame1)
            first_image = _image(project, image1)
            first_frame = next(node['frame'] for node in first['nodes'] if node['id'] == frame1)
            _assert_mode13_pixels(project, debug, image1, first_frame)
            clock1, regs1 = debug.clock_observe()['virtual_ns'], debug.registers()['registers']
            count1 = _counter(debug, base + marker['counter'])
            second = debug.timeline_advance(frames=1, timeout_ms=60000)
            assert second['completed_frames'] == 1
            frame2 = second['point']
            old = debug.timeline_image('frame2.png', point=frame2)
            old_image = _image(project, old)
            second_frame = next(node['frame'] for node in second['nodes'] if node['id'] == frame2)
            _assert_mode13_pixels(project, debug, old, second_frame)
            assert _counter(debug, base + marker['counter']) > count1
            previous = debug.vm.process
            debug.timeline_rewind(frames=1, timeout_ms=60000)
            assert previous.poll() is not None
            assert debug.clock_observe()['virtual_ns'] == clock1
            assert debug.registers()['registers'] == regs1
            branch = debug.timeline_advance(frames=1, timeout_ms=60000)
            assert branch['completed_frames'] == 1
            assert branch['point'] not in (frame1, frame2)
            status = debug.timeline_status()
            nodes = {node['id']:node for node in status['nodes']}
            assert {frame1, frame2, branch['point']} <= set(nodes)
            assert nodes[frame2]['parent'] == nodes[branch['point']]['parent'] == frame1
            first_update = nodes[frame1]['frame']
            second_update = nodes[frame2]['frame']
            assert first_update['kind'] == second_update['kind'] == 'renderer-update'
            assert second_update['update_id'] == first_update['update_id'] + 1
            assert second_update['published_ns'] > first_update['published_ns']
            assert _image(project, debug.timeline_image('old-frame2.png', point=frame2)) == old_image
            control = dict(db=str(db), dir=str(tmp_path), disk=str(disk['image']),
                timeline=status['timeline'], point=frame1, registers=regs1, clock_ns=clock1, image=first_image,
                old_image_artifact=old['artifact'], old_image_sha=old_image[1])
            debug.timeline_stop()
        assert debug.vm.process.poll() is not None
    with Project(db) as offline:
        exported = tmp_path / 'offline-frame2.png'
        offline.debug_export(control['old_image_artifact'], exported)
        assert hashlib.sha256(exported.read_bytes()).hexdigest() == control['old_image_sha']
    path = tmp_path / 'frame-control.json'; path.write_text(json.dumps(control))
    child = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(path)],
        capture_output=True, text=True, env=os.environ.copy(), timeout=240)
    assert child.returncode == 0, child.stderr[-6000:]
    assert json.loads(child.stdout)['passed'] is True
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_source
    assert digest(boot) == original_boot


if __name__ == '__main__':
    print(json.dumps(_cold(json.loads(Path(sys.argv[1]).read_text()))))


@pytest.mark.parametrize('kind', ['breakpoint', 'hook'])
def test_native_timeline_interrupt_before_renderer_fence_never_creates_node(tmp_path, kind):
    runtime = _inputs()
    disk = prepare_dos_baseline(Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE']), tmp_path / 'baseline.img',
        runtime['FDISBULL_QEMU_DOS_MCOPY'], config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    data, marker = _source(tmp_path, runtime['NASM'])
    source = tmp_path / 'FRAME.COM'; source.write_bytes(data)
    with Project.create(tmp_path / 'interrupt.fdb', source, image='com') as project:
        with _launch(project, runtime, tmp_path, disk, clock_profile='virtual') as debug:
            base = debug.dos_process_info()['source_mapping']['runtime_base']
            ready = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(ready['breakpoint_id'])
            if kind == 'breakpoint':
                trap = debug.breakpoint(base + marker['interrupt'])['breakpoint_id']
            else:
                registers = debug.registers()['registers']
                register = 'rbx' if 'rbx' in registers else 'ebx'
                value = int(registers[register], 16)
                trap = debug.hook(hex(project.regions(1)[0].start + marker['interrupt']),
                    space='source', once=False, max_hits=3,
                    actions=[dict(op='registers', registers={register:dict(expected=value, value=value)})])['hook']
            root = debug.timeline_start(period_ns=100_000_000, timeout_ms=60000)
            before = debug.timeline_status()
            result = debug.timeline_advance(frames=1, timeout_ms=60000)
            assert result['completed_frames'] == 0
            assert result['stop']['outcome'] == kind
            after = debug.timeline_status()
            assert after['point'] is None and after['valid'] is False
            assert after['head'] == before['head']
            assert after['nodes'] == before['nodes']
            assert before['point'] in {node['id'] for node in after['nodes']}
            assert debug.vm.qmp.call('query-status')['running'] is False
            if kind == 'hook':
                assert result['stop']['hook_hits'][0]['hook'] == trap
                assert result['stop']['hook_hits'][0]['hit'] == 1
                debug.delete_hook(trap)
            else:
                debug.delete_breakpoint(trap)


def test_native_timeline_refuses_held_input_without_execution(tmp_path):
    from test_qemu_memory_rules_native import _case
    with _case(tmp_path) as (project, debug, marker, base, _, _):
        root = debug.timeline_start(period_ns=20_000_000, timeout_ms=60000)
        debug.keyboard_key_down('shift')
        before = debug.registers()['registers'], debug.input_state(), debug.timeline_status()
        with pytest.raises(ValueError, match='input|released|held|cursor'):
            debug.timeline_advance(frames=1, timeout_ms=60000)
        assert (debug.registers()['registers'], debug.input_state(), debug.timeline_status()) == before
        assert not debug.closed and debug.vm.process.poll() is None


def test_native_renderer_timeline_rewind_preserves_private_irq_state(tmp_path):
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
            saved = _state(debug,control,task=a,cookie=0xa1,count=2)
            root = debug.timeline_start(period_ns=1_000_000,timeout_ms=60000)
            root_point = root['point']
            frame = debug.timeline_advance(frames=1,timeout_ms=60000)
            assert frame['completed_frames'] == 1 and frame['completed_guest_frame'] is None
            previous = debug.vm.process
            restored = debug.timeline_rewind(frames=1,timeout_ms=60000)
            assert previous.poll() is not None and restored['point'] == root_point
            _assert_state(debug,control,saved,task=a,cookie=0xa1,count=2)
            _hit(debug,hook_b,2,0xb22b,0x2222,1,True)
    assert source.read_bytes() == data and digest(boot) == original_boot


@pytest.mark.parametrize('route', ['python','json','script'])
def test_native_renderer_timeline_routes(tmp_path,route):
    from fdisbull.cli import respond
    from fdisbull.debug_script import execute_script
    from fdisbull.debugger import DebugWorkspace
    from test_qemu_memory_rules_native import _case

    with _case(tmp_path) as (project,debug,_,_,_,_):
        workspace = DebugWorkspace(); workspace.sessions[debug.run_id] = debug
        def invoke(name,**kwargs):
            if route == 'python': return getattr(debug,name.replace('-','_'))(**kwargs)
            if route == 'json':
                result = respond(dict(method='debug-' + name,params=dict(project=str(project.path),
                    run=debug.run_id,context='machine',**kwargs)),debugger=workspace)
                assert result['ok'], result
                return result['result']
            result = execute_script(debug,dict(format='fdisbull-script-1',backend='qemu-dos',
                steps=[dict(op=name,**kwargs)]),timeout_ms=60000)
            assert result['ok'] and result['completed_steps'] == 1, result
            return result['steps'][0]['result']
        try:
            root = invoke('timeline-start',period_ns=20_000_000,timeout_ms=60000)
            frame = invoke('timeline-advance',frames=1,timeout_ms=60000)
            assert frame['completed_frames'] == 1 and frame['completed_guest_frame'] is None
            assert frame['point'] != root['point']
            old = debug.vm.process
            restored = invoke('timeline-rewind',frames=1,timeout_ms=60000)
            assert old.poll() is not None and restored['point'] == root['point']
        finally:
            workspace.sessions.clear()


def test_native_armed_frame_fence_blocks_clock_and_checkpoint_until_cancelled(tmp_path):
    import uuid
    from fdisbull.dosbox_rpc import DebuggerError
    from test_qemu_memory_rules_native import _case

    with _case(tmp_path) as (project,debug,_,_,_,_):
        debug.timeline_start(period_ns=20_000_000,timeout_ms=60000)
        display = debug.display_observe()
        before_clock = debug.clock_observe()
        before_registers = debug.registers()['registers']
        before_state_rows = project.db.execute(
            "SELECT id FROM debug_artifacts WHERE kind='state' ORDER BY rowid").fetchall()
        fence_token, clock_token = uuid.uuid4().hex, uuid.uuid4().hex
        assert fence_token != clock_token
        qmp = debug.vm.qmp
        armed = qmp.call('x-fdisbull-arm-display-frame',
            {'token':fence_token,'display-token':display['window']})
        assert armed['state'] == 'armed' and armed['token'] == fence_token
        assert armed['baseline-update-id'] == display['updates']
        with pytest.raises(DebuggerError,match='fence'):
            qmp.call('x-fdisbull-arm-clock-budget',{'token':clock_token,'delta-ns':1_000_000})
        with pytest.raises(DebuggerError,match='fence'):
            qmp.call('x-fdisbull-instrumented-checkpoint-export')
        assert project.db.execute("SELECT id FROM debug_artifacts WHERE kind='state' ORDER BY rowid").fetchall() == before_state_rows
        assert not debug.closed and debug.vm.process.poll() is None
        cancelled = qmp.call('x-fdisbull-cancel-display-frame',{'token':fence_token})
        repeated = qmp.call('x-fdisbull-cancel-display-frame',{'token':fence_token})
        observed = qmp.call('x-fdisbull-query-display-frame',{'token':fence_token})
        assert cancelled == repeated == observed
        assert cancelled['state'] == 'cancelled' and cancelled['updates'] == display['updates']
        assert not cancelled['stop-pending'] and not cancelled['stop-consumed']
        assert 'completed-update-id' not in cancelled and 'published-ns' not in cancelled
        assert debug.registers()['registers'] == before_registers
        after_clock = debug.clock_observe()
        assert (after_clock['virtual_ns'],after_clock['epoch']) == (before_clock['virtual_ns'],before_clock['epoch'])
        assert debug.display_observe()['updates'] == display['updates']
        normal = debug.timeline_advance(frames=1,timeout_ms=60000)
        assert normal['completed_frames'] == 1 and normal['completed_guest_frame'] is None
