"""Opt-in RFC native-slice replayer, not a player API or standalone compiler.

Uses operator-owned game/checkpoints and the pinned native runtime profile.
Derived database/checkpoints live in a new output directory outside Git.
The snapshot requires its disposable captured game working directory unchanged.
Arguments/snapshots are trusted research input, not an untrusted execution API.
"""
import argparse
import hashlib
import sqlite3
import json
from pathlib import Path
from fdisbull.project import Project

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--project', type=Path, required=True)
ap.add_argument('--game-dir', type=Path, required=True)
ap.add_argument('--backend', type=Path, required=True)
ap.add_argument('--output', type=Path, required=True)
args = ap.parse_args()


def require(condition, message):
    """Keep native observation guards active under ``python -O``."""
    if not condition:
        raise RuntimeError(message)


root = args.output.resolve()
source = args.project.resolve(strict=True)
source_game = args.game_dir.resolve(strict=True)
backend = args.backend.resolve(strict=True)
if root.exists() or any((p / '.git').exists() for p in (root, *root.parents)):
    ap.error('output must be new and outside Git')
if root.is_relative_to(source_game):
    ap.error('output must not be inside the source game directory')
expected_exe = '2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c'
expected_backend = '1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277'
require(hashlib.sha256((source_game / 'DINOPARK.EXE').read_bytes()).hexdigest() == expected_exe,
        'captured DINOPARK.EXE hash does not match the qualified source')
require(hashlib.sha256(backend.read_bytes()).hexdigest() == expected_backend,
        'backend hash does not match the qualified runtime')
root.mkdir(parents=True)
# The runtime binds snapshots to this exact captured game_dir. Do not relabel
# compatibility metadata to make an unqualified relocated checkpoint load.
game = source_game
def inventory():
    return {p.relative_to(game).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(game.rglob('*')) if p.is_file()}
files_before = inventory()
# Use a consistent read-only SQLite snapshot; write forks only into the clone.
with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as original:
    with sqlite3.connect(root / 'study.fdb') as clone:
        original.backup(clone)
fields = {'food': ('4020:6f94', 18), 'pending': ('4020:b9e4', 18),
          'cash': ('4020:5c3a', 4), 'working': ('4020:bad4', 4),
          'month': ('4020:ccfe', 2), 'cost': ('4020:585a', 4),
          'expenses': ('4020:c03b', 48)}
def state(d):
    return {'fields': {k: d.memory(a, length=n)['hex'] for k, (a, n) in fields.items()},
            'scene': d.memory('4020:3c5c', length=2)['hex'], 'active_context_marker': d.memory('4020:3c5a', length=2)['hex'], 'pause_word': d.memory('4020:3c60', length=2)['hex'], 'registers': d.registers(),
            'mouse': d.call('input.mouse.state')}
def raw_read(d, address):
    return d.call('memory.read', {'address': {'space': 'linear', 'offset': f'0x{address:08X}'}, 'length': 10})
