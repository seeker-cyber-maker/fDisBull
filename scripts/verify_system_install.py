#!/usr/bin/env python3
"""Version-neutral staged and active fDisBull payload verification."""
from __future__ import annotations
import argparse
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

HEX = re.compile(r'[a-f0-9]{64}\Z')
SHA = re.compile(r'[a-f0-9]{40}\Z')
REPO = 'https://github.com/seeker-cyber-maker/fDisBull'
CDN = 'https://release.brewsterjennings.ca/'
NATIVE_PROFILES = {'dosbox-stable', 'dosbox-layers', 'qemu-machine', 'wine-pe64', 'wine-pe32', 'win16'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 16 * 1024 * 1024,
            'unsafe or oversized evidence')
    value = json.loads(path.read_bytes())
    require(isinstance(value, dict), 'evidence object required')
    return value


def relative(root, value):
    require(isinstance(value, str) and value and '\\' not in value, 'relative path required')
    name = PurePosixPath(value)
    require(not name.is_absolute() and str(name) == value and '..' not in name.parts
            and '.' not in name.parts, 'unsafe payload path')
    path = root / value
    require(not any(p.is_symlink() for p in (path, *path.parents) if p != root.parent),
            'payload symlink refused')
    require(path.resolve().is_relative_to(root.resolve()), 'payload escaped prefix')
    return path


def checked_ref(root, ref):
    require(isinstance(ref, dict) and isinstance(ref.get('path'), str)
            and HEX.fullmatch(str(ref.get('sha256'))) is not None, 'invalid payload reference')
    path = relative(root, ref['path'])
    require(path.is_file() and digest(path) == ref['sha256'], 'payload hash mismatch: ' + ref['path'])
    if 'size' in ref:
        require(type(ref['size']) is int and path.stat().st_size == ref['size'], 'payload size mismatch')
    return path


def _command(command, *, native=False):
    require(isinstance(command, dict) and type(command.get('returncode')) is int
            and command['returncode'] == 0, 'unsuccessful qualification command')
    argv = command.get('argv')
    require(isinstance(argv, list) and argv and all(isinstance(x, str) and x and '\x00' not in x for x in argv),
            'qualification argv missing')
    if native:
        require(type(command.get('native_cases')) is int and command['native_cases'] > 0,
                'native command has no executed cases')
        for name in ('stdout', 'stderr'):
            ref = command.get(name)
            require(isinstance(ref, dict) and isinstance(ref.get('path'), str)
                    and HEX.fullmatch(str(ref.get('sha256'))) is not None,
                    'native command output identity missing')


