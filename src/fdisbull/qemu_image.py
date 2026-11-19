"""Observe the executable of one owned QMP process; never infer wrapper layout.

Portable input identity contains bytes/version only (plus diagnostic path and
size). Process birth, file descriptors and vnode identities stay on this live
owner. The observed main executable is not a shared-library closure claim.
"""
from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import re
import select
import signal
import stat
import sys
import time

from .dosbox_rpc import DebuggerError

FORMAT = 'fdisbull-qemu-executed-image-1'
MAX_BYTES = 1024 ** 3
_MACH_MAGIC = {b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
               b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
               b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}


class ProducerMismatch(DebuggerError):
    """A passive, pre-import refusal that leaves the old stopped owner valid."""


def _remaining(deadline):
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError('QEMU executable identity deadline expired')
    return max(1, int(left * 1000))


def require_platform():
    if sys.platform not in ('linux', 'darwin'):
        raise DebuggerError('Observed QEMU executable identity requires Linux or macOS')


def _small(path):
    with open(path, 'rb') as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise DebuggerError('Process identity record exceeds its bound')
    return data


def _linux_process(pid):
    data = _small(f'/proc/{pid}/stat')
    tail = data.rsplit(b')', 1)[1].split()
    if len(tail) < 20 or int(data.split(b' ', 1)[0]) != pid:
        raise DebuggerError('Malformed owned process identity')
    return int(tail[1]), int(tail[19])


class _BsdInfo(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint32) for n in ('flags', 'status', 'xstatus', 'pid', 'ppid',
        'uid', 'gid', 'ruid', 'rgid', 'svuid', 'svgid', 'reserved')] + [
        ('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)] + [
        (n, ctypes.c_uint32) for n in ('nfiles', 'pgid', 'jobc', 'tdev', 'tpgid')] + [
        ('nice', ctypes.c_int32), ('start_sec', ctypes.c_uint64), ('start_usec', ctypes.c_uint64)]


class _Region(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint32) for n in ('protection', 'max_protection', 'inheritance', 'flags')] + [
        ('offset', ctypes.c_uint64)] + [(n, ctypes.c_uint32) for n in ('behavior', 'wired', 'tag',
        'resident', 'shared_private', 'swapped', 'dirty', 'refs', 'shadow', 'share_mode',
        'private_resident', 'shared_resident', 'object', 'depth')] + [
        ('address', ctypes.c_uint64), ('size', ctypes.c_uint64)]


class _VStat(ctypes.Structure):
    _fields_ = [('dev', ctypes.c_uint32), ('mode', ctypes.c_uint16), ('nlink', ctypes.c_uint16),
        ('ino', ctypes.c_uint64), ('uid', ctypes.c_uint32), ('gid', ctypes.c_uint32)] + [
        (n, ctypes.c_int64) for n in ('atime', 'atime_ns', 'mtime', 'mtime_ns', 'ctime', 'ctime_ns',
        'birthtime', 'birthtime_ns', 'size', 'blocks')] + [('blksize', ctypes.c_int32),
        ('flags', ctypes.c_uint32), ('gen', ctypes.c_uint32), ('rdev', ctypes.c_uint32),
        ('reserved', ctypes.c_int64 * 2)]


class _VNode(ctypes.Structure):
    _fields_ = [('stat', _VStat), ('kind', ctypes.c_int32), ('pad', ctypes.c_int32),
                ('fsid', ctypes.c_int32 * 2)]


class _RegionPath(ctypes.Structure):
    _fields_ = [('region', _Region), ('vnode', _VNode), ('path', ctypes.c_char * 1024)]


def _libproc():
    lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
    lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                ctypes.c_void_p, ctypes.c_int]
    lib.proc_pidinfo.restype = ctypes.c_int
    lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    lib.proc_pidpath.restype = ctypes.c_int
    return lib


def _mac_process(pid):
    info = _BsdInfo()
    got = _libproc().proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
    if got == 0 and ctypes.get_errno() == errno.ESRCH:
        raise ProcessLookupError(errno.ESRCH, 'Owned macOS process exited')
    if got != ctypes.sizeof(info) or info.pid != pid:
        raise DebuggerError('Cannot establish owned macOS process identity')
    return info.ppid, (info.start_sec, info.start_usec)


