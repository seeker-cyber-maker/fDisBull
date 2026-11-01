"""Bounded hostile projectile tick before the separate player-damage leaf."""
import hashlib
from pathlib import Path

from .game_il import author_program
from .shadowrun_world import SOURCE_SHA256

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_hostile_motion.c'
SPANS = ((0x14e0a, 0x14e82, 'e215457f73d59ff9450cf59613f2c6925a371b53a79350b420e2e63db70a9ee0'),
         (0x14f26, 0x14f86, 'f0768e55a0b3bccd2768fc30363ae1b7ea841d077c50520db1f6892ffa5eb3e3'),
         (0x14f86, 0x14ff8, 'd279992a91738cf2e152ff0d008036ceb27402ad2013cc46865f22bf65446832'),
         (0x15aba, 0x15bb4, 'd5f8b5a164716a92d1a7353d20a4c12685152bbee13f83940a1251517b311362'),
         (0xe7c8, 0xe8d6, 'b7399c520dcaf8a4386cf1a4a435e6e50404fc23bd77b9e0c8572969fd4b9445'))


def lift_hostile_motion(rom):
    if hashlib.sha256(rom).hexdigest() != SOURCE_SHA256 or any(
        hashlib.sha256(rom[a:b]).hexdigest() != digest for a, b, digest in SPANS
    ):
        raise ValueError('Hostile motion requires the exact reviewed Shadowrun source')
    raw = SOURCE.read_bytes()
    result = author_program(raw.decode(), evidence={
        'kind': 'source-bound-hostile-projectile-slice', 'source_sha256': SOURCE_SHA256,
        'spans': [list(s) for s in SPANS], 'authoring_sha256': hashlib.sha256(raw).hexdigest(),
        'scope': 'up to four projectile substeps through player/shooter contact or termination',
        'unsupported': ['complex terrain', 'other non-player actor hits', 'damage and death', 'projectile bursts',
                        'impact rendering', 'natural encounter'],
    })
    if SOURCE.read_bytes() != raw:
        raise ValueError('Hostile motion source changed during lifting')
    return result
