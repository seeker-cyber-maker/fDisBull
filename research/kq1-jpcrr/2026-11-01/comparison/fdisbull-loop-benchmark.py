#!/usr/bin/env python3
"""Public path-parameterized derivative of the private finite KQ1 controller.

Without --execute this validates caller inputs and prints a plan.
The caller is the sole guest owner. This controller makes a fresh byte-identical
copy of the prepared FDB, loads its existing Anchor, and never edits the original
FDB, game files, prior receipts, source worktree, installation, or Git remotes.
Storage admission precedes each material growth phase. SIGALRM and per-operation
deadlines bound execution; the ordinary context manager owns native reaping.

Core latency is TWO ordered kp5 dispatches (make THEN break while paused), ONE
DOSBox completed-renderer-frame followed by a safe fetch, then CPU registers,
ONE atomic65536-byte DS read and a released-key ownership check. Native frame
info comes from the verified advance receipt. It excludes optional
manual capture, verification image exports, report IO and setup. Manual dense
Anchor+PNG capture has a separate cost and is included in total loop latency.
Automatic capture is intrinsically inside timeline_advance. JPC-RR retrace-start
traps are different native boundaries: this is a comparable task, not proof of
identical hidden machines, guest frame cadence, instruction work, or rendering.
JPC-RR spaces its edges by1ms while DOSBox queues both before execution; stage
timings are separate and no whole-loop cross-engine speed ratio is claimed.
An accepted key edge is not proof of game-level consumption. Counts are explicit
Python API operations/native RPC dispatches, never model turns.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import sqlite3
import statistics
import subprocess
import sys
import time


ROOT = REPO = HELPER = ADMIT = None  # Set from required caller inputs.
HEAD = '865542a26b5406b2bc81e0e3bc7c542a287eec25'
BACKEND_SHA = 'a32b8285ea412413e9d60bf8b1c8735b9ee082b683a46dcba3fce65d47c47474'
EXPECTED_HELPER_SHA256 = 'f4c56cd166dfb4c4ec6afc5f41ef795d49ac87e7bdfa806017e56ea1282f9c29'
MODES = ('recording_off', 'manual_dense_anchor_stones', 'automatic_timeline', 'anchor_plus_timeline')
MIB = 1024**2


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(test, text):
    if not test:
        raise RuntimeError(text)


def compact(value):
    if isinstance(value, dict):
        return {k: compact(v) for k, v in value.items() if k not in ('points', 'data', 'data_base64')}
    if isinstance(value, (list, tuple)):
        return [compact(v) for v in value]
    return value


def reference(value):
    return {k: value[k] for k in ('artifact', 'sha256', 'size')}


def distribution(values):
    if not values:
        return {'samples': 0}
    ordered = sorted(values)
    return {'samples': len(values), 'median_ns': statistics.median(values),
            'p95_ns': ordered[math.ceil(.95 * len(ordered)) - 1],
            'minimum_ns': ordered[0], 'maximum_ns': ordered[-1],
            'p95_method': 'nearest rank; warm observations in this one live session'}


def inventory(project):
    return {i['id']: i for i in project.debug_artifacts()['artifacts']}


def growth(before, after):
    added = [i for identifier, i in after.items() if identifier not in before]
    return {'new_artifacts': len(added), 'kinds': dict(Counter(i['kind'] for i in added)),
            'logical_payload_bytes': sum(i['size'] for i in added),
            'state_payload_bytes': sum(i['size'] for i in added if i['kind'] == 'state'),
            'image_payload_bytes': sum(i['size'] for i in added if i['kind'] == 'screenshot'),
            'scope': 'Logical durable artifact bytes; live timeline cache is separate.'}


def loaded_sources():
    result = {}
    for name in ('fdisbull.project', 'fdisbull.debugger', 'fdisbull.debug_timeline',
                 'fdisbull.debug_script', 'fdisbull.dosbox_rpc'):
        module = __import__(name, fromlist=['_'])
        path = Path(module.__file__).resolve(strict=True)
        require(path.is_relative_to(REPO / 'src'), 'Imported module escaped the frozen source tree')
        relative = str(path.relative_to(REPO))
        committed = subprocess.check_output(['git', '-C', str(REPO), 'show', HEAD + ':' + relative])
        require(hashlib.sha256(committed).hexdigest() == sha(path), 'Loaded source differs from frozen HEAD')
        result[name] = {'path': str(path), 'sha256': sha(path)}
    return result


def main(argv=None):
    global ROOT, REPO, HELPER, ADMIT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='NEW directory in the authorized external runtime workspace')
    parser.add_argument('--runtime-root', type=Path, required=True, help='Existing authorized private external workspace')
    parser.add_argument('--source-root', type=Path, required=True, help='Frozen MR30 fDisBull checkout at the required HEAD')
    parser.add_argument('--helper', type=Path, required=True, help='Matching private KQ1 observer/controller helper; not distributed here')
    parser.add_argument('--storage-admit', type=Path, required=True, help='Caller storage-admission helper')
    parser.add_argument('--start', type=Path, required=True, help='Caller-owned matching KQ1 preparation receipt')
    parser.add_argument('--execute', action='store_true', help='Start native guest; omit for input validation and a plan')
    parser.add_argument('--samples', type=int, default=32)
    parser.add_argument('--warmups', type=int, default=4)
    parser.add_argument('--timeout-ms', type=int, default=30000)
    parser.add_argument('--wall-seconds', type=int, default=300)
    parser.add_argument('--max-new-bytes', type=int, default=512*MIB)
    parser.add_argument('--destination-reserve-bytes', type=int, default=20000000000,
                        help='Explicit previously approved bounded-work reserve; never below20GB')
    parser.add_argument('--rng-probe-frames', type=int, default=64)
    args = parser.parse_args(argv)
    ROOT = args.runtime_root.expanduser().resolve(strict=True)
    REPO = args.source_root.expanduser().resolve(strict=True)
    HELPER = args.helper.expanduser().resolve(strict=True)
    ADMIT = args.storage_admit.expanduser().resolve(strict=True)
    require(sha(HELPER) == EXPECTED_HELPER_SHA256, 'Private helper differs from the measured dependency')
    require(8 <= args.samples <= 64 and args.samples % 2 == 0, 'Use8..64 even timed samples')
    require(0 <= args.warmups <= 8 and args.warmups % 2 == 0, 'Use0..8 even warmups')
    require(1 <= args.timeout_ms <= 60000 and 30 <= args.wall_seconds <= 600, 'Invalid finite deadline')
    require(128*MIB <= args.max_new_bytes <= 512*MIB, 'This controller permits128..512MiB total new output')
    require(args.destination_reserve_bytes >= 20000000000, 'The20GB reserve cannot be lowered')
    require(0 <= args.rng_probe_frames <= 64, 'RNG probe must be0..64frames')
    output = args.output.expanduser().absolute()
    require(output.is_relative_to(ROOT) and not output.exists(),
            'Output must be a new authorized external runtime directory')
    for ancestor in (output, *output.parents):
        require(not ancestor.is_symlink() and not (ancestor / '.git').exists(), 'Output cannot use symlinks or Git ancestry')
    require(output.parent.is_dir(), 'Output parent must already exist on the mounted external volume')
    start_path = args.start.expanduser().resolve(strict=True)
    start_bytes = start_path.read_bytes()
    start = json.loads(start_bytes)
    require(start['format'] == 'kq1-rat-start-1', 'Unexpected preparation format')
    backend = Path(start['backend']).resolve(strict=True)
    require(sha(backend) == BACKEND_SHA == start['backend_sha256'], 'Prepared candidate-v3 backend identity changed')
    require(subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip() == HEAD,
            'Frozen MR30 source HEAD changed')
    original_project = Path(start['project']).resolve(strict=True)
    require(not Path(str(original_project) + '-wal').exists()
            or Path(str(original_project) + '-wal').stat().st_size == 0,
            'Prepared FDB has a nonempty WAL; do not take an inconsistent byte copy')
    original_sha = sha(original_project)
    admissions = []

    def admit(phase, expected):
        process = subprocess.run([sys.executable, str(ADMIT), '--path', str(output.parent),
            '--expected-bytes', str(expected), '--destination-reserve-bytes', str(args.destination_reserve_bytes)],
            text=True, capture_output=True, timeout=30)
        receipt = {'phase': phase, 'expected_bytes': expected, 'exit_code': process.returncode,
                   'stdout': process.stdout, 'stderr': process.stderr}
        admissions.append(receipt)
        require(process.returncode == 0, 'Storage admission refused phase:' + phase + '\n' + process.stdout[-6000:] + process.stderr[-2000:])

    if not args.execute:
        print(json.dumps({'execute_requested': False, 'head': HEAD,
            'backend_sha256': BACKEND_SHA, 'helper_sha256': EXPECTED_HELPER_SHA256,
            'output_would_be': str(output), 'samples_per_mode': args.samples,
            'warmups_per_mode': args.warmups, 'modes': list(MODES),
            'native_execution': False, 'storage_admission_deferred_until_execute': True}, indent=2))
        return 0

    admit('fresh_FDB_copy_and_control', 32*MIB)
    output.mkdir(mode=0o700)
    temporary = output / 'tmp'
    temporary.mkdir(mode=0o700)
    os.environ['TMPDIR'] = str(temporary)
    os.environ['FDISBULL_TARGET_STORE'] = str(output / 'objects')
    sys.path.insert(0, str(REPO / 'src'))
    spec = importlib.util.spec_from_file_location('private_kq1_helpers', HELPER)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    from fdisbull.project import Project
    source_hashes = loaded_sources()
    copied = output / 'kq1-loop.fdb'
    shutil.copy2(original_project, copied)
    require(sha(copied) == sha(original_project) == original_sha, 'FDB changed during fresh copy')
    # External-object projects need an independently copied dependency store;
    # the selected prepared project is legacy-embedded and is admitted as such.
    with sqlite3.connect(copied.as_uri() + '?mode=ro&immutable=1', uri=True) as probe:
        storage = dict(probe.execute('SELECT key,value FROM metadata')).get('storage')
    require(storage != json.dumps('external-objects-1'), 'This controller requires the selected legacy-embedded preparation')
    start = dict(start, project=str(copied))
    report_path = output / 'report.private.json'
    report = {'format': 'fdisbull-kq1-warm-input-loop-1', 'status': 'running',
        'started_at_utc': datetime.now(timezone.utc).isoformat(), 'platform': platform.platform(),
        'machine': platform.machine(), 'python': sys.version.split()[0], 'head': HEAD,
        'loaded_sources': source_hashes, 'controller_sha256': sha(__file__),
        'helper': {'path': str(HELPER), 'sha256': sha(HELPER)},
        'backend': {'path': str(backend), 'sha256': BACKEND_SHA},
        'start_receipt': {'path': str(start_path), 'sha256': hashlib.sha256(start_bytes).hexdigest()},
        'project_copy': {'original': str(original_project), 'original_sha256': original_sha,
                         'copy': str(copied), 'initial_copy_identical': True},
        'configuration': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        'boundary': 'DOSBox one completed renderer frame followed by a stopped safe CPU fetch; variable video cadence.',
        'core_pipeline': 'physical kp5 make THEN break through two ordered paused dispatches -> one completed frame -> CPU registers+atomic65536-byte DS+released-key ownership observation; frame info from verified advance receipt',
        'input_spacing': 'DOSBox queues make then break while paused with no emulated1ms gap; JPC-RR uses1ms edge spacing. These are explicit differences, not equivalent hardware schedules.',
        'observation_scope': 'Exposed CPU groups, one atomic65536-byte DS read, released frame-key ownership; native frame info is aggregated into the advance receipt rather than a separate caller info call.',
        'cross_engine_ratio': 'Not claimed: compare separately reported dispatch, native-frame advance and observation stages, with boundary/spacing/projection differences retained.',
        'controller_scope_differences': [
            'fDisBull runs from the prepared rat-room Anchor; JPC-RR runs its ready first-room prefix. These are different KQ1 scenes and machine configurations.',
            'fDisBull DS observation hashes full DS and masked-RNG DS and parses actor fields; JPC-RR hashes DS and returns its own richer info/register dictionaries. Observer postprocessing differs.',
            'fDisBull core/total-loop timers exclude report IO and file-bound checks. JPC-RR per-command file/size/log work may be inside its total timer. Totals describe each controller, not normalized emulator throughput.',
        ],
        'key_consumption': 'Native dispatch/ownership and frame completion are observed; game-level kp5 consumption is not established.',
        'comparison_limit': 'Comparable input/frame/65536-byte-observation task versus JPC-RR; not identical native boundaries, machine state, cadence or instruction workload.',
        'count_scope': 'Explicit controller API operations and backend RPC dispatches, not model turns.',
        'manual_capture': 'Dense full Anchor+PNG after every core loop; captured separately and included in total loop latency.',
        'automatic_capture': 'Full native state+PNG live cache during timeline_advance; inherent in core loop cost.',
        'mode_order': list(MODES), 'admissions': admissions, 'arms': []}

    def persist():
        helper.dump(report_path, report)

    def footprint():
        return sum(p.stat().st_size for p in output.rglob('*') if p.is_file())

    def bounded():
        require(footprint() <= args.max_new_bytes, 'Controller output exceeded its declared new-allocation bound')

    def alarm(*unused):
        raise TimeoutError('Finite controller wall deadline expired')

    prior_signal = signal.signal(signal.SIGALRM, alarm)
    signal.alarm(args.wall_seconds)
    session = None
    process = None
    try:
        persist()
        with Project(copied) as project:
            with project.debugger(backend, start['game_dir'], version=1) as session:
                process = session.rpc.process
                report['native_pid'] = process.pid
                require(session.rpc.capabilities.get('frame_timeline') and session.rpc.capabilities.get('save_states'),
                        'Candidate lacks native frame/full-state capabilities')
                report['native_capabilities'] = session.rpc.capabilities
                session.load_anchor_stone(start['anchor']['artifact'])
                validation = helper.FrameTrial(session, start, frame_budget=512, timeout_ms=args.timeout_ms)
                try:
                    report['source_witnesses'] = helper.verify_source(validation, start)
                    report['seed_state'] = validation.safe(validation.state())
                finally:
                    validation.finish()
                total = args.warmups + args.samples
                for mode in MODES:
                    admit(mode, 256*MIB if mode == MODES[1] else 32*MIB)
                    bounded()
                    result = {'mode': mode, 'status': 'running', 'samples': [], 'manual_points': []}
                    report['arms'].append(result)
                    trial = helper.FrameTrial(session, start, frame_budget=512, timeout_ms=args.timeout_ms)
                    before_artifacts = inventory(project)
                    try:
                        trial.phase = 'setup'
                        result['seed_load'] = compact(trial.call('load_anchor_stone', session.load_anchor_stone, start['anchor']['artifact']))
                        result['alignment'] = compact(trial.advance(1))
                        initial = trial.safe(trial.state())
                        result['aligned_initial_state'] = initial
                        if mode != MODES[0] and mode != MODES[1]:
                            result['timeline_start'] = compact(trial.call('timeline_start', session.timeline_start,
                                max_frames=total+4, max_bytes=64*MIB, max_state_bytes=2*MIB,
                                max_image_bytes=MIB, max_captures=512))
                            trial.timeline = True
                            if mode == MODES[3]:
                                result['coarse_pin'] = trial.call('timeline_pin', session.timeline_pin, mode+'-coarse.sav')

                        def manual_capture(name):
                            stone = trial.call('save_anchor_stone', session.save_anchor_stone, name+'.sav', max_bytes=2*MIB)
                            image = trial.call('screenshot', session.screenshot, name+'.png', hooks=False)
                            require(image['size'] <= MIB, 'Manual image exceeded its conservative one-MiB bound')
                            return {'state': reference(stone), 'image': reference(image)}

                        if mode == MODES[1]:
                            result['manual_points'].append(manual_capture(mode+'-initial'))

                        def edge_loop(index, warmup=False, retry=False):
                            trial.phase = ('retry_' if retry else 'warmup_' if warmup else 'timed_')+'core'
                            api_begin, rpc_begin = len(trial.calls), len(trial.rpc)
                            begun = time.perf_counter_ns()
                            make = {'key': 'kp5', 'pressed': True}
                            release = {'key': 'kp5', 'pressed': False}
                            # Duplicate key names are forbidden in one public
                            # batch, so preserve ordering with two paused calls.
                            accepted_make = trial.edges([make])
                            made = time.perf_counter_ns()
                            accepted_break = trial.edges([release])
                            released = time.perf_counter_ns()
                            boundary = trial.advance(1)
                            frame_done = time.perf_counter_ns()
                            observed_cpu = trial.call('registers', helper.cpu, session)
                            observed = trial.state()
                            observed_keyboard = trial.call('keyboard_state', session.keyboard_state)['keyboard']
                            require(not observed_keyboard['frame_keys'] and not observed_keyboard['pending_events']
                                    and not observed_keyboard['owned_keys'],
                                    'Timed make/break pair left owned or pending physical keys')
                            core_done = time.perf_counter_ns()
                            core_api, core_rpc = len(trial.calls)-api_begin, len(trial.rpc)-rpc_begin
                            capture_begun = time.perf_counter_ns()
                            if mode == MODES[1]:
                                trial.phase = 'retry_capture' if retry else 'warmup_capture' if warmup else 'timed_capture'
                                result['manual_points'].append(manual_capture(f'{mode}-{index}-'+('retry' if retry else 'forward')))
                            finished = time.perf_counter_ns()
                            frame_record = boundary['frames'][0]
                            sample = {'index': index, 'warmup': warmup, 'edges': [make, release],
                                'make_dispatch_elapsed_ns': made-begun,
                                'break_dispatch_elapsed_ns': released-made,
                                'input_pair_dispatch_elapsed_ns': released-begun,
                                'frame_advance_elapsed_ns': frame_done-released,
                                'observation_elapsed_ns': core_done-frame_done,
                                'core_elapsed_ns': core_done-begun, 'manual_capture_elapsed_ns': finished-capture_begun if mode == MODES[1] else 0,
                                'total_loop_elapsed_ns': finished-begun,
                                'core_caller_api_calls': core_api, 'core_backend_rpc_dispatches': core_rpc,
                                'total_caller_api_calls': len(trial.calls)-api_begin,
                                'total_backend_rpc_dispatches': len(trial.rpc)-rpc_begin,
                                'accepted_native_make': compact(accepted_make),
                                'accepted_native_break': compact(accepted_break), 'completed_frame': compact(boundary),
                                'native_frame_info': compact(frame_record.get('native_frame', frame_record)),
                                'cpu_observation': observed_cpu, 'cpu_for_retry_oracle': observed_cpu,
                                'released_frame_key_ownership_verified': True,
                                'keyboard_observation': observed_keyboard,
                                'observation': observed, 'game_level_key_consumption': 'unknown'}
                            trial.safe(observed)
                            bounded()
                            return sample

                        for index in range(total):
                            sample = edge_loop(index, warmup=index < args.warmups)
                            result['samples'].append(sample)
                            persist()
                        trial.phase = 'endpoint_verification'
                        keyboard = trial.call('keyboard_state', session.keyboard_state)['keyboard']
                        require(not keyboard['frame_keys'] and not keyboard['pending_events'] and not keyboard['owned_keys'],
                                'Completed make/break input plan left owned or pending physical keys')
                        result['endpoint_keyboard'] = keyboard
                        if trial.timeline:
                            image = trial.call('timeline_image', session.timeline_image, mode+'-endpoint.png')
                        elif mode == MODES[1]:
                            image = result['manual_points'][-1]['image']
                        else:
                            image = trial.call('screenshot', session.screenshot, mode+'-endpoint.png', hooks=False)
                        project.debug_export(image['artifact'], output/(mode+'-endpoint.png'))
                        result['endpoint_image'] = reference(image)
                        target = result['samples'][-2]
                        trial.phase = 'recent_return'
                        retry_begun = time.perf_counter_ns()
                        if trial.timeline:
                            returned = trial.call('timeline_rewind', session.timeline_rewind, frames=1, timeout_ms=args.timeout_ms)
                        elif mode == MODES[1]:
                            returned = trial.call('load_anchor_stone', session.load_anchor_stone, result['manual_points'][-2]['state']['artifact'])
                        else:
                            returned = trial.call('load_anchor_stone', session.load_anchor_stone, start['anchor']['artifact'])
                            trial.advance(1)
                            for index in range(total-1):
                                trial.edges([{'key': 'kp5', 'pressed': True}])
                                trial.edges([{'key': 'kp5', 'pressed': False}])
                                trial.advance(1)
                        restored_ns = time.perf_counter_ns()-retry_begun
                        trial.phase = 'recent_return_verification'
                        recovered = trial.state()
                        require(recovered['ds_sha256'] == target['observation']['ds_sha256'], 'Recent return DS differs from recorded boundary')
                        require(trial.call('registers', helper.cpu, session) == target['cpu_for_retry_oracle'], 'Recent return CPU differs')
                        retry = edge_loop(total, retry=True)
                        require(retry['observation']['ds_sha256'] == result['samples'][-1]['observation']['ds_sha256'], 'Same-edge retry DS differs')
                        trial.phase = 'retry_verification'
                        require(trial.call('registers', helper.cpu, session) == result['samples'][-1]['cpu_for_retry_oracle'], 'Same-edge retry CPU differs')
                        result['recent_return_and_retry'] = {'return': compact(returned), 'return_elapsed_ns': restored_ns,
                            'retry': retry, 'return_and_retry_including_verification_ns': time.perf_counter_ns()-retry_begun,
                            'same_prior_cpu_and_ds': True, 'same_retry_cpu_and_ds': True,
                            'off_mode_scope': 'Seed load, common alignment, known input replay to prior boundary' if mode == MODES[0] else None}
                        warm = [s for s in result['samples'] if not s['warmup']]
                        result['summary'] = {key: distribution([s[key] for s in warm]) for key in
                            ('input_pair_dispatch_elapsed_ns','frame_advance_elapsed_ns','observation_elapsed_ns',
                             'core_elapsed_ns','manual_capture_elapsed_ns','total_loop_elapsed_ns')}
                        result['summary']['core_caller_api_calls'] = sum(s['core_caller_api_calls'] for s in warm)
                        result['summary']['core_backend_rpc_dispatches'] = sum(s['core_backend_rpc_dispatches'] for s in warm)
                        result['summary']['total_caller_api_calls'] = sum(s['total_caller_api_calls'] for s in warm)
                        result['summary']['total_backend_rpc_dispatches'] = sum(s['total_backend_rpc_dispatches'] for s in warm)
                        if trial.timeline:
                            result['final_live_cache'] = compact(trial.call('timeline_status', session.timeline_status))
                            trial.call('timeline_stop', session.timeline_stop)
                            trial.timeline = False
                        result['durable_artifact_growth'] = growth(before_artifacts, inventory(project))
                        result['status'] = 'passed'
                    finally:
                        result['metrics'] = trial.report()
                        trial.finish()
                        persist()
                    print(json.dumps({'mode': mode, 'status': result['status'], 'summary': result.get('summary')}), flush=True)

                if args.rng_probe_frames:
                    admit('bounded_rng_restore_preserve_probe', 32*MIB)
                    trial = helper.FrameTrial(session, start, frame_budget=128, timeout_ms=args.timeout_ms)
                    probe = {'status': 'searching', 'max_frames': args.rng_probe_frames, 'steps': []}
                    report['rng_safeguards'] = probe
                    try:
                        trial.phase = 'rng_setup'
                        trial.call('load_anchor_stone', session.load_anchor_stone, start['anchor']['artifact'])
                        trial.call('timeline_start', session.timeline_start, max_frames=64, max_bytes=64*MIB,
                                   max_state_bytes=2*MIB, max_image_bytes=MIB, max_captures=128)
                        trial.timeline = True
                        for index in range(args.rng_probe_frames):
                            trial.phase = 'natural_rng_probe'
                            s1 = trial.safe(trial.state())
                            before_cpu = trial.call('registers', helper.cpu, session)
                            trial.advance(1)
                            s2 = trial.safe(trial.state())
                            probe['steps'].append({'frame': index+1, 'before_rng': s1['rng'], 'after_rng': s2['rng']})
                            if s2['rng'] == s1['rng']:
                                continue
                            require(s1['rng'] and s2['rng'], 'Natural transition used the zero-seed sentinel')
                            trial.phase = 'rng_full_restore'
                            full = trial.call('timeline_rewind', session.timeline_rewind, frames=1, timeout_ms=args.timeout_ms)
                            require(trial.state()['ds_sha256'] == s1['ds_sha256'], 'Full rewind did not restore original RNG/DS')
                            require(trial.call('registers', helper.cpu, session) == before_cpu, 'Full RNG rewind CPU differs')
                            trial.advance(1)
                            require(trial.state()['ds_sha256'] == s2['ds_sha256'], 'Natural RNG transition replay differs')
                            trial.phase = 'rng_preserve_without_partial_resume'
                            preserved = trial.call('timeline_rewind', session.timeline_rewind, frames=1,
                                policy={'name': 'preserve-current-observed-kq1-rng', 'preserve_memory': [
                                    {'address': f"0x{start['ds']+helper.RNG_OFFSET:08X}", 'length': 2}]},
                                timeout_ms=args.timeout_ms)
                            mixed = trial.state()
                            require(mixed['world_without_rng_sha256'] == s1['world_without_rng_sha256']
                                    and mixed['rng'] == s2['rng'], 'Preservation changed bytes outside the declared RNG field')
                            require(preserved['execution_allowed'] is False and preserved['resume_safe'] is False,
                                    'Unapproved partial RNG preservation allowed execution')
                            try:
                                trial.call('timeline_advance', session.timeline_advance, frames=1, timeout_ms=args.timeout_ms)
                            except ValueError as error:
                                blocked = {'blocked': True, 'type': type(error).__name__, 'message': str(error)}
                            else:
                                raise RuntimeError('Frozen mixed RNG state executed without explicit partial resume')
                            require(trial.state()['ds_sha256'] == mixed['ds_sha256'], 'Refused mixed-state advancement changed DS')
                            probe.update(status='passed', transition_frame=index+1, before=s1, after=s2,
                                full_return=compact(full), preserved_return=compact(preserved), mixed_state=mixed,
                                compared_non_rng_ds_bytes=65534, blocked_execution=blocked,
                                whole_machine_equivalence=False, resumed_mixed_state=False)
                            break
                        else:
                            probe.update(status='not_observed', reason='No natural RNG transition in the finite window; preservation not qualified by this run')
                        trial.phase = 'rng_full_anchor_recovery'
                        trial.call('load_anchor_stone', session.load_anchor_stone, start['anchor']['artifact'])
                        require(trial.state()['ds_sha256'] == report['seed_state']['ds_sha256'], 'Full Anchor recovery did not restore seed DS')
                        recovery_status = trial.call('timeline_status', session.timeline_status)
                        require(recovery_status.get('resume_safe') is True
                                and recovery_status.get('execution_allowed') is True,
                                'Full Anchor recovery did not clear mixed-state guard')
                        trial.call('timeline_stop', session.timeline_stop)
                        trial.timeline = False
                        probe['full_anchor_recovery_verified'] = True
                    finally:
                        probe['metrics'] = trial.report()
                        trial.finish()
                        persist()
                report['status'] = 'passed'
    except (Exception, KeyboardInterrupt) as error:
        report.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prior_signal)
        report['original_project_unchanged'] = sha(original_project) == original_sha
        report['prepared_receipt_unchanged'] = start_path.read_bytes() == start_bytes
        report['backend_unchanged'] = sha(backend) == BACKEND_SHA
        report['source_copy_unchanged'] = all((Path(start['game_dir'])/name).is_file()
            and sha(Path(start['game_dir'])/name) == digest for name, digest in start['source_manifest'].items())
        report['owned_native_reaped'] = process is not None and process.poll() is not None
        report['native_returncode'] = process.poll() if process is not None else None
        report['retained_file_bytes'] = footprint()
        report['completed_controller_frames'] = sum(a.get('metrics',{}).get('completed_frames',0) for a in report['arms']) + report.get('rng_safeguards',{}).get('metrics',{}).get('completed_frames',0)
        report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        if not all(report[k] for k in ('original_project_unchanged','prepared_receipt_unchanged','backend_unchanged','source_copy_unchanged','owned_native_reaped')):
            report['status'] = 'failed'
        if report['retained_file_bytes'] > args.max_new_bytes or report['completed_controller_frames'] > 512:
            report['status'] = 'failed'
        persist()
    print(json.dumps({'status': report['status'], 'report': str(report_path),
                      'owned_native_reaped': report['owned_native_reaped'],
                      'frames': report['completed_controller_frames'], 'file_bytes': report['retained_file_bytes']}), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
