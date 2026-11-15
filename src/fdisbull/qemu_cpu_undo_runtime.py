"""Freeze-only inverse projection for selected QEMU DOS CPU and RAM state.

This provider never restores a cached CPU slot and never claims machine rewind.
The caller must keep the selected machine stopped, validate the returned
preimage, and close the owner after any uncertain write result.
"""
from copy import deepcopy
import hashlib
import json

from .dosbox_rpc import DebuggerError
from .qemu_dos_checkpoint import _origin, _verify_process
from .qemu_dos_tasks import require_task


REGISTERS = (
    'rax', 'rcx', 'rdx', 'rbx', 'rsp', 'rbp', 'rsi', 'rdi',
    'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15', 'rip', 'eflags',
)
_ALIASES = {
    'rax': ('rax', 'eax'), 'rcx': ('rcx', 'ecx'), 'rdx': ('rdx', 'edx'),
    'rbx': ('rbx', 'ebx'), 'rsp': ('rsp', 'esp'), 'rbp': ('rbp', 'ebp'),
    'rsi': ('rsi', 'esi'), 'rdi': ('rdi', 'edi'), 'rip': ('rip', 'eip'),
}
_ARITHMETIC_FLAGS = 0x8D5
_MAX_RANGES = 64
_MAX_BYTES = 65536


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _uint(value, name, maximum=(1 << 64) - 1):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(name + ' must be an unsigned bounded integer')
    return value


def _number(value, name):
    if isinstance(value, str):
        try:
            value = int(value, 0)
        except ValueError:
            raise ValueError(name + ' is not an integer') from None
    return _uint(value, name)


def _register_values(session, names=REGISTERS):
    snapshot = session.registers()
    raw = snapshot.get('registers') if isinstance(snapshot, dict) else None
    if not isinstance(raw, dict):
        raise DebuggerError('Selected QEMU CPU registers are unavailable')
    described = {item.get('name') for item in getattr(session.vm.gdb, 'register_description', ())
                 if isinstance(item, dict)}
    result, gdb_names = {}, {}
    for name in names:
        actual = next((candidate for candidate in _ALIASES.get(name, (name,))
                       if candidate in raw and candidate in described), None)
        if actual is None or raw[actual] is None:
            raise ValueError('QEMU GDB does not expose selected register ' + name)
        value = raw[actual]
        if type(value) is str:
            try:
                value = int(value, 0)
            except ValueError:
                raise DebuggerError('Invalid QEMU register receipt: ' + name) from None
        if type(value) is not int or not 0 <= value < 1 << 64:
            raise DebuggerError('Invalid QEMU register width: ' + name)
        if name == 'eflags' and value > 0xffffffff:
            raise DebuggerError('QEMU EFLAGS exceeds the supported 32-bit width')
        result[name] = value
        gdb_names[name] = actual
    return snapshot, result, gdb_names


def _validate_register_map(values, *, allow_partial=False):
    if not isinstance(values, dict) or (not allow_partial and set(values) != set(REGISTERS)):
        raise ValueError('QEMU CPU projection requires the complete selected register set')
    if (not allow_partial and not values) or set(values) - set(REGISTERS):
        raise ValueError('QEMU CPU projection contains an unsupported register')
    result = {}
    for name, value in values.items():
        maximum = 0xffffffff if name == 'eflags' else (1 << 64) - 1
        result[name] = _number(value, name)
        if result[name] > maximum:
            raise ValueError('QEMU register exceeds its supported width: ' + name)
    return result


def _physical_addresses(spans):
    result = []
    for start, length in spans:
        if type(start) is not int or type(length) is not int or length < 1:
            raise ValueError('Source range has an invalid physical RAM span')
        result.extend(range(start, start + length))
    return result


