"""Captured party held-DOWN recovery from combat stagger."""
import hashlib
from pathlib import Path
from .game_il import author_program,emit_c
from .shadowrun_player_combat_slide import lift_player_combat_slide
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_player_reaction_direction_down.c'
def lift_player_reaction_direction_down(rom):
    raw=SOURCE.read_bytes();base=lift_player_combat_slide(rom)
    result=author_program(emit_c(base)+'\n'+raw.decode(),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={'kind':'source-bound-player-down-recovery','source_sha256':ROM_SHA256,'authoring_sha256':hashlib.sha256(raw).hexdigest(),'scope':'held DOWN after party stagger and expired action timer; walking and sprite separate'})
    if SOURCE.read_bytes()!=raw:raise ValueError('authoring changed')
    return result
