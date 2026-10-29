import hashlib
import pytest
from fdisbull.agi_picture import decode_picture, extract_v2_resource, priority_row_runs


def p(result, plane, x, y): return result[plane][y*160+x]


def test_lines_corners_relative_clamping_and_channels():
    result=decode_picture(bytes([0xf2,0,0xf6,0,0,3,1,0xf4,5,5,8,7,0xf7,0,0,0x90,0xf3,0xf0,9,0xf6,1,2,3,2,0xff]))
    assert all(p(result,'priority',x,y)==0 for x,y in [(0,0),(1,0),(2,1),(3,1),(5,8),(7,8),(159,0)])
    assert p(result,'visual',2,2)==9 and p(result,'priority',2,2)==4
    assert result['complete'] and result['priority_complete']


def test_fill_uses_visual_when_both_enabled():
    data=bytes([0xf0,1,0xf6,1,1,3,1,3,3,1,3,1,1,0xf0,2,0xf2,3,0xf8,2,2,0xff])
    result=decode_picture(data)
    assert p(result,'visual',2,2)==2 and p(result,'priority',2,2)==3
    assert p(result,'visual',0,0)==15 and p(result,'priority',1,1)==4
    assert priority_row_runs(result,{3})=={'row_runs':[[2,2,3]]}


def test_brush_geometry_and_raw_operand():
    d=decode_picture(bytes([0xf2,0xf0,0xf9,1,0xfa,5,5,0xff]))
    assert sum(value==0 for value in d['priority'])==6
    assert all(p(d,'priority',x,y)==0 for y in (4,5,6) for x in (4,5))
    d=decode_picture(bytes([0xf2,1,0xf9,0x20,0xfa,2,5,5,0xff]))
    assert d['complete']


def test_invalid_data_fails_closed():
    for data in (b'',b'\xf2',b'\xf6\x01\xff',b'\xfb\xff',b'\xf9\x20\xfa\x02\xff',b'\xf2\x01'):
        with pytest.raises(ValueError): decode_picture(data)
    with pytest.raises(ValueError): priority_row_runs({'priority_complete':False},[0])


def test_extract_v2_resource(tmp_path):
    payload=b'\xf2\x00\xff'; (tmp_path/'PICDIR').write_bytes(b'\x00\x00\x02'); (tmp_path/'VOL.0').write_bytes(b'xx\x12\x34\x00\x03\x00'+payload)
    r=extract_v2_resource(tmp_path/'PICDIR',tmp_path,0)
    assert r['payload']==payload and r['offset']==2 and r['sha256']==hashlib.sha256(payload).hexdigest()
    (tmp_path/'VOL.0').write_bytes(b'xx\x12\x34\x00\x04\x00'+payload)
    with pytest.raises(ValueError,match='Truncated'): extract_v2_resource(tmp_path/'PICDIR',tmp_path,0)


def test_long_line_uses_profile_byte_accumulators():
    d=decode_picture(bytes([0xf2,0,0xf6,0,0,159,100,0xff]))
    assert p(d,'priority',32,19)==0
    assert p(d,'priority',32,20)==4
