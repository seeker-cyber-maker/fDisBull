"""Offline checks for strict owned-checkpoint long-mode page fences."""
import pytest

from fdisbull.qemu_long_mode_fence import canonical, walk


def _tables():
    memory = bytearray(0x8000)
    for address, value in ((0x1000, 0x2003), (0x2000, 0x3003),
                           (0x3000, 0x4003), (0x4000 + 8 * 5, 0x6003)):
        memory[address:address + 8] = value.to_bytes(8, 'little')
    state = {'control': {'CR0': '0x80010001', 'CR3': '0x1000',
                         'CR4': '0x20', 'EFER': '0xd00'},
             'segments': {'cs': {'selector': '0x8'}}}
    return state, memory


def _reader(memory):
    return lambda address, size: bytes(memory[address:address + size])


def test_four_level_fence_walk_and_canonical_addresses():
    state, memory = _tables()
    result = walk(state, 0x5000, _reader(memory), execute=True, write=True)
    assert result['physical_address'] == '0x6000'
    assert [item['kind'] for item in result['walk']['entries']] == ['pml4', 'pdpt', 'directory', 'table']
    assert canonical(0xffff800000000000)
    assert not canonical(0x800000000000)
    with pytest.raises(ValueError, match='canonical'):
        walk(state, 0x800000000000, _reader(memory))


@pytest.mark.parametrize('value,access', [(0x6001, {'write': True}),
                                          (0x8000000000006003, {'execute': True}),
                                          (0x100000006003, {}), (0, {})])
def test_fence_refuses_denied_or_invalid_leaf(value, access):
    state, memory = _tables()
    memory[0x4028:0x4030] = value.to_bytes(8, 'little')
    with pytest.raises(ValueError):
        walk(state, 0x5000, _reader(memory), **access)


def test_fence_refuses_la57_and_reserved_large_page_address():
    state, memory = _tables()
    state['control']['CR4'] = '0x1020'
    with pytest.raises(ValueError, match='controls'):
        walk(state, 0x5000, _reader(memory))
    state['control']['CR4'] = '0x20'
    memory[0x3000:0x3008] = (0x2083).to_bytes(8, 'little')
    with pytest.raises(ValueError, match='large-page'):
        walk(state, 0x5000, _reader(memory))
