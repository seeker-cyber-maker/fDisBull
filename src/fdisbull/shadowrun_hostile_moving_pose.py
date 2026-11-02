"""Prepared moving-origin hostile negative shooting pose."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_hostile_expired_pose import lift_hostile_expired_pose
from .udl_shadowrun import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_hostile_moving_pose.c'
def lift_hostile_moving_pose(rom):
    lift_hostile_expired_pose(rom)
    names=('shadowrun_collision.c','shadowrun_collision_resolve.c','shadowrun_linked_heading.c','shadowrun_hostile_stationary.c','shadowrun_hostile_expired_pose.c','shadowrun_hostile_moving_pose.c')
    files=[SOURCE.with_name(n) for n in names];chunks=[p.read_bytes() for p in files]
    result=author_program('\n'.join(c.decode() for c in chunks),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={'kind':'source-bound-moving-origin-negative-pose','source_sha256':ROM_SHA256,'authoring_sha256':[hashlib.sha256(c).hexdigest() for c in chunks],'scope':'prepared moving-origin hostile negative pose and idle expiry; sprite payload external'})
    if any(p.read_bytes()!=c for p,c in zip(files,chunks)):raise ValueError('authoring changed')
    return result
