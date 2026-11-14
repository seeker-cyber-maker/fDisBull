"""Host-only ownership and failure contracts for task-private views."""
from copy import deepcopy
from types import SimpleNamespace
import threading
import time

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_dos_tasks import FORMAT, _identifier
from fdisbull.qemu_dos_task_views import COMMANDS, QemuDOSTaskViewMixin, validate_task_views, verify_task_views


def _binding(cookie=1, nonce='22' * 16):
    result = dict(format=FORMAT, anchor_address=0x5000, monitor_uuid='11' * 16,
                  cookie=cookie, incarnation=1, process_nonce=nonce)
    result['task_id'] = _identifier(result)
    return result


class _Qmp:
    def __init__(self):
        self.calls = []
        self.responses = {}
        self.tasks = {}
        self.selected = None

    def _status(self, arguments):
        key = (arguments['uuid'], arguments['cookie'], arguments['incarnation'])
        item = self.tasks[key]
        selected = self.selected or key
        return {'model': 'qemu-pc-task-private-v1', 'api-version': 1,
            'epoch': 1, 'generation': 1, 'uuid': key[0], 'cookie': key[1],
            'incarnation': key[2], 'task-generation': item['generation'],
            'selected': selected == key, 'selected-uuid': selected[0], 'selected-cookie': selected[1],
            'selected-incarnation': selected[2], 'sequence': 2, 'pending': False,
            'tasks': deepcopy(list(self.tasks.values()))}

    def call(self, method, arguments=None, **kwargs):
        self.calls.append((method, arguments))
        if method in self.responses:
            result = self.responses[method]
            if isinstance(result, BaseException): raise result
            return deepcopy(result)
        if method == 'x-fdisbull-task-register':
            key = (arguments['uuid'], arguments['cookie'], arguments['incarnation'])
            if self.selected is None: self.selected = key
            item = self.tasks.setdefault(key, {'uuid': key[0], 'cookie': key[1],
                'incarnation': key[2], 'generation': 0, 'retired': False, 'pages': [],
                'execution-bytes': 0, 'execution-sha256': '00' * 32})
            for page in arguments['pages']:
                address = page['address'] if isinstance(page, dict) else page
                if not any(p['address'] == address for p in item['pages']):
                    item['pages'].append({'address': address, 'backing': address, 'sha256': '00' * 32})
            return self._status(arguments)
        if method == 'x-fdisbull-task-retire':
            key = (arguments['uuid'], arguments['cookie'], arguments['incarnation'])
            self.tasks[key]['retired'] = True
            return self._status(arguments)
        if method == 'x-fdisbull-task-layer-observe':
            return self._status(arguments)
        if method == 'x-fdisbull-task-layer-read':
            return {'generation': 0, 'data-hex': '00' * arguments['length'], 'active': True}
        return {}


class _Session(QemuDOSTaskViewMixin):
    def __init__(self):
        qmp = _Qmp()
        self.vm = SimpleNamespace(lock=threading.RLock(), qmp=qmp, gdb=None,
            qmp_commands=COMMANDS, operation_deadline=time.monotonic() + 30)
        self.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False),
                                       debug_layer_info=lambda identifier: deepcopy(self.definitions[identifier]))
        self.definitions = {}
        self.version = {'id': 1}
        self.run_id = 'run'
        self._dos_task_binding = _binding()
        self._dos_task_monitor = dict(anchor_address=0x5000, monitor_uuid='11' * 16,
                                      process_nonce='22' * 16, native_epoch=1)
        self._dos_task_views = {}
        self._qemu_hooks = {}
        self._layer_active = []
        self.closed = False
        self.fail_event = False

    def _layer_epoch(self): return 3
    def _stopped(self): return None
    def _layer_ram_extent(self, address, length):
        if not 0 <= address < address + length <= 0xa0000:
            raise ValueError('outside RAM')
    def _event(self, name, data):
        if self.fail_event: raise RuntimeError('event failed')
    def close(self): self.closed = True
    def delete_hook(self, hook):
        self._qemu_hooks = {key: item for key, item in self._qemu_hooks.items() if item['hook'] != hook}


def _registered():
    session = _Session()
    binding = session.dos_task_register(cookie=1, incarnation=1, pages=[0x1000])
    return session, binding


@pytest.fixture(autouse=True)
def _selected_native_task(monkeypatch):
    import fdisbull.qemu_dos_task_views as views
    def observe(session, binding=None, vm=None):
        selected = session.vm.qmp.selected
        if selected is None:
            selected = (session._dos_task_binding['monitor_uuid'],
                        session._dos_task_binding['cookie'], session._dos_task_binding['incarnation'])
        current = _binding(cookie=selected[1])
        current['monitor_uuid'] = selected[0]
        current['incarnation'] = selected[2]
        current['task_id'] = _identifier(current)
        return {'task_identity': current, 'task_id': current['task_id'],
                'scheduler_generation': 2,
                'matches_binding': binding is None or current['task_id'] == binding['task_id']}
    monkeypatch.setattr(views, 'observe_task', observe)


