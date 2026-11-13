"""Bounded original-source G2 graph, cache and private persistence."""
import hashlib
import json

import pytest

from fdisbull.chip8_intake import create_intake
from fdisbull.chip8_packages import resolve, ENV_ID
from fdisbull.chip8_source_map import build, info
from fdisbull.project import Project
from test_chip8_intake import inputs, _blob


def _project(inputs, rom, name='map.fdb'):
    root, path, _, manifest, manifest_path, put = inputs
    path.write_bytes(rom)
    manifest['programs'][0].update(size=len(rom), sha256=hashlib.sha256(rom).hexdigest(), git_blob_sha=_blob(rom))
    pin = put()
    return create_intake(root/name, path, manifest_path=manifest_path, manifest_sha256=pin, member='authored')


def _build(project, **kwargs):
    return build(project, resolve(project, environment=ENV_ID)['closure'], **kwargs)


def test_nested_call_return_context_and_cold_cache(inputs, monkeypatch):
    # 200 call 208; 208 call 20e; 20e return; 20a return; 202 loop.
    rom = bytes.fromhex('2208 1202 0000 0000 220e 00ee 0000 00ee')
    root = inputs[0]
    with _project(inputs, rom) as project:
        result = _build(project)
        states = {(s['pc'], tuple(s['return_stack'])) for s in result['states']}
        assert {(0x208,(0x202,)), (0x20e,(0x202,0x20a)), (0x20a,(0x202,)), (0x202,())} <= states
        assert result['coverage']['worklist_exhausted'] and not result['coverage']['budget_exhausted']
        assert result['status'] == 'bounded-static-candidate'
        ident = result['mapping']; closure = result['source']['closure']
        assert project.db.execute('SELECT document FROM chip8_source_maps').fetchone()[0] == json.dumps({k:v for k,v in result.items() if k not in ('mapping','sha256')},sort_keys=True,separators=(',',':'),ensure_ascii=False)
        import fdisbull.chip8 as decoder
        monkeypatch.setattr(decoder, 'decode', lambda *a: pytest.fail('cache re-decoded source'))
        assert build(project, closure) == result
        assert info(project, ident) == result
    with Project(root/'map.fdb') as reopened:
        assert info(reopened, ident) == result


@pytest.mark.parametrize('rom,reason', [
    ('2200','call_depth_budget'), ('3000 1200 0000','unsupported_opcode'),
    ('1201','odd_fetch'), ('1fff','odd_fetch'), ('b200','indirect_jump'),
    ('6001 ff','truncated_tail'), ('00ee','return_underflow'),
    ('f00a 1200','key_wait'), ('f055 1200','possible_source_write'),
    ('f033 1200','possible_source_write'), ('1000','not_source_backed'),
])
def test_explicit_frontiers(inputs, rom, reason):
    with _project(inputs, bytes.fromhex(rom)) as project:
        result = _build(project, max_call_depth=2)
        assert reason in {f['reason'] for f in result['frontiers']}
        if reason == 'call_depth_budget': assert result['coverage']['budget_exhausted']
        if reason == 'possible_source_write':
            assert result['edges'][0]['condition'] == 'nonfaulting_write_and_subsequent_fetch_matches_original_source'
            assert result['edges'][0]['assumption'] == result['assumptions'][1]
            assert result['edges'][0]['reachability'] == 'original-source-conditional'
            assert result['states'][0]['reachability'] == 'original-source-conditional'
            assert 'return stack is empty' in result['assumptions'][0]


def test_budgets_preserve_unresolved_frontiers_and_unknown_bytes(inputs):
    with _project(inputs, bytes.fromhex('3000 6001 6002 1200 ff')) as project:
        result = _build(project, max_instructions=1)
        assert result['coverage']['budget_exhausted'] and not result['coverage']['worklist_exhausted']
        assert 'instruction_budget' in {f['reason'] for f in result['frontiers']}
        assert result['coverage']['unclassified_bytes'] == 7
        assert all(span['classification'] == 'unknown' for span in result['unclassified_spans'])
        second = _build(project, max_states=1)
        assert sum(f['reason']=='state_budget' for f in second['frontiers']) == 2
        assert second['mapping'] != result['mapping']


def test_invalid_budgets_transaction_and_bad_map_are_readonly(inputs):
    with _project(inputs, bytes.fromhex('1200')) as project:
        closure = resolve(project, environment=ENV_ID)['closure']
        for kwargs in ({'max_instructions':True},{'max_states':0},{'max_call_depth':17}):
            with pytest.raises(ValueError): build(project, closure, **kwargs)
        with project.transaction(True):
            with pytest.raises(ValueError,match='transaction'): build(project, closure)
        assert not project.db.execute("SELECT 1 FROM sqlite_master WHERE name='chip8_source_maps'").fetchone()
        with pytest.raises(ValueError): info(project,'chip8-map:'+'0'*64)


