import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts' / 'ci'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('production_control', SCRIPTS / 'production_control.py')
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


def config(tmp_path):
    root = tmp_path / 'private-state'; root.mkdir(mode=0o700)
    control.write_json(root / 'installation.json', {'schema': 'fdisbull-production-state-1', 'installation_id': 'test-install'}, exclusive=True)
    with control.FailureInbox(root / 'failure-inbox.sqlite'): pass
    lock = tmp_path / 'executor.lock'; lock.touch()
    return {'schema': 'fdisbull-production-ci-config-1', 'enabled': True,
            'installation_id': 'test-install', 'state_dir': str(root),
            'executor_lock': str(lock), 'export_root': str(tmp_path / 'exports'),
            'activated_epoch': 1, 'max_incident_seconds': 600,
            'github': {'repository': 'seeker-cyber-maker/fDisBull', 'workflow_id': 417757453,
                       'runner_id': 21, 'actor': 'seeker-cyber-maker',
                       'ref': 'codex/production-ci-recovery-20261113', 'control_sha': 'c' * 40,
                       'profile': 'ordinary', 'sole_executor_authority': True}}


def initial_success(c):
    target = {'provider': 'github', 'repository': 'seeker-cyber-maker/fDisBull',
              'run_id': '100', 'run_attempt': '1', 'job_id': '101', 'source_sha': 'a' * 40,
              'job_name': 'qualification', 'runner_id': '21', 'ref': c['github']['ref'], 'control_sha': 'c' * 40}
    path = Path(c['state_dir']) / 'initial-evidence.json'
    control.write_json(path, {'schema': 'fdisbull-production-evidence-1', 'target': target, 'job_status': 'success'}, exclusive=True)
    return {'status': 'success', 'verified': True, 'target': target, 'receipt_path': str(path)}


def test_disabled_status_does_not_contact_runtime_or_provider(tmp_path):
    c = config(tmp_path); c['enabled'] = False
    def no_call(*args): raise AssertionError('provider or runtime called')
    service = control.ProductionService(c, no_call, discover=no_call)
    assert service.status() == {'schema_version': 1, 'pending_work': False}
    assert service.run() == {'status': 'disabled'}


def test_idle_status_is_compact_and_model_free(tmp_path):
    c = config(tmp_path); calls = []
    def discover(*args, **kwargs):
        calls.append(kwargs)
        return {'candidates': [], 'diagnostics': []}
    def no_runtime(*args): raise AssertionError('runtime called by status')
    service = control.ProductionService(c, no_runtime, discover=discover)
    assert service.status() == {'schema_version': 1, 'pending_work': False}
    assert calls[0]['github_repository'] == 'seeker-cyber-maker/fDisBull'
    assert calls[0]['gitlab_project_id'] == '88349936'


def test_status_new_hint_does_not_mutate_or_enqueue(tmp_path):
    c = config(tmp_path)
    p = Path(c['state_dir']) / 'failure-inbox.sqlite'
    before = p.read_bytes(), p.stat().st_mtime_ns
    service = control.ProductionService(c, None, discover=lambda *a, **k: {
        'candidates': [{'event_key': 'new-unverified-hint'}], 'diagnostics': []})
    assert service.status() == {'schema_version': 1, 'pending_work': True}
    assert service.status() == {'schema_version': 1, 'pending_work': True}
    assert (p.read_bytes(), p.stat().st_mtime_ns) == before
    with control.FailureInbox(p) as inbox:
        assert inbox.db.execute('SELECT count(*) FROM events').fetchone()[0] == 0


def test_missing_state_or_inbox_never_creates_fresh_history(tmp_path):
    c = config(tmp_path)
    inbox = Path(c['state_dir']) / 'failure-inbox.sqlite'
    moved = inbox.with_suffix('.preserved'); inbox.rename(moved)
    with pytest.raises(ValueError, match='preinstalled durable inbox'):
        control.ProductionService(c, None)
    assert not inbox.exists() and moved.exists()


