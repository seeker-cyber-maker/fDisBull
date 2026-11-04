#!/usr/bin/env python3
"""Validate an explicitly selected original unified build before reuse.

This only binds existing inputs and original evidence; it does not qualify them
for a new source or claim that any current native acceptance has run.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def regular(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Missing or unsafe original unified build evidence')
    return path


def document(path):
    value = json.loads(regular(path).read_text())
    if not isinstance(value, dict):
        raise ValueError('Invalid original unified proof')
    return value


def recipe(source):
    text = (source / 'scripts/ci/native-unified.sh').read_text()
    start = text.index('# QEMU 9.2')
    end = text.index('\ndocker_build_network=()', start)
    kernel = text[text.index('curl --fail --location --retry 3'):text.index('chmod +x "$FDISBULL_DOSBOX"')]
    return kernel + text[start:end]


def validate(export, current_source, image_digest):
    export = Path(export).resolve(strict=True)
    phase = export.parent.parent
    old_source = phase / 'work'
    if export != phase / 'guest-data/exported' or old_source.is_symlink():
        raise ValueError('Expected original unified preparation guest export')
    process = document(phase / 'process.json')
    marker = document(phase / 'completed.json')
    post = document(phase / 'guest-data/source-postcheck.json')
    sha, run, job = (process.get(k) for k in ('source_commit', 'local_run_id', 'local_job_id'))
    try:
        if not re.fullmatch(r'[0-9a-f]{40}', sha) or str(uuid.UUID(run)) != run or str(uuid.UUID(job)) != job:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid original source or job identity') from None
    if (process.get('execution_origin') != 'local-linux' or process.get('job_name') != 'native-unified-prepare'
        or type(process.get('exit_code')) is not int or process['exit_code'] != 0
        or process.get('termination') != 'exited' or process.get('container_state_after_stop') != 'stopped'
        or process.get('image_digest') != image_digest or not re.fullmatch(r'sha256:[0-9a-f]{64}', str(image_digest))
        or process.get('runtime', {}).get('machine') != 'x86_64' or process.get('runtime', {}).get('system') != 'linux'
        or not process.get('runtime', {}).get('python', '').startswith('3.12.')
        or marker.get('local_job_id') != job or marker.get('source_commit') != sha
        or post != {'source_commit': sha, 'expected_source_commit': sha,
                    'tracked_worktree_dirty': False, 'export_success': True}):
        raise ValueError('Original unified preparation did not complete cleanly')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=old_source, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=old_source, text=True)
    if head != sha or dirty.strip():
        raise ValueError('Original frozen source snapshot changed')
    for name in ('experimental/wine/ci/Containerfile', 'experimental/wine/ci/build_runtime.py'):
        if regular(old_source / name).read_bytes() != regular(Path(current_source) / name).read_bytes():
            raise ValueError('Original Wine OS build recipe changed: ' + name)
    if recipe(old_source) != recipe(Path(current_source)):
        raise ValueError('Original QEMU build recipe changed')
    script = old_source / 'scripts/ci/unified-runtime-inputs.py'
    spec = importlib.util.spec_from_file_location('original_unified_verifier', script)
    module = importlib.util.module_from_spec(spec)
    original_path = sys.path[:]
    try:
        sys.path.insert(0, str(script.parent))
        spec.loader.exec_module(module)
        module.verify(export, sha, run, job, source_root=old_source)
    finally:
        sys.path[:] = original_path
    return {'schema': 'fdisbull-unified-base-origin-v1', 'source_commit': sha,
            'local_run_id': run, 'local_job_id': job, 'image_digest': image_digest,
            'process_sha256': digest(phase / 'process.json'),
            'completed_sha256': digest(phase / 'completed.json'),
            'source_postcheck_sha256': digest(phase / 'guest-data/source-postcheck.json'),
            'prepared_inputs_sha256': digest(export / 'native-evidence/pe/prepared-inputs.json')}


def stage(export, current_source, image_digest, destination):
    import shutil
    export = Path(export).resolve(strict=True)
    phase = export.parent.parent
    origin = validate(export, current_source, image_digest)
    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=False)
    files = {
        'process.json': phase / 'process.json',
        'completed.json': phase / 'completed.json',
        'source-postcheck.json': phase / 'guest-data/source-postcheck.json',
        'prepared-inputs.json': export / 'native-evidence/pe/prepared-inputs.json',
        'backend-identity.json': export / 'native-evidence/pe/backend-identity.json',
        'wine-preparation.json': export / 'native-evidence/pe/runtime-preparation.json',
        'wine-packages.txt': export / 'native-evidence/pe/runtime-packages.txt',
        'dos-preparation.json': export / 'native-evidence/pe/dos-runtime-preparation.json',
        'old-native-unified.sh': phase / 'work/scripts/ci/native-unified.sh',
        'old-Containerfile': phase / 'work/experimental/wine/ci/Containerfile',
        'old-build_runtime.py': phase / 'work/experimental/wine/ci/build_runtime.py',
        'qemu': export / '.native/pe/qemu-9.2.4/build/qemu-system-x86_64',
        'kernel': export / '.native/pe/linux-amd64',
        'oracle': export / '.native/pe/oracle.exe',
        'wine-base': export / '.native/pe/runtime.cpio.gz',
    }
    origin['files'] = {}
    for name, source in files.items():
        shutil.copy2(regular(source), dest / name)
        origin['files'][name] = digest(dest / name)
    shutil.copytree(export / 'native-evidence/pe/firmware', dest / 'firmware')
    origin['firmware'] = {p.relative_to(dest).as_posix(): digest(p)
                          for p in sorted((dest / 'firmware').rglob('*')) if p.is_file()}
    host_proof = {'source_commit': origin['source_commit'], 'tracked_worktree_dirty': False,
                  'method': 'host-git-frozen-source-before-staging'}
    (dest / 'host-source-postcheck.json').write_text(json.dumps(host_proof, indent=2) + '\n')
    origin['files']['host-source-postcheck.json'] = digest(dest / 'host-source-postcheck.json')
    (dest / 'origin.json').write_text(json.dumps(origin, indent=2) + '\n')
    verify_reuse(dest, current_source)
    return origin


def verify_reuse(root, current_source_root):
    """Verify the typed staged origin and immutable raw original proofs."""
    root = Path(root)
    if (root / 'native-evidence/pe/reuse/origin.json').is_file():
        root = root / 'native-evidence/pe/reuse'
    origin = document(root / 'origin.json')
    names = {'process.json', 'completed.json', 'source-postcheck.json', 'prepared-inputs.json',
             'backend-identity.json', 'wine-preparation.json', 'dos-preparation.json', 'wine-packages.txt',
             'old-native-unified.sh', 'old-Containerfile', 'old-build_runtime.py',
             'qemu', 'kernel', 'oracle', 'wine-base', 'host-source-postcheck.json'}
    files = origin.get('files')
    if origin.get('schema') != 'fdisbull-unified-base-origin-v1' or not isinstance(files, dict) or set(files) != names:
        raise ValueError('Invalid unified reuse origin')
    if any(digest(regular(root / name)) != files[name] for name in names):
        raise ValueError('Unified reuse original proof or input changed')
    for field, name in (('process_sha256', 'process.json'), ('completed_sha256', 'completed.json'),
                        ('source_postcheck_sha256', 'source-postcheck.json'),
                        ('prepared_inputs_sha256', 'prepared-inputs.json')):
        if origin.get(field) != files[name]:
            raise ValueError('Unified reuse top-level proof identity mismatch')
    firmware = origin.get('firmware')
    observed = {p.relative_to(root).as_posix(): digest(regular(p))
                for p in sorted((root / 'firmware').rglob('*')) if p.is_file()}
    if not isinstance(firmware, dict) or len(firmware) != 171 or firmware != observed:
        raise ValueError('Unified reuse firmware changed')
    old_script = (root / 'old-native-unified.sh').read_text()
    current_script = (Path(current_source_root) / 'scripts/ci/native-unified.sh').read_text()
    def part(text):
        return (text[text.index('curl --fail --location --retry 3'):text.index('chmod +x "$FDISBULL_DOSBOX"')]
                + text[text.index('# QEMU 9.2'):text.index('\ndocker_build_network=()')])
    if (part(old_script) != part(current_script)
        or (root / 'old-Containerfile').read_bytes() != (Path(current_source_root) / 'experimental/wine/ci/Containerfile').read_bytes()
        or (root / 'old-build_runtime.py').read_bytes() != (Path(current_source_root) / 'experimental/wine/ci/build_runtime.py').read_bytes()):
        raise ValueError('Unified reuse recipe changed')
    process, marker = document(root / 'process.json'), document(root / 'completed.json')
    post, manifest = document(root / 'source-postcheck.json'), document(root / 'prepared-inputs.json')
    sha, run, job = origin.get('source_commit'), origin.get('local_run_id'), origin.get('local_job_id')
    try:
        if not re.fullmatch(r'[0-9a-f]{40}', sha) or str(uuid.UUID(run)) != run or str(uuid.UUID(job)) != job:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid unified reuse original identities') from None
    if (document(root / 'host-source-postcheck.json') != {'source_commit': sha, 'tracked_worktree_dirty': False, 'method': 'host-git-frozen-source-before-staging'}
        or process.get('source_commit') != sha or process.get('local_run_id') != run or process.get('local_job_id') != job
        or process.get('image_digest') != origin.get('image_digest')
        or not re.fullmatch(r'sha256:[0-9a-f]{64}', str(origin.get('image_digest')))
        or process.get('runtime', {}).get('machine') != 'x86_64'
        or process.get('runtime', {}).get('system') != 'linux'
        or not process.get('runtime', {}).get('python', '').startswith('3.12.')
        or process.get('job_name') != 'native-unified-prepare'
        or process.get('execution_origin') != 'local-linux' or type(process.get('exit_code')) is not int
        or process['exit_code'] != 0 or process.get('termination') != 'exited' or process.get('container_state_after_stop') != 'stopped'
        or marker.get('source_commit') != sha or marker.get('local_job_id') != job
        or post != {'source_commit': sha, 'expected_source_commit': sha, 'tracked_worktree_dirty': False, 'export_success': True}
        or manifest.get('source_commit') != sha or manifest.get('local_run_id') != run or manifest.get('build_job_id') != job):
        raise ValueError('Unified reuse original provenance mismatch')
    keys = {'FDISBULL_PE_QEMU', 'FDISBULL_PE_KERNEL', 'FDISBULL_PE_INITRAMFS',
            'FDISBULL_PE_FIXTURE', 'FDISBULL_DOSBOX', 'FDISBULL_DOS_INITRAMFS'}
    inputs = manifest.get('inputs')
    if (manifest.get('schema') != 'fdisbull-unified-runtime-inputs-1'
        or not isinstance(inputs, dict) or set(inputs) != keys
        or not isinstance(manifest.get('resource_receipts'), dict)
        or set(manifest['resource_receipts']) != {'wine', 'dos'}):
        raise ValueError('Incomplete original unified input manifest')
    identity = document(root / 'backend-identity.json')
    old_inputs = identity.get('inputs')
    if not isinstance(old_inputs, dict) or set(old_inputs) != keys:
        raise ValueError('Incomplete original unified backend inputs')
    for key in keys:
        item, old_item = inputs[key], old_inputs[key]
        if (not isinstance(item, dict) or not isinstance(old_item, dict)
            or not re.fullmatch(r'[0-9a-f]{64}', str(item.get('sha256')))
            or type(item.get('size')) is not int or item['size'] < 0
            or (item['sha256'], item['size']) != (old_item.get('sha256'), old_item.get('size'))):
            raise ValueError('Original unified backend input identity mismatch')
    identity_ref = manifest.get('backend_identity')
    if (identity.get('source_commit') != sha or not isinstance(identity_ref, dict)
        or identity_ref.get('sha256') != files['backend-identity.json']
        or identity_ref.get('size') != (root / 'backend-identity.json').stat().st_size):
        raise ValueError('Unified reuse original backend identity mismatch')
    for kind, name in (('wine', 'wine-preparation.json'), ('dos', 'dos-preparation.json')):
        reference = manifest.get('resource_receipts', {}).get(kind)
        if (not isinstance(reference, dict) or reference.get('sha256') != files[name]
            or reference.get('size') != (root / name).stat().st_size):
            raise ValueError('Unified reuse original resource receipt mismatch')
    original_firmware = manifest.get('firmware')
    if not isinstance(original_firmware, list) or len(original_firmware) != 171 or {item.get('path', '').replace('native-evidence/pe/firmware/', 'firmware/', 1): item.get('sha256') for item in original_firmware if isinstance(item, dict)} != firmware:
        raise ValueError('Unified reuse firmware differs from original manifest')
    for key, name in (('FDISBULL_PE_QEMU', 'qemu'), ('FDISBULL_PE_KERNEL', 'kernel'),
                      ('FDISBULL_PE_FIXTURE', 'oracle'), ('FDISBULL_PE_INITRAMFS', 'wine-base')):
        reference = manifest.get('inputs', {}).get(key, {})
        old_identity = identity.get('inputs', {}).get(key, {})
        actual = (files[name], (root / name).stat().st_size)
        if (reference.get('sha256'), reference.get('size')) != actual or (old_identity.get('sha256'), old_identity.get('size')) != actual:
            raise ValueError('Unified reuse base differs from original manifest')
    return origin
