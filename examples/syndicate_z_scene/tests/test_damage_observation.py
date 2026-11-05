"""Authored record fixtures only; no original executable or native execution."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from damage_observation import (RecordedDamageBackend, contextual_candidates,
                                validate_recorded_witness, PHASES)
from syndicate_scene import Mission
from test_scene import fixture


def sample():
    scene = Mission(fixture()).summary()
    scene.update(observed_run='authored-run', source_main_sha256='a' * 64)
    entities = {e['id']: e for e in scene['entities']}
    entities['person-0']['health_raw'] = 7
    # The authored weapon need not be an original asset; this is a record contract.
    scene['entities'].append({'id': 'authored-weapon', 'family': 'weapon', 'category': 'weapon',
                              'position_raw': [2944, 2688, 256]})
    event = {'schema': 'syndicate-recorded-damage-1', 'main_sha256': 'a' * 64,
             'run_id': 'authored-run', 'snapshot_sha256': scene['source_state_sha256'],
             'victim_position_raw': entities['person-0']['position_raw'],
             'attribution_scope': 'same-checkpoint-native-replay',
             'interventions': {'health_writes': 0, 'code_edits': 0, 'register_edits': 0},
             'weapon_label': {'type': 42, 'name': 'Authored weapon', 'source_sha256': 'a' * 64,
                              'consumer_window_sha256': 'c' * 64},
             'events': [
                 {'phase': PHASES[0], 'owner_id': 'person-9', 'owner_ref': 830,
                  'weapon_id': 'authored-weapon', 'weapon_type': 42, 'ammo_before': 6,
                  'args': {'source_ref': 830}},
                 {'phase': PHASES[1], 'source_ref_in_ax': 830, 'old_source_ref': 830,
                  'effect_id': 'authored-effect'},
                 {'phase': PHASES[2], 'source_ref': 830, 'source_id': 'person-9',
                  'effect_id': 'authored-effect'},
                 {'phase': PHASES[3], 'weapon_id': 'authored-weapon', 'ammo_after': 5},
                 {'phase': PHASES[4], 'effect_id': 'authored-effect'},
                 {'phase': PHASES[5], 'effect_id': 'authored-effect', 'source_ref': 830,
                  'victim_id': 'person-0', 'health_before': 8, 'health_value_in_ax': 7},
                 {'phase': PHASES[6], 'victim_id': 'person-0', 'health_after': 7},
                 {'phase': PHASES[7], 'returned_id': 'person-0'},
             ]}
    return scene, event


class DamageObservationTests(unittest.TestCase):
    def setUp(self): self.scene, self.event = sample()
    def rejects(self):
        with self.assertRaises((ValueError, KeyError)):
            validate_recorded_witness(self.scene, self.event)
    def test_consistent_chain(self):
        self.assertEqual(validate_recorded_witness(self.scene, self.event)['damage_raw'], 1)
    def test_unchanged_owner_write_is_allowed(self):
        self.assertEqual(validate_recorded_witness(self.scene, self.event)['shooter_id'], 'person-9')
    def test_schema(self): self.event['schema'] = 'unknown'; self.rejects()
    def test_source_hash(self): self.event['main_sha256'] = 'b' * 64; self.rejects()
    def test_snapshot_hash(self): self.event['snapshot_sha256'] = 'b' * 64; self.rejects()
    def test_run(self): self.event['run_id'] = 'other'; self.rejects()
    def test_missing_run(self): self.scene.pop('observed_run'); self.rejects()
    def test_nearest_only_is_not_causal(self):
        self.event['attribution_scope'] = 'nearest-entity'; self.rejects()
    def test_health_patch_is_not_observation(self):
        self.event['interventions']['health_writes'] = 1; self.rejects()
    def test_missing_phase(self): self.event['events'].pop(1); self.rejects()
    def test_reordered_phase(self): self.event['events'][1:3] = self.event['events'][2:0:-1]; self.rejects()
    def test_owner_mismatch(self): self.event['events'][2]['source_ref'] += 1; self.rejects()
    def test_owner_id_mismatch(self): self.event['events'][2]['source_id'] = 'person-8'; self.rejects()
    def test_effect_mismatch(self): self.event['events'][4]['effect_id'] = 'other'; self.rejects()
    def test_victim_mismatch(self): self.event['events'][6]['victim_id'] = 'person-8'; self.rejects()
    def test_return_mismatch(self): self.event['events'][7]['returned_id'] = None; self.rejects()
    def test_ammo_mismatch(self): self.event['events'][3]['ammo_after'] = 6; self.rejects()
    def test_register_health_mismatch(self): self.event['events'][5]['health_value_in_ax'] = 8; self.rejects()
    def test_snapshot_health_mismatch(self): self.scene['entities'][0]['health_raw'] = 6; self.rejects()
    def test_position_mismatch(self): self.event['victim_position_raw'] = [1, 2, 3]; self.rejects()
    def test_rounding_refused(self): self.event['victim_position_raw'] = [10.5, 10.5, 2]; self.rejects()
    def test_unbound_name(self): self.event['weapon_label']['source_sha256'] = 'b' * 64; self.rejects()
    def test_wrong_weapon_type(self): self.event['weapon_label']['type'] = 41; self.rejects()
    def test_duplicate_entities(self): self.scene['entities'].append(copy.deepcopy(self.scene['entities'][0])); self.rejects()
    def test_candidates_are_only_candidates(self):
        candidates = contextual_candidates(self.scene, 'person-0')
        self.assertTrue(candidates); self.assertEqual({e['causation'] for e in candidates}, {'unqualified'})
    def test_different_elevation_retained(self):
        self.scene['entities'][1]['position_raw'][2] += 128
        byid = {e['id']: e for e in contextual_candidates(self.scene, 'person-0')}
        self.assertEqual(byid[self.scene['entities'][1]['id']]['delta_z_raw'], 128)
    def test_player_passive_damage_read(self):
        from fdisbull_player import Player
        backend = RecordedDamageBackend(self.scene, self.event)
        result = Player(backend).execute_result('examine last damage')
        self.assertIn('Authored weapon', result['outcome']); self.assertFalse(result['action_sent'])
    def test_no_actions(self):
        backend = RecordedDamageBackend(self.scene, self.event)
        self.assertEqual(backend.act({'verb': 'attack'})['effects'], 'none-confirmed')
    def test_snapshot_frozen(self):
        backend = RecordedDamageBackend(self.scene, self.event)
        before = backend.observe(); self.event['events'][0]['owner_id'] = 'changed'
        self.scene['entities'][0]['health_raw'] = -1
        self.assertEqual(before, backend.observe())
    def test_observation_copy(self):
        backend = RecordedDamageBackend(self.scene, self.event)
        exposed = backend.observe(); exposed['objects'].clear()
        self.assertTrue(backend.observe()['objects'])

if __name__ == '__main__': unittest.main(verbosity=2)
