"""Authored JSON metadata only; no copied game worlds, assets or action code."""
from copy import deepcopy
import json

import pytest

from examples.scene_domains.world_adapters import (
    MAX_INPUT_BYTES, civilization_domains, load_world_json,
    syndicate_destination_inventory, syndicate_domains,
)
from fdisbull.scene_domains import audit_coordinate_domains


def syndicate():
    return {'schema': 'syndicate-diagnostic-scene-research-1',
        'source_state_sha256': 'a'*64, 'map_number': 7, 'selected': 'person-12',
        'coordinates': {'x_y_units_per_tile': 256, 'z_units_per_level': 128,
                        'screen_coordinates': False},
        'entities': [
            {'id': 'person-12', 'category': 'agent', 'position_raw': [320, 384, 129],
             'position': [1.25, 1.5, 129/128]},
            {'id': 'object-5', 'category': 'authored-role', 'position_raw': [320, 384, 256]}]}


def model(scene=None):
    return {'map_number': 7, 'dimensions': [3, 2, 4],
        'source_hashes': {'map': 'b'*64, 'classes': 'c'*64},
        'scene': syndicate() if scene is None else deepcopy(scene),
        'waypoints': [{'name': 'authored anchor', 'position': [1.25, 1.5, 2.25]}]}


def civ():
    return {'format': 'civ-world-0', 'dimensions': [80, 50],
        'source_state_sha256': 'd'*64,
        'source': {'edition': 'authored-unit-fixture', 'sve_sha256': 'e'*64,
                   'map_sha256': 'f'*64, 'map_file_sha256': '1'*64},
        'cities': [{'index': 3, 'x': 4, 'y': 9, 'name_raw': 'DO_NOT_COPY_THIS_FIELD'}],
        'units': [{'civ': 2, 'slot': 7, 'x': 4, 'y': 9},
                  {'civ': 3, 'slot': 7, 'x': 4, 'y': 9}],
        'resources': [{'x': 4, 'y': 9, 'special': 'unit-only label'}]}


def route():
    return {'format': 'syndicate-candidate-route-1', 'source_state_sha256': 'a'*64,
        'map_number': 7, 'plan_id': '2'*64, 'actor_id': 'person-12', 'target_id': 'object-5',
        'start_raw': [320, 384, 129], 'target_raw': [320, 384, 256],
        'approach_raw': [512, 384, 256], 'status': 'candidate_requires_validation',
        'qualification': 'conditional_model_only'}


def test_syndicate_keeps_exact_source_ids_raw_precision_elevation_and_unknown_bounds():
    scene = syndicate(); before = deepcopy(scene)
    doc = syndicate_domains(scene)
    assert scene == before
    assert doc['bounds'] == dict.fromkeys(('world', 'room', 'collision', 'viewport'))
    assert doc['space']['unit'] == '1/256 tile'
    assert [(o['id'], o['pose']) for o in doc['objects']] == [
        ('person-12', [320, 384]), ('object-5', [320, 384])]
    assert doc['objects'][1]['role'] == 'authored-role'
    bindings = doc['provenance']['object_bindings']
    assert bindings['person-12']['position_raw'] == [320, 384, 129]
    assert bindings['person-12']['elevation_layer'] == 1
    assert bindings['person-12']['elevation_remainder_raw'] == 1
    assert bindings['object-5']['z_raw'] == 256
    assert doc['expectations'] == []
    assert all(o['render'] is None and o['collision'] is None for o in doc['objects'])


def test_matching_map_bounds_are_world_only_in_raw_units():
    doc = syndicate_domains(syndicate(), map_model=model(), alerts=False)
    assert doc['bounds'] == {'world': [0, 0, 768, 512], 'room': None,
                             'collision': None, 'viewport': None}
    assert doc['provenance']['map_dimensions'] == [3, 2, 4]
    assert doc['provenance']['supplied_map_source_hashes'] == {'map': 'b'*64, 'classes': 'c'*64}
    result = audit_coordinate_domains(doc)
    assert result['complete'] is True
    assert all(r['relation'] == 'unknown' and r['absolute_bounds'] is None for r in result['relations'])
    assert all(r['anomaly_flag'] is False for r in result['relations'])


