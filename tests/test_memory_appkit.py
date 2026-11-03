"""Native responder/palette adapter tests with a source-defined boundary stub.

The stub records host inputs; it does not substitute for game/UIL qualification.
Stored-state drawRect capture uses a controlled native context, not a screen.
"""
from importlib.resources import files
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'darwin' or not shutil.which('xcrun'),
                                reason='Native AppKit and Apple compiler required')

HEADER = '''#include <stddef.h>
#include <stdint.h>
int fdb_dispatch(const uint32_t*,const uint32_t*,size_t,int);
int fdb_initialize(uint32_t); const uint32_t *fdb_words(void);
size_t fdb_word_count(void); int fdb_select_region(size_t,size_t);
int fdb_selected_region(size_t); uint64_t fdb_revision(void);
int fdb_replace_words(const uint32_t*,size_t);
void fdb_close(void); int fdb_closed(void);
const char *fdb_last_error(void); const char *fdb_config_sha256(void);
'''
STUB = '''#include "memory-runtime.h"
#include <string.h>
static uint32_t words[32]; static int closed,selected; static uint64_t revision;
const uint32_t *fdb_words(void){return words;} size_t fdb_word_count(void){return 32;}
int fdb_initialize(uint32_t clock){closed=0;memset(words,0,sizeof(words));words[6]=clock;
words[16]=1;words[17]=2;words[18]=3;words[19]=4;revision++;return 0;}
int fdb_dispatch(const uint32_t *indices,const uint32_t *values,size_t count,int render){
(void)render;if(closed)return 1;for(size_t i=0;i<count;i++){
if(indices[i]<8||indices[i]>14)return 1;words[indices[i]-8]=values[i];}
words[7]++;if(words[1]==27)words[15]=1;revision++;return 0;}
int fdb_select_region(size_t slot,size_t value){if(slot||value>1||closed)return 1;
selected=(int)value;return 0;} int fdb_selected_region(size_t slot){return slot?-1:selected;}
uint64_t fdb_revision(void){return revision;}
int fdb_replace_words(const uint32_t *values,size_t count){if(count!=32||closed)return 1;
memcpy(words,values,128);revision++;return 0;}
void fdb_close(void){closed=1;memset(words,0,sizeof(words));}
int fdb_closed(void){return closed;} const char *fdb_last_error(void){return "refused";}
'''


def config():
    return {'plan': {'title': 'Native four-pixel fixture', 'help': 'Generic adapter test',
        'frame': {'width': 2, 'height': 2, 'offset': 16,
                  'palette': {'0': [0, 0, 0], '1': [255, 0, 0], '2': [0, 255, 0],
                              '3': [0, 0, 255], '4': [85, 170, 34]}},
        'events': {'kind': 8, 'ascii': 9, 'scan': 10, 'x': 11, 'y': 12, 'buttons': 13,
                   'clock': 14, 'quit_index': 15, 'keyboard_kind': 1,
                   'pointer_kind': 2, 'clock_kind': 0, 'tick_ms': 55},
        'keymap': {'KeyN': {'ascii': 110, 'scan': 49},
                   'ArrowUp': {'ascii': 0, 'scan': 72},
                   'Escape': {'ascii': 27, 'scan': 1}}},
        'region_controls': [{'name': 'update', 'label': 'Word update', 'default_index': 0,
                             'variants': [{'name': 'original', 'label': 'Original'},
                                          {'name': 'alternate', 'label': 'Alternative'}]}]}


@pytest.fixture(scope='module')
def adapter(tmp_path_factory):
    root = tmp_path_factory.mktemp('native-adapter')
    encoded = json.dumps(config()).encode()
    (root / 'config.json').write_bytes(encoded)
    (root / 'memory-runtime.h').write_text(HEADER)
    (root / 'stub.c').write_text(STUB + 'const char *fdb_config_sha256(void){return "' +
                               hashlib.sha256(encoded).hexdigest() + '";}\n')
    source = Path(str(files('fdisbull').joinpath('native_runtime/memory-appkit.m')))
    command = ['xcrun', 'clang', '-fobjc-arc', '-Wall', '-Wextra', '-Werror', '-I', str(root),
               str(source), str(root / 'stub.c'), '-framework', 'AppKit', '-o', str(root / 'adapter')]
    run = subprocess.run(command, text=True, capture_output=True, timeout=45)
    assert run.returncode == 0, run.stdout + run.stderr
    return root


