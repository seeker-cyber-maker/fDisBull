"""Read-only proposals from two independent native x86 decoders."""
import pytest

from fdisbull.decoder_check import compare_decoders


def test_agreement_has_exact_bytes_mode_and_engine_provenance():
    result = compare_decoders(bytes.fromhex('4889e5'), 64, address=0x1000)
    assert result['input_hex'] == '4889e5'
    assert result['bits'] == 64
    assert result['hardware_observed'] is False
    assert result['executed'] is False
    assert {engine['name'] for engine in result['engines']} == {'iced-x86', 'capstone'}
    row = result['candidates'][0]
    assert row['offset'] == 0 and row['address'] == 0x1000
    assert row['comparison']['validity_agrees'] is True
    assert row['comparison']['length_agrees'] is True
    assert {engine['size'] for engine in row['decoders']} == {3}
    assert all(engine['bytes'] == '4889e5' for engine in row['decoders'])


def test_truncated_bytes_do_not_become_an_instruction():
    row = compare_decoders(b'\x0f', 64)['candidates'][0]
    assert row['comparison']['status'] == 'both_invalid'
    assert all(not engine['valid'] and engine['size'] is None for engine in row['decoders'])
    assert row['decoders'][0]['error'] == 'truncated'


def test_real_validity_disagreement_is_retained_without_promotion():
    # Pinned iced and Capstone interpret this encoding differently. This is a
    # decoder observation, deliberately not an assertion about any CPU.
    row = compare_decoders(bytes.fromhex('0f0dc0'), 64)['candidates'][0]
    assert {engine['valid'] for engine in row['decoders']} == {True, False}
    assert row['comparison']['status'] == 'validity_disagreement'
    assert row['comparison']['validity_agrees'] is False
    assert row['classification'] == 'unconfirmed decode proposal'
    assert 'authoritative' not in row


def test_text_differences_are_separate_from_instruction_lengths():
    row = compare_decoders(bytes.fromhex('668400'), 64)['candidates'][0]
    assert row['comparison']['validity_agrees'] is True
    assert row['comparison']['length_agrees'] is True
    assert row['comparison']['text_agrees'] is False
    assert row['comparison']['status'] == 'text_difference'


def test_offset_scan_is_bounded_and_keeps_alternative_start_addresses():
    result = compare_decoders(bytes.fromhex('b800000000c3') + bytes(30), 32,
                              address=0x4000, scan_offsets=True, max_candidates=16)
    assert [row['offset'] for row in result['candidates']] == list(range(15))
    assert result['candidates'][5]['address'] == 0x4005
    assert all(row['classification'] == 'unconfirmed decode proposal' for row in result['candidates'])
    assert result['truncated_candidates'] is False
    limited = compare_decoders(bytes(30), 32, scan_offsets=True, max_candidates=3)
    assert len(limited['candidates']) == 3 and limited['truncated_candidates'] is True


def test_mode_changes_decode_without_claiming_cpu_behavior():
    data = bytes.fromhex('4889e5')
    assert compare_decoders(data, 32)['candidates'][0]['decoders'][0]['size'] == 1
    assert compare_decoders(data, 64)['candidates'][0]['decoders'][0]['size'] == 3


@pytest.mark.parametrize('kwargs', [
    {'data': b'', 'bits': 64}, {'data': bytearray(b'\x90'), 'bits': 64},
    {'data': b'\x90', 'bits': True}, {'data': b'\x90', 'bits': 8},
    {'data': b'\x90', 'bits': 64, 'arch': 'arm64'},
    {'data': b'\x90', 'bits': 64, 'max_candidates': 0},
    {'data': b'\x90', 'bits': 64, 'max_candidates': 17},
    {'data': b'\x90', 'bits': 64, 'address': -1},
    {'data': b'\x90\x90', 'bits': 64, 'address': (1 << 64) - 1, 'scan_offsets': True},
])
def test_invalid_arguments_are_rejected(kwargs):
    with pytest.raises(ValueError):
        compare_decoders(**kwargs)
