"""Authored flat32 byte fixtures exercise discovery without target bindings."""
import struct

import pytest

from fdisbull.serializer_candidates import extract_serializer_candidates
from fdisbull.serializer_discovery import discover_serializer_calls, map_le_module
from test_le_loader import le_file


BASE = 0x180000


def p32(value):
    return struct.pack('<I', value)


def reader_for(raw, base=BASE):
    reads = []
    def read(address, length):
        reads.append((address, length))
        if base <= address and address+length <= base+len(raw):
            return raw[address-base:address-base+length]
        raise ValueError('unmapped')
    return read, reads


def add_call(code, entry):
    return code+b'\xe8'+struct.pack('<i', entry-(BASE+len(code)+5))


def fixture(dynamic=False):
    raw = bytearray(0x8000)
    code = b'\x53\x51\x52\x56\x57\x55\x83\xec\x18'
    for index, size in enumerate((68, 148)):
        name = BASE+0x4000+index*0x40
        if dynamic:
            code += b'\xbe'+p32(name)+b'\x89\xe7\x8a\x06\x88\x07\x46\x47\x84\xc0\x75\xf6\x89\xe0'
        else:
            code += b'\xb8'+p32(name)
        code += b'\x8b\x15'+p32(BASE+0x6000+index*4)+b'\xbb'+p32(size)
        code = add_call(code, BASE+0x2000)
    code += b'\x83\xc4\x18\x5d\x5f\x5e\x5a\x59\x5b\xc3'
    raw[:len(code)] = code
    raw[0x4000:0x4000+11] = b'actors.dat\0'
    raw[0x4040:0x4040+11] = b'worlds.dat\0'
    return bytes(raw), code


@pytest.mark.parametrize('dynamic', [False, True])
def test_file_anchors_find_repeated_target_and_recover_abi_candidate(dynamic):
    raw, code = fixture(dynamic)
    read, reads = reader_for(raw)
    result = discover_serializer_calls(read, ranges=[[BASE, BASE+len(raw)]],
                                       code_ranges=[[BASE, BASE+len(code)]],
                                       filenames=['ACTORS.DAT', 'worlds.dat'],
                                       file_sizes={'actors.dat': 68, 'worlds.dat': 148})
    assert result['status'] == 'candidates_ready'
    assert {a['basename'] for a in result['anchors']} == {'actors.dat', 'worlds.dat'}
    target = result['serializer_targets'][0]
    assert target['entry'] == BASE+0x2000 and target['filename_count'] == 2
    candidate = target['abi_hypotheses'][0]
    assert candidate['registers'] == {'entry': BASE+0x2000, 'filename': 'eax', 'buffer': 'edx', 'length': 'ebx'}
    assert candidate['operation_candidate'] == 'write' and candidate['qualified'] is False
    assert result['callers'][0]['entry'] == BASE
    assert result['callers'][0]['end'] == BASE+len(code)
    assert all(length <= 65536 for _, length in reads)
    # The cold discovery result is consumable by the existing flow-aware stage.
    selected = {**candidate['registers'], 'operation': 'write'}
    extracted = extract_serializer_candidates(read, ranges=[[BASE, BASE+len(code)]], serializers=[selected])
    assert {c['length'] for c in extracted['candidates']} == {68, 148}
    assert all(c['buffer']['kind'] == 'pointer_global' for c in extracted['candidates'])


def test_filename_and_xref_across_snapshot_chunk_boundary():
    raw = bytearray(0x11000)
    name = BASE+65532
    code = b'\xb8'+p32(name)+b'\xba'+p32(BASE+0x8000)+b'\xbb'+p32(17)
    code = add_call(code, BASE+0x4000)+b'\xc3'
    raw[:len(code)] = code
    raw[65532:65532+10] = b'cross.dat\0'
    read, reads = reader_for(bytes(raw))
    result = discover_serializer_calls(read, ranges=[[BASE, BASE+len(raw)]], filenames=['cross.dat'])
    assert result['anchors'][0]['address'] == name
    assert result['serializer_targets'][0]['entry'] == BASE+0x4000
    assert len(reads) == 2


