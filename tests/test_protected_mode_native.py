"""Real DOS protected-mode input proof; RAM/full-checkpoint gates are separate.

Uses an authored COM that temporarily remaps CPU linear page zero. A successful
queue receipt is followed by actual INT33 samples in the program, then a guest
clock release. No GUI automation, original game assets, or mocked CPU is used.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC


SOURCE = Path(__file__).with_name('fixtures') / 'protected_mode_mouse.S'
FIXTURE_SHA256 = '7d24c97b21b317e2f53d70714003ee16dce4e34f0777a18420f70c37a9f9d4c2'


def assemble_fixture(directory):
    """GNU ELF tools on Linux; explicitly selected GNU PE tools on macOS."""
    assembler = os.environ.get('FDISBULL_AS') or shutil.which('as')
    linker = os.environ.get('FDISBULL_LD') or shutil.which('ld')
    if not assembler or not linker:
        pytest.fail('Protected-mode native acceptance requires GNU as and ld')
    version = subprocess.check_output([assembler, '--version'], text=True)
    if 'GNU assembler' not in version:
        pytest.fail('Set FDISBULL_AS/FDISBULL_LD to GNU x86 binutils')
    obj, raw = directory / 'protected.o', directory / 'protected.bin'
    subprocess.run([assembler, '--32', str(SOURCE), '-o', str(obj)],
                   check=True, capture_output=True, text=True)
    if 'mingw' in version:
        objcopy = os.environ.get('FDISBULL_OBJCOPY') or shutil.which('objcopy')
        if not objcopy:
            pytest.fail('GNU PE assembly also requires FDISBULL_OBJCOPY')
        exe = directory / 'protected.exe'
        subprocess.run([linker, '-m', 'i386pe', '--image-base', '0',
                        '--section-start', '.text=0', '--file-alignment', '1',
                        '--section-alignment', '1', '-e', '_start', str(obj),
                        '-o', str(exe)], check=True, capture_output=True, text=True)
        subprocess.run([objcopy, '-O', 'binary', '-j', '.text', str(exe), str(raw)],
                       check=True, capture_output=True, text=True)
    else:
        subprocess.run([linker, '-m', 'elf_i386', '--oformat', 'binary',
                        '-Ttext', '0', '-e', '_start', str(obj), '-o', str(raw)],
                       check=True, capture_output=True, text=True)
    data = raw.read_bytes()[0x100:]
    assert hashlib.sha256(data).hexdigest() == FIXTURE_SHA256
    binary = directory / 'PMMOUSE.COM'
    binary.write_bytes(data)
    return binary


def test_real_protected_paged_mouse_queue_then_program_consumption_and_release(tmp_path):
    backend = os.environ.get('FDISBULL_DOSBOX')
    if not backend:
        pytest.skip('Set FDISBULL_DOSBOX for native protected-mode acceptance')
    binary = assemble_fixture(tmp_path)
    report = {'fixture_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'stages': []}
    rpc = None
    try:
        rpc = DOSBoxRPC(backend, tmp_path)
        started = rpc.call('session.start', {
            'target': {'command': binary.name, 'arguments': []},
            'mounts': [{'drive': 'C', 'host_path': str(tmp_path)}], 'break_at': 'entry'})
        sid = started['session_id']

        def call(method, params=None):
            return rpc.call(method, {'session_id': sid, **(params or {})})

        def read(space, address, size):
            result = call('memory.read', {'address': {'space': space,
                          'offset': f'0x{address:08X}'}, 'length': size})
            data = base64.b64decode(result['data_base64'], validate=True)
            assert len(data) == size and hashlib.sha256(data).hexdigest() == result['sha256']
            return data

        def advance(seconds):
            call('execution.continue')
            time.sleep(seconds)
            pause = call('execution.pause')
            stopped = call('execution.wait', {'operation_id': pause['operation_id'],
                                              'timeout_ms': 3000})
            assert not stopped.get('running') and stopped['stop_reason']['kind'] == 'pause'
            return stopped

        def trace(count):
            call('trace.start', {'detail': 'normal', 'instruction_count': count})
            operation = call('execution.continue')
            stopped = call('execution.wait', {'operation_id': operation['operation_id'],
                                              'timeout_ms': 3000})
            assert not stopped.get('running')
            events = call('trace.read', {'cursor': None, 'limit': count})['events']
            assert len(events) == count
            return events

        entry = call('state.get_registers')
        assert entry['cpu_mode'] == 'real'
        assert entry['address_context']['paging_enabled'] is False
        physical = int(entry['segments']['cs'], 16) * 16
        report['stages'].append({'entry_context': entry['address_context']})
        checkpoint = call('breakpoints.create', {'kind': 'execution', 'once': False,
                          'address': {'space': 'segmented', 'segment': entry['segments']['cs'],
                                      'offset': '0x00000500'}})
        call('execution.timing', {'fast_forward': False})
        real_trace = trace(2)
        assert all(event['cpu_mode'] == 'real' and event['code_bits'] == 16 for event in real_trace)
        advance(.15)
        stopped = call('state.get_registers')
        context = stopped['address_context']
        assert stopped['cpu_mode'] == context['cpu_mode'] == 'protected'
        assert context['paging_enabled'] is True and int(context['cr0'], 16) & 0x80000001 == 0x80000001
        assert int(context['cr3'], 16) != 0 and context['a20_enabled'] is True
        assert context['code_bits'] == context['stack_bits'] == 32
        assert read('physical', physical + 0x600, 1) == b'\x01'
        retained = call('trace.read', {'cursor': None, 'limit': 2})['events']
        assert retained == real_trace  # Historical real-mode records survive a protected stop.
        protected_trace = trace(8)
        assert all(event['cpu_mode'] == 'protected' and event['code_bits'] == 32
                   and event['stack_bits'] == 32 for event in protected_trace)
        assert all('address_context' not in event for event in protected_trace)
        physical_ivt, linear_ivt = read('physical', 0xCC, 4), read('linear', 0xCC, 4)
        assert physical_ivt != linear_ivt
        report['stages'].append({'protected_context': context,
                                 'physical_ivt_differs_from_cpu_linear': True})
        assert call('input.mouse.state')['mouse']['buttons'] == 0
        frame = call('video.probe', {'points': []})
        assert (frame['width'], frame['height']) == (320, 200)
        queued_at = call('execution.timing')['guest_ticks']
        click = call('input.mouse.click', {'x': 160, 'y': 99, 'button': 'left', 'hold_ms': 1000,
                                          'mode_id': frame['mode_id'], 'frame_id': frame['frame_id']})
        assert click['accepted'] is True and click['delivery'] == 'queued'
        assert click['mouse']['buttons'] == click['mouse']['owned_buttons'] == 1
        assert click['mouse']['release_pending'] is True
        report['stages'].append({'protected_click': click})
        control = physical + 0x601
        old = read('physical', control, 1)
        call('memory.write', {'address': {'space': 'physical', 'offset': f'0x{control:08X}'},
                             'data_base64': base64.b64encode(b'\x01').decode('ascii'),
                             'expected_sha256': hashlib.sha256(old).hexdigest()})
        operation = call('execution.continue')
        stopped = call('execution.wait', {'operation_id': operation['operation_id'], 'timeout_ms': 3000})
        assert not stopped.get('running') and stopped['stop_reason']['kind'] == 'breakpoint'
        assert stopped['stop_reason']['breakpoint_id'] == checkpoint['breakpoint_id']
        sample = read('physical', physical + 0x600, 8)
        assert sample[0] == 2
        assert struct.unpack_from('<HHH', sample, 2) == (1, 320, 99)
        returned = call('state.get_registers')['address_context']
        assert returned['cpu_mode'] == 'real' and returned['paging_enabled'] is False
        assert returned['code_bits'] == returned['stack_bits'] == 16
        retained = call('trace.read', {'cursor': None, 'limit': 8})['events']
        assert retained == protected_trace  # Never relabel old protected records from this real stop.
        report['stages'].append({'program_observed': {'left_button': True, 'x': 320, 'y': 99},
                                 'returned_context': returned,
                                 'trace_modes_retained_across_both_transitions': True})
        call('breakpoints.delete', {'breakpoint_id': checkpoint['breakpoint_id']})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            advance(.1)
            mouse = call('input.mouse.state')['mouse']
            if not mouse['release_pending']:
                break
        assert mouse['buttons'] == mouse['owned_buttons'] == 0 and not mouse['release_pending']
        elapsed = call('execution.timing')['guest_ticks'] - queued_at
        assert elapsed >= 1000
        report['stages'].append({'release_guest_ms': elapsed, 'mouse': mouse})
        report['passed'] = True
    finally:
        if rpc is not None:
            rpc.close()
            report['reaped'] = rpc.process.poll() is not None
        (tmp_path / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
