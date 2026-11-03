"""Reproducible instruction-space search and bounded public-ROM coverage pilot.

Sandsifter-inspired: enumerate, differential decode, observe execution outcomes,
classify/minimize discrepancies and retain immutable evidence. CHIP-8 has no
variable-length x86 page-fault oracle; its 16-bit words are enumerated directly.
"""
from __future__ import annotations
from collections import Counter, defaultdict, deque
import argparse
import hashlib
import itertools
import json
import os
import random
from pathlib import Path
from .decoder import decode_table, decode_branches, validate_rules, PROFILES, CLASSIC
from .vm import Machine, Quirks, Trap
from .registry import build_index
from .gaps import run_gap_probes

PROJECT=Path(__file__).resolve().parents[1]
CORPUS_DIR=Path(os.getenv('CHIP8_CORPUS_DIR', str(PROJECT/'corpus')))
CORE_FAMILIES=tuple(sorted({family for _,_,family in CLASSIC if family != 'SYS'}))

def sha(data:bytes):return hashlib.sha256(data).hexdigest()

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode('utf-8')

def scan_space(profiles=PROFILES):
    validate_rules()
    summary={}
    for profile in profiles:
        classes=Counter(); family_counts=Counter(); divergences=[]
        for word in range(65536):
            a,b=decode_table(word,profile),decode_branches(word,profile)
            classes[a.tier]+=1;family_counts[a.family]+=1
            if a!=b: divergences.append({'word':f'{word:04X}','table':a.family,'branch':b.family})
        summary[profile]={'words':65536,'tier_counts':dict(sorted(classes.items())),
                          'family_count':len(family_counts),
                          'families':dict(sorted(family_counts.items())),
                          'decoder_disagreements':len(divergences),
                          'disagreement_examples':divergences[:32]}
    return summary

def execute_single_word_scan():
    counts=Counter(); by_family=Counter(); issues=[]
    for word in range(65536):
        d=decode_table(word)
        if d.tier!='classic':
            counts['invalid_word' if d.tier=='invalid' else 'legacy_opaque']+=1
            continue
        m=Machine(seed=17)
        m.memory[0x200:0x202]=word.to_bytes(2,'big')
        m.memory[0x300:0x320]=bytes(range(32))
        m.v=[z*11%256 for z in range(16)]
        m.stack=[0x204]
        m.i=0x300
        try:
            result=m.step()
            counts[result]+=1
            by_family[d.family]+=1
        except Trap as exc:
            counts['trapped_'+exc.code]+=1
            if len(issues)<30:issues.append({'word':f'{word:04X}','family':d.family,'trap':exc.code})
    return {'words':65536,'status_counts':dict(sorted(counts.items())),
            'executed_families':dict(sorted(by_family.items())),
            'unexpected_runtime_traps':issues}

def check_variant_probes():
    probes=[]
    def go(word,v={},i=0x300,mem=b'',**opts):
        m=Machine(quirks=Quirks(**opts));m.memory[0x200:0x202]=word.to_bytes(2,'big')
        m.v[:]=[0]*16
        for key,value in v.items():m.v[key]=value
        m.i=i
        if mem:m.memory[i:i+len(mem)]=mem
        m.step()
        return {'pc':m.pc,'i':m.i,'v1':m.v[1],'vf':m.v[15],
                'pixels':sum(m.frame)}
    variants=[
      ('shift_source',0x8126,{'v':{1:3,2:128}}, {'shift_vx':True}),
      ('load_store_index',0xF155,{'v':{0:4,1:5}}, {'inc_i_on_load_store':False}),
      ('logic_vf_reset',0x8121,{'v':{1:7,2:0,15:1}}, {'reset_vf_logic':False}),
      ('jump_base',0xB123,{'v':{0:1,1:2}}, {'jump_vx':True}),
      ('sprite_clipping',0xD121,{'v':{1:62,2:31},'mem':b'\xff'}, {'clip_sprites':False})]
    for name,word,init,alt in variants:
        baseline=go(word,**init); changed=go(word,**init,**alt)
        probes.append({'name':name,'word':f'{word:04X}', 'default':baseline,
                       'alternate':changed,'diverges':baseline!=changed,
                       'status':'intentional_profile_difference' if baseline!=changed else 'needs_investigation'})
    return probes