def test_changed_marker_and_blocked_state_refuse_automatic_work(tmp_path):
    c = config(tmp_path)
    marker = Path(c['state_dir']) / 'installation.json'
    original = marker.read_bytes()
    marker.write_text(json.dumps({'schema': 'fdisbull-production-state-1', 'installation_id': 'other'}))
    with pytest.raises(ValueError, match='identity unknown'):
        control.ProductionService(c, None)
    marker.write_bytes(original)
    control.write_json(marker.parent / 'blocked.json', {'reason': 'unknown-provider-outcome'}, exclusive=True)
    with pytest.raises(ValueError, match='canonical attention'):
        control.ProductionService(c, None)


def test_lease_is_exclusive_and_released_after_exception(tmp_path):
    lock = tmp_path / 'executor.lock'; lock.touch()
    with pytest.raises(RuntimeError):
        with control.executor_lease(lock) as lease:
            assert lease['owner_pid'] > 0
            with pytest.raises(BlockingIOError):
                with control.executor_lease(lock): pass
            raise RuntimeError('owned work failed')
    with control.executor_lease(lock): pass


def test_action_intent_and_acceptance_are_durable_and_idempotent(tmp_path):
    ledger = control.ActionLedger(tmp_path / 'actions', clock=lambda: 123)
    payload = {'target': {'source_sha': 'a' * 40}}
    first = ledger.claim('retry_job', 'incident:retry', payload)
    assert first['new'] and ledger.started('incident:retry') == 123
    assert ledger.claim('retry_job', 'incident:retry', payload)['new'] is False
    proof = {'envelope': {'http_status': 201, 'data': None, 'request_id': 'safe'}}
    receipt = ledger.save_acceptance('incident:retry', proof)
    assert ledger.save_acceptance('incident:retry', proof) == receipt
    assert ledger.load_acceptance('incident:retry') == {'proof': proof, 'receipt_path': receipt}
    with pytest.raises(ValueError, match='intent conflict'):
        ledger.claim('retry_job', 'incident:retry', {'target': {}})
    with pytest.raises(ValueError, match='acceptance conflict'):
        ledger.save_acceptance('incident:retry', {'different': True})


def test_acceptance_without_original_intent_cannot_be_reinitialized(tmp_path):
    ledger = control.ActionLedger(tmp_path / 'actions')
    p = ledger._path('lost-intent', '.accepted.json')
    control.write_json(p, {'action_key': 'lost-intent', 'proof': {}}, exclusive=True)
    with pytest.raises(ValueError, match='without its original intent'):
        ledger.claim('retry_job', 'lost-intent', {})


def test_idle_run_holds_one_shared_lease_and_starts_no_job(tmp_path):
    c = config(tmp_path); observed = []
    def factory(config, root, lease):
        with pytest.raises(BlockingIOError):
            with control.executor_lease(c['executor_lock']): pass
        observed.append(lease)
        return object()
    service = control.ProductionService(c, factory, discover=lambda *a, **k: {'candidates': [], 'diagnostics': []})
    assert service.run() == {'status': 'idle'}
    assert len(observed) == 1


def test_initial_dispatch_is_preserved_without_reissuing_on_restart(tmp_path):
    c = config(tmp_path)
    c['initial_request'] = {'key': 'qualification-1', 'source_sha': 'a' * 40}
    calls = []
    class Runtime:
        def prepare(self, manifest): return {'allowed': True}
        def initial_dispatch(self, request):
            calls.append(request)
            return initial_success(c)
    service = control.ProductionService(c, lambda *a: Runtime(), discover=lambda *a, **k: {'candidates': [], 'diagnostics': []})
    assert service.status()['pending_work'] is True
    assert service.run() == {'status': 'idle'}
    assert service.run() == {'status': 'idle'}
    assert len(calls) == 1
    assert service.status()['pending_work'] is False


