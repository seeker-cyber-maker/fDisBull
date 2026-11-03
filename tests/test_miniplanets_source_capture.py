"""Authored source fixtures; no original cartridge or asset data is required."""
import hashlib
from pathlib import Path

import pytest

pytest.importorskip('pycparser')
from fdisbull import udl_miniplanets_full as lifter


def test_lift_hashes_the_bytes_it_parsed_during_concurrent_source_edit(tmp_path,monkeypatch):
    units=tmp_path/'game_sources';units.mkdir()
    target=units/'miniplanets_full.c'
    original=b'typedef unsigned char u8;u8 counter;void game_boot(void){counter=0;}'
    target.write_bytes(original)
    (units/'miniplanets_actors.c').write_bytes(b'void game_frame(void){counter++;}')
    edited=b'this later edit is deliberately not valid authoring syntax'
    read_bytes,read_text=Path.read_bytes,Path.read_text
    reads=[]
    def capture_and_edit_bytes(path,*args,**kwargs):
        value=read_bytes(path,*args,**kwargs)
        if path==target:
            reads.append('bytes');path.write_bytes(edited)
        return value
    def capture_and_edit_text(path,*args,**kwargs):
        value=read_text(path,*args,**kwargs)
        if path==target:
            reads.append('text');path.write_bytes(edited)
        return value
    monkeypatch.setattr(lifter,'__file__',str(tmp_path/'udl_miniplanets_full.py'))
    monkeypatch.setattr(Path,'read_bytes',capture_and_edit_bytes)
    monkeypatch.setattr(Path,'read_text',capture_and_edit_text)
    # This synthetic cartridge only supplies55 empty stage descriptors.  Its
    # profile identity is bypassed solely to isolate source capture behavior.
    rom=bytearray(524288);rom[256]=255
    monkeypatch.setattr(lifter,'checked_rom',lambda raw:raw)
    result=lifter.lift_full_game(bytes(rom))
    assert result['program']['evidence']['authoring_units'][target.name]==hashlib.sha256(original).hexdigest()
    assert read_bytes(target)==edited
    assert reads==['bytes']
