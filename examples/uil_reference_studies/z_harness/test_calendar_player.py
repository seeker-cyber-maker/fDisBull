"""Provided calendar-bridge contracts using the repository's real Player."""
import copy
import json
from pathlib import Path
import unittest

from fdisbull_player import Player
from z_harness_study import ZHarnessStudy
from calendar_player_adapter import CalendarPlayerAdapter

ROOT = Path(__file__).resolve().parent


def model_scene():
    return json.loads((ROOT / 'examples/calendar_scene.json').read_text())


class CalendarPlayerTests(unittest.TestCase):
    def test_actual_player_runs_supplied_calendar_and_read_is_passive(self):
        h=ZHarnessStudy(model_scene());b=CalendarPlayerAdapter(h);p=Player(b)
        before=h.private_state();self.assertIn('65535',p.execute('look'))
        self.assertEqual(h.private_state(),before);self.assertEqual(b.action_calls,0)
        self.assertIn('Year: 1',p.execute('advance calendar'))
        self.assertEqual(h.private_state(),[0,1,0,0,2,65534,0,65534,246,65524,20,20])
        self.assertEqual(b.action_calls,1)
    def test_real_and_faulty_models_have_equal_public_play_but_private_difference(self):
        doc=model_scene();bad=json.loads((ROOT/'examples/faulty_calendar_variant.json').read_text())
        reference=ZHarnessStudy(doc);comparison=reference.compare_variant(bad)
        self.assertTrue(comparison['public_equal']);self.assertFalse(comparison['agreement'])
        self.assertEqual(len(comparison['mismatches']),7)
        candidate_doc=copy.deepcopy(doc);candidate_doc['uil']=bad
        a=Player(CalendarPlayerAdapter(reference))
        b=Player(CalendarPlayerAdapter(ZHarnessStudy(candidate_doc)))
        self.assertEqual(a.execute('advance calendar'),b.execute('advance calendar'))
    def test_restore_rejects_old_token_through_player_adapter(self):
        h=ZHarnessStudy(model_scene());b=CalendarPlayerAdapter(h)
        old=b.observe()['context']['token'];saved=h.checkpoint();h.restore(saved)
        before=h.private_state()
        r=b.act({'verb':'advance','target':'calendar','item':None,'context_token':old})
        self.assertEqual((r['status'],r['effects']),('rejected','none-confirmed'))
        self.assertEqual(before,h.private_state())
    def test_bridge_does_not_claim_durable_save_or_whole_turn(self):
        b=CalendarPlayerAdapter(ZHarnessStudy(model_scene()))
        self.assertFalse(b.save()['complete']);self.assertEqual(b.observe()['objects'][0]['verbs'],['advance'])
        self.assertEqual(b.act({'verb':'end-turn','target':'calendar','item':None,'context_token':'x'})['status'],'rejected')


if __name__ == '__main__':
    unittest.main(verbosity=2)
