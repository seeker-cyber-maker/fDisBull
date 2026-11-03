"""Retained NE projects reach actual native analysis, queries and image exports."""
import hashlib
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

import pytest
from PIL import Image

from fdisbull.image_views import image_views
from fdisbull.inspection import inspect_binary
from fdisbull.loader import load_image
from fdisbull.project import Project
from test_le_workflow import command
from test_ne_loader import ne_file


@pytest.mark.parametrize('selector', [None, 'auto', 'ne'])
def test_native_workflow_restarts_and_renders_stored_state(tmp_path, selector):
    original = ne_file(); source = tmp_path / 'authored.exe'; source.write_bytes(original)
    path = tmp_path / 'ne.fdb'
    with Project.create(path, source, image=selector) as project:
        assert project.context == 'x86:16:little:ne'
        assert project.analyze(max_instructions=100)['stable']
        rows = project.disassembly('ne:1:0', lines=50)['instructions']
        first = rows[0]
        assert first['bytes'] == '9affff0000' and first['target'] == '0x20000'
        assert first['logical_location']['address'] == 'ne:1:0x0000'
        assert first['target_logical_location']['runtime_selector'] is None
        assert first['ne_fixups'][0]['operand_bytes_unchanged']
        xrefs = project.xrefs('ne:2:0')
        assert any(row['kind'] == 'call' and 'validated NE internal' in row['evidence'] for row in xrefs)
        assert next(row for row in xrefs if row['kind'] == 'call')['source_logical_location']['segment_index'] == 1
        assert any(row['address'] == '0x1000b' for row in project.functions())
        cfg = project.cfg('ne:1:0', max_instructions=100)
        assert cfg['segmented_address'] == 'ne:1:0x0000'
        assert project.information('imports')['items'][0]['address'] is None
        assert project.information('relocations')['total'] == 3
        assert project.locate('ne:3:0')['source_backing'] == 'initialized_file_bytes'
        zero = project.locate('ne:3:0x20')
        assert zero['mapped'] and zero['byte'] == '00'
        assert zero['source_backing'] == 'allocation_zero_fill' and zero['source_file_offset'] is None
        assert project.locate('ne:3:0x48')['mapped'] is False
        assert bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()[0]) == original
        assert project.meta['source_sha256'] == hashlib.sha256(original).hexdigest()
    source.unlink()
    status = command('status', path)
    assert status['format'] == 'NE' and status['context'] == 'x86:16:little:ne'
    for extension in ('svg', 'png'):
        output = tmp_path / ('stored.' + extension)
        command('render', path, output, '--address', 'ne:1:0')
        if extension == 'svg':
            assert ET.parse(output).getroot().tag.endswith('svg')
            assert 'NE SEG:OFFSET' in output.read_text() and 'ne:1:0x0000' in output.read_text()
        else:
            with Image.open(output) as image:
                assert image.size[0] == 1560 and image.size[1] > 100
    with Project(path) as project:
        assert project.disassembly('ne:1:0', lines=50)['instructions'] == rows
        assert project.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


def test_explicit_ne_and_explicit_mz_are_separate_views(tmp_path):
    source = tmp_path / 'dual.exe'; source.write_bytes(ne_file())
    assert [row['image'] for row in image_views(source.read_bytes())] == ['mz', 'ne']
    for selected, context in [('ne', 'x86:16:little:ne'), ('mz', 'x86:16:little')]:
        result = command('import', source, tmp_path / (selected + '.fdb'), '--image', selected)
        assert result['format'] == selected.upper() and result['context'] == context
        assert command('inspect', source, '--image', selected)['selected_image'] == selected


