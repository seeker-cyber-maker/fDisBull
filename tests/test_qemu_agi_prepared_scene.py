"""Authored minimal plans and immutable caches; no original game resources."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest


NATIVE = Path(__file__).resolve().parents[1] / 'native/qemu-agi'


def _module(name):
    spec = importlib.util.spec_from_file_location('prepared_test_' + name, NATIVE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def api():
    return _module('prepared_scene')


def _view():
    # Two 2x1 cels. Cel zero mirrors source [1,2] into [2,1]; cel one is [3,4].
    return (bytes([0, 0, 1, 0, 0, 7, 0, 2, 5, 0, 11, 0])
            + bytes([2, 1, 0x9f, 0x11, 0x21, 0, 2, 1, 15, 0x31, 0x41, 0]))


def _package():
    pack = _module('runtime_pack')
    return pack.dump_package(pack.build_package(
        logics=[{'id': 0, 'code': b'\0', 'messages': ['No renderer needs this LOGIC.']}],
        pictures=[{'id': 2, 'data': bytes([0xf0, 5, 0xf8, 0, 0, 0xff])},
                  {'id': 3, 'data': bytes([0xf0, 6, 0xf8, 0, 0, 0xff])}],
        views=[{'id': 7, 'data': _view()}, {'id': 8, 'data': _view()}]))


def _recipe(package):
    return {'schema': 'fdisbull-agi-scene-comparison-recipe-1', 'case_id': 'authored',
        'package_sha256': sha256(package).hexdigest(), 'status': 'partial',
        'endpoint': {'status': 'unsupported', 'requested_endpoint_reached': False},
        'background_operations': [{'operation': 'draw_picture', 'picture': 3},
                                  {'operation': 'draw_picture', 'picture': 2}],
        'actors': [{'id': 9, 'drawn': True, 'view': 7, 'loop': 0, 'cel': 0,
                    'x': 10, 'y': 20, 'priority': 8}, {'id': 5, 'drawn': False}],
        'layer_order': [9], 'unresolved': [{'operation': 'unimplemented'}],
        'manual_values': [{'policy': 'explicit authored layer order'}]}


@pytest.fixture(scope='module')
def renderer(api):
    path = os.environ.get('FDISBULL_AGI_SCENE_LIBRARY')
    if not path:
        pytest.skip('explicit existing native scene library not supplied')
    identity = os.environ.get('FDISBULL_AGI_SCENE_LIBRARY_SHA256')
    assert identity, 'scene library requires its exact SHA-256'
    return api.PreparedSceneRenderer(path, expected_sha256=identity)


def test_projection_is_minimal_and_keeps_refusal_evidence(api):
    package = _package()
    recipe = _recipe(package)
    raw = json.dumps(recipe, indent=2).encode()
    plan, evidence = api.project_recipe(raw)
    assert set(plan) == {'schema', 'profile', 'package_sha256', 'background', 'layers'}
    assert plan['background'] == {'picture': 2}
    assert plan['layers'] == [{'actor_id': 9, 'view': 7, 'loop': 0, 'cel': 0,
                               'x': 10, 'y': 20, 'priority': 8}]
    assert evidence['full_recipe_sha256'] == sha256(raw).hexdigest()
    assert evidence['plan_sha256'] == sha256(api.canonical_bytes(plan)).hexdigest()
    for field in ('status', 'endpoint', 'unresolved', 'manual_values'):
        assert evidence[field] == recipe[field]
    assert evidence['projection']['full_replacement_draws'] == 2
    evidence['endpoint']['status'] = 'changed'
    assert recipe['endpoint']['status'] == 'unsupported'


@pytest.mark.parametrize('operation', ['overlay_picture', 'add_to_picture', 'unknown'])
def test_projection_never_hides_unsupported_background_before_replacement(api, operation):
    recipe = _recipe(_package())
    recipe['background_operations'].insert(0, {'operation': operation, 'picture': 2})
    with pytest.raises(ValueError, match='Unsupported background'):
        api.project_recipe(api.canonical_bytes(recipe))


def test_projection_bounds_background_history_before_collapsing_it(api):
    recipe = _recipe(_package())
    recipe['background_operations'] = [{'operation': 'draw_picture', 'picture': 2}] * 1024
    plan, evidence = api.project_recipe(api.canonical_bytes(recipe))
    assert plan['background'] == {'picture': 2}
    assert evidence['projection']['full_replacement_draws'] == 1024
    recipe['background_operations'].append({'operation': 'draw_picture', 'picture': 2})
    with pytest.raises(ValueError, match='Too many background operations'):
        api.project_recipe(api.canonical_bytes(recipe))


@pytest.mark.parametrize('field', ['actor_id', 'view', 'loop', 'cel', 'x', 'y', 'priority'])
def test_every_minimal_layer_field_is_required(api, field):
    plan, _ = api.project_recipe(api.canonical_bytes(_recipe(_package())))
    del plan['layers'][0][field]
    with pytest.raises(ValueError, match='missing or unknown'):
        api.validate_plan(plan)


@pytest.mark.parametrize('mutation', [
    lambda p: p.update(native_frame='unrelated bytes'),
    lambda p: p['layers'][0].update(x=True),
    lambda p: p['layers'][0].update(y=168),
    lambda p: p['layers'][0].update(priority=16),
    lambda p: p['layers'].append(deepcopy(p['layers'][0])),
    lambda p: p.update(profile='auto'),
])
def test_minimal_contract_rejects_ambiguous_or_out_of_range_inputs(api, mutation):
    plan, _ = api.project_recipe(api.canonical_bytes(_recipe(_package())))
    mutation(plan)
    with pytest.raises(ValueError):
        api.validate_plan(plan)


def test_package_snapshot_hits_skip_validation_and_return_detached_values(api, monkeypatch):
    package = _package()
    cache = api.DecodedAssetCache()
    first = api.PreparedSceneAssets(package, cache=cache)
    initial = cache.statistics()
    detached = first.package
    detached['views'][0]['data'] = 'bad'
    assert first.resource_bytes('view', 7) == _view()
    assert first.package['views'][0]['data'] == _view().hex()
    def forbidden(_):
        raise AssertionError('A validated package cache hit must not revalidate')
    monkeypatch.setattr(api._pack, 'load_package', forbidden)
    again = api.PreparedSceneAssets(package, cache=cache)
    assert again.resource_bytes('view', 7) == _view()
    after = cache.statistics()
    assert after['package_hits'] == 1 and after['package_misses'] == 1
    assert after['package_bytes_validated'] == initial['package_bytes_validated'] == len(package)
    assert after['raw_payload_bytes_admitted'] == initial['raw_payload_bytes_admitted']


def test_geometry_and_cel_metadata_are_detached_and_cache_keys_include_selection(api):
    assets = api.PreparedSceneAssets(_package())
    geometry = assets.view_geometry(7)
    geometry['loops'][0][0]['width'] = 100
    assert assets.view_geometry(7)['loops'][0][0]['width'] == 2
    cel0 = assets.cel(7, 0, 0)
    cel0['pixels'], cel0['width'] = b'bad', 99
    assert assets.cel(7, 0, 0)['pixels'] == bytes([2, 1])
    assert assets.cel(7, 0, 1)['pixels'] == bytes([3, 4])
    # Another local ID for the same exact source bytes can reuse the selected cel.
    assert assets.cel(8, 0, 0)['pixels'] == bytes([2, 1])
    stats = assets.cache.statistics()
    assert stats['cel_misses'] == 2 and stats['cel_hits'] == 2
    assert stats['geometry_misses'] == 1 and stats['geometry_hits'] == 1


def test_referenced_raw_bank_has_no_logic_and_checks_transport_and_payload_hashes(api):
    package = _package()
    assets = api.PreparedSceneAssets(package)
    plan, _ = api.project_recipe(api.canonical_bytes(_recipe(package)))
    bank = assets.export_raw_bank(plan)
    value = json.loads(bank)
    assert set(value) == {'schema', 'profile', 'package_sha256', 'pictures', 'views'}
    assert [r['id'] for r in value['pictures']] == [2]
    assert [r['id'] for r in value['views']] == [7]
    reopened = api.PreparedSceneAssets.from_raw_bank(bank, expected_bank_sha256=sha256(bank).hexdigest())
    assert reopened.resource_ids('logics') == ()
    assert reopened.package_bytes is None
    assert reopened.resource_bytes('view', 7) == _view()
    with pytest.raises(ValueError, match='identity'):
        api.PreparedSceneAssets.from_raw_bank(bank + b' ', expected_bank_sha256=sha256(bank).hexdigest())
    value['views'][0]['data'] = '00'
    altered = api.canonical_bytes(value)
    with pytest.raises(ValueError, match='sha256'):
        api.PreparedSceneAssets.from_raw_bank(altered, expected_bank_sha256=sha256(altered).hexdigest())


def test_failed_resource_decode_is_not_cached_as_success(api):
    pack = _module('runtime_pack')
    package = pack.load_package(_package())
    package['pictures'][0].update(data='fbff', sha256=sha256(bytes.fromhex('fbff')).hexdigest())
    assets = api.PreparedSceneAssets(pack.dump_package(package))
    for _ in range(2):
        with pytest.raises(ValueError, match='Unsupported picture'):
            assets.picture(2)
    assert assets.cache.statistics()['picture_misses'] == 2
    assert assets.cache.statistics()['picture_hits'] == 0
    assert assets.cache.statistics()['decode_failures'] == 2


@pytest.mark.parametrize('field', ['complete', 'priority_complete'])
def test_incomplete_picture_decode_is_refused_before_cache_admission(api, monkeypatch, field):
    assets = api.PreparedSceneAssets(_package())
    decode = api.decode_picture
    monkeypatch.setattr(api, 'decode_picture', lambda payload: {**decode(payload), field: False})
    for _ in range(2):
        with pytest.raises(ValueError, match='complete planes'):
            assets.picture(2)
    assert assets.cache.statistics()['picture_misses'] == 2
    assert assets.cache.statistics()['picture_hits'] == 0
    assert assets.cache.statistics()['decode_failures'] == 2


def test_real_raster_cold_warm_raw_bank_and_edits_agree_with_authored_pixels(api, renderer):
    package = _package()
    assets = api.PreparedSceneAssets(package)
    plan, _ = api.project_recipe(api.canonical_bytes(_recipe(package)))
    cold = renderer.render(plan, assets)
    expected_visual = bytearray([5]) * (160 * 168)
    expected_priority = bytearray([4]) * (160 * 168)
    start = 20 * 160 + 10
    expected_visual[start:start + 2] = bytes([2, 1])
    expected_priority[start:start + 2] = bytes([8, 8])
    assert cold['visual'] == bytes(expected_visual)
    assert cold['priority'] == bytes(expected_priority)
    assert cold['layers'][0]['mirrored'] is True
    cold['layers'][0]['x'] = 123
    warm = renderer.render(plan, assets)
    assert warm['visual'] == bytes(expected_visual) and warm['priority'] == bytes(expected_priority)
    assert warm['cache_delta']['picture_hits'] == 1 and warm['cache_delta']['cel_hits'] == 1
    assert warm['cache_delta']['picture_misses'] == warm['cache_delta']['cel_misses'] == 0
    bank = assets.export_raw_bank(plan)
    reopened = api.PreparedSceneAssets.from_raw_bank(bank, expected_bank_sha256=sha256(bank).hexdigest())
    replay = renderer.render(plan, reopened)
    assert replay['visual'] == warm['visual'] and replay['priority'] == warm['priority']
    edited = deepcopy(plan)
    edited['layers'][0].update(x=12, cel=1)
    changed = renderer.render(edited, assets)
    assert changed['visual'][start:start + 4] == bytes([5, 5, 3, 4])
    assert changed['cache_delta']['picture_hits'] == 1 and changed['cache_delta']['cel_misses'] == 1
    assert renderer.render(plan, assets)['visual'] == warm['visual']


def test_render_refuses_package_mismatch_and_bounds_without_changing_inputs(api, renderer):
    package = _package()
    assets = api.PreparedSceneAssets(package)
    plan, _ = api.project_recipe(api.canonical_bytes(_recipe(package)))
    original = deepcopy(plan)
    plan['package_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='identities differ'):
        renderer.render(plan, assets)
    plan = deepcopy(original)
    plan['layers'][0]['x'] = 159
    with pytest.raises(ValueError, match='clipping or placement'):
        renderer.render(plan, assets)
    assert plan['layers'][0]['x'] == 159
    assert renderer.render(original, assets)['visual'][20 * 160 + 10:20 * 160 + 12] == bytes([2, 1])
