"""Bounded linked-target heading using the reviewed original ROM tables."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_field_combat import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_linked_heading.c'
RANGES=((0x15d3c,0x15dcc,'8c4c3c953ae2d7fd09137371492c73ac23ed04c19ec330add800de5bf9b076e3'),
        (0x15df6,0x15e16,'51c5d98a30de167833625284b1a554cae3bffdea680a36164dcf306e39cb5e6c'),
        (0x15f96,0x16396,'621c6fa9344d64b96288813eaa135b9c5788e49fc29a413724f231fbd33a5f0d'))
def lift_linked_heading(rom):
    if len(rom)!=2097152 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256:
        raise ValueError('linked heading requires reviewed ROM')
    if any(hashlib.sha256(rom[a:b]).hexdigest()!=h for a,b,h in RANGES):
        raise ValueError('linked heading source range changed')
    raw=SOURCE.read_bytes()
    result=author_program(raw.decode(),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],
       evidence={'kind':'source-bound-reviewed-procedural-slice','source_sha256':ROM_SHA256,
         'ranges':[[a,b,h] for a,b,h in RANGES],'authoring_sha256':hashlib.sha256(raw).hexdigest(),
         'scope':'target direction and metric for signed-word deltas; does not select target or simulate projectile'})
    if SOURCE.read_bytes()!=raw:raise ValueError('heading source changed')
    return result

SPAWN_SOURCE=SOURCE.with_name('shadowrun_linked_spawn.c')
SPAWN_RANGES=((0x1509a,0x15118,'7709475bd9860d52a759f0f506f14969487a92d13826da062b5621eb02294135'),
 (0x15a4c,0x15a8c,'fb1e21d623f643313adf5b286cdd1ea2179318423a9330f9f0bc1767b0bcdcda'),
 (0x15e16,0x15f56,'6240eb7089b68249e3ee32ac7aa0f05878eba34cd2d558852229d9c1752aae0b'))
def lift_linked_spawn(rom):
    if len(rom)!=2097152 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256:
        raise ValueError('linked spawn requires reviewed ROM')
    if any(hashlib.sha256(rom[a:b]).hexdigest()!=h for a,b,h in SPAWN_RANGES):
        raise ValueError('linked spawn source range changed')
    raw=SPAWN_SOURCE.read_bytes()
    result=author_program(raw.decode(),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],
       evidence={'kind':'source-bound-reviewed-procedural-slice','source_sha256':ROM_SHA256,
         'ranges':[[a,b,h] for a,b,h in SPAWN_RANGES],'authoring_sha256':hashlib.sha256(raw).hexdigest(),
         'scope':'projectile initial offsets and velocity from an externally supplied heading; allocation and movement excluded'})
    if SPAWN_SOURCE.read_bytes()!=raw:raise ValueError('spawn source changed')
    return result

LINKED_MOTION_SOURCE=SOURCE.with_name('shadowrun_linked_motion.c')
def lift_linked_motion(rom):
    """Compose linked aim, projectile vector and shared terrain/actor gates."""
    from .shadowrun_field_combat import SOURCE as FIELD_SOURCE, lift_field_combat
    from .udl_shadowrun import lift_collision_check
    lift_linked_heading(rom);lift_linked_spawn(rom);lift_field_combat(rom);lift_collision_check(rom)
    files=(SOURCE.with_name('shadowrun_collision.c'),SOURCE.with_name('shadowrun_collision_resolve.c'),
           FIELD_SOURCE,SOURCE,SPAWN_SOURCE,LINKED_MOTION_SOURCE)
    chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(x.decode() for x in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],
      evidence={'kind':'source-bound-assisted-linked-projectile','source_sha256':ROM_SHA256,
                'authoring_sha256':[hashlib.sha256(x).hexdigest() for x in chunks],
                'scope':'linked aim/spawn/flight with caller-supplied actor state; AI, allocation lifecycle and rendering excluded'})
    if any(p.read_bytes()!=b for p,b in zip(files,chunks)):raise ValueError('linked motion source changed')
    return result
