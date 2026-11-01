"""Agent-declared mixed-state rewind, with continuation kept explicit."""
from copy import deepcopy

import pytest

from test_cpu_deltas import Session as DosSession
from test_wine_deltas import DATA, Session as WineSession


@pytest.fixture(params=['dos', 'wine'])
def target(request, tmp_path):
    debug = DosSession() if request.param == 'dos' else WineSession(tmp_path)
    base = debug.static_base if request.param == 'dos' else DATA
    reg = 'eax' if request.param == 'dos' else 'rax'
    debug.cpu_delta_start([{'address': base, 'length': 16}])
    debug.cpu_delta_record(2)
    yield debug, base, reg
    debug.project.db.close()


def test_preserve_current_rng_bytes_and_register_with_explicit_continuation(target):
    debug, base, reg = target
    current = deepcopy((debug.cpu, debug.ram))
    result = debug.cpu_delta_rewind(2, policy={
        'name': 'keep-rng', 'preserve_memory': [{'address': base + 2, 'length': 1}],
        'preserve_registers': [reg], 'allow_partial_resume': True})
    assert debug.ram[0] == 0 and debug.ram[2] == current[1][2]
    assert debug.cpu['general'][reg] == current[0]['general'][reg]
    assert not result['resume_safe'] and result['execution_allowed']
    status = debug.cpu_delta_status()
    assert not status['valid'] and not status['frozen'] and status['partial_restored']
    assert status['experiment']['policy']['name'] == 'keep-rng'
    debug.call('step' if reg == 'rax' else 'execution.continue')
    with pytest.raises(ValueError):
        debug.cpu_delta_record()
    debug.cpu_delta_recover()
    assert debug.ram == bytearray(64)
    assert debug.cpu_delta_status()['experiment'] is None
    assert debug.cpu_delta_status()['resume_safe']


def test_preserving_without_resume_keeps_guard_and_retains_recovery(target):
    debug, base, _ = target
    debug.cpu_delta_rewind(policy={'preserve_memory': [{'address': base + 2, 'length': 1}]})
    status = debug.cpu_delta_status()
    assert not status['valid'] and status['frozen'] and not status['execution_allowed']
    with pytest.raises(ValueError, match='frozen'):
        debug.call('step')
    debug.cpu_delta_recover()
    assert debug.cpu_delta_status()['resume_safe']


@pytest.mark.parametrize('policy', [
    {'allow_partial_resume': 'yes'}, {'preserve_registers': ['thread']},
    {'preserve_registers': ['eax', 'eax']},
    {'preserve_memory': [{'address': '$outside', 'length': 1}]},
    {'preserve_memory': [{'address': 0, 'length': 1}]},
])
def test_bad_policy_is_a_clean_refusal_before_any_write(target, policy):
    debug, _, _ = target
    before = deepcopy((debug.cpu, debug.ram))
    with pytest.raises(ValueError):
        debug.cpu_delta_rewind(policy=policy)
    assert debug.mutations == [] if hasattr(debug, 'mutations') else debug.rpc.mutations == []
    assert (debug.cpu, debug.ram) == before
    assert debug.cpu_delta_status()['valid']


def test_preserved_bytes_still_require_the_full_expected_after_guard(target):
    debug, base, _ = target
    debug.ram[2] = 99
    with pytest.raises(ValueError):
        debug.cpu_delta_rewind(policy={'preserve_memory': [{'address': base + 2, 'length': 1}],
                                      'allow_partial_resume': True})
    assert debug.mutations == [] if hasattr(debug, 'mutations') else debug.rpc.mutations == []
    assert not debug.cpu_delta_status()['execution_allowed'] or not debug.cpu_delta_status()['partial_restored']


def test_failed_durable_policy_receipt_never_grants_continuation(target):
    debug, _, _ = target
    previous = debug._event
    def fail_receipt(operation, evidence):
        if operation == 'cpu-delta-rewind':
            raise OSError('deliberate receipt failure')
        return previous(operation, evidence)
    debug._event = fail_receipt
    with pytest.raises(OSError, match='receipt'):
        debug.cpu_delta_rewind(policy={'allow_partial_resume': True})
    assert debug.closed
    assert not debug.cpu_delta_status()['execution_allowed']


def test_new_recording_retains_experiment_provenance(target):
    debug, base, _ = target
    debug.cpu_delta_rewind(policy={'allow_partial_resume': True})
    experiment = deepcopy(debug.cpu_delta_status()['experiment'])
    debug.cpu_delta_start([{'address': base, 'length': 16}])
    assert debug.cpu_delta_status()['experiment'] == experiment
    assert not debug.cpu_delta_status()['resume_safe']
    debug.cpu_delta_record()
