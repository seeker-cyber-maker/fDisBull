"""Boot an authored sector through QEMU's default firmware lookup, without -L.

--version never loads the BIOS and cannot qualify a staged firmware bundle.
The guest writes 0x2a to isa-debug-exit; QEMU must return (0x2a << 1) | 1.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import tempfile

SECTOR = bytes.fromhex('b02ae6f4faf4ebfe').ljust(510, b'\0') + b'\x55\xaa'
EXIT_CODE = (0x2a << 1) | 1


def smoke(executable, runner=None):
    runner = runner or subprocess.run
    executable = str(Path(executable).resolve(strict=True))
    results = []
    with tempfile.TemporaryDirectory(prefix='fdisbull-ci-boot-') as temporary:
        root = Path(temporary)
        disk = root / 'authored-boot.raw'
        disk.write_bytes(SECTOR)
        for machine in ('pc', 'q35'):
            command = [executable, '-accel', 'tcg', '-machine', machine,
                       '-cpu', 'max', '-smp', '1', '-m', '64M', '-nic', 'none',
                       '-display', 'none', '-serial', 'none', '-monitor', 'none',
                       '-no-reboot', '-drive', f'file={disk},format=raw,if=ide,snapshot=on',
                       '-boot', 'order=c', '-device', 'isa-debug-exit,iobase=0xf4,iosize=4']
            try:
                result = runner(command, cwd=root, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, timeout=30)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f'{machine}: QEMU BIOS/boot smoke timed out') from exc
            if result.returncode != EXIT_CODE:
                raise RuntimeError(f'{machine}: authored boot sector did not exit via debug port '
                                   f'(expected {EXIT_CODE}, got {result.returncode}):\n{result.stdout}')
            results.append({'machine': machine, 'exit_code': result.returncode})
    return {'status': 'passed', 'boot_sector_sha256': hashlib.sha256(SECTOR).hexdigest(),
            'default_firmware_lookup': True, 'machines': results}


def relocated_smoke(executable, runner=None):
    executable = Path(executable).resolve(strict=True)
    if executable.name != 'qemu-system-x86_64' or executable.parent.name != 'bin':
        raise ValueError('Expected the staged QEMU bin/executable layout')
    bundle = executable.parent.parent
    if bundle.name != 'qemu' or bundle.parent.name != '.native-cache':
        raise ValueError('Relocation may hide only the staged .native-cache/qemu bundle')
    if not (bundle / 'share/qemu/bios-256k.bin').is_file():
        raise ValueError('Missing staged share/qemu firmware')
    hidden = bundle.with_name(bundle.name + '.relocation-hidden')
    if hidden.exists() or hidden.is_symlink():
        raise ValueError('Relocation check temporary target already exists')
    with tempfile.TemporaryDirectory(prefix='fdisbull-ci-relocated-') as temporary:
        moved = Path(temporary) / 'qemu'
        shutil.copytree(bundle, moved)
        bundle.rename(hidden)
        try:
            receipt = smoke(moved / 'bin/qemu-system-x86_64', runner)
            receipt['relocated_with_original_unavailable'] = True
            return receipt
        finally:
            hidden.rename(bundle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--relocate', action='store_true')
    args = parser.parse_args()
    result = relocated_smoke(args.executable) if args.relocate else smoke(args.executable)
    receipt = json.dumps(result, sort_keys=True, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(receipt)
    print(receipt, end='')


if __name__ == '__main__':
    main()
