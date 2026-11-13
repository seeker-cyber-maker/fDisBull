"""Source-projected sprite-only first pass and no-input reaction recovery."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_player_reaction import SOURCE as REACTION,lift_player_reaction
from .shadowrun_player_reaction_step import SOURCE as STEP
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_player_reaction_resume.c'
def lift_player_reaction_resume(rom):
    lift_player_reaction(rom)
    files=(SOURCE.with_name('shadowrun_collision.c'),SOURCE.with_name('shadowrun_collision_resolve.c'),REACTION,STEP,SOURCE);chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
      'kind':'source-bound-player-reaction-no-input-resume','source_sha256':ROM_SHA256,
      'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
      'scope':'stationary captured party, sprite-only first hit and no-input idle continuation; graphics/audio external'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
