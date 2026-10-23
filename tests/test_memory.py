"""CPU memory semantics and stored-source queries, without executing input code."""
import hashlib
import json
import struct

import pytest

from fdisbull.memory import MEMORY_FACTS_REVISION, instruction_memory_accesses
from fdisbull.project import Project


def memory(raw, *, address=0x1000, bits=64, arch='x86', registers=None, cs=None):
    return instruction_memory_accesses(bytes.fromhex(raw), address, arch, bits,
                                       cs=cs, registers=registers)


@pytest.mark.parametrize('raw,category,read,write,width,target', [
    ('488b0520000000', 'read', True, False, 8, 0x1027),
    ('48890520000000', 'write', False, True, 8, 0x1027),
    ('83051000000001', 'read_write', True, True, 4, 0x1017),
    ('0fb10d10000000', 'conditional_write', True, True, 4, 0x1017),
    ('488d0520000000', 'address_only', False, False, None, 0x1027),
])
def test_real_x86_access_flags_width_and_rip_target(raw, category, read, write, width, target):
    fact, = memory(raw)
    assert (fact['access'], fact['may_read'], fact['may_write'], fact['width']) == (category, read, write, width)
    assert fact['concrete_target'] == target and fact['interval_exact']
    assert fact['base_register'] == 'rip' and fact['displacement'] == (0x20 if target == 0x1027 else 0x10)
    assert fact['conditional_write'] == (category == 'conditional_write')


def test_indexed_store_needs_every_register_and_uses_real_scale():
    unknown, = memory('89448b10', bits=32, registers={'ebx': 0x2000})
    assert unknown['access'] == 'write' and unknown['concrete_target'] is None
    assert unknown['index_register'] == 'ecx' and unknown['scale'] == 4
    known, = memory('89448b10', bits=32, registers={'ebx': 0x2000, 'ecx': 3})
    assert known['concrete_target'] == 0x201c and known['width'] == 4
    assert unknown['unresolved_reasons'] == ['unknown address register ecx']


def test_dos_segments_variants_and_unknown_selector_are_explicit():
    facts = memory('8907', address=0x10000, bits=16, cs=0x1000,
                   registers={'bx': 0x6f90, 'ds': [0x4020, 0x4021]})
    assert {f['segment_selector'] for f in facts} == {0x4020, 0x4021}
    assert {f['concrete_target'] for f in facts} == {0x47190, 0x471a0}
    unknown, = memory('8907', address=0x10000, bits=16, cs=0x1000, registers={'bx': 0x6f90})
    assert unknown['effective_offset'] == 0x6f90 and unknown['concrete_target'] is None
    assert unknown['segment_selector'] is None and 'unknown real-mode segment ds' in unknown['unresolved_reasons']


def test_unknown_index_is_bounded_by_actual_segment_not_all_aliases():
    fact, = memory('0187886f', address=0x10000, bits=16, cs=0x1000, registers={'ds': 0x4020})
    assert fact['access'] == 'read_write' and fact['concrete_target'] is None
    assert (fact['possible_start'], fact['possible_end']) == (0x40200, 0x50200)
    known, = memory('0187886f', address=0x10000, bits=16, cs=0x1000, registers={'ds': 0x4020, 'bx': 8})
    assert known['concrete_target'] == 0x47190


def test_stack_implicit_memory_uses_preinstruction_sp_and_ss():
    fact, = memory('50', address=0x10000, bits=16, cs=0x1000, registers={'ss': 0x4d04, 'sp': 0x80})
    assert fact['implicit'] and fact['access'] == 'write'
    assert fact['width'] == 2 and fact['effective_offset'] == 0x7e
    assert fact['concrete_target'] == 0x4d0be and fact['segment_register'] == 'ss'


def test_xlat_uses_known_low_byte_alias_and_segment_override_is_authoritative():
    fact, = memory('d7', address=0x10000, bits=16, cs=0x1000,
                   registers={'ds': 0x4020, 'bx': 0x100, 'ax': 0x1203})
    assert fact['concrete_target'] == 0x40303 and fact['width'] == 1
    cs_read, = memory('2ea13000', address=0x10000, bits=16, cs=0x1000, registers={'ds': 0x4020})
    assert cs_read['segment_register'] == 'cs' and cs_read['concrete_target'] == 0x10030


