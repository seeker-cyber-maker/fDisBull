from types import SimpleNamespace

import pytest

from fdisbull import qemu_dos_task_views
from fdisbull import qemu_memory_views as views


def test_imported_source_layers_count_toward_physical_overlay_budget():
    session = SimpleNamespace(
        project=SimpleNamespace(debug_layer_info=lambda identifier: {'patches': [{}]}),
        _layer_positions=lambda definition, patch: range(views.MAX_VIEW_BYTES))
    with pytest.raises(ValueError, match='native layer budget'):
        views._check_overlay_budget(session, ['imported-source-layer'], [views.MAX_VIEW_BYTES])


def test_physical_spans_preserve_nonmonotonic_linear_page_mapping():
    pages = [
        {'linear': '0x1000', 'physical': '0x9000'},
        {'linear': '0x2000', 'physical': '0x3000'},
    ]
    assert views._physical_pages(0x1ff0, 0x30, 'linear', pages) == [
        (0x9ff0, 0x10), (0x3000, 0x20),
    ]
    assert views._spans([0x9ff0 + i for i in range(0x10)] + [0x3000 + i for i in range(0x20)]) == [
        [0x9ff0, 0x10], [0x3000, 0x20],
    ]


def test_private_capture_binds_selected_task_and_stable_backing(monkeypatch):
    binding = dict(monitor_uuid='a' * 32, cookie=3, incarnation=4, task_id='dos-task-a')
    row = dict(binding=binding, active=['authored-layer'], generation=7, pages=[0x5000],
               retired=False)
    native_page = dict(address=0x5000, backing=0x9000, sha256='1' * 64)
    monkeypatch.setattr(qemu_dos_task_views, 'selected_view', lambda session: row)
    monkeypatch.setattr(qemu_dos_task_views, '_observe', lambda session, selected: {
        'selected': True, 'generation': 123, 'sequence': 18,
        'tasks': [dict(uuid='a' * 32, cookie=3, incarnation=4, retired=False,
                       pages=[native_page])],
    })
    monkeypatch.setattr(qemu_dos_task_views, '_read', lambda session, selected, address, length, view: (
        b'\x11' * length, {'generation': 7, 'active': True}))
    session = SimpleNamespace(
        _dos_task_monitor={'native_epoch': 2},
        _dos_task_views={'dos-task-a': row},
    )
    data, descriptor = views.capture_qemu_memory_view(
        session, 0x5000, 4, 'physical', None, 'ram')
    assert data == b'\x11' * 4
    assert descriptor == {
        'format': views.FORMAT,
        'scope': 'task-private',
        'view': 'ram',
        'task_identity': binding,
        'native_epoch': 2,
        'task_generation': 7,
        'active_layers': ['authored-layer'],
        'active_layers_sha256': views._digest(['authored-layer']),
        'backings': [{'address': 0x5000, 'backing': 0x9000}],
    }
    assert 'sequence' not in descriptor
    assert 'generation' not in descriptor
    assert 'sha256' not in descriptor['backings'][0]


def test_private_capture_refuses_unregistered_mapping(monkeypatch):
    binding = dict(monitor_uuid='b' * 32, cookie=5, incarnation=6, task_id='dos-task-b')
    row = dict(binding=binding, active=[], generation=1, pages=[0x5000], retired=False)
    monkeypatch.setattr(qemu_dos_task_views, 'selected_view', lambda session: row)
    monkeypatch.setattr(qemu_dos_task_views, '_observe', lambda session, selected: {
        'selected': True, 'tasks': [dict(uuid='b' * 32, cookie=5, incarnation=6, retired=False,
                                         pages=[dict(address=0x5000, backing=0x9000, sha256='2' * 64)])],
    })
    session = SimpleNamespace(_dos_task_monitor={'native_epoch': 1})
    with pytest.raises(ValueError, match='every mapped page'):
        views.capture_qemu_memory_view(session, 0x6000, 1, 'physical', None, 'ram')


