"""Authored ABT byte-code vectors; no licensed resource fixtures."""
import hashlib
import json
import struct

import pytest

from fdisbull.dinopark_audio import (
    ABTAudio, MAX_SOURCE_BYTES, decode_abt, inspect_abt,
)


def abt(length, stream=b'', *, first=128, block=8, rate=10000, opaque=b'xyz'):
    return struct.pack('<HHB', length, rate, block) + opaque + bytes([first]) + stream


def test_one_sample_preserves_opaque_fields_without_playback_guesses():
    raw=abt(1, first=17, block=3, rate=0)
    decoded=decode_abt(raw)
    assert isinstance(decoded,ABTAudio) and decoded.pcm_u8==b'\x11'
    assert decoded.rate_field==0 and decoded.block_samples==3 and decoded.opaque_header==b'xyz'
    report=decoded.report()
    assert report['decoded']['declared_samples']==1
    assert report['source']['sha256']==hashlib.sha256(raw).hexdigest()
    assert report['rate_hz'] is None and report['channels'] is None
    assert report['opaque_header_bytes']==3 and 'opaque_header_hex' not in report
    assert report['full_decode'] and not report['native_runtime_tested']
    assert b'xyz' not in json.dumps(report).encode()


@pytest.mark.parametrize('token,expected',[(0x80,0),(0x81,2),(0xbf,126),(0xff,254)])
def test_literal_loses_low_bit_as_native_encoding_requires(token,expected):
    assert decode_abt(abt(2,bytes([token]),first=7)).pcm_u8==bytes([7,expected])


def test_repeat_and_zero_repeat_consume_tokens_without_inventing_samples():
    d=decode_abt(abt(4,b'\x43',first=17))
    assert d.pcm_u8==bytes([17])*4
    assert dict(d.branches)['repeat_samples']==3
    zero=decode_abt(abt(2,b'\x40\x81',first=7))
    assert zero.pcm_u8==bytes([7,2]) and zero.consumed_bytes==11
    assert dict(zero.branches)['zero_repeat_tokens']==1


@pytest.mark.parametrize('tag,block,packed,first,expected',[
    (0x10,8,0b01010101,128,[128,127,128,127,128,127,128,127,128]),
    (0x20,4,0b00011011,10,[10,8,7,8,10]),
    (0x00,2,0x78,128,[128,127,128]),
    (0x30,2,0x0f,0,[0,0,8]),
    # The final step16 table value wraps from +128 to signed -128.
    (0x0f,2,0xf8,128,[128,0,16]),
    (0x00,2,0xff,255,[255,255,255]),
])
def test_delta_helpers_bit_order_zero_skip_signed_wrap_and_saturation(tag,block,packed,first,expected):
    decoded=decode_abt(abt(len(expected),bytes([tag,packed]),block=block,first=first))
    assert decoded.pcm_u8==bytes(expected)


@pytest.mark.parametrize('raw',[
    b'', b'12345678', abt(0), abt(2,block=0),
    abt(2), abt(9,b'\x10',block=8),
    abt(2,b'\x43'), abt(2,b'\x10\0',block=8),
    abt(4,b'\x10\0',block=3), abt(1,b'\0'),
])
def test_truncation_zero_counts_alignment_overrun_and_trailers_refuse(raw):
    with pytest.raises(ValueError):decode_abt(raw)


def test_source_output_and_work_budgets_are_admitted_before_progress():
    with pytest.raises(ValueError,match='source budget'):
        decode_abt(abt(1)+bytes(MAX_SOURCE_BYTES))
    with pytest.raises(ValueError,match='before allocation'):
        decode_abt(abt(65535),max_output_bytes=1)
    with pytest.raises(ValueError,match='work budget'):
        decode_abt(abt(2,b'\x40'*100+b'\x81'),max_work_units=20)
    with pytest.raises(ValueError,match='work budget'):
        decode_abt(abt(9,b'\x10\x55'),max_work_units=1)


@pytest.mark.parametrize('name,value',[
    ('max_output_bytes',True),('max_output_bytes',0),('max_output_bytes',65536),
    ('max_work_units',True),('max_work_units',0),('max_work_units',2_000_001),
])
def test_invalid_budget_parameters_refuse(name,value):
    with pytest.raises(ValueError):decode_abt(abt(1),**{name:value})


def test_mutable_inputs_refuse():
    with pytest.raises(ValueError):decode_abt(bytearray(abt(1)))


def test_metadata_inspector_does_not_modify_or_export_samples(tmp_path):
    source=tmp_path/'authored.abt';raw=abt(4,b'\x43',first=19);source.write_bytes(raw)
    report=inspect_abt(source)
    assert source.read_bytes()==raw
    assert report['decoded']['sha256']==hashlib.sha256(bytes([19])*4).hexdigest()
    assert report['trailing_bytes']==0 and report['compressed_bytes_consumed']==len(raw)
    assert not report['input_executed'] and not report['source_modified']
    link=tmp_path/'linked.abt';link.symlink_to(source)
    with pytest.raises(ValueError,match='symlink'):inspect_abt(link)
