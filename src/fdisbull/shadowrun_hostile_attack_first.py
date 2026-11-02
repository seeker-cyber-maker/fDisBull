"""Prepared source hostile post-launch first actor/sprite pass."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_hostile_stationary import SOURCE as STATIONARY,lift_hostile_stationary
from .shadowrun_linked_heading import SOURCE as HEADING
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_hostile_attack_first.c'
def lift_hostile_attack_first(rom):
    lift_hostile_stationary(rom)
    files=(SOURCE.with_name('shadowrun_collision.c'),SOURCE.with_name('shadowrun_collision_resolve.c'),HEADING,STATIONARY,SOURCE);chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
      'kind':'source-bound-hostile-post-launch-first-pass','source_sha256':ROM_SHA256,
      'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
      'scope':'prepared hostile post-launch with attested extra actor pass and later target selection external'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
