"""A bounded terminal notification handler, not a board or winner checker.

Inputs are u8: status 0=ongoing, 1=win, 2=draw; player 0=none,
1=X, 2=O. Message codes are 0=ongoing, 1=X wins, 2=O wins,
3=draw, 65535=invalid status/player combination. Every u8 pair completes.
"""


def _eq(name, value):
    return {'op': 'eq', 'left': {'var': '$' + name}, 'right': value}


def _and(*conditions):
    return {'op': 'and', 'conditions': list(conditions)}


def _set(value):
    return {'op': 'set', 'var': '$message', 'value': value}


def _if(condition, yes, no=None):
    return {'op': 'if', 'condition': condition, 'then': yes, 'else': no or []}


def _program(body):
    counter = 0

    def identify(blocks):
        nonlocal counter
        result = []
        for block in blocks:
            counter += 1
            block = dict(block, id='step_' + str(counter))
            if block['op'] == 'if':
                block['then'] = identify(block['then'])
                block['else'] = identify(block['else'])
            result.append(block)
        return result

    return {'format': 'fdisbull-il-1', 'role': 'uil',
            'variables': {'$status': {'type': 'u8', 'initial': 0},
                          '$player': {'type': 'u8', 'initial': 0},
                          '$message': {'type': 'u16', 'initial': 0}},
            'resources': {}, 'body': identify(body)}


def variants():
    """Return independent program documents with canonical scalar ports."""
    clean = _program([
        _if(_eq('status', 0),
            [_if(_eq('player', 0), [_set(0)], [_set(65535)])],
            [_if(_eq('status', 1),
                 [_if(_eq('player', 1), [_set(1)],
                      [_if(_eq('player', 2), [_set(2)], [_set(65535)])])],
                 [_if(_and(_eq('status', 2), _eq('player', 0)),
                      [_set(3)], [_set(65535)])])])])
    compact = _program([
        _set(65535),
        _if(_and(_eq('status', 0), _eq('player', 0)), [_set(0)]),
        _if(_and(_eq('status', 1), _eq('player', 1)), [_set(1)]),
        _if(_and(_eq('status', 1), _eq('player', 2)), [_set(2)]),
        _if(_and(_eq('status', 2), _eq('player', 0)), [_set(3)])])
    # Stage the default and explicitly recheck each recognized status.
    # The redundant assignments make the verbose style observable without
    # changing the scalar interface or introducing external effects.
    verbose = _program([
        _set(65535),
        _if(_eq('status', 0), [_set(65535)]),
        _if(_eq('status', 1), [_set(65535)]),
        _if(_eq('status', 2), [_set(65535)]),
        _if(_eq('player', 0),
            [_if(_eq('status', 0), [_set(0)]),
             _if(_eq('status', 2), [_set(3)])],
            [_if(_eq('status', 1),
                 [_if(_eq('player', 1), [_set(1)]),
                  _if(_eq('player', 2), [_set(2)])])])])
    return {'clean': clean, 'compact': compact, 'verbose': verbose}


def contract():
    """The clean program is the exact behavior over the full typed domain."""
    return {'format': 'fdisbull-block-contract-1',
            'name': 'tic_tac_toe.terminal_notification',
            'inputs': {'status': 'u8', 'player': 'u8'},
            'outputs': {'message': 'u16'},
            'behavior': {'kind': 'uil', 'program': variants()['clean']},
            'domain': {}}