def test_rep_stos_has_element_width_count_direction_and_zero_count():
    state = {'es': 0x4020, 'di': 0x100, 'cx': 4, 'df': 0}
    fact, = memory('f3ab', address=0x10000, bits=16, cs=0x1000, registers=state)
    assert fact['width'] == 2 and fact['access'] == 'conditional_write'
    assert (fact['interval_start'], fact['interval_end'], fact['interval_exact']) == (0x40300, 0x40308, True)
    backwards, = memory('f3ab', address=0x10000, bits=16, cs=0x1000, registers=dict(state, df=1))
    assert (backwards['interval_start'], backwards['interval_end']) == (0x402fa, 0x40302)
    assert memory('f3ab', address=0x10000, bits=16, cs=0x1000, registers=dict(state, cx=0)) == []
    unknown, = memory('f3ab', address=0x10000, bits=16, cs=0x1000, registers={k: v for k, v in state.items() if k != 'df'})
    assert unknown['concrete_target'] == 0x40300 and not unknown['interval_exact']
    assert unknown['interval_start'] is None and unknown['repeat']['direction'] is None
    assert (unknown['possible_start'], unknown['possible_end']) == (0x40200, 0x50200)


def test_rep_movs_captures_both_implicit_directions_and_32bit_count():
    facts = memory('f3a4', bits=32, registers={'esi': 0x2000, 'edi': 0x3000, 'ecx': 3, 'df': 0})
    assert {(f['access'], f['interval_start'], f['interval_end']) for f in facts} == {
        ('read', 0x2000, 0x2003), ('conditional_write', 0x3000, 0x3003)}
    assert all(f['width'] == 1 and f['implicit'] for f in facts)


def test_repeat_wrap_and_early_stop_are_possible_bounds_not_exact_intervals():
    wrapped, = memory('f3ab', address=0x10000, bits=16, cs=0x1000,
                      registers={'es': 0x4020, 'di': 0xffff, 'cx': 2, 'df': 0})
    assert not wrapped['interval_exact'] and wrapped['interval_start'] is None
    assert any('wrap' in reason for reason in wrapped['unresolved_reasons'])
    scan, = memory('f2ae', address=0x10000, bits=16, cs=0x1000,
                   registers={'es': 0x4020, 'di': 0x100, 'cx': 8, 'df': 0})
    assert scan['repeat']['early_stop'] and not scan['interval_exact']
    assert (scan['possible_start'], scan['possible_end']) == (0x40300, 0x40308)


def test_lea_offset_and_fs_selector_never_fabricate_physical_addresses():
    lea, = memory('8d07', address=0x10000, bits=16, cs=0x1000, registers={'bx': 0x30, 'ds': 0x2000})
    assert lea['access'] == 'address_only' and lea['effective_offset'] == 0x30
    assert lea['concrete_target'] is None and not lea['may_write']
    fs, = memory('64488b042520000000', registers={'fs': 0x30})
    assert fs['segment_register'] == 'fs' and fs['concrete_target'] is None
    resolved, = memory('64488b042520000000', registers={'fs_base': 0x7000})
    assert resolved['concrete_target'] == 0x7020


@pytest.mark.parametrize('raw,category,width', [
    ('200000f9', 'write', 8), ('200040f9', 'read', 8),
    ('200000b9', 'write', 4), ('20008039', 'read', 1),
    ('200400a9', 'write', 16), ('200440a9', 'read', 16),
    ('417c00c8', 'conditional_write', 8), ('417ca0c8', 'conditional_write', 8),
    ('418020f8', 'read_write', 8), ('410020f8', 'read_write', 8),
    ('200080f9', 'address_only', None),
    ('2070404c', 'read', 16), ('2070004c', 'write', 16),
    ('20c0404d', 'read', 1),  # LD1R repeats one byte into a vector.
])
def test_arm_real_bytes_correct_capstone_access_metadata(raw, category, width):
    fact, = memory(raw, arch='arm64', registers={'x1': 0x2000, 'x2': 0x3000})
    assert (fact['access'], fact['width']) == (category, width)
    assert fact['concrete_target'] in (0x2000, 0x3000)
    if category == 'write':
        assert not fact['may_read']
    if category == 'conditional_write':
        assert fact['conditional_write']


