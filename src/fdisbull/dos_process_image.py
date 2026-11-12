"""Prepare a private DOS process disk without replacing its boot configuration.

This module stages an original program and an authored COM loader through a
caller-selected mcopy executable. It only appends the loader invocation to an
existing, explicitly selected startup batch. A successful receipt proves byte
identity and disk preparation; it does not prove that the startup path runs,
DOS boots, a driver initializes, or a memory manager is active.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

from .dos_launch import guest_name
from .qemm_runtime import _FATVolume


MAX_IMAGE = 64 * 1024 * 1024
MAX_STARTUP = 65536
HELPER_NAME = 'FDBLOAD.COM'
_SHORT_PART = re.compile(r'[A-Za-z0-9_-]{1,8}(?:\.[A-Za-z0-9_-]{1,3})?')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _remaining(deadline):
    """A copy never gets more than 15 seconds or the shared remaining budget."""
    if deadline is None:
        return 15
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('DOS disk preparation deadline expired')
    return min(15, remaining)


def _file_stamp(value):
    return (value.st_dev, value.st_ino, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


@dataclass(frozen=True)
class _PinnedFile:
    path: Path
    data: bytes
    stamp: tuple

    @property
    def sha256(self):
        return _sha(self.data)

    def metadata(self):
        return dict(path=str(self.path), size=len(self.data), sha256=self.sha256)


def _pin_file(path, limit, label, *, deadline=None):
    _remaining(deadline)
    selected = Path(path).expanduser().resolve(strict=True)
    selected_info = selected.stat()
    if not stat.S_ISREG(selected_info.st_mode) or not 0 < selected_info.st_size <= limit:
        # In particular, never block while opening a caller-selected FIFO or
        # attempt an unbounded device read before validating its file type.
        raise ValueError(f'{label} must be a nonempty regular file at most {limit} bytes')
    _remaining(deadline)
    with selected.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ValueError(f'{label} must be a nonempty regular file at most {limit} bytes')
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    _remaining(deadline)
    if len(data) != before.st_size or _file_stamp(before) != _file_stamp(after):
        raise ValueError(f'{label} changed while being read')
    return _PinnedFile(selected, data, _file_stamp(after))


def _unchanged(pinned, label, *, deadline=None):
    try:
        current = _pin_file(pinned.path, MAX_IMAGE, label, deadline=deadline)
    except TimeoutError:
        raise
    except (OSError, ValueError) as error:
        raise ValueError(f'{label} changed during disk preparation') from error
    if current.stamp != pinned.stamp or current.sha256 != pinned.sha256:
        raise ValueError(f'{label} changed during disk preparation')
    _remaining(deadline)


def _guest_path(value, volume, *, root_only=False):
    """Use conservative ASCII 8.3 names safe in both DOS and mcopy arguments."""
    if (not isinstance(value, str) or not value or len(value) > 128
            or not value.isascii() or '/' in value or value != value.strip()):
        raise ValueError('Expected an unambiguous ASCII DOS 8.3 pathname')
    selected = value
    if len(selected) > 1 and selected[1] == ':':
        if selected[:2].upper() != volume.boot_drive or not selected[2:].startswith('\\'):
            raise ValueError('DOS pathname must be absolute on the selected boot volume')
        selected = selected[2:]
    if selected.startswith('\\'):
        selected = selected[1:]
    parts = selected.split('\\')
    if (not parts or any(_SHORT_PART.fullmatch(part) is None for part in parts)
            or root_only and len(parts) != 1):
        raise ValueError('Expected an unambiguous ASCII DOS 8.3 pathname')
    return volume.boot_drive + '\\' + '\\'.join(part.upper() for part in parts)


def _root_present(volume, name):
    """Treat files, directories and duplicate short names as collisions."""
    base, _, extension = name.partition('.')
    wanted = (base.ljust(8) + extension.ljust(3)).encode('ascii').upper()
    for offset in range(0, len(volume.root), 32):
        entry = volume.root[offset:offset + 32]
        if len(entry) != 32 or entry[0] == 0:
            break
        if entry[0] != 0xe5 and entry[11] != 0x0f and entry[:11].upper() == wanted:
            return True
    return False


def _owned_destination(path, identity):
    try:
        observed = path.lstat()
    except FileNotFoundError:
        return False
    return (stat.S_ISREG(observed.st_mode)
            and (observed.st_dev, observed.st_ino) == identity)


def prepare_process_disk(boot_image, source_path, source_sha256, helper_bytes,
                         destination, *, mcopy, startup_batch='FDAUTO.BAT',
                         target_name=None, image_format=None, deadline=None,
                         stage_source=True, program_guest_path=None):
    """Create one new private image and return independently pinned identities.

    ``startup_batch`` must already exist on the selected FAT12/16 boot volume.
    It is preserved byte-for-byte and followed by CRLF, the absolute loader
    invocation, and CRLF. Existing CONFIG.SYS/FDCONFIG.SYS members are verified
    unchanged. No CONFIG file, shell selection or earlier startup command is
    replaced. An EXIT/GOTO, prompt or failure in that original startup can still
    prevent the helper from running; the later native handshake must prove it.

    ``image_format`` may explicitly select COM or MZ. Without it, a leading MZ
    signature or a .COM source suffix is required. All original program bytes,
    including an MZ overlay, are retained. Source, disk and mcopy identities are
    checked again after staging. Preparation errors remove only the newly owned
    output image; the original disk and source are never written by this module.

    ``deadline`` is an optional absolute monotonic time shared with the caller's
    startup operation. Every copy receives at most the remaining budget, capped
    at 15 seconds, and no next stage or success receipt is admitted after expiry.
    """
    if deadline is not None and (type(deadline) not in (int, float) or not math.isfinite(deadline)):
        raise ValueError('DOS disk deadline must be a finite absolute monotonic time')
    _remaining(deadline)
    if (not isinstance(source_sha256, str)
            or re.fullmatch(r'[0-9a-f]{64}', source_sha256) is None):
        raise ValueError('Expected the original program SHA-256')
    if not isinstance(helper_bytes, bytes) or not 1 <= len(helper_bytes) <= 0xff00:
        raise ValueError('DOS loader helper must contain 1..65280 immutable COM bytes')
    from .dos import load_com, load_mz
    load_com(helper_bytes)

    disk = _pin_file(boot_image, MAX_IMAGE, 'DOS boot image', deadline=deadline)
    source = _pin_file(source_path, MAX_IMAGE, 'DOS program source', deadline=deadline)
    if source.sha256 != source_sha256:
        raise ValueError('DOS program source does not match its project SHA-256')
    if image_format is None:
        image_format = 'MZ' if source.data.startswith(b'MZ') else (
            'COM' if Path(source_path).suffix.lower() == '.com' else None)
    if image_format not in ('COM', 'MZ'):
        raise ValueError('DOS process image_format must explicitly select COM or MZ')
    if image_format == 'COM':
        load_com(source.data)
    else:
        # This path admits classic DOS programs. Selecting the DOS stub of a
        # secondary executable needs its own explicit process contract.
        load_mz(source.data, load_segment=0x10)

    _remaining(deadline)
    volume = _FATVolume(disk.data)
    if type(stage_source) is not bool or stage_source and program_guest_path is not None:
        raise ValueError('Workspace staging requires an explicit uncopied D: program')
    if not stage_source:
        from .dos_workspace_fat import volume_layout, parse_volume
        if not isinstance(program_guest_path, str) or not program_guest_path.startswith('D:\\'):
            raise ValueError('Workspace program requires an absolute D: path')
        extent = volume_layout(disk.data)['D']
        entries = parse_volume(disk.data[extent['offset']:extent['offset'] + extent['size']])
        entry = entries.get(program_guest_path[3:])
        if entry is None or entry['type'] != 'file' or entry['data'] != source.data:
            raise ValueError('Workspace program does not match the pinned source')
    startup_path = _guest_path(startup_batch, volume)
    if not startup_path.endswith('.BAT'):
        raise ValueError('The selected startup member must be an existing .BAT file')
    before_startup = volume.read(startup_path, maximum=MAX_STARTUP)
    _remaining(deadline)
    if b'\0' in before_startup or b'\x1a' in before_startup:
        raise ValueError('Cannot append a DOS loader after a startup NUL or DOS EOF marker')
    chosen_name = (guest_name(Path(source_path).name, source_sha256, image_format)
                   if target_name is None else target_name)
    program_path = _guest_path(chosen_name, volume, root_only=True)
    helper_path = volume.boot_drive + '\\' + HELPER_NAME
    if program_path == helper_path:
        raise ValueError('Program target conflicts with the DOS loader helper name')
    program_name = program_path.rsplit('\\', 1)[1]
    extensions = ('.COM',) if image_format == 'COM' else ('.EXE', '.COM')
    if not program_name.endswith(extensions):
        raise ValueError('DOS program target extension differs from its image format')
    for name in ((program_name, HELPER_NAME) if stage_source else (HELPER_NAME,)):
        if _root_present(volume, name):
            raise ValueError('DOS staging name already exists in the boot image: ' + name)
    appended = ('\r\n' + helper_path + '\r\n').encode('ascii')
    after_startup = before_startup + appended
    if len(after_startup) > MAX_STARTUP:
        raise ValueError('Appended DOS startup exceeds 64 KiB')

    configurations = {}
    for name in ('CONFIG.SYS', 'FDCONFIG.SYS'):
        _remaining(deadline)
        if _root_present(volume, name):
            configurations[name] = volume.read('\\' + name, maximum=MAX_STARTUP)

    # mcopy is commonly a symlink to the mtools multi-call executable. Keep its
    # invocation name while pinning the resolved executable's actual bytes.
    tool_path = Path(mcopy).expanduser().absolute()
    tool = _pin_file(tool_path, MAX_IMAGE, 'mcopy executable', deadline=deadline)
    if not os.access(tool_path, os.X_OK):
        raise ValueError('The selected mcopy must be executable')

    requested = Path(destination).expanduser().absolute()
    if requested.suffix.lower() != '.img' or '@@' in str(requested):
        raise ValueError('Choose a new private .img destination without mcopy offset syntax')
    target = requested.parent.resolve(strict=True) / requested.name
    identity = None
    try:
        _remaining(deadline)
        # Exclusive creation also rejects existing files and dangling symlinks.
        with target.open('xb') as output:
            os.fchmod(output.fileno(), 0o600)
            info = os.fstat(output.fileno())
            identity = (info.st_dev, info.st_ino)
            output.write(disk.data)
        _remaining(deadline)
        if _sha(target.read_bytes()) != disk.sha256:
            raise ValueError('Private DOS disk copy differs from its original input')
        image_argument = str(target) + (f'@@{volume.offset}' if volume.offset else '')
        staged_members = (((program_path, source.data, False),) if stage_source else ()) + (
                          (helper_path, helper_bytes, False),
                          (startup_path, after_startup, True))
        with tempfile.TemporaryDirectory(prefix='fdisbull-dos-stage-', dir=target.parent) as temporary:
            for index, (guest_path, data, replace) in enumerate(staged_members):
                _remaining(deadline)
                if (not _owned_destination(target, identity)
                        or tool_path.resolve(strict=True) != tool.path):
                    raise ValueError('Owned DOS disk or mcopy invocation changed during preparation')
                _unchanged(tool, 'mcopy executable', deadline=deadline)
                local = Path(temporary) / f'member-{index}.bin'
                local.write_bytes(data)
                member = '::/' + guest_path[3:].replace('\\', '/')
                command = [str(tool_path), '-i', image_argument, '-o' if replace else '-n',
                           str(local), member]
                timeout = _remaining(deadline)
                try:
                    subprocess.run(command, check=True, capture_output=True, timeout=timeout,
                                   stdin=subprocess.DEVNULL)
                except subprocess.TimeoutExpired as error:
                    raise TimeoutError('mcopy deadline expired while staging ' + guest_path) from error
                except (OSError, subprocess.SubprocessError) as error:
                    raise ValueError('mcopy failed while staging ' + guest_path
                                     + '; the private disk may be full or unwritable') from error
                _remaining(deadline)

        _unchanged(disk, 'DOS boot image', deadline=deadline)
        _unchanged(source, 'DOS program source', deadline=deadline)
        _unchanged(tool, 'mcopy executable', deadline=deadline)
        if (not _owned_destination(target, identity)
                or tool_path.resolve(strict=True) != tool.path):
            raise ValueError('Owned DOS disk or mcopy invocation changed during preparation')
        if target.stat().st_size != len(disk.data):
            raise ValueError('Staging changed the DOS disk size')
        with target.open('rb') as stream:
            staged_data = stream.read(len(disk.data) + 1)
        _remaining(deadline)
        if len(staged_data) != len(disk.data) or staged_data[:volume.offset + 512] != disk.data[:volume.offset + 512]:
            raise ValueError('Staging changed the DOS disk size or boot sectors')
        staged = _FATVolume(staged_data)
        for guest_path, data, _ in staged_members:
            _remaining(deadline)
            if staged.read(guest_path, maximum=MAX_IMAGE) != data:
                raise ValueError('Staged DOS member failed its byte-identity check: ' + guest_path)
        for name, data in configurations.items():
            _remaining(deadline)
            if staged.read('\\' + name, maximum=MAX_STARTUP) != data:
                raise ValueError('Staging changed the existing DOS boot configuration: ' + name)

        receipt = dict(
            format='fdisbull-dos-process-disk-1',
            original_boot_image=disk.metadata(),
            prepared_boot_image=dict(path=str(target), size=len(staged_data), sha256=_sha(staged_data)),
            program=dict(source_path=str(source.path), source_sha256=source.sha256,
                         size=len(source.data), image_format=image_format,
                         guest_path=program_path if stage_source else program_guest_path),
            helper=dict(guest_path=helper_path, size=len(helper_bytes), sha256=_sha(helper_bytes)),
            startup=dict(guest_path=startup_path, before_sha256=_sha(before_startup),
                         after_sha256=_sha(after_startup), append_hex=appended.hex(),
                         original_bytes_preserved=True),
            preserved_configuration={name: dict(size=len(data), sha256=_sha(data))
                                     for name, data in configurations.items()},
            volume=dict(format=f'FAT{volume.bits}', offset=volume.offset,
                        boot_device=volume.boot_device, boot_drive=volume.boot_drive),
            mcopy=dict(path=str(tool_path), resolved_path=str(tool.path), sha256=tool.sha256),
            runtime_validation='not_run',
            limitations=[
                'Preparation and member hashes do not prove DOS boot, startup reachability or process execution.',
                'Existing startup commands and configuration remain active and can prevent the helper from running.',
                'No driver or memory-manager runtime qualification is inferred from disk preparation.',
            ])
        _remaining(deadline)
        return receipt
    except BaseException:
        if identity is not None and _owned_destination(target, identity):
            target.unlink()
        raise
