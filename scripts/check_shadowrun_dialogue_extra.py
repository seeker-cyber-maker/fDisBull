#!/usr/bin/env python3
"""Controlled original-processor checks; output directory must be private."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'src'))
if not __debug__: raise RuntimeError('Qualification requires Python assertions enabled')
tracked_names=('scripts/check_shadowrun_dialogue_extra.py','scripts/probe_genesis_function.py',
    'src/fdisbull/shadowrun_world.py','src/fdisbull/shadowrun_dialogue.py',
    'src/fdisbull/game_sources/shadowrun_dialogue.c','src/fdisbull/game_il.py')
def sha(raw): return hashlib.sha256(raw).hexdigest()
tracked={name:sha((root/name).read_bytes()) for name in tracked_names}
from fdisbull.console_udc import _private_directory
from fdisbull.shadowrun_dialogue import lift_dialogue, read_prompt
from fdisbull.shadowrun_world import decode_stream, decode_scene_stream, read_scene
from fdisbull.game_il import GameMachine
ap=argparse.ArgumentParser()
ap.add_argument('--rom', required=True)
ap.add_argument('--core', required=True)
ap.add_argument('--output', required=True)
args=ap.parse_args()
rom=Path(args.rom).resolve()
core=Path(args.core).resolve()
b=rom.read_bytes()
core_sha=sha(core.read_bytes())
source_sha=sha(b)
out=_private_directory(args.output);out.mkdir();m=GameMachine(lift_dialogue(b),{})
receipts={}
stream_summaries={}

def run(name,contract):
 p=out/(name+'.json');p.write_text(json.dumps(contract));q=subprocess.run([sys.executable,str(root/'scripts/probe_genesis_function.py'),'--rom',str(rom),'--core',str(core),'--contract',str(p),'--output',str(out/name)],text=True,capture_output=True)
 if q.returncode: raise RuntimeError(q.stderr)
 r=json.loads((out/name/'receipt.json').read_text())
 if (not r['complete'] or not r['inputs_unchanged'] or r['source_sha256'] != source_sha or
     r['core_sha256'] != core_sha or r['probe_source_sha256'] != tracked['scripts/probe_genesis_function.py']):
  raise AssertionError('native input identity or completion mismatch')
 receipts[name]={'cases':len(r['cases']), 'contract_sha256':r['contract_sha256'],
                 'trace_sha256':r['trace_sha256'], 'instructions_executed':r['instructions_executed']}
 return r['cases']
# Source records: all eight combinations for the one- and two-choice prompts.
cases=[]
for address in (0xf4aa0,0xf4ab4):
 prompt=read_prompt(b,address)
 for i in range(8):
  flags=((i&1)<<6)|((i&2)<<3)|((i&4)<<3)
  enabled=('00' if len(prompt.options)>1 else 'ff')+('00' if len(prompt.options)>2 else 'ff')
  cases.append({'name':f'{address:x}-{i}','registers':{'A0':address+16},
   'ram':[{'address':0xffdd22,'data':f'{flags:02x}'},{'address':0xfff0d2,'data':enabled}]})
native=run('source-prompts',{'name':'source-prompts','entry':0x1f522,
 'code_ranges':[{'start':0x1f522,'end':0x1f572}],'stop_pcs':[0x1f572,0x1f3c4,0x1f50c],
 'max_instructions':18,'cases':cases})
for index,n in enumerate(native):
 address=(0xf4aa0,0xf4ab4)[index//8]; prompt=read_prompt(b,address); i=index%8
 flags=((i&1)<<6)|((i&2)<<3)|((i&4)<<3); targets=prompt.targets+(0,)*(3-len(prompt.targets))
 m.set_state(dict(zip(('shadowrun_dialogue_buttons','shadowrun_dialogue_option_count',
  'shadowrun_dialogue_terminal','shadowrun_dialogue_target_a','shadowrun_dialogue_target_b',
  'shadowrun_dialogue_target_c'),(flags,len(prompt.options),0,*targets))))
 m.call('shadowrun_dialogue_select'); state=m.snapshot(); regs=n['registers_after']; pc=regs['PC']
 expected=(0,0) if pc==0x1f50c else ((1 if pc==0x1f572 else 2),regs['A0'])
 if (state['shadowrun_dialogue_result'],state['shadowrun_dialogue_value'])!=expected:
  raise AssertionError(cases[index]['name'])
print('source prompt cases',len(native))
cases=[]
for i in range(8):
 flags=((i&1)<<6)|((i&2)<<3)|((i&4)<<3)
 cases.append({'name':str(i),'registers':{'A0':0xffa000},'ram':[{'address':0xffa000,'data':'00000001000000fa000f4ab4'},{'address':0xffdd22,'data':f'{flags:02x}'},{'address':0xfff0d2,'data':'0000'}]})
r=run('three',{'name':'three','entry':0x1f522,'code_ranges':[{'start':0x1f522,'end':0x1f572}],'stop_pcs':[0x1f572,0x1f3c4,0x1f50c],'max_instructions':18,'cases':cases})
for i,n in enumerate(r):
 flags=((i&1)<<6)|((i&2)<<3)|((i&4)<<3);m.set_state({'shadowrun_dialogue_buttons':flags,'shadowrun_dialogue_option_count':3,'shadowrun_dialogue_terminal':0,'shadowrun_dialogue_target_a':1,'shadowrun_dialogue_target_b':250,'shadowrun_dialogue_target_c':0xf4ab4});m.call('shadowrun_dialogue_select');s=m.snapshot();reg=n['registers_after'];expected=(0,0) if reg['PC']==0x1f50c else (1 if reg['PC']==0x1f572 else 2,reg['A0']);assert (s['shadowrun_dialogue_result'],s['shadowrun_dialogue_value'])==expected
print('three option cases',len(r))
cases=[{'name':str(v),'registers':{'A0':0xffa000},'ram':[{'address':0xffa000,'data':f'{v:08x}'}]} for v in (0xffffffff,0x80000000,0x00010000)]
r=run('terminal',{'name':'terminal','entry':0x1f40a,'code_ranges':[{'start':0x1f40a,'end':0x1f412}],'stop_pcs':[0x1f412,0x1f592],'max_instructions':4,'cases':cases})
for case,n in zip(cases,r):
    pointer=int(case['ram'][0]['data'],16)
    m.set_state({'shadowrun_dialogue_terminal':int(bool(pointer & 0x80000000)),
                 'shadowrun_dialogue_buttons':0,'shadowrun_dialogue_option_count':1})
    m.call('shadowrun_dialogue_select')
    state=m.snapshot()
    terminal=n['registers_after']['PC']==0x1f592
    assert (state['shadowrun_dialogue_result'],state['shadowrun_dialogue_value']) == ((3,251) if terminal else (0,0))
print('terminal cases',len(r))
cases=[{'name':f'{w:08x}-{c}', 'ram':[{'address':0xfffbfe,'data':f'{w:08x}'},{'address':0xfff10d,'data':f'{c:02x}'}]} for w,c in [(19,20),(20,20),(21,20),(0,0),(0x80000014,20),(0xffffffff,255)]]
r=run('payment',{'name':'payment','entry':0x21458,'code_ranges':[{'start':0x21458,'end':0x2148a}],'stop_pcs':[0x21472,0x21488], 'max_instructions':12,'watch':[{'name':'wallet','address':0xfffbfe,'length':4},{'name':'charge','address':0xfff10d,'length':1}],'cases':cases})
for case,n in zip(cases,r):
 wallet=int(case['ram'][0]['data'],16);charge=int(case['ram'][1]['data'],16);m.set_state({'shadowrun_dialogue_wallet':wallet,'shadowrun_dialogue_charge':charge});m.call('shadowrun_dialogue_pay');s=m.snapshot();actual=(s['shadowrun_dialogue_wallet'],s['shadowrun_dialogue_charge'],s['shadowrun_dialogue_response']);expected=(int(n['ram_after']['wallet'],16),int(n['ram_after']['charge'],16),n['registers_after']['A0']);assert actual==expected,(actual,expected)
print('payment cases',len(r))
stream=bytes([0,8,0x18,65,66,67,0,88,0x90,0]); cases=[{'name':'lz-rle-literal','registers':{'A3':0xffa000,'A1':0xffa100},'ram':[{'address':0xffa000,'data':stream.hex()}]}]
r=run('stream',{'name':'stream','entry':0x1610,'code_ranges':[{'start':0x1610,'end':0x167a}],'stop_pcs':[0x167a],'stack_scratch_bytes':64,'max_instructions':200,'watch':[{'name':'output','address':0xffa100,'length':9}],'cases':cases});assert bytes.fromhex(r[0]['ram_after']['output'])==decode_stream(stream,0)[0];print('decompress cases',len(r))
assert rom.read_bytes() == b


# Both selected candidate streams fit the probe's bounded 32 KiB watch budget.
for scene_id in (0,2):
    scene=read_scene(b,scene_id)
    decoded,_=decode_scene_stream(b,scene_id)
    watches=[{'name':f'part{i}', 'address':0xff6700+i, 'length':min(4096,len(decoded)-i)}
             for i in range(0,len(decoded),4096)]
    r=run(f'scene{scene_id}-stream',{'name':f'scene{scene_id}-stream','entry':0x1610,
        'code_ranges':[{'start':0x1610,'end':0x167a}],'stop_pcs':[0x167a],
        'stack_scratch_bytes':64,'max_instructions':200000,'max_master_cycles':10000000,
        'registers':{'A3':scene.stream_source & ~1,'A1':0xff6700},'watch':watches})
    actual=b''.join(bytes.fromhex(r[0]['ram_after'][f'part{i}']) for i in range(0,len(decoded),4096))
    if actual != decoded: raise AssertionError(f'scene {scene_id} decompression differs')
    stream_summaries[str(scene_id)]={'decoded_bytes':len(decoded),'decoded_sha256':sha(decoded),'all_bytes_match':True}
    print('scene',scene_id,'stream matched bytes',len(decoded))
if rom.read_bytes() != b: raise AssertionError('ROM changed')

# Two independent flag-setting leaves selected by commands 0x30 and 0x31.
for command, entry, stop, address, size in ((0x30,0x213ca,0x213e0,0xfffc30,4),
                                             (0x31,0x213e2,0x213f8,0xfffc27,1)):
    values=(0,1,2,(1 << (size*8))-1)
    cases=[{'name':str(v),'ram':[{'address':address,'data':v.to_bytes(size,'big').hex()}]}
           for v in values]
    native=run(f'flag-{command:02x}', {'name':f'flag-{command:02x}', 'entry':entry,
        'code_ranges':[{'start':entry,'end':stop}], 'stop_pcs':[stop], 'max_instructions':10,
        'watch':[{'name':'flag','address':address,'length':size}], 'cases':cases})
    key='shadowrun_dialogue_flag30' if command==0x30 else 'shadowrun_dialogue_flag27'
    for value,case in zip(values,native):
        m.set_state({'shadowrun_dialogue_result':1,'shadowrun_dialogue_value':command,key:value})
        m.call('shadowrun_dialogue_dispatch')
        state=m.snapshot()
        expected=(int(case['ram_after']['flag'],16),2,case['registers_after']['A0'])
        actual=(state[key],state['shadowrun_dialogue_result'],state['shadowrun_dialogue_value'])
        if actual != expected: raise AssertionError((command,value,actual,expected))
    print('flag command',hex(command),'cases',len(native))

if any(sha((root/name).read_bytes()) != value for name,value in tracked.items()):
    raise AssertionError('qualification source changed during run')
if sha(rom.read_bytes()) != source_sha or sha(core.read_bytes()) != core_sha:
    raise AssertionError('ROM or core changed during run')
summary={'format':'fdisbull-shadowrun-dialogue-world-qualification-1','status':'passed',
    'rom_sha256':source_sha,'core_sha256':core_sha,'tracked_source_sha256':tracked,
    'native_boundaries':receipts,'streams':stream_summaries,
    'scope':'controlled original-core entry; synthetic three-choice and terminal, payment and flag leaves, source stream decoding; no ordinary gameplay or full-game parity'}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('source-bound qualification passed')
