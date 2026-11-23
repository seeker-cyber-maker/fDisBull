"""Native DOSBox-X reference for VBE 4F04h display-state restoration."""

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
from support.paired_vbe_state import (
    DAC8_COLOR, DAC_RESULT, HEIGHT, MUTATED_PITCH, ORIGIN, PHASE_RESULT, PHASES, PITCH,
    SIZE_MASKS, SIZE_RESULT, SOURCE, STATE_BYTES, STATE_FILL, VRAM_MUTATION,
    WIDTH, dac_probe, expected_rgb, labels, phases, sizes,
)
from test_paired_video_frame_native import PROFILE


PROFILE_STATE = tuple(setting for setting in PROFILE if setting != 'video enable 8-bit dac=false') + (
    'video enable 8-bit dac=true', 'video vmemsize=16',
)


def _observe(rpc, directory, offsets, report):
    sid = rpc.call('session.start', {
        'target': {'command': 'STATE.COM', 'arguments': []},
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
        assert read('rm_go', 1) == bytes([old])
        call('memory.write', address={'space': 'linear', 'offset': linear('rm_go')},
             expected_sha256=sha256(bytes([old])).hexdigest(),
             data_base64=b64encode(bytes([new])).decode('ascii'))

    def park(label):
        target = {'space': 'segmented', 'segment': cs, 'offset': f'0x{offsets[label]:08x}'}
        point = call('breakpoints.create', kind='execution', once=True, address=target)
        op = call('execution.continue')['operation_id']
        for _ in range(24):
            stop = call('execution.wait', operation_id=op, timeout_ms=250)
            if not stop.get('running'):
                break
        assert not stop.get('running') and stop['stop_reason'].get('breakpoint_id') == point['breakpoint_id'], stop

    def frame(variant, origin, *, expected=None):
        assert call('frame.step')['completed'] is True
        done = call('frame.step')
        assert done['completed'] is True
        payload, info = decode_screenshot(call('video.screenshot'))
        with Image.open(BytesIO(payload)) as image:
            dimensions = image.size
            rgb = image.convert('RGB').tobytes()
        assert (info['frame_id'], info['mode_id']) == (done['frame_id'], done['mode_id'])
        report['frames'][variant] = {
            'frame_id': info['frame_id'], 'mode_id': info['mode_id'], 'origin': origin,
            'dimensions': list(dimensions), 'pixel_sha256': sha256(rgb).hexdigest(),
        }
        assert dimensions == (WIDTH, HEIGHT)
        assert rgb == expected_rgb(expected or variant)

    call('execution.timing', fast_forward=False)
    park('rm_ready')
    report['sizes'] = sizes(read('size_results', SIZE_RESULT.size * len(SIZE_MASKS)))
    assert report['sizes'][0] == report['sizes'][8] == (0x014f, 0xbeef)
    assert all(report['sizes'][mask][0] == 0x004f for mask in (1, 2, 4, 7, 15))
    full_size = report['sizes'][15][1] * 64
    assert 0 < full_size <= STATE_BYTES
    frame('initial', ORIGIN)

    advance(0, 1)
    park('rm_saved')
    state_bytes = read('state_buffer', STATE_BYTES)
    assert state_bytes[:full_size] != bytes([STATE_FILL]) * full_size
    assert state_bytes[full_size:] == bytes([STATE_FILL]) * (STATE_BYTES - full_size)
    assert read('state_guard', 16) == bytes([STATE_FILL]) * 16
    report['state_size_bytes'] = full_size
    report['guest_state_sha256'] = sha256(state_bytes[:full_size]).hexdigest()

    advance(1, 2)
    park('rm_mutated')
    frame('mutated', 0)
    advance(2, 3)
    park('rm_restored')
    report['statuses'] = unpack('<2H', read('statuses', 4))
    assert report['statuses'] == (0x004f, 0x004f)
    assert read('state_buffer', STATE_BYTES) == state_bytes
    values = report['phases'] = phases(read('phase_results', PHASE_RESULT.size * len(PHASES)))
    assert values['initial']['pitch'] == PITCH
    assert values['mutated']['pitch'] == MUTATED_PITCH
    # The pinned S3 BIOS succeeds but leaves default pitch, fine X only,
    # and bank zero. The palette returns while framebuffer writes survive.
    assert values['restored'] == dict(values['initial'], probe=VRAM_MUTATION, pitch=WIDTH,
                                     pixels=WIDTH, lines=(16 << 20) // WIDTH,
                                     x=1, y=0, bank=0)
    frame('restored', 1, expected='dosbox-restored')

    advance(3, 4)
    park('rm_dac_done')
    width = report['dac8'] = dac_probe(read('dac_results', DAC_RESULT.size))
    assert all(width[field] == 0x004f for field in
               ('set_ax', 'save_ax', 'restore_ax', 'get_ax', 'palette_ax'))
    assert width['width'] == 6
    assert width['color'] == bytes([*(channel & 63 for channel in reversed(DAC8_COLOR)), 0xCC]).hex()


def test_dosbox_vbe_101_save_restore_display_state(tmp_path):
    if os.environ.get('FDISBULL_REQUIRE_DOSBOX_VBE_STATE') != '1':
        pytest.skip('Select the DOSBox-X VBE 4F04h display-state reference producer')
    producer = Path(os.environ['FDISBULL_DOSBOX_VBE_PAN']).resolve(strict=True)
    producer_sha = os.environ['FDISBULL_DOSBOX_VBE_PAN_SHA256']
    assert digest(producer) == producer_sha
    code = assemble(tmp_path, 'vbe-state', SOURCE, os.environ['NASM'])
    directory = tmp_path / 'game'
    directory.mkdir()
    binary = directory / 'STATE.COM'
    binary.write_bytes(code)
    wrapper = tmp_path / 'dosbox-vbe-state'
    args = [part for setting in PROFILE_STATE for part in ('-set', setting)]
    wrapper.write_text(f'#!{sys.executable}\nimport os, sys\n'
                       "os.environ.update(SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='dummy')\n"
                       f'os.execv({str(producer)!r}, [{str(producer)!r}, *sys.argv[1:], *{args!r}])\n')
    wrapper.chmod(0o700)
    report = dict(producer_sha256=producer_sha, authored_com_sha256=sha256(code).hexdigest(),
                  frames={}, profile=PROFILE_STATE)
    try:
        with closing(DOSBoxRPC(wrapper, directory)) as rpc:
            owner = rpc.process
            _observe(rpc, directory, labels(code), report)
        report['owner_rc'] = owner.poll()
        assert report['owner_rc'] == 0
    finally:
        assert binary.read_bytes() == code
        (tmp_path / 'dosbox-vbe-state.json').write_text(json.dumps(report, indent=2) + '\n')
