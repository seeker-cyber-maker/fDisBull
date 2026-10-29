"""Authored synthetic source backing; not recovered DinoPark code."""
import json
import sys


def commit(values, ready):
    state = dict(zip(('cash', 'working', 'stock', 'pending', 'expense'), values))
    checkpoints = []
    if ready:
        state['stock'] = state['pending']
        checkpoints.append(state.copy())
        state['expense'] = (state['expense'] + 500) & 0xffffffff
        checkpoints.append(state.copy())
        state['cash'] = state['working']
        checkpoints.append(state.copy())
    encode = lambda s: {k: str(v) for k, v in s.items()}
    return {'status': 'complete' if ready else 'refused', 'state': encode(state),
            'events': ['stock', 'expense', 'cash'] if ready else [],
            'checkpoints': [encode(s) for s in checkpoints]}


if __name__ == '__main__':
    print(json.dumps(commit([int(v) for v in sys.argv[1:6]], sys.argv[6] == '1')))
