"""Public passive-query assertions shared by native checkpoint witnesses."""
import os


def mixer_snapshot(debug):
    available = debug.capabilities.get('mixer_gain_readback', False)
    if os.environ.get('FDISBULL_REQUIRE_QEMU_MIXER') == '1':
        assert available, 'Required native mixer gain readback is unavailable'
    if not available:
        return None
    cpu = debug.registers()
    first = debug.mixer_observe()
    second = debug.mixer_observe()
    assert second['native'] == first['native']
    assert debug.registers() == cpu
    for receipt in (first, second):
        before, after = receipt['clocks']['before'], receipt['clocks']['after']
        assert before['virtual_ns'] == after['virtual_ns']
        assert before['counter'] == after['counter']
    return first['native']