def normalize_ranges(session, ranges):
    """Resolve source-address ranges into ordered, uniquely backed RAM spans."""
    if not isinstance(ranges, list) or not 1 <= len(ranges) <= _MAX_RANGES:
        raise ValueError('QEMU CPU undo requires 1..64 source RAM ranges')
    process = getattr(session, '_process', None)
    if not isinstance(process, dict) or process.get('state') != 'active':
        raise ValueError('QEMU CPU undo requires an active source-bound DOS process')
    require_task(session)
    total, seen, normalized = 0, set(), []
    for item in ranges:
        if (not isinstance(item, dict) or set(item) - {'address', 'length', 'cs'}
                or not {'address', 'length'} <= set(item)):
            raise ValueError('A QEMU CPU undo range requires source address, length and optional cs')
        length = _uint(item['length'], 'range length', _MAX_BYTES)
        if length == 0:
            raise ValueError('QEMU CPU undo ranges must be nonempty')
        total += length
        if total > _MAX_BYTES:
            raise ValueError('QEMU CPU undo ranges exceed 65536 bytes')
        linear, static, spans, state = session._layer_spans(
            item['address'], length, 'source', item.get('cs'))
        if state.get('machine_vcpus') != 1 or state.get('register_context_match') is not True:
            raise ValueError('QEMU CPU undo requires one matching stopped vCPU')
        addresses = _physical_addresses(spans)
        if len(addresses) != length:
            raise ValueError('Source mapping does not cover the requested RAM range')
        for start, count in spans:
            session._layer_ram_extent(start, count)
        if seen.intersection(addresses):
            raise ValueError('QEMU CPU undo ranges alias the same physical RAM byte')
        seen.update(addresses)
        normalized.append(dict(address=hex(static), length=length, linear=hex(linear),
                               spans=[dict(address=start, length=count) for start, count in spans]))
    return normalized


def _admission(session):
    if session.closed or session.vm is None or session.vm.qmp is None:
        raise ValueError('QEMU CPU undo requires an open machine owner')
    if getattr(session.project.db, 'in_transaction', False):
        raise ValueError('QEMU CPU undo requires a project outside a caller-owned transaction')
    session._stopped()
    snapshot = session.registers()
    if snapshot.get('address_state', {}).get('machine_vcpus') != 1:
        raise ValueError('QEMU CPU undo requires one selected vCPU')
    history_admission = getattr(session, '_history_admission', None)
    if history_admission is not None:
        history_admission()
    else:
        from .qemu_dos_checkpoint import _preflight, _serial_idle
        _preflight(session)
        _serial_idle(session)
    if getattr(session.vm, '_active_frame_fence', None) is not None:
        raise ValueError('QEMU CPU undo cannot run with an active renderer frame fence')


def _selected_task_proof(session):
    selected = require_task(session)
    if selected is None:
        return dict(identity=None, native_epoch=None, scheduler_generation=None,
                    context_generation=None, private_view=None, binding=None)
    identity = selected.get('task_identity')
    if identity is None and getattr(session, '_dos_task_monitor', None):
        from .qemu_dos_task_views import selected_view
        row = selected_view(session)
        identity = row['binding']
    proof = dict(identity=deepcopy(selected.get('task_identity')),
                 native_epoch=selected.get('native_epoch'),
                 scheduler_generation=selected.get('scheduler_generation'),
                 context_generation=selected.get('context_generation'),
                 private_view=None, binding=deepcopy(getattr(session, '_dos_task_binding', None)))
    proof['identity'] = deepcopy(identity)
    if getattr(session, '_dos_task_monitor', None):
        from .qemu_dos_task_views import _observe, _row
        row = _row(session)
        proof['private_view'] = _observe(session, row)
        proof['active_layers'] = list(row['active'])
        proof['layer_generation'] = row['generation']
        proof['backings'] = deepcopy(row['pages'])
    return proof


def _scheduler_proof(session, selected):
    if not getattr(session, '_dos_scheduler', None):
        return None, None
    from .qemu_dos_scheduler import _context, _status
    raw = _status(session)
    if raw.get('pending-switch'):
        raise ValueError('QEMU CPU undo refuses a pending native task switch')
    if raw.get('fault'):
        raise ValueError('QEMU CPU undo refuses a faulted native task scheduler')
    selected_key = (raw.get('selected-uuid'), raw.get('selected-cookie'), raw.get('selected-incarnation'))
    identity = selected.get('identity') or {}
    if selected_key != (identity.get('monitor_uuid'), identity.get('cookie'), identity.get('incarnation')):
        raise ValueError('QEMU native scheduler selection differs from the selected DOS task')
    context = _context(session.vm, session._dos_task_binding)
    return raw, context


def _stable_scheduler(raw):
    if raw is None:
        return None
    # Selected architectural registers are the intended inverse. Keep their
    # slot identity and frame ownership, while removing live PC/SP/flags and
    # aggregate context digests that necessarily follow those registers.
    value = deepcopy(raw)
    for task in value.get('tasks', []):
        for field in ('eip', 'esp', 'eflags', 'context-sha256'):
            task.pop(field, None)
        for page in task.get('pages', []):
            page.pop('sha256', None)
    return value


