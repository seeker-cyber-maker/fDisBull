"""Boat executor contracts without Docker, a VM, or remote calls."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_offline_windows_oracles import sample_ne

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('boat_linux', ROOT / 'scripts/ci/boat-linux.py')
boat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boat)


def test_docker_index_and_platform_are_distinct_and_amd64_selected():
    index, amd = 'sha256:' + 'a'*64, 'sha256:' + 'b'*64
    manifest = {'manifests': [{'digest': amd, 'platform': {'os': 'linux', 'architecture': 'amd64'}},
                              {'digest': 'sha256:'+'c'*64, 'platform': {'os': 'linux', 'architecture': 'arm64'}}]}
    assert boat.docker_image_identity(index, manifest, {'Os': 'linux', 'Architecture': 'amd64'}) == {
        'image_index_digest': index, 'image_digest': amd}
    with pytest.raises(ValueError, match='Linux AMD64'):
        boat.docker_image_identity(index, manifest, {'Os': 'linux', 'Architecture': 'arm64'})
    manifest['manifests'].append(manifest['manifests'][0])
    with pytest.raises(ValueError, match='one Linux AMD64'):
        boat.docker_image_identity(index, manifest, {'Os': 'linux', 'Architecture': 'amd64'})


def test_consumer_has_only_input_and_results_no_host_or_source_runtime(tmp_path):
    image = {'image_reference': 'example@sha256:'+'a'*64}
    cmd = boat.docker_command('chat-consumer', 'job', image, tmp_path/'work', tmp_path/'guest', tmp_path/'input', {'FDISBULL_LOCAL_RUN_ID':'fixture-run','CI_COMMIT_SHA':'a'*40}, consumer_kit=tmp_path/'kit')
    assert cmd[:2] == ['docker', 'run']
    assert '--network' in cmd and cmd[cmd.index('--network')+1] == 'none'
    assert 'SYS_ADMIN' not in cmd and '--cap-add' not in cmd
    assert any('target=/fdisbull-chat-offline,readonly' in value for value in cmd)
    assert not any('/source' in value or '/work' in value or 'docker.sock' in value for value in cmd)
    assert any('target=/input,readonly' in value for value in cmd)
    assert any('target=/run-data' in value for value in cmd)
    assert 'bash /input/bootstrap.sh /input/archive.zip /run-data --mounted-kit' in cmd


def test_worker_identity_must_bind_current_host_boot(tmp_path, monkeypatch):
    path = tmp_path / 'worker.json'
    receipt = {'schema':'fdisbull-boat-worker-v1','execution_origin':'boat-linux','boat_sandbox_id':'bx_5asjcc78',
               'type':'default','architecture':'x86_64','host_boot_id':'a0ae3230-94b0-46fd-9b4b-8c40ed8f0e2f',
               'observed_at':'2026-11-04T00:00:00Z'}
    path.write_text(json.dumps(receipt))
    monkeypatch.setattr(boat.platform, 'system', lambda:'Linux')
    monkeypatch.setattr(boat.platform, 'machine', lambda:'x86_64')
    original = Path.read_text
    monkeypatch.setattr(Path, 'read_text', lambda self, *a, **k: receipt['host_boot_id'] if str(self) == '/proc/sys/kernel/random/boot_id' else original(self,*a,**k))
    assert boat.read_worker(path) == receipt
    receipt['host_boot_id'] = 'b0ae3230-94b0-46fd-9b4b-8c40ed8f0e2f'
    path.write_text(json.dumps(receipt))
    monkeypatch.setattr(Path, 'read_text', lambda self, *a, **k: 'a0ae3230-94b0-46fd-9b4b-8c40ed8f0e2f' if str(self) == '/proc/sys/kernel/random/boot_id' else original(self,*a,**k))
    with pytest.raises(ValueError, match='boot identity differs'):
        boat.read_worker(path)


def test_local_host_receipt_binds_boot_hostname_and_platform(tmp_path, monkeypatch):
    boot = 'a0ae3230-94b0-46fd-9b4b-8c40ed8f0e2f'
    receipt = {'schema': 'fdisbull-local-docker-host-v1', 'execution_origin': 'local-linux',
               'architecture': 'x86_64', 'host_boot_id': boot, 'host_name': 'actual-host',
               'observed_at': '2026-11-14T00:00:00Z'}
    path = tmp_path / 'host.json'; path.write_text(json.dumps(receipt))
    monkeypatch.setattr(boat.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(boat.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(boat.platform, 'node', lambda: 'actual-host')
    original = Path.read_text
    monkeypatch.setattr(Path, 'read_text', lambda self, *a, **kw: boot if str(self) == '/proc/sys/kernel/random/boot_id' else original(self, *a, **kw))
    assert boat.read_local_host(path) == receipt
    receipt['host_name'] = 'other-host'; path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='host identity'):
        boat.read_local_host(path)
    receipt['host_name'] = 'actual-host'; receipt['host_boot_id'] = 'b0ae3230-94b0-46fd-9b4b-8c40ed8f0e2f'
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='boot identity differs'):
        boat.read_local_host(path)


def test_authored_fixture_is_source_profiled_hash_checked_and_staged(tmp_path):
    fixture = tmp_path / 'fixture.exe'; fixture.write_bytes(sample_ne())
    expected = boat.authored_fixture(ROOT, fixture)
    env = {'FDISBULL_LOCAL_RUN_ID':'fixture-run','CI_COMMIT_SHA':'a'*40}
    work = tmp_path / 'work'; work.mkdir()
    boat.stage_authored_fixture(ROOT, fixture, expected, work, env)
    assert env['FDISBULL_NE_AUTHORED_FIXTURE'] == '/work/.native/authored-win16/ORACLE.EXE'
    assert (work / '.native/authored-win16/ORACLE.EXE').read_bytes() == fixture.read_bytes()
    command = boat.docker_command('chat-prepare', 'job', {'image_reference': 'example'}, work,
                                  tmp_path / 'guest', tmp_path / 'input', env)
    assert 'FDISBULL_NE_AUTHORED_FIXTURE=/work/.native/authored-win16/ORACLE.EXE' in command
    fixture.write_bytes(sample_ne() + b'changed')
    with pytest.raises(ValueError, match='changed during staging'):
        boat.stage_authored_fixture(ROOT, fixture, expected, tmp_path / 'other', {})


def test_full_profile_rejects_missing_authored_fixture_before_work(tmp_path, monkeypatch):
    monkeypatch.setattr(boat, 'source_identity', lambda source: ('a' * 40, 'branch'))
    monkeypatch.setattr(boat, 'read_local_host', lambda path: {})
    args = SimpleNamespace(source=tmp_path, local_host=True, worker_receipt=tmp_path/'host.json',
                           authored_win16_fixture=None, windows_acceptance='pe64-pe32-win16', profile='all')
    with pytest.raises(ValueError, match='Authored Win16 fixture required'):
        boat.execute(args)


def test_storage_observation_allows_low_free_space_and_checks_destination(tmp_path, monkeypatch):
    root = tmp_path/'docker'
    root.mkdir()
    monkeypatch.setattr(boat, 'capture', lambda *a, **kw: str(root))
    monkeypatch.setattr(boat.shutil, 'disk_usage', lambda p: SimpleNamespace(free=1))
    result = boat.observe_destinations(tmp_path, 8_000_000_000, 0)
    assert result['output']['free_bytes'] == 1
    assert result['output']['reserve_enforced'] is False
    link = tmp_path/'link'
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match='destination unavailable'):
        boat.observe_destinations(link, 0, 0)


def test_guest_environment_has_both_boat_provenance_fields():
    ref = {'path':'artifacts/receipts/boat-worker.json','sha256':'a'*64,'size':123}
    env = boat.job_environment('ordinary','a'*40,'run','job', origin='boat-linux',
                               boat_sandbox_id='bx_5asjcc78', boat_worker_receipt=ref)
    assert env['FDISBULL_EXECUTION_ORIGIN'] == 'boat-linux'
    assert env['FDISBULL_BOAT_SANDBOX_ID'] == 'bx_5asjcc78'
    assert json.loads(env['FDISBULL_BOAT_WORKER_RECEIPT']) == ref
    local = boat.job_environment('ordinary', 'a'*40, 'run', 'job', origin='local-linux')
    assert local['FDISBULL_EXECUTION_ORIGIN'] == 'local-linux'
    assert not any(key.startswith('FDISBULL_BOAT_') for key in local)


def test_actual_docker_hub_familiar_image_inspect_and_platform_pin(tmp_path, monkeypatch):
    index = 'sha256:6c6b3c2deae72b980c4323738be824884c9a2e17588c93db82612f8a3072be88'
    child = 'sha256:0a0704ac83aa7b896a68b710c24f9502bbae87d32e6c7ef6148ce6a60ce05260'
    initial = [{'Id': index, 'RepoDigests': ['python@' + index], 'Os': 'linux', 'Architecture': 'amd64',
                'Descriptor': {'mediaType': 'application/vnd.oci.image.index.v1+json', 'digest': index}}]
    target = [{'Id': child, 'RepoDigests': ['python@' + child], 'Os': 'linux', 'Architecture': 'amd64',
               'Descriptor': {'mediaType': 'application/vnd.oci.image.manifest.v1+json', 'digest': child}}]
    manifest = {'manifests': [{'digest': child, 'platform': {'os': 'linux', 'architecture': 'amd64'}}]}
    commands = []
    def capture(command, **kwargs):
        commands.append(command)
        if 'imagetools' in command: return json.dumps(manifest)
        return json.dumps(target if command[-1].endswith(child) else initial)
    monkeypatch.setattr(boat, 'capture', capture)
    monkeypatch.setattr(boat.subprocess, 'run', lambda command, **kwargs: commands.append(command))
    result = boat.pull_image('docker.io/library/python:3.13.5-bookworm', tmp_path/'pull.log')
    assert result == {'image_index_digest': index, 'image_digest': child,
                      'image_reference': 'docker.io/library/python@' + index}
    assert any(command[-1] == 'docker.io/library/python@' + child for command in commands)
    target[0]['Descriptor']['digest'] = 'sha256:' + 'c'*64
    target[0]['RepoDigests'] = ['python@' + index]
    with pytest.raises(ValueError, match='platform descriptor'):
        boat.pull_image('docker.io/library/python:3.13.5-bookworm', tmp_path/'second.log')


def test_docker_repo_normalization_does_not_alias_external_registries():
    assert boat.normalize_repository('python') == boat.normalize_repository('docker.io/library/python')
    assert boat.normalize_repository('index.docker.io/library/python') == boat.normalize_repository('python')
    assert boat.normalize_repository('registry.example/library/python') != boat.normalize_repository('python')


@pytest.mark.parametrize('name,kind', [('../escape', 'file'), ('fdisbull-chat-offline/../escape','file'),
                                      ('fdisbull-chat-offline/link','link'), ('fdisbull-chat-offline/a','duplicate')])
def test_extract_rejects_unsafe_zip_members(tmp_path, name, kind):
    import hashlib
    import stat
    import zipfile
    archive = tmp_path / 'archive.zip'
    with zipfile.ZipFile(archive, 'w') as zipped:
        if kind == 'link':
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zipped.writestr(info, 'outside')
        else:
            zipped.writestr(name, 'fixture')
            if kind == 'duplicate':
                with pytest.warns(UserWarning):
                    zipped.writestr(name, 'again')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        boat.extract_consumer_kit(archive, tmp_path/'kit', digest)
    assert not (tmp_path/'escape').exists()


def test_extract_preserves_content_and_rejects_wrong_archive_hash(tmp_path):
    import hashlib
    import zipfile
    archive = tmp_path/'archive.zip'
    with zipfile.ZipFile(archive, 'w') as zipped:
        zipped.writestr('fdisbull-chat-offline/tools/verify.py', 'fixture')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    boat.extract_consumer_kit(archive, tmp_path/'kit', digest)
    assert (tmp_path/'kit/tools/verify.py').read_text() == 'fixture'
    with pytest.raises(ValueError, match='identity mismatch'):
        boat.extract_consumer_kit(archive, tmp_path/'other', '0'*64)
    assert not (tmp_path/'other').exists()


def test_large_worker_class_accepted_and_unknown_rejected(tmp_path, monkeypatch):
    receipt = {'schema':'fdisbull-boat-worker-v1','execution_origin':'boat-linux','boat_sandbox_id':'bx_5asjcc78',
               'type':'large','architecture':'x86_64','host_boot_id':'a0ae3230-94b0-46fd-9b4b-8c40ed8f0e2f',
               'observed_at':'2026-11-04T00:00:00Z'}
    path = tmp_path/'worker.json'; path.write_text(json.dumps(receipt))
    monkeypatch.setattr(boat.platform, 'system', lambda:'Linux')
    monkeypatch.setattr(boat.platform, 'machine', lambda:'x86_64')
    original = Path.read_text
    monkeypatch.setattr(Path, 'read_text', lambda self,*a,**k: receipt['host_boot_id'] if str(self) == '/proc/sys/kernel/random/boot_id' else original(self,*a,**k))
    assert boat.read_worker(path)['type'] == 'large'
    receipt['type'] = 'unknown'; path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='Invalid Boat worker receipt'):
        boat.read_worker(path)


def test_retained_preparation_mounts_are_read_only_without_docker_or_host_network(tmp_path):
    image = {'image_reference': 'example@sha256:' + 'a' * 64}
    mounts = [(tmp_path / 'base', '/runtime-base'), (tmp_path / 'os', '/runtime-os-base')]
    cmd = boat.docker_command('unified-prepare', 'job', image, tmp_path / 'work',
                              tmp_path / 'guest', tmp_path / 'input', {'FDISBULL_LOCAL_RUN_ID':'fixture-run','CI_COMMIT_SHA':'a'*40}, mounts)
    assert all(any(f'source={source},target={target},readonly' in value for value in cmd)
               for source, target in mounts)
    assert not any('docker.sock' in value for value in cmd)
    assert '--network' not in cmd


def test_chat_profiles_have_default_allocation_bounds():
    from types import SimpleNamespace
    driver = boat
    for profile in ('chat-prepare', 'chat-consumer'):
        assert driver.expected_bytes(SimpleNamespace(expected_bytes=None), profile) == 32_000_000_000
        assert driver.expected_bytes(SimpleNamespace(expected_bytes=9_000_000_000), profile) == 9_000_000_000
