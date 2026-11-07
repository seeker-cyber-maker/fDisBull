"""Authored DESQview companion opcodes against explicit interrupt test doubles.

These tests execute the packaged helper in Unicorn. They qualify its protocol,
register handling and bounded control flow, not an original DESQview kernel or
a native DESQview/QEMM boot. The payload contains no third-party instructions.
"""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

import pytest

from fdisbull import desqview


def run_probe(*, version=0x022A, present=True, yields=3, mode='breakpoint',
              release=False, file_error=None, screen_type=0, poison=True):
    """Execute real helper instructions; only external interrupt services are doubles."""
    unicorn = pytest.importorskip('unicorn')
    from unicorn import x86_const as reg
    program, asset = desqview.probe_bytes(mode=mode, yields=yields,
        nonce='0123456789abcdeffedcba9876543210')
    machine = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_16)
    machine.mem_map(0, 0x200000)
    segment, base = 0x1000, 0x10000
    machine.mem_write(base + 0x100, program)
    for name in ('CS', 'SS', 'DS', 'ES'):
        machine.reg_write(getattr(reg, 'UC_X86_REG_' + name), segment)
    machine.reg_write(reg.UC_X86_REG_SP, 0xfffe)
    machine.reg_write(reg.UC_X86_REG_EFLAGS, 0x202)
    ticks = 0x123456
    machine.mem_write(0x46c, struct.pack('<I', ticks))
    report_address = base + asset['report_com_offset']
    ready_address = base + asset['ready_com_offset']
    data_start = base + 0x100 + program.index(b'FDVAPI.BIN\0')
    evidence = dict(calls=[], dos=[], report=None, exit_code=None, ready=False,
                    critical=0, pauses=0, written=None, instructions=0,
                    code_stop=None, file_error=file_error)

    def read(name):
        return machine.reg_read(getattr(reg, 'UC_X86_REG_' + name))

    def write(name, value):
        machine.reg_write(getattr(reg, 'UC_X86_REG_' + name), value)

    def carry(value):
        write('EFLAGS', (read('EFLAGS') & ~1) | int(value))

    def scratch():
        if not poison:
            return
        # Never corrupt CS/SS/SP, which are part of the external return ABI.
        # General and data-segment values are deliberately unrelated to the
        # helper's own segment, counts, output offsets and previously seen AX.
        for index, name in enumerate(('AX', 'BX', 'CX', 'DX', 'SI', 'DI', 'BP', 'DS', 'ES')):
            write(name, 0x5000 + 0x111 * index)
        write('EFLAGS', 0x603)  # IF/DF/CF set; no trap flag.

    def code(_machine, address, size, _user):
        evidence['instructions'] += 1
        assert base + 0x100 <= address < data_start, 'helper escaped its instruction extent'
        if address != ready_address:
            return
        assert mode == 'breakpoint' and evidence['critical'] == 0
        assert read('DS') == segment and read('ES') == segment
        assert read('DI') == asset['report_com_offset'] and read('CX') == 64
        evidence.update(report=bytes(machine.mem_read(report_address, 64)), ready=True, code_stop=address)
        if release:
            machine.mem_write(base + asset['release_com_offset'], b'\1')
        else:
            machine.emu_stop()

    def interrupt(_machine, vector, _user):
        ax, bx, cx, dx = read('AX'), read('BX'), read('CX'), read('DX')
        if vector == 0x15:
            assert present and version >> 8 >= 2
            evidence['calls'].append(dict(ax=ax, bx=bx, critical=evidence['critical']))
            if ax == 0x1000:
                assert evidence['critical'] == 0, 'PAUSE occurred inside a critical section'
                evidence['pauses'] += 1
                machine.mem_write(0x46c, struct.pack('<I', ticks + 7 * evidence['pauses']))
                scratch()
            elif ax == 0x101b:
                assert evidence['critical'] == 0
                evidence['critical'] += 1
                scratch()
            elif ax in (0x1117, 0xde17):
                assert evidence['critical'] == 1 and bx == 0, 'helper requested a mapping change'
                expected = 0x1117 if 0x0214 <= version < 0x021a else 0xde17
                assert version >= 0x0214 and ax == expected
                scratch()
                write('AX', 0)
                write('BX', 0xbeef)
            elif ax == 0xde07:
                assert evidence['critical'] == 1
                scratch()
                write('AX', 0x42)
            elif ax == 0x1024:
                assert evidence['critical'] == 1 and bx == 0
                scratch()
                write('ES', 0x9000)
                write('DI', 0x0321)
                write('CX', 4000)
                write('DX', 0xab00 | screen_type)
            elif ax == 0x101c:
                assert evidence['critical'] == 1
                evidence['critical'] -= 1
                scratch()
            else:
                raise AssertionError(f'unexpected DESQview selector {ax:04x}')
            return
        assert vector == 0x21
        assert evidence['critical'] == 0, 'DOS I/O occurred inside a critical section'
        evidence['dos'].append(ax)
        if ax == 0x2b01:
            assert cx == 0x4445 and dx == 0x5351
            scratch()
            write('AX', 0xa500 if present else 0xa5ff)
            write('BX', version if present else 0xffff)
            return
        ah = ax >> 8
        if ah == 0x3c:
            assert mode == 'file' and cx == 0
            assert bytes(machine.mem_read((read('DS') << 4) + dx, 11)) == b'FDVAPI.BIN\0'
            carry(file_error == 'create')
            write('AX', 5 if file_error == 'create' else 0x14)
        elif ah == 0x40:
            assert bx == 0x14 and cx == 64 and (read('DS') << 4) + dx == report_address
            payload = bytes(machine.mem_read(report_address, 64))
            evidence['report'] = payload
            count = 0 if file_error == 'write' else 63 if file_error == 'short-write' else 64
            evidence['written'] = payload[:count]
            carry(file_error == 'write')
            write('AX', 5 if file_error == 'write' else count)
        elif ah == 0x3e:
            assert bx == 0x14
            # Success in AX must not erase an earlier short/error write; and
            # failure in carry must still be observed after a full write.
            carry(file_error == 'close')
            write('AX', 0xdead)
        elif ah == 0x4c:
            evidence['exit_code'] = ax & 255
            evidence['code_stop'] = (read('CS') << 4) + read('IP')
            machine.emu_stop()
        else:
            raise AssertionError(f'unexpected DOS selector {ax:04x}')

    def memory_read(_machine, access, address, size, value, _user):
        if address in (0x46c, 0x46e):
            # The two 16-bit loads must be one interrupt-masked observation;
            # otherwise a BIOS-tick carry can tear the reported 32-bit value.
            assert size == 2 and not read('EFLAGS') & 0x200

    machine.hook_add(unicorn.UC_HOOK_CODE, code)
    machine.hook_add(unicorn.UC_HOOK_INTR, interrupt)
    machine.hook_add(unicorn.UC_HOOK_MEM_READ, memory_read)
    machine.emu_start(base + 0x100, base + 0x100 + len(program), timeout=2_000_000, count=100_000)
    assert evidence['ready'] or evidence['exit_code'] is not None, 'helper did not reach its declared endpoint'
    evidence['asset'] = asset
    evidence['report_in_memory'] = bytes(machine.mem_read(report_address, 64))
    evidence['stack_pointer'] = read('SP')
    return evidence


