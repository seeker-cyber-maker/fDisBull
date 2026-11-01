"""Authored game slices wired to fDisBull's persisted UDC selections.

This example registers exact UIL contracts and selectable model or C backings.
It does not recover either original game from executable bytes.
"""

from copy import deepcopy

from fdisbull.udc_blueprint import execute_module_uil
from fdisbull.udc_layers import (
    build_selection_shell,
    register_contract,
    register_layer,
    run_selection,
    select_layers,
)

from . import five_dice, tic_tac_toe
from .compiled_replay import replay_compiled


GAMES = {'tic-tac-toe': tic_tac_toe, 'five-dice': five_dice}
STYLES = ('clean', 'compact', 'verbose')


def register_game_variants(project, game):
    """Persist one fixed contract and three IL/C backings per game slice."""
    if game not in GAMES:
        raise ValueError('unknown authored game slice')
    spec = GAMES[game]
    contract = register_contract(project, spec.contract())
    programs = spec.variants()
    if set(programs) != set(STYLES):
        raise ValueError('game slice must supply clean, compact and verbose programs')
    layers = {}
    for backend in ('uil', 'c-uil'):
        layers[backend] = {}
        for style in STYLES:
            layer = register_layer(project, {
                'format': 'fdisbull-udl-layer-1',
                'name': f'authored.{game}.{style}.{backend}',
                'contract': contract['id'],
                'implementation': {'backend': backend, 'program': programs[style]},
                'assurance': 'candidate',
                'evidence': 'authored bounded example; no original-game source correspondence',
            })
            layers[backend][style] = layer['id']
    provider = None
    if game == 'tic-tac-toe':
        service = register_contract(project, {
            'format': 'fdisbull-block-contract-1', 'name': 'authored.tic-tac-toe.notify',
            'inputs': {'value': 'u16'}, 'outputs': {},
            'behavior': {'kind': 'service', 'service': 'ui.notify'},
        })
        provider = register_layer(project, {
            'format': 'fdisbull-udl-layer-1', 'name': 'authored.tic-tac-toe.messages',
            'contract': service['id'],
            'implementation': {
                'backend': 'message-box-a', 'title': 'Tic-Tac-Toe',
                'messages': {'0': 'ongoing', '1': 'x_wins', '2': 'o_wins', '3': 'draw'},
                'default': 'invalid', 'style': 0,
            },
        })['id']
    return {'game': game, 'contract': contract['id'], 'layers': layers, 'provider': provider}


def select_game_variants(project, registered, choices, *, backend='uil'):
    """Pin one terminal style or five independently chosen seed-step styles."""
    game = registered['game']
    if game not in GAMES or backend not in ('uil', 'c-uil'):
        raise ValueError('unknown game slice or implementation backend')
    if game == 'tic-tac-toe':
        if choices not in STYLES:
            raise ValueError('Tic-Tac-Toe needs one named style')
        bindings = {'terminal': registered['layers'][backend][choices],
                    'present': registered['provider']}
        program = GAMES[game].contract()['behavior']['program']
        name = f'authored.{game}.{backend}.{choices}'
    else:
        if type(choices) not in (list, tuple) or len(choices) != 5 or any(choice not in STYLES for choice in choices):
            raise ValueError('Five-Dice needs five named styles, one per roll')
        names = tuple(f'roll{i}' for i in range(1, 6))
        bindings = {name: registered['layers'][backend][style] for name, style in zip(names, choices)}
        program = five_dice.turn_program(registered['contract'], bindings=names)
        name = f'authored.{game}.{backend}.' + '-'.join(choices)
    return select_layers(project, name, bindings, program=program)


def replay_model(project, selection_id, game, *, status=None, player=None, seed=None):
    """Execute a selected IL model using the persisted UIL document."""
    selected = project.udl_selection_info(selection_id, full=True)['document']
    if game == 'tic-tac-toe':
        if type(status) is not int or type(player) is not int:
            raise ValueError('status and player must be integer inputs')
        return run_selection(project, selection_id, 'terminal',
                             {'status': status, 'player': player})
    if game == 'five-dice':
        if type(seed) is not int or not 0 <= seed <= 65535:
            raise ValueError('seed must be u16')
        program = selected['program']
        state = {name: declaration['initial'] for name, declaration in program['variables'].items()}
        state['$seed'] = seed
        return execute_module_uil(project, program, selection_id, state=state)
    raise ValueError('unknown authored game slice')


def native_plan(game, *, status=None, player=None, seed=None):
    """Return a supported native shell plan for the selected C backings."""
    if game == 'tic-tac-toe':
        if type(status) is not int or not 0 <= status <= 255 or type(player) is not int or not 0 <= player <= 255:
            raise ValueError('status and player must be u8')
        return {
            'format': 'fdisbull-native-shell-1', 'entry': 'main',
            'state': {'$status': {'type': 'u8', 'initial': status},
                      '$player': {'type': 'u8', 'initial': player},
                      '$message': {'type': 'u16', 'initial': 65535}},
            'resources': {
                'ongoing': {'kind': 'text', 'text': 'Game in progress'},
                'x_wins': {'kind': 'text', 'text': 'X wins'},
                'o_wins': {'kind': 'text', 'text': 'O wins'},
                'draw': {'kind': 'text', 'text': 'Draw'},
                'invalid': {'kind': 'text', 'text': 'Invalid terminal state'},
            },
            'functions': {'main': {'body': [
                {'op': 'call', 'binding': 'terminal'},
                {'op': 'notify', 'binding': 'present', 'value': {'var': '$message'}},
            ], 'return': {'var': '$message'}}},
        }
    if game == 'five-dice':
        if type(seed) is not int or not 0 <= seed <= 65535:
            raise ValueError('seed must be u16')
        body = []
        for index in range(1, 6):
            body.extend(({'op': 'call', 'binding': f'roll{index}'},
                         {'op': 'set', 'var': '$seed', 'value': {'var': '$next'}}))
        return {'format': 'fdisbull-native-shell-1', 'entry': 'main',
                'state': {'$seed': {'type': 'u16', 'initial': seed},
                          '$next': {'type': 'u16', 'initial': 0}},
                'resources': {},
                'functions': {'main': {'body': body, 'return': {'var': '$next'}}}}
    raise ValueError('unknown authored game slice')


def build_native(project, selection_id, game, destination, *, c_compiler,
                 target='linux-x64', status=None, player=None, seed=None):
    """Compile selected C-UIL layers into a fresh private PE or ELF shell."""
    selected = project.udl_selection_info(selection_id, full=True)['document']
    for binding, layer_id in selected['bindings'].items():
        if binding == 'present':
            continue
        layer = project.udl_layer_info(layer_id, full=True)['document']
        if layer['implementation']['backend'] != 'c-uil':
            raise ValueError('native example requires c-uil layers')
    plan = native_plan(game, status=status, player=player, seed=seed)
    adapters = {'present': {'backend': 'linux-stdout', 'acknowledgment': 'none'}} if game == 'tic-tac-toe' and target == 'linux-x64' else None
    return build_selection_shell(project, selection_id, deepcopy(plan), destination,
                                 target=target, service_adapters=adapters,
                                 capture_state=target == 'linux-x64', c_compiler=c_compiler)
