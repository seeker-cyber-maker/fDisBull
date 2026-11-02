"""Portable C89 tests of segmented storage and owned host/protocol behavior.

Only the page allocator is replaced with host malloc. The authored core is a
deliberately small test collaborator, not recovered game code. These checks do
not qualify Win16 loading, Windows/GDI APIs, or original-game equivalence.
"""

import ctypes
import importlib.util
from importlib.resources import files
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import uuid
import zlib

import pytest

from fdisbull.udc_memory_win16 import WIN16_MEMORY_HEADER


BRIDGE = r"""#include "M16HOST.H"
static Fdb16Arena *core;
static Fdb16Host host;
static int closed,selected;
static FdbU32 calls,revision;
static const Fdb16Key keys[]={{"KeyA",65UL,1UL}};
static const Fdb16Color colors[]={{0UL,0,0,0},{1UL,255,0,0},{2UL,0,255,0},{3UL,0,0,255},{4UL,85,170,34}};
static const char *names[]={"original","alternate"};
static const Fdb16Region regions[]={{"update","Update",2,0,names,names}};
static const char *functions[]={"event"};
static const Fdb16Config config={70000UL,69996UL,2,2,55,
 8UL,9UL,10UL,11UL,12UL,13UL,14UL,15UL,1UL,2UL,0UL,
 1,5,1,1,keys,colors,regions,functions,"Authored four pixels","Portable host test","authored",0UL};
const Fdb16Config *fdb16_config(void){return &config;}
int fdb16_core_open(const char *path){(void)path;fdb16_release(core);core=fdb16_create(70000UL);closed=0;selected=0;return core?0:1;}
const Fdb16Arena *fdb16_core_words(void){return closed?0:core;}
int fdb16_core_initialize(FdbU32 clock){FdbU32 i;if(closed)return 1;
 for(i=0;i<70000UL;i++)if(fdb16_write(core,i,0UL))return 1;
 fdb16_write(core,0UL,10UL);fdb16_write(core,6UL,clock);
 for(i=0;i<4UL;i++)fdb16_write(core,69996UL+i,i+1UL);
 calls=0UL;revision++;return 0;}
int fdb16_core_dispatch(FdbU32 kind,FdbU32 ascii,FdbU32 scan,FdbU32 x,FdbU32 y,FdbU32 buttons,FdbU32 clock){
 if(closed)return 1;fdb16_write(core,0UL,kind);fdb16_write(core,1UL,ascii);fdb16_write(core,2UL,scan);
 fdb16_write(core,3UL,x);fdb16_write(core,4UL,y);fdb16_write(core,5UL,buttons);fdb16_write(core,6UL,clock);
 fdb16_write(core,7UL,++calls);revision++;return 0;}
int fdb16_core_call(FdbU16 function,const Fdb16Arena *payload,FdbU32 count,int render){
 FdbU32 i,index,value;(void)render;if(closed)return 1;
 /* This deliberately faulty collaborator proves a refusal is re-observed. */
 if(function==7){fdb16_write(core,42UL,0xdeadbeefUL);return 1;}
 if(function || fdb16_word_count(payload)!=count*2UL)return 1;
 for(i=0;i<count;i++){if(fdb16_read(payload,2UL*i,&index) || fdb16_read(payload,2UL*i+1UL,&value) || fdb16_write(core,index,value))return 1;}
 calls++;revision++;return 0;}
int fdb16_core_replace(const Fdb16Arena *words){if(closed || fdb16_copy(core,words))return 1;revision++;return 0;}
int fdb16_core_select(FdbU16 slot,FdbU16 variant){if(closed || slot || variant>1)return 1;selected=(int)variant;return 0;}
int fdb16_core_selected(FdbU16 slot){return closed || slot?-1:selected;}
Fdb16Count fdb16_core_revision(void){Fdb16Count c;c.low=revision;c.high=0UL;return c;}
Fdb16Count fdb16_core_calls(FdbU16 function){Fdb16Count c;c.low=function?0UL:calls;c.high=1UL;return c;}
Fdb16Count fdb16_core_region_calls(FdbU16 slot,FdbU16 variant){Fdb16Count c;(void)slot;(void)variant;c.low=0UL;c.high=0UL;return c;}
const char *fdb16_core_error(void){return "authored refusal";}
void fdb16_core_close(void){fdb16_release(core);core=0;closed=1;}
static int command(void *context,const Fdb16Command *c,const Fdb16Arena *payload){
 Fdb16Host *h=(Fdb16Host *)context;(void)payload;
 switch(c->kind){
 case FDB_CMD_KEY:return fdb16_host_key(h,(FdbU16)c->a,c->b,(int)c->c,c->clock);
 case FDB_CMD_POINTER:return fdb16_host_pointer(h,(FdbU16)c->a,(FdbU16)c->b,(int)(long)c->c,(int)(long)c->d,c->clock);
 case FDB_CMD_CLOCK:return fdb16_host_tick(h,c->clock);
 case FDB_CMD_SELECT:return fdb16_host_select(h,(FdbU16)c->a,(FdbU16)c->b);
 case FDB_CMD_RESIZE:return fdb16_host_resize(h,(int)c->a,(int)c->b);
 case FDB_CMD_FOCUS:return fdb16_host_focus(h,(int)c->a,c->clock);
 default:return 1;}}
static int capture(void *context,Fdb16File *stream,FdbU16 width,FdbU16 height){
 unsigned char bgr[12288],rgba[4];FdbU16 y,x;FdbU32 at;Fdb16Host *h=(Fdb16Host *)context;
 for(y=0;y<height;y++){
  if(fdb16_host_bgr(h,bgr,width,height,y,1))return 1;
  for(x=0;x<width;x++){at=(FdbU32)x*3UL;rgba[0]=bgr[(unsigned int)(at+2UL)];rgba[1]=bgr[(unsigned int)(at+1UL)];rgba[2]=bgr[(unsigned int)at];rgba[3]=255;
   if(fdb16_write_bytes(stream,rgba,4UL))return 1;}}
 return 0;}
int bridge_open(void){return fdb16_host_open(&host,"unused",0UL);}
void bridge_destroy(void){fdb16_host_destroy(&host);}
FdbU32 bridge_word(FdbU32 index){FdbU32 value;if(fdb16_read(host.snapshot,index,&value))return 0xffffffffUL;return value;}
int bridge_study(const char *in,const char *out){Fdb16Platform p;p.command=command;p.capture_view=capture;return fdb16_host_study(&host,in,out,&p,&host);}
int bridge_resize(int width,int height){return fdb16_host_resize(&host,width,height);}
int bridge_bgr(unsigned char *out,FdbU16 width,FdbU16 height,FdbU16 top,FdbU16 rows){return fdb16_host_bgr(&host,out,width,height,top,rows);}
int bridge_pointer(FdbU16 phase,FdbU16 button,int x,int y,FdbU32 clock){return fdb16_host_pointer(&host,phase,button,x,y,clock);}
"""


