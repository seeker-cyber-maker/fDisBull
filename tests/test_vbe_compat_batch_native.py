"""Paired native VBE BIOS calls with one authored COM on DOSBox-X and QEMU."""

from base64 import b64decode
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
from struct import unpack_from
import sys

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.project import Project
from support.dos_process_fixture import assemble, digest
from support import paired_vbe_compat_batch as witness
from test_dosbox_vbe_lfb_native import PROFILE_LFB
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_vbe_flip_native import read_memory


PROFILE = 'vga-640x480-vbe-compat'
ROM = 'fdisbull-vgabios-vbe101-compat.bin'

pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_VBE_COMPAT_BATCH') != '1',
    reason='Select the pinned DOSBox-X and QEMU VBE compatibility producers',
)


def _capture(read, locations):
    data = {
        'legacy': read(locations['legacy_info'], 256),
        'legacy_guard': read(locations['legacy_guard'], 16),
        'vbe2': read(locations['vbe2_info'], 512),
        'vbe2_guard': read(locations['vbe2_guard'], 16),
        'mode': read(locations['mode_info'], 256),
        'mode_guard': read(locations['mode_guard'], 16),
        'results': read(locations['results'], 2 * len(witness.NAMES)),
        'colors': read(locations['colors'], 8),
        'returned_colors': read(locations['returned_colors'], 8),
        'colors_guard': read(locations['colors_guard'], 16),
    }
    return {
        'controller_legacy': witness.controller(data['legacy']),
        'controller_vbe2': witness.controller(data['vbe2']),
        'mode': witness.mode(data['mode']),
        'results': witness.results(data['results']),
        'guards': {name: data[name].hex() for name in
                   ('legacy_guard', 'vbe2_guard', 'mode_guard', 'colors_guard')},
        'colors': data['colors'].hex(),
        'returned_colors': data['returned_colors'].hex(),
        'vbe2_tail_sha256': sha256(data['vbe2'][256:]).hexdigest(),
    }


def _dosbox(producer, directory, code, offsets):
    game = directory / 'dosbox-game'
    game.mkdir()
    binary = game / 'COMPAT.COM'
    binary.write_bytes(code)
    wrapper = directory / 'dosbox-compat'
    args = [part for setting in PROFILE_LFB for part in ('-set', setting)]
    wrapper.write_text(f'#!{sys.executable}\nimport os, sys\n'
                       "os.environ.update(SDL_AUDIODRIVER='dummy', SDL_VIDEODRIVER='dummy')\n"
                       f'os.execv({str(producer)!r}, [{str(producer)!r}, *sys.argv[1:], *{args!r}])\n')
    wrapper.chmod(0o700)
    with closing(DOSBoxRPC(wrapper, game)) as rpc:
        owner = rpc.process
        sid = rpc.call('session.start', {
            'target': {'command': 'COMPAT.COM', 'arguments': []},
            'mounts': [{'drive': 'C', 'host_path': str(game)}],
            'break_at': 'entry',
        })['session_id']

        def call(method, **options):
            return rpc.call(method, {'session_id': sid, **options}, timeout_ms=5000)

        cs = call('state.get_registers')['segments']['cs']
        base = int(cs, 16) * 16
        target = {'space': 'segmented', 'segment': cs,
                  'offset': f"0x{offsets['done']:08x}"}
        point = call('breakpoints.create', kind='execution', once=True, address=target)
        operation = call('execution.continue')['operation_id']
        for _ in range(24):
            stop = call('execution.wait', operation_id=operation, timeout_ms=250)
            if not stop.get('running'):
                break
        assert not stop.get('running') and stop['stop_reason'].get('breakpoint_id') == point['breakpoint_id'], stop

        def read(offset, length):
            address = {'space': 'physical', 'offset': f'0x{base + offset:08x}'}
            packet = call('memory.read', address=address, length=length)
            raw = b64decode(packet['data_base64'], validate=True)
            assert len(raw) == length and sha256(raw).hexdigest() == packet['sha256']
            return raw

        result = _capture(read, offsets)
    assert owner.poll() == 0 and binary.read_bytes() == code
    result['producer_sha256'] = digest(producer)
    result['owner_exit'] = owner.poll()
    return result


