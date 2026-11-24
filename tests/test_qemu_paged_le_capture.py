"""Source and relocation checks for capture-only paged LE interpretation."""
import pytest

from fdisbull.qemu_paged_le_capture import _interpret
from test_qemu_dos_le_match import fixture


def test_paged_interpretation_rechecks_complete_relocated_instruction():
    image, cpu, table, memory, _, read_source = fixture()
    cpu['ip'] = 0x50000
    context = dict(gdt=dict(base=0x30000, limit=len(table)-1))
    def read(address, length):
        if 0x30000 <= address and address + length <= 0x30000 + len(table):
            return table[address-0x30000:address-0x30000+length]
        return read_source(address, length)
    result = _interpret(image, cpu, context, read)
    assert result['descriptor']['table'] == 'gdt'
    assert result['source_location']['object_offset'] == 0
    assert result['instruction_size'] == 5
    assert result['placements'][1]['runtime_base'] == 0x70000
    changed = bytearray(memory[0][1]); changed[1] ^= 1
    memory.append((0x50000, bytes(changed)))
    with pytest.raises(ValueError):
        _interpret(image, cpu, context, read)


def test_paged_interpretation_rejects_changed_hidden_descriptor():
    image, cpu, table, _, _, read_source = fixture()
    context = dict(gdt=dict(base=0x30000, limit=len(table)-1))
    cpu['cs_base'] = 1
    def read(address, length):
        if 0x30000 <= address and address + length <= 0x30000 + len(table):
            return table[address-0x30000:address-0x30000+length]
        return read_source(address, length)
    with pytest.raises(ValueError):
        _interpret(image, cpu, context, read)


def test_stopped_capture_offline_replay_and_tamper_refusal(monkeypatch):
    from copy import deepcopy
    from types import SimpleNamespace
    from fdisbull import qemu_paged_le_capture as capture, le, qemu_dos_trace
    from iced_x86 import Decoder

    image, cpu, table, memory, _, _ = fixture()
    cpu['ip'] = 0x50000
    hmp = ('CR0=00000001 CR3=00000000 CR4=00000000 EFER=00000000\n'
           'GDT=00030000 00000017\nLDT=0000 00000000 00000000 00000000\n')
    mem = bytearray(0x100000)
    mem[0x30000:0x30000+len(table)] = table
    for address, value in memory: mem[address:address+len(value)] = value
    class Remote:
        def memory(self, address, length, **kwargs):
            return bytes(mem[address:address+length])
    class QMP:
        def call(self, *args, **kwargs): return hmp
    process = dict(state='active', capture_epoch='run:process:1')
    controls = dict(CR0=1, CR3=0, CR4=0, EFER=0)
    regs = dict(cpu_mode='protected', instruction_pointer=hex(cpu['ip']), linear_pc=hex(cpu['ip']),
        registers=dict(cs='0x8'), address_state=dict(code_bits=32, machine_vcpus=1,
            register_context_match=True, paging=False, a20=True, control=controls,
            segments=dict(cs=dict(selector='0x8', base=0, limit=cpu['cs_limit'], attributes=cpu['cs_attributes']))))
    inputs = dict(qemu_image=dict(sha256='b'*64))
    identity = dict(source_sha256='a'*64, version=1, version_sha256='c'*64)
    project = SimpleNamespace(meta=dict(source_sha256='a'*64), arch='x86', bits=32,
                              version=lambda version: dict(id=version, sha256='c'*64))
    metadata = dict(backend='qemu-dos', source_sha256='a'*64, version_sha256='c'*64, runtime_inputs=inputs, machine_configuration=dict(memory_mib=16))
    session = SimpleNamespace(_process=process, _runtime_epoch='run:process:1', project=project,
        version=dict(id=1, sha256='c'*64), metadata=metadata, run_id='run',
        vm=SimpleNamespace(qmp=QMP(), process=SimpleNamespace(poll=lambda:None), machine_configuration=dict(memory_mib=16)), closed=False,
        registers=lambda:deepcopy(regs), _stopped=lambda:Remote(), _remaining=lambda:10000)
    monkeypatch.setattr(capture, '_source', lambda *a, **k:(b'source', identity))
    monkeypatch.setattr(le, 'load_runtime_le_carrier', lambda raw:image)
    monkeypatch.setattr(qemu_dos_trace, '_ownership', lambda *a:None)
    raw = bytes(mem[0x50000:0x50010]); ins = Decoder(32, raw, ip=0x50000).decode()
    observed = dict(space='linear', view='ram', active_layers=[], runtime_address='0x50000',
        project_address=None, length=16, hex=raw.hex(), sha256=capture._sha(raw),
        backing=[dict(physical_address='0x50000', length=16)],
        instructions=[dict(runtime_address='0x50000', size=ins.len, bytes=raw[:ins.len].hex())])
    result = capture._qualify.__wrapped__(session, observed)
    proof = capture.validate(project, result, metadata, run='run', version=1)
    assert proof['source_location']['object_offset'] == 0
    assert proof['address_translation']['selector_table'] == 'gdt'
    assert proof['address_translation']['paging'] is False
    # The stopped PC remains at the first relocated instruction, while the
    # requested capture starts at a different source-backed instruction.
    other = deepcopy(observed)
    other_raw = bytes(mem[0x50040:0x50050])
    other_ins = Decoder(32, other_raw, ip=0x50040).decode()
    other.update(runtime_address='0x50040', hex=other_raw.hex(), sha256=capture._sha(other_raw),
        backing=[dict(physical_address='0x50040', length=16)],
        instructions=[dict(runtime_address='0x50040', size=other_ins.len, bytes=other_raw[:other_ins.len].hex())])
    other_capture = capture._qualify.__wrapped__(session, other)
    other_proof = capture.validate(project, other_capture, metadata, run='run', version=1)
    assert other_proof['source_location']['object_offset'] == 64
    assert other_proof['selector_offset'] == 0x50040 and other_proof['cpu']['ip'] == 0x50000
    assert other_proof['address_translation']['instruction_segments'][0]['physical'] == 0x50040
    # A truncated instruction remains a bounded byte capture, but cannot be
    # decoded as a complete instruction by the offline analysis consumer.
    partial = deepcopy(other)
    partial.update(length=1, hex=other_raw[:1].hex(), sha256=capture._sha(other_raw[:1]),
        backing=[dict(physical_address='0x50040', length=1)], instructions=[])
    partial_capture = capture._qualify.__wrapped__(session, partial)
    partial_proof = capture.validate(project, partial_capture, metadata, run='run', version=1)
    assert Decoder(32, partial_proof['raw'], ip=partial_proof['selector_offset']).decode().is_invalid
    bounded_cpu = dict(cpu, cs_limit=0x50040)
    with pytest.raises(ValueError, match='selector'):
        capture._capture_extent(image, bounded_cpu, result['paged_le_capture']['interpretation'], 0x50040, 2)
    with pytest.raises(ValueError, match='object'):
        capture._capture_extent(image, cpu, result['paged_le_capture']['interpretation'], 0x90000, 2)
    invalid_ram = deepcopy(result)
    invalid_ram['paged_le_capture']['memory_mib'] = 32
    with pytest.raises(ValueError, match='configuration'):
        capture.validate(project, invalid_ram, metadata, run='run', version=1)
    outside_ram = deepcopy(result)
    outside_ram['paged_le_capture']['physical_reads'][0]['address'] = 0x1000000
    with pytest.raises(ValueError, match='physical witness'):
        capture.validate(project, outside_ram, metadata, run='run', version=1)
    mmio = deepcopy(result)
    mmio['paged_le_capture']['physical_reads'][0]['address'] = 0xa0000
    with pytest.raises(ValueError, match='physical witness'):
        capture.validate(project, mmio, metadata, run='run', version=1)
    with monkeypatch.context() as limits:
        limits.setattr(capture, 'MAX_WITNESS_ROWS', 1)
        with pytest.raises(ValueError, match='row budget'):
            capture.validate(project, result, metadata, run='run', version=1)
        with pytest.raises(ValueError, match='budget'):
            capture._qualify.__wrapped__(session, observed)
    with monkeypatch.context() as limits:
        limits.setattr(capture, 'MAX_WITNESS_BYTES', 4)
        with pytest.raises(ValueError, match='physical witness'):
            capture._qualify.__wrapped__(session, observed)
        with pytest.raises(ValueError, match='physical witness'):
            capture.validate(project, result, metadata, run='run', version=1)
    corrupted = deepcopy(result)
    corrupted['paged_le_capture']['physical_reads'][0]['hex'] = '00' * corrupted['paged_le_capture']['physical_reads'][0]['length']
    with pytest.raises(ValueError):
        capture.validate(project, corrupted, metadata, run='run', version=1)