def _frame_context(context):
    if context is None:
        return None
    return dict(mode=context.get('mode'), cpl=context.get('cpl'),
        segments=deepcopy(context.get('segments')),
        system_segments=deepcopy(context.get('system-segments')),
        cr0=context.get('cr0'), cr2=context.get('cr2'), cr3=context.get('cr3'),
        cr4=context.get('cr4'), efer=context.get('efer'), a20_mask=context.get('a20-mask'),
        xstate_sha256=context.get('xstate-sha256'),
        interrupt_depth=context.get('interrupt-depth'), frames=deepcopy(context.get('frames')))


def _controller_proof(session, scheduler):
    query_keys = getattr(session, '_frame_keys_query', None)
    from .qemu_frame_keys import FRAME_KEY_COMMANDS
    has_key_api = FRAME_KEY_COMMANDS <= getattr(session.vm, 'qmp_commands', frozenset())
    if not has_key_api and getattr(session.vm, '_frame_key_owner', None) is not None:
        raise ValueError('QEMU frame-key owner is unavailable in this machine profile')
    keys = query_keys() if query_keys is not None and has_key_api else None
    hooks = deepcopy(getattr(session, '_qemu_hooks', {}))
    pending_hook = getattr(session, '_qemu_hook_pending', None)
    pending_task = getattr(session, '_qemu_hook_pending_task', None)
    selected_task = (getattr(session, '_dos_task_binding', None) or {}).get('task_id')
    if pending_hook is not None and pending_task not in (None, selected_task):
        raise ValueError('QEMU CPU undo refuses a hook pending for another task')
    return dict(scheduler=_stable_scheduler(scheduler), frame_keys=deepcopy(keys),
        hooks=hooks, pending_hook=pending_hook, pending_task=pending_task)


def _binding(session, snapshot, selected, scheduler, native_context, ranges, views):
    state = snapshot.get('address_state', {})
    control = state.get('control', {})
    process = session._process
    context = _frame_context(native_context)
    if context is None:
        context = dict(cpu_mode=snapshot.get('cpu_mode'),
            address_control={key: control.get(key) for key in ('CR0', 'CR2', 'CR3', 'CR4', 'EFER')},
            segments=deepcopy(state.get('segments')))
    control_eflags = snapshot.get('registers', {}).get('eflags',
        snapshot.get('registers', {}).get('rflags'))
    if isinstance(control_eflags, str):
        control_eflags = int(control_eflags, 0)
    layer_state = []
    for view in views:
        layer_state.append(dict(scope=view.get('scope'),
            generation=view.get('task_generation') if view.get('scope') == 'task-private'
                      else view.get('layer_generation'),
            active=deepcopy(view.get('active_layers')),
            backings=deepcopy(view.get('backings'))))
    return dict(format='fdisbull-qemu-cpu-undo-binding-1',
        source_sha256=session.metadata.get('source_sha256'),
        version_id=session.version.get('id'), version_sha256=session.metadata.get('version_sha256'),
        run_id=session.run_id, process_nonce_sha256=_sha(bytes(session._nonce)),
        runtime_epoch=getattr(session, '_runtime_epoch', None),
        allocation=deepcopy(process.get('allocation')),
        source_mapping=deepcopy(process.get('source_mapping')),
        selected_task=deepcopy(selected.get('identity')),
        native_epoch=selected.get('native_epoch'),
        scheduler_generation=selected.get('scheduler_generation'),
        context_generation=selected.get('context_generation'),
        scheduler_context=context,
        scheduler_frontier=_stable_scheduler(scheduler),
        address_control={key: control.get(key) for key in ('CR0', 'CR2', 'CR3', 'CR4', 'EFER')},
        eflags_control=(control_eflags & ~_ARITHMETIC_FLAGS) if type(control_eflags) is int else None,
        cpu_mode=snapshot.get('cpu_mode'), segments=deepcopy(state.get('segments')),
        ranges=deepcopy(ranges), layer_state=layer_state)


