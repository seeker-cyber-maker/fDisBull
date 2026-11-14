"""Instruction facts and bounded candidate edges for the KINT6 guest CPU.

This independently authored decoder implements the encodings described by the
KINT6 development kit, with ambiguous details checked against its 6.3.0 runtime
and assembler. It does not execute instructions, model host services, lift UIL,
or qualify later runtime extensions. CODE also contains data: successful decoding
alone is not evidence that the selected bytes are instructions.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .kint6_format import KE_ENTRY_OFFSET, inspect_ke_bytes, read_ke
from .processor import DecodedInstruction, Location, ProcessorInfo, Successor


_CONDITIONS = ('eq', 'ne', 'ge', 'gt', 'le', 'lt', 'ev', 'od')
_CONTROL = ('dbg', 'pause', 'sys', 'brk', 'term', 'nop', 'smod', 'emod')
_UNARY = {
    0: 'negf', 1: 'neg', 2: 'not', 3: 'tst', 4: 'push', 5: 'pop', 6: 'pea',
    8: 'cvuu', 9: 'cvss', 10: 'cvuf', 11: 'cvsf', 12: 'cvud', 13: 'cvsd',
    14: 'cvfs', 15: 'cvds', 16: 'cvfd', 17: 'cvdf',
}
_BINARY = {
    0: 'divi', 1: 'modi', 2: 'rshi', 3: 'divu', 4: 'modu', 5: 'rshu',
    6: 'add', 7: 'sub', 8: 'cmp', 9: 'mul', 10: 'tst', 11: 'lsh',
    12: 'and', 13: 'or', 14: 'xor', 15: 'mov', 16: 'movz', 17: 'addf',
    18: 'subf', 19: 'mulf', 20: 'divf', 21: 'cmpf', 22: 'lea',
    23: 'memmov', 30: 'pumem', 31: 'pomem',
}

# Addressing descriptors are kept separate from operations. There are four
# destinations and six sources; extension consumption follows operand order.
_BINARY_MODES = {}
for _destination, _codes in (
    ('register', (0x1C, 0x12, 0x1A, 0x16, 0x1E, 0x11)),
    ('register_memory', (0x02, 0x0A, 0x06, 0x0E, 0x01, 0x09)),
    ('absolute', (0x19, 0x05, 0x15, 0x0D, 0x1D, 0x03)),
    ('frame', (0x13, 0x0B, 0x1B, 0x07, 0x17, 0x0F)),
):
    for _source, _code in zip(
        ('register', 'register_memory', 'absolute', 'immediate', 'small', 'frame'), _codes
    ):
        _BINARY_MODES[_code] = (_destination, _source)
del _destination, _source, _codes, _code


def _signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def _register(number: int, width: int) -> dict[str, Any]:
    if not 0 <= number <= 15:
        raise ValueError(f'Invalid KINT6 register number {number}')
    return {'kind': 'register', 'number': number, 'width_bits': width,
            'memory_offset': (number + 1) * 8, 'text': f'${number}'}


def _memory(base: str, displacement: int, bits: int, width: int,
            register: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {'kind': 'memory', 'base': base, 'width_bits': width}
    if base == 'absolute':
        result.update(address=displacement, text=f'[{displacement:#x}]')
    else:
        signed = _signed(displacement, bits)
        label = 'FP' if base == 'frame' else f'${register}'
        result.update(displacement=signed, encoded_displacement=displacement,
                      displacement_bits=bits, text=f'[{label}][{signed}]')
        if register is not None:
            _register(register, 32)
            result['register'] = register
    return result


def _immediate(value: int, encoded_bits: int, width: int, *, signed: bool = False
               ) -> dict[str, Any]:
    # These are interpretations of encoded integer bits, not evaluated machine
    # values. In particular, historical runtimes differ on widening some small
    # constants; an instruction decoder must not claim arithmetic equivalence.
    signed_value = _signed(value, encoded_bits) if signed else value
    effective = signed_value & ((1 << width) - 1)
    return {'kind': 'immediate', 'encoded_value': value, 'encoded_bits': encoded_bits,
            'value': effective, 'signed_value': _signed(effective, width),
            'width_bits': width,
            'interpretation': 'encoded_literal_not_runtime_result',
            'text': f'={signed_value}' if signed else f'={value:#x}'}


def _code_address(value: int, *, packed: bool = False) -> dict[str, Any]:
    return {'kind': 'code_address', 'value': value, 'address_unit': 'byte',
            'encoded_value': value // 4 if packed else value,
            'encoded_unit': 'dword' if packed else 'byte', 'text': f'={value:#x}'}


class _Reader:
    def __init__(self, program: bytes, offset: int):
        self.program, self.start, self.offset = program, offset, offset

    def take(self, byte_count: int = 4) -> int:
        end = self.offset + byte_count
        if end > len(self.program):
            raise ValueError(f'Truncated KINT6 instruction at {self.start:#x}')
        value = int.from_bytes(self.program[self.offset:end], 'little')
        self.offset = end
        return value


def _binary_operands(reader: _Reader, word: int, width: int,
                     destination: str, source: str) -> list[dict[str, Any]]:
    low_register, high_register = (word >> 5) & 15, (word >> 16) & 15
    if destination == 'register':
        first = _register(low_register, width)
    elif destination == 'register_memory':
        first = _memory('register', reader.take(), 32, width, low_register)
    elif destination == 'absolute':
        first = _memory('absolute', reader.take(), 32, width)
    else:
        first = _memory('frame', word >> 16, 16, width)

    register = high_register if destination in ('register', 'register_memory') else low_register
    if source == 'register':
        second = _register(register, width)
    elif source == 'register_memory':
        second = _memory('register', reader.take(), 32, width, register)
    elif source == 'absolute':
        second = _memory('absolute', reader.take(), 32, width)
    elif source == 'immediate':
        encoded_bytes = 8 if width == 64 else 4
        second = _immediate(reader.take(encoded_bytes), encoded_bytes * 8, width)
    elif source == 'small':
        second = _immediate(register, 4, width, signed=True)
    elif destination == 'frame':
        second = _memory('frame', reader.take(), 32, width)
    else:
        second = _memory('frame', word >> 16, 16, width)
    first['role'], second['role'] = 'destination', 'source'
    return [first, second]


def _decode(reader: _Reader) -> dict[str, Any]:
    word = reader.take()
    mode, tag = word & 31, word & 0x3FF
    result: dict[str, Any] = {
        'word': word, 'operands': [], 'width_bits': None, 'target': None, 'flow': 'next',
    }

    if mode in (0x00, 0x08, 0x10, 0x18):
        width = 8 << ((word >> 5) & 3)
        operand_value = reader.take()
        if mode == 0x00:
            operand = _register(operand_value, width)
        elif mode == 0x10:
            operand = _memory('register', 0, 32, width, operand_value)
        elif mode == 0x08:
            operand = _memory('absolute', operand_value, 32, width)
        else:
            operand = _memory('frame', operand_value, 32, width)
        condition = _CONDITIONS[(word >> 7) & 7]
        target = (word >> 10) * 4
        result.update(mnemonic='tlj' + condition, family='test_branch', width_bits=width,
                      condition=condition, target=target, flow='conditional',
                      operands=[operand, _code_address(target, packed=True)])
    elif word & 0x7F == 0x34:
        condition = _CONDITIONS[(word >> 7) & 7]
        target = (word >> 10) * 4
        result.update(mnemonic='lj' + condition, family='flag_branch', condition=condition,
                      target=target, flow='conditional', operands=[_code_address(target, packed=True)])
    elif tag == 0x02C:
        target = (word >> 10) * 4
        result.update(mnemonic='jmp', family='jump', target=target, flow='jump',
                      operands=[_code_address(target, packed=True)])
    elif word & 0x3F == 0x0C:
        # This reads a DWORD target from memory at register + displacement.
        # Neither the register contents nor an initial jump table is live state.
        result.update(mnemonic='jmp', family='jump', flow='indirect_jump',
                      operands=[_memory('register', (word >> 10) * 4, 32, 32,
                                        (word >> 6) & 15)])
    elif word & 0x7F == 0x14:
        if word >> 10:
            raise ValueError('Unsupported KINT6 control-opcode extension bits')
        mnemonic = _CONTROL[(word >> 7) & 7]
        flow = {'pause': 'suspend', 'smod': 'suspend', 'emod': 'modal_resume',
                'term': 'stop'}.get(mnemonic, 'next')
        result.update(mnemonic=mnemonic, family='control', flow=flow)
        if mnemonic in ('sys', 'dbg'):
            result['host_effects'] = 'unresolved_runtime_service'
        if mnemonic in ('pause', 'smod', 'emod'):
            result['continuation'] = 'requires_runtime_event_or_modal_state'
    elif tag in (0x054, 0x354):
        if word & (0xFC00 if tag == 0x054 else 0x0C00):
            raise ValueError('Unsupported KINT6 call extension bits')
        arguments = {'kind': 'argument_bytes', 'value': word >> 16, 'text': str(word >> 16)}
        if tag == 0x054:
            target = reader.take()
            result.update(target=target, flow='call', operands=[arguments, _code_address(target)])
        else:
            result.update(flow='indirect_call', operands=[arguments, _register((word >> 12) & 15, 32)])
        result.update(mnemonic='jsrfr', family='call')
    elif tag in (0x154, 0x254):
        count = (word >> 10) & 15
        if count > 14:
            raise ValueError('Invalid KINT6 saved-register count')
        if tag == 0x254 and word >> 14:
            raise ValueError('Unsupported KINT6 return extension bits')
        registers = list(range(14 - count, 14))
        result.update(mnemonic='sfvr' if tag == 0x154 else 'efr', family='frame',
                      register_count=count, saved_registers=registers,
                      operands=[{'kind': 'register_count', 'value': count, 'text': str(count)}])
        if tag == 0x154:
            local_bytes = word >> 14
            result['local_bytes'] = local_bytes
            result['operands'].insert(0, {'kind': 'local_bytes', 'value': local_bytes,
                                           'text': str(local_bytes)})
        else:
            result['flow'] = 'return'
    elif word & 0xFF in (0x74, 0xF4):
        width = 8 << ((word >> 8) & 3)
        if word & 0xFF == 0xF4:
            operand = _immediate(word >> 10, 22, width, signed=True)
            mnemonic = 'pushs'
        else:
            if word >> 10:
                raise ValueError('Unsupported KINT6 PUSH extension bits')
            encoded_bytes = 8 if width == 64 else 4
            operand = _immediate(reader.take(encoded_bytes), encoded_bytes * 8, width)
            mnemonic = 'push'
        result.update(mnemonic=mnemonic, family='push_immediate', width_bits=width,
                      stack_bytes=max(2, width // 8), operands=[operand])
    elif word & 0xFF in (0xD4, 0xAC, 0x6C, 0xEC):
        operation = (word >> 10) & 31
        if word & 0x8000 or operation not in _UNARY:
            raise ValueError(f'Unknown or reserved KINT6 unary operation {operation}')
        width = 8 << ((word >> 8) & 3)
        mnemonic = _UNARY[operation]
        if mnemonic == 'negf' and width < 32:
            raise ValueError('Invalid KINT6 floating-point operand width')
        form = word & 0xFF
        if ((form in (0xD4, 0x6C) and word >> 20)
                or (form == 0xEC and word >> 16)):
            raise ValueError('Unsupported KINT6 unary operand extension bits')
        if form == 0xD4:
            operand = _register((word >> 16) & 15, width)
        elif form == 0xAC:
            operand = _memory('frame', word >> 16, 16, width)
        elif form == 0x6C:
            operand = _memory('register', reader.take(), 32, width, (word >> 16) & 15)
        else:
            operand = _memory('absolute', reader.take(), 32, width)
        result.update(mnemonic=mnemonic, family='unary', width_bits=width,
                      operation_code=operation, operands=[operand])
    elif mode in _BINARY_MODES:
        operation = (word >> 11) & 31
        if operation not in _BINARY:
            raise ValueError(f'Unknown or reserved KINT6 binary operation {operation}')
        width = 8 << ((word >> 9) & 3)
        mnemonic = _BINARY[operation]
        if mnemonic in ('addf', 'subf', 'mulf', 'divf', 'cmpf') and width < 32:
            raise ValueError('Invalid KINT6 floating-point operand width')
        destination, source = _BINARY_MODES[mode]
        if destination != 'frame' and source != 'frame':
            upper_used = (destination in ('register', 'register_memory')
                          and source in ('register', 'register_memory', 'small'))
            if word >> (20 if upper_used else 16):
                raise ValueError('Unsupported KINT6 binary operand extension bits')
        if (destination in ('absolute', 'frame') and source in ('absolute', 'immediate', 'frame')
                and word & 0x1E0):
            raise ValueError('Unsupported KINT6 binary operand extension bits')
        operands = _binary_operands(reader, word, width, destination, source)
        if mnemonic in ('lea', 'memmov', 'pumem', 'pomem') and operands[1]['kind'] != 'memory':
            raise ValueError('KINT6 address operation requires a memory source operand')
        if mnemonic in ('pumem', 'pomem'):
            operands[0]['role'] = 'byte_count_source'
            operands[1]['role'] = 'source_address' if mnemonic == 'pumem' else 'destination_address'
            if destination == 'absolute':
                # KASM's immediate count and absolute-memory count can share an
                # encoding. Preserve it rather than inventing a dereference.
                result['count_interpretation'] = 'absolute_field_overloaded_by_assembler'
        result.update(mnemonic=mnemonic, family='binary', width_bits=width,
                      operation_code=operation, addressing_mode=mode, operands=operands)
    else:
        raise ValueError(f'Unknown or reserved KINT6 opcode {word:#010x}')

    result['op'] = result['mnemonic']
    result['op_str'] = ', '.join(operand['text'] for operand in result['operands'])
    result['size'] = reader.offset - reader.start
    result['bytes'] = reader.program[reader.start:reader.offset].hex()
    return result


class KINT6Processor:
    """Decode one immutable initialized .KE image in a source-specific space.

    Guest byte offsets equal file offsets only in the initialized CODE segment.
    ZERO/STACK/HEAP are metadata, never fabricated input bytes. Candidate edges
    do not prove reachability, instruction boundaries, or runtime equivalence.
    """

    __slots__ = ('_program', '_image_info', 'info')

    def __init__(self, image: bytes):
        self._image_info = inspect_ke_bytes(image)
        self._program = image
        self.info = ProcessorInfo(
            'fdisbull.kint6', '1', f"kint6.sha256:{self._image_info['sha256']}", 'byte',
            ('decode', 'static_successors'), None,
        )

    @classmethod
    def from_file(cls, path):
        return cls(read_ke(path))

    @property
    def program(self) -> bytes:
        return self._program

    @property
    def image_info(self) -> dict[str, Any]:
        return deepcopy(self._image_info)

    def _edge(self, kind: str, target: int, evidence: str) -> Successor:
        if target % 4 or not KE_ENTRY_OFFSET <= target <= len(self._program) - 4:
            return Successor(kind, None, evidence +
                             f'; target {target:#x} is not an aligned initialized instruction candidate')
        return Successor(kind, Location(self.info.address_space, target),
                         evidence + '; candidate boundary in intermixed CODE/data')

    def decode(self, program: bytes, location: Location) -> DecodedInstruction | None:
        if program is not self._program:
            raise ValueError('KINT6 processor requires its captured immutable program snapshot')
        if not isinstance(location, Location) or location.space != self.info.address_space:
            raise ValueError('Location is outside the KINT6 processor address space')
        offset = location.offset
        if offset < KE_ENTRY_OFFSET:
            raise ValueError('KINT6 header is not an instruction entry')
        if offset % 4:
            raise ValueError('KINT6 instruction locations must be DWORD aligned')
        if offset >= len(program):
            return None

        facts = _decode(_Reader(program, offset))
        facts.update(file_offset=offset, guest_offset=offset,
                     address_mapping='initialized_guest_byte_offset_equals_file_offset',
                     qualification='static_instruction_candidate',
                     isa_reference='KINT6-development-kit-6.3.0',
                     runtime_execution=False)
        flow, edges = facts['flow'], []
        following = offset + facts['size']
        if flow in ('conditional', 'jump', 'call'):
            edges.append(self._edge('call' if flow == 'call' else 'branch', facts['target'],
                                    'decoded direct guest byte target'))
        elif flow in ('indirect_call', 'indirect_jump'):
            edges.append(Successor('call' if flow == 'indirect_call' else 'branch', None,
                                   'target requires runtime register' +
                                   (' and memory contents' if flow == 'indirect_jump' else ' contents')))
        elif flow == 'return':
            edges.append(Successor('return', None, 'EFR restores the runtime caller frame and return address'))
        elif flow in ('suspend', 'modal_resume'):
            edges.append(Successor(flow, None, 'continuation requires interpreter event or modal state; '
                                   'no ordinary fallthrough asserted'))
        if flow in ('next', 'conditional', 'call', 'indirect_call'):
            evidence = ('continuation if callee returns' if flow in ('call', 'indirect_call')
                        else 'conditional branch not taken' if flow == 'conditional'
                        else 'sequential instruction candidate, assuming normal completion')
            edges.append(self._edge('fallthrough', following, evidence))
        return DecodedInstruction(location, facts, tuple(edges))
