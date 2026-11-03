"""Projected outer actor service for captured wounded animation modes."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_enemy_projection import SOURCE as PROJECT,lift_enemy_projection
from .shadowrun_enemy_outer import SOURCE as OUTER
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_enemy_wound_outer.c'
def lift_enemy_wound_outer(rom):
    lift_enemy_projection(rom)
    files=(OUTER,PROJECT,SOURCE);chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),evidence={
      'kind':'source-bound-wound-outer-projection','source_sha256':ROM_SHA256,
      'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
      'scope':'wounded 007C/807C actor scheduling; selected B3 unknown; later collision and callback separate'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
