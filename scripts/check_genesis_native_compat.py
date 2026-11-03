#!/usr/bin/env python3
"""Check legacy Genesis default entry with the generalized macOS backend."""
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.shadowrun_assisted_arena import assisted_arena_from_capture
from fdisbull.udc_macos import build_macos
from fdisbull.game_il import canonical
from check_shadowrun_macos import Native

def sha(x):return hashlib.sha256(x).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for n in ('rom','capture','original','output'):p.add_argument('--'+n,required=True,type=Path)
 a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):raise ValueError('fresh private output required')
 rom=a.rom.read_bytes();m=assisted_arena_from_capture(rom,a.capture);seed=m.snapshot()
 receipt=(a.original/'capture.json').read_bytes();original=json.loads(receipt)
 if original['inputs']['rom']['sha256']!=sha(rom):raise ValueError('original ROM mismatch')
 out.mkdir(mode=0o700,parents=True);build=build_macos(m.program,seed,out/'native');n=Native(out/'native'/'libfdisbull_native.dylib',a.rom.resolve());comparisons=0;fields=0
 try:
  for f in range(6000,6052):
   m.call('shadowrun_arena_frame',0);s=m.snapshot()
   if n.step(0)!=0 or s['shadowrun_arena_frame_status']!=1:raise AssertionError(('native step',f))
   fields+=n.compare(s,f)
   raw=(a.original/'native'/f'scene-{f:06}'/'ram.bin').read_bytes()
   expected_hash=original['files'][f'native/scene-{f:06}/ram.bin']['sha256']
   if sha(raw)!=expected_hash:raise AssertionError(('original hash',f))
   b=bytes(raw[i^1] for i in range(65536));w=lambda x:int.from_bytes(b[x:x+2],'big')
   got=(s['shadowrun_player_x'],s['shadowrun_player_y'],s['shadowrun_arena_hp'],s['shadowrun_target_x'][0],s['shadowrun_target_y'][0],s['shadowrun_play_actor_hp'][0])
   expect=(w(0x100),w(0x104),b[0x14c],w(0x400),w(0x404),b[0x44c])
   if got!=expect:raise AssertionError((f,got,expect))
   comparisons+=1
 finally:n.close()
 summary={'format':'genesis-macos-default-entry-regression-1','rom_sha256':sha(rom),'source_receipt_sha256':sha(receipt),'program_sha256':sha(canonical(m.program)),'native_build':build,'ticks':comparisons,'native_state_elements':fields,'source_fields_per_frame':6,'scope':'prepared arena, default entry, original sampled actor positions and HP'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({'ticks':comparisons,'native_state_elements':fields}))
if __name__=='__main__':main()
