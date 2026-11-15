"""Guest helper ABI checks; actual DOS execution belongs to the native lane."""
from pathlib import Path
import os
import shutil
import struct
import subprocess

import pytest

from fdisbull import dos_process_helper as helper


NONCE = bytes(range(16))


@pytest.fixture
def nasm():
    selected = os.environ.get('FDISBULL_NASM') or shutil.which('nasm')
    if not selected:
        if os.environ.get('FDISBULL_REQUIRE_DOS_HELPER_ASSEMBLY') == '1':
            pytest.fail('The required DOS helper assembly check needs FDISBULL_NASM')
        pytest.skip('Set FDISBULL_NASM to compare the authored source and template')
    executable = Path(selected).resolve(strict=True)
    assert executable.is_file() and os.access(executable, os.X_OK)
    return executable


def assemble(tmp_path, nasm, *, target=None, tail=None, nonce=None):
    source = Path(helper.__file__).with_name('dos_guest') / 'process_loader.asm'
    destination = tmp_path / 'helper.com'
    command = [str(nasm), '-f', 'bin', str(source), '-o', str(destination)]
    if target is not None:
        command.append('-DFDB_TARGET="' + target + '"')
    if tail:
        command.append('-DFDB_COMMAND_TAIL=' + ','.join(str(byte) for byte in tail))
    if nonce is not None:
        command.append('-DFDB_NONCE_BYTES=' + ','.join(str(byte) for byte in nonce))
    subprocess.run(command, check=True, capture_output=True, timeout=15)
    return destination.read_bytes()


def test_embedded_template_is_exactly_the_readable_authored_program(tmp_path, nasm):
    assert assemble(tmp_path, nasm) == helper._LOADER_TEMPLATE


@pytest.mark.parametrize('target,tail', [
    ('PROBE.COM', b''),
    ('A:\\PROBE.EXE', b' ALPHA.TXT BRAVO.BIN /Q'),
    ('Z:\\ABCDEFGH.XYZ', b' ' + b'\x82' * 125),
])
def test_requested_inputs_match_an_independent_assembly(tmp_path, nasm, target, tail):
    # NASM emits lengths, terminators and field placement independently of the
    # Python builder. The boundary case is 126 CP437 bytes, not UTF-8 text.
    expected = assemble(tmp_path, nasm, target=target, tail=tail, nonce=NONCE)
    assert helper.build_loader(target, tail, NONCE) == expected


@pytest.mark.parametrize('target', [
    '', None, '../BAD.COM', 'A:\\SUB\\BAD.COM', 'A:BAD.COM', '\\BAD.COM',
    '/BAD.COM', 'TOOLONG99.COM', 'BAD.TOOL', 'BAD..COM', 'BAD COM', '*.COM',
    'NUL.COM', 'COM1.EXE', 'A:\\CON', 'CLOCK$.EXE', '\u00c5.COM',
])
def test_builder_refuses_paths_and_dos_device_aliases(target):
    with pytest.raises(ValueError, match='root 8.3'):
        helper.build_loader(target, b'', NONCE)


@pytest.mark.parametrize('tail', [b'x' * 127, b'a\0b', b'a\rb', b'a\nb', 'text', None])
def test_builder_refuses_unrepresentable_command_tails(tail):
    with pytest.raises(ValueError, match='command tail'):
        helper.build_loader('PROBE.COM', tail, NONCE)


@pytest.mark.parametrize('nonce', [b'', b'a' * 15, b'a' * 17, 'a' * 16])
def test_builder_requires_an_exact_launch_nonce(nonce):
    with pytest.raises(ValueError, match='16-byte nonce'):
        helper.build_loader('PROBE.COM', b'', nonce)


def report(record_type=helper.READY, result=0):
    # Start with the assembled program's static ABI pointers, then supply an
    # independently chosen observation: an MZ entry separate from its PSP.
    frame = bytearray(helper.build_loader('PROBE.EXE', b'', NONCE)[4:100])
    frame[5] = record_type
    for offset, value in {
        24: 0x2000, 26: 0x2100, 28: 0x2120, 30: 0x0030,
        32: 0x2140, 34: 0xfff0, 36: 0xff00, 46: result,
        48: 0x0a07, 50: 0xfd, 52: 0x2000, 54: 0x0202,
        56: 0xffee, 66: 0x0090, 68: 0x0026, 70: 0x0070,
    }.items():
        struct.pack_into('<H', frame, offset, value)
    return frame


