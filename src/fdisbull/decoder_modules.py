"""Explicit trusted front ends for non-native code, without a native project.

Registration admits Python objects supplied by the application, never imports
code named by an input file. Built-in openers capture bytes once. This registry
is not a sandbox, a persistent VM database, or an interpreter.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any, Callable, Protocol

from .processor import Location, Processor, ProcessorInfo, decode_instruction


@dataclass(frozen=True)
class DecoderModuleInfo:
    identity: str
    version: str
    source_format: str
    capabilities: tuple[str, ...]

    def __post_init__(self):
        if (any(type(x) is not str or not x for x in
                (self.identity, self.version, self.source_format))
                or type(self.capabilities) is not tuple
                or any(type(x) is not str or not x for x in self.capabilities)):
            raise ValueError('invalid decoder module descriptor')


@dataclass(frozen=True)
class DecoderInput:
    module: DecoderModuleInfo
    processor: Processor
    program: Any
    entry: Location
    source_json: str
    lifter: Callable[..., dict] | None = None
    binding: Callable[[DecoderInput], None] | None = field(default=None, repr=False)
    processor_info: ProcessorInfo = field(init=False)

    def __post_init__(self):
        if (not isinstance(self.module, DecoderModuleInfo)
                or not isinstance(getattr(self.processor, 'info', None), ProcessorInfo)
                or not isinstance(self.entry, Location)
                or self.entry.space != self.processor.info.address_space):
            raise ValueError('invalid module input or entry space')
        info = self.processor.info
        if (any(type(x) is not str or not x for x in
                (info.identity, info.version, info.address_space, info.address_unit))
                or type(info.capabilities) is not tuple
                or any(type(x) is not str or not x for x in info.capabilities)
                or (info.state_schema is not None and type(info.state_schema) is not str)):
            raise ValueError('invalid module processor descriptor')
        object.__setattr__(self, 'processor_info', info)
        if type(self.source_json) is not str or len(self.source_json.encode()) > 65536:
            raise ValueError('source identity exceeds metadata budget')
        source = json.loads(self.source_json)
        if not isinstance(source, dict):
            raise ValueError('source identity must be an object')
        canonical = json.dumps(source, sort_keys=True, separators=(',', ':'), allow_nan=False)
        if len(canonical.encode()) > 65536:
            raise ValueError('source identity exceeds metadata budget')
        object.__setattr__(self, 'source_json', canonical)
        if type(self.program) is bytes and source.get('program_sha256') != sha256(self.program).hexdigest():
            raise ValueError('captured program bytes do not match source identity')
        if self.lifter is not None and not callable(self.lifter):
            raise ValueError('invalid module lifter')
        if not callable(self.binding):
            raise ValueError('source binding required; use capture_input')

    @property
    def source(self) -> dict:
        """Return a fresh metadata copy, never the captured source bytes."""
        return json.loads(self.source_json)

    @property
    def identity(self) -> str:
        _check_input(self)
        identity = dict(module=asdict(self.module), processor=asdict(self.processor_info),
                        source=self.source, entry=asdict(self.entry),
                        program_sha256=sha256(self.program).hexdigest() if type(self.program) is bytes else None)
        return sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'),
                                 allow_nan=False).encode()).hexdigest()


class DecoderModule(Protocol):
    info: DecoderModuleInfo

    def open(self, source, **options) -> DecoderInput: ...


def capture_input(module: DecoderModuleInfo, processor: Processor, program: Any,
                  entry: Location, source: dict, lifter=None) -> DecoderInput:
    """Bind a trusted opener's facts, source and optional lifter together.

    Byte snapshots are immutable. Extensions using other program objects must
    own their immutability/revision checks too. This binds normal API copies;
    it does not protect against arbitrary trusted Python replacing the guard.
    """
    if not isinstance(source, dict):
        raise ValueError('source identity must be an object')
    source_json = json.dumps(source, sort_keys=True, separators=(',', ':'), allow_nan=False)
    def bound(opened):
        if (opened.module != module or opened.processor is not processor
                or opened.program is not program or opened.entry != entry
                or opened.source_json != source_json or opened.lifter is not lifter):
            raise ValueError('opened source binding or module capabilities changed')
    return DecoderInput(module, processor, program, entry, source_json, lifter, bound)


class DecoderRegistry:
    """Application-owned registry of explicitly supplied, trusted modules."""

    def __init__(self):
        self._modules: dict[str, tuple[DecoderModuleInfo, DecoderModule]] = {}

    def register(self, module: DecoderModule) -> None:
        info = getattr(module, 'info', None)
        if not isinstance(info, DecoderModuleInfo) or not callable(getattr(module, 'open', None)):
            raise ValueError('a trusted decoder module object is required')
        if info.identity in self._modules:
            raise ValueError('decoder module is already registered')
        self._modules[info.identity] = (info, module)

    def catalog(self) -> list[dict]:
        return [asdict(self._modules[key][0]) for key in sorted(self._modules)]

    def open(self, identity: str, source, **options) -> DecoderInput:
        if type(identity) is not str or identity not in self._modules:
            raise ValueError('unknown decoder module; select an explicitly registered identity')
        pinned, module = self._modules[identity]
        if module.info != pinned:
            raise ValueError('registered decoder module descriptor changed')
        opened = module.open(source, **options)
        if (module.info != pinned or not isinstance(opened, DecoderInput)
                or opened.module != pinned):
            raise ValueError('module returned a different decoder identity')
        _check_input(opened)
        return opened


def _check_input(opened: DecoderInput) -> None:
    if not isinstance(opened, DecoderInput) or opened.processor.info != opened.processor_info:
        raise ValueError('opened processor descriptor changed')
    opened.binding(opened)


class AGI2917Module:
    info = DecoderModuleInfo('fdisbull.agi.2.917.subset', '4', 'agi-v2-logic',
                             ('decode', 'static_successors', 'lift_state_projection',
                              'lift_scalar_conditions', 'lift_direct_logic_calls', 'bounded_source_components',
                              'shared_continuations', 'opaque_control_flow', 'object_resource_effects'))

    def open(self, source, *, volume_dir, logic, profile, entry_offset=0, stop_offsets=(),
             callee_entries=None, stop_points=()) -> DecoderInput:
        from .agi import AGI2917Processor
        from .agi_lift import lift_logic
        from .agi_source import load_program
        program = load_program(source, volume_dir, logic, profile=profile, entry_offset=entry_offset,
                               stop_offsets=stop_offsets, callee_entries=callee_entries,
                               stop_points=stop_points)
        resource = program.root
        provenance = dict(kind='agi-v2-logic-resource', code_length=len(resource.code),
                          program_sha256=sha256(resource.code).hexdigest(),
                          **program.provenance())
        return capture_input(self.info, AGI2917Processor(resource.space), resource.code,
                             Location(resource.space, program.entry_offset), provenance,
                             lambda **options: lift_logic(resource, callees=program.callees,
                                 callee_entries=dict(program.callee_entries), entry_offset=program.entry_offset,
                                 stop_offsets=program.stop_offsets, stop_points=program.stop_points, **options))


class ZMachineV3Module:
    info = DecoderModuleInfo('fdisbull.zmachine.v3', '1', 'zmachine-v3-story',
                             ('decode', 'static_successors'))

    def open(self, source) -> DecoderInput:
        from .zmachine_processor import ZMachineV3Processor
        processor = ZMachineV3Processor.from_file(source)
        provenance = dict(kind='zmachine-v3-story',
                          program_sha256=sha256(processor.program).hexdigest(), **processor.story_info)
        return capture_input(self.info, processor, processor.program,
                             Location(processor.info.address_space, provenance['initial_pc']),
                             provenance)


def builtin_registry() -> DecoderRegistry:
    registry = DecoderRegistry()
    registry.register(AGI2917Module())
    registry.register(ZMachineV3Module())
    return registry


def analyze_input(opened: DecoderInput, *, address=None, max_instructions=40) -> dict:
    """Follow supplied static successors in their own source address space.

    Complete means the selected static edges were covered without unresolved
    targets, malformed instructions, overlaps or exhausted budgets. It does not
    establish runtime reachability, game intent, or interpreter equivalence.
    The initial analyzer requires byte-addressed processors with exact spans;
    the registry itself does not impose a byte address unit on other modules.
    """
    _check_input(opened)
    if type(max_instructions) is not int or not 1 <= max_instructions <= 1000:
        raise ValueError('max_instructions must be an integer in 1..1000')
    required = {'decode', 'static_successors'}
    if not (required <= set(opened.module.capabilities)
            and required <= set(opened.processor_info.capabilities)):
        raise ValueError('module and processor must declare decode/static_successors capabilities')
    if opened.processor.info.address_unit != 'byte':
        raise ValueError('static module analysis currently requires byte address units')
    if address is None:
        start = opened.entry
    else:
        if type(address) is not int or address < 0:
            raise ValueError('address must be a non-negative source offset')
        start = Location(opened.entry.space, address)
    pending, queued, seen = deque([start]), {start}, set()
    rows, issues, intervals = [], [], []
    consumed, edge_count = 0, 0
    while pending and len(seen) < max_instructions:
        location = pending.popleft()
        queued.remove(location)
        seen.add(location)
        try:
            instruction = decode_instruction(opened.processor, opened.program, location)
            if instruction is None:
                raise ValueError('no instruction at selected source location')
            facts = instruction.facts
            size, raw = facts.get('size'), facts.get('bytes')
            if (type(size) is not int or not 1 <= size <= 65536
                    or type(raw) is not str or len(raw) != 2 * size
                    or len(bytes.fromhex(raw)) != size):
                raise ValueError('byte analyzer requires an exact encoded instruction span')
            # Bound traversal work independently of instruction count.
            consumed += size
            edge_count += len(instruction.successors)
            if consumed > 1024 * 1024 or edge_count > 8192:
                issues.append(dict(location=asdict(location), kind='work_budget'))
                break
            row = dict(location=asdict(location), facts=facts,
                       successors=[asdict(edge) for edge in instruction.successors])
            if len(json.dumps(row, allow_nan=False).encode()) > 65536:
                raise ValueError('instruction facts exceed metadata budget')
            rows.append(row)
            end = location.offset + size
            if any(location.offset < old_end and old_start < end
                   for old_start, old_end in intervals):
                issues.append(dict(location=asdict(location), kind='overlapping_instruction'))
            intervals.append((location.offset, end))
            for edge in instruction.successors:
                if edge.target is None:
                    if edge.kind != 'return':
                        issues.append(dict(location=asdict(location), kind='unresolved_successor',
                                           evidence=edge.evidence))
                elif edge.target.space != opened.entry.space:
                    issues.append(dict(location=asdict(location), kind='external_address_space',
                                       target=asdict(edge.target)))
                elif edge.target not in seen and edge.target not in queued:
                    pending.append(edge.target)
                    queued.add(edge.target)
        except (ValueError, TypeError) as exc:
            issues.append(dict(location=asdict(location), kind='decode_error', error=str(exc)))
    if pending:
        issues.append(dict(kind='instruction_budget', remaining=len(pending)))
    return dict(format='fdisbull-module-analysis-1', module=asdict(opened.module),
                processor=asdict(opened.processor.info), source=opened.source,
                snapshot=opened.identity, entry=asdict(start), instructions=rows, issues=issues,
                complete=not issues, coverage='selected_static_edges', runtime_execution=False,
                limits=dict(max_instructions=max_instructions, max_decoded_bytes=1024 * 1024,
                            max_edges=8192))


def lift_input(opened: DecoderInput, *, initial_state, max_instructions=128, max_call_depth=None,
               control_flow=None, allow_opaque=None,effect_profile=None) -> dict:
    _check_input(opened)
    if opened.lifter is None or 'lift_state_projection' not in opened.module.capabilities:
        raise ValueError('this decoder module has no qualified lifter')
    options = dict(initial_state=initial_state, max_instructions=max_instructions)
    if max_call_depth is not None:
        if 'lift_direct_logic_calls' not in opened.module.capabilities:
            raise ValueError('this module does not support a logic call depth limit')
        options['max_call_depth'] = max_call_depth
    if control_flow is not None:
        if 'shared_continuations' not in opened.module.capabilities:
            raise ValueError('this module does not support compact control flow')
        options['control_flow'] = control_flow
    if allow_opaque is not None:
        if 'opaque_control_flow' not in opened.module.capabilities:
            raise ValueError('this module does not support opaque control flow')
        options['allow_opaque'] = allow_opaque
    if effect_profile is not None:
        if 'object_resource_effects' not in opened.module.capabilities:
            raise ValueError('this module does not support object/resource effects')
        options['effect_profile']=effect_profile
    result = opened.lifter(**options)
    return dict(result, module=asdict(opened.module), snapshot=opened.identity)
