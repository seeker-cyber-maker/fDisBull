"""Authored policy/invariant tests; no original target or native rewind runs."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parents[4] / 'examples' / 'syndicate_z_scene' / 'tools'))
from mixed_time_study import cells, compose_fixture, fingerprint, fixture_pair, validate
from world_history import WorldHistory


class MixedTimeTests(unittest.TestCase):
    def setUp(self):
        self.past, self.now = fixture_pair()

    def plan(self, requests=None, current=None, token=None):
        current = self.now if current is None else current
        return compose_fixture(current, requests if requests is not None else
                               [{'actor':'a','past':self.past}],
                               expected_current=token or fingerprint(current))

    def test_actor_moves_back_world_tick_stays_current(self):
        s=self.plan()['candidate'];self.assertEqual(s['actors']['a']['raw'],self.past['actors']['a']['raw'])
        self.assertEqual(s['tick'],120)
    def test_health_restored_without_refunding_guard_ammo(self):
        s=self.plan()['candidate'];self.assertEqual(s['actors']['a']['health'],16);self.assertEqual(s['guard_ammo'],190)
    def test_rng_preserved_without_an_extra_draw(self):
        self.assertEqual(self.plan()['candidate']['rng'],self.now['rng'])
    def test_current_projectiles_preserved(self):
        self.assertEqual(self.plan()['candidate']['projectiles'],self.now['projectiles'])
    def test_current_door_state_preserved(self):
        self.assertEqual(self.plan()['candidate']['doors'],self.now['doors'])
    def test_other_actor_stays_at_current_position(self):
        self.assertEqual(self.plan()['candidate']['actors']['b'],self.now['actors']['b'])
    def test_held_item_follows_without_refunding_its_ammo(self):
        s=self.plan()['candidate'];self.assertEqual(s['items']['w']['raw'],s['actors']['a']['raw'])
        self.assertEqual(s['items']['w']['ammo'],10)
    def test_spatial_index_rebuilt_from_mixed_poses(self):
        s=self.plan()['candidate'];self.assertEqual(s['spatial'],{'1,1,2':['a'],'4,4,2':['b']})
        self.assertNotEqual(s['spatial'],self.past['spatial'])
    def test_inputs_immutable(self):
        a,b=deepcopy(self.past),deepcopy(self.now);self.plan();self.assertEqual(a,self.past);self.assertEqual(b,self.now)
    def test_return_mutation_does_not_alias_inputs(self):
        p=self.plan();p['candidate']['actors']['a']['raw'][0]=999;self.assertEqual(self.past['actors']['a']['raw'][0],256)
    def test_new_epoch_invalidates_old_observation(self):
        s=self.plan()['candidate'];self.assertEqual(s['epoch'],self.now['epoch']+1)
        self.assertEqual(s['revision'],self.now['revision']+1);self.assertNotEqual(fingerprint(s),fingerprint(self.now))
    def test_equal_values_still_get_new_epoch(self):
        s=self.plan([{'actor':'a','past':deepcopy(self.now)}])['candidate']
        self.assertEqual(s['actors'],self.now['actors']);self.assertEqual(s['epoch'],1)
    def test_candidate_does_not_claim_resume_or_native_execution(self):
        r=self.plan();self.assertFalse(r['resume_safe']);self.assertFalse(r['execution_allowed'])
        self.assertFalse(r['native_execution']);self.assertFalse(r['geometry_qualified'])
    def test_stale_snapshot_refused(self):
        token=fingerprint(self.now);self.now['guard_ammo']-=1
        with self.assertRaisesRegex(ValueError,'Stale'):self.plan(token=token)
    def test_source_session_and_lineage_mismatch_refused(self):
        for key in ('source','session','lineage'):
            past=deepcopy(self.past);past[key]='another'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'Mismatched'):
                self.plan([{'actor':'a','past':past}])
    def test_reused_actor_refused(self):
        self.past['actors']['a']['generation']=0
        with self.assertRaisesRegex(ValueError,'slot was reused'):self.plan()
    def test_reused_item_refused(self):
        self.past['items']['w']['generation']=0
        with self.assertRaisesRegex(ValueError,'slot was reused'):self.plan()
    def test_changed_inventory_refused_without_duplication(self):
        self.now['actors']['a']['items']=[];self.now['items']['w']['owner']=None
        with self.assertRaisesRegex(ValueError,'ownership changed'):self.plan()
    def test_vehicle_closure_refused(self):
        self.now['actors']['a']['vehicle']='car'
        with self.assertRaisesRegex(ValueError,'closure'):self.plan()
    def test_pending_injury_closure_refused(self):
        self.now['actors']['a']['pending_conditions']=['burning']
        with self.assertRaisesRegex(ValueError,'closure'):self.plan()
    def test_terminal_state_refused(self):
        self.now['actors']['a']['health']=-1
        with self.assertRaisesRegex(ValueError,'Terminal'):self.plan()
    def test_current_obstruction_refused(self):
        self.now['blocked_raw']=[self.past['actors']['a']['raw'][:]]
        with self.assertRaisesRegex(ValueError,'blocked'):self.plan()
    def test_broken_spatial_index_refused(self):
        self.now['spatial']=self.past['spatial']
        with self.assertRaisesRegex(ValueError,'spatial'):self.plan()
    def test_unsettled_attachment_refused(self):
        self.now['items']['w']['raw']=[1,2,3]
        with self.assertRaisesRegex(ValueError,'Unsettled'):self.plan()
    def test_future_checkpoint_refused(self):
        self.past['tick']=121
        with self.assertRaisesRegex(ValueError,'Future'):self.plan()
    def test_batch_uses_one_current_base_and_epoch(self):
        r=self.plan([{'actor':'a','past':self.past},{'actor':'b','past':self.past}])
        self.assertEqual(r['candidate']['spatial'],self.past['spatial'])
        self.assertEqual(r['candidate']['epoch'],1);self.assertEqual(r['candidate']['tick'],120)
    def test_batch_duplicate_actor_refused(self):
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            self.plan([{'actor':'a','past':self.past}]*2)
    def test_late_invalid_request_changes_nothing(self):
        before=deepcopy(self.now)
        with self.assertRaisesRegex(ValueError,'Missing actor'):
            self.plan([{'actor':'a','past':self.past},{'actor':'missing','past':self.past}])
        self.assertEqual(before,self.now)
    def test_invalid_batch_refused(self):
        for requests in ([],[{'actor':'a'}],[{'actor':'a','past':self.past}]*65):
            with self.subTest(requests=len(requests)),self.assertRaises(ValueError):self.plan(requests)
    def test_naive_historical_index_is_detectably_wrong(self):
        wrong=deepcopy(self.now);wrong['actors']['a']['raw']=self.past['actors']['a']['raw'][:]
        wrong['items']['w']['raw']=wrong['actors']['a']['raw'][:];wrong['spatial']=deepcopy(self.past['spatial'])
        with self.assertRaisesRegex(ValueError,'spatial'):validate(wrong)
    def test_journal_retains_hit_intervention_and_repeated_hit(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'journal.sqlite'
            with WorldHistory(path) as h:
                h.stream('live',metadata={'fixture':True})
                hit={'kind':'damage','guest_tick':120,'victim_id':'a','health_before':16,'health_after':15,'amount':1}
                first=h.append('live','recipient','hit-1',hit)
                mixed=self.plan()
                h.stream('mixed',metadata={'policy':'authored-actor-rewind','current_parent':'now',
                                          'historical_sources':mixed['historical_sources']},
                         parent={'stream':'live','through_seq':first['seq']})
                change=h.append('mixed','orchestrator','mix-1',{'kind':'state-intervention','guest_tick':120,
                           'subject':'a','historical_snapshot':'past','world_clock_preserved':True})
                second=h.append('mixed','recipient','hit-1',hit)
                self.assertNotEqual(first['id'],second['id']);self.assertEqual(h.high_watermark,3)
                self.assertEqual(h.get(first['id'])['amount'],1)
                self.assertEqual(len(h.summarize()['groups']),3)
                self.assertEqual(h.recent(notices_only=True)[0]['id'],change['id'])
                self.assertIsNone(h.get(change['id'],perspective='player'))
            with WorldHistory(path) as h:
                self.assertEqual(h.high_watermark,3)
                self.assertEqual(h.get(first['id'])['guest_tick'],h.get(second['id'])['guest_tick'])
    def test_read_only_history_cursor_does_not_rewind_world(self):
        before=deepcopy(self.now)
        with tempfile.TemporaryDirectory() as d, WorldHistory(Path(d)/'h.sqlite') as h:
            h.stream('s',metadata={})
            old=h.append('s','p','old',{'kind':'notice','guest_tick':100})
            h.append('s','p','new',{'kind':'notice','guest_tick':120})
            self.assertEqual(h.get(old['id'])['guest_tick'],100)
            self.assertEqual(self.now,before);self.assertEqual(h.high_watermark,2)


if __name__=='__main__':unittest.main(verbosity=2)
