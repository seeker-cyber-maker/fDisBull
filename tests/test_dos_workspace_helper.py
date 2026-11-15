"""Source/template and v2 report ABI for the authored workspace loader."""
from pathlib import Path
import os
import shutil
import struct
import subprocess

import pytest
from fdisbull import dos_workspace_helper as helper

NONCE=bytes(range(16))


@pytest.fixture
def nasm():
    path=os.environ.get('FDISBULL_NASM') or shutil.which('nasm')
    if not path:
        if os.environ.get('FDISBULL_REQUIRE_DOS_HELPER_ASSEMBLY')=='1':
            pytest.fail('NASM required for workspace loader source/template gate')
        pytest.skip('NASM not available')
    return str(Path(path).resolve(strict=True))


def test_source_assembles_to_embedded_template(tmp_path,nasm):
    source=Path(helper.__file__).with_name('dos_guest')/'dos_workspace_loader.asm'
    output=tmp_path/'workspace.com'
    subprocess.run([nasm,'-f','bin',str(source),'-o',str(output)],check=True,capture_output=True,timeout=15)
    assert output.read_bytes()==helper._LOADER_TEMPLATE
    start,end=helper.loader_code_ranges()[1]
    assert start>=helper._PARENT_FILE_OFFSET+128 and end==len(output.read_bytes())-1024


def test_path_and_parent_match_independent_assembly(tmp_path,nasm):
    source=Path(helper.__file__).with_name('dos_guest')/'dos_workspace_loader.asm'
    output=tmp_path/'with-path.com'
    subprocess.run([nasm,'-f','bin',str(source),'-o',str(output),
        '-DFDB_TARGET="D:\\SUB\\GAME.COM"','-DFDB_PARENT="D:\\SUB"',
        '-DFDB_COMMAND_TAIL=32,47,81',
        '-DFDB_NONCE_BYTES='+','.join(str(x) for x in NONCE)],
        check=True,capture_output=True,timeout=15)
    assert output.read_bytes()==helper.build_loader('D:\\SUB\\GAME.COM',b' /Q',NONCE)


@pytest.mark.parametrize('target,parent',[
    ('D:\\GAME.COM','D:\\'),('d:\\SUB\\GAME.EXE','d:\\SUB'),
    ('Z:\\ONE\\TWO\\ABCDEF12.BIN','Z:\\ONE\\TWO'),
])
def test_patches_absolute_target_tail_and_parent(target,parent):
    image=helper.build_loader(target,b' /Q',NONCE)
    assert image[12:28]==NONCE
    assert image[101:229].split(b'\0',1)[0]==target.encode('ascii')
    assert image[229:234]==b'\x03 /Q\r'
    assert image[357:485].split(b'\0',1)[0]==parent.encode('ascii')


def test_127_byte_target_fits_and_128_refuses():
    target='D:\\'+'A\\'*56+'ABCDEF12.COM'
    assert len(target)==127
    assert helper.build_loader(target,b'',NONCE)[101:229]==target.encode()+b'\0'
    with pytest.raises(ValueError,match='127'):
        helper.build_loader('D:\\AB\\'+'A\\'*55+'ABCDEF12.COM',b'',NONCE)


@pytest.mark.parametrize('target',['','GAME.COM','D:GAME.COM','\\GAME.COM','D:\\',
    'D:\\..\\A.COM','D:\\A\\\\B.COM','D:\\NUL.TXT','D:\\COM1\\A.COM',
    'D:\\TOOLONG99.COM','D:\\A.BADX','D:\\A B.COM','D:\\*.COM','D:\\É.COM'])
def test_invalid_or_unsafe_paths_refused(target):
    with pytest.raises(ValueError): helper.build_loader(target,b'',NONCE)


@pytest.mark.parametrize('tail',[b'x'*127,b'a\0b',b'a\rb',b'a\nb','str',None])
def test_bad_tail_refused(tail):
    with pytest.raises(ValueError,match='command tail'): helper.build_loader('D:\\A.COM',tail,NONCE)


def frame():
    frame=bytearray(helper.build_loader('D:\\DIR\\A.COM',b'',NONCE)[4:100])
    frame[5]=helper.READY
    for offset,value in {24:0x2000,26:0x2100,28:0x2120,30:0x30,32:0x2140,34:0xfff0,
                         36:0xff00,46:0,48:0x0a07,50:0xfd,52:0x2000,54:0x202,
                         56:0xffee,66:0x90,68:0x26,70:0x70}.items():
        struct.pack_into('<H',frame,offset,value)
    return frame


def test_report_decodes_v2_and_checks_nonce():
    result=helper.parse_report(bytes(frame()),NONCE)
    assert result['schema']==2 and result['type']=='ready' and result['helper_psp']==0x2000
    with pytest.raises(ValueError,match='nonce'): helper.parse_report(bytes(frame()),b'X'*16)


@pytest.mark.parametrize('field', ['control_offset','ready_wait_ip','exit_wait_ip','report_offset',
    'target_offset','command_tail_offset','helper_paragraphs','initial_flags'])
def test_report_refuses_each_changed_layout_word(field):
    raw=frame();offset=helper.REPORT_FIELDS[field]
    struct.pack_into('<H',raw,offset,struct.unpack_from('<H',raw,offset)[0]^1)
    with pytest.raises(ValueError,match='helper layout'): helper.parse_report(bytes(raw),NONCE)


def test_report_refuses_v1_and_invalid_reserved_bytes():
    raw=frame();raw[4]=1
    with pytest.raises(ValueError,match='header'): helper.parse_report(bytes(raw),NONCE)
    raw=frame();raw[74]=1
    with pytest.raises(ValueError,match='reserved'): helper.parse_report(bytes(raw),NONCE)
