"""Authored projection and planning tests; no native execution is claimed."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from agent_map import (CandidateTerrain, ProgressWatch, destination_decision,
                       exact_decimal, plan_approach, render_ascii, resolve_overlay_cell)
from syndicate_scene import Mission
from z_provider import SceneBackend
from test_scene import fixture, terrain


def authored_scene():
    return Mission(fixture()).summary()


class ProjectionTests(unittest.TestCase):
    def test_exact_decimal(self):
        self.assertEqual(exact_decimal(23476,256),'91.703125')
        self.assertEqual(exact_decimal(23420,256),'91.484375')
        self.assertEqual(exact_decimal(1,256),'0.00390625')
    def test_float_coordinates_refused(self):
        with self.assertRaises(ValueError):
            destination_decision((1.0,2,3),(1,2,3),attachments_settled=True)
    def test_exact_noop(self):
        self.assertEqual(destination_decision((100,100,128),(100,100,128),attachments_settled=True),'already_at_exact_destination')
    def test_same_tile_is_not_same_destination(self):
        self.assertEqual(destination_decision((100,100,128),(101,100,128),attachments_settled=True),'distinct_destination')
    def test_pending_not_replayed(self):
        self.assertEqual(destination_decision((100,100,128),(101,100,128),attachments_settled=True,action_pending=True),'observe_pending_action')
    def test_attachment_delay_not_replayed(self):
        self.assertEqual(destination_decision((100,100,128),(100,100,128),attachments_settled=False),'observe_unsettled_attachments')
    def test_ascii_is_passive(self):
        scene=authored_scene(); before=json.dumps(scene,sort_keys=True)
        view=render_ascii(scene,terrain(),width=15,height=9)
        self.assertEqual(before,json.dumps(scene,sort_keys=True));self.assertIn('Local map',view['text'])
        self.assertTrue(view['text'].isascii())
    def test_stacked_entities_retained(self):
        scene=authored_scene();extra=copy.deepcopy(scene['entities'][0]);extra['id']='person-1'
        extra['position_raw']=[2690,2690,256];scene['entities'].append(extra)
        view=render_ascii(scene,terrain(),origin=(8*256,8*256),width=8,height=8)
        stack=next(s for s in view['stacks'] if 'person-0' in s['ids'])
        self.assertIn('person-1',stack['ids']);self.assertEqual(view['rows'][2][2],'@')
    def test_quarter_tile_zoom_retains_two_positions(self):
        scene=authored_scene();extra=copy.deepcopy(scene['entities'][0]);extra['id']='person-1'
        extra['position_raw']=[10*256+10,10*256+10,256];scene['entities'].append(extra)
        view=render_ascii(scene,terrain(),origin=(10*256,10*256),width=8,height=8,subdivisions=4)
        entries={e['id']:e for e in view['entities']}
        self.assertNotEqual(entries['person-0']['overlay'],entries['person-1']['overlay'])
        self.assertIn('clearance is NOT inferred',view['text'])
    def test_overlay_resolves_interval_not_point(self):
        view=render_ascii(authored_scene(),terrain(),origin=(2048,2048),width=8,height=8)
        cell=resolve_overlay_cell(view,'r02c03',overlay_id=view['overlay_id'])
        self.assertEqual(cell['x_raw'],[2816,3072]);self.assertEqual(cell['y_raw'],[2560,2816]);self.assertIsNone(cell['exact_destination'])
    def test_stale_overlay_rejected(self):
        view=render_ascii(authored_scene(),terrain())
        with self.assertRaises(ValueError):resolve_overlay_cell(view,'r00c00',overlay_id='stale')
    def test_overlay_bounds_rejected(self):
        view=render_ascii(authored_scene(),terrain(),width=5,height=5)
        with self.assertRaises(ValueError):resolve_overlay_cell(view,'r05c00',overlay_id=view['overlay_id'])
    def test_bad_zoom_rejected(self):
        with self.assertRaises(ValueError):render_ascii(authored_scene(),terrain(),subdivisions=3)
    def test_different_height_not_overlaid(self):
        scene=authored_scene();scene['entities'][1]['position_raw'][2]=512
        view=render_ascii(scene,terrain(),width=80,height=40,layer=2)
        self.assertNotIn(scene['entities'][1]['id'],[r['id'] for r in view['entities']])
    def test_duplicate_ids_rejected(self):
        scene=authored_scene();scene['entities'].append(copy.deepcopy(scene['entities'][0]))
        with self.assertRaises(ValueError):render_ascii(scene,terrain())
    def test_bad_grid_rejected(self):
        with self.assertRaises(ValueError):CandidateTerrain({'dimensions':[2,2,3],'map_number':1,'source_hashes':{},'layers':[{'z':2,'candidate':[[1]]}]})
    def test_stale_route_rejected(self):
        scene=authored_scene();route=plan_approach(scene,terrain(),'vehicle-0');route['source_state_sha256']='different'
        with self.assertRaises(ValueError):render_ascii(scene,terrain(),route=route)


class RouteTests(unittest.TestCase):
    def test_approaches_not_center(self):
        scene=authored_scene();p=plan_approach(scene,terrain(),'vehicle-0')
        self.assertEqual(p['status'],'candidate_requires_validation')
        self.assertNotEqual(p['approach_raw'],p['target_raw']);self.assertFalse(p['boarding_qualified'])
        self.assertEqual(p['start_raw'],scene['entities'][0]['position_raw'])
        for a,b in zip(p['path_cells'],p['path_cells'][1:]):
            self.assertEqual(sum(abs(x-y) for x,y in zip(a,b)),1)
    def test_views_share_plan(self):
        scene=authored_scene();p=plan_approach(scene,terrain(),'vehicle-0');old=copy.deepcopy(p)
        render_ascii(scene,terrain(),route=p);render_ascii(scene,terrain(),route=p,subdivisions=4)
        self.assertEqual(old,p)
    def test_failed_edge_can_be_excluded(self):
        scene=authored_scene();first=plan_approach(scene,terrain(),'vehicle-0')
        edge=tuple(map(tuple,first['path_cells'][:2]))
        second=plan_approach(scene,terrain(),'vehicle-0',blocked_edges=(edge,))
        self.assertEqual(second['status'],'candidate_requires_validation')
        self.assertNotIn(edge,[(tuple(a),tuple(b)) for a,b in zip(second['path_cells'],second['path_cells'][1:])])
        self.assertNotEqual(first['plan_id'],second['plan_id'])
    def test_no_connector_invented(self):
        scene=authored_scene();next(e for e in scene['entities'] if e['id']=='vehicle-0')['position_raw'][2]=384
        p=plan_approach(scene,terrain(),'vehicle-0');self.assertEqual(p['status'],'unresolved_elevation_connector')
    def test_fully_blocked_refuses_route(self):
        scene=authored_scene();blocked=tuple((x,y,2) for x,y in [(9,10),(10,9),(11,10),(10,11)])
        self.assertEqual(plan_approach(scene,terrain(),'vehicle-0',blocked_cells=blocked)['status'],'no_candidate_route')
    def test_gate_is_not_silently_opened(self):
        scene=authored_scene();scene['entities']=[scene['entities'][0],next(e for e in scene['entities'] if e['id']=='vehicle-0'),next(e for e in scene['entities'] if e['category']=='door')]
        actor,car,door=scene['entities'];actor['position_raw']=[128,128,256];car['position_raw']=[4*256+128,128,256];door['position_raw']=[2*256+128,128,256]
        model=CandidateTerrain({'dimensions':[5,1,3],'map_number':1,'source_hashes':{},'layers':[{'z':2,'candidate':[[1]*5]}]})
        p=plan_approach(scene,model,car['id']);self.assertEqual(len(p['conditional_gates']),1)
        self.assertIn('stop before',p['conditional_gates'][0]['condition'])


class ProgressTests(unittest.TestCase):
    def watch(self):return ProgressWatch((1000,1000,256),(1200,1000,256))
    def read(self,w,pos=(500,1000,256),revision=1,**kwargs):
        return w.observe(pos,revision=revision,target_raw=kwargs.pop('target_raw',(1200,1000,256)),
                         waypoint_raw=kwargs.pop('waypoint_raw',(1000,1000,256)),waypoint_index=kwargs.pop('waypoint_index',0),
                         attachments_settled=kwargs.pop('attachments_settled',True),gate_ready=kwargs.pop('gate_ready',True),**kwargs)
    def test_stale_observation_does_not_count(self):
        w=self.watch();self.read(w);self.assertEqual(self.read(w),'obtain_fresh_observation');self.assertEqual(w.stagnant,0)
    def test_bounded_stall(self):
        w=self.watch()
        for revision in range(1,5):r=self.read(w,revision=revision)
        self.assertEqual(r,'stalled_replan');self.assertEqual(self.read(w,revision=5),'held_requires_new_plan')
    def test_oscillation_detected(self):
        w=self.watch()
        for rev,x in enumerate([500,600,500,600],1):r=self.read(w,pos=(x,1000,256),revision=rev)
        self.assertEqual(r,'oscillation_replan')
    def test_target_motion_invalidates(self):
        w=self.watch();self.assertEqual(self.read(w,target_raw=(1201,1000,256)),'target_moved_replan')
    def test_unknown_gate_holds(self):
        self.assertEqual(self.read(self.watch(),gate_ready=False),'gate_unqualified_hold')
    def test_same_tile_not_arrived(self):
        w=self.watch();self.assertEqual(self.read(w,pos=(999,1000,256)),'continue_bounded_observation')
    def test_subtile_progress(self):
        w=self.watch()
        for rev,x in enumerate([990,991,992,993,994],1):
            self.assertEqual(self.read(w,pos=(x,1000,256),revision=rev),'continue_bounded_observation')
        self.assertEqual(w.stagnant,0)
    def test_arrival_attachment_boundary(self):
        w=self.watch();self.assertEqual(self.read(w,pos=(1000,1000,256),attachments_settled=False),'observe_attachment_settlement')
        self.assertEqual(self.read(w,pos=(1000,1000,256),revision=2),'arrived_at_approach')
    def test_detour_uses_waypoint_not_final_distance(self):
        w=self.watch()
        self.read(w,pos=(500,1000,256),waypoint_raw=(400,1000,256))
        self.read(w,pos=(450,1000,256),waypoint_raw=(400,1000,256),revision=2)
        self.assertEqual(w.stagnant,0)
    def test_readiness_not_assumed(self):
        with self.assertRaises(ValueError):self.read(self.watch(),gate_ready=None)
    def test_waypoint_regression_holds(self):
        w=self.watch();self.read(w,waypoint_index=2)
        self.assertEqual(self.read(w,revision=2,waypoint_index=1),'route_regressed_replan')


class ProviderTests(unittest.TestCase):
    def test_read_only_player_routes(self):
        from fdisbull_player import Player
        backend=SceneBackend(snapshot=authored_scene(),terrain=terrain());player=Player(backend)
        self.assertIn('ASCII overlay',player.execute('examine map'))
        self.assertIn('waypoints_raw',player.execute('examine route to car'))
    def test_provider_noop_has_no_calls(self):
        from types import SimpleNamespace
        scene=authored_scene();backend=SceneBackend(controller=SimpleNamespace(cfg={'run_id':'authored'}))
        backend.state=lambda:copy.deepcopy(scene)
        with patch.dict('z_provider.WAYPOINTS',{'same point':(10.5,10.5,2)}):
            result=backend.act({'context_token':backend.token(scene),'verb':'teleport','target':'waypoint-same-point'})
        self.assertEqual(result['effects'],'none-confirmed');self.assertIn('Already',result['message'])


if __name__=='__main__':unittest.main(verbosity=2)
