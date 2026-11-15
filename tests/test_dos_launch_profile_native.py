"""Opt-in original DOS execution, not a simulated RPC contract."""
import base64
import os
from pathlib import Path
import struct

import pytest

from fdisbull.dos_launch_profile import open_dos_session
from fdisbull.project import Project
from test_iso9660 import image


@pytest.mark.parametrize('descriptor', ['iso', 'ins'])
def test_native_command_tail_and_read_only_cd_access(tmp_path,descriptor):
    backend=os.environ.get('FDISBULL_DOSBOX')
    if not backend:
        pytest.skip('Set FDISBULL_DOSBOX for native DOS argument/CD acceptance')
    # mov dx,name; mov ax,3d00h; int21; pushf; pop ax;
    # mov [flags],ax; jmp $. All bytes authored; no original-game fixture.
    code=bytearray.fromhex('ba0001b8003dcd219c58a30001ebfe')
    struct.pack_into('<H',code,1,0x100+len(code)+2)
    struct.pack_into('<H',code,11,0x100+len(code))
    program=tmp_path/'PROBE.COM'
    original=bytes(code)+bytes(2)+b'D:\\ONE.BIN\0'
    program.write_bytes(original)
    blocks=image()
    # This runtime expects the primary descriptor at sector16; the generic
    # ISO inspector separately tests a boot record followed by a primary.
    blocks[16]=blocks[17];blocks[17]=blocks[18]
    iso=tmp_path/'TEST.ISO';iso.write_bytes(b''.join(blocks))
    selected=iso
    if descriptor=='ins':
        selected=tmp_path/'GAME.INS'
        selected.write_text('FILE "TEST.ISO" BINARY\n TRACK 1 MODE1/2048\n INDEX 1 00:00:00\n')
    with Project.create(tmp_path/'run.fdb',program,image='com') as db:
        db.analyze(max_instructions=100)
        with open_dos_session(db,backend,tmp_path,arguments=['-p','TEST'],cd_image=selected) as session:
            cs=int(session.registers()['cs'],16)
            def read(offset,n):
                response=session.call('memory.read',{'address':{'space':'linear',
                    'offset':f'0x{cs*16+offset:08X}'},'length':n})
                return base64.b64decode(response['data_base64'],validate=True)
            assert read(0x80,10)==b'\x08 -p TEST\r'
            session.breakpoint('1000:010d')
            assert session.run(timeout_ms=5000,fast_forward=True)['outcome']=='breakpoint'
            assert not int.from_bytes(read(0x100+len(code),2),'little')&1
            assert session.metadata['launch_profile']['arguments']==['-p','TEST']
            assert session.metadata['launch_profile']['cd']['drive']=='D'
        assert session.rpc.process.poll() is not None
    assert program.read_bytes()==original and iso.read_bytes()==b''.join(blocks)
