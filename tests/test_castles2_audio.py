"""Authored SLB fixtures exercise native-profile boundaries without game payloads."""
import hashlib
import json
import struct
from dataclasses import FrozenInstanceError
from fractions import Fraction

import pytest

from fdisbull.castles2_audio import (
    MAX_SLOTS, MAX_SOURCE_BYTES, PLAYBACK_PROFILE, bind_slb_playback,
    decode_slb, inspect_slb,
)


def fixture(selector=22, entries=None):
    # Keys 1 and 5 collide modulo four under the recovered multiplier 73.
    if entries is None:
        entries = [None, (1, b'\x80\x81\x7f'), (5, b'\x20\xe0'), None]
    payload = bytearray()
    slots = []
    for entry in entries:
        if entry is None:
            slots.append((0, 0, 0))
        else:
            key, data = entry
            slots.append((key, len(payload), len(data)))
            payload.extend(data)
    table = len(payload)
    return bytes(payload) + b''.join(struct.pack('<III', *row) for row in slots) + struct.pack('<III', selector, len(slots), table)


def test_complete_structure_and_original_directory_slots():
    raw = fixture()
    lib = decode_slb(raw)
    assert lib.footer_selector == 22
    assert lib.table_offset == 5
    assert [(s.slot, s.key, s.offset, s.length) for s in lib.slots] == [
        (0, 0, 0, 0), (1, 1, 0, 3), (2, 5, 3, 2), (3, 0, 0, 0)]
    assert lib.sample(1) == b'\x80\x81\x7f'
    assert lib.sample(2) == b'\x20\xe0'
    assert lib.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert lib.lookup_slots(1) == (1,)
    assert lib.lookup_slots(5) == (2,)
    assert lib.lookup_slots(9) == ()


def test_report_contains_hashes_not_sample_bytes_and_is_json_safe():
    raw = fixture()
    r = inspect_slb(raw)
    assert r['source']['bytes'] == len(raw)
    assert r['occupied_slots'] == r['empty_slots'] == 2
    assert r['slots'][1]['sha256'] == hashlib.sha256(b'\x80\x81\x7f').hexdigest()
    assert r['slots'][0]['sha256'] is None
    assert r['payload_partition_exact'] is True
    assert r['native_runtime_tested'] is False
    assert r['full_audio_decode'] is False
    assert r['rewrite_supported'] is False
    json.dumps(r, allow_nan=False)


def test_duplicate_keys_are_not_implicitly_deduplicated_or_randomly_selected():
    lib = decode_slb(fixture(entries=[None, (1, b'A'), (1, b'BC'), None]))
    assert lib.lookup_slots(1) == (1, 2)
    assert lib.sample(1) == b'A'
    assert lib.sample(2) == b'BC'
    assert lib.report()['duplicate_keys'] == [{'key': 1, 'variants': 2}]


def test_hash_probe_wraps_to_zero_and_stops_at_empty_slot():
    # 3*73 % 4 == 3; matching variants occupy slots3 then0.
    lib = decode_slb(fixture(entries=[(3, b'B'), None, None, (3, b'A')]))
    assert lib.lookup_slots(3) == (3, 0)


def test_full_table_cannot_loop_forever():
    lib = decode_slb(fixture(entries=[(1, b'A'), (2, b'B')]))
    with pytest.raises(ValueError, match='terminator'):
        lib.lookup_slots(1)


