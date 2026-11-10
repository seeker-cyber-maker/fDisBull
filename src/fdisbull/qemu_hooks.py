"""Paused breakpoint and watchpoint actions for an owned QEMU session."""
from __future__ import annotations

from copy import deepcopy
import time
import uuid

from .dosbox_rpc import DebuggerError
from .memory_search_runtime import _locked


class QemuHookSessionMixin:
    """Bounded host actions; this is not an in-core TCG callback."""

    def _delete_hook_breakpoint(self, identifier):
        self._qemu_hook_internal_delete = True
        try:
            return self.delete_breakpoint(identifier)
        finally:
            self._qemu_hook_internal_delete = False

    @_locked
    def hook(self, address, *, actions, once=True, max_hits=1, cs=None,
             access='x', length=1, space=None):
        if (access not in ('x', 'r', 'w', 'rw') or type(length) is not int
                or not 1 <= length <= 65536 or access == 'x' and length != 1):
            raise ValueError('Invalid QEMU hook breakpoint or watchpoint extent')
        if type(once) is not bool or type(max_hits) is not int or not 1 <= max_hits <= 1000:
            raise ValueError('Hook once must be boolean and max_hits must be 1..1000')
        if not isinstance(actions, list) or not 1 <= len(actions) <= 16:
            raise ValueError('Hook requires 1..16 actions')
        if self.project is None or self.project.db.in_transaction:
            raise ValueError('QEMU hooks require a project outside a transaction')
        if space is None:
            space = 'source' if getattr(self, '_process', None) else 'linear'
        if space not in ('source', 'linear'):
            raise ValueError('Hooks require source or linear space')
        linear, _, _, _ = self._layer_spans(address, length, space, cs)
        checked = deepcopy(actions)
        for action in checked:
            if not isinstance(action, dict):
                raise ValueError('Hook actions must be objects')
            if action.get('op') == 'layers' and set(action) == {'op', 'layers'}:
                ids = action['layers']
                if not isinstance(ids, list) or len(ids) > 64 or any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)):
                    raise ValueError('Invalid hook layer stack')
                if not self.capabilities.get('code_layers'):
                    raise ValueError('Hook layer action requires QEMU code layers')
                for layer in ids:
                    if self.project.debug_layer_info(layer)['version'] != self.version['id']:
                        raise ValueError('Hook layer version mismatch')
            elif action.get('op') == 'redirect' and set(action) == {'op', 'address'}:
                self._layer_spans(action['address'], 1, 'source')
            elif action.get('op') == 'registers' and set(action) == {'op', 'registers'}:
                edits = action['registers']
                if not isinstance(edits, dict) or not edits:
                    raise ValueError('Hook register edits must be nonempty')
                for name, change in edits.items():
                    if (not isinstance(name, str) or name.lower() in ('cs', 'eip', 'rip', 'ip')
                            or not isinstance(change, dict) or set(change) != {'expected', 'value'}):
                        raise ValueError('Hook register edit requires guarded non-PC registers')
                    for value in change.values():
                        if type(value) is int:
                            if value < 0: raise ValueError('Invalid hook register value')
                        elif isinstance(value, str):
                            try: parsed = int(value, 0)
                            except ValueError: raise ValueError('Invalid hook register value') from None
                            if parsed < 0: raise ValueError('Invalid hook register value')
                        else:
                            raise ValueError('Invalid hook register value')
            else:
                raise ValueError('Hook action must set layers, redirect, or edit guarded registers')
        point = self.breakpoint(linear, access=access, length=length)
        control = dict(hook=uuid.uuid4().hex, breakpoint_id=point['breakpoint_id'],
                       address=address, cs=cs, space=space, runtime_address=linear,
                       access=access, length=length,
                       epoch=self._layer_epoch(), actions=checked, once=once,
                       max_hits=max_hits, hits=0, dispatch='paused_rpc', extra_guest_bytes=0)
        if not hasattr(self, '_qemu_hooks'): self._qemu_hooks = {}
        self._qemu_hooks[point['breakpoint_id']] = control
        try:
            self._event('hook-create', deepcopy(control))
        except BaseException:
            self.close()
            raise
        return deepcopy(control)

    @_locked
    def hooks(self):
        return {'run': self.run_id, 'hooks': deepcopy(list(getattr(self, '_qemu_hooks', {}).values()))}

    @_locked
    def delete_hook(self, hook):
        controls = getattr(self, '_qemu_hooks', {})
        item = next((x for x in controls.values() if x['hook'] == hook), None)
        if item is None: raise ValueError('Unknown live hook')
        try:
            self._delete_hook_breakpoint(item['breakpoint_id'])
            del controls[item['breakpoint_id']]
            if getattr(self, '_qemu_hook_pending', None) == hook:
                self._qemu_hook_pending = None
            self._event('hook-delete', {'hook': hook})
        except BaseException:
            self.close()
            raise
        return {'hook': hook, 'deleted': True}

    def _dispatch_qemu_hook(self, result):
        stop = result.get('session', {}).get('stop_reason', {})
        ids = stop.get('breakpoint_ids', [])
        # A collision, timeout, signal, watch, or DOS parent return is not a
        # uniquely identified hook hit. Preserve the native stop untouched.
        if len(ids) != 1:
            return None
        control = getattr(self, '_qemu_hooks', {}).get(ids[0])
        if control is None:
            return None
        expected = 'breakpoint' if control.get('access', 'x') == 'x' else 'watchpoint'
        if result.get('outcome') != expected:
            return None
        evidence = dict(hook=control['hook'], hit=control['hits'] + 1,
                        stop=deepcopy(result), actions=[], dispatch='paused_rpc', extra_guest_bytes=0)
        try:
            linear, _, _, _ = self._layer_spans(control['address'], control.get('length', 1), control['space'], control['cs'])
            if self._layer_epoch() != control['epoch'] or linear != control['runtime_address']:
                raise ValueError('Hook source mapping or epoch changed')
            control['hits'] += 1
            exhausted = control['once'] or control['hits'] >= control['max_hits']
            if exhausted:
                self._delete_hook_breakpoint(ids[0])
                del self._qemu_hooks[ids[0]]
            for action in control['actions']:
                if action['op'] == 'layers':
                    change = self.layers(action['layers'])
                elif action['op'] == 'registers':
                    change = self.write_registers(action['registers'])
                else:
                    target, _, _, state = self._layer_spans(action['address'], 1, 'source')
                    if state['cpu_mode'] != 'real' or target >= 0x100000:
                        raise ValueError('Hook redirect requires unwrapped real-mode DOS source')
                    values = self.registers()['registers']
                    ip = 'eip' if 'eip' in values else 'rip'
                    change = self.write_registers({
                        'cs': {'expected': int(values['cs'], 16), 'value': target >> 4},
                        ip: {'expected': int(values[ip], 16), 'value': target & 15},
                    })
                    if int(change['linear_pc'], 16) != target:
                        raise DebuggerError('Hook redirect readback mismatch')
                evidence['actions'].append({'op': action['op'], 'result': change})
            self._event('hook-hit', evidence)
        except BaseException as error:
            try: self._event('hook-failed', evidence | {'error': str(error)})
            except BaseException: pass
            try: self.close()
            except BaseException: pass
            if getattr(error, 'result', None) is None:
                error.result = result
            raise
        return evidence

    def _hook_step_over(self, control, deadline):
        if control.get('access', 'x') != 'x':
            return None
        if int(self.registers()['linear_pc'], 16) != control['runtime_address']:
            return None
        old = control['breakpoint_id']
        self._delete_hook_breakpoint(old)
        del self._qemu_hooks[old]
        try:
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining < 1: raise TimeoutError('Hook deadline expired before step-over')
            stepped = self._execute('s', remaining)
            if stepped['outcome'] in ('guest_exit', 'guest_tsr', 'exited'):
                return stepped
            point = self.breakpoint(control['runtime_address'])
            control['breakpoint_id'] = point['breakpoint_id']
            self._qemu_hooks[point['breakpoint_id']] = control
            return stepped if stepped['outcome'] != 'step' else None
        except BaseException:
            self.close()
            raise

    def _run_with_hooks(self, *, timeout_ms, stop_on_hook):
        deadline = min(time.monotonic() + timeout_ms / 1000, self.vm.operation_deadline)
        hits = []
        pending = getattr(self, '_qemu_hook_pending', None)
        if pending is not None:
            control = next((x for x in self._qemu_hooks.values() if x['hook'] == pending), None)
            self._qemu_hook_pending = None
            if control is not None:
                stepped = self._hook_step_over(control, deadline)
                if stepped is not None:
                    stepped['hook_hits'] = hits
                    return stepped
        while True:
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining < 1:
                if hits: self.close()
                error = TimeoutError('Hook run deadline expired before native continuation')
                if hits: error.result = hits[-1]['stop']
                raise error
            try:
                result = self._execute('c', remaining)
            except BaseException:
                if hits: self.close()
                raise
            evidence = self._dispatch_qemu_hook(result)
            if evidence is None:
                result['hook_hits'] = hits
                return result
            hits.append(evidence)
            control = next((x for x in self._qemu_hooks.values() if x['hook'] == evidence['hook']), None)
            if stop_on_hook:
                if control is not None: self._qemu_hook_pending = control['hook']
                result['outcome'] = 'hook'
                result['hook_hits'] = hits
                return result
            # A live repeat breakpoint at the current PC must be stepped over
            # with its breakpoint temporarily removed. A redirected hook does
            # not execute the old instruction. Any non-step result is retained.
            if control is not None:
                stepped = self._hook_step_over(control, deadline)
                if stepped is not None:
                    stepped['hook_hits'] = hits
                    return stepped
