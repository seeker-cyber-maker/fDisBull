"""Recorded physical readbacks bind only their exact source/capture extent."""
from copy import deepcopy
import hashlib
import json

import pytest

from test_runtime_mapping_snapshots import capture, EVIDENCE, raw_project


def sha(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(value).hexdigest()


def recorded(p, proof):
    envelope = dict(format='fdisbull-automatic-runtime-tracking-1',
                    kind='physical-qualification', document=proof)
    data = json.dumps(envelope, sort_keys=True, separators=(',', ':')).encode()
    artifact = p._debug_artifact('authored-run', 'physical.json', 'runtime-tracking', data,
                                dict(kind='physical-qualification', automatic=True))['artifact']
    return dict(kind='recorded', reference='local-runtime-tracking:' + artifact, sha256=sha(data))


def prepared(project):
    p = project
    task = p.runtime_task_start('authored-run', 'counter', EVIDENCE,
                               capture_epoch='incarnation-1')['task']
    native = dict(handle=123, process_identity=dict(key='authored-process'))
    row = p._mapping_task(task)
    row['automatic_tracking'] = dict(identity=dict(native=native))
    row.pop('started'); row.pop('ended')
    with p.transaction(True):
        p.db.execute('UPDATE runtime_mapping_tasks SET document=? WHERE id=?',
                     (json.dumps(row), task))
    raw = p.regions(1)[0].data[:32]
    pages = [dict(linear='0x123000', physical='0x870000', entries=[]),
             dict(linear='0x124000', physical='0x973000', entries=[])]
    snap = capture(p, raw, start=0x123ff0, pages=pages)
    info = p.memory_snapshot_info(snap)
    context = info['snapshot']['context']
    from fdisbull.runtime_desqview_physical import FORMAT, SCOPE
    proof = dict(format=FORMAT, qualified=True, snapshot=snap,
                 snapshot_sha256=sha(raw), mapping_id=context['mapping_id'],
                 context_sha256=sha(context), native_identity_sha256=sha(native), passes=2,
                 verification_scope=SCOPE,
                 ranges=[dict(linear_start=0x123ff0, physical_start=0x870ff0,
                              length=16, sha256=sha(raw[:16])),
                         dict(linear_start=0x124000, physical_start=0x973000,
                              length=16, sha256=sha(raw[16:]))])
    return task, snap, dict(certificate=proof, evidence=recorded(p, proof))


def test_physical_certificate_persists_only_selected_extent_and_cold(raw_project):
    from fdisbull.project import Project
    p = raw_project
    task, snap, proof = prepared(p)
    p.runtime_map_snapshot(task, snap, 'region:0', 16, 16, snapshot_offset=16,
                           physical_readback=proof)
    binding = p.runtime_mappings(task)['bindings'][0]
    q = binding['physical_qualification']
    assert q['qualified'] is True and q['physical_start'] == 0x973000
    assert q['linear_start'] == 0x124000 and q['length'] == 16
    assert q['sha256'] == sha(p.regions(1)[0].data[16:32])
    assert q['certificate_sha256'] == sha(proof['certificate'])
    assert q['evidence'] == proof['evidence']
    with Project(p.path) as cold:
        assert cold.runtime_mappings(task)['bindings'] == [binding]


@pytest.mark.parametrize('change', ['snapshot', 'snapshot_sha256', 'mapping_id',
    'context_sha256', 'native_identity_sha256', 'qualified', 'passes',
    'verification_scope', 'physical', 'bytes', 'gap', 'duplicate', 'boolean_address'])
def test_foreign_or_incomplete_physical_proofs_publish_nothing(raw_project, change):
    p = raw_project
    task, snap, proof = prepared(p)
    cert = proof['certificate']
    if change in ('snapshot', 'snapshot_sha256', 'mapping_id', 'context_sha256',
                   'native_identity_sha256', 'verification_scope'):
        cert[change] = 'wrong'
    elif change == 'qualified': cert['qualified'] = False
    elif change == 'passes': cert['passes'] = True
    elif change == 'physical': cert['ranges'][0]['physical_start'] += 4096
    elif change == 'bytes': cert['ranges'][0]['sha256'] = '00' * 32
    elif change == 'gap': cert['ranges'].pop()
    elif change == 'duplicate': cert['ranges'].append(deepcopy(cert['ranges'][0]))
    elif change == 'boolean_address': cert['ranges'][0]['linear_start'] = True
    proof['evidence'] = recorded(p, cert)
    before = p.runtime_mapping_events(task)
    with pytest.raises(ValueError):
        p.runtime_map_snapshot(task, snap, 'region:0', 0, 16, physical_readback=proof)
    assert p.runtime_mapping_events(task) == before
    assert p.runtime_mappings(task)['bindings'] == []


@pytest.mark.parametrize('change', ['modeled', 'missing', 'changed_envelope'])
def test_certificate_requires_matching_local_recorded_artifact(raw_project, change):
    p = raw_project
    task, snap, proof = prepared(p)
    if change == 'modeled': proof['evidence'] = EVIDENCE
    elif change == 'missing': proof['evidence']['reference'] = 'local-runtime-tracking:missing'
    else: proof['certificate']['ranges'][0]['sha256'] = '00' * 32
    with pytest.raises(ValueError):
        p.runtime_map_snapshot(task, snap, 'region:0', 0, 16, physical_readback=proof)
    assert p.runtime_mappings(task)['bindings'] == []


def test_old_capture_coordinates_never_gain_direct_readback_claim(raw_project):
    p = raw_project
    task, snap, _ = prepared(p)
    p.runtime_map_snapshot(task, snap, 'region:0', 0, 16)
    binding = p.runtime_mappings(task)['bindings'][0]
    assert binding['physical_start'] == 0x870ff0
    assert 'physical_qualification' not in binding


def test_registry_checkpoint_retains_historical_proof_without_requalifying(raw_project):
    p = raw_project
    task, snap, proof = prepared(p)
    p.runtime_map_snapshot(task, snap, 'region:0', 0, 16, physical_readback=proof)
    original = p.runtime_mappings(task)['bindings'][0]
    cp = p.runtime_map_checkpoint(task, EVIDENCE)['checkpoint']
    p.runtime_map_restore(task, cp, EVIDENCE)
    restored = p.runtime_mappings(task)['bindings'][0]
    assert restored['restored_from'] == original['id']
    assert restored['physical_qualification']['qualified'] is False
    assert restored['historical_physical_qualification'] == original['physical_qualification']


@pytest.mark.parametrize('withdraw', [False, True])
def test_used_certificate_cannot_requalify_same_or_withdrawn_interval(raw_project, withdraw):
    p = raw_project
    task, snap, proof = prepared(p)
    binding = p.runtime_map_snapshot(task, snap, 'region:0', 0, 16,
                                    physical_readback=proof)['binding']
    if withdraw:
        p.runtime_unmap(task, [binding], EVIDENCE)
    before = p.runtime_mapping_events(task)
    with pytest.raises(ValueError, match='physical readback certificate'):
        p.runtime_map_snapshot(task, snap, 'region:0', 0, 16, physical_readback=proof)
    assert p.runtime_mapping_events(task) == before
