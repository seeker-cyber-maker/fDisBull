"""Execute hash-pinned GW_FIX on private copies through public fDisBull APIs.

The original executable, configuration and authored wrapper are pinned before
execution. A qualified receipt requires the exact armed completion breakpoint,
final CS:IP and complete expected file effects. AL and screenshot OCR alone are
not success tests. Failed experiments retain an explicitly unqualified receipt.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from native_witness_checks import (file_effects, identity, manifest, new_private_output,
                                   read_file, require_hash, snapshot_directory,
                                   verify_completion)


PATCHER_SHA = '14a89ef5b5249a531f2905c69818a67d79ec968de04a2574723063636eadec49'
CONFIG_SHA = '83df921317a0717c88c429ee638d34be7a2e9c58b1b9f674f2e1af493c25d0b2'
BOOTSTRAP_SHA = '215a04a9c18686e0710303f01498bbac7f6fe96bfe1ab53a71a2259dd57ff964'
FINISHED = '1000:012d'
FAILED = '1000:012f'
CASES = ('real', 'already_fixed', 'wrong_byte', 'short', 'missing')


def config_case(original, case):
    """Declare one derivative of the pinned configuration, not a general fix."""
    if len(original) <= 16:
        raise ValueError('The original configuration lacks offset 0x10')
    fixed = original[:16] + b'\x6a' + original[17:]
    if case == 'real':
        return original, fixed
    if case == 'already_fixed':
        return fixed, fixed
    if case == 'wrong_byte':
        wrong = original[:16] + b'\x55' + original[17:]
        return wrong, wrong
    if case == 'short':
        return original[:16], original[:16] + b'\x6a'
    if case == 'missing':
        return None, None
    raise ValueError('Unknown configuration case')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('patcher', 'config', 'bootstrap', 'emulator', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--case', choices=CASES, required=True)
    args = parser.parse_args(argv)
    output = new_private_output(args.output)
    disk = output / 'disk'
    disk.mkdir(mode=0o700)
    report = {'schema': 'gw32-fix-native-case-2', 'case': args.case,
              'qualified': False, 'observations': []}
    before, expected, final = {}, {}, None

    def observe(project, debug, label):
        screen = debug.screenshot(label + '.png', hooks=False)
        path = output / (label + '.png')
        project.debug_export(screen['artifact'], path)
        ocr = subprocess.run(['tesseract', str(path), 'stdout', '--psm', '6'], text=True,
                             capture_output=True, check=True, timeout=30)
        entry = {'label': label, 'ocr': ocr.stdout.splitlines(),
                 'registers': debug.registers(), 'screenshot': identity(path.read_bytes())}
        report['observations'].append(entry)
        print(json.dumps({'case': args.case, 'label': label, 'ocr': entry['ocr']}), flush=True)
        return ocr.stdout

    try:
        patcher, original, bootstrap = (read_file(args.patcher), read_file(args.config),
                                        read_file(args.bootstrap))
        report['patcher'] = require_hash(patcher, PATCHER_SHA, 'GW_FIX.EXE')
        report['original_config'] = require_hash(original, CONFIG_SHA, 'GW.CFG')
        report['bootstrap'] = require_hash(bootstrap, BOOTSTRAP_SHA, 'BOOT.COM')
        report['backend_launcher'] = identity(read_file(args.emulator))
        config, config_after = config_case(original, args.case)
        before = {'GW_FIX.EXE': patcher, 'BOOT.COM': bootstrap}
        if config is not None:
            before['GW.CFG'] = config
        expected = dict(before)
        if config_after is not None:
            expected['GW.CFG'] = config_after
        for name, data in before.items():
            with (disk / name).open('xb') as stream:
                stream.write(data)
        if snapshot_directory(disk) != before:
            raise ValueError('Mounted input copies differ from the admitted byte snapshots')
        report.update(initial_files=manifest(before),
                      authored_context='pinned configuration or declared derivative; bootstrap DF=0; private DOS directory')

        from fdisbull import __version__
        from fdisbull.project import Project
        report['fdisbull_version'] = __version__
        with Project.create(output / 'fix.fdb', disk / 'BOOT.COM', image='com') as project:
            project.analyze(start=FINISHED, max_instructions=4)
            project.analyze(start=FAILED, max_instructions=4)
            with project.debugger(str(args.emulator), disk) as debug:
                report['run_id'] = debug.run_id
                report['completion_breakpoint'] = debug.breakpoint(FINISHED)
                report['failure_breakpoint'] = debug.breakpoint(FAILED)
                report['initial_run'] = debug.run(guest_ms=250, timeout_ms=5000, fast_forward=True)
                prompt = observe(project, debug, 'prompt')
                if 'Press' not in prompt or 'Key' not in prompt:
                    raise RuntimeError('Expected original key prompt was not observed; no key sent')
                debug.keyboard_type('x')
                report['completion_run'] = debug.run(timeout_ms=5000, fast_forward=True)
                report['final_registers'] = debug.registers()
                report['completion_verification'] = verify_completion(
                    report['completion_breakpoint'], report['completion_run'], report['final_registers'],
                    run_id=debug.run_id, offset=0x12D)
                observe(project, debug, 'result')
        final = snapshot_directory(disk)
        report['output_verification'] = file_effects(before, expected, final)
        if not report['output_verification']['all_expected_file_bytes_match']:
            raise RuntimeError('Complete file effects do not match the declared configuration case')
        report['qualified'] = True
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        try:
            if final is None:
                final = snapshot_directory(disk)
            report['final_files'] = manifest(final)
            if expected:
                report['output_verification'] = file_effects(before, expected, final)
                report['changed_files'] = report['output_verification']['changed_files']
            if 'GW.CFG' in final:
                after = final['GW.CFG']
                report['config_after'] = identity(after)
                original_case = before.get('GW.CFG', b'')
                report['config_difference_offsets'] = [i for i in range(max(len(original_case), len(after)))
                    if i >= len(original_case) or i >= len(after) or original_case[i] != after[i]]
                report['byte_0x10_after'] = after[16] if len(after) > 16 else None
        except Exception as error:
            report['qualified'] = False
            report['final_inventory_error'] = {'type': type(error).__name__, 'message': str(error)}
        with (output / 'receipt.json').open('x') as receipt:
            receipt.write(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'case': args.case, 'receipt': str(output / 'receipt.json'),
                          'qualified': report['qualified'], 'changed_files': report.get('changed_files'),
                          'config_after': report.get('config_after')}), flush=True)
    if not report['qualified']:
        raise RuntimeError('Native experiment remains unqualified; inspect its receipt')


if __name__ == '__main__':
    main()
