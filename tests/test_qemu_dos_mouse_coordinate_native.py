"""Paired guest coordinate samples with physical QEMU and absolute DOSBox input.

Set FDISBULL_DOSBOX and the clock and INT33 witness inputs from
test_qemu_dos_mouse_native.py. FDISBULL_REQUIRE_QEMU_MOUSE=1 turns a missing
backend/driver into a failure. The guest COM is authored here. The pinned
driver, boot disk and private runtime artifacts remain external.
"""
import hashlib
import json
import os
from pathlib import Path
import struct

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import assemble, digest
from support.qemu_dos_mouse_fixture import CTMOUSE_SHA256, prepare_mouse_disk
from test_qemu_clock_budget_native import clock_disk, clock_runtime
from test_qemu_dos_mouse_native import mouse_inputs
from test_qemu_dos_process_native import com_address, launch_options

_ASSEMBLY = r'''
bits 16
org 100h
    nop
    push cs
    pop ds
    mov ax,0013h
    int 10h
    mov ax,0a000h
    mov es,ax
    xor ax,ax
    int 33h
    mov [installed],ax
    cmp ax,0ffffh
    jne failure

    mov ax,7
    mov cx,96
    mov dx,400
    int 33h
    mov ax,8
    mov cx,50
    mov dx,130
    int 33h
    mov ax,4
    mov cx,318
    mov dx,88
    int 33h
    mov ax,0bh
    int 33h

    mov di,origin
    call sample
ready:
    nop
left_press_loop:
    inc byte [es:0]
    mov ax,3
    int 33h
    test bx,1
    jz left_press_loop
    mov di,left_press
    call sample
pressed:
    nop
left_release_loop:
    mov ax,3
    int 33h
    test bx,1
    jnz left_release_loop
    mov di,left_release
    call sample

    mov ax,7
    mov cx,96
    mov dx,320
    int 33h
    mov ax,8
    mov cx,50
    mov dx,90
    int 33h
    mov di,clip_origin
    call sample
clip_ready:
    nop
right_press_loop:
    mov ax,3
    int 33h
    test bx,2
    jz right_press_loop
    mov di,right_press
    call sample
clipped:
    nop
right_release_loop:
    mov ax,3
    int 33h
    test bx,2
    jnz right_release_loop
    mov di,right_release
    call sample
done:
    nop
    ; DOS installs a different IRET stub at the same segment-relative offset.
    ; The observer must compare code evidence, not just recognize the offset.
    mov ax,3533h
    int 21h
    mov [old_offset],bx
    mov [old_segment],es
    mov dx,alternate_handler
    mov ax,2533h
    int 21h
alternate_vector:
    nop
    push ds
    mov ds,[old_segment]
    mov dx,[cs:old_offset]
    mov ax,2533h
    int 21h
    pop ds
restored_vector:
    nop
    mov ax,4c2ah
    int 21h
failure:
    jmp failure

sample:
    push di
    mov ax,3
    int 33h
    pop di
    mov [di],cx
    mov [di+2],dx
    mov [di+4],bx
    push di
    mov ax,0bh
    int 33h
    pop di
    mov [di+6],cx
    mov [di+8],dx
    ret

installed: dw 0
origin: times 5 dw 0
left_press: times 5 dw 0
left_release: times 5 dw 0
clip_origin: times 5 dw 0
right_press: times 5 dw 0
right_release: times 5 dw 0
old_offset: dw 0
old_segment: dw 0
    times (0xb5e - 0x100 - ($ - $$)) db 0
alternate_handler:
    iret
db 'I33C'
dw ready,pressed,clip_ready,clipped,done,installed,alternate_vector,restored_vector
dw origin,left_press,left_release,clip_origin,right_press,right_release
'''


def _park(debug, address, *, qemu):
    point = debug.breakpoint(address)
    try:
        options = {} if qemu else {'fast_forward': True}
        result = debug.run(timeout_ms=5000, **options)
        assert result['outcome'] == 'breakpoint', result
        return result
    finally:
        debug.delete_breakpoint(point['breakpoint_id'])


