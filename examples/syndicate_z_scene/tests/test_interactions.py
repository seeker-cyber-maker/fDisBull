"""Authored cases only. These do not replace the separately recorded DOSBox runs."""
import copy,struct,sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from syndicate_scene import Mission,TABLES,ENTITY_ORIGIN,put16,DOOR_STATES
from interaction_contracts import door_person_candidate,boarding_distance_gate
from original_interactions import OriginalVehicleInteractions,RejectedInteraction
from z_provider import SceneBackend
from test_scene import fixture,terrain

def occupied_fixture(two=False):
    b=bytearray(fixture());car=TABLES['vehicle'][0];first=TABLES['person'][0]
    put16(b,car+28,2);put16(b,first+36,car-ENTITY_ORIGIN)
    if two:
        # Existing civilian fixture record is used only as an authored occupant.
        second=TABLES['person'][0]+8*92;ref=second-ENTITY_ORIGIN
        put16(b,first+34,ref);put16(b,second+36,2)
    return b

class DoorTests(unittest.TestCase):
    def test_all_four_door_states_preserve_identity_and_count(self):
        for subtype,state in DOOR_STATES.items():
            with self.subTest(subtype=subtype):
                b=bytearray(fixture());b[TABLES['object'][0]+25]=subtype
                s=Mission(bytes(b)).summary();d=next(e for e in s['entities'] if e['id']=='object-0')
                self.assertEqual(s['counts']['door'],1);self.assertEqual(d['door_state'],state)
                self.assertEqual(s['nearest']['door']['id'],'object-0');self.assertEqual(d['traversal'],'unqualified')
    def test_vehicle_subtype_is_not_a_door(self):
        b=bytearray(fixture());b[TABLES['vehicle'][0]+25]=14
        e=next(e for e in Mission(bytes(b)).entities() if e['id']=='vehicle-0')
        self.assertEqual(e['category'],'vehicle');self.assertNotIn('door_state',e)
    def test_person_state_is_not_a_door(self):
        b=bytearray(fixture());b[TABLES['person'][0]+25]=14
        e=Mission(bytes(b)).entities()[0];self.assertEqual(e['category'],'agent');self.assertNotIn('door_state',e)
    def test_unknown_object_is_not_promoted(self):
        b=bytearray(fixture());b[TABLES['object'][0]+25]=16
        s=Mission(bytes(b)).summary();self.assertNotIn('door',s['counts'])
    def test_open_door_player_description(self):
        from fdisbull_player import Player
        b=bytearray(fixture());b[TABLES['object'][0]+25]=14
        p=Player(SceneBackend(snapshot=Mission(bytes(b)).summary(),terrain=terrain()))
        self.assertIn('Door state: open',p.execute('examine door 0'))
        self.assertIn('1 registered door',p.execute('examine gate'))
    def test_asymmetric_x_boundary(self):
        c=(16480,8416,256)
        a=door_person_candidate(c,(16639,8416,256));b=door_person_candidate(c,(16640,8416,256))
        self.assertTrue(a['candidate']);self.assertTrue(b['fine_distance_match']);self.assertFalse(b['root_lookup_match']);self.assertFalse(b['candidate'])
    def test_y_boundary_survives_root_lookup(self):
        self.assertTrue(door_person_candidate((16480,8416,256),(16480,8576,256))['candidate'])
    def test_negative_boundary_and_outside(self):
        c=(16480,8416,256)
        self.assertTrue(door_person_candidate(c,(16320,8416,256))['candidate'])
        self.assertFalse(door_person_candidate(c,(16319,8416,256))['candidate'])
    def test_z_bounds(self):
        c=(16480,8416,256)
        for z,expected in [(0,True),(512,True),(513,False)]:self.assertEqual(door_person_candidate(c,(16480,8416,z))['candidate'],expected)
    def test_person_filters(self):
        c=(16480,8416,256)
        for kw in [{'kind':2},{'excluded':True},{'role_word':0},{'role_word':2,'role_mask':1}]:self.assertFalse(door_person_candidate(c,c,**kw)['candidate'])
    def test_edges_rejected(self):
        with self.assertRaises(ValueError):door_person_candidate((128,128,256),(128,128,256))
    def test_raw_coordinates_required(self):
        for bad in [(1.0,2,3),(True,2,3),(1,2),(-1,2,3)]:
            with self.assertRaises(ValueError):boarding_distance_gate(bad,(1,2,3))

