"""Complete entry encodings and source-version identity are independent of layout."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.cli import respond
from fdisbull.code_backings import digest, materialize_code_backing, validate_source
from fdisbull.code_layout import compile_code_backings
from fdisbull.project import Project


ASSUMPTIONS = dict.fromkeys(('no_code_reads', 'no_code_writes', 'no_computed_entries',
                             'address_identity_unobserved', 'timing_unobserved'), True)


def _project(tmp_path, *, bits=16, code='7401a8aac3'):
    binary = tmp_path/'OVERLAP.BIN'
    binary.write_bytes(bytes.fromhex(code))
    project = Project.create(tmp_path/'overlap.fdb', binary, arch='x86', bits=bits, base=0x1000)
    project.analyze()
    return project


@pytest.mark.parametrize('bits', [16, 32])
def test_complete_backings_keep_both_roles_incoming_paths_and_physical_union(tmp_path, bits):
    with _project(tmp_path, bits=bits) as project:
        before = project.db.total_changes
        document = project.code_backings([0x1002, 0x1003])
        assert project.db.total_changes == before
        assert document['complete'] and not document['unresolved']
        # Includes the single shared RET continuation: 3 physical bytes,
        # four local encoding bytes (TEST 2 + STOSB 1 + RET 1).
        assert document['coverage']['physical_bytes'] == 3
        assert document['coverage']['encoding_bytes'] == 4
        assert document['coverage']['shared_occurrence_bytes'] == 1
        a, b, join = document['blocks']
        assert a['bytes'] == 'a8aa' and b['bytes'] == 'aa' and join['bytes'] == 'c3'
        assert a['provenance']['byte_roles'][1] == 'immediate'
        assert b['provenance']['byte_roles'][0] == 'instruction_encoding'
        assert a['exits'][0]['target'] == b['exits'][0]['target'] == join['id']
        assert any(edge['kind'] == 'fallthrough' and edge['source'].endswith('@0x1000') for edge in a['incoming'])
        assert any(edge['kind'] == 'branch' and edge['source'].endswith('@0x1000') for edge in b['incoming'])
        # An independent backing needs no neighboring document or byte storage.
        surviving_a, surviving_b = deepcopy(a), deepcopy(b)
        document.clear()
        assert materialize_code_backing(surviving_a) == bytes.fromhex('a8aa')
        assert materialize_code_backing(surviving_b) == bytes.fromhex('aa')


def test_reopen_without_original_and_shared_patch_invalidate_both_occurrences(tmp_path):
    with _project(tmp_path) as project:
        original = project.code_backings([0x1002, 0x1003])
        assert validate_source(project, original)['status'] == 'source_valid'
        child = project.patch(0x1003, '90')
        project.analyze()
        changed = project.code_backings([0x1002, 0x1003])
        assert changed['source']['version'] == child['version']
        assert [block['bytes'] for block in changed['blocks']] == ['a890', '90', 'c3']
        assert all(a['backing_revision'] != b['backing_revision'] for a, b in zip(original['blocks'], changed['blocks']))
        with pytest.raises(ValueError, match='stale'):
            validate_source(project, original)
        assert validate_source(project, original, version=1)['status'] == 'source_valid'
        assert project.code_backings([0x1002, 0x1003], version=1) == original
    (tmp_path/'OVERLAP.BIN').unlink()
    with Project(tmp_path/'overlap.fdb') as reopened:
        assert reopened.code_backings([0x1002, 0x1003], version=1) == original
        assert reopened.code_backings([0x1002, 0x1003]) == changed
        assert validate_source(reopened, changed)['semantic_qualification'] == 'unverified'


@pytest.mark.parametrize('options', [{'max_instructions': 1}, {}])
def test_missing_capture_and_budget_frontier_never_become_success(tmp_path, options):
    with _project(tmp_path) as project:
        entries = [0x1002, 0x1003] if options else [0x1001]
        document = project.code_backings(entries, **options)
        assert document['complete'] is False and document['unresolved']
        with pytest.raises(ValueError, match='incomplete'):
            compile_code_backings(document, assumptions=ASSUMPTIONS)


def test_unknown_computed_transfer_is_preserved_and_not_guessed(tmp_path):
    with _project(tmp_path, code='ffe0') as project:
        document = project.code_backings([0x1000])
        assert not document['complete'] and document['unresolved']
        with pytest.raises(ValueError, match='unresolved'):
            compile_code_backings(document, assumptions=ASSUMPTIONS)


def test_rehashed_partial_capture_cannot_masquerade_as_project_graph(tmp_path):
    with _project(tmp_path) as project:
        document = project.code_backings([0x1004, 0x1000], max_instructions=1)
        assert len(document['requested_entries']) == 2
        assert len(document['entries']) == 1 and not document['complete']
        assert validate_source(project, document)['graph_complete'] is False
        document['complete'] = True; document['unresolved'] = []
        document['sha256'] = digest({k: v for k, v in document.items() if k != 'sha256'})
        with pytest.raises(ValueError, match='graph differs'):
            validate_source(project, document)


def test_native_facts_and_self_contained_revision_integrity_are_checked(tmp_path):
    with _project(tmp_path) as project:
        document = project.code_backings([0x1002, 0x1003])
        block = deepcopy(document['blocks'][0]); block['bytes'] = 'a8'
        with pytest.raises(ValueError, match='integrity'):
            materialize_code_backing(block)
        document['blocks'][0]['exits'][0]['target'] = 'fabricated'
        with pytest.raises(ValueError, match='integrity'):
            validate_source(project, document)
        project.db.execute("UPDATE instructions SET bytes='a8' WHERE address='0000000000001002'")
        with pytest.raises(ValueError, match='complete native'):
            project.code_backings([0x1002])


def test_project_and_json_methods_capture_and_emit_the_same_bound_layout(tmp_path):
    with _project(tmp_path, bits=32) as project:
        result = project.code_layout([0x1002, 0x1003], base=0x200, assumptions=ASSUMPTIONS)
        assert result['qualification'] == 'structural_only'
        assert result['entries'][f'x86:32:little@0x1003'] != result['entries'][f'x86:32:little@0x1002']+1
    request = {'id': 'overlap', 'method': 'code-layout', 'params': {
        'project': str(tmp_path/'overlap.fdb'), 'entries': [0x1002, 0x1003],
        'base': 0x200, 'assumptions': ASSUMPTIONS}}
    response = respond(request)
    assert response['ok'], response
    assert response['result']['bytes'] == result['bytes']
    assert response['result']['source_document_sha256'] == result['source_document_sha256']


def test_cli_exposes_capture_and_explicit_assumptions_without_writing_code(tmp_path):
    with _project(tmp_path):
        pass
    assumptions = tmp_path/'assumptions.json'; assumptions.write_text(json.dumps(ASSUMPTIONS))
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'), PYTHONDONTWRITEBYTECODE='1')
    command = [sys.executable, '-B', '-m', 'fdisbull', 'code-layout', str(tmp_path/'overlap.fdb'),
               '--entry', '0x1002', '--entry', '0x1003', '--base', '0x200', '--assumptions', str(assumptions)]
    completed = subprocess.run(command, env=env, text=True, capture_output=True, timeout=20)
    assert completed.returncode == 0, completed.stderr
    response = json.loads(completed.stdout)
    assert response['ok'], response
    result = response['result']
    assert result['qualification'] == 'structural_only'
    assert result['bytes'] == 'a8aae90400aae90000c3'
