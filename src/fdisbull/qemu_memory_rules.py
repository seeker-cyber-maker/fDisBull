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
    if (getattr(session, '_dos_task_binding', None) or getattr(session, '_dos_task_monitor', None)
            or getattr(session, '_dos_task_views', None) or getattr(session, '_dos_scheduler', None)):
        raise ValueError('Periodic QEMU memory rules do not support task-private switching or task bindings')
    if getattr(session, '_layer_active', None) or getattr(session, '_layer_exec', None):
        raise ValueError('Periodic QEMU memory rules cannot run with active layers or a stale fetch overlay')
    if getattr(session, '_qemu_hooks', None) or getattr(session, '_qemu_hook_pending', None):
        raise ValueError('Periodic QEMU memory rules cannot run with native hooks')
    state = getattr(vm, '_physical_input', None)
    if state is not None and (not state.get('valid') or state.get('pending') or state.get('leases')
                              or (state.get('schedule') or {}).get('bound')):
        raise ValueError('Periodic QEMU memory rules require idle physical input ownership')
    sync = getattr(vm, '_clock_sync', None)
    if (sync is not None and (not isinstance(sync, dict) or sync.get('state') != 'stopped')):
        raise ValueError('Stop the active clock synchronization controller before running a memory rule')
    if getattr(vm, '_active_clock_budget', None) is not None:
        raise ValueError('Periodic QEMU memory rules require an unowned native clock budget')


def preflight(session, configuration):
    """Passively admit ownership, then qualify stopped clock and original mapping."""
    admit_native_rule_run(session)
    clock = session._clock_snapshot()
    native = clock.get('virtual_clock', {}).get('native', {})
    if native.get('budget-state') not in ('idle', 'stopped', 'cancelled'):
        raise ValueError('Periodic QEMU memory rules require a stable stopped virtual clock')
    original = configuration['origin_context']
    region = original['region']
    task = None if original['task_evidence'].startswith('physical address') else original['task_id']
    _, observed, _ = _capture(session, region['start'], region['length'], original['address_space'], task)
    if _json(observed) != _json(original):
        raise ValueError('Original memory rule task, mapping or epoch changed')
