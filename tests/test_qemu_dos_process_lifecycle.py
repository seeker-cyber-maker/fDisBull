"""Publication and failure cleanup against real DOS processes and SQLite.

The native cases reuse the required-by-environment runtime fixtures. They inject
one failure after a real DOS launch; successful fake loading cannot satisfy the
process ownership and reaping assertions.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import com_exit, resident_com
from test_qemu_dos_process_native import (
    create_project, launch_options, process_disk, process_record, process_runtime,
)


def reject_event(project, operation):
    """Reject one actual SQLite INSERT without replacing the persistence API."""
    assert operation in ('dos-process-entry', 'machine-run')
    with project.transaction(True):
        project.db.execute(f"""
            CREATE TRIGGER reject_lifecycle_event
            BEFORE INSERT ON debug_events
            WHEN NEW.operation = '{operation}'
            BEGIN
                SELECT RAISE(ABORT, 'authored lifecycle publication failure');
            END
        """)


def assert_invalidated(project, debug, active):
    """Require memory ownership and the persisted identity to agree after loss."""
    assert debug.vm.process.poll() is not None
    failed = debug.dos_process_info()
    assert failed['machine_closed'] is True
    assert failed['state'] == 'observation_failed'
    assert failed['capture_epoch'] != active['capture_epoch']
    assert failed['source_mapping']['live'] is False
    assert failed['source_mapping']['live_ranges'] == []
    assert failed['termination'] is None
    row = project.db.execute('SELECT metadata FROM debug_runs WHERE id=?',
                             (debug.run_id,)).fetchone()
    assert json.loads(row['metadata'])['process'] == failed
    assert not project.db.execute(
        "SELECT 1 FROM debug_events WHERE run=? AND operation='dos-process-return'",
        (debug.run_id,)).fetchone()
    return failed


def test_caller_transaction_refuses_process_launch_before_staging(tmp_path, monkeypatch):
    import fdisbull.dos_process_image as staging

    _, project = create_project(tmp_path, com_exit(37))
    spawned = []

    def unexpected_staging(*args, **kwargs):
        pytest.fail('A caller-owned transaction reached disk staging')

    monkeypatch.setattr(staging, 'prepare_process_disk', unexpected_staging)
    with project:
        with project.transaction(True):
            with pytest.raises(ValueError, match='transaction'):
                project.debugger(
                    'not-started', tmp_path, backend='qemu-dos',
                    dos_boot_image=tmp_path / 'absent.img', dos_mcopy='not-started',
                    _on_spawn=spawned.append,
                )
            assert project.db.in_transaction
        assert not spawned
        assert not project._live_debuggers
        assert not project.db.execute('SELECT 1 FROM debug_runs').fetchone()
        assert not project.db.execute('SELECT 1 FROM debug_events').fetchone()


def test_native_entry_event_failure_rolls_back_run_and_reaps_vm(
        tmp_path, process_runtime, process_disk):
    _, project = create_project(tmp_path, com_exit(37))
    spawned = []
    with project:
        reject_event(project, 'dos-process-entry')
        with pytest.raises(sqlite3.IntegrityError, match='authored lifecycle publication failure'):
            project.debugger(
                process_runtime['executable'], tmp_path, _on_spawn=spawned.append,
                **launch_options(process_runtime, process_disk),
            )
        assert len(spawned) == 1
        assert spawned[0].poll() is not None
        assert not project._live_debuggers
        assert not project.db.in_transaction
        assert not project.db.execute('SELECT 1 FROM debug_runs').fetchone()
        assert not project.db.execute('SELECT 1 FROM debug_events').fetchone()
    with Project(tmp_path / 'program.fdb') as reopened:
        assert not reopened.db.execute('SELECT 1 FROM debug_runs').fetchone()
        assert not reopened.db.execute('SELECT 1 FROM debug_events').fetchone()


def test_native_memory_snapshot_transport_failure_invalidates_process(
        tmp_path, process_runtime, process_disk, monkeypatch):
    _, project = create_project(tmp_path, com_exit(37))
    with project:
        with project.debugger(
                process_runtime['executable'], tmp_path,
                **launch_options(process_runtime, process_disk)) as debug:
            active = process_record(debug)
            control = debug.vm.qmp
            sequence = control.sequence

            def lost_reply(deadline):
                raise TimeoutError('authored QMP reply loss after dispatch')

            # QemuControl.call still dispatches query-status, then closes its
            # uncertain channel itself. The inherited snapshot operation must
            # propagate that failure through the machine ownership guard.
            monkeypatch.setattr(control, '_read', lost_reply)
            with pytest.raises(TimeoutError, match='authored QMP reply loss'):
                debug.memory_snapshot(
                    active['source_mapping']['runtime_base'], length=1,
                    space='physical',
                )
            assert control.sequence == sequence + 1
            assert control.socket is None
            assert_invalidated(project, debug, active)
            assert not project.db.execute(
                "SELECT 1 FROM debug_artifacts WHERE run=? AND kind='memory-snapshot'",
                (debug.run_id,)).fetchone()


def test_native_run_event_failure_invalidates_unobserved_completion(
        tmp_path, process_runtime, process_disk):
    _, project = create_project(tmp_path, com_exit(37))
    with project:
        with project.debugger(
                process_runtime['executable'], tmp_path,
                **launch_options(process_runtime, process_disk)) as debug:
            active = process_record(debug)
            reject_event(project, 'machine-run')
            with pytest.raises(sqlite3.IntegrityError, match='authored lifecycle publication failure'):
                debug.run(timeout_ms=3000)
            # DOS may already have exited, but its return has not been
            # independently admitted. Do not turn a journal error into a
            # successful guest-exit record or retain the old live mapping.
            assert_invalidated(project, debug, active)
            assert not project.db.execute(
                "SELECT 1 FROM debug_events WHERE run=? AND operation='machine-run'",
                (debug.run_id,)).fetchone()


@pytest.mark.parametrize('resident', [False, True], ids=['normal-exit', 'resident'])
def test_native_script_accepts_observed_dos_completion_without_exiting_machine(
        tmp_path, process_runtime, process_disk, resident):
    code = resident_com(exit_code=37)[0] if resident else com_exit(37)
    _, project = create_project(tmp_path, code)
    outcome = 'guest_tsr' if resident else 'guest_exit'
    with project:
        with project.debugger(
                process_runtime['executable'], tmp_path,
                **launch_options(process_runtime, process_disk)) as debug:
            active = process_record(debug)
            result = debug.script({
                'format': 'fdisbull-script-1', 'backend': 'qemu-dos',
                'steps': [
                    {'op': 'run', 'timeout_ms': 3000, 'expect': outcome,
                     'as': 'completion'},
                    {'op': 'assert', 'value': '$completion.process.termination.resident',
                     'equals': resident},
                    {'op': 'assert', 'value': '$completion.session.state',
                     'equals': 'stopped'},
                ],
            }, timeout_ms=10000)
            assert result['ok'], result
            assert result['completed_steps'] == 3
            returned = result['steps'][0]['result']
            assert returned['outcome'] == outcome
            assert returned['process']['state'] == ('resident' if resident else 'exited')
            assert returned['process']['termination']['code'] == 37
            assert returned['process']['capture_epoch'] != active['capture_epoch']
            assert debug.dos_process_info() == returned['process']
            assert debug.vm.process.poll() is None
            assert debug.status()['state'] == 'stopped'
