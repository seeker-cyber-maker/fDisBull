"""Authored navigation contract tests, distinct from original DOSBox receipts."""
import copy,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from test_scene import fixture,terrain
from syndicate_scene import Mission
from agent_map import plan_approach,checksum,ProgressWatch
from original_navigation import NavigationLimits,validate_route,OriginalNavigation,NavigationHeld,read_actor_sample
from original_interactions import RejectedInteraction
from z_provider import SceneBackend
from fdisbull_player import Player

def baseline():
 s=Mission(fixture()).summary();t=terrain();p=plan_approach(s,t,'vehicle-0');return s,t,p

def seal(p):
 p['plan_id']=checksum({k:v for k,v in p.items() if k!='plan_id'});return p

class RoutePreflight(unittest.TestCase):
 def valid(self,p,s=None,t=None):
  ss,tt,_=baseline();return validate_route(p,s or ss,t or tt,NavigationLimits())
 def test_unchanged_plan_admitted(self):
  s,t,p=baseline();a,b,points=self.valid(p,s,t);self.assertEqual(a['id'],'person-0');self.assertEqual(b['id'],'vehicle-0');self.assertEqual(list(points[-1]),p['approach_raw'])
 def test_tampered_identity_refused(self):
  s,t,p=baseline();p['plan_id']='bad'
  with self.assertRaises(RejectedInteraction):self.valid(p,s,t)
 def test_stale_source_refused(self):
  s,t,p=baseline();p['source_state_sha256']='different';seal(p)
  with self.assertRaises(RejectedInteraction):self.valid(p,s,t)
 def test_changed_map_refused(self):
  s,t,p=baseline();p['map_number']=2;seal(p)
  with self.assertRaises(RejectedInteraction):self.valid(p,s,t)
 def test_forged_waypoint_refused_even_with_valid_digest(self):
  s,t,p=baseline();p['waypoints_raw'][1][0]+=1;seal(p)
  with self.assertRaises(RejectedInteraction):self.valid(p,s,t)
 def test_forged_approach_refused(self):
  s,t,p=baseline();p['approach_raw']=p['target_raw'];seal(p)
  with self.assertRaises(RejectedInteraction):self.valid(p,s,t)
 def test_forged_path_cells_refused(self):
  s,t,p=baseline();p['path_cells'][1][0]+=1;seal(p)
  with self.assertRaises(RejectedInteraction):self.valid(p,s,t)
 def test_forged_gate_removal_refused(self):
  s,t,p=baseline();point=p['path_cells'][2];door=next(e for e in s['entities'] if e['category']=='door');door['position_raw']=[point[0]*256+128,point[1]*256+128,256]
  p=plan_approach(s,t,'vehicle-0');self.assertTrue(p['conditional_gates']);p['conditional_gates']=[];seal(p)
  with self.assertRaises(RejectedInteraction):self.valid(p,s,t)
 def test_real_gate_held_before_input(self):
  s,t,p=baseline();point=p['path_cells'][2];door=next(e for e in s['entities'] if e['category']=='door');door['position_raw']=[point[0]*256+128,point[1]*256+128,256];p=plan_approach(s,t,'vehicle-0')
  with self.assertRaisesRegex(RejectedInteraction,'gate'):self.valid(p,s,t)
 def test_open_animation_alone_does_not_grant_gate(self):
  s,t,p=baseline();point=p['path_cells'][2];door=next(e for e in s['entities'] if e['category']=='door');door.update(position_raw=[point[0]*256+128,point[1]*256+128,256],door_state='open');p=plan_approach(s,t,'vehicle-0')
  with self.assertRaisesRegex(RejectedInteraction,'gate'):self.valid(p,s,t)
 def test_target_moved_refused(self):
  s,t,p=baseline();next(e for e in s['entities'] if e['id']=='vehicle-0')['position_raw'][0]+=1
  with self.assertRaises(RejectedInteraction):self.valid(p,s,t)
 def test_actor_moved_one_unit_refused(self):
  s,t,p=baseline();s['entities'][0]['position_raw'][0]+=1
  with self.assertRaises(RejectedInteraction):self.valid(p,s,t)
 def test_active_actor_refused(self):
  s,t,p=baseline();s['entities'][0]['status_raw']=2
  with self.assertRaises(RejectedInteraction):self.valid(p,s,t)
 def test_vehicle_occupant_refused(self):
  s,t,p=baseline();s['entities'][0]['vehicle_membership']={'state':'occupant','vehicle_id':'vehicle-0'}
  with self.assertRaises(RejectedInteraction):self.valid(p,s,t)
 def test_invalid_spatial_graph_refused(self):
  s,t,p=baseline();s['spatial_index']['valid']=False
  with self.assertRaises(RejectedInteraction):self.valid(p,s,t)
 def test_invalid_occupant_graph_refused(self):
  s,t,p=baseline();s['vehicle_occupancy']['valid']=False
  with self.assertRaises(RejectedInteraction):self.valid(p,s,t)
 def test_unsettled_item_refused(self):
  s,t,p=baseline();e=copy.deepcopy(s['entities'][0]);e.update(id='weapon-extra',family='weapon',category='weapon',owner_id='person-0',position_raw=[1000,1000,256]);s['entities'].append(e)
  p=plan_approach(s,t,'vehicle-0')
  with self.assertRaisesRegex(RejectedInteraction,'attachment'):self.valid(p,s,t)
 def test_segment_budget_refused(self):
  s,t,p=baseline()
  with self.assertRaisesRegex(RejectedInteraction,'budget'):validate_route(p,s,t,NavigationLimits(max_segments=1))
 def test_unresolved_floor_refused(self):
  s,t,p=baseline();next(e for e in s['entities'] if e['id']=='vehicle-0')['position_raw'][2]=384;p=plan_approach(s,t,'vehicle-0')
  with self.assertRaises(RejectedInteraction):self.valid(p,s,t)
 def test_plan_is_not_mutated(self):
  s,t,p=baseline();old=copy.deepcopy((s,p));self.valid(p,s,t);self.assertEqual((s,p),old)
 def test_limits_refuse_bool(self):
  with self.assertRaises(ValueError):NavigationLimits(max_segments=True)
 def test_limits_refuse_zero(self):
  with self.assertRaises(ValueError):NavigationLimits(max_total_observations=0)
 def test_limits_refuse_excess(self):
  with self.assertRaises(ValueError):NavigationLimits(max_segments=65)
 def test_limits_refuse_infinite_wall(self):
  with self.assertRaises(ValueError):NavigationLimits(wall_seconds=float('inf'))
 def test_limits_refuse_nan_wall(self):
  with self.assertRaises(ValueError):NavigationLimits(wall_seconds=float('nan'))

