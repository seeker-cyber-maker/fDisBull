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
import time

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
motion_loop:
    inc byte [es:0]
    mov ax,3
    int 33h
    cmp cx,320
    jne motion_loop
    cmp dx,90
    jne motion_loop
motion_landed:
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
    mov ax,4
    mov cx,300
    mov dx,80
    int 33h
warped_after_edges:
    nop
    mov di,guest_edges
    xor bx,bx
    mov ax,5
    call sample_edge
    mov bx,1
    mov ax,5
    call sample_edge
    xor bx,bx
    mov ax,6
    call sample_edge
    mov bx,1
    mov ax,6
    call sample_edge
edge_queries_done:
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

sample_edge:
    push di
    int 33h
    pop di
    mov [di],bx
    mov [di+2],cx
    mov [di+4],dx
    add di,6
    ret

installed: dw 0
origin: times 5 dw 0
left_press: times 5 dw 0
left_release: times 5 dw 0
clip_origin: times 5 dw 0
right_press: times 5 dw 0
right_release: times 5 dw 0
guest_edges: times 12 dw 0
old_offset: dw 0
old_segment: dw 0
    times (0xb5e - 0x100 - ($ - $$)) db 0
alternate_handler:
    iret
db 'I33C'
dw ready,pressed,clip_ready,clipped,done,installed,alternate_vector,restored_vector,motion_landed
dw origin,left_press,left_release,clip_origin,right_press,right_release
dw warped_after_edges,edge_queries_done,guest_edges
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


