#!/usr/bin/env python3
"""Compare mapper controls by completed publication epoch and physical frame."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(data):return hashlib.sha256(data).hexdigest()


def load(root,rom):
    receipt_raw=(root/'receipt.json').read_bytes();r=json.loads(receipt_raw)
    trace=(root/'ram_trace.json').read_bytes()
    if (r['rom_sha256']!=sha(rom.read_bytes()) or r['ram_trace_sha256']!=sha(trace) or
        r['core_sha256']!='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60' or r['patches']):
        raise ValueError('Native receipt identity mismatch')
    return receipt_raw,r,trace,json.loads(trace)['frames']


def logical(rows):
    result={};wrap=0;last=None
    for row in rows:
        state=bytes.fromhex(row['raw']['state'])
        if state[:2]!=b'SW' or state[22]&1:continue
        if last is not None and state[23]<last:wrap+=256
        last=state[23]
        result[wrap+last]=(row['frame'],state)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline','candidate','baseline-rom','candidate-rom','output'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args();br,b,bt,brows=load(a.baseline,a.baseline_rom);cr,c,ct,crows=load(a.candidate,a.candidate_rom)
    if b['inputs']!=c['inputs'] or b['watches']!=c['watches'] or b['frames']!=c['frames']:
        raise ValueError('Different physical input or watch contract')
    left,right=logical(brows),logical(crows);common=sorted(left.keys()&right.keys())
    if not common:raise ValueError('No shared logical publications')
    mismatches=[]
    for tick in common:
        lf,l=left[tick];rf,r=right[tick]
        if l!=r:mismatches.append({'logical_epoch':tick,'baseline_frame':lf,'candidate_frame':rf,
                                   'differing_offsets':[i for i,(x,y) in enumerate(zip(l,r)) if x!=y]})
    if a.output.exists():raise ValueError('output exists')
    a.output.write_text(json.dumps({'format':'fdisbull-shadowrun-mapper-cadence-1',
        'baseline_receipt_sha256':sha(br),'candidate_receipt_sha256':sha(cr),
        'baseline_trace_sha256':sha(bt),'candidate_trace_sha256':sha(ct),
        'common_logical_epochs':len(common),'matching_logical_epochs':len(common)-len(mismatches),
        'mismatches':mismatches,'same_final_frame':b['frame_rgb_sha256']==c['frame_rgb_sha256'],
        'scope':'same physical schedule; logical epoch alignment does not imply identical sampled input'},indent=2)+'\n')


if __name__=='__main__':main()
