#!/usr/bin/env python3
"""Public path-parameterized derivative of the private finite macOS JPC-RR controller.

Default invocation validates and prints a plan. --execute starts one owned JVM.
The unchanged ZIP HeadlessAuthor is the front end; the stock core is not edited.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import signal
import statistics
import subprocess
import sys
import time

EXPECTED_JAR = 'be63fea4c746ec3823432b7e2ef27b19b75a25a4bcbbc124f4683d99c4f4d314'
MEDIA = {
    'KQ1': 'bd183c472bf2c054bfa944a768f10592',
    'ELPIN-2.40': '5555c682e62336cb37eb17c903322be1',
    'FREEDOS': 'f334bc4d5dc5f393feb0ca2d1e1cdc25',
    'BIOS-REL_2_6_9_FINAL': '740f01be58103af0996220bdeb7c4d12',
}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def metrics(values):
    if not values:
        return {'count': 0}
    ordered = sorted(values)
    return {'count': len(values), 'median_ms': statistics.median(values),
            'p95_ms': ordered[max(0, math.ceil(.95 * len(values)) - 1)],
            'min_ms': ordered[0], 'max_ms': ordered[-1]}


def fingerprint(paths):
    return {str(path): {'bytes': path.stat().st_size, 'sha256': sha256(path)} for path in paths}


def checked(condition, message):
    if not condition:
        raise RuntimeError(message)


class Author:
    def __init__(self, args, report):
        self.args, self.report = args, report
        self.process = None
        self.buffer = b''
        self.started = time.monotonic()
        self.log = (args.out / 'native.log').open('xb')
        self.raw = (args.out / 'protocol.stdout.jsonl').open('xb')
        self.rows = (args.out / 'commands.jsonl').open('x')
        self.command_count = 0

    def bounds(self):
        if time.monotonic() - self.started > self.args.total_timeout:
            raise TimeoutError('Total benchmark host timeout exceeded')
        size = sum(p.stat().st_size for p in self.args.out.rglob('*') if p.is_file())
        if size > self.args.max_new_bytes:
            raise RuntimeError('Output exceeded admitted estimate; stop before further growth')

    def launch(self):
        command = [str(self.args.java), '-Xmx512m', '-Djava.awt.headless=true', '-cp',
                   str(self.args.classes) + os.pathsep + str(self.args.jar),
                   'kq1tas.HeadlessAuthor', '--library', str(self.args.library)]
        self.report['command_argv'] = command
        env = os.environ.copy()
        env['TMPDIR'] = str(self.args.temp_root)
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.log, start_new_session=True, env=env, cwd=self.args.run_root)
        self.report['pid'] = self.process.pid
        result = self.reply(self.args.command_timeout)
        checked(result.get('ok') and result.get('event') == 'ready', 'Missing author ready reply')
        self.report['ready'] = result

    def reply(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            self.bounds()
            if b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                result = json.loads(line)
                checked(isinstance(result, dict), 'Protocol reply is not an object')
                return result
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Bounded author command reply timeout')
            ready, _, _ = select.select([self.process.stdout], [], [], min(remaining, .1))
            if not ready:
                continue
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError('Author exited before reply: ' + str(self.process.poll()))
            self.raw.write(chunk)
            self.raw.flush()
            self.buffer += chunk
            checked(len(self.buffer) <= 1048576, 'Protocol line exceeded 1 MiB')

    def command(self, *fields):
        self.bounds()
        strings = [str(f) for f in fields]
        checked(all(not any(c in f for c in '\t\r\n') for f in strings), 'Invalid protocol field')
        started = time.monotonic_ns()
        self.process.stdin.write(('\t'.join(strings) + '\n').encode())
        self.process.stdin.flush()
        result = self.reply(self.args.command_timeout)
        row = {'index': self.command_count, 'fields': strings, 'reply': result,
               'roundtrip_ms': (time.monotonic_ns() - started) / 1e6}
        self.command_count += 1
        self.rows.write(json.dumps(row, sort_keys=True) + '\n')
        self.rows.flush()
        checked(result.get('ok') is True, 'Author rejected command: ' + json.dumps(row))
        checked(result.get('command') == strings[0], 'Protocol command/reply mismatch')
        self.bounds()
        return result, row['roundtrip_ms']

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                try:
                    self.command('quit')
                    self.process.wait(timeout=5)
                except BaseException as error:
                    self.report['graceful_shutdown_error'] = type(error).__name__ + ': ' + str(error)
            if self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    self.process.wait(timeout=5)
            self.report['exit_code'] = self.process.returncode
            self.report['process_reaped'] = self.process.poll() is not None
            self.process.stdin.close()
            self.process.stdout.close()
        else:
            self.report['process_reaped'] = True
        self.log.close()
        self.raw.close()
        self.rows.close()


def observation(author, label, snapshot=False):
    start = time.monotonic_ns()
    info, info_ms = author.command('info')
    registers, registers_ms = author.command('registers')
    address = author.args.observe_address
    if address is None:
        checked(isinstance(registers.get('ds'), dict), 'DS register base is unavailable')
        address = registers['ds']['base']
    checked(0 <= address and address + author.args.observe_bytes <= 0xA0000,
            'DS observation is outside passive conventional RAM')
    memory, read_ms = author.command('read', hex(address), author.args.observe_bytes)
    projection = {'time_ns': info['time_ns'], 'frame': info['frame'],
                  'ram_address': address, 'ram_bytes': author.args.observe_bytes,
                  'ram_sha256': hashlib.sha256(bytes.fromhex(memory['hex'])).hexdigest(),
                  'registers': {k: v for k, v in registers.items() if k not in ('ok', 'command')},
                  'pressed_keys': info['pressed_keys']}
    stages = {'info': info_ms, 'registers': registers_ms, 'paused_ram_read': read_ms}
    if snapshot:
        path = author.args.out / (label + '.png')
        _, stages['native_png_capture'] = author.command('snapshot', path)
        projection['png_sha256'] = sha256(path)
    return {'info': info, 'projection': projection, 'native_stage_ms': stages,
            'ram_observation_scope': 'One stock read reply while guest is paused; physical base from current DS unless overridden',
            'observation_ms': (time.monotonic_ns() - start) / 1e6}


def dispatched(info, sequence):
    current = info['next_event_sequence']
    return current == -1 or current > sequence


def next_frame(author):
    result, elapsed = author.command('next_frame', author.args.advance_host_ms)
    checked(result.get('reason') == 'frame', 'Frame step did not stop at a native retrace: ' + json.dumps(result))
    checked(result['frame'] > result['start_frame'], 'Native frame counter did not advance')
    return result, elapsed


def input_segment(author, frames, label, snapshot=False, history=False):
    before, _ = author.command('info')
    checked(author.args.scan_code not in before['pressed_keys'], 'Test key is held at segment start')
    checked(before['next_event_sequence'] == -1, 'Unexpected pending inputs before new segment')
    start = time.monotonic_ns()
    make, make_ms = author.command('keyedge', author.args.scan_code, before['time_ns'])
    release, release_ms = author.command('keyedge', author.args.scan_code,
                                        make['scheduled_ns'] + author.args.hold_ns)
    waits = []
    info = before
    for _ in range(frames + author.args.max_extra_frames):
        info, elapsed = next_frame(author)
        waits.append({'roundtrip_ms': elapsed, 'reply': info})
        if info['frame'] >= before['frame'] + frames and dispatched(info, release['sequence']):
            break
    checked(dispatched(info, release['sequence']), 'Release event did not dispatch within frame bound')
    checked(author.args.scan_code not in info['pressed_keys'], 'Key remained pressed after release dispatch')
    checked(info['frame'] >= before['frame'] + frames, 'Requested native frame count was not reached')
    checkpoint = None
    if history and author.args.checkpoint_every_sample:
        path = author.args.out / (label + '-history.jrsr')
        _, save_ms = author.command('save_state', path)
        checkpoint = {'path': str(path), 'save_ms': save_ms, 'bytes': path.stat().st_size,
                      'sha256': sha256(path), 'owner': 'external Python controller; native whole-machine JRSR'}
    observed = observation(author, label, snapshot)
    elapsed = (time.monotonic_ns() - start) / 1e6
    first = waits[0]['reply']
    return {'total_ms': elapsed, 'make_reply_ms': make_ms, 'break_reply_ms': release_ms,
            'make': make, 'break': release, 'native_frame_waits': waits,
            'first_frame_ms': waits[0]['roundtrip_ms'], 'extra_frame_wait_ms': sum(w['roundtrip_ms'] for w in waits[1:]),
            'requested_frames': frames, 'actual_frames': info['frame'] - before['frame'],
            'actual_emulated_ns': info['time_ns'] - before['time_ns'],
            'first_wait_exactly_one_frame': first['frame'] - before['frame'] == 1,
            'release_dispatched_at_first_frame': dispatched(first, release['sequence']),
            'recorder_edges_accepted': 2, 'recorder_edges_dispatched': 2,
            'keyboard_released': True, 'guest_game_consumption': 'unknown', 'observation': observed,
            'external_history_checkpoint': checkpoint}


def run_benchmark(author, report):
    args = author.args
    author.launch()
    author.command('load', args.movie, 'movie')
    advanced, _ = author.command('run_until_ns', args.start_ns, args.advance_host_ms)
    checked(advanced['reason'] == 'target' and advanced['time_ns'] >= args.start_ns,
            'Initial movie advance did not reach its target')
    report['branch'] = author.command('truncate_future')[0]
    checked(report['branch']['next_event_sequence'] == -1, 'Future movie input remained after truncation')
    report['branch_native_log_offset'] = (args.out / 'native.log').stat().st_size
    for i in range(args.warmup):
        input_segment(author, 1, f'warmup-{i}', snapshot=args.capture_every_sample, history=True)
    samples = report['warm_loop_samples'] = []
    for i in range(args.samples):
        row = input_segment(author, 1, f'warm-{i}', snapshot=args.capture_every_sample, history=True)
        samples.append(row)
        print(json.dumps({'event': 'warm_sample', 'sample': i, 'total_ms': row['total_ms'],
                          'frames': row['actual_frames']}), flush=True)
    anchor = args.out / 'retry-anchor.jrsr'
    saved, save_ms = author.command('save_state', anchor)
    baseline = observation(author, 'retry-anchor', True)
    report['anchor'] = {'path': str(anchor), 'save_ms': save_ms, 'reply': saved,
                        'bytes': anchor.stat().st_size, 'sha256': sha256(anchor), 'observation': baseline}
    retries = report['recent_frame_retries'] = []
    for frames in args.depths:
        for trial in range(args.trials):
            label = f'depth-{frames}-trial-{trial}'
            _, baseline_load_ms = author.command('load', anchor, 'state')
            restored = observation(author, label + '-anchor', True)
            checked(restored['projection'] == baseline['projection'], 'Anchor observable projection did not restore')
            first = input_segment(author, frames, label + '-first', True)
            endpoint = args.out / (label + '-endpoint.jrsr')
            _, endpoint_save_ms = author.command('save_state', endpoint)
            retry_started = time.monotonic_ns()
            _, retry_load_ms = author.command('load', anchor, 'state')
            second = input_segment(author, frames, label + '-repeat', True)
            retry_total_ms = (time.monotonic_ns() - retry_started) / 1e6
            checked(first['observation']['projection'] == second['observation']['projection'],
                    'Repeated input/frame segment observable projection diverged')
            # Move away from the endpoint before timing its native restore.
            next_frame(author)
            _, endpoint_load_ms = author.command('load', endpoint, 'state')
            endpoint_restored = observation(author, label + '-endpoint-restored', True)
            checked(endpoint_restored['projection'] == first['observation']['projection'],
                    'Endpoint native restore observable projection diverged')
            row = {'frames': frames, 'trial': trial, 'baseline_load_ms': baseline_load_ms,
                   'retry_anchor_load_ms': retry_load_ms, 'retry_total_ms': retry_total_ms,
                   'endpoint_save_ms': endpoint_save_ms, 'endpoint_load_ms': endpoint_load_ms,
                   'endpoint_bytes': endpoint.stat().st_size, 'endpoint_sha256': sha256(endpoint),
                   'first': first, 'repeat': second,
                   'anchor_projection_match': True, 'repeat_projection_match': True,
                   'endpoint_restore_projection_match': True}
            retries.append(row)
            print(json.dumps({'event': 'retry_trial', 'frames': frames, 'trial': trial,
                              'retry_total_ms': retry_total_ms, 'endpoint_load_ms': endpoint_load_ms}), flush=True)
    report['summary'] = {
        'warm_total': metrics([r['total_ms'] for r in samples]),
        'make_acceptance': metrics([r['make_reply_ms'] for r in samples]),
        'break_acceptance': metrics([r['break_reply_ms'] for r in samples]),
        'first_native_frame_wait': metrics([r['first_frame_ms'] for r in samples]),
        'extra_native_frame_wait': metrics([r['extra_frame_wait_ms'] for r in samples]),
        'observation': metrics([r['observation']['observation_ms'] for r in samples]),
        'native_paused_ram_read': metrics([r['observation']['native_stage_ms']['paused_ram_read'] for r in samples]),
        'native_register_read': metrics([r['observation']['native_stage_ms']['registers'] for r in samples]),
        'native_png_capture': metrics([r['observation']['native_stage_ms']['native_png_capture'] for r in samples
                                       if 'native_png_capture' in r['observation']['native_stage_ms']]),
        'external_native_history_save': metrics([r['external_history_checkpoint']['save_ms'] for r in samples
                                                if r['external_history_checkpoint'] is not None]),
        'first_frame_release_dispatched_count': sum(r['release_dispatched_at_first_frame'] for r in samples),
        'exactly_one_frame_sample_count': sum(r['actual_frames'] == 1 for r in samples),
        'accepted_edges': 2 * len(samples), 'dispatched_edges': 2 * len(samples),
        'per_depth': {str(d): {
            'native_endpoint_load': metrics([r['endpoint_load_ms'] for r in retries if r['frames'] == d]),
            'native_endpoint_save': metrics([r['endpoint_save_ms'] for r in retries if r['frames'] == d]),
            'anchor_load_and_repeat_with_observation': metrics([r['retry_total_ms'] for r in retries if r['frames'] == d]),
            'repeat_segment_with_observation': metrics([r['repeat']['total_ms'] for r in retries if r['frames'] == d]),
        } for d in args.depths}}


def arguments():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--java', type=Path, required=True)
    p.add_argument('--jar', type=Path, required=True)
    p.add_argument('--library', type=Path, required=True)
    p.add_argument('--classes', type=Path, required=True)
    p.add_argument('--movie', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True, help='New output directory under the caller private run root')
    p.add_argument('--start-ns', type=int, default=3_000_000_000)
    p.add_argument('--scan-code', type=int, default=30, help='Stock scan code; default A, two toggling edges per sample')
    p.add_argument('--hold-ns', type=int, default=1_000_000, help='Requested lower-bound spacing; stock core chooses actual times')
    p.add_argument('--warmup', type=int, default=5)
    p.add_argument('--samples', type=int, default=30)
    p.add_argument('--depths', type=lambda s: [int(x) for x in s.split(',')], default=[1, 3, 5])
    p.add_argument('--trials', type=int, default=3)
    p.add_argument('--max-extra-frames', type=int, default=8)
    p.add_argument('--observe-address', type=lambda s: int(s, 0), default=None,
                   help='Physical address override; default reads from the current DS segment base')
    p.add_argument('--observe-bytes', '--observation-bytes', type=int, default=65536)
    p.add_argument('--capture-every-sample', action='store_true', help='Include native PNG in each warm loop')
    p.add_argument('--checkpoint-every-sample', action='store_true',
                   help='Save a native full state per warm loop; external controller history, no built-in rewind claim')
    p.add_argument('--advance-host-ms', type=int, default=30_000)
    p.add_argument('--command-timeout', type=float, default=35)
    p.add_argument('--total-timeout', type=float, default=300)
    p.add_argument('--max-new-bytes', type=int, default=134_217_728)
    p.add_argument('--destination-reserve-bytes', type=int, default=20_000_000_000,
                   help='Existing authorization for this task permits the 20 GB reserve')
    p.add_argument('--run-root', type=Path, required=True, help='Existing authorized private external workspace')
    p.add_argument('--temp-root', type=Path, required=True, help='Existing external temporary directory under run root')
    p.add_argument('--author-source', type=Path, required=True, help='Source matching the compiled HeadlessAuthor class')
    p.add_argument('--storage-admit', type=Path, required=True, help='Caller storage-admission helper')
    p.add_argument('--execute', action='store_true', help='Start guest; omit for a read-only plan')
    return p.parse_args()


def main():
    args = arguments()
    for field in ('java', 'jar', 'library', 'classes', 'movie', 'out', 'run_root', 'temp_root', 'author_source', 'storage_admit'):
        setattr(args, field, getattr(args, field).resolve())
    checked(args.run_root.is_dir() and args.temp_root.is_dir()
            and args.temp_root.is_relative_to(args.run_root), 'Existing external run/temp roots are required')
    for ancestor in (args.run_root, *args.run_root.parents):
        checked(not ancestor.is_symlink() and not (ancestor / '.git').exists(), 'Private runtime root must be outside Git and symlink ancestry')
    checked(args.out.is_relative_to(args.run_root) and not args.out.exists(), 'Output must be a new directory under the caller private run root')
    checked(0 < args.start_ns <= 60_000_000_000, 'Start target must be 1..60e9 ns')
    checked(0 <= args.warmup <= 100 and 1 <= args.samples <= 1000 and 1 <= args.trials <= 20, 'Invalid finite sample bounds')
    checked(args.depths and all(1 <= d <= 120 for d in args.depths) and len(set(args.depths)) == len(args.depths), 'Invalid frame depths')
    checked(1 <= args.max_extra_frames <= 120 and 0 < args.hold_ns <= 100_000_000, 'Invalid frame/input bounds')
    checked(args.observe_bytes > 0 and args.observe_bytes <= 0xA0000 and
            (args.observe_address is None or 0 <= args.observe_address and args.observe_address + args.observe_bytes <= 0xA0000),
            'Observation must remain inside conventional RAM')
    checked(1 <= args.advance_host_ms <= 60_000 and args.command_timeout > args.advance_host_ms / 1000,
            'Command deadline must exceed cooperative core advance budget')
    checked(args.total_timeout > args.command_timeout and args.total_timeout <= 3600 and args.command_timeout <= 70,
            'Invalid finite host deadlines')
    checked(0 < args.max_new_bytes <= 536_870_912 and args.destination_reserve_bytes >= 20_000_000_000,
            'Allocation must be 1..512 MiB with at least 20 GB reserve')
    checked((1 <= args.scan_code <= 83 or 85 <= args.scan_code <= 95 or
             129 <= args.scan_code <= 197 or 199 <= args.scan_code <= 223), 'Unsupported stock scan code')
    helper = args.classes / 'kq1tas/HeadlessAuthor.class'
    source = args.author_source
    inputs = [args.java, args.jar, helper, source, args.movie, Path(__file__).resolve()]
    for name, expected in MEDIA.items():
        path = args.library / name
        with path.open('rb') as stream:
            header = stream.read(24)
        checked(header[:5] == b'IMAGE' and header[5:21].hex() == expected, 'Required media ID mismatch: ' + name)
        inputs.append(path)
    identities = fingerprint(inputs)
    checked(identities[str(args.jar)]['sha256'] == EXPECTED_JAR, 'Stock r11.2 JAR identity mismatch')
    plan = {'format': 'jpcrr-private-warm-loop-1', 'execute_requested': args.execute,
            'parameters': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
            'input_identities': identities,
            'claim_limits': [
                'KEYEDGE acceptance and recorder dispatch do not prove BIOS, DOS or game consumption.',
                'One frame means native VGA retrace; no 60 Hz or AGI logic-cycle assumption.',
                'Frame boundary is TRACE_STOP_VRETRACE_START after stock display update; it differs from a completed renderer-frame boundary.',
                'Per-sample checkpoints are history maintained by this external Python controller, not built-in delta rewind.',
                'Restore equality checks time, frame, conventional-RAM region, exposed registers, pressed keys and PNG only.',
                'Native checkpoints retain wider machine state; sampled projection equality is not whole-machine equivalence.',
                'Warm loop excludes JVM startup/movie warmup; retry timings name load, frame execution and observation separately.',
                'This branched benchmark is separate from stock four-replay qualification and makes no full TAS parity claim.',
            ]}
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    admitted = subprocess.run([sys.executable, str(args.storage_admit), '--path', str(args.run_root),
        '--expected-bytes', str(args.max_new_bytes), '--destination-reserve-bytes', str(args.destination_reserve_bytes)],
        capture_output=True, text=True, timeout=15)
    checked(admitted.returncode == 0, 'Storage admission rejected new benchmark output: ' + admitted.stdout + admitted.stderr)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'storage-admission.json').write_text(admitted.stdout)
    report = dict(plan, complete=False, storage_admission=json.loads(admitted.stdout))
    author = Author(args, report)
    error = None
    started = time.monotonic_ns()
    try:
        run_benchmark(author, report)
        report['measurements_finished'] = True
    except BaseException as failure:
        error = failure
        report['error'] = {'type': type(failure).__name__, 'message': str(failure)}
    finally:
        try:
            author.close()
        except BaseException as failure:
            report['cleanup_error'] = {'type': type(failure).__name__, 'message': str(failure)}
            error = error or failure
        report['elapsed_host_ns'] = time.monotonic_ns() - started
        native_text = (args.out / 'native.log').read_text(errors='replace')
        report['critical_native_log_lines'] = [line for line in native_text.splitlines() if
            any(marker in line for marker in ('Critical:', 'Error: Event dispatch failed.',
                                              'Exception in thread', 'OutOfMemoryError'))]
        if 'branch_native_log_offset' in report:
            with (args.out / 'native.log').open('rb') as stream:
                stream.seek(report['branch_native_log_offset'])
                branch_text = stream.read().decode(errors='replace')
            report['executed_test_key_log_counts'] = {
                kind: len(re.findall(r'Executing key' + kind + r' on ' + str(args.scan_code) + r'\.', branch_text))
                for kind in ('Press', 'Release')}
            expected_each = args.warmup + args.samples + 2 * len(args.depths) * args.trials
            report['expected_executed_test_key_log_count_each'] = expected_each
            report['executed_test_key_log_counts_match'] = all(
                n == expected_each for n in report['executed_test_key_log_counts'].values())
        report['input_identities_after'] = fingerprint(inputs)
        report['inputs_unchanged'] = report['input_identities_after'] == identities
        report['complete'] = bool(report.get('measurements_finished') and report.get('process_reaped') and
                                  report.get('exit_code') == 0 and report['inputs_unchanged'] and error is None and
                                  not report['critical_native_log_lines'] and
                                  report.get('executed_test_key_log_counts_match'))
        report['artifact_identities'] = fingerprint(sorted(p for p in args.out.rglob('*') if p.is_file()))
        (args.out / 'benchmark-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'complete': report['complete'], 'process_reaped': report.get('process_reaped'),
                      'result': str(args.out / 'benchmark-result.json'), 'summary': report.get('summary'),
                      'error': report.get('error')}), flush=True)
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
