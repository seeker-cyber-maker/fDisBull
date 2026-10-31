"""Export a private, bounded Z scene from supplied ordinary-play observations.

The capture is evidence supplied by an operator, not an authenticated recording.
No game text, frames, or generated scene belongs in a source repository.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from fdisbull.agi import load_logic
from fdisbull.agi_resources import logic_messages
from fdisbull.il_scenes import ILSceneBackend


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return sha256(data).hexdigest()


def build(source, capture, artifact_loader):
    """Build only the contiguous observed prefix; malformed capture fails closed."""
    source = Path(source)
    require(isinstance(capture, dict) and capture.get('format') == 'fdisbull-agi-natural-encounter-1', 'invalid capture format')
    runtime = capture.get('runtime', {})
    require(isinstance(runtime, dict) and runtime.get('policy') == 'physical' and
            runtime.get('fresh_game') is True and runtime.get('interventions') == [], 'unqualified runtime')
    identity = capture.get('source', {})
    require(isinstance(identity, dict) and digest((source / 'AGI').read_bytes()) == identity.get('agi_sha256'), 'AGI identity mismatch')
    expected = identity.get('resources')
    require(isinstance(expected, dict) and '103' in expected, 'missing resource identities')
    resources = {}
    for key, value in expected.items():
        require(isinstance(key, str) and re.fullmatch(r'0|[1-9][0-9]{0,2}', key) is not None and int(key) <= 255, 'invalid resource number')
        resource = load_logic(source / 'LOGDIR', source, int(key), profile='2.917')
        require(resource.resource_sha256 == value, 'logic resource identity mismatch')
        resources[int(key)] = resource
    frames = []
    def frame(value):
        require(isinstance(value, dict) and isinstance(value.get('path'), str) and bool(value['path']), 'missing frame path')
        metadata = value.get('metadata')
        require(isinstance(metadata, dict) and all(type(metadata.get(k)) is int and metadata[k] >= 0 for k in ('frame_id', 'mode_id')) and
                all(type(metadata.get(k)) is int and metadata[k] > 0 for k in ('width', 'height')) and
                metadata.get('source') == 'last_completed_guest_frame', 'incomplete frame metadata')
        raw = artifact_loader(value['path'])
        require(isinstance(raw, bytes) and bool(raw) and digest(raw) == value.get('sha256'), 'frame artifact mismatch')
        frames.append({'sha256': value['sha256'], 'metadata': dict(metadata)})
    observations = capture.get('observations')
    require(isinstance(observations, dict), 'missing observations')
    actions = capture.get('actions')
    require(isinstance(actions, list) and 1 <= len(actions) <= 4, 'expected one to four observed actions')
    require(isinstance(actions[0], dict) and actions[0].get('id') == 'show-carrot', 'first action must be show-carrot')
    if len(actions) >= 2:
        require(isinstance(actions[1], dict) and actions[1].get('id') in ('lead-to-water', 'wander-away', 'leave-pen') and
                actions[1].get('before') == actions[0].get('after'), 'actions are not a contiguous observed route')
    extension = None
    if len(actions) >= 3:
        require(actions[1]['id'] == 'leave-pen' and isinstance(actions[2], dict) and
                actions[2].get('id') in ('troll-bridge', 'lead-to-water') and
                actions[2].get('before') == actions[1].get('after'),
                'third action requires a contiguous show-carrot and leave-pen route')
        extension = actions[2]['id']
    bridge = extension == 'troll-bridge'
    water = extension == 'lead-to-water'
    if len(actions) == 4:
        require(water and isinstance(actions[3], dict) and actions[3].get('id') == 'leave-water' and
                actions[3].get('before') == actions[2].get('after'), 'fourth action requires a contiguous water departure')
    fields = ('room', 'score', 'carrot', 'following', 'gate_open')
    if bridge:
        require(25 in resources, 'missing bridge logic identity')
        fields += ('carrot_carried', 'troll_removed', 'troll_paid')
    if water:
        fields += ('carrot_carried', 'water_refused', 'goat_wandering', 'goat_retired', 'water_departure')
        if len(actions) == 4: require(8 in resources, 'missing water departure logic identity')
    def observation(ident):
        require(isinstance(ident, str) and ident in observations, 'missing observation')
        value = observations[ident]
        require(isinstance(value, dict), 'invalid observation')
        state = value.get('state')
        require(isinstance(state, dict) and all(type(state.get(k)) is int and 0 <= state[k] <= 255 for k in ('room', 'score')) and
                all(type(state.get(k)) is bool for k in ('carrot', 'following', 'gate_open')), 'incomplete observed state')
        if bridge:
            require(all(type(state.get(k)) is bool for k in ('carrot_carried', 'troll_removed', 'troll_paid')),
                    'incomplete bridge observed state')
        if water:
            require(all(type(state.get(k)) is bool for k in fields[5:]), 'incomplete water observed state')
        require(type(value.get('goat_visible')) is bool, 'missing explicit goat visibility observation')
        frame(value.get('frame'))
        return state, value['goat_visible']
    initial, visible = observation(actions[0].get('before'))
    require(initial['carrot'] and not initial['following'] and visible, 'unqualified initial goat encounter')
    checked = []
    for index, action in enumerate(actions):
        require(action.get('complete') is True and action.get('messages_complete') is True, 'incomplete action or message observation')
        require(isinstance(action.get('label'), str) and bool(action['label']) and isinstance(action.get('verb'), str) and bool(action['verb']), 'missing action identity')
        inputs = action.get('inputs')
        require(isinstance(inputs, list) and bool(inputs) and all(isinstance(x, dict) and x.get('kind') == 'keyboard' and
                isinstance(x.get('key'), str) and bool(x['key']) and x.get('delivered') is True and x.get('complete') is True for x in inputs), 'unqualified ordinary input')
        before, _ = observation(action.get('before'))
        after, after_visible = observation(action.get('after'))
        if index == 0:
            require(after['following'] and after['score'] == before['score'] + 5, 'unqualified carrot outcome')
        native_binding = None
        score_binding = None
        branch_binding = None
        if action['id'] == 'leave-pen':
            require(before['room'] in (10, 11) and after['room'] not in (10, 11) and
                    before['carrot'] and after['carrot'] and before['following'] and after['following'] and
                    before['score'] == after['score'], 'unqualified leave-pen outcome')
            native = action.get('native_invocation')
            require(isinstance(native, dict) and isinstance(native.get('path'), str) and bool(native['path']),
                    'missing native invocation')
            raw = artifact_loader(native['path'])
            require(isinstance(raw, bytes) and digest(raw) == native.get('sha256'), 'native invocation hash mismatch')
            try:
                trial = json.loads(raw)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError('invalid native invocation') from exc
            require(isinstance(trial, dict) and trial.get('format') == 'fdisbull-agi-original-host-trial-1' and
                    trial.get('status') == 'verified' and trial.get('complete') is True and
                    trial.get('native_execution') is True and trial.get('differences') == [] and
                    isinstance(trial.get('identity'), dict) and
                    trial['identity'].get('resource_sha256') == resources[103].resource_sha256,
                    'native invocation not qualified')
            offsets = trial.get('source_offsets')
            code = resources[103].code
            require(isinstance(offsets, list) and bool(offsets) and
                    all(type(offset) is int and 0 <= offset < len(code) and code[offset] not in (22, 23) for offset in offsets) and
                    code[offsets[-1]] == 0, 'native invocation has unsupported or incomplete source path')
            native_binding = {'sha256': native['sha256'], 'source_offsets': offsets}
        if action['id'] == 'troll-bridge':
            require(before['room'] == 9 and before['score'] == 7 and before['following'] and
                    before['carrot'] and before['carrot_carried'] and not before['troll_removed'] and not before['troll_paid'] and
                    after['room'] == 25 and after['score'] == before['score'] + 4 and not after['following'] and
                    after['carrot'] and after['carrot_carried'] and after['troll_removed'] and not after['troll_paid'],
                    'unqualified troll-bridge outcome')
            require(after_visible is False and observations[action['after']].get('troll_visible') is False,
                    'bridge outcome needs explicit goat and troll absence observations')
            require(resources[25].code[0x1b8:0x1bb] == bytes((5, 3, 4)), 'bridge score instruction mismatch')
            native = action.get('native_score_write')
            require(isinstance(native, dict) and isinstance(native.get('path'), str) and bool(native['path']),
                    'missing native bridge score write')
            raw = artifact_loader(native['path'])
            require(isinstance(raw, bytes) and digest(raw) == native.get('sha256'), 'bridge score write hash mismatch')
            try:
                proof = json.loads(raw)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError('invalid native bridge score write') from exc
            require(isinstance(proof, dict) and proof.get('format') == 'fdisbull-agi-troll-score-write-1' and
                    proof.get('status') == 'verified' and proof.get('complete') is True and proof.get('native_execution') is True and
                    proof.get('source_logic_sha256') == resources[25].resource_sha256 and
                    type(proof.get('source_offset')) is int and proof['source_offset'] == 0x1b8 and
                    type(proof.get('before_score')) is int and proof['before_score'] == before['score'] and
                    type(proof.get('after_score')) is int and proof['after_score'] == after['score'],
                    'native bridge score write not qualified')
            writer = proof.get('writer')
            require(isinstance(writer, dict) and all(type(writer.get(k)) is int and writer[k] == v for k, v in
                    (('source_offset', 0x72da), ('resume_offset', 0x72de), ('bx', 3), ('al', 4))),
                    'bridge native writer differs')
            trace = proof.get('trace')
            require(isinstance(trace, dict) and isinstance(trace.get('path'), str) and bool(trace['path']) and
                    type(trace.get('count')) is int and trace['count'] == 32, 'incomplete bridge score trace')
            trace_raw = artifact_loader(trace['path'])
            require(isinstance(trace_raw, bytes) and bool(trace_raw) and digest(trace_raw) == trace.get('sha256'),
                    'bridge score trace hash mismatch')
            score_binding = {'sha256': native['sha256'], 'source_logic_sha256': proof['source_logic_sha256'],
                             'source_offset': proof['source_offset'], 'before_score': proof['before_score'],
                             'after_score': proof['after_score'],
                             'writer': {k: writer[k] for k in ('source_offset', 'resume_offset', 'bx', 'al')},
                             'trace': {'sha256': trace['sha256'], 'count': trace['count']}}
        if water and index >= 2:
            if action['id'] == 'lead-to-water':
                require(before['room'] == 9 and before['score'] == 7 and before['carrot'] and before['carrot_carried'] and
                        before['following'] and not before['water_refused'] and
                        after['room'] == 8 and after['score'] == 7 and after['carrot'] and after['carrot_carried'] and
                        after['following'] and after['water_refused'] and after['goat_wandering'] and not after['goat_retired'],
                        'unqualified water refusal outcome')
                branch, logic, offset, opcode, argument, writer_offset, resume = 'water-refusal', 103, 381, 84, 13, 0x6dcb, 0x6dcf
            else:
                require(after['room'] == 9 and after['score'] == 7 and after['carrot'] and after['carrot_carried'] and
                        not after['following'] and not after['water_refused'] and after['goat_retired'] and after['water_departure'],
                        'unqualified water departure outcome')
                require(after_visible is False, 'water departure needs explicit goat absence observation')
                branch, logic, offset, opcode, argument, writer_offset, resume = 'water-departure', 8, 478, 13, 75, 0x7432, 0x7434
            require(resources[logic].code[offset:offset+2] == bytes((opcode, argument)), 'water branch source instruction mismatch')
            native = action.get('native_branch_effect')
            require(isinstance(native, dict) and isinstance(native.get('path'), str) and bool(native['path']), 'missing native water branch effect')
            raw = artifact_loader(native['path'])
            require(isinstance(raw, bytes) and digest(raw) == native.get('sha256'), 'water branch effect hash mismatch')
            try:
                proof = json.loads(raw)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError('invalid native water branch effect') from exc
            require(isinstance(proof, dict) and proof.get('format') == 'fdisbull-agi-goat-branch-effect-1' and
                    proof.get('branch') == branch and proof.get('status') == 'verified' and proof.get('complete') is True and
                    proof.get('native_execution') is True and proof.get('source_logic_sha256') == resources[logic].resource_sha256 and
                    all(type(proof.get(k)) is int and proof[k] == value for k, value in
                        (('source_logic', logic), ('source_offset', offset), ('opcode', opcode), ('argument', argument))),
                    'native water branch effect not qualified')
            writer = proof.get('writer')
            require(isinstance(writer, dict) and all(type(writer.get(k)) is int and writer[k] == value for k, value in
                    (('offset', writer_offset), ('resume_offset', resume))), 'water branch native writer differs')
            trace = proof.get('trace')
            require(isinstance(trace, dict) and isinstance(trace.get('path'), str) and bool(trace['path']) and
                    type(trace.get('count')) is int and trace['count'] == 32, 'incomplete water branch trace')
            trace_raw = artifact_loader(trace['path'])
            require(isinstance(trace_raw, bytes) and bool(trace_raw) and digest(trace_raw) == trace.get('sha256'),
                    'water branch trace hash mismatch')
            branch_binding = {'sha256': native['sha256'], 'branch': branch, 'source_logic': logic,
                              'source_logic_sha256': proof['source_logic_sha256'], 'source_offset': offset,
                              'opcode': opcode, 'argument': argument,
                              'writer': {k: writer[k] for k in ('offset', 'resume_offset')},
                              'trace': {'sha256': trace['sha256'], 'count': trace['count']}}
        messages = action.get('messages')
        require(isinstance(messages, list), 'missing message observations')
        texts = []
        for msg in messages:
            require(isinstance(msg, dict) and msg.get('status') == 'completed' and msg.get('handler_return_observed') is True and
                    msg.get('input_settled') is True and msg.get('window_closed') is True, 'incomplete message boundary')
            logic, offset, number = msg.get('logic'), msg.get('source_offset'), msg.get('message_id')
            require(type(logic) is int and logic in resources and type(offset) is int and offset >= 0 and
                    type(number) is int and 1 <= number <= 255, 'invalid source message binding')
            resource = resources[logic]
            require(resource.code[offset:offset+2] == bytes((101, number)), 'message instruction mismatch')
            text = logic_messages(resource)[resource.resource_sha256].get(str(number))
            require(isinstance(text, str) and bool(text), 'missing source message')
            frame(msg.get('frame'))
            texts.append(text)
        if native_binding is not None:
            expected_messages=[(103,offset,resources[103].code[offset+1])
                               for offset in native_binding['source_offsets'] if resources[103].code[offset]==101]
            captured_messages=[(m['logic'],m['source_offset'],m['message_id']) for m in messages if m['logic']==103]
            require(captured_messages==expected_messages,'native message capture count or identity differs')
        if action['id'] == 'troll-bridge':
            captured_messages = [(m['logic'], m['source_offset'], m['message_id']) for m in messages if m['logic'] == 25]
            require(captured_messages == [(25, 0x14c, 1), (25, 0x16a, 2), (25, 0x19f, 30)],
                    'bridge message capture count or identity differs')
        if water and index == 2:
            captured_messages = [(m['logic'], m['source_offset'], m['message_id']) for m in messages if m['logic'] == 103]
            require(captured_messages == [(103, 375, 1)], 'water refusal message capture count or identity differs')
        checked.append((action, before, after, after_visible, texts, native_binding, score_binding, branch_binding))
    variables = {'$phase': {'type': 'u8', 'initial': 0}}
    for field in fields:
        variables['$' + field] = {'type': 'bool' if type(initial[field]) is bool else 'u8', 'initial': initial[field]}
    programs = {}
    for i, (action, before, after, _, texts, _, _, _) in enumerate(checked):
        body = [{'id': 'guard-phase', 'op': 'require', 'condition': {'op': 'eq', 'left': {'var': '$phase'}, 'right': i}}]
        for name, value in before.items():
            if name in fields:
                body.append({'id': 'guard-' + name, 'op': 'require', 'condition': {'op': 'eq', 'left': {'var': '$' + name}, 'right': value}})
        for name in fields:
            if before[name] != after[name]:
                body.append({'id': 'set-' + name, 'op': 'set', 'var': '$' + name, 'value': after[name]})
        body.append({'id': 'set-phase', 'op': 'set', 'var': '$phase', 'value': i + 1})
        text = '[Source message before runtime formatting] ' + '\n'.join(texts) if texts else 'The recorded action completes.'
        body.append({'id': 'message', 'op': 'text', 'resource': 'message'})
        programs[action['id']] = {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': variables,
                                   'resources': {'message': {'kind': 'text', 'text': text}}, 'body': body}
    contexts = [{'id': f'phase-{i}', 'title': 'Observed goat encounter',
                 'description': 'A partial reconstruction of a recorded encounter.',
                 'when': {'op': 'eq', 'left': {'var': '$phase'}, 'right': i}}
                for i in range(len(checked) + 1)]
    if bridge:
        contexts[-1]['title'] = 'Observed bridge cleared'
        contexts[-1]['description'] = 'A partial reconstruction of the supplied bridge outcome.'
    if water:
        contexts[3]['title'] = 'Observed water refusal'
        contexts[3]['description'] = 'A partial reconstruction of the supplied water refusal.'
        if len(checked) == 4:
            contexts[4]['title'] = 'Observed water departure'
            contexts[4]['description'] = 'A partial reconstruction of the supplied water departure.'
    objects = [{'id': 'carrot', 'context': 'phase-0', 'label': 'carrot', 'aliases': [],
                'description': 'A recorded carried item.', 'bindings': [],
                'inventory_when': {'op': 'eq', 'left': {'var': '$carrot_carried' if bridge or water else '$carrot'}, 'right': True}},
               {'id': 'goat', 'context': 'phase-0', 'label': 'goat', 'aliases': [],
                'description': 'The goat observed in the starting frame.',
                'bindings': [{'verb': 'use', 'item': 'carrot', 'program': 'show-carrot'}]}]
    if len(checked) >= 2:
        objects.append({'id': 'route', 'context': 'phase-1', 'label': 'route', 'aliases': [],
                        'description': 'The next recorded movement.',
                        'bindings': [{'verb': 'use', 'program': checked[1][0]['id']}]})
    if bridge:
        objects.append({'id': 'bridge', 'context': 'phase-2', 'label': 'bridge', 'aliases': [],
                        'description': 'The next recorded bridge encounter.',
                        'bindings': [{'verb': 'use', 'program': 'troll-bridge'}]})
    if water:
        objects.append({'id': 'water', 'context': 'phase-2', 'label': 'water', 'aliases': [],
                        'description': 'The next recorded water encounter.',
                        'bindings': [{'verb': 'use', 'program': 'lead-to-water'}]})
        if len(checked) == 4:
            objects.append({'id': 'exit', 'context': 'phase-3', 'label': 'exit', 'aliases': [],
                            'description': 'The recorded departure from the water room.',
                            'bindings': [{'verb': 'use', 'program': 'leave-water'}]})
    scene = {'format': 'fdisbull-il-scene-1', 'programs': programs, 'contexts': contexts,
             'objects': objects, 'partial': True}
    ILSceneBackend(scene)
    provenance = {'format': 'fdisbull-agi-natural-z-evidence-1', 'source': identity,
                  'capture_sha256': digest(json.dumps(capture, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()),
                  'frames': frames, 'edges': [{'id': a['id'], 'before': a['before'], 'after': a['after'],
                                               'messages': [{k: m[k] for k in ('logic', 'source_offset', 'message_id')} for m in a['messages']],
                                               **({'native_invocation': native} if native else {}),
                                               **({'native_score_write': score} if score else {}),
                                               **({'native_branch_effect': branch} if branch else {})}
                                              for a, _, _, _, _, native, score, branch in checked],
                  'scope': 'Supplied ordinary-play observations; hashes do not authenticate capture or establish general gameplay behavior. Text commands are authored projections. Partial coverage; no native execution or durable save.'}
    return scene, provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--artifacts', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output, source, root = args.output.resolve(), args.source.resolve(), args.artifacts.resolve()
    checkout = Path(__file__).resolve().parents[2]
    require(not output.exists() and output != checkout and checkout not in output.parents and
            output != source and source not in output.parents and output not in source.parents and
            output != root and root not in output.parents and output not in root.parents, 'output must be a fresh private directory')
    def load(path):
        target = (root / path).resolve()
        require(root in target.parents and target.is_file(), 'frame path outside artifact directory')
        return target.read_bytes()
    scene, evidence = build(source, json.loads(args.capture.read_text()), load)
    output.mkdir(parents=True, exist_ok=False)
    raw = (json.dumps(scene, ensure_ascii=False, indent=2) + '\n').encode()
    (output / 'scene.json').write_bytes(raw)
    evidence['scene_sha256'] = digest(raw)
    (output / 'provenance.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({'scene': str(output / 'scene.json'), 'provenance': str(output / 'provenance.json')}))


if __name__ == '__main__':
    main()
