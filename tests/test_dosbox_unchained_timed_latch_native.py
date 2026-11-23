"""Native two-page witness for the DOSBox-X VGA display-start latch.

Select the source diagnostic with FDISBULL_DOSBOX_FRAME_SOURCE and its exact
FDISBULL_DOSBOX_FRAME_SOURCE_SHA256. Set NASM and opt in with
FDISBULL_REQUIRE_DOSBOX_FRAME_SOURCE=1. See native/dosbox-vga-source-diagnostic.

Guest PIT channel 2 and VGA status reads bracket the actual CRTC OUT. The
receipt binds the observed edge and stopped instruction to each subsequent
completed renderer frame and its full original source indices. Page data and
its DAC setup are held throughout both measured writes.
"""
import base64
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time

import pytest

from support.dos_process_fixture import assemble, digest
from test_dosbox_frame_source_probe_native import _DiagnosticRPC, _pixels, _time
from test_paired_video_frame_native import PROFILE
from test_qemu_vga_unchained_probe_native import BODY


_WITNESS = r'''
page_a:
    nop
    in al,61h
    and al,0fch
    out 61h,al
    mov al,0b4h
    out 43h,al
    xor al,al
    out 42h,al
    out 42h,al
    in al,61h
    and al,0fch
    or al,1
    out 61h,al
hold:
    cmp byte [command],0
    je hold
    mov al,[command]
    mov byte [command],0
    mov word [period],0
    mov word [following],0
    cmp al,1
    je early
    cmp al,2
    jne fault
    mov word [requested],400ch
    call new_rise
    mov [edge],ax
    jmp commit

early:
    mov word [requested],800ch
    call new_rise
    mov [edge],ax
    call new_rise
    mov bx,[edge]
    mov [edge],ax
    sub bx,ax
    cmp bx,16000
    jb fault
    cmp bx,18000
    ja fault
    mov [period],bx
    sub bx,192
    mov ecx,200000
.wait:
    dec ecx
    jz fault
    call pit_read
    mov si,[edge]
    sub si,ax
    cmp si,18000
    ja fault
    cmp si,bx
    jb .wait
commit:
    mov dx,3dah
    in al,dx
    mov [pre_status],al
    call pit_read
    mov [pre_count],ax
    mov dx,3d4h
    mov ax,[requested]
write_start:
    out dx,ax
    call pit_read
    mov [post_count],ax
    mov dx,3dah
    in al,dx
    mov [post_status],al
    cmp word [requested],800ch
    jne .done
    call new_rise
    mov [following],ax
.done:
    inc byte [completed]
    jmp hold

pit_read:
    mov al,80h
    out 43h,al
    in al,42h
    mov ah,al
    in al,42h
    xchg al,ah
    ret

new_rise:
    mov dx,3dah
    mov ecx,200000
.wait_low:
    dec ecx
    jz fault
    in al,dx
    test al,8
    jnz .wait_low
.wait_high:
    dec ecx
    jz fault
    in al,dx
    test al,8
    jz .wait_high
    jmp pit_read

fault:
    mov ax,4c01h
    int 21h
'''


def _guest():
    setup, remaining = BODY.split('page_a:\n', 1)
    _, helpers = remaining.split('\nsequencer:')
    helper, _ = ('\nsequencer:' + helpers).split("    db 'UVGA'")
    report = """
report:
edge: dw 0
period: dw 0
pre_count: dw 0
post_count: dw 0
following: dw 0
pre_status: db 0
post_status: db 0
completed: db 0
command: db 0
requested: dw 0
db 'LVGA'
dw hold,write_start,report,command
"""
    return setup + _WITNESS + helper + report


def _delta(earlier, later):
    return (earlier - later) & 0xffff