def test_initial_unverified_success_never_advances_queue(tmp_path):
    c = config(tmp_path); c['initial_request'] = {'key': 'qualification-1', 'source_sha': 'a' * 40}
    class Runtime:
        def prepare(self, manifest): return {'allowed': True}
        def initial_dispatch(self, request): return {'status': 'success', 'verified': False}
    service = control.ProductionService(c, lambda *a: Runtime(), discover=lambda *a, **k: {'candidates': [], 'diagnostics': []})
    with pytest.raises(ValueError, match='qualification incomplete'): service.run()
    assert not (Path(c['state_dir']) / 'initial-result.json').exists()


def test_cleanup_guard_holds_executor_before_an_error_can_release_it(tmp_path):
    lock = tmp_path / 'executor.lock'; lock.touch(); held = []
    class Runtime:
        def cleanup_blocked(self): return True
        def hold_cleanup(self):
            with pytest.raises(BlockingIOError):
                with control.executor_lease(lock): pass
            held.append('lease-still-held')
    with pytest.raises(RuntimeError, match='canonical reconciliation'):
        with control.executor_lease(lock):
            with control.cleanup_guard(Runtime()):
                raise ValueError('original unknown daemon outcome')
    assert held == ['lease-still-held']


def test_initial_propagation_wait_reconciles_without_resetting_deadline(tmp_path):
    c = config(tmp_path); c['initial_request'] = {'key': 'qualification-1', 'source_sha': 'a' * 40}
    now = [100.0]; calls = []; reservations = [False, True, True]
    class Runtime:
        def prepare(self, manifest):
            ready = reservations.pop(0)
            return {'allowed': ready, 'reason': 'cooldown', 'next_refresh_at': now[0] + 5}
        def health(self): return {'state': 'healthy', 'receipt_path': 'durable-health'}
        def initial_dispatch(self, request):
            calls.append(request)
            return ({'status': 'pending', 'verified': True, 'receipt_path': 'durable-accepted'} if len(calls) == 1
                    else initial_success(c))
    service = control.ProductionService(c, lambda *a: Runtime(), clock=lambda: now[0],
        sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
        discover=lambda *a, **k: {'candidates': [], 'diagnostics': []})
    assert service.run() == {'status': 'idle'}
    assert len(calls) == 2 and now[0] == 165
    request = json.loads((Path(c['state_dir']) / 'initial-request.json').read_text())
    assert request['created_epoch'] == 100


def test_provider_admission_propagates_actual_initial_deadline(tmp_path, monkeypatch):
    c = config(tmp_path); seen = []; checked = []
    class Runtime:
        def prepare(self, manifest): seen.append(manifest); return {'allowed': True}
        def health(self): pytest.fail('ready admission does not require a wait health check')
    runtime = Runtime()
    monkeypatch.setattr(control, 'check_worker_cleanup', lambda value: checked.append(value))
    service = control.ProductionService(c, lambda *args: runtime, clock=lambda: 1000)
    service._await_provider(runtime, 'github', 1450)
    assert seen == [{'initial_target': {'provider': 'github'}, 'deadline_epoch': 1450}]
    assert checked == [runtime]


@pytest.mark.parametrize('body', ['', '{', '{"status":"success","verified":true}'])
def test_torn_or_unbound_initial_marker_never_suppresses_pending_work(tmp_path, body):
    c = config(tmp_path); c['initial_request'] = {'key': 'qualification-1', 'source_sha': 'a' * 40}
    p = Path(c['state_dir']) / 'initial-result.json'; p.write_text(body)
    service = control.ProductionService(c, None, discover=lambda *a, **k: {'candidates': [], 'diagnostics': []})
    with pytest.raises(ValueError): service.status()
    assert p.read_text() == body


