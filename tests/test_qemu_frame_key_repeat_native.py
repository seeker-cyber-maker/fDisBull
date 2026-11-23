"""Authored IRQ1 and VGA witnesses for native PS/2 typematic checkpoints.

FDISBULL_QEMU_KEY_REPEAT selects an exact privately prepared QEMU producer.
FDISBULL_REQUIRE_QEMU_KEY_REPEAT=1 makes missing inputs a test failure.
FDISBULL_REQUIRE_QEMU_DOSBOX_TYPEMATIC=1 also runs the opt-in DOSBox profile.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

import pytest

from fdisbull.project import Project
from fdisbull.qemu_video_checkpoint import LATCH_MODEL, LATCH_PROFILE
from support.dos_process_fixture import BASELINE_CONFIG, assemble, digest, prepare_dos_baseline
from test_qemu_clock_budget_native import park
from test_qemu_dos_modes_checkpoint_native import _launch
from test_qemu_frame_keys_native import _proof


QUERY = 'x-fdisbull-query-frame-key-repeat'
MILLISECOND = 1_000_000
MAKE = 0x1e
BREAK = 0x9e

# F6 sets the defaults; optionally send F3 plus a selected typematic byte.
# The test records the actual keyboard ACKs before installing the raw IRQ1
# handler. There is no controller polling or BIOS keyboard synthesis afterward.
KEYBOARD = r"""
bits 16
org 100h
    push cs
    pop ds
    mov ax,13h
    int 10h
%if TIMED_PAGE_FLIP
    call setup_pages
%endif
    cli
    xor ax,ax
    mov es,ax
    mov cx,32
drain:
    in al,64h
    test al,1
    jz drained
    in al,60h
    loop drain
    jmp setup_failed
drained:
    mov bl,0f6h
    call command
    jc setup_failed
%if PROGRAM_RATE
    mov bl,0f3h
    call command
    jc setup_failed
    mov bl,27h
    call command
    jc setup_failed
%endif
    mov word [es:9*4],keyboard_irq
    mov [es:9*4+2],cs
    in al,21h
    and al,0fdh
    out 21h,al
    mov byte [ready_flag],1
    sti
ready:
%if BUSY_LOOP
    nop
%else
    hlt
%endif
    jmp ready
setup_failed:
    mov byte [ready_flag],0ffh
    jmp ready

command:
    mov cx,0ffffh
.wait_write:
    in al,64h
    test al,2
    jz .write
    loop .wait_write
    stc
    ret
.write:
    mov al,bl
    out 60h,al
    mov cx,0ffffh
.wait_read:
    in al,64h
    test al,1
    jnz .read
    loop .wait_read
    stc
    ret
.read:
    test al,20h
    jnz .failed
    in al,60h
    mov bx,[ack_count]
    mov [acks+bx],al
    inc word [ack_count]
    cmp al,0fah
    jne .failed
    clc
    ret
.failed:
    stc
    ret

keyboard_irq:
    push ax
    push bx
    push ds
%if TIMED_PAGE_FLIP
    push dx
%endif
    push cs
    pop ds
    in al,64h
    and al,21h
    cmp al,1
    jne .eoi
    in al,60h
    mov bx,[scan_count]
    cmp bx,64
    jae .full
    mov [scans+bx],al
%if TIMED_PAGE_FLIP
    cmp al,1eh
    jne .full
    mov ax,800ch
    test bl,1
    jz .show_page
    mov ah,40h
.show_page:
    mov dx,3d4h
    out dx,ax
%endif
.full:
    inc word [scan_count]
.eoi:
    mov al,20h
    out 20h,al
%if TIMED_PAGE_FLIP
    pop dx
%endif
    pop ds
    pop bx
    pop ax
    iret
