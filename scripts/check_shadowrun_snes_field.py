#!/usr/bin/env python3
"""Compare captured SNES actor and collision fields to the original core."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.game_il import canonical
from fdisbull.shadowrun_snes_field import SOURCE,machine_from_capture,ROM_SHA256,SNAPSHOT_SHA256,SAVE_SHA256
BASE_CORE_SHA='89fe8f7602428dbe532a19f098075182619c576383f177e641b19eb1f5fa19e8'
PAD={'UP':1,'DOWN':2,'LEFT':4,'RIGHT':8}

def sha(b):return hashlib.sha256(b).hexdigest()
def original_receipt(run):
 raw=(run/'receipt.json').read_bytes();receipt=json.loads(raw)
 if receipt['rom_sha256']!=ROM_SHA256 or receipt['core_sha256']!=BASE_CORE_SHA or receipt['patches'] or receipt['system']!='snes':raise ValueError('wrong original capture')
 return raw,receipt
def original_frame(run,receipt,frame,pad):
 actual_pad=0
 for event in receipt['inputs']:
  if event['start']<=frame<event['end']:
   for button in event['buttons']:
    if button not in PAD:raise ValueError('unmodeled original controller input')
    actual_pad|=PAD[button]
 if actual_pad!=pad:raise ValueError('original controller sequence mismatch')
 entries=[item for item in receipt['frame_ram'] if item['frame']==frame]
 if len(entries)!=1:raise ValueError('original frame missing or ambiguous')
 item=entries[0];raw=(run/item['file']).read_bytes()
 if len(raw)!=131072 or sha(raw)!=item['sha256']:raise ValueError('original RAM hash mismatch')
 return raw
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','field','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();field=Path(a.field);rom=Path(a.rom).read_bytes();seed=field/'right-dense-02';ram=(seed/'ram-002999.bin').read_bytes();save=(seed/'save_ram.bin').read_bytes();rows=[]
 for name,pad in [('neutral',0),('right',8),('left',4),('up',1),('down',2)]:
  run=field/('right-dense-02' if name=='right' else name+'-dense-01');receipt_raw,r=original_receipt(run)
  m=machine_from_capture(rom,ram,save); checks=[]
  for f in range(3000,3021):
   m.call('shadowrun_snes_frame',pad);s=m.snapshot()
   if s['shadowrun_snes_frame_status']!=1:raise AssertionError((name,f,'refused'))
   if f>3010 and f!=3020:continue
   raw=original_frame(run,r,f,pad);w=lambda n:int.from_bytes(raw[n:n+2],'little');got=tuple(s[k] for k in ('shadowrun_snes_player_x','shadowrun_snes_player_y','shadowrun_snes_player_z','shadowrun_snes_velocity_x','shadowrun_snes_velocity_y','shadowrun_snes_flags'));exp=tuple(w(n) for n in (0xe86,0xede,0xf36,0xd7e,0xdd6,0x14b6))
   if got!=exp:raise AssertionError((name,f,got,exp))
   checks.append(f)
  rows.append({'direction':name,'checked_frames':checks,'original_receipt_sha256':sha(receipt_raw)})
 long_checks=[]
 for name,pad,last in [('right',8,3199),('up',1,3199),('left',4,3050),('down',2,3070)]:
  run=field/(name+'-long-01');long_receipt_raw,long_receipt=original_receipt(run);m=machine_from_capture(rom,ram,save);checks=[]
  for f in range(3000,last+1):
   m.call('shadowrun_snes_frame',pad);s=m.snapshot()
   if s['shadowrun_snes_frame_status']!=1:raise AssertionError((name,f,'long refusal'))
   if f not in (3030,3050,3070,3100,3150,3199):continue
   raw=original_frame(run,long_receipt,f,pad);w=lambda n:int.from_bytes(raw[n:n+2],'little');got=tuple(s[k] for k in ('shadowrun_snes_player_x','shadowrun_snes_player_y','shadowrun_snes_player_z','shadowrun_snes_velocity_x','shadowrun_snes_velocity_y','shadowrun_snes_flags'));exp=tuple(w(n) for n in (0xe86,0xede,0xf36,0xd7e,0xdd6,0x14b6))
   if got!=exp:raise AssertionError((name,f,got,exp))
   checks.append(f)
  long_checks.append({'direction':name,'last_model_frame':last,'matched_source_checkpoints':checks,'original_receipt_sha256':sha(long_receipt_raw)})
 m=machine_from_capture(rom,ram,save);before=m.snapshot();m.call('shadowrun_snes_frame',9);after=m.snapshot()
 if after['shadowrun_snes_frame_status']!=2 or any(after[k]!=before[k] for k in ('shadowrun_snes_player_x','shadowrun_snes_player_y','shadowrun_snes_player_z','shadowrun_snes_flags')):raise AssertionError('chord should refuse')
 m=machine_from_capture(rom,ram,save);m.call('shadowrun_snes_frame',8);m.call('shadowrun_snes_frame',0)
 if m.snapshot()['shadowrun_snes_frame_status']!=1 or m.snapshot()['shadowrun_snes_velocity_x'] or m.snapshot()['shadowrun_snes_velocity_y']:raise AssertionError('release did not stop')
 turn=field/'turn-dense-01';turn_raw,turn_receipt=original_receipt(turn);m=machine_from_capture(rom,ram,save)
 for f in range(3000,3022):
  pad=8 if f<3005 else 2 if f<3010 else 4 if f<3015 else 1 if f<3020 else 0
  m.call('shadowrun_snes_frame',pad);s=m.snapshot();raw=original_frame(turn,turn_receipt,f,pad);w=lambda n:int.from_bytes(raw[n:n+2],'little')
  got=tuple(s[k] for k in ('shadowrun_snes_player_x','shadowrun_snes_player_y','shadowrun_snes_player_z','shadowrun_snes_velocity_x','shadowrun_snes_velocity_y','shadowrun_snes_flags'));exp=tuple(w(n) for n in (0xe86,0xede,0xf36,0xd7e,0xdd6,0x14b6))
  if s['shadowrun_snes_frame_status']!=1 or got!=exp:raise AssertionError(('turn and release',f,got,exp))
 out={'status':'passed','source_sha256':sha(rom),'initial_wram_sha256':sha(ram),'save_ram_sha256':sha(save),'authoring_sha256':sha(SOURCE.read_bytes()),'program_sha256':sha(canonical(m.program)),'comparisons':rows,'long_comparisons':long_checks,'unsupported_chord_refused':True,'turn_and_release_matched_frames':22,'turn_original_receipt_sha256':sha((turn/'receipt.json').read_bytes()),'scope':'Assisted source capture seeds immutable static collision geometry; original gameplay route and ordinary directional input. Compare selected actor fields, not full world or rendering.'}
 Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
