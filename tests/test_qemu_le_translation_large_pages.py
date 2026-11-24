"""Host evidence checks for protected-mode LE page walks beyond 4 KiB."""
from copy import deepcopy

import pytest

from fdisbull.qemu_le_translation import require_executable_walks, translate_linear
from fdisbull.qemu_le_translation import QEMU_TCG_PAE_ACCESSED_IMAGE


def put(memory, address, value, size):
    memory[address:address + size] = value.to_bytes(size, 'little')


def reader(memory, reads=None):
    def read(address, length):
        value = bytes(memory[address:address + length])
        if len(value) != length:
            raise ValueError('short physical fixture read')
        if reads is not None:
            reads[address, length] = value
        return value
    return read


def legacy_context(*, cr4=0x10):
    return dict(cr0=0x80000001, cr3=0x1000, cr4=cr4, efer=0)


def pae_context():
    return dict(cr0=0x80000001, cr3=0x1000, cr4=0x20, efer=0)


def test_legacy_pse_four_mib_walk_keeps_four_kib_capture_chunks_and_replays():
    memory = bytearray(0x900000)
    put(memory, 0x1000, 0x400000 | 0x83, 4)  # present, writable, 4 MiB page
    memory[0x403ffe:0x404002] = b'abcd'
    captured = {}
    data, walks = translate_linear(legacy_context(), 0x3ffe, 4, reader(memory, captured))

    assert data == b'abcd'
    assert [w['physical'] for w in walks] == [0x403ffe, 0x404000]
    assert [w['length'] for w in walks] == [2, 2]
    for walk in walks:
        assert walk['page_size'] == 0x400000
        assert walk['paging_mode'] == 'legacy-32'
        assert walk['entries'] == [dict(kind='directory', physical_address=0x1000,
                                         value=0x400083, raw='83004000')]
        assert walk['page_attributes'] == dict(writable=True, user=False,
                                                supervisor_write_protect=False)

    replay, replay_walks = translate_linear(legacy_context(), 0x3ffe, 4,
                                             lambda a, n: captured[a, n])
    assert (replay, replay_walks) == (data, walks)
    corrupted = dict(captured)
    corrupted[0x1000, 4] = (0x400081).to_bytes(4, 'little')
    _, tampered_walks = translate_linear(legacy_context(), 0x3ffe, 4,
                                          lambda a, n: corrupted[a, n])
    assert tampered_walks != walks


def test_pae_four_kib_walk_records_three_levels_and_nx_permissions():
    memory = bytearray(0x10000)
    put(memory, 0x1000, 0x2001, 8)  # PDPT -> directory
    put(memory, 0x2000, 0x3007, 8)  # directory -> table
    put(memory, 0x3008, 0x8007 | (1 << 63), 8)  # linear 0x1000 -> NX page
    memory[0x8000:0x8003] = b'LE!'
    context = dict(pae_context(), efer=1 << 11)
    data, walks = translate_linear(context, 0x1000, 3, reader(memory))

    assert data == b'LE!'
    assert len(walks) == 1
    walk = walks[0]
    assert (walk['physical'], walk['page_size'], walk['paging_mode']) == (0x8000, 4096, 'pae')
    assert [entry['kind'] for entry in walk['entries']] == ['pdpt', 'directory', 'table']
    assert [entry['physical_address'] for entry in walk['entries']] == [0x1000, 0x2000, 0x3008]
    assert walk['page_attributes'] == dict(writable=True, user=True,
        supervisor_write_protect=False, execute_disable=True)
    with pytest.raises(ValueError, match='execute'):
        require_executable_walks(walks, 3)


