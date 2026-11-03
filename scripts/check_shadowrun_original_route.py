#!/usr/bin/env python3
"""Check unpatched observed and unobserved original controller route receipts."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.shadowrun_field_combat import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
FRAMES=(5999,6059,6079,6100,6119,6120,6121,6122,6139,6140,6150,6175,6180,6200,6250,6299)
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--observed',required=True);p.add_argument('--control',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 roots=[Path(a.observed).resolve(),Path(a.control).resolve()];caps=[];receipts=[];rawcaps=[]
 for root in roots:
  raw=(root/'capture.json').read_bytes();cap=json.loads(raw);r=json.loads((root/'native/receipt.json').read_bytes())
  if r['system']!='genesis' or r['rom_sha256']!=ROM_SHA256 or r['core_sha256']!=CORE or r['patches'] or r['memory_injection_mode']!='no memory patches':raise ValueError('source identity or patch mismatch')
  caps.append(cap);receipts.append(r);rawcaps.append(raw)
 if receipts[0]['inputs']!=receipts[1]['inputs'] or caps[0]['inputs']['inputs']['sha256']!=caps[1]['inputs']['inputs']['sha256']:raise ValueError('input schedules differ')
 required=[{'start':6000,'end':6060,'buttons':['LEFT']},{'start':6080,'end':6101,'buttons':['UP']},{'start':6120,'end':6122,'buttons':['B']},{'start':6140,'end':6250,'buttons':['A']}]
 if [x for x in receipts[0]['inputs'] if x['start']<6250 and x['end']>6000]!=required:raise ValueError('controller route mismatch')
 if caps[0]['ram_write_observer']['start']!=6118 or caps[1]['ram_write_observer']['start'] is not None:raise ValueError('observer control mismatch')
 rows=[];profile_frames=[]
 for frame in FRAMES:
  rel=f'native/scene-{frame:06}/ram.bin';data=[]
  for root,cap in zip(roots,caps):
   b=(root/rel).read_bytes();meta=cap['files'][rel]
   if len(b)!=65536 or meta['size']!=len(b) or meta['sha256']!=sha(b):raise ValueError('snapshot hash mismatch')
   data.append(b)
  if data[0]!=data[1]:raise AssertionError(('RAM mismatch',frame))
  b=data[0];mem=bytes(b[i^1] for i in range(65536));rows.append({'frame':frame,'ram_sha256':sha(b),'target':int.from_bytes(mem[0x1a2:0x1a6],'big'),'ammo':mem[0x14e],'actor0_hp':mem[0x44c]})
  if frame in (5999,6140,6150,6175,6200):
   source=mem[0x100:0x200];target=mem[0x400:0x500]
   if (source[0x10],source[0x3e:0x40],source[0x4c],source[0x4d],source[0x56:0x58],source[0x78],source[0x7b],source[0x7c],source[0x81],source[0x82],source[0x90:0x92],source[0x9a],source[0x9c],source[0xb4],source[0xdf],source[0x66:0x76])!=(15,b'\x00\x00',10,2,b'\x00\x02',3,2,4,4,0,b'\x00\x04',0,10,0,0,bytes.fromhex('022c0e10000000000000060600000000')):raise AssertionError(('player profile mismatch',frame))
   if (target[0x10],target[0x4d],target[0x76],target[0x77],target[0x78],target[0x7b],target[0x7c],target[0x90:0x92],target[0x9a],target[0x9b],target[0x9e],target[0xb0],target[0xdf])!=(0x25,2,0,2,1,2,2,b'\x00\x00',0,19,0x20,0,0):raise AssertionError(('actor profile mismatch',frame))
   profile_frames.append(frame)
 byframe={x['frame']:x for x in rows}
 if byframe[6120]['target']!=0xff0400 or (byframe[6140]['ammo'],byframe[6140]['actor0_hp'])!=(12,10) or (byframe[6175]['ammo'],byframe[6175]['actor0_hp'])!=(11,6) or (byframe[6250]['ammo'],byframe[6250]['actor0_hp'])!=(10,5):raise AssertionError('route state mismatch')
 trace=(roots[0]/'native/ram-writes.json').read_bytes()
 if caps[0]['files']['native/ram-writes.json']['sha256']!=sha(trace):raise ValueError('trace hash mismatch')
 events=json.loads(trace);ammo=[(x['frame'],x['value']) for x in events if x['address']==0xff014e and x['pc']==0x3792];hp=[(x['frame'],x['value']) for x in events if x['address']==0xff044c and x['pc']==0x55a94]
 if ammo[:2]!=[(6164,11),(6216,10)] or hp[:2]!=[(6172,6),(6224,5)]:raise AssertionError('observed write mismatch')
 result={'status':'passed','rom_sha256':ROM_SHA256,'core_sha256':CORE,'input_schedule_sha256':caps[0]['inputs']['inputs']['sha256'],'observed_capture_sha256':sha(rawcaps[0]),'control_capture_sha256':sha(rawcaps[1]),'trace_sha256':sha(trace),'frames':rows,'profile_matched_frames':profile_frames,'trace_ammo_writes':ammo[:2],'trace_hp_writes':hp[:2],'scope':'unpatched controller route; observed and unobserved runs match at 16 full-RAM snapshots; exact intermediate write frames are instrumented only, with no all-frame or whole-machine equivalence claim'}
 out=_private_directory(a.output);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'passed','matched_snapshots':len(rows),'scope':result['scope']},indent=2))
if __name__=='__main__':main()