@pytest.mark.parametrize('version, expected_selector, version_text', [
    (0x0213, None, '2.19'), (0x0214, '0x1117', '2.20'),
    (0x0219, '0x1117', '2.25'), (0x021a, '0xde17', '2.26'),
    (0x022a, '0xde17', '2.42'), (0x0250, '0xde17', '2.80'),
    (0x0247, '0xde17', '2.71'),
])
def test_packaged_helper_opcodes_gate_version_and_cooperate_without_dos_in_critical(version, expected_selector, version_text):
    result = run_probe(version=version)
    report = desqview.parse_report(result['report'])
    selectors = [call['ax'] for call in result['calls']]
    expected = [0x1000] * 3 + [0x101b]
    if expected_selector is not None:
        expected.append(int(expected_selector, 0))
    expected.extend([0xde07, 0x1024, 0x101c])
    assert selectors == expected
    assert result['critical'] == 0 and result['stack_pointer'] == 0xfffe
    assert result['dos'] == [0x2b01] and result['exit_code'] is None
    assert report['desqview']['kernel_version'] == version_text
    assert report['desqview']['product_version'] == 'not_inferred'
    assert report['mapping']['selector'] == expected_selector and report['mapping']['changed'] is False
    assert report['mapping']['handle'] == ('0xbeef' if expected_selector else None)
    assert report['application']['number'] == 0x42
    assert report['screen']['segment'] == '0x9000' and report['screen']['offset'] == '0x321'
    assert report['screen']['linear_address'] == '0x90321' and report['screen']['length'] == 4000
    assert report['screen']['kind'] == 'text'
    assert report['cooperation']['returned_yields'] == 3 and report['cooperation']['critical_balance'] == 0
    assert report['ticks'] == {'before': 0x123456, 'after': 0x123456 + 21}
    assert report['nonce'] == '0123456789abcdeffedcba9876543210'
    assert report['native_execution_validation'] == 'not_established_by_report'