def test_corruption_is_refused_before_redecode(inputs, monkeypatch):
    with _project(inputs, bytes.fromhex('6001 1200')) as project:
        result = _build(project)
        import fdisbull.chip8 as decoder
        monkeypatch.setattr(decoder, 'decode', lambda *a: pytest.fail('inspection re-decoded source'))
        with project.transaction(True):
            project.db.execute('UPDATE chip8_source_maps SET sha256=?', ('0'*64,))
        with pytest.raises(ValueError,match='hash'): info(project,result['mapping'])


def test_decoder_once_per_unique_pc_in_distinct_contexts(inputs, monkeypatch):
    # Conditional reaches the same subroutine from two distinct return stacks.
    import fdisbull.chip8 as decoder
    original = decoder.decode; calls = []
    def counted(data, pc):
        calls.append(pc)
        return original(data, pc)
    monkeypatch.setattr(decoder, 'decode', counted)
    with _project(inputs, bytes.fromhex('3000 2208 2208 1206 00ee')) as project:
        result = _build(project)
        assert sum(s['pc'] == 0x208 for s in result['states']) == 2
        assert len(calls) == len(set(calls))


def test_source_change_before_publication_does_not_create_map_table(inputs, monkeypatch):
    import fdisbull.chip8_packages as packages
    with _project(inputs, bytes.fromhex('1200')) as project:
        closure = resolve(project, environment=ENV_ID)['closure']
        original = packages._source_guard; calls = []
        def changing(*args):
            current = original(*args); calls.append(1)
            return current if len(calls) < 5 else '0'*64
        monkeypatch.setattr(packages, '_source_guard', changing)
        with pytest.raises(ValueError, match='changed'):
            build(project, closure)
        assert not project.db.execute("SELECT 1 FROM sqlite_master WHERE name='chip8_source_maps'").fetchone()


def test_private_document_only_in_external_store(inputs):
    import sqlite3
    root = inputs[0]
    with _project(inputs, bytes.fromhex('60ab 1200')) as project:
        result = _build(project)
        project.db.execute('PRAGMA wal_checkpoint(FULL)')
        with sqlite3.connect(root/'map.fdb') as raw:
            stored = raw.execute('SELECT document FROM chip8_source_maps').fetchone()[0]
        reference = json.loads(stored)['$fdisbull_external_object_1']
        assert reference['encoding'] == 'text' and reference['sha256'] == result['sha256']
        assert '60ab' not in stored
        assert result['instructions'][0]['word_hex'] == '60ab'


def test_rehashed_typed_candidate_tamper_is_refused(inputs):
    import fdisbull.chip8_source_map as module
    with _project(inputs, bytes.fromhex('6001 1200')) as project:
        result = _build(project)
        doc = {key: value for key, value in result.items() if key not in ('mapping', 'sha256')}
        doc['instructions'][0]['udl']['qualification'] = 'proven'
        data = module._raw(doc); digest = hashlib.sha256(data).hexdigest(); ident = 'chip8-map:' + digest
        with project.transaction(True):
            project.db.execute('UPDATE chip8_source_maps SET id=?,sha256=?,document=?',
                               (ident,digest,project._external_text(data.decode())))
        with pytest.raises(ValueError, match='typed source candidate'):
            info(project,ident)


def test_analysis_bound_closure_becomes_stale_without_new_mapping(inputs):
    with _project(inputs, bytes.fromhex('1200')) as project:
        closure = resolve(project, environment=ENV_ID, include_analysis=True)['closure']
        result = build(project, closure)
        with project.transaction(True):
            project.db.execute("UPDATE work SET detail='changed' WHERE version=1")
        with pytest.raises(ValueError,match='stale'):
            info(project,result['mapping'])
        assert project.db.execute('SELECT count(*) FROM chip8_source_maps').fetchone()[0] == 1


@pytest.mark.parametrize('field,value', [
    ('text', 'invented'), ('operands', 'v0, 0x02'),
    ('immediates', []), ('references', [{'role': 'code', 'target': 0x222}]),
])
def test_rehashed_decoded_fact_tamper_is_refused(inputs, field, value):
    import fdisbull.chip8_source_map as module
    with _project(inputs, bytes.fromhex('6001 1200')) as project:
        result = _build(project)
        doc = {key: value for key, value in result.items() if key not in ('mapping', 'sha256')}
        doc['instructions'][0]['decoded'][field] = value
        data = module._raw(doc); digest = hashlib.sha256(data).hexdigest(); ident = 'chip8-map:' + digest
        with project.transaction(True):
            project.db.execute('UPDATE chip8_source_maps SET id=?,sha256=?,document=?',
                               (ident, digest, project._external_text(data.decode())))
        with pytest.raises(ValueError):
            info(project, ident)


@pytest.mark.parametrize('word', ['f065', 'd012', 'd010'])
def test_i_range_operations_require_nonfaulting_continuation_and_survive_cache(inputs, word):
    with _project(inputs, bytes.fromhex(word + ' 1200')) as project:
        result = _build(project)
        assert any(f['reason'] == 'possible_i_range_fault' for f in result['frontiers'])
        assert result['edges'][0]['condition'] == 'nonfaulting_i_range'
        assert result['edges'][0]['reachability'] == 'original-source-conditional'
        assert info(project, result['mapping']) == result
