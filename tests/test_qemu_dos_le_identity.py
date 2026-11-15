"""Source recipe and exact live-instruction checks using authored LE evidence."""
from copy import deepcopy
import hashlib
import struct

import pytest

from fdisbull.le import load_runtime_le_carrier
from fdisbull.qemu_dos_le_identity import make_recipe, validate_recipe, qualify_instruction, BINDING_FORMAT
from fdisbull.qemu_dos_le_match import match
from test_le_loader import le_file
from test_le_runtime_carrier import bound_le
from test_qemu_dos_le_match import descriptor, fixture


def sha(data):return hashlib.sha256(data).hexdigest()


def admitted(image, cpu, table, read):
    observation = match(image, cpu, table, read)
    assert observation is not None
    return dict(format='fdisbull-qemu-dos-le-admission-1', backend='qemu-dos', status='admitted',
                run='authored-run', capture_epoch='authored-run:process:1', version=1, version_sha256='a'*64,
                source_sha256=image.metadata['source_sha256'], source_view='embedded-le',
                lifetime_qualified=False, live_mapping_installed=False,
                observed_cpu=deepcopy(cpu), gdt=dict(base=0x800, limit=len(table)-1, sha256=sha(table)),
                observation=observation)


def setup():
    image, cpu, table, memory, reads, read = fixture()
    document = admitted(image, cpu, table, read)
    recipe = make_recipe(image, document, binding_id='le-binding:authored')
    return image, cpu, table, memory, reads, read, recipe


def extended(*, kind='offset32', unknown_target=False, entry_offset=0):
    pointers = b''.join(b'\xb8' + bytes(4) + b'\x90'*3 for _ in range(8))
    prefix = pointers + b''.join(bytes([0x6a, i]) for i in range(32))
    current = b'\x66\xb8\0\0' if kind == 'offset16' else b'\xb8' + bytes(4)
    code = prefix + current + b''.join(bytes([0x6a, i]) for i in range(80))
    target = 1 if unknown_target else 2
    records = b''.join(struct.pack('<BBhBH', 7, 0, i*8+1, target, i) for i in range(8))
    records += struct.pack('<BBhBH', 5 if kind == 'offset16' else 7, 0,
                           130 if kind in ('offset16', 'straddling') else 129, 2, 3)
    data = b'abcdefghijklmnopqrstuvwxyz0123456789'*3
    image = load_runtime_le_carrier(bound_le(le_file(code=code, data=data, fixups=[records, b''],
                                                   object_sizes=(len(code), len(data)), entry_offset=entry_offset)))
    table = bytes(8) + descriptor(0, 0xffffffff, 32)
    cpu = dict(mode='protected', bits=32, cs=8, ip=0x50040, cs_base=0,
               cs_limit=0xffffffff, cs_attributes=0xc09a00)
    runtime = bytearray(image.regions[0].data)
    for fixup in image.metadata['le']['fixups']:
        if fixup['source_type'] == 'offset32':
            base = 0x50000 if fixup['target_object'] == 1 else 0x70000
            struct.pack_into('<I', runtime, fixup['source_offset'], base + fixup['target_offset'])
        else:struct.pack_into('<H', runtime, fixup['source_offset'], 0xf002)
    memory = [(0x50000, bytes(runtime)), (0x70000, image.regions[1].data)]
    reads = []
    def read(address, length):
        reads.append((address, length))
        for start, content in reversed(memory):
            if start <= address and address + length <= start + len(content):
                return content[address-start:address-start+length]
        return bytes(length)
    recipe = make_recipe(image, admitted(image, cpu, table, read), binding_id='le-binding:extended')
    cpu['ip'] = 0x50080
    return image, cpu, table, memory, reads, read, recipe


def test_recipe_is_canonical_proof_derived_and_detached_from_the_admission():
    image, cpu, table, memory, reads, read = fixture()
    document = admitted(image, cpu, table, read)
    recipe = make_recipe(image, document, binding_id='le-binding:authored')
    assert recipe['format'] == BINDING_FORMAT
    assert recipe['placements'] == [dict(object_index=1, runtime_base=0x50000, bits=32),
                                    dict(object_index=2, runtime_base=0x70000, bits=32)]
    assert validate_recipe(image, recipe) == recipe
    document['run'] = 'changed-input'
    assert recipe['run'] == 'authored-run'
    tampered = deepcopy(recipe);tampered['placements'][1]['runtime_base'] += 16
    with pytest.raises(ValueError, match='recipe differs'):validate_recipe(image, tampered)


