#!/usr/bin/env python3
"""Compare the bounded scripted actor slice at original main-loop checkpoints.

The first checkpoint alone seeds UIL and native state. Later private WRAM
captures are comparison evidence only; their video frames do not drive time.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import canonical
from fdisbull.shadowrun_snes_field import ROM_SHA256, SAVE_SHA256
from fdisbull.shadowrun_snes_npc import FIELDS, SOURCE as NPC_SOURCE
from fdisbull.shadowrun_snes_script import SOURCE as SCRIPT_SOURCE
from fdisbull.shadowrun_snes_scripted import machine_from_scripted_capture
from fdisbull.udc_macos import build_macos
from check_shadowrun_macos import Native

CORE = '6d679f9123cbffe635815dfc137af88c2effc54bd9355f3cd112fb3cd4e51283'
SEED = 'e4cf82bc4d2d58d28cda9ae9d90d51cf4287e9e8bf0d3c860097a1a5ce2f0ca9'
ACTOR_FIELDS = ('npc_x','npc_y','npc_z','npc_target_x','npc_target_y','npc_timer',
                'npc_control','npc_direction','npc_action','npc_task','npc_velocity_x',
                'npc_velocity_y','npc_velocity_z','npc_depth','npc_anim_table',
                'npc_anim_reload','npc_anim_selector','npc_anim_phase','npc_anim_increment',
                'npc_anim_timer','npc_anim_pending','npc_anim_kind','npc_anim_mode',
                'npc_anim_dx','npc_anim_dy','npc_anim_dz','npc_anim_dh','npc_anim_extra')
TASK_FIELDS = {'task_wait':0xbbe,'task_link':0x38e,'task_flags':0xc7e,
               'task_delay':0xc1e,'task_frame':0x26e,'task_callback':0x2ce}


def sha(data): return hashlib.sha256(data).hexdigest()
def word(data, at): return data[at] | (data[at+1] << 8)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('rom','checkpoints','output'):p.add_argument('--'+k,required=True,type=Path)
    a=p.parse_args();out=a.output.resolve();original=a.checkpoints.resolve()
    if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):
        raise ValueError('output must be a fresh private directory outside Git')
    receipt_bytes=(original/'receipt.json').read_bytes();r=json.loads(receipt_bytes)
    cps=r['snes_checkpoints']
    if (r['system']!='snes' or r['core_sha256']!=CORE or r['rom_sha256']!=ROM_SHA256 or
        r['patches'] or cps['pc']!=0x80962e or
        not cps['phase'].startswith('before selected opcode')):
        raise ValueError('unexpected source, patches or checkpoint phase')
    entries=[c for f in cps['frames'] for c in f['captures']]
    if any(f['dropped'] for f in cps['frames']):raise ValueError('checkpoint drops')
    matches=[i for i,x in enumerate(entries) if x['sha256']==SEED]
    if len(matches)!=1:raise ValueError('seed checkpoint not unique')
    entries=entries[matches[0]:]
    if len(entries)<2 or any(y['serial']!=x['serial']+1 for x,y in zip(entries,entries[1:])):
        raise ValueError('logical checkpoint sequence incomplete')
    def capture(item):
        data=(original/item['file']).read_bytes()
        if len(data)!=131072 or sha(data)!=item['sha256']:raise ValueError('checkpoint hash mismatch')
        return data
    rom=a.rom.read_bytes();save=(original/'save_ram.bin').read_bytes()
    if sha(rom)!=ROM_SHA256 or sha(save)!=SAVE_SHA256:raise ValueError('unexpected ROM or save')
    seed=capture(entries[0]);m,regions=machine_from_scripted_capture(rom,seed,save)
    watched=[Path(__file__).resolve(),NPC_SOURCE,SCRIPT_SOURCE,ROOT/'src/fdisbull/shadowrun_snes_scripted.py']
    hashes={str(x):sha(x.read_bytes()) for x in watched};initial=m.snapshot()
    out.mkdir(mode=0o700,parents=True)
    build=build_macos(m.program,initial,out/'native',entry='shadowrun_snes_frame')
    native=Native(out/'native'/'libfdisbull_native.dylib',a.rom.resolve())
    report={'format':'shadowrun-snes-scripted-checkpoint-1','result':'running',
      'receipt_sha256':sha(receipt_bytes),'seed_sha256':sha(seed),'core_sha256':CORE,
      'program_sha256':sha(canonical(m.program)),'source_hashes':hashes,'native_build':build,
      'clock':'consecutive instruction-entry checkpoints at 80:962E',
      'scope':'active task scheduler plus three actor slice, not whole scene; no rendering/audio equivalence',
      'source_checkpoints':0,'source_fields':0,'native_elements':0,'first_divergence':None}
    try:
        report['native_elements']+=native.compare(initial,'seed')
        for item in entries[1:]:
            before=m.snapshot();m.call('shadowrun_snes_frame',0);s=m.snapshot();rc=native.step(0)
            if s['shadowrun_snes_frame_status']!=1 or rc:
                report['first_divergence']={'serial':item['serial'],'kind':'unsupported',
                  'failure':s['scripted_failure'],'native_return':rc};break
            report['native_elements']+=native.compare(s,item['serial'])
            source=capture(item);shared=s['task_shared'];checks=[]
            for slot in (0x44,0x46,0x4e):
                for name in ACTOR_FIELDS:
                    at=FIELDS[name]+slot;checks.append((f'{slot:02x}.{name}',word(shared,at),word(source,at)))
                at=FIELDS['npc_flags']+slot
                checks.append((f'{slot:02x}.physics_flags',word(shared,at)&0x468,word(source,at)&0x468))
            # Slot $42's earlier unset-action animation is explicitly outside
            # the projection; compare its setup after the source task selects it.
            if word(shared,FIELDS['npc_action']+0x42)==0:
                for name in ('npc_action','npc_direction','npc_anim_table','npc_anim_reload',
                             'npc_anim_selector','npc_anim_phase','npc_anim_increment',
                             'npc_anim_timer','npc_anim_pending','npc_anim_kind','npc_anim_mode',
                             'npc_anim_dx','npc_anim_dy','npc_anim_dz','npc_anim_dh','npc_anim_extra'):
                    at=FIELDS[name]+0x42
                    checks.append((f'42.{name}',word(shared,at),word(source,at)))
            task_list=[];task=word(source,0x268)
            while not task&0x8000:
                if task&1 or task>=96 or task in task_list:raise ValueError('invalid source task list')
                task_list.append(task);task=word(source,0x32e+task)
            modeled=[];task=s['task_list_head']
            while not task&0x8000:
                if task&1 or task>=96 or task in modeled:raise ValueError('invalid model task list')
                modeled.append(task);task=s['task_next'][task//2]
            if modeled!=task_list:
                report['first_divergence']={'serial':item['serial'],'kind':'task list mismatch',
                                            'model':modeled,'source':task_list};break
            for task in task_list:
                for name,base in TASK_FIELDS.items():
                    checks.append((f'{task:02x}.{name}',s[name][task//2],word(source,base+task)))
                frame=s['task_frame'][task//2]
                for rel,label in ((3,'pc'),(7,'sp')):
                    at=frame+rel-0x3f2
                    checks.append((f'{task:02x}.{label}',word(s['task_heap'],at),word(source,frame+rel)))
            checks.append(('entity_2e56',shared[0x2e56],source[0x2e56]))
            bad=[{'field':name,'model':x,'source':y} for name,x,y in checks if x!=y]
            if bad:
                report['first_divergence']={'serial':item['serial'],'kind':'source mismatch','fields':bad[:20]};break
            report['source_checkpoints']+=1;report['source_fields']+=len(checks)
        else:
            report['result']='passed'
            before=m.snapshot()
            for retry in range(2):
                m.call('shadowrun_snes_frame',0);state=m.snapshot()
                if (state['shadowrun_snes_frame_status']!=2 or state['scripted_failure']!=2 or
                        native.step(0)!=1):raise AssertionError('budget refusal failed')
                m.set_state(before)
                report['native_elements']+=native.compare(before,('budget rollback',retry))
            report['budget_rollback_verified']=True
    finally:native.close()
    if any(sha(Path(k).read_bytes())!=v for k,v in hashes.items()):raise ValueError('source changed during check')
    if report['result']!='passed':report['result']='bounded'
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('result','source_checkpoints','source_fields','native_elements','first_divergence')},indent=2))
    if report['result']!='passed':raise SystemExit(1)

if __name__=='__main__':main()