def test_unmapped_chunks_are_explicit_and_budgets_do_not_claim_completeness():
    raw, _ = fixture()
    read, _ = reader_for(raw)
    result = discover_serializer_calls(read, ranges=[[BASE, BASE+0x10000]])
    assert result['status'] == 'partial' and result['issues']
    read, _ = reader_for(raw)
    result = discover_serializer_calls(read, ranges=[[BASE, BASE+len(raw)]], max_anchors=1)
    assert result['status'] == 'budget_stop' and len(result['anchors']) == 1


def test_false_pointer_without_address_instruction_does_not_create_xref():
    raw = bytearray(0x200)
    raw[0x100:0x109] = b'fake.dat\0'
    raw[20:24] = p32(BASE+0x100)  # Data only; no MOV/LEA/PUSH to load it.
    read, _ = reader_for(bytes(raw))
    result = discover_serializer_calls(read, ranges=[[BASE, BASE+len(raw)]], code_ranges=[[BASE, BASE+32]])
    assert result['anchors'] and not result['references'] and not result['serializer_targets']


def _mapping_fixture():
    # Two functions with different opcode/register sequences and relocatable
    # 32-bit immediates. Their source windows are spread apart in one LE object.
    first = b'\x53\x51\x52\x56\x57\x55\x83\xec\x18'+b'\xb8'+p32(0x1000)
    first += b'\x89\xc5\x89\xe7\x89\xc6\x57\x8a\x06\x88\x07\x46\x47\x84\xc0\x75\xf6'+b'\x90'*30+b'\xc3'
    second = b'\x53\x51\x52\x56\x57\x55\x83\xec\x20'+b'\xba'+p32(0x2000)
    second += b'\x89\xd3\x89\xe6\x89\xd7\x56\x8a\x07\x88\x06\x47\x46\x84\xc0\x75\xf6'+b'\x40'*30+b'\xc3'
    code = first.ljust(256, b'\xcc')+second
    source = le_file(code=code, data=b'data', fixups=[b'', b''])
    live = bytearray(code+b'\0'*16)
    live[10:14] = p32(0x217000)
    live[266:270] = p32(0x218000)
    return source, bytes(live)


def test_le_mapping_does_not_need_supported_fixups_or_launcher_mapping():
    source, live = _mapping_fixture()
    # A selector fixup profile is intentionally unsupported by load_le, but
    # enumerated source pages remain useful for matching instruction structure.
    read, reads = reader_for(live)
    result = map_le_module(read, source_bytes=source, ranges=[[BASE, BASE+len(live)]])
    binding = result['objects'][0]['candidates'][0]
    assert binding['live_base'] == BASE and binding['matching_windows'] == 2
    assert binding['status'] == 'supported_candidate'
    assert all(length <= 65536 for _, length in reads)


def test_mapping_keeps_duplicate_loaded_modules_ambiguous():
    source, live = _mapping_fixture()
    ram = live.ljust(4096, b'\0')+live
    read, _ = reader_for(ram)
    result = map_le_module(read, source_bytes=source, ranges=[[BASE, BASE+len(ram)]])
    supported = [c for c in result['objects'][0]['candidates'] if c['status'] == 'supported_candidate']
    assert [c['live_base'] for c in supported] == [BASE, BASE+4096]


@pytest.mark.parametrize('options', [
    {'ranges': [[20, 10]]}, {'ranges': [[0, 20], [10, 30]]},
    {'ranges': [[0, 65536]], 'max_bytes': 32},
    {'ranges': [[0, 100]], 'code_ranges': [[100, 200]]},
    {'ranges': [[0, 100]], 'file_sizes': {'test.dat': -1}},
])
def test_invalid_discovery_input_does_not_read(options):
    def read(*args):
        raise AssertionError('invalid request must not touch target')
    with pytest.raises(ValueError):
        discover_serializer_calls(read, **options)