def _settle_boot_events(debug):
    # QEMU coalesces boot RTC_CHANGE notifications for one host-realtime
    # second. Let that existing event expire while the authored guest stays
    # stopped, then acknowledge it before opening a strict observation lease.
    time.sleep(1.1)
    debug.clock_observe()


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
             'alternate_vector', 'restored_vector', 'motion_landed', 'origin', 'left_press',
             'left_release', 'clip_origin', 'right_press', 'right_release',
             'warped_after_edges', 'edge_queries_done', 'guest_edges')
    assert code[-40:-36] == b'I33C'
    offsets = dict(zip(names, struct.unpack('<18H', code[-36:]), strict=True))
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
                        assert len(sample['matching_source_spans']) == 8
                        assert sample['position'] + [sample['buttons']] == rows[name][:3]
                        assert sample['raster']['frame_id'] >= 1
                        assert sample['raster']['completed_ns'] <= sample['clock']['virtual_ns']
                        receipt['passive'][name] = {key: sample[key] for key in (
                            'driver', 'position', 'raw_position', 'buttons', 'minimum',
                            'maximum', 'mickeys_per_eight_units', 'clock', 'raster',
                            'sensitivity_coefficients', 'position_remainders', 'matching_source_spans',
                            'button_edges')}

                    _park(debug, locations['ready'], qemu=qemu)
                    receipt['installed'][key] = int.from_bytes(read('installed', 2), 'little')
                    take('origin')
                    if qemu:
                        _settle_boot_events(debug)
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
                        frame = receipt['passive']['origin']['raster']
                        selector = dict(stream=frame['stream'], frame_id=frame['frame_id'])
                        assert debug.video_frame_advance()['advance_completed']
                        with pytest.raises(ValueError, match='no longer retained'):
                            debug.mouse_move_int33(160, 90, **selector)
                        fresh = debug.observe_int33_mouse()['raster']
                        assert fresh['stream'] == frame['stream'] and fresh['frame_id'] > frame['frame_id']
                        assert debug.input_state()['pending_edges'] == 0
                        selector['frame_id'] = fresh['frame_id']
                        with pytest.raises(ValueError, match='no observed landing'):
                            debug.mouse_button_down_int33(160, 90, **selector)
                        assert debug.input_state()['pending_edges'] == 0
                        with pytest.raises(ValueError, match='clip range'):
                            debug.mouse_move_int33(319, 199, **selector)
                        with pytest.raises(ValueError, match='four physical counts'):
                            debug.mouse_move_int33(160, 93, **selector)
                        assert debug.input_state()['pending_edges'] == 0
                        motion = debug.mouse_move_int33(160, 90, **selector)
                        assert motion['counts'] == [2, 4] and motion['delivery'] == 'python_pending'
                        with pytest.raises(ValueError, match='neutral owned input queue'):
                            debug.mouse_button_down_int33(160, 90, **selector)
                        execution = _park(debug, locations['motion_landed'], qemu=qemu)
                        assert execution['input_delivery']['delivery'] == 'qmp_accepted'
                        landing = debug.observe_int33_mouse()
                        assert landing['position'] == [320, 90] and landing['buttons'] == 0
                        selector = dict(stream=landing['raster']['stream'],
                                        frame_id=landing['raster']['frame_id'])
                        at_target = debug.mouse_move_int33(160, 90, **selector)
                        assert at_target['delivery'] == 'already_at_target' and at_target['input'] is None
                        assert debug.input_state()['pending_edges'] == 0
                        press = debug.mouse_button_down_int33(160, 90, **selector)
                        assert press['delivery'] == 'python_pending' and press['guest_consumed'] is None
                        lease = press['lease']
                        receipt['native']['qemu_guarded_landing'] = {
                            'source_target': [160, 90], 'int33_target': landing['position'],
                            'relative_counts': motion['counts'], 'prepress_buttons': landing['buttons'],
                            'range_refusal': True, 'landing_refusal': True, 'queued_motion_refusal': True,
                            'stale_raster_refusal': True,
                        }
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
                        source = receipt['passive']['right_release']['raster']
                        with pytest.raises(ValueError, match='resident dispatcher bytes differ'):
                            debug.click(160, 90, delivery='observed-int33',
                                        session_id=source['session_id'], mode_id=source['mode_id'],
                                        frame_id=source['frame_id'])
                        assert debug.input_state()['pending_edges'] == 0
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
                        _park(debug, locations['warped_after_edges'], qemu=qemu)
                        warped = debug.observe_int33_mouse()
                        history = warped['button_edges']
                        assert warped['position'] == [300, 80]
                        assert history == receipt['passive']['right_release']['button_edges']
                        _park(debug, locations['edge_queries_done'], qemu=qemu)
                        consumed = debug.observe_int33_mouse()['button_edges']
                        guest_edges = [list(row) for row in
                                       struct.iter_unpack('<3H', read('guest_edges', 24))]
                        assert guest_edges == [[1, 320, 90]] * 4
                        for phase in ('press', 'release'):
                            for button in ('left', 'right'):
                                assert history[phase][button] == dict(count=1, last_position=[320, 90])
                                assert consumed[phase][button] == dict(count=0, last_position=[320, 90])
                            assert consumed[phase]['middle'] == dict(count=0, last_position=[0, 0])
                        receipt['native']['qemu_edge_query'] = dict(
                            position_after_warp=warped['position'], history=history,
                            consumed=consumed, guest_ax5_ax6=guest_edges)
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

    counted_edges = {
        'origin': (),
        'left_press': (('press', 'left'),),
        'clip_origin': (('press', 'left'), ('release', 'left')),
        'right_press': (('press', 'left'), ('release', 'left'), ('press', 'right')),
        'right_release': (('press', 'left'), ('release', 'left'), ('press', 'right'), ('release', 'right')),
    }
    for name, sample in receipt['passive'].items():
        for phase, buttons in sample['button_edges'].items():
            for button, record in buttons.items():
                expected = (dict(count=1, last_position=[320, 90]) if (phase, button) in counted_edges[name]
                            else dict(count=0, last_position=[0, 0]))
                assert record == expected


_CLICK_ASSEMBLY = r'''
bits 16
org 100h
    push cs
    pop ds
    mov ax,13h
    int 10h
    mov ax,0a000h
    mov es,ax
    xor ax,ax
    int 33h
    mov ax,4
    mov cx,318
    mov dx,88
    int 33h
first_frame:
    nop
wait_press:
    inc byte [es:0]
    mov ax,3
    int 33h
    test bx,1
    jz wait_press
pressed:
    nop
%if CASE = 1
    mov ax,4
    mov cx,300
    mov dx,80
    int 33h
%elif CASE = 2
    mov ax,5
    xor bx,bx
    int 33h
%endif
wait_release:
    inc byte [es:0]
    mov ax,3
    int 33h
    test bx,1
    jnz wait_release
released:
    inc byte [es:0]
    jmp released
db 'CLK1'
dw first_frame,pressed,released
'''