def validate_proofs(documents, version, source_commit, backend_hashes, resource_hashes=None):
    require(isinstance(version, str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version)
            and SHA.fullmatch(str(source_commit)),
            'installation version/source identity invalid')
    require(isinstance(documents, dict) and set(documents) == {'ci', 'native', 'release', 'delivery'},
            'all installation proofs required')
    ci, native, release, delivery = (documents[x] for x in ('ci', 'native', 'release', 'delivery'))
    require(ci.get('schema') == 'fdisbull-ci-qualification-1' and ci.get('status') == 'qualified'
            and ci.get('source_commit') == source_commit, 'CI qualification identity mismatch')
    require(isinstance(ci.get('package_inventory'), dict)
            and HEX.fullmatch(str(ci['package_inventory'].get('sha256'))), 'CI package inventory absent')
    require(release.get('schema') == 'fdisbull-production-release-result-1'
            and release.get('status') == 'complete' and release.get('source_sha') == source_commit
            and release.get('tag') == 'v' + version
            and release.get('release_url') == REPO + '/releases/tag/v' + version,
            'published release identity mismatch')
    require(delivery.get('schema') == 'fdisbull-cdn-delivery-1' and delivery.get('status') == 'passed'
            and delivery.get('source_sha') == source_commit
            and HEX.fullmatch(str(delivery.get('sha256')))
            and delivery.get('full_sha256') == delivery['sha256'] == delivery.get('resume_sha256')
            and type(delivery.get('size')) is int and delivery['size'] > 0,
            'complete download and resume proof required')
    pattern = re.escape(CDN + 'ci-' + version + '/') + r'transfer-[a-f0-9]{32}-fdisbull-' + re.escape(version) + '-' + source_commit + r'-chat-offline\.zip'
    require(isinstance(delivery.get('url'), str) and re.fullmatch(pattern, delivery['url'])
            and release.get('download_url') == delivery['url'], 'delivery URL identity mismatch')
    require(native.get('schema') == 'fdisbull-macos-native-qualification-1'
            and native.get('status') == 'passed' and native.get('source_commit') == source_commit
            and native.get('version') == version and native.get('platform') == 'darwin'
            and native.get('architecture') == 'arm64', 'Mac native qualification identity mismatch')
    require(isinstance(backend_hashes, dict) and backend_hashes
            and all(HEX.fullmatch(str(x)) for x in backend_hashes.values())
            and native.get('backends') == backend_hashes, 'native backend hashes mismatch')
    commands = native.get('commands')
    require(isinstance(commands, list) and commands, 'native commands missing')
    covered = set()
    for command in commands:
        _command(command, native=True)
        profiles = command.get('profiles')
        require(isinstance(profiles, list) and profiles and all(isinstance(x, str) for x in profiles)
                and len(profiles) == len(set(profiles)) and set(profiles) <= NATIVE_PROFILES
                and command['native_cases'] >= len(profiles), 'native profile evidence invalid')
        covered.update(profiles)
    require(covered == NATIVE_PROFILES, 'required Mac native profiles missing')
    if resource_hashes is not None:
        require(isinstance(resource_hashes, dict) and resource_hashes
                and native.get('resources') == resource_hashes, 'native runtime resource hashes mismatch')
    builds = native.get('build_receipts')
    require(isinstance(builds, dict) and set(builds) == set(backend_hashes), 'backend build provenance missing')
    for name, build in builds.items():
        require(isinstance(build, dict) and build.get('artifact_sha256') == backend_hashes[name]
                and HEX.fullmatch(str(build.get('upstream_sha256')))
                and (build.get('patch_sha256') is None or HEX.fullmatch(str(build['patch_sha256']))),
                'backend build/source identity mismatch')
        if 'dosbox' in name.lower():
            require(HEX.fullmatch(str(build.get('patch_sha256'))), 'DOSBox patch provenance missing')
        require(isinstance(build.get('commands'), list) and build['commands'], 'backend build commands missing')
        for command in build['commands']:
            _command(command)
    return documents


def _installed_wheel(prefix, artifact, distribution):
    wheel = checked_ref(prefix, artifact)
    installed = importlib.metadata.distribution(distribution)
    location = Path(installed.locate_file('')).resolve()
    require(location.is_relative_to(prefix / 'venv'), 'installed distribution outside candidate')
    compared = 0
    with zipfile.ZipFile(wheel) as archive:
        for info in archive.infolist():
            if info.is_dir() or info.filename.endswith('.dist-info/RECORD'):
                continue
            require('.data/' not in info.filename, 'unsupported wheel data layout')
            path = relative(location, info.filename)
            require(path.is_file() and path.read_bytes() == archive.read(info),
                    'installed wheel member mismatch: ' + info.filename)
            compared += 1
    require(compared > 0, 'empty installed wheel')
    return compared


