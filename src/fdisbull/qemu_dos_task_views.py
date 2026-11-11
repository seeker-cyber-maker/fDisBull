"""Cooperating native DOS task views and private physical-backing layers.

The guest monitor owns CPU scheduling. A native doorbell commits the selected
task's CPU RAM/fetch view; devices and raw debugger reads retain base RAM.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import re

from .code_layers import groups
from .debug_state import byte_string
from .dosbox_rpc import DebuggerError
from .memory_search_runtime import _locked
from .qemu_dos_tasks import FORMAT, _identifier, observe_task, require_task, task_key
from .qemu_layers import MAX_BYTES, _chunks

COMMANDS = frozenset(('x-fdisbull-task-monitor-init', 'x-fdisbull-task-register',
    'x-fdisbull-task-layer-configure', 'x-fdisbull-task-layer-read',
    'x-fdisbull-task-layer-observe', 'x-fdisbull-task-retire'))
VIEW_FORMAT = 'fdisbull-qemu-task-views-1'


def _arguments(binding):
    task_key(binding)
    return dict(uuid=binding['monitor_uuid'], cookie=binding['cookie'],
                incarnation=binding['incarnation'])


def _row(session, task=None):
    if task is None:
        task = (getattr(session, '_dos_task_binding', None) or {}).get('task_id')
    if not isinstance(task, str) or task not in getattr(session, '_dos_task_views', {}):
        raise ValueError('Unknown registered native DOS task view')
    return session._dos_task_views[task]


def _preflight(session):
    if session.project.db.in_transaction:
        raise ValueError('Task views require a project outside a transaction')
    session._stopped()
    if not COMMANDS <= session.vm.qmp_commands:
        raise ValueError('Task-private layers require the native task-view extension')
    if not getattr(session, '_dos_task_monitor', None):
        raise ValueError('Enable native task switching before registering private views')


def _observe(session, row):
    raw = session.vm.qmp.call('x-fdisbull-task-layer-observe', _arguments(row['binding']))
    try:
        _validate_status(session, row, raw)
    except BaseException:
        session.close()
        raise
    actual = observe_task(session, binding=row['binding'])
    current = actual['task_identity']
    if (raw['selected-uuid'] != current['monitor_uuid'] or raw['selected-cookie'] != current['cookie']
            or raw['selected-incarnation'] != current['incarnation']
            or raw['sequence'] != actual['scheduler_generation']):
        raise ValueError('Monitor anchor has not committed its native task view')
    return raw


def _validate_status(session, row, raw):
    def uint(value, minimum=0): return type(value) is int and minimum <= value < 1 << 64
    def digest(value): return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value)
    wanted = _arguments(row['binding'])
    if (not isinstance(raw,dict) or raw.get('model') != 'qemu-pc-task-private-v1'
            or type(raw.get('api-version')) is not int or raw['api-version'] != 1
            or not uint(raw.get('epoch'),1) or not uint(raw.get('generation'),1)
            or any(raw.get(key) != value for key,value in wanted.items())
            or not uint(raw.get('task-generation')) or raw['task-generation'] != row['generation']
            or type(raw.get('selected')) is not bool or type(raw.get('pending')) is not bool
            or any(key not in raw for key in ('selected-uuid','selected-cookie','selected-incarnation'))
            or not isinstance(raw.get('selected-uuid'),str)
            or not uint(raw.get('selected-cookie')) or not uint(raw.get('selected-incarnation'))
            or not uint(raw.get('sequence')) or raw['sequence'] & 1
            or not isinstance(raw.get('tasks'),list) or len(raw['tasks']) > 16):
        raise DebuggerError('Invalid native task-view observation')
    if raw['selected'] != ((raw['selected-uuid'],raw['selected-cookie'],raw['selected-incarnation']) ==
                            (wanted['uuid'],wanted['cookie'],wanted['incarnation'])):
        raise DebuggerError('Native selected-task flag differs from the selected lifetime')
    if raw.get('fault') or raw['pending']:
        raise DebuggerError('Native task view is faulted or has an uncommitted switch')
    expected_epoch = session._dos_task_monitor.get('native_epoch')
    if expected_epoch is not None and raw['epoch'] != expected_epoch:
        raise DebuggerError('Native task-view owner epoch changed')
    previous = getattr(session.vm,'_dos_task_view_generation',0)
    if raw['generation'] < previous:
        raise DebuggerError('Native task-view generation regressed')
    seen, requested = set(), None
    for info in raw['tasks']:
        if (not isinstance(info,dict) or not isinstance(info.get('uuid'),str)
                or not re.fullmatch('[0-9a-f]{32}',info['uuid'])
                or not uint(info.get('cookie'),1) or not uint(info.get('incarnation'),1)
                or not uint(info.get('generation')) or type(info.get('retired')) is not bool
                or not isinstance(info.get('pages'),list) or len(info['pages']) > 16
                or not uint(info.get('execution-bytes')) or not digest(info.get('execution-sha256'))):
            raise DebuggerError('Invalid native task registry receipt')
        key = (info['uuid'],info['cookie'],info['incarnation'])
        if key in seen: raise DebuggerError('Duplicate native task registry key')
        seen.add(key)
        pages = set()
        for page in info['pages']:
            if (not isinstance(page,dict) or not uint(page.get('address')) or page['address'] & 4095
                    or not uint(page.get('backing')) or page['backing'] & 4095
                    or page['backing'] in pages or not digest(page.get('sha256'))):
                raise DebuggerError('Invalid native task-private page receipt')
            pages.add(page['backing'])
        if key == (wanted['uuid'],wanted['cookie'],wanted['incarnation']): requested = info
    if (requested is None or requested['generation'] != row['generation']
            or requested['retired'] != row['retired']
            or requested['execution-bytes'] != len(row['exec'])
            or not set(row['pages']) <= {page['address'] for page in requested['pages']}):
        raise DebuggerError('Native task registry differs from its host owner')
    expected_keys = {(r['binding']['monitor_uuid'],r['binding']['cookie'],r['binding']['incarnation'])
                     for r in session._dos_task_views.values()}
    if seen != expected_keys:
        raise DebuggerError('Native task census differs from the host registry')
    if (raw['selected-uuid'],raw['selected-cookie'],raw['selected-incarnation']) not in seen:
        raise DebuggerError('Native selected task is not registered')
    session.vm._dos_task_view_generation = raw['generation']


def _read(session, row, address, length, view='ram'):
    parts, receipts = [], []
    for offset in range(0,length,4096):
        count = min(4096,length-offset)
        raw = session.vm.qmp.call('x-fdisbull-task-layer-read', dict(_arguments(row['binding']),
            address=address+offset, length=count, view=view))
        try:
            data = bytes.fromhex(raw['data-hex'])
        except (KeyError, TypeError, ValueError):
            raise DebuggerError('Invalid native task-private memory receipt') from None
        if (len(data) != count or type(raw.get('generation')) is not int
                or raw['generation'] != row['generation'] or type(raw.get('active')) is not bool):
            raise DebuggerError('Native task-private bytes or generation differ from their owner')
        parts.append(data); receipts.append(raw)
    return b''.join(parts), receipts[0] if len(receipts)==1 else dict(chunks=receipts)


def _maps_read(session, row, addresses, view='ram'):
    result = {}
    for span in groups(addresses):
        data, _ = _read(session, row, span[0], len(span), view)
        result.update(zip(span, data))
    return result


def private_reader(vm, binding, generation):
    """Read CPU-visible backing without changing the selected native task."""
    def read(address,length):
        parts = []
        for offset in range(0,length,4096):
            count = min(4096,length-offset)
            raw = vm.qmp.call('x-fdisbull-task-layer-read',dict(_arguments(binding),
                address=address+offset,length=count,view='ram'))
            if not isinstance(raw,dict) or raw.get('generation') != generation:
                raise DebuggerError('Private ownership reader generation changed')
            try: data = bytes.fromhex(raw['data-hex'])
            except (KeyError,TypeError,ValueError):
                raise DebuggerError('Invalid private ownership byte receipt') from None
            if len(data) != count: raise DebuggerError('Incomplete private ownership read')
            parts.append(data)
        return b''.join(parts)
    return read


def _positions(session, row, definition, patch, *, origin=None):
    binding = definition.get('native_binding')
    if (not isinstance(binding, dict) or binding.get('scope') != 'task-private'
            or task_key(binding.get('task_identity')) != task_key(row['binding'])
            or definition['version'] != session.version['id']):
        raise ValueError('Layer does not belong to the registered private task view')
    run, epoch = (session.run_id, session._layer_epoch()) if origin is None else origin
    if binding.get('run') != run or binding.get('epoch') != epoch:
        raise ValueError('Private layer belongs to a different run or capture epoch')
    spans = binding.get('spans')
    if not isinstance(spans, list) or len(spans) > 17:
        raise ValueError('Invalid task-private layer spans')
    addresses = []
    for start, length in spans:
        if type(start) is not int or type(length) is not int or not 1 <= length <= 4096:
            raise ValueError('Invalid task-private layer backing')
        session._layer_ram_extent(start, length)
        addresses.extend(range(start, start + length))
    if len(addresses) != len(bytes.fromhex(patch['expected_hex'])) or len(addresses) > MAX_BYTES:
        raise ValueError('Task-private layer extents differ from their bytes')
    return addresses


def _derive(session, row, active, *, origin=None):
    expected, ram, execute = {}, {}, {}
    definitions = [session.project.debug_layer_info(i) for i in active]
    if sum(len(d['patches']) for d in definitions) > 256:
        raise ValueError('Private layer stack exceeds 256 patches')
    for definition in definitions:
        if definition.get('kind') not in ('ram', 'execute'):
            raise ValueError('Unsupported task-private layer kind')
        for patch in definition['patches']:
            addresses = _positions(session, row, definition, patch, origin=origin)
            before, after = bytes.fromhex(patch['expected_hex']), bytes.fromhex(patch['data_hex'])
            if len(before) != len(after):
                raise ValueError('Private layer patch changes length')
            output = ram if definition['kind'] == 'ram' else execute
            for address, old, new in zip(addresses, before, after):
                if expected.setdefault(address, old) != old:
                    raise ValueError('Private layer base definitions conflict')
                output[address] = new
            if len(expected) > MAX_BYTES:
                raise ValueError('Private layer stack exceeds 64 KiB')
    return expected, ram, execute


def selected_view(session):
    """Resolve the observed selected task, including a foreign default binding."""
    current = observe_task(session)['task_identity']
    row = _row(session, current['task_id'])
    if task_key(current) != task_key(row['binding']) or row['retired']:
        raise ValueError('Selected native task does not have a live registered view')
    _observe(session, row)
    return row


def before_task_execution(session):
    # A debugger may stop while the monitor is publishing its next anchor.
    # Raw continuation can finish that transaction; source attribution and
    # checkpoints separately require anchor/native selection agreement.
    row = _row(session)
    from .qemu_dos_scheduler import before_scheduler_execution
    before_scheduler_execution(session)
    raw = session.vm.qmp.call('x-fdisbull-task-layer-observe',_arguments(row['binding']))
    try:
        _validate_status(session,row,raw)
    except BaseException:
        session.close()
        raise


def _stable_native(raw):
    # These two counters deliberately advance on incoming VMState. Task
    # configuration generations, bytes, mappings and the committed key do not.
    return {key: value for key, value in raw.items() if key not in ('epoch', 'generation')}


def capture_task_views(session):
    if not getattr(session, '_dos_task_monitor', None):
        return None
    from .qemu_checkpoint_controls import _pack
    _preflight(session)
    views = []
    for task, row in sorted(session._dos_task_views.items()):
        native = _observe(session, row)
        ids = set(row['active'])
        for hook in getattr(session, '_qemu_hooks', {}).values():
            if hook.get('task_id') == task:
                for action in hook['actions']:
                    if action.get('op') == 'task-layers': ids.update(action['layers'])
        if len(ids) > 256:
            raise ValueError('Private checkpoint definition budget exceeded')
        definitions = {identifier: session.project.debug_layer_info(identifier) for identifier in sorted(ids)}
        for definition in definitions.values():
            for patch in definition['patches']: _positions(session, row, definition, patch)
        expected, ram, execute = _derive(session, row, row['active'])
        if (ram != row['ram_applied'] or execute != row['exec']
                or row['ram_base'] != {a:expected[a] for a in ram}
                or row['exec_base'] != {a:ram.get(a,expected[a]) for a in execute}):
            raise ValueError('Private checkpoint layer maps differ from their definitions')
        observed = _maps_read(session, row, ram.keys() | execute.keys())
        if any(observed[a] != byte for a, byte in row['exec_base'].items()):
            raise ValueError('Private execution backing changed before checkpoint')
        if _maps_read(session, row, execute, 'execute') != execute:
            raise ValueError('Native private fetch view differs from its stack')
        views.append(dict(binding=deepcopy(row['binding']), active=list(row['active']),
            generation=row['generation'], pages=list(row['pages']), retired=row['retired'],
            maps={key:_pack(row[key]) for key in ('ram_base','ram_applied','exec_base','exec')},
            observed=_pack(observed), definitions=definitions, native=native))
    return dict(format=VIEW_FORMAT, monitor=deepcopy(session._dos_task_monitor),
        run=session.run_id, epoch=session._layer_epoch(), views=views)


def validate_task_views(session, saved, origin_nonce):
    if saved is None:
        return
    from .qemu_checkpoint_controls import _unpack
    if (not isinstance(saved, dict) or saved.get('format') != VIEW_FORMAT
            or not isinstance(saved.get('views'), list) or not 1 <= len(saved['views']) <= 16
            or not COMMANDS <= session.vm.qmp_commands):
        raise ValueError('Invalid or unsupported task-private checkpoint')
    monitor = saved.get('monitor')
    if not isinstance(monitor, dict) or monitor.get('process_nonce') != origin_nonce:
        raise ValueError('Private checkpoint monitor differs from the DOS helper lifetime')
    seen = set()
    for row in saved['views']:
        key = task_key(row['binding'])
        identifier = row['binding']['task_id']
        if (identifier in seen or key[0] != monitor.get('anchor_address')
                or key[1] != monitor.get('monitor_uuid') or key[4] != monitor.get('process_nonce')
                or type(row.get('generation')) is not int or row['generation'] < 0
                or type(row.get('retired')) is not bool
                or not isinstance(row.get('pages'), list) or len(row['pages']) > 16
                or not isinstance(row.get('active'), list) or len(row['active']) > 64
                or len(row['active']) != len(set(row['active']))
                or not isinstance(row.get('definitions'), dict) or len(row['definitions']) > 256):
            raise ValueError('Private checkpoint task registry is inconsistent')
        seen.add(identifier)
        for page in row['pages']:
            if type(page) is not int or page & 4095:
                raise ValueError('Invalid private checkpoint page')
            session._layer_ram_extent(page, 4096)
        for name in ('ram_base','ram_applied','exec_base','exec'):
            _unpack(row['maps'][name])
        observed = _unpack(row['observed'])
        if any(identifier not in row['definitions'] for identifier in row['active']):
            raise ValueError('Private checkpoint misses an active layer definition')
        for identifier, definition in row['definitions'].items():
            if session.project.debug_layer_info(identifier) != definition:
                raise ValueError('Private checkpoint layer definition changed')
            for patch in definition['patches']:
                _positions(session, row, definition, patch, origin=(saved['run'],saved['epoch']))
        expected, ram, execute = _derive(session, row, row['active'], origin=(saved['run'],saved['epoch']))
        maps = {name:_unpack(row['maps'][name]) for name in ('ram_base','ram_applied','exec_base','exec')}
        if (ram != maps['ram_applied'] or execute != maps['exec']
                or maps['ram_base'] != {a:expected[a] for a in ram}
                or maps['exec_base'] != {a:ram.get(a,expected[a]) for a in execute}
                or observed.keys() != ram.keys() | execute.keys()
                or any(observed[a] != byte for a,byte in maps['exec_base'].items())):
            raise ValueError('Invalid private checkpoint control maps')


def prime_task_views(vm, saved):
    if saved is not None:
        if not COMMANDS <= vm.qmp_commands:
            raise ValueError('Fresh QEMU lacks task-private checkpoint support')
        vm.qmp.call('x-fdisbull-task-monitor-init',
            {'anchor-address': saved['monitor']['anchor_address'], 'prepare-only': True})


def verify_task_views(vm, saved):
    if saved is None:
        return None
    proofs = []
    for row in saved['views']:
        raw = vm.qmp.call('x-fdisbull-task-layer-observe', _arguments(row['binding']))
        expected = row['native']
        if (not isinstance(raw, dict) or raw.get('fault') or raw.get('pending')
                or raw.get('epoch',0) <= expected.get('epoch',0)
                or raw.get('generation',0) <= expected.get('generation',0)
                or _stable_native(raw) != _stable_native(expected)):
            raise DebuggerError('Restored native task-private state differs from checkpoint')
        proofs.append(raw)
    return proofs


def restore_task_views(session, saved, proofs):
    session._dos_task_monitor = None
    session._dos_task_views = {}
    if saved is None:
        return {}
    from .qemu_checkpoint_controls import _unpack
    session._dos_task_monitor = deepcopy(saved['monitor'])
    session._dos_task_monitor['native_epoch'] = proofs[0]['epoch']
    layer_ids = {}
    for item in saved['views']:
        row = {key:deepcopy(item[key]) for key in ('binding','active','generation','pages','retired')}
        for name in ('ram_base','ram_applied','exec_base','exec'):
            row[name] = _unpack(item['maps'][name])
        for identifier, definition in item['definitions'].items():
            binding = dict(deepcopy(definition['native_binding']),
                           run=session.run_id, epoch=session._layer_epoch())
            clone = dict(kind=definition['kind'], patches=deepcopy(definition['patches']), native_binding=binding)
            layer_ids[identifier] = session.project._store_debug_layer(
                definition['name'], session.version['id'], clone)['layer']
        row['active'] = [layer_ids[i] for i in row['active']]
        session._dos_task_views[row['binding']['task_id']] = row
        if _maps_read(session,row,_unpack(item['observed'])) != _unpack(item['observed']):
            raise DebuggerError('Restored private task RAM differs from captured controls')
    return layer_ids


class QemuDOSTaskViewMixin:
    @_locked
    def dos_task_switching(self):
        if self.project.db.in_transaction:
            raise ValueError('Task switching requires a project outside a transaction')
        self._stopped()
        if not COMMANDS <= self.vm.qmp_commands:
            raise ValueError('Native task-view switching is unavailable')
        binding = getattr(self, '_dos_task_binding', None)
        if binding is None:
            raise ValueError('Bind the current cooperating DOS monitor task first')
        require_task(self)
        if getattr(self, '_layer_active', []):
            raise ValueError('Clear global layers before enabling task-private views')
        if any(action.get('op') == 'layers' and action.get('layers')
               for hook in getattr(self,'_qemu_hooks',{}).values() for action in hook['actions']):
            raise ValueError('Global-layer hook actions must be replaced before enabling task-private views')
        if getattr(self, '_dos_task_monitor', None) is None:
            try:
                raw = self.vm.qmp.call('x-fdisbull-task-monitor-init',
                    {'anchor-address': binding['anchor_address']})
                if (not isinstance(raw, dict) or raw.get('anchor-address') != binding['anchor_address']
                        or raw.get('doorbell-port') != 0xf1db or raw.get('doorbell-value') != 0x4446
                        or type(raw.get('epoch')) is not int or raw['epoch'] <= 0):
                    raise DebuggerError('Invalid native task monitor initialization receipt')
                self._dos_task_monitor = dict(anchor_address=binding['anchor_address'],
                    monitor_uuid=binding['monitor_uuid'], process_nonce=binding['process_nonce'],
                    native_epoch=raw['epoch'])
                self._dos_task_views = {}
                self.dos_task_register(cookie=binding['cookie'], incarnation=binding['incarnation'])
                self._event('dos-task-switching', dict(monitor=raw, binding=deepcopy(binding)))
            except BaseException:
                self.close()
                raise
        else:
            raw = _observe(self, _row(self))
        return dict(enabled=True, monitor=raw, task=deepcopy(binding))

    @_locked
    def dos_task_register(self, *, cookie, incarnation, pages=None):
        _preflight(self)
        if any(type(value) is not int or not 0 < value < 1 << 64 for value in (cookie, incarnation)):
            raise ValueError('Task cookie and incarnation must be nonzero uint64 values')
        if pages is None:
            pages = []
        if not isinstance(pages, list) or len(pages) > 16:
            raise ValueError('A task registration accepts at most 16 RAM pages')
        for page in pages:
            if type(page) is not int or page & 4095:
                raise ValueError('Task-private pages require aligned physical RAM addresses')
            self._layer_ram_extent(page, 4096)
        monitor = self._dos_task_monitor
        binding = dict(format=FORMAT, anchor_address=monitor['anchor_address'],
            monitor_uuid=monitor['monitor_uuid'], process_nonce=monitor['process_nonce'],
            cookie=cookie, incarnation=incarnation)
        binding['task_id'] = _identifier(binding)
        old = self._dos_task_views.get(binding['task_id'])
        if old is not None and old.get('retired'):
            raise ValueError('A retired native task lifetime cannot be registered again')
        try:
            raw = self.vm.qmp.call('x-fdisbull-task-register',
                dict(_arguments(binding), pages=[{'address':page} for page in pages]))
        except DebuggerError as error:
            if 'PRECONDITION' not in str(error): self.close()
            raise
        except BaseException:
            self.close()
            raise
        try:
            if old is None:
                self._dos_task_views[binding['task_id']] = dict(binding=binding, active=[], generation=0,
                    ram_base={}, ram_applied={}, exec_base={}, exec={}, pages=[], retired=False)
            row = self._dos_task_views[binding['task_id']]
            row['pages'] = sorted(set(row['pages']) | set(pages))
            _validate_status(self,row,raw)
            proof = _observe(self, row)
            self._event('dos-task-register', dict(binding=binding, pages=pages, native=raw, proof=proof,
                scope='caller-declared cooperating task lifetime; no dormant DOS allocation inference'))
        except BaseException:
            self.close()
            raise
        return deepcopy(binding)

    @_locked
    def dos_task_memory(self, address, *, length=32, task=None, view='ram'):
        _preflight(self)
        row = _row(self, task)
        address = int(address, 0) if isinstance(address, str) else address
        if type(address) is not int or type(length) is not int or not 1 <= length <= MAX_BYTES:
            raise ValueError('Private memory requires an address and length 1..65536')
        if view not in ('ram', 'execute', 'base'):
            raise ValueError('Task memory view must be ram, execute or base')
        self._layer_ram_extent(address, length)
        data, raw = _read(self, row, address, length, view)
        return dict(task_id=row['binding']['task_id'], address=hex(address), length=length,
            view=view, hex=data.hex(), sha256=hashlib.sha256(data).hexdigest(), native=raw)

    @_locked
    def dos_task_layer_patch(self, name, address, *, expected_hex, data_hex,
                             kind='ram', task=None, activate=True):
        _preflight(self)
        row = _row(self, task)
        if row['retired']:
            raise ValueError('Retired native tasks cannot acquire layers')
        if type(activate) is not bool or kind not in ('ram', 'execute'):
            raise ValueError('Private layer requires RAM/execute kind and boolean activation')
        before, after = byte_string(expected_hex), byte_string(data_hex)
        if not before or len(before) != len(after) or len(before) > MAX_BYTES:
            raise ValueError('Private layer byte extents differ or exceed 64 KiB')
        address = int(address, 0) if isinstance(address, str) else address
        if type(address) is not int:
            raise ValueError('Private layer requires a physical address')
        self._layer_ram_extent(address, len(before))
        spans = []
        offset = 0
        while offset < len(before):
            count = min(4096 - ((address + offset) & 4095), len(before) - offset)
            spans.append([address + offset, count]); offset += count
        binding = dict(scope='task-private', task_identity=deepcopy(row['binding']),
            run=self.run_id, epoch=self._layer_epoch(), spans=spans, space='physical')
        patch = dict(address=hex(address), expected_hex=before.hex(), data_hex=after.hex())
        result = self.project._store_debug_layer(name, self.version['id'],
            dict(kind=kind, patches=[patch], native_binding=binding))
        if activate:
            result['activation'] = self.dos_task_layers(row['active'] + [result['layer']],
                                                       task=row['binding']['task_id'])
        return result

    @_locked
    def dos_task_layers(self, active=None, *, task=None, conflict='stop'):
        _preflight(self)
        row = _row(self, task)
        if conflict not in ('stop', 'keep_changed') or conflict != 'stop' and active != []:
            raise ValueError('keep_changed is only valid when clearing private layers')
        native = _observe(self, row)
        if active is None:
            return dict(task_id=row['binding']['task_id'], active=list(row['active']),
                generation=row['generation'], native=native,
                layers=[self.project.debug_layer_info(i) for i in row['active']])
        if row['retired']:
            raise ValueError('Retired native tasks cannot change layers')
        if (not isinstance(active, list) or len(active) > 64 or any(not isinstance(i, str) for i in active)
                or len(active) != len(set(active))):
            raise ValueError('Private stack requires at most 64 unique layer IDs')
        expected, ram, execute = _derive(self, row, active)
        touched = expected.keys() | row['ram_applied'].keys()
        if len(touched) > MAX_BYTES:
            raise ValueError('Private layer transition exceeds 64 KiB')
        current = _maps_read(self, row, touched)
        base, preserved = dict(current), []
        for address, applied in row['ram_applied'].items():
            if current[address] == applied:
                base[address] = row['ram_base'][address]
            elif conflict == 'keep_changed':
                preserved.append(hex(address))
            else:
                raise ValueError('Private RAM layer conflicts with changed memory at ' + hex(address))
        for address, old in expected.items():
            if base[address] != old:
                raise ValueError('Private layer expected bytes differ at ' + hex(address))
        post_ram = base | ram
        writes = {a: post_ram[a] for a in row['ram_applied'].keys() | ram.keys()}
        args = dict(_arguments(row['binding']), generation=row['generation'],
                    ram=_chunks(current, writes), execute=_chunks(post_ram, execute))
        try:
            raw = self.vm.qmp.call('x-fdisbull-task-layer-configure', args)
        except DebuggerError as error:
            if 'PRECONDITION' not in str(error):
                self.close()
            raise
        except BaseException:
            self.close()
            raise
        try:
            generation = row['generation'] + 1
            if (not isinstance(raw, dict) or raw.get('generation') != generation
                    or raw.get('ram-bytes') != len(writes) or raw.get('execution-bytes') != len(execute)):
                raise DebuggerError('Invalid native task-private layer transition receipt')
            result = dict(task_id=row['binding']['task_id'], active=list(active), generation=generation,
                ram_bytes=len(ram), execution_bytes=len(execute), native=raw,
                preserved_changed_bytes=preserved, guest_instructions_during_transition=0)
            self._event('dos-task-layer-transition', result)
        except BaseException:
            self.close()
            raise
        row.update(active=list(active), generation=generation,
            ram_base={a:base[a] for a in ram}, ram_applied=ram,
            exec_base={a:post_ram[a] for a in execute}, exec=execute)
        return result

    @_locked
    def dos_task_retire(self, task):
        _preflight(self)
        row = _row(self, task)
        if _observe(self,row)['selected']:
            raise ValueError('Switch away from a selected task before retiring its lifetime')
        try:
            raw = self.vm.qmp.call('x-fdisbull-task-retire', _arguments(row['binding']))
        except DebuggerError as error:
            if 'PRECONDITION' not in str(error): self.close()
            raise
        except BaseException:
            self.close()
            raise
        try:
            row['retired'] = True
            _validate_status(self,row,raw)
            proof = _observe(self, row)
            hooks = [x['hook'] for x in getattr(self, '_qemu_hooks', {}).values()
                     if (x.get('task_identity') or {}).get('task_id') == task]
            for hook in hooks:
                self.delete_hook(hook)
            self._event('dos-task-retire', dict(task_id=task, native=raw, proof=proof, removed_hooks=hooks))
        except BaseException:
            self.close()
            raise
        return dict(task_id=task, retired=True, removed_hooks=hooks, native=raw)
