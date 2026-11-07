from pathlib import Path

import pytest

from fdisbull.record_candidates import (
    analyze_record_bytes, compare_record_snapshots, read_record_rows,
    record_frontier, snapshot_record_files,
)


def actors(stride=68, count=250):
    raw = bytearray(stride * count)
    for index, name in enumerate((b'Alex Morgan', b'Sam Foster', b'Chris Hayes', b'Jo Riley')):
        start = index * stride
        raw[start] = index + 1
        raw[start+16:start+16+len(name)] = name
    # Preserve a non-name-bearing record rather than assuming it is empty.
    raw[99*stride+3] = 71
    return bytes(raw)


def test_recovers_name_stride_before_subdivisors_and_keeps_partial_occupancy_unknown():
    result = analyze_record_bytes(actors(), source={'label': 'supplied sample'})
    first = result['name_candidates'][0]
    assert (first['stride'], first['record_count'], first['name_offset']) == (68, 250, 16)
    assert first['matched_names'] == 4
    assert first['adjacent_stride_matches'] == 3
    assert first['examples'][2] == {'row': 2, 'offset': 152, 'text': 'Chris Hayes'}
    assert 'occupancy' in result['claim']
    assert not any('occupied' in candidate for candidate in result['name_candidates'])


def test_record_reader_reconstructs_source_and_preserves_non_name_rows_and_tail(tmp_path):
    path = tmp_path / 'actors.bin'
    data = actors() + b'\x1f\x00\x82'
    path.write_bytes(data)
    census = read_record_rows(path, stride=68, source_label='fresh strategic slot', name_offset=16)
    assert census['source']['path'] == str(path)
    assert census['source']['label'] == 'fresh strategic slot'
    assert census['record_count'] == 250 and census['complete'] is True
    assert census['rows'][0]['name'] == 'Alex Morgan'
    assert bytes.fromhex(census['rows'][99]['raw_hex'])[3] == 71
    assert b''.join(bytes.fromhex(row['raw_hex']) for row in census['rows']) + bytes.fromhex(census['trailing_hex']) == data
    partial = read_record_rows(path, stride=68, source_label='fresh strategic slot', start=2, limit=3)
    assert not partial['complete'] and partial['next_row'] == 5
    assert partial['rows'][0]['offset'] == 136


def test_name_spacing_survives_unassigned_trailer_without_claiming_exact_partition():
    data = actors() + b'\x00\xff\x10\x80\x00'
    result = analyze_record_bytes(data, source={'label': 'records with trailer'})
    first = result['name_candidates'][0]
    assert (first['stride'], first['record_count'], first['name_offset']) == (68, 250, 16)
    assert first['trailing_bytes'] == 5
    assert not any(p['stride'] == 68 for p in result['partitions'])


def test_name_in_partial_tail_does_not_count_as_another_full_row():
    # Only two full named rows; a third name in a short tail is insufficient.
    data = bytearray(2 * 68 + 24)
    for i, name in enumerate((b'Alex Morgan', b'Sam Foster', b'Chris Hayes')):
        data[i * 68:i * 68 + len(name)] = name
    result = analyze_record_bytes(bytes(data), source={}, min_records=2)
    assert not any(c['stride'] == 68 for c in result['name_candidates'])


def test_inventory_changes_detect_same_size_rewrite_without_collapsing_sources(tmp_path):
    supplied = tmp_path / 'supplied'
    fresh = tmp_path / 'fresh'
    supplied.mkdir(); fresh.mkdir()
    original = actors()
    (supplied / 'actors.bin').write_bytes(original)
    (fresh / 'actors.bin').write_bytes(original)
    roots = [{'path': str(supplied), 'label': 'supplied sample'},
             {'path': str(fresh), 'label': 'strategic slot'}]
    first = record_frontier(roots)
    assert len(first['ready_tasks']) == 1
    assert first['ready_tasks'][0]['source_label'] == 'strategic slot'
    assert first['ready_tasks'][0]['also_sources'][0]['source_label'] == 'supplied sample'
    comparison = first['source_comparisons'][0]['files'][0]
    assert comparison['kind'] == 'same_bytes'
    assert comparison['before']['label'] != comparison['after']['label']
    modified = bytearray(original)
    modified[16:27] = b'Pat Andrews'
    (fresh / 'actors.bin').write_bytes(modified)
    second = record_frontier(roots, previous=first, runtime_blocker='Options control is unresolved')
    assert [row['kind'] for row in second['changes']] == ['same_bytes', 'changed']
    assert len(second['ready_tasks']) == 1
    assert second['ready_tasks'][0]['source_label'] == 'strategic slot'
    assert second['ready_tasks'][0]['candidate']['examples'][0]['text'] == 'Pat Andrews'
    assert second['blocked_tasks'][0]['blocks_offline_tasks'] is False
    assert second['ready_tasks'][0]['requires_runtime'] is False


