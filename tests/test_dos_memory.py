"""Observed-context and page-walk contracts with authored machine snapshots."""
import json
import struct
import threading
from types import SimpleNamespace

import pytest

from fdisbull.dos_memory import machine_address_state, translate_386_page
from fdisbull.qemu_machine import MachineContext


def snapshot(*, flags=0x20202, cr0=0x80010001, cr3=0x3000, cr4=0,
             cs=0x1234, base=0x12340, attributes=0x9b00, ip=0x100, a20=1, efer=0):
    values = dict(eip=hex(ip), eflags=hex(flags), cs=hex(cs))
    text = (f'EIP={ip:08x} EFL={flags:08x} A20={a20}\n'
            f'CS ={cs:04x} {base:08x} ffffffff {attributes:08x}\n'
            'SS =2000 00020000 0000ffff 00009300\n'
            f'CR0={cr0:08x} CR2=00000000 CR3={cr3:08x} CR4={cr4:08x}\n'
            f'EFER={efer:016x}\n')
    return values, text


def test_v86_is_distinct_from_protected_and_uses_observed_segment_base():
    values, text = snapshot(base=0x70000)
    observed = machine_address_state(values, text)
    assert observed['cpu_mode'] == 'v86'
    assert observed['linear_pc'] == '0x70100'
    assert observed['address_state']['code_bits'] == 16
    assert observed['address_state']['paging_mode'] == 'legacy-32'
    assert observed['address_state']['register_context_match'] is True
    assert observed['address_state']['control']['CR3'] == '0x3000'


@pytest.mark.parametrize('attributes,expected', [(0x00cf9b00, 32), (0x00009b00, 16)])
def test_protected_selector_never_becomes_a_dos_paragraph(attributes, expected):
    values, text = snapshot(flags=0x202, cs=0x18, base=0x240000, attributes=attributes, ip=0x4567)
    observed = machine_address_state(values, text)
    assert observed['cpu_mode'] == 'protected'
    assert observed['linear_pc'] == '0x244567'
    assert observed['address_state']['code_bits'] == expected
    assert observed['address_state']['segment_semantics'] == 'selector'


def test_16bit_protected_segment_preserves_observed_32bit_eip():
    # A 32-bit transfer can establish EIP > FFFF in a D=0 segment with a
    # sufficient limit. CS.D determines default decode size, not EIP width.
    # Intel 80386 JMP: https://pdos.csail.mit.edu/6.828/2018/readings/i386/JMP.htm
    values, text = snapshot(flags=2, cr0=1, cr3=0, cs=0x10, base=0x10000,
                            attributes=0x00809b00, ip=0x12345)
    observed = machine_address_state(values, text)
    assert observed['cpu_mode'] == 'protected'
    assert observed['address_state']['code_bits'] == 16
    assert observed['instruction_pointer'] == '0x12345'
    assert observed['linear_pc'] == '0x22345'


def test_long_and_compatibility_widths_use_observed_cs_attributes():
    values, text = snapshot(flags=0x202, cr4=0x20, efer=0x500, attributes=0x00af9b00)
    assert machine_address_state(values, text)['address_state']['code_bits'] == 64
    values, text = snapshot(flags=0x202, cr4=0x20, efer=0x500, attributes=0x00cf9b00)
    assert machine_address_state(values, text)['address_state']['code_bits'] == 32


def test_missing_flags_or_different_gdb_context_remain_unknown():
    values, text = snapshot()
    values.pop('eflags')
    text = text.replace('EFL=00020202 ', '')
    observed = machine_address_state(values, text)
    assert observed['cpu_mode'] == 'unknown' and observed['address_state']['code_bits'] is None
    values, text = snapshot()
    values['eip'] = '0x1234'
    observed = machine_address_state(values, text)
    assert observed['linear_pc'] is None
    assert observed['address_state']['register_context_match'] is False


def state(**kwargs):
    return machine_address_state(*snapshot(**kwargs))['address_state']


