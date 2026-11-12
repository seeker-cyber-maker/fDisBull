"""No-overlap guard for the source-order original actor collision scan."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_enemy_overlap.c'
def lift_enemy_overlap(rom):
    if len(rom)!=2097152 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256: raise ValueError('wrong reviewed ROM')
    raw=SOURCE.read_bytes()
    result=author_program(raw.decode(),evidence={'kind':'source-bound-no-overlap-actor-scan',
        'source_sha256':ROM_SHA256,'authoring_sha256':hashlib.sha256(raw).hexdigest(),
        'scope':'complete ten-slot source-order pair scan; overlapping pairs refused'})
    if SOURCE.read_bytes()!=raw:raise ValueError('authoring changed')
    return result
