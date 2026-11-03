"""Real NE/Win16 GDI and message adapters with an authored four-pixel core.

Set FDISBULL_WIN16_VM_CLIENT to an explicit offline guest's Python client.  The
client must expose Client.put/get/run and genuine OpenWatcom wcl + a Win16 Wine
runtime.  These tests never classify a host C shim as native Win16 execution.
The core is an authored adapter fixture, not recovered Snake/DOS behavior.
"""
from importlib.resources import files
import importlib.util
import math
import os
from pathlib import Path
import struct
import uuid

import pytest

from fdisbull.udc_memory_win16 import WIN16_MEMORY_HEADER


VM = os.environ.get('FDISBULL_WIN16_VM_CLIENT')
native = pytest.mark.skipif(not VM, reason='requires an explicit genuine Win16 compiler/runtime guest')

FIXTURE = r'''#include "M16HOST.H"
static const Fdb16Key keys[]={{"KeyN",110UL,49UL},{"ArrowUp",0UL,72UL},{"Escape",27UL,1UL}};
static const Fdb16Color colors[]={{0UL,0,0,0},{1UL,255,0,0},{2UL,0,255,0},{3UL,0,0,255},{4UL,85,170,34}};
static const char *names[]={"original","alternate"};
static const char *labels[]={"Original","Alternative"};
static const Fdb16Region regions[]={{"update","Word update",2,0,names,labels}};
static const char *functions[]={"event"};
static const Fdb16Config config={32UL,16UL,2,2,55,
8UL,9UL,10UL,11UL,12UL,13UL,14UL,15UL,1UL,2UL,0UL,
3,5,1,1,keys,colors,regions,functions,
"Four pixel native fixture","Generic native adapter test","authored-unit-contract",0UL};
static Fdb16Arena *words;
static int selected,closed;
static Fdb16Count revision,calls,variants[2];
static void increment(Fdb16Count *v){v->low++;if(!v->low)v->high++;}
const Fdb16Config *fdb16_config(void){return &config;}
int fdb16_core_open(const char *file){(void)file;words=fdb16_create(32UL);closed=0;selected=0;return !words;}
const Fdb16Arena *fdb16_core_words(void){return closed?NULL:words;}
int fdb16_core_initialize(FdbU32 clock){Fdb16Arena *next;if(closed)return 1;
next=fdb16_create(32UL);if(!next)return 1;fdb16_release(words);words=next;
fdb16_write(words,6UL,clock);fdb16_write(words,16UL,1UL);fdb16_write(words,17UL,2UL);
fdb16_write(words,18UL,3UL);fdb16_write(words,19UL,4UL);increment(&revision);return 0;}
int fdb16_core_dispatch(FdbU32 kind,FdbU32 ascii,FdbU32 scan,FdbU32 x,FdbU32 y,FdbU32 buttons,FdbU32 clock){
FdbU32 count;if(closed)return 1;fdb16_write(words,0UL,kind);fdb16_write(words,1UL,ascii);
fdb16_write(words,2UL,scan);fdb16_write(words,3UL,x);fdb16_write(words,4UL,y);
fdb16_write(words,5UL,buttons);fdb16_write(words,6UL,clock);
fdb16_read(words,7UL,&count);fdb16_write(words,7UL,count+1UL);
if(ascii==27UL)fdb16_write(words,15UL,1UL);increment(&revision);increment(&calls);
increment(&variants[selected]);return 0;}
int fdb16_core_call(FdbU16 f,const Fdb16Arena *p,FdbU32 count,int render){
(void)f;(void)p;(void)count;(void)render;return 1;}
int fdb16_core_replace(const Fdb16Arena *next){if(closed || fdb16_word_count(next)!=32UL)return 1;
if(fdb16_copy(words,next))return 1;increment(&revision);return 0;}
int fdb16_core_select(FdbU16 slot,FdbU16 value){if(closed || slot || value>1)return 1;selected=value;return 0;}
int fdb16_core_selected(FdbU16 slot){return closed || slot?-1:selected;}
Fdb16Count fdb16_core_revision(void){return revision;}
Fdb16Count fdb16_core_calls(FdbU16 f){(void)f;return calls;}
Fdb16Count fdb16_core_region_calls(FdbU16 s,FdbU16 v){Fdb16Count zero={0UL,0UL};return s || v>1?zero:variants[v];}
const char *fdb16_core_error(void){return "authored fixture refusal";}
void fdb16_core_close(void){if(!closed){fdb16_release(words);words=NULL;}closed=1;}
'''


