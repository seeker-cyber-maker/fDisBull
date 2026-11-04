from copy import deepcopy
import struct

import pytest

from fdisbull.serializer_candidates import extract_serializer_candidates, summarize_serializer_candidates


BASE = 0x1000
WRITER = {'entry': 0x5000, 'operation': 'write', 'filename': 'eax',
          'buffer': 'edx', 'length': 'ebx'}
READER = {'entry': 0x6000, 'operation': 'read', 'filename': 'edx', 'buffer': 'eax'}


def u32(value):
    return struct.pack('<I', value)


def call(code, target):
    return code + b'\xe8' + struct.pack('<i', target-(BASE+len(code)+5))


def analyze(code, data=None, **options):
    reads = []
    mappings = {BASE: code, **(data or {})}

    def read(address, size):
        reads.append((address, size))
        for base, raw in mappings.items():
            if base <= address < base+len(raw):
                return raw[address-base:address-base+size]
        raise ValueError('unmapped')

    result = extract_serializer_candidates(read, ranges=[(BASE, BASE+len(code))],
                                          serializers=[WRITER, READER], code_base=BASE,
                                          address_space='test preferred addresses', **options)
    return result, reads


def test_pairs_original_filename_and_pointer_identity_without_dereferencing():
    code = b'\xb8'+u32(0x3000) + b'\x8b\x15'+u32(0x4000) + b'\xbb'+u32(37)
    code = call(code, WRITER['entry'])
    code += b'\xba'+u32(0x3000) + b'\xa1'+u32(0x4000)
    code = call(code, READER['entry']) + b'\xc3'
    result, reads = analyze(code, {0x3000: b'custom/actors.bin\0', 0x4000: u32(0x12345678)})
    writer, reader = result['candidates']
    assert writer['filename']['text'] == 'custom/actors.bin'
    assert writer['filename']['kind'] == 'direct'
    assert writer['buffer'] == {'kind': 'pointer_global', 'address': 0x4000, 'pointer_width': 4}
    assert reader['buffer'] == writer['buffer']
    assert writer['length'] == 37 and reader['length'] is None
    assert not any(address == 0x4000 for address, _ in reads)
    assert result['families'][0]['filename'] == 'actors.bin'
    assert result['families'][0]['operations'] == ['read', 'write']
    assert result['families'][0]['candidate_ids'] == [writer['id'], reader['id']]
    assert result['address_space'] == 'test preferred addresses'
    assert writer['callsite_offset'] == 16


def test_dynamic_stack_path_keeps_suffix_candidate_across_copy_loop():
    # Unknown directory already occupies a local buffer. Copy a literal suffix;
    # the analyzer must not claim to have executed or proved the string copy.
    code = b'\x83\xec\x18\xbe'+u32(0x3000) + b'\x89\xe7'
    code += b'\x8a\x06\x88\x07\x46\x47\x84\xc0\x75\xf6'
    code += b'\x89\xe0\xba'+u32(0x7000) + b'\xbb'+u32(123)
    code = call(code, WRITER['entry']) + b'\xc3'
    result, _ = analyze(code, {0x3000: b'\\invented.dat\0'})
    candidate, = result['candidates']
    assert candidate['filename']['text'] == '\\invented.dat'
    assert candidate['filename']['kind'] == 'literal_candidate'
    assert candidate['filename']['full_path_known'] is False
    assert candidate['filename']['value'] == {'kind': 'stack', 'value': -24}
    assert candidate['buffer'] == {'kind': 'direct', 'address': 0x7000}
    assert candidate['length'] == 123


def test_length_that_coincides_with_an_unrelated_string_is_not_a_filename():
    code = b'\x83\xec\x18\xbe'+u32(0x3000) + b'\x89\xe7\x8a\x06\x88\x07'
    code += b'\x89\xe0\xba'+u32(0x7000) + b'\xbb'+u32(123)
    code = call(code, WRITER['entry']) + b'\xc3'
    result, _ = analyze(code, {0x3000: b'/real.bin\0', 123: b'/unrelated.texture\0'})
    candidate, = result['candidates']
    assert candidate['filename']['text'] == '/real.bin'
    assert [item['text'] for item in candidate['filename']['literals']] == ['/real.bin']
    assert candidate['filename']['literals'][0]['byte_read_sites']
    assert candidate['length'] == 123


