import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('production_intake', ROOT / 'scripts/ci/production_intake.py')
intake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(intake)

SHA = 'a' * 40
REPO = 'seeker-cyber-maker/fDisBull'
ACTIVATED = 1_790_000_000


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))


def gitlab_export(root, *, pipeline='123', job='456', status='failed', finished='2027-01-15T00:00:00Z'):
    target = root / pipeline / job
    write_json(target / 'job.json', {
        'schema': intake.GITLAB_SCHEMA, 'source_commit': SHA, 'pipeline_id': pipeline,
        'job_id': job, 'job_name': 'native-test', 'job_status': status,
        'finished_at': finished, 'export_success': True, 'files': 2,
    })
    write_json(target / 'source-postcheck.json', {
        'source_commit': SHA, 'expected_source_commit': SHA,
        'tracked_worktree_dirty': False, 'export_success': True,
    })
    write_json(target / 'inventory.json', [
        {'path': 'artifacts/receipt.json', 'size': 10, 'sha256': 'b' * 64},
    ])
    return target


def github_export(root, *, run='77', attempt='2', job='888', repository=REPO,
                  status='failure', finished='2027-01-15T00:00:00Z'):
    target = root / 'github' / run / attempt / 'qualification' / job
    write_json(target / 'job.json', {
        'schema': intake.GITHUB_SCHEMA, 'repository': repository, 'run_id': run,
        'run_attempt': attempt, 'job_id': job, 'source_sha': SHA,
        'job_name': 'ovh-bootstrap', 'job_status': status, 'finished_at': finished,
        'control_sha': 'c' * 40, 'ref': 'main', 'runner_id': 42,
        'export_success': True, 'qualification_exit_code': 1,
    })
    write_json(target / 'source-postcheck.json', {
        'source_commit': SHA, 'expected_source_commit': SHA,
        'tracked_worktree_dirty': False, 'export_success': True,
    })
    write_json(target / 'inventory.json', [])
    return target


def test_gitlab_candidate_is_explicitly_unverified_and_uses_configured_project(tmp_path):
    gitlab_export(tmp_path)
    unknown = intake.export_candidates(tmp_path, ACTIVATED)
    assert unknown['candidates'] == []
    assert unknown['diagnostics'][0]['reason'] == 'gitlab_project_namespace_required'

    result = intake.export_candidates(tmp_path, ACTIVATED, gitlab_project_id='88349936')
    candidate = result['candidates'][0]
    assert candidate['provider'] == 'gitlab'
    assert candidate['project_or_repository'] == '88349936'
    assert candidate['run_id'] == '123' and candidate['job_id'] == '456'
    assert candidate['attempt'] is None
    assert candidate['reported_status'] == 'failed'
    assert candidate['verification'] == 'unverified_hint'
    assert candidate['source_postcheck']['tracked_worktree_dirty'] is False
    assert candidate['inventory']['items'] == 1


def test_github_namespace_attempt_and_stable_event_key(tmp_path):
    github_export(tmp_path)
    result = intake.export_candidates(tmp_path, ACTIVATED, github_repository=REPO)
    candidate = result['candidates'][0]
    assert candidate['provider'] == 'github'
    assert candidate['project_or_repository'] == REPO
    assert candidate['run_id'] == '77' and candidate['attempt'] == '2' and candidate['job_id'] == '888'
    assert candidate['reported_status'] == 'failed'
    again = intake.export_candidates(tmp_path, ACTIVATED, github_repository=REPO)['candidates'][0]
    assert candidate['event_key'] == again['event_key']
    assert intake.export_candidates(tmp_path, ACTIVATED, github_repository='other/repo')['candidates'] == []


def test_activation_gate_success_and_nonterminal_are_not_failure_candidates(tmp_path):
    gitlab_export(tmp_path, pipeline='100', job='1', status='failed', finished='2026-01-15T00:00:00Z')
    gitlab_export(tmp_path, pipeline='101', job='2', status='success')
    gitlab_export(tmp_path, pipeline='102', job='3', status='running')
    result = intake.export_candidates(tmp_path, ACTIVATED, gitlab_project_id=88349936)
    assert result['candidates'] == []


@pytest.mark.parametrize('status,expected', [('canceled', 'canceled'), ('mystery-terminal', 'unknown_terminal')])
def test_canceled_and_unrecognized_terminal_statuses_are_hints(tmp_path, status, expected):
    gitlab_export(tmp_path, status=status)
    result = intake.export_candidates(tmp_path, ACTIVATED, gitlab_project_id='88349936')
    assert result['candidates'][0]['reported_status'] == expected


@pytest.mark.parametrize('field,value', [
    ('source_commit', 'not-a-sha'), ('job_id', 'wrong'), ('pipeline_id', 'wrong'),
    ('finished_at', 'no-time'), ('export_success', 'yes'),
])
def test_malformed_metadata_is_diagnostic_unknown_not_candidate(tmp_path, field, value):
    target = gitlab_export(tmp_path)
    path = target / 'job.json'
    metadata = json.loads(path.read_text())
    metadata[field] = value
    write_json(path, metadata)
    result = intake.export_candidates(tmp_path, ACTIVATED, gitlab_project_id='88349936')
    assert result['candidates'] == []
    assert result['diagnostics'] and result['diagnostics'][0]['state'] == 'unknown'


def test_symlinked_export_is_not_followed(tmp_path):
    target = gitlab_export(tmp_path / 'real')
    (tmp_path / '777').mkdir()
    (tmp_path / '777' / '888').symlink_to(target, target_is_directory=True)
    result = intake.export_candidates(tmp_path, ACTIVATED, gitlab_project_id='88349936')
    assert all(c['run_id'] != '777' for c in result['candidates'])


