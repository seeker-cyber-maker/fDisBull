"""Split topology must not grant ordinary RAM authority to the low hole."""
from types import SimpleNamespace

import pytest

from fdisbull.qemu_layers import QemuLayerSessionMixin
from fdisbull.qemu_observation_authority import _ranges
from fdisbull.qemu_ram import high_ram_end, low_ram_end


def test_low_ram_end_preserves_default_and_validates_split():
    assert low_ram_end({'memory_mib': 64}) == 64 << 20
    assert high_ram_end({'memory_mib': 64}) is None
    assert low_ram_end({'memory_mib': 4096}) == 0xc0000000
    split = {'memory_mib': 64, 'cpu': 'max', 'max_ram_below_4g_mib': 32}
    assert low_ram_end(split) == 32 << 20
    assert high_ram_end(split) == 0x102000000
    for change in ({'memory_mib': 32}, {'cpu': '486'}, {'max_ram_below_4g_mib': True}):
        with pytest.raises(ValueError, match='Unknown split'):
            low_ram_end({**split, **change})


def test_layers_and_observation_reject_low_hole():
    config = {'memory_mib': 64, 'cpu': 'max', 'max_ram_below_4g_mib': 32}
    vm = SimpleNamespace(machine_configuration=config)
    session = SimpleNamespace(vm=vm)
    QemuLayerSessionMixin._layer_ram_extent(session, (32 << 20) - 1, 1)
    assert _ranges(vm, [((32 << 20) - 1, 1)])
    with pytest.raises(ValueError, match='RAM'):
        QemuLayerSessionMixin._layer_ram_extent(session, 32 << 20, 1)
    with pytest.raises(ValueError, match='RAM'):
        _ranges(vm, [(32 << 20, 1)])
