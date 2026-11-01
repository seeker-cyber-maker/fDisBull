"""Source item-10 burst transition at an already qualified animation boundary."""
import hashlib
from pathlib import Path

from .game_il import author_program
from .shadowrun_world import SOURCE_SHA256

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_hostile_burst.c'
SPANS = ((0x14f1c, 0x14f26, 'bde2c3d119db74d56cceb5cf43fea49e20005cc314155f6e201e2ff0d32d52d4'),
         (0x14f86, 0x14ff8, 'd279992a91738cf2e152ff0d008036ceb27402ad2013cc46865f22bf65446832'),
         (0x150e8, 0x15118, '25d9d3af35fc11e458eb468f57a66af62e4764cd51248969ba50eb5e07cb244d'),
         (0x55640, 0x55828, 'b573b453517c1a63099933a16de01eade925f1bcf0a9cface3e697f6086f4031'),
         (0xd3a, 0xdfc, '4fb5074cc53d2a74ba2cf0dc8c41f7da12824dbd4cb696d3766a045eecef8966'))


def lift_hostile_burst(rom):
    if hashlib.sha256(rom).hexdigest() != SOURCE_SHA256 or any(
        hashlib.sha256(rom[a:b]).hexdigest() != digest for a, b, digest in SPANS
    ):
        raise ValueError('Hostile burst requires the exact reviewed Shadowrun source')
    raw = SOURCE.read_bytes()
    result = author_program(raw.decode(), evidence={
        'kind': 'source-bound-hostile-burst-transition', 'source_sha256': SOURCE_SHA256,
        'spans': [list(s) for s in SPANS], 'authoring_sha256': hashlib.sha256(raw).hexdigest(),
        'scope': 'item-10 burst entry after the source animation boundary',
        'unsupported': ['animation clock', 'wounded attacker', 'other projectile or weapon profiles',
                        'natural encounter'],
    })
    if SOURCE.read_bytes() != raw:
        raise ValueError('Hostile burst source changed during lifting')
    return result
