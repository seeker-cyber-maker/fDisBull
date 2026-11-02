"""Source-bound expired LEFT recovery and north-wall west slide."""
import hashlib
from pathlib import Path
from .game_il import author_program,emit_c
from .shadowrun_assisted_arena import lift_assisted_arena
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_player_combat_slide.c'
DIRECTION=SOURCE.with_name('shadowrun_player_reaction_direction_expired.c')
def lift_player_combat_slide(rom):
    base=lift_assisted_arena(rom);parts=[DIRECTION.read_bytes(),SOURCE.read_bytes()]
    existing=emit_c(base);extra=[raw.decode() for name,raw in zip(('shadowrun_reaction_resume_direction_expired','shadowrun_player_combat_slide'),parts) if ('void '+name+'(') not in existing]
    result=author_program(existing+'\n'+'\n'.join(extra),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={'kind':'source-bound-player-combat-west-wall-slide','source_sha256':ROM_SHA256,'authoring_sha256':[hashlib.sha256(x).hexdigest() for x in parts],'scope':'expired leftward reaction admission and north-wall west slide; other collision branches refused'})
    if any(p.read_bytes()!=x for p,x in zip((DIRECTION,SOURCE),parts)):raise ValueError('authoring changed')
    return result
