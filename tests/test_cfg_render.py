"""Public SVG exports retain exact CFG facts and qualify incomplete graphs."""
from copy import deepcopy
import json
import struct
import xml.etree.ElementTree as ET

import pytest

from fdisbull.cfg import CFGMixin
from fdisbull.cfg_render import render_cfg
from fdisbull.project import Project


NS = {'s': 'http://www.w3.org/2000/svg'}


def _raw(tmp_path, data):
    source = tmp_path / 'cfg.bin'
    source.write_bytes(data)
    return Project.create(tmp_path / 'cfg.fdb', source, arch='x86', base=0x1000)


def _loop():
    data = bytearray(b'\xcc' * 0x21)
    data[:17] = bytes.fromhex('31c083f8027d09e814000000ffc0ebf2c3')
    data[0x20] = 0xC3
    return data


def _xml(path):
    root = ET.parse(path).getroot()
    return root, ''.join(root.itertext())


def _metadata(root):
    return json.loads(root.find('s:metadata', NS).text)


def _blocks(root):
    return [group for group in root.findall('.//s:g', NS) if 'block' in group.get('class', '').split()]


def test_real_cfg_svg_keeps_exact_blocks_loop_and_call_assumption(tmp_path):
    with _raw(tmp_path, _loop()) as project:
        project.analyze()
        snapshot = CFGMixin.cfg(project, 0x1000)
    result = render_cfg(snapshot, tmp_path / 'nested' / 'loop.svg')
    root, text = _xml(result['path'])
    assert result['format'] == 'svg' and result['instruction_count'] == 7
    assert result['block_count'] == len(snapshot['basic_blocks'])
    assert {group.get('data-block-id') for group in _blocks(root)} == {block['id'] for block in snapshot['basic_blocks']}
    rendered_ids = [group.get('data-instruction-id') for group in root.findall('.//s:g', NS) if group.get('class') == 'instruction']
    assert len(rendered_ids) == len(set(rendered_ids)) == 7
    assert set(rendered_ids) == {node['id'] for node in snapshot['nodes']}
    assert not any('0x1020' in identity for identity in rendered_ids)
    back = next(edge for edge in snapshot['block_edges'] if edge['source_address'] == '0x100e')
    paths = [group for group in root.findall('.//s:g', NS) if group.get('class') == 'edge']
    assert any(group.get('data-source-block') == back['source_block'] and group.get('data-target-block') == back['target_block'] for group in paths)
    assert any(path.get('stroke-dasharray') for path in root.findall('.//s:path', NS))
    assert 'candidate' in text and 'function boundary not proven' in text
    assert 'Calls are not entered' in text and 'assumes' in text


def test_highlights_and_names_are_safe_selectable_xml_with_controls_cleaned(tmp_path):
    hostile = '<script onload="alert(1)">& " selected\x00\u202e 雪'
    with _raw(tmp_path, _loop()) as project:
        project.analyze()
        project.annotate(0x1000, 'routine <& "quoted">', kind='name')
        snapshot = CFGMixin.cfg(project, 0x1000, highlights=[{'address': 0x100C, 'label': hostile}])
    result = render_cfg(snapshot, tmp_path / 'safe.svg')
    root, text = _xml(result['path'])
    assert not root.findall('.//s:script', NS)
    assert '<script onload="alert(1)">& " selected 雪' in text
    assert 'routine <& "quoted">' in text
    assert '\x00' not in text and '\u202e' not in text
    selected = [group for group in _blocks(root) if 'selected' in group.get('class', '').split()]
    assert len(selected) == result['highlighted_block_count'] == 1
    assert result['highlighted_instruction_count'] == 1
    assert selected[0].find('s:rect', NS).get('stroke') == '#ffe08a'
    assert root.findall('.//s:text', NS) and root.findall('.//s:a', NS)


def test_budget_targets_and_unknown_indirect_flow_remain_explicit(tmp_path):
    with _raw(tmp_path, _loop()) as project:
        project.analyze()
        snapshot = CFGMixin.cfg(project, 0x1000, max_instructions=1, highlights=[0x100C])
    result = render_cfg(snapshot, tmp_path / 'partial.svg')
    root, text = _xml(result['path'])
    assert result['external_edge_count'] == 1
    assert _metadata(root)['budget_exhausted'] is True
    assert _metadata(root)['frontier_count'] == 1
    assert 'outside' in text and 'NOT REACHED' in text and 'budget exhausted: True' in text
    other = tmp_path / 'indirect'
    other.mkdir()
    with _raw(other, bytes.fromhex('ffe0')) as project:
        project.analyze()
        unknown = CFGMixin.cfg(project, 0x1000)
    root, text = _xml(render_cfg(unknown, tmp_path / 'unknown.svg')['path'])
    assert _metadata(root)['unresolved_count'] == 1
    assert 'unresolved: 1' in text and 'Graph closed: False' in text


