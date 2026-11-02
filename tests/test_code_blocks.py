"""Group explicit entry-qualified instructions without assuming adjacency."""
from copy import deepcopy

import pytest

from fdisbull.code_backings import digest
from fdisbull.code_blocks import group_code_backings, materialize_code_block
from fdisbull.project import Project


def _project(tmp_path, code='7401a8aac3'):
    source = tmp_path / 'authored.bin'
    source.write_bytes(bytes.fromhex(code))
    project = Project.create(tmp_path / 'authored.fdb', source, arch='x86', bits=32, base=0x1000)
    project.analyze()
    return project


def _block(plan, addr):
    return next(b for b in plan['blocks'] if b['entry'].endswith('@' + hex(addr)))


def test_shared_bytes_materialize_independently_and_exits_are_explicit(tmp_path):
    with _project(tmp_path) as project:
        capture = project.code_backings([0x1002, 0x1003])
        plan = group_code_backings(capture)
    a, b = _block(plan, 0x1002), _block(plan, 0x1003)
    assert materialize_code_block(a) == b'\xa8\xaa'
    assert materialize_code_block(b) == b'\xaa'
    assert a['occurrences'][0]['provenance']['byte_roles'][1] == 'immediate'
    assert b['occurrences'][0]['provenance']['byte_roles'][0] == 'instruction_encoding'
    assert a['exits'][0]['target_block'] == b['exits'][0]['target_block'] == _block(plan, 0x1004)['id']
    assert set(plan['atom_blocks']) == {x['id'] for x in capture['blocks']}
    assert sum(len(x['instructions']) for x in plan['blocks']) == len(capture['blocks'])
    assert plan['source_layout_modified'] is False and plan['group_placement'] == 'unplaced'
    capture.clear()
    assert materialize_code_block(a) == b'\xa8\xaa'


def test_entry_and_explicit_split_break_straight_line_independent_of_root_order(tmp_path):
    with _project(tmp_path, '909090c3') as project:
        once = project.code_backings([0x1000])
        grouped = group_code_backings(once)
        assert len(grouped['blocks']) == 1 and grouped['blocks'][0]['bytes'] == '909090c3'
        boundary = next(b['id'] for b in once['blocks'] if b['address'] == '0x1002')
        split = group_code_backings(once, split_at=[boundary])
        assert _block(split, 0x1000)['bytes'] == '9090'
        assert _block(split, 0x1000)['exits'][0]['target_block'] == _block(split, 0x1002)['id']
        with pytest.raises(ValueError, match='split_at'):
            group_code_backings(once, split_at=['x86:32:little@0x1008'])
        plans = [group_code_backings(project.code_backings(entries)) for entries in ([0x1000, 0x1002], [0x1002, 0x1000])]
        for plan in plans:
            assert _block(plan, 0x1000)['bytes'] == '9090'
            assert _block(plan, 0x1002)['bytes'] == '90c3'


def test_loop_exit_and_unresolved_frontier_stay_visible(tmp_path):
    with _project(tmp_path, 'ebfe') as project:
        loop = group_code_backings(project.code_backings([0x1000]))
        item = _block(loop, 0x1000)
        assert item['exits'][0]['target_block'] == item['id']
    # Separate project: no invented continuation when capture stops at budget.
    child = tmp_path / 'partial'; child.mkdir()
    with _project(child, '9090c3') as project:
        capture = project.code_backings([0x1000], max_instructions=1)
        plan = group_code_backings(capture)
        assert not plan['complete'] and plan['unresolved']
        assert len(plan['blocks']) == 1
        assert plan['blocks'][0]['bytes'] == '90'


def test_branch_join_and_split_inside_encoding(tmp_path):
    with _project(tmp_path) as project:
        plan = group_code_backings(project.code_backings([0x1000]))
        jump, a, b, join = (_block(plan, n) for n in (0x1000, 0x1002, 0x1003, 0x1004))
        assert {e['target_block'] for e in jump['exits']} == {a['id'], b['id']}
        assert a['exits'][0]['target_block'] == b['exits'][0]['target_block'] == join['id']
    other = tmp_path / 'no-alternative'; other.mkdir()
    with _project(other, 'a8aac3') as project:
        capture = project.code_backings([0x1000])
        with pytest.raises(ValueError, match='split_at'):
            group_code_backings(capture, split_at=['x86:32:little@0x1001'])


def test_shared_patch_changes_revisions_and_preserves_parent(tmp_path):
    with _project(tmp_path) as project:
        before = group_code_backings(project.code_backings([0x1002, 0x1003]))
        child = project.patch(0x1003, '90')['version']
        project.analyze(version=child)
        after = group_code_backings(project.code_backings([0x1002, 0x1003]))
        for address in (0x1002, 0x1003):
            assert _block(before, address)['block_revision'] != _block(after, address)['block_revision']
        assert materialize_code_block(_block(before, 0x1002)) == b'\xa8\xaa'
        assert materialize_code_block(_block(after, 0x1002)) == b'\xa8\x90'
        assert group_code_backings(project.code_backings([0x1002, 0x1003], version=1)) == before


def test_tamper_and_input_mutation_do_not_change_output(tmp_path):
    with _project(tmp_path) as project:
        capture = project.code_backings([0x1002, 0x1003])
        plan = group_code_backings(capture)
        snapshot = deepcopy(plan)
        capture['blocks'][0]['provenance']['byte_roles'][0] = 'tampered'
        assert plan == snapshot
        with pytest.raises(ValueError):
            group_code_backings(capture)
        block = deepcopy(plan['blocks'][0])
        block['bytes'] = '90'
        with pytest.raises(ValueError, match='revision'):
            materialize_code_block(block)
        block['block_revision'] = digest({k: v for k, v in block.items() if k != 'block_revision'})
        with pytest.raises(ValueError):
            materialize_code_block(block)


def test_context_transition_ends_block_with_explicit_exit(tmp_path):
    with _project(tmp_path, '90c3') as project:
        capture = project.code_backings([0x1000])
    first, second = capture['blocks']
    old_id = second['id']
    new_id = 'x86:32:little:other@0x1001'
    second['id'] = new_id
    second['context'] = 'x86:32:little:other'
    second['provenance']['context'] = second['context']
    second['backing_revision'] = digest({k: v for k, v in second.items() if k != 'backing_revision'})
    first['exits'][0]['target'] = new_id
    first['backing_revision'] = digest({k: v for k, v in first.items() if k != 'backing_revision'})
    for edge in second['incoming']:
        if edge['target'] == old_id:
            edge['target'] = new_id
    second['backing_revision'] = digest({k: v for k, v in second.items() if k != 'backing_revision'})
    capture['sha256'] = digest({k: v for k, v in capture.items() if k != 'sha256'})
    plan = group_code_backings(capture)
    assert len(plan['blocks']) == 2
    assert plan['blocks'][0]['exits'][0]['target_block'] == plan['blocks'][1]['id']


def test_missing_conditional_exit_is_not_called_complete(tmp_path):
    with _project(tmp_path) as project:
        capture = project.code_backings([0x1000])
    atom = capture['blocks'][0]
    atom['exits'].pop()
    atom['backing_revision'] = digest({k: v for k, v in atom.items() if k != 'backing_revision'})
    capture['sha256'] = digest({k: v for k, v in capture.items() if k != 'sha256'})
    plan = group_code_backings(capture)
    assert not plan['complete']
    assert any(item.get('kind') == 'incomplete_control_flow' for item in plan['unresolved'])