def test_enclosing_wrapper_users_expose_directory_argument_and_return_continuation():
    raw, wrapper = fixture()
    raw = bytearray(raw)
    # A parent menu routine calls the recovered wrapper, passing a directory.
    parent_offset = 0x1000
    parent = b'\x55\x89\xe5\xb8'+p32(BASE+0x7000)
    callsite = BASE+parent_offset+len(parent)
    parent += b'\xe8'+struct.pack('<i', BASE-(callsite+5))+b'\x85\xc0\x75\xf7\x5d\xc3'
    raw[parent_offset:parent_offset+len(parent)] = parent
    raw[0x7000:0x7007] = b'SLOT_4\0'
    read, _ = reader_for(bytes(raw))
    result = discover_serializer_calls(read, ranges=[[BASE, BASE+len(raw)]],
                                       filenames=['actors.dat'], file_sizes={'actors.dat': 68})
    caller = next(c for c in result['callers'] if c['entry'] == BASE)
    user = caller['caller_users'][0]
    assert user['callsite'] == callsite and user['return_address'] == callsite+5
    assert user['parent_entry_candidate'] == BASE+parent_offset
    assert user['register_hypotheses']['eax'] == {'kind': 'constant', 'value': BASE+0x7000}
    assert user['nearby_backward_edges']
    assert user['before'] and user['after']


def test_later_filename_branch_extends_caller_span_past_an_early_return():
    raw = bytearray(0x6000)

    def file_block(name, buffer, length, target, address):
        code = b'\xb8'+p32(name)+b'\xba'+p32(buffer)+b'\xbb'+p32(length)
        return code+b'\xe8'+struct.pack('<i', target-(address+len(code)+5))+b'\xc3'

    first = file_block(BASE+0x4000, BASE+0x5000, 11, BASE+0x2000, BASE+7)
    # The conditional edge reaches the second file block without going through
    # the first block's RET. Both belong to the same recognized prologue.
    code = b'\x55\x89\xe5\x85\xc9\x74'+bytes([len(first)])+first
    second_start = BASE+len(code)
    code += file_block(BASE+0x4040, BASE+0x5040, 22, BASE+0x2100, second_start)
    raw[:len(code)] = code
    raw[0x4000:0x400a] = b'alpha.dat\0'
    raw[0x4040:0x404a] = b'bravo.dat\0'
    read, _ = reader_for(bytes(raw))
    result = discover_serializer_calls(
        read, ranges=[[BASE, BASE+len(raw)]], code_ranges=[[BASE, BASE+len(code)]],
        filenames=['alpha.dat', 'bravo.dat'], file_sizes={'alpha.dat': 11, 'bravo.dat': 22})

    caller, = result['callers']
    assert caller['entry'] == BASE and caller['end'] == BASE+len(code)
    assert caller['filenames'] == ['alpha.dat', 'bravo.dat']
    assert all(c['caller_range'] == [BASE, BASE+len(code)] for c in result['calls'])
    assert {target['entry'] for target in result['serializer_targets']} == {BASE+0x2000, BASE+0x2100}
    # The corrected span must actually unlock both branches for the downstream
    # analyzer, rather than merely naming the second filename in a summary.
    serializers = [dict(target['abi_hypotheses'][0]['registers'], operation='write')
                   for target in result['serializer_targets']]
    extracted = extract_serializer_candidates(
        read, ranges=[[caller['entry'], caller['end']]], serializers=serializers)
    assert {(c['filename']['text'], c['length']) for c in extracted['candidates']} == {
        ('alpha.dat', 11), ('bravo.dat', 22)}


