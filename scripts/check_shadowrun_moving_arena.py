#!/usr/bin/env python3
"""Compare the assisted moving-arena model to its original full-core route."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import canonical
from fdisbull.shadowrun_assisted_arena import assisted_arena_from_capture
from fdisbull.shadowrun_replay import _read_rom, _source_capture
from fdisbull.udl_shadowrun import ROM_SHA256

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    for name in ('rom','capture','original','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--extension',type=Path)
    args=parser.parse_args()
    rom=_read_rom(args.rom)
    receipt_bytes=(args.original/'native/receipt.json').read_bytes()
    receipt=json.loads(receipt_bytes)
    expected={(0x400,256),(0xdf84,2),(0xdfd8,2),(0xe186,2),(0xf9f8,2)}
    if (sha(receipt_bytes)!='731cb1ec2f51c207d3acaf3443a4de0c231bd4db9922a9b7f0c57a6333858ff6' or receipt['rom_sha256']!=ROM_SHA256 or
        receipt['core_sha256']!='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268' or
        len(receipt['patches'])!=5 or any(p['frame']!=6000 or p['memory_id']!=2 for p in receipt['patches']) or
        {(p['offset'],len(p['data_hex'])//2) for p in receipt['patches']}!=expected):
        raise ValueError('Original assisted setup is not the reviewed one')
    machine=assisted_arena_from_capture(rom,args.capture,moving=True)
    common=(('shadowrun_player_x',0x100,2),('shadowrun_player_y',0x104,2),
        ('shadowrun_player_heading',0x12e,2),('shadowrun_hostile_x',0x400,2),
        ('shadowrun_hostile_y',0x404,2),('shadowrun_hostile_ammo',0x44e,1),
        ('shadowrun_hostile_rng',0xf9f8,2),('shadowrun_arena_hp',0x14c,1))
    walking=(('shadowrun_ai_heading',0x42e,2),('shadowrun_ai_animation',0x416,2),
        ('shadowrun_pursuit_route_service_timer',0x4b6,2),('shadowrun_pursuit_route_action_timer',0x4dc,2),
        ('shadowrun_pursuit_route_sprite_increment',0x418,2),('shadowrun_pursuit_route_sprite_accumulator',0x41a,2),
        ('shadowrun_anim_increment',0x118,2),('shadowrun_anim_accumulator',0x11a,2),('shadowrun_anim_index',0x11e,2))
    impact=(('shadowrun_attack_animation',0x416,2),('shadowrun_attack_increment',0x418,2),
        ('shadowrun_attack_accumulator',0x41a,2),('shadowrun_attack_action_timer',0x4dc,2),
        ('shadowrun_reaction_animation',0x116,2),('shadowrun_reaction_accumulator',0x11a,2))
    hostile=(('shadowrun_attack_animation',0x416,2),('shadowrun_attack_increment',0x418,2),
        ('shadowrun_attack_accumulator',0x41a,2),('shadowrun_attack_action_timer',0x4dc,2),
        ('shadowrun_attack_service_timer',0x4b6,2))
    capture_hash=None
    extension_hash=None
    if args.extension:
        extension_receipt=(args.extension/'native/receipt.json').read_bytes()
        if sha(extension_receipt)!='68d87f40204f975f293479dcea72249ad045fc10a583401d901bddbca1111d6b':
            raise ValueError('Unreviewed source extension')
        first=(args.original/'native/scene-006049/ram.bin').read_bytes()
        second=(args.extension/'native/scene-006049/ram.bin').read_bytes()
        if first!=second:raise ValueError('Source extension does not join original route')
        extension_hash=sha(extension_receipt)
    for frame in range(6000,6120 if args.extension else 6050):
        machine.call('shadowrun_arena_frame',4 if 6001<=frame<=6040 else 0)
        state=machine.snapshot()
        if state['shadowrun_arena_frame_status']!=1:raise ValueError(f'Model refused frame {frame}')
        if frame>6100 and frame not in (6110,6119):continue
        root=args.original if frame<6050 else args.extension
        identity,arrays,_=_source_capture(root/'native'/f'scene-{frame:06}',ROM_SHA256)
        if identity['frame']!=frame:raise ValueError('Source frame mismatch')
        if capture_hash is None:capture_hash=identity['capture_json_sha256']
        if frame<6050 and identity['capture_json_sha256']!='2a3b93a30be1655f51020703fa43b610109be60e2ba223d861b47a77b5e193d3':raise ValueError('Unreviewed source capture')
        raw=arrays['ram'];memory=bytes(raw[i^1] for i in range(len(raw)))
        fields=common+(walking if frame<6021 else impact if frame in (6021,6051) else hostile)
        errors=[(n,state[n],int.from_bytes(memory[o:o+w],'big')) for n,o,w in fields
                if state[n]!=int.from_bytes(memory[o:o+w],'big')]
        if errors:raise ValueError(f'Source mismatch at {frame}: {errors}')
    if args.output.exists():raise ValueError('Output already exists')
    args.output.write_text(json.dumps({'status':'passed','source_sha256':sha(rom),
        'program_sha256':sha(canonical(machine.program)),'original_capture_sha256':capture_hash,
        'original_receipt_sha256':sha(receipt_bytes),'extension_receipt_sha256':extension_hash,
        'matched_frames':103 if extension_hash else 50,'first_frame':6000,'last_dense_frame':6100 if extension_hash else 6049,
        'later_checkpoints':[6110,6119] if extension_hash else [],
        'scope':'assisted constructor and initial cooldown; player and enemy movement, live shot, first HP change and held-direction recovery',
        'excluded':['natural encounter','source death continuation','sprite upload','audio']},indent=2)+'\n')

if __name__=='__main__':main()
