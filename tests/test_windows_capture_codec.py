"""Exact bounded frame transport; every probe still requests a fresh capture."""
import base64
import hashlib
import zlib

import pytest

from fdisbull.windows_ui import _decode_bgra
from test_windows_scenes import program


def payload(raw,*,compressed=False):
    field='bgra_zlib_base64' if compressed else 'bgra_base64'
    return {field:base64.b64encode(zlib.compress(raw,1) if compressed else raw).decode()}


@pytest.mark.parametrize('raw',[
    bytes([1,2,3,0]),
    bytes([1,2,3,255])*64,
    bytes(range(256))*16,
    bytes([0,31,127,255,17,53,91,0])*512,
])
def test_codec_preserves_every_bgra_byte_and_legacy_raw_transport(raw):
    decoded=payload(raw)
    assert _decode_bgra(decoded,len(raw))==raw and not decoded
    if len(zlib.compress(raw,1))<len(raw):
        decoded=payload(raw,compressed=True)
        assert _decode_bgra(decoded,len(raw))==raw and not decoded


@pytest.mark.parametrize('width,height,compressible',[(1,1,False),(64,16,True),(32,32,False)])
def test_actual_broker_payload_round_trips_through_the_bounded_host_decoder(width,height,compressible):
    from test_wine_broker_capture import broker_functions,frame
    size=width*height*4
    raw=bytes([1,31,127,255])*(size//4) if compressible else hashlib.shake_256(b'authored BGRA').digest(size)
    native,_=frame(width,height,raw,identity={'task':'source-bound authored frame'})
    transported=broker_functions()['screenshot_payload'](native)
    assert ('bgra_zlib_base64' in transported)==compressible
    assert _decode_bgra(transported,size)==raw
    assert transported=={name:value for name,value in native.items() if name!='bgra_base64'}


@pytest.mark.parametrize('backend,profile',[
    ('wine-ne-qemu','win16-ne-original-1'),
    ('wine-qemu','pe32-win32-debug-1'),
    ('wine-qemu','pe64-win32-debug-2'),
])
def test_each_windows_profile_decodes_losslessly_without_reusing_a_capture(
        program,monkeypatch,backend,profile):
    program.backend_name=backend;program.metadata['runtime_profile']=profile
    original=program.call;compressed=False
    def screenshot(method,params=None,**kwargs):
        result=original(method,params,**kwargs)
        if method=='screenshot' and compressed:
            raw=base64.b64decode(result.pop('bgra_base64'),validate=True)
            result.update(payload(raw,compressed=True))
        return result
    monkeypatch.setattr(program,'call',screenshot)
    before=program.frame_probe([[0,0]])
    compressed=True
    exact=program.frame_probe([[0,0]])
    assert exact==before
    program.rgb=(17,53,91)
    changed=program.frame_probe([[0,0]])
    assert changed['samples'][0]['rgb']==[17,53,91]
    assert changed['frame_id']!=before['frame_id'] and changed['capture_sha256']!=before['capture_sha256']
    assert len([method for method,params in program.calls if method=='screenshot'])==3
    assert not any(method in ('keyboard','click','slice','run') for method,params in program.calls)


@pytest.mark.parametrize('result',[
    {},
    {'bgra_base64':'','bgra_zlib_base64':''},
    {'bgra_zlib_base64':None},
    {'bgra_base64':b'AAAA'},
    {'bgra_unknown_base64':'AAAA'},
])
def test_pixel_field_contract_refuses_missing_ambiguous_or_non_json_payload(result):
    with pytest.raises(ValueError):_decode_bgra(dict(result),64)


@pytest.mark.parametrize('field',['bgra_base64','bgra_zlib_base64'])
def test_encoded_budget_refuses_before_base64_allocation(field,monkeypatch):
    def forbidden(*args,**kwargs):pytest.fail('Oversized encoded payload reached base64 decoding')
    monkeypatch.setattr(base64,'b64decode',forbidden)
    with pytest.raises(ValueError,match='encoded byte budget'):_decode_bgra({field:'A'*1000},64)


@pytest.mark.parametrize('field',['bgra_base64','bgra_zlib_base64'])
@pytest.mark.parametrize('encoded',['!!!','åååå','A==='])
def test_corrupt_base64_refuses_for_both_wire_encodings(field,encoded):
    with pytest.raises(ValueError,match='base64'):_decode_bgra({field:encoded},64)


@pytest.mark.parametrize('encoded',[
    zlib.compress(bytes(64),1)[:-1],  # truncated trailer
    zlib.compress(bytes(60),1),     # valid stream, wrong exact output length
    zlib.compress(bytes(68),1),     # output exceeds width*height*4
    zlib.compress(bytes(64),1)+b'X',
    zlib.compress(bytes(64),1)+zlib.compress(bytes(64),1),
    b'not-a-zlib-stream',
])
def test_invalid_truncated_oversized_or_extra_compressed_stream_is_rejected(encoded):
    with pytest.raises(ValueError):
        _decode_bgra({'bgra_zlib_base64':base64.b64encode(encoded).decode()},64)


def test_compressed_input_must_be_strictly_smaller_than_expected_raw_bytes():
    with pytest.raises(ValueError,match='compressed pixel length'):
        _decode_bgra({'bgra_zlib_base64':base64.b64encode(bytes(128)).decode()},128)


def test_oversized_inflation_is_stopped_at_expected_plus_one(monkeypatch):
    original=zlib.decompressobj;limits=[]
    class Decoder:
        def __init__(self):self.inner=original()
        def decompress(self,data,maximum):
            limits.append(maximum)
            return self.inner.decompress(data,maximum)
        def __getattr__(self,name):return getattr(self.inner,name)
    monkeypatch.setattr(zlib,'decompressobj',Decoder)
    encoded=base64.b64encode(zlib.compress(bytes(64*1024),1)).decode()
    # The compressed representation must also fit the declared input budget.
    with pytest.raises(ValueError):_decode_bgra({'bgra_zlib_base64':encoded},1024)
    assert limits==[1025]


@pytest.mark.parametrize('dimensions',[(0,2),(1921,2),(2,0),(2,1081)])
def test_invalid_dimensions_are_rejected_before_codec_decode(program,monkeypatch,dimensions):
    import fdisbull.windows_ui as ui
    original=program.call
    def screenshot(method,params=None,**kwargs):
        result=original(method,params,**kwargs)
        if method=='screenshot':result.update(width=dimensions[0],height=dimensions[1])
        return result
    monkeypatch.setattr(program,'call',screenshot)
    def forbidden(*args,**kwargs):pytest.fail('Invalid dimensions reached pixel decoding')
    monkeypatch.setattr(ui,'_decode_bgra',forbidden)
    with pytest.raises(ValueError):program.frame_probe([])
