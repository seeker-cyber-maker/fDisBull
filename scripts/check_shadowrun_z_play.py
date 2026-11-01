#!/usr/bin/env python3
"""Exercise live Z inventory and controls on one private prepared GameIL state."""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from fdisbull.shadowrun_city_view import open_runtime
from fdisbull.shadowrun_z import ShadowrunZBackend


def main():
 p=argparse.ArgumentParser();p.add_argument('--rom',required=True);p.add_argument('--snapshot',required=True)
 a=p.parse_args();b=ShadowrunZBackend(open_runtime(a.rom,snapshot=a.snapshot));o=b.observe();i=o['inventory_state']
 if ([x['item_code'] for x in i['slots']] != [2,44,14,16,0,0,0,0] or
     i['weapon'] != {'slot_raw':0,'item_code':2} or i['armor']!=1 or i['ammo']!=12):
  raise AssertionError('prepared inventory did not match source capture')
 def act(verb,target):
  obs=b.observe();return b.act({'verb':verb,'target':target,'item':None,'context_token':obs['context']['token']})
 if act('open-inventory','control.game')['status']!='success':raise AssertionError('menu entry failed')
 if act('go','direction.east')['status']!='success':raise AssertionError('menu selection failed')
 if act('equip','shadowrun.inventory.slot.1')['status']!='success':raise AssertionError('armor toggle failed')
 if b.observe()['inventory_state']['armor']!=0:raise AssertionError('armor readback did not change')
 if act('go','direction.west')['status']!='success':raise AssertionError('weapon selection failed')
 if act('equip','shadowrun.inventory.slot.0')['status']!='success':raise AssertionError('weapon toggle failed')
 i=b.observe()['inventory_state']
 if i['weapon']!={'slot_raw':127,'item_code':0} or i['ammo']!=100:raise AssertionError('weapon readback did not change')
 if act('close-inventory','control.game')['status']!='success':raise AssertionError('menu exit failed')
 if act('target','control.game')['status']!='rejected':raise AssertionError('unexpected target in captured initial view')
 # A separate assisted diagnostic placement follows the bounded target profile.
 c=ShadowrunZBackend(open_runtime(a.rom,snapshot=a.snapshot),policy='assisted')
 def combat_act(verb,target):
  obs=c.observe();return c.act({'verb':verb,'target':target,'item':None,'context_token':obs['context']['token']})
 if combat_act('teleport-recenter','teleport.19200.12544')['status']!='success':raise AssertionError('assisted placement failed')
 if combat_act('wait','wait.30')['status']!='success':raise AssertionError('camera wait failed')
 if combat_act('target','control.game')['status']!='success':raise AssertionError('target cycle failed')
 if c.observe()['combat_state']['target_id']!='shadowrun.capture.5999.actor.ff0500':raise AssertionError('wrong target')
 hp=[];ammo=[]
 for _ in range(3):
  if combat_act('hold-fire','hold-fire.60')['status']!='success':raise AssertionError('bounded firing refused')
  obs=c.observe();npc=next(x for x in obs['captured_entities'] if x['id'].endswith('ff0500'))
  hp.append(npc['hp_current']);ammo.append(obs['inventory_state']['ammo'])
  if npc['hp_byte_4c']!=10:raise AssertionError('captured HP was overwritten')
 if hp!=[6,5,0] or ammo!=[11,10,9]:raise AssertionError(('unexpected combat state',hp,ammo))
 print(json.dumps({'complete':True,'source_sha256':hashlib.sha256(Path(a.rom).read_bytes()).hexdigest(),
  'initial_slot_codes':[2,44,14,16,0,0,0,0],'armor_after':0,'weapon_after':i['weapon'],
  'ammo_raw_after':i['ammo'],'no_target_refused':True,
  'assisted_target':'ff0500','combat_hp_after':hp,'combat_ammo_after':ammo,
  'scope':'prepared shared GameIL model through Z backend; not original-game input parity'}))
if __name__=='__main__':main()
