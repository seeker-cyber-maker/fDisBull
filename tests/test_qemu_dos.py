"""Native DOS admission and public selection, independent of emulator presence."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from fdisbull.cli import main, parser, respond
from fdisbull.debugger import DebugProjectMixin


def image(tmp_path, size=1440 * 1024):
    path = tmp_path / 'boot.img'
    data = bytearray(size)
    data[510:512] = b'\x55\xaa'
    path.write_bytes(data)
    return path


def test_native_profile_pins_input_without_claiming_dos_boot(tmp_path):
    from fdisbull.qemu_dos import prepare_dos_profile, admit_dos_profile
    path = image(tmp_path)
    original = path.read_bytes()
    profile = prepare_dos_profile(path)
    assert profile['backend'] == 'qemu-dos'
    assert profile['boot_image']['sha256'] == hashlib.sha256(original).hexdigest()
    assert profile['machine']['boot_device'] == 'floppy'
    assert profile['machine']['cpus'] == 1
    assert profile['machine']['network'] == 'none'
    assert profile['memory_manager']['observed'] == 'unknown'
    assert profile['guest_os']['observed'] == 'unknown'
    assert profile['runtime_validation'] == 'not_run'
    assert admit_dos_profile(profile, path) == profile
    assert path.read_bytes() == original
    # A caller-provided observation never becomes a new live observation.
    supplied = deepcopy(profile)
    supplied['guest_os']['observed'] = 'booted'
    assert admit_dos_profile(supplied, path)['guest_os']['observed'] == 'unknown'


def test_profile_change_and_malformed_boot_refuse_before_spawn(tmp_path):
    from fdisbull.qemu_dos import prepare_dos_profile, admit_dos_profile
    path = image(tmp_path)
    profile = prepare_dos_profile(path)
    with path.open('r+b') as output:
        output.write(b'changed')
    with pytest.raises(ValueError, match='changed'):
        admit_dos_profile(profile, path)
    path.write_bytes(b'not a boot image')
    with pytest.raises(ValueError, match='sectors|signature'):
        prepare_dos_profile(path)


def test_machine_options_are_explicit_and_hash_bound(tmp_path):
    from fdisbull.qemu_dos import prepare_dos_profile, admit_dos_profile
    path = image(tmp_path, 512)
    profile = prepare_dos_profile(path, cpu='max', memory_mib=64)
    assert profile['machine']['boot_device'] == 'ide'
    assert admit_dos_profile(profile, path)['machine']['memory_mib'] == 64
    tampered = deepcopy(profile)
    tampered['machine']['cpus'] = 2
    with pytest.raises(ValueError, match='configuration'):
        admit_dos_profile(tampered, path)
    tampered = deepcopy(profile)
    tampered['profile_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='identity'):
        admit_dos_profile(tampered, path)
    for options in ({'cpu': 'unselected'}, {'memory_mib': True}, {'memory_mib': 9000}):
        with pytest.raises(ValueError):
            prepare_dos_profile(path, **options)


def test_profile_cli_and_json_are_projectless(tmp_path, capsys):
    path = image(tmp_path)
    assert main(['dos-profile', str(path), '--memory-mib', '64']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['ok'] and result['result']['machine']['memory_mib'] == 64
    reply = respond({'method': 'dos-profile', 'params': {'boot_image': str(path)}},
                    default_project='/missing/unrelated.fdb')
    assert reply['ok'] and reply['result']['runtime_validation'] == 'not_run'


def test_explicit_qemu_selection_and_legacy_default_remain_separate(monkeypatch, tmp_path):
    from fdisbull import debugger, qemu_dos
    calls = []

    def selected(*args, **kwargs):
        calls.append(('qemu-dos', kwargs))
        return 'native'

    def legacy(*args, **kwargs):
        calls.append(('dosbox', kwargs))
        return 'legacy'

    monkeypatch.setattr(qemu_dos, 'QemuDOSSession', selected)
    monkeypatch.setattr(debugger, 'DebugSession', legacy)
    project = SimpleNamespace(meta={'format': 'raw', 'filename': 'boot.img'})
    result = DebugProjectMixin.debugger(project, '/qemu', str(tmp_path), backend='qemu-dos',
                                       qemu_transport='pipe', qemu_firmware='/firmware')
    assert result == 'native'
    assert calls[-1][1]['transport'] == 'pipe'
    assert calls[-1][1]['firmware'] == '/firmware'
    assert calls[-1][1]['boot_image'] == tmp_path / 'boot.img'
    assert DebugProjectMixin.debugger(project, '/dosbox', str(tmp_path)) == 'legacy'
    assert DebugProjectMixin.debugger(project, '/dosbox', str(tmp_path), backend='dosbox') == 'legacy'
    assert [backend for backend, _ in calls] == ['qemu-dos', 'dosbox', 'dosbox']


def test_native_failure_never_silently_relaunches_in_dosbox(monkeypatch, tmp_path):
    from fdisbull import debugger, qemu_dos

    def failed(*args, **kwargs):
        raise RuntimeError('native startup failed')

    monkeypatch.setattr(qemu_dos, 'QemuDOSSession', failed)
    monkeypatch.setattr(debugger, 'DebugSession', lambda *a, **kw: pytest.fail('Implicit fallback executed'))
    project = SimpleNamespace(meta={'format': 'raw', 'filename': 'boot.img'})
    with pytest.raises(RuntimeError, match='native startup failed'):
        DebugProjectMixin.debugger(project, '/qemu', str(tmp_path), backend='qemu-dos')


def test_native_only_options_refuse_on_other_backends_before_launch(tmp_path):
    project = SimpleNamespace(meta={'format': 'COM', 'filename': 'tiny.com'})
    for backend in (None, 'dosbox', 'dosbox-qemu', 'wine-qemu'):
        for options in ({'qemu_transport': 'pipe'}, {'qemu_firmware': '/firmware'}):
            with pytest.raises(ValueError, match='native QEMU'):
                DebugProjectMixin.debugger(project, '/missing/backend', str(tmp_path),
                                           backend=backend, **options)
    args = parser().parse_args(['debug', 'boot.fdb', '--executable', '/qemu', '--game-dir', '.',
                                '--backend', 'qemu-dos', '--qemu-transport', 'pipe',
                                '--qemu-firmware', '/firmware'])
    assert args.backend == 'qemu-dos' and args.qemu_transport == 'pipe'


def test_native_dos_rejects_process_projects_and_patched_images_before_spawn(tmp_path):
    from fdisbull.project import Project
    from fdisbull.qemu_dos import QemuDOSSession
    binary = tmp_path / 'probe.com'
    binary.write_bytes(b'\xb8\x00\x4c\xcd\x21')
    with Project.create(tmp_path / 'probe.fdb', binary, image='com') as project:
        with pytest.raises(ValueError, match='raw.*image|raw x86'):
            QemuDOSSession(project, '/missing/qemu', boot_image=binary)


def test_script_admission_uses_native_machine_contract():
    from fdisbull.debug_script import validate_script
    from fdisbull.qemu_dos import QemuDOSSession
    session = QemuDOSSession.__new__(QemuDOSSession)
    session.metadata = {'backend': 'qemu-dos'}
    steps = [{'op': 'status'}, {'op': 'registers'},
             {'op': 'memory-snapshot', 'address': 0x5000, 'length': 2, 'space': 'physical'}]
    script = {'format': 'fdisbull-script-1', 'backend': 'qemu-dos', 'steps': steps}
    assert validate_script(script) == steps
    assert validate_script(script, session=session) == steps
    assert validate_script({'format': script['format'], 'steps': steps}, session=session) == steps
    for step, error in (({'op': 'trace-until'}, 'Unsupported operation'),
                        ({'op': 'save-state'}, 'Unsupported operation')):
        with pytest.raises(ValueError, match=error):
            validate_script(dict(script, steps=[step]), session=session)
    with pytest.raises(ValueError, match='differs'):
        validate_script(dict(script, backend='qemu-machine'), session=session)
