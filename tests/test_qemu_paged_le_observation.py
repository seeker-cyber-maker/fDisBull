from copy import deepcopy

from fdisbull.qemu_paged_le_observation import observe, replay
from test_qemu_dos_le_match import fixture


def test_fresh_observation_replays_and_fails_closed_on_changed_descriptor():
    image, cpu, table, memory, _, _ = fixture()
    cpu['ip'] = 0x50000
    context = dict(cr0=1, cr3=0, cr4=0, efer=0, gdt=dict(base=0x30000, limit=len(table) - 1))
    mem = bytearray(0x100000)
    mem[0x30000 : 0x30000 + len(table)] = table
    for address, data in memory:
        mem[address : address + len(data)] = data

    def read(address, length):
        return bytes(mem[address : address + length])

    result = observe(image, 7, cpu, context, read, read)
    assert result['qualification']['qualified']
    assert result['qualification']['source_location']['object_offset'] == 0
    assert result['mapping_identity']['instruction_backing'][0]['physical'] == 0x50000
    assert replay(image, 7, result['witness']) == result
    changed = deepcopy(cpu)
    changed['cs_base'] = 1
    unknown = observe(image, 7, changed, context, read, read)
    assert not unknown['qualification']['qualified']
    assert unknown['qualification']['source_location'] is None
    assert unknown['mapping_identity'] is None
    assert observe(image, 7, cpu, context, read, read)['qualification']['qualified']


def test_remap_selector_outside_and_return_are_independent():
    image, cpu, table, memory, _, _ = fixture()
    cpu['ip'] = 0x50000
    mem = bytearray(0x300000)
    # Two selectors share an identical descriptor. The alternate code page is
    # a byte-for-byte copy, but its physical location is distinct evidence.
    table = table + table[8:16]
    mem[0x30000 : 0x30000 + len(table)] = table
    for address, data in memory:
        mem[address : address + len(data)] = data
    mem[0x150000:0x151000] = mem[0x50000:0x51000]
    mem[0x200000:0x200004] = (0x201003).to_bytes(4, 'little')
    for i in range(1024):
        mem[0x201000 + i * 4 : 0x201004 + i * 4] = (i * 4096 | 3).to_bytes(4, 'little')
    context = dict(
        cr0=0x80000001, cr3=0x200000, cr4=0, efer=0, gdt=dict(base=0x30000, limit=len(table) - 1)
    )

    def physical(a, n):
        return bytes(mem[a : a + n])

    def virtual(a, n):
        assert a // 4096 == (a + n - 1) // 4096
        pte = int.from_bytes(mem[0x201000 + (a // 4096) * 4 : 0x201004 + (a // 4096) * 4], 'little')
        return physical((pte & ~4095) + (a & 4095), n)

    first = observe(image, 7, cpu, context, physical, virtual)
    assert first['qualification']['qualified']
    mem[0x201000 + 0x50 * 4 : 0x201004 + 0x50 * 4] = (0x150003).to_bytes(4, 'little')
    remapped = observe(image, 7, cpu, context, physical, virtual)
    assert remapped['qualification']['qualified']
    assert remapped['qualification']['source_location'] == first['qualification']['source_location']
    assert remapped['mapping_identity']['instruction_backing'][0]['physical'] == 0x150000
    assert replay(image, 7, remapped['witness']) == remapped
    changed = dict(cpu, cs=0x18)
    switched = observe(image, 7, changed, context, physical, virtual)
    assert switched['qualification']['qualified']
    assert switched['mapping_identity']['selector'] == 0x18
    outside = observe(image, 7, dict(changed, ip=0x80000), context, physical, virtual)
    assert not outside['qualification']['qualified'] and outside['mapping_identity'] is None
    assert observe(image, 7, changed, context, physical, virtual)['qualification']['qualified']


def test_transport_failure_propagates_and_replay_budget_is_checked(monkeypatch):
    import pytest
    from fdisbull.dosbox_rpc import DebuggerError
    from fdisbull import qemu_paged_le_observation as module

    def interpret(image, cpu, context, read):
        read(0, 1)

    monkeypatch.setattr(module, '_interpret', interpret)

    def broken(*args):
        raise DebuggerError('transport failed')

    with pytest.raises(DebuggerError, match='transport failed'):
        observe(None, 1, {}, dict(cr0=1, cr3=0, cr4=0, efer=0), broken, broken)
    result = replay(None, 1, dict(cpu={}, context={}, reads=[dict(length=2097153, hex='')]))
    assert not result['qualification']['qualified']
    assert 'budget' in result['qualification']['reason']
