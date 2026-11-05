"""Build small, explicitly authored world/observer fixtures for three settings.

All coordinates, IDs, quantities, states, and proposed contract names are invented
for the study. The examples are not decoded maps or recovered game execution.
"""
from copy import deepcopy
import json
from pathlib import Path

from world_view import PROFILE, validate


ROOT = Path(__file__).resolve().parent / 'examples'


def space(identifier, kind, parent=None, dimensions=0):
    return {'id': identifier, 'kind': kind, 'parent': parent, 'dimensions': dimensions}


def view(identifier, title, parent=None, spaces=(), descendants=False, kinds=(), entities=()):
    return {'id': identifier, 'title': title, 'parent': parent, 'spaces': list(spaces),
            'descendants': descendants, 'kinds': list(kinds), 'entities': list(entities)}


def location(identifier, *position):
    result = {'space': identifier}
    if position:
        result['position'] = list(position)
    return result


def entity(identifier, kind, label, where, **fields):
    return {'id': identifier, 'kind': kind,
            'state': {'label': label, 'kind': kind, 'location': where, **fields},
            'bindings': {'status': 'unbound-authored-metadata',
                         'proposed_uil_object': 'fixture-object:' + identifier,
                         'source_registers_or_addresses': 'not recovered'}}


def action(identifier, label, contract):
    return {'id': identifier, 'label': label, 'uil_contract_ref': contract, 'binding_status': 'unbound'}


def world(identifier, setting, unit, position, spaces, entities, views, actions):
    return {'format': PROFILE,
            'world': {'id': identifier, 'setting': setting,
                      'evidence': 'authored-design-fixture', 'coverage': 'illustrative-partial'},
            'clock': {'unit': unit, 'position': position}, 'spaces': spaces,
            'entities': entities, 'views': views, 'observers': [], 'actions': actions}


def observation(document, identifier, admitted, remembered=None, unknown=()):
    authority = next(item for item in document['entities'] if item['id'] == identifier)
    fields = {key: {'knowledge': 'current', 'value': deepcopy(authority['state'][key]),
                    'observed_at': deepcopy(document['clock'])} for key in admitted}
    for key, (value, when) in (remembered or {}).items():
        fields[key] = {'knowledge': 'remembered', 'value': deepcopy(value),
                       'observed_at': {'unit': document['clock']['unit'], 'position': when}}
    for key in unknown:
        fields[key] = {'knowledge': 'unknown'}
    return {'entity': identifier, 'fields': fields}


def observers(document, knowledge):
    document['observers'] = [
        {'id': 'player', 'records': knowledge, 'actions': [a['id'] for a in document['actions']]},
        {'id': 'uninformed', 'records': [], 'actions': []},
    ]
    return document


def syndicate():
    d = world('syndicate-authored-world', 'Original Syndicate-inspired synthetic mission',
              'simulation_tick', 1200,
              [space('campaign', 'abstract'), space('territory-1', 'abstract', 'campaign'),
               space('district-west', 'grid', 'territory-1', 2),
               space('district-east', 'grid', 'territory-1', 2),
               space('vehicle-cabin', 'abstract', 'district-west'),
               space('tunnel', 'graph', 'district-west')],
              [entity('territory-1', 'territory', 'Territory A', location('territory-1'), control='rival'),
               entity('agent-1', 'agent', 'Agent One', location('district-west', 20, 7), hp=80, order='hold'),
               entity('agent-2', 'agent', 'Agent Two', location('vehicle-cabin'), hp=75, aboard='vehicle-1'),
               entity('vehicle-1', 'vehicle', 'Team vehicle', location('district-west', 21, 7), occupants=['agent-2']),
               entity('contact-1', 'agent', 'Observed contact', location('district-east', 70, 9), hp=17, affiliation='rival'),
               entity('unseen-1', 'agent', 'Unseen operative', location('district-east', 71, 9), hp=99, secret_alarm=777)],
              [view('campaign', 'Campaign territories', spaces=['campaign'], descendants=True, kinds=['territory']),
               view('mission-west', 'Mission: western district', 'campaign', ['district-west'], True),
               view('mission-east', 'Mission: eastern district', 'campaign', ['district-east'], True),
               view('squad', 'Squad status', 'mission-west', entities=['agent-1', 'agent-2', 'vehicle-1'])],
              [action('move-squad', 'Request squad movement', 'proposed.syndicate.move_squad'),
               action('board-vehicle', 'Request vehicle boarding', 'proposed.syndicate.board_vehicle')])
    return observers(d, [
        observation(d, 'territory-1', ['label', 'kind', 'location', 'control']),
        observation(d, 'agent-1', ['label', 'kind', 'location', 'hp', 'order']),
        observation(d, 'agent-2', ['label', 'kind', 'location', 'hp', 'aboard']),
        observation(d, 'vehicle-1', ['label', 'kind', 'location', 'occupants']),
        observation(d, 'contact-1', ['kind'],
                    remembered={'label': ('Observed contact', 1190),
                                'location': (location('district-west', 8, 9), 1190),
                                'affiliation': ('rival', 1190)}, unknown=['hp']),
    ])