def test_private_capture_rejects_inactive_read_receipt(monkeypatch):
    binding = dict(monitor_uuid='c' * 32, cookie=7, incarnation=8, task_id='dos-task-c')
    row = dict(binding=binding, active=[], generation=1, pages=[0x7000], retired=False)
    monkeypatch.setattr(qemu_dos_task_views, 'selected_view', lambda session: row)
    monkeypatch.setattr(qemu_dos_task_views, '_observe', lambda session, selected: {
        'selected': True, 'tasks': [dict(uuid='c' * 32, cookie=7, incarnation=8, retired=False,
                                         pages=[dict(address=0x7000, backing=0xb000, sha256='3' * 64)])],
    })
    monkeypatch.setattr(qemu_dos_task_views, '_read', lambda *args: (b'\x00', {'generation': 1, 'active': False}))
    session = SimpleNamespace(_dos_task_monitor={'native_epoch': 1})
    with pytest.raises(ValueError, match='does not belong to the selected task'):
        views.capture_qemu_memory_view(session, 0x7000, 1, 'physical', None, 'ram')


def _task_write_context(row, *, view='ram'):
    return {
        'address_space': 'physical',
        'qemu_memory_view': {
            'format': views.FORMAT, 'scope': 'task-private', 'view': view,
            'task_identity': {
                'monitor_uuid': row['binding']['monitor_uuid'],
                'cookie': row['binding']['cookie'],
                'incarnation': row['binding']['incarnation'],
                'task_id': row['binding']['task_id'],
            },
            'native_epoch': 2,
            'task_generation': row['generation'],
            'active_layers': list(row['active']),
            'active_layers_sha256': views._digest(row['active']),
            'backings': [{'address': 0x5000, 'backing': 0x9000}],
        },
    }


def test_task_commit_refuses_target_cas_race_before_qmp(monkeypatch):
    from fdisbull import qemu_dos_task_views

    row = dict(binding=dict(monitor_uuid='d' * 32, cookie=1, incarnation=1, task_id='task-d'),
               active=[], generation=3, ram_applied={}, ram_base={}, exec={}, exec_base={})
    native_calls = []
    monkeypatch.setattr(qemu_dos_task_views, '_derive', lambda *args: ({}, {}, {}))
    monkeypatch.setattr(qemu_dos_task_views, '_maps_read', lambda session, selected, addresses, view:
                        {address: 0x22 for address in addresses})
    session = SimpleNamespace(vm=SimpleNamespace(qmp=SimpleNamespace(call=lambda *args: native_calls.append(args))))
    prepared = dict(row=row, physical_addresses=[0x5000], expected=b'\x11',
                    active_before=[], active_after=[], replacement=b'\x33')
    with pytest.raises(ValueError, match='expected bytes changed'):
        views._commit_task_overlay(session, prepared, 'layer-new', ['layer-new'])
    assert native_calls == []


def test_global_commit_refuses_target_cas_race_before_qmp(monkeypatch):
    class Remote:
        def memory(self, address, length, *, space):
            return b'\x22' * length

    native_calls = []
    session = SimpleNamespace(
        vm=SimpleNamespace(qmp=SimpleNamespace(call=lambda *args: native_calls.append(args))),
        _stopped=lambda: Remote(), _layer_ram_applied={}, _layer_ram_base={},
        _layer_generation=4, _layer_active=[],
    )
    monkeypatch.setattr(views, '_derive_global', lambda *args: ({}, {}, {}))
    prepared = dict(physical_addresses=[0x5000], expected=b'\x11')
    with pytest.raises(ValueError, match='expected bytes changed'):
        views._commit_machine_overlay(session, prepared, ['layer-new'])
    assert native_calls == []


