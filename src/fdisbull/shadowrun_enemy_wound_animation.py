"""Projected captured nonlethal wound animation counter/selector."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_enemy_wound import SOURCE as WOUND,lift_enemy_wound
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_enemy_wound_animation.c'
def lift_enemy_wound_animation(rom):
    lift_enemy_wound(rom)
    files=(SOURCE.with_name('shadowrun_collision.c'),SOURCE.with_name('shadowrun_collision_resolve.c'),
        SOURCE.with_name('shadowrun_enemy_move.c'),WOUND,SOURCE)
    chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
      'kind':'source-bound-wound-animation-projection','source_sha256':ROM_SHA256,
      'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
      'scope':'wound counter and negative-count selector; sprite upload excluded'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