def test_arm_literal_index_and_unknown_register_resolution():
    literal, = memory('40000058', arch='arm64')  # LDR X0, literal PC+8
    assert (literal['access'], literal['width'], literal['concrete_target']) == ('read', 8, 0x1008)
    indexed, = memory('207820f8', arch='arm64', registers={'x1': 0x2000, 'x0': 3})
    assert indexed['concrete_target'] == 0x2018 and indexed['scale'] == 8
    unknown, = memory('207820f8', arch='arm64', registers={'x1': 0x2000})
    assert unknown['concrete_target'] is None


def test_invalid_and_truncated_bytes_have_no_invented_access():
    assert memory('0f') == [] and memory('ffffffff', arch='arm64') == []
    with pytest.raises(ValueError, match='CS'):
        memory('8907', bits=16, address=0x10000, cs=0x2000)
    with pytest.raises(ValueError, match='known register'):
        memory('8907', registers=['ds'])
    assert memory('8907', bits=16, address=0x1ffff, cs=0x1000) == []


def key(address):
    return f'{address:016x}'


@pytest.fixture
def stored(tmp_path):
    header = bytearray(64)
    struct.pack_into('<14H', header, 0, 0x5a4d, 320, 1, 0, 4, 0, 0xffff, 0, 0x80, 0, 0, 0, 28, 0)
    source = tmp_path / 'access.exe'
    source.write_bytes(bytes(header) + b'\xc3' + bytes(255))
    project = Project.create(tmp_path / 'access.fdb', source)
    for table in ('instructions', 'dos_states', 'memory_refs', 'analysis_facts_revision'):
        project.db.execute(f'DELETE FROM {table}')
    rows = [
        (0x10000, 0x1000, 'a1906f', {'ds': 0x4020}, 'read'),
        (0x10010, 0x1000, 'a38f6f', {'ds': 0x4020}, 'word store spans queried byte'),
        (0x10020, 0x1000, '0187886f', {'ds': 0x4020}, 'unknown staff index'),
        (0x10030, 0x1000, '8906a06f', {}, 'unknown DS'),
        (0x10040, 0x1000, '8907', {'ss': 0x4d04}, 'unknown DS is not SS'),
        (0x10050, 0x1000, '368907', {'ss': 0x4d04}, 'known SS cannot reach query'),
        (0x10060, 0x1000, 'f3ab', {'es': 0x4020, 'di': 0x6f88, 'cx': 8}, 'bulk initialization unknown DF'),
        (0x10070, 0x1001, 'a38f6f', {'ds': 0x4020}, 'different source CS'),
    ]
    for address, selector, raw, registers, reason in rows:
        context = f'x86:16:little:cs={selector:04x}'
        project.db.execute('INSERT INTO instructions VALUES (?,?,?,?,?,?,?,?,?)',
                           (1, context, key(address), len(bytes.fromhex(raw)), raw, 'fixture', 'raw operands', 'next', None))
        project.db.execute('INSERT INTO dos_states VALUES (?,?,?,?,?,?)',
                           (1, context, key(address), json.dumps(registers), 'done', reason))
    project.db.commit()
    yield project
    project.db.close()


def test_writer_query_overlaps_full_width_and_keeps_all_source_cs(stored):
    result = stored.memory_accesses('4020:6f90', access='write', include_unresolved=False)
    assert result['address'] == '0x47190' and result['selector'] == 0x4020
    assert result['address_matches'] == result['total'] == 2
    assert {r['source'] for r in result['items']} == {'0x10010', '0x10070'}
    assert {r['source_cs'] for r in result['items']} == {0x1000, 0x1001}
    assert all(r['concrete_target'] == 0x4718f and r['width'] == 2 for r in result['items'])
    assert all(r['bytes'] == 'a38f6f' and r['state_assumptions']['registers'] == {'ds': 0x4020} for r in result['items'])


