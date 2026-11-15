"""Explicit CHIP-8 intake and persistent facts through the ordinary analyzer."""
import hashlib
import pytest

from fdisbull.chip8 import PROFILE
from fdisbull.cli import main, respond
from fdisbull.decoder import decode
from fdisbull.loader import load_image
from fdisbull.memory import instruction_memory_accesses
from fdisbull.project import Project


def _rom(tmp_path, data=bytes.fromhex('60013001120a220c120a120a00ee')):
    path = tmp_path / 'authored.ch8'
    path.write_bytes(data)
    return path


def test_explicit_intake_analysis_restart_and_patch_isolation(tmp_path):
    rom = _rom(tmp_path)
    source = rom.read_bytes()
    db = tmp_path / 'analysis.fdb'
    with Project.create(db, rom, arch='chip8') as project:
        assert project.context == 'chip8:16:big'
        assert project.meta['loader_metadata']['chip8_profile'] == PROFILE
        assert project.meta['entry'] == 0x200
        project.analyze(max_instructions=100)
        rows = project.disassembly(address=0x200, lines=7)['instructions']
        assert rows
        edges = project.xrefs(0x206, direction='to')
        assert any(e['kind'] == 'branch' and int(e['source'], 0) == 0x202 for e in edges)
        child = project.patch(0x201, '07', label='authored immediate')
        assert project.regions(child['version'])[0].data[:2] == bytes.fromhex('6007')
        assert project.regions(1)[0].data[:2] == bytes.fromhex('6001')
    with Project(db) as project:
        assert project.context == 'chip8:16:big'
        assert project.meta['source_sha256'] == hashlib.sha256(source).hexdigest()
        assert project.regions(1)[0].data[:2] == bytes.fromhex('6001')
        assert project.disassembly(address=0x200, lines=1, version=1)['instructions'][0]['mnemonic'] == 'ld_vx_kk'
        from fdisbull.render import render_snapshot
        snapshot = project.disassembly(address=0x200, lines=7, version=1)
        svg = tmp_path / 'chip8-static-disassembly.svg'
        png = tmp_path / 'chip8-static-disassembly.png'
        render_snapshot(snapshot, svg)
        render_snapshot(snapshot, png)
        assert '<svg' in svg.read_text() and 'ld_vx_kk' in svg.read_text()
        assert png.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    assert rom.read_bytes() == source


def test_profile_admission_is_explicit_bounded_and_allows_data_tail(tmp_path):
    rom = _rom(tmp_path, bytes.fromhex('1200') + b'\xff')
    image = load_image(rom, profile=PROFILE)
    assert image.arch == 'chip8' and image.bits == 16
    assert image.regions[0].start == image.entry == 0x200
    assert image.source_bytes == rom.read_bytes()
    assert image.metadata['instruction_endian'] == 'big'
    for options in ({'arch':'chip8','bits':32}, {'arch':'chip8','base':0},
                    {'arch':'chip8','entry':0x202}, {'arch':'chip8','module':True},
                    {'arch':'chip8','profile':'xo-chip'}, {'profile':PROFILE,'arch':'x86'}):
        with pytest.raises(ValueError):
            load_image(rom, **options)
    for data in (b'\x00', b'\x00' * 3585):
        rom.write_bytes(data)
        with pytest.raises(ValueError, match='2..3584'):
            load_image(rom, arch='chip8')


def test_decoder_dispatch_and_memory_unknowns():
    assert decode(bytes.fromhex('3001'), 0x200, 'chip8', 16)['target'] == 0x204
    assert decode(bytes.fromhex('f055'), 0x201, 'chip8', 16) is None
    with pytest.raises(ValueError):
        decode(bytes.fromhex('6001'), 0x200, 'chip8', 32)
    unknown = instruction_memory_accesses(bytes.fromhex('f155'), 0x200, 'chip8', 16)[0]
    assert unknown['width'] == 2 and unknown['may_write']
    assert unknown['concrete_target'] is None and unknown['unresolved_reasons']
    known = instruction_memory_accesses(bytes.fromhex('f165'), 0x200, 'chip8', 16, registers={'i':0x300})[0]
    assert known['concrete_target'] == 0x300 and known['interval_end'] == 0x302
    bad = instruction_memory_accesses(bytes.fromhex('f165'), 0x200, 'chip8', 16, registers={'i':0xfff})[0]
    assert bad['concrete_target'] is None and 'exceeds 4 KiB' in bad['unresolved_reasons'][0]


def test_json_and_cli_import_profile(tmp_path, capsys):
    rom = _rom(tmp_path)
    result = respond({'method':'import','params':{'path':str(rom),'project':str(tmp_path/'json.fdb'),'arch':'chip8'}})
    assert result['ok'], result
    assert main(['import', str(rom), str(tmp_path/'cli.fdb'), '--profile', PROFILE]) == 0
    assert 'chip8' in capsys.readouterr().out


def test_debugger_route_requires_explicit_backend_and_refuses_pc_options(tmp_path, monkeypatch):
    from fdisbull import qemu_chip8
    rom = _rom(tmp_path)
    captured = {}
    def session(project, executable, **options):
        captured.update(options)
        return captured
    monkeypatch.setattr(qemu_chip8, 'Chip8DebugSession', session)
    with Project.create(tmp_path/'debug.fdb', rom, arch='chip8') as project:
        with pytest.raises(ValueError, match='explicit backend=qemu-chip8'):
            project.debugger('unused', tmp_path)
        with pytest.raises(ValueError, match='without DOS/PC'):
            project.debugger('unused', tmp_path, backend='qemu-chip8', qemu_clock='virtual')
        result = project.debugger('unused', tmp_path, backend='qemu-chip8', boot_timeout_ms=1000)
        assert result['rom'] == rom and result['timeout_ms'] == 1000