def replay(adapter, tmp_path, commands, *, initial_pointer=None):
    script = {'format': 'fdisbull-native-adapter-study-1', 'initial_clock': 36297,
              'commands': commands}
    if initial_pointer is not None:
        script['initial_pointer'] = initial_pointer
    (tmp_path / 'script.json').write_text(json.dumps(script))
    output = tmp_path / 'result.json'
    run = subprocess.run([str(adapter / 'adapter'), str(adapter / 'config.json'), '--adapter-test',
                          str(tmp_path / 'script.json'), str(output)], text=True,
                         capture_output=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(output.read_text())
    assert result['status'] == 'passed', result
    return result['rows']


def test_actual_drawrect_matches_palette_and_letterbox(adapter, tmp_path):
    rows = replay(adapter, tmp_path, [
        {'kind': 'resize', 'width': 2, 'height': 2, 'capture_view': True, 'capture_frame': True},
        {'kind': 'resize', 'width': 4, 'height': 2, 'capture_view': True},
        {'kind': 'resize', 'width': 2, 'height': 4, 'capture_view': True},
        {'kind': 'resize', 'width': 4, 'height': 4, 'capture_view': True},
    ])
    red, green, blue, mixed, black = (bytes(color) for color in
        [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255),
         (85, 170, 34, 255), (0, 0, 0, 255)])
    intrinsic = red + green + blue + mixed
    assert base64.b64decode(rows[0]['frame_rgba_base64']) == intrinsic
    assert base64.b64decode(rows[0]['view_rgba_base64']) == intrinsic
    assert base64.b64decode(rows[1]['view_rgba_base64']) == black + red + green + black + black + blue + mixed + black
    assert base64.b64decode(rows[2]['view_rgba_base64']) == black * 2 + intrinsic + black * 2
    assert base64.b64decode(rows[3]['view_rgba_base64']) == red * 2 + green * 2 + red * 2 + green * 2 + blue * 2 + mixed * 2 + blue * 2 + mixed * 2


def test_fractional_image_edges_do_not_blend_palette_with_letterbox(adapter, tmp_path):
    row = replay(adapter, tmp_path, [
        {'kind': 'resize', 'width': 5, 'height': 8, 'capture_view': True},
    ])[0]
    assert row['game_rect'] == [0, 1.5, 5, 5]
    data = base64.b64decode(row['view_rgba_base64'])
    pixels = {tuple(data[i:i + 4]) for i in range(0, len(data), 4)}
    # An exact pixel-center tie can select either adjacent source cell. It may
    # not create a new color by blending the image edge with its letterbox.
    palette = {(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255),
               (85, 170, 34, 255), (0, 0, 0, 255)}
    assert pixels == palette


def test_physical_key_mapping_modifiers_focus_and_preclose_snapshot(adapter, tmp_path):
    rows = replay(adapter, tmp_path, [
        {'kind': 'key', 'code': 'KeyN'},
        *[{'kind': 'key', 'code': 'KeyN', 'modifiers': [modifier]}
          for modifier in ['command', 'control', 'option']],
        {'kind': 'key', 'code': 'KeyN', 'focus': 'window'},
        {'kind': 'key', 'code': 'KeyN', 'modifiers': ['shift', 'caps']},
        {'kind': 'key', 'code': 'ArrowUp'},
        {'kind': 'key', 'key_code': 65535},
        {'kind': 'key', 'code': 'Escape', 'capture_frame': True},
    ])
    assert rows[0]['words'][:3] == [1, 110, 49]
    assert rows[0]['words'][6] == 36297
    for row in rows[1:5]:
        assert not row['accepted'] and not row['committed']
        assert row['words'] == rows[0]['words']
    assert rows[5]['words'][:3] == [1, 110, 49] and rows[5]['words'][7] == 2
    assert rows[6]['words'][:3] == [1, 0, 72]
    assert not rows[7]['accepted'] and rows[7]['words'] == rows[6]['words']
    assert rows[8]['closed'] and rows[8]['words'][15] == 1
    assert rows[8]['words'][16:20] == [1, 2, 3, 4]


