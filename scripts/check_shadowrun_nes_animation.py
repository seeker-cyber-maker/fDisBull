#!/usr/bin/env python3
"""Verify private native receipts for the bounded Shadowrun right-walk probe.

The original ROM, capture, target cartridge, raw runs and output receipt must
remain private. This checks controlled Genesis components, original/target
logical state and actor OAM, and seven sampled target CHR-bank screenshots.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fdisbull.game_il import GameMachine, canonical
from fdisbull.shadowrun_animation import CORE_SHA256, lift_animation_counter, observed_poses
from fdisbull.shadowrun_nes_animation import CAPTURE_RECEIPT_SHA256

NES_CORE='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60'


def sha(b): return hashlib.sha256(b).hexdigest()
def word(b,o): return (b[o^1]<<8)|b[(o+1)^1]


def native(path,rom,entry):
    data=path.read_bytes(); d=json.loads(data)
    if (not d.get('complete') or not d.get('inputs_unchanged') or d.get('source_sha256')!=sha(rom)
            or d.get('core_sha256')!=CORE_SHA256 or d['contract']['entry']!=entry
            or d.get('cases_completed')!=len(d['cases']) or not d['cases']
            or any(not c.get('complete') for c in d['cases'])):
        raise ValueError('incomplete or wrong native receipt')
    return data,d


def target_run(path,nes,inputs):
    data=(path/'receipt.json').read_bytes();d=json.loads(data); trace=(path/'ram_trace.json').read_bytes()
    if (d.get('rom_sha256')!=sha(nes) or d.get('core_sha256')!=NES_CORE or d.get('system')!='nes'
            or d.get('inputs')!=inputs or d.get('patches')!=[] or d.get('ram_trace_sha256')!=sha(trace)
            or d.get('watches')!=[{'name':'state','offset':1792,'length':32},
                                  {'name':'oam','offset':512,'length':256}]):
        raise ValueError('target run identity, input or trace mismatch')
    rows=json.loads(trace)['frames']
    if len(rows)!=d['frames'] or any(row['frame']!=i for i,row in enumerate(rows)):
        raise ValueError('target trace is incomplete')
    return data,d,rows


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('rom','capture','nes','counter-native','wrap-native','selector-native',
                 'right-run','right-up-run','release-run','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args(); out=a.output.resolve()
    if out.exists() or any((q/'.git').exists() for q in (out,*out.parents)):
        raise ValueError('output must be new and private')
    rom=a.rom.read_bytes();nes=a.nes.read_bytes(); program=lift_animation_counter(rom)
    if len(nes)!=16+32768+8*8192 or nes[:4]!=b'NES\x1a' or nes[5]!=8 or (nes[6]>>4)!=3:
        raise ValueError('unexpected target cartridge layout')
    if sha((a.capture/'capture.json').read_bytes())!=CAPTURE_RECEIPT_SHA256:
        raise ValueError('unreviewed capture receipt')
    obs=observed_poses(rom,a.capture,list(range(5999,6061)));machine=GameMachine(program,{0:rom});bad=[]
    receipts=[]
    for path,entry,kind,count in ((a.counter_native,0x5fee,'counter',96),(a.wrap_native,0x6060,'wrap',32),
                                  (a.selector_native,0xb6ba,'selector',32)):
        raw,report=native(path,rom,entry);receipts.append(sha(raw))
        if len(report['cases'])!=count:raise ValueError('unexpected native boundary case count')
        for case in report['cases']:
            c=case['contract']; before=bytes.fromhex(c['ram'][0]['data']);after=bytes.fromhex(case['ram_after']['actor'])
            if c['registers']['A0']!=0xff0100:raise ValueError('unexpected actor register')
            if kind=='counter':
                machine.set_state({'shadowrun_anim_accumulator':c['registers']['D0'],
                    'shadowrun_anim_increment':int.from_bytes(before[24:26],'big'),
                    'shadowrun_anim_threshold':int.from_bytes(before[28:30],'big'),
                    'shadowrun_anim_index':int.from_bytes(before[30:32],'big'),
                    'shadowrun_anim_flags':before[17]});machine.call('shadowrun_animation_tick');s=machine.snapshot()
                got=(s['shadowrun_anim_accumulator'],s['shadowrun_anim_index'],s['shadowrun_anim_flags'])
                want=(int.from_bytes(after[26:28],'big'),int.from_bytes(after[30:32],'big'),after[17])
            elif kind=='wrap':
                machine.set_state({'shadowrun_anim_positive_count':c['registers']['D0'],
                                   'shadowrun_anim_index':int.from_bytes(before[30:32],'big')})
                machine.call('shadowrun_animation_positive_wrap');got=machine.snapshot()['shadowrun_anim_index']
                want=int.from_bytes(after[30:32],'big')
            else:
                heading=int.from_bytes(before[54:56] if before[17]&4 else before[46:48],'big')
                ordinal=((heading<<3)|(heading>>13))&7
                got=int.from_bytes(rom[0xc062+ordinal*2:0xc064+ordinal*2],'big')
                want=int.from_bytes(after[22:24],'big')
            if got!=want:bad.append({'kind':kind,'case':c['name']})
    rraw,rr,rows=target_run(a.right_run,nes,[{'start':0,'end':160,'buttons':['RIGHT']}])
    uraw,ur,up=target_run(a.right_up_run,nes,[{'start':0,'end':90,'buttons':['RIGHT']},
                                               {'start':90,'end':110,'buttons':['UP']}])
    lraw,lr,release=target_run(a.release_run,nes,[{'start':0,'end':90,'buttons':['RIGHT']}])
    seen={}
    for row in rows:
        b=bytes.fromhex(row['raw']['state'])
        if b[:2]==b'SW' and not b[22]&1 and b[23] and b[23] not in seen:
            seen[b[23]]=(row['frame'],b)
    fields=[('x',4,0x100),('y',6,0x104),('heading',8,0x12e),('camera_x',14,0xddc6),
            ('camera_y',16,0xddc8),('counter',30,0x11a)]
    for tick in range(1,61):
        if tick not in seen:bad.append({'tick':tick,'field':'missing'});continue
        frame,b=seen[tick];ram=(a.capture/f'native/scene-{5999+tick:06d}/ram.bin').read_bytes()
        if sha(ram)!=json.loads((a.capture/'capture.json').read_text())['files'][f'native/scene-{5999+tick:06d}/ram.bin']['sha256']:
            raise ValueError('source actor RAM changed')
        for name,off,source in fields:
            if int.from_bytes(b[off:off+2],'little')!=word(ram,source):bad.append({'tick':tick,'field':name})
        item=obs['observations'][tick];relative=obs['poses'][item['pose']]['oam_offsets']
        if b[26]!=item['pose'] or b[29]!=word(ram,0x11e):bad.append({'tick':tick,'field':'pose/index'})
        expected=bytearray()
        for i in range(0,len(relative),4):
            expected.extend(((item['screen_y']+relative[i])&255,relative[i+1],relative[i+2],
                             (item['screen_x']+relative[i+3])&255))
        oam=bytes.fromhex(rows[frame+1]['raw']['oam'])
        if oam[:len(expected)]!=expected:bad.append({'tick':tick,'field':'actor OAM'})
    if not any(bytes.fromhex(row['raw']['state'])[:2]==b'SW' and
               bytes.fromhex(row['raw']['state'])[28]==2 for row in rows):
        bad.append({'field':'60-update observation limit'})
    if not any(bytes.fromhex(row['raw']['state'])[:2]==b'SW' and
               bytes.fromhex(row['raw']['state'])[28]==1 for row in release[90:]):
        bad.append({'field':'release refusal'})
    if not any(bytes.fromhex(row['raw']['state'])[:2]==b'SW' and
               bytes.fromhex(row['raw']['state'])[28]==1 for row in up[90:]):
        bad.append({'field':'UP refusal'})
    hist=defaultdict(Counter);pose_set=set();samples=0;banks=nes[16+32768:]
    for path,receipt,trace,frames in ((a.right_up_run,ur,up,[38,40,44]),
                                      (a.right_run,rr,rows,[50,70,90,110])):
        for frame in frames:
            entry=next((e for e in receipt['frame_images'] if e['frame']==frame),None)
            file=path/f'frame-{frame:06d}.png'
            if not entry or sha(file.read_bytes())!=entry['png_sha256']:raise ValueError('screenshot hash mismatch')
            image=Image.open(file).convert('RGB');b=bytes.fromhex(trace[frame]['raw']['state'])
            oam=bytes.fromhex(trace[frame]['raw']['oam']);pose=b[26];pose_set.add(pose)
            bank=banks[pose*8192+4096:pose*8192+8192]
            if len(bank)!=4096:raise ValueError('missing CHR bank')
            for i in range(0,64,4):
                y,tile,attr,x=oam[i:i+4]
                if y>=224:continue
                for dy in range(8):
                    lo,hi=bank[tile*16+dy],bank[tile*16+dy+8]
                    for dx in range(8):
                        bit=7-dx;value=((lo>>bit)&1)|(((hi>>bit)&1)<<1)
                        if value and x+dx<256 and y+dy+1<240:
                            hist[(attr&3,value)][image.getpixel((x+dx,y+dy+1))]+=1;samples+=1
    inconsistent=sum(sum(v.values())-v.most_common(1)[0][1] for v in hist.values())
    colors={v.most_common(1)[0][0] for v in hist.values()}
    if (pose_set!=set(range(7)) or inconsistent or samples<1000 or
            set(hist)!={(1,1),(1,2),(1,3)} or len(colors)!=3):
        bad.append({'field':'CHR screenshot pixels'})
    result={'format':'fdisbull-shadowrun-animation-verification-1','rom_sha256':sha(rom),'nes_sha256':sha(nes),
            'counter_gameil_sha256':sha(canonical(program)),'genesis_native_receipt_sha256':receipts,
            'right_run_receipt_sha256':sha(rraw),'right_up_run_receipt_sha256':sha(uraw),
            'release_run_receipt_sha256':sha(lraw),
            'logical_ticks':60,'sampled_poses':sorted(pose_set),'pixel_samples':samples,
            'pixel_inconsistencies':inconsistent,'mismatches':bad,
            'scope':'bounded prepared-state ordinary right walk; no audio or hardware equivalence'}
    out.write_text(json.dumps(result,indent=2)+'\n');print(out)
    if bad:raise SystemExit(f'{len(bad)} animation mismatches')

if __name__=='__main__':main()
