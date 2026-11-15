"""Authored stopped-memory contracts; no vendor bytes or native claims."""
from copy import deepcopy
import hashlib
import struct
import threading
from types import SimpleNamespace

import pytest

from fdisbull import runtime_desqview as dv


def authored_source():
    raw = bytearray(dv.DV_SIZE)
    raw[:2] = b'MZ'
    struct.pack_into('<H', raw, 8, dv.MZ_HEADER // 16)
    for ordinal, (start, size) in enumerate(dv.FINGERPRINTS):
        raw[dv.MZ_HEADER+start:dv.MZ_HEADER+start+size] = bytes((index+ordinal*37) % 256 for index in range(size))
    return bytes(raw)


class Native:
    def __init__(self):
        self.vm = SimpleNamespace(lock=threading.RLock())
        self.run_id = 'authored-native-run'
        self.ram = bytearray(0x110000)
        self.reads = []
        self.base = 0x20000
        self.segment = self.base >> 4
        self.source = authored_source()
        self.source_identity = dict(source_sha256=hashlib.sha256(self.source).hexdigest(),
                                    provider='authored-test-only')
        self.observed = dict(registers=dict(cpu_mode='v86', registers=dict(eip='0x0200', eax='0x0',
                             ebx='0x0', edx='0x0', ebp='0x0')),
                             address_state=dict(cpu_mode='v86', code_bits=16, machine_vcpus=1,
                               register_context_match=True,
                               segments=dict(cs=dict(selector='0x4000', base='0x40000'))))
        self.ram[0x54:0x58] = struct.pack('<HH', dv.INT15_IP, self.segment)
        self.ram[self.base+dv.INT15_IP-8:self.base+dv.INT15_IP] = b'DESQview'
        for start, size in dv.FINGERPRINTS:
            self.ram[self.base+start:self.base+start+size] = self.source[dv.MZ_HEADER+start:dv.MZ_HEADER+start+size]
        self.data_segment, self.task_offset, self.handle, self.mapping = 0x8000, 0x1200, 0x9234, 0x1440
        struct.pack_into('<5H', self.ram, self.base+dv.CURRENT_HANDLE,
                         self.handle, self.mapping, self.data_segment, self.task_offset, self.data_segment)
        struct.pack_into('<H', self.ram, self.data_segment*16+self.task_offset+10, self.handle)
        struct.pack_into('<2H', self.ram, self.data_segment*16+0xa04, self.mapping, self.task_offset)
        self.add_task(self.handle, self.mapping, self.task_offset, 0x7000, 0x100)
        self.ram[self.base+0x19f8] = 0xde

    def add_task(self, handle, mapping, offset, process_segment, process_offset):
        record = self.data_segment*16+offset
        for address in (record, handle*16):
            struct.pack_into('<H', self.ram, address+4, 0xfedc)
            struct.pack_into('<H', self.ram, address+10, handle)
            struct.pack_into('<HH', self.ram, address+12, offset, self.data_segment)
            struct.pack_into('<H', self.ram, address+dv.TASK_MAPPING, mapping)
        struct.pack_into('<HH', self.ram, record+dv.TASK_PROCESS, process_offset, process_segment)
        struct.pack_into('<HH', self.ram, self.data_segment*16+mapping+dv.MAPPING_PROCESS,
                         process_offset, process_segment)

    def select_task(self, handle, mapping, offset):
        struct.pack_into('<5H', self.ram, self.base+dv.CURRENT_HANDLE,
                         handle, mapping, self.data_segment, offset, self.data_segment)
        struct.pack_into('<2H', self.ram, self.data_segment*16+0xa04, mapping, offset)

    def read(self, address, size, space):
        assert space == 'linear'
        self.reads.append((address, size))
        raw = bytes(self.ram[address:address+size])
        assert len(raw) == size
        return raw

    def hook(self, event=6, **changes):
        self.observed['address_state']['segments']['cs'] = dict(selector=hex(self.segment), base=hex(self.base))
        self.observed['registers']['registers'].update(eip=hex(dv.XDI_IP), eax=hex(0xde00 | event),
                                                      ebx=hex(self.mapping), edx=hex(self.handle), ebp=hex(event*4), **changes)
        return deepcopy(self.observed['registers'])


@pytest.fixture
def native(monkeypatch):
    value = Native()
    monkeypatch.setattr(dv, '_source', lambda session: (session.source, session.source_identity))
    monkeypatch.setattr(dv, '_paused', lambda session: deepcopy(session.observed))
    monkeypatch.setattr(dv, '_read', lambda session, address, size, space: session.read(address, size, space))
    return value


def test_discover_and_current_identity_are_passive_bounded_and_explicit_about_attach(native):
    provider = dv.discover(native)
    assert provider.hook_address == native.base + dv.XDI_IP
    identity = provider.current_identity()
    assert identity['handle'] == native.handle
    assert identity['record'] == dict(segment=native.data_segment, offset=native.task_offset,
                                      linear=native.data_segment*16+native.task_offset)
    assert identity['mapping_context'] == native.mapping
    assert 'earlier creation' in identity['qualification']
    assert 'Creation before attachment is unknown' in provider.catalog['lifetime']
    assert sum(size for _, size in native.reads) < 1024


@pytest.mark.parametrize('event,kind', [(3,'dv-end'), (4,'process-create'), (5,'process-end'),
                                      (6,'create'), (7,'end'), (8,'save'), (9,'restore'),
                                      (0x10,'free'), (0x0a,'other')])
def test_natural_lifecycle_events_do_not_create_host_generations(native, event, kind):
    provider = dv.discover(native)
    result = provider.interpret_event(native.hook(event))
    assert result['kind'] == kind and result['event'] == event
    assert result['handle'] == native.handle and result['mapping_context'] == native.mapping
    assert 'generation' not in result


@pytest.mark.parametrize('change', ['handle', 'pointer', 'data_segment', 'linked_task', 'linked_mapping', 'zero_handle'])
def test_inconsistent_manager_records_never_publish_identity(native, change):
    provider = dv.discover(native)
    if change == 'handle': native.ram[native.base+dv.CURRENT_HANDLE] ^= 1
    if change == 'pointer': native.ram[native.base+dv.CURRENT_POINTER] ^= 1
    if change == 'data_segment': native.ram[native.base+dv.CURRENT_MAPPING+2] ^= 1
    if change == 'linked_task': native.ram[native.data_segment*16+0xa06] ^= 1
    if change == 'linked_mapping': native.ram[native.data_segment*16+0xa04] ^= 1
    if change == 'zero_handle': struct.pack_into('<H', native.ram, native.data_segment*16+native.task_offset+10, 0)
    with pytest.raises(dv.DesqviewProviderError, match='linkage'):
        provider.current_identity()
    assert dv.discover(native) is None


def test_changed_original_code_and_run_are_refused(native):
    provider = dv.discover(native)
    native.ram[native.base+dv.FINGERPRINTS[0][0]] ^= 1
    with pytest.raises(dv.DesqviewProviderError, match='fingerprint'):
        provider.current_identity()
    native.ram[native.base+dv.FINGERPRINTS[0][0]] ^= 1
    native.run_id = 'another-run'
    with pytest.raises(dv.DesqviewProviderError, match='another run'):
        provider.current_identity()


@pytest.mark.parametrize('change', ['pc', 'handle', 'bp', 'multiplex', 'stale'])
def test_stale_or_unqualified_lifecycle_arguments_refuse(native, change):
    provider = dv.discover(native)
    regs = native.hook()
    values = native.observed['registers']['registers']
    if change == 'pc': values['eip'] = '0x1a62'
    if change == 'handle': values['edx'] = '0x1111'
    if change == 'bp': values['ebp'] = '0x0'
    if change == 'multiplex': values['eax'] = '0xdd06'
    if change != 'stale': regs = deepcopy(native.observed['registers'])
    else: values['ebx'] = '0x1'
    with pytest.raises(dv.DesqviewProviderError): provider.interpret_event(regs)


def test_never_scan_matching_unreferenced_ram_or_follow_unbounded_vector_chain(native):
    native.ram[0x54:0x58] = struct.pack('<HH', 0x100, 0x3000)
    assert dv.discover(native) is None
    native.ram[0x30100:0x30105] = b'\xea' + struct.pack('<HH', dv.INT15_IP, native.segment)
    assert dv.discover(native) is not None
    native.ram[0x30100:0x30105] = b'\xea' + struct.pack('<HH', 0x100, 0x3000)
    assert dv.discover(native) is None
    assert len(native.reads) < 40


def test_observed_original_manager_path_can_qualify_unsupported_vector_wrapper(native):
    native.ram[0x54:0x58] = struct.pack('<HH', 0x100, 0x3000)
    native.hook()
    provider = dv.discover(native)
    assert provider.catalog['discovery'] == 'observed-manager-PC'


@pytest.mark.parametrize('change', ['protected', 'multi_cpu', 'incoherent', 'bad_base'])
def test_no_guessed_cpu_segment_domain(native, change):
    state = native.observed['address_state']
    if change == 'protected': state['cpu_mode'] = 'protected'
    if change == 'multi_cpu': state['machine_vcpus'] = 2
    if change == 'incoherent': state['register_context_match'] = False
    if change == 'bad_base': state['segments']['cs']['base'] = '0x12345'
    assert dv.discover(native) is None


def test_source_pin_rechecks_actual_carrier_and_original_member(tmp_path, monkeypatch):
    from fdisbull import qemm_runtime
    raw = authored_source()
    carrier = tmp_path / 'authored-carrier.bin'
    carrier.write_bytes(b'authored FAT collaborator')
    monkeypatch.setattr(dv, 'DV_SHA256', hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(qemm_runtime, '_FATVolume', lambda data: SimpleNamespace(read=lambda path, maximum: raw))
    session = SimpleNamespace(guest_profile=dict(profile='desqview-386-v1',
        members=[dict(role='program', sha256=dv.DV_SHA256, guest_path=r'C:\DV\DV.EXE')],
        boot_image=dict(path=str(carrier), sha256=hashlib.sha256(carrier.read_bytes()).hexdigest())))
    assert dv._source(session)[0] == raw
    carrier.write_bytes(b'changed')
    with pytest.raises(dv.DesqviewProviderError, match='carrier changed'): dv._source(session)


def test_changed_stop_during_read_is_not_an_identity(native, monkeypatch):
    count = 0
    def paused(session):
        nonlocal count
        count += 1
        observed = deepcopy(session.observed)
        if count > 1: observed['registers']['registers']['eip'] = '0x201'
        return observed
    monkeypatch.setattr(dv, '_paused', paused)
    with pytest.raises(dv.DesqviewProviderError, match='changed CPU stop'): dv.discover(native)


def wide_bank(native):
    row = native.observed['registers']
    row['architecture'] = 'i386:x86-64'
    for narrow, wide in (('eip', 'rip'), ('eax', 'rax'), ('ebx', 'rbx'),
                         ('edx', 'rdx'), ('ebp', 'rbp')):
        if narrow in row['registers']:
            row['registers'][wide] = row['registers'].pop(narrow)
    return deepcopy(row)


@pytest.mark.parametrize('mode', ['real', 'v86'])
def test_wide_xml_bank_qualifies_legacy_manager_and_event_without_rewriting_raw_registers(native, mode):
    native.observed['address_state']['cpu_mode'] = mode
    native.observed['registers']['cpu_mode'] = mode
    before = wide_bank(native)
    provider = dv.discover(native)
    assert provider is not None
    assert native.observed['registers'] == before
    native.hook(6)
    registers = wide_bank(native)
    registers['registers']['rax'] = '0xc000de06'
    native.observed['registers'] = deepcopy(registers)
    event = provider.interpret_event(registers)
    assert event['kind'] == 'create' and event['handle'] == native.handle
    assert event['mapping_context'] == native.mapping and event['containment_qualified']
    assert native.observed['registers'] == registers
    assert 'eip' not in registers['registers'] and registers['registers']['rax'] == '0xc000de06'


@pytest.mark.parametrize('name', ['eip', 'eax', 'ebx', 'edx', 'ebp'])
def test_conflicting_wide_and_narrow_register_aliases_refuse(native, name):
    provider = dv.discover(native)
    native.hook(6)
    registers = wide_bank(native)
    wide = {'eip':'rip', 'eax':'rax', 'ebx':'rbx', 'edx':'rdx', 'ebp':'rbp'}[name]
    registers['registers'][name] = hex(int(registers['registers'][wide], 0) ^ 1)
    native.observed['registers'] = deepcopy(registers)
    with pytest.raises(dv.DesqviewProviderError, match='alias'):
        provider.interpret_event(registers)


@pytest.mark.parametrize('change', ['rip-upper32', 'rax-upper32', 'rip-above16',
                                   'long-mode', 'code64', 'wrong-architecture'])
def test_wide_register_adaptation_never_truncates_invalid_or_out_of_domain_values(native, change):
    provider = dv.discover(native)
    native.hook(6)
    registers = wide_bank(native)
    if change == 'rip-upper32': registers['registers']['rip'] = '0x100001a63'
    elif change == 'rax-upper32': registers['registers']['rax'] = '0x10000de06'
    elif change == 'rip-above16': registers['registers']['rip'] = '0x11a63'
    elif change == 'long-mode':
        registers['cpu_mode'] = native.observed['address_state']['cpu_mode'] = 'long'
    elif change == 'code64': native.observed['address_state']['code_bits'] = 64
    else: registers['architecture'] = 'aarch64'
    native.observed['registers'] = deepcopy(registers)
    with pytest.raises(dv.DesqviewProviderError):
        provider.interpret_event(registers)
