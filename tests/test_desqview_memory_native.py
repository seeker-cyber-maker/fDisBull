"""Opt-in real DOSBox execution of authored fixtures; no vendor payloads.

These checks prove the new host workflow and the helper's no-DESQview path.
They do not qualify an installed DESQview or QEMM kernel.
"""
import os
from pathlib import Path

import pytest

from fdisbull.desqview import write_probe
from fdisbull.project import Project


def backend():
    path = os.environ.get('FDISBULL_DOSBOX')
    if not path:
        pytest.skip('Supply FDISBULL_DOSBOX for actual native helper/search execution')
    return path


def test_native_absence_helper_at_exact_ready_point(tmp_path):
    executable = backend()
    disk = tmp_path / 'disk'
    disk.mkdir()
    target = disk / 'FDVAPI.COM'
    info = write_probe(target, mode='breakpoint', yields=3, nonce='ab' * 16)
    with Project.create(tmp_path / 'helper.fdb', target, image='com') as project:
        project.analyze(max_instructions=512)
        with project.debugger(executable, disk) as debug:
            point = debug.breakpoint(f"1000:{info['report']['ready_com_offset']:04x}")
            stopped = debug.run(guest_ms=500, timeout_ms=10000, fast_forward=True)
            assert stopped['outcome'] == 'breakpoint'
            base = debug.runtime_load * 16
            report = debug.desqview_observe(base + info['report']['com_offset'], probe_base=base, expected_nonce='ab' * 16)
            assert report['helper']['verified_at_ready_stop']
            assert report['parsed']['status'] == 'absent'
            assert report['parsed']['cooperation']['returned_yields'] == 0
            assert report['parsed']['cooperation']['critical_balance'] == 0
            assert report['scheduler_qualification'] == 'not_established_by_report'
            debug.delete_breakpoint(point['breakpoint_id'])
        artifact = report['artifact']
    with Project(tmp_path / 'helper.fdb') as reopened:
        row = reopened.db.execute('SELECT * FROM debug_artifacts WHERE id=?', (artifact,)).fetchone()
        assert len(bytes(row['data'])) == 64


def test_native_snapshot_refine_guarded_edit_and_restart(tmp_path):
    executable = backend()
    disk = tmp_path / 'disk'
    disk.mkdir()
    target = disk / 'COUNTER.COM'
    # mov word [120],7; inc word [120]; nop; jmp inc; private scalar data.
    target.write_bytes(bytes.fromhex('c70620010700ff06200190ebf9').ljust(32,b'\0') + bytes(8))
    database = tmp_path / 'counter.fdb'
    with Project.create(database, target, image='com') as project:
        project.analyze(max_instructions=64)
        with project.debugger(executable, disk) as debug:
            stop = debug.breakpoint('1000:0106')
            assert debug.run(timeout_ms=10000, fast_forward=True)['outcome'] == 'breakpoint'
            address = debug.runtime_load * 16 + 0x120
            first = debug.memory_snapshot(address, length=8, task_id='authored-counter-lifetime')['artifact']
            initial = project.memory_search_start(first, width=2, stride=2, mode='unknown')['artifact']
            debug.delete_breakpoint(stop['breakpoint_id'])
            # The final trace event is a pre-fetch stop. Observe the next
            # instruction too so the INC is known to have completed.
            trace = debug.trace(count=2)
            assert trace['metadata']['complete']
            second = debug.memory_snapshot(address, length=8, task_id='authored-counter-lifetime')['artifact']
            narrowed = project.memory_search_refine(initial, second, mode='delta', delta=1)['artifact']
            results = project.memory_search_results(narrowed)
            assert results['candidate_count'] == 1
            assert results['rows'][0]['value'] == 8 and results['rows'][0]['previous_value'] == 7
            plan = project.memory_edit_plan(narrowed, offset=0, value=42)['artifact']
            receipt = debug.memory_apply(plan)
            assert receipt['applied'] and receipt['verified']
            assert debug.memory('1000:0120', length=2)['hex'] == '2a00'
            with pytest.raises(ValueError, match='already dispatched'):
                debug.memory_apply(plan)
            rule = project.memory_rule_create(narrowed, offset=0, value=99,
                max_applications=4, max_ticks=4)['artifact']
            repeated = debug.memory_rule_run(rule, ticks=3, interval_ms=10, timeout_ms=3000)
            assert repeated['complete'] and repeated['completed_ticks'] == 3
            assert repeated['progress']['applications'] >= 1
            assert debug.memory('1000:0120', length=2)['hex'] == '6300'
    with Project(database) as reopened:
        assert reopened.memory_search_results(narrowed)['rows'][0]['value'] == 8
        assert reopened.memory_search_results(initial)['candidate_count'] == 4
        assert reopened.memory_rule_info(rule)['progress']['ticks'] == 3
        assert target.read_bytes()[32:34] == b'\0\0'
