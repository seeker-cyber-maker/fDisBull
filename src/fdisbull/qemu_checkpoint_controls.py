"""Bounded checkpoint sidecars for stopped QEMU host-owned controls.

Machine RAM is saved by QEMU. This module preserves host-owned layer and hook
state separately; it does not make a VM snapshot or qualify its disk, device,
serial, process or clock state. Call under the session's machine lock.
"""
from __future__ import annotations

from copy import deepcopy
import json

from .code_layers import groups
from .dosbox_rpc import DebuggerError

_FORMAT = 'fdisbull-qemu-controls-1'
_TASK_FORMAT = 'fdisbull-qemu-controls-task-2'
_TASK_VIEWS_FORMAT = 'fdisbull-qemu-controls-task-3'
_MAX_BYTES = 64 * 1024 * 1024
_MAX_MAP = 65536
_MAX_LAYERS = 64
_MAX_DEFINITIONS = 256
_MAX_POINTS = 256


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _pack(values):
    return [[key, values[key]] for key in sorted(values)]


def _unpack(rows):
    if not isinstance(rows, list) or len(rows) > _MAX_MAP:
        raise ValueError('Invalid checkpoint control byte map')
    result = {}
    previous = -1
    for pair in rows:
        if (not isinstance(pair, list) or len(pair) != 2 or type(pair[0]) is not int
                or type(pair[1]) is not int or not 0 <= pair[0] <= 0xffffffff
                or not 0 <= pair[1] <= 255 or pair[0] <= previous):
            raise ValueError('Invalid checkpoint control byte map entry')
        previous = pair[0]
        result[pair[0]] = pair[1]
    return result


def _read(session, addresses):
    remote = session._stopped()
    result = {}
    for span in groups(addresses):
        session._layer_ram_extent(span[0], len(span))
        data = remote.memory(span[0], len(span), space='physical')
        if not isinstance(data, bytes) or len(data) != len(span):
            raise DebuggerError('Incomplete checkpoint control backing read')
        result.update(zip(span, data))
    return result


def _definitions(session, identifiers):
    if len(identifiers) > _MAX_DEFINITIONS:
        raise ValueError('Checkpoint control layer budget exceeded')
    result = {}
    for identifier in sorted(identifiers):
        definition = session.project.debug_layer_info(identifier)
        if definition['version'] != session.version['id']:
            raise ValueError('Checkpoint layer version differs from the session')
        result[identifier] = deepcopy(definition)
    return result


def _validate_definition_tasks(definitions, task_binding):
    for definition in definitions.values():
        binding = definition.get('native_binding')
        if binding is None:
            continue
        layer_task = binding.get('task_identity')
        if task_binding is None:
            if 'task_identity' in binding:
                raise ValueError('Unbound checkpoint cannot carry a task-scoped layer')
        elif layer_task is None:
            raise ValueError('Task checkpoint requires task-scoped native layer bindings')
        else:
            from .qemu_dos_tasks import task_key
            if task_key(layer_task) != task_key(task_binding):
                raise ValueError('Checkpoint layer task differs from the selected task')


def _derive(session, active, definitions, origin_run, origin_epoch):
    expected, ram, execute = {}, {}, {}
    patches = 0
    for identifier in active:
        definition = definitions[identifier]
        kind = definition.get('kind')
        if kind not in ('ram', 'execute'):
            raise ValueError('Unsupported checkpoint layer kind')
        for patch in definition['patches']:
            patches += 1
            if patches > 256:
                raise ValueError('Checkpoint layer patch budget exceeded')
            old, new = bytes.fromhex(patch['expected_hex']), bytes.fromhex(patch['data_hex'])
            binding = definition.get('native_binding')
            if binding is None:
                _, _, spans, _ = session._layer_spans(patch['address'], len(old), 'source')
            else:
                if binding.get('run') != origin_run or binding.get('epoch') != origin_epoch:
                    raise ValueError('Checkpoint layer binding differs from its origin epoch')
                layer_task = binding.get('task_identity')
                if layer_task is not None:
                    from .qemu_dos_tasks import task_key
                    current = getattr(session, '_dos_task_binding', None)
                    if current is None or task_key(layer_task) != task_key(current):
                        raise ValueError('Checkpoint layer task differs from the selected task')
                spans = binding.get('spans')
            if not isinstance(spans, (list, tuple)) or not spans or len(old) != len(new):
                raise ValueError('Invalid checkpoint layer extents')
            addresses = []
            for span in spans:
                if (not isinstance(span, (list, tuple)) or len(span) != 2
                        or type(span[0]) is not int or type(span[1]) is not int
                        or not 1 <= span[1] <= _MAX_MAP):
                    raise ValueError('Invalid checkpoint layer span')
                session._layer_ram_extent(span[0], span[1])
                if len(addresses) + span[1] > _MAX_MAP:
                    raise ValueError('Checkpoint layer extent exceeds budget')
                addresses.extend(range(span[0], span[0] + span[1]))
            if len(addresses) != len(old) or len(set(addresses)) != len(addresses):
                raise ValueError('Checkpoint layer span differs from its bytes')
            target = ram if kind == 'ram' else execute
            for address, before, after in zip(addresses, old, new):
                if expected.setdefault(address, before) != before:
                    raise ValueError('Checkpoint layer base definitions conflict')
                target[address] = after
                if len(expected) > _MAX_MAP:
                    raise ValueError('Checkpoint layer byte budget exceeded')
    return expected, ram, execute