def _view_proof(session, context, evidence, normalized):
    descriptor = context.get('qemu_memory_view')
    if not isinstance(descriptor, dict) or descriptor.get('format') != 'fdisbull-qemu-memory-view-1' or descriptor.get('view') != 'ram':
        raise DebuggerError('Selected QEMU RAM range lacks explicit RAM-view identity')
    from .qemu_memory_views import _physical_pages
    pages = evidence.get('pages')
    if not isinstance(pages, list):
        raise DebuggerError('Selected QEMU RAM range lacks page-table evidence')
    address = int(normalized['linear'], 16)
    expected = _physical_addresses([(row['address'], row['length']) for row in normalized['spans']])
    mapped = _physical_addresses(_physical_pages(address, normalized['length'], 'linear', pages))
    if expected != mapped:
        raise DebuggerError('Source and explicit RAM-view mappings differ')
    return descriptor


def observe(session, ranges, registers=REGISTERS):
    """Capture selected registers and source RAM with stable owner proofs."""
    _admission(session)
    requested = tuple(registers) if isinstance(registers, (list, tuple)) else None
    if (requested is None or not requested or len(set(requested)) != len(requested)
            or any(name not in REGISTERS for name in requested)):
        raise ValueError('QEMU CPU undo requires unique exposed register names')
    normalized = (normalize_ranges(session, ranges)
                  if ranges and 'spans' not in ranges[0] else deepcopy(ranges))
    snapshot, full_cpu, gdb_names = _register_values(session, REGISTERS)
    cpu = {name: full_cpu[name] for name in requested}
    selected = _selected_task_proof(session)
    scheduler, native_context = _scheduler_proof(session, selected)
    from .memory_search_runtime import _capture
    task_id = (selected.get('identity') or {}).get('task_id')
    ram, contexts, descriptors = [], [], []
    for item in normalized:
        start = int(item['linear'], 16)
        data, context, evidence = _capture(session, start, item['length'], 'linear', task_id, view='ram')
        if not isinstance(data, bytes) or len(data) != item['length']:
            raise DebuggerError('Selected QEMU RAM view returned an incomplete range')
        descriptor = _view_proof(session, context, evidence, item)
        ram.append(data)
        contexts.append(dict(context=deepcopy(context), evidence=deepcopy(evidence)))
        descriptors.append(deepcopy(descriptor))
    controller = _controller_proof(session, scheduler)
    binding = _binding(session, snapshot, selected, scheduler, native_context, normalized, descriptors)
    proof = dict(selected=selected, scheduler=scheduler, native_context=native_context,
        controller=controller, full_cpu=full_cpu, full_register_names=gdb_names,
        full_register_sha256=_sha(_json(full_cpu)), registers_sha256=_sha(_json(cpu)),
        range_sha256=[_sha(value) for value in ram], memory_contexts=[deepcopy(item['context']) for item in contexts],
        memory_views=descriptors)
    return dict(cpu=cpu, ram=ram, binding=binding, contexts=contexts,
        register_snapshot=snapshot, register_names={name:gdb_names[name] for name in requested},
        proof=proof, ranges=normalized)


def _validate_target(session, observed, target_cpu, target_ram):
    current = observed['cpu']
    full = observed['proof']['full_cpu']
    target = _validate_register_map(target_cpu, allow_partial=True)
    if set(target) - set(current):
        raise ValueError('Undo target includes registers outside the captured projection')
    merged = dict(full)
    merged.update(target)
    if (full['eflags'] ^ merged['eflags']) & ~_ARITHMETIC_FLAGS:
        raise ValueError('QEMU CPU undo may change arithmetic flags only')
    depth = (observed['proof'].get('native_context') or {}).get('interrupt-depth', 0)
    if depth and full['rsp'] != merged['rsp']:
        raise ValueError('QEMU CPU undo cannot change RSP with owned interrupt frames')
    ranges = observed['ranges']
    if not isinstance(target_ram, list) or len(target_ram) != len(ranges):
        raise ValueError('QEMU CPU undo target RAM must match its normalized ranges')
    ram = []
    for index, (value, item) in enumerate(zip(target_ram, ranges)):
        if isinstance(value, str):
            try:
                value = bytes.fromhex(value)
            except ValueError:
                raise ValueError('Invalid target RAM hex for range ' + str(index)) from None
        if not isinstance(value, bytes) or len(value) != item['length']:
            raise ValueError('QEMU CPU undo target RAM length differs for range ' + str(index))
        ram.append(value)
    if merged['rip'] != full['rip']:
        _verify_process(session, session._process, _origin(session))
        state = observed['register_snapshot'].get('address_state', {})
        cs = state.get('segments', {}).get('cs')
        if not isinstance(cs, dict) or cs.get('base') is None:
            raise ValueError('Target PC cannot be linearized from a verified CS cache')
        cs_base = int(cs['base'], 0) if isinstance(cs['base'], str) else cs['base']
        code_bits = state.get('code_bits')
        target_ip = merged['rip'] & 0xffffffff if code_bits in (16, 32) else merged['rip']
        target_linear = cs_base + target_ip
        mapping = session._process.get('source_mapping', {})
        extents = mapping.get('live_ranges', [])
        if not any(extent['runtime_address'] <= target_linear < extent['runtime_address'] + extent['length']
                   for extent in extents):
            raise ValueError('QEMU CPU undo target PC is outside the verified source module')
    if getattr(session, '_qemu_hook_pending', None) is not None and merged['rip'] != full['rip']:
        raise ValueError('QEMU CPU undo cannot displace a pending hook stop')
    return merged, ram