@pytest.mark.parametrize('fault', ('schema', 'units_float', 'screen_int', 'pose_bool',
    'display_disagrees', 'duplicate', 'missing_selected', 'alerts'))
def test_syndicate_refuses_ambiguous_selected_geometry(fault):
    scene = syndicate(); kwargs = {}
    if fault == 'schema': scene['schema'] = 'other'
    elif fault == 'units_float': scene['coordinates']['x_y_units_per_tile'] = 256.0
    elif fault == 'screen_int': scene['coordinates']['screen_coordinates'] = 0
    elif fault == 'pose_bool': scene['entities'][0]['position_raw'][0] = True
    elif fault == 'display_disagrees': scene['entities'][0]['position'][0] += 1
    elif fault == 'duplicate': scene['entities'][1]['id'] = 'person-12'
    elif fault == 'missing_selected': scene['selected'] = 'absent'
    else: kwargs['alerts'] = 1
    with pytest.raises(ValueError): syndicate_domains(scene, **kwargs)


@pytest.mark.parametrize('fault', ('state', 'map', 'dimension_bool', 'source_hash'))
def test_syndicate_map_binding_requires_actual_dimensions_and_source_identity(fault):
    value = model()
    if fault == 'state': value['scene']['source_state_sha256'] = '0'*64
    elif fault == 'map': value['map_number'] += 1
    elif fault == 'dimension_bool': value['dimensions'][0] = True
    else: del value['source_hashes']['classes']
    with pytest.raises(ValueError): syndicate_domains(syndicate(), map_model=value)


def test_civ_record_keys_and_stacking_are_distinct_without_invented_native_extents():
    world = civ(); before = deepcopy(world)
    doc = civilization_domains(world)
    assert world == before
    assert doc['bounds'] == {'world': [0, 0, 80, 50], 'room': None,
                             'collision': None, 'viewport': None}
    assert [o['id'] for o in doc['objects']] == ['city-3', 'unit-2-7', 'unit-3-7', 'resource-4-9']
    assert all(o['pose'] == [4, 9] for o in doc['objects'])
    assert all(o['render'] is None and o['collision'] is None for o in doc['objects'])
    assert doc['provenance']['object_bindings']['unit-3-7']['source_key'] == [3, 7]
    assert all(v['elevation'] is None for v in doc['provenance']['object_bindings'].values())
    assert 'DO_NOT_COPY_THIS_FIELD' not in json.dumps(doc)
    assert all(r['relation'] == 'unknown' and r['anomaly_flag'] is None
               for r in audit_coordinate_domains(doc)['relations'])


@pytest.mark.parametrize('fault', ('format', 'dimensions', 'city_bool', 'coordinate',
    'duplicate_unit', 'missing_inventory', 'hash', 'too_many'))
def test_civ_rejects_unsupported_or_incomplete_census(fault):
    value = civ()
    if fault == 'format': value['format'] = 'other'
    elif fault == 'dimensions': value['dimensions'][0] = 80.0
    elif fault == 'city_bool': value['cities'][0]['index'] = True
    elif fault == 'coordinate': value['units'][0]['x'] = 80
    elif fault == 'duplicate_unit': value['units'].append(deepcopy(value['units'][0]))
    elif fault == 'missing_inventory': del value['resources']
    elif fault == 'hash': value['source']['sve_sha256'] = 'not-a-hash'
    else: value['units'] = value['units']*513
    with pytest.raises(ValueError): civilization_domains(value)


def test_destination_inventory_is_definition_metadata_not_safety_or_action_authority():
    source = model(); before = deepcopy(source)
    result = syndicate_destination_inventory(source, candidate_routes=[route()])
    assert source == before
    anchor, candidate = result['destinations']
    assert anchor['source_id'] == 'authored anchor'
    assert anchor['position_raw'] == [320, 384, 288]
    assert anchor['status'] == 'declared_diagnostic_anchor'
    assert candidate['source_id'] == '2'*64 and candidate['position_raw'] == [512, 384, 256]
    assert candidate['target_position_raw'] == [320, 384, 256]
    assert candidate['status'] == 'candidate_requires_validation'
    assert result['coordinates'] == {'x_y_units_per_tile': 256, 'z_units_per_level': 128}
    assert all(i['safety'] == i['execution'] == 'unknown' for i in result['destinations'])
    assert 'Historical exercise is not encoded' in result['provenance']['scope']