def test_initial_marker_is_bound_to_request_and_retained_receipt(tmp_path):
    c = config(tmp_path); c['initial_request'] = {'key': 'qualification-1', 'source_sha': 'a' * 40}
    service = control.ProductionService(c, None, discover=lambda *a, **k: {'candidates': [], 'diagnostics': []})
    result = initial_success(c)
    service._write_initial_result(c['initial_request'], result)
    assert service.status()['pending_work'] is False
    service.config['initial_request'] = {'key': 'different', 'source_sha': 'a' * 40}
    with pytest.raises(ValueError, match='binding unknown'): service.status()
    service.config['initial_request'] = c['initial_request']
    Path(result['receipt_path']).write_text('{}')
    with pytest.raises(ValueError, match='receipt unavailable'): service.status()


def test_missing_github_control_pins_cannot_produce_a_status(tmp_path):
    c = config(tmp_path); del c['github']
    with pytest.raises(ValueError, match='control identity missing'):
        control.ProductionService(c, None)


def test_action_ledger_read_only_intent_lookup_binds_payload(tmp_path):
    ledger=control.ActionLedger(tmp_path,clock=lambda:1234.5)
    assert ledger.load_intent('retry') is None
    claim=ledger.claim('retry_job','retry',{'target':{'run_id':'10'}})
    path=Path(claim['receipt_path']);before=path.read_bytes()
    result=ledger.load_intent('retry')
    assert result['intent']=={'action':'retry_job','action_key':'retry','payload':{'target':{'run_id':'10'}},'created_epoch':1234.5}
    assert result['receipt_path']==str(path) and path.read_bytes()==before


def related_setup(tmp_path):
    import test_production_runtime as runtime_fixture
    import test_production_evidence as evidence_fixture

    c = config(tmp_path)
    service = control.ProductionService(c, None)
    root = Path(c['export_root'])
    target = {'provider': 'github', 'repository': 'seeker-cyber-maker/fDisBull',
              'run_id': '11', 'run_attempt': '2', 'job_id': '23', 'source_sha': 'a' * 40,
              'job_name': 'qualification', 'runner_id': '21', 'ref': c['github']['ref'], 'control_sha': 'c' * 40}
    parent_target = dict(target, run_attempt='1', job_id='22')
    runtime_fixture.make_export(root, parent_target, 'failed', 'd' * 64)
    runtime_fixture.make_export(root, target, 'failed', 'd' * 64)
    candidates = control.export_candidates(root, 1, limit=32, gitlab_project_id='88349936',
                                            github_repository='seeker-cyber-maker/fDisBull')['candidates']
    parent = next(x for x in candidates if x['job_id'] == '22')
    child = next(x for x in candidates if x['job_id'] == '23')
    directory = Path(c['state_dir']) / 'incidents' / parent['event_key']
    directory.mkdir(mode=0o700, parents=True)
    observation = {**target, 'status': 'failed'}
    ev = evidence_fixture.m.ProductionEvidence(root / 'github', directory / 'evidence', 'ordinary', evidence_fixture.capture)(observation, ['tests'])
    manifest = {'incident_id': parent['event_key']}
    state = {'manifest': manifest, 'status': 'attention', 'target': target,
             'observations': [observation], 'evidence': [ev]}
    control.write_json(directory / 'manifest.json', manifest)
    control.write_json(directory / 'state.json', state)
    with service._inbox() as inbox:
        inbox.enqueue(parent, now=2)
        inbox.claim(control.OWNER, now=3)
        inbox.attention(parent['event_key'], control.OWNER,
                        {'kind': 'controller_attention', 'status': 'attention',
                         'provider_receipt_path': str(directory / 'state.json')}, now=4)
    return service, parent, child, directory


def test_related_failure_closes_with_verified_parent_evidence_and_readonly_status(tmp_path):
    service, parent, child, directory = related_setup(tmp_path)
    assert service.status()['pending_work'] is False
    with service._inbox() as inbox:
        assert inbox.get(child['event_key']) is None
        service._discover(inbox)
        row = inbox.get(child['event_key'])
        assert row['state'] == 'attention'
        payload = row['receipt']['payload']
        assert payload['kind'] == 'related_failed_attempt'
        assert payload['parent_event_key'] == parent['event_key']
        assert payload['parent_state_path'] == str(directory / 'state.json')
        assert Path(payload['evidence_receipt_path']).is_file()
        service._discover(inbox)
        assert inbox.get(child['event_key']) == row
    assert service.status()['pending_work'] is False


