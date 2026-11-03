"""Policy routes validate literals before earlier steps and resolve bound values."""
from copy import deepcopy

import pytest

from fdisbull.cli import METHODS
from fdisbull.debug_script import execute_script, validate_script
from test_cpu_deltas import RANGES, Session


@pytest.mark.parametrize('policy', [
    [],
    {'name': ''},
    {'allow_partial_resume': 1},
    {'preserve_registers': 'eax'},
    {'preserve_memory': [{'address': '0x10002', 'length': 0}]},
    {'unknown': True},
])
def test_bad_literal_policy_rejects_before_earlier_trace_or_artifacts(policy):
    debug = Session()
    initial = deepcopy((debug.cpu, debug.ram))
    with pytest.raises(ValueError):
        execute_script(debug, {'format': 'fdisbull-script-1', 'steps': [
            {'op': 'trace', 'count': 2, 'fast_forward': True},
            {'op': 'delta-rewind', 'policy': policy},
        ]})
    assert (debug.cpu, debug.ram) == initial
    assert debug.calls == [] and debug.trace_calls == 0
    assert debug.project.db.execute('SELECT COUNT(*) FROM debug_artifacts').fetchone()[0] == 0


def test_backend_register_policy_rejects_before_earlier_trace_or_artifacts():
    debug = Session()
    with pytest.raises(ValueError):
        execute_script(debug, {'format': 'fdisbull-script-1', 'steps': [
            {'op': 'trace', 'count': 2, 'fast_forward': True},
            {'op': 'delta-rewind', 'policy': {'preserve_registers': ['rax']}},
        ]})
    assert debug.calls == [] and debug.trace_calls == 0
    assert debug.project.db.execute('SELECT COUNT(*) FROM debug_artifacts').fetchone()[0] == 0


def test_policy_reference_does_not_hide_malformed_literal_sibling():
    with pytest.raises(ValueError):
        validate_script({'format': 'fdisbull-script-1', 'steps': [
            {'op': 'delta-rewind', 'policy': {
                'preserve_memory': '$rng_ranges', 'allow_partial_resume': 'yes'}},
        ]})


@pytest.mark.parametrize('policy', [
    {'name': 'keep-rng', 'preserve_memory': [{'address': '0x10002', 'length': 1}],
     'allow_partial_resume': True},
    '$chosen',
    {'name': '$label', 'preserve_memory': '$rng_ranges', 'allow_partial_resume': '$resume'},
])
def test_script_forwards_literal_or_bound_rewind_policy_to_live_session(policy):
    debug = Session()
    debug.cpu_delta_start(RANGES)
    debug.cpu_delta_record()
    result = execute_script(debug, {'format': 'fdisbull-script-1', 'steps': [
        {'op': 'delta-rewind', 'policy': policy},
    ]}, bindings={
        'chosen': {'name': 'keep-rng',
                   'preserve_memory': [{'address': '0x10002', 'length': 1}],
                   'allow_partial_resume': True},
        'label': 'keep-rng', 'rng_ranges': [{'address': '0x10002', 'length': 1}],
        'resume': True,
    })
    assert result['ok'], result
    assert debug.ram[0] == 0 and debug.ram[2] == 3
    assert debug.cpu['instruction_pointer'] == '0x0'
    assert not debug.cpu_delta_status()['frozen']


def test_delta_rewind_method_discovery_mentions_policy_and_partial_continuation():
    description = METHODS['debug-delta-rewind']
    assert 'policy' in description and 'experimental' in description
