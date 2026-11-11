"""Admission for periodic memory rules on an owned virtual-clock QEMU VM."""
from __future__ import annotations

from .memory_search_runtime import _capture, _json
from .qemu_clock import VIRTUAL_CLOCK_COMMANDS, machine_clock_configuration


def admit_native_rule_run(session):
    """Check host-owned metadata only; perform no RPC, mutation or close."""
    project = getattr(session, 'project', None)
    if project is not None and project.db.in_transaction:
        raise ValueError('Periodic QEMU memory rules require a project outside a caller-owned transaction')
    vm = session.vm
    machine = getattr(vm, 'machine_configuration', {})
    if not isinstance(machine, dict):
        raise ValueError('Periodic QEMU memory rules require an explicit native virtual clock')
    try:
        expected = machine_clock_configuration('virtual', machine.get('cpus', 1))
    except (TypeError, ValueError):
        raise ValueError('Periodic QEMU memory rules require an explicit native virtual clock') from None
    if (machine.get('clock_profile') != expected
            or not VIRTUAL_CLOCK_COMMANDS <= getattr(vm, 'qmp_commands', frozenset())
            or vm.qmp is None):
        raise ValueError('Periodic QEMU memory rules require an explicit native virtual clock')
    state = getattr(vm, '_physical_input', None)
    if state is not None and (not state.get('valid') or state.get('pending') or state.get('leases')
                              or (state.get('schedule') or {}).get('bound')):
        raise ValueError('Periodic QEMU memory rules require idle physical input ownership')
    sync = getattr(vm, '_clock_sync', None)
    if (sync is not None and (not isinstance(sync, dict) or sync.get('state') != 'stopped')):
        raise ValueError('Stop the active clock synchronization controller before running a memory rule')
    if getattr(vm, '_active_clock_budget', None) is not None:
        raise ValueError('Periodic QEMU memory rules require an unowned native clock budget')


def admit_rule_context(session, context):
    """Layers and native tasks require an explicitly captured RAM domain."""
    view = context.get('qemu_memory_view')
    if view is not None:
        if not isinstance(view, dict) or view.get('view') != 'ram':
            raise ValueError('Memory rules require an explicit RAM view; execute views are inspection only')
        return
    if any(getattr(session, name, None) for name in (
            '_dos_task_binding', '_dos_task_monitor', '_dos_task_views', '_dos_scheduler')):
        raise ValueError('Task-private memory rules require an explicit RAM view snapshot')
    if getattr(session, '_layer_active', None) or getattr(session, '_layer_exec', None):
        raise ValueError('Memory rules with active layers require an explicit RAM view snapshot')


def preflight(session, configuration, progress=None):
    """Passively admit ownership, then qualify stopped clock and original mapping."""
    admit_native_rule_run(session)
    from .memory_rules import _current_context, _task
    original = _current_context(configuration, progress)
    admit_rule_context(session, original)
    clock = session._clock_snapshot()
    native = clock.get('virtual_clock', {}).get('native', {})
    if native.get('budget-state') not in ('idle', 'stopped', 'cancelled'):
        raise ValueError('Periodic QEMU memory rules require a stable stopped virtual clock')
    region = original['region']
    args = (session, region['start'], region['length'], original['address_space'], _task(original))
    view = original.get('qemu_memory_view', {}).get('view', 'base')
    _, observed, _ = _capture(*args, view=view) if view != 'base' else _capture(*args)
    if _json(observed) != _json(original):
        raise ValueError('Original memory rule task, mapping or epoch changed')