def test_writer_query_separates_unknown_candidates_and_prunes_ss_window(stored):
    result = stored.memory_accesses('4020:6f90', access='write')
    assert result['address_matches'] == 2 and result['unresolved_candidates'] == 4
    candidates = [r for r in result['items'] if r['match'] == 'unresolved_candidate']
    assert {r['source'] for r in candidates} == {'0x10020', '0x10030', '0x10040', '0x10060'}
    assert all(not r['interval_exact'] for r in candidates)
    assert next(r for r in candidates if r['source'] == '0x10020')['access'] == 'read_write'
    assert not any(r['source'] == '0x10050' for r in result['items'])
    assert result['facts_source'] == 'decoded_stored_instructions' and result['warnings']


def test_read_filter_and_pagination_preserve_original_categories(stored):
    reads = stored.memory_accesses(0x47190, access='read')
    assert reads['address_matches'] == 1
    assert {r['access'] for r in reads['items']} == {'read', 'read_write'}
    page = stored.memory_accesses(0x47190, access='write', limit=1, offset=1)
    assert [r['source'] for r in page['items']] == ['0x10070'] and page['has_more']
    page = stored.memory_accesses(0x47190, access='write', limit=2, offset=2)
    assert [r['source'] for r in page['items']] == ['0x10020', '0x10030']
    assert all(r['match'] == 'unresolved_candidate' for r in page['items'])


def test_dword_store_overlaps_middle_bytes_but_not_exclusive_end(stored):
    context = 'x86:16:little:cs=1000'
    stored.db.execute('INSERT INTO instructions VALUES (?,?,?,?,?,?,?,?,?)',
                      (1, context, key(0x10080), 4, '66a38e6f', 'mov', '[6f8e],eax', 'next', None))
    stored.db.execute('INSERT INTO dos_states VALUES (?,?,?,?,?,?)',
                      (1, context, key(0x10080), '{"ds":16416}', 'done', 'known destination'))
    stored.db.commit()
    result = stored.memory_accesses(0x47190, access='write', include_unresolved=False)
    match = next(row for row in result['items'] if row['source'] == '0x10080')
    assert match['width'] == 4 and match['interval_end'] == 0x47192
    result = stored.memory_accesses(0x47192, access='write', include_unresolved=False)
    assert not any(row['source'] == '0x10080' for row in result['items'])


def test_current_persisted_facts_and_readonly_fallback_agree(stored):
    expected = stored.memory_accesses(0x47190, access='write')
    for row in stored.db.execute('SELECT i.*,s.registers FROM instructions i JOIN dos_states s USING(version,context,address)').fetchall():
        for fact in instruction_memory_accesses(bytes.fromhex(row['bytes']), int(row['address'], 16), 'x86', 16,
                                                cs=int(row['context'][-4:], 16), registers=json.loads(row['registers'])):
            detail = json.dumps(fact, sort_keys=True, separators=(',', ':'))
            stored.db.execute('INSERT INTO memory_refs VALUES (?,?,?,?,?)',
                              (1, row['context'], row['address'], hashlib.sha256(detail.encode()).hexdigest(), detail))
    stored.db.execute('INSERT INTO analysis_facts_revision VALUES (?,?)', (1, MEMORY_FACTS_REVISION))
    stored.db.commit()
    changes = stored.db.total_changes
    result = stored.memory_accesses(0x47190, access='write')
    assert result['facts_source'] == 'persisted'
    assert result['items'] == expected['items'] and result['total'] == expected['total']
    assert stored.db.total_changes == changes
    stored.db.execute('UPDATE analysis_facts_revision SET revision=0')
    stored.db.commit()
    assert stored.memory_accesses(0x47190, access='write')['facts_source'] == 'decoded_stored_instructions'
