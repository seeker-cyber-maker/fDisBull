"""Bounded prepared hostile movement and sprite clock between services."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_hostile_move import lift_hostile_move
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_hostile_pursuit_route.c'
def lift_hostile_pursuit_route(rom):
    lift_hostile_move(rom)
    names=('shadowrun_collision.c','shadowrun_collision_resolve.c','shadowrun_enemy_move.c','shadowrun_hostile_move.c','shadowrun_hostile_pursuit_route.c')
    files=[SOURCE.with_name(n) for n in names];chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={'kind':'source-bound-prepared-hostile-pursuit-route','source_sha256':ROM_SHA256,'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],'scope':'prepared actor clear B574 movement between service calls; sprite transfer external'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
