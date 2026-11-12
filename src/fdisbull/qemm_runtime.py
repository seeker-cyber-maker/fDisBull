"""Read-only admission of caller-owned DOS images configured for QEMM.

Configuration proves which declared driver is in an image, not that DOS booted
or that QEMM is active. Runtime QPI observations are a separate source of evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import struct


PROFILE = 'qemm-386-v1'
MAX_IMAGE = 64 * 1024 * 1024
MAX_CONFIG = 65536
_MACHINE = dict(cpu='486', memory_mib=32, cpus=1, network='none', disk='private-verified-copy-and-snapshot')
_FLOPPY_SIZES = {size * 1024 for size in (160, 180, 320, 360, 720, 1200, 1440, 2880)}
_COMPETING = {
    'emm386', 'jemm386', 'jemmex', '386max', 'bluemax', 'rm386', 'netroom',
    'qemmxms', 'qemm', 'himem', 'himemx', 'xmgr', 'umm', 'umbpci',
}
_MANAGER_TOKEN = re.compile(
    r'(?i)(?<![\w.-])((?:qemm386|emm386|jemm386|jemmex|386max|bluemax|rm386|netroom|qemmxms|qemm|himemx?|xmgr|umm|umbpci)\.(?:sys|exe))(?![\w.-])')
_SHORT_PART = re.compile(r"^[A-Za-z0-9!#$%&'()@^_`{}~+\-]{1,8}(?:\.[A-Za-z0-9!#$%&'()@^_`{}~+\-]{1,3})?$")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _file(path, maximum, label):
    selected = Path(path).expanduser().resolve(strict=True)
    if not selected.is_file() or selected.stat().st_size > maximum:
        raise ValueError(f'{label} must be a regular file no larger than {maximum} bytes')
    with selected.open('rb') as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError(f'{label} changed beyond its size budget')
    return selected, data


def _dos_parts(path, *, boot_drive=None):
    if not isinstance(path, str) or not path or '/' in path:
        raise ValueError('QEMM driver requires a DOS short path on the supplied boot volume')
    value = PureWindowsPath(path)
    if value.drive and value.drive.upper() not in ('A:', 'C:'):
        raise ValueError('QEMM driver must be on the supplied boot volume (A: floppy or C: IDE disk)')
    if value.drive and boot_drive is not None and value.drive.upper() != boot_drive:
        raise ValueError('QEMM driver path does not match the selected boot drive ' + boot_drive)
    if value.drive and not value.root:
        raise ValueError('Drive-relative QEMM paths are ambiguous; use an absolute or root-relative path')
    parts = value.parts[1:] if value.anchor else value.parts
    if not parts or any(not _SHORT_PART.fullmatch(part) for part in parts):
        raise ValueError('QEMM driver requires unambiguous DOS 8.3 path components')
    return [part.upper() for part in parts]


def _config_lines(text):
    if not isinstance(text, str):
        raise ValueError('CONFIG.SYS must be text')
    try:
        encoded = text.encode('cp437')
    except UnicodeEncodeError as error:
        raise ValueError('CONFIG.SYS must be representable as DOS CP437 text') from error
    if len(encoded) > MAX_CONFIG or '\0' in text:
        raise ValueError('CONFIG.SYS contains NUL or exceeds 64 KiB')
    if '\x1a' in text:
        before, after = text.split('\x1a', 1)
        if after.strip(' \t\r\n\x1a'):
            raise ValueError('CONFIG.SYS has nonempty data after its DOS EOF marker')
        text = before
    devices = []
    for number, original in enumerate(text.splitlines(), 1):
        line = original.strip()
        if not line or line.startswith(';') or re.match(r'(?i)^rem(?:\s|$)', line):
            continue
        if line.startswith('[') or re.match(r'(?i)^(?:include|menuitem|menudefault|submenu)\b', line):
            raise ValueError('QEMM profile requires one unconditional CONFIG.SYS; menu/include selection is unsupported')
        match = re.match(r'(?i)^(device(?:high)?)(?:\s+/[^=]+)?\s*=\s*(.+)$', line)
        referenced = [item.lower() for item in _MANAGER_TOKEN.findall(line)]
        competing = [item for item in referenced if item.rsplit('.', 1)[0] in _COMPETING]
        if competing:
            raise ValueError('Competing memory manager in CONFIG.SYS: ' + ', '.join(competing))
        if not match:
            if referenced or re.match(r'(?i)^device(?:high)?\?', line):
                raise ValueError('Memory-manager loading must use an unconditional DEVICE= declaration')
            continue
        command, remainder = match.groups()
        target = re.match(r'^"([^"\r\n]+)"(?:\s+(.*))?$|^(\S+)(?:\s+(.*))?$', remainder)
        if target is None:
            raise ValueError('Malformed CONFIG.SYS device path')
        path = target.group(1) or target.group(3)
        options = target.group(2) or target.group(4) or ''
        basename = PureWindowsPath(path).name.lower()
        if basename.rsplit('.', 1)[0] in _COMPETING:
            raise ValueError('Competing memory manager in CONFIG.SYS: ' + basename)
        if basename == 'qemm386.sys':
            if command.lower() != 'device':
                raise ValueError('QEMM386.SYS must load with DEVICE=, not DEVICEHIGH=')
            _dos_parts(path)
        elif referenced:
            raise ValueError('Indirect memory-manager loading is unsupported in the QEMM profile')
        devices.append(dict(line=number, command=command.upper(), path=path, options=options))
    return devices


def validate_qemm_config(config_sys):
    """Validate a single unconditional DOS configuration without changing it."""
    devices = _config_lines(config_sys)
    qemm = [item for item in devices if PureWindowsPath(item['path']).name.lower() == 'qemm386.sys']
    if len(qemm) != 1:
        raise ValueError('CONFIG.SYS must contain exactly one DEVICE=QEMM386.SYS declaration')
    return dict(driver=qemm[0], other_devices=[item for item in devices if item is not qemm[0]],
                selection='unconditional', competing_memory_managers=[],
                scope='declared CONFIG.SYS drivers; runtime installation is not established')


def prepare_qemm_config(config_sys='', *, qemm_path=r'C:\QEMM\QEMM386.SYS', options='RAM'):
    """Return a CONFIG.SYS preview; never edit a disk image or caller file.

    An existing QEMM declaration retains its original options. Conflicting
    managers and conditional configurations refuse instead of being rewritten.
    """
    _dos_parts(qemm_path)
    if PureWindowsPath(qemm_path).name.upper() != 'QEMM386.SYS':
        raise ValueError('The QEMM driver filename must be QEMM386.SYS')
    if not isinstance(options, str) or len(options) > 4096 or any(ord(c) < 32 or ord(c) > 126 for c in options):
        raise ValueError('QEMM options must be a single bounded ASCII line')
    devices = _config_lines(config_sys)
    present = any(PureWindowsPath(item['path']).name.lower() == 'qemm386.sys' for item in devices)
    # DOS EOF belongs at the end, including when an earlier file omitted CRLF.
    lines = config_sys.split('\x1a', 1)[0].splitlines()
    if not present:
        lines.insert(0, 'DEVICE=' + qemm_path + (' ' + options.strip() if options.strip() else ''))
    text = '\r\n'.join(lines) + '\r\n'
    checked = validate_qemm_config(text)
    return dict(config_sys=text, sha256=_digest(text.encode('cp437')), validation=checked,
                changed=text != config_sys, applied_to_image=False,
                note='Preview only; install this configuration and your own driver in a private DOS boot image.')


class _FATVolume:
    """Bounded FAT12/16 member reads, not a general filesystem implementation."""

    def __init__(self, data):
        self.data = data
        if len(data) < 512 or len(data) % 512 or data[510:512] != b'\x55\xaa':
            raise ValueError('QEMM image requires complete 512-byte sectors and a boot signature')
        self.offset = 0
        self.partition = None
        if not self._plausible_bpb(data[:512]):
            candidates = []
            active = []
            for index in range(4):
                entry = data[446 + 16 * index:462 + 16 * index]
                status, kind = entry[0], entry[4]
                first, count = struct.unpack_from('<II', entry, 8)
                if status not in (0, 0x80):
                    raise ValueError('Invalid MBR partition status')
                if status == 0x80:
                    active.append(index)
                if kind in (0x01, 0x04, 0x06, 0x0e) and first and count:
                    candidates.append((index, first, count))
            if len(active) > 1:
                raise ValueError('Multiple active boot partitions are ambiguous')
            if active:
                candidates = [item for item in candidates if item[0] == active[0]]
            if len(candidates) != 1:
                raise ValueError('QEMM profile requires one selected primary FAT12/16 boot volume')
            self.partition, first, count = candidates[0]
            self.offset = first * 512
            if self.offset + count * 512 > len(data):
                raise ValueError('FAT partition extends beyond the boot image')
            self.partition_size = count * 512
        else:
            self.partition_size = len(data)
        boot = data[self.offset:self.offset + 512]
        if len(boot) != 512 or boot[510:512] != b'\x55\xaa' or not self._plausible_bpb(boot):
            raise ValueError('Unsupported or malformed FAT12/16 BIOS parameter block')
        self.sectors_per_cluster = boot[13]
        reserved = struct.unpack_from('<H', boot, 14)[0]
        copies = boot[16]
        root_count = struct.unpack_from('<H', boot, 17)[0]
        sectors = struct.unpack_from('<H', boot, 19)[0] or struct.unpack_from('<I', boot, 32)[0]
        fat_sectors = struct.unpack_from('<H', boot, 22)[0]
        root_sectors = (root_count * 32 + 511) // 512
        first_data = reserved + copies * fat_sectors + root_sectors
        if sectors * 512 > self.partition_size or first_data >= sectors:
            raise ValueError('FAT data layout extends beyond the selected volume')
        self.clusters = (sectors - first_data) // self.sectors_per_cluster
        if self.clusters < 1 or self.clusters >= 65525:
            raise ValueError('Only FAT12/16 volumes are supported by the QEMM profile')
        self.bits = 12 if self.clusters < 4085 else 16
        self.boot_device = 'floppy' if self.partition is None and self.bits == 12 and len(data) in _FLOPPY_SIZES else 'ide'
        self.boot_drive = 'A:' if self.boot_device == 'floppy' else 'C:'
        self.cluster_size = self.sectors_per_cluster * 512
        self.data_offset = self.offset + first_data * 512
        fat_start = self.offset + reserved * 512
        fat_size = fat_sectors * 512
        self.fat = data[fat_start:fat_start + fat_size]
        required_fat = ((self.clusters + 2) * self.bits + 7) // 8
        if len(self.fat) < required_fat:
            raise ValueError('FAT is too short for the declared cluster count')
        for copy in range(1, copies):
            if data[fat_start + copy * fat_size:fat_start + (copy + 1) * fat_size] != self.fat:
                raise ValueError('FAT copies disagree; QEMM profile will not choose one silently')
        root_start = self.offset + (reserved + copies * fat_sectors) * 512
        self.root = data[root_start:root_start + root_count * 32]

    @staticmethod
    def _plausible_bpb(boot):
        return (len(boot) == 512 and struct.unpack_from('<H', boot, 11)[0] == 512
                and boot[13] in (1, 2, 4, 8, 16, 32, 64, 128)
                and struct.unpack_from('<H', boot, 14)[0] > 0
                and boot[16] in (1, 2)
                and 0 < struct.unpack_from('<H', boot, 17)[0] <= 2048
                and struct.unpack_from('<H', boot, 22)[0] > 0)

    def _next(self, cluster):
        offset = cluster * 2 if self.bits == 16 else cluster + cluster // 2
        value = struct.unpack_from('<H', self.fat, offset)[0]
        return value if self.bits == 16 else (value >> 4 if cluster & 1 else value & 0xfff)

    def _chain(self, cluster, *, length=None, maximum=1024 * 1024):
        if length == 0:
            return b''
        chunks = []
        seen = set()
        total = 0
        while True:
            reserved = 0xff0 if self.bits == 12 else 0xfff0
            if cluster < 2 or cluster >= self.clusters + 2 or cluster >= reserved or cluster in seen:
                raise ValueError('Invalid or cyclic FAT cluster chain')
            seen.add(cluster)
            start = self.data_offset + (cluster - 2) * self.cluster_size
            chunk = self.data[start:start + self.cluster_size]
            if len(chunk) != self.cluster_size:
                raise ValueError('Truncated FAT data cluster')
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum + self.cluster_size - 1:
                raise ValueError('FAT member exceeds its bounded read budget')
            if length is not None and total >= length:
                return b''.join(chunks)[:length]
            cluster = self._next(cluster)
            if cluster >= (0xff8 if self.bits == 12 else 0xfff8):
                if length is not None:
                    raise ValueError('FAT member is shorter than its directory length')
                return b''.join(chunks)

    @staticmethod
    def _entry(directory, part):
        base, _, extension = part.partition('.')
        wanted = (base.ljust(8) + extension.ljust(3)).encode('ascii')
        matches = []
        for offset in range(0, len(directory), 32):
            entry = directory[offset:offset + 32]
            if len(entry) != 32 or entry[0] == 0:
                break
            if entry[0] == 0xe5 or entry[11] & 0x08 or entry[11] == 0x0f:
                continue
            if entry[:11].upper() == wanted:
                matches.append(entry)
        if len(matches) != 1:
            raise ValueError('Missing or duplicate DOS image member: ' + part)
        return matches[0]

    def read(self, path, *, maximum):
        parts = _dos_parts(path, boot_drive=self.boot_drive)
        directory = self.root
        for index, part in enumerate(parts):
            entry = self._entry(directory, part)
            cluster = struct.unpack_from('<H', entry, 26)[0]
            if index != len(parts) - 1:
                if not entry[11] & 0x10:
                    raise ValueError('Non-directory in DOS image member path')
                directory = self._chain(cluster)
            else:
                length = struct.unpack_from('<I', entry, 28)[0]
                if entry[11] & 0x10 or length > maximum:
                    raise ValueError('DOS image member is a directory or exceeds its size budget')
                return self._chain(cluster, length=length, maximum=maximum)


def prepare_qemm_profile(boot_image, *, config_sys=None, driver_path=None):
    """Inspect a private FAT12/16 boot image and return a hash-bound profile.

    Optional external files must exactly match the selected image's CONFIG.SYS
    and QEMM386.SYS. No source disk, configuration, or target bytes are changed.
    """
    image, data = _file(boot_image, MAX_IMAGE, 'DOS boot image')
    volume = _FATVolume(data)
    config = volume.read(r'\CONFIG.SYS', maximum=MAX_CONFIG)
    checked = validate_qemm_config(config.decode('cp437'))
    driver = volume.read(checked['driver']['path'], maximum=16 * 1024 * 1024)
    driver_guest_path = volume.boot_drive + '\\' + '\\'.join(_dos_parts(checked['driver']['path'], boot_drive=volume.boot_drive))
    image_offset = struct.unpack_from('<H', driver, 8)[0] * 16 if len(driver) >= 28 and driver[:2] == b'MZ' else 0
    if image_offset + 18 > len(driver) or driver[image_offset + 10:image_offset + 18] != b'QEMM386$':
        raise ValueError('Configured QEMM386.SYS does not contain the expected DOS device header')
    attributes, strategy, interrupt = struct.unpack_from('<3H', driver, image_offset + 4)
    if not attributes & 0x8000 or not all(18 <= entry < len(driver) - image_offset for entry in (strategy, interrupt)):
        raise ValueError('Configured QEMM386.SYS has an invalid character-driver header or entry extent')
    for path, expected, label in ((config_sys, config, 'CONFIG.SYS'), (driver_path, driver, 'QEMM386.SYS')):
        if path is not None:
            _, supplied = _file(path, MAX_CONFIG if label == 'CONFIG.SYS' else 16 * 1024 * 1024, label)
            if supplied != expected:
                raise ValueError(label + ' does not match the member inside the boot image')
    result = dict(schema=1, profile=PROFILE, backend='qemu-machine',
                boot_image=dict(path=str(image), size=len(data), sha256=_digest(data)),
                volume=dict(format='FAT' + str(volume.bits), offset=volume.offset, partition=volume.partition, drive=volume.boot_drive),
                config_sys=dict(guest_path=volume.boot_drive + r'\CONFIG.SYS', size=len(config), sha256=_digest(config), validation=checked),
                qemm_driver=dict(guest_path=driver_guest_path, size=len(driver), sha256=_digest(driver), device_name='QEMM386$'),
                machine=dict(_MACHINE, boot_device=volume.boot_device, boot_drive=volume.boot_drive),
                memory_manager=dict(configured='qemm', observed='unknown',
                                    configuration_scope='CONFIG.SYS and driver bytes read from the selected boot image'),
                limitations=['Configuration is not proof of a bootable DOS installation or an active QEMM manager.',
                             'Only one unconditional CONFIG.SYS on a primary FAT12/16 volume is admitted.',
                             'Other drivers, AUTOEXEC programs and operating-system implicit loading are not dynamically qualified.',
                             'QPI version/status and actual CPU paging require separate live observations.'])
    identity = dict(schema=result['schema'], profile=result['profile'], machine=result['machine'],
                    inputs={key: result[key]['sha256'] for key in ('boot_image', 'config_sys', 'qemm_driver')})
    result['profile_sha256'] = _digest(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode())
    return result


def admit_qemm_profile(profile, boot_image):
    """Re-read the selected image at launch; never trust supplied observation labels."""
    if isinstance(profile, str):
        if profile not in ('qemm', PROFILE):
            raise ValueError('Unknown machine guest profile: ' + profile)
        return prepare_qemm_profile(boot_image)
    if (not isinstance(profile, dict) or type(profile.get('schema')) is not int
            or profile.get('schema') != 1 or profile.get('profile') != PROFILE):
        raise ValueError('Expected qemm-386-v1 profile or the explicit name qemm')
    current = prepare_qemm_profile(boot_image)
    for field in ('boot_image', 'config_sys', 'qemm_driver'):
        recorded = profile.get(field)
        if not isinstance(recorded, dict) or any(recorded.get(key) != current[field][key] for key in ('size', 'sha256')):
            raise ValueError('QEMM guest profile input changed: ' + field)
    if profile.get('machine') != current['machine']:
        raise ValueError('QEMM guest profile machine configuration differs')
    if profile.get('profile_sha256') != current['profile_sha256']:
        raise ValueError('QEMM guest profile identity differs')
    return current
