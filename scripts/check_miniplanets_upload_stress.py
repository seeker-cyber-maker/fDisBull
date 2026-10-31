#!/usr/bin/env python3
"""Exercise native inactive-nametable uploads with diagnostic, synthetic views.

Runs the pinned FCEUmm timing/coherence gate. All output and input snapshots are
private. Synthetic RAM writes and paused game audio are explicit interventions;
this does not establish ordinary gameplay or audio-interrupt coverage.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
from check_miniplanets_native import _private_output

HERE=Path(__file__).resolve().parent

def sha(b):return hashlib.sha256(b).hexdigest()
def sym(maptext,name):
 m=re.search(r'(?m)(?:^|\s)'+re.escape('_'+name)+r'\s+([0-9A-Fa-f]{6})\s',maptext)
 if not m:raise ValueError('missing linker symbol '+name)
 x=int(m.group(1),16)
 if not 0x6000<=x<0x8000:raise ValueError('symbol outside expected cartridge SRAM: '+name)
 return x-0x6000

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--core',required=True);p.add_argument('--rom',required=True);p.add_argument('--manifest',required=True);p.add_argument('--map',required=True);p.add_argument('--output',required=True)
 a=p.parse_args();out=_private_output(a.output);out.mkdir();frozen=out/'captured';frozen.mkdir()
 inputs={'core':Path(a.core),'rom':Path(a.rom),'manifest':Path(a.manifest),'map':Path(a.map),
         'stress_script':Path(__file__),'display_checker':HERE/'check_miniplanets_nes_display.py',
         'display_observer':HERE/'miniplanets_display_observer.c','host':HERE/'check_console_udc.py',
         'private_output_helper':HERE/'check_miniplanets_native.py'}
 before={};copies={}
 for name,path in inputs.items():
  path=path.expanduser().resolve();data=path.read_bytes();before[name]={'path':str(path),'size':len(data),'sha256':sha(data)}
  # Checker imports its helper by name; keep its original filenames together.
  dest=frozen/(path.name if name in ('display_checker','display_observer','host','private_output_helper') else name+path.suffix)
  if dest.exists():raise ValueError('duplicate capture name')
  dest.write_bytes(data);copies[name]=dest
 manifest=json.loads(copies['manifest'].read_text());maps=copies['map'].read_text()
 if manifest['rom_sha256']!=before['rom']['sha256']:raise ValueError('manifest and ROM differ')
 debug=manifest['debug'];pub=manifest['publication']
 if debug.get('display_prepare_procedure')!=253:raise ValueError('missing diagnostic upload procedure')
 syms={n:sym(maps,n) for n in ['display_plane','display_hud','display_attributes','active_nt','render_oam_page','video_ready','render_phase','upload_count','upload_cursor','upload_target_nt']}
 watches=[{'name':'debug','memory_id':2,'offset':debug['base'],'length':48},
          {'name':'publication','memory_id':pub['memory_id'],'offset':pub['base'],'length':pub['slots']*pub['stride']},
          {'name':'display_status','memory_id':0,'offset':syms['video_ready'],'length':4},
          {'name':'plan','memory_id':0,'offset':syms['upload_count'],'length':3},
          {'name':'plane','memory_id':0,'offset':syms['display_plane'],'length':256},
          {'name':'hud','memory_id':0,'offset':syms['display_hud'],'length':24},
          {'name':'attrs','memory_id':0,'offset':syms['display_attributes'],'length':16},
          {'name':'oam2','memory_id':2,'offset':512,'length':256},
          {'name':'oam3','memory_id':2,'offset':768,'length':256}]
 # A/B differ at every byte, forcing every region dirty after both physical NTs
 # have received A. The repeated patterns exercise no-dirty OAM-only commits.
 def view(seed):return bytes(((i*73+seed)&255) for i in range(296))
 cases=[('cold_a0',7),('cold_a1',7),('unchanged_a',7),('dirty_b0',164),('dirty_b1',164),('unchanged_b',164),('dirty_a0',7),('dirty_a1',7)]
 frames=350;start=60;spacing=32;patches=[{'frame':10,'memory_id':2,'offset':debug['mode'],'data_hex':'01'}]
 for i,(name,seed) in enumerate(cases):
  frame=start+i*spacing;data=view(seed);oam=bytes(((j*19+i*41+3)&255) for j in range(256));page=2+(i&1)
  for memory_id,offset,blob in [(0,syms['display_plane'],data[:256]),(0,syms['display_hud'],data[256:280]),(0,syms['display_attributes'],data[280:]),(0,syms['render_oam_page'],bytes([page])),(2,page*256,oam),(2,debug['procedure'],bytes([253])),(2,debug['command'],bytes([1]))]:
   patches.append({'frame':frame,'memory_id':memory_id,'offset':offset,'data_hex':blob.hex()})
 patch_path=out/'patches.json';patch_path.write_text(json.dumps(patches));watch_path=out/'watches.json';watch_path.write_text(json.dumps(watches))
 cmd=[sys.executable,str(copies['display_checker']),'--core',str(copies['core']),'--rom',str(copies['rom']),'--frames',str(frames),'--warmup','40','--patches',str(patch_path),'--watch',str(watch_path),'--active-nt-offset',str(syms['active_nt']),'--coherence-offsets',str(syms['display_plane']),str(syms['display_hud']),str(syms['display_attributes']),str(syms['render_oam_page']),'--require-safe-display','--output',str(out/'native')]
 run=subprocess.run(cmd,text=True,capture_output=True)
 if run.returncode:raise RuntimeError('native display gate failed: '+run.stderr[-3000:])
 d=json.loads((out/'native/display-receipt.json').read_text());trace=json.loads((out/'native/observed/ram_trace.json').read_text())['frames'];raw=(out/'native/observed/ppu-events.bin').read_bytes()
 events=list(struct.iter_unpack('<IIiHHBBxx',raw));results=[];last_nt=None
 def get(frame,name):return bytes.fromhex(trace[frame]['raw'][name])
 for i,(name,seed) in enumerate(cases):
  f=start+i*spacing;end=min(frames,f+spacing);data=view(seed)
  before_status=get(f-1,'display_status');assert before_status[0]==0,(name,'not idle before write',before_status.hex())
  page=2+(i&1);oam=bytes(((j*19+i*41+3)&255) for j in range(256))
  if before_status[3]==page:raise AssertionError((name,'staging OAM page was previously active'))
  # Command/result can become visible after several host frames.
  done=[j for j in range(f,end) if get(j,'debug')[debug['command']-debug['base']]==0 and int.from_bytes(get(j,'debug')[debug['result']-debug['base']:debug['result']-debug['base']+4],'little')==0 and get(j,'display_status')[0]==0 and get(j,'display_status')[2]!=before_status[2]]
  if not done:raise AssertionError((name,'no successful completed swap'))
  complete=done[0];nt=get(complete,'display_status')[2]
  if last_nt is not None and nt==last_nt:raise AssertionError((name,'NT failed to alternate'))
  last_nt=nt
  for j in range(f,complete+1):
   status=get(j,'display_status')
   if get(j,'plane')!=data[:256] or get(j,'hud')!=data[256:280] or get(j,'attrs')!=data[280:] or get(j,'oam'+str(page))!=oam or status[3]!=page:raise AssertionError((name,'staging changed',j))
   if get(j,'debug')[debug['fault']-debug['base']]!=0:raise AssertionError((name,'runtime fault',j))
  subset=[x for x in events if f<=x[0]<=complete and x[3] in (0x2006,0x2007)]
  addresses=sum(x[3]==0x2006 for x in subset);writes=sum(x[3]==0x2007 for x in subset)
  if addresses%2:raise AssertionError((name,'partial PPU address pair'))
  jobs=addresses//2;chunks=len({x[0] for x in subset if x[3]==0x2007})
  if any(sum(x[3]==0x2006 and x[0]==j for x in subset)>14 for j in range(f,complete+1)):raise AssertionError((name,'more than seven jobs in one frame'))
  if (name.startswith('dirty_') or name.startswith('cold_')) and (jobs,writes,chunks)!=(22,296,4):raise AssertionError((name,'not full 22-job four-chunk upload',jobs,writes,chunks))
  if name.startswith('unchanged_') and (jobs,writes,chunks)!=(0,0,0):raise AssertionError((name,'nonzero unchanged upload',jobs,writes,chunks))
  results.append({'name':name,'start_frame':f,'completion_frame':complete,'active_nt':nt,'oam_page':2+(i&1),'jobs':jobs,'ppu_data_writes':writes,'data_frames':chunks})
 after={}
 for name,path in inputs.items():
  try:
   b=path.expanduser().resolve().read_bytes();after[name]={'path':str(path.expanduser().resolve()),'size':len(b),'sha256':sha(b)}
  except OSError as e:after[name]={'path':str(path),'error':type(e).__name__}
 if before!=after:raise AssertionError('stress input changed during run')
 if any(sha(copies[name].read_bytes())!=info['sha256'] for name,info in before.items()):raise AssertionError('captured stress input changed')
 receipt={'format':'miniplanets-upload-stress-1','rom_sha256':before['rom']['sha256'],'inputs_before':before,'inputs_after':after,'diagnostic_scope':'synthetic RAM patches; debug mode pauses game audio IRQ; ordinary play and active audio are excluded','cases':results,'native_display_receipt_sha256':sha((out/'native/display-receipt.json').read_bytes()),'native_coherence':d['coherence'],'native_stack':d['stack'],'status':'pass'}
 (out/'stress-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(out/'stress-receipt.json')
if __name__=='__main__':main()
