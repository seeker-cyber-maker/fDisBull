"""Contact-visible, facing-away movement-service projection."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_enemy_service import SOURCE as SERVICE,lift_enemy_service
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_enemy_visible.c'
def lift_enemy_visible(rom):
    lift_enemy_service(rom)
    files=(SOURCE.with_name('shadowrun_collision.c'),SOURCE.with_name('shadowrun_collision_resolve.c'),
        SOURCE.with_name('shadowrun_enemy_move.c'),SOURCE.with_name('shadowrun_linked_heading.c'),SERVICE,SOURCE)
    chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
        'kind':'source-bound-visible-facing-away-service-projection','source_sha256':ROM_SHA256,
        'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
        'scope':'contact-visible actor, class<=2, facing away; visibility scratch omitted'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
