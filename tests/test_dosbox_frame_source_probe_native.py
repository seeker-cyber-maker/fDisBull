"""Native DOSBox-X selected VGA page and original index witness."""
import base64
from contextlib import closing
from fractions import Fraction
import hashlib
import os
from pathlib import Path
import struct
import sys
import time

import pytest

from fdisbull import qemu_machine
from fdisbull.dosbox_rpc import DOSBoxRPC, DebuggerError
from fdisbull.project import Project
from support.dos_process_fixture import assemble, digest
from test_paired_video_frame_native import PROFILE
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_vga_unchained_probe_native import BODY, RENDER_PROOF


def _held_pages():
    # Keep the same two plane layouts while holding each page long enough for
    # DOSBox-X to latch and draw it. The host releases A only after its receipt.
    first = 'page_a:\n    nop\n'
    last = 'page_b:\n    nop\n'
    tail = '    db \'UVGA\'\n    dw chain4,page_a,page_b,wrapping,restored_page'
    assert all(BODY.count(anchor) == 1 for anchor in (first, last, tail))
    before, following = BODY.split(last)
    _, helpers = following.split('\nsequencer:')
    return (before.replace(first, first + '    cmp byte [go],0\n    je page_a\n')
            + last + '    jmp page_b\n\nsequencer:'
            + helpers.replace(tail, "go: db 0\n    db 'SVGA'\n    dw page_a,page_b,go"))


class _DiagnosticRPC(DOSBoxRPC):
    limit = 96 * 1024


def _pixels(first):
    row = bytes(range(first, first + 4)) * 80
    last = bytes(range(first + 8, first + 12)) * 80
    return row * 199 + last


def _time(frame_source):
    ticks = frame_source['selected_ticks']
    cycles = frame_source['selected_tick_cycles']
    divisor = frame_source['cycles_per_tick']
    assert ticks >= 0 and cycles >= 0 and divisor > 0
    return ticks + Fraction(cycles, divisor)


def test_native_dosbox_source_probe_binds_exact_selected_pages_and_original_indices(tmp_path):
    if os.environ.get('FDISBULL_REQUIRE_DOSBOX_FRAME_SOURCE') != '1':
        pytest.skip('Select a private DOSBox-X source diagnostic build')
    executable = Path(os.environ['FDISBULL_DOSBOX_FRAME_SOURCE']).resolve(strict=True)
    assert digest(executable) == os.environ['FDISBULL_DOSBOX_FRAME_SOURCE_SHA256']
    assert not any((directory / '.git').exists() for directory in
                   (tmp_path.resolve(), *tmp_path.resolve().parents))
    work = tmp_path / 'game'
    work.mkdir()
    code = assemble(tmp_path, 'dosbox-source-pages', _held_pages(), os.environ['NASM'])
    assert code[-10:-6] == b'SVGA'
    page_a, page_b, go = struct.unpack('<3H', code[-6:])
    game = work / 'PLANES.COM'
    game.write_bytes(code)
    wrapper = tmp_path / 'diagnostic-dosbox'
    arguments = [part for setting in PROFILE for part in ('-set', setting)]
    wrapper.write_text(f'#!{sys.executable}\nimport os, sys\n'
        "os.environ.update(SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='dummy')\n"
        f'os.execv({str(executable)!r}, [{str(executable)!r}, *sys.argv[1:], *{arguments!r}])\n')
    wrapper.chmod(0o700)
    deadline = time.monotonic() + 35

    def budget():
        remaining = int((deadline - time.monotonic()) * 1000)
        assert remaining > 0, 'Source diagnostic exceeded its owner deadline'
        return min(remaining, 5000)

    with closing(_DiagnosticRPC(wrapper, work)) as rpc:
        owner = rpc.process
        assert rpc.capabilities['limits']['max_message_bytes'] == rpc.limit
        started = rpc.call('session.start', {
            'target': {'command': 'PLANES.COM', 'arguments': []},
            'mounts': [{'drive': 'C', 'host_path': str(work)}], 'break_at': 'entry'},
            timeout_ms=budget())
        sid = started['session_id']

        def call(method, **params):
            return rpc.call(method, {'session_id': sid, **params}, timeout_ms=budget())

        registers = call('state.get_registers')
        assert registers['cpu_mode'] == 'real' and int(registers['instruction_pointer'], 16) == 0x100
        cs = registers['segments']['cs']

        def address(offset):
            return {'space': 'segmented', 'segment': cs, 'offset': f'0x{offset:08x}'}

        def park(offset):
            point = call('breakpoints.create', kind='execution', once=True, address=address(offset))
            operation = call('execution.continue')['operation_id']
            for _ in range(40):
                state = call('execution.wait', operation_id=operation, timeout_ms=min(250, budget()))
                if not state.get('running'):
                    break
            assert state['state'] == 'stopped' and not state.get('running')
            assert state['stop_reason']['breakpoint_id'] == point['breakpoint_id']
            assert int(call('state.get_registers')['instruction_pointer'], 16) == offset

        def step():
            value = call('frame.step')
            assert value['completed'] is True and value['stop_reason']['kind'] == 'frame'
            return {name: value[name] for name in ('frame_id', 'mode_id')}

        def prove(identity, origin, first):
            observation = call('video.probe', points=[], source_indices=True, **identity)
            matching = {name: observation[name] for name in identity}
            assert matching == identity
            assert observation['source_indices_available'] is True, matching
            assert (observation['width'], observation['height']) == (320, 200)
            proof = observation['frame_source']
            assert proof['model'] == 'dosbox-vga-source-indices-v1'
            assert proof['latched_crtc_start'] == origin
            assert proof['selected_draw_address'] == proof['first_row_address'] == origin * 4
            raw = base64.b64decode(proof['indices_base64'], validate=True)
            assert len(raw) == proof['indices_bytes'] == 64000
            assert raw == _pixels(first)
            assert hashlib.sha256(raw).hexdigest() == proof['indices_sha256']
            return proof

        call('execution.timing', fast_forward=False)
        park(page_a)
        step()
        identity = step()
        ordinary = call('video.probe', points=[], **identity)
        assert 'source_indices_available' not in ordinary and 'frame_source' not in ordinary
        assert call('video.probe', points=[], source_indices=True,
                    **identity)['source_indices_available'] is False
        step()
        first_identity = step()
        a = prove(first_identity, 0x4000, 1)
        with pytest.raises(DebuggerError, match='STALE_FRAME'):
            call('video.probe', points=[], source_indices=True,
                 frame_id=first_identity['frame_id'] - 1, mode_id=first_identity['mode_id'])

        flag = call('memory.read', address=address(go), length=1)
        assert base64.b64decode(flag['data_base64'], validate=True) == b'\0'
        call('memory.write', address=address(go), expected_sha256=flag['sha256'], data_base64='AQ==')
        park(page_b)
        step()
        second_identity = step()
        b = prove(second_identity, 0x8000, 5)
        assert second_identity['frame_id'] > first_identity['frame_id'] and _time(b) > _time(a)
        assert call('video.probe', points=[], source_indices=False,
                    **second_identity)['source_indices_available'] is False

    assert owner.poll() is not None and game.read_bytes() == code