class OccupantTests(unittest.TestCase):
    def test_empty_occupancy(self):
        o=Mission(fixture()).vehicle_occupancy();self.assertTrue(o['valid']);self.assertEqual(o['vehicles']['vehicle-0']['occupants'],[])
    def test_one_occupant(self):
        o=Mission(bytes(occupied_fixture())).vehicle_occupancy();self.assertTrue(o['valid']);self.assertEqual(o['people']['person-0']['vehicle_id'],'vehicle-0')
    def test_second_predecessor_is_person_not_vehicle(self):
        o=Mission(bytes(occupied_fixture(True))).vehicle_occupancy();self.assertTrue(o['valid']);self.assertEqual(o['vehicles']['vehicle-0']['occupants'],['person-0','person-8']);self.assertEqual(o['people']['person-8']['vehicle_id'],'vehicle-0')
    def test_predecessor_mismatch_remains_unknown(self):
        b=occupied_fixture(True);put16(b,0x8008+8*92+36,23554)
        o=Mission(bytes(b)).vehicle_occupancy();self.assertFalse(o['valid']);self.assertEqual(o['people']['person-8']['state'],'unknown');self.assertEqual(o['vehicles']['vehicle-0']['occupants'],[])
    def test_cycle_is_bounded(self):
        b=occupied_fixture();put16(b,0x8008+34,2);o=Mission(bytes(b)).vehicle_occupancy();self.assertFalse(o['valid']);self.assertIn('cycle',o['vehicles']['vehicle-0']['errors'])
    def test_dangling_head(self):
        b=occupied_fixture();put16(b,0xdc08+28,3);self.assertFalse(Mission(bytes(b)).vehicle_occupancy()['valid'])
    def test_nonperson_head(self):
        b=occupied_fixture();put16(b,0xdc08+28,0xdc08-ENTITY_ORIGIN);self.assertFalse(Mission(bytes(b)).vehicle_occupancy()['valid'])
    def test_orphan_predecessor_is_not_direct_vehicle(self):
        b=bytearray(fixture());put16(b,0x8008+36,23554);o=Mission(bytes(b)).vehicle_occupancy();self.assertFalse(o['valid']);self.assertEqual(o['people']['person-0']['state'],'unknown')
    def test_duplicate_occupant_rejected(self):
        b=occupied_fixture();other=0xdc08+42;b[other+24]=2;put16(b,other+28,2)
        o=Mission(bytes(b)).vehicle_occupancy();self.assertFalse(o['valid']);self.assertEqual(o['people']['person-0']['state'],'unknown')
    def test_legacy_raw_refs_are_not_rewritten(self):
        b=occupied_fixture(True);s=Mission(bytes(b)).summary();p=next(e for e in s['entities'] if e['id']=='person-8')
        self.assertEqual(p['vehicle_refs'][0],2);self.assertEqual(p['vehicle_membership']['vehicle_id'],'vehicle-0')
    def test_occupancy_is_read_only(self):
        b=bytes(occupied_fixture(True));before=b[:];Mission(b).vehicle_occupancy();self.assertEqual(b,before)
    def test_cell_graph_is_separate(self):
        b=occupied_fixture(True);self.assertTrue(Mission(bytes(b)).graph()['valid']);self.assertTrue(Mission(bytes(b)).vehicle_occupancy()['valid'])
    def test_old_snapshot_does_not_invent_new_fields(self):
        s=Mission(fixture()).summary()
        for e in s['entities']:e.pop('vehicle_membership',None);e.pop('occupancy',None)
        p=SceneBackend(snapshot=s).observe();text=next(o['description'] for o in p['objects'] if o['id']=='vehicle-0');self.assertIn('unqualified legacy snapshot',text)

