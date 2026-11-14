"""Offline replay of immutable observed PE export-resolution ledgers."""
from copy import deepcopy
import hashlib

import pytest

from fdisbull.runtime_module_analysis import _resolution
from fdisbull.wine_import_calls import resolve_loaded_export
from test_wine_import_calls import _image, _modules


@pytest.fixture
def evidence():
    kernel, _ = _image({'SetLastError': 'NTDLL.RtlSetLastWin32Error'})
    ntdll, _ = _image({'RtlSetLastWin32Error': None})
    modules, read = _modules([(0x100000, 'kernel32.dll', kernel),
                              (0x200000, 'ntdll.dll', ntdll)])
    return modules, resolve_loaded_export(modules, 'KERNEL32.dll', 'SetLastError', read)


def test_complete_forwarded_export_ledger_replays_without_mutation(evidence):
    modules, resolution = evidence
    frozen = deepcopy(evidence)
    assert _resolution(resolution, modules, 'SetLastError') is None
    assert evidence == frozen


@pytest.mark.parametrize('change', ['missing', 'extra', 'reordered', 'wrong_address',
    'wrong_length', 'wrong_hash', 'wrong_header', 'target_label', 'forwarder_label',
    'generation_label', 'module_generation', 'module_revision', 'wrong_name'])
def test_forged_or_incomplete_export_ledger_is_rejected(evidence, change):
    modules, resolution = deepcopy(evidence)
    name = 'SetLastError'
    rows = resolution['reads']
    if change == 'missing':
        rows.pop()
    elif change == 'extra':
        rows.append(deepcopy(rows[-1]))
    elif change == 'reordered':
        rows[0], rows[1] = rows[1], rows[0]
    elif change == 'wrong_address':
        rows[0]['address'] = hex(int(rows[0]['address'], 16) + 1)
    elif change == 'wrong_length':
        rows[0]['hex'] += '00'
        rows[0]['sha256'] = hashlib.sha256(bytes.fromhex(rows[0]['hex'])).hexdigest()
    elif change == 'wrong_hash':
        rows[-1]['hex'] = 'cc' + rows[-1]['hex'][2:]
    elif change == 'wrong_header':
        rows[0]['hex'] = '0000' + rows[0]['hex'][4:]
        rows[0]['sha256'] = hashlib.sha256(bytes.fromhex(rows[0]['hex'])).hexdigest()
    elif change == 'target_label':
        resolution['target'] = hex(int(resolution['target'], 16) + 1)
    elif change == 'forwarder_label':
        resolution['chain'][0]['forwarder'] = 'NTDLL.GetLastError'
    elif change == 'generation_label':
        resolution['chain'][-1]['generation'] += 1
    elif change == 'module_generation':
        modules['modules'][-1]['generation'] += 1
    elif change == 'module_revision':
        modules['module_revision'] += 1
    else:
        name = 'GetLastError'
    with pytest.raises(ValueError):
        _resolution(resolution, modules, name)
