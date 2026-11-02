"""Bounded original kind-8 hostile pursuit on a blocked corridor."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_hostile_pursuit.c'
def lift_hostile_pursuit(rom):
    if len(rom)!=2097152 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256:raise ValueError('wrong reviewed ROM')
    files=(SOURCE.with_name('shadowrun_collision.c'),SOURCE);chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
      'kind':'source-bound-prepared-hostile-corridor-pursuit','source_sha256':ROM_SHA256,
      'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
      'scope':'kind8/item10, horizontal target, north blocked corridor and west detour; unsupported branches refused'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
