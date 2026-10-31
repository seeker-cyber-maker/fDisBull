"""Source identities and explicit admission boundaries for first-party synthesis.

No upstream recompiler code is used. This is an experimental additive module;
its documents use the existing shared fdisbull-il-1 evaluator.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
from typing import Mapping


class Refused(ValueError):
    """The requested behavior is outside the admitted profile."""


class StaleSelection(Refused):
    """A previously selected backing no longer has execution authority."""


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(value: object) -> str:
    return sha256(canonical(value)).hexdigest()


def label(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', value):
        raise Refused('logical label must be 1..64 ASCII identifier characters')
    return '$' + value


@dataclass(frozen=True)
class NativeBacking:
    """Immutable executable bytes with image/bank/context identity.

    Hash a whole admitted backing at intake, never each instruction or byte.
    """
    image_id: str
    bank_id: str
    entry: int
    code: bytes
    cpu_profile: str = '6502-binary-isolated-v1'
    content_sha256: str = field(init=False)
    identity: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.image_id or not self.bank_id:
            raise Refused('image and physical-bank identities are required')
        if type(self.entry) is not int or not 0x8000 <= self.entry <= 0xffff:
            raise Refused('code entry must be in an explicitly supplied ROM window')
        if not isinstance(self.code, bytes) or not 1 <= len(self.code) <= 512:
            raise Refused('backing requires immutable bytes, length 1..512')
        if self.entry + len(self.code) > 0x10000:
            raise Refused('backing crosses the address-space boundary')
        if self.cpu_profile != '6502-binary-isolated-v1':
            raise Refused('unsupported CPU profile')
        h = sha256(self.code).hexdigest()
        object.__setattr__(self, 'content_sha256', h)
        object.__setattr__(self, 'identity', digest({
            'image': self.image_id, 'bank': self.bank_id, 'entry': self.entry,
            'profile': self.cpu_profile, 'code_sha256': h}))


@dataclass(frozen=True)
class Bindings:
    """Labels, not physical storage choices, enter the shared IL.

    RAM addresses are canonical 2 KiB cells. Mirrors are resolved by the source
    adapter. Stack-page cells are disallowed because balanced pushes are
    abstracted into temporaries under an explicit stack-unobservable contract.
    """
    ram: tuple[tuple[int, str], ...] = ()
    registers: tuple[tuple[str, str], ...] = (
        ('a', 'value'), ('x', 'index_x'), ('y', 'index_y'),
        ('c', 'carry'), ('z', 'zero'), ('n', 'negative'), ('v', 'overflow'))

    def __post_init__(self) -> None:
        if not isinstance(self.ram, tuple) or not isinstance(self.registers, tuple):
            raise Refused('bindings must be immutable tuples')
        if len(self.ram) > 64:
            raise Refused('at most 64 named RAM cells are admitted')
        regs = dict(self.registers)
        if set(regs) != {'a', 'x', 'y', 'c', 'z', 'n', 'v'} or len(self.registers) != 7:
            raise Refused('all seven projected register/flag bindings are required')
        addresses = set()
        names = [label(n) for _, n in self.registers]
        for address, name in self.ram:
            if type(address) is not int or not 0 <= address < 0x800:
                raise Refused('RAM binding must use canonical address 0..0x7ff')
            if 0x100 <= address < 0x200:
                raise Refused('source stack-page observation is outside this profile')
            if address in addresses:
                raise Refused('duplicate RAM binding; aliases must share one logical cell')
            addresses.add(address)
            names.append(label(name))
        if len(names) != len(set(names)):
            raise Refused('two distinct state locations cannot share a logical label')

    @property
    def identity(self) -> str:
        return digest({'ram': sorted(self.ram), 'registers': sorted(self.registers)})


@dataclass(frozen=True)
class Admission:
    """Caller-supplied scope, not an observed whole-machine guarantee."""
    decimal_enabled: bool = False
    asynchronous_observers: bool = False
    observe_stack_bytes: bool = False
    mapping_stable_during_block: bool = True

    def validate(self) -> None:
        values = (self.decimal_enabled, self.asynchronous_observers,
                  self.observe_stack_bytes, self.mapping_stable_during_block)
        if any(type(v) is not bool for v in values):
            raise Refused('admission switches must be Booleans')
        if self.decimal_enabled:
            raise Refused('decimal arithmetic is not admitted')
        if self.asynchronous_observers or self.observe_stack_bytes:
            raise Refused('interrupts, concurrent observers and source stack observations are not admitted')
        if not self.mapping_stable_during_block:
            raise Refused('a source mapping must remain stable during the bounded block')


@dataclass(frozen=True)
class RecoveredBlock:
    """Shared IL plus retained original backing and source bindings.

    The canonical document is immutable bytes. Returning a fresh dict prevents
    accidental mutation of an already qualified semantic identity.
    """
    backing: NativeBacking
    bindings: Bindings
    admission: Admission
    document_bytes: bytes
    source_map_bytes: bytes
    instruction_count: int
    maximum_saved_values: int

    @property
    def identity(self) -> str:
        return digest({'backing': self.backing.identity,
                       'binding': self.bindings.identity,
                       'semantics': sha256(self.document_bytes).hexdigest(),
                       'admission': self.admission.__dict__})

    def document(self, role: str = 'uil') -> dict:
        if role not in {'uil', 'udl'}:
            raise Refused('role must be uil or udl')
        doc = json.loads(self.document_bytes)
        doc['role'] = role
        return doc

    def state(self, **values: int | bool) -> dict:
        doc = self.document()
        state = {k: d['initial'] for k, d in doc['variables'].items()}
        for key, value in values.items():
            name = label(key)
            if name not in state or name.startswith('$tmp_'):
                raise Refused('unknown or private input label: ' + key)
            state[name] = value
        return state

    @property
    def public_names(self) -> tuple[str, ...]:
        return tuple(sorted(label(n) for _, n in self.bindings.ram + self.bindings.registers))

    def project(self, state: Mapping[str, int | bool]) -> dict:
        return {name: state[name] for name in self.public_names}

    def execute_original(self, executor, state):
        """An original CPU provider is explicit; IL is never substituted here."""
        if executor is None:
            raise Refused('no original-CPU executor supplied; UDL role is not execution authority')
        return executor(self.backing, self.bindings, self.admission, state)
