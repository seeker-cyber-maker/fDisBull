"""Selected actor loop, projected onto the reviewed movement read set."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_enemy_outer import SOURCE as OUTER, lift_enemy_outer
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_enemy_projection.c'
def lift_enemy_projection(rom):
    lift_enemy_outer(rom)
    chunks=[p.read_bytes() for p in (OUTER,SOURCE)]
    result=author_program('\n'.join(c.decode() for c in chunks),evidence={
        'kind':'source-bound-actor-loop-movement-projection', 'source_sha256':ROM_SHA256,
        'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
        'scope':'selected +B3 explicitly unknown; reviewed no-overlap movement projection only'})
    if any(p.read_bytes()!=c for p,c in zip((OUTER,SOURCE),chunks)):raise ValueError('authoring changed')
    return result
