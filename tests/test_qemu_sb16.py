"""SB16 profile admission/routing; real PCM/DMA evidence is native-only."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from fdisbull.cli import main, parser
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_audio import AUDIO_COMMANDS, admit_audio, machine_audio_configuration
from test_qemu_io_public import raw_project, com_project


def test_sb16_profile_is_explicit_and_preserves_the_old_profile_identity():
    assert machine_audio_configuration('pc-speaker', 'virtual') == dict(
        profile='pc-speaker', devices=['pc-speaker'], host_playback=False,
        capture_format=dict(rate=32000, channels=1, sample_format='u8', bytes_per_frame=1))
    selected = machine_audio_configuration('sb16', 'virtual')
    assert selected['devices'] == ['sb16'] and selected['host_playback'] is False
    assert selected['device_options'] == dict(iobase=544, irq=7, dma=1, dma16=5, version=0x405)
    assert selected['capture_format'] == dict(rate=32000, channels=1, sample_format='u8', bytes_per_frame=1)
    with pytest.raises(ValueError, match='virtual clock'):
        machine_audio_configuration('sb16', 'standard')


@pytest.mark.parametrize('route', ['raw-dos', 'com-dos', 'raw-machine', 'machine-python'])
def test_sb16_factory_routing(raw_project, com_project, tmp_path, monkeypatch, route):
    from fdisbull import qemu_dos, qemu_dos_process, qemu_machine
    seen = []
    def create(*args, **kwargs):
        seen.append(kwargs)
        return 'selected'
    monkeypatch.setattr(qemu_dos, 'QemuDOSSession', create)
    monkeypatch.setattr(qemu_dos_process, 'QemuDOSProcessSession', create)
    monkeypatch.setattr(qemu_machine, 'MachineDebugSession', create)
    if route == 'machine-python':
        result = raw_project.machine('/qemu', boot_image=tmp_path / 'boot.img',
            clock_profile='virtual', audio_profile='sb16')
    else:
        project = com_project if route == 'com-dos' else raw_project
        options = dict(backend='qemu-machine' if route == 'raw-machine' else 'qemu-dos',
                       qemu_clock='virtual', qemu_audio='sb16')
        if route == 'com-dos':
            options['dos_boot_image'] = tmp_path / 'dos.img'
        result = project.debugger('/qemu', tmp_path, **options)
    assert result == 'selected' and len(seen) == 1
    assert seen[0]['audio_profile'] == 'sb16' and seen[0]['clock_profile'] == 'virtual'


def test_sb16_cli_selector_and_backend_scope(com_project, tmp_path, monkeypatch):
    from fdisbull import cli
    seen = []
    monkeypatch.setattr(cli, 'serve', lambda project, launch: seen.append(launch) or 0)
    assert main(['debug', str(com_project.path), '--executable', '/qemu', '--game-dir', '.',
                 '--backend', 'qemu-dos', '--qemu-clock', 'virtual', '--qemu-audio', 'sb16']) == 0
    assert seen[0]['qemu_audio'] == 'sb16'
    # Omitting the selector still defers to the existing backend default.
    assert parser().parse_args(['debug', 'p.fdb', '--executable', '/x', '--game-dir', '.']).backend is None
    with pytest.raises(ValueError):
        com_project.debugger('/not-started', tmp_path, backend='dosbox',
                            qemu_clock='virtual', qemu_audio='sb16')


class Admission:
    def __init__(self, *, extension=True):
        self.qmp_commands = AUDIO_COMMANDS | ({'x-fdisbull-query-sb16'} if extension else set())
        self.native_clock_admission = {'epoch': 1, 'virtual-ns': 0}
        self.machine_configuration = {'audio_profile': machine_audio_configuration('sb16', 'virtual')}
        self.calls, self.closed = [], False
        self.sb = {'api-version': 1, 'iobase': 544, 'irq': 7, 'dma': 1, 'dma16': 5,
                   'version': 0x405, 'audiodev-id': 'fdisbull-sb16',
                   'voice-present': False, 'dma-active': False}
        self.qmp = SimpleNamespace(call=self.call)
    def call(self, command):
        self.calls.append(command)
        if command == 'x-fdisbull-query-sb16':
            return deepcopy(self.sb)
        return {'api-version': 1, 'epoch': 1, 'state': 'idle', 'virtual-ns': 0,
                'max-frames': 0, 'frames': 0, 'dropped-frames': 0, 'rate': 32000,
                'channels': 1, 'format': 'u8', 'enabled': False, 'chunks': []}
    def close(self):
        self.closed = True


def test_old_native_runtime_is_refused_before_audio_admission():
    vm = Admission(extension=False)
    with pytest.raises(ValueError, match='SB16.*extension'):
        admit_audio(vm)
    assert vm.calls == []


@pytest.mark.parametrize('mutation', [
    {'api-version': True}, {'api-version': 2}, {'irq': 5}, {'dma': 3},
    {'dma16': 6}, {'iobase': 576}, {'version': 0x301},
    {'audiodev-id': 'fdisbull-pc'}, {'voice-present': 0}, {'dma-active': 0},
])
def test_sb16_native_identity_mismatch_closes_the_owner(mutation):
    vm = Admission()
    vm.sb.update(mutation)
    with pytest.raises(DebuggerError, match='SB16'):
        admit_audio(vm)
    assert vm.closed


def test_sb16_idle_admission_keeps_the_capture_format():
    vm = Admission()
    value = admit_audio(vm)
    assert value['state'] == 'idle' and value['frames'] == 0
    assert vm.native_sb16_admission == vm.sb
    assert not vm.closed
