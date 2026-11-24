#!/usr/bin/env python3
"""Independent authored SCUMM v2 navigation fixtures.

The expectations below come from hand-worked examples of the pinned v2 room
format, endpoint adjustment, stored next-hop table and boundary-leg behavior.
They do not run an emulator, contain game resources, or implement a second
path planner as an oracle. A successful proposal remains unexecuted.

Primary behavior reference: ScummVM v2.9.0, commit
38af1883a2eb7a622c31bfc3708888bbcc47db48, engines/scumm/room.cpp,
boxes.cpp and actor.cpp. The fixtures and assertions are authored here;
no reference implementation is copied.

SPDX-License-Identifier: GPL-2.0-or-later
"""
from copy import deepcopy
from hashlib import sha256
import json
import unittest
from unittest import mock

import navigation
from processor_scene import build_scene_packet


CODE = b"\x00"
ROOM_ID = 1
ACTOR_ID = 1


def rectangle(left, top, right, bottom, *, mask=0, flags=0):
    """Author the eight byte fields of one v2 box, in on-disk order."""
    return (top, bottom, left, right, left, right, mask, flags)


def authored_room(boxes, rows=None, *, matrix=None, physical_order=None,
                  offset=32, trailer=b"", width=320, height=128):
    """Create a whole decoded old-bundle room with only authored geometry.

    Rows describe the logical source-box rows. ``physical_order`` permutes
    their byte storage, so tests can independently require stored offsets.
    ``matrix`` supplies an exact raw matrix for malformed/aliasing fixtures.
    This helper writes a format; it does not calculate routes or waypoints.
    """
    count = len(boxes)
    if matrix is None:
        if rows is None:
            rows = [[column for column in range(count)] for _ in range(count)]
        order = list(range(count)) if physical_order is None else list(physical_order)
        offsets = [order.index(index) * count for index in range(count)]
        matrix = bytes(offsets) + bytes(value & 255 for index in order for value in rows[index])
    assert len(matrix) == count * (count + 1)
    body = bytearray(offset)
    body[2:4] = b"\xa5\x5a"  # The second header word is opaque, not assumed zero.
    body[4:6] = width.to_bytes(2, "little")
    body[6:8] = height.to_bytes(2, "little")
    body[0x15] = offset
    body.append(count)
    for box in boxes:
        assert len(box) == 8
        body.extend(box)
    body.extend(matrix)
    body.extend(trailer)
    body[:2] = len(body).to_bytes(2, "little")
    return bytes(body)


def source():
    return {
        "version": 2,
        "code_sha256": sha256(CODE).hexdigest(),
        "code_size": len(CODE),
        "profile": "amiga-v2-isolated",
        "manifest_sha256": sha256(b"authored navigation manifest").hexdigest(),
        "source_receipt_sha256": sha256(b"authored navigation receipt").hexdigest(),
        "script_id": 1,
    }


def scene_for(room, *, start=(2, 5), room_id=ROOM_ID):
    """An explicitly authored stopped capture, not a claimed game capture."""
    actors = [
        {"id": index, "bound": 0, "x": 0, "y": 0, "room": 0,
         "costume": 0, "sound": 0, "talk_color": 0,
         "name": {"pc": 0, "size": 0, "bytes": ""}, "palette": [None] * 32}
        for index in range(32)
    ]
    actors[ACTOR_ID].update(bound=1, x=start[0], y=start[1], room=room_id)
    script = (4 + len(CODE)).to_bytes(2, "little") + b"\x00\x00" + CODE
    control = dict.fromkeys(
        ("user_state", "user_put", "cursor_visible", "current_room", "camera_mode",
         "cutscene_active", "saved_user_state", "saved_cursor", "saved_room",
         "saved_camera_mode", "override_pc", "override_script", "sentence_count",
         "ui_revision", "default_talk_color"), 0)
    control["current_room"] = room_id
    control["vars"] = dict.fromkeys(("21", "26", "27", "28", "29", "38"), 0)
    return {
        "schema": "fdisbull-scumm-scene-1", "source": source(),
        "checkpoint": {"trace_epoch": 1, "control_generation": 2, "retired": 0,
                       "pc": 0, "status": 0, "fault": 0, "fault_opcode": 0,
                       "blocked_reason": "none"},
        "observation": {"mask": 0, "capacity": 64, "count": 0, "sequence": 0,
                        "eligible": [0, 0], "stored": [0, 0], "dropped": [0, 0],
                        "helper_calls": 0},
        "actors": actors,
        "resources": {
            "counts": {"room": room_id + 1, "script": 2, "costume": 0, "sound": 0},
            "entries": [
                {"type": "room", "id": room_id, "size": len(room),
                 "available": True, "resident": False, "locked": False,
                 "sha256": sha256(room).hexdigest()},
                {"type": "script", "id": 1, "size": len(script),
                 "available": True, "resident": True, "locked": False,
                 "sha256": sha256(script).hexdigest()},
            ],
        },
        "control": control,
    }


