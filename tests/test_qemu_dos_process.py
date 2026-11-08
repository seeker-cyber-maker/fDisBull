"""Host-side source and allocation invariants for actual DOS process binding."""
import struct

import pytest

from fdisbull.dos import load_com, load_mz
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from fdisbull.qemu_dos_process import observe_devices, observe_mcbs, relocated_source
from test_dos_loader import mz_file


def test_com_mapping_uses_observed_psp_not_the_static_analysis_segment():
    source = b'\x90\xc3'
    dos = load_com(source, load_segment=0x1000).metadata['dos']
    report = dict(child_psp=0x2345, entry_cs=0x2345, entry_ip=0x100,
                  stack_ss=0x2345, stack_sp=0xfffe, raw_stack_sp=0xfffc, initial_ax=0)
    expected, mapping = relocated_source(source, dos, 'COM', report)
    assert expected == source
    assert mapping['static_base'] == 0x10100
    assert mapping['runtime_base'] == 0x23550
    assert mapping['module_size'] == 2
    assert mapping['stack_linear'] == 0x3344e


def test_mz_mapping_uses_entry_segment_and_ordered_original_relocations():
    module = bytearray(128)
    struct.pack_into('<HH', module, 4, 3, 5)
    source = mz_file(bytes(module), relocations=[(4, 0), (4, 0), (6, 0)],
                     cs=2, ip=1, ss=3, sp=32, minalloc=16, overlay=b'NOT-LOADED')
    dos = load_mz(source, load_segment=0x1000).metadata['dos']
    # Deliberately far from PSP+10h, as a high-load allocation can be.
    report = dict(child_psp=0x1800, entry_cs=0x6002, entry_ip=1,
                  stack_ss=0x6003, stack_sp=32, raw_stack_sp=30, initial_ax=0)
    expected, mapping = relocated_source(source, dos, 'MZ', report)
    assert len(expected) == len(module)
    assert struct.unpack_from('<HH', expected, 4) == (0xc003, 0x6005)
    assert mapping['load_segment'] == 0x6000
    assert mapping['entry_linear'] == 0x60021
    assert mapping['file_offset'] == 64
    assert source[68:72] == b'\x03\0\x05\0'


@pytest.mark.parametrize('field,value', [('entry_ip', 2), ('stack_ss', 0x2001), ('stack_sp', 33)])
def test_mz_loader_register_disagreement_is_refused(field, value):
    source = mz_file(bytes(64), cs=0, ip=0, ss=0, sp=32)
    dos = load_mz(source).metadata['dos']
    report = dict(child_psp=0x1ff0, entry_cs=0x2000, entry_ip=0, stack_ss=0x2000,
                  stack_sp=32, raw_stack_sp=30, initial_ax=0)
    report[field] = value
    with pytest.raises(DebuggerError, match='entry|stack'):
        relocated_source(source, dos, 'MZ', report)


def test_loader_stack_write_follows_relocation_and_records_only_file_intersection():
    # One byte of AX is in the file. The other is DOS's allocated memory, so it
    # must not enlarge or mask the source comparison. The word is also relocated.
    source = mz_file(b'\x90\x90\x34\x12', relocations=[(2, 0)],
                     cs=0, ip=0, ss=0, sp=5)
    dos = load_mz(source).metadata['dos']
    report = dict(child_psp=0x1ff0, entry_cs=0x2000, entry_ip=0,
                  stack_ss=0x2000, stack_sp=5, raw_stack_sp=3, initial_ax=0xff00)
    expected, mapping = relocated_source(source, dos, 'MZ', report)
    assert expected == b'\x90\x90\x34\x00'
    assert mapping['loader_writes'] == [dict(kind='load-only-initial-ax',
        runtime_address=0x20003, file_offset=67, module_offset=3,
        before_hex='32', after_hex='00')]
    assert source[-2:] == b'\x34\x12'


def test_com_stack_words_are_exact_and_use_the_reported_raw_offset():
    source = b'\x90' + bytes(0xfefb) + bytes.fromhex('efbefeca')
    dos = load_com(source).metadata['dos']
    report = dict(child_psp=0x2000, entry_cs=0x2000, entry_ip=0x100,
                  stack_ss=0x2000, stack_sp=0xfffe, raw_stack_sp=0xfffc, initial_ax=0xff)
    expected, mapping = relocated_source(source, dos, 'COM', report)
    assert expected[:-4] == source[:-4]
    assert expected[-4:] == b'\xff\0\0\0'
    assert [row['kind'] for row in mapping['loader_writes']] == [
        'com-near-return-zero', 'load-only-initial-ax']
    # A wrapped raw SP is a 16-bit offset, not corrected linear stack minus two.
    report.update(stack_sp=0, raw_stack_sp=0xfffe)
    expected, mapping = relocated_source(source, dos, 'COM', report)
    assert expected[-4:] == b'\xef\xbe\xff\0'
    assert mapping['loader_writes'][0]['runtime_address'] == 0x2fffe


def _mcb(kind, owner, paragraphs):
    value = bytearray(16)
    struct.pack_into('<BHH', value, 0, ord(kind), owner, paragraphs)
    return bytes(value)


