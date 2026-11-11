"""Explicit RAM/execute views and immutable QEMU memory-edit overlays."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import uuid

from .code_layers import groups
from .dosbox_rpc import DebuggerError
from .qemu_layers import _chunks

FORMAT = 'fdisbull-qemu-memory-view-1'
MAX_VIEW_BYTES = 65536


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _physical_pages(address, length, space, pages):
    """Return ordered (guest physical, byte count) spans for a captured range."""
    spans = []
    if space == 'physical':
        cursor, end = address, address + length
        while cursor < end:
            count = min(4096 - (cursor & 4095), end - cursor)
            spans.append((cursor, count))
            cursor += count
        return spans
    by_linear = {int(row['linear'], 16): int(row['physical'], 16) for row in pages}
    cursor, end = address, address + length
    while cursor < end:
        linear_page = cursor & ~4095
        if linear_page not in by_linear:
            raise ValueError('Memory view has no observed physical mapping for a linear page')
        offset = cursor & 4095
        count = min(4096 - offset, end - cursor)
        spans.append((by_linear[linear_page] + offset, count))
        cursor += count
    return spans


def _task_row(session, task_id):
    from .qemu_dos_task_views import selected_view
    selected = selected_view(session)
    identity = selected['binding']
    if task_id is not None and task_id != identity['task_id']:
        raise ValueError('Task-private memory view must name the currently selected native task')
    return selected


def _task_status(session, row):
    from .qemu_dos_task_views import _observe
    status = _observe(session, row)
    key = (row['binding']['monitor_uuid'], row['binding']['cookie'], row['binding']['incarnation'])
    record = next((item for item in status['tasks'] if
                   (item['uuid'], item['cookie'], item['incarnation']) == key), None)
    if record is None or record.get('retired'):
        raise ValueError('Task-private memory view is retired or absent from the native registry')
    return status, record


def _task_capture(session, row, status, record, address, length, space, pages, view):
    from .qemu_dos_task_views import _read
    if length > MAX_VIEW_BYTES:
        raise ValueError('Explicit QEMU memory views are limited to 65536 bytes')
    spans = _physical_pages(address, length, space, pages)
    page_records = {page['address']: page for page in record['pages']}
    backing_receipts = []
    for physical, _ in spans:
        page = page_records.get(physical & ~4095)
        if page is None:
            raise ValueError('Task-private view requires every mapped page to be registered')
        if page not in backing_receipts:
            backing_receipts.append(page)
    chunks = []
    for physical, count in spans:
        data, receipt = _read(session, row, physical, count, view)
        if receipt.get('active') is not True:
            raise ValueError('Native task-private read does not belong to the selected task view')
        chunks.append(data)
    data = b''.join(chunks)
    descriptor = dict(format=FORMAT, scope='task-private', view=view,
        task_identity={key: deepcopy(row['binding'][key]) for key in
                       ('monitor_uuid', 'cookie', 'incarnation', 'task_id')},
        native_epoch=session._dos_task_monitor['native_epoch'],
        task_generation=row['generation'], active_layers=list(row['active']),
        active_layers_sha256=_digest(row['active']),
        backings=[dict(address=page['address'], backing=page['backing'])
                  for page in sorted(backing_receipts, key=lambda item: item['address'])])
    if not status.get('selected'):
        raise ValueError('Task-private capture lost the selected native task')
    return data, descriptor


def capture_qemu_memory_view(session, address, length, space, task_id, view, *, pages=None):
    """Read one explicit QEMU view and return its stable identity descriptor."""
    if view not in ('ram', 'execute'):
        raise ValueError('QEMU view capture requires ram or execute')
    if type(length) is not int or not 1 <= length <= MAX_VIEW_BYTES:
        raise ValueError('Explicit QEMU memory views are limited to 1..65536 bytes')
    if space not in ('linear', 'physical'):
        raise ValueError('Explicit QEMU memory views require linear or physical space')
    if getattr(session, '_dos_task_monitor', None):
        row = _task_row(session, task_id)
        status, record = _task_status(session, row)
        data, descriptor = _task_capture(session, row, status, record,
            address, length, space, pages or [], view)
        return data, descriptor

    if task_id not in (None, 'physical-machine'):
        raise ValueError('QEMU task identity requires an initialized native task-view registry')
    active = list(getattr(session, '_layer_active', []))
    generation = getattr(session, '_layer_generation', 0)
    if active or getattr(session, '_layer_exec', None):
        native = session._layer_native_observe()
        if native.get('fault'):
            raise DebuggerError('Cannot capture a QEMU memory view while an instruction layer is faulted')
    if view == 'execute' and getattr(session, '_layer_exec', None):
        data = bytes.fromhex(session.code(address, length=length, view='execute', space=space)['hex'])
    else:
        data = session._stopped().memory(address, length,
            space='virtual' if space == 'linear' else 'physical')
    physical = _physical_pages(address, length, space, pages or [])
    descriptor = dict(format=FORMAT, scope='machine', view=view, task_identity=None,
        native_epoch=None, task_generation=0, layer_generation=generation,
        active_layers=active, active_layers_sha256=_digest(active),
        backings=[dict(address=start & ~4095, backing=start & ~4095)
                  for start, _ in physical])
    return data, descriptor


def _owner_rule(owner):
    if owner is None:
        return None, None
    if (not isinstance(owner, dict) or set(owner) != {'rule', 'previous_overlay'}
            or not isinstance(owner['rule'], str) or not owner['rule']
            or owner['previous_overlay'] is not None and not isinstance(owner['previous_overlay'], str)):
        raise ValueError('Invalid memory-rule overlay ownership')
    return owner['rule'], owner['previous_overlay']


def _layer_owner(definition):
    binding = definition.get('native_binding')
    return binding.get('memory_rule_owner') if isinstance(binding, dict) else None


def _range_physical(session, address, length, space):
    if space == 'physical':
        return address, _physical_pages(address, length, space, [])
    from .memory_search_runtime import _mapping, _paused
    observed = _paused(session)
    _, pages = _mapping(session, address, length, space, observed)
    return address, _physical_pages(address, length, space, pages)


def _addresses(spans):
    return [address for start, count in spans for address in range(start, start + count)]


def _spans(addresses):
    result = []
    previous = None
    for address in addresses:
        if previous is not None and address == previous + 1:
            result[-1][1] += 1
        else:
            result.append([address, 1])
        previous = address
    if len(result) > 17:
        raise ValueError('Memory-view edit crosses too many backing spans')
    return result


def _definition_addresses(definition):
    binding = definition.get('native_binding') or {}
    spans = binding.get('spans', [])
    return {address for start, count in spans for address in range(start, start + count)}


def _check_overlay_budget(session, active, new_addresses):
    if len(active) + 1 > 64:
        raise ValueError('Memory-view layer stack exceeds 64 layers')
    count, locations = 1, set(new_addresses)
    for identifier in active:
        definition = session.project.debug_layer_info(identifier)
        count += len(definition['patches'])
        if definition.get('native_binding') is None:
            # Imported source layers resolve their backing at activation time.
            # They still count toward the same physical transition budget.
            for patch in definition['patches']:
                locations.update(session._layer_positions(definition, patch))
        else:
            locations.update(_definition_addresses(definition))
    if count > 256 or len(locations) > MAX_VIEW_BYTES:
        raise ValueError('Memory-view overlay exceeds the native layer budget')
    if session.project.db.execute('SELECT count(*) FROM debug_layers WHERE version=?',
                                  (session.version['id'],)).fetchone()[0] >= 256:
        raise ValueError('Project version reached its immutable layer artifact budget')


def prepare_qemu_memory_write(session, context, address, expected, replacement, *, owner=None):
    """Validate a RAM-view write completely before the caller journals dispatch."""
    descriptor = context.get('qemu_memory_view') if isinstance(context, dict) else None
    if (not isinstance(descriptor, dict) or descriptor.get('format') != FORMAT
            or descriptor.get('view') != 'ram'):
        raise ValueError('Only an explicitly captured QEMU RAM view can be edited')
    if (not isinstance(expected, bytes) or not expected or not isinstance(replacement, bytes)
            or len(expected) != len(replacement)):
        raise ValueError('QEMU RAM-view edit requires equally sized expected and replacement bytes')
    rule, previous = _owner_rule(owner)
    if session.project.db.in_transaction:
        raise ValueError('QEMU memory-view edits require a project outside a caller-owned transaction')
    space = context['address_space']
    linear, spans = _range_physical(session, address, len(expected), space)
    physical_addresses = _addresses(spans)
    if len(physical_addresses) != len(expected):
        raise ValueError('Memory-view write mapping does not cover the edit')
    if len(set(physical_addresses)) != len(physical_addresses):
        raise ValueError('Memory-view edit aliases the same physical byte more than once')

    if descriptor.get('scope') == 'task-private':
        from .qemu_dos_task_views import _derive, _maps_read, _row
        identity = descriptor['task_identity']
        row = _row(session, identity['task_id'])
        status, record = _task_status(session, row)
        actual_identity = row['binding']
        active = list(row['active'])
        if (any(actual_identity.get(key) != identity.get(key)
                for key in ('monitor_uuid', 'cookie', 'incarnation', 'task_id'))
                or row['retired']
                or descriptor.get('native_epoch') != session._dos_task_monitor.get('native_epoch')
                or descriptor.get('task_generation') != row['generation']
                or descriptor.get('active_layers') != active
                or descriptor.get('active_layers_sha256') != _digest(active)):
            raise ValueError('Task-private RAM view identity or layer generation changed')
        registered = {page['address'] for page in record['pages']}
        if any((physical & ~4095) not in registered for physical in physical_addresses):
            raise ValueError('Task-private write requires registered private backing for every byte')
        expected_layers, _, execute = _derive(session, row, active)
        actual = _maps_read(session, row, physical_addresses, 'ram')
        if bytes(actual[item] for item in physical_addresses) != expected:
            raise ValueError('Task-private RAM view changed before edit preparation')
        layer_addresses = list(row['ram_applied'])
        if layer_addresses:
            applied_current = _maps_read(session, row, layer_addresses, 'ram')
            target = set(physical_addresses)
            if any(applied_current[item] != row['ram_applied'][item]
                   and item not in target for item in layer_addresses):
                raise ValueError('Unrelated private RAM layer changed before edit dispatch')
        base = bytes(expected_layers.get(item, actual[item]) for item in physical_addresses)
        definitions = {identifier: session.project.debug_layer_info(identifier) for identifier in active}
        remove = []
        for identifier, definition in definitions.items():
            layer_owner = _layer_owner(definition)
            overlap = bool(_definition_addresses(definition).intersection(physical_addresses))
            if identifier == previous:
                if not rule or layer_owner != rule:
                    raise ValueError('Previous memory-rule overlay is not active under this rule owner')
                remove.append(identifier)
            elif rule is not None and layer_owner == rule:
                raise ValueError('Memory rule has an untracked active overlay')
        if previous is not None and previous not in remove:
            raise ValueError('Previous memory-rule overlay is not active')
        _check_overlay_budget(session, [item for item in active if item not in remove],
                              physical_addresses)
        binding = dict(scope='task-private', task_identity=deepcopy(row['binding']),
            run=session.run_id, epoch=session._layer_epoch(),
            spans=_spans(physical_addresses), space='physical')
        if rule is not None:
            binding['memory_rule_owner'] = rule
        return dict(scope='task-private', row=row, binding=binding,
            active_before=active, active_after=[item for item in active if item not in remove],
            generation=row['generation'], address=address, linear=linear,
            physical_addresses=physical_addresses, expected=expected, base=base,
            replacement=replacement, execute=execute, owner=owner, task_status=status)

    if descriptor.get('scope') != 'machine':
        raise ValueError('Unsupported QEMU memory-view scope')
    from .qemu_layers import LAYER_COMMANDS
    if (not session.capabilities.get('code_layers')
            or not LAYER_COMMANDS <= getattr(session.vm, 'qmp_commands', frozenset())):
        raise ValueError('Global RAM-view edits require the native QEMU layer extension')
    session._layer_preflight()
    for physical, count in spans:
        session._layer_ram_extent(physical, count)
    active = list(getattr(session, '_layer_active', []))
    generation = getattr(session, '_layer_generation', 0)
    if (descriptor.get('layer_generation') != generation or descriptor.get('active_layers') != active
            or descriptor.get('active_layers_sha256') != _digest(active)):
        raise ValueError('Global QEMU RAM layer identity or generation changed')
    current = session._stopped().memory(address, len(expected),
        space='virtual' if space == 'linear' else 'physical')
    if current != expected:
        raise ValueError('Global QEMU RAM view changed before edit preparation')
    applied_before = getattr(session, '_layer_ram_applied', {})
    if applied_before:
        remote = session._stopped()
        target = set(physical_addresses)
        for group in groups(applied_before):
            observed = remote.memory(group[0], len(group), space='physical')
            if any(observed[offset] != applied_before[item] and item not in target
                   for offset, item in enumerate(group)):
                raise ValueError('Unrelated global RAM layer changed before edit dispatch')
    definitions = {identifier: session.project.debug_layer_info(identifier) for identifier in active}
    remove = []
    for identifier, definition in definitions.items():
        layer_owner = _layer_owner(definition)
        overlap = bool(_definition_addresses(definition).intersection(physical_addresses))
        if identifier == previous:
            if not rule or layer_owner != rule:
                raise ValueError('Previous memory-rule overlay is not active under this rule owner')
            remove.append(identifier)
        elif rule is not None and layer_owner == rule:
            raise ValueError('Memory rule has an untracked active overlay')
    if previous is not None and previous not in remove:
        raise ValueError('Previous memory-rule overlay is not active')
    _check_overlay_budget(session, [item for item in active if item not in remove],
                          physical_addresses)
    base_map = getattr(session, '_layer_ram_base', {})
    base = bytes(base_map.get(item, current[offset]) for offset, item in enumerate(physical_addresses))
    binding = dict(run=session.run_id, epoch=session._layer_epoch(), space=space, spans=spans)
    if rule is not None:
        binding['memory_rule_owner'] = rule
    return dict(scope='machine', binding=binding, active_before=active,
        active_after=[item for item in active if item not in remove],
        generation=generation, address=address, linear=linear,
        physical_addresses=physical_addresses, expected=expected, base=base,
        replacement=replacement, owner=owner)


def _new_overlay(session, prepared):
    rule, previous = _owner_rule(prepared['owner'])
    definition = dict(kind='ram',
        patches=[dict(address=hex(prepared['address']),
                      expected_hex=prepared['base'].hex(),
                      data_hex=prepared['replacement'].hex())],
        native_binding=prepared['binding'])
    name = 'memory-view-' + (rule[:12] if rule else 'edit') + '-' + uuid.uuid4().hex[:12]
    return session.project._store_debug_layer(name, session.version['id'], definition)['layer']


def _derive_global(session, active):
    expected, ram, execute = {}, {}, {}
    for identifier in active:
        definition = session.project.debug_layer_info(identifier)
        if definition['kind'] not in ('ram', 'execute'):
            raise ValueError('Unsupported QEMU memory-view layer kind')
        for patch in definition['patches']:
            addresses = session._layer_positions(definition, patch)
            before, after = bytes.fromhex(patch['expected_hex']), bytes.fromhex(patch['data_hex'])
            if len(addresses) != len(before) or len(before) != len(after):
                raise ValueError('QEMU layer definition differs from its backing extent')
            output = ram if definition['kind'] == 'ram' else execute
            for address, old, new in zip(addresses, before, after):
                if expected.setdefault(address, old) != old:
                    raise ValueError('Overlapping QEMU layers disagree about their base bytes')
                output[address] = new
    return expected, ram, execute


def _commit_task_overlay(session, prepared, overlay, active):
    from .qemu_dos_task_views import _derive, _maps_read, _observe

    row = prepared['row']
    expected, ram, execute = _derive(session, row, active)
    touched = set(expected) | set(row['ram_applied']) | set(physical for physical in prepared['physical_addresses'])
    current = _maps_read(session, row, touched, 'ram')
    base = dict(current)
    target = set(prepared['physical_addresses'])
    if bytes(current[address] for address in prepared['physical_addresses']) != prepared['expected']:
        raise ValueError('Task-private RAM expected bytes changed before native layer dispatch')
    for address, applied in row['ram_applied'].items():
        observed = current[address]
        if observed == applied:
            base[address] = row['ram_base'][address]
        elif address in target:
            # The fresh memory plan guards the changed current value. Retain the
            # immutable authored base underneath the new rule overlay.
            base[address] = expected.get(address, row['ram_base'][address])
        else:
            raise ValueError('Unrelated private RAM layer changed since its last transition')
    for address, old in expected.items():
        if base.get(address) != old and address not in target:
            raise ValueError('Unrelated private layer base bytes changed')
        if address in target:
            base[address] = old
    post_ram = base | ram
    writes = {address: post_ram[address]
              for address in set(row['ram_applied']) | set(ram)}
    ram_chunks = _chunks(current, writes)
    execute_chunks = _chunks(post_ram, execute)
    args = dict(uuid=row['binding']['monitor_uuid'], cookie=row['binding']['cookie'],
        incarnation=row['binding']['incarnation'], generation=row['generation'],
        ram=ram_chunks, execute=execute_chunks)
    try:
        native = session.vm.qmp.call('x-fdisbull-task-layer-configure', args)
    except DebuggerError as error:
        if 'PRECONDITION' not in str(error):
            session.close()
        raise
    except BaseException:
        session.close()
        raise
    generation = row['generation'] + 1
    if (not isinstance(native, dict) or native.get('generation') != generation
            or native.get('ram-bytes') != len(writes)
            or native.get('execution-bytes') != len(execute)):
        session.close()
        raise DebuggerError('Invalid native task-private RAM overlay receipt')
    row.update(active=list(active), generation=generation,
        ram_base={address: base[address] for address in ram},
        ram_applied=ram, exec_base={address: post_ram[address] for address in execute},
        exec=execute)
    result = dict(task_id=row['binding']['task_id'], active=list(active),
        generation=generation, ram_bytes=len(ram), execution_bytes=len(execute),
        native=native, guest_instructions_during_transition=0)
    try:
        session._event('dos-task-layer-transition', result)
        proof = _observe(session, row)
    except BaseException:
        session.close()
        raise
    result['proof'] = proof
    return result


def _commit_machine_overlay(session, prepared, active):
    expected, ram, execute = _derive_global(session, active)
    touched = set(expected) | set(getattr(session, '_layer_ram_applied', {})) | set(prepared['physical_addresses'])
    remote = session._stopped()
    current = {}
    for group in groups(touched):
        current.update(zip(group, remote.memory(group[0], len(group), space='physical')))
    base = dict(current)
    applied_before = getattr(session, '_layer_ram_applied', {})
    base_before = getattr(session, '_layer_ram_base', {})
    target = set(prepared['physical_addresses'])
    if bytes(current[address] for address in prepared['physical_addresses']) != prepared['expected']:
        raise ValueError('Global RAM expected bytes changed before native layer dispatch')
    for address, applied in applied_before.items():
        if current[address] == applied:
            base[address] = base_before[address]
        elif address in target:
            base[address] = expected.get(address, base_before[address])
        else:
            raise ValueError('Unrelated global RAM layer changed since its last transition')
    for address, old in expected.items():
        if base.get(address) != old and address not in target:
            raise ValueError('Unrelated global layer base bytes changed')
        if address in target:
            base[address] = old
    post_ram = base | ram
    writes = {address: post_ram[address] for address in set(applied_before) | set(ram)}
    args = dict(generation=getattr(session, '_layer_generation', 0),
        ram=_chunks(current, writes), execute=_chunks(post_ram, execute))
    try:
        native = session.vm.qmp.call('x-fdisbull-layer-configure', args)
    except DebuggerError as error:
        if 'FDISBULL_LAYER_PRECONDITION' not in str(error):
            session.close()
        raise
    except BaseException:
        session.close()
        raise
    generation = getattr(session, '_layer_generation', 0) + 1
    if (not isinstance(native, dict) or native.get('generation') != generation
            or native.get('ram-bytes') != len(writes)
            or native.get('execution-bytes') != len(execute)):
        session.close()
        raise DebuggerError('Invalid global RAM overlay receipt')
    session._layer_active = list(active)
    session._layer_generation = generation
    session._layer_ram_base = {address: base[address] for address in ram}
    session._layer_ram_applied = ram
    session._layer_exec_base = {address: post_ram[address] for address in execute}
    session._layer_exec = execute
    result = dict(active=list(active), generation=generation, ram_bytes=len(ram),
        execution_bytes=len(execute), backend=native, guest_instructions_during_transition=0)
    try:
        session._event('layer-transition', result)
        proof = session._layer_native_observe()
    except BaseException:
        session.close()
        raise
    result['proof'] = proof
    return result


def expected_memory_view_after(descriptor, prepared, overlay):
    expected = deepcopy(descriptor)
    expected['active_layers'] = list(prepared['active_after']) + [overlay]
    expected['active_layers_sha256'] = _digest(expected['active_layers'])
    if prepared['scope'] == 'task-private':
        expected['task_generation'] = prepared['generation'] + 1
    else:
        expected['layer_generation'] = prepared['generation'] + 1
    return expected


def commit_qemu_memory_write(session, prepared):
    """Create one immutable RAM overlay and atomically switch its layer view."""
    overlay = _new_overlay(session, prepared)
    active = list(prepared['active_after']) + [overlay]
    if prepared['scope'] == 'task-private':
        transition = _commit_task_overlay(session, prepared, overlay, active)
    else:
        transition = _commit_machine_overlay(session, prepared, active)
    return dict(qemu_rule_overlay=overlay,
                qemu_rule_overlay_owner=_owner_rule(prepared['owner'])[0],
                qemu_rule_overlay_replaced=_owner_rule(prepared['owner'])[1],
                qemu_layer_transition=transition)
