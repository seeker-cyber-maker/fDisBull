"""Pure stopped-source witnesses; no guest execution or licensed game bytes."""
import struct

import pytest

from fdisbull.le import load_runtime_le_carrier
from fdisbull.qemu_dos_le_match import match, SourceMatchError
from test_le_loader import le_file
from test_le_runtime_carrier import bound_le


def descriptor(base, limit, bits, access=0x9a):
    flags = 0x40 if bits == 32 else 0
    if limit > 65535:
        limit >>= 12
        flags |= 128
    return struct.pack('<HHBBBB', limit & 65535, base & 65535, base >> 16 & 255,
                       access, flags | (limit >> 16 & 15), base >> 24 & 255)


def fixture(*, bridge=False, rpl=0):
    code = b''.join(b'\xb8' + bytes(4) + b'\x90' * 3 for _ in range(8)) + b''.join(bytes([0x6a, i]) for i in range(80))
    data = bytes.fromhex('b81122bb3344b95566ba77889090b80000be99aabfbbcc90c3') if bridge else b'abcdefghijklmnopqrstuvwxyz0123456789' * 3
    fixups = [b'', struct.pack('<BBhBH', 5, 0, 15, 2, 2)] if bridge else [b''.join(struct.pack('<BBhBH', 7, 0, i*8+1, 2, i) for i in range(8)), b'']
    image = load_runtime_le_carrier(bound_le(le_file(code=code, data=data, fixups=fixups,
        object_sizes=(len(code), len(data)), object_flags=(0x2045, 0x1045 if bridge else 0x2043))))
    access = 0xfa if rpl == 3 else 0x9a
    table = bytes(8) + descriptor(0, 0xffffffff, 32, access) + (descriptor(0x91000, len(data)-1, 16) if bridge else bytes(8))
    cpu = dict(mode='protected', bits=32, cs=8 | rpl, ip=0x50040, cs_base=0, cs_limit=0xffffffff,
               cs_attributes=0xc00000 | access << 8)
    runtime = bytearray(image.regions[0].data)
    for fixup in image.metadata['le']['fixups']:
        if fixup['source_type'] == 'offset32':
            struct.pack_into('<I', runtime, fixup['source_offset'], 0x70000 + fixup['target_offset'])
    secondary = bytearray(image.regions[1].data)
    if bridge:
        secondary[15:17] = b'\x02\xf0'
    memory = [(0x50000, bytes(runtime)), (0x91000 if bridge else 0x70000, bytes(secondary))]
    reads = []
    def read(address, length):
        reads.append((address, length))
        for start, data in reversed(memory):
            if start <= address and address + length <= start + len(data):
                return data[address-start:address-start+length]
        return bytes(length)
    return image, cpu, table, memory, reads, read


def test_current_code_entry_and_eight_fixup_data_witness_retain_original_namespace():
    image, cpu, table, memory, reads, read = fixture()
    result = match(image, cpu, table, read)
    evidence = result['identity_evidence']
    assert evidence['current_pc_source_match']['object_offset'] == 64
    assert evidence['runtime_code_base'] == 0x50000 and not evidence['lifetime_qualified']
    assert evidence['object_proofs'][0]['runtime_base'] == 0x70000
    assert len(evidence['object_proofs'][0]['offset32_sites']) == 8
    assert {s['object_id'] for s in result['source_spans']} == {'le:1', 'le:2'}
    assert all(s['source_view'] == 'embedded-le' and 'project_address' not in s for s in result['source_spans'])
    assert next(s for s in result['source_spans'] if s['name'] == 'entry-code')['object_offset'] == 0
    for span in result['source_spans']:
        assert sum(f['length'] for f in span['file_fragments']) == span['length']
        assert min(f['file_offset'] for f in span['file_fragments']) >= 1024
    assert result['budget']['compared_bytes'] == sum(n for _, n in reads)


