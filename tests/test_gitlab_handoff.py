"""Contract tests: publication identity, attachment evidence, and uncertain retries."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('gitlab_handoff', Path(__file__).parents[1] / 'scripts/gitlab_handoff.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


@pytest.fixture
def manifest(tmp_path):
    data = b'# Authored test report\nAll focused checks passed locally.\n'
    (tmp_path / 'report.md').write_bytes(data)
    m = dict(schema=1, project_id=h.PROJECT, origin='chat:example/task-a',
             source_branch='agent/task-a', target_branch='stack/parent', head='a' * 40,
             base='b' * 40, title='Authored change', summary='A small authored change.',
             tests=['local: focused checks @ ' + 'a' * 40], limitations=['Hosted CI unverified.'],
             attachments=[dict(path='report.md', sha256=h.digest(data), reviewed=True)])
    path = tmp_path / 'handoff.json'
    path.write_text(json.dumps(m))
    return path


class GitLab:
    def __init__(self, m):
        self.m = m
        self.mrs, self.notes, self.uploads, self.writes = [], [], {}, []
        self.fail = None
        self.move = False

    def request(self, method, endpoint, payload=None, data=None, filename=None, raw=False):
        if method == 'POST':
            self.writes.append(endpoint)
            if self.fail == 'upload' and endpoint.endswith('/uploads'):
                raise h.HandoffError('simulated failed upload')
            if endpoint.endswith('/merge_requests'):
                self.mrs.append(dict(iid=42, source_project_id=h.PROJECT, target_project_id=h.PROJECT,
                    source_branch=self.m['source_branch'], target_branch=self.m['target_branch'],
                    sha=self.m['head'], description=payload['description'], draft=True, state='opened',
                    web_url=h.WEB + '/-/merge_requests/42'))
                if self.fail == 'create-after-write':
                    raise h.HandoffError('simulated timeout after creation')
                return self.mrs[0]
            if endpoint.endswith('/uploads'):
                path = '/uploads/' + 'c' * 32 + '/' + filename
                self.uploads[path] = data
                return {'url': path}
            if endpoint.endswith('/notes'):
                note = dict(id=7, body=payload['body'])
                self.notes.append(note)
                if self.fail == 'note-after-write':
                    raise h.HandoffError('simulated timeout after note')
                return note
            raise AssertionError(endpoint)
        if endpoint == f'projects/{h.PROJECT}':
            return dict(path_with_namespace=h.PROJECT_PATH, visibility='private')
        if '/repository/branches/' in endpoint:
            source = endpoint.endswith('agent%2Ftask-a')
            return {'commit': {'id': self.m['head'] if source else self.m['base']}}
        if '/uploads/' in endpoint:
            result = self.uploads[endpoint[endpoint.index('/uploads/'):]]
            return b'corrupt' if self.fail == 'corrupt' else result
        if '/notes?' in endpoint:
            return copy.deepcopy(self.notes)
        if '/merge_requests?' in endpoint:
            return copy.deepcopy(self.mrs)
        if endpoint.endswith('/merge_requests/42'):
            return copy.deepcopy(self.mrs[0])
        raise AssertionError(endpoint)


def run(api, m, reports, receipt):
    snapshots = []
    result = h.submit(m, reports, api, receipt, lambda r: snapshots.append(copy.deepcopy(r)))
    return result, snapshots


def test_publish_retry_and_cross_receipt_deduplicate(manifest):
    m, reports = h.load_manifest(manifest)
    api, receipt = GitLab(m), {}
    result, snapshots = run(api, m, reports, receipt)
    assert result['status'] == 'verified'
    assert result['mr_url'].endswith('/42')
    assert len(api.writes) == 3  # MR, upload, note
    assert snapshots[0]['pending'] == 'create-mr'
    run(api, m, reports, receipt)
    run(api, m, reports, {})  # another checkout recovers attachment note and bytes
    assert len(api.writes) == 3


def test_preview_is_offline_and_creates_no_receipt(manifest, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(h.Glab, 'request', lambda *a, **k: pytest.fail('network in preview'))
    receipt = tmp_path / 'receipt.json'
    assert h.main(['--manifest', str(manifest), '--receipt', str(receipt)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'preview'
    assert not receipt.exists()


def test_wrong_remote_branch_head_has_no_writes(manifest):
    m, reports = h.load_manifest(manifest)
    api = GitLab({**m, 'head': 'd' * 40})
    with pytest.raises(h.HandoffError, match='head mismatch'):
        run(api, m, reports, {})
    assert not api.writes


@pytest.mark.parametrize('field,value', [('target_branch', 'main'), ('sha', 'd' * 40),
    ('draft', False), ('description', 'someone else'), ('state', 'closed'), ('source_project_id', 1)])
def test_existing_mr_mismatch_never_overwritten(manifest, field, value):
    m, reports = h.load_manifest(manifest)
    api = GitLab(m)
    run(api, m, [], {})
    api.writes.clear()
    api.mrs[0][field] = value
    with pytest.raises(h.HandoffError, match='mismatch'):
        run(api, m, reports, {})
    assert not api.writes


def test_failed_upload_is_partial_and_not_blindly_retried(manifest):
    m, reports = h.load_manifest(manifest)
    api, receipt = GitLab(m), {}
    api.fail = 'upload'
    with pytest.raises(h.HandoffError, match='failed upload'):
        run(api, m, reports, receipt)
    assert receipt['iid'] == 42 and receipt['pending'].startswith('upload:')
    before = list(api.writes)
    api.fail = None
    with pytest.raises(h.HandoffError, match='uncertain'):
        run(api, m, reports, receipt)
    assert api.writes == before


@pytest.mark.parametrize('failure', ['create-after-write', 'note-after-write'])
def test_uncertain_mutation_recovers_by_readback(manifest, failure):
    m, reports = h.load_manifest(manifest)
    api, receipt = GitLab(m), {}
    api.fail = failure
    with pytest.raises(h.HandoffError, match='timeout'):
        run(api, m, reports, receipt)
    api.fail = None
    run(api, m, reports, receipt)
    assert len(api.writes) == 3
    assert receipt['status'] == 'verified' and 'pending' not in receipt


def test_changed_attachment_and_private_payload_rejected(manifest):
    (manifest.parent / 'report.md').write_text('changed')
    with pytest.raises(h.HandoffError, match='hash mismatch'):
        h.load_manifest(manifest)
    for data in [b'\x00binary', b'glpat-example_secret', b'A' * 300, b'password=hidden']:
        with pytest.raises(h.HandoffError):
            h.reviewed_text(data)


def test_target_advance_blocks_publication(manifest):
    m, reports = h.load_manifest(manifest)
    api = GitLab({**m, 'base': 'e' * 40})
    with pytest.raises(h.HandoffError, match='target advanced'):
        run(api, m, reports, {})
    assert not api.writes


def test_corrupt_upload_not_attached(manifest):
    m, reports = h.load_manifest(manifest)
    api = GitLab(m)
    api.fail = 'corrupt'
    with pytest.raises(h.HandoffError, match='hash mismatch'):
        run(api, m, reports, {})
    assert not api.notes


def test_durable_receipt_preserved_for_other_identity(manifest, tmp_path, capsys):
    path = tmp_path / 'receipt.json'
    path.write_text(json.dumps({'key': 'another task'}))
    original = path.read_bytes()
    assert h.main(['--manifest', str(manifest), '--receipt', str(path), '--publish']) == 2
    assert path.read_bytes() == original
    assert json.loads(capsys.readouterr().out)['status'] == 'blocked'


def test_cli_failure_is_durable_and_does_not_expose_stderr(manifest, tmp_path, monkeypatch, capsys):
    import subprocess
    monkeypatch.setattr(h.subprocess, 'run', lambda *a, **k:
                        subprocess.CompletedProcess(a[0], 1, b'', b'private credential detail'))
    path = tmp_path / 'receipt.json'
    assert h.main(['--manifest', str(manifest), '--receipt', str(path), '--publish']) == 2
    out = capsys.readouterr().out
    assert 'private credential detail' not in out
    assert json.loads(out)['status'] == 'blocked'
    assert json.loads(path.read_text())['status'] == 'blocked'


def test_report_upload_is_not_verified_on_branch_movement(manifest):
    m, reports = h.load_manifest(manifest)
    api = GitLab(m)
    original = api.request
    calls = 0
    def request(method, endpoint, *args, **kwargs):
        nonlocal calls
        if endpoint.endswith('agent%2Ftask-a'):
            calls += 1
            if calls > 1:
                return {'commit': {'id': 'd' * 40}}
        return original(method, endpoint, *args, **kwargs)
    api.request = request
    receipt = {}
    with pytest.raises(h.HandoffError, match='branch moved'):
        run(api, m, reports, receipt)
    assert receipt.get('status') != 'verified'
