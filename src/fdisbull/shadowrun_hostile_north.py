"""Prepared hostile northward follow of the second source waypoint."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_hostile_waypoint import SOURCE as WAYPOINT,lift_hostile_waypoint
from .shadowrun_hostile_follow import SOURCE as FOLLOW
from .shadowrun_hostile_pursuit import SOURCE as PURSUIT
from .shadowrun_linked_heading import SOURCE as HEADING
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_hostile_north.c'
def lift_hostile_north(rom):
    lift_hostile_waypoint(rom)
    files=(SOURCE.with_name('shadowrun_collision.c'),HEADING,PURSUIT,FOLLOW,WAYPOINT,SOURCE);chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
      'kind':'source-bound-hostile-north-follow','source_sha256':ROM_SHA256,
      'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
      'scope':'prepared hostile second waypoint northward follow; other path branches refused'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