def test_native_qemu_renders_the_same_held_page_fixture(
        tmp_path, clock_runtime, clock_disk, monkeypatch, record_property):
    if os.environ.get('FDISBULL_REQUIRE_QEMU_UNCHAINED_RENDER_PROOF') != '1':
        pytest.skip('Select a QEMU with unchained renderer-source proof')
    code = assemble(tmp_path, 'qemu-source-pages', _held_pages(), clock_runtime['nasm'])
    assert code[-10:-6] == b'SVGA'
    page_a, page_b, go = struct.unpack('<3H', code[-6:])
    binary = tmp_path / 'PLANES.COM'
    binary.write_bytes(code)
    record_property('authored_com_sha256', digest(binary))

    original = qemu_machine.machine_retrace_arguments
    monkeypatch.setattr(qemu_machine, 'machine_retrace_arguments',
        lambda profile: original(profile) + ['-global', 'VGA.x-fdisbull-raster-proof=on'])
    with Project.create(tmp_path / 'planes.fdb', binary, image='com') as project:
        with project.debugger(clock_runtime['executable'], tmp_path,
                **launch_options(clock_runtime, clock_disk, qemu_clock='virtual',
                                 qemu_retrace='precise')) as debug:
            owner = debug.vm.process
            info = process_record(debug)
            for position, origin, first in ((page_a, 0x4000, 1), (page_b, 0x8000, 5)):
                park(debug, com_address(info, position))
                proof = debug.vm.qmp.call(RENDER_PROOF)
                assert proof['outcome'] == 'updated' and proof['current-configuration-matches'], proof
                source = proof['source']
                assert source['start-address'] == origin * 4
                assert source['source-index-sha256'] == hashlib.sha256(_pixels(first)).hexdigest()
                if position == page_a:
                    debug.write_memory(com_address(info, go), '01', expected_hex='00')
        assert owner.poll() == 0
    assert binary.read_bytes() == code and digest(clock_disk['image']) == clock_disk['prepared_sha256']
