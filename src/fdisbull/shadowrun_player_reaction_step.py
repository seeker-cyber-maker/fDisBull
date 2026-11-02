"""Projected stationary-player source reaction pass with explicit admission."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_player_reaction import SOURCE as REACTION,lift_player_reaction
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_player_reaction_step.c'
def lift_player_reaction_step(rom):
    lift_player_reaction(rom)
    files=(SOURCE.with_name('shadowrun_collision.c'),SOURCE.with_name('shadowrun_collision_resolve.c'),REACTION,SOURCE);chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
      'kind':'source-bound-player-reaction-step','source_sha256':ROM_SHA256,
      'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
      'scope':'stationary player wound pass; sound/sprite effects external; ACAE admission is a boundary'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
