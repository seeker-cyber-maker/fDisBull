"""Real Win32 responder and GDI boundary tests using an authored core fixture.

These checks qualify host adapters; the independent Snake/DOS corpus qualifies
recovered game behavior separately. A local offline guest can be selected with
FDISBULL_DESKTOP_VM_CLIENT; otherwise these tests need a native Windows compiler.
"""
from importlib.resources import files
import importlib.util
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import uuid

import pytest

from fdisbull.udc_memory_macos import HEADER

VM = os.environ.get('FDISBULL_DESKTOP_VM_CLIENT')
CC = os.environ.get('FDISBULL_WIN64_CC') or shutil.which('gcc') or shutil.which('clang')
pytestmark = pytest.mark.skipif(not VM and not (sys.platform == 'win32' and CC),
                                reason='requires Win32 APIs and a Windows C compiler or an explicit offline guest')

CONFIG = '''static const FdbHostKey unit_keys[]={{"KeyN",110,49},{"ArrowUp",0,72},{"Escape",27,1}};
static const FdbHostColor unit_colors[]={{0,0,0,0},{1,255,0,0},{2,0,255,0},{3,0,0,255},{4,85,170,34}};
static const char *unit_names[]={"original","alternate"};
static const char *unit_labels[]={"Original","Alternative"};
static const FdbHostRegion unit_regions[]={{"update","Word update",2,0,unit_names,unit_labels}};
static const char *unit_functions[]={"event"};
static const FdbHostConfig fdb_config={.words=32,.width=2,.height=2,.frame_offset=16,.tick_ms=55,
.kind=8,.ascii=9,.scan=10,.x=11,.y=12,.buttons=13,.clock=14,.quit_index=15,
.keyboard_kind=1,.pointer_kind=2,.clock_kind=0,.key_count=3,.color_count=5,.region_count=1,
.keys=unit_keys,.colors=unit_colors,.regions=unit_regions,.title="Four pixel native fixture",
.help="Generic native adapter test",.config_sha256="authored-unit-contract",
.function_count=1,.function_names=unit_functions};
'''
STUB = '''#include "memory-runtime.h"
#include <string.h>
static uint32_t words[32];static int closed,selected;static uint64_t revision;
size_t fdb_word_count(void){return 32;}const uint32_t *fdb_words(void){return words;}
int fdb_copy_words(uint32_t*out,size_t n){if(closed||n!=32)return 1;memcpy(out,words,128);return 0;}
int fdb_initialize(uint32_t clock){closed=0;memset(words,0,128);words[6]=clock;
words[16]=1;words[17]=2;words[18]=3;words[19]=4;revision++;return 0;}
int fdb_dispatch(const uint32_t*i,const uint32_t*v,size_t n,int render){(void)render;if(closed)return 1;
for(size_t j=0;j<n;j++){if(i[j]<8||i[j]>14)return 1;words[i[j]-8]=v[j];}
words[7]++;if(words[1]==27)words[15]=1;revision++;return 0;}
int fdb_call(size_t f,const uint32_t*i,const uint32_t*v,size_t n,int r){if(f)return 1;return fdb_dispatch(i,v,n,r);}
int fdb_function_index(const char*s){return strcmp(s,"event")?-1:0;}
int fdb_select_region(size_t slot,size_t value){if(slot||value>1||closed)return 1;selected=(int)value;return 0;}
int fdb_selected_region(size_t slot){return slot||closed?-1:selected;}
uint64_t fdb_revision(void){return revision;}
uint64_t fdb_invocation_count(size_t f){(void)f;return 0;}
uint64_t fdb_region_invocation_count(size_t s,size_t v){(void)s;(void)v;return 0;}
uint32_t fdb_last_steps(void){return 0;}
int fdb_replace_words(const uint32_t*w,size_t n){if(n!=32||closed)return 1;memmove(words,w,128);revision++;return 0;}
void fdb_close(void){closed=1;memset(words,0,128);}int fdb_closed(void){return closed;}
const char *fdb_last_error(void){return "authored fixture refusal";}
const char *fdb_config_sha256(void){return "authored-unit-contract";}
'''


