"""Behavioral checks for view identity, observer knowledge and pagination."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from world_view import WorldView, validate


ROOT = Path(__file__).resolve().parent


def fixture(name):
    return json.loads((ROOT / 'examples' / (name + '.json')).read_text())


def by_id(result):
    return {row['entity']: row['fields'] for row in result['entities']}


class LargeWorldViews(unittest.TestCase):
    def test_three_fixtures_validate_and_actions_are_unbound(self):
        for name in ('syndicate', 'civilization', 'colonization'):
            with self.subTest(setting=name):
                doc = fixture(name)
                self.assertTrue(validate(doc))
                view = WorldView(doc).observe(doc['views'][0]['id'], 'player', 128)
                self.assertFalse(view['actions_executable'])
                self.assertTrue(view['action_descriptions'])
                self.assertEqual({a['binding_status'] for a in view['action_descriptions']}, {'unbound'})

    def test_civilization_city_and_tiles_have_one_identity_across_views(self):
        world = WorldView(fixture('civilization'))
        map_view = by_id(world.observe('world', 'player', 128))
        city_view = by_id(world.observe('city-1', 'player', 128))
        self.assertEqual(set(city_view), {'city-1', 'tile-1', 'tile-2'})
        for identifier in city_view:
            self.assertEqual(city_view[identifier], map_view[identifier])
        self.assertEqual(city_view['city-1']['worked_tiles']['value'], ['tile-1', 'tile-2'])

    def test_colonist_identity_matches_people_settlement_and_world(self):
        world = WorldView(fixture('colonization'))
        observed = [by_id(world.observe(view, 'player', 128))['colonist-1']
                    for view in ('people', 'colony-1', 'world')]
        self.assertEqual(observed[0], observed[1])
        self.assertEqual(observed[1], observed[2])
        self.assertEqual(observed[0]['assigned_tile']['value'], 'tile-1')

    def test_offmap_ships_retain_identity_without_inventing_coordinates(self):
        world = WorldView(fixture('colonization'))
        europe = by_id(world.observe('europe', 'player', 128))
        ships = by_id(world.observe('ships', 'player', 128))
        american = by_id(world.observe('world', 'player', 128))
        self.assertEqual(set(ships), {'ship-1', 'ship-2', 'ship-3'})
        for identifier in ships:
            self.assertEqual(ships[identifier], europe[identifier])
            self.assertNotIn(identifier, american)
            self.assertNotIn('position', ships[identifier]['location']['value'])
        self.assertEqual(ships['ship-2']['location']['value']['space'], 'outbound-transit')

    def test_squad_and_district_share_interior_agent_identity(self):
        world = WorldView(fixture('syndicate'))
        mission = by_id(world.observe('mission-west', 'player', 128))
        squad = by_id(world.observe('squad', 'player', 128))
        self.assertEqual(mission['agent-2'], squad['agent-2'])
        self.assertEqual(squad['agent-2']['location']['value'], {'space': 'vehicle-cabin'})

    def test_observation_does_not_change_authority_clock_or_epoch(self):
        world = WorldView(fixture('civilization'))
        before = world.private_snapshot()
        epoch = world.epoch()
        world.observe('world', 'player', 1)
        world.observe('city-1', 'player', 128)
        self.assertEqual(world.private_snapshot(), before)
        self.assertEqual(world.epoch(), epoch)

    def test_remembered_location_controls_membership_not_hidden_current_location(self):
        document = fixture('syndicate')
        original = WorldView(document)
        west = by_id(original.observe('mission-west', 'player', 128))
        east = by_id(original.observe('mission-east', 'player', 128))
        self.assertIn('contact-1', west)
        self.assertNotIn('contact-1', east)
        self.assertEqual(west['contact-1']['location']['value']['position'], [8, 9])
        self.assertEqual(west['contact-1']['location']['knowledge'], 'remembered')
        self.assertEqual(west['contact-1']['location']['observed_at']['position'], 1190)
        self.assertEqual(west['contact-1']['hp'], {'knowledge': 'unknown'})
        contact = next(row for row in document['entities'] if row['id'] == 'contact-1')
        contact['state']['location'] = {'space': 'tunnel'}
        contact['state']['hp'] = 999
        changed = WorldView(document)
        # Different private current state cannot change this public cached fact.
        self.assertEqual(by_id(changed.observe('mission-west', 'player', 128)), west)

    def test_unseen_entities_bindings_and_private_counts_are_not_exposed(self):
        document = fixture('syndicate')
        world = WorldView(document)
        result = world.observe('mission-east', 'player', 128)
        self.assertEqual(result['coverage']['total_known_matches'], 0)
        self.assertEqual(result['entities'], [])
        public = json.dumps(world.observe('mission-west', 'player', 128))
        for text in ('unseen-1', 'secret_alarm', '777', 'source_registers_or_addresses', 'proposed_uil_object'):
            self.assertNotIn(text, public)
        self.assertNotIn('uil_contract_ref', public)

    def test_pages_cover_known_matches_once_with_stable_order(self):
        world = WorldView(fixture('colonization'))
        expected = [row['entity'] for row in world.observe('economy', 'player', 128)['entities']]
        result = world.observe('economy', 'player', 2)
        collected = []
        while True:
            collected += [row['entity'] for row in result['entities']]
            self.assertEqual(result['coverage']['total_known_matches'], len(expected))
            self.assertEqual(result['coverage']['world_recovery'], 'not_claimed')
            if result['next_cursor'] is None:
                break
            result = world.observe('economy', 'player', 2, result['next_cursor'])
        self.assertEqual(collected, expected)
        self.assertEqual(len(set(collected)), len(collected))

    def test_cursor_rejects_cross_view_observer_page_size_and_session(self):
        world = WorldView(fixture('colonization'))
        cursor = world.observe('economy', 'player', 1)['next_cursor']
        for view, observer, limit in [('ships', 'player', 1), ('economy', 'uninformed', 1), ('economy', 'player', 2)]:
            with self.subTest(scope=(view, observer, limit)), self.assertRaises(ValueError):
                world.observe(view, observer, limit, cursor)
        with self.assertRaises(ValueError):
            WorldView(fixture('colonization')).observe('economy', 'player', 1, cursor)

    def test_equal_snapshot_restore_changes_epoch_and_rejects_old_cursor(self):
        world = WorldView(fixture('civilization'))
        old = world.observe('world', 'player', 1)
        saved = world.private_snapshot()
        world.replace_snapshot(saved)
        self.assertEqual(world.private_snapshot(), saved)
        self.assertNotEqual(world.epoch(), old['epoch'])
        with self.assertRaises(ValueError):
            world.observe('world', 'player', 1, old['next_cursor'])

    def test_defensive_copies_preserve_authority_and_knowledge(self):
        document = fixture('colonization')
        world = WorldView(document)
        document['entities'][0]['state']['warehouse_food'] = -999
        result = world.observe('colony-1', 'player', 128)
        by_id(result)['colony-1']['warehouse_food']['value'] = -999
        snapshot = world.private_snapshot()
        snapshot['clock']['position'] = 999
        self.assertEqual(by_id(world.observe('colony-1', 'player', 128))['colony-1']['warehouse_food']['value'], 40)
        self.assertEqual(world.private_snapshot()['clock']['position'], 12)

    def test_malformed_fields_knowledge_parentage_actions_and_limits_refuse(self):
        for change in (
            lambda d: d.update(extra=True),
            lambda d: d['spaces'][0].update(parent=d['spaces'][0]['id']),
            lambda d: d['views'][0].update(parent=d['views'][0]['id']),
            lambda d: d['actions'][0].update(binding_status='executable'),
            lambda d: d['observers'][0]['records'][0]['fields'].update(hp={'knowledge': 'unknown', 'value': 42}),
            lambda d: d['observers'][0]['records'][0]['fields']['label']['observed_at'].update(position=999999),
        ):
            document = fixture('syndicate')
            change(document)
            with self.subTest(document=document), self.assertRaises(ValueError):
                validate(document)
        world = WorldView(fixture('colonization'))
        for limit in (False, 0, 129):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                world.observe('world', 'player', limit)
        malformed = fixture('colonization')
        ship = next(row for row in malformed['observers'][0]['records'] if row['entity'] == 'ship-1')
        ship['fields']['location']['value']['position'] = [12, 17]
        with self.assertRaises(ValueError):
            validate(malformed)


if __name__ == '__main__':
    unittest.main(verbosity=2)
