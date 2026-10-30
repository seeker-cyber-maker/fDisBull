"""The LE module reaches the ordinary persisted x86-32 processor workflow."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from fdisbull.cli import respond
from fdisbull.image_views import image_views
from fdisbull.inspection import identify_header, inspect_binary
from fdisbull.loader import load_image
from fdisbull.project import Project
from test_le_loader import le_file


def command(*args):
    """Exercise a fresh CLI process with the source under test, not its wheel."""
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    process = subprocess.run([sys.executable, '-m', 'fdisbull', *map(str, args)],
                             env=env, capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stderr + process.stdout
    document = json.loads(process.stdout)
    assert document['ok'], document
    return document['result']


@pytest.mark.parametrize('selector', [None, 'auto', 'le'])
def test_import_analyze_and_restart_retain_the_protected_image(tmp_path, selector):
    source = tmp_path / 'authored.exe'
    original = le_file()
    source.write_bytes(original)
    path = tmp_path / 'protected.fdb'
    options = {} if selector is None else {'image': selector}
    created = respond(dict(method='import', params=dict(path=str(source), project=str(path), **options)))
    assert created['ok'], created
    with Project(path) as project:
        assert (project.meta['format'], project.arch, project.bits) == ('LE', 'x86', 32)
        assert project.context == 'x86:32:little'
        result = project.analyze(max_instructions=50)
        assert result['stable'] and result['decoded'] == 2
        instructions = project.disassembly()['instructions']
        assert instructions[0]['bytes'] == 'b802000200'
        assert instructions[1]['mnemonic'] == 'ret'
        assert project.information('header')['selected_image'] == 'le'
        assert project.information('relocations')['total'] == 1
        assert bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()[0]) == original
    source.unlink()
    status = command('status', path)
    assert status['format'] == 'LE' and status['bits'] == 32
    assert status['counts']['instructions'] == 2
    svg = tmp_path / 'persisted.svg'
    command('render', path, svg)
    assert ET.parse(svg).getroot().tag.endswith('svg')
    assert 'eax' in svg.read_text()


def test_cli_selects_le_but_preserves_an_explicit_mz_stub_view(tmp_path):
    source = tmp_path / 'dual.exe'
    source.write_bytes(le_file(code=b'\x90\xc3', fixups=[b'', b''], entry_offset=1))
    for selector, bits, entry in [('le', 32, '0x10001'), ('mz', 16, '0x10000')]:
        path = tmp_path / (selector + '.fdb')
        result = command('import', source, path, '--image', selector)
        assert result['format'] == selector.upper() and result['bits'] == bits
        assert result['entry'] == entry
        inspected = command('inspect', source, '--image', selector)
        assert inspected['selected_image'] == selector
        assert inspected['header']['bits'] == bits
    views = image_views(source.read_bytes())
    assert [view['image'] for view in views] == ['mz', 'le']
    assert all(view['available'] for view in views)
    assert views[1]['entrypoint'] == 0x10001


def test_bare_le_uses_the_same_public_selection_and_file_provenance(tmp_path):
    wrapped = le_file()
    data = bytearray(wrapped[0x80:])
    struct.pack_into('<I', data, 0x80, struct.unpack_from('<I', data, 0x80)[0] - 0x80)
    source = tmp_path / 'authored.le'
    source.write_bytes(data)
    assert identify_header(bytes(data))['format'] == 'LE'
    assert [view['image'] for view in image_views(bytes(data))] == ['le']
    loaded = load_image(source)
    assert loaded.format == 'LE' and loaded.source_bytes == bytes(data)
    inspected = inspect_binary(bytes(data), image='le')
    assert inspected['selected_image'] == 'le' and inspected['header']['entrypoint'] == 0x10000
    first = inspected['file_mappings'][0]
    assert data[first['file_offset']] == 0xb8


def test_le_memory_patch_preserves_original_fixups_and_parent_analysis(tmp_path):
    source = tmp_path / 'authored.exe'
    original = le_file()
    source.write_bytes(original)
    path = tmp_path / 'versions.fdb'
    with Project.create(path, source) as project:
        project.analyze(max_instructions=50)
        parent = project.disassembly()['instructions']
        # Edit an already relocated immediate: writing it directly into the
        # file would be overwritten by the original LE relocation on reload.
        child = project.patch('0x10001', '03000200')['version']
        assert project.regions(child)[0].data[:6] == bytes.fromhex('b803000200c3')
        for version in (1, child):
            retained = project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?', (version,)).fetchone()[0]
            assert bytes(retained) == original
        assert project.disassembly(version=1)['instructions'] == parent
        assert project.analyze(version=child, max_instructions=50)['stable']
        assert any('No inverse fixup' in message for message in project.information('header', version=child)['warnings'])
    with Project(path) as reopened:
        assert reopened.disassembly(version=child)['instructions'][0]['bytes'] == 'b803000200'
        assert reopened.disassembly(version=1)['instructions'] == parent
    assert source.read_bytes() == original


def test_status_does_not_repeat_every_fixup_or_page(tmp_path):
    records = b''.join(struct.pack('<BBhBH', 7, 0, 4 * (index + 1), 2, 2)
                       for index in range(1000))
    source = tmp_path / 'many-fixups.exe'
    source.write_bytes(le_file(code=b'\xc3' + bytes(4095), fixups=[records, b'']))
    with Project.create(tmp_path / 'many.fdb', source) as project:
        status = project.status()
        assert len(json.dumps(status).encode()) < 16000
        metadata = status['loader_metadata']['le']
        assert metadata['fixup_count'] == 1000
        assert 'fixups' not in metadata and 'pages' not in metadata
        assert project.information('relocations', limit=10)['total'] == 1000
        assert len(project.information('relocations', limit=10)['items']) == 10
        assert len(project.meta['loader_metadata']['le']['fixups']) == 1000


def test_project_relocations_remain_complete_beyond_inspection_preview(tmp_path, monkeypatch):
    # A deliberately small standalone preview exercises the real public
    # pagination boundary without constructing a huge fixture.
    import fdisbull.inspection as inspection
    monkeypatch.setattr(inspection, 'MAX_ITEMS', 1)
    records = b''.join(struct.pack('<BBhBH', 7, 0, offset, 2, 2) for offset in (4, 8))
    source = tmp_path / 'two-fixups.exe'
    original = le_file(code=b'\xc3' + bytes(16), fixups=[records, b''])
    source.write_bytes(original)
    assert len(inspection.inspect_binary(original)['relocations']) == 1
    with Project.create(tmp_path / 'complete.fdb', source) as project:
        assert project.information()['counts']['relocations'] == 2
        page = project.information('relocations', limit=1, offset=1)
        assert page['total'] == 2 and not page['has_more']
        assert page['items'][0]['address'] == '0x10008'


@pytest.mark.parametrize('options', [{'bits': 32}, {'base': 0x1000}, {'load_segment': 0x2000}, {'slice_arch': 'x86'}])
def test_le_rejects_unmodeled_mapping_overrides(tmp_path, options):
    source = tmp_path / 'authored.exe'
    source.write_bytes(le_file())
    with pytest.raises(ValueError, match='LE'):
        load_image(source, **options)


def test_unsupported_le_fixup_never_silently_falls_back_to_the_stub(tmp_path):
    source = tmp_path / 'unsupported.exe'
    source.write_bytes(le_file(fixups=[struct.pack('<BBhBH', 7, 1, 1, 2, 2), b'']))
    path = tmp_path / 'refused.fdb'
    result = respond(dict(method='import', params=dict(path=str(source), project=str(path))))
    assert not result['ok'] and 'fixup' in str(result)
    assert not path.exists()
    views = image_views(source.read_bytes())
    assert views[0]['available'] and not views[1]['available']
    assert 'fixup' in views[1]['error']
    inspected = inspect_binary(source.read_bytes())
    assert inspected['selected_image'] == 'le'
    assert not inspected['sections']
    assert any('LE memory mapping unavailable' in message for message in inspected['warnings'])
