"""Bounded real FreeDOS witness for periodic QEMU virtual-clock rules."""
import hashlib
import json
import struct
from contextlib import contextmanager
from pathlib import Path

import pytest

from fdisbull.cli import respond
from fdisbull.debug_script import execute_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, assemble, prepare_dos_baseline
from test_qemu_clock_budget_native import budget_receipt
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch


_SOURCE = r'''
bits 16
org 100h
    jmp start
    db 'FMR1'
    dw ready-$$, counter-$$, iterations-$$, early-$$, loop_body-$$
counter: dd 7
iterations: dd 0
start:
ready:
    nop
loop_body:
    inc dword [cs:counter]
    inc dword [cs:iterations]
%if EARLY
    cmp dword [cs:iterations], 100
    jne loop_body
early:
%if EXIT
    mov ax, 4c2ah
    int 21h
%else
    nop
    jmp loop_body
%endif
%else
early:
    jmp loop_body
%endif
'''


@contextmanager
def _case(tmp_path, *, profile='virtual', early=False, exit_guest=False):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = hashlib.sha256(boot.read_bytes()).hexdigest()
    source_data = assemble(tmp_path, 'rule-counter',
        f'%define EARLY {int(early)}\n%define EXIT {int(exit_guest)}\n' + _SOURCE,
        runtime['NASM'])
    index = source_data.index(b'FMR1')
    marker = dict(zip(('ready', 'counter', 'iterations', 'early', 'loop'),
                      struct.unpack_from('<5H', source_data, index+4)))
    source = tmp_path / 'RULE.COM'
    source.write_bytes(source_data)
    source_hash = hashlib.sha256(source_data).hexdigest()
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    path = tmp_path / 'rule.fdb'
    with Project.create(path, source, image='com') as project:
        with _launch(project, runtime, tmp_path, disk, clock_profile=profile) as debug:
            base = debug.dos_process_info()['source_mapping']['runtime_base']
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            target = base + marker['counter']
            snap = debug.memory_snapshot(target, length=4, task_id='authored-rule-counter')['artifact']
            search = project.memory_search_start(snap, width=4, stride=4, mode='unknown')['artifact']
            rule = project.memory_rule_create(search, offset=0, value=0,
                max_applications=10, max_ticks=10)['artifact']
            yield project, debug, marker, base, rule, path
    assert hashlib.sha256(boot.read_bytes()).hexdigest() == boot_hash
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash


def _history(project, result):
    return [json.loads(bytes(project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
        (entry['progress_artifact'],)).fetchone()['data'])) for entry in result['recent_ticks']]


def _dword(debug, address):
    return int.from_bytes(bytes.fromhex(debug.memory(address, length=4)['hex']), 'little')


@pytest.mark.parametrize('route', ['python', 'json', 'script'])
def test_native_virtual_periodic_rules_capture_fresh_values_and_persist(tmp_path, monkeypatch, route):
    with _case(tmp_path) as (project, debug, marker, base, rule, path):
        calls = []
        advance = debug.clock_advance
        def record(delta_ns, **kwargs):
            result = advance(delta_ns, **kwargs)
            calls.append((delta_ns, result, kwargs))
            return result
        monkeypatch.setattr(debug, 'clock_advance', record)
        before = debug.clock_observe()
        if route == 'python':
            result = debug.memory_rule_run(rule, ticks=3, interval_ms=10, timeout_ms=15000)
        elif route == 'json':
            workspace = DebugWorkspace()
            workspace.sessions[debug.run_id] = debug
            try:
                reply = respond(dict(method='debug-memory-rule-run', params=dict(
                    project=str(project.path), run=debug.run_id, context='machine',
                    rule=rule, ticks=3, interval_ms=10, timeout_ms=15000)), debugger=workspace)
                assert reply['ok'], reply
                result = reply['result']
            finally:
                workspace.sessions.clear()
        else:
            report = execute_script(debug, dict(format='fdisbull-script-1', backend='qemu-dos',
                steps=[dict(op='memory-rule-run', rule=rule, ticks=3, interval_ms=10,
                            timeout_ms=15000)]), timeout_ms=15000)
            assert report['ok'] and report['completed_steps'] == 1, report
            assert report['steps'][0]['op'] == 'memory-rule-run'
            result = report['steps'][0]['result']
        assert result['complete'] and result['outcome'] == 'tick_budget_complete'
        assert result['completed_ticks'] == 3 and len(calls) == 2
        receipts = [budget_receipt(receipt, 10_000_000) for _, receipt, _ in calls]
        assert all(1 <= kwargs['timeout_ms'] <= 15000 for _, _, kwargs in calls)
        assert receipts[0]['start_ns'] == before['virtual_ns']
        assert receipts[1]['start_ns'] == receipts[0]['stopped_ns']
        assert receipts[0]['token'] != receipts[1]['token']
        history = _history(project, result)
        assert [p['last']['observed_value'] for p in history][0] == 7
        assert all(p['last']['observed_value'] > 0 for p in history[1:])
        assert all(p['last']['applied'] and p['last']['write_receipt']['verified'] for p in history)
        assert len({p['last']['plan_artifact'] for p in history}) == 3
        assert _dword(debug, base + marker['counter']) == 0
        assert _dword(debug, base + marker['iterations']) > 0
        persisted = project.memory_rule_info(rule)
        assert (persisted['progress']['ticks'], persisted['progress']['applications']) == (3, 3)
    with Project(path) as reopened:
        assert reopened.memory_rule_info(rule)['progress'] == persisted['progress']


