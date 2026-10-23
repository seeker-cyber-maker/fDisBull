"""An incorrect field correspondence can be retracted without deleting evidence."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest
from PIL import Image

from fdisbull.cli import main, respond
from fdisbull.project import Project
from fdisbull.render import render_snapshot
from test_shared_labels import (
    file_endpoint, link_chain, make_linked_project, memory_endpoint,
)


def link_direct(project, data, size=8):
    project.link_labels(file_endpoint(), memory_endpoint(data), size=size,
                        evidence='An analyst declared this save-to-memory correspondence.',
                        author='mapping_author')
    return project.label_links()['items'][-1]['id']


@pytest.mark.parametrize('mode', ['x86', 'arm64', 'mz'])
def test_unlink_recomputes_native_labels_and_preserves_independent_code_evidence(tmp_path, mode):
    project, entry, data = make_linked_project(tmp_path, mode)
    with project:
        identifier = link_direct(project, data)
        project.rename_file('save-a.dat', 8, 'food_count')
        native_edges = [tuple(row) for row in project.db.execute('SELECT * FROM xrefs')]
        file_references = [tuple(row) for row in project.db.execute('SELECT * FROM file_references')]
        versions = project.versions()
        region_bytes = [region.data for region in project.regions(1)]
        before = project.disassembly(entry, lines=1)['instructions'][0]
        assert before['references'][0]['name'] == 'food_count'

        receipt = project.unlink_labels(identifier, reason='The correspondence was a mistaken interpretation.',
                                        author='reviewer')
        assert receipt['removed'] is True
        assert receipt['still_connected'] is False
        assert receipt['connectivity_scope'] == 'starting_endpoints'
        assert receipt['link']['id'] == identifier
        assert receipt['link']['active'] is False
        assert receipt['link']['author'] == 'mapping_author'
        assert receipt['link']['removal']['author'] == 'reviewer'
        assert receipt['link']['removal']['reason'] == 'The correspondence was a mistaken interpretation.'
        assert receipt['link']['removal']['created']
        assert len(receipt['left']['before']['members']) == 2
        assert len(receipt['left']['after']['members']) == 1
        assert len(receipt['right']['after']['members']) == 1
        assert project.label_info(file_endpoint())['name'] == 'food_count'
        native = project.label_info(memory_endpoint(data))
        assert native['name'] == 'live.food' and native['explicit'] is False
        assert native['links'] == []

        after = project.disassembly(entry, lines=1)['instructions'][0]
        assert after['references'][0]['name'] == 'live.food'
        # The instruction-to-file relationship is independent evidence and stays.
        assert after['file_references'][0]['locations'][0]['name'] == 'food_count'
        assert after['operands'] == before['operands'] and after['bytes'] == before['bytes']
        assert project.typed_data(data)['items'][0]['name'] == 'live.food'
        assert project.typed_file('save-a.dat', offset=8)['items'][0]['name'] == 'food_count'
        assert any(ref['target_name'] == 'live.food' for ref in project.xrefs(data))
        assert project.cfg(entry)['nodes'][0]['references'][0]['name'] == 'live.food'
        assert project.memory_accesses(data, include_unresolved=False)['name'] == 'live.food'
        svg, png = tmp_path / 'retracted.svg', tmp_path / 'retracted.png'
        render_snapshot(project.disassembly(entry, lines=1), svg)
        render_snapshot(project.disassembly(entry, lines=1), png)
        ET.parse(svg)
        assert 'live.food' in svg.read_text() and 'food_count' in svg.read_text()
        with Image.open(png) as image:
            assert image.width > 0 and image.height > 0
        assert [tuple(row) for row in project.db.execute('SELECT * FROM xrefs')] == native_edges
        assert [tuple(row) for row in project.db.execute('SELECT * FROM file_references')] == file_references
        assert [region.data for region in project.regions(1)] == region_bytes
        assert project.versions() == versions


def test_retracting_a_transitive_range_does_not_copy_names_to_detached_interior_fields(tmp_path):
    project, _, data = make_linked_project(tmp_path)
    with project:
        link_chain(project, data)
        names = ('food_count', 'restroom_count', 'gift_count', 'parking_count')
        for index, name in enumerate(names):
            project.rename_file('save-a.dat', 8+index*2, name)
        project.unlink_labels(2, reason='The save layouts agree but the memory mapping is withdrawn.')
        for index, name in enumerate(names):
            saved = project.label_info(file_endpoint('save-b.dat', 12+index*2))
            live = project.label_info(memory_endpoint(data+index*2))
            assert saved['name'] == name and len(saved['members']) == 2
            assert saved['explicit'] is True
            assert live['name'] != name and live['explicit'] is False
            assert live['members'] == [memory_endpoint(hex(data+index*2))]
        project.annotate(data+2, 'independent_native_field', kind='name')
        assert project.label_info(file_endpoint('save-a.dat', 10))['name'] == 'restroom_count'
        assert project.label_links()['total'] == 1
        assert project.label_links(include_removed=True)['total'] == 2


def test_wrong_untyped_memory_endpoint_loses_propagated_name_and_can_be_corrected(tmp_path):
    project, _, data = make_linked_project(tmp_path)
    with project:
        wrong = data+0x10
        identifier = link_direct(project, wrong)
        project.rename_file('save-a.dat', 8, 'food_count')
        assert project.label_info(memory_endpoint(wrong))['name'] == 'food_count'
        project.unlink_labels(identifier, reason='Corrected the DS/load-base conversion.')
        detached = project.label_info(memory_endpoint(wrong))
        assert detached['name'] != 'food_count' and detached['explicit'] is False
        assert detached['members'] == [memory_endpoint(hex(wrong))]
        project.link_labels(file_endpoint(), memory_endpoint(data), size=8,
                            evidence='The corrected coordinate was independently verified.')
        assert project.label_info(memory_endpoint(data))['name'] == 'food_count'
        assert project.label_links()['items'][0]['id'] > identifier
        history = project.label_links(include_removed=True)['items']
        assert [row['active'] for row in history] == [False, True]
        assert history[0]['right'] == memory_endpoint(hex(wrong))


def test_unlink_preserves_locally_authored_native_annotations_without_further_propagation(tmp_path):
    project, _, data = make_linked_project(tmp_path)
    with project:
        identifier = link_direct(project, data)
        project.annotate(data, 'native_authored_name', kind='name', author='local_analyst')
        project.unlink_labels(identifier, reason='The shared identity is withdrawn, not the local annotation.')
        assert project.label_info(memory_endpoint(data))['name'] == 'native_authored_name'
        project.annotate(data, 'native_only_revision', kind='name')
        assert project.label_info(memory_endpoint(data))['name'] == 'native_only_revision'
        assert project.label_info(file_endpoint())['name'] == 'native_authored_name'
        annotation = project.db.execute(
            "SELECT text,author FROM annotations WHERE version=1 AND address=? AND kind='name'",
            (f'{data:016x}',)).fetchone()
        assert annotation['text'] == 'native_only_revision'


def test_removing_one_edge_does_not_disconnect_an_alternate_active_path(tmp_path):
    project, _, data = make_linked_project(tmp_path)
    with project:
        link_chain(project, data)
        direct = link_direct(project, data)
        project.rename_file('save-a.dat', 8, 'food_count')
        receipt = project.unlink_labels(direct, reason='The direct evidence is withdrawn; other evidence remains.')
        assert receipt['removed'] is True
        assert receipt['still_connected'] is True
        assert len(receipt['left']['after']['members']) == 3
        assert len(receipt['right']['after']['members']) == 3
        assert project.label_info(memory_endpoint(data))['name'] == 'food_count'
        assert {row['id'] for row in project.label_info(file_endpoint())['links']} == {1, 2}
        project.unlink_labels(2, reason='The remaining memory correspondence was also rejected.')
        assert project.label_info(memory_endpoint(data))['name'] == 'live.food'


def test_removal_retries_preserve_original_audit_and_relink_uses_a_fresh_id(tmp_path):
    project, _, data = make_linked_project(tmp_path)
    with project:
        identifier = link_direct(project, data)
        original = project.unlink_labels(identifier, reason='Original review finding.', author='first_reviewer')
        repeated = project.unlink_labels(identifier, reason='A retry must not replace the audit.', author='second_reviewer')
        assert original['removed'] is True and repeated['removed'] is False
        assert repeated['link'] == original['link']
        assert project.label_links()['items'] == []
        project.link_labels(memory_endpoint(data), file_endpoint(), size=8,
                            evidence='A new review explicitly reinstates this correspondence.')
        active, = project.label_links()['items']
        assert active['id'] > identifier and active['active'] is True and active['removal'] is None
        assert active['evidence'] == 'A new review explicitly reinstates this correspondence.'
        assert project.label_links(include_removed=True)['items'][0] == original['link']


def test_link_inventory_paginates_active_and_historical_edges_separately(tmp_path):
    project, _, data = make_linked_project(tmp_path)
    with project:
        link_chain(project, data)
        link_direct(project, data)
        project.unlink_labels(2, reason='Retracted bridge.')
        active = project.label_links(limit=1, offset=1)
        assert active['total'] == 2
        assert [row['id'] for row in active['items']] == [3]
        history = project.label_links(include_removed=True, limit=1, offset=1)
        assert history['total'] == 3
        assert [row['id'] for row in history['items']] == [2]
        assert history['items'][0]['active'] is False
        assert history['items'][0]['removal']['reason'] == 'Retracted bridge.'


def test_parent_child_retractions_are_isolated_and_inherited_by_later_versions(tmp_path):
    project, _, data = make_linked_project(tmp_path)
    with project:
        identifier = link_direct(project, data)
        project.rename_file('save-a.dat', 8, 'food_count')
        child = project.patch(data+6, '0100')['version']
        project.unlink_labels(identifier, reason='Only this child interpretation is withdrawn.', version=child)
        assert project.label_info(memory_endpoint(data), version=1)['name'] == 'food_count'
        assert project.label_info(memory_endpoint(data), version=child)['name'] == 'live.food'
        assert project.label_links(version=1)['total'] == 1
        assert project.label_links(version=child)['total'] == 0
        grandchild = project.patch(data+6, '0200', version=child)['version']
        assert project.label_links(version=grandchild)['total'] == 0
        archived, = project.label_links(version=grandchild, include_removed=True)['items']
        assert archived['removal']['reason'] == 'Only this child interpretation is withdrawn.'
        assert project.label_info(memory_endpoint(data), version=grandchild)['name'] == 'live.food'
        assert project.label_links(version=1, include_removed=True)['items'][0]['removal'] is None


def test_retraction_and_audit_survive_input_deletion_and_separate_process_restart(tmp_path):
    project, _, data = make_linked_project(tmp_path)
    path = str(project.path)
    with project:
        identifier = link_direct(project, data)
        project.rename_file('save-a.dat', 8, 'food_count')
        project.unlink_labels(identifier, reason='Persisted retraction.', author='reviewer')
        assert project.db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    for name in ('save-a.dat', 'save-b.dat', 'program.bin'):
        (tmp_path/name).unlink()
    script = '''
import json,sys
from fdisbull.project import Project
with Project(sys.argv[1]) as p:
    print(json.dumps(dict(active=p.label_links(), history=p.label_links(include_removed=True),
        file=p.label_info({'file':'save-a.dat','offset':8}), native=p.label_info({'address':0x1020}))))
'''
    result = subprocess.run([sys.executable, '-c', script, path], capture_output=True,
                            text=True, check=True,
                            env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]/'src')})
    reopened = json.loads(result.stdout)
    assert reopened['active']['total'] == 0
    assert reopened['history']['items'][0]['removal']['reason'] == 'Persisted retraction.'
    assert reopened['file']['name'] == 'food_count'
    assert reopened['native']['name'] == 'live.food'


def test_schema_seven_migration_preserves_existing_link_and_names(tmp_path):
    project, _, data = make_linked_project(tmp_path)
    path = project.path
    with project:
        identifier = link_direct(project, data)
        project.rename_file('save-a.dat', 8, 'food_count')
        original = project.label_info(file_endpoint())
        versions = project.versions()
        file_values = project.typed_file('save-a.dat', offset=8)
        with project.transaction(True):
            project.db.execute('DROP TABLE label_link_removals')
            project.db.execute("UPDATE metadata SET value='7' WHERE key='schema'")
    with Project(path) as migrated:
        assert migrated.db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0] == '8'
        assert migrated.label_info(file_endpoint()) == original
        assert migrated.typed_file('save-a.dat', offset=8) == file_values
        assert migrated.versions() == versions
        migrated.unlink_labels(identifier, reason='The migrated link is now retractable.')
        assert migrated.label_info(memory_endpoint(data))['name'] == 'live.food'
        assert migrated.db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'


@pytest.mark.parametrize('identifier,reason', [
    (None, 'Invalid identifier.'), (True, 'Boolean identifier.'),
    (0, 'Zero identifier.'), (-1, 'Negative identifier.'), (999, 'Unknown identifier.'),
    (1, None), (1, ''), (1, ' '), (1, 'x'*4097),
])
def test_invalid_retraction_is_atomic(tmp_path, identifier, reason):
    project, _, data = make_linked_project(tmp_path)
    with project:
        link_direct(project, data)
        inventory = project.label_links(include_removed=True)
        labels = project.label_info(file_endpoint())
        with pytest.raises(ValueError):
            project.unlink_labels(identifier, reason=reason)
        assert project.label_links(include_removed=True) == inventory
        assert project.label_info(file_endpoint()) == labels


@pytest.mark.parametrize('options', [dict(limit=0), dict(limit=True), dict(offset=-1), dict(include_removed=1)])
def test_invalid_inventory_options_are_rejected(tmp_path, options):
    project, _, _ = make_linked_project(tmp_path)
    with project:
        with pytest.raises(ValueError):
            project.label_links(**options)


def test_failed_retraction_inside_caller_transaction_keeps_link_active(tmp_path):
    project, _, data = make_linked_project(tmp_path)
    with project:
        identifier = link_direct(project, data)
        before = project.label_links(include_removed=True)
        project.db.execute('''CREATE TEMP TRIGGER reject_retraction
            BEFORE INSERT ON label_link_removals BEGIN
            SELECT RAISE(ABORT, 'injected retraction failure'); END''')
        with project.transaction(True):
            with pytest.raises(sqlite3.IntegrityError, match='injected retraction failure'):
                project.unlink_labels(identifier, reason='This operation must fail atomically.')
            assert project.label_links(include_removed=True) == before
        project.db.execute('DROP TRIGGER reject_retraction')
        assert project.unlink_labels(identifier, reason='Retry after the transient failure.')['removed'] is True


def test_failure_after_tombstone_insert_rolls_back_inside_caller_transaction(tmp_path, monkeypatch):
    project, _, data = make_linked_project(tmp_path)
    with project:
        identifier = link_direct(project, data)
        before = project.label_links(include_removed=True)
        original_view = project._label_link_view

        def fail_after_insert(version, row):
            result = original_view(version, row)
            if result['removal'] is not None:
                raise RuntimeError('injected failure after tombstone insert')
            return result

        with monkeypatch.context() as patch:
            patch.setattr(project, '_label_link_view', fail_after_insert)
            with project.transaction(True):
                with pytest.raises(RuntimeError, match='after tombstone insert'):
                    project.unlink_labels(identifier, reason='Post-insert receipt creation fails.')
                assert project.label_links(include_removed=True) == before
        assert project.label_links(include_removed=True) == before
        assert project.unlink_labels(identifier, reason='Retry after the injected failure.')['removed'] is True


def test_cli_and_json_protocol_can_inspect_and_retract_a_link(tmp_path, capsys):
    project, _, data = make_linked_project(tmp_path)
    path = str(project.path)
    with project:
        identifier = link_direct(project, data)
    assert main(['label-links', path, '--limit', '1']) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed['ok'] and listed['result']['items'][0]['id'] == identifier
    assert main(['unlink-labels', path, str(identifier), '--reason', 'CLI correction.',
                 '--author', 'CLI reviewer']) == 0
    removed = json.loads(capsys.readouterr().out)
    assert removed['ok'] and removed['result']['removed'] is True
    assert main(['label-links', path, '--include-removed']) == 0
    history = json.loads(capsys.readouterr().out)
    assert history['ok'] and history['result']['items'][0]['active'] is False
    repeated = respond(dict(method='unlink-labels', params=dict(project=path,
                       link_id=identifier, reason='Protocol retry.')))
    assert repeated['ok'] and repeated['result']['removed'] is False
    current = respond(dict(method='label-links', params=dict(project=path)))
    assert current['ok'] and current['result']['total'] == 0
