#!/usr/bin/env python3
"""Compare the pinned native6502 full-game cartridge with its actual UIL tree.

Component calls use declared assisted RAM/procedure inputs. Original component
case bundles can be replayed unchanged, making the CPU->UIL->NES bridge explicit.
Natural and performance sessions are separate from these controlled commands.
All state- and byte-retaining outputs must remain in a fresh private directory.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import GameMachine, canonical
from fdisbull.udl_miniplanets_full import lift_full_game
from check_miniplanets_native import _private_output
from verify_miniplanets_level import NES_SHA, GEN_SHA, plans, schedule


def sha(raw): return hashlib.sha256(raw).hexdigest()
def save(path, obj): path.write_text(json.dumps(obj, indent=2) + '\n')


def encode_state(state, layout):
    size = max(x['offset'] + x['length'] for x in layout.values())
    raw = bytearray(size)
    for name, field in layout.items():
        width = field['element_bits'] // 8
        values = state[name] if field['array_length'] != 1 else [state[name]]
        if len(values) != field['array_length']: raise ValueError('state array length mismatch')
        data = b''.join((v & ((1 << (width*8))-1)).to_bytes(width, 'little') for v in values)
        raw[field['offset']:field['offset']+field['length']] = data
    return bytes(raw)


def decode_state(raw, layout):
    result = {}
    for name, field in layout.items():
        width, offset = field['element_bits']//8, field['offset']
        values = [int.from_bytes(raw[offset+i*width:offset+(i+1)*width], 'little',
                                 signed=field['signed']) for i in range(field['array_length'])]
        result[name] = values if field['array_length'] != 1 else values[0]
    return result


def patch(frame, memory_id, offset, raw):
    return {'frame': frame, 'memory_id': memory_id, 'offset': offset, 'data_hex': raw.hex()}


def publication_records(trace, manifest):
    """Consume only even, versioned, consecutively numbered completed slots."""
    pub=manifest['publication'];expected=1;records=[]
    for row in trace['frames']:
        raw=bytes.fromhex(row['raw']['publication'])
        tape=bytes.fromhex(row['raw']['publication_hv'])
        for _ in range(pub['slots']):
            slot=expected%pub['slots'];start=slot*pub['stride']
            packet=raw[start:start+pub['stride']]
            sequence=packet[pub['sequence']]
            if sequence&1 or packet[pub['version']]!=1:break
            number=int.from_bytes(packet[pub['epoch']:pub['epoch']+2],'little')
            if number!=expected:
                if records and number>expected and (number-expected)%pub['slots']==0:
                    raise AssertionError(f'completed publication ring overrun: expected{expected}, observed{number}')
                break
            fields={name:int.from_bytes(packet[at:at+width],'little')
                    for name,(at,width) in pub['fields'].items()}
            count=packet[pub['hv_count_offset']];hv=pub['hv_recording']
            if count>hv['max_words']:raise AssertionError('published HV count exceeds slot capacity')
            at=slot*hv['stride']
            words=[int.from_bytes(tape[at+i*2:at+i*2+2],hv['byte_order']) for i in range(count)]
            records.append({'epoch':number,'host_frame':row['frame'],'fields':fields,'hv':words})
            expected+=1
    return records


def shadow_publications(program, rom, manifest, receipt, trace, *, seeded_state=None, seed_frame=None):
    records=publication_records(trace,manifest)
    if not records:raise AssertionError('normal session produced no completed publication')
    # Power-on RAM precedes the reset routine, so only initialized execution
    # has a meaningful fault byte. A valid publication establishes that edge.
    first_initialized=records[0]['host_frame']
    for row in trace['frames']:
        if row['frame']>=first_initialized:
            fault=bytes.fromhex(row['raw']['debug'])[0x7ed-0x7d0]
            if fault:raise AssertionError(f'native runtime fault{fault} at host frame{row["frame"]}')
    machine=GameMachine(program,{0:rom},environment={'hv16':[0],'sound_busy':[0]})
    machine.call('game_boot');reset=False;checked=0;input_checked=0;gaps=[]
    counters={}
    for row in trace['frames']:
        counter=int.from_bytes(bytes.fromhex(row['raw']['debug'])[:2],'little')
        counters.setdefault(counter,[]).append(row['frame'])
    bits={'RIGHT':1,'LEFT':2,'UP':4,'DOWN':8,'A':16,'B':32,'START':64,'SELECT':128}
    input_checks=[];previous_sample=None
    for record in records:
        observed=record['fields']
        native_frame=observed['input_frame']
        if previous_sample is not None and not 0<((native_frame-previous_sample)&65535)<32768:
            raise AssertionError(f'normal scheduler reused or reversed sampled NMI frame at epoch{record["epoch"]}:{previous_sample}/{native_frame}')
        previous_sample=native_frame
        if seeded_state is not None and not reset and record['host_frame']>=seed_frame:
            machine.set_state(seeded_state);reset=True
        positions=counters.get(native_frame,[])
        # This is an independent controller expectation: scheduled host input,
        # indexed through the separately observed NMI frame counter. A missing
        # or ambiguous mapping stays unknown rather than using packet input as
        # its own oracle. This sampled-NMI timestamp identifies the input's
        # host frame directly; a later publication may have arbitrary latency.
        if len(positions)==1:
            host=positions[0];mask=trace['frames'][host]['input_mask']
            wanted=sum(bit for name,bit in bits.items() if mask&(1<<receipt['input_map'][name]))
            if wanted!=observed['input_buttons']:
                raise AssertionError(f'controller publication differs at epoch{record["epoch"]}: scheduled{wanted}, consumed{observed["input_buttons"]}, input_frame{native_frame}, host{host}')
            input_checked+=1
            input_checks.append({'epoch':record['epoch'],'sample_host_frame':positions[0],'controller_host_frame':host})
        else:
            gaps.append({'epoch':record['epoch'],'input_frame':native_frame,'candidate_host_frames':positions})
        machine.set_state({'input_buttons':observed['input_buttons']})
        machine.environment={'hv16':record['hv'] or [0], 'sound_busy':[observed['sound_busy_input']]}
        machine.environment_cursor={};machine.events=[]
        machine.call('game_frame');expected=machine.snapshot()
        if machine.environment_cursor.get('hv16',0)!=len(record['hv']):
            raise AssertionError(f'normal HV consumption differs at epoch{record["epoch"]}')
        differences={name:{'uil':expected[name],'native':value} for name,value in observed.items()
                     if name in expected and expected[name]!=value}
        if differences:raise AssertionError(f'normal completed-state divergence at epoch{record["epoch"]}:{differences}')
        checked+=1
    return {'completed_projection_ticks_checked':checked,'independent_controller_checks':input_checked,
            'controller_mapping_gaps':gaps,'projection_fields':len(manifest['publication']['fields'])-2,
            'controller_lag_from_sampled_nmi_host_frame':0,
            'strictly_increasing_sampled_nmi_frames':True,
            'initialized_runtime_fault_free':True,
            'first_epoch':records[0]['epoch'],'last_epoch':records[-1]['epoch'],
            'recorded_hv_words_replayed':sum(len(r['hv']) for r in records),
            'scope':'completed versioned publication vs actual UIL; controller checked independently where the NMI-to-host mapping is unique',
            'source':'even per-slot sequence and exact expected epoch; live working SRAM is not the oracle'},records


def run_host(core, cartridge, out, frames, watches, *, patches=(), inputs=(), images=(), audio=False, feedback=None):
    save(out.parent/(out.name+'-watch.json'), watches)
    save(out.parent/(out.name+'-patches.json'), list(patches))
    save(out.parent/(out.name+'-inputs.json'), list(inputs))
    args = [sys.executable, str(ROOT/'scripts/check_console_udc.py'), '--core', str(core),
            '--rom', str(cartridge), '--system', 'nes', '--frames', str(frames),
            '--watch', str(out.parent/(out.name+'-watch.json')),
            '--inputs', str(out.parent/(out.name+'-inputs.json')),
            '--patches', str(out.parent/(out.name+'-patches.json')),
            '--output', str(out), '--timeout', '300']
    if images: args += ['--frame-images', ','.join(map(str, images))]
    if audio: args.append('--capture-audio')
    if feedback is not None:
        path=out.parent/(out.name+'-feedback.json');save(path,feedback)
        args.extend(['--feedback-policy',str(path)])
    started = time.monotonic()
    run = subprocess.run(args, capture_output=True, text=True, timeout=320)
    if run.returncode: raise RuntimeError(run.stderr[-4000:])
    receipt = json.loads((out/'receipt.json').read_text())
    if receipt['rom_sha256'] != sha(cartridge.read_bytes()) or receipt['core_sha256'] != NES_SHA:
        raise AssertionError('native host input identity changed')
    return receipt, json.loads((out/'ram_trace.json').read_text()), time.monotonic()-started


def controlled_cases(program, rom, common_root=None, actor_roots=()):
    machine = GameMachine(program, {0:rom}, environment={'hv16':[0], 'sound_busy':[0]})
    zero = machine.snapshot()
    cases = []
    def add(name, entry, before=None, args=(), hv=None):
        cases.append({'name':name, 'entry':entry, 'before':{**zero, **(before or {})},
                      'args':list(args), 'hv':hv})
    add('smoke_phase', 'update_subpixel', {'anim':0x53})
    add('smoke_score', 'add_score', {'score':0x14999,'next_life':0x15000,
          'life_setting':2,'lives':5}, (1,))
    pool=[0]*192;pool[:4]=[27,0,0,1]
    add('smoke_spring_fx', 'run_objects', {'objects':pool})
    add('smoke_rng', 'rand16', {'rng_seed':0x2345}, hv=[123,456])
    for index in range(55):
        add(f'stage_load_{index}', 'begin_stage', {'stage':index,'time_setting':2,
              'life_setting':2,'lives':5}, (0,))
        machine.set_state(zero)
        machine.set_state({'stage':index,'time_setting':2,'life_setting':2,'lives':5})
        machine.call('begin_stage',0)
        add(f'stage_first_frame_{index}', 'game_frame', machine.snapshot())
    facts=json.loads((ROOT/'src/fdisbull/data/miniplanets_full_contract.json').read_text())
    mapping={**facts['contexts']['common'], **facts['contexts']['level']}
    def state_from_ram(case, fields):
        ram=bytearray(65536)
        for seed in case['ram']:
            at=seed['address']&65535;data=bytes.fromhex(seed['data']);ram[at:at+len(data)]=data
        state={**zero}
        for name, field in fields.items():
            a,n=field['address']&65535,field['length'];data=bytes(ram[a:a+n])
            if isinstance(zero[name],list): value=list(data)
            else:
                value=int.from_bytes(data,'big',signed=field.get('signed',False))-field.get('pointer_base',0)
            state[name]=value
        return state
    if common_root:
        root=Path(common_root)
        proof=json.loads((root/'summary.json').read_text())
        if proof['status']!='passed' or not proof['inputs_unchanged']:
            raise ValueError('original common CPU bundle is not qualified')
        tree_sha=sha(json.dumps(program['tree'],sort_keys=True,separators=(',',':')).encode())
        if proof.get('tree_sha256')!=tree_sha:
            raise ValueError('original common CPU qualification binds a different UIL tree')
        for name, fact in facts['procedures'].items():
            fields={**facts['contexts']['common'], **facts['contexts'][fact['context']]}
            for file in sorted(root.glob(name+'-[0-9][0-9][0-9].json')):
                contract=json.loads(file.read_text())
                for case in contract['cases']:
                    args=[case.get('registers',{}).get(k,0) for k in fact.get('arguments',[])]
                    add('original_common/'+name+'/'+case['name'],name,state_from_ram(case,fields),args)
    for root in map(Path,actor_roots):
        for file in sorted(root.glob('contract-*.json')):
            contract=json.loads(file.read_text())
            receipt_path=root/('native-'+file.stem.split('-')[-1])/'receipt.json'
            receipt=json.loads(receipt_path.read_text())
            if (not receipt['complete'] or receipt['source_sha256']!=sha(rom)
                    or receipt['core_sha256']!=GEN_SHA
                    or len(receipt['cases'])!=len(contract['cases'])):
                raise ValueError('incomplete or mismatched original actor bundle')
            for case, result in zip(contract['cases'],receipt['cases']):
                state=state_from_ram(case,mapping);regs=case.get('registers',{})
                hv=[h['value'] for h in result.get('observed_hv_reads',[])] or None
                entry=contract['entry']
                slot=((regs.get('A0',regs.get('A1',0xff0894))-0xff0894)//4)
                name='original_actor/'+root.name+'/'+case['name']
                if entry==0x4a72: add(name,'run_objects',state,hv=hv)
                elif entry==0x4a26: add(name,'init_objects',state)
                elif entry==0x4a3c: add(name,'add_object',state,[regs[k] for k in ('D7','D6','D5','D4')])
                elif entry==0x4cc4:
                    add(name+'/x','mace_x',state,[slot]);add(name+'/y','mace_y',state,[slot])
                elif entry in (0x4cec,0x4d0a,0x4d28,0x4d46):add(name,'run_raft',state,[slot])
                elif entry==0x4fd8:add(name,'detonate_bomb',state,[slot])
                else:raise ValueError(f'unknown original actor procedure{entry:x}')
    return cases


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('rom','cartridge','core','cc65-root','output'):ap.add_argument('--'+name,required=True)
    ap.add_argument('--manifest')
    ap.add_argument('--phase',choices=('smoke','components','normal','feedback','all'),default='all')
    ap.add_argument('--common-cases-root')
    ap.add_argument('--actor-cases-root',action='append',default=[])
    ap.add_argument('--case-limit',type=int)
    ap.add_argument('--case-filter',help='Bounded diagnostic subset selected by case-name regular expression')
    ap.add_argument('--spacing',type=int,default=24)
    ap.add_argument('--batch-size',type=int,default=64)
    ap.add_argument('--route-scale',type=int,default=1,help='Explicit host-frame hold multiplier for the established input route')
    ap.add_argument('--route-start',type=int,default=600)
    ap.add_argument('--performance-host-frames',type=int,default=650)
    ap.add_argument('--feedback-post-transition-host-frames',type=int)
    args=ap.parse_args()
    if not 650<=args.performance_host_frames<=20000:ap.error('invalid bounded performance duration')
    if (args.feedback_post_transition_host_frames is not None
            and not 0<=args.feedback_post_transition_host_frames<=5000):
        ap.error('invalid bounded post-transition observation tail')
    rom=Path(args.rom).read_bytes();cartridge=Path(args.cartridge).resolve();core=Path(args.core).resolve()
    manifest_path=Path(args.manifest).resolve() if args.manifest else cartridge.with_name('manifest.json')
    manifest=json.loads(manifest_path.read_text());recovered=lift_full_game(rom)
    # Historical, immutable cartridges remain reviewable when authoring source
    # advances. Replay their retained, hash-bound AST, never substitute new code.
    program=json.loads(cartridge.with_name('program.json').read_text())
    if (sha(cartridge.read_bytes())!=manifest['rom_sha256'] or sha(core.read_bytes())!=NES_SHA
        or sha(rom)!=manifest['source_rom_sha256'] or sha(canonical(program))!=manifest['program_sha256']):
        ap.error('cartridge/source/core/program identity mismatch')
    for name, receipt in manifest['toolchain'].items():
        if sha((Path(args.cc65_root)/'bin'/name).read_bytes())!=receipt['sha256']:
            ap.error('compiler toolchain identity mismatch')
    resources={}
    for name,receipt in manifest.get('runtime_resources',{}).items():
        path=cartridge.parent/receipt['captured_path'];raw=path.read_bytes()
        if len(raw)!=receipt['length'] or sha(raw)!=receipt['sha256']:
            ap.error('captured compiler runtime resource identity mismatch')
        resources[path]=receipt['sha256']
    if not 4<=args.spacing<=100 or not 1<=args.batch_size<=128:ap.error('invalid bounded command schedule')
    out=_private_output(args.output);out.mkdir()
    layout=manifest['state_layout'];size=max(x['offset']+x['length'] for x in layout.values())
    watches=[{'name':f'state{i}','memory_id':0,'offset':i,'length':min(1024,size-i)} for i in range(0,size,1024)]
    watches.append({'name':'debug','memory_id':2,'offset':0x7d0,'length':0x26})
    if 'publication' in manifest:
        pub=manifest['publication'];hv=pub['hv_recording']
        watches.extend([{'name':'publication','memory_id':pub['memory_id'],'offset':pub['base'],
                         'length':pub['head']+2-pub['base']},
                        {'name':'publication_hv','memory_id':hv['memory_id'],'offset':hv['offset'],
                         'length':hv['slots']*hv['stride']}])
    def raw_state(row):return b''.join(bytes.fromhex(row['raw'][f'state{i}']) for i in range(0,size,1024))
    def control(row):return bytes.fromhex(row['raw']['debug'])
    def epoch(row):return int.from_bytes(control(row)[2:4],'little')
    summary={'format':'miniplanets-native6502-game-1','status':'running','cartridge_sha256':manifest['rom_sha256'],
       'program_sha256':manifest['program_sha256'],'source_rom_sha256':manifest['source_rom_sha256'],
       'core_sha256':NES_SHA,'toolchain':manifest['toolchain'],'components':[],
       'runtime_resources':manifest.get('runtime_resources',{}),
       'assistance':'debug mode, scheduled RAM seeds, procedure dispatch and declared HV/sound samples',
       'normal_sessions':[],'first_divergence':None,
       'tree_sha256':sha(json.dumps(program['tree'],sort_keys=True,separators=(',',':')).encode()),
       'matches_current_authoring_tree':program['tree']==recovered['program']['tree'],
       'authoring_units':program.get('evidence',{}).get('authoring_units',{}),
       'verification_sources':{name:sha((ROOT/name).read_bytes()) for name in (
           'scripts/check_miniplanets_nes_game.py','scripts/check_console_udc.py','src/fdisbull/game_il.py')},
       'manifest_sha256':sha(manifest_path.read_bytes()),
       'qualification_ceiling':'Finite actual-core comparisons and measured rates; no whole-game formal equivalence or automatic arbitrary-ROM translation.'}
    machine=GameMachine(program,{0:rom},environment={'hv16':[0],'sound_busy':[0]})
    try:
        if args.phase in ('smoke','components','all'):
            cases=controlled_cases(program,rom,args.common_cases_root,args.actor_cases_root)
            if args.phase=='smoke':cases=cases[:4]
            if args.case_filter:cases=[case for case in cases if re.search(args.case_filter,case['name'])]
            if not cases:raise ValueError('native case selection is empty')
            if args.case_limit:cases=cases[:args.case_limit]
            groups=Counter();max_frames=0
            for start in range(0,len(cases),args.batch_size):
                batch=cases[start:start+args.batch_size];patches=[patch(10,2,0x7d4,b'\1')];expected=[]
                for i,case in enumerate(batch):
                    machine.set_state(case['before']);machine.events=[];machine.environment_cursor={}
                    machine.environment={'hv16':case['hv'] if case['hv'] else [0],'sound_busy':[0]}
                    result=machine.call(case['entry'],*case['args']);wanted=machine.snapshot()
                    hv_count=machine.environment_cursor.get('hv16',0)
                    samples=case['hv'] or [0]*128
                    if len(samples)>128:raise ValueError('native HV recording exceeds128samples')
                    at=40+i*args.spacing
                    command=bytearray(34);command[0]=1;command[1]=1;command[2]=manifest['procedures'][case['entry']]
                    for j,value in enumerate(case['args']):command[5+j*4:9+j*4]=(value&0xffffffff).to_bytes(4,'little')
                    command[22]=len(samples)
                    patches.extend([patch(at,0,0,encode_state(case['before'],layout)),
                        patch(at,0,0x1f00,b''.join(x.to_bytes(2,'big') for x in samples)),patch(at,2,0x7d4,command)])
                    expected.append((wanted,result['result']&0xffffffff,hv_count,list(machine.events)))
                folder=out/f'components-{start//args.batch_size:03d}'
                frames=40+len(batch)*args.spacing
                receipt,trace,seconds=run_host(core,cartridge,folder,frames,watches,patches=patches)
                rows=trace['frames']
                for i,(case,expectation) in enumerate(zip(batch,expected)):
                    at=40+i*args.spacing;before=rows[at-1]
                    if control(before)[5]!=0:raise AssertionError('previous native command did not complete before next patch')
                    completed=None
                    for row in rows[at:at+args.spacing]:
                        c=control(row)
                        if c[29]:raise AssertionError(f'native fault{c[29]} in{case["name"]}')
                        if c[5]==0 and epoch(row)==((epoch(before)+1)&65535):completed=row;break
                    if completed is None:raise AssertionError(f'native command timeout or epoch mismatch:{case["name"]}')
                    wanted,result,hv_count,events=expectation;c=control(completed)
                    actual=decode_state(raw_state(completed),layout)
                    if actual!=wanted:
                        differences={k:{'uil':wanted[k],'native':actual[k]} for k in wanted if wanted[k]!=actual[k]}
                        summary['first_divergence']={'case':case['name'],'procedure':case['entry'],'fields':differences}
                        raise AssertionError(f'native state differs:{case["name"]}:{list(differences)}')
                    observed_result=int.from_bytes(c[32:36],'little')
                    if observed_result!=result:raise AssertionError(f'native return differs:{case["name"]}:{result}/{observed_result}')
                    if c[27]!=hv_count:raise AssertionError(f'HV consumption differs:{case["name"]}:{hv_count}/{c[27]}')
                    if int.from_bytes(c[30:32],'little')!=len(events):raise AssertionError('native event count differs')
                    if events and (c[36],c[37])!=(events[-1]['kind'],events[-1]['id']):raise AssertionError('native final event differs')
                    max_frames=max(max_frames,completed['frame']-at+1);groups[case['entry']]+=1
                summary['components'].append({'batch':start//args.batch_size,'checked':len(batch),
                    'trace_sha256':receipt['ram_trace_sha256'],'patch_trace_sha256':receipt['patch_trace_sha256'],
                    'host_frames':frames,'elapsed_seconds':seconds})
                print('native components',start+len(batch),'/',len(cases),'passed',flush=True)
            summary['component_counts']=dict(groups);summary['component_cases']=sum(groups.values())
            summary['maximum_command_completion_host_frames']=max_frames
        if args.phase in ('normal','all'):
            if not 1<=args.route_scale<=10 or not 500<=args.route_start<=1500:
                raise ValueError('invalid bounded normal route schedule')
            def rate(rows, fps, start_frame, end_frame):
                previous=None;updates=0;torn=0
                for row in rows[start_frame:end_frame+1]:
                    value=epoch(row)
                    if previous is None:previous=value;continue
                    delta=(value-previous)&65535
                    # A host return may land between the two byte stores of a
                    # 16-bit increment. Reject backward/torn samples and retain
                    # the previous counter until a plausible successor arrives.
                    if delta>4:torn+=1;continue
                    updates+=delta;previous=value
                seconds=(end_frame-start_frame)/fps
                return {'host_start':start_frame,'host_end':end_frame,
                    'host_frames_elapsed':end_frame-start_frame,'logic_updates':updates,
                    'logic_updates_per_second':updates/seconds,'host_fps':fps,
                    'rejected_torn_epoch_samples':torn,
                    'timing':'emulated hardware time from core AV info; wall speed recorded separately'}
            values=[value for value in plans()['complete_level'] for _ in range(args.route_scale)]
            frames=args.route_start+len(values)+180
            if frames>10000:raise ValueError('normal route exceeds native host frame budget')
            inputs=[{'start':150,'end':155,'buttons':['START']}]+schedule(values,args.route_start)
            folder=out/'normal-route'
            receipt,trace,seconds=run_host(core,cartridge,folder,frames,watches,inputs=inputs,
                images=sorted({149,450,args.route_start,frames-1}),audio=True)
            rows=trace['frames'];observations=[];first_win=first_key=first_death=None;level_loaded=None
            for row in rows:
                c=control(row)
                # Early power-on RAM precedes the platform's reset/BSS clear.
                # The declared startup window is not a published fault state.
                if row['frame']>=40 and c[29]:raise AssertionError(f'normal-route native fault{c[29]} at host frame{row["frame"]}')
                s=decode_state(raw_state(row),layout)
                if s['mode']==1 and s['stage']==0 and s['stage_name']==0x11:
                    if level_loaded is None:level_loaded=row['frame']
                    if s['keys_left']==0 and first_key is None:first_key=row['frame']
                    if s['player_win'] and first_win is None:first_win=row['frame']
                    if s['player_die'] and first_death is None:first_death=row['frame']
                if row['frame'] in (149,450,args.route_start,frames-1):
                    observations.append({'host_frame':row['frame'],'logic_epoch':epoch(row),
                      **{k:s[k] for k in ('mode','stage','stage_name','player_x','player_y',
                           'player_jump','player_win','player_die','keys_left','score','lives','time_secs')}})
            normal={'name':'input_only_first_level_route','host_frames':frames,'elapsed_wall_seconds':seconds,
                'assistance':'none: ordinary boot and scheduled controller input; no memory patches',
                'route_host_frame_multiplier':args.route_scale,'route_start_host_frame':args.route_start,
                'observed_level_loaded_host_frame':level_loaded,'first_observed_key_host_frame':first_key,
                'first_observed_win_host_frame':first_win,'first_observed_death_host_frame':first_death,
                'route_completed':first_win is not None,'observations':observations,
                'state_scope':'live SRAM sampled after host frames; not a completed-state equality comparison',
                'trace_sha256':receipt['ram_trace_sha256'],'images':receipt['frame_images'],
                'audio':receipt['audio_capture'],'core_receipt_sha256':sha((folder/'receipt.json').read_bytes())}
            if 'publication' in manifest:
                normal['completed_state_shadow'],published=shadow_publications(program,rom,manifest,receipt,trace)
                save(out/'normal-route-publications.json',published)
            if level_loaded is not None:
                normal['logic_rate']=rate(rows,receipt['fps'],min(frames-2,max(level_loaded+30,args.route_start)),frames-1)
            if first_win is None:
                normal['dnf_reason']=(
                    'The level was never observed loaded; the finite Start pulse may be missed when logic advances slower than host frames.'
                    if level_loaded is None else
                    'The fixed host-frame route did not complete the level; its host-frame budget is not a logical-update budget.')
            summary['normal_sessions'].append(normal)
            # Representative performance sessions use original initialized
            # stage state and an explicit Muteki/no-death measurement adapter.
            stages=recovered['scene']['stages']
            def mace_count(stage):
                p=stage['map_offset']+256;total=0
                while rom[p]!=255:
                    if rom[p] in (6,7):total+=1
                    p+=4
                return total
            def orange_count(stage):
                p=stage['map_offset']+256;total=0
                while rom[p]!=255:
                    if rom[p]==19:total+=1
                    p+=4
                return total
            selected=sorted({0,max(stages,key=lambda x:x['object_count'])['index'],
                             max(stages,key=mace_count)['index'],max(stages,key=orange_count)['index']})
            baseline=GameMachine(program,{0:rom},environment={'hv16':[0],'sound_busy':[0]}).snapshot()
            for index in selected:
                machine.set_state(baseline)
                machine.set_state({'stage':index,'time_setting':2,'life_setting':2,'lives':5,
                                   'muteki':255,'timer_ok':255,'belt_ok':255})
                machine.call('begin_stage',0)
                seeded=machine.snapshot()
                patches=[patch(10,2,0x7d4,b'\1'),patch(40,0,0,encode_state(seeded,layout)),
                         patch(40,2,0x7d4,bytes(34))]
                folder=out/f'performance-stage-{index:02d}'
                last=args.performance_host_frames-1
                receipt,trace,seconds=run_host(core,cartridge,folder,args.performance_host_frames,watches,patches=patches,
                                              images=(100,last),audio=True)
                rows=trace['frames']
                faults=[{'host_frame':r['frame'],'fault':control(r)[29]} for r in rows[40:] if control(r)[29]]
                if faults:raise AssertionError(f'performance-stage{index} fault:{faults[0]}')
                observed=decode_state(raw_state(rows[-1]),layout)
                perf={'name':f'steady_stage_{index}','stage_index':index,
                    'original_objects':stages[index]['object_count'],'mace_objects':mace_count(stages[index]),
                    'orange_orb_objects':orange_count(stages[index]),
                    'assistance':'Original level state seeded from UIL; Muteki=255 keeps the no-input benchmark alive; ordinary native loop/audio/rendering enabled.',
                    'elapsed_wall_seconds':seconds,'logic_rate':rate(rows,receipt['fps'],100,last),
                    'final_observed_stage':observed['stage'],'trace_sha256':receipt['ram_trace_sha256'],
                    'images':receipt['frame_images'],'audio':receipt['audio_capture'],
                    'core_receipt_sha256':sha((folder/'receipt.json').read_bytes())}
                if 'publication' in manifest:
                    perf['completed_state_shadow'],published=shadow_publications(
                        program,rom,manifest,receipt,trace,seeded_state=seeded,seed_frame=40)
                    save(out/f'performance-stage-{index:02d}-publications.json',published)
                summary['normal_sessions'].append(perf)
                print('native steady stage',index,round(perf['logic_rate']['logic_updates_per_second'],3),'logic Hz',flush=True)
        if args.phase in ('feedback','normal','all') and 'publication' in manifest:
            folder=out/'feedback-route'
            policy={'format':'fdisbull-publication-controller-1','kind':'miniplanets-stage1-1',
                'rom_sha256':manifest['rom_sha256'],'publication':manifest['publication'],
                'max_logic_steps':2000,'post_goal_host_frames':1000}
            if args.feedback_post_transition_host_frames is not None:
                policy['post_transition_host_frames']=args.feedback_post_transition_host_frames
            receipt,trace,seconds=run_host(core,cartridge,folder,10000,watches,
                feedback=policy,images=(149,999),audio=True)
            result=receipt['feedback_controller']['result']
            if receipt['patches'] or receipt['memory_injection_mode']!='no memory patches':
                raise AssertionError('feedback route mutated RAM')
            checked,published=shadow_publications(program,rom,manifest,receipt,trace)
            if result['completed'] and result['next_stage_transition'] is None:
                raise AssertionError('feedback reached the goal but did not finish the score tally/next-stage transition within its bound')
            save(out/'feedback-route-publications.json',published)
            summary['normal_sessions'].append({'name':'read_only_feedback_first_level_route',
                'result':result,'route_completed':result['completed'],'host_frames':receipt['frames'],
                'elapsed_wall_seconds':seconds,'completed_state_shadow':checked,
                'controller_policy_sha256':receipt['feedback_controller']['policy_sha256'],
                'controller_observations_sha256':receipt['feedback_controller']['observations_sha256'],
                'controller_callback_masks_sha256':receipt['feedback_controller']['callback_masks_sha256'],
                'assistance':result['assistance'],'trace_sha256':receipt['ram_trace_sha256'],
                'images':receipt['frame_images'],'audio':receipt['audio_capture'],
                'final_image_sha256':receipt['frame_png_sha256'],
                'core_receipt_sha256':sha((folder/'receipt.json').read_bytes())})
            print('native feedback route',result,flush=True)
        summary['inputs_unchanged']=(sha(cartridge.read_bytes())==manifest['rom_sha256'] and sha(core.read_bytes())==NES_SHA
            and all(sha(path.read_bytes())==digest for path,digest in resources.items()))
        summary['verification_sources_unchanged']=summary['verification_sources']=={
            name:sha((ROOT/name).read_bytes()) for name in summary['verification_sources']}
        summary['status']='passed' if summary['inputs_unchanged'] else 'input-changed'
        if not summary['verification_sources_unchanged']:summary['status']='verification-source-changed'
        if summary['status']=='passed' and any(s.get('route_completed') is False for s in summary['normal_sessions']):
            summary['status']='completed-with-route-dnf'
        summary['gates']={
            'complete_state_components':'passed' if summary.get('component_cases') else 'not-run',
            'normal_completed_state_shadow':'passed' if any(s.get('completed_state_shadow') for s in summary['normal_sessions']) else 'not-run',
            'feedback_goal_and_next_stage':'passed' if any(s.get('result',{}).get('next_stage_transition') for s in summary['normal_sessions']) else 'not-run',
            'fixed_host_frame_route':'dnf' if any(s.get('route_completed') is False and s['name']=='input_only_first_level_route' for s in summary['normal_sessions']) else 'passed-or-not-run'}
    except Exception as exc:
        summary['status']='failed';summary['failure']=str(exc);raise
    finally:save(out/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='components'},indent=2))


if __name__=='__main__':main()
