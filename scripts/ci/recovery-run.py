#!/usr/bin/env python3
"""Run one explicitly configured, finite OVH CI recovery rehearsal.

This command is inert until invoked. It owns no timer, release gate, or
production-service repair. A completed rehearsal qualifies only this control
path, never the application or a native backend.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

from recovery import RecoveryController
from recovery_gitlab import GitLabRecoveryBackend, CI_STATUS
from recovery_source import SourceRepair


def load_legacy(path, expected_sha256):
    path = Path(path)
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError('retained transport helper differs')
    spec = importlib.util.spec_from_file_location('retained_ci_transport', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, value):
    CI_STATUS._write(path, value)


def run(config):
    directory = Path(config['state_dir'])
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / 'controller.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return execute(config, directory)


def execute(config, directory):
    legacy = load_legacy(config['legacy_transport'], config['legacy_transport_sha256'])
    repair = SourceRepair(config['repo_root'], directory, config['ref'])
    backend = GitLabRecoveryBackend(config, legacy, repair)
    manifest_path, state_path = directory / 'manifest.json', directory / 'state.json'
    bootstrap = directory / 'bootstrap.json'
    next_health = 0
    with backend.lease():
        while time.time() < config['deadline_epoch']:
            state = json.loads(state_path.read_text()) if state_path.exists() else None
            if state and state['status'] in ('complete', 'attention'):
                if state['status'] == 'complete':
                    # An identical replay must be harmless at the incident seam.
                    replay = directory / 'recovered-replay.json'
                    if not replay.exists():
                        write(replay, backend.emit('complete', state))
                print(json.dumps({'status': state['status'], 'reason': state.get('reason'),
                                  'target': state['target'], 'state_path': str(state_path)}), flush=True)
                return 0 if state['status'] == 'complete' else 1
            if time.time() >= next_health:
                health = backend.health()
                write(directory / 'latest-health.json', health)
                next_health = time.time() + 60
                if health['state'] != 'healthy':
                    raise RuntimeError('production health unavailable; no further dispatch')
            planned = state if state is not None else {'phase': 'dispatch_pipeline'}
            if not backend.prepare_step(planned):
                if backend.refresh_reason not in ('cooldown', 'busy'):
                    raise RuntimeError('provider refresh refused')
                # No force, reset, takeover or provider polling inside cooldown.
                remaining = (backend.next_refresh_at or time.time() + 60) - time.time()
                time.sleep(max(1, min(60, remaining)))
                continue
            if not manifest_path.exists():
                target = {'pipeline_id': '0', 'job_id': '0',
                          'source_sha': config['initial_sha'],
                          'job_name': 'ci-recovery-rehearsal', 'runner_id': str(config['runner_id'])}
                payload = {'project': str(config['project_id']), 'target': target,
                           'source_sha': config['initial_sha']}
                key = config['incident_id'] + ':bootstrap'
                if bootstrap.exists():
                    saved = json.loads(bootstrap.read_text())
                    if saved.get('key') != key or saved.get('payload') != payload:
                        raise RuntimeError('bootstrap identity mismatch')
                    result = saved.get('result')
                    if result is None:
                        result = backend.reconcile_action('start_pipeline', key, payload)
                        if result is None:
                            raise RuntimeError('bootstrap uncertain; manual canonical readback required')
                else:
                    write(bootstrap, {'key': key, 'payload': payload, 'result': None})
                    result = backend.perform('start_pipeline', key, payload)
                if result.get('status') != 'completed':
                    raise RuntimeError('bootstrap incomplete')
                write(bootstrap, {'key': key, 'payload': payload, 'result': result})
                manifest = {'incident_id': config['incident_id'], 'project': str(config['project_id']),
                            'initial_target': result['target'], 'deadline_epoch': config['deadline_epoch'],
                            'max_infrastructure_repairs': 1, 'max_source_repairs': 1}
                write(manifest_path, manifest)
                print(json.dumps({'status': 'started', 'target': result['target']}), flush=True)
                # Creation is a mutation; the next observation uses a new reservation.
                continue
            manifest = json.loads(manifest_path.read_text())
            controller = RecoveryController(state_path, manifest, backend)
            state = controller.step()
            print(json.dumps({'status': state['status'], 'phase': state['phase'],
                              'target': state['target'], 'reason': state.get('reason')}), flush=True)
        raise RuntimeError('finite incident deadline expired')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    if args.config.is_symlink() or args.config.stat().st_size > 32_768:
        raise ValueError('unsafe configuration')
    config = json.loads(args.config.read_text())
    try:
        return run(config)
    except Exception as exc:
        # Provider/CLI exception text may contain sensitive response content.
        directory = Path(config['state_dir'])
        if directory.is_dir():
            write(directory / 'controller-exit.json', {'status': 'attention',
                  'error_type': type(exc).__name__, 'observed_epoch': time.time()})
        print(json.dumps({'status': 'attention', 'error_type': type(exc).__name__}), flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