def test_pae_two_mib_walk_crossing_four_kib_boundary_replays_exactly():
    memory = bytearray(0x900000)
    put(memory, 0x1000, 0x2001, 8)
    put(memory, 0x2000, 0x400000 | 0x87, 8)  # present, writable, user, large
    memory[0x400ffe:0x401002] = b'edge'
    captured = {}
    context = pae_context()
    data, walks = translate_linear(context, 0xffe, 4, reader(memory, captured))

    assert data == b'edge'
    assert [walk['physical'] for walk in walks] == [0x400ffe, 0x401000]
    assert [walk['length'] for walk in walks] == [2, 2]
    assert all(walk['page_size'] == 0x200000 and walk['paging_mode'] == 'pae' for walk in walks)
    assert all([entry['kind'] for entry in walk['entries']] == ['pdpt', 'directory'] for walk in walks)
    assert all(walk['page_attributes']['user'] and walk['page_attributes']['writable'] for walk in walks)
    require_executable_walks(walks, 4)

    replay, replay_walks = translate_linear(context, 0xffe, 4,
                                             lambda a, n: captured[a, n])
    assert (replay, replay_walks) == (data, walks)
    tampered = deepcopy(captured)
    tampered[0x2000, 8] = (0x600000 | 0x87).to_bytes(8, 'little')
    with pytest.raises((KeyError, ValueError)):
        translate_linear(context, 0xffe, 4, lambda a, n: tampered[a, n])


def test_pae_two_mib_leaf_boundary_uses_next_nonconsecutive_physical_leaf():
    memory = bytearray(0xa00000)
    put(memory, 0x1000, 0x2001, 8)
    put(memory, 0x2000, 0x400000 | 0x83, 8)
    put(memory, 0x2008, 0x800000 | 0x83, 8)
    memory[0x5fffff:0x600000] = b'a'
    memory[0x800000:0x800001] = b'b'
    data, walks = translate_linear(pae_context(), 0x1fffff, 2, reader(memory))

    assert data == b'ab'
    assert [walk['linear'] for walk in walks] == [0x1fffff, 0x200000]
    assert [walk['physical'] for walk in walks] == [0x5fffff, 0x800000]
    assert [walk['page_size'] for walk in walks] == [0x200000, 0x200000]
    assert [walk['entries'][-1]['physical_address'] for walk in walks] == [0x2000, 0x2008]


def test_pae_nonzero_pdpt_slot_and_cr3_alignment_are_walked_exactly():
    memory = bytearray(0xa00000)
    # CR3 low bits are ignored; the PDPT base remains 32-byte aligned.
    put(memory, 0x1048, 0x3001, 8)  # slot 1 in a 32-byte-aligned, non-page-aligned PDPT
    put(memory, 0x3000, 0x800000 | 0x83, 8)
    memory[0x800000:0x800001] = b'z'
    context = dict(pae_context(), cr3=0x105f)
    data, walks = translate_linear(context, 0x40000000, 1, reader(memory))

    assert data == b'z'
    assert walks[0]['entries'][0]['physical_address'] == 0x1048
    assert walks[0]['entries'][1]['physical_address'] == 0x3000


def test_qemu_pdpte_accessed_bit_requires_exact_native_hash_including_offline_replay():
    memory = bytearray(0x900000)
    put(memory, 0x1000, 0x2001 | 0x20, 8)
    put(memory, 0x2000, 0x400000 | 0x83, 8)
    memory[0x400000:0x400001] = b'q'
    captured = {}
    context = pae_context()

    with pytest.raises(ValueError, match='PDPTE reserved'):
        translate_linear(context, 0, 1, reader(memory))
    with pytest.raises(ValueError, match='PDPTE reserved'):
        translate_linear(context, 0, 1, reader(memory), qemu_image_sha256='f' * 64)

    data, walks = translate_linear(context, 0, 1, reader(memory, captured),
                                   qemu_image_sha256=QEMU_TCG_PAE_ACCESSED_IMAGE)
    assert data == b'q'
    assert walks[0]['entries'][0]['qemu_tcg_accessed'] is True
    from fdisbull.qemu_le_translation import QEMU_TCG_PHYSICAL64_IMAGE
    assert translate_linear(context, 0, 1, reader(memory),
                            qemu_image_sha256=QEMU_TCG_PHYSICAL64_IMAGE)[0] == b'q'
    assert walks[0]['entries'][0]['raw'] == (0x2021).to_bytes(8, 'little').hex()

    # Replaying the retained exact physical reads with a forged profile digest
    # must return to strict architectural validation and reject the PDPTE bit.
    with pytest.raises(ValueError, match='PDPTE reserved'):
        translate_linear(context, 0, 1, lambda a, n: captured[a, n],
                         qemu_image_sha256='f' * 64)