@pytest.mark.parametrize('present,version,status', [(False, 0x0250, 'absent'), (True, 0x0163, 'unsupported-kernel')])
def test_absent_or_unsupported_guard_never_calls_int15(present, version, status):
    result = run_probe(present=present, version=version, yields=17)
    report = desqview.parse_report(result['report'])
    assert result['calls'] == [] and result['pauses'] == 0 and result['critical'] == 0
    assert report['status'] == status and report['cooperation']['returned_yields'] == 0
    assert report['cooperation']['requested_yields'] == 17
    assert report['mapping']['queried'] is False and report['application']['number'] is None
    assert report['ticks'] == {'before': 0, 'after': 0}
    assert report['desqview']['kernel_version'] == ('1.99' if present else None)


@pytest.mark.parametrize('yields', [0, 4096])
def test_yield_limits_and_release_endpoint_execute_with_poisoned_registers(yields):
    result = run_probe(yields=yields, release=True)
    assert result['pauses'] == yields and result['critical'] == 0
    assert result['ready'] is True and result['exit_code'] == 0
    assert desqview.parse_report(result['report'])['cooperation']['returned_yields'] == yields
    assert result['report_in_memory'] == result['report']
    assert result['instructions'] < 100_000 and result['stack_pointer'] == 0xfffe


@pytest.mark.parametrize('screen_type,expected', [(0, 'text'), (1, 'graphics')])
def test_getbuf_captures_es_di_cx_and_low_dl_without_reusing_scratch_registers(screen_type, expected):
    result = run_probe(screen_type=screen_type, yields=0)
    screen = desqview.parse_report(result['report'])['screen']
    assert screen['kind'] == expected and screen['length'] == 4000
    assert screen['segment'] == '0x9000' and screen['offset'] == '0x321'


def test_scratch_register_poisoning_does_not_change_the_report():
    ordinary = run_probe(poison=False)
    poisoned = run_probe(poison=True)
    assert ordinary['report'] == poisoned['report']
    assert ordinary['stack_pointer'] == poisoned['stack_pointer'] == 0xfffe


@pytest.mark.parametrize('error,expected_exit,expected_dos', [
    (None, 0, [0x2b, 0x3c, 0x40, 0x3e, 0x4c]),
    ('create', 3, [0x2b, 0x3c, 0x4c]),
    ('write', 3, [0x2b, 0x3c, 0x40, 0x3e, 0x4c]),
    ('short-write', 3, [0x2b, 0x3c, 0x40, 0x3e, 0x4c]),
    ('close', 3, [0x2b, 0x3c, 0x40, 0x3e, 0x4c]),
])
def test_file_mode_requires_create_full_write_and_successful_close(error, expected_exit, expected_dos):
    result = run_probe(mode='file', file_error=error)
    assert result['exit_code'] == expected_exit and result['ready'] is False
    assert [ax >> 8 for ax in result['dos']] == expected_dos
    assert result['critical'] == 0
    if error is None:
        assert result['written'] == result['report_in_memory']
        assert desqview.parse_report(result['written'])['status'] == 'complete'
    elif error == 'short-write':
        assert len(result['written']) == 63


