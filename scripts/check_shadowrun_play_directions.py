#!/usr/bin/env python3
"""Compare all four finite NES controller routes with the shared GameIL."""
import argparse,hashlib,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fdisbull.shadowrun_play import machine_from_capture

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for n in ('rom','capture','nes','runs','output'):p.add_argument('--'+n,required=True,type=Path)
 a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((q/'.git').exists() for q in (out,*out.parents)):raise ValueError('output must be new and private')
 rom=a.rom.read_bytes();nes=a.nes.read_bytes();reports=[]
 fields=[('shadowrun_player_x',4),('shadowrun_player_y',6),('shadowrun_player_heading',8),('shadowrun_pad_sample',10),('shadowrun_direction_angle',12),('shadowrun_camera_x',14),('shadowrun_camera_y',16),('shadowrun_camera_scroll_ax',18),('shadowrun_camera_scroll_ay',20)]
 for name,pad in (('up',1),('down',2),('left',4)):
  path=a.runs/(name+'-run-10');receipt_raw=(path/'receipt.json').read_bytes();receipt=json.loads(receipt_raw);trace_raw=(path/'ram_trace.json').read_bytes();trace=json.loads(trace_raw)['frames']
  if (receipt.get('system')!='nes' or receipt.get('core_sha256')!='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60' or receipt.get('rom_sha256')!=sha(nes) or receipt.get('patches')!=[] or receipt.get('ram_trace_sha256')!=sha(trace_raw) or receipt.get('inputs')!=[{'start':100,'end':160,'buttons':[name.upper()]}] or receipt.get('watches')!=[{'name':'state','offset':1792,'length':41}] or len(trace)!=receipt['frames']):raise ValueError('bad target provenance')
  m=machine_from_capture(rom,a.capture)
  for _ in range(63):m.call('shadowrun_play_frame',0)
  bad=[];previous=None
  for f in range(100,160):
   m.call('shadowrun_play_frame',pad);s=m.snapshot();b=bytes.fromhex(trace[f]['raw']['state'])
   if b[:2]!=b'SW' or b[22]&1 or (previous is not None and b[23]!=(previous+1)&255):bad.append({'frame':f,'field':'publication sequence'})
   previous=b[23]
   for key,off in fields:
    got=int.from_bytes(b[off:off+2],'little')
    if got!=s[key]:bad.append({'frame':f,'field':key,'nes':got,'gameil':s[key]})
   if b[2]!=s['shadowrun_opening_status']:bad.append({'frame':f,'field':'status','nes':b[2],'gameil':s['shadowrun_opening_status']})
  reports.append({'direction':name,'frames':60,'mismatches':bad,'receipt_sha256':sha(receipt_raw),'trace_sha256':sha(trace_raw)})
 result={'format':'fdisbull-shadowrun-play-directions-1','nes_sha256':sha(nes),'directions':reports,'scope':'prepared scene; NES vs same GameIL only, original comparisons separate'}
 out.write_text(json.dumps(result,indent=2)+'\n');print([(r['direction'],len(r['mismatches'])) for r in reports])
 if any(r['mismatches'] for r in reports):raise SystemExit(1)
if __name__=='__main__':main()
