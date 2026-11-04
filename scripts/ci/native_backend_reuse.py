"""Fail-closed validation for an explicitly selected original backend build."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import uuid

UPSTREAM = '029bd65c5dcc7cdc7f2e14e35278620d9707d969'
FLAGS = ['--enable-sdl2', '--enable-debug=heavy', '--enable-dosbox_agent',
         '--disable-avcodec', '--disable-libslirp', '--disable-libfluidsynth']
PROFILES = {'stable': 'experimental/dosbox-x', 'layers': 'experimental/dosbox-x/layers'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()



def boat_provenance(directory, prior, source_sha):
    names = ('build-boat-worker.json', 'build-boat-run.json', 'build-source-postcheck.json')
    files = [Path(directory) / name for name in names]
    if any(p.is_symlink() or not p.is_file() for p in files):
        raise ValueError('Missing original Boat build proof')
    worker, run, post = (json.loads(p.read_text()) for p in files)
    sandbox, run_id = prior.get('boat_sandbox_id'), prior.get('local_run_id')
    try:
        if str(uuid.UUID(run_id)) != run_id or str(uuid.UUID(prior.get('local_job_id'))) != prior['local_job_id']:
            raise ValueError
        if str(uuid.UUID(worker.get('host_boot_id'))) != worker['host_boot_id']:
            raise ValueError
    except (ValueError, TypeError, AttributeError, KeyError):
        raise ValueError('Invalid original Boat build identity') from None
    try:
        observed = datetime.datetime.fromisoformat(worker['observed_at'].replace('Z', '+00:00'))
        if observed.utcoffset() is None:
            raise ValueError
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ValueError('Invalid original Boat worker observation time') from None
    ref = {'path': 'artifacts/receipts/boat-worker.json', 'sha256': digest(files[0]), 'size': files[0].stat().st_size}
    if (not isinstance(sandbox, str) or not re.fullmatch(r'bx_[a-z0-9]+', sandbox)
        or prior.get('boat_worker_receipt') != ref or run.get('boat_worker_receipt') != ref
        or run.get('execution_origin') != 'boat-linux' or run.get('boat_sandbox_id') != sandbox
        or run.get('source_commit') != source_sha or run.get('local_run_id') != run_id
        or worker.get('schema') != 'fdisbull-boat-worker-v1' or worker.get('execution_origin') != 'boat-linux'
        or worker.get('boat_sandbox_id') != sandbox or worker.get('architecture') != 'x86_64'
        or worker.get('type') not in ('small', 'default', 'large', 'xlarge') or not isinstance(worker.get('observed_at'), str)
        or prior.get('termination') != 'exited' or prior.get('container_state_after_stop') != 'stopped'
        or type(prior.get('exit_code')) is not int
        or post != {'source_commit': source_sha, 'expected_source_commit': source_sha,
                    'tracked_worktree_dirty': False, 'export_success': True}):
        raise ValueError('Original Boat build provenance mismatch')
    return {'build_execution_origin': 'boat-linux',
            'build_boat_worker_sha256': digest(files[0]),
            'build_boat_run_sha256': digest(files[1]),
            'build_source_postcheck_sha256': digest(files[2])}

def verify(directory, manifest_path, image_digest, profile='stable'):
    if profile not in PROFILES:
        raise ValueError('Unsupported original backend profile')
    directory = Path(directory)
    files = [directory / name for name in ('dosbox-x', 'build-identity.json', 'config.log',
                                            'build-manifest.json', 'build-process.json')]
    if any(p.is_symlink() or not p.is_file() for p in files):
        raise ValueError('Missing or unsafe reuse input')
    binary, raw, config, old_manifest, process = files
    identity = json.loads(raw.read_text())
    if any(key in identity for key in ('build_source_commit', 'build_identity_sha256',
                                       'build_process_sha256', 'build_manifest_sha256',
                                       'build_config_sha256', 'build_image_digest', 'build_execution_origin',
                                       'build_boat_worker_sha256', 'build_boat_run_sha256',
                                       'build_source_postcheck_sha256')):
        raise ValueError('Original compiled build evidence required; reused build identity is not accepted')
    prior = json.loads(process.read_text())
    manifest = json.loads(Path(manifest_path).read_text())
    sha = identity.get('source_commit')
    if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Invalid build source commit')
    if (prior.get('source_commit') != sha or prior.get('execution_origin') not in ('local-linux', 'boat-linux')
            or prior.get('job_name') != f'native-debugger-{profile}'
            or prior.get('image_digest') != image_digest
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', str(image_digest))):
        raise ValueError('Build process identity or image mismatch')
    if (old_manifest.read_bytes() != Path(manifest_path).read_bytes()
            or manifest.get('baseline_commit') != UPSTREAM
            or identity.get('upstream_commit') != UPSTREAM
            or identity.get('profile') != PROFILES[profile]
            or identity.get('configure_flags') != FLAGS
            or identity.get('patch_sha256') != manifest.get('patch_sha256')
            or identity.get('backend_sha256') != digest(binary)):
        raise ValueError('Backend build identity or source manifest mismatch')
    with binary.open('rb') as stream:
        header = stream.read(20)
    if len(header) != 20 or header[:6] != b'\x7fELF\x02\x01' or header[18:20] != b'\x3e\x00':
        raise ValueError('Backend must be little-endian ELF64 x86-64')
    if not config.stat().st_size:
        raise ValueError('Build config log is empty')
    boat = boat_provenance(directory, prior, sha) if prior.get('execution_origin') == 'boat-linux' else {}
    return {**boat, 'build_source_commit': sha, 'build_identity_sha256': digest(raw),
            'build_process_sha256': digest(process), 'build_manifest_sha256': digest(old_manifest),
            'build_config_sha256': digest(config), 'build_image_digest': image_digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('directory', 'manifest', 'evidence_image', 'evidence', 'binary_output'):
        parser.add_argument(name)
    parser.add_argument('--profile', choices=PROFILES, default='stable')
    args = parser.parse_args()
    directory, manifest, evidence, binary_output = map(Path, (
        args.directory, args.manifest, args.evidence, args.binary_output))
    provenance = verify(directory, manifest, args.evidence_image, args.profile)
    evidence.mkdir(parents=True, exist_ok=True)
    for name in ('build-identity.json', 'config.log', 'build-manifest.json', 'build-process.json'):
        shutil.copy2(directory / name, evidence / name)
    if provenance.get('build_execution_origin') == 'boat-linux':
        for name in ('build-boat-worker.json', 'build-boat-run.json', 'build-source-postcheck.json'):
            shutil.copy2(directory / name, evidence / name)
    binary_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(directory / 'dosbox-x', binary_output)
    (evidence / 'reuse-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')


if __name__ == '__main__':
    main()