def test_match_accepts_adjacent_backing_but_refuses_a_gap(monkeypatch):
    from fdisbull import qemu_paged_le_match as paged
    from fdisbull.qemu_dos_le_match import _objects
    image, cpu, table, _, _, read = fixture()
    objects = _objects(image)
    def split(gap):
        def make(_):
            rows = _objects(image)
            rows[0]['backed'] = [(0, 80), (80 + gap, len(rows[0]['data']))]
            return rows
        return make
    from fdisbull.qemu_le_translation import observe_descriptor
    context = dict(gdt=dict(base=0x30000, limit=len(table)-1))
    descriptor = observe_descriptor(context, cpu['cs'], lambda a, n: table[a-0x30000:a-0x30000+n])
    monkeypatch.setattr(paged, '_objects', split(0))
    assert paged.match(image, cpu, descriptor, read) is not None
    monkeypatch.setattr(paged, '_objects', split(1))
    assert paged.match(image, cpu, descriptor, read) is None


def test_matching_needs_only_current_descriptor_not_unmapped_table_pages():
    image, cpu, table, _, _, read_source = fixture()
    context = dict(gdt=dict(base=0x30000, limit=65535))
    reads = []

    def read(address, length):
        reads.append((address, length))
        if 0x30000 <= address < 0x40000:
            if (address, length) != (0x30008, 8):
                raise ValueError('unmapped descriptor table page')
            return table[8:16]
        return read_source(address, length)

    result = _interpret(image, cpu, context, read)
    assert result['descriptor']['address'] == 0x30008
    assert result['match']['identity_evidence']['descriptor_identity'] == result['descriptor']
    assert (0x30000, 65536) not in reads
