"""One semantic label follows explicitly linked file and native byte identities."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest
from PIL import Image

from fdisbull.cli import main, respond
from fdisbull.project import Project
from fdisbull.render import render_snapshot


def make_linked_project(tmp_path, mode='x86'):
    source = tmp_path / 'program.bin'
    module = bytearray(64)
    if mode == 'mz':
        header = bytearray(64)
        struct.pack_into('<14H', header, 0, 0x5a4d, 128, 1, 0, 4, 0,
                         0xffff, 0, 0, 0, 0, 0, 28, 0)
        module[:5] = bytes.fromhex('8b062000cb')
        source.write_bytes(header + module)
        project = Project.create(tmp_path / 'project.fdb', source)
        entry, data = 0x10000, 0x10020
        project.analyze(ds=0x1000)
    elif mode == 'arm64':
        # LDR W0, [PC + 32], followed by RET.
        module[:8] = bytes.fromhex('00010018c0035fd6')
        source.write_bytes(module)
        project = Project.create(tmp_path / 'project.fdb', source,
                                 arch='arm64', base=0x1000)
        entry, data = 0x1000, 0x1020
        project.analyze()
    else:
        module[:6] = bytes.fromhex('a120100000c3')
        source.write_bytes(module)
        project = Project.create(tmp_path / 'project.fdb', source,
                                 arch='x86', bits=32, base=0x1000)
        entry, data = 0x1000, 0x1020
        project.analyze()
    project.define_type('Counters', dict(kind='struct', size=8, fields=[
        dict(name='food', offset=0, type='u16'),
        dict(name='rest_rooms', offset=2, type='u16'),
        dict(name='gifts', offset=4, type='u16'),
        dict(name='parking', offset=6, type='u16'),
    ]))
    project.apply_type(data, 'Counters', name='live')
    for name, offset in [('save-a.dat', 8), ('save-b.dat', 12)]:
        path = tmp_path / name
        path.write_bytes(bytes(range(32)))
        project.attach_file(path, kind='save')
        project.apply_file_type(name, 'Counters', offset=offset, name='saved')
    project.file_reference(entry, 'save-a.dat', offset=8, width=2,
                           access='read', evidence='Known save-field relationship.')
    return project, entry, data


def file_endpoint(name='save-a.dat', offset=8):
    return {'file': name, 'offset': offset}


def memory_endpoint(address):
    return {'address': address}


def link_chain(project, data):
    project.link_labels(file_endpoint(), file_endpoint('save-b.dat', 12),
                        size=8, evidence='Both save layouts encode the same counter block.')
    project.link_labels(file_endpoint('save-b.dat', 12), memory_endpoint(data),
                        size=8, evidence='The loader copies this block into native memory.')


@pytest.mark.parametrize('mode', ['x86', 'arm64', 'mz'])
def test_file_and_native_renames_follow_range_links_through_all_views(tmp_path, mode):
    project, entry, data = make_linked_project(tmp_path, mode)
    with project:
        before = project.disassembly(entry, lines=1)['instructions'][0]
        native_edges = [tuple(row) for row in project.db.execute('SELECT * FROM xrefs')]
        region_bytes = [region.data for region in project.regions(1)]
        link_chain(project, data)
        project.rename_file('save-a.dat', 8, 'food_count')
        for endpoint in (file_endpoint(), file_endpoint('save-b.dat', 12),
                         memory_endpoint(data)):
            info = project.label_info(endpoint)
            assert info['name'] == 'food_count'
            assert len(info['members']) == 3
            assert info['runtime_observed'] is False
        saved = project.typed_file('save-a.dat', offset=8)['items'][0]
        native = project.typed_data(data)['items'][0]
        assert saved['name'] == native['name'] == 'food_count'
        assert saved['path'] == 'saved.food'
        assert native['path'] == 'live.food'
        shown = project.disassembly(entry, lines=1)['instructions'][0]
        assert shown['operands'] == before['operands']
        assert shown['bytes'] == before['bytes']
        assert shown['file_references'][0]['locations'][0]['name'] == 'food_count'
        assert 'food_count' in shown['display_operands']
        # x86 and MZ have direct memory-operand identities. ARM64 literal loads
        # are retained as PC-relative data references by their decoder adapter.
        assert any(ref['name'] == 'food_count' for ref in shown['references'])
        assert any(ref['target_name'] == 'food_count' for ref in project.xrefs(data))
        accesses = project.memory_accesses(data, include_unresolved=False)
        assert accesses['name'] == 'food_count'
        assert any(item['target_name'] == 'food_count' for item in accesses['items'])
        cfg = project.cfg(entry)
        assert 'food_count' in cfg['nodes'][0]['display_operands']
        svg, png = tmp_path / 'labels.svg', tmp_path / 'labels.png'
        render_snapshot(project.disassembly(entry, lines=1), svg)
        render_snapshot(project.disassembly(entry, lines=1), png)
        ET.parse(svg)
        assert 'food_count' in svg.read_text()
        with Image.open(png) as image:
            assert image.width > 0 and image.height > 0
        project.annotate(data, 'concessions_food', kind='name')
        assert project.label_info(file_endpoint())['name'] == 'concessions_food'
        assert project.typed_file('save-b.dat', offset=12)['items'][0]['name'] == 'concessions_food'
        typed = project.typed_data(data)['items']
        assert typed[0]['path'] == 'live.food'
        assert typed[1]['path'] == 'live.rest_rooms'
        assert 'concessions_food' in project.disassembly(entry, lines=1)['instructions'][0]['display_operands']
        assert [region.data for region in project.regions(1)] == region_bytes
        assert [tuple(row) for row in project.db.execute('SELECT * FROM xrefs')] == native_edges


def test_interior_field_rename_propagates_without_renaming_neighbor_or_instruction(tmp_path):
    project, entry, data = make_linked_project(tmp_path)
    with project:
        link_chain(project, data)
        project.rename_file('save-a.dat', 10, 'restroom_count')
        assert project.label_info(file_endpoint('save-b.dat', 14))['name'] == 'restroom_count'
        assert project.label_info(memory_endpoint(data + 2))['name'] == 'restroom_count'
        assert project.typed_data(data)['items'][1]['name'] == 'restroom_count'
        assert project.typed_file('save-a.dat', offset=8)['items'][1]['path'] == 'saved.rest_rooms'
        assert project.label_info(memory_endpoint(data))['name'] != 'restroom_count'
        project.annotate(entry, 'read_counter', kind='name')
        assert project.disassembly(entry, lines=1)['instructions'][0]['name'] == 'read_counter'
        assert project.label_info(file_endpoint('save-a.dat', 10))['name'] == 'restroom_count'
        assert project.label_info(file_endpoint())['name'] != 'read_counter'


def test_explicit_label_conflict_rejects_atomically_and_named_merge_is_deliberate(tmp_path):
    project, _, data = make_linked_project(tmp_path)
    with project:
        project.rename_file('save-a.dat', 8, 'saved_food')
        project.annotate(data, 'live_food', kind='name')
        with pytest.raises(ValueError):
            project.link_labels(file_endpoint(), memory_endpoint(data), size=2,
                                evidence='These fields have the same meaning.')
        assert project.label_info(file_endpoint())['name'] == 'saved_food'
        assert project.label_info(memory_endpoint(data))['name'] == 'live_food'
        assert len(project.label_info(file_endpoint())['members']) == 1
        project.link_labels(file_endpoint(), memory_endpoint(data), size=2,
                            name='food_count', evidence='Resolved both names explicitly.')
        assert project.label_info(file_endpoint())['name'] == 'food_count'
        assert project.label_info(memory_endpoint(data))['name'] == 'food_count'


def test_contradictory_offset_cycle_is_rejected_without_partial_link(tmp_path):
    project, _, data = make_linked_project(tmp_path)
    with project:
        link_chain(project, data)
        original = project.label_info(file_endpoint())
        with pytest.raises(ValueError):
            project.link_labels(file_endpoint(), memory_endpoint(data + 2), size=4,
                                evidence='Deliberately contradictory shifted mapping.')
        after = project.label_info(file_endpoint())
        assert after['members'] == original['members']
        assert after['links'] == original['links']


def test_unset_labels_follow_type_field_revision_without_copying_old_display_text(tmp_path):
    project, entry, data = make_linked_project(tmp_path)
    with project:
        link_chain(project, data)
        project.define_type('Counters', dict(kind='struct', size=8, fields=[
            dict(name='food_counter', offset=0, type='u16'),
            dict(name='rest_rooms', offset=2, type='u16'),
            dict(name='gifts', offset=4, type='u16'),
            dict(name='parking', offset=6, type='u16'),
        ]))
        assert 'food_counter' in project.label_info(file_endpoint())['name']
        assert 'food_counter' in project.label_info(memory_endpoint(data))['name']
        assert 'food_counter' in project.disassembly(entry, lines=1)['instructions'][0]['display_operands']


def test_parent_child_labels_are_isolated_and_survive_independent_process_restart(tmp_path):
    project, entry, data = make_linked_project(tmp_path)
    db_path = str(project.path)
    with project:
        link_chain(project, data)
        project.rename_file('save-a.dat', 8, 'original_food')
        child = project.patch(data + 6, '0100')['version']
        project.rename_file('save-b.dat', 12, 'child_food', version=child)
        assert project.label_info(memory_endpoint(data), version=1)['name'] == 'original_food'
        assert project.label_info(memory_endpoint(data), version=child)['name'] == 'child_food'
        assert project.label_info(file_endpoint(), version=1)['name'] == 'original_food'
        assert project.label_info(file_endpoint(), version=child)['name'] == 'child_food'
        # A source-code patch makes its authored file reference stale; the
        # independent field equivalence remains an authored interpretation.
        patched = project.patch(entry, '90', version=child)['version']
        project.analyze(version=patched)
        view = project.disassembly(entry, lines=1, version=patched)['instructions'][0]
        assert view['file_references'][0]['stale'] is True
        assert 'child_food' not in view['display_operands']
        assert project.label_info(file_endpoint(), version=patched)['name'] == 'child_food'
        assert project.db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    for source in ('save-a.dat', 'save-b.dat', 'program.bin'):
        (tmp_path / source).unlink()
    code = '''
import json, sys
from fdisbull.project import Project
with Project(sys.argv[1]) as p:
    print(json.dumps([p.label_info({'file':'save-a.dat','offset':8},version=v)['name'] for v in (1,2)]))
'''
    result = subprocess.run([sys.executable, '-c', code, db_path],
                            capture_output=True, text=True, check=True,
                            env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')})
    assert json.loads(result.stdout) == ['original_food', 'child_food']


def test_native_to_native_labels_and_dos_aliases_share_physical_identity(tmp_path):
    project, _, data = make_linked_project(tmp_path, 'mz')
    with project:
        project.link_labels({'address': '1000:0020'}, {'address': '1000:0030'},
                            size=2, evidence='Known mirrored data field.')
        project.annotate('1001:0010', 'alias_counter', kind='name')
        assert project.label_info({'address': '1000:0030'})['name'] == 'alias_counter'
        assert project.label_info({'address': data})['name'] == 'alias_counter'


def test_untyped_file_byte_label_propagates_into_authored_code_reference(tmp_path):
    project, entry, data = make_linked_project(tmp_path)
    with project:
        source = tmp_path / 'opaque.dat'
        source.write_bytes(bytes(16))
        project.attach_file(source)
        project.file_reference(entry, 'opaque.dat', offset=4, width=2,
                               evidence='An analyst identified this untyped field.')
        project.link_labels({'file': 'opaque.dat', 'offset': 4}, {'address': data},
                            size=2, evidence='The same field is live here.')
        project.rename_file('opaque.dat', 4, 'opaque_counter')
        view = project.disassembly(entry, lines=1)['instructions'][0]
        reference = next(ref for ref in view['file_references'] if ref['file'] == 'opaque.dat')
        assert reference['locations'][0]['name'] == 'opaque_counter'
        assert 'opaque_counter' in view['display_operands']
        assert project.label_info({'address': data})['name'] == 'opaque_counter'


@pytest.mark.parametrize('arch,abi', [('x86', 'x86_64_sysv'), ('arm64', 'aarch64_aapcs64')])
def test_persisted_library_effects_resolve_current_labels_without_reanalysis(tmp_path, arch, abi):
    source = tmp_path / 'memset-caller.bin'
    if arch == 'x86':
        payload = bytearray(b'\xcc' * 0x200)
        # SysV arguments: destination=0x1100, value=0x1234, count=8.
        payload[:21] = bytes.fromhex('bf00110000be34120000ba08000000e86c000000c3')
        payload[0x80] = 0xc3
    else:
        payload = bytearray(bytes.fromhex('000020d4') * 128)
        mov = lambda register, value: struct.pack('<I', 0xd2800000 | (value << 5) | register)
        code = mov(0, 0x1100) + mov(1, 0x1234) + mov(2, 8) + bytes.fromhex('1d000094c0035fd6')
        payload[:len(code)] = code
        payload[0x80:0x84] = bytes.fromhex('c0035fd6')
    source.write_bytes(payload)
    with Project.create(tmp_path / 'effects.fdb', source, arch=arch, base=0x1000) as project:
        project.set_summary(0x1080, 'memset', abi=abi)
        assert project.auto_analyze(max_rounds=20)['stable']
        generation = project.function_analysis(0x1000)['generation']
        resource = tmp_path / 'counter.save'
        resource.write_bytes(bytes(16))
        project.attach_file(resource, kind='save')
        project.link_labels({'file': 'counter.save', 'offset': 0}, {'address': 0x1100},
                            size=8, evidence='The call initializes this serialized block.')
        project.rename_file('counter.save', 0, 'counter_block')
        effects = project.call_effects(0x1100, access='write', include_unresolved=False)
        assert effects['name'] == 'counter_block'
        effect, = effects['items']
        assert effect['target_name'] == 'counter_block'
        assert effect['summary_name'] == 'memset'
        call_site = int(effect['call_site'], 0) if isinstance(effect['call_site'], str) else effect['call_site']
        project.annotate(call_site, 'reset_call', kind='name')
        project.annotate(0x1080, 'clear_block_helper', kind='name')
        project.annotate(0x1000, 'initialize_counters', kind='name')
        project.annotate(0x1100, 'renamed_counter_block', kind='name')
        updated = project.call_effects(0x1100, access='write', include_unresolved=False)
        assert updated['items'][0]['target_name'] == 'renamed_counter_block'
        assert updated['items'][0]['call_site_name'] == 'reset_call'
        assert updated['items'][0]['callee_name'] == 'clear_block_helper'
        document = project.function_analysis(0x1000)
        assert document['generation'] == generation
        assert not document['stale']
        assert document['name'] == document['result']['name'] == 'initialize_counters'
        stored_effect, = document['result']['call_effects']
        assert stored_effect['target_name'] == 'renamed_counter_block'
        assert stored_effect['call_site_name'] == 'reset_call'
        assert stored_effect['callee_name'] == 'clear_block_helper'
        assert stored_effect['summary_name'] == 'memset'


def test_schema_six_migration_preserves_original_facts_files_and_types(tmp_path):
    project, entry, data = make_linked_project(tmp_path)
    path = project.path
    with project:
        before_native = project.disassembly(entry, lines=1)
        before_file = project.typed_file('save-a.dat', offset=8)
        before_type = project.typed_data(data)
        before_versions = project.versions()
        project.db.executescript("""
            DROP TABLE label_links;
            DROP TABLE shared_label_names;
            UPDATE metadata SET value='6' WHERE key='schema';
        """)
    with Project(path) as migrated:
        assert migrated.db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0] == '7'
        assert migrated.disassembly(entry, lines=1) == before_native
        assert migrated.typed_file('save-a.dat', offset=8) == before_file
        assert migrated.typed_data(data) == before_type
        assert migrated.versions() == before_versions
        link_chain(migrated, data)
        migrated.rename_file('save-a.dat', 8, 'migrated_food')
        assert migrated.label_info(memory_endpoint(data))['name'] == 'migrated_food'
        assert migrated.db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'


@pytest.mark.parametrize('left,right,size', [
    ({'file': 'save-a.dat', 'offset': 31}, {'address': 0x1020}, 2),
    ({'file': 'missing.dat', 'offset': 8}, {'address': 0x1020}, 1),
    ({'file': 'save-a.dat', 'offset': 8}, {'address': 0x1040}, 1),
    ({'file': 'save-a.dat', 'offset': 8}, {'address': 0x1020}, 0),
    ({'file': 'save-a.dat', 'offset': 8, 'address': 0x1020}, {'address': 0x1020}, 1),
])
def test_invalid_link_extent_or_endpoint_leaves_no_partial_identity(tmp_path, left, right, size):
    project, _, data = make_linked_project(tmp_path)
    with project:
        before = project.label_info(memory_endpoint(data))
        with pytest.raises(ValueError):
            project.link_labels(left, right, size=size, evidence='Invalid extent test.')
        after = project.label_info(memory_endpoint(data))
        assert after == before


def test_cli_and_json_protocol_can_rename_from_either_endpoint(tmp_path, capsys):
    project, _, data = make_linked_project(tmp_path)
    with project:
        path = str(project.path)
    assert main(['link-labels', path, json.dumps(file_endpoint()),
                 json.dumps(memory_endpoint(data)), '--size', '8',
                 '--evidence', 'Reviewed loader mapping.']) == 0
    assert json.loads(capsys.readouterr().out)['ok'] is True
    assert main(['rename-file', path, 'save-a.dat', '8', 'food_count']) == 0
    assert json.loads(capsys.readouterr().out)['ok'] is True
    response = respond({'id': 9, 'method': 'label-info', 'params': {
        'project': path, 'endpoint': memory_endpoint(data)}})
    assert response['ok'] and response['result']['name'] == 'food_count'
    response = respond({'id': 10, 'method': 'rename', 'params': {
        'project': path, 'address': data, 'name': 'food_counter'}})
    assert response['ok']
    response = respond({'id': 11, 'method': 'label-info', 'params': {
        'project': path, 'endpoint': file_endpoint()}})
    assert response['ok'] and response['result']['name'] == 'food_counter'