def test_child_patch_preserves_original_source_and_invalidates_changed_fixup_operand(tmp_path):
    original = ne_file(); source = tmp_path / 'authored.exe'; source.write_bytes(original)
    path = tmp_path / 'versions.fdb'
    with Project.create(path, source) as project:
        project.analyze(max_instructions=100)
        parent = project.disassembly('ne:1:0', lines=50)['instructions']
        source_hash = project.meta['source_sha256']
        child = project.patch('ne:1:1', '01000000')['version']
        assert project.analyze(version=child, max_instructions=100)['stable']
        first = project.disassembly('ne:1:0', version=child)['instructions'][0]
        assert first['target'] is None and not first['ne_fixups'][0]['operand_bytes_unchanged']
        assert project.disassembly('ne:1:0', version=1, lines=50)['instructions'] == parent
        for version in (1, child):
            retained = bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?', (version,)).fetchone()[0])
            assert retained == original and hashlib.sha256(retained).hexdigest() == source_hash
        assert any('No inverse fixup' in warning for warning in project.information('header', version=child)['warnings'])
    with Project(path) as project:
        assert project.disassembly('ne:1:0', version=1, lines=50)['instructions'] == parent
        assert project.disassembly('ne:1:0', version=child)['instructions'][0]['target'] is None
    assert source.read_bytes() == original


def test_wrapping_ip_and_refresh_never_leak_into_the_next_segment(tmp_path):
    code = b'\xc3' + bytes(65534) + b'\x90'
    source = tmp_path / 'wrap.exe'; source.write_bytes(ne_file(code=code, fixups=[], entry_offset=65535))
    with Project.create(tmp_path / 'wrap.fdb', source) as project:
        assert project.analyze(max_instructions=100)['stable']
        edges = project.xrefs('ne:1:0xffff', 'from')
        assert [(row['target'], row['kind']) for row in edges] == [('0x10000', 'fallthrough')]
        project.db.execute("DELETE FROM xrefs WHERE source='000000000001ffff'"); project.db.commit()
        project.refresh_facts()
        assert [(row['target'], row['kind']) for row in project.xrefs('ne:1:0xffff', 'from')] == [('0x10000', 'fallthrough')]
        graph = project.cfg('ne:1:0xffff', max_instructions=10)
        assert {row['address'] for row in graph['nodes']} == {'0x1ffff', '0x10000'}
        assert not project.xrefs('ne:2:0', 'to')


def test_ne_malformed_auto_never_falls_back_to_dos(tmp_path):
    data = bytearray(ne_file()); data[0x80 + 54] = 1
    source = tmp_path / 'unsupported.exe'; source.write_bytes(data)
    assert image_views(bytes(data))[1]['available'] is False
    for selector in (None, 'ne'):
        with pytest.raises(ValueError, match='Windows16'):
            Project.create(tmp_path / ('failed-' + str(selector) + '.fdb'), source, image=selector)
        with pytest.raises(ValueError, match='Windows16'):
            inspect_binary(bytes(data), image=selector)
    assert load_image(source, image='mz').format == 'MZ'


def test_complete_fixup_import_queries_and_compact_status(tmp_path, monkeypatch):
    import fdisbull.inspection as inspection
    monkeypatch.setattr(inspection, 'MAX_ITEMS', 1)
    data = ne_file(); source = tmp_path / 'bounded.exe'; source.write_bytes(data)
    assert len(inspect_binary(data)['relocations']) == 1
    with Project.create(tmp_path / 'bounded.fdb', source) as project:
        assert project.information()['counts']['relocations'] == 3
        assert project.information()['counts']['imports'] == 2
        assert project.information('relocations', offset=1, limit=1)['has_more']
        assert project.information('relocations', offset=2, limit=1)['items'][0]['import_name'] == 'BEEP'
        assert project.information('imports')['total'] == 2
        assert project.information('sections')['total'] == 3
        status = project.status()
        assert 'fixups' not in status['loader_metadata']['ne']
        assert len(json.dumps(status)) < 16000


