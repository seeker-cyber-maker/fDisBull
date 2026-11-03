"""Source-bound NPC screen-admission and target-cycling slice."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_world import SOURCE_SHA256

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_targeting.c'
SPANS = ((0x1dc4c, 0x1dd2e, '1a726071e8f8db6c38851380f62ba46afc07ae09832aa906c4936b8c28c5b24a'),
         (0x5a56, 0x5ac6, 'ba9a145a8fbdc577851680b93636c754a8ee3dd4fc3751b70113ad919178c33f'),
         (0x4618, 0x464e, 'fc74777406d33e1ed8d50c20c0fe6617e3a0370f245f0b19866f699564b2970a'),
         (0xacae, 0xad1a, 'e3b97026117e6ce4a568d4767c7103a060dd920d52f0e3ce46aaaf34e515a1d0'))


def lift_targeting(rom):
    if hashlib.sha256(rom).hexdigest() != SOURCE_SHA256 or any(
        hashlib.sha256(rom[a:b]).hexdigest() != digest for a,b,digest in SPANS):
        raise ValueError('Targeting requires the exact reviewed Shadowrun source')
    raw = SOURCE.read_bytes()
    result = author_program(raw.decode(), evidence={
        'kind': 'source-bound-targeting-slice', 'source_sha256': SOURCE_SHA256,
        'spans': [list(s) for s in SPANS], 'authoring_sha256': hashlib.sha256(raw).hexdigest(),
        'scope': 'ordinary NPC target cycle and normal camera admission on supplied actor records',
        'unsupported': ['party-target branch', 'alternate target backlink', 'special d1 route',
                        'special callback 0x15390', 'NPC AI', 'line of sight', 'weapon range']})
    if SOURCE.read_bytes() != raw: raise ValueError('Targeting source changed during lifting')
    return result
