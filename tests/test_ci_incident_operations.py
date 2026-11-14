"""Portable native-journal protocol checks; no live journal or sender."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

import pytest

SOURCES = Path(__file__).resolve().parents[1] / 'scripts/ci/operations'


def load(name, filename=None):
    spec = importlib.util.spec_from_file_location(name, SOURCES / ((filename or name) + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


journal = load('notification_journal')
_previous = sys.modules.get('notification_journal')
sys.modules['notification_journal'] = journal
try:
    ci = load('fdisbull_native_ci_incident', 'ci_incident')
finally:
    if _previous is None:
        del sys.modules['notification_journal']
    else:
        sys.modules['notification_journal'] = _previous


@pytest.fixture
def db():
    connection = sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE, incident TEXT, phase TEXT, body TEXT, created INTEGER, UNIQUE(incident,phase))')
    yield connection
    connection.close()


def request():
    return {'dedupe_key': 'controller-attention:' + 'c' * 64,
            'phase': 'attention', 'reason': 'ci_executor_unavailable', 'test': True,
            'context': {'provider': 'github', 'project': 'owner/project', 'run_id': '11',
                        'job_id': '22', 'commit_sha': 'a' * 40, 'job_name': 'qualification',
                        'receipt_path': '/var/lib/fdisbull-ci/control/recovery/production/incidents/' + 'c' * 64 + '/controller-attention-state.json'}}


def test_controller_attention_journals_once_without_down_or_recovery(db):
    payload = request()
    first = ci.append(db, payload, now=1000)
    second = ci.append(db, payload, now=1100)
    assert first['stage'] == 'journaled' and first['execution_performed'] is False
    assert first['already_present'] is False and second['already_present'] is True
    assert first['event_id'] == second['event_id']
    page = journal.page(db, 0, 100)
    assert len(page['events']) == 1
    event = page['events'][0]['event']
    assert event['data']['phase'] == 'attention'
    assert event['data']['status'] == 'needs_operator'
    assert event['data']['reason'] == 'ci_executor_unavailable'
    assert event['data']['observed_epoch'] == 1000
    assert event['data']['duration_seconds'] == 0
    assert set(event['data']['context']) == set(payload['context'])


@pytest.mark.parametrize('mutation', [
    {'dedupe_key': 'controller-attention:bad'},
    {'dedupe_key': 'controller-attention-' + 'c' * 64},
    {'dedupe_key': 'controller-attention:' + 'C' * 64},
    {'phase': 'down', 'reason': 'ci_executor_unavailable'},
    {'phase': 'recovered', 'reason': 'ci_requalified'},
    {'reason': 'ci_repair_failed'},
])
def test_reserved_namespace_rejects_other_lifecycles_and_malformed_keys(db, mutation):
    payload = request()
    payload.update(mutation)
    with pytest.raises(ValueError, match='controller_attention_binding'):
        ci.append(db, payload, now=1000)
    assert db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 0


@pytest.mark.parametrize('field,value', [
    ('provider', 'local'),
    ('receipt_path', '/var/lib/fdisbull-ci/control/recovery/production/incidents/' + 'd' * 64 + '/controller-attention-state.json'),
    ('receipt_path', '/var/lib/fdisbull-ci/control/recovery/production/incidents/' + 'c' * 64 + '/state.json'),
    ('receipt_path', '/var/lib/fdisbull-ci/control/recovery/production/incidents/' + 'c' * 64 + '/../controller-attention-state.json'),
])
def test_controller_context_is_bound_to_exact_private_snapshot_location(db, field, value):
    payload = request()
    payload['context'][field] = value
    with pytest.raises(ValueError):
        ci.append(db, payload, now=1000)
    assert db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 0


def test_conflicting_replay_preserves_original_event(db):
    payload = request()
    ci.append(db, payload, now=1000)
    payload['test'] = False
    with pytest.raises(ValueError, match='conflicting_phase_replay'):
        ci.append(db, payload, now=1100)
    assert db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 1


def test_legacy_job_lifecycle_and_initial_attention_rule_stay_intact(db):
    payload = request()
    payload['dedupe_key'] = 'ordinary-job'
    with pytest.raises(ValueError, match='invalid_transition'):
        ci.append(db, payload, now=1000)
    payload.update(phase='down', reason='ci_job_failed')
    ci.append(db, payload, now=1000)
    payload.update(phase='attention', reason='ci_repair_failed')
    ci.append(db, payload, now=1100)
    payload.update(phase='recovered', reason='ci_requalified')
    ci.append(db, payload, now=1200)
    phases = [json.loads(row[0])['data']['phase'] for row in db.execute('SELECT body FROM events ORDER BY seq')]
    assert phases == ['down', 'attention', 'recovered']
