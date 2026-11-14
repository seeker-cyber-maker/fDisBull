import hashlib
import importlib.util
import json
import os
from pathlib import Path
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('production_pipeline', ROOT / 'scripts/ci/production_pipeline.py')
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value, *, root=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + '\n')
    path.chmod(0o644)
    return {'path': str(path.relative_to(root)) if root is not None else path.name,
            'sha256': sha(path.read_bytes()), 'size': path.stat().st_size}


def request_fixture(tmp_path, monkeypatch, *, publish=True):
    root = tmp_path / 'data'
    req_root = root / 'control/production'
    source_parent = root / 'sources'
    output_parent = root / 'results/pipelines'
    input_dir = root / 'inputs'
    for path in (req_root, source_parent, output_parent, input_dir):
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
    archive = input_dir / 'dosbox.git.tar'
    fixture = input_dir / 'oracle.exe'
    archive.write_bytes(b'upstream archive')
    fixture.write_bytes(b'authored win16 fixture')
    archive.chmod(0o600); fixture.chmod(0o600)
    request = {'schema': 'fdisbull-production-release-request-1', 'key': 'release-key-1',
               'source_sha': 'a' * 40, 'version': '0.35.0', 'tag': 'v0.35.0',
               'source_root': str(source_parent / 'source-a'),
               'output_root': str(output_parent / 'run-a'),
               'driver_options': {'dosbox_upstream_archive': str(archive),
                                  'dosbox_upstream_sha256': sha(archive.read_bytes()),
                                  'authored_win16_fixture': str(fixture)},
               'deadline_seconds': 28800, 'publish': publish}
    path = req_root / 'request.json'
    write_json(path, request);path.chmod(0o600)
    monkeypatch.setattr(pipeline, 'REQUEST_ROOT', req_root)
    monkeypatch.setattr(pipeline, 'STATE_ROOT', req_root)
    monkeypatch.setattr(pipeline, 'DATA_ROOT', root)
    monkeypatch.setattr(pipeline, 'SOURCE_ROOT', source_parent)
    monkeypatch.setattr(pipeline, 'OUTPUT_ROOT', output_parent)
    pointer = {'path': str(path), 'sha256': sha(path.read_bytes())}
    return request, pointer, path


def build_qualified_output(output_root, source_sha):
    qroot = output_root / 'qualification'
    dist = qroot / 'dist'
    for name in ('fdisbull-0.35.0-py3-none-any.whl', 'fdisbull_player-0.35.0-py3-none-any.whl',
                 'fdisbull-0.35.0.tar.gz', 'fdisbull-tool-0.35.0.zip'):
        dist.mkdir(parents=True, exist_ok=True)
        (dist / name).write_bytes(('artifact:' + name).encode())
    archive_path = qroot / 'native-evidence/chat/output/fdisbull-chat-offline.zip'
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(b'offline chat archive')
    package = {'schema': 'fdisbull-package-payloads-1', 'source_commit': source_sha,
               'tracked_worktree_dirty': False, 'artifacts': {}}
    kinds = ('core', 'player', 'sdist', 'tool')
    for kind, path in zip(kinds, sorted(dist.iterdir())):
        package['artifacts'][kind] = {'name': path.name, 'sha256': sha(path.read_bytes()),
                                      'size_bytes': path.stat().st_size}
    package_ref = write_json(qroot / 'artifacts/receipts/package-payloads.json', package, root=qroot)
    verifier = {'schema': 'fdisbull-chat-consumer-verification-v1', 'status': 'passed',
                'source_commit': source_sha, 'test_source_commit': source_sha,
                'network_interfaces': ['lo'], 'skipped': 0, 'native_failures': 0,
                'archive_sha256':sha(archive_path.read_bytes()),
                'windows_native_qualification': {'pe32': 'passed', 'win16': 'passed'},
                'extended_windows': {'pe32': {'status': 'passed'}, 'win16': {'status': 'passed'}}}
    verifier_ref = write_json(qroot / 'native-evidence/chat/acceptance.json', verifier, root=qroot)
    archive_ref = {'path': 'native-evidence/chat/output/fdisbull-chat-offline.zip',
                   'sha256': sha(archive_path.read_bytes()), 'size': archive_path.stat().st_size}
    junit_path=qroot/'native-evidence/chat/tests.xml';junit_path.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="consumer"/></testsuite>')
    junit_ref={'path':'native-evidence/chat/tests.xml','sha256':sha(junit_path.read_bytes()),'size':junit_path.stat().st_size}
    receipt_ref = write_json(qroot / 'artifacts/receipts/chat-consumer.json',
                             {'schema':'fdisbull-chat-consumer-job-v1','status':'passed',
                              'source_commit':source_sha,'test_source_commit':source_sha,'source_access':'absent',
                              'junit':junit_ref,'archive': archive_ref, 'verifier': verifier_ref}, root=qroot)
    qualification = {'schema': 'fdisbull-ci-qualification-1', 'status': 'qualified',
                     'source_commit': source_sha, 'package_inventory': package_ref,
                     'chat_consumer': {'receipt': receipt_ref, 'verifier': verifier_ref,
                                       'archive': archive_ref}}
    write_json(qroot / 'qualification.json', qualification)
    return qroot


