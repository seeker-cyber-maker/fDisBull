"""Prepared hostile service with a depleted activity counter."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_hostile_relaunch import lift_hostile_relaunch
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_hostile_zero_counter.c'

def lift_hostile_zero_counter(rom):
    lift_hostile_relaunch(rom)
    names=('shadowrun_collision.c','shadowrun_collision_resolve.c','shadowrun_linked_heading.c',
           'shadowrun_hostile_stationary.c','shadowrun_hostile_relaunch.c',
           'shadowrun_hostile_idle_service.c','shadowrun_hostile_expired_pose.c','shadowrun_hostile_zero_counter.c')
    files=[SOURCE.with_name(n) for n in names];chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),
        [{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
        'kind':'source-bound-hostile-zero-activity-counter','source_sha256':ROM_SHA256,
        'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],
        'scope':'prepared stationary hostile zero-counter service and relaunch pose; other services excluded'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