def test_ne_parser_through_annotations_types_file_refs_and_labels(tmp_path):
    source = tmp_path / 'api.exe'; source.write_bytes(ne_file())
    external = tmp_path / 'authored.dat'; external.write_bytes(bytes(16))
    with Project.create(tmp_path / 'api.fdb', source) as project:
        project.analyze(max_instructions=100)
        project.annotate('ne:2:0', 'function_note')
        project.attach_file(external)
        project.file_reference('ne:1:0', external.name, evidence='authored fixture relationship')
        project.link_labels({'address': 'ne:3:0'}, {'file': external.name, 'offset': 0}, evidence='authored declaration', name='data_root')
        project.define_type('word_alias', dict(kind='typedef', target='u16'))
        project.apply_type('ne:3:0', 'word_alias')
        assert project.typed_data('ne:3:0')['items'][0]['bytes'] == '6669'
        assert project.label_info({'address': 'ne:3:0'})
        assert project.locate('ne:1:1')['instructions'][0]['byte_offset'] == 1
        for method in (project.disassembly, project.xrefs, project.cfg, project.locate):
            with pytest.raises(ValueError, match='NE|DOS'):
                method('0001:0000')
            with pytest.raises(ValueError, match='CS|DOS'):
                method('ne:1:0', cs=1)


def test_ne_memory_and_typed_far_values_do_not_assume_real_mode_or_selectors(tmp_path):
    source = tmp_path / 'memory.exe'; source.write_bytes(ne_file(code=bytes.fromhex('a10000 c3'), fixups=[]))
    with Project.create(tmp_path / 'memory.fdb', source) as project:
        project.analyze(max_instructions=100)
        accesses = project.memory_accesses('ne:3:0')
        assert accesses['unresolved_candidates']
        assert all(item['concrete_target'] is None and item['segment_selector'] is None for item in accesses['items'])
        project.define_type('far_value', dict(kind='pointer', target='u8', address_space='far16', size=4))
        project.apply_type('ne:3:0', 'far_value')
        pointer = project.typed_data('ne:3:0')['items'][0]
        assert pointer['target'] is None and pointer['target_mapped'] is False
        assert pointer['encoded_selector'] == int.from_bytes(b'xt', 'little')
        with pytest.raises(ValueError, match='boundary'):
            project.memory_accesses('ne:1:0xffff', size=2)


def test_unsupported_native_advanced_and_launch_paths_refuse_ne(tmp_path):
    source = tmp_path / 'guard.exe'; source.write_bytes(ne_file())
    with Project.create(tmp_path / 'guard.fdb', source) as project:
        for call in (lambda: project.auto_analyze(), lambda: project.function_analysis('ne:1:0'),
                     lambda: project.capture_signature('ne:1:0', 'authored'),
                     lambda: project.set_summary('ne:1:0', 'memcpy'),
                     lambda: project.machine('missing', boot_image='missing')):
            with pytest.raises(ValueError, match='NE'):
                call()
        for backend in (None,'wine-qemu','wine-ne'):
            with pytest.raises(ValueError,match='Win16 launch requires kernel'):
                project.debugger('missing',tmp_path,backend=backend)


def test_export_identity_index_is_complete_beyond_standalone_preview(tmp_path, monkeypatch):
    import fdisbull.inspection as inspection
    monkeypatch.setattr(inspection, 'MAX_ITEMS', 1)
    data = bytearray(ne_file())
    entry_table = 0x80 + struct.unpack_from('<H', data, 0x80 + 4)[0]
    entries = bytes.fromhex('0102010000 0103010000 00')
    data[entry_table:entry_table + len(entries)] = entries
    struct.pack_into('<H', data, 0x80 + 6, len(entries))
    ordinal = data.index(b'FarExport') + len(b'FarExport')
    struct.pack_into('<H', data, ordinal, 2)
    source = tmp_path / 'exports.exe'; source.write_bytes(data)
    assert len(inspect_binary(bytes(data))['exports']) == 1
    path = tmp_path / 'exports.fdb'
    with Project.create(path, source) as project:
        assert project.locate('ne:3:0')['presentation']['name'] == 'FarExport'
        exports = project.information('exports')['items']
        assert exports[1]['original_name'] == exports[1]['name'] == 'FarExport'
        child = project.patch('ne:1:1', '01000000')['version']
        assert project.locate('ne:3:0', version=child)['presentation']['name'] == 'FarExport'
    with Project(path) as project:
        for version in (1, child):
            assert project.locate('ne:3:0', version=version)['presentation']['name'] == 'FarExport'
