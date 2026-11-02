"""Spatial Z descriptions over an authoritative Shadowrun runtime snapshot.

A runtime owns one shared model for movement and investigator observations.
Teleport is an explicitly assisted debug intervention.
"""
from .shadowrun_city import project_city, validate_snapshot


def observe_city(runtime, *, radius_x=8, radius_y=5):
    return project_city(runtime.snapshot(), radius_x=radius_x, radius_y=radius_y)


def assisted_teleport(runtime, *, policy, scene_id, x, y, revision, recenter=False):
    """Ask the runtime to perform one atomic, validated same-scene placement.

    The runtime must verify revision, field bounds, the modeled terrain collision,
    camera state, and refuse unsupported paths. Dynamic-entity collision is unknown. An absent operation
    is a refusal, never a synthetic state change.
    """
    if type(recenter) is not bool:
        return {'complete': True, 'status': 'refused', 'reason': 'invalid camera option'}
    if policy != 'assisted':
        return {'complete': True, 'status': 'refused', 'reason': 'assisted policy required'}
    state = validate_snapshot(runtime.snapshot())
    if revision != state['revision'] or type(scene_id) is not int or scene_id != state['scene_id']:
        return {'complete': True, 'status': 'refused', 'reason': 'stale revision or different scene'}
    if type(x) is not int or type(y) is not int or not 0 <= x <= 65535 or not 0 <= y <= 65535:
        return {'complete': True, 'status': 'refused', 'reason': 'invalid fixed-point destination'}
    x0, x1, y0, y1 = state['bounds']
    if not (x0 <= x >> 4 < x1 and y0 <= y >> 4 < y1):
        return {'complete': True, 'status': 'refused', 'reason': 'destination outside field bounds'}
    operation = getattr(runtime, 'assisted_teleport', None)
    if not callable(operation):
        return {'complete': True, 'status': 'refused', 'reason': 'qualified runtime placement unavailable'}
    if recenter:
        return operation(policy=policy, scene_id=scene_id, x=x, y=y, revision=revision, recenter=True)
    return operation(policy=policy, scene_id=scene_id, x=x, y=y, revision=revision)


