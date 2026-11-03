"""Authored point-domain boundary audits; no game resources or native proof."""
import pytest

from fdisbull.scene_boundaries import audit_rectangle_boundary


def audit(rectangle=(105, 96, 145, 166), **kwargs):
    options = dict(width=160, height=168, convention='inclusive')
    options.update(kwargs)
    return audit_rectangle_boundary(rectangle, **options)


def test_inclusive_rectangle_derives_one_pixel_terminal_band_and_projected_witness():
    result = audit(start=(130, 136))
    assert result['complete'] is True
    assert result['status'] == 'static_candidates_only'
    assert result['rectangle']['half_open'] == [105, 96, 146, 167]
    assert result['complement_count'] == 160*168 - 41*71
    assert result['examined'] == 41
    band, = result['bands']
    assert (band['edge'], band['direction'], band['thickness'], band['count']) == ('bottom', 'down', 1, 41)
    assert band['row_runs'] == [[167, 105, 146]]
    assert band['complete'] is True
    assert band['witness'] == {'inside': [130, 166], 'outside': [130, 167], 'selection': 'start_projection'}
    assert band['reachability'] == {'status': 'unknown'}
    assert band['kind'] == 'terminal-domain-edge-complement-band'
    assert result['component_analysis'] == 'not_performed'
    # The large complement joins other outside areas. The reported 41 origins
    # are an edge transition band, not a claim of an isolated 2-D component.
    assert result['complement_count'] > band['count']


def test_half_open_and_inclusive_conventions_have_identical_bands():
    assert audit(convention='inclusive')['bands'] == audit((105, 96, 146, 167), convention='half-open')['bands']


def test_grid_height_and_rectangle_end_determine_candidate_without_preset_row():
    assert audit(height=167)['bands'] == []
    assert audit((105, 96, 145, 167))['bands'] == []
    assert audit(height=169)['bands'] == []
    band, = audit(height=169, max_band_width=2)['bands']
    assert band['thickness'] == 2 and band['count'] == 82
    assert band['row_runs'] == [[167, 105, 146], [168, 105, 146]]
    assert band['witness']['inside'][1] == 166 and band['witness']['outside'][1] == 167


@pytest.mark.parametrize('direction,edge,runs,inside,outside', [
    ('up', 'top', [[0, 1, 4]], [2, 1], [2, 0]),
    ('down', 'bottom', [[4, 1, 4]], [2, 3], [2, 4]),
    ('left', 'left', [[1, 0, 1], [2, 0, 1], [3, 0, 1]], [1, 2], [0, 2]),
    ('right', 'right', [[1, 4, 5], [2, 4, 5], [3, 4, 5]], [3, 2], [4, 2]),
])
def test_four_directions_report_adjacent_origin_witnesses(direction, edge, runs, inside, outside):
    result = audit((1, 1, 3, 3), width=5, height=5, directions=(direction,), start=(2, 2))
    band, = result['bands']
    assert band['edge'] == edge and band['row_runs'] == runs and band['count'] == 3
    assert band['witness']['inside'] == inside and band['witness']['outside'] == outside
    assert sum(abs(a-b) for a, b in zip(inside, outside)) == 1


def test_start_selects_witness_without_claiming_path_reachability():
    band, = audit(start=(0, 136))['bands']
    assert band['witness'] == {'inside': [105, 166], 'outside': [105, 167], 'selection': 'clamped_start_projection'}
    assert band['reachability']['status'] == 'unknown'
    default, = audit()['bands']
    assert default['witness']['inside'][0] == 125


def test_supplied_reachability_mask_is_counted_separately_from_geometry():
    mask = bytearray(160*168)
    mask[167*160+130] = 255
    result = audit(start=(130, 136), reachable_mask=bytes(mask))
    band, = result['bands']
    assert band['count'] == 41 and band['row_runs'] == [[167, 105, 146]]
    assert band['reachability']['status'] == 'present_in_supplied_mask'
    assert band['reachability']['count'] == 1
    assert band['reachability']['outside_witness_in_mask'] is True
    assert band['reachability']['inside_witness_in_mask'] is False
    assert band['reachability']['native_validation'] == 'not_established'
    absent, = audit(reachable_mask=bytes(160*168))['bands']
    assert absent['reachability']['status'] == 'absent_from_supplied_mask'
    assert absent['count'] == 41


@pytest.mark.parametrize('rectangle,convention', [
    ((0, 0, 159, 167), 'inclusive'),
    ((0, 0, 160, 168), 'half-open'),
    ((-10, -10, 300, 300), 'inclusive'),
])
def test_empty_complement_is_valid(rectangle, convention):
    result = audit(rectangle, convention=convention)
    assert result['complete'] is True and result['bands'] == []
    assert result['complement_count'] == 0


