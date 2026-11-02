"""Prepared moving-origin hostile bounded idle service."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_hostile_stationary import lift_hostile_stationary
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_hostile_moving_idle_18.c'
def lift_hostile_moving_idle_18(rom):
    lift_hostile_stationary(rom)
    names=('shadowrun_collision.c','shadowrun_collision_resolve.c','shadowrun_linked_heading.c','shadowrun_hostile_stationary.c','shadowrun_hostile_moving_idle_18.c')
    files=[SOURCE.with_name(n) for n in names];chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={'kind':'source-bound-moving-origin-idle-18','source_sha256':ROM_SHA256,'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],'scope':'prepared moving-origin hostile idle between services; expiry separate'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