%if TIMED_PAGE_FLIP
setup_pages:
    push es
    mov dx,3c4h
    mov ax,0604h
    out dx,ax
    mov ax,0f02h
    out dx,ax
    mov dx,3d4h
    mov ax,0014h
    out dx,ax
    mov ax,0e317h
    out dx,ax
    mov ax,2813h
    out dx,ax
    mov ax,400ch
    out dx,ax
    mov ax,000dh
    out dx,ax
    mov dx,3c8h
    mov al,1
    out dx,al
    inc dx
    mov al,63
    out dx,al
    xor al,al
    out dx,al
    out dx,al
    out dx,al
    mov al,63
    out dx,al
    xor al,al
    out dx,al
    mov ax,0a000h
    mov es,ax
    cld
    mov ax,0101h
    mov di,4000h
    mov cx,8000
    rep stosw
    mov ax,0202h
    mov di,8000h
    mov cx,8000
    rep stosw
    pop es
    ret
%endif
ready_flag: db 0
ack_count: dw 0
acks: times 3 db 0
scan_count: dw 0
scans: times 64 db 0
    db 'TYPEMATIC-SYMBOLS'
    dw ready,ready_flag,ack_count,acks,scan_count,scans
"""


def _runtime():
    selected = os.environ.get('FDISBULL_QEMU_KEY_REPEAT')
    required = os.environ.get('FDISBULL_REQUIRE_QEMU_KEY_REPEAT') == '1'
    if not selected:
        if required:
            pytest.fail('Missing FDISBULL_QEMU_KEY_REPEAT')
        pytest.skip('Provide a native QEMU typematic producer')
    runtime = {name: os.environ.get(name) for name in (
        'FDISBULL_QEMU_DOS_BOOT_IMAGE', 'FDISBULL_QEMU_DOS_MCOPY',
        'FDISBULL_QEMU_DOS_FIRMWARE', 'FDISBULL_QEMU_IMG')}
    runtime.update(FDISBULL_QEMU_LAYERS=selected, NASM=os.environ.get('NASM') or shutil.which('nasm'))
    missing = [name for name, value in runtime.items() if value is None]
    if missing:
        pytest.fail('Missing native typematic inputs: ' + ', '.join(missing))
    return runtime


def _input(directory, runtime, programmed, *, busy=False, timed_page_flip=False):
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    disk = prepare_dos_baseline(boot, directory/'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n'+BASELINE_CONFIG)
    defines = (f'%define PROGRAM_RATE {int(programmed)}\n%define BUSY_LOOP {int(busy)}\n'
               f'%define TIMED_PAGE_FLIP {int(timed_page_flip)}\n')
    code = assemble(directory, 'typematic', defines+KEYBOARD, runtime['NASM'])
    offsets = struct.unpack_from('<6H', code, code.index(b'TYPEMATIC-SYMBOLS')+len(b'TYPEMATIC-SYMBOLS'))
    target = directory/'REPEAT.COM'
    target.write_bytes(code)
    return disk, target, code, offsets


def _symbols(debug, offsets):
    base = debug.dos_process_info()['source_mapping']['runtime_base']
    names = ('ready', 'ready_flag', 'ack_count', 'acks', 'scan_count', 'scans')
    return dict(zip(names, (base+offset-0x100 for offset in offsets)))


def _bytes(debug, address, count):
    return bytes.fromhex(debug.memory(address, length=count, space='physical')['hex'])


def _count(debug, address):
    return int.from_bytes(_bytes(debug, address, 2), 'little')


def _ready(debug, offsets, programmed):
    symbols = _symbols(debug, offsets)
    park(debug, symbols['ready'])
    assert _bytes(debug, symbols['ready_flag'], 1) == b'\x01'
    count = 3 if programmed else 1
    assert _count(debug, symbols['ack_count']) == count
    assert _bytes(debug, symbols['acks'], count) == b'\xfa'*count
    return symbols


def _scans(debug, symbols):
    count = _count(debug, symbols['scan_count'])
    assert count <= 64
    return list(_bytes(debug, symbols['scans'], count)) if count else []


def _repeat(debug):
    return debug.vm.qmp.call(QUERY)


def _keys(debug):
    keyboard = debug.keyboard_state()['keyboard']
    state = keyboard['native']
    assert state['repeat-supported'] is True and state['held'] == keyboard['frame_keys']
    return state


def _advance(debug, target):
    now = debug.clock_observe()['virtual_ns']
    assert target > now
    result = debug.clock_advance(target-now, timeout_ms=15000)
    budget = result['clock_budget']
    assert budget['deadline_ns'] == target and budget['deadline_reached'], result
    assert target <= budget['stopped_ns'] < target+2*MILLISECOND, budget
    return budget['stopped_ns']


def _edges(debug, *entries):
    return debug.frame_inputs([dict(key=key, pressed=pressed) for key, pressed in entries])['native']


def _selected_page(debug, origin, color):
    expected = sha256(color * (320 * 200)).hexdigest()
    for _ in range(2):
        assert debug.video_frame_advance(timeout_ms=15000)['advance_completed']
        native = debug.video_frame_observe()['native']
        assert native['model'] == LATCH_MODEL
        frame = native['frame']
        if frame['page-latch']['origin-bytes'] == origin:
            assert len(frame['rows']) == 200 and frame['pixel-sha256'] == expected
            return {key: frame[key] for key in ('frame-id', 'page-latch', 'pixel-sha256')}
    pytest.fail(f'VGA page {origin:#x} did not latch within two completed frames')


def _capture_future(debug, symbols, saved, accepted, *, timed_page_flip=False):
    # Exercise the normal source-raster timeline route as well as raw IRQ1.
    # The middle-of-phase root has more than one frame before its due key.
    next_raster = debug.timeline_advance(frames=1, timeout_ms=15000)
    assert next_raster['completed_frames'] == 1 and next_raster['frame_source'] == 'source-raster'
    raster = next_raster['frames'][0]['frame']['source_raster']
    assert _scans(debug, symbols) == [MAKE, MAKE]
    expected_deadline = saved['deadline-ns']
    interval = saved['interval-ns']
    _advance(debug, expected_deadline-5*MILLISECOND)
    assert _scans(debug, symbols) == [MAKE, MAKE]
    _advance(debug, expected_deadline+3*MILLISECOND)
    assert _scans(debug, symbols) == [MAKE]*3
    assert _repeat(debug)['deadline-ns'] == expected_deadline+interval
    latched = []
    if timed_page_flip:
        latched.append(_selected_page(debug, 0x20000, b'\0\xff\0'))
    _advance(debug, expected_deadline+interval+3*MILLISECOND)
    assert _scans(debug, symbols) == [MAKE]*4
    if timed_page_flip:
        latched.append(_selected_page(debug, 0x10000, b'\xff\0\0'))
    next_deadline = expected_deadline+2*interval
    assert _repeat(debug)['deadline-ns'] == next_deadline
    assert _keys(debug)['accepted-edges'] == accepted
    assert _edges(debug, ('a', False))['accepted-edges'] == accepted+1
    idle = dict(saved)
    del idle['key']
    idle['deadline-ns'] = -1
    assert _repeat(debug) == idle
    stopped = _advance(debug, next_deadline+2*interval)
    assert _scans(debug, symbols) == [MAKE]*4+[BREAK]
    return dict(raster={key:raster[key] for key in ('frame_id','pixel_sha256','logical_sha256')},
                latched=latched,
                scans=_scans(debug,symbols),stopped_ns=stopped)


def _restore(debug, control):
    previous = debug.vm.process
    rewound = debug.timeline_rewind(timeline=control['timeline'],point=control['point'],timeout_ms=30000)
    assert previous.poll() == 0
    readback = rewound['restore']['frame_readback']
    assert readback['historical'] == control['raster']
    assert readback['live']['stream'] != readback['historical']['stream']
    assert readback['live']['epoch'] != readback['historical']['epoch']
    assert readback['live']['logical_sha256'] == readback['historical']['logical_sha256']
    after = _keys(debug)
    assert after['epoch'] != control['epoch'] and after['token'] != control['token']
    assert after['held'] == ['a'] and after['accepted-edges'] == control['accepted']
    assert _repeat(debug) == control['repeat']
    assert debug.keyboard_state()['keyboard']['frame_key_repeat'] == control['repeat']
    assert debug.clock_observe()['virtual_ns'] == control['saved_ns']
    assert _scans(debug, control['symbols']) == [MAKE, MAKE]
    return previous


def test_native_typematic_default_and_latest_owned_key(tmp_path):
    runtime = _runtime()
    disk,target,code,offsets = _input(tmp_path,runtime,programmed=False)
    default = dict(parameter=0x2b, **{'delay-ns':500*MILLISECOND,'interval-ns':91_666_666,'deadline-ns':-1})
    with Project.create(tmp_path/'repeat.fdb',target,image='com') as project:
        with _launch(project,runtime,tmp_path,disk,clock_profile='virtual') as debug:
            symbols = _ready(debug,offsets,programmed=False)
            assert _repeat(debug) == default and _keys(debug)['held'] == []
            start = debug.clock_observe()['virtual_ns']
            _edges(debug, ('shift', True))
            assert _repeat(debug) == default
            _advance(debug, start+510*MILLISECOND)
            assert _scans(debug, symbols) == [0x2a]

            start = debug.clock_observe()['virtual_ns']
            held = _edges(debug, ('a', True))
            first = start+500*MILLISECOND
            assert _repeat(debug) == dict(default, key='a', **{'deadline-ns':first})
            _advance(debug, first-5*MILLISECOND)
            assert _scans(debug, symbols) == [0x2a, MAKE]
            _advance(debug, first+3*MILLISECOND)
            assert _scans(debug, symbols) == [0x2a, MAKE, MAKE]
            assert _repeat(debug)['deadline-ns'] == first+default['interval-ns']
            assert _keys(debug)['accepted-edges'] == held['accepted-edges']

            start = debug.clock_observe()['virtual_ns']
            _edges(debug, ('b', True))
            second = start+500*MILLISECOND
            assert _repeat(debug) == dict(default, key='b', **{'deadline-ns':second})
            _advance(debug, second+3*MILLISECOND)
            assert _scans(debug, symbols) == [0x2a, MAKE, MAKE, 0x30, 0x30]
            _edges(debug, ('b', False))
            assert _repeat(debug) == default
            _advance(debug, second+2*default['interval-ns'])
            assert _scans(debug, symbols) == [0x2a, MAKE, MAKE, 0x30, 0x30, 0xb0]
            assert _keys(debug)['held'] == ['a','shift']
            _edges(debug, ('a', False), ('shift', False))
        assert debug.vm.process.poll() == 0
    assert target.read_bytes() == code
    assert digest(disk['image']) == disk['prepared_sha256']


def test_native_typematic_programmed_raster_timeline_hot_and_cold_restore(tmp_path):
    _programmed_raster_restore(tmp_path)


@pytest.mark.skipif(os.environ.get('FDISBULL_REQUIRE_QEMU_VGA_LATCH') != '1',
                    reason='Select the exact native timed unchained VGA witness')
def test_native_typematic_replays_guest_irq_page_flips_in_timed_raster(tmp_path):
    runtime = _runtime()
    assert digest(runtime['FDISBULL_QEMU_LAYERS']) == os.environ['FDISBULL_QEMU_VGA_LATCH_SHA256']
    assert digest(runtime['FDISBULL_QEMU_IMG']) == os.environ['FDISBULL_QEMU_VGA_LATCH_IMG_SHA256']
    _programmed_raster_restore(tmp_path, timed_page_flip=True)


def test_native_dosbox_typematic_raster_timeline_hot_and_cold_restore(tmp_path):
    if os.environ.get('FDISBULL_REQUIRE_QEMU_DOSBOX_TYPEMATIC') != '1':
        pytest.skip('Enable the optional native DOSBox typematic profile witness')
    _programmed_raster_restore(tmp_path, profile='dosbox-millisecond')


def _programmed_raster_restore(tmp_path, *, profile=None, timed_page_flip=False):
    runtime = _runtime()
    interval = 63*MILLISECOND if profile else 62_500_000
    profile_fields = {'profile': profile} if profile else {}
    rate = dict(parameter=0x27, **profile_fields,
                **{'delay-ns':500*MILLISECOND, 'interval-ns':interval})
    disk,target,code,offsets = _input(tmp_path,runtime,programmed=True,timed_page_flip=timed_page_flip)
    source_profile = {'qemu_video_source_profile': LATCH_PROFILE} if timed_page_flip else {}
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    db = tmp_path/'programmed.fdb'
    with Project.create(db,target,image='com') as project:
        with _launch(project,runtime,tmp_path,disk,clock_profile='virtual',retrace='precise',
                     qemu_key_repeat_profile=profile, **source_profile) as debug:
            symbols = _ready(debug,offsets,programmed=True)
            assert _repeat(debug) == dict(rate, **{'deadline-ns':-1})
            debug.video_frame_start()
            assert debug.video_frame_advance(timeout_ms=15000)['advance_completed']
            start = debug.clock_observe()['virtual_ns']
            keys = _edges(debug, ('a', True))
            first = start+500*MILLISECOND
            assert _repeat(debug)['deadline-ns'] == first
            _advance(debug, first-5*MILLISECOND)
            assert _scans(debug,symbols) == [MAKE]
            _advance(debug, first+10*MILLISECOND)
            assert _scans(debug,symbols) == [MAKE, MAKE]
            repeat = _repeat(debug)
            assert repeat == dict(rate, key='a', **{'deadline-ns':first+interval})
            root = debug.timeline_start(frame_source='source-raster',max_frames=8,max_bytes=160*1024**2,
                max_state_bytes=24*1024**2,timeout_ms=30000)
            control = dict(db=str(db),directory=str(tmp_path),disk=str(disk['image']), symbols=symbols,
                repeat_profile=profile,
                timed_page_flip=timed_page_flip,
                timeline=root['timeline'], point=root['point'], token=keys['token'], epoch=keys['epoch'],
                accepted=keys['accepted-edges'], raster=root['nodes'][0]['frame']['source_raster'],
                repeat=repeat,saved_ns=debug.clock_observe()['virtual_ns'])
            control['expected'] = _capture_future(
                debug,symbols,repeat,control['accepted'],timed_page_flip=timed_page_flip)
            _restore(debug,control)
            assert _capture_future(
                debug,symbols,repeat,control['accepted'],timed_page_flip=timed_page_flip) == control['expected']
        assert debug.vm.process.poll() == 0
    control_path = tmp_path/'cold-control.json'
    control_path.write_text(json.dumps(control),encoding='utf-8')
    child = subprocess.run([sys.executable,__file__,'--cold',str(control_path)], capture_output=True,
        text=True,env=os.environ.copy(),timeout=150)
    assert child.returncode == 0, child.stderr[-6000:]
    assert json.loads(child.stdout) == dict(passed=True)
    assert target.read_bytes() == code and digest(boot) == disk['source_sha256']
    assert digest(disk['image']) == disk['prepared_sha256']



def _overdue_state(debug, symbols):
    clock = debug.clock_observe()
    assert 'virtual_ns' in clock
    return dict(virtual_ns=clock['virtual_ns'], counter=clock['counter'],
                repeat=_repeat(debug), keyboard=_proof(_keys(debug)), scans=_scans(debug,symbols))


def _overdue_irq(debug, target, code):
    offset, segment = struct.unpack('<HH', _bytes(debug, 9*4, 4))
    irq = segment*16+offset
    base = debug.dos_process_info()['source_mapping']['runtime_base']
    assert base <= irq < base+len(code)
    # Entry comes from the actual IRQ1 vector installed by the authored COM.
    # Bind the port-read instruction to that exact loaded handler.
    before_read = b'\x50\x53\x1e\x0e\x1f\xe4\x64\x24\x21\x3c\x01'
    start = irq-base
    assert code[start:start+len(before_read)] == before_read
    port_read = code.index(b'\xe4\x60',start+len(before_read),start+24)
    span = code[start:port_read+2]
    assert _bytes(debug,irq,len(span)) == span and target.read_bytes() == code
    return dict(entry=irq, io_read=base+port_read, vector=[segment,offset])


def _overdue_resume(debug, control):
    symbols, saved, irq = (control[key] for key in ('symbols','saved','irq'))
    assert _overdue_state(debug,symbols) == saved

    # A debugger step from the captured frontier must also leave the
    # overdue timer and PS/2 state intact after either kind of restore.
    assert debug.step(timeout_ms=5000)['outcome'] == 'step'
    masked = _overdue_state(debug,symbols)
    assert masked['virtual_ns'] > saved['virtual_ns']
    assert masked['repeat'] == saved['repeat'] and masked['keyboard'] == saved['keyboard']
    assert masked['scans'] == saved['scans']

    # Capture actual IRQ1 dispatch before the guest consumes the waiting byte.
    park(debug,irq['entry'])
    arrival = _overdue_state(debug,symbols)
    assert int(debug.registers()['linear_pc'],0) == irq['entry']
    next_phase = dict(saved['repeat'])
    next_phase['deadline-ns'] += next_phase['interval-ns']
    assert arrival['repeat'] == next_phase and arrival['scans'] == [MAKE]
    fifo = arrival['keyboard']
    assert fifo['fifo-count'] == 1 and fifo['fifo-sha256'] != saved['keyboard']['fifo-sha256']
    assert fifo['controller-status'] & 0x21 == 1 and fifo['controller-obsrc'] == 1
    assert fifo['accepted-edges'] == saved['keyboard']['accepted-edges']

    park(debug,irq['io_read'])
    assert _bytes(debug,irq['io_read'],2) == b'\xe4\x60'
    assert debug.step(timeout_ms=5000)['outcome'] == 'step'
    cpu = debug.registers()
    assert int(cpu['linear_pc'],0) == irq['io_read']+2
    registers = cpu['registers']
    byte = int(registers.get('rax',registers.get('eax')),0) & 0xff
    assert byte == MAKE and _scans(debug,symbols) == [MAKE]
    after_read = _overdue_state(debug,symbols)
    assert after_read['keyboard']['fifo-count'] == 0
    assert not after_read['keyboard']['controller-status'] & 1

    stopped = _advance(debug,saved['virtual_ns']+5*MILLISECOND)
    consumed = _overdue_state(debug,symbols)
    assert consumed['virtual_ns'] == stopped and consumed['repeat'] == next_phase
    assert consumed['scans'] == [MAKE,MAKE]
    assert consumed['keyboard']['accepted-edges'] == saved['keyboard']['accepted-edges']
    return dict(masked_step=masked, irq_entry=arrival, native_byte=byte,
                after_read=after_read, consumed=consumed)


def _overdue_restore(debug, control):
    previous = debug.vm.process
    debug.load_state(control['artifact'],timeout_ms=30000)
    assert previous.poll() == 0 and debug.vm.process is not previous
    assert _overdue_state(debug,control['symbols']) == control['saved']
    return debug.vm.process


def test_native_typematic_checkpoint_preserves_past_pending_deadline(tmp_path):
    from fdisbull.qemu_step_policy import observe_step_policy

    runtime = _runtime()
    disk,target,code,offsets = _input(tmp_path,runtime,programmed=True,busy=True)
    db = tmp_path/'past-repeat.fdb'
    control = dict(db=str(db),directory=str(tmp_path),disk=str(disk['image']),
                   producer_sha256=digest(runtime['FDISBULL_QEMU_LAYERS']),
                   authored_com_sha256=sha256(code).hexdigest())
    receipt = dict(completed=False,stopped_captures=[])
    owners, cold_owners = {}, {}

    try:
        with Project.create(db,target,image='com') as project:
            with _launch(project,runtime,tmp_path,disk,clock_profile='virtual',retrace='precise') as debug:
                owners['source'] = debug.vm.process
                symbols = control['symbols'] = _ready(debug,offsets,programmed=True)
                control['irq'] = _overdue_irq(debug,target,code)
                _edges(debug, ('a', True))
                first = _repeat(debug)['deadline-ns']
                stopped = _advance(debug,first-1)
                pending = _overdue_state(debug,symbols)
                assert first <= stopped <= pending['repeat']['deadline-ns'] <= stopped+1, pending
                assert pending['scans'] == [MAKE]
                assert pending['keyboard']['fifo-count'] == 0
                assert not pending['keyboard']['controller-status'] & 1
                policy = observe_step_policy(debug._stopped(),timeout_ms=1000)
                assert policy['status'] == 'observed' and policy['timers_masked'] is True

                # Each timer-masked debugger step moves the executed clock but
                # leaves the logically overdue callback and the i8042 intact.
                for ordinal in range(3):
                    assert debug.step(timeout_ms=5000)['outcome'] == 'step'
                    cut = dict(pre_save=_overdue_state(debug,symbols))
                    receipt['stopped_captures'].append(cut)
                    saved = cut['pre_save']
                    assert pending['repeat']['deadline-ns'] < saved['virtual_ns']
                    assert saved['repeat'] == pending['repeat']
                    assert saved['keyboard'] == pending['keyboard'] and saved['scans'] == [MAKE]
                    artifact = debug.save_state(f'past-repeat-{ordinal}.qcow2',max_bytes=24*1024**2)
                    cut['artifact_sha256'] = artifact['sha256']
                    cut['post_save'] = _overdue_state(debug,symbols)
                    assert cut['post_save'] == saved
                control.update(artifact=artifact['artifact'],saved=saved)
                receipt['forward'] = _overdue_resume(debug,control)
                owners['hot'] = _overdue_restore(debug,control)
                receipt['hot'] = _overdue_resume(debug,control)
                assert receipt['hot'] == receipt['forward']
            assert all(owner.poll() == 0 for owner in owners.values())

        control_path = tmp_path/'cold-overdue.json'
        control_path.write_text(json.dumps(control),encoding='utf-8')
        child = subprocess.run([sys.executable,__file__,'--cold-overdue',str(control_path)],
            capture_output=True,text=True,check=False,timeout=150)
        (tmp_path/'cold-overdue.log').write_text(child.stdout+child.stderr,encoding='utf-8')
        assert child.returncode == 0, child.stderr[-6000:]
        cold = json.loads(child.stdout)
        assert cold['host_pid'] != os.getpid()
        cold_owners = cold['owners']
        assert not {owner.pid for owner in owners.values()} & {owner['pid'] for owner in cold_owners.values()}
        receipt['cold'] = cold['replay']
        assert receipt['cold'] == receipt['forward']
        receipt['completed'] = True
    finally:
        assert target.read_bytes() == code and digest(disk['image']) == disk['prepared_sha256']
        receipt['owners'] = {**{name:dict(pid=owner.pid,returncode=owner.poll())
                                for name,owner in owners.items()}, **cold_owners}
        receipt['control'] = control
        (tmp_path/'overdue-repeat.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n',
                                                 encoding='utf-8')


def _cold_overdue(control):
    runtime = _runtime()
    assert digest(runtime['FDISBULL_QEMU_LAYERS']) == control['producer_sha256']
    with Project(control['db']) as project:
        with _launch(project,runtime,Path(control['directory']),{'image':control['disk']},
                     clock_profile='virtual',retrace='precise') as debug:
            entry = debug.vm.process
            restored = _overdue_restore(debug,control)
            replay = _overdue_resume(debug,control)
    assert entry is not restored and entry.poll() == restored.poll() == 0
    print(json.dumps(dict(host_pid=os.getpid(),replay=replay,owners={
        'cold_entry': dict(pid=entry.pid,returncode=entry.poll()),
        'cold_restored': dict(pid=restored.pid,returncode=restored.poll()),
    })))


def _cold(control):
    runtime = _runtime()
    timed_page_flip = control['timed_page_flip']
    source_profile = {'qemu_video_source_profile': LATCH_PROFILE} if timed_page_flip else {}
    with Project(control['db']) as project:
        with _launch(project,runtime,Path(control['directory']),{'image':control['disk']},
                     clock_profile='virtual',retrace='precise',
                     qemu_key_repeat_profile=control['repeat_profile'], **source_profile) as debug:
            _restore(debug,control)
            assert _capture_future(debug,control['symbols'],control['repeat'],control['accepted'],
                                   timed_page_flip=timed_page_flip) == control['expected']
        assert debug.vm.process.poll() == 0
    print(json.dumps(dict(passed=True)))


if __name__ == '__main__':
    worker = {'--cold': _cold, '--cold-overdue': _cold_overdue}[sys.argv[1]]
    worker(json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')))
