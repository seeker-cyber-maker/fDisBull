"""Public launch and admission contracts for explicit native retrace evidence."""
import pytest

from fdisbull.cli import main, parser
from fdisbull.debug_script import execute_script
from test_qemu_io_public import raw_project, com_project, stopped_session


@pytest.mark.parametrize('profile,expected', [(None, 'standard'), ('standard', 'standard'),
                                            ('precise', 'precise')])
@pytest.mark.parametrize('route', ['raw-dos', 'com-dos', 'raw-machine', 'machine-python'])
def test_retrace_profile_reaches_native_factories(
        raw_project, com_project, tmp_path, monkeypatch, profile, expected, route):
    from fdisbull import qemu_dos, qemu_dos_process, qemu_machine
    captured = []
    sentinel = object()
    def create(*args, **options):
        captured.append(options)
        return sentinel
    monkeypatch.setattr(qemu_dos, 'QemuDOSSession', create)
    monkeypatch.setattr(qemu_dos_process, 'QemuDOSProcessSession', create)
    monkeypatch.setattr(qemu_machine, 'MachineDebugSession', create)
    if route == 'machine-python':
        result = raw_project.machine('/qemu', boot_image=tmp_path / 'boot.img',
                                     clock_profile='virtual', retrace_profile=expected)
    else:
        project = com_project if route == 'com-dos' else raw_project
        options = dict(backend='qemu-machine' if route == 'raw-machine' else 'qemu-dos',
                       qemu_clock='virtual', qemu_retrace=profile)
        if route == 'com-dos':
            options['dos_boot_image'] = tmp_path / 'separate-dos.img'
        result = project.debugger('/qemu', tmp_path, **options)
    assert result is sentinel and len(captured) == 1
    assert captured[0]['retrace_profile'] == expected


@pytest.mark.parametrize('value', ['unknown', '', True, 7, ['precise']])
def test_invalid_retrace_choice_is_rejected_before_constructor(com_project, tmp_path, monkeypatch, value):
    from fdisbull import qemu_dos_process
    monkeypatch.setattr(qemu_dos_process, 'QemuDOSProcessSession',
                        lambda *a, **kw: pytest.fail('Invalid retrace profile launched a backend'))
    with pytest.raises(ValueError, match='retrace'):
        com_project.debugger('/unused/qemu', tmp_path, backend='qemu-dos',
                             dos_boot_image=tmp_path / 'not-opened.img',
                             qemu_clock='virtual', qemu_retrace=value)


@pytest.mark.parametrize('backend', [None, 'dosbox', 'dosbox-qemu', 'wine-qemu'])
def test_retrace_choice_cannot_be_ignored_by_another_backend(com_project, tmp_path, backend):
    with pytest.raises(ValueError, match='native QEMU'):
        com_project.debugger('/unused', tmp_path, backend=backend, qemu_retrace='standard')


def test_cli_retrace_choice_reaches_launch(monkeypatch, raw_project):
    from fdisbull import cli
    calls = []
    monkeypatch.setattr(cli, 'serve', lambda project, launch: calls.append(launch) or 0)
    assert main(['debug', str(raw_project.path), '--executable', '/qemu', '--game-dir', '.',
                 '--backend', 'qemu-dos', '--qemu-clock', 'virtual', '--qemu-retrace', 'precise']) == 0
    assert calls[0]['qemu_retrace'] == 'precise'
    with pytest.raises(SystemExit) as error:
        parser().parse_args(['debug', str(raw_project.path), '--executable', '/qemu',
                            '--game-dir', '.', '--qemu-retrace', 'invented'])
    assert error.value.code == 2


def test_script_refuses_unselected_retrace_before_an_earlier_write(raw_project, tmp_path):
    session, peer = stopped_session(raw_project, tmp_path)
    writes = []
    session.write_memory = lambda address, data_hex: writes.append((address, data_hex))
    script = dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
        dict(op='write-memory', address=0x7c00, data_hex='90'),
        dict(op='retrace-observe'),
    ])
    with pytest.raises(ValueError, match='retrace.*profile'):
        execute_script(session, script)
    assert writes == [] and peer.calls == []
