#!/usr/bin/env python3
"""Run a fixed native fixture gate; a normal pytest run may silently skip it."""
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
HEADLESS = (
    'tests/test_native_overlay.py::test_native_headless_refuses_host_owner_without_mutation',
    'tests/test_native_overlay.py::test_native_restore_rejects_stale_generation_and_fences_failed_load',
    'tests/test_native_overlay.py::test_native_restore_receipt_preserves_owner_and_advances_generation',
    'tests/test_playable_native.py::test_original_mz_entry_and_relocation_with_standalone_runtime',
)
VISIBLE = (
    'tests/test_native_overlay.py::test_native_visible_owner_transfers_reset_and_reject_stale_inputs',
    'tests/test_harness_native.py::test_controls_learned_during_human_play_survive_service_restart',
    'tests/test_playable_native.py::test_real_game_survives_clients_and_native_ownership_changes',
    'tests/test_playable_native.py::test_default_native_desktop_path_blocks_direct_agent_input',
)
TESTS = {'all': HEADLESS + VISIBLE, 'headless': HEADLESS, 'visible': VISIBLE}


def classify_result(junit_path, selected_tests, *, pytest_exit_code, binary_stable):
    """Classify reported execution, without claiming a binary's build provenance."""
    reasons = []
    summary = {'case_count': 0, 'cases': [], 'skipped': 0, 'failure': 0,
               'error': 0, 'read_error': None}
    try:
        root = ET.parse(junit_path).getroot()
        if root.tag not in ('testsuite', 'testsuites'):
            raise ValueError('Unrecognized JUnit root')
        cases = list(root.iter('testcase'))
        summary['cases'] = [
            case.get('classname', '').replace('.', '/') + '.py::' + case.get('name', '')
            for case in cases]
        summary['case_count'] = len(cases)
        for kind in ('skipped', 'failure', 'error'):
            summary[kind] = sum(1 for _ in root.iter(kind))
        if Counter(summary['cases']) != Counter(selected_tests):
            reasons.append('JUnit cases do not exactly match the selected tests')
        if any(summary[kind] for kind in ('skipped', 'failure', 'error')):
            reasons.append('JUnit contains skipped, failed, or errored tests')
    except (OSError, ET.ParseError, ValueError) as error:
        summary['read_error'] = str(error)
        reasons.append('JUnit report is missing or invalid')
    if type(pytest_exit_code) is not int or pytest_exit_code != 0:
        reasons.append('pytest did not exit successfully')
    if binary_stable is not True:
        reasons.append('native executable changed or could not be rehashed')
    return {'accepted': not reasons, 'reasons': reasons, 'junit': summary}


def _sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def _timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _positive_seconds(value):
    try:
        seconds = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('timeout must be a positive integer') from error
    if seconds <= 0:
        raise argparse.ArgumentTypeError('timeout must be a positive integer')
    return seconds


def _stop_test_group(process):
    """Stop only the session created for this test run, including its fixtures."""
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    else:
        process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    finally:
        if os.name == 'posix':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.poll() is None:
            process.kill()
        process.wait()