def test_386_walk_uses_physical_paging_structures_and_combined_attributes():
    # Linear 0x405234: PDE[1] points at 0x9000; PTE[5] points at physical 0x12000.
    entries = {0x3004: 0x9005, 0x9014: 0x12067}
    reads = []

    def physical(address, length):
        reads.append((address, length))
        return struct.pack('<I', entries[address])

    result = translate_386_page('0x405234', state(), physical)
    assert result['status'] == 'mapped' and result['physical_address'] == '0x12234'
    assert result['page_size'] == 4096
    assert reads == [(0x3004, 4), (0x9014, 4)]
    assert result['page_attributes'] == dict(writable=False, user=True, supervisor_write_protect=True)
    assert 'not allocation identity' in result['scope']


@pytest.mark.parametrize('pde,pte,expected_reads', [(0x9004, 0, 1), (0x9007, 0x12006, 2)])
def test_not_present_pages_do_not_claim_physical_mapping(pde, pte, expected_reads):
    reads = []

    def physical(address, length):
        reads.append(address)
        return struct.pack('<I', pde if len(reads) == 1 else pte)

    result = translate_386_page(0x405234, state(), physical)
    assert result['status'] == 'not-present' and result['physical_address'] is None
    assert len(reads) == expected_reads


@pytest.mark.parametrize('changes,reason', [
    ({'cr4': 0x20}, 'PAE'),
    ({'cr4': 0x20, 'efer': 0x500}, 'IA-32e'),
    ({'a20': 0}, 'A20 disabled'),
    ({'cr0': 0x80000000}, 'protected-mode enable'),
    ({'cr3': 0x100000000}, '32-bit'),
])
def test_unsupported_paging_never_reads_a_guessed_table(changes, reason):
    result = translate_386_page(0, state(**changes), lambda *args: pytest.fail('guessed physical read'))
    assert result['status'] == 'unsupported' and reason in result['reason']
    assert result['physical_address'] is None


def test_unknown_a20_and_control_state_do_not_invent_mappings():
    observed = state()
    observed['a20'] = None
    result = translate_386_page(0, observed, lambda *args: pytest.fail('read without A20'))
    assert result['status'] == 'unknown' and 'A20' in result['reason']
    observed = state()
    observed['control'].pop('CR4')
    assert translate_386_page(0, observed, lambda *args: pytest.fail('read without CR4'))['status'] == 'unknown'
    observed = state()
    observed['machine_vcpus'] = 2
    assert translate_386_page(0, observed, lambda *args: pytest.fail('unqualified vCPU read'))['status'] == 'unsupported'


def test_unpaged_a20_gate_and_large_page_refusal():
    result = translate_386_page(0x112345, state(cr0=0x10, a20=0), lambda *args: pytest.fail('unpaged table read'))
    assert result['status'] == 'mapped' and result['physical_address'] == '0x12345'
    result = translate_386_page(0, state(cr4=0x10), lambda *args: struct.pack('<I', 0x400087))
    assert result['status'] == 'unsupported' and 'Large-page' in result['reason']
    assert len(result['entries']) == 1


@pytest.mark.parametrize('address', [-1, 0x100000000, True, None])
def test_invalid_linear_addresses_refuse(address):
    with pytest.raises(ValueError, match='32-bit linear'):
        translate_386_page(address, state(), lambda *args: pytest.fail('invalid address read'))


def test_short_physical_reads_refuse():
    with pytest.raises(ValueError, match='exact four-byte'):
        translate_386_page(0, state(), lambda *args: b'\0\0')


class MachinePeer:
    """Authored stop/register/step observations; no emulator acceptance claim."""

    def __init__(self, snapshots, *, running=False):
        self.snapshots = snapshots
        self.index = 0
        self.running = running
        self.architecture = 'i386'
        self.socket = object()
        self.physical_reads = []
        self.steps = 0

    def registers(self):
        return self.snapshots[min(self.index, len(self.snapshots) - 1)][0]

    def call(self, method, params=None):
        if method == 'query-status':
            return dict(running=self.running)
        assert method == 'human-monitor-command'
        return self.snapshots[min(self.index, len(self.snapshots) - 1)][1]

    def memory(self, address, length, *, space):
        if space == 'physical':
            self.physical_reads.append((address, length))
            return struct.pack('<I', {0x3004: 0x9007, 0x9014: 0x12007}[address])
        if length == 1120 and hasattr(self, 'report'):
            return self.report
        return b'\x90' * length

    def execute(self, command, timeout_ms):
        assert command == 's'
        self.steps += 1
        self.index += 1
        return b'T05thread:1;', False


