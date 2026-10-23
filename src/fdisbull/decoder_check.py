"""Bounded, non-executing comparisons of x86 instruction interpretations.

Each start offset is a hypothesis. Neither agreement nor disagreement selects
an instruction for the database or establishes behavior on a physical CPU.
"""
from __future__ import annotations

from importlib.metadata import version

import capstone
import iced_x86 as ix


def _iced(data: bytes, bits: int, address: int) -> dict:
    decoder = ix.Decoder(bits, data, ip=address)
    instruction = decoder.decode()
    if instruction.is_invalid:
        return {'engine': 'iced-x86', 'valid': False, 'size': None,
                'bytes': None, 'text': None,
                'error': 'truncated' if decoder.last_error == ix.DecoderError.NO_MORE_BYTES else 'invalid'}
    return {'engine': 'iced-x86', 'valid': True, 'size': instruction.len,
            'bytes': data[:instruction.len].hex(),
            'text': ix.Formatter(ix.FormatterSyntax.NASM).format(instruction), 'error': None}


def _capstone(data: bytes, bits: int, address: int, decoder) -> dict:
    instruction = next(decoder.disasm(data, address, count=1), None)
    if instruction is None:
        return {'engine': 'capstone', 'valid': False, 'size': None,
                'bytes': None, 'text': None, 'error': 'invalid_or_truncated'}
    return {'engine': 'capstone', 'valid': True, 'size': instruction.size,
            'bytes': bytes(instruction.bytes).hex(),
            'text': (instruction.mnemonic + ' ' + instruction.op_str).strip(), 'error': None}


def _comparison(left: dict, right: dict) -> dict:
    validity = left['valid'] == right['valid']
    lengths = left['size'] == right['size'] if left['valid'] and right['valid'] else None
    texts = (' '.join(left['text'].split()).lower() == ' '.join(right['text'].split()).lower()
             if left['valid'] and right['valid'] else None)
    if not validity:
        status = 'validity_disagreement'
    elif not left['valid']:
        status = 'both_invalid'
    elif not lengths:
        status = 'length_disagreement'
    elif not texts:
        status = 'text_difference'
    else:
        status = 'agreement'
    return {'status': status, 'validity_agrees': validity,
            'length_agrees': lengths, 'text_agrees': texts}


def compare_decoders(data: bytes, bits: int, address: int = 0, arch: str = 'x86',
                     scan_offsets: bool = False, max_candidates: int = 16) -> dict:
    """Compare at most fifteen possible starts without executing input bytes.

    The optional scan tests starts 0..14, bounded by available bytes and the
    candidate budget. It is not a linear sweep, instruction-length oracle or
    discovery of undocumented processor semantics. ARM64 has no independent
    iced backend and is rejected rather than compared to the same decoder.
    """
    if not isinstance(data, bytes) or not 1 <= len(data) <= 4096:
        raise ValueError('data must be immutable bytes containing 1..4096 bytes')
    if arch != 'x86':
        raise ValueError('two-engine decoder comparison currently supports x86 only')
    if isinstance(bits, bool) or not isinstance(bits, int) or bits not in (16, 32, 64):
        raise ValueError('x86 bits must be 16, 32 or 64')
    if isinstance(address, bool) or not isinstance(address, int) or not 0 <= address < 1 << 64:
        raise ValueError('address must be an unsigned 64-bit integer')
    if not isinstance(scan_offsets, bool):
        raise ValueError('scan_offsets must be a boolean')
    if isinstance(max_candidates, bool) or not isinstance(max_candidates, int) or not 1 <= max_candidates <= 16:
        raise ValueError('max_candidates must be an integer in 1..16')
    available = min(len(data), 15) if scan_offsets else 1
    count = min(available, max_candidates)
    if address + count - 1 >= 1 << 64:
        raise ValueError('candidate address exceeds the unsigned 64-bit address space')
    decoder = capstone.Cs(capstone.CS_ARCH_X86,
                          {16: capstone.CS_MODE_16, 32: capstone.CS_MODE_32, 64: capstone.CS_MODE_64}[bits])
    candidates = []
    for offset in range(count):
        raw = data[offset:offset + 15]
        left = _iced(raw, bits, address + offset)
        right = _capstone(raw, bits, address + offset, decoder)
        candidates.append({'offset': offset, 'address': address + offset,
                           'input_hex': raw.hex(),
                           'classification': 'unconfirmed decode proposal',
                           'decoders': [left, right], 'comparison': _comparison(left, right)})
    return {'arch': arch, 'bits': bits, 'address': address, 'input_hex': data.hex(),
            'scan_offsets': scan_offsets, 'truncated_candidates': count < available,
            'engines': [
                {'name': 'iced-x86', 'package_version': version('iced-x86'),
                 'options': 'default decoder options; NASM formatter'},
                {'name': 'capstone', 'package_version': version('capstone'),
                 'runtime_version': list(capstone.cs_version()),
                 'options': 'default x86 decoder options; Intel formatter; skipdata disabled'},
            ],
            'vendor_policy': 'decoder defaults; no physical CPU profile selected',
            'hardware_observed': False, 'executed': False,
            'candidates': candidates,
            'warnings': [
                'Agreement does not prove code, CPU support or equivalent semantics.',
                'Text differences can be formatting or mnemonic aliases; they are not semantic verdicts.',
                'Alternative starts are proposals only; no stored analysis or bytes are modified.',
            ]}