def _run_pytest(command, environment, output, timeout):
    result = {'exit_code': None, 'timed_out': False, 'interrupted': False,
              'launch_error': None}
    with (output / 'pytest.log').open('xb') as log:
        try:
            process = subprocess.Popen(command, cwd=ROOT, env=environment,
                                       stdin=subprocess.DEVNULL, stdout=log,
                                       stderr=subprocess.STDOUT,
                                       start_new_session=(os.name == 'posix'))
        except OSError as error:
            result['launch_error'] = str(error)
            return result
        try:
            result['exit_code'] = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            result['timed_out'] = True
            _stop_test_group(process)
            result['exit_code'] = process.returncode
        except KeyboardInterrupt:
            result['interrupted'] = True
            _stop_test_group(process)
            result['exit_code'] = process.returncode
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True,
                        help='explicit compatible native executable; never inferred from the environment')
    parser.add_argument('--report-dir', required=True,
                        help='new private directory for result.json, pytest.log and junit.xml')
    parser.add_argument('--mode', choices=tuple(TESTS), default='all',
                        help='all: eight tests; headless or visible: four each (default: all)')
    parser.add_argument('--timeout-seconds', type=_positive_seconds, default=300,
                        help='total pytest time limit (default: 300)')
    parser.add_argument('--source-receipt',
                        help='optional source receipt to identify by hash, not binary attestation')
    args = parser.parse_args(argv)
    selected = TESTS[args.mode]
    try:
        executable = Path(args.executable).expanduser().resolve(strict=True)
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError('native executable must be an executable regular file')
        before = _sha256(executable)
        driver = os.environ.get('SDL_VIDEODRIVER', '')
        if args.mode != 'headless' and any(
                item.strip().lower() in ('dummy', 'offscreen') for item in driver.split(',')):
            raise ValueError('visible tests require a visible SDL driver; SDL_VIDEODRIVER=' + driver)
        for filename in {node.split('::', 1)[0] for node in selected}:
            if not (ROOT / filename).is_file():
                raise ValueError('run this helper from a source checkout containing ' + filename)
        source_receipt = None
        if args.source_receipt:
            receipt_path = Path(args.source_receipt).expanduser().resolve(strict=True)
            if not receipt_path.is_file():
                raise ValueError('source receipt must be a regular file')
            source_receipt = {'path': str(receipt_path), 'sha256': _sha256(receipt_path),
                              'binary_attestation': False}
        output = Path(args.report_dir).expanduser().absolute()
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
    except (OSError, ValueError) as error:
        parser.error('preflight refused: ' + str(error))

    junit_path = output / 'junit.xml'
    command = [sys.executable, '-m', 'pytest', '-q', '-ra',
               '--junitxml=' + str(junit_path), '-o', 'junit_family=xunit2', *selected]
    environment = os.environ.copy()
    environment['DOTBOX_DOSBOX_EXECUTABLE'] = str(executable)
    result = {
        'format': 'dotbox-native-test-result-1', 'accepted': False,
        'scope': 'authored native fixtures; no game-route, memory-only rewind or outer desktop takeover qualification',
        'mode': args.mode, 'selected_tests': list(selected), 'expected_tests': len(selected),
        'started_utc': _timestamp(),
        'host': {'system': platform.system(), 'release': platform.release(),
                 'architecture': platform.machine(), 'python': platform.python_version()},
        'executable': {'path': str(executable), 'sha256_before': before,
                       'sha256_after': None, 'stable': False},
        'source_receipt': source_receipt,
        'environment': {'SDL_VIDEODRIVER': driver,
                        'ssh_session': bool(os.environ.get('SSH_CONNECTION') or os.environ.get('SSH_TTY'))},
        'gui': {'required': args.mode != 'headless',
                'status': 'unverified' if args.mode != 'headless' else 'not_exercised'},
        'pytest': {'command': command, 'cwd': str(ROOT), 'timeout_seconds': args.timeout_seconds},
    }
    print(f'Running {len(selected)} native {args.mode} tests; evidence: {output}', flush=True)
    run = _run_pytest(command, environment, output, args.timeout_seconds)
    result['pytest'].update(run)
    try:
        result['executable']['sha256_after'] = _sha256(executable)
        result['executable']['stable'] = result['executable']['sha256_after'] == before
    except OSError as error:
        result['executable']['read_error'] = str(error)
    classification = classify_result(junit_path, selected,
                                     pytest_exit_code=run['exit_code'],
                                     binary_stable=result['executable']['stable'])
    for flag in ('timed_out', 'interrupted', 'launch_error'):
        if run[flag]:
            classification['reasons'].append('pytest ' + flag)
            classification['accepted'] = False
    result.update(classification)
    if result['accepted'] and args.mode != 'headless':
        result['gui']['status'] = 'visible_native_tests_passed'
    result['finished_utc'] = _timestamp()
    with (output / 'result.json').open('x', encoding='utf-8') as report:
        json.dump(result, report, indent=2)
        report.write('\n')
    print(json.dumps({'accepted': result['accepted'], 'mode': args.mode,
                      'reasons': result['reasons'], 'report': str(output / 'result.json')}))
    return 0 if result['accepted'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