def static_candidate_reachability(rom:bytes,profile:str):
    """Overapproximate reachable addresses, never proof of code or hidden state."""
    lo,hi=0x200,0x200+len(rom)
    visited=set(); pending=[lo]; ambiguous=[]
    while pending and len(visited)<4096:
        pc=pending.pop()
        if pc in visited:continue
        if pc<lo or pc+1>=hi or pc%2:continue
        visited.add(pc)
        offset=pc-lo
        d=decode_table((rom[offset]<<8)|rom[offset+1],profile)
        nxt=pc+d.size
        if d.family=='LONG_I' and pc+3>=hi:
            ambiguous.append({'at':pc,'reason':'truncated_long_I'})
            continue
        if d.tier in ('invalid','legacy'):
            ambiguous.append({'at':pc,'reason':d.family.lower()})
            continue
        if d.family=='RET' or d.family=='EXIT':continue
        if d.family=='JP':pending.append(d.nnn)
        elif d.family=='CALL':pending.extend([d.nnn,nxt])
        elif d.family=='JP_V0':
            ambiguous.append({'at':pc,'reason':'computed_jump_target'}); continue
        elif d.family.startswith(('SE_','SNE_')) or d.family in ('SKP','SKNP'):
            pending.extend([nxt,nxt+2])
        else:pending.append(nxt)
    return {'candidate_addresses':len(visited),'stops':ambiguous[:20],
            'note':'syntactic CFG candidate, not proof; excludes host/memory-created code and may traverse data'}

def scan_rom(rom:bytes,profile:str):
    # A naïve raw-word scan provides an UPPER bound, not decoded program coverage.
    words=[int.from_bytes(rom[i:i+2],'big') for i in range(0,len(rom)-1,2)]
    counts=Counter(decode_table(w,profile).family for w in words)
    tiers=Counter(decode_table(w,profile).tier for w in words)
    return {'size':len(rom),'raw_words':len(words),'odd_tail_bytes':len(rom)%2,
            'word_scan_family_counts':dict(sorted(counts.items())),
            'word_scan_tier_counts':dict(sorted(tiers.items())),
            'static_reachability':static_candidate_reachability(rom,profile),
            'warning':'Linear word scan includes sprites/constants/data; do not call these executed instructions.'}

SEMANTIC_ROLES = {
    'CLS':'display.clear', 'RET':'control.return', 'JP':'control.jump', 'CALL':'control.call',
    'SE_VX_KK':'control.skip_equal', 'SNE_VX_KK':'control.skip_not_equal',
    'SE_VX_VY':'control.skip_equal', 'SNE_VX_VY':'control.skip_not_equal',
    'LD_VX_KK':'state.assign', 'LD_VX_VY':'state.copy',
    'ADD_VX_KK':'arith.add_wrap8', 'ADD_VX_VY':'arith.add_carry8',
    'OR':'logic.or8', 'AND':'logic.and8', 'XOR':'logic.xor8',
    'SUB':'arith.subtract_borrow8', 'SUBN':'arith.reverse_subtract_borrow8',
    'SHR':'arith.shift_right', 'SHL':'arith.shift_left',
    'LD_I':'memory.address_assign', 'JP_V0':'control.computed_jump',
    'RND':'random.mask', 'DRW':'display.xor_sprite',
    'SKP':'input.key_skip', 'SKNP':'input.key_skip', 'WAIT_KEY':'input.key_wait',
    'LD_VX_DT':'clock.delay_read', 'LD_DT_VX':'clock.delay_write',
    'LD_ST_VX':'audio.timer_write', 'ADD_I_VX':'memory.address_add',
    'FONT':'memory.glyph_address', 'BCD':'memory.bcd_write',
    'SAVE':'memory.register_save', 'LOAD':'memory.register_load',
}

