"""Source checks for the homegrown loader/TLS/DllMain experiment.

The optional Unicorn tests call captured fixture code explicitly. They validate
the callback source and persistent mutation, not the operating-system loader.
Native acceptance must separately observe genuine loader callbacks and exit.
"""
import os
from pathlib import Path

import pytest


FIELDS = ('event_count', 'stage', 'seen_stage', 'detach_flag', 'report_stage_seen',
          'report_count_seen', 'tls_detach_stage_seen', 'dllmain_detach_stage_seen')


def decode_dll_data(raw):
    """Decode only the authored 64-byte exported record, not arbitrary DLL data."""
    if isinstance(raw, str):
        raw = bytes.fromhex(raw)
    if len(raw) != 64:
        raise ValueError('DLL initialization record must contain exactly 64 bytes')
    words = [int.from_bytes(raw[k:k + 4], 'little') for k in range(0, 64, 4)]
    if words[0] > 8:
        raise ValueError('DLL initialization event count exceeds the source record')
    return dict(zip(FIELDS, words[:8])) | {'event_log': words[8:8 + words[0]],
                                         'unused_log': words[8 + words[0]:]}


def verify_executable_observations(entry_data, final_data, *, exit_code):
    """Check all authored EXE globals and each naturally executed DWORD input."""
    entry_data = bytes.fromhex(entry_data) if isinstance(entry_data, str) else entry_data
    final_data = bytes.fromhex(final_data) if isinstance(final_data, str) else final_data
    assert len(entry_data) == len(final_data) == 32
    expected_entry = (bytes(4) + (0xaaaaaaaa).to_bytes(4, 'little') +
                      (0xbbbbbbbbbbbbbbbb).to_bytes(8, 'little') + (0xcccccccc).to_bytes(4, 'little') * 4)
    assert entry_data == expected_entry
    values = [int.from_bytes(final_data[k:k + 4], 'little') for k in range(0, 32, 4)]
    assert values == [1, 3, 0x1234, 0, 0, 1, 0xffffffff, 0x1234]
    assert exit_code == 7
    return {'status': 'source_executable_globals_verified', 'entry_seen': 1, 'dll_report': 3,
            'last_error_inputs_and_results': [0, 1, 0xffffffff, 0x1234],
            'final_last_error': 0x1234, 'process_exit_code': exit_code}


def verify_loader_observations(observations, *, exit_code):
    """Check observed source milestones without assuming the detach order.

    Each row has ``phase``, ``data`` (64 bytes or hex), and ``constant``. The
    phases are before-tls, tls-attached, dll-attached, exe-entry, reported,
    and two detached rows. Native collection supplies their chronological order.
    ``before-tls`` must precede the first callback, rather than being a reset.
    """
    phases = [row['phase'] for row in observations]
    assert phases == ['before-tls', 'tls-attached', 'dll-attached', 'exe-entry',
                      'reported', 'detached', 'detached'], phases
    rows = [decode_dll_data(row['data']) for row in observations]
    first = rows[0]
    assert all(first[name] == 0 for name in FIELDS)
    assert first['event_log'] == [] and all(v == 0 for v in first['unused_log'])
    assert observations[0]['constant'] == 1
    tls, attached, entry, reported = rows[1:5]
    assert tls == decode_dll_data(_record((0x11,), stage=1))
    assert tls['event_log'] == [0x11] and tls['stage'] == 1
    assert tls['seen_stage'] == tls['detach_flag'] == 0
    assert observations[1]['constant'] == 2
    assert attached['event_log'] == [0x11, 0x22]
    assert attached['stage'] == 2 and attached['seen_stage'] == 1
    assert attached == decode_dll_data(_record((0x11, 0x22), stage=2, seen=1))
    assert attached['detach_flag'] == 0 and observations[2]['constant'] == 3
    assert entry == attached and observations[3]['constant'] == 3
    assert reported['event_log'] == [0x11, 0x22, 0x33]
    assert reported['stage'] == 3 and reported['seen_stage'] == 1
    assert reported['report_stage_seen'] == 2 and reported['report_count_seen'] == 2
    assert reported['detach_flag'] == 0 and observations[4]['constant'] == 3
    assert reported == decode_dll_data(_record((0x11, 0x22, 0x33), stage=3, seen=1, report=True))
    assert observations[4].get('report_return', 3) == 3
    flags, order = 0, []
    for index, (observation, state) in enumerate(zip(observations[5:], rows[5:], strict=True), 4):
        assert state['event_count'] == index
        assert state['event_log'][:-1] == [0x11, 0x22, 0x33, *order]
        event = state['event_log'][-1]
        assert event in (0x44, 0x55) and event not in order
        order.append(event)
        flags |= 1 if event == 0x44 else 2
        assert state['detach_flag'] == flags
        assert state['stage'] == 3 and state['seen_stage'] == 1
        assert state['report_stage_seen'] == state['report_count_seen'] == 2
        if event == 0x44 or 0x44 in order:
            assert state['tls_detach_stage_seen'] == 3
        if event == 0x55 or 0x55 in order:
            assert state['dllmain_detach_stage_seen'] == 3
        assert state == decode_dll_data(_record((0x11, 0x22, 0x33, *order), stage=3, seen=1,
                        flags=flags, report=True, tls_detach=0x44 in order, main_detach=0x55 in order))
        assert observation['constant'] == 3
    assert flags == 3 and exit_code == 7
    return {'status': 'source_milestones_verified',
            'attach_order': ['TLS process attach', 'DllMain process attach', 'EXE entry', 'dll_report'],
            'detach_order_observed': ['TLS process detach' if e == 0x44 else 'DllMain process detach' for e in order],
            'code_constant_versions': [1, 2, 3], 'process_exit_code': exit_code,
            'scope': 'Source milestone verification; genuine loader provenance and native exit require the collector receipts'}