class ShadowrunRuntime:
    """One GameMachine shared by movement, investigator views, and debug placement.

    The caller supplies a seeded ``GameMachine(lift_play(rom), {0: rom})``.
    Without recentering teleport is confined to the current viewport. An explicit
    authored recenter updates model camera/scroll/stream state. The source
    collision procedure is evaluated on a transactional copy; nonzero status,
    out-of-map probes, and any execution error refuse the intervention.
    """
    def __init__(self, machine, *, scene_id=2, captured_entities=None):
        import secrets
        import threading
        import hashlib
        from .shadowrun_world import SOURCE_SHA256
        source = machine.regions.get(0)
        if not isinstance(source, bytes) or hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
            raise ValueError('Runtime requires the exact source-bound GameMachine')
        self.machine = machine
        self.scene_id = scene_id
        if captured_entities is not None and (not isinstance(captured_entities, dict) or
                captured_entities.get('format') != 'fdisbull-shadowrun-captured-entities-1' or
                captured_entities.get('source_sha256') != SOURCE_SHA256 or
                captured_entities.get('capture_frame') != 5999 or
                captured_entities.get('capture_receipt_sha256') != 'b7252b76252a0ebda05d615d775c599859092302eff261cfcdad66b30a1ff42c' or
                not isinstance(captured_entities.get('entities'), list)):
            raise ValueError('Invalid captured entity packet')
        from copy import deepcopy
        self.captured_entities = deepcopy(captured_entities)
        self._epoch = secrets.token_hex(16)
        self._revision = 0
        self._lock = threading.RLock()
        validate_snapshot(self.snapshot())

    def snapshot(self):
        from copy import deepcopy
        from .shadowrun_world import SOURCE_SHA256
        with self._lock:
            s = self.machine.snapshot()
            arena = s.get('shadowrun_arena_profile') == 1
            actor_x = s.get('shadowrun_target_x')
            actor_y = s.get('shadowrun_target_y')
            if arena and isinstance(actor_x, list) and len(actor_x) == 7 and isinstance(actor_y, list) and len(actor_y) == 7:
                actor_x, actor_y = list(actor_x), list(actor_y)
                actor_x[0], actor_y[0] = s.get('shadowrun_hostile_x'), s.get('shadowrun_hostile_y')
            return {'source_sha256': SOURCE_SHA256, 'scene_id': self.scene_id,
                    'revision': f'{self._epoch}:{self._revision}',
                    'player_x': s['shadowrun_player_x'], 'player_y': s['shadowrun_player_y'],
                    'camera_x': s['shadowrun_camera_x'], 'camera_y': s['shadowrun_camera_y'],
                    'bounds': [s['shadowrun_x_min'], s['shadowrun_x_max'],
                               s['shadowrun_y_min'], s['shadowrun_y_max']],
                    'terrain': bytes(s['shadowrun_terrain_map']),
                    'model_actor_hp': s.get('shadowrun_play_actor_hp'),
                    'model_actor_x': actor_x, 'model_actor_y': actor_y,
                    'model_actor_flags': s.get('shadowrun_target_flags'),
                    'model_actor_status': s.get('shadowrun_ai_slot_status'),
                    'actor_state_profile': ('constructed_arena' if arena else
                                            'qualified_dynamic' if 'shadowrun_ai_slot_status' in s else 'captured'),
                    'model_player_hp': s.get('shadowrun_arena_hp') if arena else None,
                    'captured_entities': [] if self.captured_entities is None else deepcopy(self.captured_entities['entities'])}

    def move(self, pad, frames=1):
        if type(pad) is not int or not 0 <= pad <= 15:
            return {'complete': True, 'status': 'refused', 'reason': 'invalid direction'}
        return self.advance(pad, frames)

    def advance(self, pad, frames=1):
        from copy import deepcopy
        if type(pad) is not int or not 0 <= pad <= 255 or type(frames) is not int or not 1 <= frames <= 60:
            return {'complete': True, 'status': 'refused', 'reason': 'invalid direction or frame count'}
        with self._lock:
            candidate = deepcopy(self.machine)
            before = self.snapshot()
            executed = 0
            arena = candidate.snapshot().get('shadowrun_arena_profile') == 1
            if arena and candidate.snapshot().get('shadowrun_arena_frame_status') == 3:
                return {'complete': True, 'status': 'terminal', 'frames_executed': 0,
                        'reason': 'The player has been defeated; restart to play again.'}
            boundary = False
            terminal = False
            try:
                for _ in range(frames):
                    # Keep the last fully qualified arena frame atomically.
                    next_candidate = deepcopy(candidate) if arena else candidate
                    next_candidate.call('shadowrun_arena_frame' if arena else 'shadowrun_play_frame', pad)
                    if arena and next_candidate.snapshot().get('shadowrun_arena_frame_status') == 2:
                        boundary = True
                        break
                    candidate = next_candidate
                    executed += 1
                    if arena and candidate.snapshot().get('shadowrun_arena_frame_status') == 3:
                        terminal = True
                        break
                    if candidate.snapshot()['shadowrun_opening_status'] in (2, 3, 4):
                        break
            except (ValueError, IndexError, KeyError) as exc:
                return {'complete': False, 'status': 'unsupported', 'reason': str(exc)}
            if not executed and boundary:
                return {'complete': False, 'status': 'unsupported', 'frames_executed': 0,
                        'reason': 'The assisted arena reached an unsupported model boundary.'}
            self.machine = candidate
            self._revision += 1
            status = candidate.snapshot()['shadowrun_opening_status']
            after = self.snapshot()
            return {'complete': True, 'status': 'terminal' if terminal else 'advanced', 'opening_status': status,
                    'frames_executed': executed, 'boundary_reached': boundary,
                    'action_refused': bool(candidate.snapshot().get('shadowrun_play_refused', 0)),
                    'position_changed': (before['player_x'], before['player_y']) != (after['player_x'], after['player_y']),
                    'revision': after['revision']}

    def assisted_teleport(self, *, policy, scene_id, x, y, revision, recenter=False):
        from copy import deepcopy
        with self._lock:
            if policy != 'assisted':
                return {'complete': True, 'status': 'refused', 'reason': 'assisted policy required'}
            state = self.snapshot()
            if type(scene_id) is not int or scene_id != self.scene_id or revision != state['revision']:
                return {'complete': True, 'status': 'refused', 'reason': 'stale revision or different scene'}
            if type(x) is not int or type(y) is not int or not (0 <= x <= 65535 and 0 <= y <= 65535):
                return {'complete': True, 'status': 'refused', 'reason': 'invalid fixed-point destination'}
            if type(recenter) is not bool:
                return {'complete': True, 'status': 'refused', 'reason': 'invalid camera option'}
            candidate = deepcopy(self.machine)
            try:
                candidate.set_state({'shadowrun_debug_x': x, 'shadowrun_debug_y': y,
                                     'shadowrun_debug_assisted': 1,
                                     'shadowrun_debug_recenter': int(recenter)})
                candidate.call('shadowrun_debug_place')
                if candidate.snapshot()['shadowrun_debug_result'] != 1:
                    return {'complete': True, 'status': 'refused', 'reason': 'shared placement checks refused'}
                validate_snapshot({**state, 'player_x': x, 'player_y': y})
            except (ValueError, IndexError, KeyError) as exc:
                return {'complete': False, 'status': 'unsupported', 'reason': str(exc)}
            self.machine = candidate
            self._revision += 1
            return {'complete': True, 'status': 'placed', 'assisted': True,
                    'revision': self.snapshot()['revision'],
                    'camera_recentered': recenter, 'scope': 'shared target-only debug placement; terrain collision only; dynamic entities and original reachability unknown'}


