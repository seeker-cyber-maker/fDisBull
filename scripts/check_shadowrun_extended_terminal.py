#!/usr/bin/env python3
"""Check the rebuilt stationary terminal and whole-state terminal hold."""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from check_shadowrun_macos import Native
from fdisbull.game_il import canonical
from fdisbull.shadowrun_assisted_arena import assisted_arena_from_capture
from fdisbull.shadowrun_replay import _read_rom


def sha(b): return hashlib.sha256(b).hexdigest()


def main():
 p=argparse.ArgumentParser()
 for n in ('rom','capture','library','launch-original','terminal-original','program-sha256','output'):p.add_argument('--'+n,required=True)
 a=p.parse_args();out=Path(a.output)
 if out.exists():raise FileExistsError(out)
 rom=_read_rom(Path(a.rom));m=assisted_arena_from_capture(rom,Path(a.capture));program=sha(canonical(m.program))
 if program!=a.program_sha256:raise ValueError('unexpected shared program')
 lib=Path(a.library);receipt=(lib.parent/'receipt.json').read_bytes();build=json.loads(receipt);seed=sha(json.dumps(m.snapshot(),sort_keys=True,separators=(',',':')).encode())
 if (build['program_sha256']!=program or build['seed_sha256']!=seed or build['dylib_sha256']!=sha(lib.read_bytes()) or
     build['source_sha256']!=sha((lib.parent/'fdisbull_native.c').read_bytes()) or build['header_sha256']!=sha((lib.parent/'fdisbull_native.h').read_bytes())):raise ValueError('native receipt mismatch')
 sources=[]
 for root,rh,ch in ((Path(a.launch_original),'b40dd5e704b7bba2c3c746a10473f120978f884e9528573da966c2245b4e8510','848cc21f3dc8bbfeac991b6af9a7b73ad21ba362a2f709db33c1d9e94b3e1f95'),(Path(a.terminal_original),'a1c969d5c64b651e9be1fb53bc840b60c223d7ef30eb2b3defadeadfc31a982f','626f509e1ea1018955e2d0c2f7d76f625d6c8c277e482022a5b30890df974b1f')):
  rr=(root/'native/receipt.json').read_bytes();cr=(root/'capture.json').read_bytes()
  if sha(rr)!=rh or sha(cr)!=ch:raise ValueError('source capture mismatch')
  sources.append((root,json.loads(cr)))
 native=Native(lib,Path(a.rom));compared=[]
 try:
  seed_state=m.snapshot();elements=native.compare(seed_state,'stationary seed')
  for f in range(6000,6243):
   m.call('shadowrun_arena_frame',0);s=m.snapshot();rc=native.step(0)
   if rc or s['shadowrun_arena_frame_status']!=(3 if f==6242 else 1):raise AssertionError(('native status',f,rc,s['shadowrun_arena_frame_status']))
   native.compare(s,'stationary '+str(f))
   for root,cap in sources:
    key=f'native/scene-{f:06d}/ram.bin'
    if key not in cap['files']:continue
    raw=(root/key).read_bytes()
    if len(raw)!=65536 or sha(raw)!=cap['files'][key]['sha256']:raise ValueError('source checkpoint changed')
    b=bytes(raw[i^1] for i in range(65536));fields=(('shadowrun_arena_hp',0x14c,1),('shadowrun_hostile_rng',0xf9f8,2))
    if f<6242:fields+=(('shadowrun_player_x',0x100,2),('shadowrun_player_y',0x104,2),('shadowrun_hostile_x',0x400,2),('shadowrun_hostile_y',0x404,2),('shadowrun_hostile_ammo',0x44e,1))
    for name,offset,width in fields:
     expected=int.from_bytes(b[offset:offset+width],'big')
     if s[name]!=expected:raise AssertionError(('source',f,name,s[name],expected))
    compared.append(f)
  if s['shadowrun_arena_hp']!=0:raise AssertionError('terminal HP')
  before=m.snapshot();m.call('shadowrun_arena_frame',64)
  if native.step(64):raise AssertionError('terminal hold failed')
  native.compare(m.snapshot(),'terminal hold')
  if m.snapshot()!=before:raise AssertionError('terminal mutated state')
  if native.lib.fdisbull_reset(native.ctx):raise AssertionError('reset failed')
  native.compare(seed_state,'stationary reset')
 finally:native.close()
 r={'status':'passed','program_sha256':program,'checker_sha256':sha(Path(__file__).read_bytes()),'native_build_receipt_sha256':sha(receipt),'native_library_sha256':sha(lib.read_bytes()),'ticks':243,'full_state_elements_each_tick':elements,'source_checkpoints_compared':len(compared),'source_checkpoint_frames':compared,'terminal_frame':6242,'terminal_hp':0,'terminal_hold_whole_state_unchanged':True,'reset':'passed','scope':'separate assisted stationary neutral route; HP/RNG-only source comparison at terminal; no original death continuation'}
 out.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':'passed','summary_sha256':sha(out.read_bytes()),'source_checkpoints':len(compared)}))

if __name__=='__main__':main()
