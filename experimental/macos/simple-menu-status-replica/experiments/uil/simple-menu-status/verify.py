"""Qualify this candidate's declared slice without opening either app.

The source oracle compiles the exact replica applyPreset method and MemoryMood
source in a temporary Foundation-only harness. It does not run Monitor, SwiftUI,
UserDefaults, a network request, or a sleep assertion.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from fdisbull.interaction_il import execute_il, validate_il
import fdisbull.interaction_il as evaluator

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROGRAM = json.loads((HERE / 'candidate.uil.json').read_text())
CONTRACT = json.loads((HERE / 'contract.json').read_text())
CHECKS = []


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    CHECKS.append(name)


def initial():
    return {key: value['initial'] for key, value in PROGRAM['variables'].items()}


def step(state, action, arg=0, *, status='complete', program=PROGRAM, ack_id=None):
    supplied = dict(state, **{'$action': action, '$arg': arg})
    if ack_id is not None:
        supplied['$ack_id'] = ack_id
    result = execute_il(program, supplied)
    check(f'action.{action}.arg.{arg}.{status}.{len(CHECKS)}', result['status'] == status)
    if status == 'refused':
        check('refusal.atomic.' + str(len(CHECKS)), result['state'] == supplied and result['events'] == [])
        return state, result
    state = result['state']
    check('one.checkmark.' + str(len(CHECKS)),
          sum(state['$checked_' + str(i)] for i in range(5)) == 1 and
          state['$checked_' + str(state['$layout'])])
    return state, result


def oracle():
    layout = PROGRAM['evidence']['replica.layout']
    lines = (ROOT / layout['file']).read_text().splitlines()
    start, end = layout['lines']
    method = '\n'.join(lines[start - 1:end])
    harness = '''import Foundation
final class LayoutOracle {
 var showGPU = true, showStorage = true, showBattery = true, showNetwork = true
 var showProcesses = false, showDetails = false, dashboardOpen = false
 var selectedPreset = "Custom"
 func persistDisplayPreferences() {}
 func fetchPublicIPIfNeeded() {}
''' + method + '''
}
let names = ["Simple", "Developer", "Battery", "Local AI", "Custom"]
var layouts: [[String: Any]] = []
for name in names {
 let item = LayoutOracle(); item.applyPreset(name)
 layouts.append(["name": item.selectedPreset,
  "flags": [item.showGPU, item.showStorage, item.showBattery, item.showNetwork,
            item.showProcesses, item.showDetails]])
}
let levels: [MemoryMood.Pressure?] = [nil, .normal, .warning, .critical]
let emojis = levels.map { MemoryMood.from(pressure: $0).emoji }
let result: [String: Any] = ["layouts": layouts, "emojis": emojis]
print(String(data: try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys]), encoding: .utf8)!)
'''
    with tempfile.TemporaryDirectory(prefix='simplemenu-uil-source-') as folder:
        root = Path(folder)
        (root / 'main.swift').write_text(harness)
        build = subprocess.run(['swiftc', str(ROOT / 'Sources/StatusCore/MemoryMood.swift'),
                                str(root / 'main.swift'), '-o', str(root / 'oracle')],
                               capture_output=True, text=True, timeout=60)
        check('replica.source.projection.compiles', build.returncode == 0)
        run = subprocess.run([str(root / 'oracle')], capture_output=True, text=True, timeout=10, check=True)
        result = json.loads(run.stdout)
    return result


def main():
    check('existing.uil.validator', validate_il(PROGRAM))
    for name, evidence in PROGRAM['evidence'].items():
        if 'observation_index' in evidence:
            data = (HERE / evidence['observation_index']).read_bytes()
            check('observations.digest.' + name, hashlib.sha256(data).hexdigest() == evidence['observation_index_sha256'])
        if 'file' in evidence:
            path = ROOT / evidence['file']
            check('source.digest.' + name, hashlib.sha256(path.read_bytes()).hexdigest() == evidence['sha256'])
            if 'selection_sha256' in evidence:
                start, end = evidence['lines']
                selected = ('\n'.join(path.read_text().splitlines()[start - 1:end]) + '\n').encode()
                check('source.selection.' + name, hashlib.sha256(selected).hexdigest() == evidence['selection_sha256'])
    original = CONTRACT['original_identity']
    check('original.identity.sidecar.digest', hashlib.sha256((HERE / original['file']).read_bytes()).hexdigest() == original['sha256'])
    native = oracle()
    flags = ['show_gpu', 'show_storage', 'show_battery', 'show_network', 'show_processes', 'show_details']
    for index, expected in enumerate(native['layouts']):
        state, _ = step(initial(), 2, index)
        check('replica.layout.' + expected['name'], [state['$' + name] for name in flags] == expected['flags'])
    for index, expected in enumerate(native['emojis']):
        _, result = step(initial(), 4, index)
        emojis = [event['resource_data']['text'] for event in result['events']
                  if event.get('resource', '').startswith('memory.')]
        check('replica.pressure.' + str(index), emojis == [expected])

    traces = []
    state, _ = step(initial(), 1)
    check('dashboard.opens', state['$menu_open'])
    state, _ = step(state, 1)
    check('dashboard.closes', not state['$menu_open'])
    for section, flag in enumerate(flags):
        before, _ = step(initial(), 2, 1)
        state, _ = step(before, 3, section)
        check('section.toggle.' + flag, state['$' + flag] != before['$' + flag] and state['$layout'] == 4)
        check('section.preserves.others.' + flag,
              all(state['$' + other] == before['$' + other] for other in flags if other != flag))

    state = initial()
    sequence = [(10, 1), (5, 0), (6, 0), (5, 0), (6, 1), (7, 0), (8, 0), (7, 0), (8, 1)]
    for action, arg in sequence:
        ack = state['$sleep_request_id'] if action in (6, 8) else None
        if action in (6, 8):
            step(state, action, arg, ack_id=state['$sleep_request_id'] - 1, status='refused')
        state, result = step(state, action, arg, ack_id=ack)
        traces.append({'action': CONTRACT['actions'][str(action)], 'arg': arg,
                       'active': state['$sleep_active'], 'pending': state['$sleep_pending'],
                       'events': [e['resource'] for e in result['events']]})
        if state['$sleep_pending'] or state['$sleep_active']:
            step(state, 10, 0, status='refused')
    check('sleep.ends.inactive', not state['$sleep_active'] and state['$sleep_pending'] == 0)
    step(state, 6, 1, status='refused')
    step(state, 8, 1, status='refused')
    check('sleep.failure.does.not.activate', traces[2]['active'] is False)
    check('sleep.success.activates', traces[4]['active'] is True)
    check('sleep.failed.stop.retains.active', traces[6]['active'] is True)
    check('sleep.request.does.not.activate', traces[1]['active'] is False)

    for action, limit in [(2, 5), (3, 6), (4, 4), (11, 6), (12, 7)]:
        step(initial(), action, limit, status='refused')
    step(initial(), 255, status='refused')
    state, _ = step(initial(), 2, 3)
    stale_revision = state['$preferences_revision']
    state, _ = step(state, 2, 4)
    step(state, 14, 1, ack_id=stale_revision, status='refused')
    state, _ = step(state, 14, 0, ack_id=state['$preferences_revision'])
    check('failed.preference.write.stays.dirty', state['$preferences_dirty'])
    state, _ = step(state, 14, 1, ack_id=state['$preferences_revision'])
    check('preference.ack.clears.dirty', not state['$preferences_dirty'])
    step(state, 14, 1, status='refused')
    restored = json.loads(json.dumps(state))
    restored, _ = step(restored, 9)
    check('model.json.state.reopens', restored['$additional_open'] and restored['$layout'] == 4)
    restored, _ = step(restored, 11, 5)
    check('sleep.details.opens.collapsed', not restored['$additional_open'])
    restored, _ = step(restored, 9)
    restored, _ = step(restored, 11, 0)
    restored, _ = step(restored, 11, 5)
    check('sleep.details.reopens.collapsed', not restored['$additional_open'])
    exhausted = dict(initial(), **{'$sleep_request_id': 2**64 - 1})
    step(exhausted, 5, status='refused')
    exhausted = dict(initial(), **{'$preferences_revision': 2**64 - 1})
    step(exhausted, 2, 1, status='refused')
    invalid = dict(initial(), **{'$memory_mood': True})
    check('typed.state.refused', execute_il(PROGRAM, invalid)['status'] == 'refused')
    check('budget.refused', execute_il(PROGRAM, max_steps=1)['status'] == 'refused')
    mutant = copy.deepcopy(PROGRAM)
    mutant['resources']['memory.warning']['text'] = '😰'
    _, mismatch = step(initial(), 4, 2, program=mutant)
    mutated = [e['resource_data']['text'] for e in mismatch['events'] if e.get('resource') == 'memory.warning']
    check('falsifier.detects.wrong.warning.emoji', mutated != [native['emojis'][2]])

    # Fresh CLI processes validate/run the same file; no host effects are bound.
    cli = shutil.which('fdisbull')
    check('installed.cli.present', bool(cli))
    validated = json.loads(subprocess.run([cli, 'il-check', str(HERE / 'candidate.uil.json')],
                            capture_output=True, text=True, check=True, timeout=15).stdout)
    check('fresh.cli.valid', validated['status'] == 'valid')
    sample = dict(initial(), **{'$action': 2, '$arg': 3})
    (HERE / 'sample.state.json').write_text(json.dumps(sample, indent=2) + '\n')
    observed = json.loads(subprocess.run([cli, 'il-run', str(HERE / 'candidate.uil.json'),
                            '--state', str(HERE / 'sample.state.json')], capture_output=True,
                            text=True, check=True, timeout=15).stdout)
    check('fresh.cli.matches.evaluator', observed == execute_il(PROGRAM, sample))
    (HERE / 'sample.run.json').write_text(json.dumps(observed, ensure_ascii=False, indent=2) + '\n')
    canonical = json.dumps(PROGRAM, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    receipt = {'kind': 'bounded-candidate-verification', 'status': 'passed',
        'run_at_utc': datetime.now(timezone.utc).isoformat(), 'checks_passed': len(CHECKS),
        'checks': CHECKS, 'replica_source_cases': 9, 'source_oracle_result': native,
        'sleep_trace': traces, 'uil_sha256': hashlib.sha256(canonical).hexdigest(),
        'uil_canonical_bytes': len(canonical), 'evaluator_version': importlib.metadata.version('fdisbull'),
        'evaluator_sha256': hashlib.sha256(Path(evaluator.__file__).read_bytes()).hexdigest(),
        'claim_ceiling': 'model execution and nine replica-source projections; original native equivalence unproved',
        'host_effects_executed': [], 'falsifier': 'wrong warning emoji detected',
        'reopen_scope': 'JSON model state roundtrip only; no macOS preferences or app restart tested'}
    (HERE / 'verification.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    inventory = []
    for path in sorted(HERE.iterdir()):
        if path.is_file() and path.name != 'manifest.json' and (path.suffix in ('.json', '.py', '.md') or path.name == '.gitignore'):
            data = path.read_bytes()
            inventory.append({'file': path.name, 'bytes': len(data),
                              'sha256': hashlib.sha256(data).hexdigest()})
    inventory_bytes = json.dumps(inventory, sort_keys=True, separators=(',', ':')).encode()
    manifest = {'kind': 'experimental-artifact-inventory-not-a-new-uil-contract',
                'status': 'authored_candidate', 'uil_format': PROGRAM['format'],
                'uil_sha256': receipt['uil_sha256'], 'files': inventory,
                'inventory_sha256': hashlib.sha256(inventory_bytes).hexdigest(),
                'original_binary_bytes_included': False,
                'claim_ceiling': receipt['claim_ceiling']}
    (HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: receipt[k] for k in ['status', 'checks_passed', 'replica_source_cases',
                                           'uil_sha256', 'claim_ceiling']}, indent=2))


if __name__ == '__main__':
    main()