def test_related_export_tampering_does_not_suppress(tmp_path):
    service, parent, child, directory = related_setup(tmp_path)
    folder = Path(child['metadata_path']).parent
    (folder / 'exported/artifacts/recovery/diagnostic.json').write_text('changed')
    assert service.status()['pending_work'] is True
    with service._inbox() as inbox:
        service._discover(inbox)
        assert inbox.get(child['event_key'])['state'] == 'pending'


def test_related_claim_is_never_overridden(tmp_path):
    service, parent, child, directory = related_setup(tmp_path)
    with service._inbox() as inbox:
        inbox.enqueue(child, now=5)
        inbox.claim(control.OWNER, now=6)
        service._discover(inbox)
        assert inbox.get(child['event_key'])['state'] == 'claimed'
    assert service.status()['pending_work'] is True


def test_missing_parent_evidence_stays_pending(tmp_path):
    service, parent, child, directory = related_setup(tmp_path)
    receipt = next((directory / 'evidence').glob('*.evidence.json'))
    receipt.rename(receipt.with_suffix('.preserved'))
    assert service.status()['pending_work'] is True
    with service._inbox() as inbox:
        service._discover(inbox)
        assert inbox.get(child['event_key'])['state'] == 'pending'


def test_changed_job_metadata_remains_discoverable(tmp_path):
    service, parent, child, directory = related_setup(tmp_path)
    path = Path(child['metadata_path'])
    metadata = json.loads(path.read_bytes())
    metadata['qualification_exit_code'] = 2
    path.write_text(json.dumps(metadata))
    assert service.status()['pending_work'] is True
    with service._inbox() as inbox:
        service._discover(inbox)
        assert inbox.get(child['event_key'])['state'] == 'pending'


def test_unrelated_same_run_and_source_remains_discoverable(tmp_path):
    import test_production_runtime as runtime_fixture
    service, parent, child, directory = related_setup(tmp_path)
    target = {'provider': 'github', 'repository': 'seeker-cyber-maker/fDisBull',
              'run_id': '11', 'run_attempt': '3', 'job_id': '24', 'source_sha': 'a' * 40,
              'job_name': 'qualification', 'runner_id': '21', 'ref': service.config['github']['ref'],
              'control_sha': 'c' * 40}
    runtime_fixture.make_export(Path(service.config['export_root']), target, 'failed', 'd' * 64)
    assert service.status()['pending_work'] is True
    with service._inbox() as inbox:
        service._discover(inbox)
        rows = inbox.db.execute("SELECT descriptor,state FROM events WHERE state='pending'").fetchall()
        assert len(rows) == 1 and json.loads(bytes(rows[0][0]))['job_id'] == '24'


def test_related_expired_claim_stays_needs_reconciliation(tmp_path):
    service, parent, child, directory = related_setup(tmp_path)
    with service._inbox() as inbox:
        inbox.enqueue(child, now=5)
        inbox.claim(control.OWNER, now=6, lease_seconds=1)
        inbox.claim(control.OWNER, now=8)
        service._discover(inbox)
        assert inbox.get(child['event_key'])['state'] == 'needs_reconciliation'
    assert service.status()['pending_work'] is True


def test_parent_terminal_receipt_mismatch_fails_closed(tmp_path):
    service, parent, child, directory = related_setup(tmp_path)
    path = directory / 'state.json'
    data = json.loads(path.read_text())
    data['status'] = 'complete'
    path.write_text(json.dumps(data))
    assert service.status()['pending_work'] is True
    with service._inbox() as inbox:
        service._discover(inbox)
        assert inbox.get(child['event_key'])['state'] == 'pending'
