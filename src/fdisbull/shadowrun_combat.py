"""Two original attack-stat leaves, with preceding helper values explicit."""
import hashlib
from pathlib import Path
from .game_il import author_program
ROM_SHA256='92a614491fc3ea12a6df32459cce08b48574b7b814e244c07eb860dc5c6edb7e'
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_combat.c'
RANGES=((0x55a62,0x55a9e,'19d3d2dbc395843d25d242e246a1f648531674211bdfb3d71ce717fab9f80a0f'),
        (0x559ce,0x559f4,'39f6a7dca4af425213c2c43c3a71fcc7d8f79e33d31302ac074521a858cd093b'),
        (0x55c80,0x55c96,'52b3f3bc723421e2025f0ccf950dac8db9e308a40a1d38e869280d1300fbe641'),
        (0x11ae4,0x11b0e,'1668674a4d640bbd09d772e457aa4eb09e2c1dc4a1272a6e28efefd6ca37eede'),
        (0x12dd2,0x12dec,'1468abe4f85cbbad5fc8bfd96ac64d3799ad9e41a12adb3925ff699b483d5381'),
        (0x12d46,0x12d60,'d8e10436ca01f085e956aef895016f078a653934127cbbedd53c0ff773149703'))
def lift_combat(rom):
    if len(rom)!=2097152 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256:
        raise ValueError('combat requires the exact reviewed Shadowrun ROM')
    for lo,hi,digest in RANGES:
        if hashlib.sha256(rom[lo:hi]).hexdigest()!=digest:
            raise ValueError('combat source range changed')
    raw=SOURCE.read_bytes()
    result=author_program(raw.decode(),evidence={'kind':'source-bound-reviewed-procedural-slice',
        'source_sha256':ROM_SHA256,'ranges':[[lo,hi,d] for lo,hi,d in RANGES],
        'authoring_sha256':hashlib.sha256(raw).hexdigest(),
        'scope':'bounded normal attack-stat leaves with nonnegative baseline; helper, dispatch and combat consumers excluded'})
    if SOURCE.read_bytes()!=raw: raise ValueError('combat source changed during capture')
    return result