def test_unresolved_route_keeps_status_without_manufacturing_destination():
    value = route(); value.update(status='unresolved_elevation_connector', approach_raw=None)
    result = syndicate_destination_inventory(model(), candidate_routes=[value])
    assert result['destinations'][1]['position_raw'] is None
    assert result['destinations'][1]['status'] == 'unresolved_elevation_connector'


@pytest.mark.parametrize('fault', ('anchor_precision', 'anchor_bool', 'duplicate_anchor',
    'route_state', 'route_status', 'route_pose', 'missing_candidate_pose', 'unknown_target',
    'stale_start', 'stale_target'))
def test_destination_metadata_refuses_ambiguity(fault):
    value = model(); proposal = route()
    if fault == 'anchor_precision': value['waypoints'][0]['position'][0] = 0.1
    elif fault == 'anchor_bool': value['waypoints'][0]['position'][0] = True
    elif fault == 'duplicate_anchor': value['waypoints'].append(deepcopy(value['waypoints'][0]))
    elif fault == 'route_state': proposal['source_state_sha256'] = '0'*64
    elif fault == 'route_status': proposal['status'] = 'safe_teleport'
    elif fault == 'route_pose': proposal['approach_raw'][0] = True
    elif fault == 'missing_candidate_pose': del proposal['approach_raw']
    elif fault == 'unknown_target': proposal['target_id'] = 'foreign-id'
    elif fault == 'stale_start': proposal['start_raw'][0] += 1
    else: proposal['target_raw'][0] += 1
    with pytest.raises(ValueError): syndicate_destination_inventory(value, candidate_routes=[proposal])


@pytest.mark.parametrize('fault', ('nan', 'non_json', 'long_string', 'deep', 'bytes'))
def test_input_work_size_and_json_are_bounded(fault):
    scene = syndicate()
    if fault == 'nan': scene['extra'] = float('nan')
    elif fault == 'non_json': scene['extra'] = object()
    elif fault == 'long_string': scene['extra'] = 'x'*4097
    elif fault == 'deep':
        value = None
        for _ in range(18): value = [value]
        scene['extra'] = value
    else: scene['extra'] = ['x'*4096]*1025
    with pytest.raises(ValueError): syndicate_domains(scene)


def test_bounded_loader_rejects_duplicate_keys_oversize_and_symlink(tmp_path):
    path = tmp_path/'world.json'; path.write_text(json.dumps(civ()))
    assert load_world_json(path) == civ()
    alias = tmp_path/'alias.json'; alias.symlink_to(path)
    with pytest.raises(ValueError): load_world_json(alias)
    path.write_text('{"format":1,"format":2}')
    with pytest.raises(ValueError): load_world_json(path)
    path.write_bytes(b' '*(MAX_INPUT_BYTES+1))
    with pytest.raises(ValueError): load_world_json(path)


def test_object_and_destination_caps_fail_without_truncating_inventories():
    scene = syndicate(); scene['entities'] *= 513
    with pytest.raises(ValueError): syndicate_domains(scene)
    value = model(); value['waypoints'] *= 257
    with pytest.raises(ValueError): syndicate_destination_inventory(value)


def test_unprojected_candidate_conditions_still_change_provenance_identity():
    first = syndicate_destination_inventory(model(), candidate_routes=[route()])
    proposal = route(); proposal['conditional_gates'] = [{'entity': 'object-5', 'condition': 'unit unknown'}]
    second = syndicate_destination_inventory(model(), candidate_routes=[proposal])
    assert first['destinations'] == second['destinations']
    assert first['provenance']['candidate_routes_canonical_sha256'] != second['provenance']['candidate_routes_canonical_sha256']


def test_output_byte_cap_is_enforced_before_return(monkeypatch):
    from examples.scene_domains import world_adapters
    monkeypatch.setattr(world_adapters, 'MAX_OUTPUT_BYTES', 64)
    with pytest.raises(ValueError): civilization_domains(civ())