def instruction_candidate(pc,word):
    d=decode_table(word,'chip8')
    return {'format':'fdisbull-chip8-udl-uil-candidate-1',
            'source_address':f'{pc:04X}', 'raw_word':f'{word:04X}',
            'udl':{'family':d.family,'operands':{'x':d.x,'y':d.y,'kk':d.kk,'nnn':d.nnn},
                   'instruction_bytes':word.to_bytes(2,'big').hex()},
            'uil_intent_candidate':SEMANTIC_ROLES.get(d.family,'unresolved'),
            'behavioral_qualification':'not_proved_against_original_runtime',
            'note':'typed operand/behavior candidate only; not a validated common-UIL program'}

def run_rom(rom:bytes,steps=1600,seed=42,quirks=None):
    m=Machine(seed=seed, quirks=quirks or Quirks());m.load_rom(rom)
    count=Counter(); sequences=[]; pcs=set(); blocks=Counter(); edges=Counter(); last=None; status='budget_exhausted'; details=None
    # Explicit fixed frame schedule is a pilot policy, not historical VIP timing.
    for index in range(steps):
        if index and index%9==0:m.tick_60hz()
        pc=m.pc
        word=(m.memory[pc]<<8)|m.memory[pc+1] if 0<=pc<4095 else None
        try:
            outcome=m.step()
        except Trap as e:
            status='trapped';details={'kind':e.code,'pc':f'{e.address:04X}',
                                        'word':None if e.word is None else f'{e.word:04X}'}
            break
        if outcome=='waiting':
            status='key_wait';details={'pc':f'{pc:04X}', 'input_policy':'no keys pressed'}
            break
        pcs.add(pc);count[m.last_family]+=1;sequences.append(m.last_family)
        blocks[(pc,word)]+=1
        if last is not None:edges[(last,pc)]+=1
        last=pc
    ngrams={}
    for n in (2,3):
        ngrams[str(n)]={" ".join(z) for z in zip(*(sequences[i:] for i in range(n)))}
    return {'status':status,'detail':details,'steps':m.steps,'distinct_pcs':len(pcs),
            'executed_families':dict(sorted(count.items())),
            'executed_family_set':sorted(count),
            'n2_set':sorted(ngrams['2']),'n3_set':sorted(ngrams['3']),
            'block_candidates':[dict(instruction_candidate(pc,word),observed_count=count)
                for (pc,word),count in sorted(blocks.items())[:128]],
            'observed_edges':[{'from':f'{src:04X}','to':f'{dst:04X}','count':count}
                for (src,dst),count in sorted(edges.items())[:128]],
            'distinct_pc_word_pairs':len(blocks),'distinct_edges':len(edges),
            'trace_coverage_truncated':len(blocks)>128 or len(edges)>128,
            'final_pc':f'{m.pc:04X}','state_sha256':m.state_digest(),
            'input_policy':'all released; no key events',
            'clock_policy':'advance one 60Hz timer tick per 9 instruction attempts',
            'random_policy':'Python RNG seed 42, recorded by trial',
            'claim_ceiling':'bounded authored interpreter observation; not original runtime equivalence'}

