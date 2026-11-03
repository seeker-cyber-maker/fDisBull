"""A narrowly bounded, source-constructed hostile actor firing slice."""
import hashlib
from pathlib import Path

from .game_il import author_program
from .shadowrun_world import SOURCE_SHA256

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_hostile.c'
SPANS = (
    (0xa8fc, 0xaa74, 'd48f07757623db152568388bdb56257a427a055c8759fb863d0881c334e2e654'),
    (0xac84, 0xac9e, '3da8fe14d8826cd54e51102857837913c8f8f16a4e2a12be6e543379144c5066'),
    (0x13904, 0x139e4, '8ca11be17e230bf2d758f990ce1afc13c1a57fa89cc3444d1f29ea2fd2993023'),
    (0x13ffe, 0x14146, '3f604ffcff3a7bdc05ee272e52c63ecfe6619db1e9abee14ef584ef1082cb4f0'),
    (0x14492, 0x144e8, '10a2acd9064feaffc5dfb6a263cee92ac47fc621bf06260064f75b4e6d20bccc'),
    (0x14d8e, 0x14e0a, '03b6bfebc0d75c634f2b47b5c812c65b203bf9db4d74c654b5d85a164736c347'),
    (0x14f26, 0x14f50, '3c90a201fdce7a47df99c043e201b609db6d3561ba4042c5b700c78ca3d8d3cc'),
    (0xe7c8, 0xe8d6, 'b7399c520dcaf8a4386cf1a4a435e6e50404fc23bd77b9e0c8572969fd4b9445'),
    (0x15aba, 0x15bb4, 'd5f8b5a164716a92d1a7353d20a4c12685152bbee13f83940a1251517b311362'),
    (0x14ff8, 0x151da, '8614628c4e97e1266cc20a841c714e0ba4830e1830ed6ae96079a634129df10a'),
    (0x151da, 0x151ea, '524fae880ea240795300585bfb1ddc6f62fae90926578cc297fd72e68dfef135'),
    (0x152fa, 0x15318, '85a55b3258b8823d84bcfc4e67fa90cdbb3285729dc33c6da16aee77565a768f'),
    (0x55640, 0x55828, 'b573b453517c1a63099933a16de01eade925f1bcf0a9cface3e697f6086f4031'),
    (0xd3a, 0xdfc, '4fb5074cc53d2a74ba2cf0dc8c41f7da12824dbd4cb696d3766a045eecef8966'),
    (0x15d3c, 0x16000, '01144f301abc02643f3efa045ed994069542da7b35353a5cb731df15042f07bd'),
    (0x1d66ee, 0x1d674c, '9f5fd0bdd2c27c5a68222cfbc0fa5a1c33e665733b1974e993d998c6482873b2'),
)


def lift_hostile(rom):
    if hashlib.sha256(rom).hexdigest() != SOURCE_SHA256 or any(
        hashlib.sha256(rom[a:b]).hexdigest() != digest for a, b, digest in SPANS
    ):
        raise ValueError('Hostile slice requires the exact reviewed Shadowrun source')
    raw = SOURCE.read_bytes()
    result = author_program(raw.decode(), evidence={
        'kind': 'source-constructed-hostile-actor-slice', 'source_sha256': SOURCE_SHA256,
        'spans': [list(s) for s in SPANS], 'authoring_sha256': hashlib.sha256(raw).hexdigest(),
        'scope': 'actor tick, sight and primary projectile setup before secondary allocation',
        'unsupported': ['natural encounter', 'scene loading', 'complex slope and rectangle terrain',
                        'other actor profiles', 'empty ammunition', 'blocked visibility',
                        'other target lists', 'secondary actor', 'projectile bursts', 'player damage'],
    })
    if SOURCE.read_bytes() != raw:
        raise ValueError('Hostile source changed during lifting')
    return result
