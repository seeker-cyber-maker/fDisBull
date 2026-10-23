"""Universal selection persists original bytes while mapped offsets stay global."""
import hashlib
import json
import struct

import pytest

from fdisbull.cli import main, respond
from fdisbull.inspection import inspect_binary
from fdisbull.loader import load_image
from fdisbull.project import Project
from test_advanced_formats import _body
from test_macho_slices import _fat, _x86_64
from fixtures_formats import pe64
from test_dos_loader import mz_file

BASE = 0x100000000


def _thin(selector):
    arch = 'arm64' if selector == 'arm64' else 'x86'
    cpu, subtype = (0x0100000C, 0) if arch == 'arm64' else (0x01000007, 3)
    data = bytearray(4096)
    struct.pack_into('<8I', data, 0, 0xFEEDFACF, cpu, subtype, 2, 2, 176, 0, 0)
    struct.pack_into('<II16sQQQQIIII', data, 32, 0x19, 152, b'__TEXT', BASE, 4096, 0, 4096, 5, 5, 1, 0)
    struct.pack_into('<16s16sQQ8I', data, 104, b'__text', b'__TEXT', BASE + 0x100, 0x500,
                     0x100, 2 if arch == 'arm64' else 0, 0, 0, 0x80000400, 0, 0, 0)
    struct.pack_into('<IIQQ', data, 184, 0x80000028, 24, 0x100, 0)
    code, _, _ = _body(arch, 64, BASE + 0x100)
    data[0x100:0x100 + len(code)] = code
    marker = ('UNIVERSAL_' + selector.upper() + '_MARKER').encode()
    data[0x300:0x300 + len(marker) + 1] = marker + b'\0'
    return bytes(data), marker.decode()


def _universal(tmp_path):
    x86, _ = _thin('x86_64')
    arm, _ = _thin('arm64')
    data = _fat([(0x01000007, 3, x86), (0x0100000C, 0, arm)])
    source = tmp_path / 'universal.macho'
    source.write_bytes(data)
    return source, data


def _stored_bytes(project, version):
    return bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?', (version,)).fetchone()[0])


@pytest.mark.parametrize('selector,architecture,offset', [('x86_64', 'x86', 4096), ('arm64', 'arm64', 8192)])
def test_public_project_selects_and_auto_analyzes_each_real_cpu_without_losing_container(tmp_path, selector, architecture, offset):
    source, original = _universal(tmp_path)
    image = load_image(source, slice_arch=selector)
    assert image.source_bytes == original and image.metadata['source_sha256'] == hashlib.sha256(original).hexdigest()
    assert image.metadata['macho_slice']['slice_offset'] == offset
    assert image.metadata['file_mappings'][0]['file_offset'] == offset
    database = tmp_path / (selector + '.fdb')
    with Project.create(database, source, slice_arch=selector) as project:
        assert (project.meta['format'], project.arch, project.bits) == ('Mach-O', architecture, 64)
        assert project.meta['entry'] == BASE + 0x100
        assert _stored_bytes(project, 1) == original
        assert project.meta['source_sha256'] == hashlib.sha256(original).hexdigest()
        receipt = project.auto_analyze(max_instructions=128, max_functions=16, max_steps=1024, max_rounds=8)
        assert receipt['stable'] and not receipt['budget_exhausted']
        result = project.function_analysis(BASE + 0x100)
        assert result['state'] == 'done' and not result['stale']
        targets = result['result']['indirect']['candidates']
        assert any(item['target'] == BASE + 0x120 and item['admitted'] for item in targets)
        assert project.locate(BASE + 0x120)['decoded']
        generation = result['generation']
        assert project.auto_analyze(max_instructions=128, max_functions=16, max_steps=1024, max_rounds=8)['processed_jobs'] == 0
    source.unlink()
    with Project(database) as reopened:
        assert reopened.function_analysis(BASE + 0x100)['generation'] == generation
        assert reopened.advanced_status()['stable']
        assert _stored_bytes(reopened, 1) == original


@pytest.mark.parametrize('selector,offset', [('x86_64', 4096), ('arm64', 8192)])
def test_selected_metadata_uses_original_container_offsets_for_sections_strings_and_mappings(tmp_path, selector, offset):
    source, original = _universal(tmp_path)
    _, marker = _thin(selector)
    document = inspect_binary(original, slice_arch=selector)
    assert document['header']['format'] == 'Mach-O' and document['header']['header_offset'] == offset
    assert document['container_header']['format'] == 'Mach-O fat'
    assert document['selected_slice']['slice_offset'] == offset
    section = next(item for item in document['sections'] if item['name'] == '__text')
    assert section['file_offset'] == offset + 0x100 and section['virtual_address'] == BASE + 0x100
    string = next(item for item in document['strings'] if item['text'] == marker)
    assert string['file_offset'] == offset + 0x300 and string['address'] == BASE + 0x300
    other_marker = _thin('arm64' if selector == 'x86_64' else 'x86_64')[1]
    assert not any(item['text'] == other_marker for item in document['strings'])
    with Project.create(tmp_path / 'offsets.fdb', source, slice_arch=selector) as project:
        assert project.information('sections')['items'][0]['file_offset'] == offset + 0x100
        assert project._document(1)['file_mappings'][0]['file_offset'] == offset
        selected_string = next(item for item in project.information('strings')['items'] if item['text'] == marker)
        assert selected_string['file_offset'] == offset + 0x300


