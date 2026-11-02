"""Diagnostic composition of source projectile, damage and sprite-pass leaves."""
import hashlib
from pathlib import Path

from .game_il import author_program
from .shadowrun_hostile_motion import SOURCE as MOTION, lift_hostile_motion
from .shadowrun_hostile_animation import SOURCE as ANIMATION, lift_hostile_animation
from .shadowrun_hostile_burst import SOURCE as BURST, lift_hostile_burst
from .shadowrun_player_damage import SOURCE as DAMAGE, lift_player_damage
from .shadowrun_hostile_self_hit import SOURCE as SELF_HIT, lift_hostile_self_hit

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_hostile_cycle.c'
TRANSACTION_SOURCE = SOURCE.with_name('shadowrun_hostile_cycle_transaction.c')


def lift_hostile_cycle(rom):
    programs = [lift_hostile_motion(rom), lift_hostile_animation(rom),
                lift_hostile_burst(rom), lift_player_damage(rom), lift_hostile_self_hit(rom)]
    paths = (MOTION, ANIMATION, BURST, DAMAGE, SELF_HIT, SOURCE, TRANSACTION_SOURCE)
    raw = [path.read_bytes() for path in paths]
    prelude = ('typedef unsigned char u8; typedef unsigned int u16; typedef unsigned long u32;\n'
               'u8 rom8(u8 region,u32 offset); u16 rom16(u8 region,u32 offset);\n'
               'u8 shadowrun_terrain_map[2816],shadowrun_target_flags[7],shadowrun_play_actor_hp[7];\n'
               'u16 shadowrun_x_min,shadowrun_x_max,shadowrun_y_min,shadowrun_y_max;\n'
               'u16 shadowrun_target_x[7],shadowrun_target_y[7];\n')
    components = []
    for part in raw:
        components.append('\n'.join(line for line in part.decode().splitlines()
                                    if not line.startswith(('typedef ', 'extern ', 'u8 rom8(', 'u16 rom16('))))
    result = author_program(prelude + '\n'.join(components), evidence={
        'kind': 'bounded-hostile-projectile-loop-composition',
        'components': [p['evidence'] for p in programs],
        'authoring_sha256': hashlib.sha256(raw[-2]).hexdigest(),
        'transaction_sha256': hashlib.sha256(raw[-1]).hexdigest(),
        'scope': 'one caller-scheduled source actor pass followed by one sprite pass',
        'unsupported': ['whole frame scheduling', 'reaction must be resolved before next call',
                        'death', 'solid/bounds impact', 'other actor impact', 'complex terrain',
                        'wounded hostile attacker'],
    })
    if any(path.read_bytes() != data for path, data in zip(paths, raw, strict=True)):
        raise ValueError('Hostile cycle source changed during lifting')
    return result
