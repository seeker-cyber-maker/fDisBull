"""Executable typed UIL for the reviewed Miniplanets NES presentation policy.

The program is an authored model, not a Genesis ROM lifter or a universal
console presentation backend. It contains no original ROM data. The native
adapter and the model must be qualified separately on declared inputs.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .game_il import GameMachine, author_program, canonical, validate_program

SOURCE = Path(__file__).with_name('game_sources') / 'miniplanets_presentation_uil.c'
ARTIFACT = Path(__file__).with_name('data') / 'miniplanets_presentation.uil.json'

def lift_presentation() -> dict:
    """Return a versioned executable GameIL program, not an opaque C payload."""
    source = SOURCE.read_bytes()
    program = author_program(source.decode('utf-8'), evidence={
        'kind': 'authored-bounded-presentation-model',
        'source_sha256': hashlib.sha256(source).hexdigest(),
        'profile': 'miniplanets-nes-presentation-1',
        'entries': ['presentation_classify', 'presentation_clear_terrain',
                    'presentation_terrain_miss', 'presentation_prepare',
                    'presentation_complete'],
        'limits': ['model of a source-bound NES adapter, not Genesis ROM lifting',
                   'geometry applies only to independently qualified projection pages',
                   'callers must not mutate the declared-const geometry tables',
                   'active nametable and per-nametable validity fields are binary (0 or 1)',
                   'sparse hint is valid only when staging bytes outside the 174-cell union are zero',
                   'exact-terrain hint and validity require the documented producer certificate',
                   'pending staging and queued jobs are immutable by caller contract',
                   'completion models job application, not PPU timing or DMC DMA',
                   'native machine code requires independent equivalence checks'],
    })
    try:
        artifact_bytes = ARTIFACT.read_bytes()
        artifact = json.loads(artifact_bytes)
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError('Packaged presentation UIL artifact is missing or invalid') from exc
    if canonical(artifact) != canonical(program):
        raise ValueError('Packaged presentation UIL artifact does not match its authored source')
    validate_program(artifact)
    try:
        if SOURCE.read_bytes() != source or ARTIFACT.read_bytes() != artifact_bytes:
            raise ValueError('Presentation source or artifact changed during export')
    except OSError as exc:
        raise ValueError('Presentation source or artifact became unavailable during export') from exc
    return artifact

def presentation_machine(program: dict | None = None) -> GameMachine:
    """Validate and create a fresh bounded presentation reference machine."""
    if program is None:
        program = lift_presentation()
    validate_program(program)
    return GameMachine(program)