def test_runtime_symbolic_bridge_bytes_are_excluded_without_claiming_execution():
    image, cpu, table, memory, reads, read = fixture(bridge=True)
    result = match(image, cpu, table, read)
    bridge = next(s for s in result['source_spans'] if s['name'] == 'bridge-2')
    assert bridge['compared_bytes'] == 23 and bridge['fixups'] == [dict(offset=15, length=2)]
    assert bridge['expected_sha256'] != bridge['observed_sha256']
    proof = result['identity_evidence']['object_proofs'][0]
    assert not proof['execution_observed'] and not proof['symbolic_operands_qualified']
    changed = bytearray(memory[1][1]); changed[0] ^= 1; memory.append((0x91000, bytes(changed)))
    assert all(s['name'] != 'bridge-2' for s in match(image, cpu, table, read)['source_spans'])


def test_rpl_bits_select_same_gdt_entry_and_duplicated_limit_nibble_is_allowed():
    image, cpu, table, memory, reads, read = fixture(rpl=3)
    cpu['cs_attributes'] |= 0xf0000
    assert match(image, cpu, table, read)['identity_evidence']['current_descriptor']['value'] == 8


@pytest.mark.parametrize('kind', ['ldt', 'null', 'rpl-dpl', 'cs-base', 'cs-limit', 'cs-flags', 'segment-tail', 'not-present', 'not-code'])
def test_descriptor_and_hidden_cache_refusals_precede_runtime_reads(kind):
    image, cpu, table, memory, reads, read = fixture()
    if kind == 'ldt': cpu['cs'] |= 4
    elif kind == 'null': cpu['cs'] = 0
    elif kind == 'rpl-dpl': cpu['cs'] |= 3
    elif kind == 'cs-base': cpu['cs_base'] = 16
    elif kind == 'cs-limit': cpu['cs_limit'] -= 1
    elif kind == 'cs-flags': cpu['cs_attributes'] ^= 0x400000
    elif kind == 'segment-tail':
        table = bytes(8) + descriptor(0, 0x50050, 32) + bytes(8)
        cpu['cs_limit'] = 0x50fff
        cpu['ip'] = 0x50fff - 94
    else:
        row = bytearray(table); row[13] &= ~0x80 if kind == 'not-present' else ~8; table = bytes(row)
    with pytest.raises(SourceMatchError):
        match(image, cpu, table, read)
    assert not reads


def test_inconsistent_data_fixup_sites_refuse_the_entire_candidate():
    image, cpu, table, memory, reads, read = fixture()
    changed = bytearray(memory[0][1]); struct.pack_into('<I', changed, 1, 0x71000)
    memory.append((0x50000, bytes(changed)))
    with pytest.raises(SourceMatchError, match='inconsistent'):
        match(image, cpu, table, read)


def test_two_matching_bridge_descriptors_refuse_ambiguity():
    image, cpu, table, memory, reads, read = fixture(bridge=True)
    table += descriptor(0x92000, 24, 16)
    memory.append((0x92000, memory[1][1]))
    with pytest.raises(SourceMatchError, match='ambiguous'):
        match(image, cpu, table, read)


def test_same_current_window_in_two_code_objects_refuses_placement_ambiguity():
    code = b''.join(bytes([0x6a, i]) for i in range(110))
    image = load_runtime_le_carrier(le_file(code=code, data=code, fixups=[b'', b''],
                                           object_flags=(0x2045, 0x2045)))
    cpu = dict(mode='protected', bits=32, cs=8, ip=0x50040, cs_base=0,
               cs_limit=0xffffffff, cs_attributes=0xc09a00)
    table = bytes(8) + descriptor(0, 0xffffffff, 32)
    def read(address, length):
        return code[address-0x50000:address-0x50000+length]
    with pytest.raises(SourceMatchError, match='ambiguous protected'):
        match(image, cpu, table, read)


def test_changed_nonfixup_entry_code_refuses_even_when_current_window_matches():
    image, cpu, table, memory, reads, read = fixture()
    changed = bytearray(memory[0][1]); changed[0] ^= 1
    memory.append((0x50000, bytes(changed)))
    with pytest.raises(SourceMatchError, match='changed source bytes'):
        match(image, cpu, table, read)


@pytest.mark.parametrize('options', [dict(max_compare_bytes=100), dict(max_scan_bytes=1),
                                   dict(max_compare_bytes=True), dict(max_scan_bytes=16777217)])
