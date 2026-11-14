"""Paused CHIP-8 execution hooks; never an in-core callback."""
from copy import deepcopy
import time
import uuid

from .dosbox_rpc import DebuggerError

_MAX_HOOKS = 64
_REGISTERS = {**{f'v{i:x}': 0xff for i in range(16)}, 'i': 0xffff, 'sp': 16,
              **{f'stack{i}': 0xffff for i in range(16)}}


def _ms(deadline):
    value = int((deadline - time.monotonic()) * 1000)
    if value < 1:
        raise TimeoutError('CHIP-8 hook operation deadline expired')
    return min(value, 600000)


def _number(value, maximum):
    try:
        parsed = int(value, 0) if isinstance(value, str) else value
    except ValueError:
        raise ValueError('Invalid CHIP-8 hook register value') from None
    if type(parsed) is not int or not 0 <= parsed <= maximum:
        raise ValueError('Invalid CHIP-8 hook register value')
    return parsed


class Chip8HookMixin:
    """Execution breakpoints with bounded paused actions and explicit resume."""

    def _reset_chip8_hooks(self):
        self._chip8_hooks = {}
        self._chip8_hook_pending = None
        self._chip8_hook_deleting = False

    def _require_chip8_hooks(self):
        if not self.capabilities.get('hooks', False):
            raise ValueError('This CHIP-8 runtime has no hook support')

    def _chip8_hook_owns_breakpoint(self, identifier):
        return any(item['breakpoint_id'] == identifier for item in self._chip8_hooks.values())

    def _chip8_hook_delete_bp(self, identifier):
        previous = self._chip8_hook_deleting
        self._chip8_hook_deleting = True
        try:
            return self.delete_breakpoint(identifier)
        finally:
            self._chip8_hook_deleting = previous

    def _chip8_check_actions(self, actions):
        if not isinstance(actions, list) or not 1 <= len(actions) <= 16:
            raise ValueError('CHIP-8 hooks require 1..16 actions')
        checked = deepcopy(actions)
        for action in checked:
            if not isinstance(action, dict):
                raise ValueError('Invalid CHIP-8 hook action')
            if action.get('op') == 'layers' and set(action) == {'op', 'layers'}:
                ids = action['layers']
                if (not isinstance(ids, list) or len(ids) > 64 or
                        any(not isinstance(item, str) or not item for item in ids) or len(set(ids)) != len(ids)):
                    raise ValueError('Invalid CHIP-8 hook layer stack')
                for identifier in ids:
                    definition = self.project.debug_layer_info(identifier)
                    if (definition.get('version') != self.version['id'] or
                            definition.get('address_model') != 'chip8-flat-4k' or
                            definition.get('chip8_profile') != 'chip8-classic-pilot-default-v1'):
                        raise ValueError('CHIP-8 hook layer identity differs')
            elif action.get('op') == 'registers' and set(action) == {'op', 'registers'}:
                edits = action['registers']
                if not isinstance(edits, dict) or not edits:
                    raise ValueError('CHIP-8 hook register edits must be nonempty')
                for name, change in edits.items():
                    if name not in _REGISTERS or not isinstance(change, dict) or set(change) != {'expected', 'value'}:
                        raise ValueError('CHIP-8 hook requires guarded non-PC register edits')
                    for value in change.values():
                        _number(value, _REGISTERS[name])
            else:
                raise ValueError('CHIP-8 hooks support layer stacks and guarded registers only')
        return checked

    def _chip8_validate_control(self, item, *, portable=False):
        keys = {'hook', 'address', 'actions', 'once', 'max_hits', 'hits'}
        if not isinstance(item, dict) or set(item) != keys:
            raise ValueError('Invalid CHIP-8 hook state')
        identifier = item['hook']
        if (not isinstance(identifier, str) or len(identifier) != 32 or
                any(c not in '0123456789abcdef' for c in identifier)):
            raise ValueError('Invalid CHIP-8 hook identity')
        address = item['address']
        if type(address) is not int or not 0 <= address <= 0xffe or address & 1:
            raise ValueError('CHIP-8 hooks require an even instruction address in RAM')
        if (type(item['once']) is not bool or type(item['max_hits']) is not int or
                not 1 <= item['max_hits'] <= 1000 or type(item['hits']) is not int or
                not 0 <= item['hits'] < item['max_hits'] or item['once'] and item['hits'] != 0):
            raise ValueError('Invalid active CHIP-8 hook hit count')
        checked = deepcopy(item)
        checked['actions'] = self._chip8_check_actions(item['actions'])
        return checked

    def hook(self, address, *, actions, once=True, max_hits=1, cs=None,
             access='x', length=1, space=None, task=None):
        self._require_chip8_hooks()
        if self.project.db.in_transaction:
            raise ValueError('CHIP-8 hooks require no caller transaction')
        if cs is not None or task is not None or access != 'x' or type(length) is not int or length != 1 or space not in (None, 'linear', 'physical'):
            raise ValueError('CHIP-8 hooks support only flat execution addresses')
        if isinstance(address, str):
            try: address = int(address, 0)
            except ValueError: raise ValueError('Invalid CHIP-8 hook address') from None
        item = self._chip8_validate_control(dict(hook=uuid.uuid4().hex, address=address,
                 actions=actions, once=once, max_hits=max_hits, hits=0))
        with self.vm.lock:
            if len(self._chip8_hooks) >= _MAX_HOOKS:
                raise ValueError('CHIP-8 hook limit exceeded')
            if address in self.breakpoints.values():
                raise ValueError('A breakpoint already occupies this CHIP-8 address')
            point = self.breakpoint(address, access='x', length=1)
            item['breakpoint_id'] = point['breakpoint_id']
            self._chip8_hooks[item['hook']] = item
            try:
                self._event('hook-create', deepcopy(item))
            except BaseException:
                self.close()
                raise
            return deepcopy(item)

    def hooks(self):
        self._require_chip8_hooks()
        with self.vm.lock:
            return dict(context='machine', hooks=deepcopy(list(self._chip8_hooks.values())),
                        pending=self._chip8_hook_pending)

    def delete_hook(self, hook):
        self._require_chip8_hooks()
        if self.project.db.in_transaction:
            raise ValueError('CHIP-8 hooks require no caller transaction')
        with self.vm.lock:
            item = self._chip8_hooks.get(hook)
            if item is None:
                raise ValueError('Unknown CHIP-8 hook')
            self._chip8_hook_delete_bp(item['breakpoint_id'])
            del self._chip8_hooks[hook]
            if self._chip8_hook_pending == hook:
                self._chip8_hook_pending = None
            try: self._event('hook-delete', dict(hook=hook))
            except BaseException:
                self.close()
                raise
            return dict(context='machine', deleted=True, hook=hook)

    def _chip8_hook_state(self):
        with self.vm.lock:
            fields = ('hook', 'address', 'actions', 'once', 'max_hits', 'hits')
            return dict(hooks=[{key:deepcopy(item[key]) for key in fields}
                               for item in self._chip8_hooks.values()],
                        pending=self._chip8_hook_pending)

    def _restore_chip8_hooks(self, state):
        """Install validated portable hooks into a fresh, stopped staged owner."""
        if not isinstance(state, dict) or set(state) != {'hooks', 'pending'} or not isinstance(state['hooks'], list) or len(state['hooks']) > _MAX_HOOKS:
            raise ValueError('Invalid CHIP-8 hook checkpoint')
        controls = [self._chip8_validate_control(item, portable=True) for item in state['hooks']]
        names = [item['hook'] for item in controls]
        addresses = [item['address'] for item in controls]
        if len(set(names)) != len(names) or len(set(addresses)) != len(addresses):
            raise ValueError('Ambiguous CHIP-8 hook checkpoint')
        pending = state['pending']
        if pending is not None:
            if pending not in names or next(item for item in controls if item['hook'] == pending)['hits'] < 1:
                raise ValueError('Invalid pending CHIP-8 hook checkpoint')
        if self._chip8_hooks or any(address in self.breakpoints.values() for address in addresses):
            raise ValueError('CHIP-8 hook restore requires a fresh trap registry')
        mapping = {}
        for item in controls:
            point = self.breakpoint(item['address'], access='x', length=1)
            item['breakpoint_id'] = point['breakpoint_id']
            self._chip8_hooks[item['hook']] = item
            mapping[item['hook']] = item['breakpoint_id']
        self._chip8_hook_pending = pending
        return mapping

    def _chip8_hook_hit(self, result):
        if result.get('outcome') != 'breakpoint':
            return None
        reason = result.get('session', {}).get('stop_reason', {})
        ids = reason.get('breakpoint_ids')
        native = reason.get('native_reply', '')
        if not isinstance(native, str) or native[:3] not in ('T05', 'S05') or not isinstance(ids, list) or len(ids) != 1:
            return None
        matches = [item for item in self._chip8_hooks.values() if item['breakpoint_id'] == ids[0]]
        if len(matches) != 1:
            return None
        item = matches[0]
        regs = result.get('registers') or {}
        try: pc = int(regs['linear_pc'], 0)
        except (KeyError, TypeError, ValueError): return None
        if pc != item['address']:
            return None
        evidence = dict(hook=item['hook'], hit=item['hits'] + 1, stop=deepcopy(result),
                        actions=[], dispatch='paused_rpc', extra_guest_bytes=0,
                        breakpoint_id=item['breakpoint_id'])
        try:
            item['hits'] += 1
            if item['once'] or item['hits'] >= item['max_hits']:
                self._chip8_hook_delete_bp(item['breakpoint_id'])
                del self._chip8_hooks[item['hook']]
            for action in item['actions']:
                changed = (self.layers(action['layers']) if action['op'] == 'layers'
                           else self.write_registers(action['registers']))
                evidence['actions'].append(dict(op=action['op'], result=deepcopy(changed)))
            self._event('hook-hit', evidence)
        except BaseException as error:
            error.result = dict(stop=result, hook_hit=evidence,
                                disposition='hook action uncertain; do not replay')
            try: self.close()
            except BaseException: pass
            raise
        return evidence

    def _chip8_hook_displace(self, item, deadline):
        """Temporarily remove the owned trap and execute at most one step."""
        pc = int(self.registers()['linear_pc'], 0)
        if pc != item['address']:
            raise ValueError('Pending CHIP-8 hook no longer points at its instruction')
        result = None
        try:
            self._chip8_hook_delete_bp(item['breakpoint_id'])
            result = self._execute('s', _ms(deadline))
            if result.get('outcome') == 'timeout':
                error = TimeoutError('CHIP-8 hook displacement timed out')
                error.result = dict(stop=result, hook=item['hook'],
                                    disposition='instruction completion uncertain; do not replay')
                raise error
            if result.get('outcome') != 'exited':
                _ms(deadline)
                item['breakpoint_id'] = self.breakpoint(item['address'], access='x', length=1)['breakpoint_id']
            _ms(deadline)
            return result
        except BaseException as error:
            if result is not None and getattr(error, 'result', None) is None:
                error.result = dict(stop=result, hook=item['hook'], disposition='displacement uncertain; do not replay')
            try: self.close()
            except BaseException: pass
            raise

    def _chip8_hook_execute(self, *, timeout_ms, stop_on_hook, single):
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000 or type(stop_on_hook) is not bool:
            raise ValueError('Invalid CHIP-8 hook execution options')
        if self.project.db.in_transaction:
            raise ValueError('CHIP-8 execution requires no caller transaction')
        owner = self.vm
        deadline = time.monotonic() + timeout_ms / 1000
        with self._budget(owner, deadline):
            hits = []
            pending = self._chip8_hook_pending
            if pending is not None:
                item = self._chip8_hooks.get(pending)
                if item is None:
                    self.close()
                    raise DebuggerError('Pending CHIP-8 hook no longer exists')
                result = self._chip8_hook_displace(item, deadline)
                if result.get('outcome') == 'step':
                    self._chip8_hook_pending = None
                    if single:
                        result['hook_hits'] = hits
                        return result
                else:
                    result['hook_hits'] = hits
                    return result
            if single:
                result = self._execute('s', _ms(deadline))
                result['hook_hits'] = hits
                return result
            while True:
                try:
                    result = self._execute('c', _ms(deadline))
                except BaseException:
                    if hits:
                        self.close()
                    raise
                evidence = self._chip8_hook_hit(result)
                if evidence is None:
                    result['hook_hits'] = hits
                    return result
                hits.append(evidence)
                try:
                    _ms(deadline)
                except BaseException as error:
                    error.result = dict(stop=result, hook_hits=deepcopy(hits), disposition='hook completed after deadline; do not replay')
                    try: self.close()
                    except BaseException: pass
                    raise
                item = self._chip8_hooks.get(evidence['hook'])
                if stop_on_hook:
                    if item is not None:
                        self._chip8_hook_pending = item['hook']
                    result['outcome'] = 'hook'
                    result['stop'] = dict(trigger='hook', context='machine')
                    result['hook_hits'] = hits
                    return result
                if item is not None:
                    result = self._chip8_hook_displace(item, deadline)
                    if result.get('outcome') != 'step':
                        self._chip8_hook_pending = item['hook']
                        result['hook_hits'] = hits
                        return result

    def _chip8_run_with_hooks(self, *, timeout_ms, stop_on_hook):
        return self._chip8_hook_execute(timeout_ms=timeout_ms, stop_on_hook=stop_on_hook, single=False)

    def _chip8_step_with_hooks(self, *, timeout_ms):
        return self._chip8_hook_execute(timeout_ms=timeout_ms, stop_on_hook=False, single=True)
