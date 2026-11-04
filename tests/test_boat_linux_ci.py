"""Boat executor contracts without Docker, a VM, or remote calls."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

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
    cmd = boat.docker_command('chat-consumer', 'job', image, tmp_path/'work', tmp_path/'guest', tmp_path/'input', {}, consumer_kit=tmp_path/'kit')
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


def test_admission_preserves_minimum_and_checks_distinct_stores(tmp_path, monkeypatch):
    root = tmp_path/'docker'
    root.mkdir()
    monkeypatch.setattr(boat, 'capture', lambda *a, **kw: str(root))
    monkeypatch.setattr(boat.shutil, 'disk_usage', lambda p: SimpleNamespace(free=25_000_000_000))
    with pytest.raises(ValueError, match='Storage admission rejected'):
        boat.admit_destinations(tmp_path, 8_000_000_000, 20_000_000_000)


def test_guest_environment_has_both_boat_provenance_fields():
    ref = {'path':'artifacts/receipts/boat-worker.json','sha256':'a'*64,'size':123}
    env = boat.job_environment('ordinary','a'*40,'run','job', origin='boat-linux',
                               boat_sandbox_id='bx_5asjcc78', boat_worker_receipt=ref)
    assert env['FDISBULL_EXECUTION_ORIGIN'] == 'boat-linux'
    assert env['FDISBULL_BOAT_SANDBOX_ID'] == 'bx_5asjcc78'
    assert json.loads(env['FDISBULL_BOAT_WORKER_RECEIPT']) == ref


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
