"""Lossless bounded frame transport at the actual guest broker boundary.

No guest startup occurs: function bodies are loaded without the serial/Xvfb
initialization, while the native reply is the explicit collaborator seam.
"""
import ast
import base64
from copy import deepcopy
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
import zlib

import pytest


def broker_functions():
    source=Path(__file__).parents[1]/'src/fdisbull/wine_guest/broker.py'
    tree=ast.parse(source.read_text())
    functions=ast.Module(body=[node for node in tree.body if isinstance(node,ast.FunctionDef)],type_ignores=[])
    scope={'base64':base64,'zlib':zlib}
    exec(compile(functions,str(source),'exec'),scope)
    return scope


def frame(width=32,height=24,raw=None,**metadata):
    if raw is None:raw=bytes(range(256))*(width*height*4//256)
    assert len(raw)==width*height*4
    return {'width':width,'height':height,'window':'0x30074','pid':412,
            'state_revision':7,'frame_revision':7,
            'bgra_base64':base64.b64encode(raw).decode('ascii'),**metadata},raw


@pytest.mark.parametrize('width,height',[(1,1),(64,1),(32,24),(892,616),(1920,1080)])
def test_capture_transport_is_byte_exact_and_preserves_all_metadata(width,height):
    raw=(b'\x04\x83\xf7\xa5'*(width*height))
    original,_=frame(width,height,raw,identity={'task':'authored source identity'})
    before=deepcopy(original)
    result=broker_functions()['screenshot_payload'](original)
    assert original==before
    assert {k:v for k,v in result.items() if k not in ('bgra_base64','bgra_zlib_base64')}=={
        k:v for k,v in before.items() if k!='bgra_base64'}
    assert ('bgra_base64' in result)+('bgra_zlib_base64' in result)==1
    if 'bgra_zlib_base64' in result:
        compressed=base64.b64decode(result['bgra_zlib_base64'],validate=True)
        assert len(compressed)<len(raw)
        decoded=zlib.decompress(compressed)
    else:decoded=base64.b64decode(result['bgra_base64'],validate=True)
    assert len(decoded)==len(raw)
    assert hashlib.sha256(decoded).digest()==hashlib.sha256(raw).digest()


@pytest.mark.parametrize('raw,width,height',[(b'\x03\x04\x05\x06',1,1),
    (bytes(range(256)),64,1),
    (hashlib.shake_256(b'authored incompressible frame').digest(65536),128,128)])
def test_small_or_incompressible_frames_keep_the_legacy_raw_reply(raw,width,height):
    original,_=frame(width,height,raw)
    assert len(zlib.compress(raw,1))>=len(raw)
    result=broker_functions()['screenshot_payload'](original)
    assert result==original and 'bgra_zlib_base64' not in result


@pytest.mark.parametrize('changes',[
    {'width':0},{'height':0},{'width':True},{'height':True},{'width':1921},
    {'height':1081},{'width':1.0},{'height':'24'},{'width':1<<60},
    {'bgra_base64':None},{'bgra_base64':b'not a JSON string'},
    {'bgra_base64':'!'}, {'bgra_base64':'A'*4097},
    {'bgra_zlib_base64':'AAAA'},
])
def test_invalid_capture_dimensions_or_pixel_encoding_refuse_before_compression(changes):
    value,_=frame();value.update(changes)
    scope=broker_functions()
    scope['zlib']=SimpleNamespace(compress=lambda *args:pytest.fail('Malformed frame reached compression'))
    with pytest.raises(ValueError):scope['screenshot_payload'](value)


@pytest.mark.parametrize('encoded', ['AAAAAA!=','\u00e9'*8,
    base64.b64encode(b'123456').decode('ascii'), 'AAAA===='])
def test_wrong_decoded_length_or_invalid_base64_is_not_accepted(encoded):
    value,_=frame(1,1,b'1234');value['bgra_base64']=encoded
    with pytest.raises(ValueError):broker_functions()['screenshot_payload'](value)


def test_missing_or_already_compressed_native_pixels_are_refused():
    value,_=frame();del value['bgra_base64']
    with pytest.raises(ValueError):broker_functions()['screenshot_payload'](value)
    value['bgra_zlib_base64']=base64.b64encode(zlib.compress(b'x')).decode('ascii')
    with pytest.raises(ValueError):broker_functions()['screenshot_payload'](value)
    for malformed in (None,[],7):
        with pytest.raises(ValueError):broker_functions()['screenshot_payload'](malformed)


def test_capture_unavailability_is_preserved_without_inventing_a_frame():
    scope=broker_functions()
    for reason in ('no-visible-client-window','capture-failed'):
        reply={'available':False,'reason':reason}
        assert scope['screenshot_payload'](reply)==reply
        with pytest.raises(ValueError):scope['screenshot_payload']({**reply,'bgra_base64':''})


@pytest.mark.parametrize('profile',['pe32','pe64','ne'])
def test_every_windows_profile_keeps_fresh_native_calls_and_capture_revisions(profile):
    scope=broker_functions();stream=io.BytesIO()
    scope['process']=SimpleNamespace(stdin=stream,profile=profile)
    originals=[frame(raw=b'\x11\x22\x33\x44'*(32*24),state_revision=7,frame_revision=7)[0],
               frame(raw=b'\x44\x33\x22\x11'*(32*24),state_revision=8,frame_revision=8)[0]]
    pending=iter(originals);observed=[]
    def response(*args,**kwargs):
        observed.append(kwargs)
        return next(pending)
    scope['response']=response
    results=[scope['invoke']('screenshot',{}) for _ in range(2)]
    assert stream.getvalue()==b'screenshot\nscreenshot\n'
    assert observed==[{'unavailable_capture':True}]*2
    for original,result in zip(originals,results,strict=True):
        assert result['state_revision']==original['state_revision']
        assert result['frame_revision']==original['frame_revision']
        assert zlib.decompress(base64.b64decode(result['bgra_zlib_base64'],validate=True))==base64.b64decode(original['bgra_base64'])
    assert results[0]['bgra_zlib_base64']!=results[1]['bgra_zlib_base64']


def test_non_capture_native_operations_do_not_enter_the_pixel_transform():
    scope=broker_functions();stream=io.BytesIO();scope['process']=SimpleNamespace(stdin=stream)
    native={'state':'stopped','state_revision':17};scope['response']=lambda *args,**kwargs:native
    scope['screenshot_payload']=lambda value:pytest.fail('Status operation reached capture compression')
    assert scope['invoke']('status',{}) is native
    assert stream.getvalue()==b'status\n'
