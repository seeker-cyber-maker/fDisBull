"""Focused contracts for the Z envelope, checkpoints, and declared comparator.

These tests execute only the portable UIL model. The historical native-observation
comparison is omitted because native receipts are outside this example.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from z_harness_study import ACTION, CLOCK_UNIT, ZHarnessStudy, validate_scene

ROOT = Path(__file__).resolve().parent


def scene():
    return json.loads((ROOT / 'examples/calendar_scene.json').read_text())


def advance(harness, token=None):
    return harness.act({'action': ACTION, 'context_token': token or harness.observe()['context_token']})


class HarnessContracts(unittest.TestCase):
    def test_named_action_updates_authoritative_state_and_public_projection(self):
        harness = ZHarnessStudy(scene())
        before = harness.observe()
        self.assertEqual(before['values'], {'turn': 65535, 'year': -20})
        after = advance(harness)
        self.assertEqual(after['status'], 'complete')
        self.assertEqual(after['observation']['values'], {'turn': 0, 'year': 1})
        self.assertEqual(after['observation']['clock'], {'unit': CLOCK_UNIT, 'position': 1})
        self.assertEqual(harness.private_state(), [0, 1, 0, 0, 2, 65534, 0, 65534, 246, 65524, 20, 20])
        self.assertNotEqual(before['context_token'], after['observation']['context_token'])
        public = json.dumps(after['observation'])
        for private_name in ('source_evidence', 'DS:', 'eight_words', 'required_slots', 'state'):
            self.assertNotIn(private_name, public)


    def test_checkpoints_restore_hidden_state_and_invalidate_old_context(self):
        harness = ZHarnessStudy(scene())
        initial = harness.private_state()
        original_token = harness.observe()['context_token']
        saved = harness.checkpoint()
        advance(harness)
        self.assertEqual(harness.restore(saved)['status'], 'restored')
        self.assertEqual(harness.private_state(), initial)
        restored_token = harness.observe()['context_token']
        self.assertNotEqual(original_token, restored_token)
        refused = advance(harness, original_token)
        self.assertEqual((refused['status'], refused['reason']), ('refused', 'stale_context'))
        self.assertEqual(harness.private_state(), initial)

    def test_rewind_and_new_action_preserve_both_branches(self):
        harness = ZHarnessStudy(scene())
        start = harness.checkpoint()
        advance(harness)
        first = harness.checkpoint()
        first_state = harness.private_state()
        harness.rewind_one()
        advance(harness)
        second = harness.checkpoint()
        self.assertNotEqual(first['snapshot'], second['snapshot'])
        self.assertEqual(harness.private_state(), first_state)
        nodes = harness.private_history()['nodes']
        self.assertEqual(len(nodes), 3)
        self.assertEqual([node['parent'] for node in nodes[1:]], [start['snapshot']] * 2)
        self.assertEqual(harness.last_change(4)['after_snapshot'], second['snapshot'])
        harness.restore(first)
        self.assertEqual(harness.last_change(4)['after_snapshot'], first['snapshot'])
        harness.rewind_one()
        self.assertEqual(harness.rewind_one()['reason'], 'no_recorded_parent')

    def test_history_capacity_counts_retained_branches_and_never_advances_on_refusal(self):
        document = scene()
        document['max_history'] = 3
        harness = ZHarnessStudy(document)
        start = harness.checkpoint()
        advance(harness)
        harness.restore(start)
        advance(harness)
        harness.restore(start)
        before = harness.observe()
        refused = advance(harness)
        self.assertEqual(refused['reason'], 'history_capacity')
        self.assertEqual(harness.observe(), before)
        self.assertEqual(harness.private_history()['snapshots_used'], 3)

    def test_modeled_refusal_keeps_committed_state_and_history(self):
        document = scene()
        constants = document['uil']['program']['constants']
        false_slot = len(constants)
        constants.append({'type': 'bool'})
        document['uil']['bindings']['constants'].append(False)
        document['uil']['program']['body'].append({'op': 'require', 'condition': {'const': false_slot}})
        harness = ZHarnessStudy(document)
        before = harness.private_state()
        token = harness.observe()['context_token']
        result = advance(harness)
        self.assertEqual(result['status'], 'refused')
        self.assertEqual(harness.private_state(), before)
        self.assertEqual(harness.observe()['context_token'], token)
        self.assertEqual(harness.private_history()['snapshots_used'], 1)

    def test_pending_host_is_a_plan_and_does_not_commit_or_execute_effects(self):
        document = scene()
        constants = document['uil']['program']['constants']
        text_slot = len(constants)
        constants.append({'type': 'text'})
        document['uil']['bindings']['constants'].append('Calendar advanced')
        document['uil']['program']['body'].append({'op': 'effect', 'service': 'text.display', 'value': {'const': text_slot}})
        harness = ZHarnessStudy(document)
        before = harness.private_state()
        result = advance(harness)
        self.assertEqual(result['status'], 'pending_host')
        self.assertFalse(result['host_effects_executed'])
        self.assertEqual(result['events'], [{'service': 'text.display', 'text': 'Calendar advanced'}])
        self.assertEqual(harness.private_state(), before)
        self.assertEqual(harness.private_history()['snapshots_used'], 1)
        self.assertEqual(harness.private_last_attempt()['proposed_state'][1], 1)

    def test_same_public_narration_does_not_pass_hidden_state_comparison(self):
        harness = ZHarnessStudy(scene())
        faulty = json.loads((ROOT / 'examples/faulty_calendar_variant.json').read_text())
        checkpoint = harness.checkpoint()
        before = harness.private_state()
        comparison = harness.compare_variant(faulty)
        self.assertTrue(comparison['public_equal'])
        self.assertFalse(comparison['agreement'])
        self.assertEqual([entry['slot'] for entry in comparison['mismatches']], [4, 5, 6, 7, 8, 9, 10])
        self.assertFalse(comparison['original_machine_executed'])
        self.assertEqual(harness.private_state(), before)
        self.assertEqual(harness.checkpoint(), checkpoint)

    def test_comparator_includes_preserved_flags_and_excludes_declared_temporary(self):
        document = scene()
        harness = ZHarnessStudy(document)
        bad_flags = deepcopy(document['uil'])
        bad_flags['program']['body'].append({'op': 'set', 'dst': 2, 'value': {'const': 13}})
        self.assertEqual([entry['slot'] for entry in harness.compare_variant(bad_flags)['mismatches']], [2])
        different_scratch = deepcopy(document['uil'])
        different_scratch['program']['body'].append({'op': 'set', 'dst': 11, 'value': {'const': 9}})
        self.assertTrue(harness.compare_variant(different_scratch)['agreement'])

    def test_last_change_reports_net_changes_not_same_value_writes(self):
        harness = ZHarnessStudy(scene())
        advance(harness)
        result = harness.last_change(4)
        self.assertEqual((result['before'], result['after']), (1, 2))
        self.assertEqual(result['kind'], 'net-change-between-invocations')
        # Slot3 was written by the original/model doubling operation, but zero*2
        # remains zero. Snapshot comparison must not claim that it was unwritten.
        result = harness.last_change(3)
        self.assertEqual(result['status'], 'not_found')
        self.assertIn('Same-value writes', result['limitation'])

    def test_returned_copies_and_caller_documents_do_not_mutate_authority(self):
        document = scene()
        harness = ZHarnessStudy(document)
        document['uil']['bindings']['initial'][1] = 999
        public = harness.observe()
        public['values']['year'] = 999
        state = harness.private_state()
        state[4] = 999
        history = harness.private_history()
        history['nodes'][0]['state'][4] = 999
        self.assertEqual(harness.observe()['values']['year'], -20)
        self.assertEqual(harness.private_state()[4], 1)

    def test_strict_scene_requests_slots_and_foreign_checkpoints(self):
        for mutation in (
            lambda d: d.update(extra=True),
            lambda d: d.update(max_history=True),
            lambda d: d.update(max_history=65),
            lambda d: d['public_slots'].update(turn=False),
            lambda d: d['comparison'].update(required_slots=[0, 1]),
            lambda d: d['clock'].update(unit='game tick'),
        ):
            document = scene()
            mutation(document)
            with self.subTest(document=document), self.assertRaises(ValueError):
                validate_scene(document)
        harness = ZHarnessStudy(scene())
        with self.assertRaises(ValueError):
            harness.act({'action': ACTION})
        with self.assertRaises(ValueError):
            harness.last_change(True)
        with self.assertRaises(ValueError):
            harness.restore(ZHarnessStudy(scene()).checkpoint())
        bad_candidate = deepcopy(scene()['uil'])
        bad_candidate['program']['inputs'] = [0, 1]
        with self.assertRaises(ValueError):
            harness.compare_variant(bad_candidate)


if __name__ == '__main__':
    unittest.main(verbosity=2)
