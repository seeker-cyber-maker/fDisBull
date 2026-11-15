"""Bounded native-QEMU experiment document and route admission tests."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from fdisbull import qemu_experiments as experiments


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


class _Rows:
    def __init__(self, rows):
        self.rows = rows
        self.result = None

    def execute(self, _query, args):
        self.result = self.rows.get(args[0])
        return self

    def fetchone(self):
        return self.result


class _Project:
    def __init__(self, rows):
        self.db = _Rows(rows)

    def debug_layer_info(self, _identifier):
        raise AssertionError('No layers should be queried in this fixture')


def test_logical_layer_hash_ignores_fresh_native_owner_epoch_only():
    base = dict(id='old', name='patch', version=1, sha256='metadata-hash', kind='ram',
                patches=[{'address': '0x2000', 'expected_hex': '00', 'data_hex': '01'}],
                native_binding={'scope': 'task-private', 'run': 'one', 'epoch': 3,
                    'task_identity': {'cookie': 9, 'incarnation': 2}, 'spans': [[0x2000, 1]]})
    restored = {**base, 'id': 'new', 'native_binding': {**base['native_binding'], 'run': 'two', 'epoch': 7}}
    assert experiments._logical_layer_hash(base) == experiments._logical_layer_hash(restored)
    changed = {**restored, 'patches': [{'address': '0x2000', 'expected_hex': '00', 'data_hex': '02'}]}
    assert experiments._logical_layer_hash(base) != experiments._logical_layer_hash(changed)


def test_native_experiment_script_admission_is_bounded_and_excludes_mutators(monkeypatch):
    monkeypatch.setattr('fdisbull.debug_script.validate_script',
        lambda _script, session=None: session._expanded)
    session = SimpleNamespace(_expanded=[{'op': 'run', 'timeout_ms': 1000},
                                         {'op': 'trace', 'count': 4},
                                         {'op': 'screenshot', 'grid': False}])
    script = {'format': 'fdisbull-script-1', 'steps': [{'op': 'run'}]}
    assert len(experiments._validate_script(session, script)) == 3
    session._expanded = [{'op': 'memory', 'length': 65537}]
    with pytest.raises(ValueError, match='lengths'):
        experiments._validate_script(session, script)
    session._expanded = [{'op': 'layer-enable'}]
    with pytest.raises(ValueError, match='Unsupported native experiment operations'):
        experiments._validate_script(session, script)
    session._expanded = [{'op': 'screenshot', 'grid': True}]
    with pytest.raises(ValueError, match='ungridded'):
        experiments._validate_script(session, script)


def test_project_document_requires_matching_full_process_checkpoint(monkeypatch):
    bundle = {'format': 'fdisbull-qemu-dos-process-qcow2-v2', 'source_sha256': 'a' * 64,
              'version': 1, 'version_sha256': 'b' * 64, 'runtime': {'profile': 'test'},
              'process': {'capture_epoch': 'origin:process:1'}}
    state_data = b'full-state'
    state_metadata = {'format': bundle['format'], 'source_sha256': bundle['source_sha256'],
                      'origin_run': 'origin',
                      'sidecar_sha256': hashlib.sha256(_encode(bundle)).hexdigest()}
    script = {'format': 'fdisbull-script-1', 'backend': 'qemu-dos', 'steps': []}
    document = {'format': experiments.FORMAT, 'version': 1, 'source_sha256': bundle['source_sha256'],
        'version_sha256': bundle['version_sha256'], 'runtime': bundle['runtime'],
        'identity': {'source_sha256': bundle['source_sha256'], 'version_sha256': bundle['version_sha256'],
                     'runtime': bundle['runtime']},
        'origin_run': 'origin', 'capture_epoch': 'origin:process:1',
        'checkpoint': {'artifact': 'state-id', 'sha256': hashlib.sha256(state_data).hexdigest()},
        'script': script, 'script_sha256': hashlib.sha256(_encode(script)).hexdigest(),
        'observations': [], 'layer_hashes': {}, 'controls': {},
        'control_ids': {'breakpoints': {}, 'hooks': {}}}
    encoded = _encode(document)
    rows = {'exp-id': {'kind': 'experiment', 'version': 1, 'data': encoded,
                       'sha256': hashlib.sha256(encoded).hexdigest(), 'metadata': '{}'},
            'state-id': {'kind': 'state', 'version': 1, 'data': state_data,
                         'sha256': hashlib.sha256(state_data).hexdigest(),
                         'metadata': json.dumps(state_metadata)}}
    project = _Project(rows)
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._unarchive', lambda _data: (b'qcow', bundle))
    assert experiments.project_document(project, 'exp-id')['checkpoint']['artifact'] == 'state-id'

    rows['state-id']['metadata'] = json.dumps({**state_metadata, 'format': 'entry-only-state'})
    with pytest.raises(ValueError, match='full process checkpoint'):
        experiments.project_document(project, 'exp-id')


def test_project_document_rejects_capture_origin_mismatch(monkeypatch):
    bundle = {'format': 'fdisbull-qemu-dos-process-qcow2-v2', 'source_sha256': 'a' * 64,
              'version': 1, 'version_sha256': 'b' * 64, 'runtime': {'profile': 'test'},
              'process': {'capture_epoch': 'origin:process:1'}}
    state_data = b'full-state'
    metadata = {'format': bundle['format'], 'source_sha256': bundle['source_sha256'],
                'origin_run': 'origin', 'sidecar_sha256': hashlib.sha256(_encode(bundle)).hexdigest()}
    script = {'format': 'fdisbull-script-1', 'backend': 'qemu-dos', 'steps': []}
    document = {'format': experiments.FORMAT, 'version': 1, 'source_sha256': bundle['source_sha256'],
        'version_sha256': bundle['version_sha256'], 'runtime': bundle['runtime'],
        'identity': {'source_sha256': bundle['source_sha256'], 'version_sha256': bundle['version_sha256'],
                     'runtime': bundle['runtime']},
        'origin_run': 'other-run', 'capture_epoch': 'origin:process:1',
        'checkpoint': {'artifact': 'state-id', 'sha256': hashlib.sha256(state_data).hexdigest()},
        'script': script, 'script_sha256': hashlib.sha256(_encode(script)).hexdigest(),
        'observations': [], 'layer_hashes': {}, 'controls': {},
        'control_ids': {'breakpoints': {}, 'hooks': {}}}
    encoded = _encode(document)
    rows = {'exp-id': {'kind': 'experiment', 'version': 1, 'data': encoded,
                       'sha256': hashlib.sha256(encoded).hexdigest(), 'metadata': '{}'},
            'state-id': {'kind': 'state', 'version': 1, 'data': state_data,
                         'sha256': hashlib.sha256(state_data).hexdigest(), 'metadata': json.dumps(metadata)}}
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint._unarchive', lambda _data: (b'qcow', bundle))
    with pytest.raises(ValueError, match='capture origin'):
        experiments.project_document(_Project(rows), 'exp-id')


class _LayerProject:
    def __init__(self, info):
        self.info = info

    def debug_layer_info(self, _identifier):
        return self.info

    def _dos_parse_address(self, _address):
        return 0, None


def _candidate_fixture(binding):
    patch = {'address': '0x2000', 'expected_hex': '00', 'data_hex': '01'}
    info = {'version': 1, 'name': 'candidate', 'kind': 'ram', 'patches': [patch], 'native_binding': binding,
            'sha256': 'layer-hash'}
    document = {'origin_run': 'saved-run', 'capture_epoch': 'saved-run:process:2',
        'layer_stacks': {'selected_task': None, 'task_bindings': {}, 'task_pages': {}},
        'endpoint': {'identity': {'source_mapping': {'live_ranges': []}}}}
    session = SimpleNamespace(project=_LayerProject(info), version={'id': 1})
    session._layer_ram_extent = lambda _address, _length: None
    return session, document


def test_candidate_accepts_legacy_global_binding_and_rebinds_it():
    session, document = _candidate_fixture({'run': 'saved-run', 'epoch': 'saved-run:process:2',
                                            'space': 'physical', 'spans': [[0x2000, 1]]})
    candidate = experiments.QemuExperimentMixin._qemu_experiment_candidate(session, ['layer'], document)
    assert candidate['private'] is False
    rebound_binding = {}
    session.run_id = 'fresh-run'
    session._layer_epoch = lambda: 'fresh-run:process:1'
    def store(_name, _version, clone):
        rebound_binding.update(clone['native_binding'])
        return {'layer': 'clone'}
    session.project._store_debug_layer = store
    rebound = experiments.QemuExperimentMixin._qemu_experiment_rebind_candidate(session, candidate)
    assert rebound['layer_ids'] == ['clone']
    assert rebound_binding['run'] == 'fresh-run'
    assert rebound_binding['epoch'] == 'fresh-run:process:1'
    assert rebound_binding.get('scope') is None


def test_candidate_rejects_native_binding_from_another_origin():
    session, document = _candidate_fixture({'run': 'stale-run', 'epoch': 'saved-run:process:2',
                                            'space': 'physical', 'spans': [[0x2000, 1]]})
    with pytest.raises(ValueError, match='different captured run or epoch'):
        experiments.QemuExperimentMixin._qemu_experiment_candidate(session, ['layer'], document)


def test_comparison_artifact_failure_closes_and_preserves_partial_result():
    result = {'experiment': 'exp-id', 'ok': False, 'baseline_restored': False,
              'baseline': {'ok': True, 'complete': True}}
    class FailingSession:
        closed = False
        def _artifact(self, *_args, **_kwargs):
            raise OSError('storage unavailable')
        def close(self):
            self.closed = True
    session = FailingSession()
    with pytest.raises(OSError, match='storage unavailable') as caught:
        experiments.QemuExperimentMixin._qemu_experiment_publish_comparison(session, result)
    assert session.closed
    assert caught.value.result == result


def test_project_document_detects_modified_experiment_bytes(monkeypatch):
    project = _Project({'broken': {'kind': 'experiment', 'version': 1, 'data': b'{}',
                                  'sha256': '0' * 64, 'metadata': '{}'}})
    with pytest.raises(ValueError, match='hash mismatch'):
        experiments.project_document(project, 'broken')


def test_capacity_reserves_both_script_definitions_before_any_restore(monkeypatch):
    script={'steps':[{'op':'registers'}]}
    session=SimpleNamespace(project=object(),restores=[],
        _qemu_experiment_supported=lambda:None,
        _qemu_experiment_document=lambda _artifact:{'script':script,'layer_hashes':{}},
        _qemu_experiment_candidate=lambda _layers,_doc:{'layer_ids':[]})
    session.restore_experiment=lambda *args,**kwargs:session.restores.append((args,kwargs))
    monkeypatch.setattr(experiments,'_validate_script',lambda _session,recipe:recipe['steps'])
    reserved=[]
    def capacity(_project,needed):
        reserved.append(needed)
        raise ValueError('no capacity')
    monkeypatch.setattr(experiments,'_require_project_capacity',capacity)
    with pytest.raises(ValueError,match='no capacity'):
        experiments.QemuExperimentMixin.compare_experiment.__wrapped__(session,'experiment',layers=[])
    # Two 16 MiB script results, one 16 MiB final report, two 1 MiB scripts.
    assert reserved==[50*1024*1024] and session.restores==[]