def test_ready_report_keeps_psp_entry_and_stack_identities_distinct():
    observed = helper.parse_report(bytes(report()), NONCE)
    assert observed['type'] == 'ready'
    assert observed['helper_segment'] == observed['helper_psp'] == 0x2000
    assert observed['child_psp'] == 0x2100
    assert (observed['entry_cs'], observed['entry_ip']) == (0x2120, 0x0030)
    assert (observed['stack_ss'], observed['stack_sp']) == (0x2140, 0xfff0)
    assert observed['raw_stack_sp'] == 0xffee and observed['initial_ax'] == 0xff00
    assert (observed['dos_major'], observed['dos_minor'], observed['dos_oem']) == (7, 10, 0xfd)
    assert observed['first_mcb_segment'] == 0x90
    assert (observed['list_of_lists_segment'], observed['list_of_lists_offset']) == (0x70, 0x26)
    assert 'resident' not in observed and 'exit_code' not in observed


@pytest.mark.parametrize('result,termination,resident', [
    (0x0025, 'normal', False),
    (0x0125, 'control_c', False),
    (0x0225, 'critical_error', False),
    (0x0325, 'resident', True),
    (0x0300, 'resident', True),
    (0x0725, 'unknown', False),
])
def test_complete_dos_return_is_retained_without_guessing_instruction(result, termination, resident):
    observed = helper.parse_report(bytes(report(helper.TERMINATED, result)), NONCE)
    assert observed['type'] == 'terminated'
    assert observed['dos_result'] == result
    assert observed['exit_code'] == result & 255
    assert observed['termination_type'] == result >> 8
    assert observed['termination'] == termination
    assert observed['resident'] is resident
    assert observed['termination_instruction'] == 'not_observed'


@pytest.mark.parametrize('stage,name', [
    (1, 'helper_resize'), (2, 'select_drive'), (3, 'root_directory'), (4, 'exec'),
])
def test_preparation_or_exec_failure_never_becomes_child_termination(stage, name):
    frame = report(helper.ERROR, 8)
    struct.pack_into('<H', frame, 26, 0)
    struct.pack_into('<H', frame, 54, 0x0203)
    struct.pack_into('<H', frame, 72, stage)
    observed = helper.parse_report(bytes(frame), NONCE)
    assert observed['type'] == 'error' and observed['error_code'] == 8
    assert observed['error_stage'] == name
    assert 'resident' not in observed and 'exit_code' not in observed


def test_report_nonce_prevents_reusing_a_previous_launch_record():
    with pytest.raises(ValueError, match='different launch nonce'):
        helper.parse_report(bytes(report()), b'\xff' * 16)


@pytest.mark.parametrize('data', [b'', b'FDBP', bytes(95), bytes(97)])
def test_report_decoder_requires_one_complete_frame(data):
    with pytest.raises(ValueError, match='complete 96-byte'):
        helper.parse_report(data, NONCE)


@pytest.mark.parametrize('offset,value,message', [
    (0, 0, 'header'),
    (4, 2, 'header'),
    (5, 4, 'report type'),
    (6, 95, 'header'),
    (74, 1, 'reserved'),
    (38, 0, 'helper layout'),
    (52, 1, 'helper PSP'),
    (50, 0x100, 'OEM'),
    (26, 0, 'loaded child'),
    (54, 0x0203, 'loaded child'),
    (56, 0xfff0, 'AX stack word'),
    (72, 4, 'loaded child'),
])
def test_report_decoder_refuses_corrupt_or_inconsistent_observations(offset, value, message):
    frame = report()
    if offset in (0, 4, 5, 74):
        frame[offset] = value
    else:
        struct.pack_into('<H', frame, offset, value)
    with pytest.raises(ValueError, match=message):
        helper.parse_report(bytes(frame), NONCE)


def test_stack_word_correction_can_wrap_a_16_bit_stack_pointer():
    frame = report()
    struct.pack_into('<H', frame, 56, 0xfffe)
    struct.pack_into('<H', frame, 34, 0)
    assert helper.parse_report(bytes(frame), NONCE)['stack_sp'] == 0