def test_join_conflicts_and_partial_register_write_do_not_invent_length():
    code = b'\xb8'+u32(0x3000) + b'\xba'+u32(0x7000) + b'\xbb'+u32(10)
    code += b'\x85\xc9\x74\x05\xbb'+u32(20)
    code = call(code, WRITER['entry'])
    code += b'\xb8'+u32(0x3000) + b'\xba'+u32(0x7000) + b'\xbb'+u32(30) + b'\xb3\x02'
    code = call(code, WRITER['entry']) + b'\xc3'
    result, _ = analyze(code, {0x3000: b'state.bin\0'})
    assert len(result['candidates']) == 2
    assert all(c['length'] is None for c in result['candidates'])
    assert all('length argument unresolved' in c['unresolved'] for c in result['candidates'])


@pytest.mark.parametrize('branch', [b'\xe2', b'\xe1', b'\xe0', b'\xe3'])
def test_counter_branch_taken_edge_participates_in_argument_join(branch):
    code = b'\xbb'+u32(10) + b'\xb9'+u32(2) + branch + b'\x05\xbb'+u32(20)
    code = call(code, WRITER['entry']) + b'\xc3'
    result, _ = analyze(code)
    assert result['candidates'][0]['length'] is None


def test_unknown_call_kills_arguments_and_unreachable_call_is_not_reported():
    code = b'\xb8'+u32(0x3000) + b'\xba'+u32(0x7000) + b'\xbb'+u32(10)
    code = call(code, 0x9000)
    code = call(code, WRITER['entry'])
    code += b'\xeb\x05'
    code = call(code, WRITER['entry']) + b'\xc3'
    result, _ = analyze(code, {0x3000: b'state.bin\0'})
    candidate, = result['candidates']
    assert candidate['filename']['kind'] == 'unresolved'
    assert candidate['buffer'] == {'kind': 'unresolved'}
    assert candidate['length'] is None


def test_stack_spills_restore_argument_and_unknown_store_invalidates_spill():
    code = b'\xb8'+u32(0x3000) + b'\x50\x31\xc0\x58'
    code += b'\xba'+u32(0x7000) + b'\xbb'+u32(10)
    code = call(code, WRITER['entry'])
    code += b'\xb8'+u32(0x3000) + b'\x50\x89\x01\x58'
    code = call(code, WRITER['entry']) + b'\xc3'
    result, _ = analyze(code, {0x3000: b'state.bin\0'})
    first, second = result['candidates']
    assert first['filename']['kind'] == 'direct'
    assert second['filename']['kind'] == 'unresolved'
    assert second['filename']['value'] == {'kind': 'unresolved'}


@pytest.mark.parametrize('write', [b'\xff\x04\x24', b'\x87\x04\x24'])
def test_unmodeled_memory_write_cannot_leave_stale_stack_spill(write):
    # inc [esp] / xchg [esp],eax must invalidate a saved value, even though the
    # analyzer does not model their result.
    code = b'\xb8'+u32(0x3000) + b'\x50' + write + b'\x58'
    code = call(code, WRITER['entry']) + b'\xc3'
    result, _ = analyze(code, {0x3000: b'state.bin\0'})
    assert result['candidates'][0]['filename']['kind'] == 'unresolved'


def test_pop_to_memory_does_not_preserve_pre_increment_stack_destination():
    code = b'\xb8'+u32(0x3000) + b'\x50\xb8'+u32(0x3100) + b'\x50\x8f\x04\x24\x58'
    code = call(code, WRITER['entry']) + b'\xc3'
    result, _ = analyze(code, {0x3000: b'a.dat\0', 0x3100: b'b.dat\0'})
    assert result['candidates'][0]['filename']['kind'] == 'unresolved'


def test_decoder_and_string_budgets_are_explicit_and_reads_bounded():
    code = b'\xb8'+u32(0x3000) + b'\xba'+u32(0x7000) + b'\xbb'+u32(10)
    code = call(code, WRITER['entry']) + b'\xc3'
    result, reads = analyze(code, {0x3000: b'not terminated'}, max_instructions=2,
                            max_string_bytes=8, max_string_reads=1)
    assert result['status'] == 'budget_stop'
    assert result['decoded_instructions'] == 2
    assert result['candidates'] == []
    assert all(size <= 8 for address, size in reads if address != BASE)
    result, _ = analyze(b'\x90\x0f')
    assert result['status'] == 'partial'
    assert result['issues'][0]['reason'] == 'undecodable or truncated instruction'


