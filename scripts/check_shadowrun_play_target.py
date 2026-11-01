#!/usr/bin/env python3
"""Compare a target-adapted NES selection with prepared original leaves."""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fdisbull.game_il import canonical
from fdisbull.shadowrun_targeting import lift_targeting
from check_shadowrun_opening_route import checked_receipt,NES_CORE_SHA,GENESIS_CORE_SHA,SOURCE_ROM_SHA,indexed_frames

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--linked-combat',action='store_true')
 for n in ('rom','nes','original','run','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((x/'.git').exists() for x in (out,*out.parents)):raise ValueError('output must be new and private')
 rom=a.rom.read_bytes();nes=a.nes.read_bytes();summary_raw=(a.original/'summary.json').read_bytes();s=json.loads(summary_raw)
 if (sha(rom)!=SOURCE_ROM_SHA or s.get('complete') is not True or s.get('rom_sha256')!=sha(rom) or s.get('core_sha256')!=GENESIS_CORE_SHA or s.get('program_sha256')!=sha(canonical(lift_targeting(rom))) or s.get('camera_fixed')!=[17024,11328] or sha((a.original/'projection-native/receipt.json').read_bytes())!=s.get('projection_receipt_sha256') or sha((a.original/'target-native/receipt.json').read_bytes())!=s.get('target_receipt_sha256')):raise ValueError('original prepared check mismatch')
 raw_receipt=(a.run/'receipt.json').read_bytes();r=json.loads(raw_receipt);checked_receipt(r,system='nes',core_sha=NES_CORE_SHA,rom_sha=sha(nes))
 expected_inputs=[{'start':100,'end':104,'buttons':['SELECT']}]+[{'start':120+10*i,'end':124+10*i,'buttons':['RIGHT']} for i in range(7)]+[{'start':200+10*i,'end':204+10*i,'buttons':['DOWN']} for i in range(3)]+[{'start':240,'end':244,'buttons':['A']},{'start':280,'end':284,'buttons':['B']},{'start':300,'end':650 if a.linked_combat else 304,'buttons':['A']}]
 if r.get('inputs')!=expected_inputs or r.get('watches')!=[{'name':'state','offset':1792,'length':84 if a.linked_combat else 64}]:raise ValueError('wrong NES input/watch')
 raw=(a.run/'ram_trace.json').read_bytes();frames=indexed_frames(raw,r);before=bytes.fromhex(frames[280]['raw']['state']);after=bytes.fromhex(frames[300]['raw']['state'])
 if any(b[:2]!=b'SW' or b[22]&1 for b in (before,after)):raise ValueError('unstable publication')
 actual=[before[55],int.from_bytes(before[58:60],'little'),before[62],int.from_bytes(before[60:62],'little'),before[63]]
 wanted=[s['selected_slot'],s['contacts'][s['selected_slot']],s['selected_flags_low'],s['selected_marker'],int(bool(s['selected_backlink']))]
 camera=[int.from_bytes(before[x:x+2],'little') for x in (14,16)]
 if a.linked_combat:
  end=bytes.fromhex(frames[500]['raw']['state'])
  postcondition=after[2]==9 and after[41]==1 and end[42]>=3 and end[34]<=9 and end[65]==0
 else:
  postcondition=after[2]==2 and after[34]==before[34]==12 and after[42]==0 and after[44]==0 and after[55]==before[55]
 ok=camera==s['camera_fixed'] and actual==wanted and postcondition
 result={'format':'fdisbull-shadowrun-play-target-check-1','nes_sha256':sha(nes),'nes_receipt_sha256':sha(raw_receipt),'nes_trace_sha256':sha(raw),'original_comparison_sha256':sha(summary_raw),'camera':camera,'fields':['selected_slot','contact','flags_low','marker','backlink_nonzero'],'source':wanted,'target':actual,'linked_combat_started_and_depleted_target' if a.linked_combat else 'linked_shot_refused_ammo_unchanged':postcondition,'passed':ok,'scope':'assisted placement and frozen captured actors; original prepared projection and selector leaves; no ordinary reachability claim'}
 out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));
 if not ok:raise SystemExit(1)
if __name__=='__main__':main()
