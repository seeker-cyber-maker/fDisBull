#!/usr/bin/env python3
"""Check published damage receipts; optionally verify their exact private source.

No target execution, process attachment, network access, or installation occurs.
Checks validate retained evidence consistency, not a new observation of gameplay.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--scene-tools', type=Path, required=True)
    parser.add_argument('--main-exe', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; preserve prior receipts and choose a new file')
    sys.path.insert(0, str(args.scene_tools.resolve()))
    from damage_observation import RecordedDamageBackend, validate_recorded_witness
    from fdisbull_player import Player
    checks = []
    def check(name: str, condition: bool):
        if not condition: raise ValueError(name)
        checks.append(name)
    def read(name): return json.loads((args.evidence / name).read_text())
    record = read('damage-event.json'); chain = read('causal-chain.json')
    check('published causal events equal original receipt', record['events'] == chain['events'])
    check('no native health/code/register edits', record['interventions'] == {'health_writes': 0, 'code_edits': 0, 'register_edits': 0})
    world = read('world-evidence.json')
    check('world sampling count', world['snapshots'] == 393)
    check('car stationary across recorded samples', world['car_positions_raw'] == [[15496, 9144, 256]] and not world['car_moved_in_observed_snapshots'])
    check('no police in sampled census', world['police_count_each_snapshot'] == 0)
    check('nearest guard is not causal shooter', world['nearest_guard_id'] == 'person-10' and world['source_guard_id_after_native_trace'] == 'person-11')
    check('source observation subtracts one', world['health_before'] - world['health_after'] == 1)
    comparison = read('method-comparison.json')
    for arm, requests in [('world', 121), ('native', 49)]:
        runs = comparison[arm]['runs']; check(arm + ' three repeats', len(runs) == 3)
        check(arm + ' metered calls', all(sum(r['requests'].values()) == r['request_total'] == requests for r in runs))
        check(arm + ' median', statistics.median(r['wall_seconds'] for r in runs) == comparison[arm]['median_wall_seconds'])
    friction = read('watch-metadata-friction.json')
    check('watch address is not CPU PC', friction['reported_stop_metadata']['resume_pc']['offset'] != friction['actual_register_ip'])
    check('unchanged owner store is retained', friction['effect_owner_unchanged_negative_control']['old'] == friction['effect_owner_unchanged_negative_control']['new'])
    scene_check = 'not supplied; retained public event only'
    if (args.evidence / 'damage-scene.json').exists():
        snapshot = read('damage-scene.json'); fact = validate_recorded_witness(snapshot, record)
        check('correct shooter', fact['shooter_id'] == 'person-11')
        check('source-bound weapon name', fact['weapon_name'] == 'PISTOL')
        backend = RecordedDamageBackend(snapshot, record); before = backend.observe()
        result = Player(backend).execute_result('examine last damage')
        check('passive existing Player view', result['status'] == 'read' and not result['action_sent'])
        check('view remains unchanged', backend.observe() == before)
        scene_check = 'recorded diagnostic scene, not live collection'
    source = 'not supplied'
    if args.main_exe is not None:
        from fdisbull.le import load_le
        data = args.main_exe.read_bytes()
        check('exact original identity', hashlib.sha256(data).hexdigest() == record['main_sha256'])
        image = load_le(data)
        def span(at, size):
            for region in image.regions:
                if region.start <= at and at + size <= region.start + len(region.data):
                    return bytes(region.data[at-region.start:at-region.start+size])
            raise ValueError('Source span is outside one mapped object')
        labels = read('source-labels.json')
        for name, window in labels['windows'].items():
            check('source window ' + name, hashlib.sha256(span(int(window['preferred_start'], 16), window['length'])).hexdigest() == window['sha256'])
        pointer = int.from_bytes(span(int(labels['selected_pointer_slot'], 16), 4), 'little')
        check('weapon label pointer', pointer == int(labels['name_pointer'], 16))
        check('original English weapon name', span(pointer, 32).split(b'\0',1)[0].decode('ascii') == labels['name'] == 'PISTOL')
        source = 'five original mapped-code windows and selected name pointer verified'
    result = {'status': 'passed', 'checks': len(checks), 'assertions': checks,
              'source_check': source, 'scene_check': scene_check,
              'native_game_rerun': False, 'scope': 'Retained receipt consistency and optional original static identities'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as out: json.dump(result, out, indent=2); out.write('\n')
    print(json.dumps(result, indent=2)); return 0

if __name__ == '__main__':
    raise SystemExit(main())