@pytest.mark.parametrize('key', [True, False, -1, 0, 2**32, 0x7fffffff // 73 + 1, '1', 1.0])
def test_key_domain_refuses_guessed_signed_remainder_semantics(key):
    with pytest.raises(ValueError):
        decode_slb(fixture()).lookup_slots(key)


@pytest.mark.parametrize('slot', [True, False, -1, 0, 3, 4, '1', 1.0])
def test_slot_is_explicit_bounded_integer_and_must_be_occupied(slot):
    lib = decode_slb(fixture())
    with pytest.raises(ValueError):
        lib.sample(slot)
    with pytest.raises(ValueError):
        bind_slb_playback(lib).sample_report(slot)


@pytest.mark.parametrize('selector,tc,divisor,rate', [(11, 166, 90, 11111), (22, 211, 45, 22222)])
def test_discrete_time_constants_and_exact_rational_timing(selector, tc, divisor, rate):
    lib = decode_slb(fixture(selector))
    p = bind_slb_playback(lib, profile=PLAYBACK_PROFILE)
    assert p.time_constant == tc
    assert p.ideal_device_rate == Fraction(1_000_000, divisor)
    assert p.wave_sample_rate == rate
    r = p.sample_report(1)
    assert r['encoding'] == 'pcm_u8' and r['channels'] == 1 and r['bits'] == 8
    assert r['ideal_device_duration_seconds'] == {'numerator': 27, 'denominator': 100000 if selector == 11 else 200000}
    assert r['wave_duration_seconds'] == {'numerator': 3, 'denominator': rate}
    assert r['pcm_sha256'] == hashlib.sha256(lib.sample(1)).hexdigest()
    assert r['native_runtime_tested'] is False
    assert 'integer WAV adapter' in r['wave_rate_policy']
    assert 'polling/cleanup latency' in r['duration_scope']
    json.dumps(r, allow_nan=False)


@pytest.mark.parametrize('selector', [0, 5, 12, 11025, 22000, 22050, 0xffffffff])
def test_unknown_and_non_corpus_rate_selectors_remain_structurally_visible(selector):
    lib = decode_slb(fixture(selector))
    assert lib.report()['footer_selector'] == selector
    with pytest.raises(ValueError, match='11/22'):
        bind_slb_playback(lib)


def test_explicit_profile_is_not_a_filename_or_arbitrary_rate_hint():
    lib = decode_slb(fixture())
    with pytest.raises(ValueError, match='profile'):
        bind_slb_playback(lib, profile='guess-22050')
    with pytest.raises(ValueError, match='SLBLibrary'):
        bind_slb_playback(lib.report())


@pytest.mark.parametrize('data', [b'', bytes(12), bytes(23), bytearray(fixture()), memoryview(fixture()), 'SLB'])
def test_short_or_mutable_inputs_refuse(data):
    with pytest.raises(ValueError):
        decode_slb(data)


@pytest.mark.parametrize('kwargs', [
    {'max_source_bytes': 0}, {'max_source_bytes': True}, {'max_source_bytes': -1},
    {'max_source_bytes': MAX_SOURCE_BYTES + 1}, {'max_source_bytes': 1},
    {'max_slots': 0}, {'max_slots': True}, {'max_slots': -1},
    {'max_slots': MAX_SLOTS + 1}, {'max_slots': 1},
])
def test_admission_limits_are_typed_and_fail_before_unbounded_parsing(kwargs):
    with pytest.raises(ValueError):
        decode_slb(fixture(), **kwargs)


@pytest.mark.parametrize('field,value', [(1, 0), (1, 5), (2, 0), (2, 4), (2, 0xffffffff)])
def test_directory_must_end_exactly_at_footer(field, value):
    raw = bytearray(fixture())
    struct.pack_into('<I', raw, len(raw)-12+field*4, value)
    with pytest.raises(ValueError):
        decode_slb(bytes(raw))


@pytest.mark.parametrize('slot,field,value', [
    (0, 1, 1), (0, 2, 1),  # A supposedly empty entry cannot carry stray fields.
    (1, 0, 0), (1, 2, 0), (1, 1, 0xffffffff), (1, 2, 0xffffffff),
    (2, 1, 2),  # overlap
    (2, 1, 4),  # gap / extent beyond payload
])
def test_invalid_occupied_entries_and_payload_partition_refuse(slot, field, value):
    raw = bytearray(fixture())
    struct.pack_into('<I', raw, 5+slot*12+field*4, value)
    with pytest.raises(ValueError):
        decode_slb(bytes(raw))


def test_trailing_unexplained_payload_is_refused():
    # A correct table/footer size is insufficient if a payload byte is unowned.
    raw = fixture()
    changed = raw[:5] + b'X' + raw[5:-12] + struct.pack('<III', 22, 4, 6)
    with pytest.raises(ValueError, match='end at'):
        decode_slb(changed)


def test_empty_sample_bank_refuses():
    raw = bytes(24) + struct.pack('<III', 22, 2, 0)
    with pytest.raises(ValueError, match='no occupied'):
        decode_slb(raw)


def test_decoded_contract_is_immutable():
    lib = decode_slb(fixture())
    with pytest.raises(FrozenInstanceError):
        lib.footer_selector = 11
    with pytest.raises(FrozenInstanceError):
        lib.slots[1].length = 12
