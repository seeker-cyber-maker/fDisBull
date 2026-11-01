"""Bounded reader for the US Shadow Run mode-prompt records.

The caller supplies private ROM bytes. This module retains offsets, not text or
assets. Command effects, text decoding, timing, and the caller's display state
are outside this interface. The source is the 68000 prompt at 0x1f3c4.
"""
from dataclasses import dataclass


class UnsupportedPrompt(ValueError):
    """A record or target is outside the supported source boundary."""


@dataclass(frozen=True)
class Prompt:
    address: int
    title: int
    options: tuple[int, ...]
    targets: tuple[int, ...]
    terminal: bool = False


@dataclass(frozen=True)
class PromptAction:
    kind: str  # wait, command, record, or terminal
    value: int | None = None


def _long(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise UnsupportedPrompt('truncated prompt')
    return int.from_bytes(data[offset:offset + 4], 'big')


def _pointer(value: int, size: int) -> None:
    if not 0 < value < size:
        raise UnsupportedPrompt('text pointer outside supplied source')


def read_prompt(data: bytes, address: int) -> Prompt:
    """Read one source record, preserving opaque text references and targets."""
    title, first = _long(data, address), _long(data, address + 4)
    _pointer(title, len(data))
    if first & 0x80000000:
        return Prompt(address, title, (), (), True)
    _pointer(first, len(data))
    second, third = _long(data, address + 8), _long(data, address + 12)
    if not second and third:
        raise UnsupportedPrompt('third option without second')
    options = [first]
    for ptr in (second, third):
        if ptr:
            _pointer(ptr, len(data))
            options.append(ptr)
    targets = tuple(_long(data, address + 16 + 4 * i) for i in range(len(options)))
    return Prompt(address, title, tuple(options), targets)


def select_prompt(prompt: Prompt, pressed_bits: int) -> PromptAction:
    """Apply source button priority; command side effects are caller-owned.

    The source checks A before B before C, and ignores disabled B/C. A blocked
    B does not fall through to C. Target 0xfa and above is a record address;
    small values identify an opaque original command, not its effect.
    """
    if prompt.terminal:
        return PromptAction('terminal', 0xfb)
    index = next((i for i, bit in enumerate((14, 12, 13)) if pressed_bits & (1 << bit)), None)
    if index is None or index >= len(prompt.targets):
        return PromptAction('wait')
    target = prompt.targets[index]
    if target & 0x80000000:
        raise UnsupportedPrompt('negative target requires unmodeled signed 68000 dispatch')
    return PromptAction('command' if target < 0xfa else 'record', target)


from pathlib import Path
import hashlib
from .game_il import author_program

SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_dialogue.c'
ROM_SHA256 = '92a614491fc3ea12a6df32459cce08b48574b7b814e244c07eb860dc5c6edb7e'


def lift_dialogue(rom: bytes):
    """Produce typed GameIL for the source-bound prompt-selection slice."""
    if len(rom) != 2097152 or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('Shadowrun dialogue requires the exact reviewed source ROM')
    raw = SOURCE.read_bytes()
    evidence = {'kind': 'source-bound-reviewed-procedural-slice',
        'source_sha256': ROM_SHA256, 'source_range': [0x1f522, 0x1f590],
        'source_range_sha256': hashlib.sha256(rom[0x1f522:0x1f590]).hexdigest(),
        'flag_source_range': [0x213ca, 0x213fa],
        'flag_source_range_sha256': hashlib.sha256(rom[0x213ca:0x213fa]).hexdigest(),
        'payment_source_range': [0x21458, 0x2148a],
        'payment_source_range_sha256': hashlib.sha256(rom[0x21458:0x2148a]).hexdigest(),
        'authoring_sha256': hashlib.sha256(raw).hexdigest(),
        'scope': 'prompt selection and command 06, 30, 31 leaves; all other commands unsupported'}
    program = author_program(raw.decode(), evidence=evidence)
    if SOURCE.read_bytes() != raw:
        raise ValueError('Shadowrun dialogue source changed during capture')
    return program
