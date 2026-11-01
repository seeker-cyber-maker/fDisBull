"""Bounded civilian actor prefix while sliding east."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_enemy_outer import SOURCE as OUTER
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_enemy_outer_slide.c'
def lift_enemy_outer_slide(rom):
    if len(rom)!=2097152 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256:raise ValueError('wrong source')
    parts=[OUTER,SOURCE.with_name('shadowrun_enemy_projection.c'),SOURCE]; chunks=[p.read_bytes() for p in parts]
    result=author_program('\n'.join(x.decode() for x in chunks),evidence={'kind':'source-bound-enemy-outer-slide','source_sha256':ROM_SHA256,'authoring_sha256':[hashlib.sha256(x).hexdigest() for x in chunks]})
    if any(p.read_bytes()!=x for p,x in zip(parts,chunks)):raise ValueError('authoring changed')
    return result