def command(kind, a=0, b=0, c=0, d=0, *, flags=0, clock=36297, payload=()):
    fields = (kind, a, b, c, d, 0, clock, flags, len(payload))
    return struct.pack('<9I', *(value & 0xffffffff for value in fields)) + struct.pack(
        '<' + 'I' * len(payload), *payload)


def decode(data):
    assert data[:8] == b'FDBOUT1\0'
    words, count, regions, functions = struct.unpack_from('<4I', data, 8)
    assert words == 32 and regions == 1 and functions == 1
    at = 24
    variant_counts = struct.unpack_from('<' + 'I' * regions, data, at)
    at += 4 * regions
    rows = []
    for _ in range(count):
        head = struct.unpack_from('<12I', data, at)
        at += 48
        selected = struct.unpack_from('<' + 'i' * regions, data, at)
        at += 4 * regions
        at += 8 * (functions + sum(variant_counts))
        arena = list(struct.unpack_from('<' + 'I' * words, data, at))
        at += words * 4
        row = {'kind': head[0], 'accepted': bool(head[1]), 'committed': bool(head[2]),
               'closed': bool(head[3]), 'pointer': list(head[6:9]),
               'size': list(head[9:11]), 'selected': list(selected), 'words': arena}
        if head[11] & 1:
            row['frame'] = data[at:at + 16]
            at += 16
        if head[11] & 2:
            size = head[9] * head[10] * 4
            row['view'] = data[at:at + size]
            at += size
        rows.append(row)
    assert at == len(data), 'a partial or trailing observation is not a result'
    return rows


class Adapter:
    def __init__(self, directory):
        self.directory = directory
        self.client = None
        if VM:
            spec = importlib.util.spec_from_file_location('fdb_unit_win32_guest', VM)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.client = module.Client()
        self.job = 'win32-unit-' + uuid.uuid4().hex[:12]
        source = {'memory-runtime.h': HEADER.encode(),
                  'memory-host-config.h': CONFIG.encode(), 'stub.c': STUB.encode()}
        for name in ('memory-desktop.h', 'memory-desktop.c', 'memory-win32.c'):
            source[name] = files('fdisbull').joinpath('native_runtime/' + name).read_bytes()
        for name, data in source.items():
            (directory / name).write_bytes(data)
            if self.client:
                self.client.put(self.job, name, data)
        arguments = ['-std=c11', '-O1', '-Wall', '-Wextra', '-Werror', '-mwindows', 'memory-win32.c',
                     'memory-desktop.c', 'stub.c', '-o', 'adapter.exe', '-luser32', '-lgdi32']
        if self.client:
            built = self.client.run(self.job, ['x86_64-w64-mingw32-gcc', *arguments], timeout=180)
            assert built['exit_code'] == 0, built['stdout'] + built['stderr']
            image = self.client.get(self.job, 'adapter.exe')
        else:
            built = subprocess.run([CC, *arguments], cwd=directory, capture_output=True,
                                   text=True, timeout=180)
            assert built.returncode == 0, built.stdout + built.stderr
            image = (directory / 'adapter.exe').read_bytes()
        pe = struct.unpack_from('<I', image, 0x3c)[0]
        assert image[pe:pe + 4] == b'PE\0\0'
        assert struct.unpack_from('<H', image, pe + 4)[0] == 0x8664
        assert struct.unpack_from('<H', image, pe + 24)[0] == 0x20b
        assert struct.unpack_from('<H', image, pe + 24 + 68)[0] == 2, 'native GUI subsystem required'

    def replay(self, commands, *, initial_pointer=(0, 0, 0), success=True):
        case = uuid.uuid4().hex[:12]
        script = b'FDBEVT1\0' + struct.pack('<6I', 32, len(commands), 36297, *initial_pointer) + b''.join(commands)
        if self.client:
            self.client.put(self.job, case + '.bin', script)
            ran = self.client.run(self.job, ['wine', 'adapter.exe', '--adapter-test',
                                            case + '.bin', case + '.out'], timeout=120)
            code = ran['exit_code']
            assert (code == 0) == success, ran
            if not success:
                return ran
            data = self.client.get(self.job, case + '.out')
        else:
            (self.directory / (case + '.bin')).write_bytes(script)
            ran = subprocess.run([str(self.directory / 'adapter.exe'), '--adapter-test',
                                  case + '.bin', case + '.out'], cwd=self.directory,
                                 capture_output=True, text=True, timeout=120)
            assert (ran.returncode == 0) == success, ran.stdout + ran.stderr
            if not success:
                return ran
            data = (self.directory / (case + '.out')).read_bytes()
        return decode(data)


