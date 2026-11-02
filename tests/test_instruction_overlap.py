"""Explicit code ranges may describe distinct starts sharing physical bytes."""
import xml.etree.ElementTree as ET

import pytest
from PIL import Image

from fdisbull.cfg_render import render_cfg
from fdisbull.project import Project
from fdisbull.render import render_snapshot


def _project(tmp_path):
    source = tmp_path / 'overlap.bin'
    # JE enters STOSB at +3; fallthrough decodes TEST AL,0xaa at +2.
    source.write_bytes(bytes.fromhex('7401a8aac3'))
    return Project.create(tmp_path / 'overlap.fdb', source, arch='x86', bits=32, base=0x1000)


def _assert_overlap(project, version, shared='aa'):
    view = project.locate(0x1003, version=version)
    assert view['overlap'] and view['byte'] == shared
    assert {(i['address'], i['bytes']) for i in view['instructions']} == {
        ('0x1002', 'a8' + shared), ('0x1003', shared),
    }
    assert {(i['address'], i['size'], i['representation']) for i in view['definitions']} == {
        ('0x1002', 2, 'code'), ('0x1003', 1, 'code'),
    }


@pytest.mark.parametrize('order', [(0x1002, 0x1003), (0x1003, 0x1002)])
def test_overlapping_code_definitions_survive_patch_reopen_and_render(tmp_path, order):
    db = tmp_path / 'overlap.fdb'
    with _project(tmp_path) as project:
        for start in order:
            result = project.represent(start, 'code', size=2 if start == 0x1002 else 1)
            assert result['analysis']['stable']
        _assert_overlap(project, 1)
        graph = project.cfg(0x1000, version=1)
        assert len(graph['basic_blocks']) == 4 and len(graph['block_edges']) == 4
        listing = tmp_path / 'listing.png'
        render_snapshot(project.disassembly(version=1), listing)
        with Image.open(listing) as image:
            image.verify()
        graph_file = tmp_path / 'graph.svg'
        render_cfg(graph, graph_file)
        text = ''.join(ET.parse(graph_file).getroot().itertext()).lower()
        assert 'test' in text and 'stosb' in text
        child = project.patch(0x1003, '90')['version']
        project.analyze(version=child)
        _assert_overlap(project, 1)
        _assert_overlap(project, child, '90')
    with Project(db) as project:
        _assert_overlap(project, 1)
        _assert_overlap(project, child, '90')


@pytest.mark.parametrize('first,second', [('code', 'byte'), ('byte', 'code')])
def test_non_code_collision_is_rejected_without_mutation(tmp_path, first, second):
    with _project(tmp_path) as project:
        project.represent(0x1002 if first == 'code' else 0x1003, first,
                          size=2 if first == 'code' else 1)
        before = project.locate(0x1003)
        with pytest.raises(ValueError, match='definition overlaps'):
            project.represent(0x1002 if second == 'code' else 0x1003, second,
                              size=2 if second == 'code' else 1)
        assert project.locate(0x1003) == before


def test_replacing_code_with_data_cannot_collide_with_other_code(tmp_path):
    with _project(tmp_path) as project:
        project.represent(0x1002, 'code', size=2)
        project.represent(0x1003, 'code', size=1)
        before = project.locate(0x1003)
        with pytest.raises(ValueError, match='definition overlaps'):
            project.represent(0x1002, 'word')
        assert project.locate(0x1003) == before
        _assert_overlap(project, 1)


@pytest.mark.parametrize('indexed', [False, True])
def test_nonoverlapping_data_replacement_blocks_only_affected_stream(tmp_path, indexed):
    with _project(tmp_path) as project:
        project.represent(0x1002, 'code', size=2)
        project.represent(0x1003, 'code', size=1)
        if indexed:
            assert project.auto_analyze()['stable']
        result = project.represent(0x1002, 'byte')
        assert result['invalidation']['mode'] == ('dependency_index' if indexed else 'full_reset')
        assert result['analysis']['stable']
        assert project.locate(0x1002)['classification'] == 'data'
        surviving = project.locate(0x1003)
        assert [(item['address'], item['bytes']) for item in surviving['instructions']] == [('0x1003', 'aa')]


@pytest.mark.parametrize('order', [(0x1002, 0x1003), (0x1003, 0x1002)])
def test_indexed_reanalysis_preserves_overlapping_code_entries(tmp_path, order):
    with _project(tmp_path) as project:
        first, second = order
        reset = project.represent(first, 'code', size=2 if first == 0x1002 else 1)
        assert reset['invalidation']['mode'] == 'full_reset'
        assert project.auto_analyze()['stable']
        result = project.represent(second, 'code', size=2 if second == 0x1002 else 1)
        assert result['invalidation']['mode'] == 'dependency_index'
        assert result['analysis']['stable']
        _assert_overlap(project, 1)
