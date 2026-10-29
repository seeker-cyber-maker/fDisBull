"""Explicit, guarded travel assistance; original room transitions remain guest code.

Plans are edition/context qualified by the caller's workflow. This module never
guesses an actor address, a room variable, or an engine callback.
"""
from copy import deepcopy
import base64
import hashlib
import json
import time

from .movement import matches, validate_predicate
from .runtime_observations import capture_observations, validate_observations
from .operation_budget import rpc_budget

WIDTHS = {'u8': 1, 'u16': 2, 'u32': 4}


def validate_travel(plan):
    fields = {'format', 'kind', 'scene_revision', 'observations', 'context',
              'writes', 'inputs', 'until', 'destination', 'provenance', 'guest_ms',
              'slice_ms'}
    if not isinstance(plan, dict) or not fields <= set(plan) <= fields | {'destination_scene','cleanup'} or plan['format'] != 'fdisbull-assisted-travel-1':
        raise ValueError('Expected a complete fdisbull-assisted-travel-1 plan')
    if 'destination_scene' in plan and (not isinstance(plan['destination_scene'],str) or not plan['destination_scene']):
        raise ValueError('Destination scene must pin an explicit revision')
    if plan['kind'] not in ('within-room', 'room-jump') or not isinstance(plan['scene_revision'], str):
        raise ValueError('Travel requires an explicit kind and pinned scene revision')
    validate_observations(plan['observations'])
    for predicate in (plan['context'], plan['until']):
        validate_predicate(predicate, plan['observations'])
    if not isinstance(plan['provenance'], dict) or not plan['provenance']:
        raise ValueError('Travel requires qualification provenance')
    destination = plan['destination']
    if not isinstance(destination, dict) or set(destination) != {'label', 'room_field', 'room_value'} or not isinstance(destination['label'], str) or not destination['label']:
        raise ValueError('Travel destination requires a label and explicit room identity')
    if destination['room_field'] not in plan['observations'] or type(destination['room_value']) is not int:
        raise ValueError('Travel requires an observed destination room')
    room_ref = plan['observations'][destination['room_field']]
    if set(room_ref) not in ({'runtime_memory'}, {'memory'}):
        raise ValueError('Room identity requires a memory observation')
    if next(iter(room_ref.values()))['type'] not in WIDTHS:
        raise ValueError('Room identity requires an unsigned memory field')
    if not isinstance(plan['writes'], list) or not 1 <= len(plan['writes']) <= 32:
        raise ValueError('Travel requires 1..32 guarded actor field writes')
    for edit in plan['writes']:
        if not isinstance(edit, dict) or set(edit) not in ({'binding', 'offset', 'type', 'value'},{'binding','offset','type','set_bits'}):
            raise ValueError('Travel writes require a runtime binding, offset, type and value or set_bits')
        if not isinstance(edit['binding'], str) or not edit['binding'] or type(edit['offset']) is not int or not 0 <= edit['offset'] <= 65535 or edit['type'] not in WIDTHS:
            raise ValueError('Invalid travel field')
        operand=edit.get('value',edit.get('set_bits'))
        if type(operand) is not int or not 0 <= operand < 1 << (8 * WIDTHS[edit['type']]):
            raise ValueError('Travel field value exceeds its declared width')
    if not isinstance(plan['inputs'], list) or len(plan['inputs']) > 16:
        raise ValueError('Travel inputs exceed bounded input plan')
    from .keyboard_input import validate_keyboard
    for step in plan['inputs']:
        if not isinstance(step, dict): raise ValueError('Invalid travel input')
        validate_keyboard(**step)
    if 'cleanup' in plan:
        cleanup=plan['cleanup']
        if not isinstance(cleanup,dict) or set(cleanup)!={'when','inputs'}:
            raise ValueError('Travel cleanup requires an observed trigger and inputs')
        validate_predicate(cleanup['when'],plan['observations'])
        if not isinstance(cleanup['inputs'],list) or not 1<=len(cleanup['inputs'])<=16:
            raise ValueError('Travel cleanup requires 1..16 keyboard inputs')
        for step in cleanup['inputs']:
            if not isinstance(step,dict):raise ValueError('Invalid cleanup input')
            validate_keyboard(**step)
    if plan['kind'] == 'room-jump' and not plan['inputs']:
        raise ValueError('A room jump requires original guest transition input')
    for key, high in (('guest_ms', 120000), ('slice_ms', 1000)):
        if type(plan[key]) is not int or not 1 <= plan[key] <= high:
            raise ValueError('Invalid travel execution budget')
    if len(json.dumps(plan, allow_nan=False).encode()) > 65536:
        raise ValueError('Travel plan exceeds 64 KiB')
    return plan


