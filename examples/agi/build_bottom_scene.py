"""Export a partial Z scene from a completed ordinary-input bridge-bottom run.

The output is an observed two-action projection, not autonomous AGI execution.
Source/artifact consistency checks do not authenticate supplied run records.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from examples.agi.build_clip_scene import FIELDS, BOOLEAN_FIELDS, frame_evidence, require
from examples.agi.scan_collision_candidates import edge_water_seams
from fdisbull.agi import load_logic
from fdisbull.agi_picture import decode_picture, extract_v2_resource
from fdisbull.il_scenes import ILSceneBackend


EXTRA = ('control_direction', 'edge', 'initializing', 'ignore_blocks')
BOOL = BOOLEAN_FIELDS + ('initializing', 'ignore_blocks')
TRACKED = FIELDS + EXTRA
STAGES = ('bridge-entry', 'east-bank', 'row-start', 'over-water', 'west-exit')


def state(value, *, moving=False):
    require(isinstance(value, dict) and isinstance(value.get('ego'), dict), 'Missing observed actor')
    result = {k: value['ego'].get(k) if k in ('x', 'y', 'direction', 'drawn') else value.get(k) for k in TRACKED}
    for key, item in result.items():
        require(type(item) is bool if key in BOOL else type(item) is int and 0 <= item <= 255,
                'Invalid typed state: '+key)
    require(result['x'] < 160 and result['y'] < 168 and result['ego_width'] == 6 and
            result['ego_view'] == 0 and result['step_size'] == 1, 'Unqualified actor geometry')
    require(result['drawn'] and result['score'] == 0 and result['swimming'] == 0 and
            not any(result[k] for k in ('in_water', 'dead', 'bridge_active', 'troll_removed', 'troll_paid', 'initializing')),
            'Unsafe or unfinished observed state')
    require(result['edge'] == 0 and value.get('window') == 0 and
            (result['direction'], result['control_direction']) == ((7, 7) if moving else (0, 0)),
            'Input or room initialization has not settled')
    return result


def build(source, capture, report, artifact_loader):
    """Validate a supplied completed capture; execute no native guest or input."""
    source = Path(source)
    require(isinstance(capture, dict) and capture.get('format') == 'fdisbull-agi-bridge-bottom-capture-1',
            'Expected bottom-row capture')
    runtime = capture.get('runtime', {})
    require(runtime.get('policy') == 'physical' and runtime.get('fresh_game') is True and
            runtime.get('interventions') == [], 'Expected fresh physical gameplay')
    require(isinstance(report, dict) and report.get('boundary_case_complete') is True and
            report.get('boundary_result', {}).get('complete') is True and
            report['boundary_result'].get('result') == 'bottom-row-west-exit' and
            report.get('post_teardown_source_unchanged') is True and
            report.get('post_teardown_copy_unchanged') is True and not report.get('persistence_errors'),
            'Completed unchanged-source run receipt required')
    identity = capture.get('source', {})
    require(sha256((source/'AGI').read_bytes()).hexdigest() == identity.get('agi_sha256'), 'AGI identity differs')
    resources = {n: load_logic(source/'LOGDIR', source, n, profile='2.917') for n in (39, 40)}
    require(all(identity.get('resources', {}).get(str(n)) == r.resource_sha256 for n, r in resources.items()),
            'Room logic identity differs')
    picture = extract_v2_resource(source/'PICDIR', source, 39)
    require(capture.get('picture') == {'room': 39, 'sha256': picture['sha256']}, 'Picture identity differs')
    seams = edge_water_seams(decode_picture(picture['payload'])['priority'], width=6,
                             allow_priority_one=True, max_candidates=1024)
    require(seams['complete'] and any(p['edge'] == 'bottom' and p['x'] == 80 and p['y'] == 167
                                    for p in seams['candidates']), 'Expected source hazard seam missing')
    observations = capture.get('bottom_observations')
    require(isinstance(observations, list) and len(observations) == len(STAGES) and
            [o.get('id') for o in observations] == list(STAGES), 'Expected five ordered observations')
    inputs, messages = capture.get('inputs'), capture.get('messages')
    require(isinstance(inputs, list) and 0 < len(inputs) <= 2000 and isinstance(messages, list) and len(messages) <= 32,
            'Input/message records missing or excessive')
    require(all(isinstance(i, dict) and i.get('kind') == 'keyboard' and i.get('delivered') is True and
                i.get('complete') is True and i.get('delivery', {}).get('accepted') is True for i in inputs),
            'Incomplete or uncertain input delivery')
    checked = []
    for index, observation in enumerate(observations):
        projected = state(observation.get('state'), moving=index == 3)
        for key, maximum in (('input_count', len(inputs)), ('message_count', len(messages))):
            require(type(observation.get(key)) is int and 0 <= observation[key] <= maximum,
                    'Invalid observation record count')
        frame = frame_evidence(observation.get('frame'), artifact_loader)
        require((frame['metadata']['width'], frame['metadata']['height'], frame['metadata']['mode_id']) == (320, 200, 5),
                'Unexpected video dimensions/mode')
        require(type(observation.get('guest_ms')) is int and observation['guest_ms'] >= 0, 'Missing guest progress')
        if checked:
            previous = observations[index-1]
            require(observation['guest_ms'] > previous['guest_ms'] and
                    all(observation[k] >= previous[k] for k in ('input_count', 'message_count')) and
                    frame['metadata']['frame_id'] >= checked[-1]['frame']['metadata']['frame_id'],
                    'Observations out of order')
        checked.append({'id': observation['id'], 'state': projected, 'frame': frame,
                        'guest_ms': observation['guest_ms'], 'input_count': observation['input_count'],
                        'message_count': observation['message_count']})
    a, b, middle, end = [checked[n]['state'] for n in (1, 2, 3, 4)]
    require([(s['room'], s['x'], s['y']) for s in (a, b)] == [(39, 110, 166), (39, 110, 167)] and
            middle['room'] == 39 and middle['y'] == 167 and 5 <= middle['x'] <= 80 and
            any(p['edge'] == 'bottom' and p['x'] == middle['x'] and p['y'] == middle['y'] for p in seams['candidates']) and
            end['room'] == 40 and 149 <= end['x'] <= 154 and end['y'] == 167, 'Observed route differs')
    require(report['boundary_result'].get('final') == observations[-1], 'Final receipt/capture disagree')
    require(observations[-1]['input_count'] == len(inputs) and observations[-1]['message_count'] == len(messages),
            'Trailing unaccounted input or messages')
    require(len(messages) == 1, 'Original final-room dialogue capture missing')
    for msg in messages:
        require(msg.get('logic') == 40 and msg.get('status') == 'completed' and
                msg.get('source_offset') == 175 and msg.get('message_id') == 1 and
                msg.get('native_execution') is True and msg.get('handler_return_observed') is True and
                msg.get('input_settled') is True and msg.get('window_closed') is True and
                msg.get('identity', {}).get('resource_sha256') == resources[40].resource_sha256 and
                not msg.get('cleanup_errors'), 'Unfinished or unbound original dialogue')
        frame_evidence(msg.get('frame'), artifact_loader)
    variables = {'$phase': {'type': 'u8', 'initial': 0}, **{
        '$'+k: {'type': 'bool' if k in BOOL else 'u8', 'initial': a[k]} for k in TRACKED}}
    programs, edges = {}, []
    for index, (name, before, after, i, j) in enumerate((
            ('take-bottom-row', a, b, 1, 2), ('cross-bottom', b, end, 2, 4))):
        section = inputs[observations[i]['input_count']:observations[j]['input_count']]
        require(section and any(item.get('key') == ('press:down' if index == 0 else 'press:left') for item in section),
                'Required ordinary movement input missing')
        body = [{'id': 'phase', 'op': 'require', 'condition': {'op': 'eq', 'left': {'var': '$phase'}, 'right': index}}]
        body += [{'id': 'guard-'+k, 'op': 'require', 'condition': {'op': 'eq', 'left': {'var': '$'+k}, 'right': before[k]}}
                 for k in TRACKED]
        body += [{'id': 'set-'+k, 'op': 'set', 'var': '$'+k, 'value': after[k]} for k in TRACKED if before[k] != after[k]]
        body += [{'id': 'next-phase', 'op': 'set', 'var': '$phase', 'value': index+1},
                 {'id': 'response', 'op': 'text', 'resource': 'response'}]
        programs[name] = {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': variables,
                         'resources': {'response': {'kind': 'text', 'text':
                             'The recorded walk reaches the bottom row.' if index == 0 else
                             'The recorded bottom-row walk reaches the neighboring room, dry and without resolving the troll.'}},
                         'body': body}
        edges.append({'program': name, 'before': STAGES[i], 'after': STAGES[j], 'inputs': deepcopy(section),
                      'messages': deepcopy(messages[observations[i]['message_count']:observations[j]['message_count']])})
    scene = {'format': 'fdisbull-il-scene-1', 'programs': programs, 'partial': True,
             'contexts': [{'id': 'phase-'+str(n), 'title': title,
                           'description': 'Partial projection of a supplied ordinary-input route; no autonomous AGI execution.',
                           'when': {'op': 'eq', 'left': {'var': '$phase'}, 'right': n}}
                          for n, title in enumerate(('Southern bridge bank', 'Bottom-row seam', 'Western room'))],
             'objects': [{'id': name, 'context': 'phase-'+str(n), 'label': name, 'aliases': [],
                          'description': description, 'bindings': [{'verb': 'use', 'program': program}]}
                         for n, (name, program, description) in enumerate((
                             ('edge', 'take-bottom-row', 'Take the observed step from row166 to row167.'),
                             ('crossing', 'cross-bottom', 'Follow the observed western crossing. Other bottom-row origins remain unqualified.')))]}
    ILSceneBackend(scene)
    evidence = {'format': 'fdisbull-agi-bridge-bottom-z-evidence-1', 'source': deepcopy(identity),
                'picture': deepcopy(capture['picture']), 'observations': checked, 'edges': edges,
                'capture_sha256': sha256(json.dumps(capture, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                'report_sha256': sha256(json.dumps(report, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                'scope': 'Supplied observations and source identities; hashes do not authenticate execution. One observed ordinary route, not all82 candidates, collision-handler proof, deterministic replay or durable saves. Frames are last-completed, not atomic with state.'}
    return scene, evidence


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'capture', 'report', 'artifacts', 'output'):
        ap.add_argument('--'+name, required=True, type=Path)
    args = ap.parse_args()
    source, artifacts, output = args.source.resolve(), args.artifacts.resolve(), args.output.resolve()
    checkout = Path(__file__).resolve().parents[2]
    require(not args.output.exists() and not args.output.is_symlink() and output != checkout and checkout not in output.parents and
            all(output != p and p not in output.parents and output not in p.parents for p in (source, artifacts)),
            'Use fresh private output outside source, artifacts and Git')
    def read(path):
        target = (artifacts/path).resolve()
        require(artifacts in target.parents and target.is_file(), 'Artifact escaped private root')
        return target.read_bytes()
    scene, evidence = build(source, json.loads(args.capture.read_bytes()), json.loads(args.report.read_bytes()), read)
    raw = (json.dumps(scene, indent=2)+'\n').encode()
    evidence['scene_sha256'] = sha256(raw).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    (output/'scene.json').write_bytes(raw)
    (output/'provenance.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps({'scene': str(output/'scene.json'), 'provenance': str(output/'provenance.json')}))


if __name__ == '__main__':
    main()