def test_paired_int33_position_and_clipping(tmp_path, clock_runtime, clock_disk, mouse_inputs):
    dosbox_path = os.environ.get('FDISBULL_DOSBOX')
    if not dosbox_path:
        message = 'Native coordinate witness requires FDISBULL_DOSBOX'
        if os.environ.get('FDISBULL_REQUIRE_QEMU_MOUSE') == '1':
            pytest.fail(message)
        pytest.skip(message)
    dosbox = Path(dosbox_path).expanduser().resolve(strict=True)
    assert dosbox.is_file() and os.access(dosbox, os.X_OK), dosbox
    baseline = prepare_mouse_disk(clock_disk['image'], tmp_path / 'mouse-boot.img',
                                  mouse_inputs['driver'], clock_runtime['mcopy'])
    code = assemble(tmp_path, 'coordinate-oracle', _ASSEMBLY, clock_runtime['nasm'])
    names = ('ready', 'pressed', 'clip_ready', 'clipped', 'done', 'installed',
             'alternate_vector', 'restored_vector', 'origin', 'left_press', 'left_release',
             'clip_origin', 'right_press', 'right_release')
    assert code[-32:-28] == b'I33C'
    offsets = dict(zip(names, struct.unpack('<14H', code[-28:]), strict=True))
    binary = tmp_path / 'COORD.COM'
    binary.write_bytes(code)
    receipt = {'source_sha256': hashlib.sha256(code).hexdigest(),
               'installed': {}, 'phases': {}, 'native': {}, 'passive': {}}
    receipt['dosbox_sha256'] = digest(dosbox)
    receipt['qemu_sha256'] = digest(clock_runtime['executable'])
    receipt['driver_sha256'] = digest(mouse_inputs['driver'])
    receipt['boot_sha256'] = digest(clock_disk['image'])
    try:
        with Project.create(tmp_path/'coordinate.fdb', binary, image='com') as project:
            project.analyze(max_instructions=4096)
            for qemu in (False, True):
                key = 'qemu' if qemu else 'dosbox'
                rows = receipt['phases'][key] = {}
                options = launch_options(clock_runtime, baseline, qemu_clock='virtual',
                                         qemu_retrace='precise') if qemu else {}
                executable = clock_runtime['executable'] if qemu else dosbox
                with project.debugger(str(executable), tmp_path, **options) as debug:
                    if qemu:
                        info = debug.dos_process_info()
                        locations = {name: com_address(info, offset) for name, offset in offsets.items()}
                    else:
                        locations = {name: debug.static_base + offset - 0x100
                                     for name, offset in offsets.items()}

                    def read(name, size):
                        view = {'space':'physical'} if qemu else {}
                        return bytes.fromhex(debug.memory(locations[name], length=size, **view)['hex'])

                    def take(name):
                        rows[name] = list(struct.unpack('<HHHhh', read(name, 10)))

                    def observe(name):
                        revision = debug.vm.session_revision.snapshot()
                        sample = debug.observe_int33_mouse()
                        assert debug.vm.session_revision.snapshot() == revision
                        assert sample['complete'] and sample['authority']['complete']
                        assert sample['vector_authority']['complete']
                        assert sample['driver']['sha256'] == CTMOUSE_SHA256
                        assert sample['driver']['vector']['offset'] == 0xb5e
                        assert len(sample['matching_source_spans']) == 4
                        assert sample['position'] + [sample['buttons']] == rows[name][:3]
                        assert sample['raster']['frame_id'] >= 1
                        assert sample['raster']['completed_ns'] <= sample['clock']['virtual_ns']
                        receipt['passive'][name] = {key: sample[key] for key in (
                            'driver', 'position', 'raw_position', 'buttons', 'minimum',
                            'maximum', 'mickeys_per_eight_units', 'clock', 'raster',
                            'matching_source_spans')}

                    _park(debug, locations['ready'], qemu=qemu)
                    receipt['installed'][key] = int.from_bytes(read('installed', 2), 'little')
                    take('origin')
                    if qemu:
                        assert debug.capabilities['absolute_mouse'] is False
                        with pytest.raises(ValueError, match='active retained source raster'):
                            debug.observe_int33_mouse()
                        assert debug.vm.process.poll() is None
                        debug.video_frame_start()
                        advance = debug.video_frame_advance()
                        assert advance['advance_completed'], advance
                        cap = debug.capture_video_frame('mode13-qemu.png')
                        meta = cap['metadata']
                        assert meta['width'] == 320 and meta['height'] == 200, meta
                        receipt['frame'] = {x:meta.get(x) for x in ('width','height','frame_id','mode_id','frame_profile')}
                        observe('origin')
                        with pytest.raises(ValueError, match='no longer retained'):
                            debug.observe_int33_mouse(stream='stale-stream', frame_id=meta['frame_id'])
                        assert debug.vm.process.poll() is None
                        debug.mouse_move_relative(2, 4)
                        lease = debug.mouse_button_down('left')['lease']
                    else:
                        debug.run(guest_ms=70, timeout_ms=5000, fast_forward=True)
                        stale = debug.screenshot('mode13-dosbox-stale.png')['metadata']
                        debug.run(guest_ms=70, timeout_ms=5000, fast_forward=True)
                        meta = debug.screenshot('mode13-dosbox.png')['metadata']
                        assert stale['mode_id'] == meta['mode_id'] and stale['frame_id'] < meta['frame_id']
                        state = debug.call('input.mouse.state')['mouse']
                        with pytest.raises(DebuggerError, match='STALE_FRAME'):
                            debug.click(160, 90, mode_id=meta['mode_id'], frame_id=stale['frame_id'])
                        assert debug.call('input.mouse.state')['mouse'] == state
                        receipt['native']['dosbox_stale_frame_refused'] = True
                        assert meta['width'] == 320 and meta['height'] == 200, meta
                        mode = meta['mode_id']
                        receipt['native']['dosbox_first_click'] = debug.click(
                            160, 90, mode_id=mode, frame_id=meta['frame_id'], hold_ms=80)['mouse']

                    _park(debug, locations['pressed'], qemu=qemu)
                    take('left_press')
                    if qemu:
                        observe('left_press')
                        debug.mouse_button_up(lease)
                    _park(debug, locations['clip_ready'], qemu=qemu)
                    take('left_release')
                    take('clip_origin')

                    if qemu:
                        observe('clip_origin')
                        debug.mouse_move_relative(4, 4)
                        lease = debug.mouse_button_down('right')['lease']
                    else:
                        receipt['native']['dosbox_clip_click'] = debug.click(
                            319, 199, button='right', mode_id=mode, hold_ms=80)['mouse']
                    _park(debug, locations['clipped'], qemu=qemu)
                    take('right_press')
                    if qemu:
                        observe('right_press')
                        debug.mouse_button_up(lease)
                    _park(debug, locations['done'], qemu=qemu)
                    take('right_release')
                    if qemu:
                        observe('right_release')
                        _park(debug, locations['alternate_vector'], qemu=qemu)
                        with pytest.raises(ValueError, match='resident dispatcher bytes differ') as failure:
                            debug.observe_int33_mouse()
                        assert failure.value.code == 'resident_source_mismatch'
                        assert debug.vm.process.poll() is None
                        receipt['native']['qemu_other_int33_driver_refused'] = True
                        _park(debug, locations['restored_vector'], qemu=qemu)
                        restored = debug.observe_int33_mouse()
                        assert restored['driver'] == receipt['passive']['right_release']['driver']
                        assert restored['position'] + [restored['buttons']] == rows['right_release'][:3]
                        frame = restored['raster']
                        assert debug.observe_int33_mouse(stream=frame['stream'],
                            frame_id=frame['frame_id'])['raster'] == frame
                        assert debug.capabilities['absolute_mouse'] is False
                    result = debug.run(timeout_ms=5000)
                    assert result['outcome'] == 'guest_exit', result
                    receipt['native'][key + '_exit'] = result['outcome']
                    owner = debug.vm.process if qemu else debug.rpc.process
                assert owner.poll() is not None
    finally:
        assert binary.read_bytes() == code
        assert digest(mouse_inputs['driver']) == CTMOUSE_SHA256
        assert digest(baseline['image']) == baseline['prepared_sha256']
        assert digest(clock_disk['image']) == baseline['source_sha256']
        (tmp_path / 'int33-coordinate-receipt.json').write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    assert receipt['installed'] == {'qemu':65535,'dosbox':65535}
    dosbox_samples, qemu_samples = receipt['phases']['dosbox'], receipt['phases']['qemu']
    expected = {
        'origin': [318, 88, 0],
        'left_press': [320, 90, 1],
        'left_release': [320, 90, 0],
        'clip_origin': [320, 90, 0],
        'right_press': [320, 90, 2],
        'right_release': [320, 90, 0],
    }
    for phase, values in expected.items():
        assert dosbox_samples[phase][:3] == qemu_samples[phase][:3] == values
    # CuteMouse 2.1b4 defaults to 8/16 mickeys per eight position units.
    # A <=4-count raw packet bypasses its acceleration at default sensitivity.
    # DOSBox places the cursor directly and the same application sees no mickeys.
    assert qemu_samples['left_press'][3:] == [2, 4]
    assert qemu_samples['right_press'][3:] == [4, 4]
    assert all(sample[3:] == [0, 0] for sample in dosbox_samples.values())

    assert list(receipt['passive']) == ['origin', 'left_press', 'clip_origin', 'right_press', 'right_release']
    for name, sample in receipt['passive'].items():
        assert sample['position'] == sample['raw_position']
        assert sample['mickeys_per_eight_units'] == [8, 16]
        assert sample['minimum'] == [96, 50]
        assert sample['maximum'] == ([400, 130] if name in ('origin', 'left_press') else [320, 90])
