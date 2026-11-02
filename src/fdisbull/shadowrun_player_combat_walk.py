"""Captured party clear movement during source combat mode."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .udl_shadowrun import ROM_SHA256, lift_player_move_proposal
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_player_combat_walk.c'
def lift_player_combat_walk(rom):
    lift_player_move_proposal(rom)
    names=('shadowrun_collision.c','shadowrun_collision_resolve.c','shadowrun_player_move.c','shadowrun_player_walk.c','shadowrun_player_combat_walk.c')
    files=[SOURCE.with_name(n) for n in names];chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={'kind':'source-bound-player-combat-walk','source_sha256':ROM_SHA256,'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],'scope':'captured party attribute3 nonzero combat mode and clear source movement; fallback excluded'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
