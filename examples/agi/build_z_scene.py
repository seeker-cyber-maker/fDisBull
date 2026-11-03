"""Build a private diagnostic Z scene from an owned KQ1 resource and receipt.

The resulting independent probes are authored projections, not an AGI VM or
ordinary-play route. Do not commit the output: it contains game message text.
"""
import argparse
import hashlib
import json
from pathlib import Path

from fdisbull.agi import load_logic
from fdisbull.agi_resources import logic_messages
from fdisbull.il_scenes import ILSceneBackend

SOURCE = 'cb1293db23b0007712fdd6193bd590dbdfdbaa8a84698f16c56b70c1321cdaed'


def build(resource, receipt, erase_trial_bytes):
    if resource.logic != 103 or resource.profile != '2.917' or resource.resource_sha256 != SOURCE:
        raise ValueError('Unexpected logic source identity')
    if receipt.get('format') != 'fdisbull-agi-dos-host-verification-1' or receipt.get('source_logic_sha256') != SOURCE:
        raise ValueError('Receipt source identity mismatch')
    cases = {case['case']: case for case in receipt['cases']}
    for name, required in [('print', {450}), ('erase', {413, 427})]:
        case = cases[name]
        ops = {(op['source_offset'], op['operation']) for op in case['host_operations']}
        expected = {(450, 'print')} if name == 'print' else {(413, 'print'), (427, 'erase')}
        if (case['status'] != 'verified' or case['complete'] is not True or
            case['comparison_performed'] is not True or case['differences'] != [] or
            not required.issubset(case['source_offsets']) or not expected.issubset(ops)):
            raise ValueError('Native receipt does not qualify selected probe')
    digest = hashlib.sha256(erase_trial_bytes).hexdigest()
    if digest != cases['erase'].get('private_trial_sha256'):
        raise ValueError('Native trial hash mismatch')
    trial = json.loads(erase_trial_bytes)
    if (trial.get('status') != 'verified' or trial.get('complete') is not True or
        trial.get('native_execution') is not True or trial.get('differences') != [] or
        trial.get('identity', {}).get('resource_sha256') != SOURCE):
        raise ValueError('Native trial is not qualified for this source')
    attempts = [a for a in trial['attempts'] if a['offset'] == 427]
    if len(attempts) != 1 or attempts[0]['status'] != 'completed':
        raise ValueError('Missing completed native erase')
    before = bytes.fromhex(attempts[0]['raw_before']['object_13_hex'])
    after = bytes.fromhex(attempts[0]['raw_after']['object_13_hex'])
    if (len(before) != 43 or len(after) != 43 or
        not int.from_bytes(before[0x25:0x27], 'little') & 1 or
        int.from_bytes(after[0x25:0x27], 'little') & 1):
        raise ValueError('Native drawn flag transition not observed')
    for offset, expected in [(413, bytes([101, 2])), (427, bytes([36, 13])), (450, bytes([101, 1]))]:
        if resource.code[offset:offset + 2] != expected:
            raise ValueError('Source instruction mismatch')
    messages = logic_messages(resource)[SOURCE]
    variables = {'$object13_drawn': {'type': 'bool', 'initial': True}}
    def program(message, *, erase=False):
        body = [{'id': 'message', 'op': 'text', 'resource': 'message'}]
        if erase:
            body.insert(0, {'id': 'drawn-guard', 'op': 'require', 'condition': {'op': 'eq', 'left': {'var': '$object13_drawn'}, 'right': True}})
            body.append({'id': 'erase', 'op': 'set', 'var': '$object13_drawn', 'value': False})
        if erase:
            body.append({'id': 'erase-note', 'op': 'text', 'resource': 'erase-note'})
        resources = {'message': {'kind': 'text', 'text': message}}
        if erase:
            resources['erase-note'] = {'kind': 'text', 'text': '[Diagnostic observation: object 13 was erased.]'}
        return {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': variables,
                'resources': resources, 'body': body}
    scene = {'format': 'fdisbull-il-scene-1', 'partial': True,
             'programs': {'water': program(messages['1']), 'departure': program(messages['2'], erase=True)},
             'contexts': [{'id': 'probes', 'title': 'Goat: diagnostic probes',
                           'description': 'Two independent source-linked diagnostic observations.',
                           'when': {'op': 'eq', 'left': True, 'right': True}}],
             'objects': [
                 {'id': 'water', 'context': 'probes', 'label': 'water probe', 'aliases': ['water'],
                  'description': 'Read the recorded water message.', 'bindings': [{'verb': 'use', 'program': 'water'}]},
                 {'id': 'departure', 'context': 'probes', 'label': 'departure probe', 'aliases': ['departure'],
                  'description': 'Read the recorded departure message and erase observation.',
                  'bindings': [{'verb': 'use', 'program': 'departure'}]}]}
    ILSceneBackend(scene)  # Validate the actual consumer contract before export.
    provenance = {'format': 'fdisbull-agi-z-scene-evidence-1', 'source': resource.provenance(),
                  'native_receipt_sha256': hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                  'binding': {'water': {'case': 'print', 'message_id': 1, 'source_offsets': [450]},
                              'departure': {'case': 'erase', 'message_id': 2, 'source_offsets': [413, 427], 'native_trial_sha256': digest,
                                            'object_13_drawn': {'before': True, 'after': False}}},
                  'scope': 'Independent diagnostic invocations, not ordinary reachability or a sequential route. Print handler returned; visual content was not verified. Erase was a second diagnostic invocation. No blocking-dialogue completion claim.'}
    return scene, provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--erase-trial', type=Path, required=True, help='private native erase trial')
    parser.add_argument('--output', type=Path, required=True, help='new private output directory')
    args = parser.parse_args()
    output=args.output.resolve();source=args.source.resolve()
    checkout=Path(__file__).resolve().parents[2]
    if (output.exists() or output==checkout or checkout in output.parents or
        output==source or source in output.parents or output in source.parents):
        raise ValueError('Use a fresh private output directory outside source and checkout')
    resource = load_logic(args.source / 'LOGDIR', args.source, 103, profile='2.917')
    scene, evidence = build(resource, json.loads(args.receipt.read_text()), args.erase_trial.read_bytes())
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'scene.json').write_text(json.dumps(scene, indent=2) + '\n')
    evidence['scene_sha256'] = hashlib.sha256((args.output / 'scene.json').read_bytes()).hexdigest()
    (args.output / 'provenance.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({'scene': str(args.output / 'scene.json'), 'provenance': str(args.output / 'provenance.json')}))


if __name__ == '__main__':
    main()
