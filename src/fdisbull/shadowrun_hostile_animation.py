"""Source sprite-pass animation boundary for item-10 projectile impacts."""
import hashlib
from pathlib import Path

from .game_il import author_program
from .shadowrun_world import SOURCE_SHA256

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_hostile_animation.c'
SPANS = ((0x5fdc, 0x60ae, 'a467f65e086100d748cc9c26950a800d14c2a29a0c7f70d50a9380cd3454827a'),
         (0x62b0, 0x62b4, 'a5426ff4ebd130c4201e502700e9a254d9663a91416c46a7bb284be02a9f8526'),
         (0x634c, 0x6364, '868d54cbdd0c2cc40026bebd0c555bf1a2ad7d2afcf703e15a3266a4b7b34399'),
         (0x7320, 0x7380, '4dbe02e36111e6b291af167040e997b24a1414c0ddfea28ec876219aa1708f48'))


def lift_hostile_animation(rom):
    if hashlib.sha256(rom).hexdigest() != SOURCE_SHA256 or any(
        hashlib.sha256(rom[a:b]).hexdigest() != digest for a, b, digest in SPANS
    ):
        raise ValueError('Hostile animation requires the exact reviewed Shadowrun source')
    raw = SOURCE.read_bytes()
    result = author_program(raw.decode(), evidence={
        'kind': 'source-bound-hostile-impact-sprite-pass', 'source_sha256': SOURCE_SHA256,
        'spans': [list(s) for s in SPANS], 'authoring_sha256': hashlib.sha256(raw).hexdigest(),
        'scope': 'kind1 projectile flight/impact counter and negative-count table selector',
        'unsupported': ['sprite-pass scheduling', 'graphics upload', 'other animation tables',
                        'natural encounter'],
    })
    if SOURCE.read_bytes() != raw:
        raise ValueError('Hostile animation source changed during lifting')
    return result
