"""Execute a relocated VBE protected-mode interface on native DOSBox-X."""

from base64 import b64decode, b64encode
from contextlib import closing
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
from struct import unpack
import sys

from PIL import Image
import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.screenshot_codecs import decode_screenshot
from support.dos_process_fixture import assemble, digest
from support.paired_vbe_pmi import (
    EXPECTED_BANK, EXPECTED_TIMED_RGB, HEIGHT, ORIGIN, QUERIES, QUERY, SOURCE, WIDTH,
    expected_rgb, labels, query_records,
)
from test_paired_video_frame_native import PROFILE


PROFILE_PMI = (*PROFILE, 'video vmemsize=16', 'video vbe protected mode interface=true')


def _observe(rpc, directory, offsets, report):
    sid = rpc.call('session.start', {
        'target': {'command': 'PMI.COM', 'arguments': []},
        'mounts': [{'drive': 'C', 'host_path': str(directory)}],
        'break_at': 'entry',
    })['session_id']

    def call(method, **options):
        return rpc.call(method, {'session_id': sid, **options}, timeout_ms=5000)

    initial = call('state.get_registers')
    assert initial['cpu_mode'] == 'real'
    cs = initial['segments']['cs']
    base = int(cs, 16) * 16

    def address(offset):
        return {'space': 'linear', 'offset': f'0x{base + offset:08x}'}

    def read_absolute(linear, length):
        packet = call('memory.read', address={'space': 'physical', 'offset': f'0x{linear:08x}'},
                      length=length)
        data = b64decode(packet['data_base64'], validate=True)
        assert len(data) == length and sha256(data).hexdigest() == packet['sha256']
        return data

    def read(label, length):
        return read_absolute(base + offsets[label], length)

    def advance(old, new):
        assert read('pm_go', 1) == bytes([old])
        call('memory.write', address=address(offsets['pm_go']),
             expected_sha256=sha256(bytes([old])).hexdigest(),
             data_base64=b64encode(bytes([new])).decode('ascii'))

    def park(label, mode='protected'):
        offset = offsets[label]
        # DOSBox resolves each execution breakpoint to its physical address
        # when it is created. Use the currently valid selector and offset.
        protected = call('state.get_registers')['cpu_mode'] == 'protected'
        segment, location = ('0x0008', base + offset) if protected else (cs, offset)
        target = {'space': 'segmented', 'segment': segment, 'offset': f'0x{location:08x}'}
        point = call('breakpoints.create', kind='execution', once=True, address=target)
        op = call('execution.continue')['operation_id']
        for _ in range(24):
            stop = call('execution.wait', operation_id=op, timeout_ms=250)
            if not stop.get('running'):
                break
        assert not stop.get('running') and stop['stop_reason'].get('breakpoint_id') == point['breakpoint_id'], stop
        regs = call('state.get_registers')
        context = regs['address_context']
        assert regs['cpu_mode'] == mode
        assert context['code_bits'] == context['stack_bits'] == (32 if mode == 'protected' else 16)
        assert not context['paging_enabled']
        assert int(regs['instruction_pointer'], 16) == (base + offset if mode == 'protected' else offset)
        return regs

    def screenshot(name, origin=0, *, changed=False):
        payload, info = decode_screenshot(call('video.screenshot'))
        with Image.open(BytesIO(payload)) as image:
            assert image.size == (WIDTH, HEIGHT)
            rgb = image.convert('RGB').tobytes()
        assert rgb == expected_rgb(origin, changed)
        report['frames'][name] = {
            **{key: info[key] for key in ('frame_id', 'mode_id')},
            'origin': origin, 'pixel_sha256': sha256(rgb).hexdigest(),
        }
        return report['frames'][name]

    def frame(name, origin=0, *, changed=False, settle=False):
        if settle:
            assert call('frame.step')['completed'] is True
        done = call('frame.step')
        assert done['completed'] is True, done
        retained = screenshot(name, origin, changed=changed)
        assert (retained['frame_id'], retained['mode_id']) == (done['frame_id'], done['mode_id'])

    call('execution.timing', fast_forward=False)
    park('pm_ready')
    queries = read('pmi_queries', QUERY.size * QUERIES)
    _, length, offset, segment = QUERY.unpack_from(queries)
    copied = read('pmi_copy', length)
    table = query_records(queries, copied, read('pmi_startup', QUERY.size))
    assert copied == read_absolute(segment * 16 + offset, length)
    assert table['ports'] == 0
    report['table'] = table
    bank = read('pm_result', len(EXPECTED_BANK))
    assert bank == EXPECTED_BANK
    report['bank'] = bank.hex()
    frame('baseline', settle=True)

    advance(0, 1)
    park('pm_timed_call')
    park('pm_palette_return')
    park('pm_done')
    color = read('pm_palette_capture', len(EXPECTED_TIMED_RGB))
    assert color == EXPECTED_TIMED_RGB
    report['palette'] = color.hex()
    screenshot('old-retained')
    frame('changed', changed=True)

    advance(1, 2)
    park('pm_flipped')
    frame('panned', ORIGIN, changed=True, settle=True)

    advance(2, 3)
    park('pm_timed_start_call')
    park('pm_timed_start_return')
    park('pm_restored')
    status = read('pm_status', 4)
    assert all(value in (0, 1, 9) for value in status)
    assert status[1] & status[3] & 8
    report['status'] = list(status)
    frame('zero', changed=True)

    advance(3, 4)
    park('rm_done', 'real')
    readback = unpack('<3H', read('rm_readback', 6))
    assert readback == (0x004F, 0, 0)
    report['real_readback'] = list(readback)


def test_dosbox_vbe_4f0a_relocated_protected_entries(tmp_path):
    if os.environ.get('FDISBULL_REQUIRE_DOSBOX_VBE_PMI') != '1':
        pytest.skip('Select the DOSBox-X VBE 4F0Ah reference producer')
    producer = Path(os.environ['FDISBULL_DOSBOX_VBE_PAN']).resolve(strict=True)
    producer_sha = os.environ['FDISBULL_DOSBOX_VBE_PAN_SHA256']
    assert digest(producer) == producer_sha
    code = assemble(tmp_path, 'vbe-pmi', SOURCE, os.environ['NASM'])
    offsets = labels(code)
    directory = tmp_path / 'game'
    directory.mkdir()
    binary = directory / 'PMI.COM'
    binary.write_bytes(code)
    wrapper = tmp_path / 'dosbox-vbe-pmi'
    args = [part for setting in PROFILE_PMI for part in ('-set', setting)]
    wrapper.write_text(f'#!{sys.executable}\nimport os, sys\n'
                       "os.environ.update(SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='dummy')\n"
                       f'os.execv({str(producer)!r}, [{str(producer)!r}, *sys.argv[1:], *{args!r}])\n')
    wrapper.chmod(0o700)
    report = dict(producer_sha256=producer_sha, authored_com_sha256=sha256(code).hexdigest(),
                  frames={}, profile=PROFILE_PMI)
    try:
        with closing(DOSBoxRPC(wrapper, directory)) as rpc:
            owner = rpc.process
            _observe(rpc, directory, offsets, report)
        report['owner_rc'] = owner.poll()
        assert report['owner_rc'] == 0
    finally:
        assert binary.read_bytes() == code
        (tmp_path / 'dosbox-vbe-pmi.json').write_text(json.dumps(report, indent=2) + '\n')