@pytest.mark.parametrize('failure', ['bad-receipt', 'register-failure', 'event-failure'])
def test_switching_partial_native_initialization_closes(monkeypatch, failure):
    import fdisbull.qemu_dos_task_views as views
    session = _Session()
    session._dos_task_monitor = None
    monkeypatch.setattr(views, 'require_task', lambda *args, **kwargs: None)
    session.vm.qmp.responses['x-fdisbull-task-monitor-init'] = {
        'anchor-address': 0x5000, 'doorbell-port': 0xf1db, 'doorbell-value': 0x4446, 'epoch': 1}
    if failure == 'bad-receipt':
        session.vm.qmp.responses['x-fdisbull-task-monitor-init'] = {}
    elif failure == 'register-failure':
        session.vm.qmp.responses['x-fdisbull-task-register'] = DebuggerError('transport failed')
    else:
        session.fail_event = True
    with pytest.raises((DebuggerError, RuntimeError)):
        session.dos_task_switching()
    assert session.closed


def test_private_switching_refuses_incompatible_global_hook_before_native_mutation(monkeypatch):
    import fdisbull.qemu_dos_task_views as views
    session = _Session()
    session._dos_task_monitor = None
    session._qemu_hooks = {'bp': {'actions':[{'op':'layers','layers':['global-layer']}]}}
    monkeypatch.setattr(views,'require_task',lambda *args,**kwargs: None)
    with pytest.raises(ValueError,match='Global-layer hook actions'):
        session.dos_task_switching()
    assert not session.vm.qmp.calls and not session.closed


@pytest.mark.parametrize('operation', ['register', 'retire'])
@pytest.mark.parametrize('failure', ['transport', 'proof', 'event'])
def test_registry_mutation_uncertainty_closes(operation, failure):
    session, binding = _registered()
    if operation == 'retire': binding = session.dos_task_register(cookie=2, incarnation=1)
    command = 'x-fdisbull-task-' + operation
    if failure == 'transport':
        session.vm.qmp.responses[command] = DebuggerError('transport failed')
    elif failure == 'proof':
        session.vm.qmp.responses['x-fdisbull-task-layer-observe'] = {'epoch': 99}
    else:
        session.fail_event = True
    with pytest.raises((DebuggerError, RuntimeError)):
        if operation == 'register': session.dos_task_register(cookie=2, incarnation=1)
        else: session.dos_task_retire(binding['task_id'])
    assert session.closed


def test_retirement_handles_unbound_hook_identity_without_removing_it():
    session, _ = _registered()
    binding = session.dos_task_register(cookie=2, incarnation=1)
    session._qemu_hooks = {'bp': {'hook': 'global', 'task_identity': None}}
    assert session.dos_task_retire(binding['task_id'])['removed_hooks'] == []
    assert session._qemu_hooks['bp']['hook'] == 'global' and not session.closed


@pytest.mark.parametrize('failure', ['receipt', 'event'])
def test_layer_transition_postdispatch_failure_closes(failure):
    session, binding = _registered()
    if failure == 'event':
        session.vm.qmp.responses['x-fdisbull-task-layer-configure'] = {
            'generation': 1, 'ram-bytes': 0, 'execution-bytes': 0}
        session.fail_event = True
    with pytest.raises((DebuggerError, RuntimeError)):
        session.dos_task_layers([], task=binding['task_id'])
    assert session.closed


def test_explicit_native_precondition_refusal_keeps_owner_live():
    session, _ = _registered()
    session.vm.qmp.responses['x-fdisbull-task-register'] = DebuggerError('PRECONDITION: not eligible')
    with pytest.raises(DebuggerError, match='PRECONDITION'):
        session.dos_task_register(cookie=2, incarnation=1)
    assert not session.closed


@pytest.mark.parametrize('operation', ['register', 'retire', 'layer-configure'])
def test_native_mutation_timeout_closes_owner(operation):
    session, binding = _registered()
    if operation == 'retire': binding = session.dos_task_register(cookie=2, incarnation=1)
    session.vm.qmp.responses['x-fdisbull-task-' + operation] = TimeoutError('lost response')
    with pytest.raises(TimeoutError, match='lost response'):
        if operation == 'register': session.dos_task_register(cookie=2, incarnation=1)
        elif operation == 'retire': session.dos_task_retire(binding['task_id'])
        else: session.dos_task_layers([], task=binding['task_id'])
    assert session.closed


@pytest.mark.parametrize('change', ['model', 'identity', 'generation', 'retired', 'pages', 'missing-field', 'selected-flag'])
def test_register_rejects_malformed_native_status_and_closes(change):
    session, binding = _registered()
    args = {'uuid': binding['monitor_uuid'], 'cookie': binding['cookie'], 'incarnation': binding['incarnation']}
    status = session.vm.qmp._status(args)
    if change == 'model': status['model'] = 'unrecognized'
    elif change == 'identity': status['cookie'] += 1
    elif change == 'generation': status['task-generation'] += 1
    elif change == 'retired': status['tasks'][0]['retired'] = True
    elif change == 'pages': status['tasks'][0]['pages'][0]['address'] = 0x2000
    elif change == 'selected-flag': status['selected'] = False
    else: del status['selected']
    session.vm.qmp.responses['x-fdisbull-task-layer-observe'] = status
    with pytest.raises(DebuggerError):
        session.dos_task_register(cookie=1, incarnation=1, pages=[0x1000])
    assert session.closed