class ProfileStateTests(unittest.TestCase):
 def nav(self):
  c=SimpleNamespace(vehicle_interactions=None)
  return c
 def test_missing_source_profile_refused(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):OriginalNavigation(self.nav(),terrain(),Path(d))
 def test_held_route_refuses_before_controller(self):
  n=OriginalNavigation.__new__(OriginalNavigation);n.held=True
  with self.assertRaisesRegex(RejectedInteraction,'held'):n.follow({})
 def test_foreign_run_refused(self):
  c=SimpleNamespace(last_revision=9,cfg={'run_id':'here'});n=OriginalNavigation.__new__(OriginalNavigation);n.c=c;n.held=False;n.profile=SimpleNamespace(_checked_state=lambda _: (fixture(),{}))
  with self.assertRaisesRegex(RejectedInteraction,'run or runtime revision'):n.follow({'observed_run':'elsewhere','runtime_revision':9})
 def test_stale_revision_refused(self):
  c=SimpleNamespace(last_revision=10,cfg={'run_id':'here'});n=OriginalNavigation.__new__(OriginalNavigation);n.c=c;n.held=False;n.profile=SimpleNamespace(_checked_state=lambda _: (fixture(),{}))
  with self.assertRaisesRegex(RejectedInteraction,'run or runtime revision'):n.follow({'observed_run':'here','runtime_revision':9})
 def test_missing_revision_refused(self):
  c=SimpleNamespace(last_revision=10,cfg={'run_id':'here'});n=OriginalNavigation.__new__(OriginalNavigation);n.c=c;n.held=False;n.profile=SimpleNamespace(_checked_state=lambda _: (fixture(),{}))
  with self.assertRaises(RejectedInteraction):n.follow({'observed_run':'here'})
 def test_snapshot_cannot_walk(self):
  b=SceneBackend(snapshot=Mission(fixture()).summary(),terrain=terrain());p=Player(b);r=p.execute_result('walk route to car');self.assertFalse(r['action_sent']);self.assertEqual(r['effects'],'none-confirmed')
 def test_snapshot_keeps_route_description(self):
  b=SceneBackend(snapshot=Mission(fixture()).summary(),terrain=terrain());p=Player(b);r=p.execute_result('examine route to car');self.assertEqual(r['status'],'read');self.assertIn('conditional_model_only',r['outcome']);self.assertFalse(r['action_sent'])
 def test_zero_health_is_not_implicitly_hazard(self):
  s,t,p=baseline();self.assertEqual(s['entities'][0]['health_raw'],0);self.valid=validate_route(p,s,t,NavigationLimits());self.assertTrue(self.valid)

class ProgressInterpretation(unittest.TestCase):
 def sample(self,w,x,y,r):
  return w.observe((x,y,256),revision=r,target_raw=(1000,1000,256),waypoint_raw=(900,1000,256),waypoint_index=1,attachments_settled=True,gate_ready=True)
 def test_moving_away_is_not_zero_motion(self):
  w=ProgressWatch((900,1000,256),(1000,1000,256),stall_limit=3)
  for r,x in enumerate((500,490,480,470),1):out=self.sample(w,x,1000,r)
  self.assertEqual(out,'moving_without_progress_hold');self.assertEqual(w.stationary,0)
 def test_stationary_is_distinct(self):
  w=ProgressWatch((900,1000,256),(1000,1000,256),stall_limit=3)
  for r in range(1,5):out=self.sample(w,500,1000,r)
  self.assertEqual(out,'stalled_replan')
 def test_deviation_never_auto_resets(self):
  w=ProgressWatch((900,1000,256),(1000,1000,256),stall_limit=1)
  self.sample(w,500,1000,1);self.sample(w,490,1000,2)
  self.assertEqual(self.sample(w,600,1000,3),'held_requires_new_plan')
 def test_one_unit_progress_is_progress(self):
  w=ProgressWatch((900,1000,256),(1000,1000,256),stall_limit=1)
  for r,x in enumerate((500,501,502,503),1):out=self.sample(w,x,1000,r)
  self.assertEqual(out,'continue_bounded_observation')

if __name__=='__main__':unittest.main()
