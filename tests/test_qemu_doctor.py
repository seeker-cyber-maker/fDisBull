"""Installed native core self-test reports success only after real execution."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from fdisbull.qemu_doctor import doctor_qemu


def test_qemu_doctor_missing_backend_is_a_failed_receipt(tmp_path):
    output = tmp_path / 'evidence'
    report = doctor_qemu(executable=tmp_path / 'missing-qemu', output=output)
    assert report['format'] == 'fdisbull-doctor-1'
    assert report['backend'] == 'qemu-dos' and report['status'] == 'failed'
    assert report['checks'][0]['status'] == 'failed'
    assert report['guest_os_validation'] == 'not_run'
    assert report['native_state_restored'] is False
    assert report['process_cleanup'] == dict(spawned=0, reaped=True, forced=False)
    assert report['artifacts'] == {}
    assert {path.name for path in output.iterdir()} == {'receipt.json'}
    assert json.loads((output / 'receipt.json').read_text()) == report
    with pytest.raises(FileExistsError):
        doctor_qemu(executable=tmp_path / 'missing-qemu', output=output)


@pytest.mark.parametrize('options', [dict(qemu_transport='tcp'), dict(boot_timeout_ms=True),
                                     dict(boot_timeout_ms=0), dict(boot_timeout_ms=600001)])
def test_qemu_doctor_invalid_admission_never_spawns(tmp_path, options):
    report = doctor_qemu(executable=tmp_path / 'missing-qemu', **options)
    assert report['status'] == 'failed' and report['process_cleanup']['spawned'] == 0
    assert 'ValueError' in report['checks'][0]['error']


def test_native_doctor_cli_can_report_failure_without_decoder_dependencies(tmp_path):
    import fdisbull
    # Isolate only the package from either source or an installed wheel. -S
    # disables dependency discovery without assuming this test has a src tree.
    isolated = tmp_path / 'without-dependencies'
    shutil.copytree(Path(fdisbull.__file__).parent, isolated / 'fdisbull',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    environment = {**os.environ, 'PYTHONPATH': str(isolated)}
    result = subprocess.run([sys.executable, '-S', '-m', 'fdisbull', 'doctor',
                             '--backend', 'qemu-dos', '--executable', str(tmp_path / 'missing'),
                             '--qemu-transport', 'pipe'], env=environment,
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)['result']
    assert report['status'] == 'failed' and report['backend'] == 'qemu-dos'
    assert report['process_cleanup']['spawned'] == 0


def test_real_installed_native_qemu_doctor_exports_only_evidence(tmp_path):
    from fdisbull.doctor import doctor
    from test_qemu_dos_native import selected_qemu
    executable, options = selected_qemu()
    output = tmp_path / 'evidence'
    report = doctor(backend='qemu-dos', executable=executable, output=output,
                    qemu_transport=options['qemu_transport'], qemu_firmware=options['qemu_firmware'])
    assert report['status'] == 'passed', report
    assert all(check['status'] == 'passed' for check in report['checks'])
    assert report['process_cleanup'] == dict(spawned=1, reaped=True, forced=False)
    assert report['runtime_inputs']['qemu']['sha256'] == report['input_sha256']['executable']
    assert report['runtime_inputs']['boot_image']['sha256'] == report['authored_target_sha256']
    assert report['guest_os_validation'] == 'not_run' and report['native_state_restored'] is False
    expected = {'receipt.json', 'trace.json'}
    if report['capabilities']['screenshot']:
        expected.add('frame.png')
        assert report['graphics']['status'] == 'passed'
    else:
        assert report['graphics']['status'] == 'unavailable'
    assert {path.name for path in output.iterdir()} == expected
    assert all(artifact['retained'] for artifact in report['artifacts'].values())
    assert json.loads((output / 'receipt.json').read_text()) == report
    trace = json.loads((output / 'trace.json').read_text())
    assert all(event['observation']['instruction_completed'] is None
               for event in trace['events'])
    assert trace['single_step_policy']['status'] == 'observed'
    assert trace['single_step_policy']['changed'] is False
