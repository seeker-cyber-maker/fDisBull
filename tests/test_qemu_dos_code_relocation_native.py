"""Native MZ relocation normalization across a closed QEMU session."""
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import digest, mz_exit, prepare_dos_baseline
from test_qemu_dos_checkpoint_sessions_native import _inputs, _number, _open_debug


def test_qemu_mz_capture_promotes_complete_relocation_after_reopen(tmp_path):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img',
                                runtime['FDISBULL_QEMU_DOS_MCOPY'])
    source, fixture = mz_exit()
    binary = tmp_path / 'RELOC.EXE'
    binary.write_bytes(source)
    database = tmp_path / 'relocation.fdb'

    with Project.create(database, binary) as project:
        static = project.regions(1)[0].start
        project_cs = static // 16 + fixture['relative_cs']
        address = static + 0x21  # MOV AX,7; the immediate is an MZ fixup.
        project.analyze(start=address, cs=project_cs, max_instructions=1)
        parent = project.disassembly(address, cs=project_cs, lines=1)['instructions'][0]['bytes']
        assert parent == (b'\xb8' + (static // 16 + 7).to_bytes(2, 'little')).hex()
        with _open_debug(project, runtime, tmp_path, disk) as debug:
            process = debug.dos_process_info()
            load = _number(process['source_mapping']['load_segment'])
            assert _number(process['entry']['cs']) == load + fixture['relative_cs']
            observed = debug.code(address, cs=project_cs, length=3, view='ram', space='source')
            assert observed['instructions'][0]['bytes'] == (b'\xb8' + (load + 7).to_bytes(2, 'little')).hex()
            assert observed['runtime_cs'] == hex(load + fixture['relative_cs'])
            full = debug.capture_code(address, cs=project_cs, length=3, view='ram', space='source')['artifact']
            partial = debug.capture_code(address + 2, cs=project_cs, length=1, view='ram', space='source')['artifact']

    with Project(database) as project:
        promoted = project.debug_promote_code(full, max_instructions=1)
        version = promoted['version']
        assert project.disassembly(address, cs=project_cs, version=version, lines=1)['instructions'][0]['bytes'] == parent
        assert project.runtime_version_info(version)['relocations'][0]['project_hex'] == parent[2:]
        before = len(project.versions())
        with pytest.raises(ValueError, match='cuts through'):
            project.debug_promote_code(partial)
        assert len(project.versions()) == before
        assert project.disassembly(address, cs=project_cs, version=1, lines=1)['instructions'][0]['bytes'] == parent
    assert binary.read_bytes() == source and digest(boot) == boot_hash
