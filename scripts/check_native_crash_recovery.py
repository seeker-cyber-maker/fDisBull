#!/usr/bin/env python3
"""Bounded authored-target proof of pinned artifacts after injected backend loss.

Default is a read-only plan. --execute requires explicit backend/output paths and
storage admission. No game files, downloads, CI, installation or publication.
Raw states, images, DS reads and the FDB remain private outside Git.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

MIB = 1024 * 1024
CPU_FIELDS = ('cpu_mode', 'general', 'segments', 'instruction_pointer', 'flags')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def write_report(path, value):
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def private_path(path):
    path = path.expanduser().absolute()
    for parent in (path, *path.parents):
        require(not parent.is_symlink(), 'Output may not have symlink ancestry')
        require(not (parent / '.git').exists(), 'Output must be outside Git')
        require(not ((parent / 'HEAD').is_file() and (parent / 'objects').is_dir()),
                'Output may not be inside a bare repository')
    require(not path.exists(), 'Output must be a new private directory')
    return path


def output_bytes(root):
    return sum(p.stat().st_size for p in root.rglob('*') if p.is_file())


def source_modules(repo, head):
    result = {}
    for name, module in list(sys.modules.items()):
        if not (name == 'fdisbull' or name.startswith('fdisbull.')):
            continue
        filename = getattr(module, '__file__', None)
        if filename is None:
            continue
        path = Path(filename).resolve()
        require(path.is_relative_to(repo / 'src'), 'Imported source is outside selected checkout: ' + name)
        relative = path.relative_to(repo).as_posix()
        recorded = subprocess.run(['git', 'show', head + ':' + relative], cwd=repo,
                                  capture_output=True, check=True).stdout
        actual = path.read_bytes()
        require(actual == recorded, 'Imported source differs from declared commit: ' + relative)
        result[relative] = sha(actual)
    return result


def observe(debug, directory, label):
    registers = debug.registers()
    cpu = {key: registers[key] for key in CPU_FIELDS}
    address = int(registers['segments']['ds'], 16) * 16
    result = debug.call('memory.read', {'address': {'space': 'linear', 'offset': f'0x{address:08X}'},
                                       'length': 65536})
    raw = base64.b64decode(result['data_base64'], validate=True)
    require(len(raw) == 65536 and sha(raw) == result['sha256'], 'DS read identity mismatch')
    path = directory / (label + '.ds.private.bin')
    with path.open('xb') as stream:
        stream.write(raw)
    require(raw[0x200:0x204] == b'FTL1', 'Authored target signature is not in runtime DS')
    return {'cpu': cpu, 'ds_address': hex(address), 'ds_bytes': len(raw),
            'ds_sha256': sha(raw), 'ds_private_file': path.name,
            'controls': {name: int.from_bytes(raw[offset:offset+2], 'little')
                         for name, offset in [('count', 0x204), ('sum', 0x206), ('last', 0x208)]}}


def same_projection(left, right):
    return (left['cpu'] == right['cpu'] and left['ds_address'] == right['ds_address']
            and left['ds_sha256'] == right['ds_sha256'])


def export(project, artifact, path):
    result = project.debug_export(artifact['artifact'], path)
    require(result['sha256'] == artifact['sha256'] == sha(path.read_bytes()),
            'Exported artifact differs from committed identity')
    return {'artifact': artifact['artifact'], 'sha256': result['sha256'],
            'bytes': path.stat().st_size, 'private_file': path.name}


def run_case(project_type, backend, root, mode, fixture, ledger, budget_check, track):
    directory = root / mode
    directory.mkdir()
    game = directory / 'game'
    game.mkdir()
    target = game / 'FRAMES.COM'
    target.write_bytes(fixture)
    record = {'mode': mode, 'target_sha256': sha(fixture), 'target_bytes': len(fixture),
              'planned_failure_class': 'injected-owned-backend-SIGKILL',
              'guest_fault_address': None, 'guest_progress_during_failure': 'unknown',
              'started_at_utc': stamp()}
    ledger.append(record)
    db = directory / 'authored.fdb'
    with project_type.create(db, target, image='com') as project:
        with project.debugger(backend, game, version=1,
                              _on_spawn=lambda process: track(process, mode, 'failure-arm')) as debug:
            process = debug.rpc.process
            record['failed_backend_pid'] = process.pid
            record['failed_backend_returncode'] = None
            debug.advance_frames(4)
            debug.timeline_start(storage_mode=mode, keyframe_interval=8, max_frames=4,
                max_bytes=8*MIB, max_state_bytes=2*MIB, max_image_bytes=MIB, max_captures=16)
            debug.timeline_advance(2, inputs=[
                {'frame': 0, 'edges': [{'key': 'a', 'pressed': True}]},
                {'frame': 1, 'edges': [{'key': 'a', 'pressed': False}]}])
            record['input_plan'] = {'alignment_frames': 4, 'recorded_frames': 2,
                'edges': [{'frame': 0, 'key': 'a', 'pressed': True},
                          {'frame': 1, 'key': 'a', 'pressed': False}],
                'golden_suffix_frames': 1, 'recovery_suffix_frames': 1}
            status = debug.timeline_status()
            record['pre_failure_history'] = {key: status[key] for key in
                ('storage_mode', 'full_state_points', 'delta_state_points', 'cursor', 'point')}
            if mode == 'delta':
                require(status['points'][-1]['storage_kind'] == 'delta',
                        'Selected pin did not exercise delta materialization')
            stone = debug.timeline_pin('before-loss.sav')
            image = debug.timeline_image('before-loss.png')
            record['pinned_projection'] = observe(debug, directory, 'pinned')
            require(record['pinned_projection']['controls'] ==
                    {'count': 1, 'sum': 0x1e61, 'last': 0x1e61},
                    'Authored target did not consume the declared input')
            record['pin'] = export(project, stone, directory / 'before-loss.sav')
            record['image'] = export(project, image, directory / 'before-loss.png')
            debug.timeline_advance(1)
            record['golden_projection'] = observe(debug, directory, 'golden')
            golden_image = debug.timeline_image('golden.png')
            record['golden_image'] = export(project, golden_image, directory / 'golden.png')
            budget_check()

            # Inject only at this owned RPC's response-read boundary. The complete
            # frame.step request has been written, but guest progress/response
            # completion may already have occurred; neither is claimed here.
            original_call = debug.rpc.call
            original_ready = debug.rpc._ready
            injection = {'fired': False, 'phase': 'after-request-write-before-response-read'}

            def fault_call(method, params=None, timeout_ms=15000):
                if method != 'frame.step' or injection['fired']:
                    return original_call(method, params, timeout_ms=timeout_ms)

                def ready(fd, writing, deadline):
                    if not writing and fd == debug.rpc.reader and not injection['fired']:
                        require(process.poll() is None, 'Owned backend exited before injection')
                        injection['fired'] = True
                        injection['at_utc'] = stamp()
                        process.kill()
                        injection['returncode'] = process.wait(timeout=5)
                        require(injection['returncode'] == -signal.SIGKILL,
                                'Backend termination was not the requested SIGKILL')
                    return original_ready(fd, writing, deadline)

                debug.rpc._ready = ready
                try:
                    result = original_call(method, params, timeout_ms=timeout_ms)
                    injection['buffered_frame_result'] = result
                    return result
                finally:
                    debug.rpc._ready = original_ready

            debug.rpc.call = fault_call
            try:
                try:
                    debug.timeline_advance(1, timeout_ms=2000)
                except Exception as error:
                    record['observed_failure'] = {'type': type(error).__name__,
                                                  'message': str(error)[:500]}
                else:
                    raise ValueError('Injected backend loss did not fail the attempted operation')
            finally:
                debug.rpc.call = original_call
                debug.rpc._ready = original_ready
                record['injection'] = injection
                record['failed_backend_returncode'] = process.poll()
            require(injection['fired'] and process.poll() == -signal.SIGKILL,
                    'Owned backend was not injected/reaped')
            record['failure_class'] = 'injected-owned-backend-SIGKILL'
            require(debug.closed and debug._frame_timeline is None,
                    'Failure close did not clear unpinned frame history')
            record['failure_closed_session'] = debug.closed
            record['live_cache_cleared'] = debug._frame_timeline is None
        record['image_export_after_backend_loss'] = export(
            project, image, directory / 'after-loss.png')
        record['anchor_export_after_backend_loss'] = export(
            project, stone, directory / 'after-loss.sav')

    # Reopen the persisted project and use a genuinely new native process.
    with project_type(db) as reopened:
        record['offline_reopened_image'] = export(
            reopened, image, directory / 'reopened-offline.png')
        with reopened.debugger(backend, game, version=1,
                               _on_spawn=lambda process: track(process, mode, 'recovery-arm')) as fresh:
            fresh_process = fresh.rpc.process
            record['recovery_backend_pid'] = fresh_process.pid
            require(fresh_process.pid != process.pid, 'Recovery reused the failed process')
            require(fresh.timeline_status()['retained_points'] == 0,
                    'Fresh context inherited a live timeline')
            fresh.load_anchor_stone(stone['artifact'])
            restored = observe(fresh, directory, 'restored')
            record['restored_projection'] = restored
            require(same_projection(record['pinned_projection'], restored),
                    'Fresh recovery CPU/full DS differs from the pinned point')
            fresh.advance_frames(1)
            replay = observe(fresh, directory, 'replayed')
            record['replayed_projection'] = replay
            require(same_projection(record['golden_projection'], replay),
                    'Recovered suffix CPU/full DS differs from the golden suffix')
            screenshot = fresh.call('video.screenshot')
            replay_png = base64.b64decode(screenshot['png_base64'], validate=True)
            require(replay_png.startswith(b'\x89PNG\r\n\x1a\n')
                    and sha(replay_png) == screenshot['sha256'] == golden_image['sha256'],
                    'Recovered suffix PNG differs from the golden image')
            with (directory / 'replayed.png').open('xb') as stream:
                stream.write(replay_png)
            record['replayed_png_sha256'] = screenshot['sha256']
            record['replayed_png_private_file'] = 'replayed.png'
        record['recovery_backend_returncode'] = fresh_process.poll()
        require(fresh_process.poll() is not None, 'Recovery backend was not reaped')
        record['offline_image_after_recovery_exit'] = export(
            reopened, image, directory / 'after-recovery-exit.png')
    require(target.read_bytes() == fixture, 'Authored target was modified')
    record['target_unchanged'] = True
    record['status'] = 'passed'
    record['finished_at_utc'] = stamp()
    budget_check()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-head', required=True)
    parser.add_argument('--wall-seconds', type=int, default=120)
    parser.add_argument('--max-new-bytes', type=int, default=64*MIB)
    parser.add_argument('--destination-reserve-bytes', type=int, default=40_000_000_000)
    parser.add_argument('--storage-admit', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    require(30 <= args.wall_seconds <= 180 and 16*MIB <= args.max_new_bytes <= 64*MIB,
            'Finite wall/output bounds required')
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo,
                          text=True, capture_output=True, check=True).stdout.strip()
    require(head == args.expected_head, 'Source head differs from the declared candidate')
    backend = args.backend.expanduser().resolve(strict=True)
    require(backend.is_file() and os.access(backend, os.X_OK), 'Backend is not executable')
    root = private_path(args.output)
    import benchmark_frame_timeline as fixture_module
    require(Path(fixture_module.__file__).resolve() == repo / 'scripts/benchmark_frame_timeline.py',
            'Fixture module is outside selected checkout')
    fixture = fixture_module.authored_com()
    fixture_source = Path(fixture_module.__file__).read_bytes()
    committed_fixture = subprocess.run(['git', 'show', head + ':scripts/benchmark_frame_timeline.py'],
                                       cwd=repo, capture_output=True, check=True).stdout
    require(fixture_source == committed_fixture, 'Fixture source differs from declared commit')
    from fdisbull.project import Project
    loaded = source_modules(repo, head)
    plan = {'format': 'fdisbull-authored-native-crash-recovery-1', 'status': 'plan',
            'source_head': head, 'controller_sha256': sha(Path(__file__).read_bytes()),
            'backend_sha256': sha(backend.read_bytes()), 'backend': str(backend),
            'target_bytes': len(fixture), 'target_sha256': sha(fixture),
            'fixture_module_sha256': sha(Path(fixture_module.__file__).read_bytes()),
            'loaded_source_modules': loaded,
            'modes': ['full', 'delta'], 'maximum_owned_native_processes': 4,
            'maximum_simultaneous_guests': 1, 'wall_seconds': args.wall_seconds,
            'max_new_bytes': args.max_new_bytes,
            'injection_class': 'owned SIGKILL after frame request write, before response read',
            'guest_progress_during_injection': 'unknown', 'native_guest_vulnerability_claim': False}
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    admission = subprocess.run([sys.executable, str(args.storage_admit), '--path', str(root.parent),
        '--expected-bytes', str(args.max_new_bytes), '--destination-reserve-bytes',
        str(args.destination_reserve_bytes)], text=True, capture_output=True)
    require(admission.returncode == 0, 'Storage admission refused; no native work started')
    root.mkdir(mode=0o700)
    temporary = root / 'tmp'
    temporary.mkdir()
    os.environ['TMPDIR'] = str(temporary)
    import tempfile
    tempfile.tempdir = str(temporary)
    os.environ['FDISBULL_TARGET_STORE'] = str(root / 'objects')
    report = {**plan, 'status': 'running', 'started_at_utc': stamp(),
              'platform': {'os': platform.system(), 'machine': platform.machine(),
                           'python': platform.python_version()},
              'storage_admission': json.loads(admission.stdout), 'cases': [], 'owned_native': []}
    owned = []
    path = root / 'report.private.json'
    write_report(path, report)

    def budget_check():
        require(output_bytes(root) < args.max_new_bytes - 2*MIB, 'Output budget nearly exhausted')
        require(os.statvfs(root).f_bavail * os.statvfs(root).f_frsize > 20_000_000_000,
                'Physical free-space floor reached')

    def deadline(signum, frame):
        raise TimeoutError('Authored native crash proof wall deadline')

    def track(process, mode, role):
        entry = {'pid': process.pid, 'mode': mode, 'role': role, 'spawned_at_utc': stamp()}
        owned.append((process, entry))
        report['owned_native'].append(entry)
        write_report(path, report)
        require(len(owned) <= 4, 'Native process count exceeded the finite plan')

    previous = signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, args.wall_seconds)
    try:
        for mode in plan['modes']:
            budget_check()
            run_case(Project, backend, root, mode, fixture, report['cases'], budget_check, track)
            write_report(path, report)
        require(sha(backend.read_bytes()) == plan['backend_sha256'], 'Backend binary changed')
        report['loaded_source_modules_after'] = source_modules(repo, head)
        report['status'] = 'passed'
    except BaseException as error:
        report['status'] = 'failed'
        report['error'] = {'type': type(error).__name__, 'message': str(error)[:1000]}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        for process, entry in owned:
            try:
                if process.poll() is None:
                    entry['forced_final_cleanup'] = True
                    process.kill()
                entry['returncode'] = process.wait(timeout=3)
                entry['reaped'] = True
            except BaseException as error:
                entry['reaped'] = False
                entry['cleanup_error'] = type(error).__name__
                report['status'] = 'failed'
        report['all_owned_native_reaped'] = all(entry.get('reaped') for _, entry in owned)
        report['finished_at_utc'] = stamp()
        report['retained_file_bytes'] = output_bytes(root)
        write_report(path, report)
    print(json.dumps({'status': report['status'], 'report': str(path),
                      'cases': len(report['cases']), 'error': report.get('error')}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