def test_instruction_budget_does_not_certify_arguments_before_unseen_backedge():
    code = b'\xb8'+u32(0x3000) + b'\xba'+u32(0x7000) + b'\xbb'+u32(10)
    code = call(code, WRITER['entry']) + b'\xbb'+u32(20) + b'\xeb\xf4'
    result, _ = analyze(code, {0x3000: b'state.bin\0'}, max_instructions=4)
    assert result['status'] == 'budget_stop'
    candidate, = result['candidates']
    assert candidate['length'] is None and candidate['buffer']['kind'] == 'unresolved'
    assert 'analysis budget stopped; argument facts withheld' in candidate['unresolved']


@pytest.mark.parametrize('options', [
    {'ranges': [(0, 65537)]}, {'ranges': [(10, 20), (19, 30)]},
    {'serializers': [{**WRITER, 'buffer': 'ax'}]},
    {'max_instructions': True}, {'max_string_reads': 0},
])
def test_invalid_contract_is_refused_before_reading(options):
    def forbidden(*args):
        pytest.fail('invalid input must not read native bytes')
    kwargs = {'ranges': [(BASE, BASE+1)], 'serializers': [WRITER], **options}
    with pytest.raises(ValueError):
        extract_serializer_candidates(forbidden, **kwargs)


def test_summary_pairs_calls_without_collapsing_writes_or_pointer_identity():
    code = b'\xb8'+u32(0x3000) + b'\x8b\x15'+u32(0x4000) + b'\xbb'+u32(37)
    code = call(code, WRITER['entry'])
    code += b'\xb8'+u32(0x3000) + b'\xba'+u32(0x7000) + b'\xbb'+u32(42)
    code = call(code, WRITER['entry'])
    code += b'\xba'+u32(0x3100) + b'\xa1'+u32(0x4100)
    code = call(code, READER['entry']) + b'\xc3'
    raw, _ = analyze(code, {0x3000: b'one/state.bin\0', 0x3100: b'two/state.bin\0'})
    unchanged = deepcopy(raw)
    summary = summarize_serializer_candidates(raw)
    assert raw == unchanged
    row, = summary['families']
    first, second, reader = raw['candidates']
    assert row['candidate_ids'] == [c['id'] for c in raw['candidates']]
    assert [w['callsite'] for w in row['writes']] == [hex(first['callsite']), hex(second['callsite'])]
    assert row['reads'][0]['callsite'] == hex(reader['callsite'])
    assert row['writes'][0]['buffer'] == {
        'kind': 'pointer_global', 'slot_address': '0x4000', 'pointer_width': 4, 'pointee_address': None}
    assert row['writes'][1]['buffer'] == {'kind': 'direct', 'address': '0x7000'}
    assert row['reads'][0]['buffer']['slot_address'] == '0x4100'
    assert row['observed_write_lengths'] == [37, 42]
    assert row['writes'][0]['filename']['text'] == 'one/state.bin'
    assert row['reads'][0]['filename']['text'] == 'two/state.bin'
    assert row['reads'][0]['length'] is None
    assert 'unproved' in row['basis']
    assert row['unresolved_candidate_count'] == 2
    assert row['unresolved_fact_count'] == 3
    assert sum(len(item['candidate_ids']) for item in row['unresolved']) == 3
    assert summary['code_base'] == '0x1000'
    assert summary['address_space'] == raw['address_space']


def test_summary_keeps_unnamed_candidates_unpaired_and_unknown_lengths_explicit():
    code = call(b'', WRITER['entry'])
    code = call(code, READER['entry']) + b'\xc3'
    raw, _ = analyze(code)
    summary = summarize_serializer_candidates(raw)
    assert summary['candidate_count'] == 2 and len(summary['families']) == 2
    writer, reader = summary['families']
    assert writer['filename'] is reader['filename'] is None
    assert writer['candidate_ids'] == [raw['candidates'][0]['id']]
    assert writer['writes'][0]['buffer'] == {'kind': 'unresolved'}
    assert writer['observed_write_lengths'] == []
    assert writer['unknown_write_length_count'] == 1
    assert reader['unknown_write_length_count'] == 0
    assert writer['unresolved_fact_count'] == reader['unresolved_fact_count'] == 3
    assert summary['unresolved_candidate_count'] == 2


def test_summary_preserves_budget_status_and_hex_issue_addresses():
    raw, _ = analyze(b'\x90\x90\xc3', max_instructions=1)
    summary = summarize_serializer_candidates(raw)
    assert summary['status'] == 'budget_stop'
    assert summary['families'] == []
    assert summary['issues'] == [{'address': '0x1001', 'reason': 'instruction budget stopped'}]
    assert summary['scope'] == raw['scope']