def test_exact_relocated_operand_qualifies_with_preferred_image_hash():
    image, cpu, table, memory, reads, read, recipe = setup()
    cpu['ip'] = 0x50000
    result = qualify_instruction(image, recipe, cpu, table, read)
    assert result['qualified'] and result['instruction_size'] == 5
    assert result['execution_bytes'] == 'b800000700'
    assert result['source_instruction_sha256'] == sha(image.regions[0].data[:5])
    assert result['source_location'] == dict(source_view='embedded-le', application_source_sha256=recipe['application_source_sha256'],
        object_id='le:1', object_index=1, object_offset=0, preferred_address=0x10000)
    assert result['context'] == 'embedded-le:' + recipe['application_source_sha256'] + ':le:1:32'


def test_initialized_data_mutation_is_allowed_and_not_reread_per_instruction():
    image, cpu, table, memory, reads, read, recipe = setup()
    memory.append((0x70000, b'Z'*len(image.regions[1].data)))
    cpu['ip'] = 0x50080;reads.clear()
    result = qualify_instruction(image, recipe, cpu, table, read)
    assert result['qualified'] and result['execution_bytes'] == '6a20'
    assert reads and all(address < 0x70000 for address, _ in reads)


def test_complete_instruction_at_last_backed_bytes_qualifies_without_bss_prefetch():
    image, cpu, table, memory, reads, read, recipe = setup()
    cpu['ip'] = 0x50000 + len(image.regions[0].data) - 2
    result = qualify_instruction(image, recipe, cpu, table, read)
    assert result['qualified'] and result['instruction_size'] == 2


def test_wrong_unanchored_runtime_operand_does_not_gain_source_authority():
    image, cpu, table, memory, reads, read, recipe = extended()
    changed = bytearray(memory[0][1]);struct.pack_into('<I', changed, 129, 0x71003)
    memory.append((0x50000, bytes(changed)))
    result = qualify_instruction(image, recipe, cpu, table, read)
    assert not result['qualified'] and result['reason'] == 'changed-source-instruction'
    assert result['instruction_size'] == 5 and result['context'] is None
    assert result['source_instruction_sha256'] is None and result['source_location'] is None
    assert result['candidate_location']['object_offset'] == 128


@pytest.mark.parametrize('kind,reason', [('offset16', 'symbolic-or-unsupported-relocation'),
                                       ('straddling', 'straddling-relocation'),
                                       ('unknown', 'unproved-relocation-target')])
def test_unresolved_operands_stop_as_unqualified_boundaries(kind, reason):
    image, cpu, table, memory, reads, read, recipe = extended(kind=kind, unknown_target=kind == 'unknown')
    result = qualify_instruction(image, recipe, cpu, table, read)
    assert not result['qualified'] and result['reason'] == reason
    assert result['context'] is result['source_instruction_sha256'] is result['source_location'] is None


@pytest.mark.parametrize('kind,reason', [('anchor','code-anchor-changed'), ('pointer','runtime-placement-witness-changed')])
def test_code_anchor_and_original_pointer_witnesses_are_rechecked(kind, reason):
    image, cpu, table, memory, reads, read, recipe = extended(entry_offset=96) if kind == 'pointer' else setup()
    cpu['ip'] = 0x500e0 if kind == 'pointer' else 0x50080
    changed = bytearray(memory[0][1])
    if kind == 'anchor':changed[0] ^= 1
    else:
        struct.pack_into('<I', changed, 1, 0x71000)
    memory.append((0x50000, bytes(changed)))
    result = qualify_instruction(image, recipe, cpu, table, read)
    assert not result['qualified'] and result['reason'] == reason