def command(kind, a=0, b=0, c=0, d=0, *, flags=0, clock=36297, payload=()):
    fields = (kind, a, b, c, d, 0, clock, flags, len(payload))
    return struct.pack('<9I', *(v & 0xffffffff for v in fields)) + struct.pack(
        '<' + 'I' * len(payload), *payload)


def decode(data):
    assert data[:8] == b'FDBOUT1\0'
    words, count, regions, functions = struct.unpack_from('<4I', data, 8)
    assert (words, regions, functions) == (32, 1, 1)
    at = 24
    variants = struct.unpack_from('<I', data, at)[0]
    assert variants == 2
    at += 4
    rows = []
    for _ in range(count):
        head = struct.unpack_from('<12I', data, at)
        at += 48
        selected = struct.unpack_from('<i', data, at)[0]
        at += 4 + 8 * (functions + variants)
        arena = list(struct.unpack_from('<32I', data, at))
        at += 128
        row = dict(kind=head[0], accepted=bool(head[1]), committed=bool(head[2]),
                   closed=bool(head[3]), size=list(head[9:11]), selected=selected, words=arena)
        if head[11] & 1:
            row['frame'] = data[at:at + 16]
            at += 16
        if head[11] & 2:
            size = head[9] * head[10] * 4
            row['view'] = data[at:at + size]
            at += size
        rows.append(row)
    assert at == len(data), 'partial or trailing observations are not results'
    return rows


class Adapter:
    def __init__(self, directory):
        spec = importlib.util.spec_from_file_location('fdb_unit_win16_guest', VM)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.client = module.Client()
        self.job = 'w16-unit-' + uuid.uuid4().hex[:12]
        self.directory = directory
        sources = {'M16ABI.H': WIN16_MEMORY_HEADER.encode(), 'FIXTURE.C': FIXTURE.encode()}
        for alias, name in [('M16HOST.H', 'memory-win16.h'),
                            ('M16GUI.C', 'memory-win16.c'), ('M16COM.C', 'memory-win16-common.c')]:
            sources[alias] = files('fdisbull').joinpath('native_runtime/' + name).read_bytes()
        for name, data in sources.items():
            (directory / name).write_bytes(data)
            self.client.put(self.job, name, data)
        built = self.client.run(self.job, ['wcl', '-bt=windows', '-ml', '-zq', '-w4',
            '-i=/opt/watcom/h', '-i=/opt/watcom/h/win', '-l=windows', '-fe=ADAPTER.EXE',
            'M16GUI.C', 'M16COM.C', 'FIXTURE.C'], timeout=180)
        assert built['exit_code'] == 0, built['stdout'] + built['stderr']
        image = self.client.get(self.job, 'ADAPTER.EXE')
        (directory / 'ADAPTER.EXE').write_bytes(image)
        assert image[:2] == b'MZ'
        ne = struct.unpack_from('<I', image, 0x3c)[0]
        assert image[ne:ne + 2] == b'NE', 'genuine segmented NE executable required'
        assert image[ne + 0x36] == 2, 'NE target must be Windows'

    def replay(self, commands):
        # Explicit 8.3 names also work on a native Windows 3.x filesystem.
        stem = uuid.uuid4().hex[:8].upper()
        script = b'FDBEVT1\0' + struct.pack('<6I', 32, len(commands), 36297, 0, 0, 0) + b''.join(commands)
        self.client.put(self.job, stem + '.BIN', script)
        ran = self.client.run(self.job, ['wine', 'ADAPTER.EXE', '--adapter-test',
            stem + '.BIN', stem + '.OUT'], timeout=180)
        # Wine's Win16 loader can swallow the application exit status.  A
        # complete, strictly decoded output is mandatory evidence as well.
        assert ran['exit_code'] == 0, ran
        data = self.client.get(self.job, stem + '.OUT')
        (self.directory / (stem + '.OUT')).write_bytes(data)
        return decode(data)