def context(peer):
    vm = SimpleNamespace(lock=threading.RLock(), qmp=peer, gdb=peer,
                         debugger=lambda: peer, close=lambda: None)
    return MachineContext(vm)


def test_machine_translation_requires_stop_and_keeps_explicit_spaces():
    peer = MachinePeer([snapshot()], running=True)
    debug = context(peer)
    with pytest.raises(ValueError, match='Pause the machine'):
        debug.memory_translation(0x405234)
    assert peer.physical_reads == []
    peer.running = False
    result = debug.memory_translation('0x405234')
    assert result['physical_address'] == '0x12234' and result['cpu_mode'] == 'v86'
    assert peer.physical_reads == [(0x3004, 4), (0x9014, 4)]


def test_observed_trace_width_follows_v86_to_protected_transition():
    peer = MachinePeer([snapshot(ip=0x100),
                        snapshot(ip=0x101, flags=0x202, cs=0x18, base=0, attributes=0x00cf9b00),
                        snapshot(ip=0x102, flags=0x202, cs=0x18, base=0, attributes=0x00cf9b00)])
    debug = context(peer)
    debug._artifact = lambda name, kind, data, metadata: json.loads(data)
    result = debug.trace(count=2, bits=None)
    assert result['complete'] and peer.steps == 2
    assert [event['code_bits'] for event in result['events']] == [16, 32]
    assert [event['cpu_mode'] for event in result['events']] == ['v86', 'protected']
    assert result['bitness_source'] == 'observed per instruction'
    assert all(event['identity']['context'] == 'machine' for event in result['events'])


def test_trace_fetches_full_eip_while_decoding_16bit_protected_code():
    peer = MachinePeer([snapshot(flags=2, cr0=1, cr3=0, cs=0x10, base=0x10000,
                                attributes=0x00809b00, ip=ip) for ip in (0x12345, 0x12348)])
    reads = []
    # A truncated EIP selects a different valid instruction, not an invalid
    # opcode that would incidentally cause the trace to refuse.
    memory = {0x22345: b'\xb8\x34\x12' + b'\x90' * 12,
              0x12345: b'\xf4' + b'\x90' * 14}

    def read_memory(address, length, *, space):
        reads.append((address, length, space))
        return memory[address][:length]

    peer.memory = read_memory
    debug = context(peer)
    debug._artifact = lambda name, kind, data, metadata: json.loads(data)
    result = debug.trace(count=1, bits=None)
    assert result['complete'] and peer.steps == 1
    assert reads == [(0x22345, 15, 'virtual')]
    event = result['events'][0]
    assert event['address'] == '0x22345' and event['bytes'] == 'b83412'
    assert event['code_bits'] == 16 and event['cpu_mode'] == 'protected'
    assert result['session']['registers']['linear_pc'] == '0x22348'


def test_wrong_trace_width_refuses_before_executing():
    peer = MachinePeer([snapshot()])
    debug = context(peer)
    with pytest.raises(ValueError, match='code-segment width'):
        debug.trace(count=1, bits=32)
    assert peer.steps == 0


def qpi_record(*, status=0, active=0):
    """An authored wire record; no guest invocation is implied."""
    data = bytearray(1120)
    data[:8] = b'FDQPI001'
    struct.pack_into('<6H', data, 8, 1120, status, 0x0902, 0x0902, 0x1234, 0x9000)
    data[20] = active
    count, flags = {0: (272, 31), 5: (0, 3), 7: (3, 15)}[status]
    struct.pack_into('<2H', data, 22, count, flags)
    for page in range(count):
        struct.pack_into('<I', data, 32 + page * 4, (page << 12) | 7)
    return bytes(data)


