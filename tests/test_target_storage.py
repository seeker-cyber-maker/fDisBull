"""External source identity and approval contract, using authored bytes only."""
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from fdisbull.cli import invoke
from fdisbull.project import Project
from fdisbull.target_storage import PREFIX, TargetStore, identity, reference, storage_report

CODE = bytes.fromhex('b80100000083c002c3')


@pytest.fixture
def target(tmp_path, monkeypatch):
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path / 'private-objects'))
    source = tmp_path / 'authored.bin'
    source.write_bytes(CODE)
    project = tmp_path / 'analysis.fdb'
    with Project.create(project, source, arch='x86', base=0x1000) as db:
        db.analyze()
        db.annotate(0x1000, 'Authored research')
    return project, source


def test_external_default_keeps_source_regions_instructions_and_resource_out_of_sqlite(target, tmp_path):
    project, source = target
    resource = tmp_path / 'authored-resource.dat'
    resource.write_bytes(b'\x00\xffAuthoredResourcePayload\x00')
    with Project(project) as db:
        db.attach_file(resource)
        assert db.source_info()['identity'] == {'size': len(CODE), 'sha256': hashlib.sha256(CODE).hexdigest()}
        assert db.source_info()['verified']
        assert db.file_bytes(resource.name)['bytes'] == resource.read_bytes().hex()
        assert db.disassembly()['instructions'][0]['bytes'] == 'b801000000'
        child = db.patch(0x1001, '07')['version']
        assert db.regions(child)[0].data == CODE[:1] + b'\x07' + CODE[2:]
        assert db.regions(1)[0].data == CODE
    with sqlite3.connect(project) as raw:
        for table, column in [('regions','data'), ('binary_info','source_bytes'), ('instructions','bytes'), ('external_files','data')]:
            for (value,) in raw.execute(f'SELECT {column} FROM {table}'):
                assert reference(value) is not None
        assert raw.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    for path in (project, Path(str(project) + '-wal')):
        if path.exists():
            assert CODE not in path.read_bytes()
            assert CODE.hex().encode() not in path.read_bytes()
            assert resource.read_bytes() not in path.read_bytes()
    assert storage_report(project)['embedded_payload_columns'] == []
    with Project(project) as db:
        assert db.regions(child)[0].data[1] == 7
        assert db.disassembly(version=1)['instructions'][0]['comment'] == 'Authored research'


def test_missing_store_keeps_stored_disassembly_and_requires_explicit_source(target, monkeypatch, tmp_path):
    project, source = target
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path / 'empty-store'))
    with Project(project) as db:
        assert db.source_info()['verified'] is False
        assert not db.disassembly()['byte_cache_available']
        rows = db.disassembly()['instructions']
        assert rows[0]['mnemonic'] == 'mov'
        assert rows[0]['bytes'] == ''
        assert rows[0]['comment'] == 'Authored research'
        with pytest.raises(ValueError, match='external target object missing'):
            db.analyze()
        assert db.bind_source(source, version=1)['attached'] is True
        assert db.source_info(version=1)['verified'] is True
        assert db.regions(1)[0].data == CODE
        assert db.disassembly()['byte_cache_available']
        assert db.disassembly()['instructions'][0]['bytes'] == 'b801000000'
    with Project(project) as reopened:
        assert reopened.regions(1)[0].data == CODE


