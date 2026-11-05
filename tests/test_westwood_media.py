"""Synthetic Westwood fixtures: no third-party game bytes in repo/tests."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import struct

import pytest

from fdisbull.cli import main, respond
from fdisbull.decoder_modules import builtin_registry, analyze_input
from fdisbull.media import inspect_media, extract_media
from fdisbull.westwood_media import (decode_cps, decode_lcw, decode_rle3,
                                    decode_wsa_frames, inspect_pak, inspect_wsa, parse_emc2)


def pak(entries, *, v3=False, tail=b''):
    # A compact invented Westwood PAK: offsets are absolute file bytes.
    header_bytes = sum(5+len(name) for name,_ in entries)+4+(5 if v3 else 0)
    off=header_bytes;header=bytearray();payload=bytearray()
    for name,content in entries:
        header+=struct.pack('<I',off)+name.encode('ascii')+b'\0'
        payload+=content;off+=len(content)
    if v3:header+=struct.pack('<I',off)+b'\0'
    header+=bytes(4)
    assert len(header)==header_bytes
    return bytes(header+payload+tail)


def cps(payload, *, compression=4, raw_len=4, palette=b''):
    size=8+len(palette)+len(payload) if compression in (0,4) else 10+len(palette)+len(payload)
    return struct.pack('<HHIH',size,compression,raw_len,len(palette))+palette+payload


def emc2(words=(0x4801,), entries=(0,), text=None):
    parts=[]
    def chunk(tag,body):
        return tag+struct.pack('>I',len(body))+body+(b'\0' if len(body)&1 else b'')
    parts.append(chunk(b'ORDR',struct.pack('>'+'H'*len(entries),*entries)))
    if text is not None:parts.append(chunk(b'TEXT',text))
    parts.append(chunk(b'DATA',struct.pack('>'+'H'*len(words),*words)))
    body=b'EMC2'+b''.join(parts)
    return b'FORM'+struct.pack('>I',8+len(body))+body


def wsa(*, late=False, flags=0, chained=False):
    delta=b'\x04ABCD\x80\0\0' # Format40 xor four literals, then termination
    packed=bytes([0x80+len(delta)])+delta+b'\x80' # LCW literals + EOF
    count=1; header_len=14 if late else 8
    start=header_len+4*(count+2)+(768 if flags&1 else 0)
    if late:header=struct.pack('<7H',count,0,0,2,2,8,flags)
    else:header=struct.pack('<4H',count,2,2,8)
    if chained:
        offsets=struct.pack('<3I',0,start,0)
        return header+offsets+bytes(768 if flags&1 else 0)
    offsets=struct.pack('<3I',start,start+len(packed)-(768 if flags&1 else 0),0)
    return header+offsets+bytes(768 if flags&1 else 0)+packed


def test_pak_index_v2_v3_duplicate_names_and_hidden_tail():
    data=pak([('ONE.CPS',b'ab'),('TWO.EMC',b'xyz')])
    x=inspect_pak(data)
    assert x['format']=='westwood-pak-v2'
    assert [(i['name'],i['size']) for i in x['members']]==[('ONE.CPS',2),('TWO.EMC',3)]
    assert x['members'][1]['sha256']==sha256(b'xyz').hexdigest()
    data=pak([('TEST.TLK',b'a'),('test.tlk',b'bb')],v3=True,tail=b'HIDDEN')
    x=inspect_pak(data)
    assert x['format']=='westwood-pak-v3'
    assert [m['size'] for m in x['members']]==[1,2]
    assert x['opaque_tail_bytes']==6
    assert all(m['duplicate_name'] for m in x['members'])


def test_pak_private_extraction_uses_unambiguous_names(tmp_path):
    source=tmp_path/'AUTHORED.PAK'
    source.write_bytes(pak([('same.dat',b'first'),('SAME.DAT',b'second')],v3=True))
    report=inspect_media(source,adapter='westwood-pak')
    assert [x['name'] for x in report['members']]==['#0:same.dat','#1:SAME.DAT']
    receipt=extract_media(source,tmp_path/'private',adapter='westwood-pak',member='#1:SAME.DAT')
    assert (tmp_path/'private/payload.bin').read_bytes()==b'second'
    assert receipt['extracted']['sha256']==sha256(b'second').hexdigest()
    with pytest.raises(ValueError,match='Unknown member'):
        extract_media(source,tmp_path/'bad',adapter='westwood-pak',member='same.dat')


@pytest.mark.parametrize('invalid',[
    b'', b'\x00'*16,
    pak([('A',b'12')])[:-4],
    pak([('A',b'12')])[:4]+b'\xff'*6,
    pak([('A',b'12')]).replace(b'A\0',b'\x01\0',1),
])
def test_pak_malformed_and_unsafe_refused(invalid):
    with pytest.raises(ValueError):inspect_pak(invalid)


def test_lcw_five_commands_and_bounds():
    assert decode_lcw(b'\x83ABC\x80',expected_size=3)==b'ABC'
    assert decode_lcw(b'\x83ABC\x00\x03\x80',expected_size=6)==b'ABCABC'
    assert decode_lcw(b'\x83ABC\xc0\x00\x00\x80',expected_size=6)==b'ABCABC'
    assert decode_lcw(b'\x83ABC\xff\x03\0\0\0\x80',expected_size=6)==b'ABCABC'
    assert decode_lcw(b'\xfe\x04\0Z\x80',expected_size=4)==b'ZZZZ'
    # Flagged relative LCW long-copy (distance of 3, not absolute start 3).
    assert decode_lcw(b'\0\x83ABC\xc0\x03\0\x80',expected_size=6)==b'ABCABC'
    for data in (b'\xfe\xff',b'\x80NOTZERO',b'\0\x80ZZ'):
        with pytest.raises(ValueError):decode_lcw(data)
    with pytest.raises(ValueError,match='out of range'):
        decode_lcw(b'\xfe\xff\xffZ\x80',max_output=5)
    with pytest.raises(ValueError):decode_lcw(b'\x00\x00\x80')


def test_cps_lcw_rle_and_pixel_geometry():
    assert decode_cps(cps(b'\x84DATA\x80')).pixels==b'DATA'
    assert decode_cps(cps(b'ABCD',compression=0)).pixels==b'ABCD'
    # DOS Format3 long-run count is big endian, unlike its CPS container.
    rle=b'\x02AB\xfeZ\0\0\x03X'
    image=decode_cps(cps(rle,compression=3,raw_len=7))
    assert image.pixels==b'ABZZXXX'
    assert image.width is None and image.height is None
    with pytest.raises(ValueError):decode_cps(cps(b'\x80',compression=1))
    with pytest.raises(ValueError):decode_cps(cps(b'\x80')[:-1])
    with pytest.raises(ValueError):decode_rle3(b'\0\xff\xffX',expected_size=1)


def test_wsa_early_late_and_chain_policy():
    a=wsa();info=inspect_wsa(a)
    assert info['variant']=='early'
    _,frames=decode_wsa_frames(a,max_frames=1)
    assert frames==[b'ABCD']
    b=wsa(late=True);info=inspect_wsa(b)
    assert info['variant']=='late'
    assert decode_wsa_frames(b,max_frames=1)[1]==[b'ABCD']
    missing=wsa(chained=True)
    assert inspect_wsa(missing)['missing_first_frame']
    with pytest.raises(ValueError,match='previous chained'):
        decode_wsa_frames(missing,max_frames=1)
    with pytest.raises(ValueError):decode_wsa_frames(missing,max_frames=1,previous=b'AAA')
    report=decode_wsa_frames(missing,max_frames=1,previous=b'WXYZ')
    assert report[1]==[b'WXYZ']


def test_emc2_decoder_module_and_entry_policies(tmp_path):
    script=emc2(words=(0x4103,0x8203,0x4801,0x4107,0x4801),entries=(0,0xffff),text=b'Z')
    source=tmp_path/'authored.EMC';source.write_bytes(script)
    parsed=parse_emc2(script)
    assert parsed['valid_entry_count']==1
    reg=builtin_registry()
    kyr=reg.open('fdisbull.westwood.emc2',source,profile='kyrandia1-dos')
    lol=reg.open('fdisbull.westwood.emc2',source,profile='lol1-dos')
    assert lol.entry.offset == kyr.entry.offset + 2
    a=analyze_input(kyr,max_instructions=5)
    assert a['instructions'][0]['facts']['opcode']==1 # set_ret_value
    assert a['source']['program_sha256']==sha256(script).hexdigest()
    with pytest.raises(ValueError,match='absent'):
        reg.open('fdisbull.westwood.emc2',source,profile='kyrandia1-dos',function_index=1)
    with pytest.raises(ValueError):parse_emc2(script[:-1])
    with pytest.raises(ValueError):parse_emc2(script.replace(b'EMC2',b'EMCX',1))


def test_media_cli_public_contract(tmp_path,capsys):
    src=tmp_path/'frame.CPS'
    src.write_bytes(cps(b'\x84TEST\x80'))
    assert main(['media-inspect',str(src),'--adapter','westwood-cps'])==0
    response=json.loads(capsys.readouterr().out)
    assert response['result']['members'][0]['offset'] is None
    assert main(['media-extract',str(src),str(tmp_path/'private'),
                 '--adapter','westwood-cps','--member','indices'])==0
    assert (tmp_path/'private/payload.bin').read_bytes()==b'TEST'
    assert respond({'method':'decoder-modules'})['ok']


def test_paletted_cps_png_derived_preview(tmp_path):
    from fdisbull.westwood_media import encode_cps_png
    import zlib
    # Authored flat indexed image and its 6-bit VGA palette.
    pal=bytes([0,0,0,63,0,0])+bytes(762)
    frame=cps(b'\xfe\x00\xfa\x01\x80',raw_len=64000,palette=pal)
    image=decode_cps(frame)
    assert image.width == 320 and image.height == 200
    assert image.pixels == bytes([1])*64000
    png=encode_cps_png(image)
    assert png.startswith(b'\x89PNG\r\n\x1a\n')
    # Independently check the indexed palette and real scanline payload.
    chunks=[];pos=8
    while pos<len(png):
        n=struct.unpack_from('>I',png,pos)[0]
        typ=png[pos+4:pos+8];body=png[pos+8:pos+8+n]
        assert zlib.crc32(typ+body) == struct.unpack_from('>I',png,pos+8+n)[0]
        chunks.append((typ,body));pos+=n+12
    assert [x[0] for x in chunks]==[b'IHDR',b'PLTE',b'IDAT',b'IEND']
    assert chunks[1][1][3:6]==bytes([255,0,0])
    decoded=zlib.decompress(chunks[2][1]);assert len(decoded)==200*(320+1)
    assert decoded[:5]==b'\0\x01\x01\x01\x01'
    src=tmp_path/'PANEL.CPS';src.write_bytes(frame)
    receipt=extract_media(src,tmp_path/'out',adapter='westwood-cps',member='preview-png')
    assert (tmp_path/'out/payload.bin').read_bytes()==png
    with pytest.raises(ValueError,match='palette'):
        encode_cps_png(decode_cps(cps(b'\xfe\x00\xfa\x01\x80', raw_len=64000)))
