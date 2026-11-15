"""Compile the real bounded loader/TEB protocol functions with passive peers.

This tests cursor preservation, retention gaps and identity serialization. Real
CREATE_PROCESS/LOAD_DLL timing and runtime compatibility require native Wine.
"""
from pathlib import Path
import json
import shutil
import subprocess

import pytest


def _function(source, signature):
    start = source.index('static ' + signature)
    return source[start:source.index('\n}', start) + 2]


def test_native_loader_cursor_preserves_snapshots_and_reports_lost_prefix(tmp_path):
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('C compiler required for loader cursor contract')
    source = (Path(__file__).resolve().parents[1] / 'src/fdisbull/wine_guest/agent.c').read_text()
    first = source.index('#define MAX_LOADER_EVENTS ')
    end = source.index('static ULONGLONG loader_sequence;', first) + len('static ULONGLONG loader_sequence;')
    declarations = source[first:end]
    functions = '\n'.join(_function(source, signature) for signature in (
        'void json_text(', 'void loader_record(', 'void loader_settings(', 'void loader_history(',
        'void remember_teb(', 'void thread_information(',
    ))
    harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned long DWORD;
typedef unsigned long long ULONGLONG;
#define MAX_MODULES 4
#define MAX_THREADS 4
#define CREATE_PROCESS_DEBUG_EVENT 3
#define CREATE_THREAD_DEBUG_EVENT 2
static int early_loader,loader_stop_loads,loader_entry_reached;
static ULONGLONG module_revision=4,state_revision=12;
static unsigned target_bits=64;
static struct {DWORD dwProcessId,dwThreadId;} ev={88,99};
static struct {uintptr_t base;DWORD size;unsigned bits;ULONGLONG generation;int loaded;char name[256];
    DWORD entry_rva,tls_rva,tls_size;int header_details_observed;} modules[MAX_MODULES];
static struct {DWORD id;uintptr_t handle;int suspended;uintptr_t teb;DWORD teb_event;} threads[MAX_THREADS];
static void fatal(const char *message) {(void)message;abort();}
''' + declarations + '\n' + functions + r'''
int main(void) {
    modules[0].base=0x140000000ULL;modules[0].size=0x4000;modules[0].bits=64;
    modules[0].generation=4;modules[0].loaded=1;strcpy(modules[0].name,"authored.dll");
    modules[0].entry_rva=0x1000;modules[0].tls_rva=0x2000;modules[0].tls_size=40;
    modules[0].header_details_observed=1;
    loader_record("process-create",3,modules[0].base,0x140001000ULL,0x70001234,1);
    assert(loader_sequence==0); /* The default launch does not record or pause. */
    early_loader=loader_stop_loads=1;
    loader_record("process-create",3,modules[0].base,0x140001000ULL,0x70001234,1);
    assert(loader_sequence==1);
    strcpy(modules[0].name,"changed.dll");modules[0].generation=5;
    loader_history(0,10);
    for(unsigned i=0;i<300;i++) loader_record("dll-load",6,modules[0].base,0,0x70002000+i,1);
    loader_history(0,2);
    loader_history(47,1);
    loader_history(301,10);
    loader_history(302,10);
    loader_stop_loads=0;loader_entry_reached=1;loader_settings();puts("");
    threads[0].id=99;threads[0].handle=1;
    remember_teb(99,(void*)(uintptr_t)0x7ffdf000,CREATE_PROCESS_DEBUG_EVENT);
    thread_information();
    target_bits=32;thread_information();
    threads[0].teb=0;thread_information();
    return 0;
}
'''
    path = tmp_path / 'loader-protocol.c'
    path.write_text(harness)
    binary = tmp_path / 'loader-protocol'
    subprocess.run([compiler, '-std=c99', '-Wall', '-Wextra', '-Werror', str(path), '-o', str(binary)], check=True)
    output = subprocess.run([str(binary)], check=True, text=True, capture_output=True).stdout
    first, lost, resumed, current, ahead, control, teb64, teb32, absent = map(json.loads, output.splitlines())
    event = first['events'][0]
    assert event['name'] == 'authored.dll' and event['module_generation'] == 4
    assert event['base'] == '0x140000000' and event['declared_entry'] == '0x140001000'
    assert event['stopped_pc'] == '0x70001234' and event['stopped_pc'] != event['declared_entry']
    assert event['paused_before_continue'] is True and event['pe_header_observed'] is True
    assert (event['tls_rva'], event['tls_size']) == (0x2000, 40)
    assert lost['lost_before'] is True and lost['oldest_sequence'] == 46 and lost['latest_sequence'] == 301
    assert [e['sequence'] for e in lost['events']] == [46, 47] and lost['next_after'] == 47
    assert resumed['lost_before'] is False and resumed['events'][0]['sequence'] == 48
    assert current['events'] == [] and current['next_after'] == 301
    assert ahead['error'] == 'loader-cursor-ahead'
    assert control['phase'] == 'entry-reached' and control['stop_on_load'] is False
    assert teb64['teb'] == teb64['gs_base'] == '0x7ffdf000'
    assert teb64['teb_source'] == 'CREATE_PROCESS_DEBUG_EVENT.lpThreadLocalBase'
    assert teb64['gs_base_register_observed'] is False and 'convention' in teb64['gs_base_source']
    assert teb32['gs_base'] is None and teb32['teb'] == '0x7ffdf000'
    assert absent['error'] == 'selected-thread-teb-unavailable'
