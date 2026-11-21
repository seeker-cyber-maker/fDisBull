"""Apply explicit scene policy to an existing native draw-intent packet.

The packet retains authoritative stopped QEMU state. This detached result is a
Sarien-derived seeded preview, never a completion receipt for that guest.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from draw_intent_trial import validate_intent, validate_intent_journal, validate_intent_reset
from sarien_scene import ANIMATED, IGNORE_HORIZON, SceneInputError


def _read(directory, name, maximum):
    if not isinstance(name, str) or not name or Path(name).name != name or '\\' in name:
        raise SceneInputError('Packet filenames must be single relative components')
    path = directory / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise SceneInputError('Missing, indirect or oversized packet input')
    return path.read_bytes()


def _raw(values):
    if type(values) is not list or len(values) > 65536 \
            or any(type(value) is not int or not 0 <= value <= 255 for value in values):
        raise SceneInputError('Invalid packet instruction bytes')
    return bytes(values)


def _endpoint(packet, state, code):
    """Bind the declared packet endpoint to the actual stopped guest."""
    guest = state['guest']
    declaration = packet['execution_endpoint']
    kind = declaration.get('kind')
    if kind == 'authored_return':
        if guest['status'] != 'return' or guest['pc'] != len(code) \
                or guest['pending_effect'] is not None or guest['fault'] is not None:
            raise SceneInputError('Packet did not complete its authored return')
        expected = {'kind': kind, 'fragment_pc': len(code) - 1, 'bytes': [0],
                    'original_source_address': None, 'retired': True, 'committed': True}
        request = None
    elif kind == 'pending_draw':
        if not packet['sites']:
            raise SceneInputError('Pending draw requires an exact final source site')
        last, pending = packet['sites'][-1], guest['pending_effect']
        if guest['status'] != 'effect' or pending is None \
                or guest['pc'] != last['fragment_pc'] or last['opcode'] != 35 \
                or pending['bytes'] != last['bytes'] \
                or pending['actor'] not in packet['selected_actors']:
            raise SceneInputError('Packet did not stop at its declared pending draw')
        expected = {'kind': kind, **last, 'retired': False, 'committed': False}
        request = {'native_descriptor': pending, 'source': state['source'],
                   'site': last, 'committed_pose': guest['actors'][pending['actor']],
                   'position_repair_completed': False, 'sprite_buffers_updated': False,
                   'presentation_established': False,
                   'unresolved': ['position_repair', 'collision_and_priority_effects',
                                  'sprite_composition', 'presentation']}
    else:
        raise SceneInputError('Unknown packet endpoint')
    # JSON comparison also distinguishes boolean declarations from integer aliases.
    if json.dumps(declaration, sort_keys=True) != json.dumps(expected, sort_keys=True) \
            or json.dumps(packet['draw_request'], sort_keys=True) != json.dumps(request, sort_keys=True):
        raise SceneInputError('Packet endpoint or draw request contradicts native state')
    return kind


def preview_packet(kernel, packet_directory, *, bands, actor_policy, max_attempts=4096):
    """Verify and consume one packet using explicit missing-state assumptions.

    actor_policy maps every actor ID to {flags, priority}. Flags specify only
    fields absent from the native profile; animation and horizon flags come
    from native state. Priority bands and prior drawn/peer/terrain flags are
    caller assumptions. The packet's external preview order is retained.
    """
    directory = Path(packet_directory).expanduser().resolve(strict=True)
    raw_packet = _read(directory, 'packet.json', 2 * 1024**2)
    packet = json.loads(raw_packet)
    if packet.get('schema') != 'fdisbull-agi-draw-intent-packet-1':
        raise SceneInputError('Unsupported scene packet')
    prelude = _raw(packet['entry']['load_prologue_bytes'])
    code = bytearray(prelude)
    for site in packet['sites']:
        if type(site.get('fragment_pc')) is not int or site['fragment_pc'] != len(code):
            raise SceneInputError('Packet source mapping is not contiguous')
        code.extend(_raw(site['bytes']))
    if _raw(packet['entry']['authored_return_bytes']) != b'\x00' or len(code) >= 65536:
        raise SceneInputError('Packet authored return or code size differs')
    code.append(0)
    code = bytes(code)
    catalog = _read(directory, packet['catalog']['file'], 65536)
    state = packet['native']['snapshot']
    initial = packet['entry']['initial_snapshot']
    validate_intent_reset(initial, code=code, catalog=catalog)
    validate_intent(state, code=code, catalog=catalog)
    endpoint = _endpoint(packet, state, code)
    journal = validate_intent_journal(initial, state, packet['native']['observations'],
        prepared={'prelude': prelude, 'code': code, 'sites': packet['sites'],
                  'spec': {'endpoint': endpoint}})
    guest = state['guest']
    native_before = deepcopy(guest)
    if type(actor_policy) is not dict or any(type(key) is not int for key in actor_policy) \
            or set(actor_policy) != {row['id'] for row in guest['actors']}:
        raise SceneInputError('Every native actor requires an explicit scene policy')
    actors = []
    for native in guest['actors']:
        policy = actor_policy[native['id']]
        if type(policy) is not dict or set(policy) != {'flags', 'priority'} \
                or type(policy['flags']) is not int or not 0 <= policy['flags'] <= 255 \
                or policy['flags'] & (ANIMATED | IGNORE_HORIZON) \
                or type(policy['priority']) is not int or not 0 <= policy['priority'] <= 15:
            raise SceneInputError('Scene policy must not override native-known flags')
        flags = policy['flags'] | (ANIMATED if native['animated'] else 0) \
                | (IGNORE_HORIZON if native['ignore_horizon'] else 0)
        actors.append({**{key: native[key] for key in
                         ('id', 'x', 'y', 'prev_x', 'prev_y', 'width', 'height')},
                       'flags': flags, 'priority': policy['priority']})
    assets, identities = {}, {}
    def asset(name):
        if name not in assets:
            metadata = packet['assets'][name]
            data = _read(directory, name, 160 * 168)
            if metadata['file'] != name or type(metadata['bytes']) is not int \
                    or len(data) != metadata['bytes'] or sha256(data).hexdigest() != metadata['sha256']:
                raise SceneInputError('Packet asset identity differs')
            assets[name] = data
            identities[name] = {'bytes': len(data), 'sha256': sha256(data).hexdigest()}
        return assets[name]
    order = packet['render_contract']['draw_order']
    if type(order) is not list or not order or len(order) > 16 \
            or any(type(number) is not int or not 0 <= number < 16 for number in order) \
            or len(order) != len(set(order)) or order != packet['selected_actors']:
        raise SceneInputError('Packet preview order differs from the selected actor list')
    layers = []
    for number in order:
        actor = guest['actors'][number]
        matches = [cel for cel in packet['cel_assets']
                   if (cel['view'], cel['loop'], cel['cel']) ==
                      (actor['view'], actor['loop'], actor['cel'])]
        if not actor['view_bound'] or len(matches) != 1:
            raise SceneInputError('Preview actor lacks one unambiguous bound cel')
        cel = matches[0]
        if (cel['width'], cel['height']) != (actor['width'], actor['height']):
            raise SceneInputError('Cel geometry differs from native binding')
        layers.append({'actor_id': number, 'cel': asset(cel['asset']),
                       'transparent': cel['transparent_color']})
    result = kernel.preview(asset('background.idx'), asset('priority.idx'), bands,
                            horizon=guest['horizon'], actors=actors, layers=layers,
                            max_attempts=max_attempts)
    if guest != native_before or _read(directory, 'packet.json', 2 * 1024**2) != raw_packet:
        raise SceneInputError('Native packet changed during preview')
    for name, data in assets.items():
        if _read(directory, name, 160 * 168) != data:
            raise SceneInputError('Packet asset changed during preview')
    result.update(schema='fdisbull-agi-seeded-priority-preview-1',
        packet_sha256=sha256(raw_packet).hexdigest(), library_sha256=kernel.binary_sha256,
        native_source=deepcopy(state['source']), native_endpoint=endpoint,
        native_guest_unchanged=True, original_room_state_qualified=False,
        policy={'actor_policy': deepcopy(actor_policy), 'priority_bands': list(bands),
                'draw_order': list(order), 'max_attempts_per_actor': max_attempts,
                'selection_basis': 'explicit_seeded_preview_not_native_draw_completion'},
        input_assets=identities, journal_validation=journal,
        pending_effect=deepcopy(guest['pending_effect']))
    return result
