# SPDX-License-Identifier: GPL-2.0-or-later
"""Exact registration planning against clean QEMU or the prepared AGI companion."""
import hashlib
from pathlib import Path

REGISTRATIONS = {
    'hw/Kconfig': ('f7940f36d1aa7b15a554f6378be03a85ddc9a40e2608b107c9d7c5dd2ccbe3d0',
        'source avr/Kconfig\n', 'source avr/Kconfig\nsource scumm/Kconfig\n', 'source avr/Kconfig\nsource agi/Kconfig\n'),
    'hw/meson.build': ('c3bc3f1e22ff16eea62af2e2fe8642d1d683e9ec8307c5f05ba5d66171678d5b',
        "subdir('avr')\n", "subdir('avr')\nsubdir('scumm')\n", "subdir('avr')\nsubdir('agi')\n"),
    'target/Kconfig': ('ac823c76c3267069432d63943e82cb067fb9ead2451785b798558457327e6544',
        'source avr/Kconfig\n', 'source avr/Kconfig\nsource scumm/Kconfig\n', 'source avr/Kconfig\nsource agi/Kconfig\n'),
    'target/meson.build': ('43d9537ac1fc911a9c76cd03ddc59753795e2acb3e76de4a9f0ba683c49f345b',
        "subdir('avr')\n", "subdir('avr')\nsubdir('scumm')\n", "subdir('avr')\nsubdir('agi')\n"),
    'include/system/arch_init.h': ('2bed554869e91d03a85060eb3e006592b7cf3488c029edab55c6a3f23201e20f',
        '    QEMU_ARCH_LOONGARCH = (1 << 23),\n', '    QEMU_ARCH_LOONGARCH = (1 << 23),\n    QEMU_ARCH_SCUMM = (1 << 26),\n', '    QEMU_ARCH_LOONGARCH = (1 << 23),\n    QEMU_ARCH_AGI = (1 << 25),\n'),
    'qapi/machine.json': ('78f0ecaa75dbb8c69c93cefe915e735fddb49de315bd267d5fd92f5678f961f6',
        "  'data' : [ 'aarch64', 'alpha', 'arm', 'avr', 'hppa', 'i386',\n", "  'data' : [ 'aarch64', 'scumm', 'alpha', 'arm', 'avr', 'hppa', 'i386',\n", "  'data' : [ 'aarch64', 'agi', 'alpha', 'arm', 'avr', 'hppa', 'i386',\n"),
}

def plan_registration(relative, current):
    expected, old, scumm, agi = REGISTRATIONS[relative]
    old, scumm, agi = (x.encode() for x in (old, scumm, agi))
    both = agi.replace(old, scumm, 1) if old in agi else scumm.replace(b"'aarch64',", b"'aarch64', 'agi',", 1)
    candidates = []
    for form, out in ((old, scumm), (scumm, scumm), (agi, both), (both, both)):
        if current.count(form) != 1:
            continue
        base = current.replace(form, old, 1)
        if hashlib.sha256(base).hexdigest() == expected:
            candidates.append(base.replace(old, out, 1))
    if len(candidates) != 1:
        raise ValueError(f'unrecognized or ambiguous registration: {relative}')
    return candidates[0]

if __name__ == '__main__':
    import sys
    root = Path(sys.argv[1])
    for path, (_, old, scumm, agi) in REGISTRATIONS.items():
        before = (root / path).read_bytes()
        after = plan_registration(path, before)
        assert plan_registration(path, after) == after
        assert b'agi' in after.lower() and b'scumm' in after.lower()
        # Corrupt any unrelated byte: exact hash guard must refuse.
        try:
            plan_registration(path, before + b'\n')
        except ValueError:
            pass
        else:
            raise AssertionError('accepted altered base')
        print(path, hashlib.sha256(before).hexdigest(), hashlib.sha256(after).hexdigest())