def test_unrelated_dirty_private_layer_refuses_during_preparation(monkeypatch):
    from fdisbull import qemu_dos_task_views

    binding = dict(monitor_uuid='e' * 32, cookie=2, incarnation=3, task_id='task-e')
    row = dict(binding=binding, active=[], generation=5, pages=[0x5000], retired=False,
               ram_applied={0x6000: 0x20}, ram_base={0x6000: 0x10})
    context = _task_write_context(row)
    session = SimpleNamespace(
        project=SimpleNamespace(db=SimpleNamespace(in_transaction=False)),
        _dos_task_monitor={'native_epoch': 2}, run_id='run-e', _layer_epoch=lambda: 'epoch-e',
    )
    monkeypatch.setattr(views, '_range_physical', lambda *args: (0x5000, [(0x5000, 1)]))
    monkeypatch.setattr(views, '_task_status', lambda *args: ({'selected': True}, {
        'pages': [{'address': 0x5000, 'backing': 0x9000}],
    }))
    monkeypatch.setattr(qemu_dos_task_views, '_row', lambda *args: row)
    monkeypatch.setattr(qemu_dos_task_views, '_derive', lambda *args: ({}, {}, {}))

    def read(_session, _row, addresses, _view):
        return {address: (0x11 if address == 0x5000 else 0x99) for address in addresses}

    monkeypatch.setattr(qemu_dos_task_views, '_maps_read', read)
    with pytest.raises(ValueError, match='Unrelated private RAM layer changed'):
        views.prepare_qemu_memory_write(session, context, 0x5000, b'\x11', b'\x33')


def test_execute_view_is_rejected_before_edit_preparation():
    row = dict(binding=dict(monitor_uuid='f' * 32, cookie=1, incarnation=1, task_id='task-f'),
               active=[], generation=1)
    session = SimpleNamespace(project=SimpleNamespace(db=SimpleNamespace(in_transaction=False)))
    with pytest.raises(ValueError, match='Only an explicitly captured QEMU RAM view'):
        views.prepare_qemu_memory_write(session, _task_write_context(row, view='execute'),
                                        0x5000, b'\x11', b'\x22')


def test_global_prepare_refuses_missing_layer_capability_before_journal():
    from fdisbull.qemu_layers import LAYER_COMMANDS

    descriptor = {
        'format': views.FORMAT, 'scope': 'machine', 'view': 'ram',
        'task_identity': None, 'native_epoch': None, 'task_generation': 0,
        'layer_generation': 0, 'active_layers': [],
        'active_layers_sha256': views._digest([]), 'backings': [],
    }
    session = SimpleNamespace(
        project=SimpleNamespace(db=SimpleNamespace(in_transaction=False)),
        capabilities={'code_layers': False},
        vm=SimpleNamespace(qmp_commands=LAYER_COMMANDS),
    )
    with pytest.raises(ValueError, match='native QEMU layer extension'):
        views.prepare_qemu_memory_write(session,
            {'address_space': 'physical', 'qemu_memory_view': descriptor},
            0x5000, b'\x11', b'\x22')


def test_global_prepare_refuses_nonram_span_before_journal():
    from fdisbull.qemu_layers import LAYER_COMMANDS

    descriptor = {
        'format': views.FORMAT, 'scope': 'machine', 'view': 'ram',
        'task_identity': None, 'native_epoch': None, 'task_generation': 0,
        'layer_generation': 0, 'active_layers': [],
        'active_layers_sha256': views._digest([]), 'backings': [],
    }
    def reject_extent(address, length):
        raise ValueError('Layer backing must be conventional or extended PC RAM')
    session = SimpleNamespace(
        project=SimpleNamespace(db=SimpleNamespace(in_transaction=False)),
        capabilities={'code_layers': True},
        vm=SimpleNamespace(qmp_commands=LAYER_COMMANDS),
        _layer_preflight=lambda: None,
        _layer_ram_extent=reject_extent,
    )
    with pytest.raises(ValueError, match='conventional or extended PC RAM'):
        views.prepare_qemu_memory_write(session,
            {'address_space': 'physical', 'qemu_memory_view': descriptor},
            0xa0000, b'\x11', b'\x22')


def test_overlay_stack_budget_refuses_before_layer_creation():
    session = SimpleNamespace(
        project=SimpleNamespace(db=SimpleNamespace(execute=lambda *args: SimpleNamespace(fetchone=lambda: (0,)))),
        version={'id': 1},
    )
    with pytest.raises(ValueError, match='64 layers'):
        views._check_overlay_budget(session, [f'layer-{index}' for index in range(64)], [0x5000])