@pytest.mark.parametrize('stop', ['breakpoint', 'exit'])
def test_native_periodic_rule_stops_before_next_tick_on_guest_event(tmp_path, stop):
    with _case(tmp_path, early=True, exit_guest=stop == 'exit') as (project, debug, marker, base, rule, _):
        if stop == 'breakpoint':
            debug.breakpoint(base + marker['early'])
        result = debug.memory_rule_run(rule, ticks=3, interval_ms=100, timeout_ms=15000)
        assert not result['complete'] and result['outcome'] == 'clock_interrupted'
        assert result['completed_ticks'] == 1
        assert result['clock_stop']['outcome'] == ('breakpoint' if stop == 'breakpoint' else 'guest_exit')
        assert result['clock_stop']['clock_budget']['deadline_reached'] is False
        progress = project.memory_rule_info(rule)['progress']
        assert (progress['ticks'], progress['applications']) == (1, 1)
        assert _history(project, result)[0]['last']['observed_value'] == 7


@pytest.mark.parametrize('guard', ['nonvirtual', 'native hooks', 'active layers'])
def test_native_rule_preflight_refuses_without_effects(tmp_path, guard):
    with _case(tmp_path, profile=None if guard == 'nonvirtual' else 'virtual') as (project, debug, marker, base, rule, _):
        hook = None
        if guard == 'native hooks':
            static = project.regions(1)[0].start
            hook = debug.hook(hex(static + marker['loop']), space='source', once=False,
                max_hits=3, actions=[dict(op='layers', layers=[])])
        if guard == 'active layers':
            ram = debug.layer_patch('rule-guard-ram', base + marker['iterations'],
                expected_hex='00000000', data_hex='01000000', kind='ram',
                activate=True, space='linear')
            fetch = debug.layer_patch('rule-guard-fetch', base + marker['ready'],
                expected_hex='90', data_hex='f8', kind='execute',
                activate=True, space='linear')
            before_layers = debug.layers()
            assert before_layers['active'] == [ram['layer'], fetch['layer']]
            assert debug.code(base + marker['ready'], length=1, view='execute', space='linear')['hex'] == 'f8'
        before_registers = debug.registers()['registers']
        before_memory = debug.memory(base + marker['counter'], length=8)['hex']
        before_progress = project.memory_rule_info(rule)
        with pytest.raises(ValueError, match='virtual|clock' if guard == 'nonvirtual' else guard):
            debug.memory_rule_run(rule, ticks=3, interval_ms=10, timeout_ms=15000)
        assert debug.registers()['registers'] == before_registers
        assert debug.memory(base + marker['counter'], length=8)['hex'] == before_memory
        assert project.memory_rule_info(rule) == before_progress
        if guard == 'active layers':
            assert debug.layers() == before_layers
            assert debug.code(base + marker['ready'], length=1, view='execute', space='linear')['hex'] == 'f8'
            debug.layers([])
            assert debug.memory(base + marker['iterations'], length=4)['hex'] == '00000000'
            assert debug.code(base + marker['ready'], length=1, view='execute', space='linear')['hex'] == '90'
        if hook:
            assert debug.hooks()['hooks'][0]['hook'] == hook['hook']
            debug.delete_hook(hook['hook'])
