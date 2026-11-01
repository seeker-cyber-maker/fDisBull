"""Authored collision candidates, without original resources or native execution."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

import examples.agi.scan_collision_candidates as module


def picture(rows):
    return bytes(value for row in rows for value in row)


def resource(code):
    return len(code).to_bytes(2, 'little') + code


def position(rectangle=(2, 1, 4, 3), obj=0):
    return bytes((11, obj, *rectangle))


def branch(conditions, body=b'\x0c\x00'):
    return b'\xff' + conditions + b'\xff' + len(body).to_bytes(2, 'little') + body


def small_baseline(row, **kwargs):
    return module.baseline_passability(bytes(row), 0, 0,
                                      image_width=6, image_height=1, **kwargs)


@pytest.mark.parametrize('row,passable,all_water,mixed_water', [
    ([4] * 6, True, False, False),
    ([3] * 6, False, True, False),
    ([3, 3, 3, 3, 3, 4], True, False, True),
    ([4, 3, 3, 3, 3, 3], True, False, True),
    ([3, 3, 0, 3, 3, 4], False, False, True),
    ([4, 4, 4, 4, 4, 2], False, False, False),
])
def test_baseline_uses_the_complete_six_pixel_footprint(row, passable, all_water, mixed_water):
    result = small_baseline(row)

    assert result['passable'] is passable
    assert result['all_water'] is all_water
    assert result['mixed_water'] is mixed_water
    assert bool(result['blocked_by']) is not passable


def test_priority_one_requires_an_explicit_policy():
    row = [3, 3, 1, 3, 3, 4]

    assert small_baseline(row)['passable'] is False
    allowed = small_baseline(row, allow_priority_one=True)

    assert allowed['passable'] is True
    assert allowed['conditional_one'] is True
    assert small_baseline([0, 1, 4, 4, 4, 4], allow_priority_one=True)['passable'] is False


@pytest.mark.parametrize('plane,x,y,kwargs', [
    (bytes([4] * 6), -1, 0, {}),
    (bytes([4] * 6), 1, 0, {}),
    (bytes([4] * 6), 0, 1, {}),
    (bytes([4] * 5), 0, 0, {}),
    (bytes([16] * 6), 0, 0, {}),
    (bytes([4] * 6), 0, 0, {'width': 0}),
    (bytes([4] * 6), 0, 0, {'width': 7}),
    (bytes([4] * 6), 0, 0, {'image_width': 0}),
    (bytes([4] * 6), True, 0, {}),
])
def test_invalid_baseline_inputs_are_rejected(plane, x, y, kwargs):
    options = {'image_width': 6, 'image_height': 1, **kwargs}
    with pytest.raises(ValueError):
        module.baseline_passability(plane, x, y, **options)


def test_single_position_guard_retains_source_identity_and_code_offsets():
    instruction = branch(position())
    payload = resource(instruction + b'\x00')

    guards = module.extract_water_guards(payload, logic_number=39)

    assert len(guards) == 1
    guard = guards[0]
    assert guard['if_offset'] == 0
    assert guard['body_offset'] == 10
    assert guard['rectangles'] == [[2, 1, 4, 3]]
    assert guard['source_sha256'] == sha256(payload).hexdigest()
    assert guard['if_sha256'] == sha256(instruction[:10]).hexdigest()
    assert guard['lexical_parent_if_offsets'] == []
    assert guard['parent_condition_caveat']


def test_or_guard_is_kept_under_its_unevaluated_parent_condition():
    first, second = (2, 1, 4, 3), (6, 5, 6, 7)
    inner = branch(b'\xfc' + position(first) + position(second) + b'\xfc')
    # NOT isset(63) is a lexical parent, not an evaluated runtime premise.
    payload = resource(branch(b'\xfd\x07\x3f', inner) + b'\x00')

    guards = module.extract_water_guards(payload)

    assert len(guards) == 1
    guard = guards[0]
    assert guard['if_offset'] == 7
    assert guard['body_offset'] == 25
    assert guard['rectangles'] == [list(first), list(second)]
    assert guard['lexical_parent_if_offsets'] == [0]
    assert guard['parent_condition_caveat']


@pytest.mark.parametrize('conditions,body', [
    (b'\xfd' + position(), b'\x0c\x00'),
    (position() + position((5, 1, 6, 3)), b'\x0c\x00'),
    (position(obj=1), b'\x0c\x00'),
    (b'\x07\x00', b'\x0c\x00'),
    (position(), b'\x0c\x01'),
    (position(), b'\x03\x0c\x00\x0c\x00'),
    (position(), b'\x0d\x00\x0c\x00'),
])
def test_guard_extraction_refuses_other_conditions_or_non_immediate_water_writes(conditions, body):
    assert module.extract_water_guards(resource(branch(conditions, body) + b'\x00')) == []


def test_zero_length_true_body_does_not_claim_a_following_unconditional_writer():
    code = b'\xff' + position() + b'\xff\x00\x00\x0c\x00\x00'

    assert module.extract_water_guards(resource(code)) == []


def test_position_shaped_action_operands_are_not_guards():
    code = bytes.fromhex('510b000a0b140c0000')

    assert module.extract_water_guards(resource(code)) == []


@pytest.mark.parametrize('payload', [
    b'',
    resource(b'\xff\x0b\x00\x01'),
    resource(b'\xff' + position() + b'\xff\x01\x00\x0c\x00\x00'),
])
def test_malformed_or_non_boundary_layouts_fail_closed(payload):
    with pytest.raises(ValueError):
        module.extract_water_guards(payload)


def test_guard_rectangle_limit_refuses_an_oversized_but_valid_or_group():
    conditions = b'\xfc' + position() * 257 + b'\xfc'
    payload = resource(branch(conditions) + b'\x00')

    with pytest.raises(ValueError, match='budget'):
        module.extract_water_guards(payload)


@pytest.mark.parametrize('rows,edge,origin,inner', [
    ([[4] * 7, [4, 3, 3, 3, 3, 3, 3], [4] * 7], 'left', (0, 1), (1, 1)),
    ([[4] * 7, [3, 3, 3, 3, 3, 3, 4], [4] * 7], 'right', (1, 1), (0, 1)),
    ([[3, 3, 3, 3, 3, 4, 4], [3] * 7, [4] * 7], 'top', (0, 0), (0, 1)),
    ([[4] * 7, [3] * 7, [3, 3, 3, 3, 3, 4, 4]], 'bottom', (0, 2), (0, 1)),
])
def test_edge_seams_require_mixed_edge_and_all_water_inner_baselines(rows, edge, origin, inner):
    result = module.edge_water_seams(picture(rows), image_width=7, image_height=3)

    assert result['complete'] is True
    assert any(item['edge'] == edge
               and (item['x'], item['y']) == origin
               and (item['inner_x'], item['inner_y']) == inner
               for item in result['candidates'])


def test_dry_bottom_baseline_adjacent_to_all_water_is_a_static_seam():
    result = module.edge_water_seams(picture([[4] * 8, [3] * 8, [15] * 8]),
                                     image_width=8, image_height=3, width=6)

    bottom = [item for item in result['candidates'] if item['edge'] == 'bottom']
    assert result['complete'] is True
    assert [(item['x'], item['y'], item['inner_x'], item['inner_y'], item['status'])
            for item in bottom] == [(x, 2, x, 1, 'static_edge_seam') for x in range(3)]


def test_dry_bottom_with_priority_one_obeys_explicit_policy():
    rows = [[3] * 6, [15, 15, 1, 15, 15, 15]]
    blocked = module.edge_water_seams(picture(rows), image_width=6, image_height=2)
    admitted = module.edge_water_seams(picture(rows), image_width=6, image_height=2,
                                       allow_priority_one=True)
    assert not any(item['edge'] == 'bottom' for item in blocked['candidates'])
    assert any(item['edge'] == 'bottom' for item in admitted['candidates'])


@pytest.mark.parametrize('blocked_pixel', [0, 2])
def test_dry_bottom_with_unconditional_control_pixel_stays_blocked(blocked_pixel):
    rows = [[3] * 6, [15, 15, blocked_pixel, 15, 15, 15]]
    result = module.edge_water_seams(picture(rows), image_width=6, image_height=2,
                                     allow_priority_one=True)
    assert not any(item['edge'] == 'bottom' for item in result['candidates'])


def test_dry_bottom_candidate_cap_reports_partial_without_overflow():
    rows = [[3] * 8, [15] * 8]
    result = module.edge_water_seams(picture(rows), image_width=8, image_height=2,
                                     width=6, max_candidates=1)
    assert len(result['candidates']) == 1
    assert result['complete'] is False
    assert result['examined'] == 10


def test_dry_bottom_candidate_cap_exactly_fitting_is_complete():
    result = module.edge_water_seams(picture([[3] * 8, [15] * 8]),
                                     image_width=8, image_height=2,
                                     width=6, max_candidates=3)
    assert len(result['candidates']) == 3
    assert result['complete'] is True
    assert result['examined'] == 10


@pytest.mark.parametrize('edge_value', [0, 1, 2])
def test_blocked_or_conditional_edge_pixels_are_not_water_seams(edge_value):
    rows = [[4] * 7, [3, 3, 3, 3, 3, 3, edge_value], [4] * 7]
    result = module.edge_water_seams(picture(rows), image_width=7, image_height=3)

    assert not any(item['edge'] == 'right' and item['y'] == 1
                   for item in result['candidates'])


def test_edge_candidate_limit_retains_an_incomplete_status():
    rows = [[3, 3, 3, 3, 3, 3, 4]] * 3
    result = module.edge_water_seams(picture(rows), image_width=7, image_height=3,
                                     max_candidates=1)

    assert len(result['candidates']) == 1
    assert result['complete'] is False
    assert result['examined'] > 1


def test_geometry_guard_overlap_is_reported_without_claiming_a_runtime_glitch():
    plane = picture([[4] * 7 for _ in range(3)])
    guards = [{'if_offset': 12, 'rectangles': [[0, 0, 1, 2]],
               'parent_condition_caveat': 'Not evaluated'}]

    result = module.hazard_overlaps(plane, guards, image_width=7, image_height=3,
                                     max_samples=2)

    assert result['complete'] is True
    assert len(result['overlaps']) == 1
    overlap = result['overlaps'][0]
    assert overlap['if_offset'] == 12
    assert overlap['rectangle'] == [0, 0, 1, 2]
    assert overlap['geometry_passable_count'] == 6
    assert len(overlap['sample_origins']) == 2


def test_hazard_overlap_budget_is_not_reported_as_a_complete_scan():
    guards = [{'if_offset': 12, 'rectangles': [[0, 0, 1, 2]],
               'parent_condition_caveat': 'Not evaluated'}]

    result = module.hazard_overlaps(bytes([4] * 21), guards,
                                     image_width=7, image_height=3, max_checks=1)

    assert result['examined'] <= 1
    assert result['complete'] is False


def test_overlap_rectangle_limit_is_enforced_before_partial_scanning():
    guards = [{'if_offset': 12, 'rectangles': [[0, 0, 0, 0]] * 257,
               'parent_condition_caveat': 'Not evaluated'}]

    with pytest.raises(ValueError, match='budget'):
        module.hazard_overlaps(bytes([4] * 6), guards,
                               image_width=6, image_height=1, max_checks=1)


@pytest.mark.parametrize('diagonals,expected_points', [(False, 5), (True, 3)])
def test_bfs_returns_unit_steps_for_the_declared_neighborhood(diagonals, expected_points):
    result = module.bounded_path(bytes([4] * 9), (0, 0), (2, 2),
                                 image_width=3, image_height=3, width=1,
                                 diagonals=diagonals)

    assert result['status'] == 'found'
    assert result['complete'] is True
    path = result['path']
    assert tuple(path[0]) == (0, 0)
    assert tuple(path[-1]) == (2, 2)
    assert len(path) == expected_points
    for start, end in zip(path, path[1:]):
        dx, dy = abs(start[0] - end[0]), abs(start[1] - end[1])
        assert max(dx, dy) == 1
        assert diagonals or dx + dy == 1


def test_optional_script_hazards_apply_to_inclusive_baseline_origins():
    plane = bytes([4] * 9)
    options = {'image_width': 3, 'image_height': 3, 'width': 1}

    open_route = module.bounded_path(plane, (0, 1), (2, 1), **options)
    closed_route = module.bounded_path(plane, (0, 1), (2, 1),
                                       hazards=[(1, 0, 1, 2)], **options)

    assert open_route['status'] == 'found'
    assert closed_route['status'] == 'unreachable'
    assert closed_route['complete'] is True
    assert closed_route['path'] == []


def test_bfs_diagonal_policy_checks_destinations_without_swept_corner_assumptions():
    plane = picture([[4, 0], [0, 4]])
    options = {'image_width': 2, 'image_height': 2, 'width': 1}

    assert module.bounded_path(plane, (0, 0), (1, 1), **options)['status'] == 'unreachable'
    assert module.bounded_path(plane, (0, 0), (1, 1), diagonals=True,
                               **options)['status'] == 'found'


@pytest.mark.parametrize('row,options', [
    ([4, 3], {}),
    ([4, 1], {}),
    ([4, 4], {'hazards': [(1, 0, 1, 0)]}),
])
def test_bfs_refuses_blocked_endpoints(row, options):
    result = module.bounded_path(bytes(row), (0, 0), (1, 0),
                                 image_width=2, image_height=1, width=1, **options)

    assert result['status'] == 'blocked_endpoint'
    assert result['path'] == []


@pytest.mark.parametrize('options,status', [
    ({'max_nodes': 1}, 'node_budget'),
    ({'max_steps': 1}, 'step_budget'),
])
def test_bfs_budget_stops_remain_incomplete(options, status):
    result = module.bounded_path(bytes([4] * 5), (0, 0), (4, 0),
                                 image_width=5, image_height=1, width=1, **options)

    assert result['status'] == status
    assert result['complete'] is False
    assert result['path'] == []
    if 'max_nodes' in options:
        assert result['visited'] <= options['max_nodes']


def test_an_already_reached_goal_needs_no_search_steps():
    result = module.bounded_path(bytes([4]), (0, 0), (0, 0),
                                 image_width=1, image_height=1, width=1,
                                 max_nodes=1, max_steps=1)

    assert result['status'] == 'found'
    assert [tuple(point) for point in result['path']] == [(0, 0)]


def test_cli_refuses_to_overwrite_a_receipt_before_source_analysis(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    output = tmp_path / 'receipt.json'
    output.write_text('preserved receipt')

    with pytest.raises((ValueError, FileExistsError)):
        module.main(['--source', str(source), '--output', str(output)])

    assert output.read_text() == 'preserved receipt'


def test_cli_refuses_output_inside_owner_source(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    output = source / 'receipt.json'

    with pytest.raises(ValueError):
        module.main(['--source', str(source), '--output', str(output)])

    assert not output.exists()


def test_cli_rejects_an_output_parent_symlink_into_owner_source(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    alias = tmp_path / 'innocent-output-name'
    alias.symlink_to(source, target_is_directory=True)
    output = alias / 'receipt.json'

    with pytest.raises(ValueError):
        module.main(['--source', str(source), '--output', str(output)])

    assert not (source / 'receipt.json').exists()


def test_cli_rejects_oversized_resource_directories_before_emitting_a_receipt(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'PICDIR').write_bytes(b'\x00\x00\x00')
    (source / 'LOGDIR').write_bytes(bytes(769))
    output = tmp_path / 'receipt.json'

    with pytest.raises(ValueError):
        module.main(['--source', str(source), '--rooms', '0', '--output', str(output)])

    assert not output.exists()


def test_cli_refuses_output_inside_the_checkout(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    output = Path(module.__file__).resolve().parents[2] / 'collision-receipt-test.json'
    assert not output.exists()

    with pytest.raises(ValueError):
        module.main(['--source', str(source), '--output', str(output)])

    assert not output.exists()


def test_cli_scans_only_selected_authored_resources_and_writes_one_fresh_receipt(tmp_path):
    source = tmp_path / 'owner-input'
    source.mkdir()
    logic = resource(b'\x00')
    pic = b'\xff'  # A valid empty picture retains the default dry priority plane.

    def record(payload):
        return b'\x12\x34\x00' + len(payload).to_bytes(2, 'little') + payload

    logic_record = record(logic)
    # Room 1 points outside VOL.0, so analyzing it would fail. It is unselected.
    dormant_invalid_entry = bytes.fromhex('00fffe')
    logdir = b'\x00\x00\x00' + dormant_invalid_entry
    picdir = len(logic_record).to_bytes(3, 'big') + dormant_invalid_entry
    (source / 'LOGDIR').write_bytes(logdir)
    (source / 'PICDIR').write_bytes(picdir)
    (source / 'VOL.0').write_bytes(logic_record + record(pic))
    output = tmp_path / 'private-results' / 'receipt.json'
    args = ['--source', str(source), '--rooms', '0', '--width', '6',
            '--output', str(output), '--path', '0:0,0:2,2', '--neighbors', '8']

    assert module.main(args) == 0
    original_receipt = output.read_bytes()
    receipt = json.loads(original_receipt)

    assert receipt['status'] == 'static_candidates_only'
    assert receipt['native_validation'] == 'not_run'
    assert receipt['selected_rooms'] == [0]
    assert receipt['complete'] is True
    assert receipt['directory_sha256'] == {
        'LOGDIR': sha256(logdir).hexdigest(), 'PICDIR': sha256(picdir).hexdigest()}
    assert len(receipt['rooms']) == 1
    room = receipt['rooms'][0]
    assert room['room'] == 0
    assert room['picture_sha256'] == sha256(pic).hexdigest()
    assert room['logic_sha256'] == sha256(logic).hexdigest()
    assert room['water_flag_guards'] == []
    assert room['edge_seams']['segments'] == []
    assert room['edge_seams']['retained_candidate_count'] == 0
    assert room['paths'][0]['result']['status'] == 'found'
    assert len(room['paths'][0]['result']['path']) == 3

    def all_keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from all_keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from all_keys(child)

    assert not set(all_keys(receipt)) & {
        'payload', 'code', 'visual', 'priority', 'messages', 'bytes', 'plane', 'raw'}
    with pytest.raises((ValueError, FileExistsError)):
        module.main(args)
    assert output.read_bytes() == original_receipt
