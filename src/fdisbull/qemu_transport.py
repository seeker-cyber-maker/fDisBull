"""Private, deadline-bounded POSIX channels for an owned QEMU process.

The protocol clients use the same small socket interface with either Unix
sockets or these file descriptors. No network listener, shell, or guest agent
is needed for the pipe transport. A FIFO is a byte stream, not a reconnectable
socket: keep its GDB client alive while the machine runs outside the debugger.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import select
import time


class PipeChannel:
    """Own a read/write pair and apply one absolute deadline per operation."""

    def __init__(self, reader, writer, *, process=None):
        if os.name != 'posix':
            raise ValueError('QEMU pipe transport requires a POSIX host')
        self.reader = reader
        self.writer = writer
        self.process = process
        self.timeout = 10.0
        self.closed = False
        for stream in (reader, writer):
            os.set_blocking(self._fd(stream), False)

    @staticmethod
    def _fd(stream):
        return stream if isinstance(stream, int) else stream.fileno()

    def settimeout(self, seconds):
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('Pipe deadline must be finite and positive')
        self.timeout = float(seconds)

    def _wait(self, stream, deadline, *, writing=False):
        while True:
            if self.closed:
                raise OSError('QEMU pipe channel is closed')
            if self.process is not None and self.process.poll() is not None:
                raise BrokenPipeError('Owned QEMU process exited')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('QEMU pipe deadline expired')
            descriptor = self._fd(stream)
            interval = min(remaining, .05) if self.process is not None else remaining
            try:
                readable, writable, _ = select.select(
                    [] if writing else [descriptor], [descriptor] if writing else [], [], interval)
            except InterruptedError:
                continue
            if writable if writing else readable:
                return descriptor

    def recv(self, maximum):
        deadline = time.monotonic() + self.timeout
        while True:
            descriptor = self._wait(self.reader, deadline)
            try:
                return os.read(descriptor, maximum)
            except (BlockingIOError, InterruptedError):
                continue

    def sendall(self, data):
        deadline = time.monotonic() + self.timeout
        remaining = memoryview(data)
        while remaining:
            descriptor = self._wait(self.writer, deadline, writing=True)
            try:
                written = os.write(descriptor, remaining)
            except (BlockingIOError, InterruptedError):
                continue
            if written == 0:
                raise BrokenPipeError('QEMU pipe stopped accepting bytes')
            remaining = remaining[written:]

    def close(self):
        if self.closed:
            return
        self.closed = True
        seen = set()
        for stream in (self.reader, self.writer):
            try:
                descriptor = self._fd(stream)
                if descriptor in seen:
                    continue
                seen.add(descriptor)
                if isinstance(stream, int):
                    os.close(stream)
                else:
                    stream.close()
            except (OSError, ValueError):
                pass


def create_fifo_pair(base):
    """Create QEMU's .in/.out pair in a caller-owned private directory."""
    if os.name != 'posix':
        raise ValueError('QEMU pipe transport requires a POSIX host')
    base = Path(base)
    created = []
    try:
        for suffix in ('.in', '.out'):
            path = Path(str(base) + suffix)
            os.mkfifo(path, 0o600)
            created.append(path)
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise


def open_fifo_pair(base, process):
    """Open the host side; the owning process supplies FIFO EOF detection."""
    flags = os.O_RDWR | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0)
    reader = os.open(str(base) + '.out', flags)
    try:
        writer = os.open(str(base) + '.in', flags)
    except BaseException:
        os.close(reader)
        raise
    try:
        return PipeChannel(reader, writer, process=process)
    except BaseException:
        os.close(reader)
        os.close(writer)
        raise
