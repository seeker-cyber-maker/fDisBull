"""Authored records and actual helper opcodes; no original QEMM execution."""
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

import pytest

from fdisbull.qpi import REPORT_SIZE, parse_qpi_report, probe_bytes, write_qpi_probe


def authored_report(*, enabled=0, status=0, count=272):
    data = bytearray(REPORT_SIZE)
    data[:8] = b'FDQPI001'
    flags = {0: 31, 1: 0, 2: 0, 3: 0, 4: 1, 5: 3, 6: 7, 7: 15, 8: 0}[status]
    struct.pack_into('<6H', data, 8, REPORT_SIZE, status, 0x0902, 0x0902, 0x100, 0x9000)
    data[20:22] = bytes([enabled, ord('M')])
    struct.pack_into('<2H', data, 22, count, flags)
    for page in range(count):
        physical = 0x200000 if page in (0xa0, 0xb0) else page << 12
        struct.pack_into('<I', data, 32 + page * 4, physical | 7)
    return bytes(data)


def test_report_preserves_bcd_pte_bits_and_aliases():
    result = parse_qpi_report(authored_report(), include_pages=True)
    assert result['qemm']['version'] == '9.02'
    assert result['qemm']['active'] is True
    assert result['qemm']['stealth_mode'] == 'M'
    assert result['mappings']['complete'] is True
    assert result['mappings']['pages'][0]['pte_user'] is True
    assert result['mappings']['pages'][0]['raw_pte'] == '0x00000007'
    assert result['mappings']['aliases'] == [dict(physical_start=0x200000, linear_starts=[0xa0000, 0xb0000])]
    assert result['native_execution_validation'] == 'not_established_by_report'
    assert 'pages' not in parse_qpi_report(authored_report())['mappings']


def test_disabled_and_partial_evidence_do_not_become_complete_active_runs():
    assert parse_qpi_report(authored_report(enabled=3))['qemm']['active'] is False
    partial = parse_qpi_report(authored_report(status=7, count=19))
    assert partial['probe_status']['name'] == 'pte-call-failed'
    assert partial['mappings']['complete'] is False
    assert partial['qemm']['active'] is True  # The earlier GetStatus succeeded.
    absent = parse_qpi_report(authored_report(status=1, count=0))
    assert absent['qemm']['active'] is None and absent['qemm']['version'] is None


def test_getinfo_disk_fields_are_version_qualified():
    data = bytearray(authored_report())
    struct.pack_into('<2H', data, 12, 0x0600, 0x0600)
    data[27:29] = b'\x80\xff'  # Undefined scratch registers in QEMM 6.x.
    report = parse_qpi_report(bytes(data))['qemm']
    assert report['version'] == '6.00'
    assert report['disk_buffer_kib'] is None and report['disk_buffer_flags_raw'] is None
    assert report['raw_info']['dl'] == 128 and report['raw_info']['bh'] == 255


@pytest.mark.parametrize('offset,value', [(0, b'wrong'), (8, b'\x00\x00'), (10, b'\xff\xff'),
    (12, b'\x03\x09'), (14, b'\xaa\x09'), (20, b'\x04'), (22, b'\x0f\x01'),
    (24, b'\xff\xff'), (29, b'\x01')])
def test_inconsistent_reports_refuse(offset, value):
    data = bytearray(authored_report())
    data[offset:offset + len(value)] = value
    with pytest.raises(ValueError):
        parse_qpi_report(bytes(data))


def test_report_limits_and_probe_export_do_not_clobber(tmp_path):
    with pytest.raises(ValueError):
        parse_qpi_report(authored_report() + b'X')
    with pytest.raises(ValueError):
        parse_qpi_report(authored_report(), include_pages=1)
    destination = tmp_path / 'FDQPI.COM'
    result = write_qpi_probe(destination)
    assert result['execution'] == 'not_run' and result['written'] is True
    assert write_qpi_probe(destination)['written'] is False
    before = destination.read_bytes()
    with pytest.raises(ValueError, match='different bytes'):
        write_qpi_probe(destination, mode='file')
    assert destination.read_bytes() == before


def test_packaged_helper_reproduces_with_binutils(tmp_path):
    if not all(shutil.which(name) for name in ('as', 'ld', 'objcopy', 'nm')):
        pytest.skip('GNU binutils not installed; packaged-byte checks run separately')
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / 'rebuilt.json'
    subprocess.run([sys.executable, str(root / 'scripts/build_qpi_probe.py'), '--output', str(output)],
                   check=True, timeout=45, capture_output=True)
    assert json.loads(output.read_text()) == json.loads((root / 'src/fdisbull/data/qpi-probe.json').read_text())