def verify_prefix(prefix, manifest_path):
    prefix = Path(prefix).absolute()
    require(prefix.is_dir() and not any(x.is_symlink() for x in (prefix, *prefix.parents)), 'unsafe prefix')
    manifest_path = Path(manifest_path)
    require(manifest_path == prefix / 'share/install-manifest.json', 'unexpected manifest path')
    manifest = read(manifest_path)
    require(manifest.get('schema') == 'fdisbull-system-install-manifest-1', 'install manifest schema mismatch')
    version, source_commit = manifest.get('version'), manifest.get('source_commit')
    files = manifest.get('files')
    require(isinstance(files, dict) and files, 'payload inventory missing')
    for name, ref in files.items():
        require(isinstance(ref, dict) and set(ref) == {'size', 'sha256'}, 'payload inventory invalid')
        checked_ref(prefix, {'path': name, **ref})
    payload = read(prefix / 'PAYLOAD.json')
    require(payload.get('schema') == 'fdisbull-system-payload-1' and payload.get('files') == files,
            'payload manifest differs from installation inventory')
    runtime = read(prefix / 'RUNTIME.json')
    receipt = read(prefix / 'INSTALLATION.json')
    require(runtime.get('version') == receipt.get('version') == version
            and runtime.get('source_commit') == receipt.get('source_commit') == source_commit,
            'runtime/installation identities disagree')
    proofs = manifest.get('proofs')
    require(isinstance(proofs, dict) and set(proofs) == {'ci', 'native', 'release', 'delivery'}, 'proof references missing')
    documents = {name: read(checked_ref(prefix, ref)) for name, ref in proofs.items()}
    backends = manifest.get('backends')
    require(isinstance(backends, dict) and backends, 'backend references missing')
    for ref in backends.values():
        checked_ref(prefix, ref)
    validate_proofs(documents, version, source_commit, {k: v['sha256'] for k, v in backends.items()},
                    {name: ref['sha256'] for name, ref in files.items() if name.startswith('resources/')})
    inventory_path = prefix / 'share/proofs/ci-package-inventory.json'
    require(digest(inventory_path) == documents['ci']['package_inventory']['sha256'],
            'staged CI package inventory hash mismatch')
    inventory = read(inventory_path)
    require(inventory.get('schema') == 'fdisbull-package-payloads-1'
            and inventory.get('source_commit') == source_commit and inventory.get('tracked_worktree_dirty') is False,
            'staged CI package inventory identity mismatch')
    delivery_ref = documents['release'].get('delivery_receipt', {})
    require(delivery_ref.get('sha256') == proofs['delivery']['sha256'], 'release delivery receipt binding mismatch')
    for command in documents['native']['commands']:
        for stream in ('stdout', 'stderr'):
            checked_ref(prefix, command[stream])
    require(Path(sys.prefix).resolve() == (prefix / 'venv').resolve(), 'candidate venv interpreter required')
    artifacts = manifest.get('artifacts')
    require(isinstance(artifacts, dict) and set(artifacts) == {'core', 'player', 'sdist', 'tool'}, 'four release artifacts required')
    for ref in artifacts.values():
        checked_ref(prefix, ref)
    for role, ref in artifacts.items():
        artifact = checked_ref(prefix, ref)
        row = inventory.get('artifacts', {}).get(role, {})
        require((row.get('name'), row.get('size_bytes'), row.get('sha256'))
                == (artifact.name, artifact.stat().st_size, ref['sha256']), 'staged CI artifact mismatch')
    compared = {}
    for package, module, role in [('fdisbull', 'fdisbull', 'core'), ('fdisbull-player', 'fdisbull_player', 'player')]:
        require(importlib.metadata.version(package) == version, 'installed package version mismatch')
        loaded = importlib.import_module(module)
        require(Path(loaded.__file__).resolve().is_relative_to(prefix / 'venv'), 'import outside candidate')
        compared[role] = _installed_wheel(prefix, artifacts[role], package)
    base = Path(manifest.get('base', ''))
    require(base.is_absolute() and prefix.parent == base / 'releases', 'installation base mismatch')
    current = base / 'current'
    active = current.is_symlink() and current.resolve() == prefix
    return {'status': 'passed', 'version': version, 'source_commit': source_commit,
            'active_default': active, 'files_verified': len(files), 'payload_entries': len(files),
            'wheel_members_verified': compared, 'wheel_resources': compared}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', nargs='?', choices=['verify'], default='verify')
    parser.add_argument('--prefix', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_prefix(args.prefix, args.manifest or args.prefix / 'share/install-manifest.json')
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'error': str(error)}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