def _process(pid):
    return _linux_process(pid) if sys.platform == 'linux' else _mac_process(pid)


def _path(pid):
    if sys.platform == 'linux':
        return os.readlink(f'/proc/{pid}/exe')
    buffer = ctypes.create_string_buffer(4096)
    size = _libproc().proc_pidpath(pid, buffer, len(buffer))
    if not 0 < size < len(buffer) or buffer.raw[size] != 0:
        raise DebuggerError('Cannot establish complete macOS executable path')
    return os.fsdecode(buffer.raw[:size])


def _signature(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns, stat.S_IFMT(value.st_mode))


def _mac_mapping(pid, path, opened, deadline):
    """Bind proc_pidpath to its mapped vnode, not a replacement at that name."""
    lib, address = _libproc(), 0
    for _ in range(4096):
        _remaining(deadline)
        info = _RegionPath()
        got = lib.proc_pidinfo(pid, 8, address, ctypes.byref(info), ctypes.sizeof(info))
        if got != ctypes.sizeof(info):
            break
        region, value = info.region, info.vnode.stat
        if os.fsdecode(bytes(info.path)) == path:
            identity = (value.dev, value.ino, value.size,
                        value.mtime * 10**9 + value.mtime_ns,
                        value.ctime * 10**9 + value.ctime_ns,
                        stat.S_IFMT(value.mode))
            expected = (opened.st_dev & 0xffffffff, *_signature(opened)[1:])
            if identity != expected:
                raise DebuggerError('macOS executing vnode differs from opened image')
            return
        next_address = region.address + region.size
        if region.size == 0 or next_address <= address or next_address >= 1 << 64:
            break
        address = next_address
    raise DebuggerError('Cannot bind macOS executable path to its mapped vnode')


def _current_file(pid, fd, path, deadline):
    opened = os.fstat(fd)
    if not stat.S_ISREG(opened.st_mode) or not 0 < opened.st_size <= MAX_BYTES:
        raise DebuggerError('QEMU executing image is not a bounded regular file')
    if sys.platform == 'linux':
        current = os.stat(f'/proc/{pid}/exe')
        if _signature(current) != _signature(opened):
            raise DebuggerError('Owned process changed its executing image')
    else:
        if _path(pid) != path:
            raise DebuggerError('Owned process changed its executing image path')
        _mac_mapping(pid, path, opened, deadline)
    return opened


def _hash(fd, deadline, *, native=True):
    os.lseek(fd, 0, os.SEEK_SET)
    digest, count, magic = hashlib.sha256(), 0, None
    while True:
        _remaining(deadline)
        block = os.read(fd, 1024 * 1024)
        if not block:
            break
        if magic is None:
            magic = block[:4]
        count += len(block)
        if count > MAX_BYTES:
            raise DebuggerError('Executing image exceeds the identity byte budget')
        digest.update(block)
    expected = magic == b'\x7fELF' if sys.platform == 'linux' else magic in _MACH_MAGIC
    if native and not expected:
        raise DebuggerError('Observed QEMU process is not a native executable image')
    _remaining(deadline)
    return digest.hexdigest(), count


