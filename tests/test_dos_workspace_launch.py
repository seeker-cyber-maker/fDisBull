"""Host-side launch selection for immutable DOS workspace generations."""
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from fdisbull.dos_file_layers import WorkspaceStore, capture_directory
from fdisbull.dos_workspace_launch import prepare_workspace
from fdisbull.project import Project
from fdisbull import dos_workspace_fat as fat


@pytest.fixture
def project(tmp_path):
    source = tmp_path / 'GAME.COM'
    source.write_bytes(b'\x90\xc3')
    with Project.create(tmp_path / 'game.fdb', source, image='com') as instance:
        yield instance


def _session(project, run_id='workspace-launch'):
    version = project.version()
    metadata = dict(source_sha256=project.meta['source_sha256'], version_sha256=version['sha256'])
    with project.transaction(True):
        project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                           (run_id, version['id'], 'test', None, 'stopped', json.dumps(metadata)))
    session = SimpleNamespace(project=project, version=version, run_id=run_id)
    session._artifact = lambda *args: project._debug_artifact(run_id, *args)
    return session


def _boot(tmp_path):
    path = tmp_path / 'freedos.img'
    image = bytearray(fat.FLOPPY_BYTES)
    image[:3] = b'\xeb\x3c\x90'
    image[3:11] = b'FREEDOS '
    struct.pack_into('<HBHBHHBHHHII', image, 11, 512, 1, 1, 2, 224, 2880,
                     0xf0, 9, 18, 2, 0, 0)
    image[38] = 0x29
    image[43:54] = b'FREEDOS    '
    image[54:62] = b'FAT12   '
    image[510:512] = b'\x55\xaa'
    image[512:515] = b'\xf0\xff\xff'
    image[512 + 9 * 512:512 + 9 * 512 + 3] = b'\xf0\xff\xff'
    path.write_bytes(image)
    return path


def _staging(tmp_path):
    path = tmp_path / 'stage'
    path.mkdir(exist_ok=True)
    return path


def _generation(project, root):
    capture = capture_directory(root)
    store = WorkspaceStore(_session(project))
    return store.seal(capture['entries'], source_root=root,
                      source_identity=capture['root_identity'])['artifact']


def test_explicit_directory_root_captures_source_below_game_directory(project, tmp_path):
    root = tmp_path / 'workspace'
    program_dir = root / 'PROGRAM'
    program_dir.mkdir(parents=True)
    (program_dir / 'GAME.COM').write_bytes(b'\x90\xc3')
    (root / 'README.TXT').write_bytes(b'workspace')

    result = prepare_workspace(project, program_dir, root, 'checkpointed', None,
                               _boot(tmp_path), _staging(tmp_path))

    assert result['capture']['root'] == str(root.resolve())
    assert result['source_dospath'] == 'PROGRAM\\GAME.COM'
    assert result['target'] == 'D:\\PROGRAM\\GAME.COM'
    assert Path(result['source']).read_bytes() == b'\x90\xc3'
    assert result['mode'] == 'checkpointed'


def test_live_directory_mode_is_refused(project, tmp_path):
    with pytest.raises(ValueError, match='Only checkpointed'):
        prepare_workspace(project, tmp_path, tmp_path, 'live', None,
                          _boot(tmp_path), _staging(tmp_path))


def test_cold_generation_launch_survives_source_root_move(project, tmp_path):
    root = tmp_path / 'original-root'
    root.mkdir()
    (root / 'GAME.COM').write_bytes(b'\x90\xc3')
    generation = _generation(project, root)
    moved = tmp_path / 'moved-root'
    root.rename(moved)

    result = prepare_workspace(project, root, None, None, None, _boot(tmp_path),
                               _staging(tmp_path), generation=generation,
                               version_id=project.version()['id'])

    assert result['capture']['root'] == str(root.resolve())
    assert not root.exists()
    assert result['source_dospath'] == 'GAME.COM'
    assert result['target'] == 'D:\\GAME.COM'
    assert Path(result['source']).read_bytes() == b'\x90\xc3'


def test_generation_version_mismatch_is_refused(project, tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    (root / 'GAME.COM').write_bytes(b'\x90\xc3')
    generation = _generation(project, root)
    address = project.regions(project.version()['id'])[0].start
    project.patch(address, 'cc', label='different version')

    with pytest.raises(ValueError, match='another source version'):
        prepare_workspace(project, root, None, None, None, _boot(tmp_path),
                          _staging(tmp_path), generation=generation,
                          version_id=project.version()['id'])


def test_generation_with_edited_original_executable_is_refused(project, tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    (root / 'GAME.COM').write_bytes(b'\x90\xc3')
    initial = _generation(project, root)
    store = WorkspaceStore(_session(project, 'workspace-edited'))
    current = store.load(initial)
    executable = next(row for row in current['entries'] if row['dos_path'] == 'GAME.COM')
    edited = store.write_file(initial, 'GAME.COM', b'\xcc\xc3',
                               expected_sha256=hashlib.sha256(executable['data']).hexdigest())

    with pytest.raises(ValueError, match='matching original project source|differs from its original'):
        prepare_workspace(project, root, None, None, None, _boot(tmp_path),
                          _staging(tmp_path), generation=edited['artifact'],
                          version_id=project.version()['id'])
