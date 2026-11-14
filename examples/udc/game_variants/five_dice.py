"""Authored Five-Dice seed and turn examples for the bounded UIL model.

The seed step is the authored 16-bit LCG ``x' = 5*x + 1 mod 65536``. It is
deterministic and reproducible, but makes no claim about statistical quality
or fidelity to any private game.
"""


def _program(body):
    return {
        'format': 'fdisbull-il-1',
        'role': 'uil',
        'variables': {'$seed': {'type': 'u16', 'initial': 0},
                      '$next': {'type': 'u16', 'initial': 0},
                      '$scratch': {'type': 'u16', 'initial': 0}},
        'resources': {},
        'body': [dict(block, id=f'b{i}') for i, block in enumerate(body, 1)],
    }


def contract():
    """Return the shared exact UIL contract for one seed transition."""
    return {
        'format': 'fdisbull-block-contract-1',
        'name': 'five-dice.seed-step',
        'inputs': {'seed': 'u16'},
        'outputs': {'next': 'u16'},
        'domain': {},
        'behavior': {'kind': 'uil', 'program': _program([
            {'op': 'set', 'var': '$next', 'value': {'var': '$seed'}},
            {'op': 'add', 'var': '$next', 'value': {'var': '$seed'}},
            {'op': 'add', 'var': '$next', 'value': {'var': '$seed'}},
            {'op': 'add', 'var': '$next', 'value': {'var': '$seed'}},
            {'op': 'add', 'var': '$next', 'value': {'var': '$seed'}},
            {'op': 'add', 'var': '$next', 'value': 1},
        ])},
    }


def variants():
    """Three structurally distinct UIL implementations of the seed step."""
    return {
        'clean': {'format': 'fdisbull-il-1', 'role': 'uil',
                  'variables': {'$seed': {'type': 'u16', 'initial': 0},
                                '$next': {'type': 'u16', 'initial': 0},
                                '$scratch': {'type': 'u16', 'initial': 0}},
                  'resources': {}, 'body': [
                      {'id': 'copy-seed', 'op': 'set', 'var': '$next', 'value': {'var': '$seed'}},
                      {'id': 'add-seed-1', 'op': 'add', 'var': '$next', 'value': {'var': '$seed'}},
                      {'id': 'add-seed-2', 'op': 'add', 'var': '$next', 'value': {'var': '$seed'}},
                      {'id': 'add-seed-3', 'op': 'add', 'var': '$next', 'value': {'var': '$seed'}},
                      {'id': 'add-seed-4', 'op': 'add', 'var': '$next', 'value': {'var': '$seed'}},
                      {'id': 'increment', 'op': 'add', 'var': '$next', 'value': 1}]},
        'compact': _program([
            {'op': 'set', 'var': '$next', 'value': {'var': '$seed'}},
            {'op': 'add', 'var': '$next', 'value': {'var': '$next'}},
            {'op': 'add', 'var': '$next', 'value': {'var': '$next'}},
            {'op': 'add', 'var': '$next', 'value': {'var': '$seed'}},
            {'op': 'add', 'var': '$next', 'value': 1},
        ]),
        'verbose': _program([
            {'op': 'set', 'var': '$next', 'value': {'var': '$seed'}},
            {'op': 'add', 'var': '$next', 'value': {'var': '$seed'}},
            {'op': 'add', 'var': '$next', 'value': {'var': '$seed'}},
            {'op': 'add', 'var': '$next', 'value': {'var': '$seed'}},
            {'op': 'add', 'var': '$next', 'value': {'var': '$seed'}},
            {'op': 'subtract', 'var': '$next', 'value': 65535},
            {'op': 'set', 'var': '$scratch', 'value': {'var': '$seed'}},
            {'op': 'add', 'var': '$scratch', 'value': {'var': '$seed'}},
            {'op': 'subtract', 'var': '$scratch', 'value': {'var': '$seed'}},
            {'op': 'add', 'var': '$next', 'value': 0},
            {'op': 'subtract', 'var': '$next', 'value': 0},
        ]),
    }


def turn_program(contract_id, bindings=None):
    """Return a module UIL turn that invokes one selected seed variant and
    derives five one-based die faces from successive seed transitions.

    The module interface intentionally uses the normal persisted selection
    mechanism, so callers can qualify each move and mix variants by replacing
    the selected binding between turns. The five generated faces are an
    authored bounded example, not a recovered game's rules.
    """
    if bindings is None:
        bindings = ('rng',) * 5
    if len(bindings) != 5 or any(not isinstance(name, str) or not name for name in bindings):
        raise ValueError('bindings must contain exactly five non-empty binding names')
    variables = {'$seed': {'type': 'u16', 'initial': 1}}
    body = []
    for i in range(1, 6):
        face = f'$face{i}'
        variables[face] = {'type': 'u16', 'initial': 0}
        body.extend([
            {'id': f'step-{i}', 'op': 'invoke', 'binding': bindings[i - 1],
             'contract': contract_id, 'inputs': {'seed': {'var': '$seed'}},
             'outputs': {'next': '$seed'}},
            {'id': f'copy-{i}', 'op': 'set', 'var': face, 'value': {'var': '$seed'}},
            {'id': f'reduce-{i}', 'op': 'remainder', 'var': face, 'value': 6},
            {'id': f'face-{i}', 'op': 'add', 'var': face, 'value': 1},
        ])
    return {'format': 'fdisbull-module-uil-1', 'role': 'uil',
            'variables': variables, 'resources': {}, 'body': body}
