"""Authored interaction programs against the production portable native CPU.

The bridge only supplies resources and reads state. It contains no opcode
decoder or executor. QEMU integration is exercised separately with its binary.
"""
from __future__ import annotations

import ctypes as C
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native/qemu-agi/overlay/target/agi"
VIEW = bytes([0, 0, 1, 0, 0, 7, 0, 1, 3, 0, 2, 1, 0, 0x42, 0])
PICTURE = bytes([0xF0, 2, 0xF8, 0, 0, 0xFF])

BRIDGE = r'''
#include "runtime.h"
#include <stdlib.h>
#include <string.h>
typedef struct TestEngine {
    AgiRuntime r;
    AgiRuntimeResources resources;
    AgiRuntimeEvent events[256];
    AgiRuntimeWord words[64];
} TestEngine;
static void *copy(const void *p,size_t n) { void *q=malloc(n); if(q)memcpy(q,p,n);return q; }
void *rt_new(void) {
    TestEngine *t=calloc(1,sizeof(*t));
    static const unsigned char ret[]={0};
    if(!t)return NULL;
    t->resources.logics[0].code.data=copy(ret,1);
    t->resources.logics[0].code.size=1;
    memset(t->resources.sha256,'0',64);
    t->resources.words=t->words;
    return t;
}
void rt_free(TestEngine *t) {
    unsigned i,j;
    for(i=0;i<256;i++) {
        free((void*)t->resources.logics[i].code.data);
        for(j=0;j<256;j++)free((void*)t->resources.logics[i].messages[j]);
        free((void*)t->resources.views[i].data);
        free((void*)t->resources.pictures[i].data);
        free((void*)t->resources.sounds[i].data);
        free((void*)t->resources.object_names[i]);
    }
    for(i=0;i<t->resources.word_count;i++)free((void*)t->words[i].text);
    free(t);
}
void rt_logic(TestEngine *t,unsigned n,const void *p,unsigned size) {
    free((void*)t->resources.logics[n].code.data);
    t->resources.logics[n].code.data=copy(p,size);t->resources.logics[n].code.size=size;
}
void rt_message(TestEngine *t,unsigned logic,unsigned n,const char *p) {
    free((void*)t->resources.logics[logic].messages[n]);
    t->resources.logics[logic].messages[n]=copy(p,strlen(p)+1);
    if(n>t->resources.logics[logic].message_count)t->resources.logics[logic].message_count=n;
}
void rt_blob(TestEngine *t,unsigned kind,unsigned n,const void *p,unsigned size) {
    AgiRuntimeBlob *b=kind==0?&t->resources.views[n]:kind==1?&t->resources.pictures[n]:&t->resources.sounds[n];
    free((void*)b->data);b->data=copy(p,size);b->size=size;
}
void rt_word(TestEngine *t,const char *p,unsigned id) {
    unsigned n=t->resources.word_count++;
    t->words[n].text=copy(p,strlen(p)+1);t->words[n].id=id;
}
void rt_object(TestEngine *t,unsigned n,unsigned room,const char *name) {
    if(n>=t->resources.object_count)t->resources.object_count=n+1;
    t->resources.object_rooms[n]=room;
    free((void*)t->resources.object_names[n]);t->resources.object_names[n]=copy(name,strlen(name)+1);
}
int rt_init(TestEngine *t,unsigned entry,unsigned mask,unsigned capacity) {
    t->resources.entry_logic=entry;
    if(!agi_runtime_init(&t->r,&t->resources,t->events,256))return 0;
    return agi_runtime_observation(&t->r,mask,capacity);
}
void rt_var(TestEngine *t,unsigned n,unsigned v){t->r.state.v[n]=v;}
void rt_flag(TestEngine *t,unsigned n,unsigned v){t->r.state.f[n]=v;}
int rt_run(TestEngine *t,unsigned budget){return agi_runtime_run(&t->r,budget);}
uint64_t rt_probe(TestEngine *t,unsigned field,unsigned n) {
    AgiRuntimeState *s=&t->r.state;
    switch(field) {
    case 0:return s->v[n];case 1:return s->f[n];case 2:return s->status;
    case 3:return s->pc;case 4:return s->logic;case 5:return s->retired;
    case 6:return s->fault;case 7:return s->fault_detail;case 8:return s->stack_depth;
    case 9:return s->scan_start[n];case 10:return s->pending.id;case 11:return s->pending.opcode;
    case 12:return s->pending.reply;case 13:return s->parsed_count;case 14:return s->word_ids[n];
    case 15:return s->inventory[n];case 16:return s->controllers[n];case 17:return s->keypress;
    case 18:return s->world.actors[n].flags;case 19:return s->world.actors[n].x;
    case 20:return s->world.actors[n].y;case 21:return s->world.actors[n].view;
    case 22:return s->world.actors[n].cel;case 23:return s->world.actors[n].priority;
    case 24:return s->world.ticks;case 25:return s->clock_ticks;case 26:return s->sound_active;
    case 27:return s->sound_remaining;case 28:return t->r.obs_count;
    case 29:return t->r.obs_eligible[n];case 30:return t->r.obs_dropped[n];
    case 31:return s->scene_revision;case 32:return s->cycle_active;case 33:return s->cycle_count;
    case 34:return s->loaded_logics[n];case 35:return s->world.loaded_views[n];
    case 36:return s->script_count;case 37:return s->script_saved;case 38:return s->window_open;
    case 39:return s->menu_item_count;case 40:return s->menu_items[n].enabled;
    case 41:return s->input_enabled;case 42:return s->picture_shown;case 43:return s->trace_enabled;
    default:return UINT64_MAX;
    }
}
const char *rt_string(TestEngine *t,unsigned n){return t->r.state.strings[n];}
const char *rt_pending_text(TestEngine *t){return t->r.state.pending.text;}
const void *rt_state(TestEngine *t){return &t->r.state;}
size_t rt_state_size(void){return sizeof(AgiRuntimeState);}
int rt_complete(TestEngine *t,uint64_t id,int accepted,const char *text,unsigned number){return agi_runtime_complete(&t->r,id,accepted,text,number);}
int rt_input(TestEngine *t,const char *text){return agi_runtime_input(&t->r,text);}
int rt_key(TestEngine *t,unsigned key,int pressed){return agi_runtime_key(&t->r,key,pressed);}
int rt_controller(TestEngine *t,unsigned n){return agi_runtime_controller(&t->r,n);}
int rt_tick(TestEngine *t,unsigned n){return agi_runtime_tick(&t->r,n);}
int rt_cycle(TestEngine *t){return agi_runtime_cycle(&t->r);}
size_t rt_snapshot_size(void){return agi_runtime_snapshot_size();}
int rt_snapshot(TestEngine *t,void *p,size_t n){return agi_runtime_snapshot(&t->r,p,n);}
int rt_restore(TestEngine *t,uint64_t id,const void *p,size_t n){return agi_runtime_restore(&t->r,id,p,n);}
int rt_scene(TestEngine *t,void *v,void *p){return agi_runtime_scene(&t->r,v,p,160*168);}
'''


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    cc = shutil.which("cc")
    if cc is None:
        pytest.skip("native C compiler required")
    directory = tmp_path_factory.mktemp("agi-runtime")
    bridge = directory / "bridge.c"
    bridge.write_text(BRIDGE)
    library = directory / "runtime.so"
    subprocess.run([cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-shared", "-fPIC", "-I", str(NATIVE), str(bridge),
                    *(str(NATIVE / p) for p in ["runtime.c", "runtime_actor.c", "runtime_scene.c", "runtime_sound.c", "decode.c"]),
                    "-o", str(library)], check=True, capture_output=True, text=True)
    lib = C.CDLL(str(library))
    ptr, uint = C.c_void_p, C.c_uint
    signatures = {
        "rt_new": ([], ptr), "rt_free": ([ptr], None),
        "rt_logic": ([ptr, uint, ptr, uint], None),
        "rt_message": ([ptr, uint, uint, C.c_char_p], None),
        "rt_blob": ([ptr, uint, uint, ptr, uint], None),
        "rt_word": ([ptr, C.c_char_p, uint], None),
        "rt_object": ([ptr, uint, uint, C.c_char_p], None),
        "rt_init": ([ptr, uint, uint, uint], C.c_int),
        "rt_var": ([ptr, uint, uint], None), "rt_flag": ([ptr, uint, uint], None),
        "rt_run": ([ptr, uint], C.c_int), "rt_probe": ([ptr, uint, uint], C.c_uint64),
        "rt_string": ([ptr, uint], C.c_char_p), "rt_pending_text": ([ptr], C.c_char_p),
        "rt_state": ([ptr], ptr), "rt_state_size": ([], C.c_size_t),
        "rt_complete": ([ptr, C.c_uint64, C.c_int, C.c_char_p, uint], C.c_int),
        "rt_input": ([ptr, C.c_char_p], C.c_int),
        "rt_key": ([ptr, uint, C.c_int], C.c_int), "rt_controller": ([ptr, uint], C.c_int),
        "rt_tick": ([ptr, uint], C.c_int), "rt_cycle": ([ptr], C.c_int),
        "rt_snapshot_size": ([], C.c_size_t),
        "rt_snapshot": ([ptr, ptr, C.c_size_t], C.c_int),
        "rt_restore": ([ptr, C.c_uint64, ptr, C.c_size_t], C.c_int),
        "rt_scene": ([ptr, ptr, ptr], C.c_int),
    }
    for name, (args, result) in signatures.items():
        getattr(lib, name).argtypes = args
        getattr(lib, name).restype = result
    return lib


