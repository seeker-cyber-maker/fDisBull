"""Real X11 queue, physical-key, Pixmap and pointer adapter checks.

The four-pixel source-defined core records host service inputs. It qualifies
native adapter boundaries, independently of the separate Snake/DOS comparison.
"""
from importlib.resources import files
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import uuid

import pytest

from fdisbull.udc_memory_macos import HEADER


CONFIG = r'''
static const FdbHostKey keys[]={{"KeyN",110,49},{"ArrowUp",0,72},{"Escape",27,1}};
static const FdbHostColor colors[]={{0,0,0,0},{1,255,0,0},{2,0,255,0},{3,0,0,255},{4,85,170,34}};
static const char *const names[]={"original","alternate"};
static const char *const labels[]={"Original","Alternative"};
static const FdbHostRegion regions[]={{"update","Word update",2,0,names,labels}};
static const char *const functions[]={"advance"};
static const FdbHostConfig fdb_config={
 .words=32,.width=2,.height=2,.frame_offset=16,.tick_ms=55,
 .kind=8,.ascii=9,.scan=10,.x=11,.y=12,.buttons=13,.clock=14,.quit_index=15,
 .keyboard_kind=1,.pointer_kind=2,.clock_kind=0,
 .key_count=3,.color_count=5,.region_count=1,.function_count=1,
 .keys=keys,.colors=colors,.regions=regions,.function_names=functions,
 .title="X11 four-pixel adapter fixture",.help="Source-defined adapter check",
 .config_sha256="authored-fixture"};
'''

STUB = r'''
#include "memory-runtime.h"
#include <string.h>
#ifndef FDB_FIXTURE_MUTANT
#define FDB_FIXTURE_MUTANT 0
#endif
static uint32_t words[32];static int closed,selected;static uint64_t revision,calls;
size_t fdb_word_count(void){return 32;}const uint32_t *fdb_words(void){return words;}
int fdb_copy_words(uint32_t *out,size_t n){if(n!=32||closed)return 1;memcpy(out,words,128);return 0;}
int fdb_initialize(uint32_t clock){closed=0;memset(words,0,sizeof(words));words[6]=clock;
 words[16]=1;words[17]=2;words[18]=3;words[19]=4;revision++;return 0;}
int fdb_dispatch(const uint32_t *indices,const uint32_t *values,size_t count,int render){
 (void)render;if(closed)return 1;for(size_t i=0;i<count;i++)if(indices[i]<8||indices[i]>14){
  if(FDB_FIXTURE_MUTANT){words[0]=999;}return 1;}
 for(size_t i=0;i<count;i++)words[indices[i]-8]=values[i];
 words[7]++;if(words[1]==27)words[15]=1;revision++;calls++;return 0;}
int fdb_call(size_t fn,const uint32_t *indices,const uint32_t *values,size_t n,int render){
 if(fn){return 1;}return fdb_dispatch(indices,values,n,render);}
int fdb_function_index(const char *name){return !strcmp(name,"advance")?0:-1;}
int fdb_select_region(size_t slot,size_t value){if(slot||value>1||closed)return 1;selected=(int)value;return 0;}
int fdb_selected_region(size_t slot){return slot||closed?-1:selected;}
int fdb_replace_words(const uint32_t *in,size_t n){if(n!=32||closed)return 1;memcpy(words,in,128);revision++;return 0;}
uint64_t fdb_revision(void){return revision;}uint64_t fdb_invocation_count(size_t fn){return fn?0:calls;}
uint64_t fdb_region_invocation_count(size_t slot,size_t variant){(void)slot;(void)variant;return 0;}
uint32_t fdb_last_steps(void){return 1;}void fdb_close(void){closed=1;memset(words,0,sizeof(words));}
int fdb_closed(void){return closed;}const char *fdb_last_error(void){return "fixture refused";}
const char *fdb_config_sha256(void){return "authored-fixture";}
'''


