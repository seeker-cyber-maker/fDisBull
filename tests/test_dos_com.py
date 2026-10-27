"""Explicit DOS COM selection and real-mode launch contracts."""
import hashlib
import os
from pathlib import Path
import pytest
from fdisbull.dos import load_com
from fdisbull.loader import load_image
from fdisbull.project import Project
from fdisbull.cli import respond
from fdisbull.dos_launch import guest_name
from test_dos_loader import mz_file

CODE = bytes.fromhex('b83412bb7856ebfe')


def test_com_requires_explicit_selection_and_maps_only_file_bytes(tmp_path):
    binary=tmp_path/'GAME.COM'; binary.write_bytes(CODE)
    with pytest.raises(ValueError,match='unsupported'):
        load_image(binary)
    image=load_image(binary,image='com',load_segment=0x2000)
    assert (image.format,image.arch,image.bits,image.entry)==('COM','x86',16,0x20100)
    assert image.regions[0].start==0x20100 and image.regions[0].data==CODE
    assert image.metadata['dos']['psp_segment']==0x2000
    assert image.metadata['dos']['sp'] is None
    assert image.metadata['source_sha256']==hashlib.sha256(CODE).hexdigest()
    assert image.metadata['file_mappings']==[dict(virtual_address=0x20100,file_offset=0,file_size=len(CODE))]
    with Project.create(tmp_path/'test.fdb',binary,image='com',load_segment=0x2000) as db:
        db.analyze(max_instructions=10)
        rows=db.disassembly()['instructions']
        assert rows[0]['segmented_address']=='2000:0100' and rows[0]['bytes']=='b83412'
        access=db.memory_accesses('2000:0100')
        assert access['selector']==0x2000 and access['address']==db.memory_accesses(0x20100)['address']
        assert 'sp' not in rows[0]['assumptions']['registers']
        assert db._mapping(1,0x20000) is None
        old=db.version(1)['sha256']
        child=db.patch('2000:0101','aa')['version']
        assert db.version(1)['sha256']==old and db.regions(1)[0].data==CODE
        assert db.regions(child)[0].data==CODE[:1]+b'\xaa'+CODE[2:]
        signature_child=db.patch('2000:0100','4d5a',version=1)['version']
        assert db.regions(signature_child)[0].data.startswith(b'MZ')
        assert any('MZ signature' in w for w in db._document(signature_child)['warnings'])
        with pytest.raises(ValueError,match='unpatched'):
            db.debugger('/does/not/exist',tmp_path,version=child)


def test_com_bounds_and_format_selection(tmp_path):
    assert len(load_com(b'X'*0xff00).regions[0].data)==0xff00
    for data in (b'',b'X'*0xff01,b'MZ'+bytes(28),b'ZM'+bytes(28)):
        with pytest.raises(ValueError): load_com(data)
    with pytest.raises(ValueError,match='1 MiB'): load_com(b'X'*0x100,load_segment=0xfff0)
    binary=tmp_path/'fake.com';binary.write_bytes(mz_file())
    assert load_image(binary).format=='MZ'
    with pytest.raises(ValueError,match='MZ-signature'):load_image(binary,image='com')
    with pytest.raises(ValueError):load_image(binary,image='com',arch='x86')
    with pytest.raises(ValueError):load_image(binary,image='com',base=1)
    assert guest_name('long game name', 'abcdef00','COM')=='FBABCDEF.COM'
    assert guest_name('GAME.EXE','abcdef00','COM')=='FBABCDEF.COM'


def test_com_cli_json_import(tmp_path):
    binary=tmp_path/'GAME.COM';binary.write_bytes(CODE)
    result=respond({'method':'import','params':{'path':str(binary),'project':str(tmp_path/'cli.fdb'),'image':'com'}})
    assert result.get('error') is None, result
    with Project(tmp_path/'cli.fdb') as db: assert db.meta['format']=='COM'


def test_com_source_hash_guard(tmp_path):
    binary=tmp_path/'GAME.COM';binary.write_bytes(CODE)
    with Project.create(tmp_path/'guard.fdb',binary,image='com') as db:
        binary.write_bytes(CODE+b'x')
        with pytest.raises(ValueError,match='source hash'):
            db.debugger('/does/not/exist',tmp_path)
        assert not db.debug_runs(version=1)['runs']


