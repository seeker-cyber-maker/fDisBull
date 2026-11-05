"""Read-only projection of an already qualified damage witness into the Z player.

Receipt validation checks consistency, not authenticity or native execution. This
module does not infer an attacker from proximity, run a guest, or collect live
combat events. It is an opt-in research view over a frozen diagnostic snapshot.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re
from typing import Any

SHA256 = re.compile(r'^[a-f0-9]{64}$')
PHASES = (
    'fire-request', 'owner-store-before', 'owner-store-after', 'ammo-after',
    'projectile-hit-query', 'health-store-before', 'health-store-after',
    'hit-query-return',
)


def identity(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def _xyz(value: Any) -> tuple[int, int, int]:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError('Expected exact raw XYZ')
    if any(type(x) is not int for x in value):
        raise ValueError('Coordinates must be integers, not rounded display values')
    return tuple(value)


def contextual_candidates(snapshot: dict, victim_id: str) -> list[dict]:
    """Geometric candidates only. Nearness is not a damage attribution."""
    entities = snapshot['entities']
    lookup = {e['id']: e for e in entities}
    if len(lookup) != len(entities) or victim_id not in lookup:
        raise ValueError('Missing victim or ambiguous entity identities')
    pos = _xyz(lookup[victim_id]['position_raw'])
    result = []
    for entity in entities:
        if entity['id'] == victim_id or entity.get('family') not in ('person', 'vehicle', 'effect'):
            continue
        other = _xyz(entity['position_raw'])
        result.append({'id': entity['id'], 'category': entity.get('category', 'unknown'),
                       'position_raw': list(other), 'delta_z_raw': other[2] - pos[2],
                       'distance_xy_raw': math.hypot(other[0] - pos[0], other[1] - pos[1]),
                       'causation': 'unqualified'})
    return sorted(result, key=lambda e: (e['distance_xy_raw'], e['id']))


def validate_recorded_witness(snapshot: dict, record: dict) -> dict:
    """Reject stale/mismatched or internally inconsistent *recorded* evidence.

    This never promotes a JSON packet into a new native execution certificate.
    Native receipts, source hashes, checkpoint generation and methodology must
    be audited independently before a producer supplies this record.
    """
    if record.get('schema') != 'syndicate-recorded-damage-1':
        raise ValueError('Unsupported damage-record schema')
    for field in ('main_sha256', 'snapshot_sha256'):
        if not isinstance(record.get(field), str) or not SHA256.fullmatch(record[field]):
            raise ValueError('Missing source identity')
    if snapshot.get('source_state_sha256') != record['snapshot_sha256']:
        raise ValueError('Stale snapshot: receipt belongs to another state')
    if not record.get('run_id') or snapshot.get('observed_run') != record['run_id']:
        raise ValueError('Wrong or absent run identity')
    if snapshot.get('source_main_sha256') != record['main_sha256']:
        raise ValueError('Wrong original binary identity')
    if record.get('attribution_scope') != 'same-checkpoint-native-replay':
        raise ValueError('No admitted native attribution scope')
    if record.get('interventions') != {'health_writes': 0, 'code_edits': 0, 'register_edits': 0}:
        raise ValueError('Unsupported intervention profile')
    chain = record.get('events', [])
    if [event.get('phase') for event in chain] != list(PHASES):
        raise ValueError('Incomplete or unordered causal chain')
    fire, before_owner, after_owner, ammo, hit, before_hp, after_hp, returned = chain
    shooter, effect, victim = fire['owner_id'], after_owner['effect_id'], before_hp['victim_id']
    if not (fire['args']['source_ref'] == fire['owner_ref'] == before_owner['source_ref_in_ax']
            == after_owner['source_ref'] == before_hp['source_ref']):
        raise ValueError('Projectile provenance does not match the firing owner')
    if after_owner['source_id'] != shooter:
        raise ValueError('Source-reference resolution mismatch')
    if any(e['effect_id'] != effect for e in (before_owner, hit, before_hp)):
        raise ValueError('Projectile identity changed within this witnessed allocation')
    if after_hp['victim_id'] != victim or returned['returned_id'] != victim:
        raise ValueError('Different victim or unexpected hit-query return')
    if ammo['weapon_id'] != fire['weapon_id'] or ammo['ammo_after'] != fire['ammo_before'] - 1:
        raise ValueError('Firing/ammunition witness mismatch')
    if (type(before_hp['health_before']) is not int or type(after_hp['health_after']) is not int
            or before_hp['health_value_in_ax'] != after_hp['health_after']
            or after_hp['health_after'] != before_hp['health_before'] - 1):
        raise ValueError('Health decrement witness mismatch')
    entities = snapshot['entities']
    byid = {e['id']: e for e in entities}
    if len(byid) != len(entities) or any(key not in byid for key in (shooter, victim, fire['weapon_id'])):
        raise ValueError('Ambiguous or absent source-linked entity')
    if byid[victim].get('health_raw') != after_hp['health_after']:
        raise ValueError('Victim health does not match this frozen snapshot')
    if _xyz(byid[victim]['position_raw']) != _xyz(record['victim_position_raw']):
        raise ValueError('Victim moved relative to the evidence-bound snapshot')
    label = record.get('weapon_label', {})
    if (label.get('source_sha256') != record['main_sha256'] or
            label.get('type') != fire['weapon_type'] or not label.get('name') or
            not isinstance(label.get('consumer_window_sha256'), str) or
            not SHA256.fullmatch(label['consumer_window_sha256'])):
        raise ValueError('Unbound weapon name')
    return {'victim_id': victim, 'shooter_id': shooter, 'shooter_category': byid[shooter]['category'],
            'effect_slot': effect, 'weapon_id': fire['weapon_id'], 'weapon_name': label['name'],
            'health_before': before_hp['health_before'], 'health_after': after_hp['health_after'],
            'damage_raw': before_hp['health_before'] - after_hp['health_after'],
            'record_id': identity(record), 'validation_scope': 'recorded-packet consistency only'}


class RecordedDamageBackend:
    """Freeze a scene and add an evidence-backed, passive `examine last damage`.

    No action is delegated to the base provider. This observer cannot resume a
    guest, replay an order, or claim a new runtime watch has been installed.
    """
    def __init__(self, snapshot: dict, record: dict):
        from z_provider import SceneBackend
        frozen = deepcopy(snapshot)
        fact = validate_recorded_witness(frozen, record)
        observation = SceneBackend(snapshot=frozen).observe()
        context = observation['context']
        context['token'] = identity({'base': context['token'], 'damage': fact['record_id']})
        message = (
            f"Recorded native witness: {fact['victim_id']} lost {fact['damage_raw']} raw health "
            f"({fact['health_before']} -> {fact['health_after']}) from {fact['shooter_category']} "
            f"{fact['shooter_id']} using {fact['weapon_name']} ({fact['weapon_id']}). "
            f"Firing, projectile-owner store, hit query and health write were traced. "
            "Same-checkpoint native replay; not attribution from nearest-entity distance. "
            "Effect slot IDs are reusable, not permanent projectile identities. "
            "This is a frozen diagnostic evidence view, not fair-play visibility or a live monitor."
        )
        observation['objects'].append({'id': 'recorded-damage', 'label': 'last damage',
                                       'aliases': ['damage source', 'last hit'],
                                       'description': message, 'verbs': []})
        self._observation = observation
        self.fact = fact

    def observe(self) -> dict:
        return deepcopy(self._observation)

    def act(self, request: dict) -> dict:
        return {'status': 'rejected', 'complete': True, 'effects': 'none-confirmed',
                'message': 'Recorded damage view is read-only; no action or native input sent.'}
