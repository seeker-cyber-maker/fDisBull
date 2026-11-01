"""Authored VIEW fixtures; no original game pixels or payloads."""
import pytest

from fdisbull.agi_resources import bind_native_view


def pair():
    # Two loops alias one cel. Omitted trailing transparent pixels move when
    # the native cache mirrors it; literal reversal of RLE bytes is incorrect.
    header=bytes([0,0,2,0,0,9,0,9,0,1,3,0,6,2])
    source=header+b'\x80\x01\x41\x00\x01\xb1\x41\x00'
    cached=header+b'\x90\x04\x41\x00\x03\x41\xb1\x00'
    return source,cached


def test_identical_bytes_are_distinct_from_source_derived_cache():
    source,cached=pair()
    assert bind_native_view(source,source)['byte_identical'] is True
    binding=bind_native_view(source,cached)
    assert binding['byte_identical'] is False
    assert binding['source_sha256']!=binding['runtime_sha256']
    assert binding['relation']=='aliased-mirror-cache'
    assert binding['changed_cels']==[{'offset':12,'from_loop':0,'to_loop':1,'aliases':[0,1]}]
    assert bind_native_view(cached,source)['relation']=='aliased-mirror-cache'


@pytest.mark.parametrize('kind',['pixel','transparency','mirror-bit','selector','directory','tail','length','dimensions','truncated-row'])
def test_other_mutations_are_not_hidden_by_render_equivalence(kind):
    source,cached=pair();data=bytearray(cached)
    if kind=='pixel':data[16]=0x31
    elif kind=='transparency':data[14]=0x91
    elif kind=='mirror-bit':data[14]=0x10
    elif kind=='selector':data[14]=0xa0
    elif kind=='directory':data[7]=10
    elif kind=='tail':
        source=source[:3]+len(source).to_bytes(2,'little')+source[5:]+b'X\0'
        data[3:5]=(len(data)).to_bytes(2,'little');data+=b'Y\0'
    elif kind=='length':data+=b'X'
    elif kind=='dimensions':data[12]=7
    elif kind=='truncated-row':data[-1]=0x41
    with pytest.raises(ValueError):bind_native_view(source,bytes(data))


def test_same_selector_does_not_allow_alternative_encoding():
    source,cached=pair();data=bytearray(cached);data[14]=0x80
    with pytest.raises(ValueError):bind_native_view(source,bytes(data))


def test_round_trip_cache_can_leave_unused_bytes_in_its_allocation():
    source,_=pair()
    result=bind_native_view(source+b'\xff\xff',source+b'\xde\xad')
    assert result['byte_identical'] is False
    assert result['changed_cels'][0]['from_loop']==result['changed_cels'][0]['to_loop']==0


def test_aliased_pixel_work_is_bounded():
    count=128;start=5+2*count
    source=bytes([0,0,count,0,0])+start.to_bytes(2,'little')*count+bytes([1,3,0,160,168,0x80])+bytes(168)
    cached=bytearray(source);cached[start+5]=0x90
    with pytest.raises(ValueError,match='pixel budget'):
        bind_native_view(source,bytes(cached))


def test_description_aliasing_a_cel_is_not_silently_modified():
    header=bytes([0,0,2,12,0,9,0,9,0,1,5,0,65,66,6,2])
    source=header+b'\x80\x01\x41\0\x01\xb1\x41\0'
    cached=header+b'\x90\x04\x41\0\x03\x41\xb1\0'
    with pytest.raises(ValueError,match='protected structure'):
        bind_native_view(source,cached)