def private_state(pointer):
    root = pipeline.REQUEST_ROOT / 'pipelines' / pointer['sha256']
    root.parent.mkdir(parents=True, exist_ok=True)
    root.parent.chmod(0o700)
    root.mkdir(mode=0o700)
    return root


def test_inspect_request_binds_root_private_request_and_options(tmp_path, monkeypatch):
    raw, pointer, _ = request_fixture(tmp_path, monkeypatch)
    parsed = pipeline.inspect_request(pointer)
    assert parsed['source_sha'] == raw['source_sha']
    assert parsed['_request_sha256'] == pointer['sha256']
    assert parsed['driver_options']['dosbox_upstream_archive'] == raw['driver_options']['dosbox_upstream_archive']


def test_inspect_request_rejects_hash_mutation_and_unapproved_option(tmp_path, monkeypatch):
    raw, pointer, path = request_fixture(tmp_path, monkeypatch)
    path.write_text(json.dumps({**raw, 'driver_options': {**raw['driver_options'], 'shell': 'touch /tmp/x'}}))
    path.chmod(0o600)
    with pytest.raises(ValueError, match='hash or size'):
        pipeline.inspect_request(pointer)
    pointer['sha256'] = sha(path.read_bytes())
    with pytest.raises(ValueError, match='unsupported driver option'):
        pipeline.inspect_request(pointer)


def test_inspect_request_requires_publication_and_exact_release_identity(tmp_path, monkeypatch):
    _, pointer, _ = request_fixture(tmp_path, monkeypatch, publish=False)
    with pytest.raises(ValueError, match='schema or identity'):
        pipeline.inspect_request(pointer)


def test_release_manifest_binds_five_payloads_and_sha256sums(tmp_path):
    output = tmp_path / 'out'
    output.mkdir(mode=0o700)
    request = {'source_sha': 'a' * 40}
    qroot = build_qualified_output(output, request['source_sha'])
    manifest_path, manifest_hash, manifest = pipeline._release_manifest(request, output)
    assert manifest_path.is_file() and manifest_hash == sha(manifest_path.read_bytes())
    assert len(manifest['assets']) == 6
    checksum = output / 'SHA256SUMS'
    lines = checksum.read_text().splitlines()
    assert len(lines) == 5
    for asset, line in zip(manifest['assets'][:5], lines):
        digest, name = line.split('  ', 1)
        assert (digest, name) == (asset['sha256'], asset['name'])
        assert Path(asset['path']).read_bytes()
    sums_asset = manifest['assets'][5]
    assert sums_asset == {'name': 'SHA256SUMS', 'path': str(checksum),
                          'sha256': sha(checksum.read_bytes()), 'size': checksum.stat().st_size}
    assert manifest['qualification']['root'] == str(qroot)


def test_run_persists_attention_for_unknown_intent_without_relaunch(tmp_path, monkeypatch):
    _, pointer, path = request_fixture(tmp_path, monkeypatch)
    request = pipeline.inspect_request(pointer)
    state = private_state(pointer)
    pipeline._write_once(state / 'intent.json', {'request_sha256': pointer['sha256']})
    monkeypatch.setattr(pipeline, '_source_checkout', lambda *a: pytest.fail('must not launch source work'))
    result = pipeline.run(request, state, guard=lambda: None,
                          health=lambda: {'state': 'healthy'}, publisher=lambda *a: pytest.fail('must not publish'))
    assert result['status'] == 'attention' and result['reason'] == 'unknown-existing-intent'
    assert result['request_sha256'] == pointer['sha256']
    assert pipeline.run(request, state, guard=lambda: None, health=lambda: {}, publisher=lambda *a: None) == result


