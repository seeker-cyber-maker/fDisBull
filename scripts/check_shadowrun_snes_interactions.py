#!/usr/bin/env python3
"""Compare a title-seeded interaction route at original main-loop boundaries.

Only ordinary controller samples are supplied after the title seed. Modal
polls are separate inputs to the public transactional model entry; they do
not themselves imply a completed source main-loop pass.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import canonical
from fdisbull.shadowrun_snes_field import ROM_SHA256,SAVE_SHA256
from fdisbull.shadowrun_snes_opening import TITLE_SHA256,machine_from_title
from fdisbull.udc_macos import build_macos,_Compiler
from check_shadowrun_macos import Native
from check_shadowrun_snes_opening import Reader,Mismatch,check,journal_pad,sha,word,order,UNPATCHED_CORE

CORE='34f40027761df3cdbcfa9efad1ad68540cc069105757168e8b81f19864d0b022'
MODAL={0x80a67d:1,0x80a7b2:2,0x80a7c1:2,0x80c03a:3}
CURSOR=(0x1ec,0x1ee,0x1f0,0x1f2,0x1f4,0x1f6,0x1fa,0x1fc,0x1fe,0x200,0x202)
CHECKPOINT_CORE='6d679f9123cbffe635815dfc137af88c2effc54bd9355f3cd112fb3cd4e51283'


def validate_neutrality(observer,checkpoint_bytes,unpatched_bytes):
    checkpoint=json.loads(checkpoint_bytes);unpatched=json.loads(unpatched_bytes)
    fields=('rom_sha256','inputs','frames','system_ram_sha256','state_sha256',
            'frame_rgb_sha256','frame_png_sha256','save_ram_sha256')
    for baseline,core in ((checkpoint,CHECKPOINT_CORE),(unpatched,UNPATCHED_CORE)):
        if (baseline['core_sha256']!=core or baseline['patches'] or
            baseline['memory_injection_mode']!='no memory patches' or
            any(baseline[k]!=observer[k] for k in fields)):
            raise ValueError('baseline identity or final-state mismatch')
    def checkpoint_index(r):
        c=r['snes_checkpoints']
        if c['pc']!=0x80962e or c['phase']!=observer['snes_checkpoints']['phase']:
            raise ValueError('checkpoint baseline phase mismatch')
        found={}
        for frame in c['frames']:
            if frame['dropped']:raise ValueError('baseline checkpoint drops')
            for x in frame['captures']:
                if x['serial'] in found:raise ValueError('duplicate baseline serial')
                found[x['serial']]=(frame['video_frame'],x['sha256'],x['size'],x['registers']['pc'])
        return found
    observed=checkpoint_index(observer);compared=checkpoint_index(checkpoint)
    if not observed or observed!=compared or set(observed)!=set(range(1,len(observed)+1)):
        raise ValueError('independent checkpoint baseline mismatch')
    def selected(key,fields):
        def index(r):
            rows=r[key];items={row['frame']:tuple(row[k] for k in fields) for row in rows}
            if len(rows)!=len(items):raise ValueError('duplicate selected frame')
            return items
        a=index(observer);b=index(unpatched)
        if not a or a!=b:raise ValueError('unpatched selected frame mismatch')
        return len(a)
    return {'checkpoint_receipt_sha256':sha(checkpoint_bytes),'checkpoint_core_sha256':CHECKPOINT_CORE,
            'matching_checkpoint_digests':len(observed),'unpatched_receipt_sha256':sha(unpatched_bytes),
            'unpatched_core_sha256':UNPATCHED_CORE,'ram_frames':selected('frame_ram',('size','sha256')),
            'image_frames':selected('frame_images',('width','height','rgb_sha256','png_sha256')),
            'scope':'unpatched baseline compares selected post-frame and final hashes; no instruction checkpoints'}


def prepare_journal(data,entries):
    """Keep every modal poll in order; player samples observe, not drive, input."""
    if (data.get('format')!='snes-main-loop-controller-journal-1' or data.get('dropped')!=0 or
        data.get('duplicate_serials') or data.get('conflicting_serials')):
        raise ValueError('invalid controller observer integrity')
    groups={};last_serial=0;last_frame=0
    for sample in data['samples']:
        serial=sample.get('serial');frame=sample.get('video_frame');kind=sample.get('kind')
        if (type(serial) is not int or type(frame) is not int or serial<last_serial or
            frame<last_frame or kind not in ('main','modal','player') or
            any(type(sample.get(k)) is not int or not 0<=sample[k]<=65535 for k in ('held','previous','edge'))):
            raise ValueError('invalid controller observation order or words')
        if kind=='modal' and sample.get('pc') not in MODAL:raise ValueError('unknown modal poll')
        if kind=='player' and (type(sample.get('actor')) is not int or sample['actor']&1 or not 0<=sample['actor']<88):
            raise ValueError('invalid player consumer actor')
        if kind!='player' and sample.get('actor') is not None:raise ValueError('unexpected consumer actor')
        journal_pad(sample['held']);groups.setdefault(serial,[]).append(sample)
        last_serial=serial;last_frame=frame
    for serial in range(1,len(entries)):
        group=groups.get(serial,[])
        if not group or group[0]['kind']!='main' or sum(s['kind']=='main' for s in group)!=1:
            raise ValueError(f'missing or duplicate main input at serial {serial}')
        if any(not entries[serial-1][0]<=s['video_frame']<=entries[serial][0] for s in group):
            raise ValueError('input sample outside checkpoint interval')
    disagreements=[]
    for serial,group in groups.items():
        main=[s for s in group if s['kind']=='main']
        player=[s for s in group if s['kind']=='player']
        if len(main)>1 or len(player)>1:raise ValueError('duplicate controller consumer')
        if main and player and main[0]['held']!=player[0]['held']:
            player_index=group.index(player[0]);prior=group[:player_index]
            modal=[s for s in prior if s['kind']=='modal']
            if not modal or modal[-1]['pc']!=0x80c03a or modal[-1]['held']!=player[0]['held']:
                raise ValueError('unexplained main/player disagreement')
            disagreements.append(serial)
    if sorted(disagreements)!=sorted(data.get('consumer_disagreements',[])):
        raise ValueError('controller disagreement accounting mismatch')
    return groups


def compare_interaction(reader,source):
    counts={'cursor_words':0,'camera_words':0,'item_bytes':0,'actor_entity_bytes':0}
    for at in (0x0ce0,0x0ce2,0x0ce4,0x0ce6):
        a=reader.word(at);b=word(source,at);counts['camera_words']+=1
        if a!=b:raise Mismatch(f'camera.{at:04x}',a,b)
    for at in CURSOR:
        a=reader.word(at);b=word(source,at);counts['cursor_words']+=1
        if a!=b:raise Mismatch(f'cursor.{at:04x}',a,b)
    for at in (*range(0x2ea0,0x2ea5),*range(0x2e7d,0x2e82)):
        a=reader.byte(at);b=source[at];counts['item_bytes']+=1
        if a!=b:raise Mismatch(f'item.{at:04x}',a,b)
    for slot in order(source,0x14cc,0x14ce):
        pointer=word(source,0x13c4+slot);actual=reader.word(0x13c4+slot)
        counts['actor_entity_bytes']+=2
        if actual!=pointer:raise Mismatch(f'actor.{slot:02x}.entity',actual,pointer)
        if pointer and not pointer&0x8000:
            if pointer>65530:raise ValueError('actor entity crosses shared RAM boundary')
            for off in range(5):
                actual=reader.byte(pointer+off);expected=source[pointer+off]
                counts['actor_entity_bytes']+=1
                if actual!=expected:raise Mismatch(f'actor.{slot:02x}.entity.{off}',actual,expected)
    return counts


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('rom','reference','output','checkpoint-baseline','unpatched-baseline'):
        p.add_argument('--'+key,required=True,type=Path)
    p.add_argument('--until-serial',required=True,type=int)
    p.add_argument('--native-build',type=Path)
    p.add_argument('--require-pickup',action='store_true',help='require the observed patch count transition and actor removal')
    p.add_argument('--require-item',choices=('patch','scalpel'),help='require the named source item ownership and actor-removal transition')
    p.add_argument('--require-repeat',action='store_true',help='require the observed empty-target repeat attempt after patch pickup')
    a=p.parse_args();ref=a.reference.resolve();out=a.output.resolve()
    if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):
        raise ValueError('output must be a fresh private directory outside Git')
    receipt_bytes=(ref/'receipt.json').read_bytes();r=json.loads(receipt_bytes)
    journal_bytes=(ref/'controller_journal.json').read_bytes();j=json.loads(journal_bytes)
    c=r['snes_checkpoints']
    if (r['system']!='snes' or r['core_sha256']!=CORE or r['rom_sha256']!=ROM_SHA256 or
        r['patches'] or r['memory_injection_mode']!='no memory patches' or
        r['snes_controller_journal_sha256']!=sha(journal_bytes) or c['pc']!=0x80962e or
        c['phase']!='before selected opcode at instruction entry; video frame identifies containing retro_run'):
        raise ValueError('unexpected observer identity or phase')
    checkpoint_bytes=(a.checkpoint_baseline.resolve()/'receipt.json').read_bytes()
    unpatched_bytes=(a.unpatched_baseline.resolve()/'receipt.json').read_bytes()
    neutrality=validate_neutrality(r,checkpoint_bytes,unpatched_bytes)
    entries=[]
    for frame in c['frames']:
        if frame['dropped']:raise ValueError('checkpoint observer drops')
        for index,item in enumerate(frame['captures']):
            if (item['serial']!=len(entries)+1 or item['size']!=131072 or
                item['registers']['pc']!=0x80962e or
                item['file']!=f"checkpoint-{frame['video_frame']:06d}-{index:02d}.bin"):
                raise ValueError('invalid checkpoint sequence or filename')
            entries.append((frame['video_frame'],item))
    if a.until_serial<2 or a.until_serial>len(entries):raise ValueError('invalid requested serial')
    entries=entries[:a.until_serial]
    groups=prepare_journal(j,entries)
    title_items=[x for x in r['frame_ram'] if x['frame']==839]
    if len(title_items)!=1:raise ValueError('missing title seed')
    title=(ref/title_items[0]['file']).read_bytes();rom=a.rom.read_bytes();save=(ref/'save_ram.bin').read_bytes()
    if sha(title)!=TITLE_SHA256 or sha(rom)!=ROM_SHA256 or sha(save)!=SAVE_SHA256:
        raise ValueError('incorrect ROM, title seed or save')
    watched=[Path(__file__).resolve(),ROOT/'scripts/check_shadowrun_snes_opening.py']
    watched+=sorted((ROOT/'src/fdisbull/game_sources').glob('shadowrun_snes_*.c'))
    watched+=sorted((ROOT/'src/fdisbull').glob('shadowrun_snes_*.py'))
    hashes={str(x):sha(x.read_bytes()) for x in watched}
    m,_=machine_from_title(rom,title,save);template=m.snapshot();out.mkdir(mode=0o700,parents=True)
    if a.native_build:
        native_dir=a.native_build.resolve();build=json.loads((native_dir/'receipt.json').read_bytes())
        seed=sha(json.dumps(template,sort_keys=True,separators=(',',':')).encode())
        generated=_Compiler(m.program,template,entry='shadowrun_snes_frame').generate(m.program)
        if (build.get('program_sha256')!=sha(canonical(m.program)) or build.get('seed_sha256')!=seed or
            build.get('entry')!='shadowrun_snes_frame' or build.get('unsupported_status')!='shadowrun_snes_frame_status' or
            build.get('architecture')!='arm64' or build.get('source_sha256')!=sha(generated.encode()) or
            any(build.get(k)!=sha((native_dir/f).read_bytes()) for k,f in
                (('source_sha256','fdisbull_native.c'),('header_sha256','fdisbull_native.h'),('dylib_sha256','libfdisbull_native.dylib')))):
            raise ValueError('native reuse does not match current program and artifacts')
        origin='validated_reuse'
    else:
        native_dir=out/'native';build=build_macos(m.program,template,native_dir,entry='shadowrun_snes_frame');origin='fresh'
    native=Native(native_dir/'libfdisbull_native.dylib',a.rom.resolve())
    report={'format':'shadowrun-snes-interactions-checkpoint-1','result':'running',
      'scope':'title-seeded ordinary-input interaction; selected actor, task, collision, sprite, window, text, cursor and item fields',
      'limitations':'source main-loop checkpoints; cursor display $0204, rendering and audio excluded; modal polls are input observations',
      'core_sha256':CORE,'receipt_sha256':sha(receipt_bytes),'controller_journal_sha256':sha(journal_bytes),
      'neutrality':neutrality,
      'program_sha256':sha(canonical(m.program)),'source_hashes':hashes,'native_build':build,'native_build_origin':origin,
      'requested_until_serial':a.until_serial,'source_checkpoints':0,'source_elements':{},
      'pickup_required':a.require_pickup or a.require_item=='patch' or a.require_repeat,
      'pickup_observation':{'saw_before':False,'saw_after':False},
      'scalpel_required':a.require_item=='scalpel','scalpel_observation':{'saw_before':False,'saw_after':False},
      'repeat_required':a.require_repeat,'repeat_observation':{'attempt_serial':None,'verified':False},
      'public_steps':0,'modal_steps':0,'compiler':{'native_elements':0,'continuous_prefix':[],'sampled_one_step':[]},
      'first_divergence':None}
    def add_counts(delta):
        for key,value in delta.items():report['source_elements'][key]=report['source_elements'].get(key,0)+value
    modal_sampled=set()
    def step(pad,serial,sample):
        sample_kind=sample['kind'];modal_pc=sample.get('pc')
        sampled=(serial<=2 or (sample_kind=='main' and serial in (63,183,300,500,800,1200,1600,1887,1896,1900,1950,2009,2010,2243,2244,2255,2310,2362)) or
                 (sample_kind=='modal' and (modal_pc not in modal_sampled or sample['edge']!=0)))
        if sampled:
            prior=Reader(native).snapshot(template)
            if serial>2:m.set_state(prior)
            m.call('shadowrun_snes_frame',pad);ms=m.snapshot()
        rc=native.step(pad);report['public_steps']+=1
        if rc:
            if not sampled:
                prior=Reader(native).snapshot(template);m.set_state(prior);m.call('shadowrun_snes_frame',pad);ms=m.snapshot()
            rollback=True;retry=None
            try:
                report['compiler']['native_elements']+=native.compare(prior,('rollback',serial,sample_kind))
                retry=native.step(pad)
                report['compiler']['native_elements']+=native.compare(prior,('retry rollback',serial,sample_kind))
                if retry!=rc:rollback=False
            except AssertionError:rollback=False
            report['first_divergence']={'kind':'unsupported' if rc==1 else 'native fault','serial':serial,
              'sample':sample_kind,'native_return':rc,'retry_return':retry,'failure':ms['opening_failure'],
              'interaction_fault':ms['interaction_fault'],'opening_phase':ms['opening_phase'],
              'task':ms['opening_fault_task'],'native_callback':ms['opening_fault_native'],
              'vm_opcode':ms['task_vm_fault_op'],'vm_pc':ms['task_vm_fault_pc'],
              'rollback_verified':rollback}
            return False
        if sampled:
            report['compiler']['native_elements']+=native.compare(ms,('sample',serial,sample_kind))
            if serial<=2:report['compiler']['continuous_prefix'].append([serial,sample_kind])
            else:
                report['compiler']['sampled_one_step'].append([serial,sample_kind,modal_pc])
                if sample_kind=='modal':modal_sampled.add(modal_pc)
        return True
    repeat_pending=None
    try:
        report['compiler']['native_elements']+=native.compare(template,'title seed')
        m.call('shadowrun_snes_frame',16);state=m.snapshot();rc=native.step(16)
        if rc:raise ValueError('title start refused')
        report['compiler']['native_elements']+=native.compare(state,'title START')
        report['compiler']['continuous_prefix'].append('title START')
        for index,(frame,item) in enumerate(entries):
            serial=index+1;reader=Reader(native)
            if reader.get('opening_phase')!=0:
                report['first_divergence']={'kind':'checkpoint phase mismatch','serial':serial};break
            original=(ref/item['file']).read_bytes()
            if len(original)!=131072 or sha(original)!=item['sha256']:raise ValueError('checkpoint hash mismatch')
            try:
                add_counts(check(reader,original,dynamic_ready=serial>1));add_counts(compare_interaction(reader,original))
            except Mismatch as exc:
                report['first_divergence']={'kind':'source mismatch','serial':serial,**exc.detail};break
            report['source_checkpoints']+=1
            actor_slots=order(original,0x14cc,0x14ce)
            if original[0x2ea2]==0 and word(original,0x2ea3)==65535 and 0x38 in actor_slots:
                report['pickup_observation']['saw_before']=True
            if original[0x2ea2]==1 and word(original,0x2ea3)==0x08b2 and 0x38 not in actor_slots:
                report['pickup_observation']['saw_after']=True
            if original[0x2e7d:0x2e80]==bytes(3) and word(original,0x2e80)==65535 and 0x3e in actor_slots:
                report['scalpel_observation']['saw_before']=True
            if original[0x2e7d:0x2e80]==bytes(3) and word(original,0x2e80)==0x08b2 and 0x3e not in actor_slots:
                report['scalpel_observation']['saw_after']=True
            if repeat_pending is not None:
                if (serial!=repeat_pending['serial']+1 or original[0x2ea2]!=1 or
                    word(original,0x2ea3)!=0x08b2 or 0x38 in actor_slots or
                    word(original,0x1f6)!=65535 or word(original,0x1fa)!=65535 or
                    word(original,0x1f4)!=0 or reader.get('interaction_action_count')!=repeat_pending['actions']):
                    report['first_divergence']={'kind':'repeat attempt postcondition mismatch','serial':serial};break
                report['repeat_observation']['verified']=True;repeat_pending=None
            if report['repeat_observation']['verified'] and (original[0x2ea2]!=1 or word(original,0x2ea3)!=0x08b2 or 0x38 in actor_slots):
                report['first_divergence']={'kind':'repeat item state changed','serial':serial};break
            if serial==len(entries):break
            main=groups[serial][0]
            if (a.require_repeat and report['pickup_observation']['saw_after'] and not report['repeat_observation']['verified'] and
                main['held']&0x8000 and not main['previous']&0x8000 and
                word(original,0x1f4)!=0 and word(original,0x1f6)==65535 and word(original,0x1fa)==65535 and
                word(original,0x1f0)>>8==86 and word(original,0x1f2)>>8==134):
                if any(s['kind']=='modal' for s in groups[serial]):
                    report['first_divergence']={'kind':'unexpected repeat menu','serial':serial};break
                repeat_pending={'serial':serial,'actions':reader.get('interaction_action_count')}
                report['repeat_observation']['attempt_serial']=serial
            latest_held=None
            for sample in groups[serial]:
                kind=sample['kind'];reader=Reader(native)
                if kind=='player':
                    if latest_held!=sample['held']:
                        report['first_divergence']={'kind':'player consumer mismatch','serial':serial};break
                    continue
                phase=reader.get('opening_phase')
                expected_phase=0 if kind=='main' else MODAL[sample['pc']]
                if phase!=expected_phase:
                    report['first_divergence']={'kind':'input phase mismatch','serial':serial,'sample':kind,
                                                'model_phase':phase,'expected_phase':expected_phase};break
                previous=reader.word(0x1e8)
                if kind=='main' and previous!=sample['previous']:
                    report['first_divergence']={'kind':'controller previous mismatch','serial':serial};break
                if kind=='modal' and (sample['previous']!=sample['held'] or
                    sample['edge']!=((sample['held']^previous)&sample['held'])):
                    report['first_divergence']={'kind':'modal controller edge mismatch','serial':serial};break
                if not step(journal_pad(sample['held']),serial,sample):break
                if kind=='modal':report['modal_steps']+=1
                latest_held=sample['held']
            if report['first_divergence']:break
        if (not report['first_divergence'] and report['pickup_required'] and
            (not report['modal_steps'] or not all(report['pickup_observation'].values()))):
            report['first_divergence']={'kind':'required pickup transition not covered'}
        if not report['first_divergence'] and report['scalpel_required'] and not all(report['scalpel_observation'].values()):
            report['first_divergence']={'kind':'required scalpel transition not covered'}
        if not report['first_divergence'] and report['repeat_required'] and not report['repeat_observation']['verified']:
            report['first_divergence']={'kind':'required repeat attempt not covered'}
        report['result']='passed' if not report['first_divergence'] and report['source_checkpoints']==len(entries) else 'bounded'
    except (AssertionError,ValueError,RuntimeError) as exc:
        report['result']='bounded';report['first_divergence']={'kind':'checker or compiler error','exception':type(exc).__name__}
    finally:native.close()
    changed=[k for k,v in hashes.items() if not Path(k).exists() or sha(Path(k).read_bytes())!=v]
    if changed:
        report['underlying_divergence']=report['first_divergence'];report['result']='source_changed'
        report['first_divergence']={'kind':'source changed during check','files':changed}
    watched_inputs=((ref/'receipt.json',sha(receipt_bytes)),(ref/'controller_journal.json',sha(journal_bytes)),
                    (a.checkpoint_baseline.resolve()/'receipt.json',sha(checkpoint_bytes)),
                    (a.unpatched_baseline.resolve()/'receipt.json',sha(unpatched_bytes)),
                    (ref/title_items[0]['file'],TITLE_SHA256),(ref/'save_ram.bin',SAVE_SHA256),
                    (a.rom,ROM_SHA256),(native_dir/'fdisbull_native.c',build['source_sha256']),
                    (native_dir/'fdisbull_native.h',build['header_sha256']),
                    (native_dir/'libfdisbull_native.dylib',build['dylib_sha256']))
    changed_inputs=[str(path) for path,digest in watched_inputs if not path.exists() or sha(path.read_bytes())!=digest]
    if changed_inputs:
        report['underlying_divergence']=report['first_divergence'];report['result']='input_changed'
        report['first_divergence']={'kind':'input changed during check','files':changed_inputs}
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('result','source_checkpoints','source_elements','public_steps','modal_steps','compiler','first_divergence')},indent=2))
    if report['result']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
