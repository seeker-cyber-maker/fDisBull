"""Offline alias dispatch over authored metadata, not a native-state claim."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from fdisbull.cli import invoke
from fdisbull.project import Project
from test_dos_loader import mz_file


def test_anchor_stone_info_dispatches_offline_after_project_restart(tmp_path):
    executable = tmp_path / 'AUTHORED.EXE'
    executable.write_bytes(mz_file())
    project = tmp_path / 'authored.fdb'
    state = io.BytesIO()
    with zipfile.ZipFile(state, 'w') as archive:
        archive.writestr('CPU', b'authored metadata fixture; not a resumable machine')
    with Project.create(project, executable) as db:
        with db.transaction(True):
            db.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                          ('authored-run', db.version()['id'], 'now', 'now', 'closed', '{}'))
        artifact = db._debug_artifact('authored-run', 'metadata.sav', 'state', state.getvalue(),
                                     {'format': 'authored-metadata-only'})['artifact']
        expected = db.debug_state_info(artifact)
    assert invoke('debug-anchor-stone-info', {'project': str(project), 'artifact': artifact}) == expected
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
    process = subprocess.run([sys.executable, '-m', 'fdisbull', 'debug-anchor-stone-info',
                              str(project), artifact], capture_output=True, text=True, env=environment)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)['result'] == expected
