"""Exercise the actual bounded C serializer without executing a target.

The host harness supplies stopped-agent tables, not Windows API behavior.
Real migration/control persistence remains a separate native qualification.
"""
from pathlib import Path
import ast
import io
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def inventory_program(tmp_path_factory):
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('Host C compiler required for control inventory contract')
    source = (ROOT / 'src/fdisbull/wine_guest/agent.c').read_text()
    signature = 'static void control_inventory(void)'
    assert signature in source, 'The guest has no stopped control-inventory reader'
    start = source.index(signature)
    function = source[start:source.index('\n}', start) + 2]
    harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef unsigned long DWORD;
typedef unsigned long long ULONGLONG;
typedef unsigned char BYTE;
typedef size_t SIZE_T;
#define MAX_BP 256
#define MAX_WATCH 64
#define MAX_GUARDS 512
#define MAX_THREADS 256
static int pending=1,exited=0,hit=255,guard_pending=1;
static DWORD continuation=0x10002,stepping_tid=17;
static unsigned target_bits=32;
static ULONGLONG state_revision=23,module_revision=29;
static struct {DWORD dwDebugEventCode,dwProcessId,dwThreadId;} ev={1,11,17};
static struct {uintptr_t address;BYTE original;int used,armed;} bp[MAX_BP];
static struct {uintptr_t address;SIZE_T length;int used;char access[3];} watches[MAX_WATCH],overlays[MAX_WATCH];
static struct {uintptr_t address;DWORD protection;int armed;} pages[MAX_GUARDS];
static int page_count;
static struct {DWORD id;uintptr_t handle;int suspended;} threads[MAX_THREADS];
''' + function + r'''
int main(int argc,char **argv) {
    if(argc>1 && !strcmp(argv[1],"running"))pending=0;
    if(argc>1 && !strcmp(argv[1],"exited"))exited=1;
    if(argc==1 || !strcmp(argv[1],"low")) {
        bp[255].used=1;bp[255].armed=0;bp[255].address=argc==1?0x123456789ULL:0x3456789;bp[255].original=0x90;
        bp[1].used=1;bp[1].armed=1;bp[1].address=0x1010;bp[1].original=0x55;
        watches[63].used=1;watches[63].address=0x2020;watches[63].length=2;strcpy(watches[63].access,"rw");
        overlays[63].used=1;overlays[63].address=0x3030;overlays[63].length=7;
        pages[0].address=0x2000;pages[0].protection=4;pages[0].armed=1;page_count=1;
        threads[255].id=17;threads[255].handle=0xdeadbeef;threads[255].suspended=1;
    }
    BYTE old_bp[sizeof(bp)],old_watches[sizeof(watches)],old_pages[sizeof(pages)],old_threads[sizeof(threads)];
    memcpy(old_bp,bp,sizeof(bp));memcpy(old_watches,watches,sizeof(watches));
    memcpy(old_pages,pages,sizeof(pages));memcpy(old_threads,threads,sizeof(threads));
    control_inventory();control_inventory();
    assert(!memcmp(old_bp,bp,sizeof(bp)) && !memcmp(old_watches,watches,sizeof(watches)));
    assert(!memcmp(old_pages,pages,sizeof(pages)) && !memcmp(old_threads,threads,sizeof(threads)));
    assert(state_revision==23 && module_revision==29);
    return 0;
}
'''
    directory = tmp_path_factory.mktemp('control-inventory')
    path = directory / 'inventory.c'
    path.write_text(harness)
    binary = directory / 'inventory'
    subprocess.run([compiler, '-std=c11', '-Wall', '-Werror', str(path), '-o', str(binary)],
                   check=True, capture_output=True, text=True)
    return binary


def read_inventory(binary, *args):
    result = subprocess.run([str(binary), *args], check=True, capture_output=True, text=True)
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(records) == 2 and records[0] == records[1]
    return records[0]


def test_control_inventory_preserves_owned_tables_and_exact_ids(inventory_program):
    record = read_inventory(inventory_program)
    assert record['format'] == 'fdisbull-debug-controls-1'
    assert record['pending_event'] == dict(pending=True,event=1,process=11,thread=17,target_bits=32,
        state_revision=23,module_revision=29,continuation=0x10002,stepping_thread=17,
        breakpoint_hit=255,guard_pending=True)
    assert record['breakpoints'] == [
        dict(id='bp-1',address='0x1010',original_hex='55',armed=True),
        dict(id='bp-255',address='0x123456789',original_hex='90',armed=False)]
    assert record['watchpoints'] == [dict(id='wp-63',address='0x2020',length=2,access='rw')]
    assert record['overlays'] == [dict(index=63,address='0x3030',length=7)]
    assert record['pages'] == [dict(address='0x2000',protection=4,armed=True)]
    assert record['threads'] == [dict(id=17,suspended=True)]
    assert 'handle' not in json.dumps(record)


def test_control_inventory_keeps_empty_arrays_explicit(inventory_program):
    record = read_inventory(inventory_program, 'empty')
    assert all(record[name] == [] for name in ('breakpoints','watchpoints','overlays','pages','threads'))


def test_actual_guest_json_matches_win16_checkpoint_wire_schema(inventory_program):
    from fdisbull.win16_state import _control_inventory
    record = read_inventory(inventory_program, 'low')
    session = SimpleNamespace(
        rpc=SimpleNamespace(capabilities={'control_inventory':True}),
        call=lambda method:record,
        bindings={1:dict(base=0x1000,generation=1),2:dict(base=0x3450000,generation=1),
                  3:dict(base=0x2000,generation=1)},
        breakpoints={'bp-1':dict(address=0x10010,runtime_address=0x1010,binding_generation=1),
                     'bp-255':dict(address=0x26789,runtime_address=0x3456789,binding_generation=1)},
        watchpoints={'wp-63':dict(address=0x30020,runtime_address=0x2020,binding_generation=1,
                                 length=2,access='rw')})
    normalized = _control_inventory(session,record['pending_event'])
    assert normalized['threads'] == [dict(id=17,suspended=True)]
    assert {row['id'] for row in normalized['breakpoints']} == {'bp-1','bp-255'}


@pytest.mark.parametrize('state', ['running','exited'])
def test_control_inventory_requires_pending_live_target(inventory_program, state):
    assert read_inventory(inventory_program, state) == {'error':'control-inventory-requires-pending-event'}


def test_broker_control_inventory_has_no_mutating_parameters():
    source = (ROOT / 'src/fdisbull/wine_guest/broker.py').read_text()
    tree = ast.parse(source)
    invoke = next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='invoke')
    stream = io.BytesIO()
    expected = {'format':'fdisbull-debug-controls-1'}
    namespace = {'process':SimpleNamespace(stdin=stream),'response':lambda *a,**kw:expected}
    exec(compile(ast.Module(body=[invoke],type_ignores=[]),'<actual broker invoke>','exec'),namespace)
    assert namespace['invoke']('control-inventory',{}) is expected
    assert stream.getvalue() == b'control-inventory\n'
    with pytest.raises(ValueError,match='parameters'):
        namespace['invoke']('control-inventory',{'resume':True})
    assert stream.getvalue() == b'control-inventory\n'