def adapter_sources(*, mutant=False):
    resources = files('fdisbull').joinpath('native_runtime')
    result = {name: resources.joinpath(name).read_bytes() for name in
              ('memory-desktop.h', 'memory-desktop.c', 'memory-x11.c')}
    stub = ('#define FDB_FIXTURE_MUTANT 1\n' if mutant else '') + STUB
    result.update({'memory-runtime.h': HEADER.encode(), 'memory-host-config.h': CONFIG.encode(),
                   'fixture.c': stub.encode()})
    return result


def command(kind, *, a=0, b=0, c=0, d=0, clock=36297, flags=0):
    return [kind, a, b, c, d, 0, clock, flags, 0]


def encode(commands):
    result = bytearray(b'FDBEVT1\0' + struct.pack('<6I', 32, len(commands), 36297, 0, 0, 0))
    for row in commands:
        assert len(row) == 9 + row[8]
        result += struct.pack('<9I', *(v & 0xffffffff for v in row[:9]))
        if row[8]:
            result += struct.pack('<' + str(row[8]) + 'I', *row[9:])
    return bytes(result)


def decode(data):
    assert data[:8] == b'FDBOUT1\0'
    words, count, regions, functions = struct.unpack_from('<4I', data, 8)
    assert (words, regions, functions) == (32, 1, 1)
    variants, = struct.unpack_from('<I', data, 24)
    assert variants == 2
    offset = 28; result = []
    for _ in range(count):
        header = struct.unpack_from('<12I', data, offset); offset += 48
        selected, = struct.unpack_from('<i', data, offset); offset += 4
        calls, = struct.unpack_from('<Q', data, offset); offset += 8
        offset += 16  # Two per-variant counters.
        arena = list(struct.unpack_from('<32I', data, offset)); offset += 128
        row = {'kind': header[0], 'accepted': header[1], 'committed': header[2],
               'closed': header[3], 'selected': selected, 'calls': calls, 'words': arena,
               'pointer': list(header[6:9]), 'view_size': list(header[9:11])}
        if header[11] & 1:
            row['frame'] = data[offset:offset + 16]; offset += 16
        if header[11] & 2:
            size = header[9] * header[10] * 4
            row['view'] = data[offset:offset + size]; offset += size
        result.append(row)
    assert offset == len(data), 'Partial or trailing native output is not a result'
    return result