def test_file_mode_also_records_absence_without_making_a_desqview_call():
    result = run_probe(present=False, mode='file')
    assert result['exit_code'] == 0 and result['calls'] == []
    assert desqview.parse_report(result['written'])['status'] == 'absent'


def test_companion_bytes_reproduce_from_authored_assembly(tmp_path):
    if not all(shutil.which(name) for name in ('as', 'ld', 'objcopy', 'nm')):
        pytest.skip('GNU binutils unavailable; packaged helper still executes in other tests')
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / 'probe.json'
    subprocess.run([sys.executable, str(root / 'scripts/build_desqview_probe.py'), '--output', str(output)],
                   check=True, timeout=45, capture_output=True)
    expected = json.loads((root / 'src/fdisbull/data/desqview-probe.json').read_text())
    assert json.loads(output.read_text()) == expected


def test_actual_instruction_facilities_fit_the_exported_286_contract(tmp_path):
    import iced_x86 as ix
    program, _ = desqview.probe_bytes(mode='breakpoint')
    end = program.index(b'FDVAPI.BIN\0')
    decoded = list(ix.Decoder(16, program[:end], ip=0x100))
    assert decoded and sum(ins.len for ins in decoded) == end
    # The helper currently needs only 8086 facilities. In particular, GAS jump
    # relaxation must not introduce 0F 8x near Jcc instructions (386+) merely
    # because a branch to an absent/unsupported handler grew beyond 127 bytes.
    assert all(not ins.is_invalid and ins.cpuid_features() == [ix.CpuidFeature.INTEL8086] for ins in decoded)
    assert desqview.write_probe(tmp_path / 'DVPROBE.COM')['minimum_cpu'] == '80286'


@pytest.fixture(scope='module')
def complete_report():
    return run_probe()['report']


@pytest.mark.parametrize('offset,data', [
    (0, b'bad'), (8, b'\x3f\0'), (10, b'\x03\0'), (12, b'\x19\x02'),
    (14, b'\xff'), (15, b'\1'), (16, b'\x17\x11'), (20, b'\0\1'),
    (28, b'\2'), (29, b'\1'), (30, b'\1\x10'), (32, b'\4\0'),
    (32, b'\2\0'), (34, b'\x3d\0'), (60, b'\1\0'), (62, b'\1'), (63, b'\1'),
])
def test_malformed_report_fields_do_not_claim_completed_cooperation(complete_report, offset, data):
    altered = bytearray(complete_report)
    altered[offset:offset + len(data)] = data
    with pytest.raises(ValueError):
        desqview.parse_report(bytes(altered))


def test_report_type_and_exact_extent_are_required(complete_report):
    for data in (complete_report[:-1], complete_report + b'\0', bytearray(complete_report), None):
        with pytest.raises(ValueError):
            desqview.parse_report(data)


def test_pre_assertmap_kernel_cannot_claim_mapping_result():
    altered = bytearray(run_probe(version=0x0213)['report'])
    struct.pack_into('<H', altered, 18, 0xbeef)
    with pytest.raises(ValueError, match='mapping'):
        desqview.parse_report(bytes(altered))


@pytest.mark.parametrize('present,version', [(False, 0x0250), (True, 0x0163)])
def test_unexecuted_ticks_are_zero_for_absent_and_unsupported_reports(present, version):
    altered = bytearray(run_probe(present=present, version=version)['report'])
    struct.pack_into('<I', altered, 52, 1)
    with pytest.raises(ValueError):
        desqview.parse_report(bytes(altered))


@pytest.mark.parametrize('options', [
    {'mode': 'wrong'}, {'yields': -1}, {'yields': 4097}, {'yields': True},
    {'yields': 1.5}, {'nonce': '00' * 15}, {'nonce': 'GG' * 16}, {'nonce': bytes(16)},
])
def test_invalid_probe_configuration_refuses(options):
    with pytest.raises(ValueError):
        desqview.probe_bytes(**options)


