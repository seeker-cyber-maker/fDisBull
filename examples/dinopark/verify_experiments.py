#!/usr/bin/env python3
"""Verify saved experiments against user-owned DinoPark, with private states.

Output must be a new directory outside Git. Only evidence/ is shareable;
private/ contains a copied game, the project database and native checkpoints.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import fdisbull
from fdisbull import __version__
from fdisbull.project import Project


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    result = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Game input contains a symbolic link')
        if path.is_file():
            result.append({'path': path.relative_to(root).as_posix(), 'sha256': digest(path)})
    return result


def click(x, y, name, guest_ms, hold_ms=150):
    return [{'op': 'click-frame', 'x': x, 'y': y, 'name': name + '.png', 'hold_ms': hold_ms},
            {'op': 'run', 'guest_ms': guest_ms, 'timeout_ms': 5000}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True, type=Path)
    parser.add_argument('--game-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    backend = args.executable.resolve(strict=True)
    game = args.game_dir.resolve(strict=True)
    output = args.output.resolve()
    if output == game or game in output.parents or output in game.parents:
        raise ValueError('Output must be separate from game inputs')
    if any((parent / '.git').exists() for parent in [output, *output.parents]):
        raise ValueError('Private experiment output must be outside Git')
    assert digest(game / 'DINOPARK.EXE') == '2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c'
    assert digest(game / 'DINOSG.001') == 'bf7af4fa7b57c96ff67dcd545d4b6873aee70681c0a197844fd73a84c40d32c5'
    original = inventory(game)
    output.mkdir(parents=True, exist_ok=False)
    private = output / 'private'; private.mkdir()
    evidence = output / 'evidence'; evidence.mkdir()
    mounted = private / 'game'; shutil.copytree(game, mounted)
    database = private / 'dinopark.fdb'
    processes = []
    report = {'version': __version__, 'module': fdisbull.__file__, 'driver_sha256': digest(Path(__file__)),
              'backend_sha256': digest(backend), 'source_sha256': digest(game / 'DINOPARK.EXE')}
    boot = [{'op': 'run', 'guest_ms': 35000, 'timeout_ms': 10000, 'fast_forward': True}]
    for x, y, name, ms in [(160, 160, 'old-game', 1500), (90, 70, 'select-pmm', 300), (250, 73, 'load-pmm', 3000)]:
        boot += click(x, y, name, ms)
    store = [{'op': 'run', 'guest_ms': 120, 'timeout_ms': 3000}]
    for x, y, name, ms in [(260, 120, 'general-store', 1200), (265, 145, 'enter-store', 1600),
                            (205, 105, 'catalogue', 1000), (263, 165, 'cover', 1000), (195, 54, 'concessions', 1500)]:
        store += click(x, y, name, ms, 500)
    store.append({'op': 'screenshot', 'name': 'concessions-grid8.png', 'grid': True, 'grid_step': 8})
    (evidence / 'navigation.json').write_text(json.dumps({'format': 'fdisbull-script-1', 'steps': boot}, indent=2) + '\n')
    (evidence / 'street-to-concessions.json').write_text(json.dumps({'format': 'fdisbull-script-1', 'steps': store}, indent=2) + '\n')
    with Project.create(database, mounted / 'DINOPARK.EXE', load_segment=0x1000) as p:
        p.analyze(start='334b:0ca2', max_instructions=8)
        with p.debugger(backend, mounted) as d:
            processes.append(d.rpc.process)
            routed = d.script({'format': 'fdisbull-script-1', 'steps': boot}, timeout_ms=60000)
            assert routed['ok'], routed
            street = d.save_state('street.sav')
        with p.debugger(backend, mounted) as d:
            processes.append(d.rpc.process)
            d.load_state(street['artifact'])
            routed = d.script({'format': 'fdisbull-script-1', 'steps': store}, timeout_ms=60000)
            assert routed['ok'], routed
            assert d.code('334b:0c9e', length=4, view='ram')['hex'] == '8b877568'
            assert d.memory('0x46a75', length=8)['hex'] == '8813e8034c1d1027'
            layer = p.debug_layer('Gift lookup selects the 5000 entry', kind='execute', patches=[
                {'address': '334b:0c9e', 'expected_hex': '8b877568', 'data_hex': '8b877168'}])['layer']
            bp = d.breakpoint('334b:0ca3')
            watch = d.breakpoint('0x46a75', access='r', length=8)
            fs = d.registers()['segments']['fs']
            hook = d.hook('1000:75bc', actions=[{'op': 'registers', 'registers': {'fs': {'expected': fs, 'value': fs}}}])
            steps = [{'op': 'run', 'guest_ms': 120, 'timeout_ms': 3000}]
            steps += [{'op': 'click-frame', 'x': 195, 'y': 85, 'name': 'gift-selection-grid8.png', 'hold_ms': 150},
                      {'op': 'run', 'timeout_ms': 5000, 'as': 'price_watch'},
                      {'op': 'assert', 'value': '$price_watch.session.stop_reason.data_access.project_instruction', 'equals': '0x3414e'},
                      {'op': 'registers', 'as': 'selected_price'}]
            steps += [{'op': 'delete-breakpoint', 'breakpoint_id': '$controls.breakpoints.' + b['breakpoint_id'] + '.breakpoint_id'}
                      for b in watch['breakpoints']]
            steps += [{'op': 'run', 'timeout_ms': 5000, 'as': 'execution_stop'},
                      {'op': 'assert', 'value': '$execution_stop.session.stop_reason.project_address', 'equals': '0x34153'},
                      {'op': 'registers'},
                      {'op': 'delete-breakpoint', 'breakpoint_id': '$controls.breakpoints.' + bp['breakpoint_id'] + '.breakpoint_id'},
                      {'op': 'trace', 'name': 'selected-price.json', 'count': 16, 'timeout_ms': 5000},
                      {'op': 'run', 'guest_ms': 1000, 'timeout_ms': 5000},
                      {'op': 'screenshot', 'name': 'after-selection-grid8.png', 'grid': True, 'grid_step': 8}]
            script = {'format': 'fdisbull-script-1', 'steps': steps}
            (evidence / 'price-experiment-script.json').write_text(json.dumps(script, indent=2) + '\n')
            saved_script = p.debug_save_script('gift price trial', script)
            saved = d.save_experiment('gift price baseline', script_id=saved_script['script_id'],
                                      observations=[{'address': '0x46a75', 'length': 8}])
            # Deliberately remove every saved control before leaving the original session.
            d.delete_hook(hook['hook'])
            for b in watch['breakpoints']:
                d.delete_breakpoint(b['breakpoint_id'])
            d.delete_breakpoint(bp['breakpoint_id'])
            assert d.controls() == {'breakpoints': [], 'hooks': []}
        report.update(experiment=saved['artifact'], layer=layer, layer_definition=p.debug_layer_info(layer),
                      original_controls_removed=True)
    with Project(database) as p:
        with p.debugger(backend, mounted) as d:
            processes.append(d.rpc.process)
            compared = d.compare_experiment(saved['artifact'], layers=[layer], timeout_ms=60000)
            assert compared['ok'], compared
            assert compared['comparison']['observed_difference'] is True
            prices = []
            for name in ('baseline', 'layer'):
                trial = compared[name]
                selected = next(o for o in trial['observations'] if o['op'] == 'registers')
                prices.append(int(selected['value']['general.eax'], 16) & 0xffff)
                body = json.loads(bytes(p.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (trial['script_report'],)).fetchone()[0]))
                hits = [hit for step in body['steps'] for hit in step.get('result', {}).get('hook_hits', [])]
                assert len(hits) == 1 and hits[0]['hit'] == 1
            assert prices == [7500, 5000], prices
            assert len(d.controls()['breakpoints']) == 9
            assert len(d.hooks()['hooks']) == 1 and d.hooks()['hooks'][0]['hits'] == 0
            assert d.layers()['active'] == []
            assert d.code('334b:0c9e', length=4, view='ram')['hex'] == '8b877568'
            assert d.memory('0x46a75', length=8)['hex'] == '8813e8034c1d1027'
            report.update(result='pass', prices=prices, comparison=compared['artifact'], breakpoint_restored=True,
                          read_watch_bytes_restored=8, once_hook_restored=True, once_hook_fired_once_per_trial=True,
                          hook_hit_count_restored=0, baseline_layers_restored=True, code_ram_unchanged=True,
                          price_table_unchanged=True, fresh_session_restore=True)
    # Reopen once more: export only reports, scripts, traces and authentic frames.
    with Project(database) as p:
        p.debug_export(compared['artifact'], evidence / 'comparison.json')
        for item in p.debug_artifacts()['artifacts']:
            if item['kind'] in ('script', 'script-result', 'trace', 'screenshot', 'screenshot-grid'):
                p.debug_export(item['id'], evidence / (item['id'] + '-' + item['name']))
    assert all(process.poll() is not None for process in processes)
    assert inventory(game) == original and inventory(mounted) == original
    report.update(processes_reaped=True, game_files_unchanged=len(original), native_states_exported=False,
                  database_exported=False, evidence_exported_after_restart=True)
    (evidence / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n')
    (evidence / 'SHA256SUMS.json').write_text(json.dumps({p.name: digest(p) for p in sorted(evidence.iterdir())}, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
