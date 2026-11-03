"""Small, source-bound facts for the assisted SMB warp investigation.

These are semantic results about one matched mapper-66 cartridge, not a
lifter, game binary, input movie, or claim that the wall clip was performed.
"""
from __future__ import annotations
import hashlib

SOURCE_SHA256 = '23ec3f6bb68f8774070ce936869e7f62ac3490449f58e62d6ed33a0fb385d456'
CORE_SHA256 = '5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60'
WINDOWS = {0x87f2:(12,'0ae5a090719296c5e357f3ad78598e87f6e6af1125ea16b83ea1fe8a0e819c8c'),
           0xdf0a:(55,'240a6b4a023cc617559d47fb88407387e2673e6f4fe58e025566ad9f33736487'),
           0x9cb4:(65,'4d38e64efa89554318eb365795c53bae4425ac8f97b81b6417f845cd4bc4bd2b')}


def identify(raw):
    """Require exact recorded combined cartridge and matched mapped code windows."""
    digest=hashlib.sha256(raw).hexdigest()
    if len(raw)!=81936 or digest!=SOURCE_SHA256 or raw[:8]!=b'NES\x1a\x04\x02\x21\x40':
        raise ValueError('Requires the exact reviewed mapper-66 combined cartridge')
    for addr,(length,digest) in WINDOWS.items():
        data=raw[16+addr-0x8000:16+addr-0x8000+length]
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Mapped code identity mismatch')
    return {'source_sha256':SOURCE_SHA256,'mapper':66,'mapped_prg_bank':0,
            'scope':'exact ROM and selected code windows; not publisher authenticity'}


def warp_result(control, player_x):
    """Compute the table index and stored world for this observed routine."""
    if type(control) is not int or not 0<=control<=255 or type(player_x) is not int or not 0<=player_x<=255:
        raise ValueError('control and player_x must be bytes')
    if not control:return None
    table=(4,3,2,0,36,5,36,0,8,7,6,0)
    index=(control&3)*4+(player_x>=0x60)+(player_x>=0xa0)
    if index>=len(table):return {'table_index':index,'world_index':None,'scope':'outside observed table'}
    return {'table_index':index,'table_value':table[index],
            'world_index':(table[index]-1)&255,'display_tile':table[index]}