def _native_fetch(session, exec_base, execution):
    for span in groups(execution):
        for offset in range(0, len(span), 4096):
            part = span[offset:offset+4096]
            native = session._layer_native_observe(address=part[0], length=len(part))
            if native.get('fault') or native.get('data-hex') != bytes(execution[a] for a in part).hex():
                raise DebuggerError('Checkpoint execution overlay lacks native fetch evidence')
    if _read(session, exec_base) != exec_base:
        raise ValueError('Execution-layer backing changed before checkpoint')


def capture_controls(session):
    """Capture deterministic JSON-safe controls without changing the guest."""
    if session.project is None or session.project.db.in_transaction:
        raise ValueError('Checkpoint controls require a project outside a transaction')
    session._stopped()
    epoch, run = session._layer_epoch(), session.run_id
    task_binding = deepcopy(getattr(session, '_dos_task_binding', None))
    if task_binding is not None:
        from .qemu_dos_tasks import require_task
        require_task(session, binding=task_binding)
    active = list(getattr(session, '_layer_active', []))
    if (len(active) > _MAX_LAYERS or any(not isinstance(i, str) for i in active)
            or len(active) != len(set(active))):
        raise ValueError('Invalid active checkpoint layer stack')
    maps = {key: dict(getattr(session, '_layer_' + key, {})) for key in
            ('ram_base', 'ram_applied', 'exec_base', 'exec')}
    if any(len(value) > _MAX_MAP for value in maps.values()):
        raise ValueError('Checkpoint control map budget exceeded')
    if maps['ram_base'].keys() != maps['ram_applied'].keys() or maps['exec_base'].keys() != maps['exec'].keys():
        raise ValueError('Inconsistent checkpoint layer map extents')
    hooks = deepcopy(list(getattr(session, '_qemu_hooks', {}).values()))
    if len(hooks) > _MAX_POINTS:
        raise ValueError('Checkpoint hook budget exceeded')
    hook_ids = {item['breakpoint_id'] for item in hooks}
    task_views = getattr(session, '_dos_task_views', {})
    if ((len(hook_ids) != len(hooks) and not task_views)
            or any(not isinstance(item.get('hook'), str) for item in hooks)
            or len({item['hook'] for item in hooks}) != len(hooks)):
        raise ValueError('Duplicate checkpoint hook breakpoint')
    pending = getattr(session, '_qemu_hook_pending', None)
    if pending is not None and sum(item['hook'] == pending for item in hooks) != 1:
        raise ValueError('Checkpoint pending hook is not uniquely owned')
    ids = set(active)
    for item in hooks:
        if item.get('task_identity') is not None:
            from .qemu_dos_tasks import task_key
            owner = task_views.get(item['task_identity'].get('task_id'), {}).get('binding', task_binding)
            if owner is None or task_key(item['task_identity']) != task_key(owner):
                raise ValueError('Checkpoint hook task identity differs from the selected task')
        point = session.breakpoints.get(item['breakpoint_id'])
        if (item.get('epoch') != epoch or not isinstance(point, dict)
                or point['address'] != item['runtime_address'] or point['access'] != item['access']
                or point['length'] != item['length'] or type(item.get('hits')) is not int
                or not 0 <= item['hits'] < item['max_hits']):
            raise ValueError('Checkpoint hook ownership changed')
        for action in item['actions']:
            if action.get('op') == 'layers': ids.update(action['layers'])
    reserved = getattr(session, '_return_breakpoint', None)
    points = [{'id': key, **deepcopy(value)} for key, value in session.breakpoints.items()
              if key not in hook_ids and key != reserved]
    if len(points) + len(hooks) > _MAX_POINTS:
        raise ValueError('Checkpoint breakpoint budget exceeded')
    definitions = _definitions(session, ids)
    _validate_definition_tasks(definitions, task_binding)
    expected, ram, execution = _derive(session, active, definitions, run, epoch)
    if maps['ram_applied'] != ram or maps['exec'] != execution:
        raise ValueError('Checkpoint layer definitions differ from owned maps')
    if maps['ram_base'] != {address: expected[address] for address in ram}:
        raise ValueError('Checkpoint RAM-layer base differs from its definitions')
    if maps['exec_base'] != {address: ram.get(address, expected[address]) for address in execution}:
        raise ValueError('Checkpoint execute-layer base differs from its definitions')
    observed = _read(session, maps['ram_applied'].keys() | maps['exec_base'].keys())
    if getattr(session, 'capabilities', {}).get('code_layers'):
        native = session.vm.qmp.call('x-fdisbull-layer-observe')
        if (not isinstance(native, dict) or native.get('fault')
                or native.get('generation') != getattr(session, '_layer_generation', 0)
                or native.get('execution-bytes') != len(maps['exec'])):
            raise ValueError('Checkpoint native layer ownership is not valid')
        if execution:
            _native_fetch(session, maps['exec_base'], execution)
    elif active:
        raise ValueError('Checkpoint layers are not supported by this machine')
    if task_binding is None:
        for item in hooks:
            if item.get('task_identity') is not None:
                raise ValueError('Unbound checkpoint cannot carry a task-scoped hook')
            item.pop('task_identity', None)
    result = dict(format=_TASK_VIEWS_FORMAT if task_views else _TASK_FORMAT if task_binding is not None else _FORMAT,
        run=run, epoch=epoch,
        source_sha256=session.metadata['source_sha256'], version=session.version['id'],
        version_sha256=session.version['sha256'], active=active, definitions=definitions,
        maps={key: _pack(value) for key, value in maps.items()}, observed=_pack(observed),
        hooks=hooks, pending_hook=pending, breakpoints=points)
    if task_binding is not None:
        result['task_identity'] = task_binding
    if task_views:
        result['pending_task'] = getattr(session, '_qemu_hook_pending_task', None)
    if len(_encode(result)) > _MAX_BYTES:
        raise ValueError('Checkpoint controls exceed the sidecar budget')
    return result