@pytest.mark.parametrize(('case', 'outcome'), [
    ('complete', 'completed'),
    ('breakpoint', 'competing_stop'),
    ('release_breakpoint', 'competing_stop'),
    ('warp', 'cursor_left_target'),
    ('consumed', 'driver_edge_unconfirmed'),
])
def test_observed_int33_click_resolves_only_qualified_press(
        tmp_path, clock_runtime, clock_disk, mouse_inputs, case, outcome):
    baseline = prepare_mouse_disk(clock_disk['image'], tmp_path / 'mouse-boot.img',
                                  mouse_inputs['driver'], clock_runtime['mcopy'])
    case_number = {'warp': 1, 'consumed': 2}.get(case, 0)
    code = assemble(tmp_path, 'observed-click', f'%define CASE {case_number}\n' + _CLICK_ASSEMBLY,
                    clock_runtime['nasm'])
    assert code[-10:-6] == b'CLK1'
    ready, pressed, released = struct.unpack('<3H', code[-6:])
    binary = tmp_path / 'CLICK.COM'
    binary.write_bytes(code)
    options = launch_options(clock_runtime, baseline, qemu_clock='virtual', qemu_retrace='precise')
    with Project.create(tmp_path / 'click.fdb', binary, image='com') as project:
        project.analyze(max_instructions=4096)
        with project.debugger(str(clock_runtime['executable']), tmp_path, **options) as debug:
            info = debug.dos_process_info()
            _park(debug, com_address(info, ready), qemu=True)
            _settle_boot_events(debug)
            debug.video_frame_start()
            assert debug.video_frame_advance()['advance_completed']
            sample = debug.observe_int33_mouse()
            frame = sample['raster']
            selection = dict(stream=frame['stream'], frame_id=frame['frame_id'])
            with pytest.raises(ValueError, match='observed landing'):
                debug.mouse_click_int33(160, 88, **selection)
            assert debug.input_state()['pending_edges'] == 0
            stop_offset = {'breakpoint': pressed, 'release_breakpoint': released}.get(case)
            stop = None if stop_offset is None else debug.breakpoint(com_address(info, stop_offset))
            result = debug.mouse_click_int33(159, 88, **selection)
            assert result['outcome'] == outcome, result
            assert result['complete'] is (case == 'complete')
            assert result['press']['execution']['input_delivery']['delivery'] == 'qmp_accepted'
            if stop is not None:
                phase = 'press' if case == 'breakpoint' else 'release'
                original = result[phase]['execution']['session']['stop_reason']
                assert original['breakpoint_ids'] == [stop['breakpoint_id']]
                assert result[phase]['observed'] is None
                debug.delete_breakpoint(stop['breakpoint_id'])
            if case in ('complete', 'release_breakpoint'):
                assert result['press']['observed']['buttons'] == 1
                assert result['release']['execution']['input_delivery']['delivery'] == 'qmp_accepted'
                assert result['press']['observed_edge_at_target'] is True
                assert result['lease_state'] is None and not debug.input_state()['leases']
                if case == 'complete':
                    assert result['effect'] == 'press_and_release_observed'
                    assert result['release']['observed_edge_at_target'] is True
                    live = result['release']['observed']
                    assert live['buttons'] == 0
                    assert live['button_edges']['release']['left'] == dict(count=1, last_position=[318, 88])
                else:
                    assert result['effect'] == 'press_observed'
            else:
                assert result['release'] is None
                assert result['next_action'] == 'release_owned_button'
                assert result['lease_state']['make'] == 'qmp_accepted'
                assert result['lease_state']['release'] is None
                assert debug.input_state()['pending_edges'] == 0
                if case in ('warp', 'consumed'):
                    live = result['press']['observed']
                    assert live['buttons'] == 1
                    assert live['button_edges']['release']['left']['count'] == 0
                    if case == 'warp':
                        assert result['press']['observed_edge_at_target'] is True
                        assert live['position'] == [300, 80]
                        assert live['button_edges']['press']['left']['last_position'] == [318, 88]
                    else:
                        assert live['button_edges']['press']['left']['count'] == 0
                debug.mouse_button_up(result['lease'])
                debug.clock_advance(50_000_000)
                assert debug.observe_int33_mouse()['buttons'] == 0
                assert not debug.input_state()['leases']
            assert debug.capabilities['absolute_mouse'] is False
            proc = debug.vm.process
        assert proc.poll() is not None
    assert binary.read_bytes() == code
    (tmp_path / 'int33-observed-click.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')


