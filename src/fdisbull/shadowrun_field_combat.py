"""Bounded prepared Shadowrun projectile encounter, not ordinary dispatch."""
import hashlib
from pathlib import Path
from .game_il import author_program

ROM_SHA256 = '92a614491fc3ea12a6df32459cce08b48574b7b814e244c07eb860dc5c6edb7e'
SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_field_action.c'
RANGES = ((0x1517a,0x151be,'e3fff9de16fbc96690a13818d2f988e33686581a551750cd412c7b806001b1d0'),
 (0x38ac,0x38fa,'2480aa01389909ca4b0c5a22fb508b7ddd99aa82f3427e7a6acbc1917172057b'),
 (0x15a8c,0x15aba,'5ea7f76c9d00e23dc3ed5cced82dc1f11ff33ec69264c579084384adb5ebfc2c'),
 (0x15aba,0x15bb4,'d5f8b5a164716a92d1a7353d20a4c12685152bbee13f83940a1251517b311362'),
 (0x14e6e,0x14e88,'713fdebe5ce9dab772576dff2cc123463a90f513e554c4a4077f43d88ee00e20'),
 (0x55948,0x55ab0,'eb91edc71a6d763ee409e61a2f5b593c710d439bad2b10848978e110d36faa29'),
 (0x55e62,0x55f44,'04aec1e9026c38cd7791e5a172a9365aef73ce2a7f53085902f4a07c428a3f96'),
 (0xd3a,0xdfc,'4fb5074cc53d2a74ba2cf0dc8c41f7da12824dbd4cb696d3766a045eecef8966'),
 (0xd4540,0xd4570,'eafefdd6440ef43b2f4e40b4915252f5c5ecc7f9d54ef97003ec35ee7e94b7e6'),
 (0x166ad4,0x166ad6,'e37ebf9386af53684064f4c6053faf2ee35662571e72eabdad46108d841bd892'),
 (0x55786,0x55848,'02dd91efed773a54f6ed552f4ab08ac35b54541063750fa294f83db312b71cdd'),
 (0x36fc,0x37d4,'c0834853610446e2114849c157717f454cbfd39928753d30028d336fa4fc0a64'),
 (0xd4570,0xd45a0,'4f8f360aa48ab6b5428fae63b6f2363289c95d181f7bc185ee78d175bfa65fb0'),
 (0x55640,0x55740,'e12ef9e23209ce27b83347623fef5f6995cc398b37caf6e46738cff8d1b9a70f'),
 (0x12c74,0x12cd6,'3098cac932e02a2d1855321f850de80e733c741b7947c2ddddaa8383de87a27d'),
 (0x14ff8,0x1514e,'321d7c1d0934ec22459c5081259e4c4973d7bc0e13243b5fce8cc42fff0c814f'),
 (0x1dbaa,0x1dbf0,'c49d7a42d5d4fad08e49edfb21e991d152c69082037f1ed6c6a9c69ecf91b397'))

def lift_field_combat(rom):
    if len(rom) != 2097152 or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('field combat requires the reviewed ROM')
    for lo, hi, digest in RANGES:
        if hashlib.sha256(rom[lo:hi]).hexdigest() != digest:
            raise ValueError('field combat source range changed')
    raw = SOURCE.read_bytes()
    result = author_program(raw.decode(), evidence={'kind':'source-bound-reviewed-procedural-slice',
        'source_sha256':ROM_SHA256, 'ranges':[[lo,hi,d] for lo,hi,d in RANGES],
        'authoring_sha256':hashlib.sha256(raw).hexdigest(),
        'scope':'prepared party or index 3, item 1 or 2, precomputed projectile collision; dispatcher, motion and zero-health continuation excluded'})
    if SOURCE.read_bytes() != raw:
        raise ValueError('field source changed during capture')
    return result

MOTION_SOURCE = SOURCE.with_name('shadowrun_field_motion.c')
MOTION_RANGES = ((0x14e0a,0x14e6e,'e3a908648c722123c2c3b90ab3eb65dadc719e3588262b7293066647f83cf5c6'),
 (0x14f26,0x14f86,'f0768e55a0b3bccd2768fc30363ae1b7ea841d077c50520db1f6892ffa5eb3e3'),
 (0x15a4c,0x15a8c,'fb1e21d623f643313adf5b286cdd1ea2179318423a9330f9f0bc1767b0bcdcda'),
 (0x15e16,0x15ed8,'46fcf986ecfba890e99723960356fd5dd88f4e368e1f7a1d697a00562118a6d2'))

def lift_field_motion(rom):
    """Compose the captured-heading action and shared terrain collision."""
    from .udl_shadowrun import lift_collision_check
    lift_field_combat(rom)
    lift_collision_check(rom)  # validates the collision source and ROM spans
    if any(hashlib.sha256(rom[lo:hi]).hexdigest()!=digest for lo,hi,digest in MOTION_RANGES):
        raise ValueError('field motion source range changed')
    files = (SOURCE.with_name('shadowrun_collision.c'),
             SOURCE.with_name('shadowrun_collision_resolve.c'), SOURCE, MOTION_SOURCE)
    chunks = [path.read_bytes() for path in files]
    result = author_program('\n'.join(x.decode() for x in chunks),
      [{'id':0,'length':len(rom),'sha256':ROM_SHA256}],
      evidence={'kind':'source-bound-prepared-projectile-composition',
        'source_sha256':ROM_SHA256,'motion_ranges':[[lo,hi,d] for lo,hi,d in MOTION_RANGES],
        'authoring_sha256':[hashlib.sha256(x).hexdigest() for x in chunks],
        'scope':'captured heading and source player profile, shared source terrain collision; actor and allocation side effects excluded'})
    if any(path.read_bytes()!=raw for path,raw in zip(files,chunks)):
        raise ValueError('field motion source changed during capture')
    return result
