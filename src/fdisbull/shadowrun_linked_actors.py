"""Captured-actor, source-order linked projectile composition."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_field_combat import ROM_SHA256,SOURCE as FIELD_SOURCE
from .shadowrun_linked_heading import SOURCE as HEADING_SOURCE,SPAWN_SOURCE,LINKED_MOTION_SOURCE,lift_linked_motion
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_linked_actors.c'
# Standalone lift input declarations; the NES composition supplies these from
# its targeting and play state rather than defining a second copy.
SHIM='''typedef unsigned char u8; typedef unsigned int u16;
u16 shadowrun_target_x[7],shadowrun_target_y[7];
u8 shadowrun_target_flags[7],shadowrun_target_flags_b0[7];
u8 shadowrun_target_selected,shadowrun_play_actor_hp[7];'''
def lift_linked_actors(rom):
    lift_linked_motion(rom)
    files=(FIELD_SOURCE.with_name('shadowrun_collision.c'),FIELD_SOURCE.with_name('shadowrun_collision_resolve.c'),
           FIELD_SOURCE,HEADING_SOURCE,SPAWN_SOURCE,LINKED_MOTION_SOURCE,SOURCE)
    chunks=[p.read_bytes() for p in files]
    units=[x.decode() for x in chunks[:-1]]+[SHIM,chunks[-1].decode()]
    result=author_program('\n'.join(units),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],
      evidence={'kind':'source-bound-captured-actor-adapter','source_sha256':ROM_SHA256,
       'authoring_sha256':[hashlib.sha256(x).hexdigest() for x in chunks],
       'scope':'source-order projectile candidates among three captured actor profiles; AI, animation and other actor types excluded'})
    if any(p.read_bytes()!=b for p,b in zip(files,chunks)):raise ValueError('actor adapter source changed')
    return result