def test_divergence_needs_exact_base_candidate_approval_and_preserves_base(target, tmp_path):
    project, source = target
    changed = tmp_path / 'modified.bin'
    changed.write_bytes(CODE[:1] + b'\x07' + CODE[2:])
    with Project(project) as db:
        candidate = db.source_candidate(changed)
        assert candidate['approval_required'] and not candidate['attached'] and not candidate['executed']
        for approval in (None, False, True, {}, {**candidate['approval'], 'base_version': 3}):
            with pytest.raises(ValueError, match='exact user approval'):
                db.bind_source(changed, approval=approval)
            assert len(db.versions()) == 1
        result = db.bind_source(changed, approval=candidate['approval'])
        child = result['version']
        assert result['layer'] and not result['executed']
        assert db.regions(1)[0].data == CODE
        assert db.regions(child)[0].data == changed.read_bytes()
        assert db.source_info(child)['approval'] == candidate['approval']
        assert db.source_info(1)['identity'] == identity(CODE)
        assert db.analyze(version=child)['version'] == child
        assert db.disassembly(version=child)['source_sha256'] == identity(changed.read_bytes())['sha256']
        assert db.disassembly(version=1)['source_sha256'] == identity(CODE)['sha256']
        # Approval from one base must not authorize the next version.
        with pytest.raises(ValueError, match='exact user approval'):
            db.bind_source(source, version=child, approval=candidate['approval'])
    with Project(project) as reopened:
        assert reopened.source_info(child)['identity'] == identity(changed.read_bytes())
        assert reopened.source_info(1)['identity'] == identity(CODE)
        assert reopened.regions(child)[0].data == changed.read_bytes()
    assert storage_report(project)['embedded_payload_columns'] == []


def test_changed_candidate_after_approval_is_refused_and_new_analysis_is_explicit(target, tmp_path):
    project, source = target
    changed = tmp_path / 'candidate.bin'
    changed.write_bytes(CODE[:1] + b'\x02' + CODE[2:])
    with Project(project) as db:
        approval = db.source_candidate(changed)['approval']
        changed.write_bytes(CODE[:1] + b'\x03' + CODE[2:])
        with pytest.raises(ValueError, match='exact user approval'):
            db.bind_source(changed, approval=approval)
        assert len(db.versions()) == 1
        separate = tmp_path / 'separate.fdb'
        result = db.new_source_analysis(changed, separate)
        assert result['existing_analysis_preserved'] and not result['executed']
        assert len(db.versions()) == 1
        with Project(separate) as other:
            assert other.source_info()['identity'] == identity(changed.read_bytes())
            assert other.meta['project_id'] != db.meta['project_id']
            with pytest.raises(ValueError, match='exact user approval'):
                other.bind_source(source, approval=approval)


def test_store_corruption_fails_closed(target):
    project, source = target
    with Project(project) as db:
        path = db.db.store.root / hashlib.sha256(CODE).hexdigest()
        path.write_bytes(b'corrupt')
        with pytest.raises(ValueError, match='size/SHA-256 mismatch'):
            db.regions(1)
        with pytest.raises(ValueError, match='size/SHA-256 mismatch'):
            db.source_info()


def test_json_raw_cache_is_external_and_legacy_derivative_preserves_original(target, tmp_path):
    project, source = target
    legacy = tmp_path / 'legacy.fdb'
    # Deliberate authored schema-8 fixture. Decode the current references into
    # a separate fixture to represent historical persisted raw bytes.
    with Project(project) as db, sqlite3.connect(legacy) as old:
        for (sql,) in db.db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            old.execute(sql)
        for (table,) in db.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            rows = db.db.execute(f'SELECT * FROM "{table}"').fetchall()
            for row in rows:
                old.execute(f'INSERT INTO "{table}" VALUES ({",".join("?" for _ in row)})', tuple(row))
        old.execute("UPDATE metadata SET value='8' WHERE key='schema'")
        old.execute("DELETE FROM metadata WHERE key IN ('storage','project_id')")
        old.execute('DROP TABLE target_sources')
        old.execute('CREATE TABLE authored_cache (document TEXT NOT NULL)')
        old.execute('INSERT INTO authored_cache VALUES (?)', (json.dumps({'low_level_ir': {'memory': {'initial': list(CODE)}}}),))
    before = legacy.read_bytes()
    assert storage_report(legacy)['storage'] == 'legacy-embedded'
    assert storage_report(legacy)['embedded_payload_columns']
    assert legacy.read_bytes() == before
    derivative = tmp_path / 'derivative.fdb'
    result = Project.migrate_external(legacy, derivative)
    assert result['source_preserved'] and result['embedded_payload_columns'] == []
    assert legacy.read_bytes() == before
    with Project(derivative) as migrated:
        assert migrated.regions(1)[0].data == CODE
        assert migrated.source_info(1)['loader']['version'] == 'unknown legacy import'
        assert migrated.source_info(1)['identity'] == identity(CODE)
        assert migrated.bind_source(source, version=1)['attached']
        assert migrated.disassembly()['instructions'][0]['mnemonic'] == 'mov'
        assert json.loads(migrated.db.execute('SELECT document FROM authored_cache').fetchone()[0])['low_level_ir']['memory']['initial'] == list(CODE)
    with sqlite3.connect(derivative) as raw:
        assert reference(raw.execute('SELECT document FROM authored_cache').fetchone()[0])
    with pytest.raises(FileExistsError):
        Project.migrate_external(legacy, derivative)
    assert legacy.read_bytes() == before


