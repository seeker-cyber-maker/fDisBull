"""Inspectable migration coverage; selection never implies backend parity."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
import json


@lru_cache(maxsize=1)
def _inventory():
    value = json.loads(files('fdisbull').joinpath('data/dos-migration.json').read_text())
    if value.get('format') != 'fdisbull-dosbox-qemu-migration-inventory-1':
        raise ValueError('Unknown DOS migration inventory')
    return value


def migration_status(*, details=False, surface=None, slice=None):
    """Report source coverage and remaining gates without launching any backend.

    A slice's test list names required witnesses. Neither their presence nor a
    binary detected on the host turns an unqualified operation into a pass.
    """
    if type(details) is not bool:
        raise ValueError('details must be boolean')
    if surface is not None and (not isinstance(surface, str) or not surface):
        raise ValueError('surface must be an exact migration method or extra-surface ID')
    if slice is not None and (not isinstance(slice, str) or not slice):
        raise ValueError('slice must be a migration slice ID')
    manifest = deepcopy(_inventory())
    slices = {item['id']: item for item in manifest['slices']}
    if slice is not None and slice not in slices:
        raise ValueError('Unknown DOS migration slice: ' + slice)
    groups = {key: manifest[key] for key in ('rpc_methods', 'public_methods', 'extra_surfaces')}
    rows = [row for group in groups.values() for row in group]
    pending = [row for row in rows if row.get('qualification') != 'qualified']
    campaigns = [item for item in manifest['required_campaigns'] if item['qualification'] != 'qualified']
    # This is an observable gate, not a mutation that changes the user's default.
    result = dict(format=manifest['format'], inventory_base=manifest['inventory_base'],
                  status='in_progress' if pending or campaigns else 'qualified',
                  default_backend=manifest['default_backend'], native_backend=manifest['native_backend'],
                  retained_fallback_backends=manifest['retained_fallback_backends'],
                  automatic_runtime_fallback=False, runtime_validation='not_run',
                  policy=manifest['policy'], qualification_notice=manifest['qualification_notice'],
                  inventory_counts={key: len(value) for key, value in groups.items()},
                  default_switch_gate=dict(eligible=not pending and not campaigns,
                      unqualified_surfaces=len(pending), unqualified_campaigns=[item['id'] for item in campaigns],
                      action='review required; this command never changes backend selection'),
                  dosbox_removal_permitted=False)
    result['slices'] = []
    for identifier, item in slices.items():
        if slice is not None and identifier != slice:
            continue
        selected = [row for row in rows if row['slice'] == identifier]
        entry = {key: item[key] for key in ('id', 'order', 'title', 'status', 'depends_on', 'gate')}
        entry['surfaces'] = len(selected)
        entry['native_status'] = dict(Counter(row.get('current_status', row.get('status')) for row in selected))
        if details:
            entry.update(witness_tests=item['witness_tests'], scope_limits=item['scope_limits'])
        result['slices'].append(entry)
    if details or surface is not None or slice is not None:
        found = False
        for key, values in groups.items():
            selected = [row for row in values if (surface is None or row.get('method', row.get('id')) == surface)
                        and (slice is None or row['slice'] == slice)]
            result[key] = selected
            found |= bool(selected)
        if surface is not None and not found:
            raise ValueError('Unknown DOS migration surface for the selected slice: ' + surface)
    return result


def unavailable_operation(method):
    """Explain a missing native route without starting another emulator."""
    for row in _inventory()['public_methods']:
        if row['method'] == method:
            return (f'{method} is unavailable on qemu-dos; migration slice={row["slice"]}. '
                    'DOSBox remains explicitly selectable for its supported project inputs. '
                    'No fallback was launched; inspect dos-migration for the capability gap.')
    return f'{method} is unavailable on qemu-dos; no fallback was launched'