def prepare(session, ranges, observed, target_cpu, target_ram):
    """Preflight the entire selected inverse, including all RAM layer spans."""
    if not isinstance(observed, dict) or not isinstance(observed.get('binding'), dict):
        raise ValueError('QEMU CPU undo requires an owned observation')
    normalized = (normalize_ranges(session, ranges)
                  if ranges and 'spans' not in ranges[0] else deepcopy(ranges))
    if normalized != observed.get('ranges'):
        raise ValueError('QEMU CPU undo ranges differ from the captured projection')
    selected_names = tuple(observed.get('cpu', {}))
    fresh = observe(session, normalized, selected_names)
    if (fresh['binding'] != observed['binding'] or fresh['cpu'] != observed['cpu']
            or fresh['ram'] != observed['ram']):
        raise ValueError('Selected QEMU CPU or RAM changed before undo preparation')
    merged_cpu, ram = _validate_target(session, observed, target_cpu, target_ram)
    from .qemu_memory_views import prepare_qemu_memory_write, _spans
    parts = []
    for index, item in enumerate(normalized):
        parts.append(prepare_qemu_memory_write(session, observed['contexts'][index]['context'],
            int(item['linear'], 16), observed['ram'][index], ram[index]))
    scopes = {part['scope'] for part in parts}
    if len(scopes) != 1:
        raise ValueError('QEMU CPU undo cannot mix machine and task-private RAM views')
    physical = [address for part in parts for address in part['physical_addresses']]
    if len(physical) != len(set(physical)) or len(physical) > _MAX_BYTES:
        raise ValueError('QEMU CPU undo physical projection aliases or exceeds 65536 bytes')
    first = parts[0]
    if any(part['active_before'] != first['active_before'] or part['generation'] != first['generation']
           for part in parts):
        raise ValueError('QEMU CPU undo layer state changed while preparing')
    binding = deepcopy(first['binding'])
    binding['spans'] = _spans(physical)
    if first['scope'] == 'task-private':
        split = []
        for start, length in binding['spans']:
            cursor, end = start, start + length
            while cursor < end:
                count = min(4096 - (cursor & 4095), end - cursor)
                split.append([cursor, count])
                cursor += count
        if len(split) > 17:
            raise ValueError('QEMU CPU undo private overlay crosses too many backing spans')
        binding['spans'] = split
    from .qemu_memory_views import _check_overlay_budget
    _check_overlay_budget(session, first['active_after'], physical)
    prepared = dict(first, binding=binding, physical_addresses=physical,
        expected=b''.join(part['expected'] for part in parts),
        base=b''.join(part['base'] for part in parts), replacement=b''.join(ram),
        parts=parts, ranges=normalized, target_cpu=merged_cpu, target_ram=ram,
        target_registers=deepcopy(target_cpu), observed=deepcopy(observed),
        before_views=deepcopy(observed['proof']['memory_views']))
    return prepared


def _expected_cpu(before, target):
    result = deepcopy(before)
    result.update(target)
    return result


def _changed_paths(before, after, prefix='', limit=16):
    """Return a compact list of differing proof paths for refusal diagnostics."""
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        paths = []
        for key in sorted(set(before) | set(after)):
            name = f'{prefix}.{key}' if prefix else str(key)
            if key not in before or key not in after:
                paths.append(name)
            else:
                paths.extend(_changed_paths(before[key], after[key], name, limit - len(paths)))
            if len(paths) >= limit:
                return paths[:limit]
        return paths
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        paths = []
        for index, (left, right) in enumerate(zip(before, after)):
            paths.extend(_changed_paths(left, right, f'{prefix}[{index}]', limit - len(paths)))
            if len(paths) >= limit:
                return paths[:limit]
        return paths
    return [prefix or '<root>']


