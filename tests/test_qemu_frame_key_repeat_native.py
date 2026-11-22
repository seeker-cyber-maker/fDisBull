"""Authored IRQ1 and VGA witnesses for native PS/2 typematic checkpoints.

FDISBULL_QEMU_KEY_REPEAT selects an exact privately prepared QEMU producer.
FDISBULL_REQUIRE_QEMU_KEY_REPEAT=1 makes missing inputs a test failure.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, assemble, digest, prepare_dos_baseline
from test_qemu_clock_budget_native import park
from test_qemu_dos_modes_checkpoint_native import _launch


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
.full:
    inc word [scan_count]
.eoi:
    mov al,20h
    out 20h,al
    pop ds
    pop bx
    pop ax
    iret
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


def _input(directory, runtime, programmed, *, busy=False):
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    disk = prepare_dos_baseline(boot, directory/'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n'+BASELINE_CONFIG)
    defines = f'%define PROGRAM_RATE {int(programmed)}\n%define BUSY_LOOP {int(busy)}\n'
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


def _capture_future(debug, symbols, saved, accepted):
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
    _advance(debug, expected_deadline+interval+3*MILLISECOND)
    assert _scans(debug, symbols) == [MAKE]*4
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
    runtime = _runtime()
    disk,target,code,offsets = _input(tmp_path,runtime,programmed=True)
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    db = tmp_path/'programmed.fdb'
    with Project.create(db,target,image='com') as project:
        with _launch(project,runtime,tmp_path,disk,clock_profile='virtual',retrace='precise') as debug:
            symbols = _ready(debug,offsets,programmed=True)
            assert _repeat(debug) == dict(parameter=0x27, **{
                'delay-ns':500*MILLISECOND,'interval-ns':62_500_000,'deadline-ns':-1})
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
            assert repeat == dict(parameter=0x27, key='a', **{
                'delay-ns':500*MILLISECOND,'interval-ns':62_500_000,'deadline-ns':first+62_500_000})
            root = debug.timeline_start(frame_source='source-raster',max_frames=8,max_bytes=160*1024**2,
                max_state_bytes=24*1024**2,timeout_ms=30000)
            control = dict(db=str(db),directory=str(tmp_path),disk=str(disk['image']), symbols=symbols,
                timeline=root['timeline'], point=root['point'], token=keys['token'], epoch=keys['epoch'],
                accepted=keys['accepted-edges'], raster=root['nodes'][0]['frame']['source_raster'],
                repeat=repeat,saved_ns=debug.clock_observe()['virtual_ns'])
            control['expected'] = _capture_future(debug,symbols,repeat,control['accepted'])
            _restore(debug,control)
            assert _capture_future(debug,symbols,repeat,control['accepted']) == control['expected']
        assert debug.vm.process.poll() == 0
    control_path = tmp_path/'cold-control.json'
    control_path.write_text(json.dumps(control),encoding='utf-8')
    child = subprocess.run([sys.executable,__file__,'--cold',str(control_path)], capture_output=True,
        text=True,env=os.environ.copy(),timeout=150)
    assert child.returncode == 0, child.stderr[-6000:]
    assert json.loads(child.stdout) == dict(passed=True)
    assert target.read_bytes() == code and digest(boot) == disk['source_sha256']
    assert digest(disk['image']) == disk['prepared_sha256']



def test_native_typematic_checkpoint_preserves_past_pending_deadline(tmp_path):
    from fdisbull.qemu_step_policy import observe_step_policy
    runtime = _runtime()
    disk,target,code,offsets = _input(tmp_path,runtime,programmed=True,busy=True)
    with Project.create(tmp_path/'past-repeat.fdb',target,image='com') as project:
        with _launch(project,runtime,tmp_path,disk,clock_profile='virtual',retrace='precise') as debug:
            symbols = _ready(debug,offsets,programmed=True)
            keys = _edges(debug, ('a', True))
            first = _repeat(debug)['deadline-ns']
            stopped = _advance(debug, first-1)
            pending = _repeat(debug)
            assert first <= stopped and stopped <= pending['deadline-ns'] <= stopped+1, pending
            assert _scans(debug,symbols) == [MAKE]
            policy = observe_step_policy(debug._stopped(),timeout_ms=1000)
            assert policy['status'] == 'observed' and policy['timers_masked'] is True
            assert debug.step(timeout_ms=5000)['outcome'] == 'step'
            saved_ns = debug.clock_observe()['virtual_ns']
            assert pending['deadline-ns'] < saved_ns and _repeat(debug) == pending
            assert _scans(debug,symbols) == [MAKE]

            checkpoint = debug.save_state('past-repeat.qcow2',max_bytes=24*1024**2)['artifact']
            assert _repeat(debug) == pending
            target_ns = saved_ns+5*MILLISECOND
            original_stop = _advance(debug,target_ns)
            next_phase = _repeat(debug)
            assert next_phase['deadline-ns'] == pending['deadline-ns']+pending['interval-ns']
            assert _scans(debug,symbols) == [MAKE, MAKE]

            original_owner = debug.vm.process
            debug.load_state(checkpoint,timeout_ms=30000)
            assert original_owner.poll() == 0
            assert _repeat(debug) == pending
            assert debug.clock_observe()['virtual_ns'] == saved_ns
            assert _scans(debug,symbols) == [MAKE]
            assert _keys(debug)['accepted-edges'] == keys['accepted-edges']
            assert _advance(debug,target_ns) == original_stop
            assert _repeat(debug) == next_phase and _scans(debug,symbols) == [MAKE, MAKE]
        assert debug.vm.process.poll() == 0
    assert target.read_bytes() == code


def _cold(control):
    runtime = _runtime()
    with Project(control['db']) as project:
        with _launch(project,runtime,Path(control['directory']),{'image':control['disk']},
                     clock_profile='virtual',retrace='precise') as debug:
            _restore(debug,control)
            assert _capture_future(debug,control['symbols'],control['repeat'],control['accepted']) == control['expected']
        assert debug.vm.process.poll() == 0
    print(json.dumps(dict(passed=True)))


if __name__ == '__main__':
    assert sys.argv[1] == '--cold'
    _cold(json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')))
