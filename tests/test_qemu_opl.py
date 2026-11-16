"""Explicit mixed OPL2/SB16 profile; native synthesis is tested separately."""
from copy import deepcopy

import pytest

from fdisbull.cli import parser
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_audio import admit_audio, machine_audio_arguments, machine_audio_configuration
from test_qemu_sb16 import Admission


def test_combined_profile_has_distinct_fixed_identity_and_keeps_backend_default():
    value = machine_audio_configuration('sb16-opl', 'virtual')
    assert value['devices'] == ['sb16', 'adlib']
    assert value['device_options'] == dict(iobase=544, irq=7, dma=1, dma16=5, version=1029)
    assert value['opl_options'] == dict(iobase=544, freq=32000, checkpoint=True)
    assert value['capture_format'] == dict(rate=32000, channels=1, sample_format='u8', bytes_per_frame=1)
    assert machine_audio_arguments('sb16-opl') == [
        '-audiodev', 'none,id=fdisbull-sb16-opl,timer-period=10000,out.frequency=32000,out.channels=1,out.format=u8',
        '-device', 'sb16,audiodev=fdisbull-sb16-opl,iobase=544,irq=7,dma=1,dma16=5,version=1029',
        '-device', 'adlib,audiodev=fdisbull-sb16-opl,iobase=544,freq=32000,fdisbull-checkpoint=on']
    args = parser().parse_args(['debug', 'p.fdb', '--executable', '/qemu', '--game-dir', '.',
        '--qemu-clock', 'virtual', '--qemu-audio', 'sb16-opl'])
    assert args.backend is None and args.qemu_audio == 'sb16-opl'
    with pytest.raises(ValueError, match='virtual clock'):
        machine_audio_configuration('sb16-opl', 'standard')


class OplAdmission(Admission):
    def __init__(self):
        super().__init__()
        self.machine_configuration['audio_profile'] = machine_audio_configuration('sb16-opl', 'virtual')
        self.qmp_commands |= {'x-fdisbull-query-opl'}
        self.sb['audiodev-id'] = 'fdisbull-sb16-opl'
        self.opl = {'api-version': 1, 'iobase': 544, 'frequency': 32000,
            'audiodev-id': 'fdisbull-sb16-opl', 'checkpoint-enabled': True,
            'active': False, 'enabled': True}
    def call(self, command):
        if command == 'x-fdisbull-query-opl':
            self.calls.append(command)
            return deepcopy(self.opl)
        return super().call(command)


def test_combined_profile_admits_both_passive_extensions_before_capture():
    vm = OplAdmission()
    assert admit_audio(vm)['state'] == 'idle'
    assert vm.calls == ['x-fdisbull-query-sb16', 'x-fdisbull-query-opl', 'x-fdisbull-query-audio']
    assert vm.native_opl_admission == vm.opl and vm.native_sb16_admission == vm.sb


@pytest.mark.parametrize('mutation', [
    {'api-version': True}, {'api-version': 2}, {'iobase': 0x240}, {'frequency': 44100},
    {'audiodev-id': 'fdisbull-sb16'}, {'checkpoint-enabled': False},
    {'active': 0}, {'enabled': 1},
])
def test_combined_profile_refuses_changed_native_opl_identity(mutation):
    vm = OplAdmission()
    vm.opl.update(mutation)
    with pytest.raises(DebuggerError, match='OPL'):
        admit_audio(vm)
    assert vm.closed and 'x-fdisbull-query-audio' not in vm.calls


def test_combined_profile_refuses_missing_opl_extension():
    vm = OplAdmission()
    vm.qmp_commands -= {'x-fdisbull-query-opl'}
    with pytest.raises(ValueError, match='OPL.*extension'):
        admit_audio(vm)
    assert 'x-fdisbull-query-audio' not in vm.calls