@pytest.mark.parametrize('selector,offset,other_offset', [('x86_64', 4096, 8192), ('arm64', 8192, 4096)])
def test_patch_changes_only_selected_original_file_extent_and_parent_survives_restart(tmp_path, selector, offset, other_offset):
    source, original = _universal(tmp_path)
    database = tmp_path / 'patched.fdb'
    with Project.create(database, source, slice_arch=selector) as project:
        project.auto_analyze()
        child = project.patch(BASE + 0x300, '58')['version']
        expected = original[:offset + 0x300] + b'X' + original[offset + 0x301:]
        assert _stored_bytes(project, child) == expected
        assert _stored_bytes(project, 1) == original
        assert _stored_bytes(project, child)[other_offset:other_offset + 4096] == original[other_offset:other_offset + 4096]
        assert project.regions(1)[0].data[0x300] == ord('U')
        assert project.regions(child)[0].data[0x300] == ord('X')
        _, marker = _thin(selector)
        changed = next(item for item in project.information('strings', version=child)['items'] if item['text'] == 'X' + marker[1:])
        assert changed['file_offset'] == offset + 0x300 and int(changed['address'], 0) == BASE + 0x300
        assert project.auto_analyze(version=child)['stable']
    source.unlink()
    with Project(database) as reopened:
        assert _stored_bytes(reopened, 1) == original
        assert _stored_bytes(reopened, child) == expected
        assert reopened.meta['source_sha256'] == hashlib.sha256(original).hexdigest()
        assert reopened.function_analysis(BASE + 0x100, version=child)['state'] == 'done'


def test_inspection_inventory_needs_no_choice_but_import_failures_leave_no_database(tmp_path):
    source, original = _universal(tmp_path)
    document = inspect_binary(original)
    assert document['header']['format'] == 'Mach-O fat'
    assert [item['selector'] for item in document['header']['slices']] == ['x86_64', 'arm64']
    assert document['sections'] == [] and 'selected_slice' not in document
    assert all(item['address'] is None for item in document['strings'])
    for options in ({}, {'slice_arch': 'x86'}, {'arch': 'x86', 'slice_arch': 'x86_64'}):
        database = tmp_path / 'absent.fdb'
        response = respond({'method': 'import', 'params': dict(project=str(database), path=str(source), **options)})
        assert not response['ok'] and not database.exists()
        assert not database.with_name(database.name + '-wal').exists()
    ambiguous = tmp_path / 'ambiguous.macho'
    ambiguous.write_bytes(_fat([(0x01000007, 3, _x86_64(3)), (0x01000007, 8, _x86_64(8))]))
    result = respond({'method': 'analyze-module', 'params': dict(project=str(tmp_path / 'ambiguous.fdb'), path=str(ambiguous),
                                                              entry=BASE + 0x100, slice_arch='x86_64')})
    assert not result['ok'] and not (tmp_path / 'ambiguous.fdb').exists()


def test_protocol_inspect_and_import_expose_explicit_slice_selection(tmp_path):
    source, _ = _universal(tmp_path)
    inventory = respond({'method': 'inspect', 'params': {'path': str(source)}})
    assert inventory['ok'] and len(inventory['result']['header']['slices']) == 2
    selected = respond({'method': 'inspect', 'params': {'path': str(source), 'slice_arch': 'arm64'}})
    assert selected['ok'] and selected['result']['selected_slice']['selector'] == 'arm64'
    imported = respond({'method': 'import', 'params': {'path': str(source), 'project': str(tmp_path / 'protocol.fdb'), 'slice_arch': 'x86_64'}})
    assert imported['ok'] and imported['result']['arch'] == 'x86' and imported['result']['bits'] == 64


@pytest.mark.parametrize('data', [mz_file(b'\xcb'), pe64()], ids=['dos_mz', 'pe64'])
def test_non_macho_slice_selector_is_rejected_before_creating_a_project(tmp_path, data):
    source = tmp_path / 'other.exe'
    source.write_bytes(data)
    database = tmp_path / 'absent.fdb'
    result = respond({'method': 'import', 'params': dict(path=str(source), project=str(database), slice_arch='arm64')})
    assert not result['ok'] and not database.exists()


def test_explicit_mz_image_choice_still_rejects_macho_cpu_slice_selection(tmp_path):
    source = tmp_path / 'classic.exe'
    source.write_bytes(mz_file(b'\xcb'))
    database = tmp_path / 'absent.fdb'
    result = respond({'method': 'import', 'params': dict(path=str(source), project=str(database), image='mz', slice_arch='arm64')})
    assert not result['ok'] and not database.exists()
    assert result['error']['type'] == 'ValueError' and 'slice' in result['error']['message'].lower()


@pytest.mark.parametrize('selector,architecture', [('x86_64', 'x86'), ('arm64', 'arm64')])
def test_cli_inspect_import_and_module_entry_keep_the_explicit_slice(tmp_path, capsys, selector, architecture):
    source, _ = _universal(tmp_path)
    assert main(['inspect', str(source), '--slice-arch', selector]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected['result']['selected_slice']['selector'] == selector
    imported = tmp_path / 'cli.fdb'
    assert main(['import', str(source), str(imported), '--slice-arch', selector]) == 0
    assert json.loads(capsys.readouterr().out)['result']['arch'] == architecture
    module = tmp_path / 'module.fdb'
    assert main(['analyze-module', str(source), str(module), '--entry', hex(BASE + 0x120), '--slice-arch', selector]) == 0
    result = json.loads(capsys.readouterr().out)['result']
    assert result['analysis_roots'] == [hex(BASE + 0x120)] and result['analysis']['stable']
    with Project(module) as project:
        assert project.arch == architecture
        assert project.meta['analysis_roots'] == [BASE + 0x120]
        assert [item['address'] for item in project.disassembly(BASE + 0x100)['instructions']] == [hex(BASE + 0x120)]