def packet_for(room, **kwargs):
    return build_scene_packet(code=CODE, scene=scene_for(room, **kwargs))


def authored_verbs():
    fields = ("id", "x", "y", "color", "hicolor", "dimcolor", "type", "charset",
              "mode", "saveid", "key", "center", "imgindex", "prep")
    return [{"slot": slot, **dict.fromkeys(fields, 0),
             "name": {"pc": 0, "size": 0, "bytes": ""}} for slot in range(100)]


def request(**changes):
    result = {"room_id": ROOM_ID, "start": [2, 5], "goal": [15, 18],
              "actor_id": ACTOR_ID, "player_ids": [ACTOR_ID],
              "flags": {"policy": "room_initial"}, "max_hops": 255}
    result.update(changes)
    return result


def canonical_hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


BEND_BOXES = [rectangle(0, 0, 10, 10), rectangle(10, 0, 20, 10),
              rectangle(10, 10, 20, 20)]
BEND_ROWS = [[0, 1, 1], [0, 1, 2], [1, 1, 2]]


class NavigationInspectionTests(unittest.TestCase):
    def inspect(self, room, **kwargs):
        return navigation.inspect_room(room, **{"room_id": ROOM_ID, "source": source(), **kwargs})

    def test_whole_room_identity_coordinates_fields_and_opaque_tail(self):
        box = (2, 9, 3, 13, 5, 17, 0x39, 0x18)
        room = authored_room([box], [[0]], offset=40, trailer=b"authored opaque tail")
        identity = source()
        geometry = self.inspect(room, source=identity)
        self.assertEqual(geometry["schema"], "fdisbull-scumm-v2-room-navigation-1")
        self.assertEqual(geometry["source"], identity)
        self.assertEqual(geometry["room"], {"id": 1, "size": len(room), "sha256": sha256(room).hexdigest()})
        self.assertEqual(geometry["coordinates"], {"space": "scumm-v2-actor",
                                                  "x_pixel_multiplier": 8, "y_pixel_multiplier": 2})
        self.assertEqual(geometry["dimensions"], {"width_pixels": 320, "height_pixels": 128})
        self.assertEqual(geometry["box_table"], {"offset": 40, "size": 9, "count": 1})
        self.assertEqual(geometry["boxes"], [
            {"id": 0, "uy": 2, "ly": 9, "ulx": 3, "urx": 13,
             "llx": 5, "lrx": 17, "mask": 0x39, "flags": 0x18,
             "corners": [[3, 2], [13, 2], [17, 9], [5, 9]]}])
        self.assertEqual(geometry["matrix"], {"offset": 49, "size": 2, "prefix_size": 0,
                                              "row_offsets": [0], "next_hops": [[0]]})
        self.assertEqual(geometry["flags_origin"], "initial_room_bytes")
        geometry["source"]["script_id"] = 9
        self.assertEqual(identity, source())

    def test_physical_row_permutation_and_non_aligned_aliases_are_honored(self):
        room = authored_room(BEND_BOXES, BEND_ROWS, physical_order=[2, 0, 1])
        geometry = self.inspect(room)
        self.assertEqual(geometry["matrix"]["row_offsets"], [3, 6, 0])
        self.assertEqual(geometry["matrix"]["next_hops"], BEND_ROWS)
        # These stored offsets are not multiples of N. The format permits
        # bounded overlapping reads; a canonical-row rewrite changes them.
        matrix = bytes([1, 4, 0, 0, 0, 1, 1, 0, 1, 2, 2, 2])
        alias = self.inspect(authored_room(BEND_BOXES, matrix=matrix))
        self.assertEqual(alias["matrix"]["row_offsets"], [1, 4, 0])
        self.assertEqual(alias["matrix"]["next_hops"], [[0, 1, 1], [0, 1, 2], [0, 0, 1]])

    def test_leading_ff_skip_is_bounded_by_copied_matrix_not_room_tail(self):
        boxes = BEND_BOXES[:2]
        room = authored_room(boxes, matrix=bytes([255, 0, 0, 0, 1, 99]))
        geometry = self.inspect(room)
        self.assertEqual(geometry["matrix"]["prefix_size"], 1)
        self.assertEqual(geometry["matrix"]["row_offsets"], [0, 0])
        self.assertEqual(geometry["matrix"]["next_hops"], [[0, 1], [0, 1]])
        bad = authored_room(boxes, matrix=bytes([255, 0, 2, 0, 1, 0]), trailer=b"\x01" * 32)
        with self.assertRaises(navigation.NavigationInputError):
            self.inspect(bad)

    def test_all_signed_negative_next_hops_are_preserved(self):
        for encoded in range(128, 256):
            with self.subTest(encoded=encoded):
                room = authored_room(BEND_BOXES[:2], [[0, encoded], [0, 1]])
                self.assertEqual(self.inspect(room)["matrix"]["next_hops"][0][1], encoded - 256)

    def test_empty_degenerate_and_triangle_geometry_are_explicit(self):
        empty = self.inspect(authored_room([]))
        self.assertEqual(empty["box_table"]["count"], 0)
        self.assertEqual(empty["matrix"]["size"], 0)
        self.assertEqual(empty["boxes"], [])
        self.assertEqual(empty["matrix"]["next_hops"], [])
        for box in (rectangle(4, 7, 4, 7), (0, 8, 5, 5, 0, 10, 0, 0)):
            with self.subTest(box=box):
                self.assertEqual(len(self.inspect(authored_room([box]))["boxes"]), 1)

    def test_malformed_geometry_and_matrix_extents_are_rejected(self):
        valid = authored_room(BEND_BOXES, BEND_ROWS)
        wrong_length = bytearray(valid)
        wrong_length[0] ^= 1
        header_offset = bytearray(valid)
        header_offset[0x15] = 27
        distant_offset = bytearray(valid)
        distant_offset[0x15] = 255
        truncated_box = bytearray(valid[:40])
        truncated_box[:2] = len(truncated_box).to_bytes(2, "little")
        truncated_matrix = bytearray(valid[:-1])
        truncated_matrix[:2] = len(truncated_matrix).to_bytes(2, "little")
        cases = {
            "empty": b"", "short header": bytes(27), "length": bytes(wrong_length),
            "header overlap": bytes(header_offset), "offset outside": bytes(distant_offset),
            "truncated box": bytes(truncated_box), "truncated matrix": bytes(truncated_matrix),
            "reversed y": authored_room([(8, 2, 0, 10, 0, 10, 0, 0)]),
            "reversed top": authored_room([(0, 8, 10, 0, 0, 10, 0, 0)]),
            "reversed bottom": authored_room([(0, 8, 0, 10, 10, 0, 0, 0)]),
            "row overrun": authored_room(BEND_BOXES[:2], matrix=bytes([0, 4, 0, 1, 0, 1])),
            "positive hop outside": authored_room(BEND_BOXES[:2], [[0, 2], [0, 1]]),
            "over 16-bit span": bytes(65536),
        }
        for label, room in cases.items():
            with self.subTest(label=label), self.assertRaises(navigation.NavigationInputError):
                self.inspect(room)

    def test_inspector_rejects_mutable_bytes_bad_identity_and_bool_integers(self):
        room = authored_room(BEND_BOXES, BEND_ROWS)
        for bad in (bytearray(room), memoryview(room), list(room), None):
            with self.subTest(type=type(bad).__name__), self.assertRaises(navigation.NavigationInputError):
                self.inspect(bad)
        for room_id in (True, False, 0, -1, 256, 1.0, "1"):
            with self.subTest(room_id=room_id), self.assertRaises(navigation.NavigationInputError):
                self.inspect(room, room_id=room_id)
        for key, value in (("version", True), ("version", 1), ("profile", "none"),
                           ("code_size", True), ("code_size", 0), ("code_size", 65537),
                           ("script_id", True), ("script_id", 0), ("script_id", 256),
                           ("code_sha256", "a" * 63), ("manifest_sha256", "A" * 64),
                           ("source_receipt_sha256", "")):
            malformed = source()
            malformed[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(navigation.NavigationInputError):
                self.inspect(room, source=malformed)


class NavigationProposalTests(unittest.TestCase):
    def setUp(self):
        self.room = authored_room(BEND_BOXES, BEND_ROWS)
        self.packet = packet_for(self.room)

    def plan(self, *, room=None, packet=None, **changes):
        room = self.room if room is None else room
        packet = (self.packet if room == self.room else packet_for(room)) if packet is None else packet
        return navigation.plan_movement(packet, room, **request(**changes))

    def test_bending_path_has_independent_expected_boundary_points(self):
        proposal = self.plan()
        self.assertEqual(proposal["schema"], "fdisbull-scumm-v2-movement-plan-1")
        self.assertEqual(proposal["status"], "planned")
        self.assertEqual(proposal["box_path"], [0, 1, 2])
        self.assertEqual(proposal["waypoints"], [[2, 5], [10, 5], [10, 10], [15, 18]])
        self.assertEqual(proposal["hops"], 2)
        self.assertIsNone(proposal["blocked_next_box"])
        self.assertEqual(proposal["adjustment"], {
            "start": {"requested": [2, 5], "point": [2, 5], "box": 0, "distance": 0},
            "goal": {"requested": [15, 18], "point": [15, 18], "box": 2, "distance": 0}})
        self.assertEqual(proposal, self.plan())
        self.assertEqual(proposal["source"], self.packet["source"])
        self.assertEqual(proposal["room"], {"id": 1, "size": len(self.room),
                                            "sha256": sha256(self.room).hexdigest()})
        self.assertEqual(proposal["scene_binding"]["packet_sha256"], canonical_hash(self.packet))
        self.assertEqual(proposal["scene_binding"]["checkpoint"], self.packet["checkpoint"])
        self.assertEqual(proposal["scene_binding"]["actor"],
                         {"id": 1, "bound": 1, "x": 2, "y": 5, "room": 1})
        self.assertEqual(proposal["scene_binding"]["room_resource"], self.packet["resources"]["entries"][0])
        self.assertTrue(proposal["scene_binding"]["start_matches_recorded_position"])
        self.assertTrue(proposal["scene_binding"]["recorded_room_matches_requested"])

    def test_stored_row_layout_changes_neither_route_nor_waypoints(self):
        permuted = authored_room(BEND_BOXES, BEND_ROWS, physical_order=[2, 0, 1])
        alias = authored_room(BEND_BOXES, matrix=bytes([1, 4, 0, 0, 0, 1, 1, 0, 1, 2, 2, 2]))
        for room in (permuted, alias):
            with self.subTest(room_hash=sha256(room).hexdigest()):
                proposal = self.plan(room=room)
                self.assertEqual(proposal["status"], "planned")
                self.assertEqual(proposal["box_path"], [0, 1, 2])
                self.assertEqual(proposal["waypoints"], [[2, 5], [10, 5], [10, 10], [15, 18]])

    def test_same_box_ignores_diagonal_and_uses_no_hop_budget(self):
        room = authored_room([rectangle(0, 0, 20, 20)], [[-128]])
        proposal = self.plan(room=room, max_hops=0)
        self.assertEqual(proposal["status"], "planned")
        self.assertEqual(proposal["box_path"], [0])
        self.assertEqual(proposal["waypoints"], [[2, 5], [15, 18]])
        self.assertEqual(proposal["hops"], 0)
        still = self.plan(room=room, goal=[2, 5], max_hops=0)
        self.assertEqual(still["waypoints"], [[2, 5]])

    def test_endpoint_adjustment_preserves_v2_midpoint_rounding(self):
        room = authored_room([(0, 7, 0, 10, 10, 20, 0, 0)])
        proposal = self.plan(room=room, start=[-1, 3], goal=[10, 6])
        self.assertEqual(proposal["adjustment"]["start"],
                         {"requested": [-1, 3], "point": [5, 3], "box": 0, "distance": 6})
        self.assertEqual(proposal["waypoints"], [[5, 3], [10, 6]])
        self.assertFalse(proposal["scene_binding"]["start_matches_recorded_position"])

    def test_adjustment_ties_descend_and_y_distance_has_quarter_granularity(self):
        identical = authored_room([rectangle(0, 0, 20, 20)] * 2, [[0, 1], [0, 1]])
        overlap = self.plan(room=identical)
        self.assertEqual(overlap["box_path"], [1])
        equidistant = authored_room([rectangle(0, 0, 5, 10), rectangle(9, 0, 14, 10)])
        tied = self.plan(room=equidistant, start=[7, 5], goal=[11, 5])
        self.assertEqual(tied["adjustment"]["start"]["point"], [9, 5])
        self.assertEqual(tied["adjustment"]["start"]["box"], 1)
        stacked = authored_room([rectangle(0, 0, 10, 10), rectangle(0, 10, 10, 20)])
        close = self.plan(room=stacked, start=[5, 8], goal=[5, 18])
        self.assertEqual(close["adjustment"]["start"],
                         {"requested": [5, 8], "point": [5, 10], "box": 1, "distance": 0})

    def test_boundary_projection_tie_prefers_top_before_left(self):
        # Next-box projection is (4,4). Its equal-distance projections onto
        # the current box are (4,0) on top and (0,4) on left; top wins.
        room = authored_room([rectangle(0, 0, 10, 10), rectangle(4, 4, 6, 6)])
        proposal = self.plan(room=room, start=[1, 1], goal=[5, 5])
        self.assertEqual(proposal["box_path"], [0, 1])
        self.assertEqual(proposal["waypoints"], [[1, 1], [4, 0], [5, 5]])

    def test_sloped_boundary_keeps_each_integer_division_toward_zero(self):
        # For the second fixture's descending left edge, the hand-worked
        # dominant-y terms are -10, -18, 13, then trunc(130/-20)=-6.
        # That yields (14,13), not a floating projection rounded at the end.
        cases = [
            ((0, 20, 10, 20, 20, 30, 0, 0), [22, 15], [12, 4], [10, 4]),
            ((0, 20, 20, 30, 10, 20, 0, 0), [20, 15], [14, 13], [10, 13]),
        ]
        for box, goal, projection, boundary in cases:
            room = authored_room([rectangle(0, 0, 10, 20), box])
            with self.subTest(box=box):
                proposal = self.plan(room=room, start=[4, 9], goal=goal)
                self.assertEqual(proposal["status"], "planned")
                self.assertEqual(proposal["legs"][0]["next_box_projection"], projection)
                self.assertEqual(proposal["legs"][0]["boundary"], boundary)
                self.assertEqual(proposal["waypoints"], [[4, 9], boundary, goal])

    def test_negative_next_hops_report_no_route_without_geometry_search(self):
        for value in range(-128, 0):
            room = authored_room(BEND_BOXES, [[0, 1, value], BEND_ROWS[1], BEND_ROWS[2]])
            with self.subTest(next_hop=value):
                proposal = self.plan(room=room)
                self.assertEqual(proposal["status"], "no_route")
                self.assertEqual(proposal["box_path"], [0])
                self.assertEqual(proposal["waypoints"], [[2, 5]])
                self.assertNotIn([15, 18], proposal["waypoints"])

    def test_cycles_and_budgets_have_distinct_bounded_outcomes(self):
        cyclic = authored_room(BEND_BOXES, [[0, 1, 1], [0, 1, 0], BEND_ROWS[2]])
        cycle = self.plan(room=cyclic)
        self.assertEqual(cycle["status"], "routing_cycle")
        self.assertLessEqual(cycle["hops"], 3)
        self.assertNotIn([15, 18], cycle["waypoints"])
        self_loop = authored_room(BEND_BOXES, [[0, 1, 0], BEND_ROWS[1], BEND_ROWS[2]])
        self.assertEqual(self.plan(room=self_loop)["status"], "routing_cycle")
        for budget, expected_path, expected_points in (
                (0, [0], [[2, 5]]), (1, [0, 1], [[2, 5], [10, 5]])):
            with self.subTest(budget=budget):
                proposal = self.plan(max_hops=budget)
                self.assertEqual(proposal["status"], "budget_exhausted")
                self.assertEqual(proposal["hops"], budget)
                self.assertEqual(proposal["box_path"], expected_path)
                self.assertEqual(proposal["waypoints"], expected_points)
        self.assertEqual(self.plan(max_hops=2)["status"], "planned")

    def test_empty_and_all_ineligible_boxes_are_distinct(self):
        self.assertEqual(self.plan(room=authored_room([]))["status"], "no_walkboxes")
        invisible = authored_room([rectangle(0, 0, 20, 20, flags=0x80)])
        self.assertEqual(self.plan(room=invisible)["status"], "no_eligible_box")
        distant = self.plan(start=[32767, 32767], goal=[-32768, -32768])
        self.assertEqual(distant["status"], "no_eligible_box")

    def test_invisible_and_player_only_exception_is_explicit(self):
        room = authored_room([rectangle(0, 0, 20, 20, flags=0xA0)])
        self.assertEqual(self.plan(room=room)["status"], "no_eligible_box")
        self.assertEqual(self.plan(room=room, player_ids=[])["status"], "planned")
        ordinary = authored_room([rectangle(0, 0, 20, 20, flags=0x80)])
        self.assertEqual(self.plan(room=ordinary, player_ids=[])["status"], "no_eligible_box")

    def test_invisible_intermediate_box_is_not_an_invented_route_filter(self):
        boxes = BEND_BOXES[:]
        boxes[1] = rectangle(10, 0, 20, 10, flags=0x80)
        proposal = self.plan(room=authored_room(boxes, BEND_ROWS))
        self.assertEqual(proposal["status"], "planned")
        self.assertEqual(proposal["box_path"], [0, 1, 2])
        self.assertEqual(proposal["waypoints"], [[2, 5], [10, 5], [10, 10], [15, 18]])

    def test_disjoint_boxes_do_not_turn_a_table_proposal_into_walkability_proof(self):
        room = authored_room([rectangle(0, 0, 10, 10), rectangle(20, 0, 30, 10)])
        proposal = self.plan(room=room, goal=[25, 5])
        self.assertEqual(proposal["status"], "planned")
        self.assertEqual(proposal["box_path"], [0, 1])
        self.assertEqual(proposal["waypoints"], [[2, 5], [10, 5], [25, 5]])
        self.assertIs(proposal["qualification"]["continuous_walkable_path_verified"], False)

    def test_lock_stops_at_approach_boundary_and_player_only_can_allow_npc(self):
        for lock_flag in (0x40, 0x60):
            boxes = BEND_BOXES[:]
            boxes[1] = rectangle(10, 0, 20, 10, flags=lock_flag)
            room = authored_room(boxes, BEND_ROWS)
            with self.subTest(flags=lock_flag):
                proposal = self.plan(room=room)
                self.assertEqual(proposal["status"], "locked")
                self.assertEqual(proposal["blocked_next_box"], 1)
                self.assertEqual(proposal["box_path"], [0])
                self.assertEqual(proposal["waypoints"], [[2, 5], [10, 5]])
                npc = self.plan(room=room, player_ids=[])
                self.assertEqual(npc["status"], "planned" if lock_flag == 0x60 else "locked")

    def test_same_box_lock_does_not_create_a_transition_check(self):
        room = authored_room([rectangle(0, 0, 20, 20, flags=0x40)])
        self.assertEqual(self.plan(room=room)["status"], "planned")

    def test_explicit_flags_override_is_bound_and_does_not_mutate_room(self):
        before = bytes(self.room)
        flags = {"policy": "override", "values": [0, 0x40, 0]}
        proposal = self.plan(flags=flags)
        self.assertEqual(proposal["status"], "locked")
        self.assertEqual(proposal["waypoints"], [[2, 5], [10, 5]])
        self.assertEqual(self.room, before)
        self.assertEqual(self.plan()["status"], "planned")
        self.assertEqual(flags, {"policy": "override", "values": [0, 0x40, 0]})

    def test_strict_request_types_ranges_and_required_policy(self):
        cases = [
            {"room_id": True}, {"room_id": 0}, {"room_id": 256},
            {"start": [True, 5]}, {"start": [0, False]}, {"goal": [0.0, 1]},
            {"start": [-32769, 0]}, {"goal": [0, 32768]}, {"start": [0]},
            {"goal": [0, 0, 0]}, {"start": "2,5"},
            {"actor_id": 0}, {"actor_id": 32}, {"actor_id": True},
            {"player_ids": [True]}, {"player_ids": [0]}, {"player_ids": [32]},
            {"player_ids": [1, 1]}, {"player_ids": None},
            {"max_hops": True}, {"max_hops": -1}, {"max_hops": 256},
            {"flags": None}, {"flags": {}}, {"flags": {"policy": "current"}},
            {"flags": {"policy": "override", "values": [0, 0]}},
            {"flags": {"policy": "override", "values": [0, True, 0]}},
            {"flags": {"policy": "override", "values": [0, -1, 0]}},
            {"flags": {"policy": "override", "values": [0, 256, 0]}},
        ]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(navigation.NavigationInputError):
                self.plan(**changes)
        args = request()
        del args["flags"]
        with self.assertRaises(TypeError):
            navigation.plan_movement(self.packet, self.room, **args)

    def test_room_bytes_must_match_the_exact_available_scene_slot(self):
        altered = bytearray(self.room)
        altered[2] ^= 1  # Opaque header change still changes the whole-room identity.
        with self.assertRaises(navigation.NavigationInputError):
            self.plan(room=bytes(altered), packet=self.packet)
        for change in ("missing", "unavailable", "size", "hash"):
            scene = scene_for(self.room)
            room = scene["resources"]["entries"][0]
            if change == "missing":
                scene["resources"]["entries"].pop(0)
            elif change == "unavailable":
                room.update(available=False, resident=False, locked=True, size=0, sha256="")
            elif change == "size":
                room["size"] += 1
            else:
                room["sha256"] = "f" * 64
            packet = build_scene_packet(code=CODE, scene=scene)
            with self.subTest(change=change), self.assertRaises(navigation.NavigationInputError):
                self.plan(packet=packet)

    def test_proposal_and_checker_are_pure_and_do_not_claim_execution(self):
        original = deepcopy(self.packet)
        args = request()
        original_args = deepcopy(args)
        with mock.patch("subprocess.Popen", side_effect=AssertionError("must not start an engine")), \
             mock.patch("socket.socket", side_effect=AssertionError("must not inject input")), \
             mock.patch("builtins.open", side_effect=AssertionError("must not write or load guest state")):
            proposal = navigation.plan_movement(self.packet, self.room, **args)
            checked = navigation.check_movement_plan(self.packet, self.room, proposal, **args)
        self.assertTrue(checked["valid"])
        self.assertEqual(checked["reason"], "match")
        self.assertEqual(proposal["execution"], "not_performed")
        self.assertEqual(proposal["live_applicability"], "unverified")
        self.assertEqual(checked["execution"], "not_performed")
        self.assertEqual(checked["live_applicability"], "unverified")
        for field in ("current_room_established", "native_actor_initialized",
                      "live_box_flags_established", "native_timing_established",
                      "continuous_walkable_path_verified", "actor_collision_avoidance_verified",
                      "original_engine_equivalence", "native_execution_performed", "screen_presentation"):
            self.assertIs(proposal["qualification"][field], False)
        self.assertEqual(self.packet, original)
        self.assertEqual(args, original_args)
        proposal["source"]["script_id"] = 31
        proposal["scene_binding"]["checkpoint"]["trace_epoch"] = 999
        self.assertEqual(self.packet, original)

    def test_proposal_records_uninitialized_room_and_actor_without_initializing_them(self):
        scene = scene_for(self.room)
        scene["actors"][1].update(bound=0, room=0)
        scene["control"]["current_room"] = 0
        packet = build_scene_packet(code=CODE, scene=scene)
        original = deepcopy(packet)
        proposal = self.plan(packet=packet)
        self.assertEqual(proposal["status"], "planned")
        self.assertEqual(proposal["scene_binding"]["actor"]["bound"], 0)
        self.assertFalse(proposal["scene_binding"]["recorded_room_matches_requested"])
        self.assertEqual(proposal["scene_binding"]["recorded_current_room"], 0)
        self.assertFalse(proposal["qualification"]["native_actor_initialized"])
        self.assertFalse(proposal["qualification"]["current_room_established"])
        self.assertEqual(packet, original)


class NavigationCheckerTests(unittest.TestCase):
    def setUp(self):
        self.room = authored_room(BEND_BOXES, BEND_ROWS)
        self.packet = packet_for(self.room)
        self.args = request()
        self.proposal = navigation.plan_movement(self.packet, self.room, **self.args)

    def check(self, proposal=None, *, packet=None, room=None, **changes):
        return navigation.check_movement_plan(
            self.packet if packet is None else packet,
            self.room if room is None else room,
            self.proposal if proposal is None else proposal,
            **{**self.args, **changes})

    def assert_mismatch(self, **kwargs):
        result = self.check(**kwargs)
        self.assertEqual(result["schema"], "fdisbull-scumm-v2-movement-check-1")
        self.assertIs(result["valid"], False)
        self.assertEqual(result["reason"], "proposal_mismatch")
        return result

    def test_matches_after_json_round_trip(self):
        roundtrip = json.loads(json.dumps(self.proposal))
        result = self.check(roundtrip)
        self.assertIs(result["valid"], True)
        self.assertEqual(result["reason"], "match")
        self.assertEqual(result["expected_status"], "planned")

    def test_replanning_rejects_tampered_path_claims_and_binding_fields(self):
        mutations = {
            "waypoint": lambda p: p["waypoints"][1].__setitem__(1, 6),
            "box path": lambda p: p["box_path"].__setitem__(1, 2),
            "status": lambda p: p.update(status="no_route"),
            "hops": lambda p: p.update(hops=1),
            "execution": lambda p: p.update(execution="performed"),
            "live": lambda p: p.update(live_applicability="verified"),
            "source": lambda p: p["source"].update(manifest_sha256="f" * 64),
            "room": lambda p: p["room"].update(id=2),
            "scene": lambda p: p["scene_binding"].update(packet_sha256="0" * 64),
            "checkpoint": lambda p: p["scene_binding"]["checkpoint"].update(trace_epoch=2),
            "adjustment": lambda p: p["adjustment"]["goal"].update(point=[15, 17]),
            "extra claim": lambda p: p.update(engine_movement_completed=True),
        }
        for label, mutate in mutations.items():
            proposal = deepcopy(self.proposal)
            mutate(proposal)
            with self.subTest(label=label):
                self.assert_mismatch(proposal=proposal)

    def test_malformed_proposal_is_a_mismatch_not_a_trusted_plan(self):
        cyclic = {}
        cyclic["self"] = cyclic
        for proposal in (False, 1, [], {"waypoints": float("nan")}, {"bad": {1}}, cyclic):
            with self.subTest(type=type(proposal).__name__):
                self.assert_mismatch(proposal=proposal)

    def test_stale_rebuilt_scene_rejects_even_when_waypoints_are_unchanged(self):
        changes = {
            "epoch": lambda s: s["checkpoint"].update(trace_epoch=2),
            "generation": lambda s: s["checkpoint"].update(control_generation=3),
            "actor pose": lambda s: s["actors"][1].update(x=3),
            "actor room": lambda s: s["actors"][1].update(room=0),
            "actor palette": lambda s: s["actors"][1]["palette"].__setitem__(0, 2),
            "control": lambda s: s["control"].update(ui_revision=1),
            "resource flag": lambda s: s["resources"]["entries"][0].update(resident=True),
            "source manifest": lambda s: s["source"].update(manifest_sha256="c" * 64),
            "source receipt": lambda s: s["source"].update(source_receipt_sha256="d" * 64),
        }
        for label, mutate in changes.items():
            scene = scene_for(self.room)
            mutate(scene)
            packet = build_scene_packet(code=CODE, scene=scene)
            with self.subTest(label=label):
                result = self.assert_mismatch(packet=packet)
                self.assertEqual(result["expected_status"], "planned")

    def test_changed_room_whole_span_is_stale_even_when_geometry_is_identical(self):
        altered = bytearray(self.room)
        altered[3] ^= 1
        altered = bytes(altered)
        self.assert_mismatch(room=altered, packet=packet_for(altered))

    def test_every_explicit_request_is_bound_even_for_equivalent_path(self):
        changes = [
            {"goal": [14, 18]}, {"start": [3, 5]}, {"actor_id": 2},
            {"player_ids": []}, {"max_hops": 254},
            {"flags": {"policy": "override", "values": [0, 0, 0]}},
        ]
        for change in changes:
            with self.subTest(change=change):
                self.assert_mismatch(**change)

    def test_unvalidated_packet_mutation_is_rejected_before_a_check_claim(self):
        for field, value in (("x", True), ("x", 70000), ("bound", True)):
            packet = deepcopy(self.packet)
            packet["actors"][1][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(navigation.NavigationInputError):
                self.check(packet=packet)
        changed = deepcopy(self.packet)
        changed["actors"][1]["x"] = 3
        with self.assertRaises(navigation.NavigationInputError):
            self.check(packet=changed)

    def test_capture_evidence_and_snapshot_qualification_are_required(self):
        for field in ("code_sha256", "scene_sha256"):
            packet = deepcopy(self.packet)
            packet["evidence"][field] = "e" * 64
            with self.subTest(field=field), self.assertRaises(navigation.NavigationInputError):
                self.check(packet=packet)
        for value in (False, 1, "true", None):
            packet = deepcopy(self.packet)
            packet["qualification"]["current_snapshot"] = value
            with self.subTest(value=value), self.assertRaises(navigation.NavigationInputError):
                self.check(packet=packet)
        for field in ("evidence", "qualification", "observation"):
            packet = deepcopy(self.packet)
            del packet[field]
            with self.subTest(missing=field), self.assertRaises(navigation.NavigationInputError):
                self.check(packet=packet)

    def test_optional_verb_inventory_joins_the_same_capture_binding(self):
        scene = scene_for(self.room)
        self.assertNotIn("verbs", self.packet)
        self.assertTrue(self.check()["valid"])
        scene["verbs"] = authored_verbs()
        scene["verbs"][3].update(id=7, x=10, y=100, mode=1)
        packet = build_scene_packet(code=CODE, scene=scene)
        proposal = navigation.plan_movement(packet, self.room, **self.args)
        self.assertTrue(self.check(proposal, packet=packet)["valid"])
        self.assertEqual(proposal["scene_binding"]["packet_sha256"], canonical_hash(packet))
        altered = deepcopy(packet)
        altered["verbs"][3]["id"] = 8
        with self.assertRaises(navigation.NavigationInputError):
            self.check(proposal, packet=altered)
        scene["verbs"][3]["id"] = 8
        fresh_packet = build_scene_packet(code=CODE, scene=scene)
        self.assert_mismatch(proposal=proposal, packet=fresh_packet)


if __name__ == "__main__":
    unittest.main()