class Engine:
    def __init__(self, lib, code, *, mask=0, capacity=256, entry=0,
                 logics=None, messages=None, words=None, objects=None, blobs=None):
        self.lib, self.ptr = lib, lib.rt_new()
        assert self.ptr
        for number, program in {entry: bytes(code), **(logics or {})}.items():
            lib.rt_logic(self.ptr, number, program, len(program))
        for (logic, number), text in (messages or {}).items():
            lib.rt_message(self.ptr, logic, number, text.encode())
        for text, number in (words or {}).items():
            lib.rt_word(self.ptr, text.encode(), number)
        for n, (name, room) in enumerate(objects or []):
            lib.rt_object(self.ptr, n, room, name.encode())
        for (kind, number), data in (blobs or {}).items():
            lib.rt_blob(self.ptr, kind, number, data, len(data))
        assert lib.rt_init(self.ptr, entry, mask, capacity)

    def __enter__(self): return self
    def __exit__(self, *_): self.lib.rt_free(self.ptr)
    def probe(self, field, n=0): return self.lib.rt_probe(self.ptr, field, n)
    def run(self, budget=1000): return self.lib.rt_run(self.ptr, budget)
    def state(self): return C.string_at(self.lib.rt_state(self.ptr), self.lib.rt_state_size())
    def complete(self, *, id=None, accepted=True, text=None, number=0):
        return self.lib.rt_complete(self.ptr, self.probe(10) if id is None else id,
                                    accepted, None if text is None else text.encode(), number)
    def snapshot(self):
        data = C.create_string_buffer(self.lib.rt_snapshot_size())
        assert self.lib.rt_snapshot(self.ptr, data, len(data))
        return data.raw
    def scene(self):
        visual, priority = C.create_string_buffer(26880), C.create_string_buffer(26880)
        assert self.lib.rt_scene(self.ptr, visual, priority)
        return visual.raw, priority.raw


