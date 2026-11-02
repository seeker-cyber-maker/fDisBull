#!/usr/bin/env python3
"""Build and qualify the source-bound playable first Miniplanets level on NES."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.udl_miniplanets import lift_level, ROM_SHA256
from fdisbull.console_udc import write_console_rom
from fdisbull.interaction_il import execute_il

NES_SHA = '5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60'
GEN_SHA = '27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
BITS = {'RIGHT':1,'LEFT':2,'UP':4,'DOWN':8,'A':16,'B':32,'START':64,'SELECT':128}
FILES = ('src/fdisbull/interaction_il.py','src/fdisbull/console_udc.py',
 'src/fdisbull/udc_nes.py','src/fdisbull/udc_nes_level.py','src/fdisbull/udl_miniplanets.py',
 'scripts/check_console_udc.py','scripts/probe_genesis_function.py',
 'scripts/check_miniplanets_native.py','scripts/verify_miniplanets_level.py')


def sha(data):return hashlib.sha256(data).hexdigest()
def hashes():return {name:sha((ROOT/name).read_bytes()) for name in FILES}
def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n')

def masks(segments):
    result=[]
    for direction,count,jump in segments:
        value=BITS.get(direction,0)
        result.extend([value | (16 if jump and i==0 else 0) for i in range(count)])
    return result


def plans():
    win=[('UP',96,False),('RIGHT',60,False),('RIGHT',48,True),('RIGHT',52,False),
      ('UP',64,False),('LEFT',60,False),('LEFT',48,True),('LEFT',52,False),
      ('RIGHT',60,False),('RIGHT',48,True),('RIGHT',52,False),('DOWN',144,False)]
    loss=[('UP',96,False),('RIGHT',70,False)]
    return {'complete_level':masks(win),'wall_right':masks([('RIGHT',64,False)]),
      'wall_down':masks([('DOWN',64,False)]),'water_death':masks(loss),
      'jump_wall':masks([('',16,False),('RIGHT',64,True)]),
      'wrap_roundtrip':masks([('UP',16,False),('DOWN',16,False),('LEFT',16,False),('RIGHT',16,False)]),
      'restart_after_death':masks(loss)+[64,64]+[0]*16+[1]*16}


def schedule(values,offset):
    result=[];start=0
    for end in range(1,len(values)+1):
        if end==len(values) or values[end]!=values[start]:
            if values[start]:result.append({'start':start+offset,'end':end+offset,
                'buttons':[k for k,b in BITS.items() if values[start]&b]})
            start=end
    return result


def host(core,rom,system,frames,inputs,watches,out,expected_rom_sha):
    if sha(Path(rom).read_bytes())!=expected_rom_sha:
        raise AssertionError('ROM changed before emulator session')
    save(out.parent/(out.name+'-inputs.json'),inputs)
    save(out.parent/(out.name+'-watch.json'),watches)
    c=subprocess.run([sys.executable,str(ROOT/'scripts/check_console_udc.py'),
      '--core',str(core),'--rom',str(rom),'--system',system,'--frames',str(frames),
      '--inputs',str(out.parent/(out.name+'-inputs.json')),
      '--watch',str(out.parent/(out.name+'-watch.json')),'--output',str(out)],
      capture_output=True,text=True,timeout=90)
    if c.returncode:raise RuntimeError(c.stderr[-2000:])
    receipt=json.loads((out/'receipt.json').read_text())
    if receipt['core_sha256']!=(NES_SHA if system=='nes' else GEN_SHA) or receipt['rom_sha256']!=expected_rom_sha:
        raise AssertionError('emulator receipt identity differs from qualified inputs')
    return receipt,json.loads((out/'ram_trace.json').read_text())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('rom','nes-core','genesis-core','output'):ap.add_argument('--'+name,required=True)
    args=ap.parse_args();rom=Path(args.rom).read_bytes()
    if sha(rom)!=ROM_SHA256 or sha(Path(args.nes_core).read_bytes())!=NES_SHA or sha(Path(args.genesis_core).read_bytes())!=GEN_SHA:
        ap.error('requires the qualified original ROM and core hashes')
    root=Path(args.output).resolve()
    if root.exists() or not root.parent.is_dir() or any((p/'.git').exists() for p in (root,*root.parents)):
        ap.error('output must be a new private directory outside Git')
    frozen=hashes();root.mkdir()
    summary={'format':'fdisbull-miniplanets-playable-level-1','status':'running',
      'source_sha256':ROM_SHA256,'source_hashes':frozen,'sessions':[],
      'scope':'Stage 1-1 logical gameplay with authored NES presentation, terminal freeze and restart',
      'excluded':['score','lives','time limit','audio','original globe rendering','other levels']}
    def checkpoint():save(root/'summary.json',summary)
    checkpoint()
    try:
        recovered=lift_level(rom);program=recovered['program'];scene=recovered['scene']
        package=root/'cartridge'
        manifest=write_console_rom(program,target='nes',scene=scene,output=package)
        save(root/'recovery.json',recovered)
        summary['provenance']=recovered['provenance'];summary['rom_sha256']=manifest['rom_sha256']
        summary['compiler_profile']=manifest['profile'];layout=manifest['variables']
        first=min(v['address'] for v in layout.values())&~1
        end=(max(v['address']+v['width']//8 for v in layout.values())+1)&~1
        watches=[{'name':'vars','offset':first,'length':end-first},
          {'name':'control','offset':manifest['symbols']['runtime_frame_counter'],'length':4}]
        transitions=[];all_plans=plans()
        for name,values in all_plans.items():
            folder=root/name;folder.mkdir()
            receipt,trace=host(args.nes_core,package/'program.nes','nes',len(values)+24,
              schedule(values,3),watches,folder/'run',manifest['rom_sha256'])
            state={k:v['initial'] for k,v in program['variables'].items()}
            count=checked=0;first_key=first_win=first_death=None
            for frame in trace['frames']:
                raw=bytes.fromhex(frame['raw']['control'])
                if int.from_bytes(raw[2:4],'little')!=0xa55a:continue
                tick=int.from_bytes(raw[:2],'little')
                if tick==count:
                    if count:raise AssertionError(f'{name}: frame did not complete a tick')
                    continue
                if tick!=count+1:raise AssertionError(f'{name}: skipped tick')
                # Qualified FCEUmm publication is one host frame after polling.
                previous_mask=trace['frames'][frame['frame']-1]['input_mask'] if frame['frame'] else 0
                expected_buttons=sum(bit for key,bit in BITS.items() if previous_mask&(1<<receipt['input_map'][key]))
                before=copy.deepcopy(state);before['$buttons']=expected_buttons
                model=execute_il(program,before)
                if not model['complete']:raise AssertionError(model)
                data=bytes.fromhex(frame['raw']['vars'])
                actual={k:int.from_bytes(data[v['address']-first:v['address']-first+v['width']//8],'little') for k,v in layout.items()}
                if actual!=model['state']:
                    raise AssertionError(f'{name}: NES/UIL divergence tick{tick}: '+str({k:(model['state'][k],actual[k]) for k in actual if actual[k]!=model['state'][k]}))
                transitions.append({'name':f'{name}-{tick}','before':before,'after':actual})
                state=actual;count=tick;checked+=1
                if state['$keys']==0 and first_key is None:first_key=tick
                if state['$win'] and first_win is None:first_win=tick
                if state['$dead'] and first_death is None:first_death=tick
            if checked< len(values):raise AssertionError('insufficient NES replay coverage')
            summary['sessions'].append({'name':name,'checked_ticks':checked,'first_key_tick':first_key,
              'first_win_tick':first_win,'first_death_tick':first_death,
              'final_state':state,'trace_sha256':receipt['ram_trace_sha256'],
              'frame_sha256':receipt['frame_rgb_sha256'],'input_publication_delay_frames':1})
            if name=='complete_level' and (first_key!=472 or first_win!=784 or state['$dead']):raise AssertionError('level not completed')
            if name=='wall_right' and state['$x']!=31:raise AssertionError('wall did not block right')
            if name=='wall_down' and state['$y']!=31:raise AssertionError('wall did not block down')
            if name=='water_death' and not state['$dead']:raise AssertionError('water did not hurt')
            if name=='jump_wall' and state['$x']!=31:raise AssertionError('jump passed a wall')
            if name=='wrap_roundtrip' and (state['$x'],state['$y'])!=(0,0):raise AssertionError('wrap failed')
            if name=='restart_after_death' and (state['$x'],state['$y'],state['$dead'])!=(16,0,0):raise AssertionError('restart failed')
            checkpoint()
        # Cover all D-pad combinations and every distinct diagonal phase class
        # at floor, wall, water, key and goal boundaries, independently of replay.
        for x,y in [(16,16),(31,0),(0,31),(63,160),(0,96),(160,240)]:
            for phase in (0,1,3):
                for pad in range(16):
                    before={k:v['initial'] for k,v in program['variables'].items()}
                    before.update({'$x':x,'$y':y,'$jump':0,'$phase':phase,'$buttons':pad})
                    result=execute_il(program,before);assert result['complete']
                    transitions.append({'name':f'boundary-{x}-{y}-{phase}-{pad}','before':before,'after':result['state']})
        cases_path=root/'native-cases.json';save(cases_path,transitions)
        proc=subprocess.run([sys.executable,str(ROOT/'scripts/check_miniplanets_native.py'),
          '--rom',args.rom,'--core',args.genesis_core,'--cases',str(cases_path),
          '--output',str(root/'original-cpu')],capture_output=True,text=True,timeout=300)
        if proc.returncode:raise RuntimeError('original CPU comparison failed: '+proc.stderr[-3000:])
        native=json.loads((root/'original-cpu/summary.json').read_text())
        if native['status']!='passed':raise AssertionError(native)
        summary['original_cpu']=native
        # Natural, unmodified game play: load normally, then use a known
        # reproducible title/intro schedule. No original RAM/PC is changed.
        natural_watches=[{'name':'map','offset':0x786,'length':256},
          {'name':'player','offset':0x88c,'length':8},{'name':'status','offset':0x782,'length':4},
          {'name':'key','offset':0x894,'length':4},{'name':'clock','offset':0x758,'length':4}]
        natural_inputs=[{'start':180,'end':185,'buttons':['START']}]+schedule(all_plans['complete_level'],650)
        receipt,trace=host(args.genesis_core,args.rom,'genesis',1434,natural_inputs,natural_watches,root/'original-gameplay',ROM_SHA256)
        def arch(h):
            b=bytes.fromhex(h);return bytes(b[i^1] for i in range(len(b)))
        baseline=trace['frames'][649]['raw'];initial=arch(baseline['player'])
        state={k:v['initial'] for k,v in program['variables'].items()}
        field_names={0:'$x',1:'$y',2:'$angle',3:'$action',4:'$jump',6:'$win',7:'$dead'}
        state.update({name:initial[index] for index,name in field_names.items()})
        state.update({'$keys':arch(baseline['status'])[1],'$key_active':arch(baseline['key'])[0],
                      '$phase':int.from_bytes(arch(baseline['clock'])[:2],'big')&255})
        baseline_projection={k:state[k] for k in list(field_names.values())+['$keys','$key_active','$phase']}
        if sha(arch(baseline['map']))!=recovered['provenance']['regions']['map']['sha256']:
            raise AssertionError('natural original did not load the expected level')
        aligned_initial=copy.deepcopy(state)
        natural_states=[]
        for tick,buttons in enumerate(all_plans['complete_level']):
            state['$buttons']=buttons;model=execute_il(program,state);assert model['complete'];state=model['state']
            f=trace['frames'][650+tick]['raw'];player=arch(f['player'])
            observed={name:player[index] for index,name in field_names.items()}
            observed.update({'$keys':arch(f['status'])[1],'$key_active':arch(f['key'])[0],
              '$phase':int.from_bytes(arch(f['clock'])[:2],'big')&255,'$subpixel':int.from_bytes(arch(f['clock'])[2:],'big')})
            if any(state[k]!=v for k,v in observed.items()):
                raise AssertionError(f'natural Genesis/UIL divergence tick{tick+1}: '+str({k:(state[k],v) for k,v in observed.items() if state[k]!=v}))
            natural_states.append(observed)
        if not state['$win'] or state['$keys']:raise AssertionError('original game did not complete')
        summary['natural_gameplay']={'checked_transitions':784,'first_input_host_frame':650,
          'baseline_projection':baseline_projection,'baseline':'observed loaded-game state; no original memory/PC mutation',
          'trace_sha256':receipt['ram_trace_sha256'],'frame_sha256':receipt['frame_rgb_sha256'],
          'final_projection':{k:state[k] for k in observed}}
        # A second NES cartridge starts from that same observed logical state.
        # Its first 784 ticks can therefore be compared directly with the
        # untouched game's recorded projection, including phase and subpixel.
        aligned_program=copy.deepcopy(program)
        for key,value in aligned_initial.items():
            aligned_program['variables'][key]['initial']=value
        aligned_manifest=write_console_rom(aligned_program,target='nes',scene=scene,output=root/'aligned-cartridge')
        aligned_receipt,aligned_trace=host(args.nes_core,root/'aligned-cartridge/program.nes','nes',808,
          schedule(all_plans['complete_level'],3),watches,root/'aligned-nes',aligned_manifest['rom_sha256'])
        checked=0
        for frame in aligned_trace['frames']:
            control=bytes.fromhex(frame['raw']['control'])
            if int.from_bytes(control[2:4],'little')!=0xa55a:continue
            tick=int.from_bytes(control[:2],'little')
            if not 1<=tick<=len(natural_states):continue
            if tick!=checked+1:raise AssertionError('aligned NES counter gap')
            data=bytes.fromhex(frame['raw']['vars'])
            projection={key:data[layout[key]['address']-first] for key in natural_states[tick-1]}
            if projection!=natural_states[tick-1]:raise AssertionError(f'aligned Genesis/NES divergence tick{tick}')
            checked+=1
        if checked!=784:raise AssertionError('incomplete direct Genesis/NES comparison')
        summary['aligned_original_to_nes']={'checked_transitions':checked,'initial_projection':baseline_projection,
          'rom_sha256':aligned_manifest['rom_sha256'],'nes_trace_sha256':aligned_receipt['ram_trace_sha256'],
          'nes_frame_sha256':aligned_receipt['frame_rgb_sha256'],
          'scope':'same observed logical initial state and inputs; selected state projection, aligned application ticks'}
        if (hashes()!=frozen or sha(Path(args.rom).read_bytes())!=ROM_SHA256
            or sha(Path(args.nes_core).read_bytes())!=NES_SHA
            or sha(Path(args.genesis_core).read_bytes())!=GEN_SHA):raise AssertionError('inputs changed')
        summary['inputs_unchanged']=True;summary['status']='passed'
    except Exception as exc:
        summary['status']='failed';summary['failure']=f'{type(exc).__name__}: {exc}';checkpoint();raise
    checkpoint();print(root/'summary.json')


if __name__=='__main__':main()