def qpi_context(tmp_path, monkeypatch, report):
    from fdisbull.project import Project
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path / 'objects'))
    source = tmp_path / 'authored.bin'
    source.write_bytes(b'\x90' * 16)
    project = Project.create(tmp_path / 'observation.fdb', source, arch='x86', bits=16, base=0x7c00, entry=0x7c00)
    peer = MachinePeer([snapshot()])
    peer.report = report
    debug = context(peer)
    debug.bind(project, 'authored-observation')
    debug.guest_profile = dict(profile='qemm-386-v1', profile_sha256='b' * 64,
                              boot_image=dict(sha256=project.meta['source_sha256']),
                              memory_manager=dict(configured='qemm', observed='unknown'))
    debug.vm.inputs = dict(qemu=dict(sha256='c' * 64))
    debug.metadata = dict(guest_profile=debug.guest_profile)
    with project.transaction(True):
        project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                           (debug.run_id, 1, 'authored', None, 'stopped', json.dumps(debug.metadata)))
    return project, debug, peer


@pytest.mark.parametrize('status,active,observed,complete', [
    (0, 0, 'guest-reported-active', True),
    (7, 1, 'guest-reported-active', False),
    (0, 2, 'guest-reported-inactive', True),
    (5, 0, 'unknown', False),
])
def test_qpi_observation_persists_exact_report_without_freshness_claim(tmp_path, monkeypatch, status, active, observed, complete):
    from fdisbull.project import Project
    record = qpi_record(status=status, active=active)
    project, debug, peer = qpi_context(tmp_path, monkeypatch, record)
    try:
        result = debug.qemm_observe('0x70236')
        observation = result['observation']
        assert observation['observed'] == observed and observation['complete'] is complete
        assert observation['guest_api_called'] is False
        assert observation['freshness'] == 'not_established'
        assert observation['native_execution_validation'] == 'not_established_by_report'
        assert observation['identity']['boot_image_sha256'] == project.meta['source_sha256']
        assert result['registers']['cpu_mode'] == 'v86'
        assert peer.steps == 0
        artifact_id = result['artifact']['artifact']
        assert bytes(project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (artifact_id,)).fetchone()[0]) == record
        assert debug.guest_profile['memory_manager']['observed'] == observed
        assert debug.guest_profile['memory_manager']['configured'] == 'qemm'
    finally:
        project.__exit__(None, None, None)
    with Project(tmp_path / 'observation.fdb') as reopened:
        run = reopened.debug_runs()['runs'][0]
        assert run['metadata']['qemm_observation']['observed'] == observed
        assert run['metadata']['qemm_observation']['complete'] is complete
        assert run['metadata']['qemm_observation']['artifact'] == artifact_id
        assert bytes(reopened.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (artifact_id,)).fetchone()[0]) == record
        assert reopened.debug_runs()['live_state_verified'] is False


def test_failed_qpi_parse_never_updates_observation_or_artifacts(tmp_path, monkeypatch):
    record = b'INVALID!' + qpi_record()[8:]
    project, debug, peer = qpi_context(tmp_path, monkeypatch, record)
    try:
        with pytest.raises(ValueError, match='signature'):
            debug.qemm_observe(0x70236)
        assert debug.guest_profile['memory_manager']['observed'] == 'unknown'
        assert project.debug_artifacts()['artifacts'] == []
        assert 'qemm_observation' not in project.debug_runs()['runs'][0]['metadata']
    finally:
        project.__exit__(None, None, None)


def test_qpi_observation_requires_stopped_profile_and_exact_extent(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='QEMM guest profile'):
        context(MachinePeer([snapshot()])).qemm_observe(0)
    project, debug, peer = qpi_context(tmp_path, monkeypatch, qpi_record())
    try:
        for length in (1119, 1121, True):
            with pytest.raises(ValueError, match='exactly 1120'):
                debug.qemm_observe(0, length=length)
        with pytest.raises(ValueError, match='bounded 32-bit'):
            debug.qemm_observe(0xffffffff)
        peer.running = True
        with pytest.raises(ValueError, match='Pause the machine'):
            debug.qemm_observe(0)
        assert project.debug_artifacts()['artifacts'] == []
    finally:
        project.__exit__(None, None, None)