def corpus_metrics(steps=1600):
    manifest=json.loads((PROJECT/'corpus/manifest.json').read_text())
    results=[];families=set();bigrams=set(); trigrams=set(); curve=[]
    for program in manifest['programs']:
        raw=(CORPUS_DIR/(program['key']+'.ch8')).read_bytes()
        if sha(raw)!=program['sha256'] or len(raw)!=program['size']:
            raise ValueError('corpus file mismatch '+program['key'])
        entry={**program,'word_scan':scan_rom(raw,program['platform'])}
        if program['platform']=='chip8':
            dyn=run_rom(raw,steps)
            oldfamilies=set(families)
            families|=set(dyn['executed_family_set']); bigrams|=set(dyn['n2_set']);trigrams|=set(dyn['n3_set'])
            entry['dynamic']={k:v for k,v in dyn.items() if k not in ('n2_set','n3_set')}
            curve.append({'program':program['key'],'programs':len(curve)+1,
                          'unique_families':len(families),'new_families':len(families-oldfamilies),
                          'unique_adjacent_pairs':len(bigrams),'unique_trigrams':len(trigrams)})
        else:
            entry['dynamic']={'status':'not_executed','reason':'SCHIP/XO profiles require separate qualified interpreter and quirks'}
        results.append(entry)
    return {'rom_count':len(results),'executed_classic_count':len(curve),
            'executed_family_count':len(families),'classic_family_denominator':len(CORE_FAMILIES),
            'executed_coverage_pct':round(len(families)/len(CORE_FAMILIES)*100,2),
            'executed_families':sorted(families),
            'unseen_classic_families':sorted(set(CORE_FAMILIES)-families),
            'unique_adjacent_pairs':len(bigrams),'unique_trigrams':len(trigrams),
            'curve':curve,'roms':results}

