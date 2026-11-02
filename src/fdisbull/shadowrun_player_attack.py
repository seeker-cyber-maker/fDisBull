"""Wound-based attack difficulty, preserving the older healthy-player profile."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_combat import ROM_SHA256

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_player_attack.c'


def lift_player_attack(rom):
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('player attack requires the exact reviewed Shadowrun ROM')
    raw = SOURCE.read_bytes()
    result = author_program(raw.decode(), evidence={
        'kind': 'source-bound-party-wound-attack-modifier', 'source_sha256': ROM_SHA256,
        'range': [0xD5A, 0xD94, hashlib.sha256(rom[0xD5A:0xD94]).hexdigest()],
        'authoring_sha256': hashlib.sha256(raw).hexdigest(),
        'scope': 'two nonzero health channels and captured base difficulty4; '
                 'roll, skill, other modifiers and actor readiness separate'})
    if SOURCE.read_bytes() != raw:
        raise ValueError('player attack source changed during lift')
    return result
