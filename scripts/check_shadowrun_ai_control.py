#!/usr/bin/env python3
"""Compare a separately built pruned control against the frozen NES profile.

Only even-sequence completed publications are authoritative. Differing odd
sequences are reported as in-progress observations, not completed state.
"""
import argparse,hashlib,json
from pathlib import Path

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for n in ('baseline','candidate','baseline-rom','candidate-rom','output'):p.add_argument('--'+n,required=True,type=Path)
 a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):raise ValueError('output must be new and private')
 def load(root,image):
  rr=(root/'receipt.json').read_bytes();r=json.loads(rr);tr=(root/'ram_trace.json').read_bytes()
  if (r.get('system')!='nes' or r.get('core_sha256')!='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60' or r.get('rom_sha256')!=sha(image.read_bytes()) or r.get('patches')!=[] or r.get('ram_trace_sha256')!=sha(tr)):
   raise ValueError('invalid native provenance')
  rows=json.loads(tr)['frames']
  if len(rows)!=r['frames'] or any(x['frame']!=i for i,x in enumerate(rows)):raise ValueError('incomplete native trace')
  return rr,r,tr,rows
 ar,aa,at,x=load(a.baseline,a.baseline_rom);br,bb,bt,y=load(a.candidate,a.candidate_rom)
 if aa['inputs']!=bb['inputs'] or aa['watches']!=bb['watches'] or len(x)!=len(y):raise ValueError('different test contract')
 mismatches=[];stable=0;in_progress=0
 for left,right in zip(x,y):
  if left['input_mask']!=right['input_mask']:raise ValueError('input trace mismatch')
  l=bytes.fromhex(left['raw']['state']);r=bytes.fromhex(right['raw']['state'])
  if l[:2]!=b'SW' or r[:2]!=b'SW':continue
  if l[22]&1 or r[22]&1:
   in_progress+=1
   continue
  stable+=1
  if l!=r:mismatches.append({'frame':left['frame']})
 if not stable:raise ValueError('no stable publications')
 result={'format':'fdisbull-shadowrun-ai-control-check-1','stable_frames':stable,'in_progress_frames_skipped':in_progress,
         'mismatches':mismatches,'final_frame_equal':aa['frame_rgb_sha256']==bb['frame_rgb_sha256'],
         'baseline_rom_sha256':sha(a.baseline_rom.read_bytes()),'candidate_rom_sha256':sha(a.candidate_rom.read_bytes()),
         'baseline_receipt_sha256':sha(ar),'candidate_receipt_sha256':sha(br),
         'baseline_trace_sha256':sha(at),'candidate_trace_sha256':sha(bt),
         'scope':'same-input static-NPC controls; no AI or whole-game claim'}
 out.write_text(json.dumps(result,indent=2)+'\n');print(f'{stable} stable frames, {len(mismatches)} differences; {in_progress} in-progress skipped')
 if mismatches or not result['final_frame_equal']:raise SystemExit(1)
if __name__=='__main__':main()