with Project(root / 'study.fdb') as p:
    refs = {r['name']: {'artifact': r['id'], 'sha256': r['sha256']} for r in
            p.db.execute("select id,name,sha256 from debug_artifacts where kind='state'")}
    office_ref, prepared_ref = refs['office.sav'], refs['prepared.sav']
    states = {}
    for name, ref in [('office', office_ref), ('prepared', prepared_ref)]:
        with p.debugger(backend, game) as d:
            d.load_state(ref['artifact']); states[name] = state(d)
    office, prepared = states['office'], states['prepared']
    require(office['active_context_marker'] == '0600',
            'office snapshot context marker did not match the qualified value')
    require(prepared['active_context_marker'] == '0400',
            'prepared snapshot context marker did not match the qualified value')
    require(prepared['registers']['cpu_mode'] == 'real',
            'prepared snapshot is not in real mode')
    require(int(prepared['registers']['instruction_pointer'], 16) == 0x2810,
            'prepared snapshot instruction pointer did not match the qualified entry')
    require(prepared['fields']['cost'] == 'f4010000',
            'prepared snapshot cost did not match the qualified value')
    r = prepared['registers']
    stack = int(r['segments']['ss'], 16) * 16 + (int(r['general']['esp'], 16) & 0xffff)
    with p.debugger(backend, game) as d:
        d.load_state(prepared_ref['artifact']); arguments = raw_read(d, stack)
    def reg_map(r):
        return {**r['general'], **r['segments'], 'eip': r['instruction_pointer'], 'flags': r['flags']}
    old, new = reg_map(office['registers']), reg_map(prepared['registers'])
    edits = {k: {'expected': old[k], 'value': v} for k, v in new.items() if old[k] != v}
    bridge = [{'address': fields[k][0], 'expected_hex': office['fields'][k], 'data_hex': v}
              for k, v in prepared['fields'].items() if office['fields'][k] != v]
    foreign = p.debug_fork_state(office_ref['artifact'], backend, game,
                                name='office-data-and-register-bridge.sav', memory=bridge, registers=edits)
    negative = p.debug_fork_state(office_ref['artifact'], backend, game,
                                 name='office-register-bridge-only.sav', registers=edits)
    results = {'scope': 'bounded native slice, not a player purchase',
               'original_exe_sha256': expected_exe, 'backend_sha256': expected_backend,
               'office_parent': office_ref, 'prepared_parent': prepared_ref,
               'bridge': bridge, 'register_edits': edits, 'stack_address': hex(stack),
               'stack_argument_bytes': 10, 'cases': {}}
    for label, ref, copy_stack in [('native-replay', prepared_ref, False),
                                  ('office-prepared', foreign, True),
                                  ('office-unprepared', negative, True)]:
        with p.debugger(backend, game) as d:
            d.load_state(ref['artifact'])
            if copy_stack:
                original = raw_read(d, stack)
                write = d.call('memory.write', {'address': original['address'],
                    'expected_sha256': original['sha256'], 'data_base64': arguments['data_base64']})
                actual = raw_read(d, stack)
                require(actual['data_base64'] == arguments['data_base64'],
                        f'{label}: copied caller-frame bytes did not read back')
                derivation = {'parent': ref, 'runtime_stack_write': write, 'before': original, 'after': actual}
                child = d.save_state(label + '-entry.sav')
                results[label + '-derivation'] = {**derivation, 'child': child}
            before = state(d)
            p.analyze(start='2d0a:283d', max_instructions=8)
            bp = d.breakpoint('2d0a:283d')
            trace = d.trace(label + '-trace.json', count=256, timeout_ms=10000, fast_forward=True)
            row = p.db.execute('select data from debug_artifacts where id=?', (trace['artifact'],)).fetchone()
            t = json.loads(row['data'])
            require(t['run']['outcome'] == 'breakpoint',
                    f'{label}: trace did not stop at a breakpoint')
            require(t['run']['session']['stop_reason']['breakpoint_id'] == bp['breakpoint_id'],
                    f'{label}: trace stopped at a different breakpoint')
            after = state(d)
            results['cases'][label] = {'before': before, 'after': after, 'trace': trace,
                'pc_sequence': [e['project_address'] for e in t['events']],
                'region_exit_reached': True, 'trace_budget_complete': t['complete']}
            d.delete_breakpoint(bp['breakpoint_id'])
            print(label, 'scene', before['scene'], '->', after['scene'],
                  'food', before['fields']['food'], '->', after['fields']['food'], flush=True)
    cases = results['cases']
    results['comparison'] = {
        'prepared_effect_fields_equal': cases['native-replay']['after']['fields'] == cases['office-prepared']['after']['fields'],
        'prepared_instruction_sequence_equal': cases['native-replay']['pc_sequence'] == cases['office-prepared']['pc_sequence'],
        'office_context_preserved_to_exit': cases['office-prepared']['after']['active_context_marker'] == office['active_context_marker'] != prepared['active_context_marker'],
        'parent_sha256_preserved': all(p.debug_state_info(ref['artifact'])['sha256'] == ref['sha256']
                                     for ref in (office_ref, prepared_ref))}
    results['game_files_unchanged'] = inventory() == files_before
    (root / 'effect-results.json').write_text(json.dumps(results, indent=2))
    require(results['game_files_unchanged'], 'captured working-directory files changed')
    require(all(results['comparison'].values()),
            'native comparison invariants did not all hold')
    print('COMPARISON', results['comparison'], flush=True)