def test_json_api_exact_mismatch_approval_and_separate_choice(target, tmp_path):
    project, source = target
    assert invoke('source-candidate', {'project':str(project), 'path':str(source)})['exact_match']
    assert invoke('bind-source', {'project':str(project), 'path':str(source)})['attached']
    changed = tmp_path / 'modified.bin'
    changed.write_bytes(CODE[:1] + b'\x09' + CODE[2:])
    params = {'project':str(project), 'path':str(changed)}
    candidate = invoke('source-candidate', params)
    with pytest.raises(ValueError, match='exact user approval'):
        invoke('bind-source', params)
    result = invoke('bind-source', {**params, 'approval':candidate['approval']})
    assert result['layer']
    assert invoke('source-info', {'project':str(project), 'version':1})['identity'] == identity(CODE)
    assert not invoke('storage-info', {'project':str(project)})['publication_ready']


def test_store_refuses_git_directory_and_public_permissions(tmp_path):
    repo = tmp_path / 'repo'; repo.mkdir(); (repo / '.git').mkdir()
    with pytest.raises(ValueError, match='outside Git'):
        TargetStore(repo / 'objects')
    public = tmp_path / 'public'; public.mkdir(mode=0o755); public.chmod(0o755)
    with pytest.raises(ValueError, match='0700'):
        TargetStore(public).put(CODE)


def test_missing_candidate_does_not_attach_or_implicitly_create_analysis(target, tmp_path):
    project, source = target
    with Project(project) as db:
        with pytest.raises(ValueError, match='not a regular input file'):
            db.bind_source(tmp_path / 'missing.bin')
        assert len(db.versions()) == 1
        assert db.source_info()['identity'] == identity(CODE)


def test_cli_fresh_process_reopen_and_exact_source_binding(target):
    import subprocess
    import sys
    project, source = target
    result = subprocess.run([sys.executable, '-m', 'fdisbull', 'source-info', str(project), '--version', '1'],
                            check=True, capture_output=True, text=True)
    body = json.loads(result.stdout)
    assert body['ok'] and body['result']['identity'] == identity(CODE)
    result = subprocess.run([sys.executable, '-m', 'fdisbull', 'bind-source', str(project), str(source), '--version', '1'],
                            check=True, capture_output=True, text=True)
    body = json.loads(result.stdout)
    assert body['ok'] and body['result']['attached'] and not body['result']['executed']


def test_com_stored_research_is_readable_without_external_objects(tmp_path, monkeypatch):
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path / 'private-com-objects'))
    source = tmp_path / 'authored.com'
    source.write_bytes(bytes.fromhex('b8004ccd21'))
    path = tmp_path / 'com.fdb'
    with Project.create(path, source, image='com') as db:
        db.analyze()
        db.annotate('1000:0100', 'Authored COM research')
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path / 'empty-com-objects'))
    with Project(path) as db:
        assert not db.source_info()['verified']
        assert db.status()['regions'][0]['size'] == 5
        assert not db.disassembly()['byte_cache_available']
        row = db.disassembly()['instructions'][0]
        assert row['mnemonic'] == 'mov' and row['bytes'] == ''
        assert row['comment'] == 'Authored COM research'
        with pytest.raises(ValueError, match='external target object missing'):
            db.analyze()