def conditional(predicates, yes, no):
    """Construct authored source, not interpret it."""
    skip = len(yes) + 3
    return bytes([255, *predicates, 255, skip & 255, skip >> 8, *yes,
                  254, len(no) & 255, len(no) >> 8, *no, 0])


def test_native_indirection_aliasing_arithmetic_and_flags(native):
    code = [3, 1, 7, 3, 7, 9, 9, 1, 7, 10, 2, 1, 11, 1, 250,
            5, 7, 10, 7, 7, 5, 1, 7, 2, 7, 165, 2, 3, 167, 2, 2,
            3, 8, 30, 15, 8, 17, 8, 15, 8, 16, 8,
            12, 31, 14, 31, 130, 10, 20, 9, 0]
    with Engine(native, code) as e:
        assert e.run() == 0 and e.probe(2) == 3
        assert e.probe(0, 1) == 7 and e.probe(0, 2) == 13
        assert e.probe(0, 7) == 254
        assert e.probe(1, 30) == e.probe(1, 31) == 0
        assert 10 <= e.probe(0, 9) <= 20


def test_fault_does_not_retire_or_commit_division(native):
    with Engine(native, [3, 1, 42, 167, 1, 0, 0], mask=3) as e:
        assert e.run() == -1
        assert (e.probe(6), e.probe(3), e.probe(5), e.probe(0, 1)) == (10, 3, 1, 42)
        before = e.state()
        assert e.run() == -1 and e.state() == before
        assert e.probe(29, 0) == 1


