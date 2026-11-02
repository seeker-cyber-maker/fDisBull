"""Prepared hostile continuation along an existing source path."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_hostile_pursuit import SOURCE as PURSUIT,lift_hostile_pursuit
from .shadowrun_linked_heading import SOURCE as HEADING,lift_linked_heading
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_hostile_follow.c'
def lift_hostile_follow(rom):
    lift_hostile_pursuit(rom);lift_linked_heading(rom)
    files=(SOURCE.with_name('shadowrun_collision.c'),HEADING,PURSUIT,SOURCE);chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
      'kind':'source-bound-hostile-path-follow','source_sha256':ROM_SHA256,
      'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
      'scope':'existing same-row westward detour, positive pursuit counter; alternate branches refused'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
