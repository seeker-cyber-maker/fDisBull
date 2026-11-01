"""Source-bound projectile active-bit retirement, given animation state."""
import hashlib
from pathlib import Path
from .game_il import author_program
from .shadowrun_field_combat import ROM_SHA256
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_projectile_lifecycle.c'
RANGES=((0x14f1c,0x14f26,'bde2c3d119db74d56cceb5cf43fea49e20005cc314155f6e201e2ff0d32d52d4'),
 (0x14f86,0x14f9a,'a4647ee4f8e6e2c89a87b41a99703ef5f5b0b42df4dedb0ff3f1345e66476188'),
 (0x14ff0,0x14ff8,'60d3a8e310c2df338ff736198f393333e3e8a6c77dd98e84b5a706ac1fdfd8e7'),
 (0xac4e,0xac5e,'8a0ff2368f87bdb994fa3f5c23533e4c713536ed8361c3f0c5107c7722c9594c'),
 (0x5fdc,0x60b0,'21d0905410db209591c13af9331f7bfd1687e6ecf41f3e0733620f3c8f0a2f30'),
 (0x62b0,0x62b4,'a5426ff4ebd130c4201e502700e9a254d9663a91416c46a7bb284be02a9f8526'),
 (0x634c,0x6350,'15f481a07551bf52a4fc730e75e1598872697e80f1b2c5ab63219ef7c57981b9'),
 (0x7320,0x7324,'41e44de326afc8c9fbb28b43d1cc1f588aa0be9bcb16ae5e4edf5356962000f9'))
def lift_projectile_lifecycle(rom):
 if len(rom)!=2097152 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256:raise ValueError('wrong ROM')
 if any(hashlib.sha256(rom[a:b]).hexdigest()!=h for a,b,h in RANGES):raise ValueError('lifecycle source changed')
 raw=SOURCE.read_bytes();p=author_program(raw.decode(),evidence={'kind':'source-bound-reviewed-procedural-slice','source_sha256':ROM_SHA256,'ranges':[[a,b,h] for a,b,h in RANGES],'authoring_sha256':hashlib.sha256(raw).hexdigest(),'scope':'projectile active-bit retirement given animation word; rearming and animation timing excluded'})
 if SOURCE.read_bytes()!=raw:raise ValueError('authoring source changed')
 return p
