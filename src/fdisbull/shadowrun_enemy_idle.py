"""Bounded source-derived captured NPC idle callback."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_enemy_waypoint import lift_enemy_waypoint, SOURCE as WAYPOINT
from .shadowrun_enemy_service import SOURCE as SERVICE
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_enemy_idle.c'
def lift_enemy_idle(rom):
    lift_enemy_waypoint(rom)
    files=(SOURCE.with_name('shadowrun_collision.c'),SOURCE.with_name('shadowrun_collision_resolve.c'),
           SOURCE.with_name('shadowrun_enemy_move.c'),SOURCE.with_name('shadowrun_linked_heading.c'), SERVICE, WAYPOINT, SOURCE)
    chunks=[p.read_bytes() for p in files]
    program=author_program('\n'.join(x.decode() for x in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],
        evidence={'kind':'source-bound-captured-idle-callback','source_sha256':ROM_SHA256,
                  'authoring_sha256':[hashlib.sha256(x).hexdigest() for x in chunks],
                  'scope':'captured type-11 idle callback; no attack or decision dispatch'})
    if any(p.read_bytes()!=x for p,x in zip(files,chunks)):raise ValueError('authoring changed')
    return program