@pytest.mark.parametrize('literal, suffix', [
    (b'noise/actors.dat\0', b'/actors.dat'),
    (b'noise\\actors.dat\0', b'\\actors.dat'),
    (b'pmissdat/actors.dat\0', b'missdat/actors.dat'),
    (b'prefixactors.dat\0', b'actors.dat'),
])
def test_filename_search_finds_actual_suffix_pointer_after_printable_prefix(literal, suffix):
    raw = bytearray(0x6000)
    pointer = BASE+0x4000+literal.index(suffix)
    code = b'\x55\x89\xe5\xb8'+p32(pointer)
    code += b'\xba'+p32(BASE+0x5000)+b'\xbb'+p32(68)
    code = add_call(code, BASE+0x2000)+b'\xc3'
    raw[:len(code)] = code
    raw[0x4000:0x4000+len(literal)] = literal
    read, _ = reader_for(bytes(raw))
    result = discover_serializer_calls(
        read, ranges=[[BASE, BASE+len(raw)]], code_ranges=[[BASE, BASE+len(code)]],
        filenames=['ACTORS.DAT'], file_sizes={'actors.dat': 68})

    anchor = next(a for a in result['anchors'] if a['address'] == pointer)
    assert anchor['text'] == suffix.decode()
    assert anchor['source_match'] == {'address': BASE+0x4000, 'text': literal[:-1].decode()}
    target, = result['serializer_targets']
    assert target['entry'] == BASE+0x2000 and target['filenames'] == ['actors.dat']
    assert target['abi_hypotheses'][0]['registers'] == {
        'entry': BASE+0x2000, 'filename': 'eax', 'buffer': 'edx', 'length': 'ebx'}
    assert len({a['address'] for a in result['anchors']}) == len(result['anchors'])


def test_filename_suffixes_preserve_full_match_and_respect_anchor_budget():
    raw = bytearray(0x100)
    raw[16:16+len(b'noise/actors.dat\0')] = b'noise/actors.dat\0'
    read, _ = reader_for(bytes(raw))
    result = discover_serializer_calls(read, ranges=[[BASE, BASE+len(raw)]],
                                       filenames=['actors.dat'], max_anchors=2)
    assert result['status'] == 'budget_stop'
    assert len(result['anchors']) == 2
    assert result['anchors'][0]['text'] == 'noise/actors.dat'
    assert result['anchors'][1]['text'] == '/actors.dat'


@pytest.mark.parametrize('dynamic', [False, True])
def test_selected_filename_is_not_attributed_to_later_unselected_file_call(dynamic):
    raw, code = fixture(dynamic)
    read, _ = reader_for(raw)
    result = discover_serializer_calls(
        read, ranges=[[BASE, BASE+len(raw)]], code_ranges=[[BASE, BASE+len(code)]],
        filenames=['actors.dat'], file_sizes={'actors.dat': 68})
    # Both original calls fit the same proximity window, but the second copies
    # worlds.dat into its filename argument. The filter must not hide that
    # redefinition and mislabel the second file's pointer global as actors.dat.
    selected_calls = [c for c in result['calls'] if c['target'] == BASE+0x2000]
    assert len(selected_calls) == 1
    assert selected_calls[0]['registers']['edx'] == {'kind': 'pointer_global', 'address': BASE+0x6000}
    assert selected_calls[0]['filename'] == 'actors.dat'
    assert 'candidate' in selected_calls[0]['filename_relation']
    assert result['serializer_targets'][0]['callsite_count'] == 1


def test_later_unrelated_filename_does_not_hide_an_exact_argument_pointer():
    raw = bytearray(0x6000)
    code = b'\x55\x89\xe5\xb8'+p32(BASE+0x4000)
    code += b'\xbe'+p32(BASE+0x4040)  # An unrelated string in ESI, not the filename ABI.
    code += b'\xba'+p32(BASE+0x5000)+b'\xbb'+p32(68)
    code = add_call(code, BASE+0x2000)+b'\xc3'
    raw[:len(code)] = code
    raw[0x4000:0x400b] = b'actors.dat\0'
    raw[0x4040:0x404b] = b'worlds.dat\0'
    read, _ = reader_for(bytes(raw))
    result = discover_serializer_calls(
        read, ranges=[[BASE, BASE+len(raw)]], code_ranges=[[BASE, BASE+len(code)]],
        filenames=['actors.dat'], file_sizes={'actors.dat': 68})
    selected, = result['calls']
    assert selected['filename'] == 'actors.dat'
    assert selected['filename_relation'] == 'argument-pointer candidate'
    assert selected['abi_hypotheses'][0]['registers']['filename'] == 'eax'
