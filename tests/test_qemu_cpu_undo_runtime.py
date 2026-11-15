"""Focused contracts for the QEMU selected CPU/RAM inverse provider."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from fdisbull import qemu_cpu_undo_runtime as undo


class _ProjectDB:
    in_transaction = False


class _Session:
    def __init__(self):
        self.closed = False
        self.vm = SimpleNamespace(qmp=object(), gdb=SimpleNamespace(register_description=[
            {'name': name, 'size': 8 if name.startswith('r') and name not in ('rip',) else 4}
            for name in undo.REGISTERS]))
        self.project = SimpleNamespace(db=_ProjectDB())
        self.metadata = {'source_sha256': 'a' * 64, 'version_sha256': 'b' * 64}
        self.version = {'id': 'version-1'}
        self.run_id = 'run-1'
        self._nonce = b'n' * 16
        self._runtime_epoch = 'epoch-1'
        self._process = {'state': 'active', 'allocation': {'base': 0x1000, 'size': 0x100},
            'source_mapping': {'runtime_base': 0x1100,
                'live_ranges': [{'runtime_address': 0x1100, 'project_address': 0x100, 'length': 0x100}]}}
        self.memory = bytearray(b'abcd')
        self.generation = 2
        self.active = ['authored-layer']
        self.cpu = {name: 0 for name in undo.REGISTERS}
        self.cpu.update(rip=0x100, rsp=0x8000, eflags=0x202, rax=7, rbx=0x22)
        self._history_admission = lambda: None
        self._dos_task_binding = None
        self._dos_task_monitor = None
        self._dos_scheduler = None
        self._qemu_hooks = {}
        self._qemu_hook_pending = None
        self._qemu_hook_pending_task = None
        self._layer_generation = self.generation
        self._layer_active = list(self.active)
        self._layer_ram_extent = lambda address, length: None

    def _stopped(self):
        return self

    def registers(self):
        raw = {name: hex(value) for name, value in self.cpu.items()}
        state = {'machine_vcpus': 1, 'register_context_match': True,
            'cpu_mode': 'real', 'paging': False, 'code_bits': 16,
            'control': {'CR0': '0x0', 'CR2': '0x0', 'CR3': '0x0', 'CR4': '0x0', 'EFER': '0x0'},
            'segments': {'cs': {'selector': '0x100', 'base': '0x1000', 'limit': '0xffff', 'attributes': '0x0'},
                         'ss': {'selector': '0x800', 'base': '0x8000', 'limit': '0xffff', 'attributes': '0x0'}},
            'flags': '0x202'}
        return {'registers': raw, 'address_state': state, 'cpu_mode': 'real',
                'segments': state['segments'], 'linear_pc': hex(0x1100 + self.cpu['rip'])}

    def _layer_spans(self, address, length, space, cs=None):
        assert space == 'source'
        static = int(address, 0) if isinstance(address, str) else address
        linear = 0x1100 + static - 0x100
        physical = 0x2100 + static - 0x100
        return linear, static, [(physical, length)], self.registers()['address_state']

    def close(self):
        self.closed = True

    def write_registers(self, edits):
        for name, item in edits.items():
            canonical = next(key for key, aliases in undo._ALIASES.items() if name in aliases) if name not in self.cpu else name
            assert self.cpu[canonical] == item['expected']
            self.cpu[canonical] = item['value']
        return self.registers()


def _capture(session, address, length, space, task_id, *, view):
    assert space == 'linear' and view == 'ram' and task_id is None
    offset = address - 0x1100
    descriptor = dict(format='fdisbull-qemu-memory-view-1', scope='machine', view='ram',
        task_identity=None, native_epoch=None, task_generation=0, layer_generation=session.generation,
        active_layers=list(session.active),
        active_layers_sha256=undo._sha(undo._json(session.active)),
        backings=[dict(address=0x2000, backing=0x2000)])
    context = dict(qemu_memory_view=descriptor)
    evidence = dict(pages=[dict(linear='0x1000', physical='0x2000')])
    offset = max(0, min(len(session.memory), offset))
    return bytes(session.memory[offset:offset + length]), context, evidence


@pytest.fixture
def session(monkeypatch):
    from fdisbull import memory_search_runtime
    from fdisbull import qemu_cpu_undo_runtime
    monkeypatch.setattr(qemu_cpu_undo_runtime, 'require_task', lambda owner: None)
    monkeypatch.setattr(memory_search_runtime, '_capture', _capture)
    return _Session()


def _ranges():
    return [{'address': '0x100', 'length': 4}]


def test_normalize_preserves_source_range_order_and_rejects_physical_alias(session):
    normalized = undo.normalize_ranges(session, _ranges())
    assert normalized == [dict(address='0x100', length=4, linear='0x1100',
                               spans=[dict(address=0x2100, length=4)])]
    with pytest.raises(ValueError, match='alias'):
        undo.normalize_ranges(session, [dict(address='0x100', length=4),
                                        dict(address='0x100', length=4)])


def test_observe_honors_register_subset_but_keeps_full_cpu_proof(session):
    result = undo.observe(session, _ranges(), ['rax', 'rip'])
    assert result['cpu'] == {'rax': 7, 'rip': 0x100}
    assert set(result['proof']['full_cpu']) == set(undo.REGISTERS)
    assert result['ram'] == [b'abcd']
    assert result['binding']['ranges'][0]['spans'] == [dict(address=0x2100, length=4)]


def _install_layer_helpers(monkeypatch, session):
    from fdisbull import qemu_memory_views as views
    monkeypatch.setattr(views, 'prepare_qemu_memory_write', lambda owner, context, address, expected, replacement:
        dict(scope='machine', binding=dict(scope='machine', run=owner.run_id, epoch=owner._runtime_epoch,
             spans=[[0x2100, len(expected)]]), active_before=list(owner.active), active_after=list(owner.active),
             generation=owner.generation, physical_addresses=list(range(0x2100, 0x2100 + len(expected))),
             expected=expected, base=expected, replacement=replacement, address=address,
             execute={} ))
    monkeypatch.setattr(views, '_check_overlay_budget', lambda owner, active, addresses: None)

    def commit(owner, prepared):
        overlay = 'undo-overlay'
        offset = 0
        offset = 0
        for row in prepared['ranges']:
            start = int(row['linear'], 16) - 0x1100
            data = prepared['target_ram'][offset]
            owner.memory[start:start + row['length']] = data
            offset += 1
        owner.active = list(prepared['active_after']) + [overlay]
        owner.generation += 1
        owner._layer_active = list(owner.active)
        owner._layer_generation = owner.generation
        return dict(qemu_rule_overlay=overlay,
            qemu_layer_transition=dict(active=list(owner.active), generation=owner.generation))
    monkeypatch.setattr(views, 'commit_qemu_memory_write', commit)


def test_prepare_and_apply_commit_one_ram_overlay_and_only_selected_registers(session, monkeypatch):
    from fdisbull import qemu_memory_views as views
    _install_layer_helpers(monkeypatch, session)
    monkeypatch.setattr(views, 'expected_memory_view_after',
        lambda descriptor, prepared, overlay: dict(descriptor,
            active_layers=list(prepared['active_after']) + [overlay],
            active_layers_sha256=undo._sha(undo._json(list(prepared['active_after']) + [overlay])),
            layer_generation=prepared['generation'] + 1))
    observed = undo.observe(session, _ranges(), ['rax', 'rip'])
    plan = undo.prepare(session, _ranges(), observed, {'rax': 9}, [b'WXYZ'])
    result = undo.apply(session, plan)
    assert session.cpu['rax'] == 9 and session.cpu['rbx'] == 0x22
    assert result['observation']['cpu'] == {'rax': 9, 'rip': 0x100}
    assert result['observation']['ram'] == [b'WXYZ']
    assert result['ram_transition']['qemu_rule_overlay'] == 'undo-overlay'
    assert session.generation == 3 and session.active[-1] == 'undo-overlay'


def test_prepare_rejects_non_arithmetic_flags_and_owned_frame_rsp_change(session, monkeypatch):
    observed = undo.observe(session, _ranges(), ['eflags', 'rsp'])
    with pytest.raises(ValueError, match='arithmetic flags'):
        undo._validate_target(session, observed, {'eflags': observed['cpu']['eflags'] & ~0x200}, [b'abcd'])
    observed['proof']['native_context'] = {'interrupt-depth': 1}
    with pytest.raises(ValueError, match='interrupt frames'):
        undo._validate_target(session, observed, {'rsp': observed['cpu']['rsp'] - 2}, [b'abcd'])


def test_unknown_partial_dispatch_closes_owner(session, monkeypatch):
    _install_layer_helpers(monkeypatch, session)
    from fdisbull import qemu_memory_views as views
    observed = undo.observe(session, _ranges(), ['rax'])
    plan = undo.prepare(session, _ranges(), observed, {'rax': 11}, [b'WXYZ'])
    def uncertain(*args, **kwargs):
        session.memory[:] = b'WXYZ'
        raise TimeoutError('lost native response')
    monkeypatch.setattr(views, 'commit_qemu_memory_write', uncertain)
    with pytest.raises(TimeoutError):
        undo.apply(session, plan)
    assert session.closed


def test_private_overlay_allows_only_one_task_manager_generation_step():
    binding = {'scheduler_frontier': {'generation': 10, 'runqueue-generation': 4,
        'preemption': {'ack-count': 3}, 'selected-cookie': 9}}
    controller = {'scheduler': deepcopy(binding['scheduler_frontier']),
        'frame_keys': {'generation': 2, 'held': ['shift']}, 'hooks': {'hook': 4}}
    transition = {'qemu_rule_overlay': 'new-overlay',
        'qemu_layer_transition': {'generation': 7}}
    expected_binding, expected_controller = undo._expected_task_layer_generation(
        binding, controller, 'task-private', transition)
    assert expected_binding['scheduler_frontier']['generation'] == 11
    assert expected_controller['scheduler']['generation'] == 11
    assert expected_controller['scheduler']['runqueue-generation'] == 4
    assert expected_controller['scheduler']['preemption'] == {'ack-count': 3}
    assert expected_controller['frame_keys'] == controller['frame_keys']
    assert expected_controller['hooks'] == controller['hooks']
    with pytest.raises(undo.DebuggerError, match='cannot advance safely'):
        undo._expected_task_layer_generation(
            {'scheduler_frontier': {'generation': (1 << 64) - 1}}, {},
            'task-private', transition)
