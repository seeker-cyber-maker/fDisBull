"""An explicit native PC/DOS lane, independent of the DOSBox-in-QEMU bridge.

Admission binds a caller-owned raw disk and machine configuration. It does not
certify an operating system, installed driver, process address map or a game.
The default DOSBox lane remains available throughout the staged migration.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .qemu_machine import MachineDebugSession


PROFILE = 'dos-pc-v1'
MAX_IMAGE = 64 * 1024 * 1024
_FLOPPY_SIZES = frozenset(size * 1024 for size in (160, 180, 320, 360, 720, 1200, 1440, 2880))


def prepare_dos_profile(boot_image, *, cpu='486', memory_mib=32):
    """Read and identify one raw PC disk without modifying or booting it."""
    if cpu not in ('486', 'max'):
        raise ValueError('Native DOS CPU must be 486 or max')
    if type(memory_mib) is not int or not 16 <= memory_mib <= 8192:
        raise ValueError('Native DOS memory_mib must be an integer in 16..8192')
    path = Path(boot_image).expanduser().resolve(strict=True)
    if not path.is_file() or not 512 <= path.stat().st_size <= MAX_IMAGE:
        raise ValueError('Native DOS boot image requires 512-byte sectors, at most 64 MiB')
    with path.open('rb') as stream:
        data = stream.read(MAX_IMAGE + 1)
    if not 512 <= len(data) <= MAX_IMAGE or len(data) % 512 or data[510:512] != b'\x55\xaa':
        raise ValueError('Native DOS boot image requires complete 512-byte sectors and a boot signature')
    floppy = len(data) in _FLOPPY_SIZES
    machine = dict(cpu=cpu, memory_mib=memory_mib, cpus=1, network='none',
                   disk='private-verified-copy-and-snapshot',
                   boot_device='floppy' if floppy else 'ide', boot_drive='A:' if floppy else 'C:')
    identity = dict(schema=1, profile=PROFILE, machine=machine,
                    boot_image=dict(size=len(data), sha256=hashlib.sha256(data).hexdigest()))
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(identity, backend='qemu-dos',
                boot_image=dict(identity['boot_image'], path=str(path)), profile_sha256=digest,
                memory_manager=dict(configured='unknown', observed='unknown'),
                guest_os=dict(configured='caller-supplied boot image', observed='unknown'),
                runtime_validation='not_run',
                limitations=[
                    'Sector layout and signature are admission checks, not proof that DOS boots.',
                    'One TCG vCPU; no DOS process loader or automatic COM/MZ entry mapping.',
                    'QEMM and DESQview use their separate pinned guest profiles and live observations.',
                    'Snapshot-on disk writes are private to this run; closing discards them.',
                    'Native state restore, execution layers and frame-timed input are separate migration slices.',
                ])


def admit_dos_profile(profile, boot_image):
    """Re-read identities, validate configuration, discard asserted observations."""
    if isinstance(profile, str):
        if profile not in ('dos', PROFILE):
            raise ValueError('Unknown native DOS guest profile: ' + profile)
        return prepare_dos_profile(boot_image)
    if (not isinstance(profile, dict) or type(profile.get('schema')) is not int
            or profile.get('schema') != 1 or profile.get('profile') != PROFILE):
        raise ValueError('Expected dos-pc-v1 profile or the explicit name dos')
    machine = profile.get('machine')
    if not isinstance(machine, dict):
        raise ValueError('Native DOS machine configuration is missing')
    current = prepare_dos_profile(boot_image, cpu=machine.get('cpu'), memory_mib=machine.get('memory_mib'))
    if machine != current['machine']:
        raise ValueError('Native DOS machine configuration differs')
    recorded = profile.get('boot_image')
    if not isinstance(recorded, dict) or any(recorded.get(key) != current['boot_image'][key] for key in ('size', 'sha256')):
        raise ValueError('Native DOS guest profile input changed: boot_image')
    if profile.get('profile_sha256') != current['profile_sha256']:
        raise ValueError('Native DOS guest profile identity differs')
    return current


class QemuDOSSession(MachineDebugSession):
    """Native machine semantics; never pretend to be a DOSBox process context."""
    backend_id = 'qemu-dos'

    def __init__(self, project, executable, *, boot_image, version=None, boot_timeout_ms=30000,
                 guest_profile=None, transport='unix', firmware=None, _on_spawn=None):
        # Refuse process input before parsing a disk or probing an executable.
        selected = project.version(version)
        if project.meta['format'] != 'raw' or project.meta['arch'] != 'x86' or selected['parent'] is not None:
            raise ValueError('Native DOS launch requires an original unpatched raw x86 boot image; '
                             'COM/MZ process launch remains on backend=dosbox')
        super().__init__(project, executable, boot_image=boot_image, version=version,
                         boot_timeout_ms=boot_timeout_ms, guest_profile='dos' if guest_profile is None else guest_profile,
                         transport=transport, firmware=firmware, _on_spawn=_on_spawn)

    @staticmethod
    def _admit_guest_profile(profile, image):
        name = profile if isinstance(profile, str) else profile.get('profile') if isinstance(profile, dict) else None
        if name in ('dos', PROFILE):
            return admit_dos_profile(profile, image)
        return MachineDebugSession._admit_guest_profile(profile, image)
