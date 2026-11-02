"""The runtime hash must describe the library actually passed to the linker."""
import hashlib
import os
from pathlib import Path

import pytest


def test_native_link_uses_captured_library_despite_later_source_edit(tmp_path, monkeypatch):
    root = os.environ.get('FDISBULL_CC65_ROOT')
    source = os.environ.get('FDISBULL_MINIPLANETS_ROM')
    if not root or not source:
        pytest.skip('requires explicitly prepared cc65 and private Miniplanets ROM')
    from fdisbull import udc_nes_game as backend
    from fdisbull.udl_miniplanets_full import lift_full_game
    prepared = Path(root)
    private_tools = tmp_path / 'tools'
    (private_tools / 'bin').mkdir(parents=True)
    (private_tools / 'lib').mkdir()
    for name in ('cc65', 'ca65', 'ld65', 'od65'):
        (private_tools / 'bin' / name).symlink_to((prepared / 'bin' / name).resolve())
    library = (prepared / 'lib/nes.lib').read_bytes()
    live = private_tools / 'lib/nes.lib'
    live.write_bytes(library)
    original_run = backend._run
    links = []

    def mutate_before_link(argv, work):
        if Path(argv[0]).name == 'ld65':
            links.append(Path(argv[-1]))
            assert Path(argv[-1]).read_bytes() == library
            live.write_bytes(b'not a usable runtime library')
        return original_run(argv, work)

    monkeypatch.setattr(backend, '_run', mutate_before_link)
    rom = Path(source).read_bytes()
    out = tmp_path / 'cartridge'
    manifest = backend.build_nes_game(lift_full_game(rom)['program'], rom, out,
                                     cc65_root=private_tools)
    assert links == [out / 'build/nes.lib']
    assert (out / 'build/nes.lib').read_bytes() == library
    assert manifest['runtime_resources']['nes.lib'] == {
        'sha256': hashlib.sha256(library).hexdigest(),
        'length': len(library), 'captured_path': 'build/nes.lib'}
    assert manifest['rom_sha256'] == hashlib.sha256((out / 'program.nes').read_bytes()).hexdigest()
