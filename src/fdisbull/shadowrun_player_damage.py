"""Original-backed bullet defense and HP update for the captured player profile."""
from pathlib import Path
import hashlib

from .game_il import author_program
from .shadowrun_combat import ROM_SHA256

SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_player_damage.c'
SOURCE_RANGES = ((0x55948, 0x55A62), (0x55E62, 0x55F44),
                 (0x55786, 0x55848), (0x3674, 0x36F0), (0xD3A, 0xDFC))


def lift_player_damage(rom):
    if len(rom) != 2097152 or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('player damage requires the exact reviewed Shadowrun ROM')
    raw = SOURCE.read_bytes()
    program = author_program(raw.decode(),
        [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}],
        evidence={'kind': 'source-bound-captured-player-damage',
                  'source_sha256': ROM_SHA256,
                  'ranges': [[lo, hi, hashlib.sha256(rom[lo:hi]).hexdigest()]
                             for lo, hi in SOURCE_RANGES],
                  'authoring_sha256': hashlib.sha256(raw).hexdigest(),
                  'scope': 'captured party stats, projectile effect supplied; '
                           'normal bullet defense and HP before HUD/animation/death'})
    if SOURCE.read_bytes() != raw:
        raise ValueError('player damage source changed while lifting')
    return program
