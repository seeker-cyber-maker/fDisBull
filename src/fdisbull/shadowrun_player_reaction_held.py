"""Bounded held-A continuation following a captured party stagger."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_player_reaction_resume import lift_player_reaction_resume
from .udl_shadowrun import ROM_SHA256

SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_player_reaction_held.c'


def lift_player_reaction_held(rom):
    lift_player_reaction_resume(rom)
    names = ('shadowrun_collision.c', 'shadowrun_collision_resolve.c',
             'shadowrun_player_reaction.c', 'shadowrun_player_reaction_step.c',
             'shadowrun_player_reaction_resume.c', 'shadowrun_player_reaction_held.c')
    files = [SOURCE.with_name(name) for name in names]
    chunks = [p.read_bytes() for p in files]
    result = author_program('\n'.join(c.decode() for c in chunks),
        [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}], evidence={
            'kind': 'source-bound-party-held-a-recovery', 'source_sha256': ROM_SHA256,
            'authoring_sha256': [hashlib.sha256(c).hexdigest() for c in chunks],
            'scope': 'captured stationary party held-A idle admission; following attack separate'})
    if any(p.read_bytes() != c for p,c in zip(files,chunks)):
        raise ValueError('authoring changed')
    return result
