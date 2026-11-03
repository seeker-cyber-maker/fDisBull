"""Bounded held-direction admission after a source party stagger."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_player_reaction_resume import lift_player_reaction_resume
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_player_reaction_direction.c'
def lift_player_reaction_direction(rom):
    lift_player_reaction_resume(rom)
    names=('shadowrun_collision.c','shadowrun_collision_resolve.c','shadowrun_player_reaction.c',
           'shadowrun_player_reaction_step.c','shadowrun_player_reaction_resume.c','shadowrun_player_reaction_direction.c')
    files=[SOURCE.with_name(n) for n in names];chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={'kind':'source-bound-party-held-direction-recovery','source_sha256':ROM_SHA256,'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],'scope':'captured party left-direction recovery admission; movement and sprite clock separate'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
