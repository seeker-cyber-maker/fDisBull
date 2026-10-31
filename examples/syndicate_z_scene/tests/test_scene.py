"""Authored fixtures only: no original game bytes or reconstructed game code."""
import sys,unittest,struct,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from syndicate_scene import *
from z_provider import SceneBackend

def fixture():
 b=bytearray(GAME_SIZE);put16(b,0x1bd28,1)
 def entity(family,slot,x,y,z=2,role=None,previous=0,nxt=0):
  base,stride,_,kind=TABLES[family];at=base+slot*stride;ref=at-ENTITY_ORIGIN
  struct.pack_into('<HHHHH',b,at,nxt,previous,int(x*256),int(y*256),int(z*128))
  b[at+10]=4;b[at+24]=kind
  if role is not None:b[at+28]=role
  put16(b,ROOT_BASE+2*(int(y)*128+int(x)),ref)
  return at,ref
 entity('person',0,10.5,10.5,role=2)
 entity('person',8,12.5,10.5,role=1)
 entity('person',9,11.5,10.5,role=4)
 entity('vehicle',0,14.5,10.5)
 entity('object',0,11.5,12.5);b[TABLES['object'][0]+25]=12
 struct.pack_into('<HHHHH',b,0x1bd36,2,2+8*92,0,0,0)
 return bytes(b)

def terrain():
 nx=20;ny=20;nz=4;head=struct.pack('<III',nx,ny,nz);directory=b''.join(struct.pack('<I',nx*ny*4+4*i) for i in range(nx*ny));payload=bytes([0,1,0,0])*nx*ny
 cls=bytearray(256);cls[1]=5
 return Terrain(head+directory+payload,bytes(cls))

class SceneTests(unittest.TestCase):
 def test_complete_census(self):
  m=Mission(fixture());self.assertTrue(m.graph()['valid']);self.assertEqual(m.graph()['entity_count'],5)
 def test_expected_families_and_nearest(self):
  s=Mission(fixture()).summary();self.assertEqual(s['counts']['police'],1);self.assertEqual(s['nearest']['civilian']['id'],'person-8');self.assertAlmostEqual(s['nearest']['civilian']['distance_xy'],2)
 def test_zero_health_does_not_erase_people(self):self.assertEqual(Mission(fixture()).summary()['counts']['civilian'],1)
 def test_special_target_preserved(self):
  s=Mission(fixture()).summary();e=next(e for e in s['entities'] if e['id']=='person-8');self.assertTrue(e['mission_critical'])
 def test_unknown_role_retained(self):
  b=bytearray(fixture());b[0x8008+8*92+28]=64;s=Mission(bytes(b)).summary();self.assertEqual(s['counts']['person-class-64'],1)
 def test_relocate_empty_cell(self):
  new,_=relocate(fixture(),'person-0',(15*256,15*256,256));g=Mission(new).graph();self.assertTrue(g['valid']);self.assertEqual(g['entity_count'],5)
 def test_relocate_occupied_cell(self):
  new,_=relocate(fixture(),'person-0',(12*256+10,10*256,256));g=Mission(new).graph();self.assertTrue(g['valid']);self.assertEqual(g['chains'][10*128+12],[2,738])
 def test_relocate_out_of_chain(self):
  new,_=relocate(fixture(),'person-0',(12*256+10,10*256,256));back,_=relocate(new,'person-0',(15*256,15*256,256));self.assertTrue(Mission(back).graph()['valid']);self.assertEqual(u16(back,0x8008+8*92+2),0)
 def test_same_cell_preserves_chain(self):
  new,_=relocate(fixture(),'person-0',(10*256+2,10*256+2,256));self.assertEqual(Mission(new).graph()['chains'],Mission(fixture()).graph()['chains'])
 def test_vehicle_rider_refused(self):
  b=bytearray(fixture());put16(b,0x8008+36,23554)
  with self.assertRaises(ValueError):relocate(bytes(b),'person-0',(2560,2560,256))
 def test_other_state_profile_refused(self):
  b=bytearray(fixture());b[0x8008+25]=40
  with self.assertRaises(ValueError):relocate(bytes(b),'person-0',(2560,2560,256))
 def test_existing_movement_target_refused(self):
  b=bytearray(fixture());put16(b,0x8008+46,3000)
  with self.assertRaises(ValueError):relocate(bytes(b),'person-0',(2560,2560,256))
 def test_nonteam_teleport_refused(self):
  with self.assertRaises(ValueError):relocate(fixture(),'person-8',(2560,2560,256))
 def test_edge_wrap_domain_refused(self):
  for p in [(0,2560,256),(32512,2560,256),(2560,24320,256),(2560,2560,-1),(True,2560,256)]:
   with self.assertRaises(ValueError):relocate(fixture(),'person-0',p)
 def test_cycles_rejected(self):
  b=bytearray(fixture());put16(b,0x8008,2)
  self.assertFalse(Mission(bytes(b)).graph()['valid'])
  with self.assertRaises(ValueError):relocate(bytes(b),'person-0',(2560,2560,256))
 def test_wrong_root_rejected(self):
  b=bytearray(fixture());put16(b,6+2*(10*128+10),123)
  self.assertFalse(Mission(bytes(b)).graph()['valid'])
 def test_missing_flagged_entity_rejected(self):
  b=bytearray(fixture());put16(b,6+2*(10*128+10),0)
  with self.assertRaises(ValueError):Mission(bytes(b)).summary()
 def test_bad_extent_rejected(self):
  with self.assertRaises(ValueError):Mission(b'not a game')
 def test_flat_model_connects(self):self.assertEqual(len(terrain().path((2,2,2),(4,2,2))),3)
 def test_height_not_collapsed(self):self.assertIsNone(terrain().path((2,2,2),(2,2,3)))
 def test_terrain_bounds_refused(self):
  t=terrain()
  with self.assertRaises(ValueError):t.column(20,0)
 def test_partial_map_rejected(self):
  with self.assertRaises(ValueError):Terrain(b'\0'*12,b'\0'*256)
 def test_snapshot_has_passive_aliases(self):
  from fdisbull_player import Player
  b=SceneBackend(snapshot=Mission(fixture()).summary(),terrain=terrain());p=Player(b)
  self.assertIn('1 registered police',p.execute('examine police'))
  self.assertIn('person-8',p.execute('examine mission target'))
  self.assertIn('Local map',p.execute('examine map'))
 def test_snapshot_actions_refused(self):
  b=SceneBackend(snapshot=Mission(fixture()).summary());self.assertEqual(b.act({'verb':'teleport','target':'waypoint-car-approach'})['status'],'rejected')
 def test_snapshot_never_certifies_checkpoint(self):
  b=SceneBackend(snapshot=Mission(fixture()).summary());self.assertFalse(b.save()['complete']);self.assertFalse(b.load()['complete'])
 def test_no_los_or_path_promotion(self):
  s=Mission(fixture()).summary();self.assertEqual(s['coverage']['visibility'],'unknown');self.assertIsNone(s['nearest']['civilian']['path_distance'])
 def test_duplicate_entity_category_does_not_duplicate_reference(self):
  s=Mission(fixture()).summary();self.assertEqual(len({e['id'] for e in s['entities']}),len(s['entities']))

if __name__=='__main__':unittest.main(verbosity=2)