def test_calls_preserve_return_pc_and_per_logic_scan_start(native):
    with Engine(native, [22, 2, 22, 2, 0],
                logics={2: bytes([1, 30, 145, 22, 3, 0]), 3: bytes([1, 31, 0])}) as e:
        assert e.run() == 0 and e.probe(2) == 3
        assert (e.probe(0, 30), e.probe(0, 31), e.probe(8), e.probe(9, 2)) == (1, 2, 0, 3)
        assert e.probe(4) == 0 and e.probe(34, 2) == e.probe(34, 3) == 1


def test_missing_call_and_stack_limit_are_finite(native):
    with Engine(native, [22, 19, 0]) as e:
        assert e.run() == -1 and e.probe(6) == 2 and e.probe(5) == 0
    with Engine(native, [22, 0, 0]) as e:
        assert e.run(100) == -1
        assert e.probe(6) == 4 and e.probe(8) == 64 and e.probe(5) == 64


def test_new_room_unwinds_nested_call_and_restarts_logic_zero(native):
    with Engine(native, [22, 2, 3, 9, 99, 0], entry=1,
                logics={0: bytes([3, 9, 7, 0]), 2: bytes([18, 3, 0]), 3: bytes([0])}) as e:
        assert e.run() == 0
        assert (e.probe(4), e.probe(8), e.probe(0, 0), e.probe(0, 9)) == (0, 0, 3, 7)
        assert e.probe(1, 5) == 1


def test_parser_said_and_or_short_circuit_do_not_consume_skipped_effects(native):
    said = [14, 2, 10, 0, 20, 0]
    code = conditional([252, 1, 1, 0, *said, 13, 252], [3, 2, 1], [3, 2, 2])
    with Engine(native, code, words={"look": 10, "tree": 20}) as e:
        assert native.rt_input(e.ptr, b"LOOK, tree!")
        assert native.rt_key(e.ptr, 65, 1)
        assert e.run() == 0 and e.probe(0, 2) == 1
        assert e.probe(1, 4) == 0 and e.probe(17) == 65
    code = conditional([1, 1, 9, *said, 13], [3, 2, 1], [3, 2, 2])
    with Engine(native, code, words={"look": 10, "tree": 20}) as e:
        assert native.rt_input(e.ptr, b"look tree") and native.rt_key(e.ptr, 65, 1)
        assert e.run() == 0 and e.probe(0, 2) == 2
        assert e.probe(1, 4) == 0 and e.probe(17) == 65
    code = conditional([*said, 13], [3, 2, 1], [3, 2, 2])
    with Engine(native, code, words={"look": 10, "tree": 20}) as e:
        assert native.rt_input(e.ptr, b"look tree") and native.rt_key(e.ptr, 65, 1)
        assert e.run() == 0 and e.probe(0, 2) == 1
        assert e.probe(1, 4) == 1 and e.probe(17) == 0


