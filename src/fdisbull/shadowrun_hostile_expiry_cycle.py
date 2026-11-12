"""Bounded source projectile lifetime-expiry continuation."""
import hashlib
from pathlib import Path
from .game_il import author_program,emit_c
from .shadowrun_hostile_cycle import lift_hostile_cycle
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_hostile_expiry_cycle.c'
def lift_hostile_expiry_cycle(rom):
    base=lift_hostile_cycle(rom);raw=SOURCE.read_bytes()
    result=author_program(emit_c(base)+'\n'+raw.decode(),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={'kind':'source-bound-hostile-projectile-expiry','source_sha256':ROM_SHA256,'authoring_sha256':hashlib.sha256(raw).hexdigest(),'scope':'prepared item10 effect 0 or 1 projectile lifetime expiry, single sprite pass; caller owns rollback and further burst'})
    if SOURCE.read_bytes()!=raw:raise ValueError('authoring changed')
    return result