@pytest.fixture(scope='module')
def adapter(tmp_path_factory):
    return Adapter(tmp_path_factory.mktemp('win32-adapter'))


def test_real_gdi_palette_origin_letterbox_and_fractional_fit(adapter):
    rows = adapter.replay([command(5, a=w, b=h, flags=3) for w, h in
                           [(2, 2), (4, 2), (2, 4), (4, 4), (5, 8)]])
    red, green, blue, mixed, black = map(bytes, [(255, 0, 0, 255), (0, 255, 0, 255),
                                               (0, 0, 255, 255), (85, 170, 34, 255),
                                               (0, 0, 0, 255)])
    intrinsic = red + green + blue + mixed
    assert all(row['frame'] == intrinsic for row in rows)
    assert rows[0]['view'] == intrinsic
    assert rows[1]['view'] == black + red + green + black + black + blue + mixed + black
    assert rows[2]['view'] == black * 2 + intrinsic + black * 2
    assert rows[3]['view'] == red * 2 + green * 2 + red * 2 + green * 2 + blue * 2 + mixed * 2 + blue * 2 + mixed * 2
    assert rows[4]['view'] == black * 5 + (red * 2 + green * 3) * 2 + (blue * 2 + mixed * 3) * 3 + black * 10


def test_real_wndproc_physical_keys_modifiers_focus_and_terminal_snapshot(adapter):
    rows = adapter.replay([
        command(1, a=0, c=1),
        *[command(1, a=0, b=modifier, c=1) for modifier in (1, 2, 4)],
        command(1, a=0, c=0), command(1, a=0, b=24, c=1),
        command(1, a=1, c=1), command(1, a=2, c=1, flags=1), command(0, flags=1),
    ])
    assert rows[0]['words'][:3] == [1, 110, 49]
    assert rows[0]['words'][6] == 36297
    for row in rows[1:5]:
        assert not row['accepted'] and not row['committed']
        assert row['words'] == rows[0]['words']
    assert rows[5]['words'][:3] == [1, 110, 49] and rows[5]['words'][7] == 2
    assert rows[6]['words'][:3] == [1, 0, 72] and rows[6]['words'][7] == 3
    assert rows[7]['closed'] and rows[7]['words'][15] == 1
    assert rows[7]['words'][16:20] == [1, 2, 3, 4]
    assert rows[8]['closed'] and rows[8]['words'] == rows[7]['words']
    assert rows[8]['frame'] == rows[7]['frame']


def test_real_pointer_capture_buttons_focus_release_and_native_selector(adapter):
    rows = adapter.replay([
        command(5, a=4, b=2),
        command(2, a=1, c=0, d=0),  # letterbox press
        command(2, a=1, c=1, d=0), command(2, a=3, c=100, d=-10),
        command(2, a=2, c=100, d=-10),
        command(2, a=1, b=1, c=2, d=1), command(2, a=1, b=2, c=2, d=1),
        command(2, a=2, b=1, c=2, d=1), command(7, a=0),
        command(4, a=0, b=1),
    ])
    assert not rows[1]['accepted'] and rows[1]['words'][7] == 0
    assert rows[2]['words'][3:6] == [0, 0, 1]
    assert rows[3]['words'][3:6] == [1, 0, 1]
    assert rows[4]['words'][3:6] == [1, 0, 0]
    assert rows[5]['words'][3:6] == [1, 1, 2]
    assert rows[6]['words'][3:6] == [1, 1, 6]
    assert rows[7]['words'][3:6] == [1, 1, 4]
    assert rows[8]['words'][3:6] == [1, 1, 0] and rows[8]['committed']
    assert rows[9]['selected'] == [1] and rows[9]['accepted']
    assert rows[9]['words'] == rows[8]['words']