def test_export_is_idempotent_for_identical_bytes_and_does_not_clobber(tmp_path):
    output = tmp_path / 'DVPROBE.COM'
    result = desqview.write_probe(output, yields=2, nonce='12' * 16)
    saved = output.read_bytes()
    assert result['written'] is True and result['execution'] == 'not_run'
    assert hashlib.sha256(saved).hexdigest() == result['sha256']
    assert desqview.write_probe(output, yields=2, nonce='12' * 16)['written'] is False
    with pytest.raises(ValueError, match='different bytes'):
        desqview.write_probe(output, yields=3, nonce='12' * 16)
    assert output.read_bytes() == saved


@pytest.mark.parametrize('field,value', [
    ('report_length', 63), ('ready_com_offset', 0x10000),
    ('release_com_offset', 0x10000), ('mode_file_offset', True),
])
def test_packaged_endpoint_metadata_is_bounded_even_when_program_hash_matches(tmp_path, monkeypatch, field, value):
    source_root = Path(__file__).resolve().parents[1] / 'src/fdisbull/data'
    destination = tmp_path / 'data'
    destination.mkdir()
    asset = json.loads((source_root / 'desqview-probe.json').read_text())
    asset[field] = value
    (destination / 'desqview-probe.json').write_text(json.dumps(asset))
    (destination / 'FdisbullDesqviewProbe.txt').write_bytes((source_root / 'FdisbullDesqviewProbe.txt').read_bytes())
    monkeypatch.setattr(desqview, 'files', lambda _package: tmp_path)
    with pytest.raises(ValueError):
        desqview.probe_bytes()


def test_service_descriptions_require_the_full_installation_signature_and_version_selector():
    installation = dict(ax=0x2b01, cx=0x4445, dx=0x5351)
    result = desqview.describe_interrupt(0x21, installation)
    assert result['name'] == 'installation_check'
    assert result['runtime_observed'] is False and result['handler_verified'] is False
    for key in ('ax', 'cx', 'dx'):
        altered = dict(installation)
        altered[key] ^= 1
        assert desqview.describe_interrupt(0x21, altered) is None
    assert desqview.describe_interrupt(0x15, {'ax': 0x1022}) is None
    assert desqview.describe_interrupt(0x15, {'ax': 0x1022, 'bx': 1}) is None
    assert desqview.describe_interrupt(0x15, {'ax': 0x1022, 'bx': 0})['name'] == 'get_version'
    version = desqview.describe_interrupt(0x15, {'ax': 0x1022, 'bx': 0})
    assert 'TopView compatibility' in version['outputs']['bx']
    assert 'BL=major, BH=minor' in version['outputs']['bx']


def test_service_critical_stack_and_mapping_abis_do_not_conflate_selectors():
    expected = {0x1000: 'pause', 0x101a: 'other_stack', 0x101b: 'begin_critical',
                0x101c: 'end_critical', 0x1024: 'get_virtual_screen', 0x1025: 'user_stack'}
    for selector, name in expected.items():
        assert desqview.describe_interrupt(0x15, {'ax': selector})['name'] == name
    for selector, minimum in [(0x1117, '2.20'), (0xde17, '2.26')]:
        assert desqview.describe_interrupt(0x15, {'ax': selector, 'bx': 0})['mapping_operation'] == 'query'
        assert desqview.describe_interrupt(0x15, {'ax': selector, 'bx': 0xbeef})['mapping_operation'] == 'set'
        unknown = desqview.describe_interrupt(0x15, {'ax': selector})
        assert unknown['mapping_operation'] == 'unknown' and unknown['minimum_version'] == minimum
    assert desqview.describe_interrupt(0x15, {'ax': 0xdead}) is None
    split = desqview.describe_interrupt(0x21, {'ah': 0x2b, 'al': 1, 'ch': 0x44, 'cl': 0x45, 'dh': 0x53, 'dl': 0x51})
    assert split['name'] == 'installation_check'
    assert desqview.describe_interrupt(0x10, {'ah': 0xfe})['name'] == 'virtual_video_address'
    assert desqview.describe_interrupt(0x10, {'ah': 0xff})['name'] == 'video_buffer_update'
    assert all(row['family'] == 'desqview' and not row['handler_verified'] for row in desqview.service_catalog())
