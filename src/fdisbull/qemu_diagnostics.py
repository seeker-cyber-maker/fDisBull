"""Bounded, byte-addressed access to an owned QEMU diagnostic stream."""
from contextlib import contextmanager
import time


def read_diagnostics(owner, *, cursor=0, limit=4096, identity=None):
    """Read a bounded snapshot; cursors are byte offsets, not text positions."""
    if type(cursor) is not int or cursor < 0:
        raise ValueError('Diagnostic cursor must be a nonnegative byte offset')
    if type(limit) is not int or not 1 <= limit <= 16384:
        raise ValueError('Diagnostic limit must be 1..16384 bytes')
    current = owner._diagnostic_id
    if (identity is not None and identity != current) or (cursor and identity != current):
        raise ValueError('Diagnostic cursor requires the current log identity')
    with owner.qemu_log_path.open('rb') as stream:
        stream.seek(0, 2)
        size = stream.tell()
        if cursor > size:
            raise ValueError('Diagnostic cursor is beyond the current log')
        stream.seek(cursor)
        data = stream.read(min(limit, size - cursor))
    process = owner.process
    return dict(identity=current, cursor=cursor, next_cursor=cursor + len(data), size=size,
                hex=data.hex(), native_exit_code=process.poll() if process is not None else None)


class QemuInspectionMixin:
    """Shared inspection of a single, still-owned QEMU process."""

    def _refresh_inspection_capability(self):
        if getattr(self, '_inspection_capability_owner', self.vm) is not self.vm:
            self.capabilities['native_cpu_inventory'] = None
            self._inspection_capability_owner = self.vm

    @contextmanager
    def _inspection_owner(self, timeout_ms):
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
            raise ValueError('Inspection timeout must be 1..600000 ms')
        deadline = time.monotonic() + timeout_ms / 1000
        owner = self.vm
        if not owner.lock.acquire(timeout=timeout_ms / 1000):
            raise TimeoutError('QEMU inspection lock deadline expired')
        try:
            def check():
                if self.vm is not owner:
                    raise ValueError('QEMU machine owner changed during inspection')
                if getattr(self, 'closed', False) or getattr(owner, 'closed', False):
                    raise ValueError('QEMU machine owner is closed')
                remaining = int((deadline - time.monotonic()) * 1000)
                if remaining < 1:
                    raise TimeoutError('QEMU inspection deadline expired')
                return remaining
            check()
            yield owner, check
            check()
        finally:
            owner.lock.release()

    def diagnostics(self, *, cursor=0, limit=4096, identity=None, timeout_ms=10000):
        with self._inspection_owner(timeout_ms) as (owner, check):
            return read_diagnostics(owner, cursor=cursor, limit=limit, identity=identity)

    def cpu_inventory(self, *, timeout_ms=10000):
        from .native_cpu import inspect_native_cpu
        with self._inspection_owner(timeout_ms) as (owner, check):
            result = inspect_native_cpu(owner.qmp, expected_target=owner.inspection_target,
                                        expected_cpu_type=getattr(owner, 'inspection_qom_cpu_type', None),
                                        timeout_ms=check())
            check()
            self._inspection_capability_owner = owner
            self.capabilities['native_cpu_inventory'] = bool(result['cpu_paths'] and result['status'] is not None)
            return result