def test_native_timer_and_prefix_replacement_retain_frame(adapter):
    rows = adapter.replay([
        command(0, flags=1), command(3, clock=65535),
        command(6, payload=(7, 8)), command(0, flags=1),
    ])
    assert rows[1]['words'][0] == 0 and rows[1]['words'][6] == 65535
    assert rows[1]['accepted'] and rows[1]['committed']
    assert rows[3]['words'][:2] == [7, 8]
    assert rows[3]['frame'] == rows[0]['frame']


def test_native_coordinate_carrier_refuses_overflow_instead_of_wrapping(adapter):
    adapter.replay([command(2, a=1, c=32768)], success=False)


LIFECYCLE = r'''#define main fdb_adapter_main
#include "memory-win32.c"
#undef main
int main(int argc,char **argv) {
    if(argc!=2)return 2;
    FdbWin app;memset(&app,0,sizeof(app));app.config=fdb_host_config();app.diagnostic=1;
    app.selectors=(HWND*)calloc(app.config->region_count?app.config->region_count:1u,sizeof(HWND));
    if(!app.selectors)return 3;
    SetProcessDPIAware();
    if(fdb_host_open(&app.host,36297u) || fdb_win_create(&app))return 4;
    uint32_t result[24]={0};
    result[0]=(uint32_t)app.host.view_width;result[1]=(uint32_t)app.host.view_height;
    RECT original;if(!GetWindowRect(app.window,&original))return 5;
    ShowWindow(app.window,SW_MINIMIZE);
    SendMessageW(app.window,WM_SIZE,SIZE_MINIMIZED,0);
    result[2]=(uint32_t)IsIconic(app.window);
    result[3]=(uint32_t)app.host.view_width;result[4]=(uint32_t)app.host.view_height;
    result[5]=(uint32_t)app.failed;
    ShowWindow(app.window,SW_RESTORE);
    SendMessageW(app.window,WM_SIZE,SIZE_RESTORED,0);
    result[6]=(uint32_t)app.host.view_width;result[7]=(uint32_t)app.host.view_height;
    result[8]=(uint32_t)app.failed;
    MINMAXINFO info;memset(&info,0,sizeof(info));
    info.ptMaxSize.x=info.ptMaxSize.y=50000;
    info.ptMaxTrackSize.x=info.ptMaxTrackSize.y=50000;
    SendMessageW(app.window,WM_GETMINMAXINFO,0,(LPARAM)&info);
    result[9]=(uint32_t)info.ptMaxTrackSize.x;result[10]=(uint32_t)info.ptMaxTrackSize.y;
    result[11]=(uint32_t)info.ptMaxSize.x;result[12]=(uint32_t)info.ptMaxSize.y;
    result[13]=(uint32_t)info.ptMinTrackSize.x;result[14]=(uint32_t)info.ptMinTrackSize.y;
    int controls_height=app.config->region_count?102:70;
    RECT admitted={0,0,4096+32,4096+controls_height+16};
    if(!AdjustWindowRectEx(&admitted,(DWORD)GetWindowLongPtrW(app.window,GWL_STYLE),
                          GetMenu(app.window)!=NULL,(DWORD)GetWindowLongPtrW(app.window,GWL_EXSTYLE)))return 6;
    result[15]=(uint32_t)(admitted.right-admitted.left);
    result[16]=(uint32_t)(admitted.bottom-admitted.top);
    if(result[9]<=result[15] && result[10]<=result[16]) {
        /* The size-policy probe does not need a large GDI backing allocation. */
        ShowWindow(app.view,SW_HIDE);
        if(!SetWindowPos(app.window,NULL,0,0,(int)result[9],(int)result[10],SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE))return 7;
        RECT child;if(!GetClientRect(app.view,&child))return 8;
        result[17]=(uint32_t)child.right;result[18]=(uint32_t)child.bottom;
        /* Programmatic native resizes also preserve the admitted arena bound. */
        if(!SetWindowPos(app.window,NULL,0,0,(int)result[9]+100,(int)result[10]+100,SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE))return 9;
        if(!GetClientRect(app.view,&child))return 10;
        result[19]=(uint32_t)child.right;result[20]=(uint32_t)child.bottom;
        result[21]=(uint32_t)app.failed;
        if(!SetWindowPos(app.window,NULL,0,0,original.right-original.left,original.bottom-original.top,
                         SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE))return 11;
        result[22]=(uint32_t)app.host.view_width;result[23]=(uint32_t)app.host.view_height;
    }
    FILE *out=fopen(argv[1],"wb");if(!out)return 12;
    int failed=fwrite(result,sizeof(result),1,out)!=1;
    if(fclose(out))failed=1;
    DestroyWindow(app.window);fdb_win_surface_dispose(&app.surface);
    fdb_host_destroy(&app.host);free(app.selectors);
    return failed?13:0;
}
'''


