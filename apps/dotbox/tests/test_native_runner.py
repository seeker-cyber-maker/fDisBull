"""Runner bookkeeping uses authored JUnit; these checks launch no emulator."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/test_native.py'
AUTHORED_CASES = ('tests/test_authored.py::test_first',
                  'tests/test_authored.py::test_second')


def _runner():
    spec = importlib.util.spec_from_file_location('dotbox_native_runner', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _junit(path, cases=AUTHORED_CASES, status=None):
    root = ET.Element('testsuites')
    suite = ET.SubElement(root, 'testsuite', tests=str(len(cases)))
    for index, node in enumerate(cases):
        filename, name = node.split('::')
        case = ET.SubElement(suite, 'testcase',
                             classname=filename[:-3].replace('/', '.'), name=name)
        if index == 0 and status:
            ET.SubElement(case, status, message='Authored classifier fixture')
    ET.ElementTree(root).write(path)
    return path


def test_authored_complete_junit_is_classified_without_native_execution(tmp_path):
    result = _runner().classify_result(_junit(tmp_path / 'result.xml'), AUTHORED_CASES,
                                       pytest_exit_code=0, binary_stable=True)
    assert result['accepted'] is True
    assert result['reasons'] == []
    assert result['junit']['case_count'] == 2


@pytest.mark.parametrize('status', ['skipped', 'failure', 'error'])
def test_any_nonpassing_case_rejects_authored_result(tmp_path, status):
    result = _runner().classify_result(
        _junit(tmp_path / 'result.xml', status=status), AUTHORED_CASES,
        pytest_exit_code=0, binary_stable=True)
    assert result['accepted'] is False
    assert result['junit'][status] == 1


@pytest.mark.parametrize('cases', [
    AUTHORED_CASES[:1],
    AUTHORED_CASES + ('tests/test_authored.py::test_extra',),
    (AUTHORED_CASES[0], AUTHORED_CASES[0]),
    (AUTHORED_CASES[0], 'tests/test_other.py::test_second'),
])
def test_wrong_count_duplicate_or_wrong_identity_rejects_result(tmp_path, cases):
    result = _runner().classify_result(_junit(tmp_path / 'result.xml', cases),
                                       AUTHORED_CASES, pytest_exit_code=0,
                                       binary_stable=True)
    assert result['accepted'] is False
    assert result['reasons']


@pytest.mark.parametrize('exit_code', [1, 2, 5, None])
def test_junit_cannot_override_failed_or_absent_pytest_exit(tmp_path, exit_code):
    result = _runner().classify_result(_junit(tmp_path / 'result.xml'), AUTHORED_CASES,
                                       pytest_exit_code=exit_code, binary_stable=True)
    assert result['accepted'] is False
    assert 'pytest did not exit successfully' in result['reasons']


def test_binary_changed_after_tests_rejects_result(tmp_path):
    result = _runner().classify_result(_junit(tmp_path / 'result.xml'), AUTHORED_CASES,
                                       pytest_exit_code=0, binary_stable=False)
    assert result['accepted'] is False
    assert 'native executable changed or could not be rehashed' in result['reasons']


@pytest.mark.parametrize('contents', [None, '<testsuites>', '<unrelated/>'])
def test_missing_malformed_or_unrecognized_junit_rejects_result(tmp_path, contents):
    path = tmp_path / 'result.xml'
    if contents is not None:
        path.write_text(contents)
    result = _runner().classify_result(path, AUTHORED_CASES,
                                       pytest_exit_code=0, binary_stable=True)
    assert result['accepted'] is False
    assert result['junit']['read_error']


def test_modes_select_exact_disjoint_native_cases():
    tests = _runner().TESTS
    assert len(tests['all']) == len(set(tests['all'])) == 8
    assert len(tests['headless']) == len(tests['visible']) == 4
    assert set(tests['headless']).isdisjoint(tests['visible'])
    assert set(tests['headless']) | set(tests['visible']) == set(tests['all'])
    assert ('tests/test_playable_native.py::'
            'test_original_mz_entry_and_relocation_with_standalone_runtime') in tests['headless']
    assert ('tests/test_native_overlay.py::'
            'test_native_visible_owner_transfers_reset_and_reject_stale_inputs') in tests['visible']


def test_help_and_missing_binary_preflight_do_not_need_pytest(tmp_path):
    help_result = subprocess.run([sys.executable, '-S', str(SCRIPT), '--help'],
                                 capture_output=True, text=True)
    assert help_result.returncode == 0
    assert '--mode' in help_result.stdout
    output = tmp_path / 'evidence'
    result = subprocess.run([
        sys.executable, '-S', str(SCRIPT), '--executable', str(tmp_path / 'missing'),
        '--report-dir', str(output)], capture_output=True, text=True)
    assert result.returncode == 2
    assert 'executable' in result.stderr.lower()
    assert not output.exists()


@pytest.mark.parametrize('kind', ['directory', 'not_executable'])
def test_nonexecutable_inputs_fail_before_report_creation(tmp_path, kind):
    executable = tmp_path / 'fixture'
    if kind == 'directory':
        executable.mkdir()
    else:
        executable.write_text('authored non-executable fixture')
        executable.chmod(0o600)
    with pytest.raises(SystemExit) as error:
        _runner().main(['--executable', str(executable),
                        '--report-dir', str(tmp_path / 'report')])
    assert error.value.code == 2
    assert not (tmp_path / 'report').exists()


def test_existing_evidence_is_preserved_before_pytest(tmp_path):
    executable = tmp_path / 'fixture'
    executable.write_text('authored executable placeholder; never launched')
    executable.chmod(0o700)
    output = tmp_path / 'report'
    output.mkdir()
    retained = output / 'keep'
    retained.write_text('prior evidence')
    with pytest.raises(SystemExit) as error:
        _runner().main(['--executable', str(executable), '--report-dir', str(output)])
    assert error.value.code == 2
    assert list(output.iterdir()) == [retained]
    assert retained.read_text() == 'prior evidence'


@pytest.mark.parametrize('mode,driver', [('all', 'dummy'), ('visible', 'offscreen'),
                                        ('visible', 'cocoa, DUMMY')])
def test_explicit_nonvisible_driver_is_rejected_without_clearing_env(
        tmp_path, monkeypatch, mode, driver):
    executable = tmp_path / 'fixture'
    executable.write_text('authored executable placeholder; never launched')
    executable.chmod(0o700)
    monkeypatch.setenv('SDL_VIDEODRIVER', driver)
    with pytest.raises(SystemExit) as error:
        _runner().main(['--executable', str(executable), '--mode', mode,
                        '--report-dir', str(tmp_path / 'report')])
    assert error.value.code == 2
    assert not (tmp_path / 'report').exists()
    assert os.environ['SDL_VIDEODRIVER'] == driver


@pytest.mark.parametrize('change_binary', [False, True])
def test_authored_failed_run_preserves_private_receipt_and_explicit_inputs(
        tmp_path, monkeypatch, change_binary):
    runner = _runner()
    executable = tmp_path / 'fixture'
    original = b'authored executable placeholder; never launched'
    executable.write_bytes(original)
    executable.chmod(0o700)
    source = tmp_path / 'source-receipt.json'
    source.write_text('{"untrusted_origin_claim": "not an attestation"}')
    output = tmp_path / 'report'
    monkeypatch.setenv('DOTBOX_DOSBOX_EXECUTABLE', '/ignored/environment/input')
    monkeypatch.setenv('SDL_VIDEODRIVER', 'dummy')

    def authored_report(command, environment, directory, timeout):
        assert command[:3] == [sys.executable, '-m', 'pytest']
        assert environment['DOTBOX_DOSBOX_EXECUTABLE'] == str(executable)
        assert environment['SDL_VIDEODRIVER'] == 'dummy'
        assert timeout == 300
        _junit(directory / 'junit.xml', runner.TESTS['headless'], status='skipped')
        if change_binary:
            executable.write_bytes(b'changed authored bytes')
        return {'exit_code': 0, 'timed_out': False, 'interrupted': False,
                'launch_error': None}

    monkeypatch.setattr(runner, '_run_pytest', authored_report)
    assert runner.main(['--executable', str(executable), '--mode', 'headless',
                        '--source-receipt', str(source), '--report-dir', str(output)]) == 1
    result = json.loads((output / 'result.json').read_text())
    assert result['accepted'] is False
    assert result['expected_tests'] == result['junit']['case_count'] == 4
    assert result['junit']['skipped'] == 1
    assert result['pytest']['cwd'] == str(ROOT)
    assert result['executable']['sha256_before'] == hashlib.sha256(original).hexdigest()
    assert result['executable']['sha256_after'] == hashlib.sha256(executable.read_bytes()).hexdigest()
    assert result['executable']['stable'] is (not change_binary)
    assert result['source_receipt'] == {'path': str(source), 'binary_attestation': False,
                                        'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    assert result['gui'] == {'required': False, 'status': 'not_exercised'}
    assert output.stat().st_mode & 0o777 == 0o700


def test_timeout_stops_an_authored_python_process_without_native_execution(tmp_path):
    result = _runner()._run_pytest(
        [sys.executable, '-c', 'import time; time.sleep(10)'], os.environ.copy(),
        tmp_path, timeout=0.05)
    assert result['timed_out'] is True
    assert result['interrupted'] is False
    assert result['exit_code'] is not None
    assert result['exit_code'] != 0


def test_failed_process_launch_is_recorded_without_native_execution(tmp_path):
    result = _runner()._run_pytest([str(tmp_path / 'absent-python')], os.environ.copy(),
                                  tmp_path, timeout=1)
    assert result['exit_code'] is None
    assert result['launch_error']