def _validate_restored_task_hook(session, item):
    """Validate dormant task controls without running or selecting that task."""
    from .qemu_dos_tasks import task_key
    binding = item.get('task_identity')
    registry = getattr(session, '_dos_task_views', {})
    if binding is None:
        raise ValueError('Private task checkpoint requires task-scoped hooks')
    row = registry.get(binding.get('task_id'))
    if (row is None or row['retired'] or task_key(binding) != task_key(row['binding'])
            or item.get('task_id') not in (None, binding['task_id'])):
        raise ValueError('Restored hook lacks a live registered task lifetime')
    if (type(item.get('runtime_address')) is not int or not 0 <= item['runtime_address'] <= 0xffffffff
            or item.get('access') not in ('x','r','w','rw')
            or type(item.get('length')) is not int or not 1 <= item['length'] <= 65536
            or item['access'] == 'x' and item['length'] != 1
            or type(item.get('once')) is not bool or type(item.get('max_hits')) is not int
            or not 1 <= item['max_hits'] <= 1000 or item.get('space') not in ('source','linear')):
        raise ValueError('Invalid restored private task hook')
    def resolve_source(address, length=1, cs=None):
        static, _ = session.project._dos_parse_address(address, cs)
        for extent in session._process['source_mapping']['live_ranges']:
            offset = static - extent['project_address']
            if 0 <= offset and offset + length <= extent['length']:
                return extent['runtime_address'] + offset
        raise ValueError('Restored task hook source is outside the owned DOS module')
    if item['space'] == 'source':
        runtime = resolve_source(item['address'], item['length'], item.get('cs'))
    else:
        runtime = int(item['address'],0) if isinstance(item['address'],str) else item['address']
    if runtime != item['runtime_address']:
        raise ValueError('Restored task hook address differs from its saved mapping')
    actions = item.get('actions')
    if not isinstance(actions,list) or not 1 <= len(actions) <= 16:
        raise ValueError('Invalid restored task hook actions')
    for action in actions:
        if not isinstance(action,dict): raise ValueError('Invalid restored task hook action')
        op = action.get('op')
        if op in ('layers','task-layers') and set(action) == {'op','layers'}:
            ids = action['layers']
            if (not isinstance(ids,list) or len(ids)>64 or len(ids)!=len(set(ids))
                    or any(not isinstance(i,str) for i in ids)):
                raise ValueError('Invalid restored hook layer stack')
            for identifier in ids:
                definition = session.project.debug_layer_info(identifier)
                if definition['version'] != session.version['id']:
                    raise ValueError('Restored hook layer version changed')
                if op == 'task-layers':
                    native = definition.get('native_binding') or {}
                    if (native.get('scope') != 'task-private'
                            or task_key(native.get('task_identity')) != task_key(binding)):
                        raise ValueError('Restored hook layer has a different private owner')
        elif op == 'redirect' and set(action) == {'op','address'}:
            resolve_source(action['address'])
        elif op == 'registers' and set(action) == {'op','registers'}:
            edits = action['registers']
            if not isinstance(edits,dict) or not edits: raise ValueError('Invalid restored register action')
            for name, change in edits.items():
                if (not isinstance(name,str) or name.lower() in ('cs','eip','rip','ip')
                        or not isinstance(change,dict) or set(change) != {'expected','value'}):
                    raise ValueError('Invalid restored register action')
                for value in change.values():
                    parsed = int(value,0) if isinstance(value,str) else value
                    if type(parsed) is not int or parsed < 0:
                        raise ValueError('Invalid restored register action value')
        else:
            raise ValueError('Unsupported restored task hook action')


