"""Prepared hostile direct pursuit after its initial detour."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_hostile_path_finish import SOURCE as FINISH,lift_hostile_path_finish
from .shadowrun_hostile_north import SOURCE as NORTH
from .shadowrun_hostile_waypoint import SOURCE as WAYPOINT
from .shadowrun_hostile_follow import SOURCE as FOLLOW
from .shadowrun_hostile_pursuit import SOURCE as PURSUIT
from .shadowrun_linked_heading import SOURCE as HEADING
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_hostile_direct.c'
def lift_hostile_direct(rom):
    lift_hostile_path_finish(rom)
    files=(SOURCE.with_name('shadowrun_collision.c'),HEADING,PURSUIT,FOLLOW,WAYPOINT,NORTH,FINISH,SOURCE);chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
      'kind':'source-bound-hostile-direct-pursuit','source_sha256':ROM_SHA256,
      'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
      'scope':'prepared hostile direct pursuit, event10 and clear movement state'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
