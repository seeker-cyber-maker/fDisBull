"""Initial raw sessions use the existing run-id epoch until a genuine restore.

This uses an authored provider and actual Project/snapshot storage. It never
runs a guest or edits a captured snapshot.
"""
from copy import deepcopy
import hashlib
import json

import pytest

from fdisbull import runtime_desqview as dv
from fdisbull.memory_search_runtime import MemorySearchSessionMixin
from fdisbull.project import Project
from test_runtime_desqview_physical import PhysicalSession, EVIDENCE


@pytest.mark.parametrize('explicit_epoch', [True, False], ids=['explicit_epoch', 'initial_default_epoch'])
def test_default_epoch_uses_run_identity_without_private_injection(tmp_path, monkeypatch, explicit_epoch):
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path/'objects'))
    source = tmp_path/'authored.bin'
    source.write_bytes(bytes(range(256))*32)
    with Project.create(tmp_path/'epoch.fdb', source, arch='x86', bits=32) as project:
        session = PhysicalSession(project)
        if not explicit_epoch:
            # Remove only the reusable fixture's explicit-epoch model, BEFORE
            # task creation/capture. Normal initial MachineContext has no attr.
            del session._runtime_epoch
            assert not hasattr(session, '_runtime_epoch')
        expected_epoch = getattr(session, '_runtime_epoch', session.run_id)
        if not explicit_epoch:
            assert expected_epoch == session.run_id
        monkeypatch.setattr(dv, '_source', lambda _: (session.source, session.source_identity))
        with project.transaction(True):
            project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                (session.run_id, session.version['id'], 'authored', None, 'stopped', '{}'))
        provider = dv.discover(session)
        native = provider.current_identity()
        external = 'authored-default-epoch-task'
        task = project.runtime_task_start(session.run_id, external, EVIDENCE,
            capture_epoch=expected_epoch)['task']
        document = project._mapping_task(task)
        document.pop('started'); document.pop('ended')
        document['automatic_tracking'] = dict(identity=dict(provider='source-qualified-desqview', native=deepcopy(native)))
        with project.transaction(True):
            project.db.execute('UPDATE runtime_mapping_tasks SET document=? WHERE id=?', (json.dumps(document), task))
        captured = MemorySearchSessionMixin.memory_snapshot(session, session.linear,
            length=32, task_id=external, name='fresh-authored-default-epoch.bin')
        assert captured['snapshot']['context']['capture_epoch'] == expected_epoch
        assert project._mapping_task(task)['capture_epoch'] == expected_epoch
        before = project.db.execute('SELECT data,metadata FROM debug_artifacts WHERE id=?',
                                    (captured['artifact'],)).fetchone()
        retained_before = (bytes(before['data']), before['metadata'])
        try:
            proof = provider.qualify_physical(captured['artifact'], native)
        finally:
            after = project.db.execute('SELECT data,metadata FROM debug_artifacts WHERE id=?',
                                       (captured['artifact'],)).fetchone()
            assert (bytes(after['data']), after['metadata']) == retained_before
            if not explicit_epoch:
                assert not hasattr(session, '_runtime_epoch')
        assert proof['qualified'] is True
        assert proof['snapshot'] == captured['artifact']
        assert proof['context_sha256'] == hashlib.sha256(json.dumps(captured['snapshot']['context'],
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