def restore_controls(session, controls, old_epoch, *, private_layer_ids=None):
    """Rebind a verified sidecar onto a fresh stopped VM; return new control IDs.

    The QEMU snapshot must already have restored RAM. This never reapplies RAM
    overlays; guest changes to an active RAM layer retain conflict semantics.
    """
    if not isinstance(controls, dict) or len(_encode(controls)) > _MAX_BYTES:
        raise ValueError('Invalid checkpoint controls')
    if (controls.get('format') not in (_FORMAT, _TASK_FORMAT, _TASK_VIEWS_FORMAT) or controls.get('epoch') != old_epoch
            or controls.get('source_sha256') != session.metadata['source_sha256']
            or controls.get('version') != session.version['id']
            or controls.get('version_sha256') != session.version['sha256']):
        raise ValueError('Checkpoint controls differ from the source, version or origin epoch')
    if session.project.db.in_transaction:
        raise ValueError('Checkpoint controls require a project outside a transaction')
    session._stopped()
    saved_task = controls.get('task_identity')
    current_task = getattr(session, '_dos_task_binding', None)
    if controls['format'] in (_TASK_FORMAT, _TASK_VIEWS_FORMAT) and saved_task is None:
        raise ValueError('Task checkpoint controls require a task binding')
    if controls['format'] == _TASK_VIEWS_FORMAT and not getattr(session, '_dos_task_views', {}):
        raise ValueError('Task-view checkpoint controls require the restored private registry')
    if controls['format'] == _FORMAT:
        definitions = controls.get('definitions')
        hooks = controls.get('hooks')
        if ('task_identity' in controls or not isinstance(definitions, dict)
                or not isinstance(hooks, list)
                or any(isinstance(item, dict) and 'task_identity' in item for item in hooks)
                or any(isinstance(item, dict) and isinstance(item.get('native_binding'), dict)
                       and 'task_identity' in item['native_binding'] for item in definitions.values())):
            raise ValueError('Legacy checkpoint controls cannot carry task identities')
    if saved_task is not None or current_task is not None:
        from .qemu_dos_tasks import require_task, task_key
        if saved_task is None or current_task is None or task_key(saved_task) != task_key(current_task):
            raise ValueError('Checkpoint task identity differs from the restored task')
        require_task(session, binding=current_task)
    if session._layer_epoch() == old_epoch:
        raise ValueError('Checkpoint controls require a fresh runtime epoch')
    if (getattr(session, '_layer_active', []) or getattr(session, '_qemu_hooks', {})
            or getattr(session, '_qemu_hook_pending', None)):
        raise ValueError('Checkpoint restore requires empty host control state')
    reserved = getattr(session, '_return_breakpoint', None)
    if set(session.breakpoints) - ({reserved} if reserved else set()):
        raise ValueError('Checkpoint restore requires an empty user breakpoint registry')
    active, definitions = controls.get('active'), controls.get('definitions')
    if (not isinstance(active, list) or len(active) > _MAX_LAYERS
            or any(not isinstance(i, str) for i in active) or len(active) != len(set(active))
            or not isinstance(definitions, dict) or len(definitions) > _MAX_DEFINITIONS
            or any(not isinstance(identifier, str) for identifier in definitions)
            or any(identifier not in definitions for identifier in active)):
        raise ValueError('Invalid checkpoint layer definitions')
    if active and not session.capabilities.get('code_layers'):
        raise ValueError('Fresh QEMU cannot restore layers')
    if _definitions(session, set(definitions)) != definitions:
        raise ValueError('Checkpoint layer definitions or identities changed')
    _validate_definition_tasks(definitions, current_task)
    maps = {key: _unpack(controls['maps'][key]) for key in ('ram_base', 'ram_applied', 'exec_base', 'exec')}
    observed = _unpack(controls['observed'])
    expected, ram, execution = _derive(session, active, definitions, controls['run'], old_epoch)
    if (maps['ram_applied'] != ram or maps['exec'] != execution
            or maps['ram_base'] != {a: expected[a] for a in ram}
            or maps['exec_base'] != {a: ram.get(a, expected[a]) for a in execution}
            or observed.keys() != (ram.keys() | execution.keys())):
        raise ValueError('Checkpoint layer maps do not match their definitions')
    if _read(session, observed) != observed:
        raise ValueError('Restored RAM differs from checkpoint control observation')
    if any(observed[a] != value for a, value in maps['exec_base'].items()):
        raise ValueError('Restored execution-layer backing differs')
    hooks, points = controls.get('hooks'), controls.get('breakpoints')
    if not isinstance(hooks, list) or not isinstance(points, list) or len(hooks) + len(points) > _MAX_POINTS:
        raise ValueError('Invalid checkpoint hook or breakpoint budget')
    if (any(not isinstance(item, dict) or not isinstance(item.get('hook'), str) for item in hooks)
            or any(not isinstance(item, dict) or not isinstance(item.get('id'), str) for item in points)
            or len({item['hook'] for item in hooks}) != len(hooks)
            or len({item['id'] for item in points}) != len(points)):
        raise ValueError('Invalid checkpoint hook or breakpoint identities')
    pending = controls.get('pending_hook')
    if pending is not None and sum(item.get('hook') == pending for item in hooks) != 1:
        raise ValueError('Invalid checkpoint pending hook')
    mutated = False
    try:
        layer_ids = {}
        for identifier in sorted(definitions):
            definition = definitions[identifier]
            binding = definition.get('native_binding')
            if binding is None:
                layer_ids[identifier] = identifier
                continue
            if binding.get('run') != controls['run'] or binding.get('epoch') != old_epoch:
                raise ValueError('Checkpoint layer binding differs from its origin')
            clone = dict(kind=definition['kind'], patches=deepcopy(definition['patches']),
                         native_binding=dict(deepcopy(binding), run=session.run_id, epoch=session._layer_epoch()))
            mutated = True
            layer_ids[identifier] = session.project._store_debug_layer(
                definition['name'], session.version['id'], clone)['layer']
        if not hasattr(session, '_layer_active'):
            session._reset_native_layers()
        if session._layer_generation != 0 or session._layer_exec:
            raise ValueError('Fresh QEMU layer generation is not empty')
        if execution:
            if not session.capabilities.get('code_layers'):
                raise ValueError('Fresh QEMU cannot restore execution layers')
            native = session._layer_native_observe()
            if native.get('fault'):
                raise ValueError('Fresh QEMU execution layer state is faulted')
            chunks = [dict(address=span[0], before=bytes(maps['exec_base'][a] for a in span).hex(),
                           after=bytes(execution[a] for a in span).hex()) for span in groups(execution)]
            mutated = True
            receipt = session.vm.qmp.call('x-fdisbull-layer-configure',
                {'generation': 0, 'ram': [], 'execute': chunks})
            if (not isinstance(receipt, dict) or receipt.get('generation') != 1
                    or receipt.get('ram-bytes') != 0 or receipt.get('execution-bytes') != len(execution)
                    or receipt.get('fault')):
                raise DebuggerError('Invalid restored execution-layer receipt')
            session._layer_generation = 1
        session._layer_active = [layer_ids[i] for i in active]
        session._layer_ram_base = maps['ram_base']; session._layer_ram_applied = maps['ram_applied']
        session._layer_exec_base = maps['exec_base']; session._layer_exec = maps['exec']
        if execution:
            _native_fetch(session, maps['exec_base'], execution)
        point_ids, hook_ids = {}, {}
        for point in points:
            mutated = True
            created = session.breakpoint(point['address'], access=point['access'], length=point['length'])
            point_ids[point['id']] = created['breakpoint_id']
        for item in hooks:
            if (item.get('epoch') != old_epoch or type(item.get('hits')) is not int
                    or type(item.get('max_hits')) is not int or not 0 <= item['hits'] < item['max_hits']):
                raise ValueError('Invalid checkpoint hook epoch or hit count')
            hook_task = item.get('task_identity')
            if hook_task is not None:
                from .qemu_dos_tasks import task_key
                task_views = getattr(session, '_dos_task_views', {}) if controls['format'] == _TASK_VIEWS_FORMAT else {}
                owner = task_views.get(hook_task.get('task_id'), {}).get('binding', current_task)
                if owner is None or task_key(hook_task) != task_key(owner):
                    raise ValueError('Checkpoint hook task differs from the restored task')
            actions = deepcopy(item['actions'])
            for action in actions:
                if action.get('op') == 'layers': action['layers'] = [layer_ids[i] for i in action['layers']]
                elif action.get('op') == 'task-layers':
                    if controls['format'] != _TASK_VIEWS_FORMAT or private_layer_ids is None:
                        raise ValueError('Task-layer hook lacks a restored private stack')
                    action['layers'] = [private_layer_ids[i] for i in action['layers']]
            mutated = True
            if controls['format'] == _TASK_VIEWS_FORMAT:
                restored_item = dict(deepcopy(item), actions=actions)
                _validate_restored_task_hook(session, restored_item)
                created = session._install_restored_qemu_hook(restored_item)
                session._event('hook-restore', dict(hook=item['hook'], breakpoint_id=created['breakpoint_id'],
                    hits=item['hits'], origin_epoch=old_epoch))
                hook_ids[item['hook']] = item['hook']
                continue
            created = session.hook(item['address'], actions=actions, once=item['once'],
                max_hits=item['max_hits'], cs=item['cs'], access=item['access'],
                length=item['length'], space=item['space'])
            if created['runtime_address'] != item['runtime_address']:
                raise ValueError('Restored hook mapping differs from checkpoint')
            rebound = session._qemu_hooks[created['breakpoint_id']]
            rebound['hits'] = item['hits']
            rebound['hook'] = item['hook']
            rebound['task_identity'] = deepcopy(current_task) if hook_task is not None else None
            session._event('hook-restore', dict(hook=item['hook'], created_hook=created['hook'],
                                               breakpoint_id=created['breakpoint_id'],
                                               hits=item['hits'], origin_epoch=old_epoch))
            hook_ids[item['hook']] = item['hook']
        session._qemu_hook_pending = None if pending is None else hook_ids[pending]
        session._qemu_hook_pending_task = controls.get('pending_task')
        if (session._qemu_hook_pending_task is not None and
                session._qemu_hook_pending_task not in getattr(session, '_dos_task_views', {})):
            raise ValueError('Checkpoint pending hook task is not registered')
        return dict(layers=layer_ids, breakpoints=point_ids, hooks=hook_ids,
                    pending_hook=session._qemu_hook_pending, epoch=session._layer_epoch())
    except BaseException:
        if mutated:
            session.close()
        raise
