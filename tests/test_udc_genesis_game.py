"""Authored fixtures for Genesis native verifier address and publication rules."""
import copy
import importlib.util
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('check_genesis_game', SCRIPTS / 'check_genesis_game.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def field(offset, bits, signed=False, count=1):
    return {'address': 0xff0000 + offset, 'memory_id': 2, 'offset': offset,
            'element_bits': bits, 'signed': signed, 'array_length': count,
            'length': bits // 8 * count}


def swap(raw):
    assert len(raw) % 2 == 0
    return bytes(raw[i ^ 1] for i in range(len(raw)))


def test_absolute_address_mapping_preserves_odd_edges_and_patch_gaps():
    initial = bytearray(range(24))
    patches = check.physical_patches(7, [(3, b'\xaa\xbb\xcc'), (11, b'\xdd')])
    for patch in patches:
        assert patch['memory_id'] == 2 and patch['frame'] == 7
        data = bytes.fromhex(patch['data_hex'])
        initial[patch['offset']:patch['offset']+len(data)] = data
    assert check.arch_read(initial, 0, 3, 3) == b'\xaa\xbb\xcc'
    assert check.arch_read(initial, 0, 11, 1) == b'\xdd'
    assert initial[0] == 0 and initial[1] == 1
    with pytest.raises(ValueError, match='overlapping'):
        check.physical_patches(0, [(4, b'\x01\x02'), (5, b'\x03')])
    with pytest.raises(ValueError, match='does not contain'):
        check.arch_read(b'\x00', 0, 0, 1)


def test_big_endian_signed_and_array_state_round_trip():
    layout = {'byte': field(0x2201, 8), 'negative': field(0x2202, 16, True),
              'long': field(0x2204, 32), 'array': field(0x2209, 8, count=3)}
    state = {'byte': 0xab, 'negative': -2, 'long': 0x12345678, 'array': [1, 2, 255]}
    writes = check.state_writes(state, layout)
    raw = bytearray(65536)
    for patch in check.physical_patches(3, writes):
        blob = bytes.fromhex(patch['data_hex'])
        raw[patch['offset']:patch['offset']+len(blob)] = blob
    decoded = {}
    for name, f in layout.items():
        data = check.arch_read(raw, 0, f['offset'], f['length'])
        decoded.update(check.decode_fields(data, {name: {**f, 'offset': 0}}))
    assert decoded == state
    with pytest.raises(ValueError, match='names differ'):
        check.state_writes({'byte': 1}, layout)
    broken = copy.deepcopy(layout)
    broken['byte']['offset'] = broken['negative']['offset']
    broken['byte']['address'] = broken['negative']['address']
    with pytest.raises(ValueError, match='overlapping'):
        check.validate_layout(broken)


def fixture_manifest():
    layout = {'input_buttons': field(0x2300, 8), 'x': field(0x2301, 8)}
    packed = {'input_buttons': {**layout['input_buttons'], 'offset': 0},
              'x': {**layout['x'], 'offset': 1}}
    return {'state_layout': layout, 'publication': {'base': 0, 'slots': 4,
                                                    'stride': 704, 'state_fields': packed}}


def fixture_row(frame, records=(), *, fault=0, mask=0):
    pub = bytearray(4*704)
    for epoch, seq, buttons, x, hv in records:
        at = (epoch % 4)*704
        pub[at] = seq
        pub[at+1] = 1
        pub[at+2:at+4] = epoch.to_bytes(2, 'big')
        pub[at+4:at+6] = (10+epoch).to_bytes(2, 'big')
        pub[at+6] = buttons
        pub[at+7] = len(hv)
        pub[at+8] = 0
        pub[at+16:at+18] = bytes([buttons, x])
        for i, value in enumerate(hv):
            pub[at+632+i*2:at+634+i*2] = value.to_bytes(2, 'big')
    debug = bytearray(36)
    debug[:2] = (10+frame).to_bytes(2, 'big')
    debug[31] = fault
    raw = {'debug0': swap(debug).hex()}
    physical = swap(pub)
    for pos in (0, 1024, 2048):
        raw[f'publication{pos}'] = physical[pos:pos+1024].hex()
    return {'frame': frame, 'input_mask': mask, 'raw': raw}


def test_publication_accepts_only_completed_consecutive_versions():
    m = fixture_manifest()
    rows = [fixture_row(0), fixture_row(1, [(1, 1, 16, 1, [0x1234])]),
            fixture_row(2, [(1, 2, 16, 1, [0x1234])]),
            fixture_row(3, [(1, 2, 16, 1, [0x1234])])]
    records = check.publication_records({'frames': rows}, m)
    assert len(records) == 1
    assert records[0]['epoch'] == 1 and records[0]['input_frame'] == 11
    assert records[0]['state'] == {'input_buttons': 16, 'x': 1}
    assert records[0]['hv'] == [0x1234]


def test_publication_rejects_ring_overrun_and_oversized_hv():
    m = fixture_manifest()
    rows = [fixture_row(1, [(1, 2, 0, 1, [])]), fixture_row(2, [(6, 2, 0, 2, [])])]
    with pytest.raises(AssertionError, match='overrun'):
        check.publication_records({'frames': rows}, m)
    row = fixture_row(1, [(1, 2, 0, 1, [])])
    raw = bytearray(swap(bytes.fromhex(row['raw']['publication0'])))
    raw[704+7] = 33
    row['raw']['publication0'] = swap(raw).hex()
    with pytest.raises(AssertionError, match='HV count'):
        check.publication_records({'frames': [row]}, m)


def test_normal_replay_checks_all_fields_and_independent_input():
    pytest.importorskip('pycparser')
    from fdisbull.game_il import author_program
    p = author_program('''typedef unsigned char u8;u8 input_buttons;u8 x;
                         void game_boot(void){x=0;}void game_frame(void){x++;}''')
    rows = [fixture_row(0), fixture_row(1, [(1, 2, 16, 1, [])], mask=2),
            fixture_row(2, [(1, 2, 16, 1, []), (2, 2, 16, 2, [])], mask=2)]
    receipt = {'input_map': {'A': 1}}
    result = check.shadow_publications(p, b'', fixture_manifest(), receipt, {'frames': rows})
    assert result['completed_ticks'] == 2 and result['state_fields'] == 2
    assert result['independent_controller_checks'] == 2
    bad = copy.deepcopy(rows)
    bad[1]['input_mask'] = 0
    with pytest.raises(AssertionError, match='controller mismatch'):
        check.shadow_publications(p, b'', fixture_manifest(), receipt, {'frames': bad})
    bad = copy.deepcopy(rows)
    bad[2] = fixture_row(2, [(1, 2, 16, 1, []), (2, 2, 16, 9, [])], mask=2)
    with pytest.raises(AssertionError, match='state mismatch'):
        check.shadow_publications(p, b'', fixture_manifest(), receipt, {'frames': bad})