def test_limit_validation_and_candidate_limit(tmp_path):
    for n in range(1, 4):
        gitlab_export(tmp_path, pipeline=str(100 + n), job=str(200 + n))
    with pytest.raises(ValueError, match='1 and 32'):
        intake.export_candidates(tmp_path, ACTIVATED, limit=33)
    result = intake.export_candidates(tmp_path, ACTIVATED, 2, gitlab_project_id='88349936')
    assert len(result['candidates']) == 2 and result['truncated'] is True


def test_inbox_duplicate_is_idempotent_and_conflicting_payload_fails(tmp_path):
    gitlab_export(tmp_path / 'exports')
    candidate = intake.export_candidates(tmp_path / 'exports', ACTIVATED,
                                         gitlab_project_id='88349936')['candidates'][0]
    with intake.FailureInbox(tmp_path / 'inbox.sqlite') as inbox:
        first = inbox.enqueue(candidate, now=ACTIVATED)
        second = inbox.enqueue(candidate, now=ACTIVATED + 1)
        assert first['state'] == 'pending' and first['duplicate'] is False
        assert second['state'] == 'pending' and second['duplicate'] is True
        changed = dict(candidate, job_name='changed')
        with pytest.raises(ValueError, match='conflicts'):
            inbox.enqueue(changed, now=ACTIVATED + 2)


def test_inbox_capacity_fails_closed_without_eviction(tmp_path):
    gitlab_export(tmp_path / 'exports', pipeline='123', job='456')
    gitlab_export(tmp_path / 'exports', pipeline='124', job='457')
    candidates = intake.export_candidates(tmp_path / 'exports', ACTIVATED,
                                          gitlab_project_id='88349936')['candidates']
    with intake.FailureInbox(tmp_path / 'inbox.sqlite', max_events=1) as inbox:
        inbox.enqueue(candidates[0], now=ACTIVATED)
        with pytest.raises(OverflowError, match='capacity full'):
            inbox.enqueue(candidates[1], now=ACTIVATED + 1)
        assert inbox.get(candidates[0]['event_key'])['state'] == 'pending'


def test_claim_survives_reopen_and_expiry_requires_reconciliation(tmp_path):
    gitlab_export(tmp_path / 'exports')
    candidate = intake.export_candidates(tmp_path / 'exports', ACTIVATED,
                                         gitlab_project_id='88349936')['candidates'][0]
    db = tmp_path / 'inbox.sqlite'
    inbox = intake.FailureInbox(db)
    inbox.enqueue(candidate, now=100)
    claim = inbox.claim('controller-A', now=200, lease_seconds=10)
    assert claim['state'] == 'claimed'
    inbox.close()

    with intake.FailureInbox(db) as reopened:
        expired = reopened.claim('controller-B', now=211)
        assert expired['state'] == 'needs_reconciliation'
        assert expired['previous_owner'] == 'controller-A'
        assert reopened.get(candidate['event_key'])['state'] == 'needs_reconciliation'
        repeated = reopened.claim('controller-B', now=212)
        assert repeated['state'] == 'needs_reconciliation'
        assert repeated['event_key'] == candidate['event_key']
        with pytest.raises(ValueError, match='canonical no-action'):
            reopened.resolve_reconciliation(candidate['event_key'], 'controller-A', 'pending',
                                            {'kind': 'checked'}, now=213)
        resolved = reopened.resolve_reconciliation(candidate['event_key'], 'controller-A', 'pending',
            {'kind': 'canonical-reconcile', 'verification': 'canonical_no_action'}, now=214)
        assert resolved['state'] == 'pending'
        assert reopened.claim('controller-B', now=215)['state'] == 'claimed'


def test_expired_owner_cannot_complete_without_reconciliation(tmp_path):
    gitlab_export(tmp_path / 'exports')
    candidate = intake.export_candidates(tmp_path / 'exports', ACTIVATED,
                                         gitlab_project_id='88349936')['candidates'][0]
    with intake.FailureInbox(tmp_path / 'inbox.sqlite') as inbox:
        inbox.enqueue(candidate, now=100)
        inbox.claim('controller', now=200, lease_seconds=10)
        result = inbox.complete(candidate['event_key'], 'controller',
                                {'kind': 'done', 'verification': 'canonical_terminal'}, now=211)
        assert result['state'] == 'needs_reconciliation'
        assert inbox.get(candidate['event_key'])['state'] == 'needs_reconciliation'


def test_receipts_are_small_closed_and_terminal_states_do_not_reopen(tmp_path):
    gitlab_export(tmp_path / 'exports')
    candidate = intake.export_candidates(tmp_path / 'exports', ACTIVATED,
                                         gitlab_project_id='88349936')['candidates'][0]
    with intake.FailureInbox(tmp_path / 'inbox.sqlite') as inbox:
        inbox.enqueue(candidate, now=100)
        inbox.claim('controller', now=101)
        with pytest.raises(ValueError, match='allowlisted'):
            inbox.complete(candidate['event_key'], 'controller',
                           {'kind': 'verified', 'verification': 'canonical_terminal',
                            'password': 'must-not-be-stored'}, now=102)
        result = inbox.complete(candidate['event_key'], 'controller',
                                {'kind': 'verified', 'verification': 'canonical_terminal'}, now=102)
        assert result['state'] == 'complete'
        assert inbox.get(candidate['event_key'])['state'] == 'complete'


def test_inbox_refuses_symlink_database(tmp_path):
    real = tmp_path / 'real.sqlite'
    real.touch()
    link = tmp_path / 'link.sqlite'
    link.symlink_to(real)
    with pytest.raises(ValueError, match='symlink'):
        intake.FailureInbox(link)