@pytest.mark.parametrize('rectangle', [(0, 0, 0, 5), (0, 3, 6, 3), (-10, -10, -1, -1)])
def test_empty_clipped_inside_region_does_not_invent_adjacent_witness(rectangle):
    result = audit(rectangle, convention='half-open')
    assert result['complete'] is True and result['bands'] == []
    assert result['complement_count'] == 160*168


def test_cell_budget_preserves_partial_rle_and_never_claims_complete():
    result = audit(max_checks=3)
    assert result['complete'] is False and result['examined'] == 3
    band, = result['bands']
    assert band['complete'] is False and band['count'] == 3
    assert band['row_runs'] == [[167, 105, 108]]
    assert band['reachability']['status'] == 'unknown'


def test_run_budget_preserves_prior_rows_and_never_claims_complete():
    result = audit((1, 1, 3, 3), width=5, height=5, directions=('right',), max_runs=1)
    assert result['complete'] is False
    band, = result['bands']
    assert band['row_runs'] == [[1, 4, 5]] and band['count'] == 1
    assert band['complete'] is False


def test_global_cell_budget_and_declared_direction_order():
    result = audit((1, 1, 3, 3), width=5, height=5, directions=('up', 'down'), max_checks=4)
    assert [b['direction'] for b in result['bands']] == ['up', 'down']
    assert [b['count'] for b in result['bands']] == [3, 1]
    assert result['complete'] is False and result['examined'] == 4


def test_partial_empty_supplied_mask_is_unknown_not_absent():
    result = audit(max_checks=1, reachable_mask=bytes(160*168))
    band, = result['bands']
    assert result['complete'] is False and band['complete'] is False
    assert band['reachability']['status'] == 'unknown'
    assert band['reachability']['count'] == 0


def test_single_column_domain_and_clipped_outside_coordinates():
    band, = audit((-5, -5, 5, 1), width=1, height=3)['bands']
    assert band['row_runs'] == [[2, 0, 1]] and band['count'] == 1
    assert band['witness']['inside'] == [0, 1] and band['witness']['outside'] == [0, 2]


def test_largest_admitted_mask_domain_has_a_valid_empty_complement():
    result = audit((0, 0, 1024, 1024), width=1024, height=1024, convention='half-open')
    assert result['complete'] is True and result['complement_count'] == 0
    assert result['bands'] == []


def test_terminal_runs_match_independently_evaluated_one_step_boundary_flips():
    width, height = 7, 6
    rectangles = [(1, 1, 5, 4), (0, 1, 5, 5), (1, 0, 6, 4), (-3, -3, 5, 4)]
    moves = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}
    for rectangle in rectangles:
        x0, y0, x1, y1 = rectangle
        inside = lambda x, y: x0 <= x <= x1 and y0 <= y <= y1
        for direction, (dx, dy) in moves.items():
            expected = set()
            for y in range(height):
                for x in range(width):
                    if (dx == -1 and x != 0 or dx == 1 and x != width-1
                            or dy == -1 and y != 0 or dy == 1 and y != height-1):
                        continue
                    if not inside(x, y) and inside(x-dx, y-dy):
                        expected.add((x, y))
            result = audit(rectangle, width=width, height=height, directions=(direction,))
            actual = {(x, y) for b in result['bands'] for y, left, right in b['row_runs']
                      for x in range(left, right)}
            assert actual == expected and result['complete'] is True


@pytest.mark.parametrize('kwargs', [
    {'width': True}, {'width': 0}, {'height': 0}, {'width': 4096, 'height': 4096},
    {'convention': 'unspecified'}, {'directions': 'down'}, {'directions': ()},
    {'directions': ('down', 'down')}, {'directions': ('diagonal',)},
    {'start': (160, 1)}, {'start': (True, 1)},
    {'reachable_mask': b'\0'}, {'reachable_mask': bytearray(160*168)},
    {'max_checks': 0}, {'max_checks': True}, {'max_runs': 0}, {'max_band_width': 0},
])
def test_invalid_or_unbounded_inputs_are_refused(kwargs):
    with pytest.raises(ValueError): audit(**kwargs)


@pytest.mark.parametrize('rectangle', [(3, 0, 2, 5), (0, 3, 2, 2), (0, 1, 2), (False, 0, 2, 4)])
def test_malformed_rectangles_are_refused(rectangle):
    with pytest.raises(ValueError): audit(rectangle)