def test_strings_vocabulary_phrases_ignored_words_and_unknowns(native):
    code = [114, 1, 1, 117, 1, 116, 2, 1, 0]
    with Engine(native, code, messages={(0, 1): "pick up the red key"},
                words={"pick up": 10, "the": 0, "red key": 20}) as e:
        assert e.run() == 0
        assert e.probe(13) == 2 and [e.probe(14, i) for i in range(2)] == [10, 20]
        assert native.rt_string(e.ptr, 2) == b"red key"
    with Engine(native, [0], words={"look": 10}) as e:
        assert native.rt_input(e.ptr, b"look mysterious box")
        assert e.probe(0, 9) == 2 and e.probe(14, 1) == 19999


def test_inventory_state_and_predicates(native):
    prefix = [92, 0, 3, 1, 7, 95, 1, 1]
    program = prefix + list(conditional([9, 0, 10, 1, 1], [3, 2, 1], [3, 2, 0]))
    with Engine(native, program, objects=[("coin", 0), ("key", 0)]) as e:
        assert e.run() == 0
        assert (e.probe(15, 0), e.probe(15, 1), e.probe(0, 2)) == (255, 7, 1)


def test_picture_actor_draw_erase_and_real_native_scene(native):
    code = [3, 20, 1, 24, 20, 25, 20, 26, 30, 1, 33, 1,
            37, 1, 10, 50, 41, 1, 1, 54, 1, 8, 35, 1, 0]
    with Engine(native, code, blobs={(0, 1): VIEW, (1, 1): PICTURE}) as e:
        assert e.run() == 0, (e.probe(6), e.probe(7))
        v, p = e.scene()
        assert v[0] == 2 and p[0] == 4
        assert v[50 * 160 + 10:50 * 160 + 12] == bytes([4, 4])
        assert p[50 * 160 + 10:50 * 160 + 12] == bytes([8, 8])
        assert e.probe(42) == 1 and e.probe(18, 1) & 2


def test_pending_completion_is_bound_atomic_and_exactly_once(native):
    code = [101, 1, 115, 2, 2, 22, 0, 5, 118, 3, 4, 0]
    with Engine(native, code, messages={(0, 1): "Hello", (0, 2): "Name?", (0, 3): "Number?"}) as e:
        assert e.run() == 0 and e.probe(2) == 4 and e.probe(5) == 0
        assert native.rt_pending_text(e.ptr) == b"Hello"
        before, ticket = e.state(), e.probe(10)
        assert e.run() == 0 and e.state() == before
        assert not e.complete(id=ticket + 1) and e.state() == before
        assert e.complete() and not e.complete(id=ticket)
        assert e.probe(5) == 1
        assert e.run() == 0 and e.probe(11) == 115
        before = e.state()
        assert not e.complete(text="too long") and e.state() == before
        assert e.complete(text="TiGa")
        assert native.rt_string(e.ptr, 2) == b"TiGa"
        assert e.run() == 0 and e.probe(11) == 118
        assert e.complete(number=42)
        assert e.run() == 0 and e.probe(0, 4) == 42 and e.probe(5) == 4


def test_menus_keys_controllers_and_disabled_selection(native):
    code = [156, 1, 157, 2, 7, 157, 3, 8, 158, 160, 8, 161,
            121, 65, 0, 9, 0]
    with Engine(native, code, messages={(0, 1): "Game", (0, 2): "Save", (0, 3): "Load"}) as e:
        native.rt_flag(e.ptr, 14, 1)
        assert e.run() == 0 and e.probe(11) == 161
        before = e.state()
        assert not e.complete(number=8) and e.state() == before
        assert e.complete(number=7) and e.probe(16, 7) == 1
        assert e.run() == 0 and native.rt_key(e.ptr, 65, 1)
        assert e.probe(16, 9) == 1


