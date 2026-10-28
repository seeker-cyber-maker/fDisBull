"""Explicit, in-process instruction decoder seam; not a plugin loader.

This layer does not admit guest projects to the native SQLite analyzer. Location
spaces and successor facts here are independent of host/file provenance.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol


@dataclass(frozen=True)
class Location:
    space: str
    offset: int

    def __post_init__(self):
        if not isinstance(self.space, str) or not self.space:
            raise ValueError('location requires a named address space')
        if isinstance(self.offset, bool) or not isinstance(self.offset, int) or self.offset < 0:
            raise ValueError('location offset must be a non-negative integer')


@dataclass(frozen=True)
class Successor:
    kind: str
    target: Location | None
    evidence: str


@dataclass(frozen=True)
class ProcessorInfo:
    identity: str
    version: str
    address_space: str
    address_unit: str
    capabilities: tuple[str, ...]
    state_schema: str | None


@dataclass(frozen=True)
class DecodedInstruction:
    location: Location
    facts: dict[str, Any]
    successors: tuple[Successor, ...]


class Processor(Protocol):
    info: ProcessorInfo

    def decode(self, program: Any, location: Location) -> DecodedInstruction | None: ...


def decode_instruction(processor: Processor, program: Any, location: Location) -> DecodedInstruction | None:
    """Dispatch an explicitly supplied processor, without importing code by name."""
    info = processor.info
    if (not isinstance(info, ProcessorInfo)
            or any(not isinstance(value, str) or not value for value in
                   (info.identity, info.version, info.address_space, info.address_unit))
            or not isinstance(info.capabilities, tuple)
            or any(not isinstance(value, str) or not value for value in info.capabilities)
            or (info.state_schema is not None and not isinstance(info.state_schema, str))):
        raise ValueError('invalid processor descriptor')
    if not isinstance(location, Location) or location.space != info.address_space:
        raise ValueError('location is outside the processor address space')
    result = processor.decode(program, location)
    if result is None:
        return None
    if (not isinstance(result, DecodedInstruction) or result.location != location
            or not isinstance(result.facts, dict) or not isinstance(result.successors, tuple)
            or any(not isinstance(edge, Successor) or not isinstance(edge.kind, str) or not edge.kind
                   or not isinstance(edge.evidence, str) or not edge.evidence
                   or (edge.target is not None and not isinstance(edge.target, Location))
                   for edge in result.successors)):
        raise ValueError('invalid processor instruction result')
    return result


class NativeProcessor:
    """Adapter to the existing flat native decoder; program is a byte window."""

    def __init__(self, arch: str, bits: int):
        self.arch, self.bits = arch, bits
        self.info = ProcessorInfo(f'fdisbull.native.{arch}.{bits}', '1', 'native.flat', 'byte',
                                  ('decode', 'static_successors'), None)

    def decode(self, program: bytes, location: Location) -> DecodedInstruction | None:
        from .decoder import decode
        facts = decode(program, location.offset, self.arch, self.bits)
        if facts is None:
            return None
        flow, target = facts['flow'], facts['target']
        edges = []
        if target is not None:
            edges.append(Successor('call' if flow == 'call' else 'branch',
                                   Location(location.space, target), 'decoded direct operand'))
        elif flow in ('jump', 'conditional', 'call', 'indirect_jump', 'indirect_call'):
            edges.append(Successor('call' if flow in ('call', 'indirect_call') else 'branch', None,
                                   'unresolved control-flow target'))
        if flow in ('next', 'call', 'conditional', 'indirect_call'):
            following = location.offset + facts['size']
            if following < 1 << 64:
                edges.append(Successor('fallthrough', Location(location.space, following),
                                       'call return assumed' if flow in ('call', 'indirect_call') else 'decoded fallthrough'))
        return DecodedInstruction(location, facts, tuple(edges))


class CILMethodProcessor:
    """Adapt an existing managed decoder, retaining assembly- and method-local offsets.

    This calls `disassemble_managed`; it does not execute CIL or
    validate stacks, exception handlers, or dynamic call targets.
    """

    def __init__(self, assembly: bytes, token, max_instructions: int = 10000):
        from .managed import disassemble_managed
        method = disassemble_managed(assembly, token, max_instructions=max_instructions)
        token = method['method']['token']
        self.method = method
        self.info = ProcessorInfo('fdisbull.cil.method', '1',
                                  f'cil.sha256:{sha256(assembly).hexdigest()}:method:{token}', 'byte',
                                  ('decode', 'static_successors'), None)
        self._instructions = {item['offset']: item for item in method['instructions']}
        self._branches = {}
        for branch in method['branch_references']:
            self._branches.setdefault(branch['source_offset'], []).append(branch)

    def decode(self, program: Any, location: Location) -> DecodedInstruction | None:
        if program is not self.method:
            raise ValueError('CIL adapter requires its decoded method document')
        facts = self._instructions.get(location.offset)
        if facts is None:
            return None
        edges = []
        for branch in self._branches.get(location.offset, ()):
            target = branch['target_offset']
            valid = branch['target_is_instruction'] is True and branch['target_in_code'] and target >= 0
            evidence = 'decoded ' + branch['kind']
            if not valid:
                evidence += f'; target offset {target} is invalid or its instruction boundary is unverified'
            edges.append(Successor('branch', Location(location.space, target) if valid else None, evidence))
        flow = facts['flow']
        # dncil classifies CIL jmp as a call, but jmp transfers control without
        # a return to the following instruction. Preserve raw facts unchanged.
        if facts['mnemonic'] == 'jmp':
            edges.append(Successor('branch', None, 'method transfer target not modeled as a method entry'))
        elif flow in ('call', 'indirect_call'):
            edges.append(Successor('call', None, 'call target not modeled as a method entry'))
        if facts['mnemonic'] != 'jmp' and flow in ('next', 'prefix', 'call', 'indirect_call', 'conditional', 'break'):
            edges.append(Successor('fallthrough', Location(location.space, location.offset + facts['size']),
                                   'call return assumed' if flow in ('call', 'indirect_call') else 'decoded fallthrough'))
        return DecodedInstruction(location, facts, tuple(edges))
