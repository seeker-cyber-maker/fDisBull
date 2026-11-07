"""Reproduce the observed vendor update on private copies through fDisBull.

The patcher, payload and authored BOOT.COM are pinned. Recognized predecessor
GW/INSTALL.PRO pairs are declared below; auxiliary files are snapshotted and
must stay byte-identical. Completion requires the exact armed endpoint and
whole expected outputs. Independent-candidate differences remain evidence.
The DOS A: alias is not a physical-floppy compatibility test or a bindiff engine.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from check_gw_update import compare, reconstruct
from native_witness_checks import (file_effects, identity, manifest, new_private_output,
                                   read_file, require_hash, snapshot_directory,
                                   verify_completion)


PATCHER_SHA = '0008d6360c1c7bba04993c43c665305900fbd37921a63e5dac84eb3d8022e32d'
BOOTSTRAP_SHA = '3c78f20af9395b16e17b499f2d1c474db6eaf9726b3666b51ff9ec43d711ab17'
FINISHED = '1000:0143'
FAILED = '1000:0145'
PREDECESSORS = {
    ('ee33ab12beceedc1f9725950009d12d82beeca8c919f4078777592ff8203e5cc',
     'c8adc8dc04b3b68800de570a5e5fc18a4e5479c2c985ecc4980d4896fdec5ee1'): 'supplied_30_donor',
    ('d4f393dbe743bf8cfa9c42d584a727bed5ced225f9be454f24b1ad9844202f26',
     'dbae55cecfb988439a6b1125ceaf1f611aa2f5a3a6268d25cba2142d8ba67b5d'): 'preserved_30a_disk',
    ('d4f393dbe743bf8cfa9c42d584a727bed5ced225f9be454f24b1ad9844202f26',
     '3b0cb4994540852e801d768ca51231e97f014881d1e49b9d1cb0c109139fc945'): 'donor_updated_30a',
}


def predecessor_profile(files):
    if not {'GW', 'INSTALL.PRO'} <= files.keys():
        raise ValueError('Predecessor must contain GW and INSTALL.PRO under their DOS names')
    pair = (identity(files['GW'])['sha256'], identity(files['INSTALL.PRO'])['sha256'])
    if pair not in PREDECESSORS:
        raise ValueError('Predecessor pair is outside the inspected input profiles')
    return PREDECESSORS[pair]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('before', 'patch', 'candidate', 'bootstrap', 'emulator', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(argv)
    output = new_private_output(args.output)
    mounted = output / 'disk'
    mounted.mkdir(mode=0o700)
    report = {'format': 'gamewizard-native-patch-experiment-2', 'qualified': False,
              'completed_at_bootstrap': False, 'observations': [],
              'mount_model': 'one private C directory; DOS SUBST alias A to that same directory',
              'candidate_matching_is_not_qualification': True}
    before, expected, final = {}, {}, None

    def observe(debug, project, label):
        screen = debug.screenshot(label + '.png', hooks=False)
        image = output / (label + '.png')
        project.debug_export(screen['artifact'], image)
        ocr = subprocess.run(['tesseract', str(image), 'stdout', '--psm', '6'],
                             text=True, capture_output=True, check=True, timeout=30)
        lines = ocr.stdout.splitlines()
        report['observations'].append({'label': label, 'text': lines,
                                       'screenshot': identity(image.read_bytes()),
                                       'registers': debug.registers()})
        print(json.dumps({'label': label, 'text': lines}), flush=True)
        return '\n'.join(lines)

    try:
        before = snapshot_directory(args.before)
        report['predecessor_profile'] = predecessor_profile(before)
        candidate = snapshot_directory(args.candidate)
        if not {'GW', 'INSTALL.PRO'} <= candidate.keys():
            raise ValueError('Independent candidate lacks GW or INSTALL.PRO')
        patcher = read_file(args.patch / 'GW_PATCH.EXE')
        patch = read_file(args.patch / 'GWPRO30A.UPD')
        bootstrap = read_file(args.bootstrap)
        report['patcher'] = require_hash(patcher, PATCHER_SHA, 'GW_PATCH.EXE')
        report['bootstrap'] = require_hash(bootstrap, BOOTSTRAP_SHA, 'BOOT.COM')
        report['bootstrap_sha256'] = BOOTSTRAP_SHA
        # reconstruct pins the exact UPD length/hash before producing any output.
        predicted = reconstruct(before['INSTALL.PRO'], patch)
        report['patch_payload'] = identity(patch)
        report['backend_launcher'] = identity(read_file(args.emulator))
        staged = {'GW_PATCH.EXE': patcher, 'GWPRO30A.UPD': patch, 'BOOT.COM': bootstrap}
        if {name.casefold() for name in before} & {name.casefold() for name in staged}:
            raise ValueError('Predecessor already contains a reserved experiment filename')
        before = {**before, **staged}
        expected = {**before, **predicted}
        for name, data in before.items():
            with (mounted / name).open('xb') as stream:
                stream.write(data)
        if snapshot_directory(mounted) != before:
            raise ValueError('Mounted input copies differ from the admitted byte snapshots')
        report['initial_files'] = manifest(before)
        report['candidate_files'] = manifest(candidate)

        from fdisbull import __version__
        from fdisbull.project import Project
        report['fdisbull_version'] = __version__
        with Project.create(output / 'patch.fdb', mounted / 'BOOT.COM', image='com') as project:
            project.analyze(start=FINISHED, max_instructions=4)
            project.analyze(start=FAILED, max_instructions=8)
            with project.debugger(str(args.emulator), mounted) as debug:
                report['run_id'] = debug.run_id
                report['completion_breakpoint'] = debug.breakpoint(FINISHED)
                report['failure_breakpoint'] = debug.breakpoint(FAILED)
                report['initial_run'] = debug.run(guest_ms=500, timeout_ms=5000, fast_forward=True)
                prompt = observe(debug, project, 'prompt')
                if 'installation disk' not in prompt or 'A:' not in prompt or 'B:' not in prompt:
                    raise RuntimeError('Expected vendor drive prompt not observed; no key sent')
                debug.keyboard_type('A')
                report['completion_run'] = debug.run(timeout_ms=15000, fast_forward=True)
                report['final_registers'] = debug.registers()
                report['completion_verification'] = verify_completion(
                    report['completion_breakpoint'], report['completion_run'], report['final_registers'],
                    run_id=debug.run_id, offset=0x143)
                report['completed_at_bootstrap'] = True
                report['raw_child_eax'] = report['final_registers']['general']['eax']
                observe(debug, project, 'result')
        final = snapshot_directory(mounted)
        report['output_verification'] = file_effects(before, expected, final)
        report['candidate_comparison'] = [
            {'name': name, **compare(final[name], candidate[name])}
            for name in sorted(final.keys() & candidate.keys())]
        report['candidate_only_files'] = sorted(candidate.keys() - final.keys())
        report['observed_only_files'] = sorted(final.keys() - candidate.keys())
        if not report['output_verification']['all_expected_file_bytes_match']:
            raise RuntimeError('Complete file effects do not match the inspected update recipe')
        report['qualified'] = True
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        try:
            if final is None:
                final = snapshot_directory(mounted)
            report['final_files'] = manifest(final)
            if expected:
                report['output_verification'] = file_effects(before, expected, final)
                report['changed_files'] = report['output_verification']['changed_files']
        except Exception as error:
            report['qualified'] = False
            report['final_inventory_error'] = {'type': type(error).__name__, 'message': str(error)}
        with (output / 'receipt.json').open('x') as receipt:
            receipt.write(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'receipt': str(output / 'receipt.json'),
                          'qualified': report['qualified'], 'changed_files': report.get('changed_files'),
                          'completed_at_bootstrap': report['completed_at_bootstrap']}), flush=True)
    if not report['qualified']:
        raise RuntimeError('Native experiment remains unqualified; inspect its receipt')


if __name__ == '__main__':
    main()
