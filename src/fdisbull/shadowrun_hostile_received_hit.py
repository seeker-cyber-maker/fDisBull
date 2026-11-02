"""Prepared hostile kind8/type2 received-hit and depletion projection."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_field_combat import SOURCE as FIELD,lift_field_combat,ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_hostile_received_hit.c'
def lift_hostile_received_hit(rom):
    lift_field_combat(rom)
    files=(FIELD,SOURCE);chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
      'kind':'source-bound-prepared-hostile-received-hit','source_sha256':ROM_SHA256,
      'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
      'scope':'prepared kind8/type2 exact defense profile at positive-effect hit; armor item3 read from source ROM'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
