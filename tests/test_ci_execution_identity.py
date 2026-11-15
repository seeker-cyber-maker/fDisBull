import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('identity', Path(__file__).parents[1] / 'scripts/ci/execution_identity.py')
identity = importlib.util.module_from_spec(spec); spec.loader.exec_module(identity)


def test_github_identity_uses_canonical_fields_without_gitlab_ids(monkeypatch):
    values = {'FDISBULL_EXECUTION_ORIGIN': 'github', 'FDISBULL_GITHUB_REPOSITORY': 'org/repo',
              'FDISBULL_GITHUB_CONTROL_REF': 'codex/control', 'FDISBULL_GITHUB_CONTROL_SHA': 'a' * 40,
              'FDISBULL_GITHUB_RUN_ID': '10', 'FDISBULL_GITHUB_RUN_ATTEMPT': '2',
              'FDISBULL_GITHUB_JOB_ID': '30', 'FDISBULL_GITHUB_RUNNER_ID': '21', 'CI_JOB_NAME': 'qualification'}
    for key, value in values.items(): monkeypatch.setenv(key, value)
    result = identity.execution_identity()
    assert result['run_id'] == '10' and result['job_id'] == '30' and result['runner_id'] == '21'
    assert 'pipeline_id' not in result
    monkeypatch.setenv('FDISBULL_GITHUB_JOB_ID', '0')
    with pytest.raises(ValueError): identity.execution_identity()
