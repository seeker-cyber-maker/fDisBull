"""Prepared linked player projectile against source-constructed hostile."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_linked_heading import lift_linked_motion
from .shadowrun_hostile_received_hit import lift_hostile_received_hit
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_hostile_linked.c'
def lift_hostile_linked(rom):
    lift_linked_motion(rom);lift_hostile_received_hit(rom)
    files=tuple(SOURCE.with_name(x) for x in ('shadowrun_collision.c','shadowrun_collision_resolve.c',
      'shadowrun_field_action.c','shadowrun_linked_heading.c','shadowrun_linked_spawn.c','shadowrun_linked_motion.c',
      'shadowrun_hostile_received_hit.c','shadowrun_hostile_linked.c'))
    chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
      'kind':'source-bound-prepared-hostile-linked-projectile','source_sha256':ROM_SHA256,
      'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
      'scope':'prepared source player linked projectile and type2 hostile; actor death reaction excluded'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
