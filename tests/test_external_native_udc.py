"""Combined schema9/native-backing boundary, with authored overlap bytes only."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from fdisbull.code_backings import materialize_code_backing
from fdisbull.native_udc import capture_native_definition, compile_native_definition, native_definition_info
from fdisbull.project import Project
from fdisbull.target_storage import reference, storage_report


CODE = bytes.fromhex('7401a8aac3')


@pytest.fixture
def captured(tmp_path, monkeypatch):
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path / 'objects'))
    source = tmp_path / 'AUTHORED.COM'
    source.write_bytes(CODE)
    path = tmp_path / 'analysis.fdb'
    with Project.create(path, source, image='com') as project:
        project.analyze()
        info = capture_native_definition(project, 'overlap', [0x10102, 0x10103])
    return path, source, info


def assert_private_columns(path):
    with sqlite3.connect(path) as raw:
        source = raw.execute('SELECT data FROM native_udc_sources').fetchone()[0]
        document = raw.execute('SELECT document FROM native_udc_definitions').fetchone()[0]
        assert reference(source)['encoding'] == 'bytes'
        assert reference(document)['encoding'] == 'text'
        assert raw.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    for file in (path, Path(str(path) + '-wal')):
        if file.exists():
            data = file.read_bytes()
            assert CODE not in data and CODE.hex().encode() not in data
            assert b'"bytes":"a8aa"' not in data
    assert storage_report(path)['embedded_payload_columns'] == []


def test_capture_wal_and_fresh_process_exact_overlap_materialization(captured):
    path, source, info = captured
    with Project(path) as project:
        # Keep the WAL alive while inspecting with a plain SQLite connection.
        project.db.execute('PRAGMA journal_mode=WAL')
        second = capture_native_definition(project, 'second', [0x10102, 0x10103])
        assert second['capsule_sha256'] == info['capsule_sha256']
        assert_private_columns(path)
    source.unlink()
    script = '''
import json, sys
from fdisbull.project import Project
from fdisbull.native_udc import native_definition_info, compile_native_definition
from fdisbull.code_backings import materialize_code_backing
with Project(sys.argv[1]) as project:
    info = native_definition_info(project, sys.argv[2], include_blocks=True)
    cap = info['document']['capsule']
    assert cap['coverage']['physical_bytes'] == 3
    assert cap['coverage']['encoding_bytes'] == 4
    assert sorted(materialize_code_backing(b).hex() for b in cap['blocks']) == ['a8aa','aa','c3']
    result = compile_native_definition(project, sys.argv[2])
    assert result['bytes'] == '7401a8aac3'
    print(json.dumps({'sha256':info['sha256'], 'capsule_sha256':info['capsule_sha256'],
                      'plan_sha256':info['plan_sha256'], 'qualification':result['qualification']}))
'''
    result = subprocess.run([sys.executable, '-c', script, str(path), info['id']],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    reply = json.loads(result.stdout)
    assert all(reply[key] == info[key] for key in ('sha256', 'capsule_sha256', 'plan_sha256'))
    assert reply['qualification'] == 'original_bytes_only'


@pytest.mark.parametrize('column', ['source', 'capsule'])
@pytest.mark.parametrize('failure', ['missing', 'corrupt'])
def test_missing_or_corrupt_native_objects_fail_closed(captured, column, failure):
    path, source, info = captured
    with sqlite3.connect(path) as raw:
        sql = ('SELECT data FROM native_udc_sources' if column == 'source'
               else 'SELECT document FROM native_udc_definitions')
        ref = reference(raw.execute(sql).fetchone()[0])
    obj = Path(os.environ['FDISBULL_TARGET_STORE']) / ref['sha256']
    if failure == 'missing':
        obj.unlink()
    else:
        obj.write_bytes(b'corrupt')
    with Project(path) as project:
        # Stable instruction metadata remains available with absent byte caches.
        assert project.disassembly()['instructions'][0]['mnemonic'] == 'je'
        with pytest.raises(ValueError, match='missing|mismatch|corrupt'):
            compile_native_definition(project, info['id'])
        assert project.db.execute('SELECT name FROM native_udc_definitions').fetchone()[0] == 'overlap'


def test_legacy_native_udc_migration_preserves_original_and_all_definitions(captured, tmp_path):
    path, source, info = captured
    legacy = tmp_path / 'legacy.fdb'
    # Materialize the historical embedded representation in a separate fixture.
    with Project(path) as project, sqlite3.connect(legacy) as old:
        tables = project.db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        for table, sql in tables:
            old.execute(sql)
            for row in project.db.execute(f'SELECT * FROM "{table}"'):
                old.execute(f'INSERT INTO "{table}" VALUES ({",".join("?" for _ in row)})', tuple(row))
        old.execute("UPDATE metadata SET value='8' WHERE key='schema'")
        old.execute("DELETE FROM metadata WHERE key IN ('storage','project_id')")
        old.execute('DROP TABLE target_sources')
        before_info = native_definition_info(project, info['id'], include_blocks=True)
    before = legacy.read_bytes()
    derivative = tmp_path / 'derivative.fdb'
    assert Project.migrate_external(legacy, derivative)['source_preserved']
    assert legacy.read_bytes() == before
    assert_private_columns(derivative)
    with Project(derivative) as migrated:
        assert native_definition_info(migrated, info['id'], include_blocks=True) == before_info
        assert compile_native_definition(migrated, info['id'])['bytes'] == CODE.hex()
        assert migrated.bind_source(source, version=1)['attached']
    assert legacy.read_bytes() == before


def test_approved_child_never_substitutes_original_or_reuses_approval(captured, tmp_path):
    path, source, info = captured
    candidate = tmp_path / 'CHILD.COM'
    candidate.write_bytes(bytes.fromhex('7401a890c3'))
    with Project(path) as project:
        approval = project.source_candidate(candidate, version=1)['approval']
        with pytest.raises(ValueError, match='exact user approval'):
            project.bind_source(candidate, version=1)
        child = project.bind_source(candidate, version=1, approval=approval)['version']
        project.analyze(version=child)
        second = capture_native_definition(project, 'child', [0x10102, 0x10103], version=child)
        assert not second['original_layout_available']
        with pytest.raises(ValueError, match='unavailable'):
            compile_native_definition(project, second['id'])
        assert compile_native_definition(project, info['id'])['bytes'] == CODE.hex()
        with pytest.raises(ValueError, match='exact user approval'):
            project.bind_source(source, version=child, approval=approval)
        assert project.source_info(child)['approval'] == approval
        assert project.source_info(child)['identity']['sha256'] == hashlib.sha256(candidate.read_bytes()).hexdigest()
    with Project(path) as reopened:
        assert reopened.source_info(child)['approval'] == approval
        assert compile_native_definition(reopened, info['id'])['bytes'] == CODE.hex()
        with pytest.raises(ValueError, match='unavailable'):
            compile_native_definition(reopened, second['id'])
    assert_private_columns(path)


def test_ne_stored_metadata_remains_readable_without_instruction_cache(tmp_path, monkeypatch):
    from test_ne_loader import ne_file
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path / 'objects'))
    source = tmp_path / 'AUTHORED.EXE'
    source.write_bytes(ne_file())
    path = tmp_path / 'ne.fdb'
    with Project.create(path, source) as project:
        project.analyze(max_instructions=100)
    with sqlite3.connect(path) as raw:
        refs = [reference(row[0]) for row in raw.execute('SELECT bytes FROM instructions')]
    for ref in refs:
        (Path(os.environ['FDISBULL_TARGET_STORE']) / ref['sha256']).unlink(missing_ok=True)
    with Project(path) as project:
        listing = project.disassembly('ne:1:0')
        assert not listing['byte_cache_available']
        assert listing['instructions'][0]['logical_location']['address'] == 'ne:1:0x0000'
        assert listing['instructions'][0]['bytes'] == ''
        assert listing['instructions'][0]['ne_fixups'] == []


def test_ne_metadata_divergence_requires_separate_analysis_even_with_exact_approval(tmp_path, monkeypatch):
    from test_ne_loader import ne_file, fixup
    from fdisbull.target_storage import identity
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path / 'objects'))
    source = tmp_path / 'BASE.EXE'
    source.write_bytes(ne_file())
    candidate = tmp_path / 'CHANGED.EXE'
    candidate.write_bytes(ne_file(fixups=[fixup(3, 1, 1, 0), fixup(3, 14, 1, 42, 1), fixup(3, 19, 1, 7, 2)]))
    path = tmp_path / 'ne.fdb'
    with Project.create(path, source) as project:
        project.analyze(max_instructions=100)
        base = project.source_info(1)
        # The mapped code and entry are identical: only a relocation declaration changed.
        approval = {'project_id': project.meta['project_id'], 'base_version': 1,
                    'base_mapped_sha256': project.version(1)['sha256'],
                    'base_identity': base['identity'], 'candidate_identity': identity(candidate.read_bytes()),
                    'loader_options': base['loader_options']}
        objects = set(project.db.store.root.iterdir())
        with pytest.raises(ValueError, match='NE loader metadata.*separate analysis'):
            project.source_candidate(candidate, version=1)
        with pytest.raises(ValueError, match='NE loader metadata.*separate analysis'):
            project.bind_source(candidate, version=1, approval=approval)
        assert len(project.versions()) == 1 and set(project.db.store.root.iterdir()) == objects
        assert project.disassembly('ne:1:0', version=1)['instructions'][0]['target'] == '0x20000'
        separate = tmp_path / 'changed.fdb'
        project.new_source_analysis(candidate, separate, version=1)
    with Project(path) as original, Project(separate) as changed:
        assert len(original.versions()) == 1
        assert original.disassembly('ne:1:0')['instructions'][0]['target'] == '0x20000'
        changed.analyze(max_instructions=100)
        assert changed.disassembly('ne:1:0')['instructions'][0]['target'] == '0x10000'
        assert changed.source_info(1)['identity'] == identity(candidate.read_bytes())
    with Project(separate) as reopened:
        assert reopened.disassembly('ne:1:0')['instructions'][0]['target'] == '0x10000'


def test_ne_code_only_approved_child_preserves_fixups_and_reopens(tmp_path, monkeypatch):
    from test_ne_loader import ne_file
    from fdisbull.loader import load_image
    from fdisbull.target_storage import identity
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path / 'objects'))
    source = tmp_path / 'BASE.EXE'
    source.write_bytes(ne_file())
    image = load_image(source)
    data = bytearray(source.read_bytes())
    # MOV AX,7 -> MOV AX,8 in segment2; no relocation or mapping declaration changes.
    data[image.metadata['ne']['segments'][1]['file_offset'] + 1] = 8
    candidate = tmp_path / 'CODE.EXE'
    candidate.write_bytes(data)
    assert load_image(candidate).metadata['ne'] == image.metadata['ne']
    path = tmp_path / 'ne.fdb'
    with Project.create(path, source) as project:
        project.analyze(max_instructions=100)
        approval = project.source_candidate(candidate, version=1)['approval']
        child = project.bind_source(candidate, version=1, approval=approval)['version']
        project.analyze(version=child, max_instructions=100)
        parent_rows = project.disassembly('ne:1:0', version=1, lines=100)['instructions']
        child_rows = project.disassembly('ne:1:0', version=child, lines=100)['instructions']
        assert child_rows[0]['target'] == parent_rows[0]['target'] == '0x20000'
        assert next(r for r in child_rows if r['address'] == '0x20000')['bytes'] == 'b80800'
        assert next(r for r in parent_rows if r['address'] == '0x20000')['bytes'] == 'b80700'
        assert project.source_info(child)['approval'] == approval
        assert project.source_info(child)['identity'] == identity(candidate.read_bytes())
    with Project(path) as reopened:
        assert reopened.disassembly('ne:1:0', version=child, lines=100)['instructions'] == child_rows
        assert reopened.disassembly('ne:1:0', version=1, lines=100)['instructions'] == parent_rows
        assert reopened.source_info(child)['approval'] == approval
    expected = tmp_path / 'expected.json'
    expected.write_text(json.dumps({'parent': parent_rows, 'child': child_rows, 'approval': approval}))
    script = '''
import json, sys
from fdisbull.project import Project
expected = json.loads(open(sys.argv[2]).read())
child = int(sys.argv[3])
with Project(sys.argv[1]) as project:
    assert project.disassembly('ne:1:0', version=1, lines=100)['instructions'] == expected['parent']
    assert project.disassembly('ne:1:0', version=child, lines=100)['instructions'] == expected['child']
    assert project.source_info(child)['approval'] == expected['approval']
'''
    result = subprocess.run([sys.executable, '-c', script, str(path), str(expected), str(child)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
