"""Build a private, partial Z scene from supplied bridge-clip observations.

Hashes and consistency checks do not authenticate native execution. Generated
text is authored here; no original game messages or frames enter the scene.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

from fdisbull.agi import AGI2917Processor, load_logic
from fdisbull.agi_layout import logic_layout
from fdisbull.agi_picture import decode_picture, extract_v2_resource
from fdisbull.agi_resources import logic_messages
from fdisbull.il_scenes import ILSceneBackend
from fdisbull.processor import Location
from fdisbull.scene_domains import audit_coordinate_domains
from examples.agi.scan_collision_candidates import edge_water_seams


ACTION_IDS = ('approach-corner', 'cross-gap', 'leave-bridge')
BOOLEAN_FIELDS = ('drawn', 'in_water', 'dead', 'bridge_active', 'troll_removed', 'troll_paid')
BYTE_FIELDS = ('room', 'score', 'x', 'y', 'direction', 'ego_width', 'ego_view', 'step_size', 'swimming')
FIELDS = BYTE_FIELDS + BOOLEAN_FIELDS


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return sha256(raw).hexdigest()


def artifact(reference, loader, name):
    require(isinstance(reference, dict) and isinstance(reference.get('path'), str) and bool(reference['path']),
            'missing ' + name + ' artifact')
    raw = loader(reference['path'])
    require(type(raw) is bytes and bool(raw) and digest(raw) == reference.get('sha256'), name + ' artifact hash mismatch')
    return raw


def json_artifact(reference, loader, name):
    try:
        value = json.loads(artifact(reference, loader, name))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('invalid ' + name + ' JSON') from exc
    require(isinstance(value, dict), 'invalid ' + name + ' document')
    return value


def frame_evidence(frame, loader):
    artifact(frame, loader, 'frame')
    metadata = frame.get('metadata')
    require(isinstance(metadata, dict) and metadata.get('source') == 'last_completed_guest_frame' and
            all(type(metadata.get(key)) is int and metadata[key] >= 0 for key in ('frame_id', 'mode_id')) and
            all(type(metadata.get(key)) is int and metadata[key] > 0 for key in ('width', 'height')),
            'incomplete native frame metadata')
    return {'sha256': frame['sha256'], 'metadata': deepcopy(metadata)}


def project_state(value):
    require(isinstance(value, dict) and isinstance(value.get('ego'), dict), 'incomplete observed state')
    ego = value['ego']
    projected = {key: ego.get(key) if key in ('x', 'y', 'direction', 'drawn') else value.get(key) for key in FIELDS}
    require(all(type(projected[key]) is int and 0 <= projected[key] <= 255 for key in BYTE_FIELDS) and
            all(type(projected[key]) is bool for key in BOOLEAN_FIELDS), 'invalid typed observed state')
    require(projected['x'] < 160 and projected['y'] < 168, 'observed coordinates outside game geometry')
    require(projected['direction'] == 0 and projected['ego_width'] == 6 and projected['ego_view'] == 0 and
            projected['step_size'] == 1, 'unqualified walking geometry or direction')
    require(projected['score'] == 0 and projected['swimming'] == 0 and
            not any(projected[key] for key in ('in_water', 'dead', 'bridge_active', 'troll_removed', 'troll_paid')),
            'unsafe clip outcome or changed score/troll state')
    return projected


def predicate_evidence(reference, loader, resource):
    proof = json_artifact(reference, loader, 'native predicate')
    require(proof.get('format') == 'fdisbull-agi-posn-observation-1' and proof.get('status') == 'verified' and
            proof.get('complete') is True and proof.get('native_execution') is True and proof.get('result') is False and
            proof.get('source_logic_sha256') == resource.resource_sha256 and
            all(type(proof.get(key)) is int and proof[key] == expected for key, expected in
                (('source_logic', 39), ('condition_offset', 0x410), ('handler_entry_offset', 0x8c6),
                 ('return_offset', 0x7fb), ('continuation_source_offset', 0x41e))) and
            all(proof.get(key) is True for key in
                ('call_frame_verified', 'handler_return_observed', 'false_continuation_observed')),
            'native predicate boundary not qualified')
    arguments = proof.get('arguments')
    require(isinstance(arguments, list) and all(type(value) is int for value in arguments) and
            arguments == [0, 72, 84, 72, 87], 'native predicate arguments differ')
    position = proof.get('input_position')
    require(isinstance(position, dict) and all(type(position.get(key)) is int and position[key] == expected
            for key, expected in (('x', 72), ('y', 88), ('width', 6))), 'native predicate input position differs')
    trace = proof.get('trace')
    require(isinstance(trace, dict) and type(trace.get('event_count')) is int and
            type(trace.get('maximum_count')) is int and 0 < trace['event_count'] < 128 and
            trace['maximum_count'] == 128, 'invalid native predicate trace bounds')
    recorded = json_artifact(trace, loader, 'native predicate trace')
    require(recorded.get('format') == 'fdisbull-agi-posn-trace-1' and recorded.get('complete') is True and
            type(recorded.get('maximum_count')) is int and recorded['maximum_count'] == 128 and
            isinstance(recorded.get('events'), list) and len(recorded['events']) == trace['event_count'] and
            all(isinstance(event, dict) for event in recorded['events']) and
            isinstance(recorded.get('runs'), list) and bool(recorded['runs']) and
            all(isinstance(run, dict) for run in recorded['runs']), 'native predicate trace incomplete or count differs')
    return {'sha256': reference['sha256'], 'source_logic': 39, 'source_logic_sha256': resource.resource_sha256,
            'condition_offset': 0x410, 'arguments': arguments, 'result': False,
            'input_position': {key: position[key] for key in ('x', 'y', 'width')},
            'handler_entry_offset': 0x8c6, 'return_offset': 0x7fb,
            'call_frame_verified': True, 'handler_return_observed': True,
            'false_continuation_observed': True, 'continuation_source_offset': 0x41e,
            'trace': {key: trace[key] for key in ('sha256', 'event_count', 'maximum_count')}}


def build(source, capture, artifact_loader):
    """Validate supplied observations and source identities; perform no guest work."""
    source = Path(source)
    require(isinstance(capture, dict) and capture.get('format') == 'fdisbull-agi-bridge-clip-capture-1', 'invalid clip capture format')
    runtime = capture.get('runtime')
    require(isinstance(runtime, dict) and runtime.get('policy') == 'physical' and runtime.get('fresh_game') is True and
            runtime.get('interventions') == [], 'unqualified physical runtime')
    identity = capture.get('source')
    require(isinstance(identity, dict) and digest((source / 'AGI').read_bytes()) == identity.get('agi_sha256'), 'AGI identity mismatch')
    expected = identity.get('resources')
    require(isinstance(expected, dict) and all(key in expected for key in ('39', '40')) and len(expected) <= 256,
            'missing clip source logic identities')
    resources = {}
    for key, value in expected.items():
        require(isinstance(key, str) and re.fullmatch(r'0|[1-9][0-9]{0,2}', key) is not None and int(key) <= 255,
                'invalid logic resource number')
        resource = load_logic(source / 'LOGDIR', source, int(key), profile='2.917')
        require(resource.resource_sha256 == value, 'logic resource identity mismatch')
        resources[int(key)] = resource
    resource = resources[39]
    condition = logic_layout(resource.payload)['conditions'].get(0x412)
    require(condition == {'opcode': 11, 'end': 0x418, 'negated': False} and
            resource.code[0x410:0x416] == bytes.fromhex('0b0048544857'), 'posn source condition witness differs')
    parent = AGI2917Processor(resource.space).decode(resource.code, Location(resource.space, 0x408))
    require(parent.facts.get('mnemonic') == 'if' and any(successor.kind == 'false' and successor.target.offset == 0x41e
            for successor in parent.successors), 'posn source false successor differs')
    picture = capture.get('picture')
    require(isinstance(picture, dict) and type(picture.get('room')) is int and picture['room'] == 39, 'missing picture 39 identity')
    extracted = extract_v2_resource(source / 'PICDIR', source, 39)
    picture_sha = digest(extracted['payload'])
    require(picture_sha == extracted['sha256'] == picture.get('sha256'), 'picture resource identity mismatch')
    decoded_picture = decode_picture(extracted['payload'])
    observations = capture.get('observations')
    actions = capture.get('actions')
    require(isinstance(observations, dict) and isinstance(actions, list) and len(actions) == 3 and
            all(isinstance(action, dict) and action.get('id') == name for action, name in zip(actions, ACTION_IDS)),
            'expected the three ordered clip actions')
    require(all(actions[index].get('before') == actions[index-1].get('after') for index in (1, 2)), 'clip actions are not contiguous')
    checked_observations = {}

    def observation(ident):
        require(isinstance(ident, str) and ident in observations, 'missing clip observation')
        if ident not in checked_observations:
            value = observations[ident]
            require(isinstance(value, dict), 'invalid clip observation')
            state = project_state(value.get('state'))
            checked_observations[ident] = {'state': state, 'frame': frame_evidence(value.get('frame'), artifact_loader)}
        return checked_observations[ident]['state']

    states = [observation(actions[0].get('before'))]
    message_bindings = []
    for index, action in enumerate(actions):
        require(action.get('complete') is True and action.get('messages_complete') is True, 'incomplete action or message observation')
        messages = action.get('messages')
        require(isinstance(messages, list) and len(messages) == (1 if index == 2 else 0), 'unexpected clip dialogue count')
        binding = None
        if index == 2:
            message = messages[0]
            require(isinstance(message, dict) and message.get('status') == 'completed' and
                    message.get('mode') == 'blocking' and all(message.get(key) is True for key in
                    ('native_execution', 'native_execution_attempted', 'input_attempted',
                     'handler_return_observed', 'input_settled', 'window_closed')) and
                    message.get('cleanup_errors', []) == [], 'incomplete final-room message')
            require(all(type(message.get(key)) is int and message[key] == expected for key, expected in
                    (('logic', 40), ('source_offset', 175), ('message_id', 1))), 'unexpected final-room message identity')
            target = resources[40]
            require(target.code[175:177] == bytes((101, 1)), 'final-room print source differs')
            text = logic_messages(target)[target.resource_sha256].get('1')
            require(isinstance(text, str) and bool(text), 'missing final-room source message')
            encoded = text.encode('cp437')
            native_identity, native_message = message.get('identity'), message.get('message')
            require(isinstance(native_identity, dict) and native_identity.get('resource_sha256') == target.resource_sha256 and
                    isinstance(native_message, dict) and native_message.get('resource_sha256') == target.resource_sha256 and
                    type(native_message.get('message_id')) is int and native_message['message_id'] == 1 and
                    native_message.get('text_sha256') == digest(encoded) and type(native_message.get('length')) is int and
                    native_message['length'] == len(encoded), 'final-room native message metadata differs from source')
            receipt, after_keyboard = message.get('input'), message.get('keyboard_after')
            require(isinstance(receipt, dict) and receipt.get('accepted') is True and isinstance(after_keyboard, dict) and
                    isinstance(after_keyboard.get('keyboard'), dict) and all(type(after_keyboard['keyboard'].get(key)) is int and
                    after_keyboard['keyboard'][key] == 0 for key in ('pending_events', 'owned_keys', 'queued_guest_ms')),
                    'final-room physical input not qualified or settled')
            binding = {'logic': 40, 'source_offset': 175, 'message_id': 1,
                       'resource_sha256': target.resource_sha256, 'text_sha256': digest(encoded), 'length': len(encoded),
                       'native_execution': True, 'handler_return_observed': True, 'input_accepted_and_settled': True,
                       'frame': frame_evidence(message.get('frame'), artifact_loader)}
        message_bindings.append(binding)
        inputs = action.get('inputs')
        require(isinstance(inputs, list) and bool(inputs) and all(isinstance(item, dict) and item.get('kind') == 'keyboard' and
                isinstance(item.get('key'), str) and bool(item['key']) and item.get('delivered') is True and
                item.get('complete') is True and isinstance(item.get('delivery'), dict) and item['delivery'].get('accepted') is True
                for item in inputs), 'unqualified keyboard input')
        observation(action.get('before'))
        states.append(observation(action.get('after')))
    observation_ids = [actions[0]['before']] + [action['after'] for action in actions]
    frame_ids = [checked_observations[ident]['frame']['metadata']['frame_id'] for ident in observation_ids]
    require(all(after > before for before, after in zip(frame_ids, frame_ids[1:])), 'clip observation frames are not ordered')
    message_frame_id = message_bindings[2]['frame']['metadata']['frame_id']
    require(frame_ids[2] < message_frame_id < frame_ids[3], 'final-room message frame lies outside its action')
    for state, point in zip(states[:3], ((39, 85, 100), (39, 72, 88), (39, 10, 87))):
        require((state['room'], state['x'], state['y']) == point, 'clip waypoint differs')
    require(states[-1]['room'] == 40 and 149 <= states[-1]['x'] <= 154, 'clip exit differs')
    predicate = predicate_evidence(actions[1].get('native_predicate'), artifact_loader, resource)
    # The picture viewport is in AGI units. It is not the full native frame;
    # neither an unknown sprite extent nor an edge seam grants a walking route.
    coordinate_domains = {
        'format': 'fdisbull-coordinate-domains-1',
        'space': {'name': 'agi-room-39', 'unit': 'agi-picture-unit'},
        'bounds': {'world': None, 'room': [0, 0, 160, 168],
                   'collision': [0, 0, 160, 168], 'viewport': [0, 0, 160, 168]},
        'objects': [{'id': 'ego', 'role': 'actor', 'pose': [states[0]['x'], states[0]['y']],
                     'render': None, 'collision': [0, 0, states[0]['ego_width'], 1]}],
        'expectations': [], 'alerts': True,
        'provenance': {'source_picture_sha256': picture_sha,
                       'observation_frame_sha256': checked_observations[observation_ids[0]]['frame']['sha256'],
                       'evidence_status': 'source-grid-and-supplied-observation',
                       'scope': 'Logical picture viewport and land collision baseline; full frame transform, sprite rectangle and world bounds are not inferred.'},
    }
    layout_audit = audit_coordinate_domains(coordinate_domains)
    edge_seams = edge_water_seams(decoded_picture['priority'], width=states[0]['ego_width'],
                                  allow_priority_one=True, max_candidates=1024)
    edge_seams['scope'] = ('Static passable edge baselines adjacent to all-water baselines. '
                           'Priority-one allowance is declared; live blockers, borders, '
                           'reachability and bottom-row traversal are not qualified by this capture.')
    variables = {'$phase': {'type': 'u8', 'initial': 0}, **{
        '$'+key: {'type': 'bool' if key in BOOLEAN_FIELDS else 'u8', 'initial': states[0][key]} for key in FIELDS}}
    texts = ('The recorded approach reaches the corner at (72, 88).',
             'The recorded route crosses the gap to the western bank.', 'The recorded route reaches room 40.')
    programs = {}
    for index, name in enumerate(ACTION_IDS):
        before, after = states[index:index+2]
        body = [{'id': 'guard-phase', 'op': 'require', 'condition': {'op': 'eq', 'left': {'var': '$phase'}, 'right': index}}]
        for key in FIELDS:
            body.append({'id': 'guard-'+key, 'op': 'require', 'condition': {'op': 'eq', 'left': {'var': '$'+key}, 'right': before[key]}})
        for key in FIELDS:
            if before[key] != after[key]:
                body.append({'id': 'set-'+key, 'op': 'set', 'var': '$'+key, 'value': after[key]})
        body += [{'id': 'set-phase', 'op': 'set', 'var': '$phase', 'value': index+1},
                 {'id': 'message', 'op': 'text', 'resource': 'message'}]
        programs[name] = {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': variables,
                          'resources': {'message': {'kind': 'text', 'text': texts[index]}}, 'body': body}
    titles = ('Observed eastern bridge approach', 'Observed bridge corner', 'Observed western bank', 'Observed route to room 40')
    scene = {'format': 'fdisbull-il-scene-1', 'programs': programs,
             'contexts': [{'id': 'phase-'+str(index), 'title': title,
                           'description': 'A partial reconstruction of supplied route observations.',
                           'when': {'op': 'eq', 'left': {'var': '$phase'}, 'right': index}} for index, title in enumerate(titles)],
             'objects': [{'id': target, 'context': 'phase-'+str(index), 'label': target, 'aliases': [],
                          'description': 'The next recorded movement.', 'bindings': [{'verb': 'use', 'program': ACTION_IDS[index]}]}
                         for index, target in enumerate(('corner', 'gap', 'route'))], 'partial': True}
    bottom = [candidate for candidate in edge_seams['candidates'] if candidate['edge'] == 'bottom']
    if bottom:
        notice = ('Source layout notice: '+str(len(bottom))+' bottom-edge baseline candidates '
                  'are adjacent to water. Their walking routes remain unqualified; '
                  'this projection retains only its recorded corner crossing.')
        scene['contexts'][1]['description'] += ' '+notice
        scene['objects'][1]['description'] += ' '+notice
    ILSceneBackend(scene)
    provenance = {'format': 'fdisbull-agi-bridge-clip-z-evidence-1', 'source': deepcopy(identity),
        'capture_sha256': digest(json.dumps(capture, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()),
        'picture': {'room': 39, 'sha256': picture_sha, 'length': len(extracted['payload'])},
        'coordinate_domains': coordinate_domains, 'layout_audit': layout_audit,
        'edge_seams': edge_seams,
        'observations': deepcopy(checked_observations),
        'edges': [{'id': action['id'], 'before': action['before'], 'after': action['after'],
                   'messages': [message_bindings[index]] if message_bindings[index] else [],
                   **({'native_predicate': predicate} if index == 1 else {})} for index, action in enumerate(actions)],
        'scope': 'Supplied observations and source/artifact identities. Hashes do not authenticate execution. The exported partial IL scene supplies no native execution, autonomous timing, full-engine proof, or durable saves.'}
    return scene, provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'capture', 'artifacts', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    source, root, output = args.source.resolve(), args.artifacts.resolve(), args.output.resolve()
    checkout = Path(__file__).resolve().parents[2]
    require(not output.exists() and not args.output.is_symlink() and output != checkout and checkout not in output.parents and
            all(output != path and path not in output.parents and output not in path.parents for path in (source, root)),
            'output must be a fresh private directory outside source and artifact trees')
    def load(path):
        target = (root / path).resolve()
        require(root in target.parents and target.is_file(), 'artifact path outside private directory')
        return target.read_bytes()
    scene, provenance = build(source, json.loads(args.capture.read_bytes()), load)
    raw = (json.dumps(scene, ensure_ascii=False, indent=2)+'\n').encode()
    provenance['scene_sha256'] = digest(raw)
    output.mkdir(parents=True, exist_ok=False)
    with (output / 'scene.json').open('xb') as stream:
        stream.write(raw)
    with (output / 'provenance.json').open('x') as stream:
        json.dump(provenance, stream, indent=2); stream.write('\n')
    print(json.dumps({'scene': str(output / 'scene.json'), 'provenance': str(output / 'provenance.json')}))


if __name__ == '__main__':
    main()
