#!/usr/bin/env python3
"""Compare Wine CPU/RAM delta rewind with full native Anchor Stones.

Run from the selected checkout with its dependencies and PYTHONPATH=src:
    python scripts/benchmark_wine_deltas.py --qemu /absolute/qemu-system-x86_64 \
        --kernel /private/linux-amd64 --initramfs /private/wine-runtime.cpio.gz \
        --fixture /private/oracle.exe --output /private/new-wine-comparison

Use the package's authored PE self-test image. Each fresh project/VM executes
the same three instructions: write_only's MOV of 17 to counter, its RET to the
initial WinMain caller, then that caller's direct JMP. Setup deliberately edits
RIP and a 64-bit GPR while stopped; this is diagnostic intervention, not play.
All arms in one trial restore the exact same saved starting native state.

Anchor recording saves one complete native state before each instruction.
Delta recording captures its required native recovery anchor, then records the
same three completed instructions. Mode order alternates. Relative undo counts
1 and 2 select cumulative depths 1 and 3. Direct controls load the exact Anchor
Stone artifacts for those boundaries. All exposed GPRs, RIP, RFLAGS, selected
thread and four counter bytes are checked against an independent instruction
oracle. Delta undo is partial and must refuse execution/capture/input and a
cached outer-machine resume until successful full native recovery.

The native sidecar is charged along with each state manifest. A separate
project per trial preserves all immutable native artifacts within the existing
6 GiB project cap; this script never deletes snapshots to make room. Timings
are local bounded observations, not full-machine equivalence or speed promises.
All databases, inputs, states, traces and raw reports remain private outside Git.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import time

import benchmark_rewind as benchmark_support
from benchmark_rewind import new_private_directory, require, timed, write_report


STEPS = 3
DEPTHS = (1, 3)
MAX_BYTES = 2 * 1024**3
PROJECT_NATIVE_CAP = 6 * 1024**3
GPRS = ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp',
        'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15')
MODES = ('anchor_stones', 'cpu_ram_deltas')
SENTINEL = 0x123456789abcdef0
FROZEN_OPERATIONS = ('trace', 'run', 'save_anchor_stone', 'screenshot', 'click', 'cached_machine_resume')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_identity(path):
    path = Path(path).expanduser().resolve(strict=True)
    require(path.is_file(), 'Expected a regular input file')
    with path.open('rb') as stream:
        sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'size': path.stat().st_size, 'sha256': sha256}


def number(value):
    require(type(value) is int or isinstance(value, str), 'Invalid exposed CPU value')
    result = int(value, 0) if isinstance(value, str) else value
    require(0 <= result < 2**64, 'Exposed CPU value exceeds unsigned 64-bit width')
    return result


def cpu(registers):
    require(registers.get('cpu_mode', 'long64') == 'long64', 'Fixture left PE long64 mode')
    require(set(registers['general']) == set(GPRS), 'PE register projection is incomplete')
    require(number(registers['rflags']) <= 0xffffffff, 'PE RFLAGS exceeds native width')
    return {'general': {name: hex(number(registers['general'][name])) for name in GPRS},
            'rip': hex(number(registers['rip'])), 'rflags': hex(number(registers['rflags'])),
            'thread': number(registers['thread']), 'cpu_mode': 'long64'}


def observe(session, address):
    registers = cpu(session.registers())
    data = bytes.fromhex(session.memory(address, length=4)['hex'])
    require(len(data) == 4, 'Incomplete selected counter read')
    return {'cpu': registers, 'ram_hex': data.hex(), 'ram_sha256': digest(data)}


def equal(left, right):
    result = {'all_exposed_registers_and_thread_equal': left['cpu'] == right['cpu'],
              'all_selected_ram_equal': left['ram_hex'] == right['ram_hex']}
    require(all(result.values()), 'Selected CPU/thread or RAM differs from its control')
    return result


def expected_state(initial, oracle, completed):
    result = deepcopy(initial)
    if completed:
        result['ram_hex'] = '11000000'
        result['ram_sha256'] = digest(bytes.fromhex(result['ram_hex']))
        result['cpu']['rip'] = hex(oracle['write_runtime'] + oracle['mov_length'])
    if completed >= 2:
        result['cpu']['general']['rsp'] = hex(number(initial['cpu']['general']['rsp']) + 8)
        result['cpu']['rip'] = hex(oracle['return_runtime'])
    if completed >= 3:
        result['cpu']['rip'] = hex(oracle['jump_target_runtime'])
    return result


def verify_oracle(snapshot, initial, oracle, completed):
    require(0 <= completed <= STEPS, 'Invalid instruction-oracle boundary')
    require(initial['ram_hex'] == '07000000', 'Authored counter must initially be seven')
    require(number(initial['cpu']['general']['rax']) == SENTINEL,
            'The 64-bit sentinel was not established')
    return equal(snapshot, expected_state(initial, oracle, completed))


def artifact_map(project):
    return {item['id']: item for item in project.debug_artifacts()['artifacts']}


def sidecars(project):
    directory = Path(str(project.path) + '.fdisbull-states')
    return {path.name: path.stat().st_size for path in directory.glob('*.mig.gz')}


def state_reference(project, receipt):
    info = project.debug_anchor_stone_info(receipt['artifact'])
    require(info['sha256'] == receipt['sha256'] and info['size'] == receipt['size'],
            'Anchor Stone manifest differs from its receipt')
    require(0 < info['native_size'] <= MAX_BYTES, 'Native sidecar exceeds the compressed cap')
    return {key: info[key] for key in ('artifact', 'sha256', 'size', 'native_size')}


def storage(project, before, before_sidecars, result, mode):
    artifacts = artifact_map(project)
    added = [item for identifier, item in artifacts.items() if identifier not in before]
    current_sidecars = sidecars(project)
    require(sum(current_sidecars.values()) <= PROJECT_NATIVE_CAP,
            'Native project payload exceeds the retained 6 GiB cap')
    new_sidecar_bytes = sum(size for name, size in current_sidecars.items() if name not in before_sidecars)
    if mode == MODES[0]:
        payloads = [state_reference(project, point['checkpoint']) for point in result['records']]
        step_bytes = sum(item['size'] + item['native_size'] for item in payloads)
        anchor_bytes = 0
    else:
        payloads = [point['delta'] for point in result['record_result']['records']]
        step_bytes = 0
        for item in payloads:
            stored = artifacts.get(item['artifact'])
            require(stored is not None and stored['kind'] == 'cpu-ram-delta'
                    and stored['sha256'] == item['sha256'] and stored['size'] == item['size'],
                    'Delta artifact receipt differs from retained data')
            step_bytes += stored['size']
        anchor = state_reference(project, result['start_result']['anchor'])
        anchor_bytes = anchor['size'] + anchor['native_size']
        history = result['record_result']['history']
        require(history['anchor_bytes_used'] == anchor_bytes
                and history['delta_bytes_used'] == step_bytes
                and history['total_bytes_used'] == anchor_bytes + step_bytes,
                'Delta accounting does not include the complete native recovery sidecar')
    require(len(payloads) == STEPS and len({p['artifact'] for p in payloads}) == STEPS,
            'Recording did not retain one distinct payload per instruction')
    return {'step_payload_count': STEPS, 'step_payload_bytes_without_anchor': step_bytes,
            'recovery_anchor_bytes_manifest_plus_sidecar': anchor_bytes,
            'payload_bytes_including_recovery_anchor': step_bytes + anchor_bytes,
            'new_artifact_count': len(added), 'new_artifact_kinds': dict(Counter(a['kind'] for a in added)),
            'new_artifact_manifest_or_inline_bytes': sum(a['size'] for a in added),
            'new_native_sidecar_bytes': new_sidecar_bytes,
            'all_new_payload_bytes_including_traces_and_sidecars': sum(a['size'] for a in added) + new_sidecar_bytes,
            'new_trace_payload_bytes': sum(a['size'] for a in added if a['kind'] == 'trace'),
            'project_retained_native_sidecar_bytes': sum(current_sidecars.values()),
            'accounting': 'Logical payload lengths; native state references charge manifest plus sidecar. '
                          'All-new totals count newly retained sidecar files once; these are not disk block allocations.'}


def verify_trace(project, artifact, path, initial, oracle, index):
    project.debug_export(artifact, path)
    document = json.loads(path.read_text())
    require(document.get('complete') is True and document.get('requested_count') == 1,
            'Expected one complete PE instruction trace')
    events = document['events']
    require(len(events) == 1, 'PE interval contains a different number of completed instructions')
    event = events[0]
    expected = expected_state(initial, oracle, index)['cpu']
    require(cpu(event['registers']) == expected, 'Trace pre-instruction CPU/thread differs from the oracle')
    require(number(event['address']) == number(expected['rip']), 'Trace begins at the wrong instruction')
    require(event['bytes'] == oracle['instruction_bytes'][index]
            and event['ram_bytes'] == event['bytes'] and event['execution_bytes'] == event['bytes'],
            'Observed or executed trace bytes differ from the authored instruction oracle')
    require(event.get('observation', {}).get('instruction_completed') is True,
            'Trace does not establish completed instruction semantics')
    require(event.get('active_layers') == [], 'Benchmark unexpectedly executed a code layer')
    return {'artifact': artifact, 'complete': True, 'completed_instructions': 1,
            'before_rip': event['address'], 'thread': event['registers']['thread'],
            'bytes': event['bytes'], 'export_sha256': digest(path.read_bytes())}


def setup(session, project, exports, timeout_ms):
    from iced_x86 import Decoder, FlowControl
    breakpoint = session.breakpoint(exports['checkpoint'])
    reached = session.run(timeout_ms=timeout_ms)
    require(reached['outcome'] == 'breakpoint', 'Authored GUI did not reach its initial checkpoint')
    session.delete_breakpoint(breakpoint['breakpoint_id'])
    before = session.registers()
    write_runtime = exports['write_only'] + session.delta
    session.write_registers({
        'rip': {'expected': before['rip'], 'value': write_runtime},
        'rax': {'expected': before['general']['rax'], 'value': SENTINEL}})
    initial = observe(session, exports['counter'])
    code = bytes.fromhex(session.memory(exports['write_only'], length=16)['hex'])
    mov = Decoder(64, code, ip=write_runtime).decode()
    require(code[:2] == bytes.fromhex('c705') and mov.len == 10 and mov.immediate32 == 17
            and mov.ip_rel_memory_address == exports['counter'] + session.delta
            and code[mov.len] == 0xc3,
            'Expected authored MOV counter,17 followed by a bare RET')
    stack = session.call('read', {'address': number(initial['cpu']['general']['rsp']), 'length': 8})
    raw = base64.b64decode(stack['data_base64'], validate=True)
    require(len(raw) == 8, 'Incomplete stopped return-address observation')
    return_runtime = int.from_bytes(raw, 'little')
    return_project = session.project_address(return_runtime)
    require(return_project is not None, 'Authored checkpoint return is outside the main image')
    next_bytes = bytes.fromhex(session.memory(return_project, length=16)['hex'])
    jump = Decoder(64, next_bytes, ip=return_runtime).decode()
    require(jump.flow_control == FlowControl.UNCONDITIONAL_BRANCH
            and next_bytes[0] in (0xeb, 0xe9),
            'Authored WinMain return must begin with a direct JMP')
    target = jump.near_branch_target
    require(session.project_address(target) is not None, 'Authored JMP leaves the main image')
    oracle = {'write_runtime': write_runtime, 'mov_length': mov.len,
              'return_runtime': return_runtime, 'jump_target_runtime': target,
              'instruction_bytes': [code[:mov.len].hex(), 'c3', next_bytes[:jump.len].hex()],
              'meaning': 'MOV counter,17; RET consumes the observed caller address; direct JMP. '
                         'All other exposed CPU values and RFLAGS remain unchanged.'}
    verify_oracle(initial, initial, oracle, 0)
    require(session.breakpoints == {} and session.watchpoints == {}, 'Setup retained user breakpoints')
    return initial, oracle, {'run_to_checkpoint': reached,
        'intervention': 'Stopped guarded RIP redirect to authored write_only and RAX sentinel; no input timing claim.',
        'before_rip': before['rip'], 'write_runtime': hex(write_runtime), 'rax_sentinel': hex(SENTINEL)}


def frozen_checks(project, session, cached_machine, snapshot, counter, timeout_ms):
    before_artifacts, before_sidecars = artifact_map(project), sidecars(project)
    operations = {
        'trace': lambda: session.trace('forbidden.json', count=1, timeout_ms=timeout_ms),
        'run': lambda: session.run(timeout_ms=timeout_ms),
        'save_anchor_stone': lambda: session.save_anchor_stone('forbidden.sav'),
        'screenshot': lambda: session.screenshot('forbidden.png'),
        'click': lambda: session.click(80, 80),
        'cached_machine_resume': cached_machine.resume,
    }
    result = {}
    for name, operation in operations.items():
        try:
            operation()
        except ValueError as error:
            require('frozen' in str(error).lower(), name + ' failed for a reason other than the partial-state guard')
            result[name] = {'blocked': True, 'error': str(error)}
        else:
            raise ValueError(name + ' was permitted after partial delta restore')
        equal(observe(session, counter), snapshot)
    require(artifact_map(project) == before_artifacts and sidecars(project) == before_sidecars,
            'A refused operation retained a new capture or changed an artifact')
    require(session.call('status')['state'] == 'stopped', 'Frozen target is not stopped')
    result['projection_and_artifacts_unchanged'] = True
    return result


def record_arm(project, session, seed, initial, oracle, counter, trial, mode, output, timeout_ms, persist):
    trial['phase'] = mode + ':setup'
    persist()
    session.load_anchor_stone(seed['artifact'])
    verify_oracle(observe(session, counter), initial, oracle, 0)
    cached_machine = session.machine
    before, before_sidecars = artifact_map(project), sidecars(project)
    result = {'status': 'running'}
    trial['modes'][mode] = result
    trial['phase'] = mode + ':record'
    if mode == MODES[0]:
        result['start_elapsed_ns'] = 0
        result['start_cost'] = 'Manual history bookkeeping; no native start operation. Common seed is excluded from both arms.'
        records = []
        persist()

        def record():
            for index in range(STEPS):
                saved = session.save_anchor_stone(f'anchor-before-{index}.sav', max_bytes=MAX_BYTES)
                trace = session.trace(f'anchor-step-{index}.json', count=1, timeout_ms=timeout_ms)
                records.append({'checkpoint': saved, 'trace_artifact': trace['artifact']})
            return {'records': records, 'recorded_count': len(records)}

        recorded, duration = timed(record)
        result.update(records=records, record_result=recorded, record_elapsed_ns=duration,
                      start_plus_record_elapsed_ns=duration)
    else:
        trial['phase'] = mode + ':start'
        persist()
        started, duration = timed(lambda: session.cpu_delta_start(
            [{'address': hex(counter), 'length': 4}], max_steps=STEPS, max_bytes=MAX_BYTES))
        result.update(start_result=started, start_elapsed_ns=duration)
        persist()
        require(started['valid'] and started['cursor'] == 0, 'Delta history did not start at cursor zero')
        verify_oracle(observe(session, counter), initial, oracle, 0)
        trial['phase'] = mode + ':record'
        persist()
        recorded, duration = timed(lambda: session.cpu_delta_record(count=STEPS, timeout_ms=timeout_ms))
        require(recorded['recorded_count'] == STEPS and recorded['cursor'] == STEPS,
                'Delta recording did not complete its declared interval budget')
        result.update(record_result=recorded, record_elapsed_ns=duration,
                      start_plus_record_elapsed_ns=result['start_elapsed_ns'] + duration)
        records = recorded['records']
    persist()
    result['storage'] = storage(project, before, before_sidecars, result, mode)
    result['traces'] = [verify_trace(project, item['trace_artifact'], output / f'{mode}-{index}.json',
                                     initial, oracle, index) for index, item in enumerate(records)]
    result['endpoint'] = observe(session, counter)
    verify_oracle(result['endpoint'], initial, oracle, STEPS)
    delta_snapshots = {}
    if mode == MODES[1]:
        result['restores'] = []
        previous = 0
        for depth in DEPTHS:
            trial['phase'] = mode + ':undo-' + str(depth)
            restored, duration = timed(lambda: session.cpu_delta_rewind(count=depth - previous))
            require(restored['cursor'] == STEPS - depth and restored['rewound_count'] == depth - previous
                    and restored['partial_restored'] is True and restored['full_machine_restored'] is False
                    and restored['history']['frozen'] is True and restored['history']['resume_safe'] is False,
                    'Delta result lost its partial selected-state contract')
            snapshot = observe(session, counter)
            verify_oracle(snapshot, initial, oracle, STEPS - depth)
            sample = {'depth': depth, 'relative_count': depth - previous, 'elapsed_ns': duration,
                      'result': restored, 'observation': snapshot}
            result['restores'].append(sample)
            persist()
            sample['frozen_operations'] = frozen_checks(project, session, cached_machine, snapshot, counter, timeout_ms)
            delta_snapshots[STEPS - depth] = snapshot
            previous = depth
            persist()
        trial['phase'] = mode + ':full-anchor-recovery'
        persist()
        recovered, duration = timed(session.cpu_delta_recover)
        result['recovery'] = {'elapsed_ns': duration, 'result': recovered}
        require(recovered['history']['frozen'] is False, 'Full native recovery did not clear the partial-state guard')
        equal(observe(session, counter), initial)
        require(session.call('status')['state'] == 'stopped', 'Recovery implicitly resumed the target')
        result['recovery']['initial_projection_equal_and_stopped'] = True
    result['status'] = 'passed'
    persist()
    return delta_snapshots


def run_trial(project, session, trial, output, exports, timeout_ms, persist):
    trial.update(status='running', phase='fixture-setup', modes={})
    persist()
    initial, oracle, setup_receipt = setup(session, project, exports, timeout_ms)
    trial.update(initial=initial, oracle=oracle, setup=setup_receipt,
                 native_capabilities=session.rpc.capabilities, session_metadata=deepcopy(session.metadata))
    trial['phase'] = 'common-seed-capture'
    persist()
    seed, seed_ns = timed(lambda: session.save_anchor_stone('common-seed.sav', max_bytes=MAX_BYTES))
    trial['common_seed'] = {'checkpoint': state_reference(project, seed), 'elapsed_ns': seed_ns,
                            'excluded_from_both_recording_arms': True}
    verify_oracle(observe(session, exports['counter']), initial, oracle, 0)
    order = list(MODES if trial['trial'] % 2 else reversed(MODES))
    trial['recording_mode_order'] = order
    persist()
    delta_snapshots = {}
    for mode in order:
        snapshots = record_arm(project, session, seed, initial, oracle, exports['counter'], trial,
                               mode, output, timeout_ms, persist)
        if mode == MODES[1]:
            delta_snapshots = snapshots
    equal(trial['modes'][MODES[0]]['endpoint'], trial['modes'][MODES[1]]['endpoint'])
    trial['phase'] = 'same-artifact-anchor-load-controls'
    trial['anchor_loads'] = []
    persist()
    for depth in DEPTHS:
        cursor = STEPS - depth
        point = trial['modes'][MODES[0]]['records'][cursor]['checkpoint']
        restored, duration = timed(lambda: session.load_anchor_stone(point['artifact']))
        require(restored['sha256'] == point['sha256'], 'Direct native load used different Anchor Stone bytes')
        snapshot = observe(session, exports['counter'])
        verify_oracle(snapshot, initial, oracle, cursor)
        comparison = equal(snapshot, delta_snapshots[cursor])
        trial['anchor_loads'].append({'depth': depth, 'elapsed_ns': duration, 'checkpoint': state_reference(project, point),
                                      'result': restored, 'observation': snapshot, 'equality_with_delta': comparison})
        persist()
    trial.update(status='passed', phase='complete', retained_native_sidecar_bytes=sum(sidecars(project).values()))
    persist()


def module_provenance(repo, session=None):
    names = {'fdisbull', 'fdisbull.project', 'fdisbull.debug_cpu_deltas', 'fdisbull.debug_script',
             'fdisbull.debugger', 'fdisbull.wine_debugger', 'fdisbull.wine_execution',
             'fdisbull.wine_state', 'fdisbull.wine_rpc', 'fdisbull.qemu_machine'}
    session_type = type(session) if session is not None else importlib.import_module('fdisbull.wine_debugger').PEDebugSession
    names.update(cls.__module__ for cls in session_type.__mro__ if cls.__module__.startswith('fdisbull.'))
    result = {}
    for name in sorted(names):
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve(strict=True)
        require(path.is_relative_to(repo / 'src'), 'Imported module is outside the selected checkout: ' + name)
        result[name] = {'path': str(path), 'sha256': digest(path.read_bytes())}
    return result


def summarize(trials):
    completed = [t for t in trials if t['status'] == 'passed']
    result = {'completed_trials': len(completed), 'timing_population': 'completed trials only'}
    if not completed:
        return result
    result['recording'] = {}
    for mode in MODES:
        samples = [t['modes'][mode] for t in completed]
        result['recording'][mode] = {key + '_median': statistics.median(s[key] for s in samples)
            for key in ('start_elapsed_ns', 'record_elapsed_ns', 'start_plus_record_elapsed_ns')}
        result['recording'][mode]['storage_samples'] = [s['storage'] for s in samples]
        result['recording'][mode]['storage_medians'] = {key: statistics.median(s['storage'][key] for s in samples)
            for key in ('step_payload_bytes_without_anchor', 'recovery_anchor_bytes_manifest_plus_sidecar',
                        'payload_bytes_including_recovery_anchor', 'all_new_payload_bytes_including_traces_and_sidecars')}
    result['paired_delta_vs_anchor_start_plus_record_ratio_median'] = statistics.median(
        t['modes'][MODES[1]]['start_plus_record_elapsed_ns'] / t['modes'][MODES[0]]['start_plus_record_elapsed_ns']
        for t in completed)
    result['restore_groups'] = []
    for index, depth in enumerate(DEPTHS):
        deltas = [t['modes'][MODES[1]]['restores'][index] for t in completed]
        anchors = [t['anchor_loads'][index] for t in completed]
        result['restore_groups'].append({'depth': depth, 'samples_per_mode': len(completed),
            'delta_undo_median_ns': statistics.median(s['elapsed_ns'] for s in deltas),
            'same_artifact_anchor_load_median_ns': statistics.median(s['elapsed_ns'] for s in anchors),
            'all_exposed_cpu_thread_and_selected_ram_equal': all(all(s['equality_with_delta'].values()) for s in anchors),
            'all_partial_state_guards_blocked': all(
                all(s['frozen_operations'].get(name, {}).get('blocked') is True for name in FROZEN_OPERATIONS)
                and s['frozen_operations'].get('projection_and_artifacts_unchanged') is True for s in deltas)})
    result['full_anchor_recovery_median_ns'] = statistics.median(
        t['modes'][MODES[1]]['recovery']['elapsed_ns'] for t in completed)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for option in ('qemu', 'kernel', 'initramfs', 'fixture'):
        parser.add_argument('--' + option, type=Path, required=True)
    parser.add_argument('--output', required=True, help='new private directory outside Git')
    parser.add_argument('--trials', type=int, choices=range(1, 6), default=3)
    parser.add_argument('--steps', type=int, choices=(STEPS,), default=STEPS)
    parser.add_argument('--timeout-ms', type=int, default=60000)
    args = parser.parse_args(argv)
    require(1000 <= args.timeout_ms <= 600000, '--timeout-ms must be in 1000..600000')
    inputs = {name: file_identity(getattr(args, name)) for name in ('qemu', 'kernel', 'initramfs', 'fixture')}
    require(os.access(inputs['qemu']['path'], os.X_OK), '--qemu must name an executable')
    output = new_private_directory(args.output)
    report_path = output / 'report.json'
    repo = Path(__file__).resolve().parents[1]
    report = {'format': 'fdisbull-wine-cpu-ram-delta-benchmark-1', 'status': 'running',
        'started_at_utc': datetime.now(timezone.utc).isoformat(), 'platform': platform.platform(),
        'machine': platform.machine(), 'python': platform.python_version(), 'inputs': inputs,
        'configuration': {'trials': args.trials, 'steps': STEPS, 'cumulative_depths': list(DEPTHS),
                          'relative_rewind_counts': [1, 2], 'max_delta_bytes': MAX_BYTES,
                          'native_project_cap_bytes': PROJECT_NATIVE_CAP,
                          'order': 'paired same seed per fresh trial; recording order alternates; full-load controls last'},
        'claim_boundary': {'unit': 'one completed instruction on one selected PE thread',
            'delta_restore': '16 exposed GPRs, RIP, RFLAGS and four selected counter bytes; selected thread pinned.',
            'unselected_memory': 'not restored', 'hidden_cpu_and_devices': 'not restored',
            'other_threads_and_guest_services': 'not rewound', 'host_files': 'not rolled back',
            'resumable_delta_state': False, 'whole_machine_equivalence': False,
            'timing': 'Start, record, delta undo, exact-artifact full load and native recovery timed separately. '
                      'Verification and setup excluded. Delta total includes one native recovery Anchor Stone; '
                      'the common pairing seed is excluded from both recording arms.',
            'scope': 'Tiny authored selected-state microbenchmark on the declared host/runtime, not a game throughput claim.'},
        'trials': []}
    persist = lambda: write_report(report_path, report)
    previous_store = os.environ.get('FDISBULL_TARGET_STORE')
    os.environ['FDISBULL_TARGET_STORE'] = str(output / 'target-objects')
    try:
        persist()
        require(shutil.disk_usage(output).free >= args.trials * PROJECT_NATIVE_CAP + MAX_BYTES,
                'Insufficient free space for retained per-trial native budgets plus reserve')
        report['module_origins'] = module_provenance(repo)
        helper = Path(benchmark_support.__file__).resolve(strict=True)
        require(helper == repo / 'scripts' / 'benchmark_rewind.py', 'Benchmark helper imported from another checkout')
        report['implementation_files'] = {str(Path(item['path']).relative_to(repo)): item['sha256']
                                           for item in report['module_origins'].values()}
        report['implementation_files'][str(Path(__file__).resolve().relative_to(repo))] = digest(Path(__file__).read_bytes())
        report['implementation_files'][str(helper.relative_to(repo))] = digest(helper.read_bytes())
        revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True, check=True)
        report['checkout_head'] = revision.stdout.strip()
        import lief
        from fdisbull.project import Project
        binary = lief.PE.parse(inputs['fixture']['path'])
        require(binary is not None and binary.optional_header.magic == lief.PE.PE_TYPE.PE32_PLUS,
                '--fixture must be the authored x86-64 PE self-test image')
        base = binary.optional_header.imagebase
        exports = {entry.name: base + entry.address for entry in binary.get_export().entries}
        require(all(name in exports for name in ('checkpoint', 'write_only', 'counter')),
                'Fixture does not export the expected authored self-test boundaries')
        report['fixture_exports'] = {name: hex(exports[name]) for name in ('checkpoint', 'write_only', 'counter')}
        persist()
        for index in range(1, args.trials + 1):
            directory = output / f'trial-{index}'
            directory.mkdir(mode=0o700)
            guest = directory / 'guest'
            guest.mkdir(mode=0o700)
            fixture = guest / 'ORACLE.EXE'
            shutil.copyfile(inputs['fixture']['path'], fixture)
            trial = {'trial': index, 'status': 'running', 'phase': 'launch', 'project': str(directory / 'wine.fdb')}
            report['trials'].append(trial)
            persist()
            session = None
            try:
                with Project.create(directory / 'wine.fdb', fixture) as project:
                    project.analyze(start=exports['checkpoint'], max_instructions=16)
                    session = project.debugger(inputs['qemu']['path'], guest,
                        kernel=inputs['kernel']['path'], initramfs=inputs['initramfs']['path'], version=1)
                    require(module_provenance(repo, session) == report['module_origins'],
                            'Module source or import origin changed during the benchmark')
                    try:
                        for method in ('cpu_delta_start', 'cpu_delta_record', 'cpu_delta_rewind', 'cpu_delta_recover'):
                            require(callable(getattr(session, method, None)), 'Required PE delta API is unavailable: ' + method)
                        run_trial(project, session, trial, directory, exports, args.timeout_ms, persist)
                    finally:
                        try:
                            session.close()
                            trial['cleanup'] = {'closed': session.closed, 'process_reaped': session.rpc.process.poll() is not None}
                            require(all(trial['cleanup'].values()), 'Native process cleanup was not verified')
                        except BaseException as error:
                            trial['cleanup'] = {'error_type': type(error).__name__, 'error': str(error)}
                            if trial['status'] == 'passed':
                                raise
                        persist()
                require(file_identity(fixture)['sha256'] == inputs['fixture']['sha256'], 'Private authored fixture changed')
            except BaseException as error:
                trial.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
                             error={'type': type(error).__name__, 'message': str(error)})
                persist()
                raise
        for name, identity in inputs.items():
            require(file_identity(identity['path']) == identity, name + ' input changed during comparison')
        for relative, expected in report['implementation_files'].items():
            require(digest((repo / relative).read_bytes()) == expected, 'Implementation changed during comparison: ' + relative)
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
                      error={'type': type(error).__name__, 'message': str(error)})
    finally:
        if previous_store is None:
            os.environ.pop('FDISBULL_TARGET_STORE', None)
        else:
            os.environ['FDISBULL_TARGET_STORE'] = previous_store
        report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        report['summary'] = summarize(report['trials'])
        persist()
    print(json.dumps({'status': report['status'], 'report': str(report_path), 'summary': report['summary']}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
