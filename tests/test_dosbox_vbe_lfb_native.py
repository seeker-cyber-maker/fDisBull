"""Native DOSBox-X oracle for protected-mode access to the VBE 101h LFB."""

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
from support.paired_vbe_lfb import (
    BANK_BYTES, HEIGHT, MODE_INFO_BYTES, MODE_RESULTS, ORIGIN, PITCH, PROBE_OFFSETS,
    RESULT_BYTES, SOURCE, VARIANTS, WIDTH,
    expected_rgb, expected_vram, labels, mode_info, mode_results, results,
)
from test_paired_video_frame_native import PROFILE


PROFILE_LFB = (*PROFILE, 'video vmemsize=16')


def _observe(rpc, directory, offsets, report):
    sid = rpc.call('session.start', {
        'target': {'command': 'LFB.COM', 'arguments': []},
        'mounts': [{'drive': 'C', 'host_path': str(directory)}],
        'break_at': 'entry',
    })['session_id']

    def call(method, **options):
        return rpc.call(method, {'session_id': sid, **options}, timeout_ms=5000)

    initial = call('state.get_registers')
    assert initial['cpu_mode'] == 'real'
    cs = initial['segments']['cs']
    base = int(cs, 16) * 16

    def linear(label):
        return f'0x{base + offsets[label]:08x}'

    def read(label, length):
        address = {'space': 'physical', 'offset': linear(label)}
        packet = call('memory.read', address=address, length=length)
        data = b64decode(packet['data_base64'], validate=True)
        assert len(data) == length and sha256(data).hexdigest() == packet['sha256']
        return data

    def advance(old, new):
        assert read('pm_go', 1) == bytes([old])
        call('memory.write', address={'space': 'linear', 'offset': linear('pm_go')},
             expected_sha256=sha256(bytes([old])).hexdigest(),
             data_base64=b64encode(bytes([new])).decode('ascii'))

    def park(label, mode='protected'):
        # The breakpoint is resolved against the current segment cache.
        protected = call('state.get_registers')['cpu_mode'] == 'protected'
        segment, location = ('0x0008', linear(label)) if protected else (cs, f'0x{offsets[label]:08x}')
        target = {'space': 'segmented', 'segment': segment, 'offset': location}
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
        pc = base + offsets[label] if mode == 'protected' else offsets[label]
        assert int(regs['instruction_pointer'], 16) == pc

    def frame(name, variant, origin=0):
        # The first completion may straddle a write or a new viewport.
        assert call('frame.step')['completed'] is True
        done = call('frame.step')
        assert done['completed'] is True, done
        payload, info = decode_screenshot(call('video.screenshot'))
        with Image.open(BytesIO(payload)) as image:
            assert image.size == (WIDTH, HEIGHT)
            rgb = image.convert('RGB').tobytes()
        assert rgb == expected_rgb(variant, origin)
        assert (info['frame_id'], info['mode_id']) == (done['frame_id'], done['mode_id'])
        report['frames'][name] = {
            'frame_id': info['frame_id'], 'mode_id': info['mode_id'],
            'origin': origin, 'pixel_sha256': sha256(rgb).hexdigest(),
        }

    call('execution.timing', fast_forward=False)
    park('pm_ready')
    info = report['mode_info'] = mode_info(read('mode_info', MODE_INFO_BYTES))
    assert (info['width'], info['height'], info['bits_per_pixel']) == (WIDTH, HEIGHT, 8)
    assert info['default_pitch'] == WIDTH
    assert info['attributes'] & 0x81 == 0x81
    lfb = unpack('<I', read('lfb_base', 4))[0]
    assert lfb == info['physical_base'] and lfb >= 0x1000000 and lfb % 0x10000 == 0
    frame('baseline', 'baseline')

    advance(0, 1)
    park('pm_update_cut')
    frame('half', 'half')
    advance(1, 2)
    park('pm_updated')
    frame('updated', 'updated')

    advance(2, 3)
    park('rm_panned', 'real')
    frame('panned', 'updated', ORIGIN)
    advance(3, 4)
    park('rm_banked', 'real')
    frame('banked', 'updated')

    mode = report['mode_results'] = mode_results(read('mode_results', MODE_RESULTS.size))
    assert (mode['linear_mode'], mode['banked_mode'] & 0x7fff) == (0x4101, 0x0101)
    assert (mode['pitch_bytes'], mode['pitch_pixels'], mode['pitch_lines']) == (PITCH, PITCH, (16 << 20) // PITCH)
    assert (mode['pan_x'], mode['pan_y']) == (5, 64)
    assert all(value == 0x004f for key, value in mode.items() if key.endswith('_ax') and key != 'linear_window_ax')
    # This S3 BIOS accepts a bank query in linear mode. SeaVGABIOS returns 034Fh.
    assert (mode['linear_window_ax'], mode['linear_window_dx']) == (0x004f, 0)
    raw = results(read('results', RESULT_BYTES))
    for variant in VARIANTS:
        vram = expected_vram(variant)
        assert raw[variant] == bytes(vram[index] for index in PROBE_OFFSETS)
    vram = expected_vram('updated')
    assert raw['banked'] == vram[BANK_BYTES - 1:BANK_BYTES + 1] + vram[2 * BANK_BYTES - 1:2 * BANK_BYTES + 1]
    report['results'] = {key: value.hex() for key, value in raw.items()}


def test_dosbox_vbe_101_linear_aperture_and_banked_roundtrip(tmp_path):
    if os.environ.get('FDISBULL_REQUIRE_DOSBOX_VBE_LFB') != '1':
        pytest.skip('Select the DOSBox-X VBE linear framebuffer reference producer')
    producer = Path(os.environ['FDISBULL_DOSBOX_VBE_PAN']).resolve(strict=True)
    producer_sha = os.environ['FDISBULL_DOSBOX_VBE_PAN_SHA256']
    assert digest(producer) == producer_sha
    code = assemble(tmp_path, 'vbe-lfb', SOURCE, os.environ['NASM'])
    offsets = labels(code)
    directory = tmp_path / 'game'
    directory.mkdir()
    binary = directory / 'LFB.COM'
    binary.write_bytes(code)
    wrapper = tmp_path / 'dosbox-vbe-lfb'
    args = [part for setting in PROFILE_LFB for part in ('-set', setting)]
    wrapper.write_text(f'#!{sys.executable}\nimport os, sys\n'
                       "os.environ.update(SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='dummy')\n"
                       f'os.execv({str(producer)!r}, [{str(producer)!r}, *sys.argv[1:], *{args!r}])\n')
    wrapper.chmod(0o700)
    report = dict(producer_sha256=producer_sha, authored_com_sha256=sha256(code).hexdigest(),
                  frames={}, profile=PROFILE_LFB)
    try:
        with closing(DOSBoxRPC(wrapper, directory)) as rpc:
            owner = rpc.process
            _observe(rpc, directory, offsets, report)
        report['owner_rc'] = owner.poll()
        assert report['owner_rc'] == 0
    finally:
        assert binary.read_bytes() == code
        (tmp_path / 'dosbox-vbe-lfb.json').write_text(json.dumps(report, indent=2) + '\n')
