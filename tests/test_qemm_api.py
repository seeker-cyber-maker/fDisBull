"""Public CLI/JSON and project/debugger boundaries for DOS driver support."""
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from fdisbull.cli import main, parser, respond
from fdisbull.debugger import DebugProjectMixin, DebugWorkspace
from fdisbull.debug_script import validate_script


def test_sys_selector_flows_through_import_restart_and_analysis(tmp_path, capsys):
    source = tmp_path / 'authored.sys'
    data = bytearray(64)
    struct.pack_into('<IHHH8s', data, 0, 0xffffffff, 0x8000, 32, 48, b'AUTHOR$ ')
    data[32] = data[48] = 0xcb
    source.write_bytes(data)
    project = tmp_path / 'driver.fdb'
    assert main(['import', str(source), str(project), '--image', 'sys']) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported['ok']
    result = respond({'method': 'analyze', 'params': {'project': str(project), 'max_instructions': 16}})
    assert result['ok']
    from fdisbull.project import Project
    with Project(project) as opened:
        assert opened.meta['format'] == 'SYS'
        assert opened.meta['loader_metadata']['dos']['psp_segment'] is None


def test_projectless_methods_ignore_server_default_project(tmp_path, capsys):
    # These fixture builders contain authored bytes, not held-out targets.
    from test_le_driver import le_driver
    from test_qemm_runtime import fat_image
    from test_qpi import authored_report
    le = tmp_path / 'module.vxd'
    le.write_bytes(le_driver())
    image = tmp_path / 'authored.img'
    image.write_bytes(fat_image())
    report = tmp_path / 'FDQPI.BIN'
    report.write_bytes(authored_report())
    calls = [
        ('le-driver-inspect', dict(path=str(le))),
        ('le-driver-disasm', dict(path=str(le), object_number=1, max_instructions=3)),
        ('qemm-config', dict(config_sys='FILES=30\r\n')),
        ('qemm-profile', dict(boot_image=str(image))),
        ('qpi-probe', dict(output=str(tmp_path / 'FDQPI.COM'))),
        ('qpi-report', dict(path=str(report))),
    ]
    for method, params in calls:
        reply = respond({'method': method, 'params': params}, default_project='/missing/project.fdb')
        assert reply['ok'], reply
    assert main(['le-driver-disasm', str(le), '1', '--max-instructions', '3']) == 0
    view = json.loads(capsys.readouterr().out)
    assert view['ok'] and view['result']['source_path'] == str(le)
    assert main(['qpi-report', str(report)]) == 0
    decoded = json.loads(capsys.readouterr().out)
    assert decoded['result']['qemm']['version'] == '9.02'


def test_config_validation_is_read_only_and_unknown_options_refuse(tmp_path):
    config = tmp_path / 'CONFIG.SYS'
    original = b'DEVICE=C:\\QEMM\\QEMM386.SYS RAM ST:M\r\n'
    config.write_bytes(original)
    reply = respond({'method': 'qemm-config', 'params': {'config_file': str(config), 'validate_only': True}})
    assert reply['ok'] and reply['result']['applied_to_image'] is False
    assert config.read_bytes() == original
    for params in (dict(config_file=str(config), config_sys=''),
                   dict(config_sys=original.decode(), validate_only=1),
                   dict(config_sys=original.decode(), validate_only=True, options='NOEMS'),
                   dict(config_sys=original.decode(), unknown=True)):
        assert not respond({'method': 'qemm-config', 'params': params})['ok']


def test_guest_profile_public_launch_is_machine_only(monkeypatch, tmp_path):
    from fdisbull import qemu_machine
    seen = {}

    def session(project, executable, **options):
        seen.update(options)
        return 'authored-session'

    monkeypatch.setattr(qemu_machine, 'MachineDebugSession', session)
    project = SimpleNamespace(meta={'format': 'RAW', 'filename': 'boot.img'})
    project.machine = lambda executable, **options: DebugProjectMixin.machine(project, executable, **options)
    result = DebugProjectMixin.debugger(project, '/selected/qemu', str(tmp_path),
                                       backend='qemu-machine', guest_profile='qemm')
    assert result == 'authored-session'
    assert seen['guest_profile'] == 'qemm'
    assert seen['boot_image'] == tmp_path / 'boot.img'
    for backend in (None, 'dosbox', 'dosbox-qemu', 'wine-qemu'):
        with pytest.raises(ValueError, match='full-system'):
            DebugProjectMixin.debugger(project, '/selected/qemu', str(tmp_path),
                                       backend=backend, guest_profile='qemm')
    args = parser().parse_args(['debug', 'x.fdb', '--executable', '/qemu', '--game-dir', '.',
                                '--backend', 'qemu-machine', '--guest-profile', 'qemm'])
    assert args.guest_profile == 'qemm'


def test_live_methods_route_to_selected_machine_and_refuse_other_contexts(tmp_path):
    workspace = DebugWorkspace()
    project = SimpleNamespace(path=tmp_path.resolve())
    machine = SimpleNamespace(memory_translation=lambda address: dict(translated=address),
                              qemm_observe=lambda address, length=1120: dict(observed=address, length=length))
    session = SimpleNamespace(project=project, context=lambda name: machine if name == 'machine' else SimpleNamespace())
    workspace.sessions['r'] = session
    for method, key in (('debug-memory-translation', 'translated'), ('debug-qemm-observe', 'observed')):
        result = workspace.invoke(method, tmp_path, dict(run='r', context='machine', address='0xa0000'))
        assert result[key] == '0xa0000'
        with pytest.raises(ValueError, match='unavailable'):
            workspace.invoke(method, tmp_path, dict(run='r', context='dos', address=0xa0000))


def test_machine_observation_scripts_have_explicit_backend_grammar():
    script = dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
        dict(op='memory-translation', address='0xa0000'),
        dict(op='qemm-observe', address='0x10200', length=1120),
    ])
    assert len(validate_script(script)) == 2
    with pytest.raises(ValueError, match='Unsupported operation'):
        validate_script({**script, 'backend': 'scummvm-agi'})
