"""Source-bound normal-field camera state; Genesis tile streaming is an edge.

Native comparisons must qualify the model independently. This is a reviewed
translation, not automatic recovery or proof of arbitrary game reachability.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from .game_il import author_program

ROM_SHA256 = '92a614491fc3ea12a6df32459cce08b48574b7b814e244c07eb860dc5c6edb7e'
SOURCE = Path(__file__).parent / 'game_sources/shadowrun_camera.c'
SPANS = ((14908, 15640, 'aa8de043e40cae9f04571282b9bbfcc09471711970c629b9acac6a9ed51c6879'), (89548, 89590, '2e20c8620b426fe570861819e59432ccb03b9897a86425970b0d8b6081b4c272'), (89622, 89942, '6240eb7089b68249e3ee32ac7aa0f05878eba34cd2d558852229d9c1752aae0b'))


def lift_camera(rom: bytes) -> dict:
    if len(rom) != 2097152 or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('Camera lift requires the exact reviewed Shadowrun source')
    for start, end, digest in SPANS:
        if hashlib.sha256(rom[start:end]).hexdigest() != digest:
            raise ValueError('Reviewed Shadowrun camera interval changed')
    raw = SOURCE.read_bytes()
    evidence = {
        'kind': 'reviewed-source-bound-camera-state-slice',
        'source_sha256': ROM_SHA256,
        'spans': [{'start': a, 'end': b, 'sha256': h} for a, b, h in SPANS],
        'authoring_sha256': hashlib.sha256(raw).hexdigest(),
        'scope': 'normal field camera lookahead, hysteresis, bounds, scroll and stream requests',
        'unsupported': ['scripted camera mode 3'],
        'excluded': ['Genesis graphics streaming helper effects', 'CPU registers and flags',
                     'whole-game reachability', 'audio'],
    }
    result = author_program(raw.decode(),
                            [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}],
                            evidence=evidence)
    if SOURCE.read_bytes() != raw:
        raise ValueError('Camera source changed while lifting')
    return result
