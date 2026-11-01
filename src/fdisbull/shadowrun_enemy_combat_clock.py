"""Bounded combat-global start/countdown and ten-record reset."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_enemy_combat_clock.c'
def lift_enemy_combat_clock(rom):
    if len(rom)!=2097152 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256:raise ValueError('wrong reviewed ROM')
    raw=SOURCE.read_bytes()
    result=author_program(raw.decode(),evidence={'kind':'source-bound-combat-clock','source_sha256':ROM_SHA256,
      'authoring_sha256':hashlib.sha256(raw).hexdigest(), 'scope':'start and countdown/clear only; target-processing tail excluded'})
    if SOURCE.read_bytes()!=raw:raise ValueError('authoring changed')
    return result