class DistanceAndAdmissionTests(unittest.TestCase):
    def test_xy_strict(self):
        self.assertTrue(boarding_distance_gate((1000,1000,256),(1127,1127,256))['distance_gate'])
        self.assertFalse(boarding_distance_gate((1000,1000,256),(1128,1000,256))['distance_gate'])
    def test_z_inclusive(self):
        self.assertTrue(boarding_distance_gate((1000,1000,256),(1000,1000,384))['distance_gate'])
        self.assertFalse(boarding_distance_gate((1000,1000,256),(1000,1000,385))['distance_gate'])
    def test_not_euclidean(self):
        # Diagonal distance exceeds 128 Euclidean units but each component is <128.
        self.assertTrue(boarding_distance_gate((1000,1000,256),(1100,1100,256))['distance_gate'])
    def ready_scene(self):
        b=bytearray(fixture());b[0xdc08+25]=13;return Mission(bytes(b)).summary()
    def profile(self,scene):
        p=OriginalVehicleInteractions.__new__(OriginalVehicleInteractions)
        p.controller=SimpleNamespace();p._checked_state=lambda expected:(b'',copy.deepcopy(scene))
        return p
    def test_far_board_refused_before_input(self):
        with self.assertRaisesRegex(RejectedInteraction,'nearby approach'):self.profile(self.ready_scene()).perform('x','person-0','vehicle-0','board')
    def test_unoccupied_exit_refused_before_input(self):
        with self.assertRaisesRegex(RejectedInteraction,'not a qualified occupant'):self.profile(self.ready_scene()).perform('x','person-0','vehicle-0','exit')
    def test_repeated_board_is_noop(self):
        b=occupied_fixture();b[0xdc08+25]=13;s=Mission(bytes(b)).summary()
        r=self.profile(s).perform('x','person-0','vehicle-0','board');self.assertEqual(r['writes'],0);self.assertEqual(r['effects'],'none-confirmed')
    def test_unqualified_actor_refused(self):
        with self.assertRaises(RejectedInteraction):self.profile(Mission(fixture()).summary()).perform('x','person-8','vehicle-0','board')
    def test_unqualified_vehicle_subtype_refused(self):
        with self.assertRaises(RejectedInteraction):self.profile(Mission(fixture()).summary()).perform('x','person-0','vehicle-0','board')
    def test_no_live_profile_means_no_board_verb(self):
        b=SceneBackend(snapshot=Mission(fixture()).summary());o=b.observe();v=next(x for x in o['objects'] if x['id']=='vehicle-0');self.assertNotIn('board',v['verbs'])
    def test_offline_board_never_dispatches(self):
        from fdisbull_player import Player
        p=Player(SceneBackend(snapshot=Mission(fixture()).summary()));r=p.execute_result('board car');self.assertFalse(r['action_sent'])


class FrameBoundaryTests(unittest.TestCase):
    def profile(self,*,foreign=False,wrong_pc=False,changed=False,cleanup_error='BREAKPOINT_NOT_FOUND'):
        from syndicate_scene import digest
        events=[];payload=b'authored-boundary-fixture'
        def rpc(method,args=None):
            events.append((method,args))
            if method=='session.status':return {'session_id':'foreign' if foreign else 'owned'}
            if method=='breakpoints.create':return {'breakpoint_id':'authored-once'}
            if method=='breakpoints.delete':
                if cleanup_error:raise RuntimeError(cleanup_error)
                return {'removed':True}
            raise AssertionError(method)
        def call(op,args=None):
            events.append((op,args))
            if op=='run':return {'outcome':'breakpoint','guest_elapsed_ms':40}
            if op=='regs':return {'cpu_mode':'protected','segments':{'cs':'0x0158','ds':'0x0160'},'instruction_pointer':hex(0 if wrong_pc else 0x2d610+0x100000)}
            raise AssertionError(op)
        c=SimpleNamespace(cfg={'session_id':'owned','cs':'0x0158','ds':'0x0160'},rpc=rpc,call=call,
                          read=lambda *_:b'changed' if changed else payload,address=lambda p:p+0x100000)
        p=OriginalVehicleInteractions.__new__(OriginalVehicleInteractions);p.controller=c
        p.windows=[{'preferred':0x2d610,'length':len(payload),'sha256':digest(payload)}]
        return p,events
    def test_one_shot_cleanup_not_a_target_failure(self):
        p,e=self.profile();self.assertEqual(p.advance_to_frame()['outcome'],'breakpoint')
        self.assertFalse(any('write' in name for name,_ in e))
    def test_wrong_return_boundary_rejected(self):
        p,e=self.profile(wrong_pc=True)
        with self.assertRaisesRegex(RuntimeError,'boundary not reached'):p.advance_to_frame()
    def test_foreign_session_rejected_without_run(self):
        p,e=self.profile(foreign=True)
        with self.assertRaisesRegex(RuntimeError,'Foreign'):p.advance_to_frame()
        self.assertFalse(any(name=='run' for name,_ in e))
    def test_changed_code_rejected_without_run(self):
        p,e=self.profile(changed=True)
        with self.assertRaisesRegex(RuntimeError,'Changed'):p.advance_to_frame()
        self.assertFalse(any(name=='run' for name,_ in e))
    def test_unrelated_cleanup_error_not_hidden(self):
        p,e=self.profile(cleanup_error='CONNECTION_LOST')
        with self.assertRaisesRegex(RuntimeError,'CONNECTION_LOST'):p.advance_to_frame()

if __name__=='__main__':unittest.main(verbosity=2)
