"""New recovery-slice POSIX child supervision, derived from recovered source.

The leader remains unreaped through the final owned-group cleanup decision.
On Darwin, the kernel process table can confirm that the exited leader is
the only remaining member when signaling that group returns EPERM.
"""
from __future__ import annotations

import errno
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def terminate_as_exception(signum, frame):
    """Let Python context managers reap native owners on group termination."""
    raise SystemExit(128 + signum)


def _exists(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


def _signal_owned_group(process, name, receipt):
    """Send the signal while the group ID is still reserved by our child.

    The direct child has not been reaped when this is called. Its PID, which is
    also our group ID, therefore cannot have been reused for an unrelated group.
    """
    outcome = 'sent'
    try:
        os.killpg(process.pid, getattr(signal, 'SIG' + name))
    except ProcessLookupError:
        outcome = 'absent'
    except PermissionError as error:
        if (error.errno != errno.EPERM or name != 'KILL' or sys.platform != 'darwin'
                or not _only_exited_darwin_leader(process)):
            raise
        outcome = 'only-exited-leader'
    receipt['signals'].append(name)
    receipt.setdefault('group_signals', []).append(dict(signal=name, outcome=outcome))


def _exit_status(process, timeout):
    """Observe exit without reaping, so the leader PID/PGID cannot be reused."""
    end = time.monotonic() + timeout
    while True:
        value = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        if value is not None:
            return value.si_status if value.si_code == os.CLD_EXITED else -value.si_status
        if time.monotonic() >= end:
            return None
        time.sleep(min(.01, max(0, end-time.monotonic())))


def _only_exited_darwin_leader(process):
    # The child started a new session; no other session can add a member to
    # its group. Keep the zombie unreaped while checking for descendants.
    try:
        if _exit_status(process, 0) is None:
            return False
        result = subprocess.run(['/bin/ps', '-axo', 'pid=,pgid=,stat='],
            capture_output=True, text=True, check=True, timeout=.5)
        members = []
        for line in result.stdout.splitlines():
            pid, pgid, state = line.split()
            if int(pgid) == process.pid:
                members.append((int(pid), state[0]))
        return members == [(process.pid, 'Z')]
    except (IndexError, OSError, ValueError, subprocess.SubprocessError):
        return False


def _cleanup(process, grace, receipt):
    """Signal only the new group created by this Popen, then reap its leader.

    Group disappearance and leader reaping are recorded separately. A group
    that cannot be observed or removed is not described as fully cleaned.
    """
    if _exit_status(process, 0) is None:
        _signal_owned_group(process, 'TERM', receipt)
        _exit_status(process, grace)
    # The direct child is intentionally still unreaped. Its PID cannot become
    # an unrelated process/group between observation and this final signal.
    # Killing an already exited leader has no effect; this also removes any
    # remaining members of precisely the group we created, before PID reuse.
    _signal_owned_group(process, 'KILL', receipt)
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        receipt['cleanup_error'] = 'Owned cold leader could not be reaped within the cleanup budget'
    receipt['leader_reaped'] = process.poll() is not None
    end = time.monotonic() + grace
    while _exists(process.pid) and time.monotonic() < end:
        time.sleep(.01)
    receipt['group_gone'] = not _exists(process.pid)


def run_owned_cold(command, *, cwd, env, log_path, receipt_path, timeout, grace=2.0):
    """Run one cold Python child with its QEMU descendants in a new group.

    A temporary SIGTERM handler turns the outer controller's graceful timeout
    into this same cleanup path. The outer controller must allow more than
    three grace intervals before SIGKILL. No software can clean up after an
    immediate SIGKILL of its own supervisor; such an outcome must stay failed.
    """
    if (os.name != 'posix' or not all(hasattr(os, key) for key in ('waitid', 'WNOWAIT'))
            or type(timeout) not in (int, float) or not math.isfinite(timeout)
            or type(grace) not in (int, float) or not math.isfinite(grace)
            or not 0 < timeout <= 150 or not 0 < grace <= 2):
        raise ValueError('Owned cold processes require POSIX and finite bounded deadlines')
    log_path, receipt_path = Path(log_path), Path(receipt_path)
    if receipt_path.exists():
        raise FileExistsError('Preserve the previous cold-process receipt')
    receipt = dict(format='fdisbull-owned-cold-process-recovery-1', command=list(command),
        timed_out=False, interrupted=None, signals=[], leader_reaped=False,
        group_gone=False, cleanup_error=None, timeout_seconds=timeout,
        cleanup_grace_seconds=grace, passed=False)
    process = None
    previous_handler = signal.getsignal(signal.SIGTERM)
    primary = None
    tick = time.monotonic()
    admission_terms = []
    def defer_admission_term(signum, frame):
        admission_terms.append(signum)
    with log_path.open('xb') as output:
        try:
            # Defer Python's exception until Popen has returned its ownership
            # handle. This does not block SIGTERM in the spawned child's mask.
            signal.signal(signal.SIGTERM, defer_admission_term)
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output,
                stderr=subprocess.STDOUT, start_new_session=True)
            receipt.update(pid=process.pid, pgid=process.pid, state='running')
            signal.signal(signal.SIGTERM, terminate_as_exception)
            if admission_terms:
                terminate_as_exception(admission_terms[0], None)
            receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
            try:
                status = _exit_status(process, timeout)
                if status is None:
                    raise subprocess.TimeoutExpired(command, timeout)
                receipt['observed_exit_status'] = status
            except subprocess.TimeoutExpired as error:
                receipt['timed_out'] = True
                primary = error
            except BaseException as error:
                receipt['interrupted'] = type(error).__name__
                primary = error
        except BaseException as error:
            primary = error
            receipt['interrupted'] = type(error).__name__
        finally:
            # Further TERM requests cannot interrupt the bounded cleanup.
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            if process is not None:
                try:
                    _cleanup(process, grace, receipt)
                except BaseException as error:
                    receipt['cleanup_error'] = type(error).__name__ + ': ' + str(error)
                    # A failed observation must never skip the known Popen reap.
                    try:
                        process.kill()
                        process.wait(timeout=grace)
                    except BaseException as reap_error:
                        receipt['reap_error'] = type(reap_error).__name__ + ': ' + str(reap_error)
                    receipt['leader_reaped'] = process.poll() is not None
                receipt['returncode'] = process.returncode
                receipt['passed'] = (primary is None and process.returncode == 0 and
                    receipt['leader_reaped'] and receipt['group_gone'] and
                    not receipt['cleanup_error'])
            signal.signal(signal.SIGTERM, previous_handler)
            receipt.update(state='finished', elapsed_seconds=round(time.monotonic()-tick, 3))
            try:
                receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
            except BaseException as persistence_error:
                receipt['passed'] = False
                receipt['receipt_error'] = type(persistence_error).__name__ + ': ' + str(persistence_error)
                if primary is None:
                    primary = persistence_error
                else:
                    primary.add_note('Cold-process receipt persistence failed: ' + receipt['receipt_error'])
    if primary is not None:
        primary.cold_process_receipt = receipt
        raise primary
    result = subprocess.CompletedProcess(command, process.returncode if receipt['passed'] else (process.returncode or 1),
        stdout=log_path.read_text(), stderr='')
    return result, receipt