def ddmin(sequence:list[int], failing):
    """Reduce a multiword reproducer; preserve an externally supplied anomaly predicate."""
    items=list(sequence); stride=2
    while len(items)>=2:
        chunk=max(1,(len(items)+stride-1)//stride); reduced=False
        for i in range(0,len(items),chunk):
            c=items[:i]+items[i+chunk:]
            if c and failing(c):items=c;stride=max(2,stride-1);reduced=True;break
        if not reduced:
            if stride>=len(items):break
            stride=min(len(items),stride*2)
    return items

def mutation_sanity():
    # Intentionally faulty decoder accepting 5XY1 as 5XY0. This checks the fuzzer,
    # not any real emulator bug.
    mismatches=[]
    for w in range(65536):
        good=decode_table(w).family
        mutant='SE_VX_VY' if (w&0xF00F)==0x5001 else good
        if mutant!=good:mismatches.append(w)
    seed=[0x6001,0x5011,0x6102,0x1200]
    reduced=ddmin(seed,lambda seq:any(w in mismatches for w in seq))
    return {'injected_bug':'accept 5XY1 as SE_VX_VY','anomalous_words':len(mismatches),
            'minimized_words':[f'{w:04X}' for w in reduced], 'examples':[f'{w:04X}' for w in mismatches[:8]],
            'finding_type':'synthetic_fuzzer_positive_control_not_a_real_decoder_bug'}


def fuzz_short_programs(rounds=3000, seed=20261102, straightline=False):
    """Sandsifter-style synthetic sequences; detects nondeterminism, not semantic truth."""
    rng=random.Random(seed)
    control={'JP','CALL','RET','JP_V0','SE_VX_KK','SNE_VX_KK','SE_VX_VY',
             'SNE_VX_VY','SKP','SKNP','WAIT_KEY'}
    pool=[word for word in range(65536) if decode_table(word).tier=='classic'
          and (not straightline or decode_table(word).family not in control)]
    status=Counter(); families=set(); failures=[]; stop_examples=defaultdict(list)
    for case in range(rounds):
        length=rng.randint(2,7)
        words=[rng.choice(pool) for _ in range(length)]
        data=b''.join(w.to_bytes(2,'big') for w in words)
        state_seed=rng.getrandbits(32)
        values=[rng.randrange(256) for _ in range(16)]
        initial_i=rng.randrange(0x2ff,0x1000) # some boundary traps intentional
        keys={rng.randrange(16)} if rng.randrange(3)==0 else set()
        def execute():
            m=Machine(seed=state_seed)
            m.load_rom(data)
            m.i=initial_i
            m.v[:]=values
            m.keys=set(keys)
            outcome='bounded_complete'
            for _ in range(length):
                try:
                    observed=m.step()
                    families.add(m.last_family)
                    if observed=='waiting':
                        outcome='key_wait';break
                except Trap as e:
                    outcome='trap_'+e.code;break
            return (outcome,m.state_digest())
        a,b=execute(),execute()
        status[a[0]]+=1
        if a[0]!='bounded_complete' and len(stop_examples[a[0]])<3:
            stop_examples[a[0]].append({'case':case,'words':[f'{w:04X}' for w in words],
                                        'i':f'{initial_i:04X}', 'keys':sorted(keys),
                                        'kind':'bounded_precondition_or_control_flow_stop'})
        if a!=b:
            failures.append({'case':case,'words':[f'{w:04X}' for w in words],
                            'a':a,'b':b})
            if len(failures)>=10:break
    return {'rounds_requested':rounds,'rounds_observed':sum(status.values()),
            'random_seed':seed,'word_pool':len(pool),'straightline':straightline,
            'stop_counts':dict(sorted(status.items())),
            'families_encountered':sorted(families),
            'repeatability_disagreements':len(failures), 'examples':failures,
            'stop_examples':dict(sorted(stop_examples.items())),
            'claim_ceiling':'same authored machine twice with same recorded inputs; not independent interpreter correctness'}

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',type=Path,
                    default=Path(os.getenv('XDG_STATE_HOME',str(Path.home()/'.local/state')))
                        /'fdisbull/chip8_pilot/pilot.json',
                    help='Private local output outside Git; a fresh directory per experiment run')
    ap.add_argument('--steps',type=int,default=1600)
    args=ap.parse_args(argv)
    if args.steps<=0 or args.steps>100000:ap.error('steps must be 1..100000')
    result={'format':'fdisbull-chip8-instruction-pilot-1',
            'method':'bounded Sandsifter-inspired enumeration, two decoder oracles, synthetic instruction execution, dialect quirk probes, minimization and CC0 ROM corpus',
            'scope':'structural decode + authored VM observation, not independent emulator qualification or whole-program UIL',
            'instruction_scan':scan_space(),
            'single_word_execution':execute_single_word_scan(),
            'intentional_quirk_divergences':check_variant_probes(),
            'mutation_positive_control':mutation_sanity(),
            'short_sequence_fuzz':fuzz_short_programs(),
            'straightline_sequence_fuzz':fuzz_short_programs(straightline=True),
            'corpus':corpus_metrics(args.steps)}
    result['gap_probe_results']=run_gap_probes(result['corpus']['unseen_classic_families'])
    result['source_commit']='761e3ffc63f43e6a849e80714122feff2afca208'
    result['input_sha256']={f'corpus/{p.name}':sha(p.read_bytes())
                            for p in sorted(CORPUS_DIR.glob('*.ch8')) if p.is_file()}
    result['input_sha256']['corpus/manifest.json']=sha((PROJECT/'corpus/manifest.json').read_bytes())
    result['program_sha256']={str(p.relative_to(PROJECT)):sha(p.read_bytes()) for p in sorted((PROJECT/'chip8lab').glob('*.py'))}
    result['receipt_sha256']=sha(canonical(result))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    result['registry_summary']=build_index(result, args.out.parent/'observations.sqlite')
    (args.out.parent/'registry_summary.json').write_text(json.dumps(result['registry_summary'],indent=2,sort_keys=True)+'\n')
    result['result_path']=str(args.out)
    return result

if __name__=='__main__':
    r=main()
    print(json.dumps({'receipt':str(Path(r.get('result_path','results/pilot.json'))),'receipt_sha256':r['receipt_sha256'],
            'mismatches':{k:v['decoder_disagreements'] for k,v in r['instruction_scan'].items()},
            'corpus':{k:v for k,v in r['corpus'].items() if k not in ('roms','curve')},
            'quirks':r['intentional_quirk_divergences']},indent=2))