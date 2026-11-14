"""Author-created BOB fixtures only. No original commercial game bytes."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import struct
import pytest
from PIL import Image
from fdisbull.castles2_bob import decode_bob
from fdisbull.media import inspect_media, extract_media, media_modules


def bob_fixture(width=3,height=2):
    palette=bytearray(768)
    palette[0:3]=bytes([1,2,3])
    palette[3:6]=bytes([255,0,255])
    palette[6:9]=bytes([15,90,230])
    palette[9:12]=bytes([0,255,100])
    pixels=(bytes([0,1,2,3,2,1]) if (width,height)==(3,2)
            else bytes(i%4 for i in range(width*height)))
    return struct.pack('<HH',width,height)+palette+pixels


def test_decode_exact_indexed_image_and_png_colors():
    image=decode_bob(bob_fixture())
    assert (image.width,image.height)==(3,2)
    assert image.pixels==bytes([0,1,2,3,2,1])
    assert image.palette[0]==(1,2,3)
    assert image.palette[1]==(255,0,255)
    assert image.palette[2]==(15,90,230)
    assert image.transparent is None
    with Image.open(BytesIO(image.png())) as png:
        assert png.size==(3,2)
        assert png.convert('RGBA').getpixel((1,0))==(255,0,255,255)
        assert png.convert('RGB').getpixel((2,0))==(15,90,230)


@pytest.mark.parametrize('malformed',[
    b'',b'\0'*772,b'\0'*771,bob_fixture()[:-1],bob_fixture()+b'\0',
    b'\0\0'+bob_fixture()[2:],
    bob_fixture()[:2]+b'\0\0'+bob_fixture()[4:],
    struct.pack('<HH',65535,65535)+b'\0'*768+b'\0',
    bytearray(bob_fixture())])
def test_fail_closed_on_truncation_overhang_geometry_and_mutability(malformed):
    with pytest.raises(ValueError): decode_bob(malformed)


def test_existing_media_inspect_and_extract_semantics(tmp_path):
    src=bob_fixture()
    path=tmp_path/'ANIM.BOB'
    path.write_bytes(src)
    module=next(x for x in media_modules()['modules'] if x['name']=='castles2-bob')
    assert module['methods']==['media-inspect','media-extract']
    result=inspect_media(path,adapter='castles2-bob')
    assert result['inputs']==[{'role':'container','size':len(src),'sha256':sha256(src).hexdigest()}]
    assert result['bob_dimensions']=={'width':3,'height':2}
    members={x['name']:x for x in result['members']}
    assert len(members)==3
    assert (members['palette-rgb']['offset'],members['palette-rgb']['size'])==(4,768)
    assert (members['indices']['offset'],members['indices']['size'])==(772,6)
    assert members['indices']['sha256']==sha256(src[772:]).hexdigest()
    assert members['preview-png']['offset'] is None
    assert 'pixels' not in str(result)
    private=tmp_path/'private'
    private.mkdir(mode=0o700)
    exported=extract_media(path,private/'export',adapter='castles2-bob',member='preview-png')
    payload=Path(exported['output'])/'payload.bin'
    with Image.open(payload) as im:
        assert im.size==(3,2)
        assert im.convert('RGB').getpixel((2,0))==(15,90,230)
    assert (private/'export/media-manifest.json').exists()
    with pytest.raises(ValueError,match='Unknown member'):
        extract_media(path,private/'missing',adapter='castles2-bob',member='frame9')


def test_reject_directory_number_symlink_and_invalid_source(tmp_path):
    src=tmp_path/'image.BOB'
    src.write_bytes(bob_fixture())
    with pytest.raises(ValueError,match='standalone'):
        inspect_media(src,adapter='castles2-bob',number=1)
    alias=tmp_path/'alias.BOB'
    alias.symlink_to(src)
    with pytest.raises(ValueError,match='symlink'):
        inspect_media(alias,adapter='castles2-bob')
    with pytest.raises((ValueError,OSError)):
        inspect_media(tmp_path,adapter='castles2-bob')
    with pytest.raises(ValueError,match='Unsupported adapter'):
        inspect_media(src,adapter='bob')


def test_common_320x200_corpus_dimensions():
    image=decode_bob(bob_fixture(320,200))
    assert len(image.pixels)==64000
    assert image.png().startswith(b'\x89PNG\r\n\x1a\n')


def test_cli_dynamic_adapter_routing_without_new_command(tmp_path,capsys):
    from fdisbull.cli import main, respond
    import json
    src=tmp_path/'frame.BOB'
    src.write_bytes(bob_fixture())
    assert main(['media-inspect',str(src),'--adapter','castles2-bob'])==0
    printed=json.loads(capsys.readouterr().out)
    assert printed['ok'] and printed['result']['bob_dimensions']=={'width':3,'height':2}
    response=respond({'method':'media-inspect','params':{'path':str(src),'adapter':'castles2-bob'}})
    assert response['ok'] and response['result']['members'][0]['name']=='palette-rgb'
    assert main(['media-extract',str(src),str(tmp_path/'out'),
                 '--adapter','castles2-bob','--member','indices'])==0
    assert (tmp_path/'out/payload.bin').read_bytes()==bytes([0,1,2,3,2,1])
