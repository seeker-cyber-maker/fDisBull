#!/usr/bin/env python3
"""Compare native checkpoints with a bounded CPU/selected-RAM delta projection.

Run with the selected checkout's dependencies and PYTHONPATH=src:
    python scripts/benchmark_cpu_deltas.py --executable /absolute/dosbox-x \
        --output /private/new-comparison --trials 3 --steps 12

One live session and one saved initial state serve every comparison arm. Each
trial records twelve next-fetch intervals once per mode, then unwinds relative
counts 1, 3, 8 (cumulative depths 1, 4, 12). Direct native loads use the exact
checkpoint artifacts selected by MR14. Delta recovery precedes every direct
load or later recording arm. The two recording modes alternate order by trial;
plain trace runs first and direct-load controls run last in every trial.

Delta undo restores only exposed registers and the declared 512-byte module.
Devices, other RAM and hidden CPU state are unverified. Ordinary execution must
remain blocked after delta undo until full native anchor recovery. This is a
bounded microbenchmark, not whole-machine reverse execution or a speed promise.
Private outputs retain authored inputs, project, states, deltas and traces.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import statistics

from benchmark_rewind import (
    CPU_FIELDS, MODULE, PCS, artifact_inventory, digest, equal_state,
    export_trace, fixture_bytes, new_private_directory, observation_record,
    observe, pc_offset, require, serializable, timed, verify_oracle, write_report,
)


STEPS = 12
DEPTHS = (1, 4, STEPS)
RANGES = [{'address': '1000:0000', 'length': len(MODULE)}]
MAX_BYTES = 64 * 1024 * 1024
MODES = ('native_checkpoints', 'cpu_ram_deltas')


def artifact_map(project):
    return {item['id']: item for item in project.debug_artifacts()['artifacts']}


def check_reference(reference, artifacts):
    item = artifacts.get(reference['artifact'])
    require(item is not None, 'Recording references an absent artifact')
    require(item['sha256'] == reference['sha256'] and item['size'] == reference['size'],
            'Recording artifact identity or byte count differs from stored metadata')


def recording_storage(project, before, started, recorded, mode):
    artifacts = artifact_map(project)
    added = [item for identifier, item in artifacts.items() if identifier not in before]
    keys = Counter(item['kind'] for item in added)
    payloads = ([point['checkpoint'] for point in recorded['records']]
                if mode == MODES[0] else [point['delta'] for point in recorded['records']])
    anchor = started['anchor'] if mode == MODES[1] else None
    for reference in payloads + ([anchor] if anchor else []):
        check_reference(reference, artifacts)
    require(len({item['artifact'] for item in payloads}) == STEPS,
            'Recording did not retain twelve distinct step artifacts')
    step_bytes = sum(item['size'] for item in payloads)
    anchor_bytes = anchor['size'] if anchor else 0
    unique = {item['sha256']: item['size'] for item in payloads + ([anchor] if anchor else [])}
    result = {
        'step_payload_count': len(payloads), 'step_payload_bytes_without_anchor': step_bytes,
        'anchor_count': int(anchor is not None), 'anchor_bytes': anchor_bytes,
        'payload_bytes_including_anchor': step_bytes + anchor_bytes,
        'unique_payload_sha256_count': len(unique), 'unique_payload_bytes': sum(unique.values()),
        'new_artifact_count': len(added), 'new_artifact_kinds': dict(keys),
        'new_artifact_bytes_including_traces': sum(item['size'] for item in added),
        'new_trace_artifact_bytes': sum(item['size'] for item in added if item['kind'] == 'trace'),
        'accounting': 'Logical artifact payload sizes; unique SHA totals are not filesystem allocation.',
    }
    if mode == MODES[1]:
        status = recorded['history']
        require(status['anchor_bytes_used'] == anchor_bytes and status['delta_bytes_used'] == step_bytes
                and status['total_bytes_used'] == anchor_bytes + step_bytes,
                'Delta history byte accounting differs from retained artifacts')
        result['delta_payload_count'] = len(payloads)
        result['delta_payload_bytes_without_anchor'] = step_bytes
        result['delta_payload_bytes_including_anchor'] = step_bytes + anchor_bytes
    return result


def frozen_execution_check(session, snapshot, trial_number, depth, timeout_ms):
    """A public execution request must fail before changing the projection."""
    try:
        session.trace(f'forbidden-{trial_number}-{depth}.json', count=2, timeout_ms=timeout_ms)
    except ValueError as error:
        require('frozen' in str(error).lower(), 'Execution failed for a reason other than frozen projection')
        result = {'blocked': True, 'error_type': type(error).__name__, 'error': str(error)}
    else:
        raise ValueError('Ordinary execution was allowed after a partial CPU/RAM restore')
    result['state_unchanged'] = equal_state(observe(session), snapshot)
    require(session.call('session.status')['state'] == 'stopped', 'Frozen projection is not stopped')
    result['stopped'] = True
    return result


def record_mode(project, session, initial_artifact, initial, plain_end, trial, mode,
                output, timeout_ms, persist):
    trial['phase'] = mode + ':setup'
    session.load_state(initial_artifact)
    equal_state(observe(session), initial)
    before = artifact_map(project)
    result = {'status': 'running', 'restores': []}
    trial['modes'][mode] = result
    if mode == MODES[0]:
        started, start_ns = timed(lambda: session.rewind_start(max_steps=16, max_bytes=MAX_BYTES))
        record = lambda: session.rewind_record(count=STEPS, timeout_ms=timeout_ms)
        undo = session.rewind
    else:
        started, start_ns = timed(lambda: session.cpu_delta_start(
            ranges=[dict(item) for item in RANGES], max_steps=16, max_bytes=MAX_BYTES))
        record = lambda: session.cpu_delta_record(count=STEPS, timeout_ms=timeout_ms)
        undo = session.cpu_delta_rewind
    result.update(start_elapsed_ns=start_ns, start_result=started)
    persist()
    require(started['cursor'] == 0 and started['valid'], 'History did not start at cursor zero')
    equal_state(observe(session), initial)
    trial['phase'] = mode + ':record'
    recorded, record_ns = timed(record)
    result.update(record_elapsed_ns=record_ns, start_plus_record_elapsed_ns=start_ns + record_ns,
                  record_result=recorded)
    persist()
    require(recorded['recorded_count'] == STEPS and recorded['cursor'] == STEPS,
            'Recording stopped before the declared interval budget')
    records = recorded['records']
    require(len(records) == STEPS, 'Recording did not retain every interval')
    result['storage'] = recording_storage(project, before, started, recorded, mode)
    result['trace_verification'] = []
    for index, point in enumerate(records):
        require(pc_offset(point['before_pc']) == PCS[index]
                and pc_offset(point['after_pc']) == PCS[index + 1],
                'Recorded boundaries differ from the authored PC sequence')
        result['trace_verification'].append(export_trace(project, point['trace_artifact'],
            output / f'{mode}-{trial["trial"]}-{index}.json', PCS[index:index + 2]))
    endpoint = observe(session)
    verify_oracle(endpoint, initial, STEPS)
    result['endpoint'] = observation_record(endpoint)
    result['same_endpoint_as_plain'] = equal_state(endpoint, plain_end)
    result['record_vs_plain_ratio'] = record_ns / trial['plain_trace']['elapsed_ns']
    result['start_plus_record_vs_plain_ratio'] = (start_ns + record_ns) / trial['plain_trace']['elapsed_ns']
    trial['_states'][mode] = {}
    persist()

    trial['phase'] = mode + ':undo'
    previous_depth = 0
    for depth in DEPTHS:
        relative = depth - previous_depth
        cursor = STEPS - depth
        sample = {'relative_rewind_count': relative, 'cumulative_depth_from_recorded_end': depth,
                  'expected_cursor': cursor, 'status': 'running'}
        result['restores'].append(sample)
        restored, elapsed = timed(lambda: undo(count=relative))
        sample.update(elapsed_ns=elapsed, result=restored)
        persist()
        require(restored['rewound_count'] == relative and restored['cursor'] == cursor,
                'Undo selected the wrong history position')
        if mode == MODES[0]:
            checkpoint = records[cursor]['checkpoint']
            require(restored['target_checkpoint']['artifact'] == checkpoint['artifact'],
                    'Native rewind selected a different checkpoint artifact')
            sample['checkpoint'] = checkpoint
        else:
            require(restored['partial_restored'] is True and restored['full_machine_restored'] is False,
                    'Delta undo must identify its partial restoration')
            status = restored['history']
            require(status['frozen'] is True and status['resume_safe'] is False,
                    'Delta undo must freeze execution until full native recovery')
        snapshot = observe(session)
        verify_oracle(snapshot, initial, cursor)
        trial['_states'][mode][cursor] = snapshot
        sample['observation'] = observation_record(snapshot)
        if mode == MODES[1]:
            sample['ordinary_execution'] = frozen_execution_check(
                session, snapshot, trial['trial'], depth, timeout_ms)
        sample['status'] = 'passed'
        previous_depth = depth
        persist()

    if mode == MODES[1]:
        trial['phase'] = mode + ':full-anchor-recovery'
        recovered, elapsed = timed(session.cpu_delta_recover)
        result['recovery'] = {'elapsed_ns': elapsed, 'result': recovered}
        persist()
        require(recovered['history']['frozen'] is False, 'Full native recovery did not clear freeze')
        require(recovered['restore']['sha256'] == started['anchor']['sha256'],
                'Recovery did not use the captured native anchor')
        snapshot = observe(session)
        result['recovery']['initial_projection_equality'] = equal_state(snapshot, initial)
        verify_oracle(snapshot, initial, 0)
        require(session.call('session.status')['state'] == 'stopped', 'Recovery implicitly resumed execution')
        result['recovery']['stopped_without_implicit_resume'] = True
    result['status'] = 'passed'
    persist()


def run_trial(project, session, initial_artifact, initial, trial, output, timeout_ms,
              separate_trace_control, persist):
    trial.update(status='running', phase='plain-trace', modes={}, _states={})
    session.load_state(initial_artifact)
    equal_state(observe(session), initial)
    plain, elapsed = timed(lambda: session.trace(f'plain-{trial["trial"]}.json', count=STEPS + 1,
                                               timeout_ms=timeout_ms, fast_forward=True))
    trial['plain_trace'] = {'elapsed_ns': elapsed, 'requested_fetches': STEPS + 1}
    persist()
    trial['plain_trace']['verification'] = export_trace(
        project, plain['artifact'], output / f'plain-{trial["trial"]}.json', PCS)
    plain_end = observe(session)
    verify_oracle(plain_end, initial, STEPS)
    trial['plain_trace']['endpoint'] = observation_record(plain_end)

    if separate_trace_control:
        trial['phase'] = 'separate-trace-control'
        session.load_state(initial_artifact)
        equal_state(observe(session), initial)
        control = {'samples': []}
        trial['separate_trace_control'] = control
        for index in range(STEPS):
            trace, duration = timed(lambda: session.trace(
                f'control-{trial["trial"]}-{index}.json', count=2, timeout_ms=timeout_ms, fast_forward=True))
            sample = {'interval': index + 1, 'elapsed_ns': duration}
            control['samples'].append(sample)
            sample['verification'] = export_trace(project, trace['artifact'],
                output / f'control-{trial["trial"]}-{index}.json', PCS[index:index + 2])
            verify_oracle(observe(session), initial, index + 1)
            persist()
        control['total_elapsed_ns'] = sum(item['elapsed_ns'] for item in control['samples'])
    order = list(MODES if trial['trial'] % 2 else reversed(MODES))
    trial['recording_mode_order'] = order
    persist()
    for mode in order:
        record_mode(project, session, initial_artifact, initial, plain_end, trial, mode,
                    output, timeout_ms, persist)

    # A delta-first trial also recovers before entering MR14. Direct loads run
    # after both modes, so they cannot invalidate a still-needed history.
    trial['phase'] = 'same-artifact-direct-load-controls'
    trial['direct_loads'] = []
    for native_sample in trial['modes'][MODES[0]]['restores']:
        checkpoint = native_sample['checkpoint']
        cursor = native_sample['expected_cursor']
        sample = {'cumulative_depth_from_recorded_end': STEPS - cursor,
                  'expected_cursor': cursor, 'checkpoint': checkpoint, 'status': 'running'}
        trial['direct_loads'].append(sample)
        restored, elapsed = timed(lambda: session.load_state(checkpoint['artifact']))
        sample.update(elapsed_ns=elapsed, result=restored)
        persist()
        require(restored['sha256'] == checkpoint['sha256'], 'Direct load used different native bytes')
        snapshot = observe(session)
        verify_oracle(snapshot, initial, cursor)
        sample['observation'] = observation_record(snapshot)
        sample['equality_by_mode'] = {mode: equal_state(snapshot, trial['_states'][mode][cursor])
                                      for mode in MODES}
        sample['status'] = 'passed'
        persist()
    trial.update(status='passed', phase='complete', storage_after_trial=artifact_inventory(project))
    persist()


def summary(trials):
    complete = [trial for trial in trials if trial['status'] == 'passed']
    result = {'completed_trials': len(complete), 'timing_population': 'completed trials only'}
    if not complete:
        return result
    result['plain_trace_median_ns'] = statistics.median(t['plain_trace']['elapsed_ns'] for t in complete)
    result['recording'] = {}
    for mode in MODES:
        entries = [t['modes'][mode] for t in complete]
        result['recording'][mode] = {
            key + '_median': statistics.median(item[key] for item in entries)
            for key in ('start_elapsed_ns', 'record_elapsed_ns', 'start_plus_record_elapsed_ns',
                        'record_vs_plain_ratio', 'start_plus_record_vs_plain_ratio')}
        result['recording'][mode]['storage_samples'] = [item['storage'] for item in entries]
    result['deltas_vs_native_start_plus_record_median_ratio'] = statistics.median(
        t['modes'][MODES[1]]['start_plus_record_elapsed_ns']
        / t['modes'][MODES[0]]['start_plus_record_elapsed_ns'] for t in complete)
    result['restore_groups'] = []
    for index, depth in enumerate(DEPTHS):
        native = [t['modes'][MODES[0]]['restores'][index] for t in complete]
        delta = [t['modes'][MODES[1]]['restores'][index] for t in complete]
        direct = [t['direct_loads'][index] for t in complete]
        result['restore_groups'].append({
            'cumulative_depth': depth, 'relative_rewind_count': native[0]['relative_rewind_count'],
            'samples_per_mode': len(complete),
            'native_rewind_median_ns': statistics.median(item['elapsed_ns'] for item in native),
            'cpu_ram_delta_undo_median_ns': statistics.median(item['elapsed_ns'] for item in delta),
            'same_artifact_direct_load_median_ns': statistics.median(item['elapsed_ns'] for item in direct),
            'all_exposed_cpu_and_declared_ram_equal': all(
                all(check.values()) for item in direct for check in item['equality_by_mode'].values()),
            'all_delta_execution_attempts_blocked': all(item['ordinary_execution']['blocked'] for item in delta),
        })
    result['full_anchor_recovery_median_ns'] = statistics.median(
        t['modes'][MODES[1]]['recovery']['elapsed_ns'] for t in complete)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', required=True, help='new private output directory outside Git')
    parser.add_argument('--trials', type=int, choices=range(1, 6), default=3)
    parser.add_argument('--steps', type=int, choices=(STEPS,), default=STEPS)
    parser.add_argument('--timeout-ms', type=int, default=10000)
    parser.add_argument('--separate-trace-control', action='store_true')
    args = parser.parse_args(argv)
    require(1 <= args.timeout_ms <= 60000, '--timeout-ms must be in 1..60000')
    backend = args.executable.expanduser().resolve(strict=True)
    require(backend.is_file() and os.access(backend, os.X_OK), '--executable must name an executable file')
    output = new_private_directory(args.output)
    report_path = output / 'report.json'
    report = {
        'format': 'fdisbull-cpu-ram-delta-benchmark-1', 'status': 'running',
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'platform': platform.platform(), 'machine': platform.machine(), 'python': platform.python_version(),
        'backend': {'path': str(backend), 'size': backend.stat().st_size, 'sha256': digest(backend.read_bytes())},
        'configuration': {'trials': args.trials, 'steps': STEPS, 'ranges': RANGES,
                          'max_history_steps': 16, 'max_history_bytes': MAX_BYTES,
                          'relative_rewind_counts': [1, 3, 8], 'cumulative_depths': list(DEPTHS),
                          'separate_trace_control': args.separate_trace_control,
                          'order': 'plain first; native/delta order alternates by trial; direct controls last'},
        'claim_boundary': {
            'comparison': 'Same backend, live session, authored fixture and saved initial projection for all arms.',
            'unit': 'next-fetch interval', 'general_instruction_completion': 'unknown',
            'delta_restore': 'Exposed CPU register groups and only the declared RAM range; execution frozen until full recovery.',
            'hidden_cpu_state': 'unknown', 'devices': 'unknown', 'other_ram': 'unknown',
            'whole_machine_equivalence': False, 'disk_rollback': False,
            'timing': 'Start, record, undo, direct load and recovery calls timed separately; verification/setup excluded. '
                      'Start-plus-record includes the one full native delta anchor. Bounded observations, not guarantees.',
        },
        'cpu_comparison_fields': list(CPU_FIELDS), 'trials': [],
    }
    persist = lambda: write_report(report_path, serializable(report))
    old_store = os.environ.get('FDISBULL_TARGET_STORE')
    os.environ['FDISBULL_TARGET_STORE'] = str(output / 'target-objects')
    try:
        persist()
        from fdisbull.project import Project
        guest = output / 'guest'
        guest.mkdir(mode=0o700)
        binary = guest / 'DELTAS.EXE'
        data = fixture_bytes()
        binary.write_bytes(data)
        report['fixture'] = {'source': 'authored MZ fixture and independent oracle from benchmark_rewind.py',
                             'bytes': len(data), 'sha256': digest(data), 'mapped_ram_bytes': len(MODULE),
                             'expected_pc_offsets': list(PCS), 'no_guest_file_writes': True}
        repo = Path(__file__).resolve().parents[1]
        report['implementation_files'] = {str(path.relative_to(repo)): digest(path.read_bytes()) for path in (
            Path(__file__).resolve(), repo / 'scripts/benchmark_rewind.py',
            repo / 'src/fdisbull/debug_cpu_deltas.py', repo / 'src/fdisbull/debug_rewind.py',
            repo / 'src/fdisbull/debugger.py') if path.is_file()}
        with Project.create(output / 'benchmark.fdb', binary) as project:
            project.analyze(max_instructions=32)
            with project.debugger(backend, guest, version=1) as session:
                require(session.rpc.capabilities.get('save_states'), 'Selected backend lacks native save states')
                for method in ('rewind_start', 'rewind_record', 'rewind', 'rewind_status', 'cpu_delta_start',
                               'cpu_delta_status', 'cpu_delta_record', 'cpu_delta_rewind', 'cpu_delta_recover'):
                    require(callable(getattr(session, method, None)), f'Required API is unavailable: {method}')
                initial = observe(session)
                verify_oracle(initial, initial, 0)
                report['initial_state'] = observation_record(initial)
                report['initial_state']['runtime_differs_from_file_at_offsets'] = [
                    offset for offset, (loaded, authored) in enumerate(zip(initial['ram'], MODULE)) if loaded != authored]
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
                                  args.timeout_ms, args.separate_trace_control, persist)
                    except Exception as error:
                        trial.update(status='failed', error={'type': type(error).__name__, 'message': str(error)})
                        trial['storage_on_failure'] = artifact_inventory(project)
                        trial['native_history_on_failure'] = session.rewind_status()
                        trial['delta_history_on_failure'] = session.cpu_delta_status()
                        persist()
                        raise
                report['storage'] = artifact_inventory(project)
        objects = [path for path in (output / 'target-objects').iterdir() if path.is_file()]
        report['external_store'] = {'object_count': len(objects), 'bytes_on_disk': sum(p.stat().st_size for p in objects)}
        require(digest(backend.read_bytes()) == report['backend']['sha256'], 'Backend file changed during the comparison')
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