def test_shared_row_counts_surface_linkable_files_without_claiming_schema(tmp_path):
    (tmp_path / 'entities.bin').write_bytes(bytes(35 * 124))
    (tmp_path / 'positions.bin').write_bytes(bytes(35 * 20))
    result = record_frontier([{'path': str(tmp_path), 'label': 'runtime handoff'}])
    candidate, = [row for row in result['shared_record_counts'] if row['record_count'] == 35]
    assert {Path(f['path']).name: f['stride'] for f in candidate['files']} == {
        'entities.bin': 124, 'positions.bin': 20}
    assert candidate['source_label'] == 'runtime handoff'
    assert 'unverified' in candidate['basis']


def test_budgets_and_unreadable_files_leave_other_work_ready(tmp_path):
    (tmp_path / 'a-large.bin').write_bytes(bytes(100))
    (tmp_path / 'b-small.bin').write_bytes(bytes(30))
    (tmp_path / 'c-small.bin').write_bytes(bytes(30))
    result = record_frontier([{'path': str(tmp_path), 'label': 'handoff'}],
                             max_file_bytes=50, max_total_bytes=50)
    assert result['status'] == 'partial'
    assert [Path(f['path']).name for f in result['sources'][0]['files']] == ['b-small.bin']
    assert len(result['ready_tasks']) == 1 and len(result['errors']) == 2
    assert result['limits']['bytes_read'] == 30


def test_missing_or_budget_excluded_file_does_not_become_false_removal(tmp_path):
    path = tmp_path / 'data.bin'
    path.write_bytes(bytes(100))
    before = snapshot_record_files(tmp_path, 'before')
    after = snapshot_record_files(tmp_path, 'after', max_file_bytes=50)
    assert compare_record_snapshots(before, after)[0]['kind'] == 'unobserved'
    absent = snapshot_record_files(tmp_path / 'missing', 'missing')
    assert compare_record_snapshots(before, absent)[0]['kind'] == 'unobserved'
    path.unlink()
    assert compare_record_snapshots(before, snapshot_record_files(tmp_path, 'after'))[0]['kind'] == 'removed'


def test_total_budgets_apply_across_roots_and_symlink_is_not_followed(tmp_path):
    roots = []
    for name in ('one', 'two'):
        folder = tmp_path / name
        folder.mkdir()
        (folder / 'data.bin').write_bytes(bytes(20))
        roots.append({'path': str(folder), 'label': name})
    (tmp_path / 'one' / 'link.bin').symlink_to(tmp_path / 'two' / 'data.bin')
    result = record_frontier(roots, max_files=1)
    assert result['limits']['files_observed'] == 1
    assert result['status'] == 'partial'
    assert result['sources'][1]['files_truncated']


def test_compact_ready_queue_reports_omissions_and_prioritizes_changed_source(tmp_path):
    before = tmp_path / 'before'
    after = tmp_path / 'after'
    before.mkdir(); after.mkdir()
    for name in ('unchanged.bin', 'changed.bin'):
        (before / name).write_bytes(bytes(30))
        (after / name).write_bytes(bytes(30))
    (after / 'changed.bin').write_bytes(bytes(31))
    result = record_frontier([{'path': str(before), 'label': 'supplied'},
                              {'path': str(after), 'label': 'fresh'}], max_ready_tasks=1)
    assert result['ready_tasks'][0]['path'] == str(after / 'changed.bin')
    assert result['ready_tasks'][0]['change_from_previous_source'] == 'changed'
    assert result['limits']['ready_tasks_omitted'] == 2


@pytest.mark.parametrize('kwargs', [
    {'max_files': True}, {'max_candidates': 0}, {'max_total_bytes': 0},
    {'previous': {}}, {'runtime_blocker': []},
])
def test_rejects_invalid_limits_and_previous_schema(tmp_path, kwargs):
    with pytest.raises(ValueError):
        record_frontier([{'path': str(tmp_path), 'label': 'test'}], **kwargs)


def test_duplicate_labels_are_rejected_instead_of_joining_distinct_samples(tmp_path):
    with pytest.raises(ValueError, match='distinct'):
        record_frontier([{'path': str(tmp_path), 'label': 'sample'}] * 2)


def test_bounded_string_search_and_empty_data_do_not_invent_records():
    result = analyze_record_bytes(actors(), source={}, max_strings=3)
    assert result['limits']['strings_truncated'] is True
    assert result['strings_found'] == 3
    assert analyze_record_bytes(b'', source={})['name_candidates'] == []
    assert analyze_record_bytes(bytes(512), source={})['name_candidates'] == []