class AssistedTravelSessionMixin:
    @rpc_budget
    def assisted_travel(self, plan, *, timeout_ms=10000):
        """Apply a qualified actor edit, then observe the original guest's outcome.

        Room jumps skip traversal to a qualified portal and send its original
        input. They never change the room number or bypass room initialization.
        Errors preserve actual partial writes and stops; no rollback is implied.
        """
        if not getattr(self, '_allow_assisted_travel', True):
            result = {'format': 'fdisbull-assisted-travel-result-1',
                      'run': self.run_id, 'version': self.version['id'],
                      'ok': False, 'complete': True, 'status': 'refused',
                      'policy': {'assisted_travel': False},
                      'writes': [], 'inputs': []}
            self._event('assisted-travel', result)
            return result
        plan = deepcopy(validate_travel(plan))
        started = time.monotonic()
        result = {'format': 'fdisbull-assisted-travel-result-1', 'run': self.run_id,
                  'version': self.version['id'], 'assistance': plan['kind'],
                  'plan_sha256': hashlib.sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                  'plan': plan, 'ok': False, 'complete': False, 'status': 'incomplete',
                  'writes': [], 'inputs': [], 'polls': [], 'runs': [], 'guest_elapsed_ms': 0}
        try:
            scene = self.scene(plan['scene_revision'])
            if scene.revision != plan['scene_revision']: raise ValueError('Travel must pin a scene revision')
            target_scene=self.scene(plan['destination_scene']) if 'destination_scene' in plan else None
            if target_scene is not None and target_scene.revision!=plan['destination_scene']:
                raise ValueError('Destination scene must pin a scene revision')
            checked = scene.check()
            result['scene_check'] = checked
            if not checked.get('complete') or checked.get('status') != 'matched':
                raise ValueError('Travel context is not freshly qualified')
            keyboard = self.keyboard_state()['keyboard']
            if keyboard.get('pending_events') != 0 or keyboard.get('owned_keys') != 0:
                raise ValueError('Travel requires neutral, drained guest input')
            before = capture_observations(self, plan['observations'])
            result['before'] = before
            if not before['complete'] or not matches(plan['context'], before['values']):
                raise ValueError('Travel start observations do not match')
            dest = plan['destination']; initial_room = before['values'][dest['room_field']]
            if (plan['kind'] == 'within-room') != (initial_room == dest['room_value']):
                raise ValueError('Travel kind disagrees with observed room identity')
            # Preflight every range and expected byte before any write. Runtime
            # bindings supply session/epoch identity and a verified witness.
            prepared = []; ranges = []
            room_ref = plan['observations'][dest['room_field']]
            if 'runtime_memory' in room_ref:
                ref = room_ref['runtime_memory']
                self.runtime_memory(ref['binding'], offset=ref.get('offset', 0), length=WIDTHS[ref['type']])
                key = self._runtime_names.get(ref['binding'], ref['binding'])
                room_address = self._runtime_bindings[key]['address'] + ref.get('offset', 0)
            else:
                ref = room_ref['memory']
                room_address = self.project._dos_parse_address(ref['address'], ref.get('cs'))[0] + self.delta
            room_end = room_address + WIDTHS[ref['type']]
            for edit in plan['writes']:
                size = WIDTHS[edit['type']]
                observed = self.runtime_memory(edit['binding'], offset=edit['offset'], length=size)
                key = self._runtime_names.get(edit['binding'], edit['binding'])
                binding = self._runtime_bindings[key]
                address = binding['address'] + edit['offset']
                if address < room_end and room_address < address + size:
                    raise ValueError('Travel must not write the observed room field')
                if any(address < hi and lo < address + size for lo, hi in ranges):
                    raise ValueError('Travel fields overlap')
                ranges.append((address, address + size))
                # Keep the identity witness intact so later fields cannot lose
                # their binding midway through a host-side transaction.
                if edit['offset'] < len(bytes.fromhex(binding['expected_hex'])):
                    raise ValueError('Travel cannot overwrite its identity witness')
                value=edit['value'] if 'value' in edit else int.from_bytes(bytes.fromhex(observed['hex']),'little') | edit['set_bits']
                prepared.append((edit, observed, address, value.to_bytes(size, 'little')))
            for edit, observed, address, data in prepared:
                current = self.runtime_memory(edit['binding'], offset=edit['offset'], length=len(data))
                if current != observed: raise ValueError('Travel preflight became stale')
                raw = bytes.fromhex(current['hex'])
                record = {'field': edit, 'before_hex': raw.hex(), 'expected_after_hex': data.hex(),
                          'write_outcome': 'unknown', 'verified': False}
                result['writes'].append(record)
                self.call('memory.write', {'address': {'space': 'linear', 'offset': f'0x{address:08X}'},
                    'expected_sha256': hashlib.sha256(raw).hexdigest(), 'data_base64': base64.b64encode(data).decode()})
                record['write_outcome'] = 'acknowledged'
                actual = self.runtime_memory(edit['binding'], offset=edit['offset'], length=len(data))
                record.update(after_hex=actual['hex'], verified=actual['hex'] == data.hex())
                if not record['verified']: raise ValueError('Travel field readback differs')
            def queue_inputs(steps,phase):
                for step in steps:
                    record = {'input': deepcopy(step), 'phase':phase,'outcome': 'unknown'}
                    result['inputs'].append(record)
                    if 'text' in step: value = self.keyboard_type(**step)
                    else: value = self.keyboard_press(**step)
                    record.update(outcome='acknowledged', result=value)
            queue_inputs(plan['inputs'],'initial')
            cleanup_sent=False
            # At least one bounded guest slice must execute after host writes;
            # RAM readback alone does not prove the engine adopted a position.
            while True:
                remaining = timeout_ms - int((time.monotonic() - started) * 1000)
                guest_remaining = plan['guest_ms'] - result['guest_elapsed_ms']
                if remaining <= 0 or guest_remaining <= 0: raise TimeoutError('Travel budget expired')
                stop = self.run(guest_ms=min(plan['slice_ms'], guest_remaining), timeout_ms=remaining,
                                fast_forward=True, stop_on_hook=True)
                result['runs'].append(stop); result['guest_elapsed_ms'] += stop.get('guest_elapsed_ms', 0)
                if stop.get('outcome') != 'guest_time' or stop.get('hook_hits'):
                    result.update(status='stopped', stop=stop)
                    break
                observed = capture_observations(self, plan['observations'])
                result['polls'].append(observed); result['after'] = observed
                if not observed['complete']: raise ValueError('Travel outcome observation incomplete')
                if result['guest_elapsed_ms'] > plan['guest_ms'] or (time.monotonic()-started)*1000 >= timeout_ms:
                    raise TimeoutError('Travel outcome arrived outside its budget')
                values = observed['values']
                if not cleanup_sent and 'cleanup' in plan and matches(plan['cleanup']['when'],values):
                    keyboard=self.keyboard_state()['keyboard']
                    if keyboard.get('pending_events')==0 and keyboard.get('owned_keys')==0:
                        cleanup_sent=True
                        result['cleanup_trigger']=observed
                        queue_inputs(plan['cleanup']['inputs'],'cleanup')
                        continue # Observe the delivered cleanup before success.
                if matches(plan['until'], values) and values[dest['room_field']] == dest['room_value']:
                    keyboard = self.keyboard_state()['keyboard']
                    if keyboard.get('pending_events') == 0 and keyboard.get('owned_keys') == 0:
                        matched=True
                        if target_scene is not None:
                            destination_check=target_scene.check()
                            result['destination_check']=destination_check
                            if destination_check.get('complete') is not True:
                                raise ValueError('Required destination scene capture is incomplete')
                            matched=destination_check.get('status')=='matched'
                        if matched:
                            if (time.monotonic()-started)*1000>=timeout_ms:
                                raise TimeoutError('Destination capture arrived outside its budget')
                            result.update(ok=True, complete=True, status='success')
                            break
                if values[dest['room_field']] not in (initial_room, dest['room_value']):
                    raise ValueError('Travel reached an unexpected room')
        except Exception as error:
            result['error'] = str(error)
        result['host_elapsed_ms'] = round((time.monotonic() - started) * 1000, 3)
        if not result['ok']:
            try: result['diagnostic_frame'] = self.screenshot('travel-diagnostic.png', hooks=False)['artifact']
            except Exception as error: result['diagnostic_error'] = str(error)
        self._event('assisted-travel', result)
        return result
