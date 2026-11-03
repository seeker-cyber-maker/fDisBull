"""Source-bound clear movement service for captured Shadowrun field actors."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .udl_shadowrun import ROM_SHA256,lift_collision_check
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_enemy_move.c'
RANGES=((0xb530,0xb732,'6431182139e865f468d3ccea6f08784c5d5bff3d7c3711543d5c150eef7b1a16'),
 (0xb77e,0xb7b8,'259ebf783d5b0a785b170e4f31fe87b326d1f664f9d49e819a9272578850b775'),
 (0xbade,0xbb0a,'1ba787f860ec420fae270f700e3f728b794605fe91ca5b45b113e99d855a76d8'),
 (0xbbe4,0xbbf6,'44ca9e06f1a9b4c4a7da2aab3e1054e55fc32f4436780d8ca14892b10474d907'),
 (0xb48c,0xb49c,'1470f688c21cd144825cd67a06b29fc1142f6691f91706a921ac6752c21e93c0'),
 (0xbd72,0xc082,'1fa9fad99da029bd3b188b0b8de3f544ed8a14627059489fabc460892ccfcb44'))
def lift_enemy_move(rom):
    if len(rom)!=2097152 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256:raise ValueError('wrong reviewed ROM')
    if any(hashlib.sha256(rom[a:b]).hexdigest()!=h for a,b,h in RANGES):raise ValueError('enemy movement source changed')
    lift_collision_check(rom)
    files=(SOURCE.with_name('shadowrun_collision.c'),SOURCE.with_name('shadowrun_collision_resolve.c'),SOURCE)
    chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(x.decode() for x in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],
      evidence={'kind':'source-bound-reviewed-enemy-clear-movement','source_sha256':ROM_SHA256,
        'ranges':[[a,b,h] for a,b,h in RANGES],'authoring_sha256':[hashlib.sha256(x).hexdigest() for x in chunks],
        'scope':'captured type-11 actor B574 clear-terrain service; waypoint/decision, fallback, events and attack excluded'})
    if any(p.read_bytes()!=x for p,x in zip(files,chunks)):raise ValueError('authoring changed')
    return result