def test_sound_completion_and_clock_are_explicit_ticks(native):
    voice = bytes([3, 0, 0, 0, 15, 255, 255])
    sound = b"".join((8 + 7 * n).to_bytes(2, "little") for n in range(4)) + voice * 4
    with Engine(native, [98, 1, 99, 1, 8, 0], blobs={(2, 1): sound}) as e:
        assert e.run() == 0 and e.probe(26) == 1 and e.probe(1, 8) == 0
        assert native.rt_tick(e.ptr, 3)
        assert e.probe(26) == 0 and e.probe(1, 8) == 1
        assert native.rt_tick(e.ptr, 17) and e.probe(0, 11) == 1
        assert e.probe(24) == e.probe(25) == 20


def test_snapshot_save_continuation_restore_and_rejected_foreign_header(native):
    with Engine(native, [3, 1, 42, 125, 3, 1, 99, 126, 0]) as e:
        assert e.run() == 0 and e.probe(11) == 125
        snapshot = e.snapshot()
        assert e.complete() and e.run() == 0 and e.probe(0, 1) == 99 and e.probe(11) == 126
        before, ticket = e.state(), e.probe(10)
        bad = b"X" + snapshot[1:]
        assert not native.rt_restore(e.ptr, ticket, bad, len(bad)) and e.state() == before
        assert native.rt_restore(e.ptr, ticket, snapshot, len(snapshot))
        assert e.probe(0, 1) == 42 and e.probe(3) == 4 and e.probe(1, 12) == 1
        assert e.run() == 0 and e.probe(10) > ticket
        assert e.complete(accepted=False) and e.run() == 0 and e.probe(2) == 3


def test_native_observation_masks_and_overflow_do_not_change_state(native):
    code = [3, 20, 1, 24, 20, 25, 20, 30, 1, 33, 1, 37, 1, 10, 50,
            41, 1, 1, 35, 1, 22, 2, 0]
    states = []
    for mask, capacity in [(0, 256), (1, 256), (2, 256), (3, 256), (3, 1), (3, 0)]:
        with Engine(native, code, mask=mask, capacity=capacity,
                    logics={2: bytes([3, 5, 4, 165, 5, 3, 0])},
                    blobs={(0, 1): VIEW, (1, 1): PICTURE}) as e:
            assert e.run() == 0 and e.probe(2) == 3
            states.append(e.state())
            if mask == 0: assert e.probe(28) == e.probe(29, 0) == e.probe(29, 1) == 0
            if capacity <= 1: assert e.probe(30, 0) + e.probe(30, 1) > 0
    assert all(state == states[0] for state in states)


def test_cycle_phase_runs_logic_between_prepare_and_finish(native):
    with Engine(native, [1, 1, 0]) as e:
        assert native.rt_cycle(e.ptr) and not native.rt_cycle(e.ptr)
        assert not native.rt_tick(e.ptr, 1)
        assert e.run() == 0
        assert (e.probe(0, 1), e.probe(24), e.probe(32), e.probe(33)) == (1, 1, 0, 1)
        assert native.rt_cycle(e.ptr) and e.run() == 0
        assert (e.probe(0, 1), e.probe(24), e.probe(33)) == (2, 2, 2)


def test_text_script_dialogue_and_trace_state(native):
    code = [114, 1, 1, 12, 15, 101, 2, 169, 163, 164, 149, 150, 0, 1, 5,
            142, 20, 171, 172, 173, 0]
    with Engine(native, code, messages={(0, 1): "TiGa", (0, 2): "Hello %s1"}) as e:
        assert e.run() == 0 and e.probe(2) == 3
        assert e.probe(38) == 0 and e.probe(43) == 1
        assert e.probe(36) == e.probe(37) == 0
