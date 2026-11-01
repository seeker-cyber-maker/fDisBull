"""Bounded source-backed start-option and archetype menu transitions."""
from pathlib import Path
import hashlib
from .game_il import author_program
from .udl_shadowrun import ROM_SHA256

SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_menu.c'
RANGES = ((0x590D2, 0x59170), (0x59264, 0x59316), (0xC376, 0xC3B2))
MAIN_LABELS = ('New Game', 'Load Game')
ARCHETYPE_LABELS = ('Samurai', 'Decker', 'Gator Shaman')


def lift_menu(rom):
    if len(rom) != 2097152 or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('menu requires the reviewed Shadowrun source ROM')
    raw = SOURCE.read_bytes()
    program = author_program(raw.decode(), [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}],
        evidence={'kind': 'source-bound-shadowrun-menu', 'source_sha256': ROM_SHA256,
                  'ranges': [[a,b,hashlib.sha256(rom[a:b]).hexdigest()] for a,b in RANGES],
                  'authoring_sha256': hashlib.sha256(raw).hexdigest(),
                  'scope': 'start option and archetype cursor/confirm edges; initializer/load/video/audio excluded'})
    if SOURCE.read_bytes() != raw:
        raise ValueError('menu source changed while lifting')
    return program