def test_pae_cr3_low_five_bits_are_ignored_as_architecturally_defined():
    memory = bytearray(0x900000)
    put(memory, 0x1000, 0x2001, 8)
    put(memory, 0x2000, 0x400000 | 0x83, 8)
    memory[0x400000:0x400001] = b'x'
    context = dict(pae_context(), cr3=0x101f)
    data, walks = translate_linear(context, 0, 1, reader(memory))
    assert data == b'x'
    assert walks[0]['entries'][0]['physical_address'] == 0x1000


def test_pae_large_page_reserved_bits_nx_without_nxe_and_physical_overflow_refuse():
    memory = bytearray(0x10000)
    put(memory, 0x1000, 0x2001, 8)
    put(memory, 0x2000, 0x400000 | 0x87 | (1 << 13), 8)
    with pytest.raises(ValueError, match='reserved'):
        translate_linear(pae_context(), 0, 1, reader(memory))

    put(memory, 0x2000, 0x400000 | 0x87 | (1 << 63), 8)
    with pytest.raises(ValueError, match='NXE'):
        translate_linear(pae_context(), 0, 1, reader(memory))

    put(memory, 0x2000, (1 << 40) | 0x87, 8)
    with pytest.raises(ValueError, match='high physical'):
        translate_linear(pae_context(), 0, 1, reader(memory))


def test_legacy_non_pae_four_kib_capture_dictionary_remains_byte_for_byte_stable():
    memory = bytearray(0x10000)
    put(memory, 0x1000, 0x2003, 4)
    put(memory, 0x201c, 0x7003, 4)
    memory[0x7fff:0x8000] = b'x'
    data, walks = translate_linear(legacy_context(cr4=0), 0x7fff, 1, reader(memory))
    assert data == b'x'
    assert walks == [dict(linear=0x7fff, length=1, physical=0x7fff, paging=True,
        pde_address=0x1000, pde=0x2003, pde_bytes='03200000',
        pte_address=0x201c, pte=0x7003, pte_bytes='03700000')]


@pytest.mark.parametrize(('large', 'expected'), [(False, 4096), (True, 2**21)])
def test_pae_high_frames_keep_address_bit_32_and_replay_exact_reads(large, expected):
    high = 2**32
    end = high + 32 * 2**20
    # Keep both table and code pointers above 4 GiB. The wrapped addresses
    # contain different bytes so truncating an intermediate read cannot pass.
    tables = {0x1000: (high + 0x2001).to_bytes(8, 'little')}
    if large:
        tables[high + 0x2000] = (high + 0x800083).to_bytes(8, 'little')
    else:
        tables[high + 0x2000] = (high + 0x3003).to_bytes(8, 'little')
        tables[high + 0x3000] = (high + 0x800003).to_bytes(8, 'little')
    tables[high + 0x800005] = b'LE'
    tables[0x800005] = b'xx'
    reads = []

    def physical(a, n):
        reads.append((a, n))
        return tables[a]

    result, walks = translate_linear(pae_context(), 5, 2, physical, high_ram_end=end)
    assert result == b'LE' and walks[0]['physical'] == high + 0x800005
    assert walks[0]['page_size'] == expected
    assert [a for a, _ in reads] == [entry['physical_address'] for entry in walks[0]['entries']] + [high + 0x800005]
    with pytest.raises(ValueError, match='high physical'):
        translate_linear(pae_context(), 5, 2, physical)
    with pytest.raises(ValueError, match='high physical'):
        translate_linear(pae_context(), 5, 2, physical, high_ram_end=high + 0x800000)
    tables[0x1000] = (2 * high + 0x2001).to_bytes(8, 'little')
    with pytest.raises(ValueError, match='high physical'):
        translate_linear(pae_context(), 5, 2, physical, high_ram_end=end)


def test_split_ram_witness_excludes_the_pci_hole_and_bank_end():
    from fdisbull.qemu_paged_le_capture import _ram_limits, _ram_extent

    low_end, high_end = _ram_limits({'memory_mib': 64, 'cpu': 'max', 'max_ram_below_4g_mib': 32})
    assert low_end == 32 * 2**20 and high_end == 2**32 + low_end
    for address, length in [(low_end, 1), (low_end - 1, 2), (2**32 - 1, 2), (high_end, 1), (high_end - 1, 2)]:
        assert not _ram_extent(address, length, low_end, high_end)
    assert _ram_extent(2**32, 1, low_end, high_end)
    assert _ram_extent(high_end - 1, 1, low_end, high_end)
    assert not _ram_extent(2**32, 1, *_ram_limits({'memory_mib': 64}))


