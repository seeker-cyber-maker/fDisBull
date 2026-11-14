"""Paused breakpoint and watchpoint actions for an owned QEMU session."""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
import time
import uuid

from .dosbox_rpc import DebuggerError
from .memory_search_runtime import _locked


class QemuHookSessionMixin:
    """Bounded host actions; this is not an in-core TCG callback."""

    @contextmanager
    def _hook_binding(self, binding):
        old = getattr(self, '_dos_task_binding', None)
        if binding is not None:
            self._dos_task_binding = binding
        try:
            yield
        finally:
            self._dos_task_binding = old

    def _hook_reindex(self, controls):
        indexed = {}
        for item in controls:
            bp = item['breakpoint_id']
            indexed[bp if bp not in indexed else 'hook:' + item['hook']] = item
        self._qemu_hooks = indexed

    def _hook_remove(self, control):
        controls = list(self._qemu_hooks.values())
        survivors = [item for item in controls if item is not control]
        if not any(item['breakpoint_id'] == control['breakpoint_id'] for item in survivors):
            self._delete_hook_breakpoint(control['breakpoint_id'])
        self._hook_reindex(survivors)

    def _install_restored_qemu_hook(self, item):
        """Reinstall a previously validated sidecar control on the fresh VM."""
        control = deepcopy(item)
        peers = [value for value in getattr(self, '_qemu_hooks', {}).values()
                 if (value['runtime_address'], value['access'], value['length']) ==
                    (control['runtime_address'], control['access'], control['length'])]
        if peers:
            from .qemu_dos_tasks import task_key
            if control.get('task_identity') is None or any(
                    peer.get('task_identity') is None or
                    task_key(peer['task_identity']) == task_key(control['task_identity']) for peer in peers):
                raise ValueError('Ambiguous restored task hook')
            bp = peers[0]['breakpoint_id']
        else:
            bp = self.breakpoint(control['runtime_address'], access=control['access'],
                                 length=control['length'])['breakpoint_id']
        control['breakpoint_id'] = bp
        control['epoch'] = self._layer_epoch()
        self._hook_reindex([*getattr(self, '_qemu_hooks', {}).values(), control])
        return deepcopy(control)

    def _delete_hook_breakpoint(self, identifier):
        self._qemu_hook_internal_delete = True
        try:
            return self.delete_breakpoint(identifier)
        finally:
            self._qemu_hook_internal_delete = False

    @_locked
    def hook(self, address, *, actions, once=True, max_hits=1, cs=None,
             access='x', length=1, space=None, task=None):
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
        task_binding = deepcopy(getattr(self, '_dos_task_binding', None))
        if task is not None:
            registry = getattr(self, '_dos_task_views', {})
            if not isinstance(task, str) or task not in registry:
                raise ValueError('Unknown registered DOS task')
            task_binding = deepcopy(registry[task]['binding'])
            if task_binding.get('task_id') != task:
                raise ValueError('Registered DOS task identity differs')
        if task_binding is not None:
            from .qemu_dos_tasks import require_task
            require_task(self, binding=task_binding)
        with self._hook_binding(task_binding):
            linear, _, _, _ = self._layer_spans(address, length, space, cs)
        checked = deepcopy(actions)
        for action in checked:
            if not isinstance(action, dict):
                raise ValueError('Hook actions must be objects')
            if action.get('op') in ('layers', 'task-layers') and set(action) == {'op', 'layers'}:
                ids = action['layers']
                if not isinstance(ids, list) or len(ids) > 64 or any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)):
                    raise ValueError('Invalid hook layer stack')
                if action['op'] == 'task-layers' and (task is None or not hasattr(self, 'dos_task_layers')):
                    raise ValueError('Task-layer action requires a registered task view')
                if action['op'] == 'layers' and not self.capabilities.get('code_layers'):
                    raise ValueError('Hook layer action requires QEMU code layers')
                for layer in ids:
                    definition = self.project.debug_layer_info(layer)
                    if definition['version'] != self.version['id']:
                        raise ValueError('Hook layer version mismatch')
                    if action['op'] == 'task-layers':
                        from .qemu_dos_tasks import task_key
                        native = definition.get('native_binding') or {}
                        if (native.get('scope') != 'task-private' or
                                task_key(native.get('task_identity')) != task_key(task_binding)):
                            raise ValueError('Hook task layer belongs to a different task view')
            elif action.get('op') == 'redirect' and set(action) == {'op', 'address'}:
                with self._hook_binding(task_binding):
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
        siblings = [item for item in getattr(self, '_qemu_hooks', {}).values()
                    if (item['runtime_address'], item['access'], item['length']) == (linear, access, length)]
        if siblings:
            from .qemu_dos_tasks import task_key
            if task_binding is None or any(item.get('task_identity') is None or
                    task_key(item['task_identity']) == task_key(task_binding) for item in siblings):
                raise ValueError('Ambiguous hook already owns this breakpoint for the task')
            point = {'breakpoint_id': siblings[0]['breakpoint_id']}
        else:
            point = self.breakpoint(linear, access=access, length=length)
        control = dict(hook=uuid.uuid4().hex, breakpoint_id=point['breakpoint_id'],
                       address=address, cs=cs, space=space, runtime_address=linear,
                       access=access, length=length,
                       epoch=self._layer_epoch(), actions=checked, once=once,
                       max_hits=max_hits, hits=0, dispatch='paused_rpc', extra_guest_bytes=0,
                       task_identity=task_binding, task_id=task)
        if not hasattr(self, '_qemu_hooks'): self._qemu_hooks = {}
        self._hook_reindex([*self._qemu_hooks.values(), control])
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
            self._hook_remove(item)
            if getattr(self, '_qemu_hook_pending', None) == hook:
                peer = next((x for x in self._qemu_hooks.values()
                             if x['breakpoint_id'] == item['breakpoint_id']), None)
                self._qemu_hook_pending = peer['hook'] if peer else None
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
        candidates = [item for item in getattr(self, '_qemu_hooks', {}).values()
                      if item['breakpoint_id'] == ids[0]]
        if not candidates:
            return None
        control = candidates[0]
        expected = 'breakpoint' if control.get('access', 'x') == 'x' else 'watchpoint'
        if result.get('outcome') != expected:
            return None
        task_binding = control.get('task_identity')
        observed = None
        if task_binding is not None:
            from .qemu_dos_tasks import observe_task, task_key
            try:
                if (getattr(self,'_dos_scheduler',None) or {}).get('enabled'):
                    from .qemu_dos_scheduler import _status
                    _status(self,adopt=True)
                observed = observe_task(self, binding=task_binding)
                selected = [item for item in candidates if item.get('task_identity') is not None
                            and task_key(item['task_identity']) == task_key(observed['task_identity'])]
                if len(selected) > 1:
                    raise ValueError('Ambiguous task hook breakpoint')
            except BaseException as error:
                self.close()
                if getattr(error, 'result', None) is None:
                    error.result = result
                raise
            if not selected:
                return dict(task_switch=True, hook=control['hook'], task=observed)
            control = selected[0]
        evidence = dict(hook=control['hook'], hit=control['hits'] + 1,
                        stop=deepcopy(result), actions=[], dispatch='paused_rpc', extra_guest_bytes=0)
        try:
          with self._hook_binding(control.get('task_identity')):
            linear, _, _, _ = self._layer_spans(control['address'], control.get('length', 1), control['space'], control['cs'])
            if self._layer_epoch() != control['epoch'] or linear != control['runtime_address']:
                raise ValueError('Hook source mapping or epoch changed')
            control['hits'] += 1
            exhausted = control['once'] or control['hits'] >= control['max_hits']
            if exhausted:
                self._hook_remove(control)
            for action in control['actions']:
                if action['op'] == 'layers':
                    change = self.layers(action['layers'])
                elif action['op'] == 'task-layers':
                    change = self.dos_task_layers(active=action['layers'], task=control['task_id'])
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
            evidence['breakpoint_id'] = ids[0]
            if observed is not None:
                evidence['task'] = observed
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
        peers = [item for item in self._qemu_hooks.values() if item['breakpoint_id'] == old]
        others = [item for item in self._qemu_hooks.values() if item['breakpoint_id'] != old]
        self._delete_hook_breakpoint(old)
        self._hook_reindex(others)
        try:
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining < 1: raise TimeoutError('Hook deadline expired before step-over')
            stepped = self._execute('s', remaining)
            if stepped['outcome'] in ('guest_exit', 'guest_tsr', 'exited'):
                return stepped
            point = self.breakpoint(control['runtime_address'], access=control['access'], length=control['length'])
            for item in peers:
                item['breakpoint_id'] = point['breakpoint_id']
            self._hook_reindex([*others, *peers])
            # A renderer fence may complete while this displaced instruction
            # single-steps. Preserve that actual stop even if GDB attributes a
            # coincident trap to the step; another continue would lose the
            # completed publication boundary.
            frame_stop = getattr(self, '_frame_stop_after_step', None)
            if frame_stop is not None and frame_stop():
                return stepped
            if stepped.get('save_boundary_conflict'):
                return stepped
            return stepped if stepped['outcome'] != 'step' else None
        except BaseException:
            self.close()
            raise

    def _run_with_hooks(self, *, timeout_ms, stop_on_hook):
        deadline = min(time.monotonic() + timeout_ms / 1000, self.vm.operation_deadline)
        hits = []
        pending_stop = None
        pending = getattr(self, '_qemu_hook_pending', None)
        if pending is not None:
            control = next((x for x in self._qemu_hooks.values() if x['hook'] == pending), None)
            self._qemu_hook_pending = None
            if control is not None:
                previous_task = getattr(self, '_qemu_hook_pending_task', None)
                if (control['access'] == 'x' and previous_task is not None
                        and control.get('task_identity') is not None):
                    from .qemu_dos_tasks import observe_task
                    try:
                        current = observe_task(self, binding=control['task_identity'])
                        same_site = int(self.registers()['linear_pc'], 16) == control['runtime_address']
                    except BaseException:
                        self.close()
                        raise
                    if current.get('task_id') != previous_task and same_site:
                        pending_stop = dict(outcome='breakpoint' if control['access'] == 'x' else 'watchpoint',
                            session=dict(stop_reason=dict(breakpoint_ids=[control['breakpoint_id']])))
                if pending_stop is None:
                    stepped = self._hook_step_over(control, deadline)
                    if stepped is not None:
                        # An interrupted single step may have stopped before
                        # the trapped instruction completed. Preserve the
                        # already-dispatched hook across the explicit resume;
                        # the next step-over checks its PC and task again.
                        if stepped.get('outcome') not in ('guest_exit', 'guest_tsr', 'exited'):
                            self._qemu_hook_pending = control['hook']
                            self._qemu_hook_pending_task = previous_task
                        stepped['hook_hits'] = hits
                        return stepped
        self._qemu_hook_pending_task = None
        while True:
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining < 1:
                if hits: self.close()
                error = TimeoutError('Hook run deadline expired before native continuation')
                if hits: error.result = hits[-1]['stop']
                raise error
            if pending_stop is not None:
                result, pending_stop = pending_stop, None
            else:
                try:
                    result = self._execute('c', remaining)
                except BaseException:
                    if hits: self.close()
                    raise
            evidence = self._dispatch_qemu_hook(result)
            if evidence is None:
                result['hook_hits'] = hits
                return result
            if evidence.get('task_switch') is True:
                self._qemu_hook_pending = evidence['hook']
                self._qemu_hook_pending_task = evidence['task'].get('task_id')
                result['outcome'] = 'task-switch'
                result['task'] = evidence['task']
                result['hook_hits'] = hits
                return result
            hits.append(evidence)
            control = next((x for x in self._qemu_hooks.values() if x['hook'] == evidence['hook']), None)
            if control is None:
                control = next((x for x in self._qemu_hooks.values()
                                if x['breakpoint_id'] == evidence['breakpoint_id']), None)
            if stop_on_hook or result.get('save_boundary_conflict'):
                if control is not None:
                    self._qemu_hook_pending = control['hook']
                    self._qemu_hook_pending_task = evidence.get('task', {}).get('task_id')
                result['outcome'] = 'hook'
                result['hook_hits'] = hits
                return result
            # A live repeat breakpoint at the current PC must be stepped over
            # with its breakpoint temporarily removed. A redirected hook does
            # not execute the old instruction. Any non-step result is retained.
            if control is not None:
                stepped = self._hook_step_over(control, deadline)
                if stepped is not None:
                    if stepped.get('outcome') not in ('guest_exit', 'guest_tsr', 'exited'):
                        self._qemu_hook_pending = control['hook']
                        self._qemu_hook_pending_task = evidence.get('task', {}).get('task_id')
                    stepped['hook_hits'] = hits
                    return stepped
