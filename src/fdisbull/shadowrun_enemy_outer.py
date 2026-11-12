"""Bounded actor-loop dispatch prefix; register input must be source-derived."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_enemy_outer.c'
def lift_enemy_outer(rom):
    if len(rom)!=2097152 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256: raise ValueError('wrong reviewed ROM')
    raw=SOURCE.read_bytes()
    program=author_program(raw.decode(), evidence={'kind':'source-bound-captured-actor-loop-prefix',
        'source_sha256':ROM_SHA256,'authoring_sha256':hashlib.sha256(raw).hexdigest(),
        'scope':'actor-loop prefix; caller supplies original entry D0 and separately handles collision and callback'})
    if SOURCE.read_bytes()!=raw: raise ValueError('authoring changed')
    return program
