#!/usr/bin/env python3
"""Compare party reaction start to an uninterrupted prepared original impact."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine,canonical
from fdisbull.shadowrun_player_reaction import SOURCE,lift_player_reaction
from fdisbull.udl_shadowrun import ROM_SHA256
CORE='27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
def sha(b):return hashlib.sha256(b).hexdigest()
def w(b,n):return int.from_bytes(b[n:n+2],'big')
def l(b,n):return int.from_bytes(b[n:n+4],'big')
def main():
 p=argparse.ArgumentParser()
 for k in ('rom','native','output'):p.add_argument('--'+k,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();root=Path(a.native);rr=(root/'receipt.json').read_bytes();r=json.loads(rr);before=(root/'ram-before.bin').read_bytes();after=(root/'ram-after.bin').read_bytes();tr=(root/'trace.json').read_bytes();steps=json.loads(tr)[0]['steps'];case=r['cases'][0]
 if sha(rom)!=ROM_SHA256 or not r['complete'] or not r['inputs_unchanged'] or r['source_sha256']!=ROM_SHA256 or r['core_sha256']!=CORE or sha(before)!=case['ram_before_sha256'] or sha(after)!=case['ram_after_sha256'] or sha(tr)!=r['trace_sha256'] or case['registers_after']['PC']!=0x14eda:raise ValueError('original impact provenance')
 pcs=[x['pc'] for x in steps];path=[0x36b2,0x14e8a,0x14ed2,0x14ed4,0xaff2,0xb03c];at=-1
 for pc in path:at=pcs.index(pc,at+1)
 actor=before[0x100:0x200];actual=after[0x100:0x200]
 if actor[0x4c]<=actual[0x4c] or not actual[0x4c]:raise ValueError('not a nonlethal HP-changing hit')
 program=lift_player_reaction(rom);m=GameMachine(program,{0:rom});m.set_state({'shadowrun_reaction_kind':w(actor,14),'shadowrun_reaction_heading':w(actor,0x2e),'shadowrun_reaction_flags':actor[0x10],'shadowrun_reaction_flags_low':actor[0x11],'shadowrun_reaction_hp':actual[0x4c],'shadowrun_reaction_max_hp':actual[0x9c], 'shadowrun_reaction_callback':l(actor,0x3a),'shadowrun_reaction_animation':w(actor,0x16),'shadowrun_reaction_accumulator':w(actor,0x1a),'shadowrun_reaction_index':w(actor,0x1e),'shadowrun_reaction_counter':actor[0xce]});m.call('shadowrun_reaction_start');s=m.snapshot()
 got=(s['shadowrun_reaction_callback'],s['shadowrun_reaction_animation'],s['shadowrun_reaction_accumulator'],s['shadowrun_reaction_index'],s['shadowrun_reaction_flags_low'],s['shadowrun_reaction_counter']);expected=(l(actual,0x3a),w(actual,0x16),w(actual,0x1a),w(actual,0x1e),actual[0x11],actual[0xce])
 if not s['shadowrun_reaction_supported'] or got!=expected:raise AssertionError((got,expected))
 result={'status':'passed','cases':1,'rom_sha256':sha(rom),'native_receipt_sha256':sha(rr),'native_trace_sha256':sha(tr),'authoring_sha256':sha(SOURCE.read_bytes()),'program_sha256':sha(canonical(program)),'player_hp_before':actor[0x4c],'player_hp_after':actual[0x4c],'scope':'controlled prepared hostile projectile nonlethal HP-changing hit through original AFF2 reaction; sound hardware disabled; later sprite cadence not established'}
 out=_private_directory(a.output);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