def test_com_native_launch_and_breakpoint(tmp_path):
    emulator=os.environ.get('FDISBULL_DOSBOX')
    if not emulator: pytest.skip('Set FDISBULL_DOSBOX for native integration')
    binary=tmp_path/'LONG GAME.COM';binary.write_bytes(CODE)
    with Project.create(tmp_path/'run.fdb',binary,image='com') as db:
        db.analyze(max_instructions=10)
        with db.debugger(emulator,tmp_path) as d:
            regs=d.registers();cs=int(regs['cs'],16)
            assert int(regs['ip'],16)==0x100
            assert all(int(regs['segments'][r],16)==cs for r in ('ds','es','ss'))
            assert d.runtime_base==cs*16+0x100 and d.static_base==0x10100
            assert regs['project_address']=='0x10100'
            assert d.memory('1000:0100',length=len(CODE))['hex']==CODE.hex()
            alias=tmp_path/d.metadata['target'];assert alias.name.endswith('.COM') and alias.read_bytes()==CODE
            bp=d.breakpoint('1000:0106')
            assert bp['bytes_verified']
            assert d.run(timeout_ms=5000,fast_forward=True)['outcome']=='breakpoint'
            d.delete_breakpoint(bp['breakpoint_id'])
            d.run(guest_ms=60,timeout_ms=5000,fast_forward=True)
            frame=d.screenshot('com.png')
            trace=d.trace(count=4)
            checkpoint=d.save_state()
        assert not alias.exists() and binary.read_bytes()==CODE
    with Project(tmp_path/'run.fdb') as db:
        with db.debugger(emulator,tmp_path,version=1) as d:
            restored=d.load_state(checkpoint['artifact'])
            assert restored['artifact']==checkpoint['artifact']
        db.debug_export(frame['artifact'],tmp_path/'saved.png')
        db.debug_export(trace['artifact'],tmp_path/'trace.json')
    assert (tmp_path/'saved.png').read_bytes().startswith(b'\x89PNG')


def test_qemu_state_fork_reuses_source_allowlist_not_derived_alias(tmp_path, monkeypatch):
    binary=tmp_path/'LONG GAME.COM';binary.write_bytes(CODE)
    seen={}
    class Session:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def load_state(self,artifact): seen['loaded']=artifact
        def save_state(self,name): return {'name':name}
    monkeypatch.setattr('fdisbull.debug_state.apply_edits',lambda *args: {'registers': [], 'memory': []})
    with Project.create(tmp_path/'fork.fdb',binary,image='com') as db:
        metadata={'files':[{'path':binary.name},{'path':'FBABCDEF.COM'}],
                  'source_files':[{'path':binary.name}]}
        monkeypatch.setattr(db,'debug_state_info',lambda artifact: {'version':1,'sha256':'fake','metadata':metadata})
        def debugger(executable,game_dir,**options):
            seen.update(options);return Session()
        monkeypatch.setattr(db,'debugger',debugger)
        db.debug_fork_state('old','agent',tmp_path,backend='dosbox-qemu',kernel='kernel',initramfs='initramfs',
                            registers={'eax':{'expected':0,'value':1}})
    assert seen['files']==[binary.name] and seen['loaded']=='old'


def test_com_refuses_stale_static_breakpoint(tmp_path):
    emulator=os.environ.get('FDISBULL_DOSBOX')
    if not emulator: pytest.skip('Set FDISBULL_DOSBOX for native integration')
    # mov byte [0100],90h; jmp $ -- prove later in-range bytes are not presumed original.
    binary=tmp_path/'SELF.COM';binary.write_bytes(bytes.fromhex('c606000190ebfe'))
    with Project.create(tmp_path/'self.fdb',binary,image='com') as db:
        db.analyze(max_instructions=12)
        with db.debugger(emulator,tmp_path) as d:
            stop=d.breakpoint('1000:0105')
            assert d.run(timeout_ms=5000,fast_forward=True)['outcome']=='breakpoint'
            d.delete_breakpoint(stop['breakpoint_id'])
            with pytest.raises(ValueError,match='Runtime code bytes differ'):
                d.breakpoint('1000:0100')
