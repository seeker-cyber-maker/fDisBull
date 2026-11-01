"""Independent edge checks for intentional partial rewind policies."""
from copy import deepcopy
import json

import pytest

from test_cpu_deltas import Session as DosSession
from test_wine_deltas import DATA, Session as WineSession


@pytest.fixture(params=['dos', 'wine'])
def recording(request, tmp_path):
    debug = DosSession() if request.param == 'dos' else WineSession(tmp_path)
    base = debug.static_base if request.param == 'dos' else DATA
    debug.cpu_delta_start([{'address': base, 'length': 16}])
    debug.cpu_delta_record(2)
    yield debug, base
    debug.project.db.close()


def test_overlapping_preservation_is_refused_without_consuming_history(recording):
    debug, base = recording
    original = deepcopy((debug.cpu, debug.ram, debug.cpu_delta_status()))
    with pytest.raises(ValueError, match='overlap'):
        debug.cpu_delta_rewind(policy={
            'preserve_memory': [{'address': base, 'length': 3},
                                {'address': base + 2, 'length': 2}],
            'allow_partial_resume': True})
    assert (debug.cpu, debug.ram, debug.cpu_delta_status()) == original
    writes = debug.mutations if hasattr(debug, 'mutations') else debug.rpc.mutations
    assert writes == []


def test_no_write_policy_receipt_failure_cannot_grant_execution(recording):
    debug, base = recording
    original = deepcopy((debug.cpu, debug.ram))
    previous = debug._event
    def fail_receipt(operation, evidence):
        if operation == 'cpu-delta-rewind':
            raise OSError('independent no-write receipt failure')
        return previous(operation, evidence)
    debug._event = fail_receipt
    with pytest.raises(OSError, match='no-write receipt'):
        debug.cpu_delta_rewind(policy={
            'preserve_registers': sorted(debug._delta_registers),
            'preserve_memory': [{'address': base, 'length': 16}],
            'allow_partial_resume': True})
    assert (debug.cpu, debug.ram) == original
    writes = debug.mutations if hasattr(debug, 'mutations') else debug.rpc.mutations
    assert writes == [] and debug.closed
    assert not debug.cpu_delta_status()['execution_allowed']


def test_new_history_default_undo_keeps_experiment_origin(recording):
    debug, base = recording
    debug.cpu_delta_rewind(policy={'name': 'intentional branch', 'allow_partial_resume': True})
    origin = deepcopy(debug.cpu_delta_status()['experiment'])
    debug.cpu_delta_start([{'address': base, 'length': 16}])
    debug.cpu_delta_record()
    debug.cpu_delta_rewind()
    status = debug.cpu_delta_status()
    assert status['experiment'] == origin and status['partial_restored']
    assert status['frozen'] and not status['execution_allowed'] and not status['resume_safe']


def test_hash_refusal_during_further_default_undo_keeps_anchor_recovery(recording):
    debug, _ = recording
    debug.cpu_delta_rewind()
    writes = debug.mutations if hasattr(debug, 'mutations') else debug.rpc.mutations
    before = deepcopy((debug.cpu, debug.ram, writes))
    artifact = debug._cpu_delta_history['entries'][0]['delta']['artifact']
    debug.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',
                             (b'corrupt delta payload', artifact))
    with pytest.raises(ValueError, match='hash'):
        debug.cpu_delta_rewind()
    assert (debug.cpu, debug.ram, writes) == before
    assert not debug.closed
    debug.cpu_delta_recover()
    assert not debug.cpu_delta_status()['frozen']


def test_preserved_wine_register_retains_64_bit_value(tmp_path):
    debug = WineSession(tmp_path)
    try:
        initial = 0x123456789abc0000
        debug.cpu['general']['rax'] = hex(initial)
        debug.cpu_delta_start([{'address': DATA, 'length': 16}])
        debug.cpu_delta_record(2)
        debug.cpu_delta_rewind(2, policy={
            'preserve_registers': ['rax'], 'allow_partial_resume': True})
        assert int(debug.cpu['general']['rax'], 16) == initial + 14
        assert debug.ram[:16] == bytes(16)
        assert not debug.cpu_delta_status()['resume_safe']
    finally:
        debug.project.db.close()


def test_code_snapshot_after_opt_in_contains_experiment_identity(tmp_path):
    debug = WineSession(tmp_path)
    try:
        debug.project.arch, debug.project.bits = 'x86', 64
        debug._layer_generation = 0
        debug.cpu_delta_start([{'address': DATA, 'length': 16}])
        debug.cpu_delta_record()
        debug.cpu_delta_rewind(policy={'name': 'declared experiment', 'allow_partial_resume': True})
        capture = debug.capture_code(DATA, length=4, view='ram')
        row = debug.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                       (capture['artifact'],)).fetchone()
        document = json.loads(row['data'])
        assert document['identity']['delta_experiment'] == debug.cpu_delta_status()['experiment']
        assert document['identity']['delta_experiment']['resume_safe'] is False
    finally:
        debug.project.db.close()