def _record(events=(), *, stage=0, seen=0, flags=0, report=False, tls_detach=False, main_detach=False):
    words = [len(events), stage, seen, flags, 2 if report else 0, 2 if report else 0,
             3 if tls_detach else 0, 3 if main_detach else 0, *events, *([0] * (8 - len(events)))]
    return b''.join(v.to_bytes(4, 'little') for v in words)


def _observations(detach=(0x44, 0x55)):
    rows = [{'phase': 'before-tls', 'data': _record(), 'constant': 1},
            {'phase': 'tls-attached', 'data': _record((0x11,), stage=1), 'constant': 2},
            {'phase': 'dll-attached', 'data': _record((0x11, 0x22), stage=2, seen=1), 'constant': 3}]
    rows.append(rows[-1] | {'phase': 'exe-entry'})
    rows.append({'phase': 'reported', 'data': _record((0x11, 0x22, 0x33), stage=3, seen=1, report=True),
                 'constant': 3, 'report_return': 3})
    events, flags = [0x11, 0x22, 0x33], 0
    for event in detach:
        events.append(event)
        flags |= 1 if event == 0x44 else 2
        rows.append({'phase': 'detached', 'data': _record(events, stage=3, seen=1, flags=flags, report=True,
                     tls_detach=0x44 in events, main_detach=0x55 in events), 'constant': 3})
    return rows


@pytest.mark.parametrize('detach', [(0x44, 0x55), (0x55, 0x44)])
def test_source_milestones_preserve_the_observed_detach_order(detach):
    result = verify_loader_observations(_observations(detach), exit_code=7)
    assert result['status'] == 'source_milestones_verified'
    assert result['code_constant_versions'] == [1, 2, 3]


@pytest.mark.parametrize('phase', ['before-tls', 'tls-attached', 'dll-attached', 'exe-entry', 'reported', 'detached'])
def test_missing_or_forged_loader_milestones_are_rejected(phase):
    observations = _observations()
    index = next(i for i, row in enumerate(observations) if row['phase'] == phase)
    del observations[index]
    with pytest.raises(AssertionError):
        verify_loader_observations(observations, exit_code=7)


def test_unmodified_code_or_wrong_api_exit_cannot_qualify_the_loader_target():
    observations = _observations()
    observations[2]['constant'] = 2
    with pytest.raises(AssertionError):
        verify_loader_observations(observations, exit_code=7)
    with pytest.raises(AssertionError):
        verify_loader_observations(_observations(), exit_code=9)
    with pytest.raises(ValueError):
        decode_dll_data(bytes(63))
    with pytest.raises(ValueError):
        decode_dll_data((9).to_bytes(4, 'little') + bytes(60))


def test_executable_source_globals_include_each_dword_api_result():
    initial = bytes(4) + (0xaaaaaaaa).to_bytes(4, 'little') + (0xbbbbbbbbbbbbbbbb).to_bytes(8, 'little') + (0xcccccccc).to_bytes(4, 'little') * 4
    final = b''.join(value.to_bytes(4, 'little') for value in (1, 3, 0x1234, 0, 0, 1, 0xffffffff, 0x1234))
    assert verify_executable_observations(initial, final, exit_code=7)['dll_report'] == 3
    wrong = bytearray(final)
    wrong[24:28] = (0x7fffffff).to_bytes(4, 'little')
    with pytest.raises(AssertionError):
        verify_executable_observations(initial, wrong, exit_code=7)
    with pytest.raises(AssertionError):
        verify_executable_observations(initial, final, exit_code=9)


