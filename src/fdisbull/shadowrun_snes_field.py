"""Bounded SNES opening scene movement with caller-owned captured collision data."""
import hashlib
from pathlib import Path
from .game_il import author_program, GameMachine
ROM_SHA256='e6bc0a595d5c7c4bc0bbb61ffe35a70288a77eb78544ed74682d489a9e6f07f4'
SNAPSHOT_SHA256='0032d4c7e01fce638a8ef653be6ab94871d7aa51ce48bb65d5d7b1444f791211'
SAVE_SHA256='5eef00d9bf324987decb0aae450a28a73b8ceb2a61cdf5360440f41eddc97130'
CAPTURE={'frame':2999,'rom_sha256':ROM_SHA256,'wram_sha256':SNAPSHOT_SHA256,'save_ram_sha256':SAVE_SHA256,'capture_receipt_sha256':'fb5221413d6533a572e6ab4bce7f36778cbb2bdb7b19d0c7d4ce8101774fa496','logical_pad':{'up':1,'down':2,'left':4,'right':8},'coordinate_units':'source coordinates are divided by four before collision bounds comparisons','scope':'captured static opening scene actor; autonomous actor changes excluded'}
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_snes_field.c'
def machine_from_capture(rom: bytes, snapshot: bytes, save_ram: bytes):
    if len(rom)!=1048576 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256:raise ValueError('wrong SNES source')
    if len(snapshot)!=131072 or hashlib.sha256(snapshot).hexdigest()!=SNAPSHOT_SHA256:raise ValueError('wrong captured scene')
    if len(save_ram)!=8192 or hashlib.sha256(save_ram).hexdigest()!=SAVE_SHA256:raise ValueError('wrong captured save RAM')
    raw=SOURCE.read_bytes()
    program=author_program(raw.decode(),[{'id':0,'length':len(rom),'sha256':ROM_SHA256},{'id':1,'length':len(snapshot),'sha256':SNAPSHOT_SHA256}],evidence={'kind':'bounded-snes-opening scene-source-movement','source_sha256':ROM_SHA256,'collision_snapshot_sha256':SNAPSHOT_SHA256,'authoring_sha256':hashlib.sha256(raw).hexdigest(),'scope':'single captured actor, cardinal movement and captured static collision geometry within bounded captured coordinate domain; chords and dynamic world behavior refused'})
    m=GameMachine(program,{0:rom,1:snapshot});w=lambda n:int.from_bytes(snapshot[n:n+2],'little')
    if w(0xcde)!=0x42:raise ValueError('unexpected source player slot')
    m.set_state({'shadowrun_snes_player_x':w(0xe86),'shadowrun_snes_player_y':w(0xede),'shadowrun_snes_player_z':w(0xf36),'shadowrun_snes_velocity_x':w(0xd7e),'shadowrun_snes_velocity_y':w(0xdd6),'shadowrun_snes_flags':w(0x14b6),'shadowrun_snes_rotation':int.from_bytes(save_ram[0x1ffd:0x1fff],'little'),'shadowrun_snes_left':w(0x425e),'shadowrun_snes_right':w(0x42b6),'shadowrun_snes_top':w(0x430e),'shadowrun_snes_bottom':w(0x4366),'shadowrun_snes_height':w(0x43be),'shadowrun_snes_frame_status':1})
    if SOURCE.read_bytes()!=raw:raise ValueError('source changed')
    return m
