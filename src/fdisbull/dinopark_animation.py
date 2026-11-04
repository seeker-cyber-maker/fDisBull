"""Bounded DinoPark ACT sequence inspection and explicit-input simulation.

Operand rules follow the original reader at static 2A4E:0DCC. The runtime
derives the 32-opcode observed corpus from the E51 contracts and E55 typed interpreter: context zero, a bounded
16-record bank and explicit display mode, initialization and phase ticks/signals.
This is not a general scene player, a wall clock, or a palette/compositor.
Reports retain offsets and hashes, never original program bytes.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
import hashlib
import itertools
import struct

from .dinopark_images import ActorFile, decode_act

MAX_INSTRUCTIONS = 65536
PROFILE = 'dinopark-observed-act-context0-v1'


def signed8(value):
    return value - 256 if value >= 128 else value


def signed16(value):
    return value - 65536 if value >= 32768 else value


@dataclass(frozen=True)
class AnimationInstruction:
    offset: int
    opcode: int
    length: int
    a: int
    b: int
    scratch: bytes
    operands: tuple

    @property
    def supported(self):
        return self.opcode in SUPPORTED_OPCODES


# Names are authored interpretations, not recovered symbols. Opcode shape is
# separate from meaning; an unknown operation is never admitted by the runtime.
_NAMES = {
    1: 'block', 3: 'terminal', 4: 'wait.cycle.end', 5: 'cycle.forward',
    6: 'cycle.reverse', 7: 'cycle.pingpong', 0x10: 'set.draw.order',
    0x11: 'set.frame', 0x12: 'set.visible', 0x14: 'set.velocity.x',
    0x15: 'set.velocity.y', 0x16: 'signal.clear', 0x17: 'branch',
    0x19: 'wait.frame', 0x1a: 'set.frame.cadence', 0x1b: 'set.sprite',
    0x1c: 'set.frame.count', 0x1d: 'wait.signal.one', 0x1f: 'set.draw.argument',
    0x40: 'set.x', 0x41: 'set.y', 0x45: 'wait.x.eq', 0x46: 'wait.y.eq',
    0x47: 'set.group', 0x4a: 'wait.x.lt', 0x4b: 'wait.x.gt',
    0x4d: 'wait.y.gt', 0x4e: 'wait.deadline', 0x5d: 'signal.set',
    0x5f: 'branch.signal.one', 0xf2: 'frames.forward.loop',
    0xf3: 'frames.forward.hold',
}


def decode_instruction(data: bytes, offset: int = 0) -> AnimationInstruction:
    """Inspect one operand shape, including explicit variable-read lookahead.

    A successfully read operand shape does not establish its operation meaning.
    F0..FE retain the native extra read; missing lookahead is refused. Opcode
    66 and FF retain the original reader's one-byte gaps.
    """
    if not isinstance(data, bytes) or not 1 <= len(data) <= 65535:
        raise ValueError('program must contain 1..65535 immutable bytes')
    if type(offset) is not int or not 0 <= offset < len(data):
        raise ValueError('instruction is outside the program')
    op = data[offset]
    a = b = 0
    scratch = b''
    n = 1
    operands = ()
    def octet(i):
        if offset + i >= len(data):
            raise ValueError('truncated instruction or native lookahead')
        return data[offset + i]
    def word(i):
        return signed16(octet(i) * 256 + octet(i + 1))
    if 0x10 <= op < 0x40:
        a = signed8(octet(1)); n = 2; operands = (a,)
    elif 0x40 <= op < 0x5c:
        a = word(1); n = 3; operands = (a,)
    elif 0x5c <= op < 0x66:
        a = signed8(octet(1)); b = signed8(octet(2)); n = 3; operands = (a, b)
    elif 0x66 < op < 0x80:
        a = word(1); b = signed8(octet(3)); n = 4; operands = (a, b)
    elif 0x80 <= op < 0x90:
        a = signed8(octet(1)); b = word(2); n = 4; operands = (a, b)
    elif 0x90 <= op < 0xb0:
        a = signed8(octet(1)); b = signed8(octet(2)); scratch = bytes((octet(3),))
        n = 4; operands = (a, b, signed8(scratch[0]))
    elif 0xb0 <= op < 0xd0:
        a = word(1); b = word(3); n = 5; operands = (a, b)
    elif 0xd0 <= op < 0xf0:
        a = word(1); b = word(3); scratch = bytes((octet(5),))
        n = 6; operands = (a, b, signed8(scratch[0]))
    elif 0xf0 <= op < 0xff:
        if op == 0xf7:
            b = signed8(octet(1)); a = signed8(octet(2))
            if a < 0:
                raise ValueError('negative variable count is unsupported')
            scratch = bytes(octet(3 + i) for i in range(a))
            n = 2 + a; operands = (b, a, tuple(signed8(x) for x in scratch))
        else:
            a = signed8(octet(1))
            if a < 0:
                raise ValueError('negative variable count is unsupported')
            scratch = bytes(octet(2 + i) for i in range(a + 1))
            n = 2 + a; operands = (a, tuple(signed8(x) for x in scratch[:a]))
    return AnimationInstruction(offset, op, n, a, b, scratch, operands)


def program(data: bytes, *, max_instructions: int = MAX_INSTRUCTIONS):
    """Return bounded linear instructions; reject truncated tails."""
    _integer(max_instructions, 'max_instructions', 1, MAX_INSTRUCTIONS)
    out = []
    at = 0
    while at < len(data):
        if len(out) >= max_instructions:
            raise ValueError('animation instruction budget exceeded')
        item = decode_instruction(data, at)
        out.append(item)
        at += item.length
    if not out or at != len(data):
        raise ValueError('instruction spans do not end at the sequence boundary')
    return tuple(out)


@dataclass(frozen=True)
class AnimationProgram:
    index: int
    file_offset: int
    length: int
    sha256: str
    instructions: tuple[AnimationInstruction, ...]


@dataclass(frozen=True)
class AnimationFile:
    source_sha256: str
    source_size: int
    programs: tuple[AnimationProgram, ...]


def inspect_animation(data, *, max_instructions=MAX_INSTRUCTIONS, **decoder_limits):
    """Inspect every ACT sequence under source/pixel/work and instruction bounds.

    The existing ACT decoder enforces container/stream bounds. The independent
    instruction count bounds object allocation across all programs, rather
    than granting each program another full budget.
    """
    _integer(max_instructions, 'max_instructions', 1, MAX_INSTRUCTIONS)
    resource = decode_act(data, **decoder_limits)
    remaining = max_instructions
    at = resource.sequence_offset
    programs = []
    for index, code in enumerate(resource.sequences):
        if remaining <= 0:
            raise ValueError('animation instruction budget exceeded')
        instructions = program(code, max_instructions=remaining)
        remaining -= len(instructions)
        programs.append(AnimationProgram(index, at + 2, len(code),
                        hashlib.sha256(code).hexdigest(), instructions))
        at += 2 + len(code)
    return AnimationFile(resource.source_sha256, resource.source_size, tuple(programs))


def describe_animation(data, **limits):
    """Return metadata and hashes only; no source/scratch/lookahead byte arrays."""
    parsed = inspect_animation(data, **limits)
    programs = []
    for p in parsed.programs:
        boundaries = {i.offset for i in p.instructions}
        rows = []
        for i in p.instructions:
            following = (_branch_target(i) if i.opcode in (0x17, 0x5F) else i.offset + i.length)
            if i.opcode == 3:
                successors = []
            else:
                successors = [following] if following in boundaries else []
                if i.opcode == 0x5F and i.offset + i.length in boundaries:
                    successors = sorted(set(successors + [i.offset + i.length]))
            rows.append({'offset': i.offset, 'file_offset': p.file_offset + i.offset,
                         'opcode': i.opcode, 'mnemonic': _NAMES.get(i.opcode, 'unknown'),
                         'length': i.length, 'read_length': i.length + int(0xf0 <= i.opcode < 0xff),
                         'runtime_supported': i.supported,
                         'local_successors': successors if i.supported else [],
                         'syntactic_continuation_candidate': following if following in boundaries else None,
                         'flow_scope': 'unconditional branch or linear continuation only; conditional/host flow unresolved'})
        unsupported = sorted({i.opcode for i in p.instructions if not i.supported})
        programs.append({'index': p.index, 'file_offset': p.file_offset,
                         'length': p.length, 'sha256': p.sha256,
                         'instruction_count': len(rows), 'instructions': rows,
                         'unsupported_opcodes': unsupported})
    return {'format': 'dinopark-act-animation-1', 'source_sha256': parsed.source_sha256,
            'source_size': parsed.source_size, 'program_count': len(programs),
            'instruction_count': sum(len(p.instructions) for p in parsed.programs),
            'input_executed': False, 'native_runtime_tested': False,
            'runtime_profile': PROFILE, 'runtime_default_display_mode': 0, 'programs': programs,
            'claim_scope': 'bounded sequence operand inspection; runtime supports an explicit context0 phase/display-mode subset; no implicit frame rate, palette, clipping or scene playback'}


SUPPORTED_OPCODES = frozenset((0x01, 0x03, 0x04, 0x05, 0x06, 0x07,
    0x10, 0x11, 0x12, 0x14, 0x15, 0x16, 0x17, 0x19, 0x1A, 0x1B,
    0x1C, 0x1D, 0x1F, 0x40, 0x41, 0x45, 0x46, 0x47, 0x4A, 0x4B,
    0x4D, 0x4E, 0x5D, 0x5F, 0xF2, 0xF3))
ACTOR_RECORD_SIZE = 234
ACTOR_BANK_RECORDS = 16


def _integer(value: int, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def _signed32(value: int) -> int:
    return value - 0x100000000 if value & 0x80000000 else value


def _branch_target(instruction: AnimationInstruction) -> int:
    raw = (instruction.a if instruction.opcode == 0x17 else instruction.b) & 255
    adjustment = raw if raw < 128 else 126 - raw
    return (instruction.offset + instruction.length + adjustment) & 65535


class ProgramValidationError(ValueError):
    """The supplied program is outside the declared executable subset."""

    def __init__(self, message: str, *, program_index: int,
                 offset: int | None = None, opcode: int | None = None):
        self.program_index = program_index
        self.offset = offset
        self.opcode = opcode
        context = f'program {program_index}'
        if offset is not None:
            context += f' at {offset:#x}'
        super().__init__(f'{context}: {message}')


class RuntimeBudgetExceeded(RuntimeError):
    """A tick did not yield inside its explicit per-actor command budget."""

    def __init__(self, actor: int, pc: int, budget: int):
        self.actor = actor
        self.pc = pc
        self.budget = budget
        super().__init__(f'actor {actor} at {pc:#x} exceeded {budget} commands')


class RuntimeStateError(RuntimeError):
    """Execution would leave the declared program or sprite bounds."""


@dataclass(frozen=True)
class ActorSnapshot:
    """Raw finite-width values, except local PC and explicit Boolean flags."""

    actor_index: int
    program_index: int
    pc: int = 0
    base_sprite: int = 0
    x: int = 0
    y: int = 0
    previous_x: int = 0
    previous_y: int = 0
    velocity_x: int = 0
    velocity_y: int = 0
    motion_cadence: int = 0
    draw_argument: int = 0
    blocked: bool = False
    frame_count: int = 0
    frame_offset: int = 0
    group: int = 0
    width: int = 0
    height: int = 0
    draw_order: int = 0
    visible: int = 0
    hidden_dirty: int = 0
    deadline: int = 0
    frame_deadline: int = 0
    next_motion_tick: int = 0
    suspended: bool = False
    wait_opcode: int = 0
    wait_a: int = 0
    wait_b: int = 0
    frame_cadence: int = 0
    cycle_mode: int = 0
    cycle_index: int = 0
    frame_table: tuple[int, ...] = (0,) * 32


def _actor_report(actor):
    result = asdict(actor)
    table = bytes(result.pop('frame_table'))
    result['frame_table_sha256'] = hashlib.sha256(table).hexdigest()
    result['frame_table_bytes'] = len(table)
    return result


def _actor_record(actor: ActorSnapshot, pointer: int, source_segment: int) -> bytes:
    """Serialize all retained fields of one declared zero-initialized record."""
    record = bytearray(ACTOR_RECORD_SIZE)
    def word(offset: int, value: int) -> None:
        struct.pack_into('<H', record, offset, value)
    def dword(offset: int, value: int) -> None:
        struct.pack_into('<I', record, offset, value)
    word(0, pointer)
    word(2, source_segment)
    for offset, value in ((0x88, actor.base_sprite), (0x91, actor.velocity_x),
                          (0x92, actor.velocity_y), (0xD5, actor.motion_cadence),
                          (0x93, actor.blocked),
                          (0x94, actor.wait_opcode), (0x99, actor.frame_count),
                          (0x9A, actor.frame_offset), (0xAB, actor.cycle_mode),
                          (0xAC, actor.cycle_index), (0xCD, actor.draw_order),
                          (0xCF, actor.visible), (0xD0, actor.hidden_dirty),
                          (0xD6, actor.next_motion_tick), (0xE9, actor.suspended)):
        record[offset] = value
    for offset, value in ((0x89, actor.x), (0x8B, actor.y),
                          (0x8D, actor.previous_x), (0x8F, actor.previous_y),
                          (0x95, actor.wait_a), (0x97, actor.wait_b),
                          (0x9B, actor.group), (0x9F, actor.width),
                          (0xA1, actor.height), (0xA3, actor.draw_argument),
                          (0xA5, actor.frame_cadence)):
        word(offset, value)
    dword(0xA7, actor.frame_deadline)
    dword(0xD1, actor.deadline)
    record[0xAD:0xCD] = bytes(actor.frame_table)
    return bytes(record)


def _actor_bank_byte(actors: list[ActorSnapshot], actor_index: int, offset: int) -> int:
    """Read an actual serialized field, including F3's neighboring-record read.

    The host fixture supplies 16 zero-initialized records. Inactive records stay
    zero; memory beyond those records is unavailable and never guessed.
    """
    address = actor_index * ACTOR_RECORD_SIZE + offset
    if not 0 <= address < ACTOR_BANK_RECORDS * ACTOR_RECORD_SIZE:
        raise RuntimeStateError('cycle read leaves the declared 16-record actor bank')
    index, within = divmod(address, ACTOR_RECORD_SIZE)
    if index >= len(actors):
        return 0
    actor = actors[index]
    return _actor_record(actor, index * 2048 + actor.pc, 0x2F)[within]


@dataclass(frozen=True)
class TickResult:
    time: int
    draws: tuple[tuple[int, int, int, int, int], ...]
    actors: tuple[ActorSnapshot, ...]
    released: tuple[int, ...]
    waiting: bool
    executed_commands: int

    def to_dict(self) -> dict:
        """Return JSON-serializable results; command count is not a CPU count."""
        result = asdict(self)
        result['actors'] = [_actor_report(actor) for actor in self.actors]
        return result


class AnimationRuntime:
    """Execute the bounded observed ACT opcode union with explicit phase clocks.

    The default is the historical zero-context/display0 fixture. Display modes
    1/2/4 adjust cached width by 7/1/3 pixels; initial_time seeds only the frame
    deadline and initial_positions supplies explicit host positioning. Neither
    infers original initialization, wall-clock rate or scene services. update()
    and schedule() separate original phases; tick() composes both at one time.

    ``suspended`` and ``hidden`` are 16-bit actor masks. Suspension is assigned
    each tick; the default zero resumes every selected actor. A missing hidden
    mask preserves current visibility. ``signals`` updates supplied word slots;
    signal waits compare to exactly one, and opcode 16 clears its selected slot.

    Validation and tick failures leave the committed runtime unchanged. That
    transactional host-API policy is not claimed as original error behavior.
    """

    def __init__(self, resource: ActorFile, *,
                 program_indices: Sequence[int] | None = None,
                 instruction_budget: int = 256, display_mode: int = 0,
                 initial_time: int = 0, initial_positions=None):
        if not isinstance(resource, ActorFile):
            raise ValueError('resource must be a decoded ActorFile')
        if not 1 <= len(resource.sprites) <= 256:
            raise ValueError('the bounded runtime requires 1..256 sprites')
        for sprite in resource.sprites:
            _integer(sprite.width, 'sprite width', 1, 4096)
            _integer(sprite.height, 'sprite height', 1, 255)
        self.display_mode = _integer(display_mode, 'display_mode', 0, 4)
        initial_time = _integer(initial_time, 'initial_time', 0, 0xffffffff)
        self.instruction_budget = _integer(instruction_budget,
                                           'instruction_budget', 1, 65536)
        indices = tuple(range(len(resource.sequences))) if program_indices is None else tuple(itertools.islice(iter(program_indices), 17))
        if not 1 <= len(indices) <= 16:
            raise ValueError('the bounded runtime requires 1..16 actors')
        for index in indices:
            _integer(index, 'program index', 0, len(resource.sequences) - 1)
        self._resource = resource
        self.program_indices = indices
        self.programs = tuple(resource.sequences[i] for i in indices)
        self._instructions: tuple[dict[int, AnimationInstruction], ...] = tuple(
            self._validate_program(code, index) for code, index in zip(self.programs, indices))
        if initial_positions is None:
            positions = ((0, 0),) * len(indices)
        else:
            positions = tuple(itertools.islice(iter(initial_positions), 17))
            if len(positions) != len(indices):
                raise ValueError('initial_positions must contain one coordinate pair per actor')
            for pair in positions:
                if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                    raise ValueError('initial_positions must contain coordinate pairs')
                for value in pair:
                    _integer(value, 'initial coordinate', 0, 65535)
        self._actors = tuple(ActorSnapshot(actor, index, x=positions[actor][0],
                             y=positions[actor][1], frame_deadline=initial_time)
                             for actor, index in enumerate(indices))
        self._signals = (0,) * 32
        self._time: int | None = None

    def _validate_program(self, code: bytes, index: int) -> dict[int, AnimationInstruction]:
        if not isinstance(code, bytes) or not 1 <= len(code) <= 2047:
            raise ProgramValidationError('requires 1..2047 immutable program bytes',
                                         program_index=index)
        try:
            instructions = program(code)
        except ValueError as error:
            raise ProgramValidationError(str(error), program_index=index) from error
        mapping = {instruction.offset: instruction for instruction in instructions}
        for instruction in instructions:
            op = instruction.opcode
            if op not in SUPPORTED_OPCODES:
                raise ProgramValidationError(f'opcode {op:#04x} is outside the observed ACT opcode subset',
                                             program_index=index, offset=instruction.offset,
                                             opcode=op)
            if op in (0x16, 0x1D, 0x5D, 0x5F) and not 0 <= instruction.a < 32:
                raise ProgramValidationError('signal operand is outside the supplied 32-word bank',
                                             program_index=index, offset=instruction.offset,
                                             opcode=op)
            if op in (0xF2, 0xF3):
                count = instruction.a
                table = instruction.scratch[:count]
                if not 2 <= count <= 32 or table[0] == 255 or 255 not in table:
                    raise ProgramValidationError('F2/F3 requires 2..32 copied bytes, a first frame and an in-table FF marker',
                                                 program_index=index, offset=instruction.offset,
                                                 opcode=op)
            if op == 0x1B and (instruction.a & 255) >= len(self._resource.sprites):
                raise ProgramValidationError('base sprite is outside the supplied resource',
                                             program_index=index, offset=instruction.offset,
                                             opcode=op)
            if op != 0x03:
                following = _branch_target(instruction) if op in (0x17, 0x5F) else instruction.offset + instruction.length
                if following not in mapping or op == 0x5F and instruction.offset + instruction.length not in mapping:
                    raise ProgramValidationError('successor is outside an instruction boundary',
                                                 program_index=index, offset=instruction.offset,
                                                 opcode=op)
        return mapping

    @property
    def actors(self) -> tuple[ActorSnapshot, ...]:
        return self._actors

    def snapshot(self) -> dict:
        return {'format': 'dinopark-act-runtime-state-1', 'profile': PROFILE, 'display_mode': self.display_mode, 'time': self._time,
                'actors': [_actor_report(actor) for actor in self._actors],
                'signals': list(self._signals)}

    def signal_bytes(self) -> bytes:
        return struct.pack('<32H', *self._signals)

    def tick(self, time: int, *, suspended: int = 0,
             hidden: int | None = None,
             signals: Mapping[int, int] | None = None) -> TickResult:
        return self._advance(time, suspended=suspended, hidden=hidden,
                             signals=signals, do_update=True, do_schedule=True)

    def update(self, time: int, *, suspended: int = 0,
               hidden: int | None = None,
               signals: Mapping[int, int] | None = None) -> TickResult:
        """Advance/render/release only; the caller owns original phase timing."""
        return self._advance(time, suspended=suspended, hidden=hidden,
                             signals=signals, do_update=True, do_schedule=False)

    def schedule(self, time: int, *, suspended: int = 0,
                 hidden: int | None = None,
                 signals: Mapping[int, int] | None = None) -> TickResult:
        """Dispatch only; never invent an update or elapsed logical time."""
        return self._advance(time, suspended=suspended, hidden=hidden,
                             signals=signals, do_update=False, do_schedule=True)

    def _advance(self, time, *, suspended, hidden, signals, do_update, do_schedule):
        time = _integer(time, 'time', 0, 0xFFFFFFFF)
        suspended = _integer(suspended, 'suspended', 0, 65535)
        if hidden is not None:
            hidden = _integer(hidden, 'hidden', 0, 65535)
        next_signals = list(self._signals)
        if signals is not None:
            if not isinstance(signals, Mapping):
                raise ValueError('signals must map word-slot numbers to word values')
            items = tuple(itertools.islice(signals.items(), 33))
            if len(items) > 32:
                raise ValueError('signals exceeds the 32-word bank')
            for slot, value in items:
                _integer(slot, 'signal slot', 0, 31)
                next_signals[slot] = _integer(value, 'signal value', 0, 65535)

        # Work on immutable snapshots and commit only after the whole tick.
        actors = [replace(actor, suspended=bool(suspended & (1 << actor.actor_index)),
                          visible=(int(not (hidden & (1 << actor.actor_index)))
                                   if hidden is not None else actor.visible))
                  for actor in self._actors]
        released: set[int] = set()

        draws: list[tuple[int, int, int, int, int]] = []
        if do_update:
            # Original update phase: deadlines and eligible movement first.
            for index, actor in enumerate(actors):
                if actor.suspended:
                    continue
                if actor.deadline:
                    if _signed32(actor.deadline) > _signed32(time):
                        continue
                    actor = replace(actor, deadline=0, blocked=False)
                    released.add(index)
                if signed8(actor.next_motion_tick) <= _signed32(time):
                    actor = replace(actor, previous_x=actor.x, previous_y=actor.y,
                                    x=(actor.x + signed8(actor.velocity_x)) & 65535,
                                    y=(actor.y + signed8(actor.velocity_y)) & 65535,
                                    next_motion_tick=(2 * actor.motion_cadence + time) & 255)
                actors[index] = actor

            # Original render order precedes released-PC advancement and scheduling.
            for actor in sorted(actors, key=lambda state: (signed8(state.draw_order), state.actor_index)):
                if actor.suspended or not actor.visible or not 0 <= signed8(actor.draw_order) < 16:
                    continue
                if self._instructions[actor.actor_index][actor.pc].opcode == 0x03:
                    actor = replace(actor, cycle_mode=0)
                if (actor.cycle_mode and actor.deadline == 0 and
                        _signed32(actor.frame_deadline) <= _signed32(time)):
                    mode, cursor = actor.cycle_mode, actor.cycle_index
                    count = signed8(actor.frame_count)
                    if mode == 5:
                        next_index = cursor + 1 if cursor + 1 <= count - 1 else 0
                    elif mode == 6:
                        next_index = cursor - 1 if cursor > 0 else count - 1
                    elif mode in (7, 0xF2, 0xF3):
                        # Initial custom cursor FF reads next actor +C3.
                        following = _actor_bank_byte(actors, actor.actor_index, 0xAE + cursor)
                        next_index = (cursor if mode == 0xF3 else 0) if following == 255 else (cursor + 1) & 255
                    else:
                        raise RuntimeStateError(f'unvalidated cycle mode {mode:#x}')
                    frame = _actor_bank_byte(actors, actor.actor_index, 0xAD + next_index)
                    interval = signed16((2 * actor.frame_cadence) & 65535)
                    actor = replace(actor, cycle_index=next_index, frame_offset=frame,
                                    frame_deadline=(time + interval) & 0xFFFFFFFF)
                actors[actor.actor_index] = actor
                sprite = (actor.base_sprite + signed8(actor.frame_offset)) & 65535
                if not 0 <= sprite < len(self._resource.sprites):
                    raise RuntimeStateError(f'actor {actor.actor_index}: draw sprite {sprite} is outside the resource')
                draws.append((sprite, 3, actor.x, actor.y, actor.draw_argument))

            # Conditional waits inspect the post-render frame and the supplied
            # signals. There is no second release pass after script signal writes.
            for index, actor in enumerate(actors):
                if actor.suspended or actor.wait_opcode == 0:
                    continue
                if actor.wait_opcode == 1:
                    satisfied = False
                elif actor.wait_opcode == 4:
                    if actor.cycle_mode == 5:
                        satisfied = signed8(actor.frame_offset) == signed8(actor.frame_count) - 1
                    elif actor.cycle_mode == 6:
                        satisfied = actor.frame_offset == 0
                    elif actor.cycle_mode == 7:
                        try:
                            marker = actor.frame_table.index(255)
                        except ValueError as error:
                            raise RuntimeStateError('ping-pong cycle has no bounded marker') from error
                        satisfied = actor.cycle_index == marker - 1
                    else:
                        satisfied = False
                elif actor.wait_opcode in (0x45, 0x46, 0x4A, 0x4B, 0x4D):
                    x, y, threshold = signed16(actor.x), signed16(actor.y), signed16(actor.wait_a)
                    satisfied = {0x45: x == threshold, 0x46: y == threshold,
                                 0x4A: x < threshold, 0x4B: x > threshold,
                                 0x4D: y > threshold}[actor.wait_opcode]
                elif actor.wait_opcode == 0x19:
                    satisfied = signed8(actor.frame_offset) == signed16(actor.wait_a)
                elif actor.wait_opcode == 0x1D:
                    satisfied = next_signals[actor.wait_a] == 1
                else:
                    raise RuntimeStateError(f'unvalidated wait opcode {actor.wait_opcode:#x}')
                if satisfied:
                    released.add(index)
                if index in released:
                    actors[index] = replace(actor, wait_opcode=0, wait_a=0, wait_b=0,
                                            blocked=False)

            # A released wait advances by decoding its retained instruction without
            # executing that instruction again, then resets the frame deadline.
            for index in sorted(released):
                actor = actors[index]
                instruction = self._instructions[index][actor.pc]
                actors[index] = replace(actor, pc=actor.pc + instruction.length,
                                        frame_deadline=time)

        waiting = False
        executed_commands = 0
        if do_schedule:
            for index, actor in enumerate(actors):
                actor, count, actor_waiting = self._schedule_actor(index, actor, time, next_signals)
                actors[index] = actor
                executed_commands += count
                waiting = waiting or actor_waiting

        result = TickResult(time, tuple(draws), tuple(actors), tuple(sorted(released)),
                            waiting, executed_commands)
        self._actors = result.actors
        self._signals = tuple(next_signals)
        self._time = time
        return result

    def _schedule_actor(self, index: int, actor: ActorSnapshot,
                        time: int, signals: list[int]) -> tuple[ActorSnapshot, int, bool]:
        if actor.suspended:
            return actor, 0, False
        if actor.blocked:
            return actor, 0, True
        instructions = self._instructions[index]
        if instructions[actor.pc].opcode == 0x03:
            return actor, 0, False

        for dispatched in range(1, self.instruction_budget + 1):
            instruction = instructions[actor.pc]
            op, value = instruction.opcode, instruction.a
            if op == 0x03:
                return replace(actor, blocked=True), dispatched, True
            if op == 0x4E:
                return replace(actor, deadline=(time + value) & 0xFFFFFFFF,
                               blocked=True), dispatched, True
            if op in (1, 4, 0x19, 0x1D, 0x45, 0x46, 0x4A, 0x4B, 0x4D):
                return replace(actor, wait_opcode=op, wait_a=value & 65535,
                               wait_b=instruction.b & 65535, blocked=True), dispatched, True
            if op in (0x17, 0x5F) and (op == 0x17 or signals[value] == 1):
                actor = replace(actor, pc=_branch_target(instruction))
                continue
            changes: dict[str, int] = {'pc': actor.pc + instruction.length}
            if op in (5, 6, 7):
                count = signed8(actor.frame_count)
                if not 1 <= count <= (16 if op == 7 else 32):
                    raise RuntimeStateError('cycle frame count exceeds the bounded table')
                table = tuple(range(count))
                if op == 7:
                    table += tuple(range(count - 2, 0, -1)) + (255,)
                changes.update(frame_table=table + (0,) * (32 - len(table)),
                               cycle_mode=op, cycle_index=0,
                               frame_offset=count - 1 if op == 6 else 0)
            elif op == 0x5F:
                pass  # Untaken exact-one branch: normal decoded-length advance.
            elif op == 0x10:
                changes['draw_order'] = value & 255
            elif op == 0x11:
                changes['frame_offset'] = value & 255
                changes.update(cycle_mode=0, cycle_index=0)
            elif op == 0x12:
                changes['visible'] = value & 255
                if value == 0:
                    changes['hidden_dirty'] = 1
            elif op == 0x1B:
                sprite = self._resource.sprites[value & 255]
                changes.update(base_sprite=value & 255,
                               width=sprite.width + {1: 7, 2: 1, 4: 3}.get(self.display_mode, 0),
                               height=sprite.height)
            elif op == 0x1C:
                changes['frame_count'] = value & 255
            elif op in (0x14, 0x15):
                changes['velocity_x' if op == 0x14 else 'velocity_y'] = value & 255
            elif op == 0x1F:
                changes['draw_argument'] = value & 65535
            elif op in (0x16, 0x5D):
                signals[value] = 0 if op == 0x16 else instruction.b & 65535
            elif op == 0x1A:
                changes['frame_cadence'] = value & 65535
            elif op in (0xF2, 0xF3):
                table = tuple(instruction.scratch[:value]) + (0,) * (32 - value)
                changes.update(frame_table=table, cycle_mode=op, cycle_index=255,
                               frame_deadline=(time - 1) & 0xFFFFFFFF)
            elif op == 0x40:
                changes['x'] = value & 65535
            elif op == 0x41:
                changes['y'] = value & 65535
            elif op == 0x47:
                changes['group'] = value & 65535
            else:
                raise RuntimeStateError(f'unvalidated opcode {op:#x}')
            actor = replace(actor, **changes)
        raise RuntimeBudgetExceeded(index, actor.pc, self.instruction_budget)

    def actor_records(self, *, program_base: int = 0, program_stride: int = 2048,
                      source_segment: int = 0x2F) -> bytes:
        """Serialize the exact declared 234-byte zero-initialized actor fixture.

        The supplied layout maps local PCs into a conventional source segment.
        Unmodeled record bytes remain zero. This is not general DOS save-state
        serialization and does not recover arbitrary pre-existing actor bytes.
        """
        program_base = _integer(program_base, 'program_base', 0, 65535)
        program_stride = _integer(program_stride, 'program_stride', 1, 65535)
        source_segment = _integer(source_segment, 'source_segment', 0, 65535)
        for index, code in enumerate(self.programs):
            start = program_base + index * program_stride
            if len(code) > program_stride or start + len(code) > 65536:
                raise ValueError('program layout overlaps or leaves the supplied segment')
        return b''.join(_actor_record(actor,
                                      program_base + actor.actor_index * program_stride + actor.pc,
                                      source_segment) for actor in self._actors)


