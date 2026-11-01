"""Source-bounded offscreen civilian eastward wall slide."""
import hashlib
from pathlib import Path
from .game_il import author_program,emit_c
from .shadowrun_enemy_idle import lift_enemy_idle
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_enemy_east_slide.c'
def lift_enemy_east_slide(rom):
    raw=SOURCE.read_bytes(); extra=SOURCE.with_name('shadowrun_enemy_east_slide_exit.c').read_bytes(); base=lift_enemy_idle(rom)
    result=author_program(emit_c(base)+'\n'+raw.decode()+'\n'+extra.decode(),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={'kind':'source-bound-enemy-east-wall-slide','source_sha256':ROM_SHA256,'authoring_sha256':hashlib.sha256(raw).hexdigest(),'scope':'captured offscreen civilian eastward terrain fallback; other directions refused'})
    if SOURCE.read_bytes()!=raw:raise ValueError('authoring changed')
    return result
