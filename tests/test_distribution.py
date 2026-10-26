"""Check the release guard with hostile additions to an otherwise valid archive."""
from pathlib import Path
import runpy
import zipfile

import pytest


@pytest.mark.parametrize('unwanted',[
    'local.fdb','local.fdb-wal','local.db','local.sqlite','local.sqlite3',
    'checkpoint.sav','checkpoint.STATE','GAME.EXE','GAME.COM','VARS.DAT',
])
def test_distribution_check_rejects_game_state_and_database_files(tmp_path,unwanted):
    check=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/check_dist.py'))['check_archive']
    archive=tmp_path/'fdisbull-test-tool.zip'
    required_files=('src/fdisbull/__init__.py','pyproject.toml','tests/fixtures_formats.py','tests/fixtures_macho.py',
                         'tests/wine_gui_fixture.c','tests/dosbox_zip_empty_write.cpp','src/fdisbull/wine_guest/agent.c',
                         'src/fdisbull/wine_guest/init.sh','src/fdisbull/wine_guest/broker.py',
                         'tests/ida_rpc_vectors.json','src/fdisbull/ida_wire.py','src/fdisbull/ida_remote.py',
                         'src/fdisbull/ida_guest/broker.py','src/fdisbull/ida_guest/init.sh',
                         'src/fdisbull/ida_guest/ui.c','src/fdisbull/ida_guest/SDK-LICENSE.txt','src/fdisbull/ida_trace.py',
                         'src/fdisbull/dos_guest/__init__.py','src/fdisbull/dos_guest/init.sh','src/fdisbull/dos_guest/broker.py',
                         'src/fdisbull/dos_qemu.py','src/fdisbull/dos_runtime.py','src/fdisbull/qemu_machine.py',
                         'src/fdisbull/gdb_rpc.py','src/fdisbull/guest_assets.py')
    with zipfile.ZipFile(archive,'w') as output:
        for required in required_files:
            output.writestr('fdisbull-test/'+required,'')
    assert check(archive)==25
    with zipfile.ZipFile(archive,'a') as output:
        output.writestr('fdisbull-test/docs/'+unwanted,'local bytes')
    with pytest.raises(ValueError,match='Excluded binary/data file'):
        check(archive)