def test_pse36_high_leaf_requires_capability_and_preserves_reserved_bits():
    high = 1 << 32
    end = high + 32 * 2**20
    values = {0x1000: (0x800000 | 0x2000 | 0x83).to_bytes(4, 'little'),
              high + 0x800ffe: b'ab', high + 0x801000: b'cd'}
    read = lambda a, n: values[a]
    with pytest.raises(ValueError, match='PSE-36'):
        translate_linear(legacy_context(), 0xffe, 4, read, high_ram_end=end)
    data, walks = translate_linear(legacy_context(), 0xffe, 4, read, high_ram_end=end, pse36=True)
    assert data == b'abcd'
    assert [w['physical'] for w in walks] == [high + 0x800ffe, high + 0x801000]
    assert all(w['page_size'] == 0x400000 and w['paging_mode'] == 'legacy-32' for w in walks)
    for bit in (14, 20, 21):
        values[0x1000] = (0x800000 | 0x2000 | 0x83 | (1 << bit)).to_bytes(4, 'little')
        with pytest.raises(ValueError, match='reserved'):
            translate_linear(legacy_context(), 0xffe, 4, read, high_ram_end=end, pse36=True)
    values[0x1000] = (0x2000000 | 0x2000 | 0x83).to_bytes(4, 'little')
    with pytest.raises(ValueError, match='high RAM extent'):
        translate_linear(legacy_context(), 0, 1, read, high_ram_end=end, pse36=True)


def test_pse36_runtime_profile_is_exact_and_previous_manifest_is_retained():
    from fdisbull.qemu_paged_le_capture import _pse36, _producer, _compatible_producer, _supports_high_ram
    config = {'memory_mib': 64, 'cpu': 'max', 'max_ram_below_4g_mib': 32}
    assert _pse36(config, QEMU_TCG_PAE_ACCESSED_IMAGE)
    from fdisbull.qemu_le_translation import QEMU_TCG_PHYSICAL64_IMAGE
    assert _pse36(config, QEMU_TCG_PHYSICAL64_IMAGE)
    assert not _pse36(config, 'f' * 64)
    assert not _pse36({'memory_mib': 64}, QEMU_TCG_PAE_ACCESSED_IMAGE)
    current = _producer()
    old = dict(current, **{'qemu_le_translation.py': '6e40403e81266323e8e96a978a3c73764b7bc337724880835bc968206ea13ee6',
                          'qemu_paged_le_capture.py': '33e589a44d2e2a8be59c4bd46f814d213cbf7883009b3cd6ef0dfaafe7ae8d44'})
    assert _compatible_producer(old, current) and _supports_high_ram(old, current)
    old['le.py'] = '0' * 64
    assert not _compatible_producer(old, current) and not _supports_high_ram(old, current)


def test_pre_physical64_producer_retains_exact_high_replay_manifest():
    from fdisbull.qemu_paged_le_capture import _producer, _compatible_producer, _supports_high_ram, _supports_pse36
    from fdisbull.qemu_le_translation import QEMU_TCG_PHYSICAL64_IMAGE
    current = _producer()
    prior = dict(current, **{
        'qemu_le_translation.py': 'd25de015b988de444bd70bf53dfd4be64e3ed8651373748b05d679ba6f8c536f',
        'qemu_paged_le_capture.py': '497050af45d0361b56db8015e68ad9503f6983c726afa9e6bb2eac53230a6fba'})
    assert _compatible_producer(prior, current) and _supports_high_ram(prior, current)
    assert _supports_pse36(prior, current, QEMU_TCG_PAE_ACCESSED_IMAGE)
    assert not _supports_pse36(prior, current, QEMU_TCG_PHYSICAL64_IMAGE)
    prior['le.py'] = '0' * 64
    assert not _compatible_producer(prior, current) and not _supports_high_ram(prior, current)
    assert not _supports_pse36(prior, current, QEMU_TCG_PAE_ACCESSED_IMAGE)
