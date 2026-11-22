"""Reusable immutable AGI assets and minimal, explicitly ordered composition.

This module frames and validates data. Existing runtime_pack, PIC/VIEW readers
and SarienScene.blit own their respective formats and raster semantics. No
LOGIC decoder, interpreter, native frame input, placement or scheduler is used.
Prepared packages retain their exact transport identity. Raw asset banks are
independently hash-bound exports; their package identity is an inherited claim,
not a way to authenticate a whole package from a subset of its resources.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import sys
from threading import RLock
from time import perf_counter_ns
from types import MappingProxyType

from fdisbull.agi_picture import decode_picture
from fdisbull.agi_resources import view_metadata
from fdisbull_core.agi_view import decode_view_cel


def _sibling(name):
    path = Path(__file__).resolve().with_name(name + '.py')
    key = '_fdisbull_prepared_' + name + '_' + sha256(str(path).encode()).hexdigest()[:12]
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(key, None)
            raise
    return sys.modules[key]


_pack, _scene = _sibling('runtime_pack'), _sibling('sarien_scene')
PROFILE = _pack.PROFILE
PLAN_SCHEMA = 'fdisbull-agi-minimal-scene-plan-1'
BANK_SCHEMA = 'fdisbull-agi-scene-asset-bank-1'
EVIDENCE_SCHEMA = 'fdisbull-agi-scene-plan-evidence-1'
WIDTH, HEIGHT = 160, 168
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_KINDS = {'logic': 'logics', 'view': 'views', 'picture': 'pictures', 'sound': 'sounds'}
_PLAN_FIELDS = {'schema', 'profile', 'package_sha256', 'background', 'layers'}
_LAYER_FIELDS = {'actor_id', 'view', 'loop', 'cel', 'x', 'y', 'priority'}


class ScenePreparationError(ValueError):
    """An identity, asset or minimal-scene contract was not satisfied."""


def canonical_bytes(value):
    """Deterministic JSON for newly authored plans/evidence, not package identity."""
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def _json(data):
    if type(data) is not bytes or not 1 <= len(data) <= _pack.MAX_PACKAGE_BYTES:
        raise ScenePreparationError('Expected bounded exact JSON bytes')
    try:
        return json.loads(data.decode('utf-8'), object_pairs_hook=_pack._unique_object,
                          parse_constant=_pack._constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ScenePreparationError('Invalid UTF-8 JSON') from exc


def _fields(value, fields, label):
    if type(value) is not dict or set(value) != fields:
        raise ScenePreparationError(label + ' has missing or unknown fields')


def _hash(value, label):
    if type(value) is not str or not _HASH.fullmatch(value):
        raise ScenePreparationError(label + ' requires a lowercase SHA-256')
    return value


def _uint(value, high, label):
    if type(value) is not int or not 0 <= value <= high:
        raise ScenePreparationError(label + ' requires an integer in 0..' + str(high))
    return value


def _freeze(value):
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value):
    if isinstance(value, MappingProxyType):
        return {key: _thaw(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw(item) for item in value]
    return value


def validate_plan(plan, *, package_sha256=None):
    """Validate the complete renderer input and return an independent object."""
    _fields(plan, _PLAN_FIELDS, 'plan')
    if plan['schema'] != PLAN_SCHEMA or plan['profile'] != PROFILE:
        raise ScenePreparationError('Unsupported minimal scene schema/profile')
    identity = _hash(plan['package_sha256'], 'package_sha256')
    if package_sha256 is not None and identity != package_sha256:
        raise ScenePreparationError('Plan and prepared package identities differ')
    if plan['background'] is not None:
        _fields(plan['background'], {'picture'}, 'background')
        _uint(plan['background']['picture'], 255, 'picture')
    if type(plan['layers']) is not list or len(plan['layers']) > 256:
        raise ScenePreparationError('layers requires at most 256 ordered actors')
    identifiers = set()
    for layer in plan['layers']:
        _fields(layer, _LAYER_FIELDS, 'layer')
        for field in ('actor_id', 'view', 'loop', 'cel'):
            _uint(layer[field], 255, field)
        for field, high in (('x', 159), ('y', 167), ('priority', 15)):
            _uint(layer[field], high, field)
        if layer['actor_id'] in identifiers:
            raise ScenePreparationError('Duplicate actor_id in ordered layers')
        identifiers.add(layer['actor_id'])
    return deepcopy(plan)


def project_recipe(recipe_bytes):
    """Project a full recipe; retain completion/evidence outside composition.

    Every background request is checked before full replacements are collapsed.
    Unsupported overlay/add-to-picture/unknown operations never disappear just
    because a later draw might replace their pixels. Input bytes bind the exact
    original recipe; output plan identity uses canonical_bytes.
    """
    recipe = _json(recipe_bytes)
    if type(recipe) is not dict or recipe.get('schema') != 'fdisbull-agi-scene-comparison-recipe-1':
        raise ScenePreparationError('Unsupported full scene recipe')
    required = {'case_id', 'package_sha256', 'status', 'endpoint', 'background_operations',
                'actors', 'layer_order', 'unresolved', 'manual_values'}
    if required - set(recipe):
        raise ScenePreparationError('Full recipe is missing required fields')
    if type(recipe['case_id']) is not str or not recipe['case_id']:
        raise ScenePreparationError('Full recipe requires case_id')
    if recipe['status'] not in ('complete', 'partial', 'blocked') or type(recipe['endpoint']) is not dict:
        raise ScenePreparationError('Invalid full recipe completion metadata')
    for field in ('background_operations', 'actors', 'layer_order', 'unresolved', 'manual_values'):
        if type(recipe[field]) is not list:
            raise ScenePreparationError(field + ' requires a list')
    if len(recipe['background_operations']) > 1024:
        raise ScenePreparationError('Too many background operations')
    background = None
    for operation in recipe['background_operations']:
        if type(operation) is not dict or operation.get('operation') != 'draw_picture':
            raise ScenePreparationError('Unsupported background operation; only full draw_picture replacements are admitted')
        background = {'picture': _uint(operation.get('picture'), 255, 'picture')}
    if len(recipe['actors']) > 256:
        raise ScenePreparationError('Too many actor records')
    drawn, identifiers = {}, set()
    for actor in recipe['actors']:
        if type(actor) is not dict:
            raise ScenePreparationError('Actor must be an object')
        ident = _uint(actor.get('id'), 255, 'actor id')
        if ident in identifiers or type(actor.get('drawn')) is not bool:
            raise ScenePreparationError('Duplicate actor or missing drawn state')
        identifiers.add(ident)
        if actor['drawn']:
            if any(field not in actor for field in _LAYER_FIELDS - {'actor_id'}):
                raise ScenePreparationError('Drawn actor is missing a composition field')
            drawn[ident] = {'actor_id': ident, **{field: actor[field] for field in _LAYER_FIELDS - {'actor_id'}}}
    order = recipe['layer_order']
    for ident in order:
        _uint(ident, 255, 'layer_order actor')
    if len(order) != len(set(order)) or set(order) != set(drawn):
        raise ScenePreparationError('layer_order must contain every drawn actor exactly once')
    plan = validate_plan({'schema': PLAN_SCHEMA, 'profile': PROFILE,
        'package_sha256': recipe['package_sha256'], 'background': background,
        'layers': [drawn[ident] for ident in order]})
    evidence = {'schema': EVIDENCE_SCHEMA, **{key: deepcopy(recipe[key]) for key in
        ('case_id', 'status', 'endpoint', 'unresolved', 'manual_values')},
        'full_recipe_sha256': sha256(recipe_bytes).hexdigest(),
        'plan_sha256': sha256(canonical_bytes(plan)).hexdigest(),
        'projection': {'full_replacement_draws': len(recipe['background_operations']),
                       'retained_background_draws': int(background is not None),
                       'source_actor_count': len(recipe['actors']), 'drawn_layers': len(order)}}
    return plan, evidence


@dataclass(frozen=True)
class _Resource:
    payload: bytes
    sha256: str


@dataclass(frozen=True)
class _Snapshot:
    package_sha256: str
    package_bytes: bytes | None
    package: object
    resources: object
    raw_bank_sha256: str | None = None


class DecodedAssetCache:
    """One caller-owned cache; immutable entries, explicit identities/counters.

    Package hits reuse a validated immutable snapshot, not another validation
    or JSON parse. Resource/cel entries are keyed by validated payload identity
    and decoder profile/source. Returned dictionaries are detached; cached
    metadata and pixels/planes are immutable bytes. Failures are not cached.
    """
    def __init__(self):
        started = perf_counter_ns()
        self._lock = RLock()
        self._packages, self._banks, self._raw = {}, {}, {}
        self._pictures, self._cels, self._geometry = {}, {}, {}
        functions = {'picture': decode_picture, 'cel': decode_view_cel, 'geometry': view_metadata}
        self._identities = {name: sha256(Path(sys.modules[fn.__module__].__file__).read_bytes()).hexdigest()
                            for name, fn in functions.items()}
        self._metrics = Counter({key: 0 for key in ('package_hits', 'package_misses',
            'bank_hits', 'bank_misses', 'picture_hits', 'picture_misses', 'cel_hits',
            'cel_misses', 'geometry_hits', 'geometry_misses', 'package_bytes_validated',
            'bank_bytes_validated', 'raw_payload_bytes_admitted', 'decode_ns', 'decode_failures')})
        self.preparation_ns = perf_counter_ns() - started

    @property
    def identities(self):
        return dict(self._identities)

    def statistics(self):
        with self._lock:
            return dict(self._metrics)

    def _resources(self, package):
        result = {}
        for kind in ('logics', 'pictures', 'views', 'sounds'):
            bank = {}
            for record in package.get(kind, ()):
                key = kind, record['sha256']
                if key not in self._raw:
                    payload = bytes.fromhex(record['code' if kind == 'logics' else 'data'])
                    self._raw[key] = _Resource(payload, record['sha256'])
                    self._metrics['raw_payload_bytes_admitted'] += len(payload)
                bank[record['id']] = self._raw[key]
            result[kind] = MappingProxyType(bank)
        return MappingProxyType(result)

    def _package(self, data):
        if type(data) is not bytes:
            raise ScenePreparationError('Package admission requires exact immutable bytes')
        identity = sha256(data).hexdigest()
        with self._lock:
            if identity in self._packages:
                self._metrics['package_hits'] += 1
                return self._packages[identity]
            package = _pack.load_package(data)
            snapshot = _Snapshot(identity, data, _freeze(package), self._resources(package))
            self._packages[identity] = snapshot
            self._metrics['package_misses'] += 1
            self._metrics['package_bytes_validated'] += len(data)
            return snapshot

    def _bank(self, data, expected):
        _hash(expected, 'expected_bank_sha256')
        if type(data) is not bytes or sha256(data).hexdigest() != expected:
            raise ScenePreparationError('Raw asset bank identity differs')
        with self._lock:
            if expected in self._banks:
                self._metrics['bank_hits'] += 1
                return self._banks[expected]
            bank = _json(data)
            _fields(bank, {'schema', 'profile', 'package_sha256', 'pictures', 'views'}, 'asset bank')
            if bank['schema'] != BANK_SCHEMA or bank['profile'] != PROFILE:
                raise ScenePreparationError('Unsupported raw asset bank schema/profile')
            _hash(bank['package_sha256'], 'package_sha256')
            for kind in ('pictures', 'views'):
                _pack._array(bank[kind], 256, kind)
                identifiers = set()
                for row in bank[kind]:
                    _pack._fields(row, {'id', 'data', 'sha256'}, kind)
                    _uint(row['id'], 255, 'resource id')
                    if row['id'] in identifiers:
                        raise ScenePreparationError('Duplicate raw-bank resource id')
                    identifiers.add(row['id'])
                    _pack._blob(row, 'data', _pack.MAX_RESOURCE_BYTES, kind)
            snapshot = _Snapshot(bank['package_sha256'], None, None, self._resources(bank), expected)
            self._banks[expected] = snapshot
            self._metrics['bank_misses'] += 1
            self._metrics['bank_bytes_validated'] += len(data)
            return snapshot

    def _decode(self, kind, resource, loop=None, cel=None):
        key = (resource.sha256, PROFILE, self._identities[kind], loop, cel)
        table = {'picture': self._pictures, 'cel': self._cels, 'geometry': self._geometry}[kind]
        with self._lock:
            if key in table:
                self._metrics[kind + '_hits'] += 1
            else:
                start = perf_counter_ns()
                self._metrics[kind + '_misses'] += 1
                try:
                    if kind == 'picture':
                        value = decode_picture(resource.payload)
                        if value.get('complete') is not True or value.get('priority_complete') is not True:
                            raise ScenePreparationError('Picture decoder did not produce complete planes')
                    elif kind == 'cel':
                        value = decode_view_cel(resource.payload, loop=loop, cel=cel)
                    else:
                        value = view_metadata(resource.payload)
                except Exception:
                    self._metrics['decode_failures'] += 1
                    raise
                finally:
                    self._metrics['decode_ns'] += perf_counter_ns() - start
                byte_fields = {name: item for name, item in value.items() if type(item) is bytes}
                metadata = canonical_bytes({name: item for name, item in value.items() if name not in byte_fields})
                table[key] = (metadata, tuple(byte_fields.items()))
            metadata, binary = table[key]
            return {**json.loads(metadata), **dict(binary)}


class PreparedSceneAssets:
    """Validated package/resource snapshots plus lazy shared asset decoding."""
    def __init__(self, package_bytes, *, cache=None):
        start = perf_counter_ns()
        self.cache = cache if cache is not None else DecodedAssetCache()
        self._snapshot = self.cache._package(package_bytes)
        self.preparation_ns = perf_counter_ns() - start

    @classmethod
    def from_raw_bank(cls, bank_bytes, *, expected_bank_sha256, cache=None):
        start = perf_counter_ns()
        result = cls.__new__(cls)
        result.cache = cache if cache is not None else DecodedAssetCache()
        result._snapshot = result.cache._bank(bank_bytes, expected_bank_sha256)
        result.preparation_ns = perf_counter_ns() - start
        return result

    @property
    def package_sha256(self):
        return self._snapshot.package_sha256

    @property
    def package_bytes(self):
        return self._snapshot.package_bytes

    @property
    def package(self):
        if self._snapshot.package is None:
            raise ScenePreparationError('Raw asset bank has no LOGIC/package document')
        return _thaw(self._snapshot.package)

    def _resource(self, kind, ident):
        kind = _KINDS.get(kind, kind)
        _uint(ident, 255, 'resource id')
        if kind not in self._snapshot.resources or ident not in self._snapshot.resources[kind]:
            raise ScenePreparationError('Missing ' + str(kind) + ' resource ' + str(ident))
        return self._snapshot.resources[kind][ident]

    def resource_ids(self, kind):
        kind = _KINDS.get(kind, kind)
        if kind not in self._snapshot.resources:
            raise ScenePreparationError('Unknown resource kind')
        return tuple(sorted(self._snapshot.resources[kind]))

    def resource_bytes(self, kind, ident):
        return self._resource(kind, ident).payload

    def picture(self, ident):
        return self.cache._decode('picture', self._resource('pictures', ident))

    def cel(self, view, loop, cel):
        _uint(loop, 255, 'loop')
        _uint(cel, 255, 'cel')
        return self.cache._decode('cel', self._resource('views', view), loop, cel)

    def view_geometry(self, ident):
        return self.cache._decode('geometry', self._resource('views', ident))

    def export_raw_bank(self, plan):
        plan = validate_plan(plan, package_sha256=self.package_sha256)
        selected = {'pictures': [] if plan['background'] is None else [plan['background']['picture']],
                    'views': sorted({layer['view'] for layer in plan['layers']})}
        bank = {'schema': BANK_SCHEMA, 'profile': PROFILE, 'package_sha256': self.package_sha256}
        for kind, identifiers in selected.items():
            bank[kind] = []
            for ident in identifiers:
                resource = self._resource(kind, ident)
                bank[kind].append({'id': ident, 'data': resource.payload.hex(), 'sha256': resource.sha256})
        return canonical_bytes(bank)


class PreparedSceneRenderer:
    """One admitted existing Sarien blitter; no placement, execution or I/O."""
    def __init__(self, library, *, expected_sha256):
        start = perf_counter_ns()
        self._scene = _scene.SarienScene(library, expected_sha256=expected_sha256)
        self.library_sha256 = self._scene.binary_sha256
        self.preparation_ns = perf_counter_ns() - start

    def render(self, plan, assets):
        if not isinstance(assets, PreparedSceneAssets):
            raise ScenePreparationError('PreparedSceneAssets instance required')
        start = perf_counter_ns()
        plan = validate_plan(plan, package_sha256=assets.package_sha256)
        before = assets.cache.statistics()
        lookup_ns = blit_ns = 0
        visual, priority = bytes([15]) * (WIDTH * HEIGHT), bytes([4]) * (WIDTH * HEIGHT)
        if plan['background'] is not None:
            phase = perf_counter_ns()
            decoded = assets.picture(plan['background']['picture'])
            if decoded['complete'] is not True or decoded['priority_complete'] is not True:
                raise ScenePreparationError('Picture decoder did not produce complete planes')
            visual, priority = decoded['visual'], decoded['priority']
            lookup_ns += perf_counter_ns() - phase
        layers = []
        for layer in plan['layers']:
            phase = perf_counter_ns()
            decoded = assets.cel(layer['view'], layer['loop'], layer['cel'])
            lookup_ns += perf_counter_ns() - phase
            if layer['x'] + decoded['width'] > WIDTH or layer['y'] + 1 < decoded['height']:
                raise ScenePreparationError('Actor pose requires clipping or placement repair')
            phase = perf_counter_ns()
            result = self._scene.blit(visual, priority, decoded['pixels'], x=layer['x'],
                baseline=layer['y'], width=decoded['width'], height=decoded['height'],
                transparent=decoded['transparent_color'], actor_priority=layer['priority'])
            blit_ns += perf_counter_ns() - phase
            visual, priority = result['visual'], result['priority']
            layers.append({**layer, **{name: decoded[name] for name in
                ('width', 'height', 'transparent_color', 'mirrored', 'source_sha256')},
                'written_pixels': result['written_pixels'], 'hidden': result['hidden']})
        after = assets.cache.statistics()
        return {'schema': 'fdisbull-agi-prepared-scene-render-1', 'width': WIDTH, 'height': HEIGHT,
            'plan_sha256': sha256(canonical_bytes(plan)).hexdigest(), 'package_sha256': assets.package_sha256,
            'visual': visual, 'priority': priority, 'layers': layers,
            'renderer': {'library_sha256': self.library_sha256, 'api': 'SarienScene.blit',
                         'decoders': assets.cache.identities, 'native_frame_input': False},
            'timing_ns': {'asset_lookup_decode': lookup_ns, 'blit': blit_ns, 'total': perf_counter_ns() - start},
            'cache_delta': {key: after[key] - before[key] for key in before}}