@pytest.fixture(scope='module')
def adapter(tmp_path_factory):
    if not VM:
        pytest.skip('requires an explicit genuine Win16 compiler/runtime guest')
    return Adapter(tmp_path_factory.mktemp('win16-adapter'))


@native
def test_real_ne_gdi_origin_palette_letterbox_fractional_and_multiple_chunks(adapter):
    sizes = [(2, 2), (4, 2), (2, 4), (4, 4), (5, 8), (321, 203)]
    rows = adapter.replay([command(5, a=w, b=h, flags=3) for w, h in sizes])
    red, green, blue, mixed, black = map(bytes, [(255, 0, 0, 255), (0, 255, 0, 255),
        (0, 0, 255, 255), (85, 170, 34, 255), (0, 0, 0, 255)])
    intrinsic = red + green + blue + mixed
    assert all(row['frame'] == intrinsic for row in rows)
    assert rows[0]['view'] == intrinsic
    assert rows[1]['view'] == black + red + green + black + black + blue + mixed + black
    assert rows[2]['view'] == black * 2 + intrinsic + black * 2
    assert rows[3]['view'] == (red * 2 + green * 2) * 2 + (blue * 2 + mixed * 2) * 2
    assert rows[4]['view'] == black * 5 + (red * 2 + green * 3) * 2 + (blue * 2 + mixed * 3) * 3 + black * 10
    # Exact mathematical pixel-center geometry across more than one DIB chunk.
    width, height = sizes[-1]
    left = (width - height) // 2
    expected = bytearray()
    for y in range(height):
        for x in range(width):
            if x < left or x >= left + height:
                expected.extend(black)
            else:
                sx = ((x - left) * 2 + 1) * 2 // (height * 2)
                sy = (y * 2 + 1) * 2 // (height * 2)
                expected.extend((red, green, blue, mixed)[sy * 2 + sx])
    assert rows[-1]['view'] == expected


@native
def test_real_win16_wndproc_physical_keys_modifiers_focus_and_closed_snapshot(adapter):
    rows = adapter.replay([command(1, a=0, c=1),
        *[command(1, a=0, b=modifier, c=1) for modifier in (1, 2, 4)],
        command(1, a=0, c=0), command(1, a=0, b=24, c=1),
        command(1, a=1, c=1), command(1, a=2, c=1, flags=1), command(0, flags=1)])
    assert rows[0]['words'][:3] == [1, 110, 49]
    for row in rows[1:5]:
        assert not row['accepted'] and not row['committed']
        assert row['words'] == rows[0]['words']
    assert rows[5]['words'][:3] == [1, 110, 49] and rows[5]['words'][7] == 2
    assert rows[6]['words'][:3] == [1, 0, 72] and rows[6]['words'][7] == 3
    assert rows[7]['closed'] and rows[7]['words'][15] == 1
    assert rows[8]['closed'] and rows[8]['words'] == rows[7]['words']
    assert rows[8]['frame'] == rows[7]['frame']


