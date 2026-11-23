"""Guest 03DAh and PIT2 timing against the DOSBox-X row scheduler."""
from base64 import b64decode, b64encode
from hashlib import sha256
import json
import os
from pathlib import Path
import struct

import pytest

from support.dos_process_fixture import assemble, digest
from support.paired_vbe_status import RECORD_BYTES, read_edges, source_with_status_probe, status_lattice, symbols
from test_dosbox_vga_visible_rows_native import _lattice
from test_qemu_dosbox_vga_modes_native import _DAC, _SOURCE, _dosbox_pages


_COM_SHA = '3dd4cbaf8ad2ff81c2bbbbadb7b1ec5f4ee92498f12377eec28eb764e4894347'


def _journal(call, address, offsets, record, output):
    def read(offset, length):
        packet = call('memory.read', address=address(offset), length=length)
        return b64decode(packet['data_base64'], validate=True)

    def park(offset):
        point = call('breakpoints.create', kind='execution', once=True, address=address(offset))
        operation = call('execution.continue')['operation_id']
        for _ in range(24):
            state = call('execution.wait', operation_id=operation, timeout_ms=250)
            if not state.get('running'):
                break
        assert not state.get('running') and state['stop_reason']['kind'] == 'breakpoint', state
        assert state['stop_reason']['breakpoint_id'] == point['breakpoint_id'], state
        registers = call('state.get_registers')
        assert int(registers['instruction_pointer'], 16) == offset
        return registers

    assert read(offsets['timing_go'], 1) == b'\0'
    call('memory.write', address=address(offsets['timing_go']),
         expected_sha256=sha256(b'\0').hexdigest(), data_base64=b64encode(b'\1').decode('ascii'))
    before = park(offsets['status_in'])
    assert int(before['general']['edx'], 16) & 0xffff == 0x03da
    assert read(offsets['status_in'], 1) == b'\xec'
    assert call('execution.step', mode='into')['stop_reason']['kind'] == 'step'
    after = call('state.get_registers')
    assert int(after['instruction_pointer'], 16) == offsets['status_out']
    record['first_status'] = int(after['general']['eax'], 16) & 9

    park(offsets['timing_done'])
    size = struct.unpack('<H', read(offsets['edge_count'], 2))[0] * RECORD_BYTES
    journal = read(offsets['edge_journal'], size)
    output.write_bytes(journal)
    record['journal_sha256'] = digest(output)
    record['journal_count'] = size // RECORD_BYTES
    record['journal_result'] = read(offsets['timing_result'], 1)[0]
    assert record['journal_result'] == 1
    edges = read_edges(journal)
    assert edges[0]['new'] == record['first_status']
    record['status'] = status_lattice(edges)
    timing = call('video.probe', points=[], source_visible_rows=True)
    assert timing['source_visible_rows_available'] is True
    record['native_rows_after_guest_poll'] = dict(
        frame_id=timing['frame_id'], mode_id=timing['mode_id'], timing=timing['source_visible_rows'])
    _lattice(timing['source_visible_rows'], 'packed8')


def test_dosbox_vbe_status_port_matches_visible_rows(tmp_path):
    if os.environ.get('FDISBULL_REQUIRE_DOSBOX_VBE_STATUS') != '1':
        pytest.skip('Select the DOSBox-X guest VBE status producer')
    producer = Path(os.environ['FDISBULL_DOSBOX_VGA_VISIBLE_ROWS']).resolve(strict=True)
    producer_sha = os.environ['FDISBULL_DOSBOX_VGA_VISIBLE_ROWS_SHA256']
    assert digest(producer) == producer_sha
    code = assemble(tmp_path, 'vbe-retrace', source_with_status_probe(_SOURCE) + '\ncolors: db '
                    + ','.join(str(value) for color in _DAC for value in color), os.environ['NASM'])
    labels, offsets = symbols(code)
    directory = tmp_path / 'game'
    directory.mkdir()
    binary = directory / 'VGA.COM'
    binary.write_bytes(code)
    assert digest(binary) == _COM_SHA
    record = dict(producer_sha256=producer_sha, authored_com_sha256=_COM_SHA)

    def arm_rows(call, page, step, frame):
        if page != 'banked' or step != 2:
            call('video.probe', points=[], source_visible_rows=True,
                 frame_id=frame['frame_id'], mode_id=frame['mode_id'])
            return
        timing = call('video.probe', points=[], source_visible_rows=True,
                      frame_id=frame['frame_id'], mode_id=frame['mode_id'])
        assert timing['source_visible_rows_available'] is True
        record['native_rows_before_guest_poll'] = dict(
            frame_id=timing['frame_id'], mode_id=timing['mode_id'], timing=timing['source_visible_rows'])
        _lattice(timing['source_visible_rows'], 'packed8')

    def observe(call, page, address):
        if page == 'banked':
            _journal(call, address, offsets, record, tmp_path / 'guest-pit-status.bin')
            before = record['native_rows_before_guest_poll']
            after = record['native_rows_after_guest_poll']
            assert before['mode_id'] == after['mode_id'] and before['frame_id'] < after['frame_id']

    try:
        record['pixels'] = _dosbox_pages(producer, tmp_path, directory, labels,
                                         observe_rows=arm_rows, operate_page=observe)
    finally:
        assert binary.read_bytes() == code
        (tmp_path / 'dosbox-vbe-status.json').write_text(json.dumps(record, indent=2) + '\n')