def launcher_hash(path, deadline):
    """Bound the requested launch-file receipt separately from the live image."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_BYTES:
            raise DebuggerError('QEMU launcher is not a bounded regular file')
        digest, size = _hash(fd, deadline, native=False)
        if (_signature(before) != _signature(os.fstat(fd))
                or _signature(before) != _signature(os.stat(path)) or size != before.st_size):
            raise DebuggerError('QEMU launcher changed while hashing')
        return digest
    finally:
        os.close(fd)


def _descendant(pid, ancestor, deadline):
    seen = set()
    for _ in range(32):
        _remaining(deadline)
        if pid == ancestor:
            return True
        if pid <= 1 or pid in seen:
            return False
        seen.add(pid)
        pid = _process(pid)[0]
    return False


def _peer(vm, deadline):
    records = vm.qmp.call('query-cpus-fast', timeout_ms=_remaining(deadline))
    count = vm.machine_configuration['cpus']
    if (not isinstance(records, list) or len(records) != count
            or any(not isinstance(r, dict) for r in records)
            or {r.get('cpu-index') for r in records} != set(range(count))):
        raise DebuggerError('QMP CPU owner observation is incomplete')
    peers = set()
    for record in records:
        tid = record.get('thread-id')
        if type(tid) is not int or tid <= 0:
            raise DebuggerError('QMP CPU thread identity is invalid')
        if sys.platform == 'linux':
            rows = _small(f'/proc/{tid}/status').splitlines()
            groups = [int(line.split()[1]) for line in rows if line.startswith(b'Tgid:')]
            if len(groups) != 1:
                raise DebuggerError('Cannot bind QMP CPU thread to its process')
            peers.add(groups[0])
        else:
            # QEMU's Darwin qemu_get_thread_id returns getpid(). An unknown
            # native implementation is refused rather than guessed from names.
            peers.add(tid)
    if len(peers) != 1:
        raise DebuggerError('QMP CPU threads do not have one process owner')
    pid = peers.pop()
    if _descendant(pid, vm.process.pid, deadline):
        birth = _process(pid)[1]
        vm._admission_guest = (pid, birth)
        if pid != vm.process.pid and sys.platform == 'linux':
            if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
                raise DebuggerError('Non-exec QEMU descendant cannot be safely owned without Linux pidfd')
            vm._admission_guest_pidfd = os.pidfd_open(pid)
            if (_process(pid)[1] != birth or not _descendant(pid, vm.process.pid, deadline)):
                raise DebuggerError('QMP descendant changed during owner-handle admission')
    if pid != vm.process.pid:
        raise DebuggerError('QEMU launcher must exec the owned QMP process; descendant forwarding is unsupported')


def _version(vm):
    expected = re.search(r'QEMU emulator version (\d+)\.(\d+)\.(\d+)', vm.inputs['qemu']['version'])
    raw = vm.qmp.greeting.get('QMP', {}).get('version', {}).get('qemu', {})
    actual = tuple(raw.get(k) for k in ('major', 'minor', 'micro'))
    if (expected is None or any(type(x) is not int or x < 0 for x in actual)
            or actual != tuple(map(int, expected.groups())) or actual[:2] < (9, 1)):
        raise DebuggerError('Owned QMP version differs from the selected launcher')
    return '.'.join(map(str, actual))


class ImageProof:
    def __init__(self, vm, deadline):
        self.fd = None
        self.owner = vm.process
        self.pid = self.owner.pid
        self.birth = _process(self.pid)[1]
        self.path = _path(self.pid)
        try:
            target = f'/proc/{self.pid}/exe' if sys.platform == 'linux' else self.path
            self.fd = os.open(target, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            before = _current_file(self.pid, self.fd, self.path, deadline)
            digest, size = _hash(self.fd, deadline)
            after = _current_file(self.pid, self.fd, self.path, deadline)
            if _signature(before) != _signature(after) or size != after.st_size:
                raise DebuggerError('QEMU executing image changed while hashing')
            self.signature = _signature(after)
            self.identity = dict(format=FORMAT, path=self.path, sha256=digest, size=size,
                                 version=_version(vm))
            self._owner(vm, deadline)
        except BaseException:
            self.close()
            raise

    def _owner(self, vm, deadline):
        _remaining(deadline)
        if (vm.process is not self.owner or self.owner.poll() is not None
                or _process(self.pid)[1] != self.birth):
            raise DebuggerError('QEMU executing-image process owner changed')

    def verify(self, vm, deadline):
        self._owner(vm, deadline)
        before = _current_file(self.pid, self.fd, self.path, deadline)
        if _signature(before) != self.signature:
            raise DebuggerError('QEMU executing image file changed after admission')
        digest, size = _hash(self.fd, deadline)
        after = _current_file(self.pid, self.fd, self.path, deadline)
        self._owner(vm, deadline)
        if (_signature(after) != self.signature or digest != self.identity['sha256']
                or size != self.identity['size'] or vm.inputs.get('qemu_image') != self.identity):
            raise DebuggerError('QEMU executing image identity changed after admission')

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def admit(vm, deadline):
    require_platform()
    owner = vm.process
    if owner is None or owner.poll() is not None:
        raise DebuggerError('QEMU exited before executable identity admission')
    _peer(vm, deadline)
    _version(vm)
    proof = ImageProof(vm, deadline)
    # The requested launch file remains a separate receipt and relaunch route.
    try:
        if launcher_hash(vm.inputs['qemu']['path'], deadline) != vm.inputs['qemu']['sha256']:
            raise DebuggerError('QEMU launcher changed during startup')
        _remaining(deadline)
        return proof
    except BaseException:
        proof.close()
        raise


def require_record(inputs):
    image = inputs.get('qemu_image') if isinstance(inputs, dict) else None
    if (not isinstance(image, dict) or not isinstance(image.get('sha256'), str)
            or re.fullmatch('[0-9a-f]{64}', image['sha256']) is None
            or not isinstance(image.get('version'), str) or not image['version']):
        raise ProducerMismatch('Checkpoint lacks observed QEMU executable identity; legacy producer is unqualified')
    return image


def verify(vm, deadline=None):
    proof = getattr(vm, '_qemu_image_proof', None)
    bounds = [time.monotonic() + 10, deadline, getattr(vm, 'operation_deadline', None)]
    bound = min(x for x in bounds if x is not None)
    try:
        if not isinstance(proof, ImageProof):
            raise DebuggerError('Live QEMU executing-image identity is unavailable')
        proof.verify(vm, bound)
    except BaseException as error:
        try:
            vm._fdisbull_control_quarantine = 'executing-image identity changed or unavailable'
            vm.close()
        except BaseException as cleanup:
            error.machine_cleanup_error = type(cleanup).__name__
        raise


def compatible(inputs, expected):
    """Compare portable components; retain original launch paths for relaunch."""
    require_record(inputs)
    require_record(expected)
    def projection(values):
        return {key: {field: value[field] for field in ('sha256', 'version') if field in value}
                for key, value in values.items()}
    if projection(inputs) != projection(expected):
        raise ProducerMismatch('QEMU runtime or executing-image producer identity differs')


def admission_quit(vm):
    """Quit the private admitted QMP peer before terminating a waiting wrapper."""
    peer = getattr(vm, '_admission_guest', None)
    qmp = getattr(vm, 'qmp', None)
    if peer is None:
        # The private endpoint can still be asked to quit, but a malformed or
        # unavailable CPU observation cannot authorize signals to descendants.
        # Only the known Popen launcher will be reaped by outer cleanup.
        vm._admission_guest_cleanup = 'unobserved QMP owner; descendant cleanup unqualified'
        if qmp is not None:
            try:
                qmp.operation_deadline = time.monotonic() + 1
                qmp.call('quit', timeout_ms=1000)
            except Exception:
                pass
        return
    pid, birth = peer
    handle = getattr(vm, '_admission_guest_pidfd', None)
    def alive():
        if handle is not None and select.select([handle], [], [], 0)[0]:
            return False
        try:
            current = _process(pid)[1]
        except ProcessLookupError:
            return False
        except FileNotFoundError:
            return False
        if current != birth:
            raise DebuggerError('Captured QMP guest PID was reused; refusing cleanup signal')
        return True
    def wait_for_exit(seconds):
        end = time.monotonic() + seconds
        while alive():
            # Reap the directly owned wrapper if it has exited, but continue
            # to own the captured guest even if the wrapper reparented it.
            if vm.process is not None:
                vm.process.poll()
            if time.monotonic() >= end:
                return False
            time.sleep(.01)
        return True
    if not alive():
        return
    try:
        # Teardown has a separate bounded grace; it never advances the guest.
        if qmp is not None:
            qmp.operation_deadline = time.monotonic() + 1
            qmp.call('quit', timeout_ms=1000)
    except Exception:
        # QEMU commonly closes stdio before replying to quit.
        pass
    if wait_for_exit(.5):
        return
    for action, grace in ((signal.SIGTERM, .5), (signal.SIGKILL, 1)):
        if not alive():
            return
        if handle is not None:
            signal.pidfd_send_signal(handle, action)
        elif pid == vm.process.pid:
            vm.process.send_signal(action)
        elif sys.platform != 'darwin':
            raise DebuggerError('Captured QMP descendant has no process handle; cleanup remains unresolved')
        else:
            # Darwin has no pidfd equivalent. Recheck the captured birth
            # immediately before targeted signalling; a residual PID-reuse
            # race remains between this check and kill(2). No name/group scan.
            if _process(pid)[1] != birth:
                raise DebuggerError('Captured QMP guest PID was reused; refusing cleanup signal')
            os.kill(pid, action)
        if wait_for_exit(grace):
            return
    raise DebuggerError('Captured QMP guest did not exit within cleanup deadline')
