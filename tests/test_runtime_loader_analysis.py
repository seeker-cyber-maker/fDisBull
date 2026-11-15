"""Source/run/journal identity gates for native loader composition evidence."""
from copy import deepcopy
import hashlib
import json

import pytest

from fdisbull.project import Project
from fdisbull.runtime_loader_analysis import _journal_artifacts, _reference, _source, _resolve, _native_exit, load_loader_evidence
from fdisbull.wine_import_calls import resolve_loaded_export
from fixtures_formats import pe64
from test_wine_import_calls import _image, _modules


@pytest.fixture
def journal(tmp_path):
    source = tmp_path / 'authored.exe'; source.write_bytes(pe64())
    with Project.create(tmp_path / 'journal.fdb', source) as p:
        for run in ('owner', 'foreign'):
            p.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)', (run, 1, 'authored', 'authored', 'closed', '{}'))
        p.db.commit()
        first = p._debug_artifact('owner', 'first.json', 'loader-frame-snapshot', json.dumps({'run': 'owner', 'value': 1}).encode(), {})
        second = p._debug_artifact('owner', 'second.json', 'dll-callback', json.dumps({'run': 'owner', 'value': 2}).encode(), {})
        foreign = p._debug_artifact('foreign', 'foreign.json', 'dll-callback', json.dumps({'run': 'foreign'}).encode(), {})
        yield p, first, second, foreign


def test_native_journal_binds_exact_objects_without_modifying_them(journal):
    p, first, second, _ = journal
    before = [tuple(row) for row in p.db.execute('SELECT * FROM debug_artifacts ORDER BY id')]
    documents, receipts = _journal_artifacts(p, 'owner')
    assert _reference(first, documents, receipts, 'loader-frame-snapshot')['value'] == 1
    assert _reference(second, documents, receipts, 'dll-callback')['value'] == 2
    assert receipts[first['artifact']]['sequence'] < receipts[second['artifact']]['sequence']
    assert [tuple(row) for row in p.db.execute('SELECT * FROM debug_artifacts ORDER BY id')] == before


@pytest.mark.parametrize('field', ['run', 'version', 'sha256', 'kind', 'size'])
def test_forged_reference_metadata_cannot_cross_the_journal_gate(journal, field):
    p, first, _, _ = journal
    documents, receipts = _journal_artifacts(p, 'owner')
    wrong = deepcopy(first)
    wrong[field] = {'run': 'foreign', 'version': 2, 'sha256': '0' * 64, 'kind': 'trace', 'size': first['size'] + 1}[field]
    with pytest.raises(ValueError, match='contradicts'):
        _reference(wrong, documents, receipts)


def test_foreign_run_and_wrong_kind_artifacts_are_not_reassigned(journal):
    p, first, _, foreign = journal
    documents, receipts = _journal_artifacts(p, 'owner')
    with pytest.raises(ValueError, match='owning run'):
        _reference(foreign, documents, receipts)
    with pytest.raises(ValueError, match='kind'):
        _reference(first, documents, receipts, 'trace')


@pytest.mark.parametrize('change', ['artifact_hash', 'journal_hash', 'journal_version', 'missing_journal', 'duplicate_journal'])
def test_artifact_storage_and_event_chronology_must_agree(journal, change):
    p, first, _, _ = journal
    event = p.db.execute("SELECT * FROM debug_events WHERE operation='artifact' ORDER BY sequence LIMIT 1").fetchone()
    evidence = json.loads(event['evidence'])
    if change == 'artifact_hash':
        p.db.execute('UPDATE debug_artifacts SET sha256=? WHERE id=?', ('0' * 64, first['artifact']))
    elif change == 'missing_journal':
        p.db.execute('DELETE FROM debug_events WHERE sequence=?', (event['sequence'],))
    elif change == 'duplicate_journal':
        p.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)', ('owner', 'authored', 'artifact', event['evidence']))
    else:
        evidence['sha256' if change == 'journal_hash' else 'version'] = '0' * 64 if change == 'journal_hash' else 2
        p.db.execute('UPDATE debug_events SET evidence=? WHERE sequence=?', (json.dumps(evidence), event['sequence']))
    p.db.commit()
    with pytest.raises(ValueError):
        _journal_artifacts(p, 'owner')


def test_original_source_bytes_are_rechecked_before_loader_semantics(journal):
    p, _, _, _ = journal
    raw, _ = _source(p)
    assert hashlib.sha256(raw).hexdigest() == p.meta['source_sha256']
    p.db.execute('UPDATE binary_info SET source_bytes=? WHERE version=1', (raw[:-1] + bytes([raw[-1] ^ 1]),))
    p.db.commit()
    with pytest.raises(ValueError, match='source bytes'):
        _source(p)


def test_old_milestone_only_report_is_not_upgraded_to_full_composition(journal):
    p, _, _, _ = journal
    with pytest.raises(ValueError, match='Fresh full-range'):
        load_loader_evidence(p, p, {'milestones': []})


def test_authored_dll_named_export_is_replayed_from_actual_read_ledger():
    raw, _ = _image({'dll_report': None})
    modules, read = _modules([(0x180000000, 'SMCINIT.dll', raw)])
    resolution = resolve_loaded_export(modules, 'SMCINIT.dll', 'dll_report', read)
    _resolve(resolution, modules, 'SMCINIT.dll', 'dll_report')
    resolution['target'] = hex(int(resolution['target'], 16) + 1)
    with pytest.raises(ValueError, match='differs'):
        _resolve(resolution, modules, 'SMCINIT.dll', 'dll_report')


@pytest.mark.parametrize('change', ['none', 'wrong_code', 'wrong_run', 'missing_event', 'duplicate_event', 'wrong_state', 'wrong_code_type'])
def test_terminal_claim_requires_its_unique_actual_native_exit(journal, change):
    p, _, _, _ = journal
    native = {'run': 'owner', 'outcome': 'exited', 'session': {'state': 'exited', 'exit_code': 7}}
    if change == 'wrong_state': native['session']['state'] = 'stopped'
    if change == 'wrong_code_type': native['session']['exit_code'] = True
    if change != 'missing_event':
        p.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)', ('owner', 'authored', 'run', json.dumps(native)))
    if change == 'duplicate_event':
        p.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)', ('owner', 'authored', 'run', json.dumps(native)))
    p.db.commit()
    reported = deepcopy(native)
    if change == 'wrong_code': reported['session']['exit_code'] = 9
    if change == 'wrong_run': reported['run'] = 'foreign'
    if change == 'none':
        assert _native_exit(p, 'owner', reported) > 0
    else:
        with pytest.raises(ValueError, match='actual native process-exit'):
            _native_exit(p, 'owner', reported)
