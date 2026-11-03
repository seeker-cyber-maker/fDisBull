"""Source-bound normal kind-3 party pose and sprite timing."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .udl_shadowrun import ROM_SHA256

SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_party_clock.c'
ANIMATION = SOURCE.with_name('shadowrun_animation.c')
RANGES = ((0xb45c, 0xb480), (0xb6ba, 0xb6e4), (0x5fdc, 0x60ae))

def lift_party_clock(rom):
    if len(rom) != 2097152 or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('party clock requires the reviewed source ROM')
    chunks = [p.read_bytes() for p in (ANIMATION, SOURCE)]
    program = author_program('\n'.join(p.decode() for p in chunks),
        [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}],
        evidence={'kind': 'source-bound-party-normal-sprite-clock',
                  'source_sha256': ROM_SHA256,
                  'ranges': [[a, b, hashlib.sha256(rom[a:b]).hexdigest()] for a,b in RANGES],
                  'authoring_sha256': [hashlib.sha256(c).hexdigest() for c in chunks],
                  'scope': 'kind3 positive-count idle/walking; graphics upload external'})
    if any(p.read_bytes()!=c for p,c in zip((ANIMATION,SOURCE),chunks)):
        raise ValueError('party clock source changed while lifting')
    return program