@pytest.mark.parametrize('route', ['python', 'rpc', 'json', 'frame', 'partial'])
def test_coordinate_click_routes_verify_landing_and_hold(
        tmp_path, clock_runtime, clock_disk, mouse_inputs, route):
    from fdisbull.cli import respond
    from fdisbull.debugger import DebugWorkspace

    baseline = prepare_mouse_disk(clock_disk['image'], tmp_path / 'mouse-boot.img',
                                  mouse_inputs['driver'], clock_runtime['mcopy'])
    code = assemble(tmp_path, 'coordinate-click-route', '%define CASE 0\n' + _CLICK_ASSEMBLY,
                    clock_runtime['nasm'])
    ready, pressed, _ = struct.unpack('<3H', code[-6:])
    binary = tmp_path / 'ROUTE.COM'
    binary.write_bytes(code)
    options = launch_options(clock_runtime, baseline, qemu_clock='virtual', qemu_retrace='precise')
    with Project.create(tmp_path / 'route.fdb', binary, image='com') as project:
        project.analyze(max_instructions=4096)
        with project.debugger(str(clock_runtime['executable']), tmp_path, **options) as debug:
            info = debug.dos_process_info()
            _park(debug, com_address(info, ready), qemu=True)
            _settle_boot_events(debug)
            debug.video_frame_start()
            assert debug.video_frame_advance()['advance_completed']
            first = debug.call('video.screenshot', {'encoding': 'png'})
            assert debug.video_frame_advance()['advance_completed']
            selected = debug.call('video.screenshot', {'encoding': 'png'})
            assert first['mode_id'] == selected['mode_id'] and first['frame_id'] < selected['frame_id']
            ids = {key: selected[key] for key in ('session_id', 'mode_id', 'frame_id')}
            initial = debug.observe_int33_mouse()
            scenarios = [
                (dict(ids, delivery=None), 'explicit delivery'),
                (dict(ids, session_id='0' * 32), 'STALE_SESSION'),
                (dict(ids, mode_id=ids['mode_id'] + 1), 'STALE_MODE'),
                (dict(ids, frame_id=first['frame_id']), 'STALE_FRAME'),
            ]
            for selection, reason in scenarios:
                selection.setdefault('delivery', 'observed-int33')
                with pytest.raises(ValueError, match=reason):
                    debug.click(160, 90, **selection)
            with pytest.raises(ValueError, match='four physical counts'):
                debug.click(160, 110, delivery='observed-int33', **ids)
            assert debug.observe_int33_mouse()['clock'] == initial['clock']
            assert debug.input_state()['pending_edges'] == 0
            options = dict(x=160, y=90, delivery='observed-int33', hold_ms=15, **ids)
            if route == 'partial':
                point = debug.breakpoint(com_address(info, pressed))
            if route in ('json', 'frame', 'partial'):
                workspace = DebugWorkspace()
                workspace.sessions[debug.run_id] = debug
                method = 'debug-click-frame' if route == 'frame' else 'debug-click'
                request = dict(id=1, method=method, params=dict(project=str(project.path),
                               run=debug.run_id, **options))
                reply = respond(request, debugger=workspace)
                assert reply['ok'], reply
                result = reply['result']
                workspace.sessions.clear()
            elif route == 'rpc':
                result = debug.call('input.mouse.click', options)
            else:
                result = debug.click(**options)
            assert result['format'] == 'fdisbull-qemu-coordinate-click-1'
            assert result['source']['frame_id'] == selected['frame_id']
            assert result['target_landing']['position'] == [320, 90]
            assert result['motion']['counts'] == [2, 4]
            if route == 'frame':
                assert result['frame_phase'] == 'before_observed_input'
                assert result['frame']['metadata']['frame_id'] == selected['frame_id']
                assert result['frame']['metadata']['mode_id'] == selected['mode_id']
                assert result['frame']['metadata']['coordinate_grid']['target'] == [160, 90]
            click = result['click']
            if route == 'partial':
                assert not result['complete'] and result['outcome'] == 'competing_stop'
                assert result['next_action'] == 'release_owned_button'
                assert click['hold'] is None and click['release'] is None
                reason = click['press']['execution']['session']['stop_reason']
                assert reason['breakpoint_ids'] == [point['breakpoint_id']]
                debug.delete_breakpoint(point['breakpoint_id'])
                debug.mouse_button_up(click['lease'])
                debug.clock_advance(50_000_000)
                assert debug.observe_int33_mouse()['buttons'] == 0
            else:
                assert result['complete'] and result['effect'] == 'press_and_release_observed'
                assert click['verified_hold_ns'] >= 15_000_000
                assert click['press']['observed_edge_at_target'] and click['release']['observed_edge_at_target']
                assert click['release']['observed']['buttons'] == 0
            assert not debug.input_state()['leases']
            assert debug.capabilities['absolute_mouse'] is False
            native_process = debug.vm.process
        assert native_process.poll() is not None
    assert binary.read_bytes() == code
    (tmp_path / 'coordinate-click-route.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
