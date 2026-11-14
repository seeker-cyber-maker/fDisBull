"""A full attach theorem must not erase the remaining environment contracts."""
from copy import deepcopy

import pytest

from fdisbull.pe_loader_module_recovery import (
    ENVIRONMENT, VERIFIED_PROCESS_ATTACH_ENVIRONMENT, recover_loader_module,
)
from fdisbull.runtime_loader_analysis import load_loader_evidence


def test_full_attach_profile_retains_terminal_api_and_segment_requirements():
    assert set(VERIFIED_PROCESS_ATTACH_ENVIRONMENT) == set(ENVIRONMENT)
    for key in ('initial_iat_binding', 'wine_api_frame', 'termination', 'segment_binding'):
        assert VERIFIED_PROCESS_ATTACH_ENVIRONMENT[key] == ENVIRONMENT[key]
    assert 'outer_scheduling_observed' in VERIFIED_PROCESS_ATTACH_ENVIRONMENT['dispatch']
    assert 'outer_owned_memory_frame_assumed' in VERIFIED_PROCESS_ATTACH_ENVIRONMENT['memory_frame']


@pytest.mark.parametrize('key', list(ENVIRONMENT))
def test_missing_full_attach_environment_requirement_cannot_qualify(key):
    profile = deepcopy(VERIFIED_PROCESS_ATTACH_ENVIRONMENT)
    del profile[key]
    result = recover_loader_module(None, None, {}, environment_contract=profile, loader_source=b'bytes')
    assert result['status'] == 'unknown' and result['whole_module_recovery'] is None
    assert 'Explicit loader' in result['reason']


def test_full_attach_does_not_accept_proof_attachments_without_source_and_native_views():
    result = recover_loader_module(None, None, {}, environment_contract=VERIFIED_PROCESS_ATTACH_ENVIRONMENT)
    assert result['status'] == 'unknown' and 'original Wine loader bytes' in result['reason']
    with pytest.raises(ValueError, match='derived caller intervals'):
        load_loader_evidence(None, None, {}, require_process_attach=True)
