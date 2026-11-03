#!/usr/bin/env python3
"""Verify a receipt-bound, assisted original B-input targeting observation."""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.console_udc import _private_directory
from fdisbull.game_il import GameMachine, canonical
from fdisbull.shadowrun_replay import _source_capture
from fdisbull.shadowrun_targeting import lift_targeting
from fdisbull.shadowrun_world import SOURCE_SHA256

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for name in ('rom','run','output'):p.add_argument('--'+name,required=True)
 a=p.parse_args();rom=Path(a.rom).read_bytes();run=Path(a.run).resolve();program=lift_targeting(rom)
 receipt_raw=(run/'native/receipt.json').read_bytes();receipt=json.loads(receipt_raw)
 expected_patches=[(256,'004b'),(260,'0032'),(56774,'8042'),(56776,'002b'),(56584,'18ff'),(56586,'9800'),(56588,'18ff'),(56590,'9800'),(57144,'8042'),(57142,'002b')]
 actual_patches=[(q.get('offset'),q.get('data_hex')) for q in receipt.get('patches',[]) if q.get('frame')==6000 and q.get('memory_id')==2]
 if (receipt.get('memory_injection_mode')!='assisted state injection' or len(receipt.get('patches',[]))!=10 or actual_patches!=expected_patches or
     not any(x.get('start')==6001 and x.get('end')==6003 and x.get('buttons')==['B'] for x in receipt.get('inputs',[]))):
  raise ValueError('expected assisted player/camera patch and B input were not established')
 identities={};states={}
 for frame in (5999,6000,6001):
  ident,arrays,_=_source_capture(run/f'native/scene-{frame:06d}',SOURCE_SHA256)
  identities[frame]=ident
  raw=arrays['ram'];states[frame]=bytes(raw[i^1] for i in range(len(raw)))
 pre,mid,post=(states[i] for i in (5999,6000,6001))
 w=lambda data,n:int.from_bytes(data[n:n+2],'big')
 l=lambda data,n:int.from_bytes(data[n:n+4],'big')
 if not (l(pre,0x1a2)==0 and l(mid,0x1a2)==0 and l(post,0x1a2)==0xff0500 and
         w(mid,0xdd22)==0 and w(post,0xdd22)&0x1010==0x1010 and
         w(mid,0x50c)==271 and w(post,0x50c)==268 and
         post[0x511]&16 and l(post,0x5ac)==0xff0100 and post[0x143]==0):
  raise AssertionError('expected B dispatch observation differs')
 def actors(data):return [data[0x400+i*256:0x500+i*256] for i in range(7)]
 rows=actors(mid); model=GameMachine(program)
 word=lambda row,offset:int.from_bytes(row[offset:offset+2],'big')
 model.set_state({'shadowrun_target_x':[word(x,0) for x in rows],
  'shadowrun_target_y':[word(x,4) for x in rows],'shadowrun_target_height':[word(x,8) for x in rows],
  'shadowrun_target_index':[word(x,0x3e) for x in rows], 'shadowrun_target_contact':[word(x,0x0c) for x in rows],
  'shadowrun_target_flags':[x[0x10] for x in rows], 'shadowrun_target_flags_low':[x[0x11] for x in rows],
  'shadowrun_target_flags_b0':[x[0xb0] for x in rows], 'shadowrun_target_item':mid[0x157],
  'shadowrun_target_equipped_slot':mid[0x156], 'shadowrun_target_player_43':mid[0x143]})
 model.call('shadowrun_target_cycle');s=model.snapshot()
 if not (s['shadowrun_target_supported']==1 and s['shadowrun_target_result']==1 and s['shadowrun_target_selected']==1 and
         s['shadowrun_target_flags_low'][1]==post[0x511] and s['shadowrun_target_backlink'][1]==1 and
         s['shadowrun_target_player_43']==post[0x143]):raise AssertionError('selector and B-input observed fields differ')
 # Contact is refreshed by the original frame, after NPC and camera movement;
 # compare the projection separately at the actual post-frame coordinates.
 postrows=actors(post)
 model.set_state({'shadowrun_camera_x':w(post,0xddc6),'shadowrun_camera_y':w(post,0xddc8),
  'shadowrun_target_x':[word(x,0) for x in postrows], 'shadowrun_target_y':[word(x,4) for x in postrows],
  'shadowrun_target_height':[word(x,8) for x in postrows], 'shadowrun_target_flags':[x[0x10] for x in postrows]})
 model.call('shadowrun_target_refresh');projection=model.snapshot()['shadowrun_target_contact']
 if any(projection[i]!=word(row,0xc) for i,row in enumerate(postrows) if row[0x10]&1):raise AssertionError('post-frame contact projection differs')
 result={'format':'fdisbull-shadowrun-original-b-target-check-1','complete':True,
  'rom_sha256':sha(rom),'core_sha256':receipt['core_sha256'],'native_receipt_sha256':sha(receipt_raw),
  'capture_receipt_sha256':identities[6001]['capture_json_sha256'],'frame_ram_sha256':{str(i):identities[i]['snapshot_arrays']['ram']['sha256'] for i in identities},
  'program_sha256':sha(canonical(program)),'assistance':'player/camera fields injected at frame 6000; no target fields injected',
  'input':{'button':'B','start':6001,'end':6003,'source_pad_word':w(post,0xdd22)},
  'pre_target':l(mid,0x1a2),'post_target':l(post,0x1a2),'matched_selected_slot':1,
  'contacts_before_and_after':[w(mid,0x50c),w(post,0x50c)], 'post_camera':[w(post,0xddc6),w(post,0xddc8)],
  'flag_low':post[0x511],'backlink':l(post,0x5ac),'player_field_43':post[0x143],
  'marker_immediate_model':s['shadowrun_target_marker'][1],'marker_observed_post_frame':w(post,0x5a6),
  'marker_note':'different observation phases; intervening original frame effects not attributed by this check',
  'scope':'assisted prepared original run: B input and selected target fields; bounded selector and post-frame projection comparison; not NPC AI parity'}
 out=_private_directory(a.output);out.mkdir(mode=0o700);(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
