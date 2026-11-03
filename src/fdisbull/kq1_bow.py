"""Exact-source producer for one KQ1 audience interaction and its UDL.

Original resource bytes and messages are read from the caller's private game.
The complete scene census remains unchanged low-level IR. This module checks
source bindings; it does not execute the native engine, renderer or scheduler.
Opcode semantics are independently referenced in the pinned ScummVM AGI
sources listed in ``_ENGINE_SOURCE``; no interpreter implementation is copied.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from .agi_resources import V2Resources, logic_messages
from .agi_scenes import _decode, inspect_scenes
from .court_intents import build_definition, canonical_digest, validate_intent
from .zork_uil import _private_destination, write_document


FORMAT = 'fdisbull-kq1-bow-package-1'
UDL_FORMAT = 'fdisbull-kq1-bow-udl-1'
PROFILE = '2.917'
SOURCE_ENTRY = 0x1b8
SOURCE_STOP = 0x460
MESSAGE_BINDINGS = {'response': 4, 'invisible': 7, 'improper_position': 6,
                    'repeat': 55, 'distant': 14}

# These are identities, not embedded original game data. Qualifying another
# edition requires source review, not a package-supplied override. Tests replace
# this internal profile only for explicitly unqualified, authored fixtures.
_EDITION = {
    'id': 'kq1-dos-agi-2.917-pinned-resources',
    'qualification': 'exact_original_resource_identity',
    'logic_source': {'kind': 'logic', 'number': 53, 'volume': 1,
                     'offset': 177640, 'status': 'ok', 'length': 4707,
                     'sha256': '672b526d9606dbc59221c96b95f56556da581a5db1c1b73b8761e1c860d7f3bd'},
    'manifest_sha256': '050d6a10650241a117112ef6200fb917eb8380fe954c9e2b5d7b1633e53cb784',
    'census_sha256': '5f86e87107c351be9e8bb4f472124f2ebb7f10cf2d29b1b53a6eb44840ca3f03',
}

FIELD_BINDINGS = {
    'score': {'space': 'agi_variable', 'number': 3, 'type': 'byte'},
    'direction': {'space': 'agi_variable', 'number': 6, 'type': 'byte'},
    'sequence_countdown': {'space': 'agi_variable', 'number': 30, 'type': 'byte', 'room': 53},
    'treasure_count': {'space': 'agi_variable', 'number': 74, 'type': 'byte'},
    'bowed_this_visit': {'space': 'agi_flag', 'number': 24, 'type': 'boolean', 'room': 53},
    'respect_awarded': {'space': 'agi_flag', 'number': 168, 'type': 'boolean'},
    'invisible': {'space': 'agi_flag', 'number': 79, 'type': 'boolean'},
    'standing_animation': {'space': 'agi_flag', 'number': 98, 'type': 'boolean'},
    'bow_complete': {'space': 'agi_flag', 'number': 22, 'type': 'boolean', 'room': 53},
    'input_ready': {'space': 'agi_flag', 'number': 2, 'type': 'boolean'},
    'input_consumed': {'space': 'agi_flag', 'number': 4, 'type': 'boolean'},
    'player_control': {'space': 'agi_interpreter', 'field': 'player_control', 'type': 'boolean'},
    'actor_x': {'space': 'agi_actor', 'number': 0, 'field': 'x', 'type': 'byte'},
    'actor_y': {'space': 'agi_actor', 'number': 0, 'field': 'y', 'type': 'byte'},
}

QUALIFICATION = {
    'scope': 'initial_audience_bow_dispatch_segment', 'profile': PROFILE,
    'variables_equal': {'0': 53, '21': 0, '30': 0, '70': 0, '71': 0},
    'variables_not_equal': {'74': 3},
    'flags_equal': {'5': False, '15': False, '27': False,
                    '194': False, '195': False},
    'modal_host_mutable_variables': [11, 12, 13, 14],
    'caller_obligations': [
        'established room after room-entry initialization',
        'no earlier LOGIC0 death handler or other return bypasses room dispatch',
        'source entry is after the retained room-ending scheduler prefix',
        'animation completion is supplied by the qualified actor scheduler',
        'ordinary blocking print: f15=false and v21=0',
        'modal acknowledgement resumes the suspended dispatch before any new cycle',
    ],
    'scope_bounds': 'engine requests and dispatch effects, not a standalone renderer or timer',
    'native_execution_verified': False, 'all_game_intent_recovered': False,
}

BLOCK_SPANS = {
    'refresh_position_flag': [0x1b8, 0x1c9],
    'near_geometry': [0x1c9, 0x1d3],
    'near_input_claim': [0x20d, 0x21d],
    'invisible_guard_and_response': [0x21d, 0x228],
    'improper_position_guard_and_response': [0x228, 0x236],
    'begin_guard': [0x236, 0x24b],
    'begin_bow': [0x24b, 0x26f],
    'award_first_respect': [0x26f, 0x27b],
    'quest_return_bow_retained_ir': [0x27e, 0x2c5],
    'repeat_response': [0x2c5, 0x2c7],
    'king_talk_retained_ir': [0x2c7, 0x374],
    'far_geometry_and_countdown': [0x374, 0x38a],
    'far_input_claim': [0x3a2, 0x3b2],
    'distant_response': [0x3b2, 0x3b4],
    'completion_guard': [0x428, 0x42e],
    'finish_bow': [0x42e, 0x44f],
    'completion_response': [0x44f, 0x451],
    'completion_ending_retained_ir': [0x451, 0x460],
}

GEOMETRY_BINDINGS = {
    'coordinates': 'inclusive_actor_base_position', 'actor': 0,
    'addressing': {'rectangle': [18, 80, 86, 113], 'source_offset': 0x1c9},
    'improper_position': {'rectangle': [18, 80, 67, 107], 'source_offset': 0x1b8},
    'distance_reference': {'rectangle': [60, 85, 86, 113], 'source_offset': 0x374},
}

ENGINE_REQUESTS = {
    'court.begin_bow': [
        {'operation': 'erase', 'operands': [0]},
        {'operation': 'stop.motion', 'operands': [0]},
        {'operation': 'set.view', 'operands': [0, 71]},
        {'operation': 'set.cel', 'operands': [0, 0]},
        {'operation': 'position.v', 'operands': [0, 60, 61]},
        {'operation': 'cycle.time', 'operands': [0, 31]},
        {'operation': 'draw', 'operands': [0]},
        {'operation': 'end.of.loop', 'operands': [0, 22]},
    ],
    'court.finish_bow': [
        {'operation': 'erase', 'operands': [0]},
        {'operation': 'set.loop', 'operands': [0, 1]},
        {'operation': 'set.view', 'operands': [0, 0]},
        {'operation': 'position.v', 'operands': [0, 60, 61]},
        {'operation': 'cycle.time', 'operands': [0, 31]},
        {'operation': 'draw', 'operands': [0]},
        {'operation': 'start.motion', 'operands': [0]},
    ],
}

_ENGINE_COMMIT = 'f7403b6efaae2f033e8abea80b3fb6bee5303369'
_ENGINE_SOURCE = {
    name: f'https://github.com/scummvm/scummvm/blob/{_ENGINE_COMMIT}/engines/agi/{name}'
    for name in ('agi.h', 'op_test.cpp', 'op_cmd.cpp', 'view.cpp', 'cycle.cpp', 'text.cpp')
}


def _equal(actual, expected, label):
    # Canonical JSON also distinguishes bool from int, unlike Python equality.
    if canonical_digest(actual) != canonical_digest(expected):
        raise ValueError(f'{label} changed or is not the qualified binding')


def _resources(payload):
    messages = {row['number']: row for row in logic_messages(payload)}
    bindings = {}
    for name, number in MESSAGE_BINDINGS.items():
        row = messages.get(number)
        if not row or row['text'] is None:
            raise ValueError(f'Missing bound LOGIC53 message {number}')
        bindings[name] = {'logic': 53, **row}
    return bindings


def _witnesses(payload, instructions):
    result = {}
    for name, (start, end) in BLOCK_SPANS.items():
        rows = [row for row in instructions if start <= row['offset'] < end]
        if not rows or rows[0]['offset'] != start or rows[-1]['end_offset'] != end:
            raise ValueError(f'Source block {name} is not instruction aligned')
        raw = payload[start:end]
        result[name] = {
            'space': 'agi_logic_payload', 'logic': 53,
            'resource_sha256': sha256(payload).hexdigest(),
            'start': start, 'end': end, 'bytes': raw.hex(),
            'sha256': sha256(raw).hexdigest(), 'instructions': rows,
        }
    return result


def _make_udl(payload, census, definition, instructions):
    return {
        'format': UDL_FORMAT, 'profile': PROFILE,
        'source': {'edition': _EDITION['id'],
                   'qualification': _EDITION['qualification'],
                   'logic': deepcopy(_EDITION['logic_source']),
                   'manifest': deepcopy(census['source'])},
        'source_logic_sha256': sha256(payload).hexdigest(),
        'uil_sha256': canonical_digest(definition),
        'low_level_ir_sha256': canonical_digest(census),
        'source_entry': SOURCE_ENTRY, 'source_stop': SOURCE_STOP,
        'qualification': deepcopy(QUALIFICATION),
        'field_bindings': deepcopy(FIELD_BINDINGS),
        'resource_bindings': _resources(payload),
        'command_bindings': {'bow_to_king': [239, 208], 'bow': [239]},
        'parser_contract': {'test': 'ordered_stateful_said',
                            'requires': {'f2': True, 'f4': False},
                            'on_success': {'f4': True},
                            'ordered_alternatives': ['bow_to_king', 'bow']},
        'geometry_bindings': deepcopy(GEOMETRY_BINDINGS),
        'block_spans': deepcopy(BLOCK_SPANS),
        'witnesses': _witnesses(payload, instructions),
        'primitive_correspondences': {
            'input.claim': ['near_input_claim', 'far_input_claim'],
            'court.begin_bow': ['begin_guard', 'begin_bow'],
            'court.award_first_respect': ['award_first_respect'],
            'court.finish_bow': ['completion_guard', 'finish_bow'],
            'narration.modal': ['invisible_guard_and_response',
                                'improper_position_guard_and_response',
                                'repeat_response', 'distant_response',
                                'completion_response'],
        },
        'residual_correspondences': {'refresh_position_flag': 'refresh_position_flag'},
        'engine_requests': deepcopy(ENGINE_REQUESTS),
        'engine_contract': {
            'evidence': 'pinned_reference_interpreter_source; original native checks are separate',
            'sources': dict(_ENGINE_SOURCE),
            'stop_motion': 'actor direction=0, normal motion, v6=0, player_control=false',
            'start_motion': 'normal motion, v6=0, player_control=true; actor direction sync is later',
            'cycle_time': 'write both cycle period and remaining count from v31',
            'end_of_loop': 'clear completion flag; enable end cycler and skip next view update',
            'pose_order': 'preserve set.loop(0,1) before set.view(0,0); no generic loop clamping',
            'position': 'scratch v60/v61 read current actor coordinates; x shifts -7 then +7',
            'stationary_cycle': 'LOGIC0 consumes f98 to cycle ego when v6=0',
        },
        'print_mode': {'flag15': False, 'variable21': 0,
                       'boundary': 'yield at print and resume after real acknowledgement',
                       'clock': 'event and clock processing continues; room and actor cycles pause'},
        'phase_order': ['position_residual', 'command', 'completion'],
        'retained_ir': [
            'complete unmodified scene census including every original operation',
            'all-three-treasures bow and ending choreography',
            'king talk and quest dialogue',
            'room initialization, global dispatch and timers',
            'actor scheduler, rendering, modal clock and input implementation',
            'generic fallback when said does not consume input',
        ],
        'all_game_intent_recovered': False,
    }


def _check_census(census, payload):
    if not isinstance(census, dict) or canonical_digest(census) != _EDITION['census_sha256']:
        raise ValueError('Complete retained census identity changed')
    if canonical_digest(census.get('source')) != _EDITION['manifest_sha256']:
        raise ValueError('Exact KQ1 resource manifest is required')
    rows = [row for row in census.get('logics', []) if row.get('logic') == 53]
    if len(rows) != 1:
        raise ValueError('Retained census must contain one LOGIC53')
    row = rows[0]
    _equal(row['source'], _EDITION['logic_source'], 'Retained LOGIC53 source identity')
    _, instructions, _ = _decode(payload, 100000, 1048576)
    _equal(row.get('ir', {}).get('instructions'), instructions, 'Source operations')
    if (row.get('representation') != 'low_level_ir' or
            row.get('ir', {}).get('semantic_status') != 'all_operations_retained_as_low_level_ir'):
        raise ValueError('Original operations must remain low-level IR')
    return instructions


def recover_bow(game_dir):
    """Produce a private exact-edition UIL/UDL package with complete retained IR."""
    resources = V2Resources(game_dir)
    manifest = resources.manifest()
    if canonical_digest(manifest) != _EDITION['manifest_sha256']:
        raise ValueError('Exact qualified KQ1 resource set is required')
    rows = [row for row in resources.resources('logic') if row['number'] == 53]
    if len(rows) != 1 or rows[0]['status'] != 'ok':
        raise ValueError('Qualified LOGIC53 is unavailable')
    source = {key: value for key, value in rows[0].items() if key != 'payload'}
    _equal(source, _EDITION['logic_source'], 'Exact KQ1 LOGIC53 source identity')
    payload = rows[0]['payload']
    census = inspect_scenes(game_dir, profile=PROFILE, include_ir=True, include_text=True)
    # The two readers snapshot independently. A mutation between snapshots is
    # an explicit failure, never mixed source evidence.
    _equal(census['source'], manifest, 'Resource snapshot identity')
    instructions = _check_census(census, payload)
    bindings = _resources(payload)
    definition = validate_intent(build_definition({key: row['text'] for key, row in bindings.items()}))
    package = {
        'format': FORMAT, 'uil': definition,
        'udl': _make_udl(payload, census, definition, instructions),
        'low_level_ir': census,
        'source_logic': {'number': 53, 'payload': payload.hex(), 'sha256': sha256(payload).hexdigest()},
    }
    verify_bow_package(package)
    return package


def verify_bow_package(package):
    """Reconstruct every approved mapping from pinned source, not self-hashes.

    Recomputed package digests cannot authorize a different state binding,
    opcode, resource, qualification, intent definition or retained census.
    The receipt is static mapping evidence, not a native execution claim.
    """
    if (not isinstance(package, dict) or
            set(package) != {'format', 'uil', 'udl', 'low_level_ir', 'source_logic'} or
            package['format'] != FORMAT):
        raise ValueError('Invalid KQ1 bow package fields or format')
    source = package['source_logic']
    if (not isinstance(source, dict) or set(source) != {'number', 'payload', 'sha256'} or
            type(source['number']) is not int or source['number'] != 53 or
            not isinstance(source['payload'], str) or
            len(source['payload']) != _EDITION['logic_source']['length'] * 2):
        raise ValueError('Invalid bounded LOGIC53 source payload')
    try:
        payload = bytes.fromhex(source['payload'])
    except ValueError as error:
        raise ValueError('Invalid LOGIC53 hexadecimal source payload') from error
    digest = sha256(payload).hexdigest()
    if (len(payload) != _EDITION['logic_source']['length'] or
            digest != _EDITION['logic_source']['sha256'] or source['sha256'] != digest):
        raise ValueError('Exact qualified LOGIC53 payload identity is required')
    instructions = _check_census(package['low_level_ir'], payload)
    bindings = _resources(payload)
    expected = validate_intent(build_definition({key: row['text'] for key, row in bindings.items()}))
    _equal(package['uil'], expected, 'UIL source-derived definition')
    udl = _make_udl(payload, package['low_level_ir'], expected, instructions)
    _equal(package['udl'], udl, 'UDL source mapping or qualification')
    return {
        'source_logic_sha256': digest, 'uil_sha256': canonical_digest(expected),
        'low_level_ir_sha256': canonical_digest(package['low_level_ir']),
        'witness_count': len(udl['witnesses']), 'qualified_profile': PROFILE,
        'edition': _EDITION['id'], 'edition_qualification': _EDITION['qualification'],
        'verification': 'exact_source_and_mapping_bindings',
        'native_execution_verified': False, 'all_game_intent_recovered': False,
    }


def export_bow(game_dir, *, output, uil=None, udl=None):
    """Write private package and optional exact UIL/UDL views without replacing files."""
    targets = [Path(path).expanduser().resolve() for path in (output, uil, udl) if path]
    if len(set(targets)) != len(targets):
        raise ValueError('Output paths must be distinct')
    source_root = Path(game_dir).expanduser().resolve()
    if any(path == source_root or source_root in path.parents for path in targets):
        raise ValueError('Outputs must be separate from original game inputs')
    for path in targets:
        _private_destination(path)
    package = recover_bow(game_dir)
    receipt = verify_bow_package(package)
    outputs = {'package': write_document(output, package)}
    for name, destination in (('uil', uil), ('udl', udl)):
        if destination:
            outputs[name] = write_document(destination, package[name])
    return {'source': package['udl']['source'], 'bindings': receipt,
            'qualification': package['udl']['qualification'], 'outputs': outputs}