def test_registration_encodes_qapi_page_objects():
    session, _ = _registered()
    arguments = next(args for command, args in session.vm.qmp.calls
                     if command == 'x-fdisbull-task-register')
    assert arguments['pages'] == [{'address': 0x1000}]


def test_native_selection_must_match_cooperating_anchor(monkeypatch):
    import fdisbull.qemu_dos_task_views as views
    session, binding = _registered()
    other = _binding(cookie=2)
    monkeypatch.setattr(views, 'observe_task', lambda *args, **kwargs: {
        'task_identity': other, 'task_id': other['task_id'], 'scheduler_generation': 2,
        'matches_binding': False})
    with pytest.raises((DebuggerError, ValueError)):
        session.dos_task_layers(task=binding['task_id'])


def test_full_private_memory_read_is_chunked_for_native_limit():
    session = _Session()
    binding = session.dos_task_register(cookie=1, incarnation=1,
                                        pages=list(range(0x1000, 0x11000, 0x1000)))
    result = session.dos_task_memory(0x1000, length=65536, task=binding['task_id'])
    calls = [args for command, args in session.vm.qmp.calls if command == 'x-fdisbull-task-layer-read']
    assert len(bytes.fromhex(result['hex'])) == 65536
    assert sum(args['length'] for args in calls) == 65536
    assert all(1 <= args['length'] <= 4096 for args in calls)


def _saved(session, binding):
    definition = dict(version=1, kind='ram', patches=[dict(expected_hex='00', data_hex='11')],
        native_binding=dict(scope='task-private', task_identity=deepcopy(binding),
                            run='run', epoch=3, spans=[[0x1000, 1]]))
    session.definitions['layer'] = definition
    row = dict(binding=deepcopy(binding), active=['layer'], generation=1, pages=[0x1000], retired=False,
        maps=dict(ram_base=[[0x1000, 0]], ram_applied=[[0x1000, 17]], exec_base=[], exec=[]),
        observed=[[0x1000, 17]], definitions={'layer': deepcopy(definition)})
    return dict(format='fdisbull-qemu-task-views-1', monitor=deepcopy(session._dos_task_monitor),
                run='run', epoch=3, views=[row])


def test_private_checkpoint_registry_accepts_owned_definition_and_mapping():
    session, binding = _registered()
    validate_task_views(session, _saved(session, binding), binding['process_nonce'])


@pytest.mark.parametrize('changes', [dict(epoch=3), dict(generation=8), dict(pending=True),
                                    dict(fault='lost view'), dict(**{'task-generation': 8})])
def test_restored_private_native_status_requires_fresh_epoch_and_matching_state(changes):
    session, binding = _registered()
    args = {'uuid': binding['monitor_uuid'], 'cookie': binding['cookie'], 'incarnation': binding['incarnation']}
    previous = session.vm.qmp._status(args)
    previous.update(epoch=3, generation=8, **{'task-generation': 7})
    previous['tasks'][0]['generation'] = 7
    saved = {'views': [{'binding': binding, 'native': previous}]}
    current = dict(previous, epoch=4, generation=9)
    session.vm.qmp.responses['x-fdisbull-task-layer-observe'] = current
    assert verify_task_views(session.vm, saved) == [current]
    current.update(changes)
    session.vm.qmp.responses['x-fdisbull-task-layer-observe'] = current
    with pytest.raises(DebuggerError, match='differs'):
        verify_task_views(session.vm, saved)


@pytest.mark.parametrize('change', ['nonce', 'monitor', 'wrong-owner', 'wrong-epoch', 'outside-ram', 'changed-definition'])
def test_private_checkpoint_rejects_changed_identity_mapping_or_definition(change):
    session, binding = _registered()
    saved = _saved(session, binding)
    row = saved['views'][0]
    if change == 'nonce': saved['monitor']['process_nonce'] = '33' * 16
    elif change == 'monitor': saved['monitor']['anchor_address'] = 0x6000
    elif change == 'wrong-owner':
        row['definitions']['layer']['native_binding']['task_identity'] = _binding(cookie=2)
        session.definitions['layer'] = deepcopy(row['definitions']['layer'])
    elif change == 'wrong-epoch':
        row['definitions']['layer']['native_binding']['epoch'] = 2
        session.definitions['layer'] = deepcopy(row['definitions']['layer'])
    elif change == 'outside-ram': row['pages'] = [0xa0000]
    else: session.definitions['layer']['patches'][0]['data_hex'] = '22'
    with pytest.raises(ValueError):
        validate_task_views(session, saved, binding['process_nonce'])
