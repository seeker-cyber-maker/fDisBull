"""Compare private fDisBull packets and export a narrow, sanitized result.

Reads only; never opens an app, invokes fDisBull, changes defaults or writes
inside either input directory. Input screenshots and AX trees stay private.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

from PIL import Image

COORDINATES = 'CoreGraphics-global-logical-top-left'
EXPECTED_TITLES = ['Start at Login', 'Update Interval', 'View Mode', 'Theme',
                   'Show cores individually', 'Open Activity Monitor', 'Quit']
FILES = ('before.json', 'after-open.json', 'capture.json', 'receipt.json', 'capture.png')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rectangle(value):
    require(isinstance(value, dict) and set(value) == {'x', 'y', 'width', 'height'}, 'invalid rectangle')
    require(all(type(v) in (int, float) and math.isfinite(v) for v in value.values()), 'non-finite rectangle')
    require(value['width'] > 0 and value['height'] > 0, 'empty rectangle')
    return value


def contains(outer, inner):
    return (outer['x'] <= inner['x'] and outer['y'] <= inner['y'] and
            inner['x'] + inner['width'] <= outer['x'] + outer['width'] and
            inner['y'] + inner['height'] <= outer['y'] + outer['height'])


def normalized(frame, origin):
    return {key: frame[key] - origin[key] if key in ('x', 'y') else frame[key]
            for key in ('x', 'y', 'width', 'height')}


def _json(path):
    with path.open('rb') as stream:
        raw = stream.read(512 * 1024 + 1)
    require(len(raw) <= 512 * 1024, 'packet JSON exceeds its budget')
    return json.loads(raw)


def _colored(red, green, blue):
    # Bounded Default-theme discriminator. It intentionally excludes neutral
    # menu-bar backgrounds, white labels and the blue selected-item backdrop.
    return ((green > 100 and red < 140 and blue < 110) or
            (red > 150 and green < 190 and blue < 100))


def profile(folder, expected_cores):
    before = _json(folder / 'before.json')
    opened = _json(folder / 'after-open.json')
    capture = _json(folder / 'capture.json')
    receipt = _json(folder / 'receipt.json')
    require(receipt.get('format') == 'fdisbull-macos-session-1', 'not a fDisBull session receipt')
    require(receipt.get('status') == 'confirmed' and receipt.get('cleanup', {}).get('status') == 'confirmed',
            'session cleanup is not confirmed')
    require(any(item.get('status') == 'restored_closed' for item in receipt['cleanup'].get('outcomes', [])),
            'test-opened menu was not reported restored')
    require(before.get('menu', {}).get('open') is False and opened.get('menu', {}).get('open') is True,
            'expected a closed to open menu observation')
    identity = ('bundle_id', 'running', 'pid', 'launch_date')
    require(all(before['target'].get(key) == opened['target'].get(key) == receipt['identity'].get(key)
                for key in identity), 'target identity changed inside a session')
    require(capture.get('coordinate_system') == COORDINATES and opened.get('coordinate_system') == COORDINATES,
            'coordinate system mismatch')
    display = capture['display']
    bounds, global_rect, local_rect = map(rectangle,
        (display['global_bounds'], capture['global_rect'], capture['display_local_rect']))
    require(contains(bounds, global_rect), 'capture crosses display bounds')
    require(local_rect == normalized(global_rect, bounds), 'global/local display conversion mismatch')
    require(contains({'x': 0, 'y': 0, 'width': bounds['width'], 'height': bounds['height']}, local_rect),
            'display-local crop is outside the selected display')
    matches = [item for item in opened['displays'] if item['id'] == display['id']]
    require(len(matches) == 1 and matches[0]['uuid'] == display['uuid'] and
            matches[0]['global_bounds'] == bounds, 'display identity changed between AX and capture')
    sx, sy = capture['scale_x'], capture['scale_y']
    require(all(type(v) in (int, float) and math.isfinite(v) and 0 < v <= 8 for v in (sx, sy)), 'invalid scale')
    require(abs(display['pixel_width'] / bounds['width'] - sx) < 0.000001 and
            abs(display['pixel_height'] / bounds['height'] - sy) < 0.000001, 'display backing scale mismatch')
    with Image.open(folder / 'capture.png') as original:
        require(original.format == 'PNG', 'capture is not PNG')
        require(original.width * original.height <= 64 * 1024 * 1024, 'image exceeds pixel budget')
        require(original.size == (capture['pixel_width'], capture['pixel_height']) ==
                (round(global_rect['width'] * sx), round(global_rect['height'] * sy)), 'PNG/metadata dimensions disagree')
        image = original.convert('RGB')
    require(opened['ax'].get('truncated') is False, 'AX coverage is truncated')
    nodes = opened['ax']['nodes']
    visible = [node for node in nodes if node.get('role') == 'AXMenu' and
               node.get('global_frame', {}).get('width', 0) > 0 and
               node.get('global_frame', {}).get('height', 0) > 0]
    require(len(visible) == 1, 'expected one actually rendered root menu')
    root_menu = visible[0]
    menu_rect = rectangle(root_menu['global_frame'])
    require(contains(global_rect, menu_rect), 'image does not cover the visible menu')
    children = [node for node in nodes if node.get('parent') == root_menu['index'] and node.get('role') == 'AXMenuItem']
    rows = []
    for child in children:
        frame = rectangle(child['global_frame'])
        require(contains(menu_rect, frame), 'visible row falls outside its root menu')
        if child.get('title'):
            require(type(child.get('enabled')) is bool, 'row enabled state is unknown')
            rows.append({'title': child['title'], 'enabled': child['enabled'], 'frame': normalized(frame, menu_rect)})
    require([row['title'] for row in rows] == EXPECTED_TITLES, 'visible English menu coverage differs')
    require(len(rows) == 7 and rows[2]['enabled'] is False, 'expected seven rows and disabled View Mode')
    status_index = opened['menu']['status_index']
    statuses = [item for item in opened['status_items'] if item['index'] == status_index]
    prior = [item for item in before['status_items'] if item['index'] == status_index]
    require(len(statuses) == 1 and len(prior) == 1, 'status item selection is ambiguous')
    status = rectangle(statuses[0]['global_frame'])
    require(status == prior[0]['global_frame'], 'opening moved the status item')
    require(contains(global_rect, status), 'capture does not cover the status item')
    x0, y0 = round((status['x'] - global_rect['x']) * sx), round((status['y'] - global_rect['y']) * sy)
    cropped = image.crop((x0, y0, x0 + round(status['width'] * sx), y0 + round(status['height'] * sy)))
    columns = {}
    for y in range(cropped.height):
        for x in range(cropped.width):
            if _colored(*cropped.getpixel((x, y))):
                columns.setdefault(x, []).append(y)
    groups = []
    for x in sorted(columns):
        if groups and x == groups[-1][-1] + 1:
            groups[-1].append(x)
        else:
            groups.append([x])
    widths = [len(group) for group in groups]
    gaps = [groups[i + 1][0] - groups[i][-1] - 1 for i in range(len(groups) - 1)]
    bottoms = [max(y for x in group for y in columns[x]) for group in groups]
    require(len(groups) == expected_cores, 'colored core-bar count differs')
    require(all(width == round(3 * sx) for width in widths), 'colored bars are not 3 logical points wide')
    require(all(gap == round(2 * sx) for gap in gaps), 'bar gaps are not 2 logical points')
    require(len(set(bottoms)) == 1 and bottoms[0] == round(20 * sy) - 1, 'bar baseline differs')
    hidden_inventory = [node['title'] for node in nodes if node.get('role') == 'AXMenuItem' and node.get('title') and
                        node.get('global_frame', {}).get('width') == 0]
    return {
        'packet_sha256': {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in FILES},
        'capture': {'pixel_size': list(image.size), 'scale': [sx, sy], 'display_identity_matches_packet': True,
                    'global_local_conversion_valid': True, 'capture_within_display': True,
                    'negative_display_origin_observed': bounds['x'] < 0 or bounds['y'] < 0},
        'menu': {'size': [menu_rect['width'], menu_rect['height']], 'rows': rows,
                 'separator_count': len(children) - len(rows), 'hidden_ax_label_inventory': hidden_inventory},
        'status': {'size': [status['width'], status['height']], 'position_unchanged_after_open': True,
                   'bar_count': len(groups), 'bar_widths_pixels': widths, 'gaps_pixels': gaps,
                   'bar_bottoms_relative_to_status_pixels': bottoms,
                   'bar_starts_relative_to_status_pixels': [group[0] for group in groups]},
        'cleanup_confirmed_by_tool_receipt': True,
    }


def differences(original, replica):
    problems = []
    if original['menu']['size'] != replica['menu']['size']:
        problems.append('menu_size')
    if original['menu']['rows'] != replica['menu']['rows']:
        problems.append('visible_menu_rows')
    if original['menu']['separator_count'] != replica['menu']['separator_count']:
        problems.append('separator_count')
    for key in ('size', 'bar_count', 'bar_widths_pixels', 'gaps_pixels',
                'bar_bottoms_relative_to_status_pixels', 'bar_starts_relative_to_status_pixels'):
        if original['status'][key] != replica['status'][key]:
            problems.append('status.' + key)
    return problems


def compare(original_directory, replica_directory, *, expected_cores=10):
    original, replica = profile(original_directory, expected_cores), profile(replica_directory, expected_cores)
    mismatches = differences(original, replica)
    mutant = copy.deepcopy(replica)
    mutant['menu']['rows'][0]['title'] = 'Deliberately wrong menu label'
    require('visible_menu_rows' in differences(original, mutant), 'wrong-label falsifier was not detected')
    return {
        'format': 'cpuinfo-fdisbull-capture-comparison-1',
        'status': 'matched_observed_subset' if not mismatches else 'mismatch',
        'tool_source_commit': 'ecbe4c577bcd57d7224a5594a8475dda4c412d10',
        'capture_method': 'fDisBull reversible native macOS session and ScreenCaptureKit',
        'original': original, 'replica': replica, 'differences': mismatches,
        'falsifier': {'wrong_visible_menu_label': 'detected'},
        'coverage': {'visible_english_root_rows': 7, 'expected_default_core_bars': expected_cores,
                     'normalized_menu_geometry_and_enabled_states': not mismatches,
                     'separate_display_coordinate_validation': True,
                     'hidden_submenu_labels': 'AX inventory only; not rendered or interacted with'},
        'claim_ceiling': 'source-assisted candidate matched the observed default English menu and bar geometry only',
        'unqualified': ['font identity', 'full pixel equivalence', 'dynamic CPU-counter equivalence',
                        'login registration/checkmark parity', 'localization', 'restart persistence',
                        'hidden submenu rendering and action outcomes'],
        'privacy': {'input_paths_exported': False, 'pids_or_display_uuids_exported': False,
                    'screenshots_or_raw_ax_trees_exported': False, 'ui_or_preferences_changed_by_comparator': False},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', required=True, type=Path, help='Private original session directory')
    parser.add_argument('--replica', required=True, type=Path, help='Private replica session directory')
    parser.add_argument('--output', required=True, type=Path, help='New sanitized JSON result')
    parser.add_argument('--expected-cores', type=int, default=10)
    args = parser.parse_args()
    require(1 <= args.expected_cores <= 1024, 'invalid expected core count')
    result = compare(args.original, args.replica, expected_cores=args.expected_cores)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'visible_rows': 7,
                      'core_bars': args.expected_cores, 'falsifier': result['falsifier']}))
    return 0 if result['status'] == 'matched_observed_subset' else 1


if __name__ == '__main__':
    raise SystemExit(main())