def test_dosbox_unchained_vga_latches_before_and_after_retrace(tmp_path):
    if os.environ.get('FDISBULL_REQUIRE_DOSBOX_FRAME_SOURCE') != '1':
        pytest.skip('Requires an exact retained-source DOSBox diagnostic')
    binary = Path(os.environ['FDISBULL_DOSBOX_FRAME_SOURCE']).resolve(strict=True)
    runtime_sha = os.environ['FDISBULL_DOSBOX_FRAME_SOURCE_SHA256']
    assert digest(binary) == runtime_sha
    work = tmp_path / 'game'
    work.mkdir()
    code = assemble(tmp_path, 'latch-witness', _guest(), os.environ['NASM'])
    assert code[-12:-8] == b'LVGA'
    hold, out, report, command = struct.unpack('<4H', code[-8:])
    assert code[out-0x100:out-0x100+1] == b'\xef'
    guest = work / 'LATCH.COM'
    guest.write_bytes(code)
    wrapper = tmp_path / 'dosbox-latch'
    args = [part for setting in PROFILE for part in ('-set', setting)]
    wrapper.write_text(f'#!{sys.executable}\nimport os, sys\n'
        "os.environ.update(SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='dummy')\n"
        f'os.execv({str(binary)!r}, [{str(binary)!r}, *sys.argv[1:], *{args!r}])\n')
    wrapper.chmod(0o700)
    deadline = time.monotonic() + 25
    receipt = dict(backend_sha256=runtime_sha, authored_com_sha256=digest(guest), trials=[])

    def budget():
        remaining = int((deadline - time.monotonic()) * 1000)
        assert remaining > 0, 'Latch fixture exceeded its owner deadline'
        return min(remaining, 5000)

    try:
        with closing(_DiagnosticRPC(wrapper, work)) as rpc:
            owner = rpc.process
            sid = rpc.call('session.start', {'target': {'command':'LATCH.COM', 'arguments':[]},
                'mounts':[{'drive':'C','host_path':str(work)}], 'break_at':'entry'}, timeout_ms=budget())['session_id']

            def call(method, **params):
                return rpc.call(method, {'session_id': sid, **params}, timeout_ms=budget())

            start_cpu = call('state.get_registers')
            assert start_cpu['cpu_mode'] == 'real' and int(start_cpu['instruction_pointer'], 16) == 0x100
            cs = start_cpu['segments']['cs']

            def address(offset):
                return {'space':'segmented', 'segment':cs, 'offset':f'0x{offset:08x}'}

            def read(offset, length):
                value = call('memory.read', address=address(offset), length=length)
                return base64.b64decode(value['data_base64'], validate=True)

            def park(offset):
                point = call('breakpoints.create', kind='execution', once=True, address=address(offset))
                operation = call('execution.continue')['operation_id']
                for _ in range(20):
                    state = call('execution.wait', operation_id=operation, timeout_ms=min(250, budget()))
                    if not state.get('running'):
                        break
                assert not state.get('running') and state['stop_reason']['kind'] == 'breakpoint', state
                assert state['stop_reason']['breakpoint_id'] == point['breakpoint_id'], state
                cpu = call('state.get_registers')
                assert int(cpu['instruction_pointer'],16) == offset and cpu['segments']['cs'] == cs
                return cpu

            def source(frame):
                identity = {key:frame[key] for key in ('frame_id','mode_id')}
                observed = call('video.probe', points=[], source_indices=True, **identity)
                assert all(observed[k] == v for k,v in identity.items())
                if not observed['source_indices_available']:
                    return None
                proof = dict(observed['frame_source'])
                pixels = base64.b64decode(proof.pop('indices_base64'), validate=True)
                origin = proof['latched_crtc_start']
                assert origin in (0x4000, 0x8000)
                assert proof['first_row_address'] == proof['selected_draw_address'] == origin * 4
                assert pixels == _pixels(1 if origin == 0x4000 else 5)
                assert proof['indices_bytes'] == len(pixels) == 64000
                assert proof['indices_sha256'] == hashlib.sha256(pixels).hexdigest()
                return dict(**identity, **proof, captured_ticks=observed['captured_ticks'])

            def advance():
                value = call('frame.step')
                assert value['completed'] is True and value['stop_reason']['kind'] == 'frame', value
                assert value['boundary'] == 'completed_renderer_frame_then_safe_fetch'
                return value

            call('execution.timing', fast_forward=False)
            park(hold)
            advance()
            assert source(advance()) is None
            advance()
            settled = source(advance())
            assert settled and settled['latched_crtc_start'] == 0x4000
            receipt['settled'] = settled

            for number, old, new in ((1,0x4000,0x8000),(2,0x8000,0x4000)):
                arm = call('memory.read', address=address(command), length=1)
                assert base64.b64decode(arm['data_base64'], validate=True) == b'\0'
                call('memory.write', address=address(command), expected_sha256=arm['sha256'],
                     data_base64=base64.b64encode(bytes([number])).decode('ascii'))
                cpu = park(out)
                trial = dict(phase='before' if number==1 else 'after', old=old, requested=new,
                             observations=[])
                receipt['trials'].append(trial)
                assert int(cpu['general']['eax'],16) & 65535 == new | 0x0c
                assert int(cpu['general']['edx'],16) & 65535 == 0x03d4
                open_frame = call('video.probe', points=[])
                pre = trial['pre'] = source(open_frame)
                assert pre and pre['latched_crtc_start'] == old
                trial['write_guest_ticks'] = call('execution.timing')['guest_ticks']
                step = call('execution.step', mode='into')
                assert step['stop_reason']['kind'] == 'step'
                assert int(call('state.get_registers')['instruction_pointer'],16) == out+1
                after = trial['just_after'] = source(call('video.probe', points=[]))
                assert after == pre
                previous = pre
                for _ in range(3):
                    current = source(advance())
                    assert current and current['frame_id'] == previous['frame_id']+1
                    assert _time(current) > _time(previous)
                    trial['observations'].append(current)
                    previous=current
                    if current['latched_crtc_start'] == new:
                        break
                report_values = struct.unpack('<5H3B', read(report,13))
                edge, period, started, ended, following, before_status, after_status, completed = report_values
                trial['guest'] = dict(edge=edge, period=period, before_out=started, after_out=ended,
                    following=following, pre_status=before_status, post_status=after_status, completed=completed,
                    out_bracket_pit_ticks=_delta(started,ended), since_sampled_rise=_delta(edge,started))
                assert completed == number and _delta(started,ended)<96, trial['guest']
                if number == 1:
                    assert not ((before_status | after_status)&8), trial['guest']
                    remaining = _delta(ended,following)
                    trial['guest']['after_out_until_rise_pit_ticks'] = remaining
                    assert 15 <= remaining <= 400, trial['guest']
                    assert 16000 <= _delta(edge,following) <= 18000
                else:
                    assert before_status & after_status & 8, trial['guest']
                    assert _delta(edge,started) < 100, trial['guest']
                trial['latched_sequence'] = [row['latched_crtc_start'] for row in trial['observations']]
            receipt['owners_reaped'] = True
    finally:
        if 'owner' in locals():
            receipt['owner_returncode'] = owner.poll()
        assert guest.read_bytes() == code and digest(binary) == runtime_sha
        (tmp_path/'timed-latch-receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n')

    assert owner.poll() == 0
    assert [trial['latched_sequence'] for trial in receipt['trials']] == [[0x8000],[0x8000,0x4000]]