def inventory_view(machine_state):
    """Project eight source slots and equipment from the current shared model."""
    names = [f'shadowrun_inventory_cell{i}' for i in range(8)]
    if any(name not in machine_state for name in names):
        return {'status': 'unknown', 'slots': [], 'weapon': None, 'armor': None, 'ammo': None, 'ammo_units': 'unknown'}
    slots = []
    weapon_slot = machine_state.get('shadowrun_play_weapon_slot')
    weapon_item = machine_state.get('shadowrun_play_weapon_item')
    for i, name in enumerate(names):
        item = machine_state[name]
        slots.append({'id': f'shadowrun.inventory.slot.{i}', 'slot': i,
                      'item_code': item, 'state': 'empty' if item == 0 else 'occupied',
                      'weapon_equipped': (None if weapon_slot is None or weapon_item is None else
                                          bool(item and weapon_slot == i and weapon_item == item)),
                      'phase': machine_state.get(f'shadowrun_play_phase{i}')})
    return {'status': 'known', 'slots': slots,
            'weapon': None if weapon_slot is None or weapon_item is None else
                      {'slot_raw': weapon_slot, 'item_code': weapon_item},
            'armor': machine_state.get('shadowrun_inventory_equipped_armor'),
            'ammo': machine_state.get('shadowrun_play_ammo'),
            'ammo_units': ('rounds' if weapon_slot == 0 and weapon_item == 2 else
                           'stored percentage' if weapon_slot == 127 and weapon_item == 0 else 'unknown')}