def test_budgets_never_publish_partial_matches(options):
    image, cpu, table, memory, reads, read = fixture()
    with pytest.raises(SourceMatchError, match='budget'):
        match(image, cpu, table, read, **options)


def test_unrelated_current_pc_returns_no_candidate_and_short_reads_refuse():
    image, cpu, table, memory, reads, read = fixture()
    cpu['ip'] = 0x60000
    assert match(image, cpu, table, read) is None
    with pytest.raises(SourceMatchError, match='short'):
        match(image, cpu, table, lambda *_: b'')


def test_source_identity_tamper_refuses_before_runtime_reads():
    image, cpu, table, memory, reads, read = fixture()
    image.metadata['source_sha256'] = '0' * 64
    with pytest.raises(SourceMatchError, match='source identity'):
        match(image, cpu, table, read)
    assert not reads


@pytest.mark.parametrize('second_has_no_unique_anchor', [False, True])
@pytest.mark.parametrize('entrypoint', ['qemu', 'legacy'])
def test_complementary_fixup_masks_refuse_same_object_placement_ambiguity(
        second_has_no_unique_anchor, entrypoint):
    observed = bytes(range(96))
    code = bytearray(b'\xcc' * 224)
    code[:96] = code[128:224] = observed
    # P retains A and masks B; Q masks A and retains B. Both complete
    # windows match the observation, although P has a unique raw A anchor.
    sites = [*range(16, 32, 4), *range(128, 144, 4)]
    fixups = b''.join(struct.pack('<BBhBH', 7, 0, site, 2, i)
                     for i, site in enumerate(sites))
    if second_has_no_unique_anchor:
        # A short non-window decoy duplicates every remaining anchor of Q
        # that is not already duplicated by P. It cannot hold a 96-byte match.
        code += observed[16:47]
    image = load_runtime_le_carrier(le_file(code=bytes(code), data=b'D' * 64,
        fixups=[fixups, b''], object_sizes=(len(code), 64),
        object_flags=(0x2045, 0x2045)))
    source = image.regions[0].data
    if second_has_no_unique_anchor:
        assert all(source.count(observed[at:at + 16]) >= 2 for at in range(16, 81))
    for offset, excluded in ((0, set(range(16, 32))), (128, set(range(16)))):
        assert all(source[offset + i] == value for i, value in enumerate(observed)
                   if i not in excluded)
    if entrypoint == 'legacy':
        from fdisbull import runtime_source_matching as legacy
        intervals = [(site, site + 4) for site in sites]
        with pytest.raises(legacy.SourceMatchError, match='ambiguous'):
            legacy._signature(source, observed, intervals,
                              legacy._Budget(None, 524288, 16777216))
        return
    runtime = bytearray(source)
    runtime[:96] = runtime[128:224] = observed
    cpu = dict(mode='protected', bits=32, cs=8, ip=0x50000, cs_base=0,
               cs_limit=0xffffffff, cs_attributes=0xc09a00)
    table = bytes(8) + descriptor(0, 0xffffffff, 32)
    def read(address, length):
        return bytes(runtime[address-0x50000:address-0x50000+length])
    with pytest.raises(SourceMatchError, match='ambiguous'):
        match(image, cpu, table, read)


def test_zero_filled_alternatives_do_not_make_a_unique_file_backed_window_ambiguous():
    # Only 96 bytes are present in the physical page. The rest of object 1
    # and the entirely zero-filled object 2 cannot supply source extents.
    image = load_runtime_le_carrier(le_file(code=bytes(96), data=bytes(4096),
        fixups=[b'', b''], page_flags=[0, 3], object_sizes=(8192, 4096),
        object_flags=(0x2045, 0x2045)))
    cpu = dict(mode='protected', bits=32, cs=8, ip=0x50000, cs_base=0,
               cs_limit=0xffffffff, cs_attributes=0xc09a00)
    table = bytes(8) + descriptor(0, 0xffffffff, 32)
    result = match(image, cpu, table, lambda address, length: bytes(length))
    assert result['identity_evidence']['code_object'] == 1
    assert result['identity_evidence']['current_pc_source_match']['object_offset'] == 0
    assert result['source_spans'][0]['compared_bytes'] == 96
