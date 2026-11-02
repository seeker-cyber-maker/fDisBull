"""Per-actor source-order no-overlap guard."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_enemy_overlap import SOURCE as BASE, lift_enemy_overlap
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_enemy_overlap_one.c'
def lift_enemy_overlap_one(rom):
    lift_enemy_overlap(rom)
    chunks=[p.read_bytes() for p in (BASE,SOURCE)]
    result=author_program('\n'.join(c.decode() for c in chunks),evidence={'kind':'source-bound-per-actor-overlap-guard',
      'source_sha256':ROM_SHA256,'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
      'scope':'one actor scans later source-order slots; overlap response refused'})
    if any(p.read_bytes()!=c for p,c in zip((BASE,SOURCE),chunks)):raise ValueError('authoring changed')
    return result
