#!/usr/bin/env python3
"""Bounded native checkpoint-history comparison using an authored DOS fixture.

Run from the selected checkout with its Python environment and PYTHONPATH=src:
    python scripts/benchmark_rewind.py --executable /absolute/dosbox-x \
        --output /private/new-benchmark --trials 3 --steps 12

Each trial compares one ordinary trace with checkpoint recording from the same
saved starting state in one live session. Rewinds move cumulatively back 1, 4,
and N next-fetch intervals, using relative counts 1, 3, and N-4. Direct-load
controls then restore the exact same three checkpoint artifacts. Verification
and setup restores are excluded from the measured restoration calls.

The private output retains the authored executable, project, native states and
traces. report.json contains individual timings, identities and state checks;
it is not a publication-sanitization certificate or a throughput guarantee.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import struct
import sys
import time
from datetime import datetime, timezone


# CLI; PUSH CS; POP DS; MOV AX,0100; MOV BX,3; MOV [0100],AX;
# ADD AX,BX; INC word [0100]; XOR AX,0055; MOV [0102],AX;
# INC BX; ADD word [0100],BX; NOP; JMP $.
CODE = bytes.fromhex('fa0e1fb80001bb0300a3000101d8ff060001355500a3020143011e000190ebfe')
PCS = (0, 1, 2, 3, 6, 9, 12, 14, 18, 21, 24, 25, 29)
MODULE = CODE.ljust(512, b'\0')
CPU_FIELDS = ('cpu_mode', 'general', 'segments', 'instruction_pointer', 'flags')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def integer(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fixture_bytes():
    """A complete 576-byte authored MZ, with stack and data inside its module."""
    header = bytearray(64)
    size = len(header) + len(MODULE)
    struct.pack_into('<14H', header, 0, 0x5a4d, size % 512, (size + 511) // 512,
                     0, 4, 0, 0xffff, 0, 0x1f0, 0, 0, 0, 28, 0)
    return bytes(header) + MODULE


def new_private_directory(value):
    path = Path(value).expanduser().absolute()
    require(not path.exists(), '--output must name a new directory')
    for parent in (path, *path.parents):
        require(not parent.is_symlink(), '--output must have no symlink ancestry')
        marker = parent / '.git'
        bare = (parent / 'HEAD').is_file() and (parent / 'objects').is_dir() and (parent / 'refs').is_dir()
        require(not marker.exists() and not marker.is_symlink() and not bare,
                '--output must be outside Git')
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    return path


def write_report(path, report):
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def timed(call):
    start = time.perf_counter_ns()
    result = call()
    return result, time.perf_counter_ns() - start


def cpu(registers):
    return {key: registers[key] for key in CPU_FIELDS}


def observe(session):
    registers = cpu(session.registers())
    ram = bytes.fromhex(session.memory('1000:0000', length=len(MODULE))['hex'])
    require(len(ram) == len(MODULE), 'Incomplete mapped-RAM observation')
    return {'cpu': registers, 'ram': ram}


def observation_record(snapshot):
    return {'cpu': snapshot['cpu'], 'mapped_ram_bytes': len(snapshot['ram']),
            'mapped_ram_sha256': digest(snapshot['ram'])}


def equal_state(left, right):
    result = {'cpu_equal': left['cpu'] == right['cpu'],
              'all_mapped_ram_equal': left['ram'] == right['ram']}
    require(all(result.values()), 'Restored CPU or mapped RAM differs from its control')
    return result


def expected_ram(initial, completed):
    # DOS has initialized the runtime stack before the paused MZ entry. Preserve
    # that observed baseline, then apply only the fixture's independent writes.
    data = bytearray(initial['ram'])
    if completed >= 2:
        registers = initial['cpu']
        require(integer(registers['segments']['ss']) == integer(registers['segments']['cs']),
                'Authored MZ requires SS=CS')
        sp = integer(registers['general']['esp']) & 0xffff
        require(sp == 0x1f0, 'Unexpected authored MZ starting SP')
        struct.pack_into('<H', data, sp - 2, integer(registers['segments']['cs']))
    word = 0x105 if completed >= 12 else 0x101 if completed >= 8 else 0x100 if completed >= 6 else 0
    struct.pack_into('<H', data, 0x100, word)
    struct.pack_into('<H', data, 0x102, 0x156 if completed >= 10 else 0)
    return bytes(data)


def verify_oracle(snapshot, initial, completed):
    registers = snapshot['cpu']
    require(initial['ram'][:len(CODE)] == CODE, 'Loaded authored code differs from its source')
    require(initial['ram'][0x100:0x104] == bytes(4), 'Authored data words must initially be zero')
    require(integer(initial['cpu']['general']['esp']) & 0xffff == 0x1f0,
            'Unexpected authored MZ starting SP')
    require(registers['cpu_mode'] == 'real', 'Fixture left real mode')
    require(integer(registers['instruction_pointer']) == PCS[completed],
            f'Unexpected PC after {completed} next-fetch intervals')
    require(registers['segments']['cs'] == initial['cpu']['segments']['cs'], 'CS changed')
    if completed >= 3:
        require(integer(registers['segments']['ds']) == integer(registers['segments']['cs']), 'DS must equal CS')
    if completed >= 4:
        ax = 0x156 if completed >= 9 else 0x103 if completed >= 7 else 0x100
        require(integer(registers['general']['eax']) & 0xffff == ax, 'AX oracle differs')
    if completed >= 5:
        require(integer(registers['general']['ebx']) & 0xffff == (4 if completed >= 11 else 3),
                'BX oracle differs')
    require(snapshot['ram'] == expected_ram(initial, completed), 'Full mapped-RAM oracle differs')


def pc_offset(value):
    require(isinstance(value, dict) and 'offset' in value, 'Expected a segmented PC record')
    return integer(value['offset'])


def export_trace(project, artifact, path, expected_pcs):
    project.debug_export(artifact, path)
    trace = json.loads(path.read_text())
    events = trace['events']
    require(trace['complete'] and len(events) == len(expected_pcs), 'Native trace is incomplete')
    require([pc_offset(event['address']) for event in events] == list(expected_pcs),
            'Native trace PC sequence differs from the authored sequence')
    require(events[-1]['observation']['instruction_completed'] is False,
            'Final trace fetch must remain explicitly unexecuted')
    return {'artifact': artifact, 'event_count': len(events), 'complete': True,
            'observed_pc_offsets': list(expected_pcs), 'last_fetch_unexecuted': True,
            'export_sha256': digest(path.read_bytes())}


def artifact_inventory(project):
    artifacts = project.debug_artifacts()['artifacts']
    states = [item for item in artifacts if item['kind'] == 'state']
    return {'artifact_count': len(artifacts), 'kinds': dict(Counter(a['kind'] for a in artifacts)),
            'state_artifact_count': len(states), 'logical_state_bytes': sum(a['size'] for a in states),
            'logical_all_artifact_bytes': sum(a['size'] for a in artifacts)}


def run_trial(project, session, initial_artifact, initial, trial, output, steps, timeout_ms,
              separate_trace_control, persist):
    trial.update(status='running', phase='plain-trace', steps=steps)
    session.load_state(initial_artifact)
    equal_state(observe(session), initial)
    plain, elapsed = timed(lambda: session.trace(f'plain-{trial["trial"]}.json', count=steps + 1,
                                               timeout_ms=timeout_ms, fast_forward=True))
    trial['plain_trace'] = {'elapsed_ns': elapsed, 'requested_fetches': steps + 1}
    persist()
    trial['plain_trace']['verification'] = export_trace(
        project, plain['artifact'], output / f'plain-{trial["trial"]}.json', PCS[:steps + 1])
    plain_end = observe(session)
    verify_oracle(plain_end, initial, steps)
    trial['plain_trace']['endpoint'] = observation_record(plain_end)

    if separate_trace_control:
        trial['phase'] = 'separate-trace-control'
        session.load_state(initial_artifact)
        samples = []
        trial['separate_trace_control'] = {'samples': samples}
        for index in range(steps):
            trace, duration = timed(lambda: session.trace(
                f'control-{trial["trial"]}-{index}.json', count=2, timeout_ms=timeout_ms,
                fast_forward=True))
            sample = {'interval': index + 1, 'elapsed_ns': duration}
            samples.append(sample)
            sample['verification'] = export_trace(project, trace['artifact'],
                output / f'control-{trial["trial"]}-{index}.json', PCS[index:index + 2])
            verify_oracle(observe(session), initial, index + 1)
            persist()
        trial['separate_trace_control']['total_elapsed_ns'] = sum(s['elapsed_ns'] for s in samples)

    trial['phase'] = 'record'
    session.load_state(initial_artifact)
    equal_state(observe(session), initial)
    trial['storage_before_record'] = artifact_inventory(project)
    trial['history_start'] = session.rewind_start(max_steps=16, max_bytes=64 * 1024 * 1024)
    recorded, elapsed = timed(lambda: session.rewind_record(count=steps, timeout_ms=timeout_ms))
    trial['recording'] = {'elapsed_ns': elapsed, 'requested_count': steps,
                          'result': recorded, 'record_vs_plain_ratio': elapsed / trial['plain_trace']['elapsed_ns']}
    persist()
    require(recorded['recorded_count'] == steps and recorded['cursor'] == steps,
            'Recording stopped before the declared interval budget')
    records = recorded['records']
    require(len(records) == steps, 'Recording did not retain every interval')
    for index, point in enumerate(records):
        require(pc_offset(point['before_pc']) == PCS[index] and pc_offset(point['after_pc']) == PCS[index + 1],
                'Recorded next-fetch boundaries differ from the authored sequence')
        export_trace(project, point['trace_artifact'],
                     output / f'recorded-{trial["trial"]}-{index}.json', PCS[index:index + 2])
    recorded_end = observe(session)
    verify_oracle(recorded_end, initial, steps)
    trial['recording']['endpoint'] = observation_record(recorded_end)
    trial['recording']['same_endpoint_as_plain'] = equal_state(recorded_end, plain_end)
    trial['storage_after_record'] = artifact_inventory(project)
    trial['history_after_record'] = session.rewind_status()
    persist()

    trial['phase'] = 'rewind'
    rewind_samples = []
    trial['restores'] = rewind_samples
    previous_depth = 0
    for depth in (1, 4, steps):
        relative = depth - previous_depth
        target_cursor = steps - depth
        checkpoint = records[target_cursor]['checkpoint']
        sample = {'relative_rewind_count': relative, 'cumulative_depth_from_recorded_end': depth,
                  'expected_cursor': target_cursor, 'checkpoint': checkpoint, 'status': 'running'}
        rewind_samples.append(sample)
        result, elapsed = timed(lambda: session.rewind(count=relative))
        sample.update(rewind_elapsed_ns=elapsed, rewind_result=result)
        persist()
        require(result['rewound_count'] == relative and result['cursor'] == target_cursor,
                'Rewind selected the wrong history position')
        require(result['target_checkpoint']['artifact'] == checkpoint['artifact'],
                'Rewind selected a different checkpoint artifact')
        restored = observe(session)
        verify_oracle(restored, initial, target_cursor)
        sample['rewind_observation'] = observation_record(restored)
        sample['_snapshot'] = restored
        sample['rewind_verified'] = True
        previous_depth = depth
        persist()

    # Direct loads intentionally invalidate history. Run them only after all
    # cumulative rewinds, and restore the identical selected artifacts.
    trial['phase'] = 'direct-load-controls'
    for sample in rewind_samples:
        result, elapsed = timed(lambda: session.load_state(sample['checkpoint']['artifact']))
        sample.update(direct_load_elapsed_ns=elapsed, direct_load_result=result)
        persist()
        require(result['sha256'] == sample['checkpoint']['sha256'], 'Direct load used different native bytes')
        restored = observe(session)
        verify_oracle(restored, initial, sample['expected_cursor'])
        sample['direct_load_observation'] = observation_record(restored)
        sample['equality'] = equal_state(restored, sample['_snapshot'])
        sample['rewind_vs_direct_load_ratio'] = sample['rewind_elapsed_ns'] / elapsed
        sample['status'] = 'passed'
        persist()
    trial.update(status='passed', phase='complete', history_after_controls=session.rewind_status())
    trial['storage_after_trial'] = artifact_inventory(project)
    persist()


def serializable(value):
    """Keep in-memory RAM comparisons out of the JSON receipt."""
    if isinstance(value, dict):
        return {key: serializable(item) for key, item in value.items() if not key.startswith('_')}
    if isinstance(value, list):
        return [serializable(item) for item in value]
    return value


def summary(trials):
    complete = [trial for trial in trials if trial['status'] == 'passed']
    if not complete:
        return {'completed_trials': 0}
    result = {'completed_trials': len(complete),
              'plain_trace_median_ns': statistics.median(t['plain_trace']['elapsed_ns'] for t in complete),
              'recording_median_ns': statistics.median(t['recording']['elapsed_ns'] for t in complete),
              'record_vs_plain_median_ratio': statistics.median(t['recording']['record_vs_plain_ratio'] for t in complete),
              'restore_groups': []}
    for depth in (1, 4, complete[0]['steps']):
        samples = [s for t in complete for s in t['restores']
                   if s['cumulative_depth_from_recorded_end'] == depth]
        result['restore_groups'].append({'cumulative_depth': depth,
            'relative_rewind_count': samples[0]['relative_rewind_count'], 'samples': len(samples),
            'rewind_median_ns': statistics.median(s['rewind_elapsed_ns'] for s in samples),
            'same_artifact_direct_load_median_ns': statistics.median(s['direct_load_elapsed_ns'] for s in samples),
            'rewind_vs_direct_load_median_ratio': statistics.median(s['rewind_vs_direct_load_ratio'] for s in samples),
            'all_cpu_and_mapped_ram_equal': all(all(s['equality'].values()) for s in samples)})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--executable', type=Path, required=True, help='explicit native DOSBox-X backend')
    parser.add_argument('--output', required=True, help='new private output directory outside Git')
    parser.add_argument('--trials', type=int, choices=range(1, 6), default=3)
    parser.add_argument('--steps', type=int, choices=range(8, 13), default=12)
    parser.add_argument('--timeout-ms', type=int, default=10000)
    parser.add_argument('--separate-trace-control', action='store_true',
                        help='also time N separate trace(count=2) calls per trial')
    args = parser.parse_args(argv)
    require(1 <= args.timeout_ms <= 60000, '--timeout-ms must be in 1..60000')
    backend = args.executable.expanduser().resolve(strict=True)
    require(backend.is_file() and os.access(backend, os.X_OK), '--executable must name an executable file')
    output = new_private_directory(args.output)
    report_path = output / 'report.json'
    report = {'format': 'fdisbull-native-rewind-benchmark-1', 'status': 'running',
              'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version(),
              'backend': {'path': str(backend), 'size': backend.stat().st_size,
                          'sha256': digest(backend.read_bytes())},
              'configuration': {'trials': args.trials, 'steps': args.steps, 'max_history_steps': 16,
                                'max_history_bytes': 64 * 1024 * 1024,
                                'separate_trace_control': args.separate_trace_control},
              'claim_boundary': 'Bounded authored-fixture microbenchmark; full native checkpoint history, not inverse execution. '
                                'Units are next-fetch intervals; general instruction completion remains unknown. '
                                'Recording/restore timings exclude setup and state verification; ratios are observations, not guarantees.',
              'cpu_comparison_fields': list(CPU_FIELDS), 'trials': []}
    persist = lambda: write_report(report_path, serializable(report))
    old_store = os.environ.get('FDISBULL_TARGET_STORE')
    os.environ['FDISBULL_TARGET_STORE'] = str(output / 'target-objects')
    try:
        persist()
        from fdisbull.project import Project
        guest = output / 'guest'
        guest.mkdir(mode=0o700)
        binary = guest / 'REWIND.EXE'
        data = fixture_bytes()
        binary.write_bytes(data)
        report['fixture'] = {'source': 'authored inline MZ fixture in this benchmark script',
                             'bytes': len(data), 'sha256': digest(data), 'mapped_ram_bytes': len(MODULE),
                             'expected_pc_offsets': list(PCS[:args.steps + 1]),
                             'no_guest_file_writes': True}
        repo = Path(__file__).resolve().parents[1]
        report['implementation_files'] = {str(path.relative_to(repo)): digest(path.read_bytes())
            for path in (Path(__file__).resolve(), repo / 'src/fdisbull/debug_rewind.py',
                         repo / 'src/fdisbull/debugger.py') if path.is_file()}
        with Project.create(output / 'benchmark.fdb', binary) as project:
            project.analyze(max_instructions=32)
            with project.debugger(backend, guest, version=1) as session:
                require(session.rpc.capabilities.get('save_states'), 'Selected backend lacks native save states')
                for method in ('rewind_start', 'rewind_record', 'rewind', 'rewind_status'):
                    require(callable(getattr(session, method, None)), f'Required API is unavailable: {method}')
                initial = observe(session)
                verify_oracle(initial, initial, 0)
                report['initial_state'] = observation_record(initial)
                report['initial_state']['authored_code_verified'] = True
                report['initial_state']['authored_data_words_zero'] = True
                report['initial_state']['runtime_differs_from_file_at_offsets'] = [
                    offset for offset, (loaded, authored) in enumerate(zip(initial['ram'], MODULE))
                    if loaded != authored]
                saved = session.save_state('initial.sav')
                report['initial_checkpoint'] = {key: saved[key] for key in ('artifact', 'sha256', 'size')}
                report['native_capabilities'] = session.rpc.capabilities
                report['session_metadata'] = session.metadata
                persist()
                for number in range(1, args.trials + 1):
                    trial = {'trial': number, 'status': 'pending'}
                    report['trials'].append(trial)
                    try:
                        run_trial(project, session, saved['artifact'], initial, trial, output,
                                  args.steps, args.timeout_ms, args.separate_trace_control, persist)
                    except Exception as error:
                        trial.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
                        trial['history_on_failure'] = session.rewind_status()
                        trial['storage_on_failure'] = artifact_inventory(project)
                        persist()
                        raise
                report['storage'] = artifact_inventory(project)
        objects = [p for p in (output / 'target-objects').iterdir() if p.is_file()]
        report['external_store'] = {'object_count': len(objects), 'bytes_on_disk': sum(p.stat().st_size for p in objects)}
        report['status'] = 'passed'
    except KeyboardInterrupt:
        report.update(status='interrupted', error={'type': 'KeyboardInterrupt', 'message': 'Benchmark interrupted'})
    except Exception as error:
        report.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
    finally:
        if old_store is None:
            os.environ.pop('FDISBULL_TARGET_STORE', None)
        else:
            os.environ['FDISBULL_TARGET_STORE'] = old_store
        report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        report['summary'] = summary(report['trials'])
        persist()
    print(json.dumps({'status': report['status'], 'report': str(report_path), 'summary': report['summary']}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
