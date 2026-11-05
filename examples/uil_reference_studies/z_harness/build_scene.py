"""Build the authored Z envelope around the recovered calendar UIL document."""
from copy import deepcopy
import json
from pathlib import Path

from z_harness_study import ACTION, CLOCK_UNIT, PROFILE, validate_scene

ROOT = Path(__file__).resolve().parent
EXAMPLES = ROOT / 'examples'


def build():
    uil = json.loads((EXAMPLES / 'civ_calendar.json').read_text())
    # This is an authored entry witness, matching one retained native probe case.
    uil['bindings']['initial'] = [65535, -20, 0, 0, 1, 32767, 32768, 65535, 123, 65530, 10, 0]
    scene = {'format': PROFILE,
             'scene': {'id': 'civilization-calendar-study', 'title': 'Calendar laboratory',
                       'description': 'A recovered calendar slice with an authored Z interface; not the full End Turn action.'},
             'clock': {'unit': CLOCK_UNIT, 'basis': 'successful committed call'},
             'action': {'id': ACTION, 'label': 'Advance the calendar slice'},
             'public_slots': {'turn': 0, 'year': 1},
             'comparison': {'required_slots': list(range(11))},
             'max_history': 64, 'uil': uil}
    validate_scene(scene)
    (EXAMPLES / 'calendar_scene.json').write_text(json.dumps(scene, indent=2) + '\n')
    faulty = deepcopy(uil)
    faulty['description'] = 'Deliberately faulty authored variant: skips eight word updates but keeps public turn/year behavior.'
    faulty['source_evidence'] = {'kind': 'authored_counterexample',
                                 'qualification': 'Not recovered source and not an accepted replacement.'}
    # Retain the year-zero correction while deliberately omitting its word writes.
    faulty['program']['body'][3]['then'] = faulty['program']['body'][3]['then'][-1:]
    (EXAMPLES / 'faulty_calendar_variant.json').write_text(json.dumps(faulty, indent=2) + '\n')
    return scene


if __name__ == '__main__':
    build()
    print('Wrote calendar_scene.json and faulty_calendar_variant.json')