@pytest.fixture(scope="module")
def common(tmp_path_factory):
    compiler = shutil.which("clang") or shutil.which("gcc")
    if not compiler:
        pytest.skip(
            "portable C89 compiler unavailable; Win16 qualification is separate"
        )
    directory = tmp_path_factory.mktemp("win16-portable-common")
    (directory / "windows.h").write_text(
        "#define FAR\ntypedef void *HGLOBAL;\ntypedef void *HINSTANCE;\n"
    )
    (directory / "M16ABI.H").write_text(WIN16_MEMORY_HEADER)
    runtime = files("fdisbull").joinpath("native_runtime")
    (directory / "M16HOST.H").write_bytes(
        runtime.joinpath("memory-win16.h").read_bytes()
    )
    (directory / "common.c").write_bytes(
        runtime.joinpath("memory-win16-common.c").read_bytes()
    )
    (directory / "bridge.c").write_text(BRIDGE)
    library = directory / (
        "portable.dylib" if sys.platform == "darwin" else "portable.so"
    )
    warning_flags = (
        ["-Wno-misleading-indentation"] if "gcc" in Path(compiler).name else []
    )
    ran = subprocess.run(
        [
            compiler,
            "-std=c89",
            "-pedantic-errors",
            "-Wall",
            "-Wextra",
            *warning_flags,
            "-Werror",
            "-DFDB16_HOST_TEST",
            "-I",
            str(directory),
            "-shared",
            "-fPIC",
            "common.c",
            "bridge.c",
            "-o",
            str(library),
        ],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr
    loaded = ctypes.CDLL(str(library))
    pointer = ctypes.c_void_p
    u32 = ctypes.c_uint32
    u16 = ctypes.c_uint16
    signatures = {
        "fdb16_create": ([u32], pointer),
        "fdb16_word_count": ([pointer], u32),
        "fdb16_read": ([pointer, u32, ctypes.POINTER(u32)], ctypes.c_int),
        "fdb16_write": ([pointer, u32, u32], ctypes.c_int),
        "fdb16_release": ([pointer], None),
        "fdb16_clone": ([pointer], pointer),
        "fdb16_copy": ([pointer, pointer], ctypes.c_int),
        "fdb16_equal": ([pointer, pointer], ctypes.c_int),
        "fdb16_load_initial": ([ctypes.c_char_p, u32, u32], pointer),
        "fdb16_file_open": ([ctypes.c_char_p, ctypes.c_int], pointer),
        "fdb16_file_close": ([pointer], ctypes.c_int),
        "fdb16_file_read": ([pointer, pointer, u32], ctypes.c_int),
        "fdb16_file_eof": ([pointer], ctypes.c_int),
        "fdb16_write_bytes": ([pointer, pointer, u32], ctypes.c_int),
        "bridge_open": ([], ctypes.c_int),
        "bridge_destroy": ([], None),
        "bridge_word": ([u32], u32),
        "bridge_study": ([ctypes.c_char_p, ctypes.c_char_p], ctypes.c_int),
        "bridge_resize": ([ctypes.c_int, ctypes.c_int], ctypes.c_int),
        "bridge_bgr": ([pointer, u16, u16, u16, u16], ctypes.c_int),
        "bridge_pointer": ([u16, u16, ctypes.c_int, ctypes.c_int, u32], ctypes.c_int),
        "fdb16_arguments": ([ctypes.c_char_p, pointer, pointer], ctypes.c_int),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(loaded, name)
        function.argtypes = arguments
        function.restype = result
    yield loaded
    loaded.bridge_destroy()


def word(common, arena, index):
    value = ctypes.c_uint32()
    assert common.fdb16_read(arena, index, ctypes.byref(value)) == 0
    return value.value


def test_segmented_arena_crosses_page_and_16_bit_offsets_without_aliases(common):
    arena = common.fdb16_create(70000)
    assert arena
    try:
        assert common.fdb16_word_count(arena) == 70000
        for index in (0, 8191, 8192, 65535, 65536, 69999):
            assert common.fdb16_write(arena, index, 0xFFFFFFFF - index) == 0
        clone = common.fdb16_clone(arena)
        assert clone
        try:
            assert common.fdb16_equal(arena, clone) == 1
            for index in (0, 8191, 8192, 65535, 65536, 69999):
                assert word(common, clone, index) == 0xFFFFFFFF - index
            assert common.fdb16_write(clone, 65536, 123) == 0
            assert (
                common.fdb16_equal(arena, clone) == 0
                and word(common, arena, 65536) != 123
            )
            assert (
                common.fdb16_copy(clone, arena) == 0
                and common.fdb16_equal(arena, clone) == 1
            )
            assert common.fdb16_write(arena, 70000, 1) == 1
        finally:
            common.fdb16_release(clone)
    finally:
        common.fdb16_release(arena)
    maximum = common.fdb16_create(262144)
    assert maximum
    assert common.fdb16_write(maximum, 262143, 0xABCDEF01) == 0
    assert word(common, maximum, 262143) == 0xABCDEF01
    common.fdb16_release(maximum)
    assert not common.fdb16_create(262145)


class Range(ctypes.Structure):
    _fields_ = [("start", ctypes.c_uint32), ("count", ctypes.c_uint32)]


def test_segmented_ranges_are_atomic_and_unadmitted_changes_are_detected(common):
    signature = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(Range),
        ctypes.c_uint16,
    ]
    common.fdb16_copy_ranges.argtypes = signature
    common.fdb16_footprint.argtypes = signature
    before = common.fdb16_create(70000)
    after = common.fdb16_clone(before)
    try:
        common.fdb16_write(after, 65536, 123)
        admitted = (Range * 1)(Range(65535, 2))
        assert common.fdb16_footprint(before, after, admitted, 1) == 0
        common.fdb16_write(after, 8192, 4)
        assert common.fdb16_footprint(before, after, admitted, 1) == 1
        invalid = (Range * 2)(Range(8192, 1), Range(69999, 2))
        assert common.fdb16_copy_ranges(before, after, invalid, 2) == 1
        assert word(common, before, 8192) == 0
        assert common.fdb16_copy_ranges(before, after, admitted, 1) == 0
        assert word(common, before, 65536) == 123 and word(common, before, 8192) == 0
    finally:
        common.fdb16_release(before)
        common.fdb16_release(after)


def test_initial_binary_is_count_crc_and_exact_eof_bound(common, tmp_path):
    words = [0] * 70000
    words[65536] = 0x12345678
    payload = struct.pack("<70000I", *words)
    encoded = b"FDBINI1\0" + struct.pack("<I", 70000) + payload
    crc = zlib.crc32(payload)
    path = tmp_path / "INITIAL.BIN"
    path.write_bytes(encoded)
    arena = common.fdb16_load_initial(bytes(path), 70000, crc)
    assert arena
    assert word(common, arena, 65536) == 0x12345678
    common.fdb16_release(arena)
    assert not common.fdb16_load_initial(bytes(path), 70000, crc ^ 1)
    for malformed in (
        encoded[:-1],
        encoded + b"x",
        b"BADMAGIC" + encoded[8:],
        encoded[:8] + struct.pack("<I", 69999) + payload,
    ):
        path.write_bytes(malformed)
        assert not common.fdb16_load_initial(bytes(path), 70000, crc)
    assert not common.fdb16_load_initial(bytes(path), 131073, crc)


def test_raw_file_buffer_preserves_binary_counts_eof_and_exclusive_creation(
    common, tmp_path
):
    path = tmp_path / "RAW.BIN"
    data = bytes(range(256)) * 255 + bytes(range(240))
    assert len(data) == 65520
    writer = common.fdb16_file_open(bytes(path), 1)
    assert writer
    assert not common.fdb16_file_open(bytes(path), 1)
    assert common.fdb16_write_bytes(writer, data, len(data)) == 0
    assert common.fdb16_file_close(writer) == 0 and path.read_bytes() == data
    reader = common.fdb16_file_open(bytes(path), 0)
    assert reader
    buffer = ctypes.create_string_buffer(len(data))
    assert common.fdb16_file_read(reader, buffer, len(data)) == 0
    assert buffer.raw == data and common.fdb16_file_eof(reader) == 1
    assert common.fdb16_file_read(reader, buffer, 1) == 1
    assert common.fdb16_file_close(reader) == 0


def command(kind, a=0, b=0, c=0, d=0, *, flags=0, clock=36297, payload=()):
    return struct.pack(
        "<9I",
        *[v & 0xFFFFFFFF for v in (kind, a, b, c, d, 0, clock, flags, len(payload))],
    ) + struct.pack("<" + "I" * len(payload), *payload)


def replay(common, tmp_path, commands, *, success=0):
    source = tmp_path / "IN.BIN"
    output = tmp_path / "OUT.BIN"
    source.write_bytes(
        b"FDBEVT1\0"
        + struct.pack("<6I", 70000, len(commands), 36297, 0, 0, 0)
        + b"".join(commands)
    )
    assert common.bridge_open() == 0
    try:
        assert common.bridge_study(bytes(source), bytes(output)) == success
        return output.read_bytes() if output.exists() else b""
    finally:
        common.bridge_destroy()


def decode(data):
    assert data[:8] == b"FDBOUT1\0"
    words, count, regions, functions, variants = struct.unpack_from("<5I", data, 8)
    assert (words, regions, functions, variants) == (70000, 1, 1, 2)
    at = 28
    rows = []
    for _ in range(count):
        fields = struct.unpack_from("<12I", data, at)
        at += 48
        selected = struct.unpack_from("<i", data, at)[0]
        at += 4
        counters = struct.unpack_from("<3Q", data, at)
        at += 24
        values = struct.unpack_from("<70000I", data, at)
        at += 280000
        row = {
            "fields": fields,
            "selected": selected,
            "counters": counters,
            "words": values,
        }
        if fields[11] & 1:
            row["frame"] = data[at : at + 16]
            at += 16
        if fields[11] & 2:
            size = fields[9] * fields[10] * 4
            row["view"] = data[at : at + size]
            at += size
        rows.append(row)
    assert at == len(data)
    return rows


def test_streamed_study_observes_real_refusal_state_and_owns_terminal_snapshot(
    common, tmp_path
):
    rows = decode(
        replay(
            common,
            tmp_path,
            [
                command(1, c=1, flags=3),
                command(10, a=7, flags=4),
                command(9, flags=1),
                command(0, flags=1),
            ],
        )
    )
    assert rows[0]["words"][:7] == (1, 65, 1, 0, 0, 0, 36297)
    assert (
        rows[0]["frame"]
        == rows[0]["view"]
        == bytes((255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 85, 170, 34, 255))
    )
    assert rows[0]["counters"][0] == 0x100000001
    assert rows[1]["words"][42] == 0xDEADBEEF
    assert rows[1]["fields"][1:3] == (1, 0)
    assert rows[2]["selected"] == -1 and rows[2]["fields"][3] == 1
    assert rows[2]["words"] == rows[3]["words"] and rows[2]["frame"] == rows[3]["frame"]


def test_large_payload_prefix_and_pairs_keep_u32_indices(common, tmp_path):
    prefix = [0] * 65537
    prefix[65536] = 0x87654321
    rows = decode(
        replay(
            common,
            tmp_path,
            [command(6, payload=prefix), command(10, payload=[65536, 0x12345678])],
        )
    )
    assert rows[0]["words"][65536] == 0x87654321
    assert rows[0]["words"][69996:] == (1, 2, 3, 4)
    assert rows[1]["words"][65536] == 0x12345678


def test_bgr_chunk_fit_orientation_padding_and_pixel_center_pointer(common):
    assert common.bridge_open() == 0
    try:
        assert common.bridge_resize(5, 8) == 0
        buffer = ctypes.create_string_buffer(16 * 8)
        assert common.bridge_bgr(buffer, 5, 8, 0, 8) == 0
        red = bytes((0, 0, 255))
        green = bytes((0, 255, 0))
        blue = bytes((255, 0, 0))
        mixed = bytes((34, 170, 85))
        black = bytes(3)
        top = [
            black * 5,
            (red * 2 + green * 3),
            (red * 2 + green * 3),
            (blue * 2 + mixed * 3),
            (blue * 2 + mixed * 3),
            (blue * 2 + mixed * 3),
            black * 5,
            black * 5,
        ]
        assert buffer.raw == b"".join(row + b"\0" for row in reversed(top))
        assert common.bridge_bgr(buffer, 5, 8, 1, 2) == 0
        assert buffer.raw[:32] == b"".join(row + b"\0" for row in reversed(top[1:3]))
        assert common.bridge_pointer(1, 0, 4, 5, 99) == 0
        assert [common.bridge_word(i) for i in (3, 4, 5, 6)] == [1, 1, 1, 99]
        assert common.bridge_pointer(2, 0, -32768, -32768, 100) == 0
        assert [common.bridge_word(i) for i in (3, 4, 5)] == [0, 0, 0]
        assert common.bridge_pointer(1, 0, 32768, 0, 100) == 1
        assert common.bridge_bgr(buffer, 5, 8, 8, 1) == 1
        assert common.bridge_resize(4096, 4096) == 0
        assert common.bridge_bgr(buffer, 4096, 4096, 0, 3) == 1
    finally:
        common.bridge_destroy()


def test_study_rejects_wide_aliases_and_preserves_existing_output(common, tmp_path):
    rows = decode(
        replay(
            common,
            tmp_path,
            [
                command(1, a=65536, c=1, flags=4),
                command(2, a=1, c=32768, flags=4),
                command(4, a=65536, flags=4),
            ],
        )
    )
    assert all(row["fields"][1:3] == (0, 0) for row in rows)
    assert all(row["words"][:7] == (10, 0, 0, 0, 0, 0, 36297) for row in rows)
    existing = tmp_path / "OUT.BIN"
    retained = existing.read_bytes()
    assert common.bridge_open() == 0
    try:
        assert common.bridge_study(bytes(tmp_path / "IN.BIN"), bytes(existing)) == 2
    finally:
        common.bridge_destroy()
    assert existing.read_bytes() == retained


@pytest.mark.parametrize("suffix", [b"garbage", b"\0"])
def test_study_trailing_input_is_not_a_success(common, tmp_path, suffix):
    source = tmp_path / "IN.BIN"
    output = tmp_path / "OUT.BIN"
    source.write_bytes(b"FDBEVT1\0" + struct.pack("<6I", 70000, 0, 0, 0, 0, 0) + suffix)
    assert common.bridge_open() == 0
    try:
        assert common.bridge_study(bytes(source), bytes(output)) == 3
    finally:
        common.bridge_destroy()


@pytest.mark.parametrize(
    "line,expected",
    [
        (b"", 0),
        (b"  ", 0),
        (b"--adapter-test IN.BIN OUT.BIN", 1),
        (b'--adapter-test "input directory/IN.BIN" "output directory/OUT.BIN"', 1),
        (b"--adapter-test IN.BIN", -1),
        (b"--adapter-test IN OUT EXTRA", -1),
        (b'--adapter-test "unfinished OUT', -1),
        (b'--adapter-test "IN"suffix OUT', -1),
        (b"--adapter-test " + b"A" * 256 + b" OUT", -1),
    ],
)
def test_explicit_study_arguments_are_bounded(common, line, expected):
    source = ctypes.create_string_buffer(256)
    output = ctypes.create_string_buffer(256)
    assert common.fdb16_arguments(line, source, output) == expected


NATIVE_MAIN = r"""#include "M16HOST.H"
extern int bridge_open(void);
extern void bridge_destroy(void);
extern int bridge_study(const char *,const char *);
int PASCAL WinMain(HINSTANCE instance,HINSTANCE previous,LPSTR line,int show) {
 static FdbU32 report[12],value;Fdb16Arena *a,*b;Fdb16File *file;Fdb16Range range;int i;
 (void)instance;(void)previous;(void)line;(void)show;
 for(i=0;i<12;i++)report[i]=0xffffffffUL;
 report[0]=(FdbU32)sizeof(int);report[1]=(FdbU32)sizeof(FdbU32);
 a=fdb16_create(70000UL);report[2]=a?1UL:0UL;
 if(a){fdb16_write(a,65535UL,0xaabbccddUL);fdb16_write(a,65536UL,0x12345678UL);
  fdb16_read(a,65535UL,&value);report[3]=value;fdb16_read(a,65536UL,&value);report[4]=value;
  b=fdb16_clone(a);report[5]=(FdbU32)fdb16_equal(a,b);
  range.start=65535UL;range.count=2UL;fdb16_write(b,65536UL,0xdeadbeefUL);
  report[10]=(FdbU32)fdb16_footprint(a,b,&range,1);report[11]=(FdbU32)fdb16_copy_ranges(b,a,&range,1);
  if(!fdb16_equal(a,b))report[11]=2UL;fdb16_release(b);
  file=fdb16_file_open("ARENA.BIN",1);report[7]=file?(FdbU32)fdb16_dump_words(file,a):2UL;
  if(file && fdb16_file_close(file))report[7]=3UL;fdb16_release(a);}
 a=fdb16_load_initial("INITIAL.BIN",70000UL,FDB_TEST_CRC);report[6]=a?1UL:0UL;fdb16_release(a);
 report[8]=(FdbU32)bridge_open();if(!report[8])report[9]=(FdbU32)bridge_study("IN.BIN","OUT.BIN");bridge_destroy();
 file=fdb16_file_open("CHECK.BIN",1);if(!file)return 10;
 for(i=0;i<12;i++)if(fdb16_write32(file,report[i])){fdb16_file_close(file);return 11;}
 return fdb16_file_close(file);
}
"""


@pytest.mark.skipif(
    not os.environ.get("FDISBULL_WIN16_VM_CLIENT"),
    reason="requires explicit OpenWatcom/Win16 runtime guest; portable C89 tests are separate",
)
def test_real_win16_far_arena_raw_initial_and_streamed_owned_study():
    spec = importlib.util.spec_from_file_location(
        "fdb_win16_common_guest", os.environ["FDISBULL_WIN16_VM_CLIENT"]
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client = module.Client()
    job = "common16-" + uuid.uuid4().hex[:12]
    runtime = files("fdisbull").joinpath("native_runtime")
    values = [0] * 70000
    values[65536] = 0x12345678
    payload = struct.pack("<70000I", *values)
    main = NATIVE_MAIN.replace("FDB_TEST_CRC", hex(zlib.crc32(payload)) + "UL")
    bridge = BRIDGE.replace(
        "unsigned char bgr[12288],rgba[4];",
        "static unsigned char bgr[12288];unsigned char rgba[4];",
    )
    commands = [
        command(1, c=1, flags=3),
        command(10, a=7, flags=4),
        command(9, flags=1),
    ]
    sources = {
        "M16ABI.H": WIN16_MEMORY_HEADER.encode(),
        "M16HOST.H": runtime.joinpath("memory-win16.h").read_bytes(),
        "COMMON.C": runtime.joinpath("memory-win16-common.c").read_bytes(),
        "BRIDGE.C": bridge.encode(),
        "MAIN.C": main.encode(),
        "INITIAL.BIN": b"FDBINI1\0" + struct.pack("<I", 70000) + payload,
        "IN.BIN": b"FDBEVT1\0"
        + struct.pack("<6I", 70000, len(commands), 36297, 0, 0, 0)
        + b"".join(commands),
    }
    for name, data in sources.items():
        client.put(job, name, data)
    built = client.run(
        job,
        [
            "wcl",
            "-bt=windows",
            "-ml",
            "-zq",
            "-w4",
            "-we",
            "-i=/opt/watcom/h",
            "-i=/opt/watcom/h/win",
            "-l=windows",
            "-fe=COMMON.EXE",
            "COMMON.C",
            "BRIDGE.C",
            "MAIN.C",
        ],
        timeout=180,
    )
    assert built["exit_code"] == 0, built
    image = client.get(job, "COMMON.EXE")
    offset = struct.unpack_from("<I", image, 0x3C)[0]
    assert (
        image[:2] == b"MZ"
        and image[offset : offset + 2] == b"NE"
        and image[offset + 0x36] == 2
    )
    ran = client.run(job, ["wine", "COMMON.EXE"], timeout=180)
    assert ran["exit_code"] == 0, ran
    assert struct.unpack("<12I", client.get(job, "CHECK.BIN")) == (
        2,
        4,
        1,
        0xAABBCCDD,
        0x12345678,
        1,
        1,
        0,
        0,
        0,
        0,
        0,
    )
    expected = bytearray(280000)
    struct.pack_into("<II", expected, 65535 * 4, 0xAABBCCDD, 0x12345678)
    assert client.get(job, "ARENA.BIN") == expected
    rows = decode(client.get(job, "OUT.BIN"))
    assert rows[0]["words"][:7] == (1, 65, 1, 0, 0, 0, 36297)
    assert (
        rows[0]["frame"]
        == rows[0]["view"]
        == bytes((255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 85, 170, 34, 255))
    )
    assert rows[0]["counters"][0] == 0x100000001
    assert rows[1]["words"][42] == 0xDEADBEEF and rows[1]["fields"][1:3] == (1, 0)
    assert (
        rows[2]["selected"] == -1
        and rows[2]["fields"][3] == 1
        and rows[2]["words"][42] == 0xDEADBEEF
    )