def test_pointer_boundaries_buttons_release_and_selector(adapter, tmp_path):
    rows = replay(adapter, tmp_path, [
        {'kind': 'resize', 'width': 4, 'height': 2},
        {'kind': 'pointer', 'phase': 'down', 'space': 'view', 'x': 0.5, 'y': 0.5},
        {'kind': 'pointer', 'phase': 'down', 'x': 0, 'y': 0},
        {'kind': 'pointer', 'phase': 'drag', 'space': 'view', 'x': 100, 'y': -10},
        {'kind': 'pointer', 'phase': 'up', 'space': 'view', 'x': 100, 'y': -10},
        {'kind': 'pointer', 'phase': 'down', 'button': 1, 'x': 1, 'y': 1},
        {'kind': 'pointer', 'phase': 'down', 'button': 2, 'x': 1, 'y': 1},
        {'kind': 'pointer', 'phase': 'up', 'button': 1, 'x': 1, 'y': 1},
        {'kind': 'focus-loss'},
        {'kind': 'select', 'slot': 0, 'variant': 1},
    ])
    assert not rows[1]['accepted'] and rows[1]['words'][7] == 0
    assert rows[2]['words'][3:6] == [0, 0, 1]
    assert rows[3]['words'][3:6] == [1, 0, 1]
    assert rows[4]['words'][3:6] == [1, 0, 0]
    assert rows[5]['words'][3:6] == [1, 1, 2]
    assert rows[6]['words'][3:6] == [1, 1, 6]
    assert rows[7]['words'][3:6] == [1, 1, 4]
    assert rows[8]['words'][3:6] == [1, 1, 0]
    assert rows[9]['selected'] == [1] and rows[9]['words'] == rows[8]['words']


def test_stored_state_export_and_config_identity(adapter, tmp_path):
    image = tmp_path / 'frame.png'
    run = subprocess.run([str(adapter / 'adapter'), str(adapter / 'config.json'),
                          '--export-frame', str(image)], text=True, capture_output=True, timeout=20)
    assert run.returncode == 0, run.stdout + run.stderr
    assert image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    changed = tmp_path / 'changed.json'
    changed.write_text(json.dumps(config(), indent=2))
    run = subprocess.run([str(adapter / 'adapter'), str(changed), '--export-frame',
                          str(tmp_path / 'refused.png')], text=True, capture_output=True, timeout=20)
    assert run.returncode == 2 and 'config identity differs' in run.stderr
    assert not (tmp_path / 'refused.png').exists()


def test_diagnostic_pointer_initialization_and_timer_path(adapter, tmp_path):
    rows = replay(adapter, tmp_path, [
        {'kind': 'snapshot'},
        {'kind': 'focus-loss'},
        {'kind': 'clock', 'clock': 65535},
    ], initial_pointer={'x': 1, 'y': 0, 'buttons': 1})
    assert rows[0]['pointer'] == {'x': 1, 'y': 0, 'buttons': 1}
    assert rows[1]['pointer'] == {'x': 1, 'y': 0, 'buttons': 0}
    assert rows[1]['words'][3:6] == [1, 0, 0]
    assert rows[2]['accepted'] and rows[2]['committed']
    assert rows[2]['words'][0] == 0 and rows[2]['words'][6] == 65535


def test_prefix_replacement_retains_actual_nonspecified_arena(adapter, tmp_path):
    rows = replay(adapter, tmp_path, [
        {'kind': 'key', 'code': 'KeyN'},
        {'kind': 'snapshot', 'capture_frame': True},
        {'kind': 'replace', 'prefix_words': [7, 8]},
        {'kind': 'snapshot', 'capture_frame': True},
    ])
    assert rows[3]['words'][:2] == [7, 8]
    assert rows[3]['words'][2:] == rows[1]['words'][2:]
    assert rows[3]['frame_rgba_base64'] == rows[1]['frame_rgba_base64']