def _expected_task_layer_generation(binding, controller, scope, transition):
    expected_binding = deepcopy(binding)
    expected_controller = deepcopy(controller)
    if transition is not None and scope == 'task-private':
        for proof in (expected_binding.get('scheduler_frontier'),
                      expected_controller.get('scheduler')):
            if isinstance(proof, dict):
                generation = proof.get('generation')
                if type(generation) is not int or generation >= (1 << 64) - 1:
                    raise DebuggerError('Native task manager generation cannot advance safely')
                proof['generation'] = generation + 1
    return expected_binding, expected_controller


def apply(session, plan):
    """Apply one RAM overlay and one guarded GDB register batch while stopped."""
    if not isinstance(plan, dict) or not isinstance(plan.get('observed'), dict):
        raise ValueError('Invalid QEMU CPU undo plan')
    selected_names = tuple(plan['observed']['cpu'])
    before = observe(session, plan['ranges'], selected_names)
    if (before['binding'] != plan['observed']['binding'] or before['cpu'] != plan['observed']['cpu']
            or before['ram'] != plan['observed']['ram']):
        raise ValueError('QEMU CPU undo preimage changed before dispatch')
    transition = None
    dispatched = False
    try:
        if any(old != new for old, new in zip(plan['expected'], plan['replacement'])):
            from .qemu_memory_views import commit_qemu_memory_write
            dispatched = True
            transition = commit_qemu_memory_write(session, plan)
        edits = {}
        selected_before = plan['observed']['cpu']
        for name, wanted in plan['target_registers'].items():
            current = selected_before[name]
            if wanted != current:
                actual = plan['observed']['register_names'].get(name)
                if actual is None:
                    raise ValueError('No guarded GDB register binding for ' + name)
                edits[actual] = dict(expected=current, value=wanted)
        if edits:
            dispatched = True
            session.write_registers(edits)
        after = observe(session, plan['ranges'], selected_names)
        expected_selected = _expected_cpu(selected_before, plan['target_registers'])
        if after['cpu'] != expected_selected:
            raise DebuggerError('Selected QEMU register readback differs from the undo target')
        if after['ram'] != plan['target_ram']:
            raise DebuggerError('Selected QEMU RAM readback differs from the undo target')
        expected_full = _expected_cpu(plan['observed']['proof']['full_cpu'], plan['target_registers'])
        if after['proof']['full_cpu'] != expected_full:
            raise DebuggerError('An unselected QEMU register changed during the undo')
        if transition is None:
            if after['proof']['memory_views'] != plan['before_views']:
                raise DebuggerError('QEMU RAM view changed without an overlay transition')
        else:
            overlay = transition['qemu_rule_overlay']
            from .qemu_memory_views import expected_memory_view_after
            expected_views = [expected_memory_view_after(descriptor, part, overlay)
                              for descriptor, part in zip(plan['before_views'], plan['parts'])]
            if after['proof']['memory_views'] != expected_views:
                raise DebuggerError('QEMU RAM layer stack did not make the expected single transition')
        stable_before = deepcopy(before['binding'])
        stable_after = deepcopy(after['binding'])
        stable_before.pop('layer_state', None)
        stable_after.pop('layer_state', None)
        expected_controller_binding, expected_controller = _expected_task_layer_generation(
            stable_before, before['proof']['controller'], plan.get('scope'), transition)
        expected_controller_binding.pop('layer_state', None)
        stable_before = expected_controller_binding
        if stable_after != stable_before:
            changed = ', '.join(_changed_paths(stable_before, stable_after))
            raise DebuggerError('Selected task, mode, frame, hook or controller identity changed during undo: ' + changed)
        if after['proof']['controller'] != expected_controller:
            changed = ', '.join(_changed_paths(expected_controller, after['proof']['controller']))
            raise DebuggerError('QEMU controller or hook ownership changed during undo: ' + changed)
        return dict(observation=after, ram_transition=transition)
    except BaseException:
        if dispatched or getattr(session, 'closed', False):
            try:
                session.close()
            except Exception:
                pass
        raise