def _qemu(directory, code, offsets, runtime, disk, tool):
    binary = directory / 'COMPAT.COM'
    binary.write_bytes(code)
    with Project.create(directory / 'vbe-compat.fdb', binary, image='com') as project:
        with project.debugger(
            runtime['executable'], directory,
            **launch_options(runtime, disk, qemu_clock='virtual', qemu_retrace='precise',
                             qemu_video_source_profile=PROFILE, qemu_checkpoint_tool=tool),
        ) as debug:
            owner = debug.vm.process
            process = process_record(debug)
            locations = {name: com_address(process, offset)
                         for name, offset in offsets.items()}
            park(debug, locations['done'])
            result = _capture(lambda address, length: read_memory(debug, address, length),
                              locations)
            segment_value = process['psp_segment']
            guest_segment = int(segment_value, 0) if isinstance(segment_value, str) else int(segment_value)
            strings = {}
            for label, field in (('oem', 6), ('vendor', 22), ('product', 26), ('revision', 30)):
                pointer = read_memory(debug, locations['vbe2_info'] + field, 4)
                offset, segment = unpack_from('<HH', pointer)
                assert segment == guest_segment
                assert offsets['vbe2_info'] + 256 <= offset < offsets['vbe2_info'] + 512
                value = read_memory(debug, guest_segment * 16 + offset, 64).split(b'\0', 1)[0]
                strings[label] = value.decode('ascii')
            result['vbe2_oem_strings'] = strings
            before = debug.vga_configuration_observe()['current']['raw']['vbe']
            assert before[4] & 1
            saved = debug.save_state('vbe-compat.qcow2')
            loaded = debug.load_state(saved['artifact'], timeout_ms=60_000)
            assert loaded['instrumentation']['format'] == 'fdisbull-instrumented-qemu-state-14'
            restored_owner = debug.vm.process
            assert restored_owner is not owner and owner.poll() == 0
            replayed = _capture(lambda address, length: read_memory(debug, address, length),
                                locations)
            assert replayed == {key: result[key] for key in replayed}
            assert debug.vga_configuration_observe()['current']['raw']['vbe'] == before
            result['checkpoint_restored'] = True
        assert owner.poll() == restored_owner.poll() == 0
    assert binary.read_bytes() == code and digest(disk['image']) == disk['prepared_sha256']
    result['producer_sha256'] = digest(runtime['executable'])
    result['rom_sha256'] = digest(Path(runtime['firmware']) / ROM)
    result['owner_exit'] = owner.poll()
    return result


def _verify(qemu, dosbox):
    success = ('legacy', 'vbe2', 'mode', 'set_mode', 'set_bank', 'get_bank',
               'get_bank_after', 'set_palette', 'get_palette')
    for observed in (qemu, dosbox):
        assert all(observed['results'][key] == 0x004f for key in success), observed['results']
        assert observed['results']['bank_before'] == 2
        assert observed['controller_legacy']['version'] >= 0x0200
        assert observed['controller_vbe2']['version'] >= 0x0200
        assert observed['controller_legacy']['memory_blocks'] == 256
        assert observed['controller_vbe2']['memory_blocks'] == 256
        info = observed['mode']
        assert (info['width'], info['height'], info['bpp'], info['pitch']) == (640, 480, 8, 640)
        assert info['attributes'] & 0x81 == 0x81
        assert observed['colors'] == '030f1f552c053caa'
        assert observed['returned_colors'] == '030f1fcc2c053ccc'
        assert all(bytes.fromhex(value) == b'\x5a' * 16 for value in observed['guards'].values())
    assert qemu['results']['reject_bank'] == 0x014f
    assert qemu['results']['bank_after'] == 2
    # This pinned S3 BIOS accepts bank 256 and wraps it to bank zero.
    assert dosbox['results']['reject_bank'] == 0x004f
    assert dosbox['results']['bank_after'] == 0
    assert qemu['results']['secondary_set'] == qemu['results']['secondary_get'] == 0x024f
    assert dosbox['results']['secondary_set'] == dosbox['results']['secondary_get'] == 0x0109
    assert qemu['controller_vbe2']['software_revision'] == 0x0100
    assert qemu['vbe2_oem_strings']['oem'].startswith('SeaBIOS')
    assert qemu['vbe2_oem_strings']['vendor'] == 'SeaBIOS Developers'
    assert qemu['vbe2_oem_strings']['product'] == 'SeaBIOS VBE Adapter'
    assert qemu['vbe2_oem_strings']['revision'] == 'Rev. 1'
    assert qemu['mode']['pages'] == qemu['mode']['bank_pages'] == qemu['mode']['linear_pages'] == 50
    assert qemu['mode']['linear_pitch'] == 640


def test_vbe_bios_compatibility_batch_against_dosbox_x(tmp_path, clock_runtime, clock_disk):
    tool = Path(os.environ['FDISBULL_QEMU_IMG']).resolve(strict=True)
    producer = Path(os.environ['FDISBULL_DOSBOX_VBE_PAN']).resolve(strict=True)
    pinned = {
        'qemu': os.environ['FDISBULL_QEMU_VBE_COMPAT_BATCH_SHA256'],
        'qemu-img': os.environ['FDISBULL_QEMU_VBE_COMPAT_BATCH_IMG_SHA256'],
        'rom': os.environ['FDISBULL_QEMU_VBE_COMPAT_BATCH_ROM_SHA256'],
        'dosbox': os.environ['FDISBULL_DOSBOX_VBE_PAN_SHA256'],
    }
    assert digest(clock_runtime['executable']) == pinned['qemu']
    assert digest(tool) == pinned['qemu-img']
    assert digest(Path(clock_runtime['firmware']) / ROM) == pinned['rom']
    assert digest(producer) == pinned['dosbox']
    code = assemble(tmp_path, 'vbe-compat', witness.SOURCE, clock_runtime['nasm'])
    offsets = witness.labels(code)
    report = {'authored_com_sha256': sha256(code).hexdigest(),
              'profile': PROFILE, 'complete': False}
    try:
        report['dosbox'] = _dosbox(producer, tmp_path, code, offsets)
        report['qemu'] = _qemu(tmp_path, code, offsets, clock_runtime, clock_disk, str(tool))
        _verify(report['qemu'], report['dosbox'])
        report['complete'] = True
    finally:
        (tmp_path / 'vbe-compat-batch.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
