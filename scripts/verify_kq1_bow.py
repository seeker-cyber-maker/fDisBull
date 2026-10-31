#!/usr/bin/env python3
"""Execute court UIL against original LOGIC bytes and optional native evidence.

Inputs and native observations stay private. The output contains selected
identities, comparison counts and limits, never game code, prose or raw states.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.agi_slice import run_slice
from fdisbull.court_adapter import CourtRuntime
from fdisbull.kq1_bow import recover_bow, SOURCE_ENTRY, SOURCE_STOP


def initial_state(x, y, *, words=(239, 208), score=1, invisible=False,
                  visited=False, awarded=False, complete=False):
    state = {'variables': [0] * 256, 'flags': [False] * 256,
             'ego': {'x': x, 'y': y}, 'words': list(words), 'player_control': not complete}
    state['variables'][0], state['variables'][3] = 53, score
    for number, value in {2: bool(words), 24: visited, 168: awarded, 79: invisible,
                          22: complete, 98: complete}.items():
        state['flags'][number] = value
    return state


def compare_case(runtime, payload, state, counts):
    original = copy.deepcopy(state)
    reference = run_slice(payload, state, entry=SOURCE_ENTRY, stop=SOURCE_STOP)
    candidate = runtime.step(state)
    if state != original:
        raise ValueError('An evaluator changed caller-owned input')
    for phase in range(4):
        if (reference['state'] != candidate['state'] or reference['effects'] != candidate['effects']
                or reference['status'] != ('complete' if candidate['status'] == 'slice_complete' else candidate['status'])):
            raise ValueError('Original source and UIL differ at a dispatch/modal boundary')
        counts['segments_compared'] += 1
        counts['source_actions_compared'] += len(reference['effects'])
        for intent in candidate['executed_intents']:
            counts['intent:' + intent] += 1
        if reference['status'] == 'complete':
            return
        counts['modal_acknowledgements'] += 1
        # A declared host-clock advance tests ownership, not elapsed-time physics.
        reference['state']['variables'][11] = (reference['state']['variables'][11] + 1) % 60
        candidate['state']['variables'][11] = reference['state']['variables'][11]
        reference = run_slice(payload, reference['state'], entry=reference['pc'], stop=SOURCE_STOP)
        candidate = runtime.step(candidate['state'], {'kind': 'ack', 'continuation': candidate['continuation']})
    raise ValueError('Unexpected modal count in bounded interaction')


def source_matrix(runtime, payload):
    counts = Counter()
    positions = product((17, 18, 59, 60, 67, 68, 79, 80, 86, 87, 153),
                        (79, 80, 84, 85, 107, 108, 113, 114))
    for (x, y), words, invisible, visited, awarded, score in product(
            list(positions), ((239,), (239, 208)), (False, True), (False, True),
            (False, True), (0, 1, 252, 254, 255)):
        compare_case(runtime, payload, initial_state(x, y, words=words, score=score,
                     invisible=invisible, visited=visited, awarded=awarded), counts)
        counts['command_cases'] += 1
    for x, y, words, invisible, score in product((11, 60, 61, 63, 79),
            (80, 107, 108, 110, 113), ((), (239,), (239, 208)), (False, True), (0, 254, 255)):
        compare_case(runtime, payload, initial_state(x, y, words=words, score=score,
                     invisible=invisible, visited=True, awarded=True, complete=True), counts)
        counts['completion_and_tie_cases'] += 1
    for field, number, value in [('variables', 0, 54), ('variables', 74, 3),
            ('variables', 30, 1), ('variables', 70, 1), ('variables', 71, 1),
            ('variables', 21, 1), ('flags', 5, True), ('flags', 15, True),
            ('flags', 27, True), ('flags', 194, True), ('flags', 195, True)]:
        state = initial_state(70, 110)
        state[field][number] = value
        result = runtime.step(state)
        if result['status'] != 'unrecovered' or result['state'] != state or result['effects']:
            raise ValueError('Unsupported source context was not retained without semantic effects')
        counts['explicit_context_refusals'] += 1
    return dict(sorted(counts.items()))


def checked_native_state(receipt, root, name):
    record = receipt['states'][name]
    identity = record['source_snapshot']
    if Path(identity['filename']).name != identity['filename']:
        raise ValueError('Native snapshot must have a local basename')
    raw = (root / identity['filename']).read_bytes()
    if len(raw) != identity['size'] or sha256(raw).hexdigest() != identity['sha256']:
        raise ValueError('Native snapshot identity changed')
    snapshot = json.loads(raw)
    memory = bytes.fromhex(snapshot['raw_data']['hex'])
    actor = bytes.fromhex(snapshot['raw_actor']['hex'])
    if (sha256(memory).hexdigest() != snapshot['raw_data']['sha256'] or
            sha256(actor).hexdigest() != snapshot['raw_actor']['sha256']):
        raise ValueError('Native raw-read identity changed')
    if len(memory) < 297 or len(actor) < 15:
        raise ValueError('Truncated native carrier observation')
    variables = list(memory[9:265])
    flags = [bool(memory[265 + n // 8] & (0x80 >> (n % 8))) for n in range(256)]
    ego = {'x': int.from_bytes(actor[3:5], 'little'),
           'y': int.from_bytes(actor[5:7], 'little')}
    pose = {'view': actor[7], 'loop': actor[10], 'cel': actor[14]}
    supplied = record['source_state']
    if variables != supplied['variables'] or flags != supplied['flags'] or any(
            ego[key] != supplied['ego'][key] for key in ego) or any(
                pose[key] != supplied['ego'][key] for key in pose):
        raise ValueError('Derived native state disagrees with raw observations')
    return {'variables': variables, 'flags': flags, 'ego': ego}, pose


def native_comparisons(runtime, receipt_path):
    raw = receipt_path.read_bytes()
    receipt = json.loads(raw)
    if (receipt['format'] != 'private-kq1-bow-native-reference-1' or receipt['status'] != 'passed'
            or receipt['fresh_native_execution'] is not True or receipt['input_files_unchanged'] is not True):
        raise ValueError('Native receipt is not the qualified fresh reference')
    field_map = receipt['field_interpretation']
    if (field_map['variable_base_offset'] != 9 or field_map['flag_base_offset'] != 265 or
            field_map['flag_mask'] != '0x80 >> (flag_index % 8)'):
        raise ValueError('Native carrier layout differs from the observed profile')
    inputs = {row['name'].upper(): row for row in receipt['inputs']}
    source = runtime.package['low_level_ir']['source']
    for section in ('directories', 'volumes', 'auxiliary'):
        for row in source[section]:
            if 'sha256' in row and inputs[row['filename'].upper()]['sha256'] != row['sha256']:
                raise ValueError('Native and recovered resource identities differ')
    comparisons = []
    # The first two use directly observed dispatch/completion flags. The latter
    # two bridge an explicit typed command from an earlier native observation.
    pairs = [('bow_admission', 'dispatch-watch-2', 'dispatch-watch-7', False, None),
             ('bow_completion', 'bow-phase-14', 'bow-phase-15', False, 4),
             ('distant_refusal', 'throne-entry', 'far-refusal-modal', True, 14),
             ('completed_repeat', 'bow-resumed', 'repeat-modal', True, 55)]
    variables, flags = (3, 6, 31, 60, 61), (4, 21, 22, 24, 98, 168)
    for name, before, after, bridge_input, message in pairs:
        start, _ = checked_native_state(receipt, receipt_path.parent, before)
        finish, observed_pose = checked_native_state(receipt, receipt_path.parent, after)
        for control in (False, True):
            state = copy.deepcopy(start)
            state['player_control'] = control
            state['words'] = [] if name == 'bow_completion' else [239, 208]
            if bridge_input:
                state['flags'][2], state['flags'][4] = True, False
            result = runtime.step(state)
            if result['status'] == 'unrecovered':
                raise ValueError('Native boundary lies outside the qualified intent')
            actual = result['state']
            if (any(actual['variables'][n] != finish['variables'][n] for n in variables)
                    or any(actual['flags'][n] != finish['flags'][n] for n in flags)
                    or actual['ego'] != finish['ego']):
                raise ValueError(f'UIL differs from observed native fields for {name}')
            printed = [row['operands'][0] for row in result['effects'] if row['operation'] == 'print']
            if printed != ([] if message is None else [message]):
                raise ValueError('UIL response request differs from native reference')
        comparisons.append({'boundary': name, 'matched': True,
                            'input_flags': 'explicit_parser_bridge' if bridge_input else 'native_observed',
                            'unbound_control_alternatives_checked': 2,
                            'observed_pose': observed_pose})
    for case, resource in (('far_refusal', 'distant'), ('initial_bow', 'response'),
                           ('completed_repeat', 'repeat')):
        binding = runtime.package['udl']['resource_bindings'][resource]
        observed = receipt['cases'][case]
        if (binding['number'] != observed['logic_message'] or
                binding['text_sha256'] != observed['source_message_text_sha256']):
            raise ValueError('Native visual output reference differs from bound narrative')
    animation = [checked_native_state(receipt, receipt_path.parent, name)[1]
                 for name in receipt['states'] if name.startswith('bow-phase-')]
    cels = sorted({pose['cel'] for pose in animation if pose['view'] == 71})
    _, modal_pose = checked_native_state(receipt, receipt_path.parent, 'bow-phase-15')
    _, resumed_pose = checked_native_state(receipt, receipt_path.parent, 'bow-resumed')
    return {'receipt_sha256': sha256(raw).hexdigest(), 'fresh_native_cases': 3,
            'model_boundary_comparisons': comparisons,
            'compared_variables': list(variables), 'compared_flags': list(flags),
            'compared_actor_fields': ['x', 'y'],
            'native_player_control_field': 'unbound; both Boolean alternatives checked',
            'parsed_groups': 'declared typed command plus source-correlated native buffer; parser outside model',
            'output': 'bound message requests and source text hashes match visually checked native frames; no OCR claim',
            'animation_cels_observed': cels,
            'native_completion_pose': {'modal': modal_pose, 'resumed_sample': resumed_pose},
            'timing': receipt['animation_timing'],
            'host_timing_reimplemented': False, 'native_renderer_replaced': False,
            'native_backend_sha256': receipt['backend']['sha256']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game_dir', type=Path)
    parser.add_argument('--native-receipt', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    files = [ROOT / 'src/fdisbull' / name for name in
             ('court_intents.py', 'court_adapter.py', 'kq1_bow.py', 'agi_slice.py', 'cli.py')]
    files.append(Path(__file__).resolve())
    identities = {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest() for path in files}
    package = recover_bow(args.game_dir)
    runtime = CourtRuntime(package)
    matrix = source_matrix(runtime, bytes.fromhex(package['source_logic']['payload']))
    native = native_comparisons(runtime, args.native_receipt) if args.native_receipt else None
    if identities != {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest() for path in files}:
        raise ValueError('Implementation changed during verification')
    report = {'format': 'fdisbull-kq1-bow-verification-1', 'status': 'passed',
              'bindings': runtime.bindings, 'source_matrix': matrix, 'native_reference': native,
              'implementation_sha256': identities,
              'claim': ('one bounded initial-audience interaction: intent execution and source-state/request equivalence'
                        + (', with selected native observations' if native is not None else '; source-only verification')),
              'all_game_intent_recovered': False, 'complete_game_player': False,
              'source_scope': 'selected dispatch segment; original parser, room/global scheduler and host engine remain outside the evaluator'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'status': 'passed', 'source_matrix': matrix,
                      'native_boundaries': len(native['model_boundary_comparisons']) if native else 0}, sort_keys=True))


if __name__ == '__main__':
    main()
