"""Bounded north-facing combat wall stop after a refused clear step."""
import hashlib
from pathlib import Path
from .game_il import author_program,emit_c
from .udl_shadowrun import ROM_SHA256,lift_opening_walk
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_player_combat_wall.c'
def lift_player_combat_wall(rom):
    base=lift_opening_walk(rom);parts=[SOURCE.with_name('shadowrun_player_combat_walk.c').read_bytes(),SOURCE.read_bytes()]
    result=author_program(emit_c(base)+'\n'+'\n'.join(x.decode() for x in parts),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={'kind':'source-bound-player-combat-north-wall','source_sha256':ROM_SHA256,'authoring_sha256':[hashlib.sha256(x).hexdigest() for x in parts],'scope':'northward source combat wall stop when both leading corner probes block; other collision and events refused'})
    if SOURCE.read_bytes()!=parts[-1]:raise ValueError('authoring changed')
    return result