def test_unrelated_and_undecodable_boundaries_never_receive_source_identity():
    image, cpu, table, memory, reads, read, recipe = setup()
    cpu['ip'] = 0x60000
    unrelated = qualify_instruction(image, recipe, cpu, table, read)
    assert unrelated['reason'] == 'unrelated-source' and unrelated['source_location'] is None
    changed = bytearray(memory[0][1]);changed[128:143] = b'\x66'*15
    memory.append((0x50000, bytes(changed)));cpu['ip'] = 0x50080
    undecodable = qualify_instruction(image, recipe, cpu, table, read)
    assert undecodable['reason'] == 'undecodable-source' and undecodable['instruction_size'] == 0
    assert undecodable['context'] is None


@pytest.mark.parametrize('damage',['gdt','base','limit','flags','gdtr-base'])
def test_live_descriptor_or_gdt_identity_drift_raises_before_memory_reads(damage):
    image, cpu, table, memory, reads, read, recipe = setup();reads.clear()
    if damage == 'gdt':table = b'\x01' + table[1:]
    elif damage == 'base':cpu['cs_base'] = 16
    elif damage == 'limit':cpu['cs_limit'] -= 1
    elif damage == 'flags':cpu['cs_attributes'] ^= 0x400000
    else:cpu['gdtr_base'] = 0x900
    with pytest.raises(ValueError):qualify_instruction(image, recipe, cpu, table, read)
    assert not reads


def test_malformed_proof_or_source_identity_is_not_a_recipe():
    image, cpu, table, memory, reads, read, recipe = setup()
    bad = deepcopy(recipe['initial_admission']);bad['observation']['identity_evidence']['object_proofs'][0]['offset32_sites'].pop()
    with pytest.raises(ValueError, match='eight'):make_recipe(image, bad, binding_id='le-binding:bad')
    bad = deepcopy(recipe);bad['source_sha256'] = '0'*64
    with pytest.raises(ValueError):validate_recipe(image, bad)
    image.metadata['source_sha256'] = '0'*64
    with pytest.raises(ValueError, match='source/profile'):qualify_instruction(image, recipe, cpu, table, read)


def test_canonical_site_identity_is_stable_across_runtime_placements():
    image, cpu, table, memory, reads, read, recipe = setup()
    shifted = [(address + 0x10000, data) for address, data in memory]
    relocated = bytearray(shifted[0][1])
    for fixup in image.metadata['le']['fixups']:
        struct.pack_into('<I', relocated, fixup['source_offset'], 0x80000 + fixup['target_offset'])
    shifted[0] = (0x60000, bytes(relocated))
    def shifted_read(address, length):
        for start, data in shifted:
            if start <= address and address + length <= start + len(data):
                return data[address-start:address-start+length]
        return bytes(length)
    other_cpu = dict(cpu, ip=cpu['ip'] + 0x10000)
    document = admitted(image, other_cpu, table, shifted_read)
    document.update(run='second-owned-run', capture_epoch='second-owned-run:process:1')
    other = make_recipe(image, document, binding_id='le-binding:other')
    first = qualify_instruction(image, recipe, dict(cpu, ip=0x50000), table, read)
    second = qualify_instruction(image, other, dict(other_cpu, ip=0x60000), table, shifted_read)
    assert first['qualified'] and second['qualified']
    assert first['execution_bytes'] != second['execution_bytes']
    assert first['context'] == second['context'] and first['source_location'] == second['source_location']
    assert first['source_instruction_sha256'] == second['source_instruction_sha256']
    assert first['binding_context']['run'] != second['binding_context']['run']


def test_changed_opcode_length_is_an_unqualified_source_shape():
    image, cpu, table, memory, reads, read, recipe = setup()
    changed = bytearray(memory[0][1]);changed[128] = 0xb8
    memory.append((0x50000, bytes(changed)));cpu['ip'] = 0x50080
    result = qualify_instruction(image, recipe, cpu, table, read)
    assert not result['qualified'] and result['reason'] == 'source-instruction-shape-changed'
    assert result['instruction_size'] == 5 and result['source_location'] is result['context'] is None


def test_admission_context_cannot_be_detached_from_its_current_code_span():
    image, cpu, table, memory, reads, read, recipe = setup()
    document = deepcopy(recipe['initial_admission'])
    document['observed_cpu']['ip'] += 2
    document['observation']['identity_evidence']['cpu']['ip'] += 2
    with pytest.raises(ValueError, match='current-code placement'):
        make_recipe(image, document, binding_id='le-binding:detached')