@native
def test_real_win16_capture_all_buttons_focus_release_and_selector_notification(adapter):
    rows = adapter.replay([command(5, a=4, b=2), command(2, a=1, c=0, d=0),
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
    assert rows[8]['words'][3:6] == [1, 1, 0] and rows[8]['committed']
    assert rows[9]['selected'] == 1 and rows[9]['accepted']
    assert rows[9]['words'] == rows[8]['words']


@native
def test_real_win16_timer_prefix_replacement_and_coordinate_refusal(adapter):
    rows = adapter.replay([command(0, flags=1), command(3, clock=65535),
        command(6, payload=(7, 8)), command(0, flags=1),
        command(2, a=1, c=32768, flags=4)])
    assert rows[1]['words'][0] == 0 and rows[1]['words'][6] == 65535
    assert rows[1]['accepted'] and rows[1]['committed']
    assert rows[3]['words'][:2] == [7, 8]
    assert rows[3]['frame'] == rows[0]['frame']
    assert rows[4]['words'] == rows[3]['words']
    assert not rows[4]['accepted'] and not rows[4]['committed']


LIFECYCLE = r'''#define WinMain fdb16_original_main
#include "M16GUI.C"
#undef WinMain
int PASCAL WinMain(HINSTANCE instance,HINSTANCE previous,LPSTR command,int show){
Fdb16Win app;FdbU32 values[18];RECT original,child,admitted;MINMAXINFO limits;
HFILE output;int controls,i,result;
(void)previous;(void)command;(void)show;
memset(&app,0,sizeof(app));memset(values,0,sizeof(values));
app.instance=instance;app.config=fdb16_config();app.diagnostic=1;
if(fdb16_host_open(&app.host,"unused-fixture-path",36297UL) || fdb16_win_create(&app,SW_SHOW))return 2;
values[0]=(FdbU32)app.host.view_width;values[1]=(FdbU32)app.host.view_height;
GetWindowRect(app.window,&original);ShowWindow(app.window,SW_MINIMIZE);
SendMessage(app.window,WM_SIZE,SIZE_MINIMIZED,0L);
values[2]=(FdbU32)IsIconic(app.window);values[3]=(FdbU32)app.host.view_width;
values[4]=(FdbU32)app.host.view_height;values[5]=(FdbU32)app.failed;
ShowWindow(app.window,SW_RESTORE);SendMessage(app.window,WM_SIZE,SIZE_RESTORED,0L);
values[6]=(FdbU32)app.host.view_width;values[7]=(FdbU32)app.host.view_height;
values[8]=(FdbU32)app.failed;memset(&limits,0,sizeof(limits));
limits.ptMaxSize.x=limits.ptMaxSize.y=5000;
SendMessage(app.window,WM_GETMINMAXINFO,0,(LPARAM)&limits);
values[9]=(FdbU32)limits.ptMaxTrackSize.x;values[10]=(FdbU32)limits.ptMaxTrackSize.y;
values[11]=(FdbU32)limits.ptMaxSize.x;values[12]=(FdbU32)limits.ptMaxSize.y;
values[13]=(FdbU32)limits.ptMinTrackSize.x;values[14]=(FdbU32)limits.ptMinTrackSize.y;
controls=app.config->region_count?102:70;
admitted.left=0;admitted.top=0;admitted.right=4096+32;admitted.bottom=4096+controls+16;
AdjustWindowRect(&admitted,(DWORD)GetWindowLong(app.window,GWL_STYLE),FALSE);
values[15]=(FdbU32)(admitted.right-admitted.left);values[16]=(FdbU32)(admitted.bottom-admitted.top);
ShowWindow(app.view,SW_HIDE);
result=SetWindowPos(app.window,NULL,0,0,limits.ptMaxTrackSize.x+100,limits.ptMaxTrackSize.y+100,
SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE)?0:1;
GetClientRect(app.view,&child);
values[17]=!result && child.right<=4096 && child.bottom<=4096 && child.right>0 && child.bottom>0;
output=_lcreat("LIFE.BIN",0);if(output==HFILE_ERROR)result=1;
else {for(i=0;i<18;i++)if(_lwrite(output,(LPCSTR)&values[i],4)!=4)result=1;_lclose(output);}
fdb16_win_dispose(&app);return result?2:0;
}
'''


@native
def test_real_win16_minimize_restore_and_maximum_geometry(adapter):
    adapter.client.put(adapter.job, 'LIFE.C', LIFECYCLE.encode())
    built = adapter.client.run(adapter.job, ['wcl', '-bt=windows', '-ml', '-zq', '-w4',
        '-i=/opt/watcom/h', '-i=/opt/watcom/h/win', '-l=windows', '-fe=LIFE.EXE',
        'LIFE.C', 'M16COM.C', 'FIXTURE.C'], timeout=180)
    assert built['exit_code'] == 0, built['stdout'] + built['stderr']
    ran = adapter.client.run(adapter.job, ['wine', 'LIFE.EXE'], timeout=180)
    assert ran['exit_code'] == 0, ran
    data = adapter.client.get(adapter.job, 'LIFE.BIN')
    assert len(data) == 18 * 4
    values = struct.unpack('<18I', data)
    assert values[2] == 1
    assert values[3:5] == values[:2]
    assert values[6:8] == values[:2]
    assert values[5] == values[8] == 0
    assert values[9:11] == values[15:17]
    assert values[11:13] == values[15:17]
    assert values[13:15] == (420, 350)
    assert values[17] == 1


CLOCK = r'''#define WinMain fdb16_original_main
#include "M16GUI.C"
#undef WinMain
int PASCAL WinMain(HINSTANCE instance,HINSTANCE previous,LPSTR command,int show){
Fdb16Win app;Fdb16Config config;FdbU32 values[10];HFILE output;int i,result;
(void)instance;(void)previous;(void)command;(void)show;
memset(&app,0,sizeof(app));config=*fdb16_config();config.tick_ms=54.92549323064085;
app.config=&config;values[0]=fdb16_win_clock_at(&app,102008UL);
values[1]=fdb16_win_clock_at(&app,4294967040UL);
values[2]=fdb16_win_clock_at(&app,4294967280UL);
values[3]=fdb16_win_clock_at(&app,64UL);values[4]=app.millis_high;
values[5]=app.last_millis;values[6]=(FdbU32)fdb16_win_interval(&app);
app.clock_override=1;app.controlled_clock=12345UL;values[7]=fdb16_win_clock(&app);
config.tick_ms=0.49;values[8]=(FdbU32)fdb16_win_interval(&app);
config.tick_ms=70000.2;values[9]=(FdbU32)fdb16_win_interval(&app);
result=0;output=_lcreat("CLOCK.BIN",0);if(output==HFILE_ERROR)return 2;
for(i=0;i<10;i++)if(_lwrite(output,(LPCSTR)&values[i],4)!=4)result=1;
_lclose(output);return result?2:0;
}
'''


@native
def test_real_win16_fractional_clock_wrap_epoch_and_wakeup_rounding(adapter):
    adapter.client.put(adapter.job, 'CLOCK.C', CLOCK.encode())
    built = adapter.client.run(adapter.job, ['wcl', '-bt=windows', '-ml', '-zq', '-w4',
        '-i=/opt/watcom/h', '-i=/opt/watcom/h/win', '-l=windows', '-fe=CLOCK.EXE',
        'CLOCK.C', 'M16COM.C', 'FIXTURE.C'], timeout=180)
    assert built['exit_code'] == 0, built['stdout'] + built['stderr']
    ran = adapter.client.run(adapter.job, ['wine', 'CLOCK.EXE'], timeout=180)
    assert ran['exit_code'] == 0, ran
    data = adapter.client.get(adapter.job, 'CLOCK.BIN')
    assert len(data) == 40
    values = struct.unpack('<10I', data)
    expected = tuple(math.floor(ms / 54.92549323064085) % 65536 for ms in
                     (102008, 4294967040, 4294967280, 4294967296 + 64))
    assert expected[0] != 102008 // 55
    assert values[:4] == expected
    assert values[4:] == (1, 64, 55, 12345, 1, 65535)
