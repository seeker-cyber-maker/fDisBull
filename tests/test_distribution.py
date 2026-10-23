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
    with zipfile.ZipFile(archive,'w') as output:
        for required in ('src/fdisbull/__init__.py','pyproject.toml','tests/fixtures_formats.py','tests/fixtures_macho.py'):
            output.writestr('fdisbull-test/'+required,'')
    assert check(archive)==4
    with zipfile.ZipFile(archive,'a') as output:
        output.writestr('fdisbull-test/docs/'+unwanted,'local bytes')
    with pytest.raises(ValueError,match='Excluded binary/data file'):
        check(archive)
