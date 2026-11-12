"""Source-level procedural UIL for the optimized Miniplanets PSG step."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .game_il import author_program, validate_program

SOURCE = Path(__file__).with_name('game_sources') / 'miniplanets_psg_uil.c'
ARTIFACT_PATH = Path(__file__).with_name('data') / 'miniplanets_psg.uil.json'


def lift_psg() -> dict:
    """Parse the authored fixed-width PSG routines into a bounded GameIL AST.

    The two entry points model the optimized envelope/period service and its
    PSG volume helper. They are not the full audio driver. The source has no
    external ROM regions; declared lookup tables must remain immutable by
    callers, since ``GameMachine.set_state`` itself does not enforce constness.
    """
    source = SOURCE.read_bytes()
    program = author_program(source.decode('utf-8'), evidence={
        'kind': 'authored-bounded-psg',
        'source_sha256': hashlib.sha256(source).hexdigest(),
        'profile': 'miniplanets-nes-psg-envelope-volume-1',
        'entries': ['audio_render_psg', 'audio_render_psg_volume'],
        'limits': [
            'models eight fixed PSG envelope voices, half-rate period copies, and PSG volume for channels 8 through 11',
            'does not model the complete audio driver, FM voices, PCM/DMC scheduling, APU writes, stream decoding, waveforms, or hardware timing',
            'the gain lookup tables are const by source declaration but GameMachine.set_state does not enforce constness; callers must not mutate them',
            'native 6502 behavior remains separately qualified by the bounded C/ASM comparison',
        ],
    })
    source_sha256 = hashlib.sha256(source).hexdigest()
    if program['evidence']['source_sha256'] != source_sha256:
        raise ValueError('PSG model source capture does not match its evidence')
    if SOURCE.read_bytes() != source:
        raise ValueError('PSG model source changed during export')
    try:
        packaged = json.loads(ARTIFACT_PATH.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Packaged PSG GameIL artifact is unavailable or invalid') from exc
    try:
        validate_program(packaged)
    except (TypeError, ValueError) as exc:
        raise ValueError('Packaged PSG GameIL artifact failed validation') from exc
    if packaged != program:
        raise ValueError('Packaged PSG GameIL artifact differs from the source-derived program')
    if SOURCE.read_bytes() != source:
        raise ValueError('PSG model source changed during artifact validation')
    return packaged