def civilization():
    d = world('civilization-authored-world', 'Original Civilization-inspired synthetic map and city',
              'turn', 42,
              [space('world-map', 'grid', dimensions=2), space('empire-administration', 'abstract')],
              [entity('city-1', 'city', 'City A', location('world-map', 8, 4), population=3,
                      worked_tiles=['tile-1', 'tile-2'], food_store=12, production='unit'),
               entity('tile-1', 'tile', 'Western worked tile', location('world-map', 7, 4), terrain='grassland', worked_by='city-1'),
               entity('tile-2', 'tile', 'Eastern worked tile', location('world-map', 9, 4), terrain='hills', worked_by='city-1'),
               entity('unit-1', 'unit', 'Scout A', location('world-map', 9, 3), moves_left=1),
               entity('government', 'controller', 'Empire administration', location('empire-administration'), treasury=120, research='authored-topic'),
               entity('rival-unit', 'unit', 'Rival scout', location('world-map', 11, 5), moves_left=2)],
              [view('world', 'Known world map', spaces=['world-map']),
               view('city-1', 'City A economy', 'world', entities=['city-1', 'tile-1', 'tile-2']),
               view('units', 'Known unit view', 'world', kinds=['unit']),
               view('empire', 'Empire overview')],
              [action('move-unit', 'Request unit movement', 'proposed.civilization.move_unit'),
               action('assign-worked-tile', 'Request a worked-tile assignment', 'proposed.civilization.assign_worked_tile'),
               action('end-turn', 'Request complete turn resolution', 'proposed.civilization.end_turn')])
    return observers(d, [
        observation(d, 'city-1', ['label', 'kind', 'location', 'population', 'worked_tiles', 'food_store', 'production']),
        observation(d, 'tile-1', ['label', 'kind', 'location', 'terrain', 'worked_by']),
        observation(d, 'tile-2', ['label', 'kind', 'location', 'terrain', 'worked_by']),
        observation(d, 'unit-1', ['label', 'kind', 'location', 'moves_left']),
        observation(d, 'government', ['label', 'kind', 'location', 'treasury', 'research']),
        observation(d, 'rival-unit', [], remembered={'label': ('Rival scout', 40),
                    'kind': ('unit', 40), 'location': (location('world-map', 10, 4), 40)}, unknown=['moves_left']),
    ])


def colonization():
    d = world('colonization-authored-world', 'Original Colonization-inspired synthetic colony and voyage',
              'turn', 12,
              [space('america', 'grid', dimensions=2), space('colony-workplaces', 'abstract', 'america'),
               space('colony-harbor', 'abstract', 'america'), space('europe-harbor', 'abstract'),
               space('outbound-transit', 'abstract'), space('return-transit', 'abstract')],
              [entity('colony-1', 'colony', 'Colony A', location('america', 5, 6), warehouse_food=40, construction='warehouse'),
               entity('colonist-1', 'colonist', 'Worker A', location('colony-workplaces'), assignment='farm', assigned_tile='tile-1'),
               entity('colonist-2', 'colonist', 'Worker B', location('colony-workplaces'), assignment='workshop'),
               entity('tile-1', 'tile', 'Worked field', location('america', 6, 6), worked_by='colonist-1'),
               entity('ship-1', 'ship', 'Merchant A', location('europe-harbor'), cargo={'goods': 'tobacco', 'amount': 30}),
               entity('ship-2', 'ship', 'Merchant B', location('outbound-transit'), destination='europe-harbor', transit_remaining=2),
               entity('ship-3', 'ship', 'Merchant C', location('return-transit'), destination='america', transit_remaining=1),
               entity('market', 'market', 'European market', location('europe-harbor'), tobacco_price=5)],
              [view('world', 'Known American map', spaces=['america'], descendants=True),
               view('colony-1', 'Colony A settlement', 'world', entities=['colony-1', 'colonist-1', 'colonist-2', 'tile-1']),
               view('people', 'Colony A people', 'colony-1', entities=['colonist-1', 'colonist-2']),
               view('europe', 'Europe and voyage states', spaces=['europe-harbor', 'outbound-transit', 'return-transit']),
               view('ships', 'Known ships across all locations', kinds=['ship']),
               view('economy', 'Colonial economy overview')],
              [action('assign-worker', 'Request worker reassignment', 'proposed.colonization.assign_worker'),
               action('load-cargo', 'Request cargo loading', 'proposed.colonization.load_cargo'),
               action('sail-to-europe', 'Request voyage to Europe', 'proposed.colonization.sail_to_europe'),
               action('sell-cargo', 'Request market sale', 'proposed.colonization.sell_cargo')])
    return observers(d, [observation(d, entity['id'], list(entity['state'])) for entity in d['entities']])


def build():
    ROOT.mkdir(parents=True, exist_ok=True)
    for name, builder in [('syndicate', syndicate), ('civilization', civilization), ('colonization', colonization)]:
        document = builder()
        validate(document)
        (ROOT / (name + '.json')).write_text(json.dumps(document, indent=2) + '\n')


if __name__ == '__main__':
    build()
    print('Built three authored world-view fixtures.')
