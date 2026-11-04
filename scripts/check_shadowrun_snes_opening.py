#!/usr/bin/env python3
"""Compare title-seeded opening execution to source main-loop checkpoints.

The model receives only the title seed, the caller's ROM/save, and ordinary
input epochs from the receipt. Later checkpoints are comparison evidence only.
Native execution uses the public transactional entry point. Source, compiler,
window and collision coverage are reported independently and remain bounded.
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
from fdisbull.shadowrun_snes_npc import FIELDS
from fdisbull.shadowrun_snes_opening import machine_from_title,TITLE_SHA256
from fdisbull.udc_macos import build_macos,_Compiler
from check_shadowrun_macos import Native

CORE='6d679f9123cbffe635815dfc137af88c2effc54bd9355f3cd112fb3cd4e51283'
JOURNAL_CORE='b98b6856f98d88070c1f28827dd95f8cc358d30f988c4bb14ab04c062fc81423'
UNPATCHED_CORE='89fe8f7602428dbe532a19f098075182619c576383f177e641b19eb1f5fa19e8'
FIRST='4af5e56bea7f16881567d4f73a9ca276493aeab0853ab3178d51e74e2c10f4d9'
PAD={'UP':1,'DOWN':2,'LEFT':4,'RIGHT':8,'START':16,'B':32,'SELECT':64}
ACTOR=('npc_x','npc_y','npc_z','npc_velocity_x','npc_velocity_y','npc_velocity_z',
       'npc_depth','npc_timer','npc_direction','npc_action','npc_task','npc_anim_kind','npc_anim_table')
ANIM=('npc_anim_reload','npc_anim_selector','npc_anim_phase',
      'npc_anim_increment','npc_anim_timer','npc_anim_mode','npc_anim_dx',
      'npc_anim_dy','npc_anim_dz','npc_anim_dh','npc_anim_extra')
TASK={'task_wait':0xbbe,'task_link':0x38e,'task_flags':0xc7e,
      'task_delay':0xc1e,'task_frame':0x26e,'task_callback':0x2ce,'task_next':0x32e}
WINDOW=(0x2000,0x2020,0x2040,0x2060,0x2080,0x20a0,0x20c0,0x20e0,0x2100,
        0x2120,0x2140,0x2160,0x2180)


def sha(b):return hashlib.sha256(b).hexdigest()
def word(b,at):return b[at]|(b[at+1]<<8)


class Mismatch(Exception):
    def __init__(self,field,model,source):
        self.detail={'field':field,'model':model,'source':source}


class Reader:
    """Use only the public state-get ABI, with a per-checkpoint cache."""
    def __init__(self,native):self.native=native;self.cache={}
    def get(self,name,index=0):
        key=(name,index)
        if key not in self.cache:
            out=ctypes.c_int64()
            if self.native.lib.fdisbull_state_get(self.native.ctx,name.encode(),index,ctypes.byref(out)):
                raise ValueError(f'native state unavailable: {name}[{index}]')
            self.cache[key]=out.value
        return self.cache[key]
    def byte(self,addr):return self.get('task_shared',addr)
    def word(self,addr):return self.byte(addr)|(self.byte(addr+1)<<8)
    def other_word(self,addr):return self.get('scene_7f',addr)|(self.get('scene_7f',addr+1)<<8)
    def snapshot(self,template):
        return {k:[self.get(k,i) for i in range(len(v))] if isinstance(v,list) else self.get(k)
                for k,v in template.items()}


def order(source,at_count,at_list):
    count=word(source,at_count)
    if count==0xfffe:return []
    if count&0x8001 or count>=88:raise ValueError('invalid source actor count')
    values=[word(source,at_list+i) for i in range(0,count+2,2)]
    if len(set(values))!=len(values) or any(v&1 or v>=88 for v in values):raise ValueError('invalid source actor order')
    return values


def task_order(source):
    result=[];i=word(source,0x268)
    while not i&0x8000:
        if i&1 or i>=96 or i in result:raise ValueError('invalid source task list')
        result.append(i);i=word(source,0x32e+i)
    return result


def pad_at(intervals,frame):
    mask=0
    for item in intervals:
        if item['start']<=frame<item['end']:
            for name in item['buttons']:
                if name not in PAD:raise ValueError('input has no qualified logical mapping: '+name)
                mask|=PAD[name]
    return mask


def journal_pad(held):
    """Translate the observed source controller word to the model input ABI."""
    pairs=((0x800,1),(0x400,2),(0x200,4),(0x100,8),
           (0x1000,16),(0x8000,32),(0x2000,64))
    supported=0;pad=0
    for bit,out in pairs:
        supported|=bit
        if held&bit:pad|=out
    if held&~supported:raise ValueError('observed controller word has unsupported buttons')
    return pad


def read_controller_journal(path,reference,entries,baseline=None,baseline_sha256=None):
    """Validate an independent input observer against the checkpoint route."""
    raw=path.read_bytes();observer_bytes=(path.parent/'receipt.json').read_bytes()
    observer=json.loads(observer_bytes)
    data=json.loads(raw)
    if baseline is None:
        if reference.get('core_sha256')!=CORE:
            raise ValueError('an independent pre-journal baseline receipt is required')
        baseline=reference
    if (baseline.get('core_sha256')!=CORE or baseline.get('rom_sha256')!=ROM_SHA256 or
        baseline.get('patches') or baseline.get('memory_injection_mode')!='no memory patches'):
        raise ValueError('unexpected independent controller baseline')
    if (observer['core_sha256']!=JOURNAL_CORE or observer['rom_sha256']!=ROM_SHA256 or
        observer['patches'] or observer['memory_injection_mode']!='no memory patches' or
        observer.get('snes_controller_journal_sha256')!=sha(raw) or
        observer['frames']!=reference['frames'] or observer['inputs']!=reference['inputs'] or
        observer['frames']!=baseline['frames'] or observer['inputs']!=baseline['inputs'] or
        any(observer[k]!=reference[k] for k in ('system_ram_sha256','state_sha256','frame_rgb_sha256','frame_png_sha256','save_ram_sha256')) or
        any(observer[k]!=baseline[k] for k in ('system_ram_sha256','state_sha256','frame_rgb_sha256','frame_png_sha256','save_ram_sha256')) or
        data.get('format')!='snes-main-loop-controller-journal-1' or data.get('dropped')!=0 or
        data.get('duplicate_serials') or data.get('conflicting_serials') or data.get('consumer_disagreements')):
        raise ValueError('controller observer identity, neutrality or integrity mismatch')
    checkpoints=observer['snes_checkpoints']
    if checkpoints['pc']!=0x80962e or checkpoints['phase']!=reference['snes_checkpoints']['phase']:
        raise ValueError('controller observer checkpoint phase mismatch')
    observed={}
    for frame in checkpoints['frames']:
        if frame['dropped']:raise ValueError('controller observer checkpoint drops')
        for c in frame['captures']:
            serial=c['serial']
            if serial in observed:raise ValueError('duplicate controller checkpoint serial')
            observed[serial]=(frame['video_frame'],c['sha256'],c['size'],c['registers']['pc'])
    independent=baseline['snes_checkpoints']
    if independent['pc']!=0x80962e or independent['phase']!=checkpoints['phase']:
        raise ValueError('independent controller baseline checkpoint phase mismatch')
    baseline_captures={}
    for frame in independent['frames']:
        if frame['dropped']:raise ValueError('independent controller baseline dropped checkpoints')
        for c in frame['captures']:
            serial=c['serial']
            if serial in baseline_captures:raise ValueError('duplicate independent checkpoint serial')
            baseline_captures[serial]=(frame['video_frame'],c['sha256'],c['size'],c['registers']['pc'])
    if not observed or observed!=baseline_captures or set(observed)!=set(range(1,len(observed)+1)):
        raise ValueError('controller observer does not match independent baseline checkpoints')
    for frame,c in entries:
        if observed.get(c['serial'])!=(frame,c['sha256'],131072,0x80962e):
            raise ValueError('controller observer and reference checkpoint mismatch')
    main={};players={}
    for sample in data['samples']:
        kind=sample.get('kind');serial=sample.get('serial')
        if kind not in ('main','player') or type(serial) is not int or serial<1:
            raise ValueError('invalid controller sample identity')
        if any(type(sample.get(k)) is not int or not 0<=sample[k]<=65535 for k in ('held','previous','edge')):
            raise ValueError('invalid source controller words')
        if type(sample.get('video_frame')) is not int or sample['video_frame']<0:
            raise ValueError('invalid controller sample frame')
        if kind=='main':
            if sample.get('actor') is not None:raise ValueError('main controller actor must be absent')
            target=main
        else:
            if type(sample.get('actor')) is not int or sample['actor']&1 or not 0<=sample['actor']<88:
                raise ValueError('invalid player controller actor')
            target=players
        if serial in target:raise ValueError('duplicate controller consumer sample')
        target[serial]=sample
    for i in range(len(entries)-1):
        frame,item=entries[i];next_frame=entries[i+1][0];serial=item['serial']
        sample=main.get(serial)
        if sample is None:raise ValueError(f'missing main controller sample for serial {serial}')
        if not frame<=sample['video_frame']<=next_frame:
            raise ValueError('main controller sample outside its checkpoint interval')
        journal_pad(sample['held'])
        player=players.get(serial)
        if player is not None:
            if not frame<=player['video_frame']<=next_frame or player['held']!=sample['held']:
                raise ValueError('main and player controller samples disagree')
    return main,players,{'sha256':sha(raw),'observer_receipt_sha256':sha(observer_bytes),
                         'observer_core_sha256':JOURNAL_CORE,
                         'independent_core_sha256':CORE,'independent_receipt_sha256':baseline_sha256,
                         'independent_checkpoint_count':len(baseline_captures),
                         'main_samples':len(main),'player_samples':len(players),
                         'required_transition_samples':len(entries)-1,
                         'neutrality':'checkpoint hashes and final RAM/state/frame/save match earlier checkpoint-only instrumented core; not a second emulator'}


def check_unpatched_baseline(reference,observer_bytes,baseline_bytes):
    """Compare recorded ordinary-run hashes; baseline has no PC checkpoints."""
    observer=json.loads(observer_bytes);baseline=json.loads(baseline_bytes)
    if (observer!=reference or observer['core_sha256']!=JOURNAL_CORE or
        baseline['core_sha256']!=UNPATCHED_CORE or baseline['rom_sha256']!=ROM_SHA256 or
        baseline['patches'] or baseline['memory_injection_mode']!='no memory patches' or
        any(observer[k]!=baseline[k] for k in ('rom_sha256','inputs','frames','system_ram_sha256',
             'state_sha256','frame_rgb_sha256','frame_png_sha256','save_ram_sha256'))):
        raise ValueError('unpatched baseline identity or final-state mismatch')
    def selected(key,fields):
        def index(receipt):
            rows=receipt[key];result={row['frame']:tuple(row[k] for k in fields) for row in rows}
            if len(result)!=len(rows):raise ValueError('duplicate unpatched baseline frame')
            return result
        left,right=index(observer),index(baseline)
        if not left or left!=right:raise ValueError('unpatched baseline selected-frame mismatch')
        return len(left)
    return {'observer_receipt_sha256':sha(observer_bytes),'baseline_receipt_sha256':sha(baseline_bytes),
            'baseline_core_sha256':UNPATCHED_CORE,
            'selected_ram_frames':selected('frame_ram',('size','sha256')),
            'selected_image_frames':selected('frame_images',('width','height','rgb_sha256','png_sha256')),
            'scope':'selected post-frame hashes and final state; unpatched baseline has no instruction checkpoints'}


def check(reader,source,*,dynamic_ready=True):
    """Compare declared behavioral readsets; return counts, not source bytes."""
    counts={'actor_fields':0,'task_fields':0,'window_fields':0,'collision_elements':0,
            'sprite_fields':0,'text_bytes':0}
    def eq(field,a,b,group):
        counts[group]+=1
        if a!=b:raise Mismatch(field,a,b)
    actors=order(source,0x14cc,0x14ce)
    actual_count=reader.word(0x14cc)
    expected_count=word(source,0x14cc)
    eq('actor_count',actual_count,expected_count,'actor_fields')
    actual=[reader.word(0x14ce+2*i) for i in range(len(actors))]
    if actual!=actors:raise Mismatch('actor_order',actual,actors)
    for slot in actors:
        for base in (0x12bc,0x1314,0x3f5c,0x115c):
            eq(f'{slot:02x}.sprite.{base:04x}',reader.word(base+slot),word(source,base+slot),'sprite_fields')
        action=word(source,FIELDS['npc_action']+slot)
        for name in ACTOR+(ANIM if action!=0xffff else ()):
            at=FIELDS[name]+slot;eq(f'{slot:02x}.{name}',reader.word(at),word(source,at),'actor_fields')
        # Bits participating in actor dispatch, collision, gravity and control.
        at=FIELDS['npc_flags']+slot
        eq(f'{slot:02x}.physics_flags',reader.word(at)&0x56b,word(source,at)&0x56b,'actor_fields')
        mode=word(source,0x0fa4+slot)
        eq(f'{slot:02x}.sort_mode',reader.word(0x0fa4+slot),mode,'actor_fields')
        if mode:
            eq(f'{slot:02x}.sort_delta',reader.word(0x0ffc+slot),word(source,0x0ffc+slot),'actor_fields')
        if word(source,FIELDS['npc_timer']+slot):
            for name in ('npc_control','npc_target_x','npc_target_y'):
                at=FIELDS[name]+slot;eq(f'{slot:02x}.{name}',reader.word(at),word(source,at),'actor_fields')
    tasks=task_order(source);model=[];i=reader.get('task_list_head')
    for name,at in (('task_list_head',0x268),('task_list_free',0x26a),('task_list_current',0x26c)):
        eq(name,reader.get(name),word(source,at),'task_fields')
    while not i&0x8000:
        if i&1 or i>=96 or i in model:raise ValueError('invalid model task list')
        model.append(i);i=reader.get('task_next',i//2)
    if model!=tasks:raise Mismatch('task_order',model,tasks)
    for task in tasks:
        for name,base in TASK.items():
            eq(f'{task:02x}.{name}',reader.get(name,task//2),word(source,base+task),'task_fields')
        frame=word(source,0x26e+task)
        if not 0x3f2<=frame<=0xbb5:raise ValueError('source active task frame outside heap')
        for off,name in ((3,'pc'),(7,'sp')):
            j=frame+off-0x3f2
            val=reader.get('task_heap',j)|(reader.get('task_heap',j+1)<<8)
            eq(f'{task:02x}.{name}',val,word(source,frame+off),'task_fields')
    for at in (0x21e,0x220,0x22e,0x232,0x234,0x236,0x238,0x23a,0x23c,0x23e,0x240):
        eq(f'window.{at:04x}',reader.word(at),word(source,at),'window_fields')
    head=word(source,0x220)
    if not head&0x8000:
        if head&1 or head>=32:raise ValueError('invalid source window head')
        for slot in range(0,head+2,2):
            eq(f'window.{slot:02x}.active',reader.word(0x242+slot),word(source,0x242+slot),'window_fields')
            if not word(source,0x242+slot):continue
            for base in WINDOW:
                eq(f'window.{slot:02x}.{base:04x}',reader.word(base+slot),word(source,base+slot),'window_fields')
    for at in (0x0d38,0x0d3a):
        eq(f'sprite.pool.{at:04x}',reader.word(at),word(source,at),'sprite_fields')
    for off in range(0,240,2):
        eq(f'sprite.node.{off:02x}',reader.word(0x1580+off),word(source,0x1580+off),'sprite_fields')
    if reader.get('opening_message_count'):
        for off in range(256):
            a=reader.byte(0x21a0+off);b=source[0x21a0+off]
            counts['text_bytes']+=1
            # The receipt records location only; original text stays private.
            if a!=b:raise Mismatch(f'text.byte.{off:03x}','redacted','redacted')
            if not b:break
        else:raise ValueError('source text has no terminator within decoder bound')
    # Match both head arrays and each reachable node, record and owner. The
    # unallocated tail may retain stale bytes and is deliberately excluded.
    seen_nodes=set();seen_records=set()
    for name,at in (('static_record_end',0xde84),('static_node_end',0xde86)):
        eq('collision.'+name,reader.word(at),word(source,at),'collision_elements')
    heads=[(0xde88,'static')]
    if dynamic_ready:heads.append((0xe088,'dynamic'))
    for head_base,label in heads:
        for cell in range(0,512,2):
            node=word(source,head_base+cell)
            eq(f'collision.{label}.head.{cell:03x}',reader.word(head_base+cell),node,'collision_elements')
            chain=set()
            while not node&0x8000:
                if node&1 or node>0x85e or node in chain:raise ValueError('invalid source collision chain')
                chain.add(node)
                rec=word(source,0xef18+node);nxt=word(source,0xf778+node)
                if rec>0xc78 or rec%12:raise ValueError('invalid source collision record')
                if node not in seen_nodes:
                    eq(f'collision.node.{node:03x}.record',reader.word(0xef18+node),rec,'collision_elements')
                    eq(f'collision.node.{node:03x}.next',reader.word(0xf778+node),nxt,'collision_elements')
                    seen_nodes.add(node)
                if rec not in seen_records:
                    for off in range(0,12,2):
                        eq(f'collision.record.{rec:03x}.{off}',reader.word(0xe288+rec+off),
                           word(source,0xe288+rec+off),'collision_elements')
                    owner=0xe214+(rec>>2)
                    eq(f'collision.record.{rec:03x}.owner',reader.other_word(owner),
                       word(source,65536+owner),'collision_elements')
                    seen_records.add(rec)
                node=nxt
    return counts


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('rom','reference','output'):p.add_argument('--'+k,required=True,type=Path)
    p.add_argument('--until-serial',required=True,type=int)
    p.add_argument('--controller-journal',type=Path,help='optional validated source controller-consumer observation')
    p.add_argument('--controller-baseline',type=Path,help='independent pre-journal reference directory when the main reference uses the journal observer')
    p.add_argument('--unpatched-baseline',type=Path,help='optional ordinary unmodified-core run directory for selected-frame and final-state neutrality')
    p.add_argument('--native-build',type=Path,help='optional previously built private native directory, revalidated against this exact program and title seed')
    a=p.parse_args();out=a.output.resolve();ref=a.reference.resolve()
    if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):
        raise ValueError('output must be a fresh private directory outside Git')
    receipt=(ref/'receipt.json').read_bytes();r=json.loads(receipt);c=r['snes_checkpoints']
    if (r['system']!='snes' or r['core_sha256'] not in (CORE,JOURNAL_CORE) or r['rom_sha256']!=ROM_SHA256 or
        r['patches'] or r['memory_injection_mode']!='no memory patches' or c['pc']!=0x80962e or
        c['phase']!='before selected opcode at instruction entry; video frame identifies containing retro_run' or
        r['frame_images_phase']!='after retro_run; frame is zero-based'):
        raise ValueError('unexpected source identity, injection, or checkpoint phase')
    entries=[];seen=set()
    for f in c['frames']:
        if f['dropped']:raise ValueError('original checkpoint drops')
        for n,x in enumerate(f['captures']):
            if x['file']!=f"checkpoint-{f['video_frame']:06d}-{n:02d}.bin" or x['file'] in seen:
                raise ValueError('unexpected or duplicate checkpoint filename')
            if x['size']!=131072 or x['registers']['pc']!=0x80962e:raise ValueError('bad checkpoint metadata')
            seen.add(x['file']);entries.append((f['video_frame'],x))
    if (not entries or entries[0][1]['serial']!=1 or entries[0][1]['sha256']!=FIRST or
        any(y[1]['serial']!=x[1]['serial']+1 for x,y in zip(entries,entries[1:]))):
        raise ValueError('source serial sequence is not consecutive from first pass')
    if a.until_serial<2 or a.until_serial>entries[-1][1]['serial']:
        raise ValueError('requested serial must include at least one update and be present')
    available_serial=entries[-1][1]['serial']
    entries=entries[:a.until_serial]
    if entries[-1][1]['serial']!=a.until_serial:raise ValueError('serial selection mismatch')
    rom=a.rom.read_bytes();save=(ref/'save_ram.bin').read_bytes()
    title_item=[x for x in r['frame_ram'] if x['frame']==839]
    if len(title_item)!=1 or title_item[0]['file']!='ram-000839.bin':raise ValueError('missing title seed')
    title=(ref/title_item[0]['file']).read_bytes()
    if (sha(rom)!=ROM_SHA256 or sha(save)!=SAVE_SHA256 or len(title)!=131072 or
        sha(title)!=TITLE_SHA256 or title_item[0]['sha256']!=TITLE_SHA256):raise ValueError('ROM/save/title mismatch')
    intervals=r['inputs']
    for item in intervals:
        if (not isinstance(item.get('start'),int) or not isinstance(item.get('end'),int) or
            item['start']<0 or item['start']>=item['end'] or not isinstance(item.get('buttons'),list) or
            any(name not in PAD for name in item['buttons'])):raise ValueError('unqualified input epoch')
    if pad_at(intervals,839)!=0 or pad_at(intervals,840)!=16:
        raise ValueError('title START epoch differs from qualified route')
    main_samples=player_samples=None;journal_info=None
    if a.controller_journal is not None:
        baseline=None;baseline_hash=None
        if a.controller_baseline is not None:
            baseline_bytes=(a.controller_baseline.resolve()/'receipt.json').read_bytes()
            baseline=json.loads(baseline_bytes);baseline_hash=sha(baseline_bytes)
        elif r['core_sha256']==CORE:
            baseline_hash=sha(receipt)
        main_samples,player_samples,journal_info=read_controller_journal(
            a.controller_journal.resolve(),r,entries,baseline,baseline_hash)
    unpatched_info=None
    if a.unpatched_baseline is not None:
        if journal_info is None:raise ValueError('unpatched baseline requires a validated controller journal')
        unpatched_bytes=(a.unpatched_baseline.resolve()/'receipt.json').read_bytes()
        unpatched_info=check_unpatched_baseline(r,receipt,unpatched_bytes)
    watched=[Path(__file__).resolve(),ROOT/'src/fdisbull/shadowrun_snes_opening.py']
    watched+=sorted((ROOT/'src/fdisbull/game_sources').glob('shadowrun_snes_*.c'))
    watched+=sorted((ROOT/'src/fdisbull').glob('shadowrun_snes_*.py'))
    hashes={str(x):sha(x.read_bytes()) for x in watched}
    m,regions=machine_from_title(rom,title,save);template=m.snapshot()
    out.mkdir(mode=0o700,parents=True)
    if a.native_build is None:
        native_dir=out/'native'
        build=build_macos(m.program,template,native_dir,entry='shadowrun_snes_frame')
        build_origin={'kind':'fresh','directory':str(native_dir)}
    else:
        native_dir=a.native_build.resolve()
        if any((x/'.git').exists() for x in (native_dir,*native_dir.parents)):
            raise ValueError('native build must be private and outside Git')
        build_bytes=(native_dir/'receipt.json').read_bytes();build=json.loads(build_bytes)
        seed_digest=sha(json.dumps(template,sort_keys=True,separators=(',',':')).encode())
        generated=_Compiler(m.program,template,entry='shadowrun_snes_frame').generate(m.program)
        if (build.get('program_sha256')!=sha(canonical(m.program)) or build.get('seed_sha256')!=seed_digest or
            build.get('entry')!='shadowrun_snes_frame' or build.get('unsupported_status')!='shadowrun_snes_frame_status' or
            build.get('architecture')!='arm64' or
            build.get('dylib_sha256')!=sha((native_dir/'libfdisbull_native.dylib').read_bytes()) or
            build.get('source_sha256')!=sha(generated.encode()) or
            build.get('source_sha256')!=sha((native_dir/'fdisbull_native.c').read_bytes()) or
            build.get('header_sha256')!=sha((native_dir/'fdisbull_native.h').read_bytes())):
            raise ValueError('reused native build does not match exact program, seed or artifacts')
        build_origin={'kind':'validated_reuse','directory':str(native_dir),'receipt_sha256':sha(build_bytes)}
    native=Native(native_dir/'libfdisbull_native.dylib',a.rom.resolve())
    report={'format':'shadowrun-snes-opening-checkpoint-1','result':'running',
      'scope':'title-seeded logical opening; selected actor, task, window, sprite allocator, decoded text and reachable collision fields; rendering/audio excluded',
      'input_phase':('title START frame840; source-observed main-consumer held input per preceding serial' if journal_info else
                     'title START frame840; each source pass uses normalized input at preceding checkpoint video frame'),
      'controller_journal':journal_info,
      'unpatched_baseline':unpatched_info,
      'clock':'consecutive instruction-entry checkpoints at 80:962E',
      'collision_coverage':'static reachable lists from serial1; dynamic reachable lists after first logical rebuild, starting serial2',
      'requested_until_serial':a.until_serial,'available_until_serial':available_serial,
      'receipt_sha256':sha(receipt),'title_sha256':sha(title),'rom_sha256':sha(rom),'core_sha256':r['core_sha256'],
      'program_sha256':sha(canonical(m.program)),'source_hashes':hashes,'native_build':build,'native_build_origin':build_origin,
      'source_checkpoints':0,'source_elements':{'actor_fields':0,'task_fields':0,'window_fields':0,'collision_elements':0,'sprite_fields':0,'text_bytes':0},
      'compiler':{'continuous_complete_state_prefix':[],'sampled_one_step_from_native':[],'native_elements':0},
      'input_epochs':[],'first_divergence':None}
    def capture(item):
        b=(ref/item['file']).read_bytes()
        if len(b)!=131072 or sha(b)!=item['sha256']:raise ValueError('source checkpoint hash mismatch')
        return b
    last_pad=None
    try:
        report['compiler']['native_elements']+=native.compare(template,'title seed')
        m.call('shadowrun_snes_frame',16);s=m.snapshot();rc=native.step(16)
        if rc or s['shadowrun_snes_frame_status']!=1:
            report['first_divergence']={'serial':1,'kind':'title initialization refused','native_return':rc}
        else:
            report['compiler']['native_elements']+=native.compare(s,'title start')
            report['compiler']['continuous_complete_state_prefix'].append('title START')
            reader=Reader(native)
            try:
                delta=check(reader,capture(entries[0][1]),dynamic_ready=False)
                for key,value in delta.items():report['source_elements'][key]+=value
                report['source_checkpoints']=1
            except Mismatch as exc:report['first_divergence']={'serial':1,'kind':'source mismatch',**exc.detail}
            except ValueError as exc:report['first_divergence']={'serial':1,'kind':'invalid source or model state','detail':str(exc)}
        for i in range(1,len(entries)):
            if report['first_divergence']:break
            prev_frame=entries[i-1][0];frame,item=entries[i]
            if main_samples is not None:
                sample=main_samples[entries[i-1][1]['serial']]
                model_previous=Reader(native).word(0x01e8)
                if model_previous!=sample['previous']:
                    report['first_divergence']={'serial':item['serial'],'kind':'controller previous-state mismatch',
                                                'model':model_previous,'source':sample['previous']};break
                pad=journal_pad(sample['held'])
            else:
                pad=pad_at(intervals,prev_frame)
                if any(pad_at(intervals,f)!=pad for f in range(prev_frame,frame)):
                    report['first_divergence']={'serial':item['serial'],'kind':'ambiguous input epoch across checkpoint gap'};break
            if pad!=last_pad:
                report['input_epochs'].append({'from_serial':item['serial'],'preceding_video_frame':prev_frame,'logical_pad':pad});last_pad=pad
            sampled=i<=2 or item['serial'] in (63,183,300,500,800,1200,1600,1820)
            if sampled:
                prior=Reader(native).snapshot(template)
                if i>2:m.set_state(prior)
                m.call('shadowrun_snes_frame',pad);ms=m.snapshot()
            rc=native.step(pad)
            if rc:
                reader=Reader(native)
                if not sampled:
                    prior=reader.snapshot(template);m.set_state(prior);m.call('shadowrun_snes_frame',pad);ms=m.snapshot()
                rollback=True;retry=None
                try:
                    report['compiler']['native_elements']+=native.compare(prior,('refusal rollback',item['serial']))
                    retry=native.step(pad)
                    report['compiler']['native_elements']+=native.compare(prior,('refusal retry rollback',item['serial']))
                    if retry!=rc:rollback=False
                except AssertionError:
                    rollback=False
                report['first_divergence']={'serial':item['serial'],'kind':'unsupported' if rc==1 else 'native fault',
                  'native_return':rc,'retry_return':retry,'model_status':ms['shadowrun_snes_frame_status'],
                  'failure':ms['opening_failure'],'task':ms['opening_fault_task'],
                  'native_callback':ms['opening_fault_native'],'vm_opcode':ms['task_vm_fault_op'],
                  'vm_pc':ms['task_vm_fault_pc'],'rollback_verified':rollback};break
            if sampled:
                if ms['shadowrun_snes_frame_status']!=1:raise ValueError('UIL/native support disagreement')
                report['compiler']['native_elements']+=native.compare(ms,('compiler',item['serial']))
                if i<=2:report['compiler']['continuous_complete_state_prefix'].append(item['serial'])
                else:report['compiler']['sampled_one_step_from_native'].append(item['serial'])
            reader=Reader(native)
            try:
                delta=check(reader,capture(item))
                for key,value in delta.items():report['source_elements'][key]+=value
                report['source_checkpoints']+=1
            except Mismatch as exc:
                report['first_divergence']={'serial':item['serial'],'kind':'source mismatch',**exc.detail};break
            except ValueError as exc:
                report['first_divergence']={'serial':item['serial'],'kind':'invalid source or model state','detail':str(exc)};break
        if not report['first_divergence'] and report['source_checkpoints']==len(entries) and len(entries)>=2:
            report['result']='passed'
        else:report['result']='bounded'
    except (AssertionError,ValueError,RuntimeError) as exc:
        report['result']='bounded'
        report['first_divergence']={'kind':'checker or compiler verification error',
                                    'exception':type(exc).__name__}
    finally:native.close()
    changed=[k for k,v in hashes.items() if not Path(k).exists() or sha(Path(k).read_bytes())!=v]
    if changed:
        report['underlying_divergence']=report['first_divergence']
        report['result']='source_changed'
        report['first_divergence']={'kind':'source changed during check','files':changed}
    changed_inputs=[]
    for path,digest in ((ref/'receipt.json',sha(receipt)),(ref/title_item[0]['file'],TITLE_SHA256),
                        (ref/'save_ram.bin',SAVE_SHA256),(a.rom,ROM_SHA256),
                        (native_dir/'libfdisbull_native.dylib',build['dylib_sha256']),
                        (native_dir/'fdisbull_native.c',build['source_sha256']),
                        (native_dir/'fdisbull_native.h',build['header_sha256'])):
        if not path.exists() or sha(path.read_bytes())!=digest:changed_inputs.append(str(path))
    if journal_info:
        for path,digest in ((a.controller_journal.resolve(),journal_info['sha256']),
                            (a.controller_journal.resolve().parent/'receipt.json',journal_info['observer_receipt_sha256'])):
            if not path.exists() or sha(path.read_bytes())!=digest:changed_inputs.append(str(path))
        if a.controller_baseline is not None:
            path=a.controller_baseline.resolve()/'receipt.json'
            if not path.exists() or sha(path.read_bytes())!=journal_info['independent_receipt_sha256']:
                changed_inputs.append(str(path))
    if unpatched_info:
        path=a.unpatched_baseline.resolve()/'receipt.json'
        if not path.exists() or sha(path.read_bytes())!=unpatched_info['baseline_receipt_sha256']:
            changed_inputs.append(str(path))
    if changed_inputs:
        report['underlying_divergence']=report['first_divergence']
        report['result']='input_changed'
        report['first_divergence']={'kind':'input changed during check','files':changed_inputs}
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('result','requested_until_serial','source_checkpoints','source_elements','compiler','first_divergence')},indent=2))
    if report['result']!='passed':raise SystemExit(1)

if __name__=='__main__':main()
