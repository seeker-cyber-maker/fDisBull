"""Fail-closed boundaries for selectively verified Wine loader composition."""
from copy import deepcopy
import hashlib

import pytest

from fdisbull.pe_loader_module_recovery import (
    ENVIRONMENT, VERIFIED_LOADER_ENVIRONMENT, _bind_loader_source, recover_loader_module,
)
from fdisbull.runtime_loader_analysis import _bind_loader_capsules, _require_protected_memory_join


def test_verified_profile_retains_every_assumption_not_discharged_by_the_capsules():
    assert set(VERIFIED_LOADER_ENVIRONMENT) == set(ENVIRONMENT)
    for name in ('initial_iat_binding', 'wine_api_frame', 'termination', 'segment_binding'):
        assert VERIFIED_LOADER_ENVIRONMENT[name] == ENVIRONMENT[name]
    assert VERIFIED_LOADER_ENVIRONMENT['dispatch'] != ENVIRONMENT['dispatch']
    assert VERIFIED_LOADER_ENVIRONMENT['memory_frame'] != ENVIRONMENT['memory_frame']


@pytest.mark.parametrize('name', list(ENVIRONMENT))
def test_omitting_any_retained_environment_assumption_cannot_qualify(name):
    incomplete = dict(VERIFIED_LOADER_ENVIRONMENT)
    del incomplete[name]
    result = recover_loader_module(None, None, {}, environment_contract=incomplete, loader_source=b'bytes')
    assert result['status'] == 'unknown' and result['whole_module_recovery'] is None
    assert 'Explicit loader' in result['reason']


@pytest.mark.parametrize('source', [None, 'path-to-unread-source', bytearray(b'bytes')])
def test_verified_dispatch_requires_the_actual_immutable_source_bytes(source):
    result = recover_loader_module(None, None, {}, environment_contract=VERIFIED_LOADER_ENVIRONMENT,
                                   loader_source=source)
    assert result['status'] == 'unknown' and 'original Wine loader bytes' in result['reason']


def _source_identity():
    raw = b'original frozen loader source; identity test, not a PE semantic fixture'
    digest = hashlib.sha256(raw).hexdigest()
    bound = {'report': {'loader_selection': {'source': {'source_sha256': digest}}},
             'loader_capsules': [{'capsule': {'loader_module': {'source_sha256': digest}}},
                                 {'capsule': {'loader_module': {'source_sha256': digest}}}]}
    return raw, bound


def test_a_different_loader_cannot_borrow_the_executed_source_identity():
    source, bound = _source_identity()
    assert _bind_loader_source(bound, source) == hashlib.sha256(source).hexdigest()
    # Identical hypothetical executed text does not make differing PE files
    # interchangeable: unused metadata is still part of the frozen identity.
    with pytest.raises(ValueError, match='native selected source identity'):
        _bind_loader_source(bound, source + b'changed unused metadata')
    for index in (0, 1):
        forged = deepcopy(bound)
        forged['loader_capsules'][index]['capsule']['loader_module']['source_sha256'] = '0' * 64
        with pytest.raises(ValueError, match='native selected source identity'):
            _bind_loader_source(forged, source)


@pytest.mark.parametrize('label', ['entry snapshot', 'return snapshot', 'inner callback return', 'inner next callback entry'])
def test_equal_machine_contexts_cannot_hide_a_protected_memory_change(label):
    before = {'registers': {'rip': '0x1000'}, 'memory': [{'address': '0x2000', 'hex': '01020304'}]}
    after = deepcopy(before)
    expected = {0x2000 + i: i + 1 for i in range(4)}
    selected = set(expected)
    _require_protected_memory_join(after['memory'], expected, selected, label)
    after['memory'][0]['hex'] = '01090304'
    assert before['registers'] == after['registers']
    with pytest.raises(ValueError, match='protected-memory boundary'):
        _require_protected_memory_join(after['memory'], expected, selected, label)
    with pytest.raises(ValueError, match='protected-memory boundary'):
        _require_protected_memory_join([{'address': '0x2000', 'hex': '010203'}], expected, selected, label)


@pytest.mark.parametrize('references', [None, [], [{'artifact': 'one'}], [{'artifact': 'a'}] * 3])
def test_milestones_or_one_capsule_do_not_establish_both_dispatch_intervals(references):
    with pytest.raises(ValueError, match='both attach/detach capsules'):
        _bind_loader_capsules({'loader_capsules': references}, run='owner', exe_image={}, dll_image={},
                              documents={}, receipts={}, protected={}, terminal_sequence=100)


def test_legacy_profile_is_not_implicitly_promoted_to_native_dispatch_verification():
    assert ENVIRONMENT['dispatch'] == 'observed_single_thread_tls_dllmain_process_lifetime'
    assert 'outer_scheduling' in VERIFIED_LOADER_ENVIRONMENT['dispatch']