def test_mcb_walk_ignores_stale_headers_inside_a_coalesced_free_block():
    memory = bytearray(0x5000)
    memory[0x1000:0x1010] = _mcb('M', 0x101, 0x20)
    memory[0x1210:0x1220] = _mcb('Z', 0, 0x100)
    # A freed/coalesced child header may remain readable as stale bytes.
    memory[0x1800:0x1810] = _mcb('M', 0x181, 0x10)
    blocks = observe_mcbs(lambda a, n: bytes(memory[a:a+n]), 0x100)
    assert [(b['mcb_segment'], b['owner_psp']) for b in blocks] == [(0x100, 0x101), (0x121, 0)]
    assert all(b['owner_psp'] != 0x181 for b in blocks)


def test_mcb_walk_refuses_wrapping_malformed_and_excessive_chains():
    with pytest.raises(DebuggerError, match='wraps'):
        observe_mcbs(lambda a, n: _mcb('Z', 1, 0xffff), 0x100)
    with pytest.raises(DebuggerError, match='malformed'):
        observe_mcbs(lambda a, n: bytes(16), 0x100)
    with pytest.raises(DebuggerError, match='bounded inventory'):
        observe_mcbs(lambda a, n: _mcb('M', 0, 0), 0x100, maximum=2)


def test_device_observation_requires_nul_anchor_and_bounds_the_chain():
    memory = bytearray(0x3000)
    anchor = 0x1022
    struct.pack_into('<HHHHH8s', memory, anchor, 0, 0x120, 0x8004, 0x40, 0x50, b'NUL     ')
    struct.pack_into('<HHHHH8s', memory, 0x1200, 0xffff, 0xffff, 0x8000, 0x60, 0x70, b'AUTHDRV ')
    read = lambda a, n: bytes(memory[a:a+n])
    observed = observe_devices(read, 0x100, 0)
    assert observed['status'] == 'observed'
    assert [row['name'] for row in observed['headers']] == ['NUL', 'AUTHDRV']
    memory[anchor+10:anchor+18] = b'NOT-NUL '
    assert observe_devices(read, 0x100, 0)['status'] == 'unknown'
    memory[anchor+10:anchor+18] = b'NUL     '
    struct.pack_into('<HH', memory, 0x1200, 0, 0x120)
    assert observe_devices(read, 0x100, 0)['status'] == 'incomplete'


@pytest.fixture
def com_project(tmp_path):
    source = tmp_path/'SMALL.COM'
    source.write_bytes(b'\xc3')
    with Project.create(tmp_path/'small.fdb', source, image='com') as project:
        yield project


def test_factory_keeps_program_and_boot_disk_as_separate_inputs(com_project, tmp_path, monkeypatch):
    import fdisbull.qemu_dos_process as implementation
    captured = {}
    sentinel = object()

    def create(project, executable, game_dir, **options):
        captured.update(project=project, executable=executable, game_dir=game_dir, **options)
        return sentinel

    monkeypatch.setattr(implementation, 'QemuDOSProcessSession', create)
    disk = tmp_path/'separate.img'
    result = com_project.debugger('qemu', tmp_path, backend='qemu-dos', dos_boot_image=disk,
        dos_mcopy='mcopy', dos_startup_batch='AUTOEXEC.BAT', dos_arguments=' /Q', qemu_transport='pipe')
    assert result is sentinel
    assert captured['boot_image'] == disk
    assert captured['startup_batch'] == 'AUTOEXEC.BAT'
    assert captured['arguments'] == ' /Q'
    assert captured['transport'] == 'pipe'


def test_process_launch_requires_explicit_native_disk_and_backend(com_project, tmp_path):
    with pytest.raises(ValueError, match='separate dos_boot_image'):
        com_project.debugger('not-started', tmp_path, backend='qemu-dos')
    with pytest.raises(ValueError, match='require backend=qemu-dos'):
        com_project.debugger('not-started', tmp_path, backend='dosbox', dos_boot_image=tmp_path/'DOS.img')


@pytest.mark.parametrize('arguments', ['x'*127, 'one\rtwo', 'one\ntwo', 'one\0two', '\U0001f642'])
def test_invalid_command_tail_is_refused_before_qemu_or_disk_access(com_project, tmp_path, arguments):
    with pytest.raises(ValueError, match='command tail|CP437'):
        com_project.debugger('not-started', tmp_path, backend='qemu-dos',
                            dos_boot_image=tmp_path/'absent.img', dos_arguments=arguments)


def test_close_reaps_owned_resources_even_if_persistence_fails():
    from types import SimpleNamespace
    from fdisbull.qemu_dos_process import QemuDOSProcessSession
    observed = []

    def unavailable_database(*args):
        raise RuntimeError('database unavailable')

    session = QemuDOSProcessSession.__new__(QemuDOSProcessSession)
    session.closed = False
    session.run_id = 'owned-run'
    session.vm = SimpleNamespace(close=lambda: observed.append('machine closed'))
    session._staging = SimpleNamespace(cleanup=lambda: observed.append('staging removed'))
    session._process = dict(state='active', source_mapping=dict(live=True, live_ranges=[]))
    session.metadata = {}
    session.project = SimpleNamespace(transaction=unavailable_database, _live_debuggers=[session])
    with pytest.raises(RuntimeError, match='database unavailable'):
        session.close()
    assert observed == ['machine closed', 'staging removed']
    assert session.closed and session.project._live_debuggers == []