def inspect_loader_fixtures(executable, library):
    """Check shipped PE directory/import identities before any runtime claim."""
    lief = pytest.importorskip('lief')
    exe, dll = lief.PE.parse(str(executable)), lief.PE.parse(str(library))
    assert exe is not None and dll is not None and dll.has_tls and not exe.has_tls
    assert not exe.data_directories[14].rva and not dll.data_directories[14].rva
    exports = {e.name: dll.imagebase + e.address for e in dll.get_export().entries}
    assert dll.imagebase + dll.optional_header.addressof_entrypoint == exports['dll_entry']
    assert list(dll.tls.callbacks) == [exports['dll_tls_callback']]
    assert dll.tls.addressof_index == exports['dll_tls_index']
    assert dll.tls.addressof_callbacks == exports['dll_tls_callbacks']
    assert bytes(dll.get_content_from_virtual_address(exports['dll_data_start'], 64)) == bytes(64)
    assert bytes(dll.get_content_from_virtual_address(exports['dll_report_constant_immediate'], 4)) == bytes.fromhex('01000000')
    imports = {item.name.lower(): {entry.name for entry in item.entries} for item in exe.imports}
    assert imports == {'kernel32.dll': {'SetLastError', 'GetLastError', 'ExitProcess'}, 'smcinit.dll': {'dll_report'}}
    assert not list(dll.imports)
    assert exports['dll_code_end'] - exports['dll_code_start'] <= 512
    return exe, dll, exports


def _inputs():
    exe = os.environ.get('FDISBULL_INIT_EXE_FIXTURE')
    dll = os.environ.get('FDISBULL_INIT_DLL_FIXTURE')
    if not exe or not dll:
        pytest.skip('Select the real built homegrown EXE and SMCINIT.dll fixtures')
    assert Path(exe).is_file() and Path(dll).is_file()
    return Path(exe), Path(dll)


def test_real_pe_tls_directory_and_imports_reference_the_authored_callbacks():
    inspect_loader_fixtures(*_inputs())


@pytest.mark.parametrize('detach', [('tls', 'main'), ('main', 'tls')])
def test_independent_cpu_callbacks_preserve_source_code_epochs_and_data(detach):
    """Manual callback CPU replay, explicitly distinct from genuine loader use."""
    unicorn = pytest.importorskip('unicorn')
    from unicorn import x86_const as reg
    _, dll, symbols = inspect_loader_fixtures(*_inputs())
    cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
    for section in dll.sections:
        start = dll.imagebase + section.virtual_address
        length = max(section.virtual_size, len(section.content))
        if length:
            cpu.mem_map(start & ~4095, ((start % 4096 + length + 4095) // 4096) * 4096)
            cpu.mem_write(start, bytes(section.content))
    cpu.mem_map(0x6000, 0x3000)
    boundary, stack = 0x6000, 0x8008
    cpu.mem_write(boundary, b'\x90')
    code_start, code_end = symbols['dll_code_start'], symbols['dll_code_end']
    original = bytes(cpu.mem_read(code_start, code_end - code_start))
    observed = []
    def snapshot(phase, result=None):
        row = {'phase': phase, 'data': bytes(cpu.mem_read(symbols['dll_data_start'], 64)),
               'constant': cpu.mem_read(symbols['dll_report_constant_immediate'], 1)[0]}
        if result is not None:
            row['report_return'] = result
        observed.append(row)
    def call(function, reason):
        cpu.mem_write(stack, boundary.to_bytes(8, 'little'))
        cpu.reg_write(reg.UC_X86_REG_RSP, stack)
        cpu.reg_write(reg.UC_X86_REG_RCX, dll.imagebase)
        cpu.reg_write(reg.UC_X86_REG_RDX, reason)
        cpu.reg_write(reg.UC_X86_REG_R8, 0)
        cpu.reg_write(reg.UC_X86_REG_RBX, 0xaabbccddeeff0011)
        cpu.emu_start(symbols[function], boundary + 1, count=256)
        assert cpu.reg_read(reg.UC_X86_REG_RSP) == stack + 8
        assert cpu.reg_read(reg.UC_X86_REG_RBX) == 0xaabbccddeeff0011
        return cpu.reg_read(reg.UC_X86_REG_RAX)
    snapshot('before-tls')
    call('dll_tls_callback', 1)
    snapshot('tls-attached')
    assert call('dll_entry', 1) == 1
    snapshot('dll-attached')
    for reason in (2, 3):
        before = bytes(cpu.mem_read(symbols['dll_data_start'], 64))
        call('dll_tls_callback', reason)
        assert call('dll_entry', reason) == 1
        assert bytes(cpu.mem_read(symbols['dll_data_start'], 64)) == before
    snapshot('exe-entry')
    snapshot('reported', call('dll_report', 0))
    for name in detach:
        call('dll_tls_callback' if name == 'tls' else 'dll_entry', 0)
        snapshot('detached')
    assert verify_loader_observations(observed, exit_code=7)['status'] == 'source_milestones_verified'
    final = bytes(cpu.mem_read(code_start, code_end - code_start))
    assert [(k, a, b) for k, (a, b) in enumerate(zip(original, final, strict=True)) if a != b] == [
        (symbols['dll_report_constant_immediate'] - code_start, 1, 3)]
