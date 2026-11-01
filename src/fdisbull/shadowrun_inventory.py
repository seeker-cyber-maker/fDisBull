"""Source-bound, controlled inventory leaf operations; no menu dispatcher."""
import hashlib
from pathlib import Path
from .game_il import author_program

ROM_SHA256 = '92a614491fc3ea12a6df32459cce08b48574b7b814e244c07eb860dc5c6edb7e'
SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_inventory.c'
RANGES = ((0x12148, 0x12166, 'd183b8fa625e5276ce4eb7bf1ae52029deff8cc68168ca279092992c3f9a3621'),
          (0x1219c, 0x121c0, '09119c842e914d02b68459b851d9a30c6a75ad57ade4a539a37af9a5346b4e53'))

def lift_inventory(rom):
    if len(rom) != 2097152 or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('inventory requires the exact reviewed Shadowrun ROM')
    for lo, hi, digest in RANGES:
        if hashlib.sha256(rom[lo:hi]).hexdigest() != digest:
            raise ValueError('inventory source range changed')
    raw = SOURCE.read_bytes()
    result = author_program(raw.decode(), evidence={
        'kind': 'source-bound-reviewed-procedural-slice', 'source_sha256': ROM_SHA256,
        'ranges': [[lo, hi, digest] for lo, hi, digest in RANGES],
        'authoring_sha256': hashlib.sha256(raw).hexdigest(),
        'scope': 'valid inventory grid selection and isolated armor branch; dispatch and presentation excluded'})
    if SOURCE.read_bytes() != raw:
        raise ValueError('inventory source changed during capture')
    return result
