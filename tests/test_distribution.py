"""Check the release guard with hostile additions to an otherwise valid archive."""
from pathlib import Path
import runpy
import zipfile

import pytest


REQUIRED_SOURCE_FILES=('src/fdisbull/__init__.py','pyproject.toml','tests/fixtures_formats.py','tests/fixtures_macho.py',
                       'tests/wine_gui_fixture.c','tests/dosbox_zip_empty_write.cpp','src/fdisbull/wine_guest/agent.c',
                       'src/fdisbull/wine_guest/init.sh','src/fdisbull/wine_guest/broker.py','src/fdisbull/wine_guest/selftest.c',
                       'tests/ida_rpc_vectors.json','src/fdisbull/ida_wire.py','src/fdisbull/ida_remote.py',
                       'src/fdisbull/ida_guest/broker.py','src/fdisbull/ida_guest/init.sh',
                       'src/fdisbull/ida_guest/ui.c','src/fdisbull/ida_guest/SDK-LICENSE.txt','src/fdisbull/ida_trace.py',
                       'src/fdisbull/dos_guest/__init__.py','src/fdisbull/dos_guest/init.sh','src/fdisbull/dos_guest/broker.py',
                       'src/fdisbull/dos_qemu.py','src/fdisbull/dos_runtime.py','src/fdisbull/qemu_machine.py',
                       'src/fdisbull/gdb_rpc.py','src/fdisbull/guest_assets.py',
                       'src/fdisbull/data/dos-runtime-signatures.json','src/fdisbull/data/MICROSOFT-DOS-LICENSE.txt',
                       'src/fdisbull/skills/fdisbull-investigate/SKILL.md',
                       'src/fdisbull/skills/fdisbull-investigate/references/scenes.md',
                       'src/fdisbull/skills/fdisbull-investigate/references/methodology.md',
                       'src/fdisbull/skills/fdisbull-investigate/references/runtime-navigation.md')


def source_archive(path,files=REQUIRED_SOURCE_FILES):
    with zipfile.ZipFile(path,'w') as output:
        for required in files:output.writestr('fdisbull-test/'+required,'')


@pytest.mark.parametrize('unwanted',[
    'local.fdb','local.fdb-wal','local.db','local.sqlite','local.sqlite3',
    'checkpoint.sav','checkpoint.STATE','GAME.EXE','GAME.COM','VARS.DAT',
])
def test_distribution_check_rejects_game_state_and_database_files(tmp_path,unwanted):
    check=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/check_dist.py'))['check_archive']
    archive=tmp_path/'fdisbull-test-tool.zip'
    source_archive(archive)
    assert check(archive)==len(REQUIRED_SOURCE_FILES)
    with zipfile.ZipFile(archive,'a') as output:
        output.writestr('fdisbull-test/docs/'+unwanted,'local bytes')
    with pytest.raises(ValueError,match='Excluded binary/data file'):
        check(archive)


def test_distribution_check_requires_methodology_reference(tmp_path):
    check=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/check_dist.py'))['check_archive']
    archive=tmp_path/'fdisbull-missing-methodology.zip'
    methodology='src/fdisbull/skills/fdisbull-investigate/references/methodology.md'
    source_archive(archive,tuple(path for path in REQUIRED_SOURCE_FILES if path!=methodology))
    with pytest.raises(ValueError,match='methodology[.]md'):
        check(archive)


def test_distribution_check_requires_runtime_navigation_reference(tmp_path):
    check=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/check_dist.py'))['check_archive']
    archive=tmp_path/'fdisbull-missing-runtime-navigation.zip'
    reference='src/fdisbull/skills/fdisbull-investigate/references/runtime-navigation.md'
    source_archive(archive,tuple(path for path in REQUIRED_SOURCE_FILES if path!=reference))
    with pytest.raises(ValueError,match='runtime-navigation[.]md'):
        check(archive)
