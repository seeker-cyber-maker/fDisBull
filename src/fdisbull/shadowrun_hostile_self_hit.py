"""Prepared hostile item10 self-impact damage projection."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_hostile_self_hit.c'
def lift_hostile_self_hit(rom):
    if len(rom)!=2097152 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256:raise ValueError('wrong reviewed ROM')
    raw=SOURCE.read_bytes()
    result=author_program(raw.decode(),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
      'kind':'source-bound-prepared-hostile-self-hit','source_sha256':ROM_SHA256,
      'authoring_sha256':hashlib.sha256(raw).hexdigest(),
      'scope':'item10 projectile against constructed kind8 armor3 target; reaction and death removal excluded'})
    if SOURCE.read_bytes()!=raw:raise ValueError('authoring changed')
    return result
