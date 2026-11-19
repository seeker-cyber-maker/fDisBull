from __future__ import annotations

import os
import shutil

import pytest

from support.qemu_sb16_count_fixture import FIELDS, REPORT_SIZE, expected_progress, parse_report, sb16_count


def _dsp_start_command(code, offsets):
    """Decode emitted real-mode AL writes/calls between authored boundaries."""
    from capstone import CS_ARCH_X86, CS_MODE_16, Cs
    raw = code[offsets['ready'] - 256:offsets['started'] - 256]
    instructions = list(Cs(CS_ARCH_X86, CS_MODE_16).disasm(raw, offsets['ready']))
    assert sum(item.size for item in instructions) == len(raw)
    value, command, targets = None, [], set()
    for item in instructions:
        assert item.mnemonic in ('nop', 'mov', 'xor', 'call')
        if item.mnemonic == 'mov' and item.op_str.startswith('al, '):
            value = int(item.op_str.split(', ')[1], 0)
        elif item.mnemonic == 'xor' and item.op_str == 'al, al':
            value = 0
        elif item.mnemonic == 'call':
            assert value is not None
            command.append(value)
            targets.add(item.op_str)
            value = None
    assert len(command) == 4 and len(targets) == 1
    return command


def test_report_keeps_high_dma_word_units_distinct_from_bytes():
    fields = dict(bits=16, channels=2, initial_address=0xa000, initial_count=4095)
    raw = b'SCN1' + b''.join(fields.get(name, 0).to_bytes(width, 'little') for name, width in FIELDS)
    actual = expected_progress(parse_report(raw))
    assert actual == dict(address=0xa400, count=3071, bytes=2048, irq_status=2)
    fields['bits'] = 8
    raw = b'SCN1' + b''.join(fields.get(name, 0).to_bytes(width, 'little') for name, width in FIELDS)
    assert expected_progress(parse_report(raw)) == dict(address=0xa400, count=3071, bytes=1024, irq_status=1)


@pytest.mark.parametrize('raw', [b'', b'SCN1', b'BAD!' + bytes(REPORT_SIZE - 4), b'SCN1' + bytes(REPORT_SIZE)])
def test_report_refuses_truncation_wrong_magic_and_extra_bytes(raw):
    with pytest.raises(ValueError):
        parse_report(raw)


@pytest.mark.parametrize('address,count', [(0xf800, 4095), (0x1000, 2047)])
def test_expected_progress_refuses_ambiguous_wrap_or_wrong_capacity(address, count):
    with pytest.raises(ValueError):
        expected_progress(dict(bits=8, channels=2, initial_address=address, initial_count=count))


@pytest.mark.parametrize('bits,channels,fifo', [(b,c,f) for b in (8,16) for c in (1,2) for f in (False,True)])
def test_assembled_count_guest_has_bounded_report_and_original_allocation(tmp_path, bits, channels, fifo):
    nasm = os.environ.get('NASM') or shutil.which('nasm')
    if not nasm:
        pytest.skip('NASM is needed for authored guest assembly')
    code, offsets = sb16_count(tmp_path, nasm, bits=bits, channels=channels, fifo=fifo)
    assert len(code) < 0xff00
    raw = code[offsets['report'] - 256:offsets['report'] - 256 + REPORT_SIZE]
    report = parse_report(raw)
    assert (report['bits'], report['channels'], report['fifo']) == (bits,channels,int(fifo))
    assert report['initial_count'] == 4095 and report['phase'] == report['failure'] == 0
    assert code[offsets['ready'] - 256] == code[offsets['started'] - 256] == code[offsets['done'] - 256] == 0x90
    assert offsets['arena'] + 16384 <= len(code) + 256


@pytest.mark.parametrize('channels', [1, 2])
def test_known_wave_guest_requests_every_authored_channel_sample(tmp_path, channels):
    from support.qemu_sb16_fixture import DMA_BYTES, sb16_pcm
    nasm = os.environ.get('NASM') or shutil.which('nasm')
    if not nasm:
        pytest.skip('NASM is needed for authored guest assembly')
    code, offsets = sb16_pcm(tmp_path, nasm, channels=channels)
    command, mode, low, high = _dsp_start_command(code, offsets)
    assert (command, mode) == (0xc0, 0x20 if channels == 2 else 0)
    assert low + 256 * high + 1 == DMA_BYTES


def test_auto_init_ring_requests_one_complete_refill_block(tmp_path):
    from support.qemu_sb16_ring_fixture import BLOCK_BYTES, sb16_ring
    nasm = os.environ.get('NASM') or shutil.which('nasm')
    if not nasm:
        pytest.skip('NASM is needed for authored guest assembly')
    code, offsets = sb16_ring(tmp_path, nasm)
    command, mode, low, high = _dsp_start_command(code, offsets)
    assert (command, mode) == (0xc6, 0x20)
    assert low + 256 * high + 1 == BLOCK_BYTES
