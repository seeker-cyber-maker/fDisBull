"""Prepared hostile firing pose and stationary scheduler branch."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_linked_heading import SOURCE as HEADING,lift_linked_heading
from .udl_shadowrun import ROM_SHA256,lift_collision_check
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_hostile_stationary.c'
def lift_hostile_stationary(rom):
    if len(rom)!=2097152 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256:raise ValueError('wrong reviewed ROM')
    lift_collision_check(rom);lift_linked_heading(rom)
    files=(SOURCE.with_name('shadowrun_collision.c'),SOURCE.with_name('shadowrun_collision_resolve.c'),HEADING,SOURCE);chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
      'kind':'source-bound-hostile-stationary-firing-pose','source_sha256':ROM_SHA256,
      'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
      'scope':'kind8/item10 source firing pose and DFDE-active stationary expiry; selected B3, audio and sprite uploads external'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