def test_run_calls_publisher_once_only_after_verified_driver_and_stopped_containers(tmp_path, monkeypatch):
    raw, pointer, _ = request_fixture(tmp_path, monkeypatch)
    request = pipeline.inspect_request(pointer)
    state = private_state(pointer)
    def source_checkout(req, deadline, *, guard, health, state_root):
        source = Path(req['source_root']); source.mkdir()
        return source
    def host_receipt(path):
        pipeline._write_once(path, {'schema': 'test'})
    def drive(argv, *, output, request, state_root, guard, health, deadline, sleeper):
        build_qualified_output(output, request['source_sha'])
        (output / 'run.json').write_text(json.dumps({'source_commit': request['source_sha'],
            'local_run_id': str(uuid.uuid4()), 'execution_origin': 'local-linux'}))
        (output / 'run.json').chmod(0o600)
        return json.loads((output / 'run.json').read_text())['local_run_id']
    calls = []
    def publisher(key, payload):
        calls.append((key, payload))
        manifest = json.loads(Path(payload['manifest_path']).read_text())
        assert len(manifest['assets']) == 6
        return {'status': 'completed', 'source_sha': request['source_sha'], 'tag': 'v0.35.0',
                'release_url': 'https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.35.0'}
    monkeypatch.setattr(pipeline, '_source_checkout', source_checkout)
    monkeypatch.setattr(pipeline, '_host_receipt', host_receipt)
    monkeypatch.setattr(pipeline, '_driver_argv', lambda *a: ['fake-driver'])
    monkeypatch.setattr(pipeline, '_drive', drive)
    monkeypatch.setattr(pipeline, '_stop_owned', lambda *a, **kw: {'checked': 2, 'stopped': 0, 'running_after': 0})
    result = pipeline.run(request, state, guard=lambda: None, health=lambda: {'state': 'healthy'},
                          publisher=publisher)
    assert result['status'] == 'complete'
    assert result['release_url'] == 'https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.35.0'
    assert len(calls) == 1 and calls[0][0] == raw['key']


def test_manifest_contract_matches_actual_publisher_evidence_reader(tmp_path,monkeypatch):
    import importlib.util
    spec=importlib.util.spec_from_file_location('actual_publisher_contract',ROOT/'scripts/ci/production_release.py')
    publisher=importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)
    output=tmp_path/'out';output.mkdir()
    request={'source_sha':'a'*40};build_qualified_output(output,request['source_sha'])
    _,_,manifest=pipeline._release_manifest(request,output)
    monkeypatch.setattr(publisher,'RESULTS',str(tmp_path)+'/')
    publisher.validate_manifest(manifest)
    def fetch(path,size,digest,target,deadline,**kwargs):
        data=Path(path).read_bytes();assert sha(data)==digest
        if size is not None:assert size==len(data)
        target.write_bytes(data)
    monkeypatch.setattr(publisher,'fetch',fetch)
    cache=tmp_path/'cache';cache.mkdir()
    archive,packages,verifier=publisher.evidence(manifest,cache,0)
    assert len(packages)==4 and archive['sha256']==verifier['archive_sha256']


def test_completed_result_can_be_read_after_actual_workspaces_exist(tmp_path,monkeypatch):
    raw,pointer,_=request_fixture(tmp_path,monkeypatch)
    request=pipeline.inspect_request(pointer);state=private_state(pointer)
    Path(raw['source_root']).mkdir();Path(raw['output_root']).mkdir()
    result=pipeline._write_result(state/'result.json',request,'complete',
        release_url='https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.35.0',
        cleanup={'running_after':0})
    monkeypatch.setattr(pipeline,'_source_checkout',lambda *a,**kw:pytest.fail('must not re-clone'))
    assert pipeline.run(request,state,guard=lambda:None,health=lambda:{},publisher=lambda *a:pytest.fail('must not publish'))==result
    assert result['owned_cleanup_verified'] is True


def test_public_readable_driver_metadata_can_be_observed_and_partial_write_is_unknown(tmp_path):
    run=tmp_path/'run.json';run.write_text('{');run.chmod(0o644)
    assert pipeline._read_run_id(tmp_path,'a'*40) is None
    run.write_text(json.dumps({'local_run_id':'12345678-1234-1234-1234-123456789abc','source_commit':'a'*40,'execution_origin':'local-linux'}))
    assert pipeline._read_run_id(tmp_path,'a'*40)=='12345678-1234-1234-1234-123456789abc'
    run.chmod(0o666)
    with pytest.raises(ValueError):pipeline._read_run_id(tmp_path,'a'*40)


def test_full_driver_gets_every_declared_windows_fixture_and_capability(tmp_path):
    options={'retained_windows_fixtures':str(tmp_path/'windows-fixtures')}
    argv=pipeline._driver_argv(tmp_path/'source',tmp_path/'output',tmp_path/'host.json',options)
    assert argv[argv.index('--retained-windows-fixtures')+1]==options['retained_windows_fixtures']
    caps=[argv[i+1] for i,value in enumerate(argv[:-1]) if value=='--require-os-capability']
    assert set(caps)=={'wine64','dos','pe32','win16-guards'}
