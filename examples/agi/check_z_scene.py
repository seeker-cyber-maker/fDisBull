"""Exercise a generated diagnostic scene; export hashes, not game text."""
import argparse
import hashlib
import json
from pathlib import Path

from fdisbull.il_scenes import ILSceneBackend
from fdisbull_player import Player


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='new receipt file')
    args = parser.parse_args()
    raw = args.scene.read_bytes()
    backend = ILSceneBackend(json.loads(raw)); player = Player(backend)
    if backend.state != {'$object13_drawn': True}:
        raise ValueError('Unexpected diagnostic starting state')
    results = []
    for command in ('look', 'use water', 'use departure', 'use departure'):
        output = player.execute(command)
        expected = ('diagnostic probes' in output if command == 'look' else
                    output == 'Rejected: Action refused.' if len(results) == 3 else
                    output.startswith('Success:'))
        if not expected:
            raise ValueError('Unexpected player result')
        results.append({'command': command, 'output_sha256': hashlib.sha256(output.encode()).hexdigest()})
    if backend.state != {'$object13_drawn': False} or not backend.observe()['coverage']['partial']:
        raise ValueError('Unexpected final state or coverage')
    if backend.save('after')['status'] != 'saved' or backend.load('after')['status'] != 'restored':
        raise ValueError('In-memory checkpoint failed')
    if player.execute('use departure') != 'Rejected: Action refused.':
        raise ValueError('Restored state did not preserve refusal')
    receipt = {'format': 'fdisbull-agi-z-player-check-2', 'scene_sha256': hashlib.sha256(raw).hexdigest(),
               'results': results, 'object_13_drawn': {'before': True, 'after': False},
               'repeat_refused': True, 'in_memory_save_load_refusal': True, 'partial': True}
    with args.output.open('x') as stream:
        json.dump(receipt, stream, indent=2); stream.write('\n')
    print(json.dumps({'receipt': str(args.output)}))


if __name__ == '__main__':
    main()