@pytest.fixture(scope='module')
def lifecycle(adapter):
    source = LIFECYCLE.encode()
    (adapter.directory / 'lifecycle.c').write_bytes(source)
    arguments = ['-std=c11', '-O1', '-Wall', '-Wextra', '-Werror', '-mwindows',
                 'lifecycle.c', 'memory-desktop.c', 'stub.c', '-o', 'lifecycle.exe',
                 '-luser32', '-lgdi32']
    if adapter.client:
        adapter.client.put(adapter.job, 'lifecycle.c', source)
        built = adapter.client.run(adapter.job, ['x86_64-w64-mingw32-gcc', *arguments], timeout=180)
        assert built['exit_code'] == 0, built['stdout'] + built['stderr']
        ran = adapter.client.run(adapter.job, ['wine', 'lifecycle.exe', 'lifecycle.out'], timeout=120)
        assert ran['exit_code'] == 0, ran
        data = adapter.client.get(adapter.job, 'lifecycle.out')
    else:
        built = subprocess.run([CC, *arguments], cwd=adapter.directory, capture_output=True,
                               text=True, timeout=180)
        assert built.returncode == 0, built.stdout + built.stderr
        ran = subprocess.run([str(adapter.directory / 'lifecycle.exe'), 'lifecycle.out'],
                             cwd=adapter.directory, capture_output=True, text=True, timeout=120)
        assert ran.returncode == 0, ran.stdout + ran.stderr
        data = (adapter.directory / 'lifecycle.out').read_bytes()
    assert len(data) == 24 * 4
    return struct.unpack('<24I', data)


def test_minimize_and_restore_preserve_the_last_valid_native_viewport(lifecycle):
    assert lifecycle[2] == 1, 'the native window must actually be minimized'
    assert lifecycle[0:2] == lifecycle[3:5] == lifecycle[6:8]
    assert lifecycle[5] == lifecycle[8] == 0
    assert lifecycle[22:24] == lifecycle[0:2]


def test_tracking_maximize_and_programmatic_resize_preserve_native_view_budget(lifecycle):
    max_track = lifecycle[9:11]
    assert max_track == lifecycle[15:17], 'nonclient bounds must follow the actual native style'
    assert lifecycle[11] <= max_track[0] and lifecycle[12] <= max_track[1]
    assert lifecycle[13:15] == (420, 350)
    assert lifecycle[17:19] == (4096, 4096)
    assert lifecycle[19:21] == (4096, 4096)
    assert lifecycle[21] == 0
