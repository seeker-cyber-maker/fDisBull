"""One PE container can retain an independently selectable DOS load image."""
import hashlib
import struct

import pytest

from fdisbull.dos import load_mz
from fdisbull.image_views import image_views, secondary_header
from fixtures_formats import pe64
from test_dos_loader import mz_file


def dual_pe_mz():
    """Valid x86-64 PE and classic DOS MZ stub, each with a different entry."""
    data=bytearray(pe64())
    # DOS load module is only 0x40 bytes: native PE starts at 0x80 and is an
    # overlay from the DOS loader's perspective. Relocation fixes MOV AX,imm.
    struct.pack_into('<14H',data,0,0x5a4d,0x80,1,1,4,1,0xffff,0,0x40,0,0,0,0x1c,0)
    struct.pack_into('<HH',data,0x1c,1,0)
    data[0x40:0x48]=bytes.fromhex('b801008ed8b8004c')
    data[0x48:0x4a]=bytes.fromhex('cd21')
    data[0x4a:0x80]=b'\0'*(0x80-0x4a)
    struct.pack_into('<I',data,0x3c,0x80)
    return bytes(data)


def test_secondary_loader_remains_opt_in_and_retains_both_source_images():
    data=dual_pe_mz()
    with pytest.raises(ValueError,match='PE secondary'):
        load_mz(data)
    image=load_mz(data,allow_secondary=True,load_segment=0x2000)
    assert (image.format,image.arch,image.bits,image.entry)==('MZ','x86',16,0x20000)
    assert image.source_bytes==data
    assert image.metadata['source_sha256']==hashlib.sha256(data).hexdigest()
    assert image.metadata['selected_image']=='mz'
    assert image.metadata['secondary_format']=='PE'
    assert image.metadata['secondary_header_offset']==0x80
    dos=image.metadata['dos']
    assert (dos['declared_file_size'],dos['header_size'],dos['module_size'])==(0x80,0x40,0x40)
    assert (dos['overlay_offset'],dos['overlay_size'])==(0x80,len(data)-0x80)
    assert image.regions[0].data[:3]==bytes.fromhex('b80120')
    assert len(image.regions[0].data)==0x50  # 0x40 module plus one minimum paragraph.
    assert image.regions[0].data[0x40:]==bytes(0x10)
    assert b'PE\0\0' not in image.regions[0].data
    assert image.source_bytes[0x80:0x84]==b'PE\0\0'


def test_both_recognized_views_are_listed_with_separate_entries_and_offsets():
    views=image_views(dual_pe_mz())
    assert [v['image'] for v in views]==['mz','pe']
    mz,pe=views
    assert mz['available'] and mz['loadable'] and mz['header_offset']==0
    assert mz['entrypoint']==0x10000 and mz['bits']==16
    assert mz['declared_file_size']==0x80 and mz['module_file_offset']==0x40
    assert pe['available'] and pe['valid'] and pe['header_offset']==0x80
    assert (pe['arch'],pe['bits'],pe['entrypoint'])==('x86',64,0x140001000)
    assert pe['section_count']==1 and pe['header_end']==0x1b0
    assert secondary_header(dual_pe_mz())==dict(format='PE',header_offset=0x80)


def test_valid_pe_with_invalid_dos_pages_still_offers_native_view_only():
    # Existing fixture deliberately leaves the legacy DOS fields zero.
    views=image_views(pe64())
    mz,pe=views
    assert not mz['available'] and not mz['loadable'] and 'page count' in mz['error']
    assert pe['available'] and pe['valid']
    with pytest.raises(ValueError,match='page count'):
        load_mz(pe64(),allow_secondary=True)


def test_explicit_secondary_view_keeps_mz_validation_strict():
    data=bytearray(dual_pe_mz())
    struct.pack_into('<HH',data,0x1c,0x3f,0) # incomplete final relocation word.
    with pytest.raises(ValueError,match='relocation target'):
        load_mz(bytes(data),allow_secondary=True)
    assert 'relocation target' in image_views(bytes(data))[0]['error']
    struct.pack_into('<HH',data,0x1c,1,0)
    struct.pack_into('<H',data,2,512)
    with pytest.raises(ValueError,match='last-page'):
        load_mz(bytes(data),allow_secondary=True)


@pytest.mark.parametrize('signature',[b'NE',b'LE',b'LX'])
def test_other_secondary_headers_require_explicit_opt_in(signature):
    data=bytearray(mz_file(overlay=signature+b'\0'*200))
    struct.pack_into('<I',data,0x3c,96)
    assert secondary_header(bytes(data))==dict(format=signature.decode(),header_offset=96)
    with pytest.raises(ValueError,match='secondary'):
        load_mz(bytes(data))
    assert load_mz(bytes(data),allow_secondary=True).metadata['secondary_format']==signature.decode()
    assert [v['image'] for v in image_views(bytes(data))]==['mz']


def test_relocation_overlap_never_invents_independent_secondary_header():
    # Relocation table occupies 0x3c..0x3f. The same four bytes incidentally
    # point to a PE marker in a trailing overlay, but remain relocation data.
    data=bytearray(mz_file(bytes(0x100),relocations=[(0x80,0)],header_size=80,
                           relocation_offset=60,overlay=b'PE\0\0'))
    data[0x80:0x84]=b'PE\0\0'
    assert struct.unpack_from('<I',data,0x3c)[0]==0x80
    assert secondary_header(bytes(data)) is None
    assert [v['image'] for v in image_views(bytes(data))]==['mz']
    assert load_mz(bytes(data)).metadata['secondary_format'] is None


@pytest.mark.parametrize('value',[0,1,None,'true',[],{}])
def test_allow_secondary_requires_an_actual_boolean(value):
    with pytest.raises(ValueError,match='allow_secondary'):
        load_mz(dual_pe_mz(),allow_secondary=value)


def test_truncated_secondary_signature_stays_an_unavailable_pe_view():
    data=bytearray(dual_pe_mz()[:0x84])
    views=image_views(bytes(data))
    assert views[0]['available']
    assert not views[1]['available'] and 'COFF' in views[1]['error']


def test_classic_mz_and_arbitrary_lfanew_bytes_do_not_add_native_views():
    data=bytearray(mz_file())
    struct.pack_into('<I',data,0x3c,0x12345678)
    views=image_views(bytes(data))
    assert len(views)==1 and views[0]['image']=='mz' and views[0]['available']
    assert image_views(b'\x7fELF'+bytes(64))==[]
    assert image_views(b'MZ')[0]['available'] is False