class ShadowrunZBackend:
    """Text-player protocol over the same GameMachine used for the NES lift."""
    DIRECTIONS = {'north': 1, 'south': 2, 'west': 4, 'east': 8}

    def __init__(self, runtime, *, policy='physical'):
        if policy not in ('physical', 'assisted'):
            raise ValueError('Expected physical or assisted policy')
        self.runtime, self.policy = runtime, policy

    def observe(self):
        from .shadowrun_city import render_city_text, render_region_text
        with self.runtime._lock:
            state = self.runtime.snapshot()
            city = project_city(state, radius_x=1, radius_y=1)
            actors = city['captured_entities']
            model_state = self.runtime.machine.snapshot()
            inventory = inventory_view(model_state)
            selected = model_state.get('shadowrun_target_selected')
            target_state = ('none' if selected == 255 else 'selected' if type(selected) is int and 0 <= selected < 7 else 'unknown')
            target_id = (next((actor['id'] for actor in actors
                               if actor.get('slot_address') == 0xff0400 + selected * 0x100
                               and (state.get('actor_state_profile', 'captured') == 'captured' or
                                    (actor.get('present') is True and actor.get('current_position') == 'shared model'))), None)
                         if target_state == 'selected' else None)
            combat = {'target_state': target_state, 'target_id': target_id,
                      'shot_pending': (None if 'shadowrun_play_shot_pending' not in model_state else
                                       bool(model_state['shadowrun_play_shot_pending'])),
                      'projectile_state_raw': model_state.get('shadowrun_field_motion_state')}
            in_menu = bool(model_state.get('shadowrun_play_menu', 0))
            objects = [{'id': f'direction.{name}', 'label': name, 'aliases': [],
                        'description': 'Move for one model frame in this direction.', 'verbs': ['go']}
                       for name in self.DIRECTIONS]
            controls = ['close-inventory', 'release'] if in_menu else ['open-inventory', 'target', 'fire', 'release']
            objects.append({'id': 'control.game', 'label': 'game controls', 'aliases': [],
                            'description': 'Each action advances one shared model frame; repeated button presses require release.',
                            'verbs': controls})
            for frames in (1, 10, 30, 60):
                objects.append({'id': f'wait.{frames}', 'label': f'wait {frames} frames', 'aliases': [],
                                'description': 'Advance the shared model with no buttons held.', 'verbs': ['wait']})
                if not in_menu and frames > 1:
                    objects.append({'id': f'hold-fire.{frames}', 'label': f'hold fire {frames} frames',
                                    'aliases': [], 'description': 'Advance model frames with A held.',
                                    'verbs': ['hold-fire']})
            items = []
            for slot in inventory['slots']:
                if slot['state'] == 'occupied':
                    active = in_menu and model_state.get('shadowrun_inventory_slot') == slot['slot']
                    items.append({'id': slot['id'], 'label': f"item {slot['item_code']} (slot {slot['slot']})",
                                  'aliases': [], 'description': f"Item code {slot['item_code']}; equipped weapon: {slot['weapon_equipped']}; armor phase: {slot['phase']}.",
                                  'verbs': ['equip'] if active else []})
            if inventory['status'] == 'unknown':
                items.append({'id':'inventory.unknown', 'label':'inventory unknown', 'aliases':[],
                              'description':'The shared model does not expose all inventory slots.', 'verbs':[]})
            if self.policy == 'assisted':
                for cell in city['local_cells']:
                    tx, ty = (cell['x'] * 32 + 16) << 4, (cell['y'] * 32 + 16) << 4
                    objects.append({'id': f'teleport.{tx}.{ty}', 'label': f'debug position {tx} {ty}',
                                    'aliases': [], 'description': 'Exact fixed-point debug position; collision and viewport checks may refuse.',
                                    'verbs': ['teleport', 'teleport-recenter']})
                existing = {obj['id'] for obj in objects}
                for region in city['regions']:
                    x0, x1, y0, y1 = region['cell_bounds']
                    tx, ty = ((x0 + x1) * 16) << 4, ((y0 + y1) * 16) << 4
                    ident = f'teleport.{tx}.{ty}'
                    if ident not in existing:
                        objects.append({'id': ident, 'label': f'debug position {tx} {ty}',
                            'aliases': [], 'description': 'Exact fixed-point region candidate; authored camera recenter and terrain checks may refuse.',
                            'verbs': ['teleport-recenter']})
                        existing.add(ident)
            display = lambda value: 'unknown' if value is None else str(value)
            equipment_text = (f"\nInventory: {inventory['status']}; weapon {display(inventory['weapon'])}; "
                              f"armor code {display(inventory['armor'])}; ammunition {display(inventory['ammo'])} {inventory['ammo_units']}."
                              f" Target: {combat['target_id'] if combat['target_id'] else combat['target_state']}; shot pending: {display(combat['shot_pending'])}.")
            if state.get('actor_state_profile') == 'constructed_arena':
                equipment_text += f"\nAssisted source-constructed arena. Player HP: {display(state.get('model_player_hp'))}."
            return {'complete': True, 'session_token': self.runtime._epoch,
                    'context': {'id': city['scene_key'], 'title': f"Scene {state['scene_id']}",
                                'description': render_region_text(state) + '\n\n' + render_city_text(state, radius_x=4, radius_y=3) + equipment_text + ('\nActor records (position status and visibility are explicit): ' + '; '.join(a['id'] + ' at ' + display(a['x']) + ',' + display(a['y']) + ' kind=' + str(a.get('kind', 'unknown')) + ' position=' + a.get('current_position', 'unknown') + ' current HP=' + display(a['hp_current']) for a in actors) if actors else ''),
                                'token': state['revision']},
                    'objects': objects, 'inventory': items, 'inventory_state': inventory, 'combat_state': combat,
                    'player_state': city['player'], 'actor_records': actors, 'captured_entities': actors,
                    'coverage': {'partial': True, 'visibility': 'unknown',
                                 'profile': 'investigator', 'policy': self.policy,
                                 'actor_state_profile': state.get('actor_state_profile', 'captured')}}

    def act(self, request):
        with self.runtime._lock:
            if (not isinstance(request, dict) or set(request) != {'verb', 'target', 'item', 'context_token'}
                    or request['item'] is not None):
                return {'complete': True, 'status': 'rejected', 'message': 'Invalid action.'}
            obs = self.observe()
            if request['context_token'] != obs['context']['token']:
                return {'complete': True, 'status': 'rejected', 'message': 'Context changed.'}
            obj = next((o for o in obs['objects'] + obs['inventory'] if o['id'] == request['target']), None)
            # A protocol client may request an exact fixed-point coordinate,
            # without treating a displayed coarse cell as an execution point.
            if obj is None and self.policy == 'assisted':
                import re
                target = request['target']
                if (isinstance(target, str) and re.fullmatch(r'teleport\.[0-9]{1,5}\.[0-9]{1,5}', target)
                        and request['verb'] in ('teleport', 'teleport-recenter')):
                    obj = {'id': target, 'verbs': ['teleport', 'teleport-recenter']}
            if obj is None or request['verb'] not in obj['verbs']:
                return {'complete': True, 'status': 'rejected', 'message': 'Action unavailable.'}
            if request['verb'] == 'go':
                result = self.runtime.move(self.DIRECTIONS[obj['id'].split('.')[1]])
            elif request['verb'] in ('wait', 'hold-fire'):
                result = self.runtime.advance(0 if request['verb'] == 'wait' else 64, int(obj['id'].split('.')[1]))
            elif request['verb'] in ('open-inventory', 'close-inventory', 'target', 'fire', 'release', 'equip'):
                pad = {'open-inventory':128, 'close-inventory':128, 'target':16,
                       'fire':64, 'release':0, 'equip':64}[request['verb']]
                previous = self.runtime.machine.snapshot().get('shadowrun_play_previous')
                if pad and previous is not None and previous & pad:
                    return {'complete': True, 'status': 'rejected', 'message': 'Release the button before pressing it again.'}
                result = self.runtime.advance(pad)
            else:
                parts = obj['id'].split('.')
                x, y = int(parts[-2]), int(parts[-1])
                result = assisted_teleport(self.runtime, policy=self.policy,
                                          scene_id=self.runtime.scene_id, x=x, y=y,
                                          revision=obs['context']['token'], recenter=request['verb'] == 'teleport-recenter')
            success = ((result['status'] in ('advanced', 'placed') and
                        not result.get('action_refused', False) and result.get('opening_status') not in (2, 3, 4))
                       or (result['status'] == 'terminal' and result.get('frames_executed', 0) > 0))
            new = self.observe()
            if result['status'] == 'terminal' and success:
                message = 'The player was defeated; restart to play again.'
            elif result['status'] == 'placed':
                message = 'Assisted debug placement.'
            elif success:
                message = f"Model advanced {result.get('frames_executed', 1)} frame(s)."
                if result.get('boundary_reached'):
                    message += ' It then stopped at an unsupported model boundary.'
            else:
                message = result.get('reason', 'Action refused; a model frame advanced.')
            return {'complete': result['complete'], 'status': 'success' if success else 'rejected',
                    'message': message,
                    'detail': result,
                    'witness': {'session_token': self.runtime._epoch,
                                'context_id': new['context']['id'], 'context_token': new['context']['token']}}