def _mz(module, relocations):
    header = bytearray(64)
    size = len(header) + len(module)
    struct.pack_into('<14H', header, 0, 0x5A4D, size % 512, (size + 511) // 512,
                     len(relocations), 4, 0, 0xFFFF, 0, 0, 0, 0, 0, 28, 0)
    for index, offset in enumerate(relocations):
        struct.pack_into('<HH', header, 28 + index * 4, offset, 0)
    return bytes(header) + bytes(module)


def test_dos_context_aliases_keep_distinct_segmented_addresses(tmp_path):
    module = bytearray(96)
    module[:5] = bytes.fromhex('ea10000300')
    module[0x40:0x45] = bytes.fromhex('ea00000400')
    source = tmp_path / 'alias.exe'
    source.write_bytes(_mz(module, [3, 0x43]))
    with Project.create(tmp_path / 'alias.fdb', source) as project:
        project.analyze()
        snapshot = CFGMixin.cfg(project, '1000:0000')
    assert len([node for node in snapshot['nodes'] if node['address'] == '0x10040']) == 2
    root, text = _xml(render_cfg(snapshot, tmp_path / 'alias.svg')['path'])
    assert '1003:0010' in text and '1004:0000' in text
    identities = [group.get('data-instruction-id') for group in root.findall('.//s:g', NS) if group.get('class') == 'instruction']
    assert len(identities) == len(set(identities)) == 3
    assert any('cs=1003' in identity for identity in identities)
    assert any('cs=1004' in identity for identity in identities)


def test_large_graph_is_deterministic_wrapped_and_has_no_overlapping_blocks(tmp_path):
    # A public CFG-shaped snapshot with a long field and a sizeable loop.
    nodes, blocks, edges = [], [], []
    for index in range(205):
        identity, block = f'node-{index}', f'b{index}'
        nodes.append(dict(id=identity, address=hex(0x1000 + index), mnemonic='mov',
                          operands='label_' + 'x' * 1600 if index == 0 else 'ax,bx', bytes='89d8'))
        blocks.append(dict(id=block, address=hex(0x1000 + index), context='x86:16', instruction_ids=[identity]))
        target = index + 1 if index < 204 else 0
        edges.append(dict(source=identity, target=f'node-{target}', source_block=block,
                          target_block=f'b{target}', kind='branch', evidence='stored test edge'))
    snapshot = dict(nodes=nodes, basic_blocks=blocks, block_edges=edges, status='candidate')
    first = render_cfg(snapshot, tmp_path / 'one.svg')
    render_cfg(snapshot, tmp_path / 'two.svg')
    assert (tmp_path / 'one.svg').read_bytes() == (tmp_path / 'two.svg').read_bytes()
    root, text = _xml(first['path'])
    rects = [{key: int(rect.get(key)) for key in ('x', 'y', 'width', 'height')}
             for rect in root.findall('.//s:rect', NS) if rect.get('class') == 'block-box']
    assert len(rects) == 205
    for index, box in enumerate(rects):
        assert box['width'] > 0 and box['height'] > 0
        assert box['x'] + box['width'] <= first['width'] and box['y'] + box['height'] <= first['height']
        for other in rects[index + 1:]:
            assert (box['x'] + box['width'] <= other['x'] or other['x'] + other['width'] <= box['x']
                    or box['y'] + box['height'] <= other['y'] or other['y'] + other['height'] <= box['y'])
    assert sum('xxxxxxxx' in element.text for element in root.findall('.//s:text', NS) if element.text) > 10


def test_empty_exact_entry_view_retains_status_and_gap(tmp_path):
    with _raw(tmp_path, b'\xc3') as project:
        project.analyze()
        snapshot = CFGMixin.cfg(project, 0x1001)
    result = render_cfg(snapshot, tmp_path / 'empty.svg')
    root, text = _xml(result['path'])
    assert result['block_count'] == result['instruction_count'] == 0
    assert 'No stored instruction blocks at this exact entry.' in text
    assert _metadata(root)['gap_count'] == 1 and '0x1001' in text


def test_invalid_or_oversized_snapshots_fail_before_output(tmp_path):
    path = tmp_path / 'absent' / 'bad.svg'
    with pytest.raises(ValueError, match='format must be svg'):
        render_cfg({}, path.with_suffix('.png'))
    with pytest.raises(ValueError, match='at most 10000'):
        render_cfg({'nodes': [{}] * 10001}, path)
    with _raw(tmp_path, b'\xc3') as project:
        project.analyze()
        snapshot = CFGMixin.cfg(project, 0x1000)
    duplicate = deepcopy(snapshot)
    duplicate['basic_blocks'].append(deepcopy(duplicate['basic_blocks'][0]))
    duplicate['basic_blocks'][-1]['id'] = 'duplicate'
    with pytest.raises(ValueError, match='exactly once'):
        render_cfg(duplicate, path)
    bad_id = deepcopy(snapshot)
    bad_id['nodes'][0]['id'] += '\x00'
    with pytest.raises(ValueError, match='control characters'):
        render_cfg(bad_id, path)
    snapshot['nodes'][0]['display_operands'] = 'x' * 4097
    with pytest.raises(ValueError, match='text exceeds'):
        render_cfg(snapshot, path)
    assert not path.exists() and not path.parent.exists()