def build_adapter(tmp_path_factory, *, mutant=False):
    if sys.platform != 'linux' or not shutil.which('gcc'):
        pytest.skip('Native Linux GCC and X11 execution required')
    if not os.environ.get('DISPLAY'):
        pytest.skip('An explicitly prepared X11/Xvfb display is required')
    if not Path('/usr/include/X11/Xlib.h').is_file():
        pytest.skip('X11 development headers required')
    root = tmp_path_factory.mktemp('native-x11-adapter')
    for name, payload in adapter_sources(mutant=mutant).items():
        (root / name).write_bytes(payload)
    run = subprocess.run(['gcc', '-std=c11', '-O1', '-Wall', '-Wextra', '-Werror',
                          'memory-x11.c', 'memory-desktop.c', 'fixture.c', '-o', 'program', '-lX11'],
                         cwd=root, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr

    def execute(commands):
        identity = uuid.uuid4().hex
        source = root / (identity + '.bin'); target = root / (identity + '.out')
        source.write_bytes(encode(commands))
        run = subprocess.run([str(root / 'program'), '--adapter-test', str(source), str(target)],
                             cwd=root, capture_output=True, text=True, timeout=30)
        assert run.returncode == 0, run.stdout + run.stderr
        return decode(target.read_bytes())
    return execute


@pytest.fixture(scope='module')
def adapter(tmp_path_factory):
    return build_adapter(tmp_path_factory)


@pytest.fixture(scope='module')
def faulty_adapter(tmp_path_factory):
    return build_adapter(tmp_path_factory, mutant=True)


def test_x11_pixmap_palette_integer_and_fractional_scaling(adapter):
    rows = adapter([command(5, a=2, b=2, flags=3), command(5, a=4, b=2, flags=2),
                    command(5, a=5, b=8, flags=2)])
    red, green, blue, mixed, black = (bytes(c) for c in
        [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255),
         (85, 170, 34, 255), (0, 0, 0, 255)])
    assert rows[0]['view'] == rows[0]['frame'] == red + green + blue + mixed
    assert rows[1]['view'] == black + red + green + black + black + blue + mixed + black
    expected = b''
    for y in range(8):
        for x in range(5):
            if y < 1 or y >= 6: color = black
            else: color = [red, green, blue, mixed][((2 * (y - 1) + 1) * 2 // 10) * 2 + ((2 * x + 1) * 2 // 10)]
            expected += color
    assert rows[2]['view'] == expected


def test_x11_key_modifiers_focus_and_final_owned_frame(adapter):
    rows = adapter([command(1, a=0, c=1),
        *[command(1, a=0, b=modifier, c=1) for modifier in (1, 2, 4)],
        command(1, a=0, c=0), command(1, a=0, b=24, c=1),
        command(1, a=1, c=1), command(5, a=2, b=2), command(1, a=2, c=1, flags=3)])
    assert rows[0]['words'][:3] == [1, 110, 49]
    for row in rows[1:5]:
        assert not row['accepted'] and not row['committed']
        assert row['words'] == rows[0]['words']
    assert rows[5]['words'][:3] == [1, 110, 49] and rows[5]['words'][7] == 2
    assert rows[6]['words'][:3] == [1, 0, 72]
    assert rows[-1]['closed'] and rows[-1]['words'][15] == 1
    assert rows[-1]['frame'] == rows[-1]['view']


def test_x11_pointer_capture_buttons_focus_release_and_selector(adapter):
    rows = adapter([command(5, a=4, b=2), command(2, a=1, c=0, d=0),
        command(2, a=1, c=1, d=0), command(2, a=3, c=100, d=-10),
        command(2, a=2, c=100, d=-10), command(2, a=1, b=1, c=2, d=1),
        command(2, a=1, b=2, c=2, d=1), command(2, a=2, b=1, c=2, d=1),
        command(7, a=0), command(4, a=0, b=1)])
    assert not rows[1]['accepted'] and rows[1]['words'][7] == 0
    assert rows[2]['words'][3:6] == [0, 0, 1]
    assert rows[3]['words'][3:6] == [1, 0, 1]
    assert rows[4]['words'][3:6] == [1, 0, 0]
    assert rows[5]['words'][3:6] == [1, 1, 2]
    assert rows[6]['words'][3:6] == [1, 1, 6]
    assert rows[7]['words'][3:6] == [1, 1, 4]
    assert rows[8]['words'][3:6] == [1, 1, 0]
    assert rows[9]['selected'] == 1 and rows[9]['words'] == rows[8]['words']


def test_x11_timer_after_pointer_events(adapter):
    rows = adapter([command(7, a=0), command(2, a=1, c=0, d=0),
                    command(2, a=2, c=0, d=0), command(1, a=0, c=1),
                    command(3, clock=65535)])
    assert rows[3]['words'][:3] == [1, 110, 49]
    assert rows[4]['words'][0] == 0 and rows[4]['words'][6] == 65535


def test_x11_fractional_pointer_picks_displayed_source_pixel(adapter):
    rows = adapter([command(5, a=5, b=8, flags=2), command(2, a=1, c=2, d=3)])
    # Source 2x2 is fitted into [0,1,5,5]. Destination pixel(2,3) has its
    # center over source pixel(1,1), the mixed bottom-right palette entry.
    assert rows[0]['view'][(3 * 5 + 2) * 4:(3 * 5 + 2) * 4 + 4] == bytes((85, 170, 34, 255))
    assert rows[1]['words'][3:6] == [1, 1, 1]


def test_x11_refusal_observer_exposes_mutant_core_state(faulty_adapter):
    refused = command(10, a=0, b=0, flags=4)
    refused[8] = 2
    refused.extend((31, 1))  # Deliberately invalid core input patch.
    rows = faulty_adapter([command(0), refused, command(0)])
    assert rows[0]['words'][0] == 0
    assert not rows[1]['committed']
    # This deliberately faulty core changes a word before reporting refusal.
    # Reading the old display cache would conceal the broken rollback rule.
    assert rows[1]['words'][0] == rows[2]['words'][0] == 999
    assert rows[1]['words'] != rows[0]['words']
