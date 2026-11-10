"""Experimental QMP internal-snapshot job primitive, not an Anchor Stone.

The caller must own the complete writable block-node set and the QCOW2 image.
This primitive does not create, copy, validate or persist a checkpoint, nor
does it establish compatibility or source bindings across sessions.
"""
from __future__ import annotations

import re
import struct
import time
import uuid

from .dosbox_rpc import DebuggerError
from .qemu_input import require_released_machine_input


_NAME = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")
_PENDING = frozenset(('created', 'running', 'waiting', 'pending', 'aborting'))
_STOPPED = frozenset(('paused', 'debug'))


def validate_qcow_header(header, expected_size):
    """Reject unsupported qcow2 dependencies before any image parser runs."""
    if not isinstance(header, bytes) or len(header) < 104:
        raise ValueError('Truncated qcow2 header')
    magic, version, backing_offset, backing_size, cluster_bits, size, crypt = struct.unpack_from('>IIQIIQI', header)
    incompatible = struct.unpack_from('>Q', header, 72)[0]
    compatible = struct.unpack_from('>Q', header, 80)[0]
    header_length = struct.unpack_from('>I', header, 100)[0]
    if (magic != 0x514649fb or version != 3 or backing_offset or backing_size or crypt
            or incompatible or compatible or not 9 <= cluster_bits <= 21 or size != expected_size
            or not 104 <= header_length <= (1 << cluster_bits)):
        raise ValueError('Unsupported qcow2 header or disk identity')


def _stopped(status, *, allow_prelaunch=False):
    return (isinstance(status, dict) and status.get('running') is False
            and (status.get('status') in _STOPPED
                 or allow_prelaunch and status.get('status') == 'prelaunch'))


def snapshot_job(vm, operation, *, tag, vmstate, devices, timeout_ms=30000):
    """Run one internal snapshot job while stopped; close on uncertain outcome.

    This low-level primitive does not prove that ``devices`` contains every
    writable device. It is deliberately not exposed as a public save-state
    capability. The caller must establish exclusive disk ownership and identity.
    """
    if operation not in ('save', 'load'):
        raise ValueError('Snapshot operation must be save or load')
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('Snapshot timeout must be 1..600000 ms')
    if (not isinstance(tag, str) or not _NAME.fullmatch(tag)
            or not isinstance(vmstate, str) or not _NAME.fullmatch(vmstate)
            or not isinstance(devices, (list, tuple)) or not devices
            or any(not isinstance(node, str) or not _NAME.fullmatch(node) for node in devices)
            or len(set(devices)) != len(devices) or vmstate not in devices):
        raise ValueError('Invalid snapshot tag or block-node set')
    deadline = time.monotonic() + timeout_ms / 1000
    if not vm.lock.acquire(timeout=max(0, deadline - time.monotonic())):
        raise TimeoutError('Machine is busy')
    dispatched = False
    try:
        def call(method, args=None):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Snapshot deadline expired')
            return vm.qmp.call(method, args, timeout_ms=max(1, min(600000, int(remaining * 1000))))

        if vm.qmp is None or getattr(vm, 'closed', False):
            raise ValueError('Snapshot requires an owned machine')
        require_released_machine_input(vm)
        status = call('query-status')
        if not _stopped(status, allow_prelaunch=operation == 'load'):
            raise ValueError('Snapshot requires a stopped machine')
        job_id = 'fdisbull-snapshot-' + uuid.uuid4().hex
        command = 'snapshot-' + operation
        dispatched = True
        call(command, {'job-id': job_id, 'tag': tag, 'vmstate': vmstate,
                       'devices': list(devices)})
        while True:
            jobs = call('query-jobs')
            if not isinstance(jobs, list):
                raise DebuggerError('Malformed snapshot job list')
            selected = [job for job in jobs if isinstance(job, dict) and job.get('id') == job_id]
            if len(selected) != 1 or selected[0].get('type') != command:
                raise DebuggerError('Snapshot job identity missing or ambiguous')
            job = selected[0]
            state = job.get('status')
            if state == 'concluded':
                if 'error' in job:
                    raise DebuggerError('Snapshot job failed: ' + str(job['error']))
                break
            if state not in _PENDING:
                raise DebuggerError('Unexpected snapshot job status')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Snapshot job deadline expired')
            time.sleep(min(.02, remaining))
        call('job-dismiss', {'id': job_id})
        after = call('query-status')
        if not _stopped(after, allow_prelaunch=operation == 'load'):
            raise DebuggerError('Snapshot did not preserve stopped execution')
        return {'operation': operation, 'job_id': job_id, 'tag': tag,
                'vmstate': vmstate, 'devices': list(devices), 'status': 'concluded'}
    except BaseException:
        if dispatched:
            vm.close()
        raise
    finally:
        vm.lock.release()