def run_probe(*, mode='breakpoint', fail=None, enabled=0, short_write=False, release=False):
    """Unicorn executes the assembled 386 instructions; DOS/QPI are test doubles.

    This tests stack/segment/register preservation and the IOCTL/call protocol,
    not the behavior or compatibility of a native QEMM installation.
    """
    unicorn = pytest.importorskip('unicorn')
    from unicorn import x86_const as reg
    uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_16)
    uc.mem_map(0, 0x200000)
    segment, entry_segment, entry_offset = 0x1000, 0x9000, 0x100
    base, entry = segment << 4, (entry_segment << 4) + entry_offset
    program, asset = probe_bytes(mode=mode)
    uc.mem_write(base + 0x100, program)
    uc.mem_write(entry, b'\xcb')  # QPI test double returns through the real far stack.
    for name in ('CS', 'DS', 'ES', 'SS'):
        uc.reg_write(getattr(reg, 'UC_X86_REG_' + name), segment)
    uc.reg_write(reg.UC_X86_REG_SP, 0xfffe)
    evidence = dict(calls=[], dos=[], report=None, exit=None)

    def read(name):
        return uc.reg_read(getattr(reg, 'UC_X86_REG_' + name))

    def write(name, value):
        uc.reg_write(getattr(reg, 'UC_X86_REG_' + name), value)

    def carry(value):
        write('EFLAGS', (read('EFLAGS') & ~1) | int(value))

    def qpi(machine, address, size, user):
        if mode == 'breakpoint' and address == base + asset['ready_com_offset']:
            assert read('CX') == REPORT_SIZE
            evidence['report'] = bytes(uc.mem_read((read('ES') << 4) + read('DI'), REPORT_SIZE))
            if release:
                uc.mem_write(base + asset['release_com_offset'], b'\x01')
            else:
                uc.emu_stop()
            return
        if address != entry:
            return
        ax, cx = read('AX'), read('CX')
        evidence['calls'].append((ax, cx))
        selector = {0x0300: 'version', 0: 'status', 0x1e00: 'info', 0x1f00: 'pte'}[ax]
        carry(fail == selector or fail == ('pte', cx))
        if not read('EFLAGS') & 1:
            if selector == 'version':
                write('AX', 0x0902)
                write('BX', 0x0902)
            elif selector == 'status':
                write('AX', enabled)
            elif selector == 'info':
                write('CX', 0x2f4d)
                write('DX', 16)
                write('BX', 0x0300)
            else:
                write('EDX', (cx << 12) | 7)
                write('BX', 0xdead)
                write('CX', 0xbeef)
        # Documented scratch registers must not redirect the helper's stores.
        write('DS', 0x5555)
        write('ES', 0x6666)
        write('SI', 0x1111)
        write('DI', 0x2222)

    def interrupt(machine, vector, user):
        assert vector == 0x21
        ax, ah = read('AX'), read('AX') >> 8
        evidence['dos'].append(ax)
        carry(False)
        if ax == 0x3d00:
            assert bytes(uc.mem_read((read('DS') << 4) + read('DX'), 9)) == b'QEMM386$\0'
            carry(fail == 'open')
            write('AX', 5)
        elif ax == 0x4402:
            assert read('BX') == 5 and read('CX') == 4
            pointer = b'\0' * 4 if fail == 'null' else struct.pack('<HH', entry_offset, entry_segment)
            uc.mem_write((read('DS') << 4) + read('DX'), pointer)
            carry(fail == 'ioctl')
            write('AX', 2 if fail == 'short' else 4)
        elif ah == 0x3e:
            # Deliberately destroy AX/CF: the helper must retain the preceding
            # IOCTL/write result across CloseHandle.
            carry(read('BX') == 5 or fail == 'close')
            write('AX', 0xffff)
        elif ax == 0x3c00:
            assert bytes(uc.mem_read((read('DS') << 4) + read('DX'), 10)) == b'FDQPI.BIN\0'
            write('AX', 6)
        elif ah == 0x40:
            assert read('BX') == 6 and read('CX') == REPORT_SIZE
            evidence['report'] = bytes(uc.mem_read((read('DS') << 4) + read('DX'), REPORT_SIZE))
            carry(fail == 'write')
            write('AX', REPORT_SIZE - int(short_write))
        elif ah == 0x4c:
            evidence['exit'] = ax & 255
            uc.emu_stop()
        else:
            raise AssertionError(f'unexpected DOS call {ax:04x}')

    uc.hook_add(unicorn.UC_HOOK_CODE, qpi)
    uc.hook_add(unicorn.UC_HOOK_INTR, interrupt)
    uc.emu_start(base + 0x100, base + 0x100 + len(program), count=30000)
    assert evidence['report'] is not None, 'helper did not reach its bounded output'
    evidence['decoded'] = parse_qpi_report(evidence['report'], include_pages=True)
    return evidence


@pytest.mark.parametrize('mode', ['breakpoint', 'file'])
def test_authored_machine_code_uses_documented_read_only_protocol(mode):
    result = run_probe(mode=mode)
    assert len(result['calls']) == 275
    assert [call[0] for call in result['calls'][:3]] == [0x0300, 0, 0x1e00]
    assert [call[1] for call in result['calls'][3:]] == list(range(272))
    assert result['decoded']['probe_status']['complete'] is True
    assert result['decoded']['qemm']['version'] == '9.02'
    assert result['decoded']['mappings']['pages'][-1]['raw_pte'] == '0x0010f007'
    assert result['exit'] == (0 if mode == 'file' else None)


@pytest.mark.parametrize('failure,status,count', [
    ('open', 1, 0), ('ioctl', 2, 0), ('short', 3, 0), ('version', 4, 0),
    ('status', 5, 0), ('info', 6, 0), (('pte', 19), 7, 19), ('null', 8, 0)])
def test_authored_probe_failure_paths_preserve_partial_evidence(failure, status, count):
    result = run_probe(fail=failure)
    assert result['decoded']['probe_status']['code'] == status
    assert result['decoded']['mappings']['captured_pages'] == count
    assert result['decoded']['probe_status']['complete'] is False


def test_authored_probe_off_state_and_short_file_write():
    assert run_probe(enabled=2)['decoded']['qemm']['active'] is False
    assert run_probe(mode='file', short_write=True)['exit'] == 2
    assert run_probe(mode='file', fail='write')['exit'] == 2
    assert run_probe(mode='file', fail='close')['exit'] == 2
    assert run_probe(release=True)['exit'] == 0
