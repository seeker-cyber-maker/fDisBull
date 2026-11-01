#!/usr/bin/env python3
"""Compare one assisted placement/step and a refusal to shared GameIL.

The supplied native receipts, capture and generated JSON are private. This
checks finite prepared-state observations, not original reachability.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fdisbull.shadowrun_play import machine_from_capture

CORE='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60'
def sha(b): return hashlib.sha256(b).hexdigest()
def read_run(path,rom,inputs):
    receipt_raw=(path/'receipt.json').read_bytes();receipt=json.loads(receipt_raw)
    trace_raw=(path/'ram_trace.json').read_bytes()
    if (receipt.get('system')!='nes' or receipt.get('core_sha256')!=CORE or receipt.get('rom_sha256')!=sha(rom)
        or receipt.get('inputs')!=inputs or receipt.get('patches')!=[] or receipt.get('ram_trace_sha256')!=sha(trace_raw)
        or receipt.get('watches')!=[{'name':'state','offset':1792,'length':41}]):
        raise ValueError('NES run provenance mismatch')
    trace=json.loads(trace_raw)['frames']
    if len(trace)!=receipt['frames'] or any(x['frame']!=i for i,x in enumerate(trace)): raise ValueError('Incomplete trace')
    return receipt_raw,trace

def main():
    p=argparse.ArgumentParser();
    for x in ('rom','capture','nes','step-run','fail-run','output'):p.add_argument('--'+x,required=True,type=Path)
    a=p.parse_args();out=a.output.resolve()
    if out.exists() or any((q/'.git').exists() for q in (out,*out.parents)):raise ValueError('output must be new and private')
    rom=a.rom.read_bytes();nes=a.nes.read_bytes()
    select={'start':100,'end':112,'buttons':['SELECT']};fire={'start':160,'end':172,'buttons':['A']}
    step_inputs=[select,{'start':130,'end':142,'buttons':['RIGHT']},fire,{'start':190,'end':194,'buttons':['RIGHT']}]
    fail_inputs=[select,{'start':130,'end':142,'buttons':['UP']},fire]
    sr,step=read_run(a.step_run,nes,step_inputs);fr,fail=read_run(a.fail_run,nes,fail_inputs)
    machine=machine_from_capture(rom,a.capture)
    for _ in range(63):machine.call('shadowrun_play_frame',0)
    checkpoints={160,189,190,193,194,210};comparisons=[]
    for f in range(100,211):
        pad=32 if f<112 else 8 if 130<=f<142 or 190<=f<194 else 64 if 160<=f<172 else 0
        machine.call('shadowrun_play_frame',pad)
        if f in checkpoints:
            state=machine.snapshot();raw=bytes.fromhex(step[f]['raw']['state'])
            if raw[:2]!=b'SW' or raw[22]&1:raise ValueError('Torn publication')
            expected=[state[k] for k in ('shadowrun_player_x','shadowrun_player_y','shadowrun_camera_x','shadowrun_camera_y')]
            observed=[int.from_bytes(raw[o:o+2],'little') for o in (4,6,14,16)]
            comparisons.append({'frame':f,'expected':expected,'observed':observed})
    before=bytes.fromhex(fail[90]['raw']['state']);after=bytes.fromhex(fail[180]['raw']['state'])
    unchanged=all(before[o:o+2]==after[o:o+2] for o in (4,6,14,16))
    good=all(x['expected']==x['observed'] for x in comparisons) and unchanged and after[35:37]==bytes([1,2])
    result={'format':'fdisbull-shadowrun-debug-native-check-1','nes_sha256':sha(nes),'core_sha256':CORE,
            'step_receipt_sha256':sha(sr),'fail_receipt_sha256':sha(fr),'comparisons':comparisons,
            'refusal_kept_player_and_camera':unchanged,'refusal_result':list(after[35:37]),'passed':good,
            'scope':'assisted target placement and subsequent four direction ticks; collision model and viewport only'}
    out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    if not good:raise SystemExit(1)
if __name__=='__main__':main()
