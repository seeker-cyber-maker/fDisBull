#!/usr/bin/env python3
"""Authored synthetic captures for the stateless SCUMM packet consumer.

No game assets, emulator, network or third-party dependency is required.
SPDX-License-Identifier: GPL-2.0-or-later
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from processor_scene import build_scene_packet, SceneInputError, DECODE_FIELDS


def actor(index):
    return {"id": index, "bound": 0, "x": 0, "y": 0, "room": 0, "costume": 0,
            "sound": 0, "talk_color": 0, "name": {"pc": 0, "size": 0, "bytes": ""},
            "palette": [None] * 32}


def control():
    result = dict.fromkeys(("user_state", "user_put", "cursor_visible", "current_room", "camera_mode",
                           "cutscene_active", "saved_user_state", "saved_cursor", "saved_room",
                           "saved_camera_mode", "override_pc", "override_script", "sentence_count",
                           "ui_revision"), 0)
    result["vars"] = dict.fromkeys(("21", "26", "27", "28", "29", "38"), 0)
    return result


def scene_for(code):
    return {
        "schema": "fdisbull-scumm-scene-1",
        "source": {"version": 2, "code_sha256": sha256(code).hexdigest(), "code_size": len(code),
                   "profile": "none", "manifest_sha256": "", "source_receipt_sha256": "", "script_id": 0},
        "checkpoint": {"trace_epoch": 1, "control_generation": 2, "retired": 0, "pc": 0,
                       "status": 0, "fault": 0, "fault_opcode": 0, "blocked_reason": "none"},
        "observation": {"mask": 3, "capacity": 64, "count": 0, "sequence": 0,
                        "eligible": [0, 0], "stored": [0, 0], "dropped": [0, 0], "helper_calls": 0},
        "actors": [actor(index) for index in range(32)],
        "resources": {"counts": dict.fromkeys(("costume", "room", "script", "sound"), 0), "entries": []},
        "control": {**control(), "default_talk_color": 0},
    }


def instruction(code, pc, size, op, args=(), *, subop=0, payload_pc=0, payload_size=0,
                branch=-1, conditional=0):
    return {"pc": pc, "opcode": code[pc], "op": op, "fault": 0, "size": size, "next": pc + size,
            "branch": branch, "conditional": conditional, "subop": subop,
            "payload_pc": payload_pc, "payload_size": payload_size,
            "args": [list(arg) for arg in args], "bytes": code[pc:pc + size].hex()}


def record(row, retired, *, kind="retire", resolved=None, destination=None, **payload):
    return {"seq": 0, "retired": retired, "control_generation": 2, "channel": int(kind != "retire"),
            "kind": kind, "pc": row["pc"], "next": row["next"], "opcode": row["opcode"],
            "size": row["size"], "bytes": row["bytes"],
            "decoded": {key: deepcopy(row[key]) for key in DECODE_FIELDS},
            "resolved": ([arg[1] for arg in row["args"]] if resolved is None else resolved),
            "destination": destination, "branch_taken": None, **payload}


def envelope(scene, records):
    records = deepcopy(records)
    for index, row in enumerate(records, 1):
        row["seq"] = index
    stored = [sum(row["channel"] == channel for row in records) for channel in (0, 1)]
    scene["observation"].update(count=len(records), sequence=len(records), eligible=stored[:], stored=stored,
                                dropped=[0, 0], helper_calls=scene["checkpoint"]["retired"])
    return {"schema": "fdisbull-scumm-events-2", "source": deepcopy(scene["source"]),
            "epoch": scene["checkpoint"]["trace_epoch"],
            "control_generation": scene["checkpoint"]["control_generation"],
            "observation": deepcopy(scene["observation"]), "records": records}


def pages_for(scene, rows):
    return [{"schema": "fdisbull-scumm-early-decode-1", "source": deepcopy(scene["source"]),
             "start_pc": 0, "limit": 64, "next_pc": rows[-1]["next"] if rows else 0,
             "stop": "end", "records": deepcopy(rows)}]


def raw_fixture():
    code = bytes.fromhex("1a070500 01010a14 1301090204 13010003414200 13000705 00")
    scene = scene_for(code)
    rows = [instruction(code, 0, 4, "move", ((2, 7, 1), (0, 5, 2))),
            instruction(code, 4, 4, "place_actor", ((0, 1, 1), (0, 10, 1), (0, 20, 1))),
            instruction(code, 8, 5, "actor_config", ((0, 1, 1), (0, 9, 1), (0, 2, 1)),
                        subop=2, payload_pc=12, payload_size=1),
            instruction(code, 13, 7, "actor_config", ((0, 1, 1), (0, 0, 1), (0, 3, 1)),
                        subop=3, payload_pc=17, payload_size=2),
            instruction(code, 20, 4, "actor_config", ((0, 0, 1), (0, 7, 1), (0, 5, 1)), subop=5),
            instruction(code, 24, 1, "stop")]
    records = [record(rows[0], 1, resolved=[0, 5], destination={"index": 7, "before": 0, "after": 5})]
    current = actor(1)
    for retired, row in enumerate(rows[1:4], 2):
        before = deepcopy(current)
        if retired == 2:
            current.update(bound=1, x=10, y=20)
        elif retired == 3:
            current["palette"][4] = 9
        else:
            current["name"] = {"pc": 17, "size": 2, "bytes": "4142"}
        records.extend([record(row, retired), record(row, retired, kind="actor",
                                                     before_actor=before, after_actor=deepcopy(current))])
    records.extend([record(rows[4], 5), record(rows[4], 5, kind="default_talk_color", before_color=0, after_color=7),
                    record(rows[5], 6)])
    scene["actors"][1] = current
    scene["control"]["default_talk_color"] = 7
    scene["checkpoint"].update(retired=6, pc=len(code), status=3)
    events = envelope(scene, records)
    return {"code": code, "scene": scene, "events": events, "decode_pages": pages_for(scene, rows)}


def runtime_fixture():
    code = bytes.fromhex("0c0121 60071f 1a156300 600000 00")
    scene = scene_for(code)
    scene["source"].update(profile="amiga-v2-isolated", manifest_sha256=sha256(b"authored manifest").hexdigest(),
                           source_receipt_sha256=sha256(b"authored receipt").hexdigest(), script_id=1)
    scene["resources"]["counts"].update(costume=3, script=2)
    script = (len(code) + 4).to_bytes(2, "little") + b"\x00\x00" + code
    script_entry = {"type": "script", "id": 1, "size": len(script), "available": True, "resident": True,
                    "locked": False, "sha256": sha256(script).hexdigest()}
    before_resource = {"size": 6, "available": True, "resident": False, "locked": False,
                       "sha256": sha256(b"\x06\x00\x00\x00\x01\x02").hexdigest()}
    after_resource = {**before_resource, "resident": True}
    scene["resources"]["entries"] = [{"type": "costume", "id": 1, **after_resource}, script_entry]
    rows = [instruction(code, 0, 3, "resource_operation", ((0, 1, 1), (0, 0x21, 1))),
            instruction(code, 3, 3, "cursor", ((0, 0x1f07, 2),)),
            instruction(code, 6, 4, "move", ((2, 21, 1), (0, 99, 2))),
            instruction(code, 10, 3, "cursor", ((0, 0, 2),)), instruction(code, 13, 1, "stop")]
    initial_control = control()
    first_control = deepcopy(initial_control)
    first_control.update(user_put=1, cursor_visible=1, ui_revision=1)
    first_control["vars"]["21"] = 7
    second_before = deepcopy(first_control)
    second_before["vars"]["21"] = 99  # A scalar instruction is outside the control-event chain.
    final_control = deepcopy(second_before)
    final_control["ui_revision"] = 2
    records = [record(rows[0], 1), record(rows[0], 1, kind="resource", type="costume", id=1,
                                        before_resource=before_resource, after_resource=after_resource),
               record(rows[1], 2), record(rows[1], 2, kind="control", before_control=initial_control,
                                         after_control=first_control),
               record(rows[2], 3, resolved=[7, 99], destination={"index": 21, "before": 7, "after": 99}),
               record(rows[3], 4), record(rows[3], 4, kind="control", before_control=second_before,
                                         after_control=final_control), record(rows[4], 5)]
    scene["control"] = {**final_control, "default_talk_color": 0}
    scene["checkpoint"].update(retired=5, pc=len(code), status=3)
    events = envelope(scene, records)
    return {"code": code, "scene": scene, "events": events, "decode_pages": pages_for(scene, rows)}


def blank_verb(slot):
    fields = ("id", "x", "y", "hicolor", "dimcolor", "type", "mode", "saveid",
              "key", "center", "imgindex", "prep")
    return {**dict.fromkeys(fields, 0), "slot": slot, "color": 2, "charset": 1,
            "name": {"pc": 0, "size": 0, "bytes": ""}}


def verb_fixture(text=b"A\xff\x04\x00\x00B\xff\x01C"):
    code = b"\x7a\x05\x01\x02\x00\x04" + text + b"\0\0"
    scene = scene_for(code)
    scene["source"].update(profile="amiga-v2-isolated", script_id=1,
                           manifest_sha256=sha256(b"authored verb manifest").hexdigest(),
                           source_receipt_sha256=sha256(b"authored verb receipt").hexdigest())
    script = (len(code) + 4).to_bytes(2, "little") + b"\0\0" + code
    scene["resources"]["counts"]["script"] = 2
    scene["resources"]["entries"] = [{"type": "script", "id": 1, "size": len(script),
                                        "available": True, "resident": True, "locked": False,
                                        "sha256": sha256(script).hexdigest()}]
    scene["verbs"] = [blank_verb(i) for i in range(100)]
    before = blank_verb(1)
    after = {**before, "id": 5, "x": 8, "y": 16, "hicolor": 14, "dimcolor": 8,
             "charset": 0, "mode": 1, "key": ord("q"), "prep": 4,
             "name": {"pc": 6, "size": len(text), "bytes": text.hex()}}
    scene["verbs"][1] = deepcopy(after)
    scene["control"]["ui_revision"] = 1
    scene["checkpoint"].update(retired=2, pc=len(code), status=3)
    rows = [instruction(code, 0, len(code) - 1, "verb_op", ((0, 5, 1), (0, 0, 1), (0, 4, 1)),
                        payload_pc=2, payload_size=len(code) - 3),
            instruction(code, len(code) - 1, 1, "stop")]
    events = envelope(scene, [record(rows[0], 1), record(rows[0], 1, kind="verb",
                            before_verb=before, after_verb=deepcopy(after),
                            before_ui_revision=0, after_ui_revision=1), record(rows[1], 2)])
    return {"code": code, "scene": scene, "events": events, "decode_pages": pages_for(scene, rows)}


class ProcessorSceneTests(unittest.TestCase):
    def test_verb_snapshot_escaped_text_and_detached_change(self):
        fixture = verb_fixture()
        original = deepcopy(fixture)
        packet = build_scene_packet(**fixture)
        self.assertEqual(packet["verbs"], fixture["scene"]["verbs"])
        self.assertEqual(packet["committed_changes"][0]["after_verb"], packet["verbs"][1])
        self.assertEqual(packet["verbs"][1]["name"]["bytes"], "41ff04000042ff0143")
        self.assertTrue(packet["qualification"]["verb_state"])
        self.assertFalse(packet["qualification"]["verb_rendering"])
        self.assertFalse(packet["qualification"]["verb_hit_testing"])
        packet["verbs"][1]["mode"] = 255
        packet["committed_changes"][0]["after_verb"]["id"] = 99
        self.assertEqual(fixture, original)

    def test_verb_name_absent_empty_and_invalidation_only(self):
        fixture = verb_fixture(b"")
        packet = build_scene_packet(**fixture)
        self.assertEqual(packet["verbs"][1]["name"], {"pc": 6, "size": 0, "bytes": ""})
        self.assertEqual(packet["verbs"][2]["name"], {"pc": 0, "size": 0, "bytes": ""})
        event = fixture["events"]["records"][1]
        event["before_verb"] = deepcopy(event["after_verb"])
        self.assertEqual(len(build_scene_packet(**fixture)["committed_changes"]), 1)
        # A repeated accepted redraw request is a revision change, not a draw.
        event["after_ui_revision"] = 0
        with self.assertRaises(SceneInputError):
            build_scene_packet(**fixture)

    def test_verb_inventory_bounds_and_malformed_text(self):
        mutations = [
            lambda f: f["scene"]["verbs"].pop(),
            lambda f: f["scene"]["verbs"][1].update(slot=0),
            lambda f: f["scene"]["verbs"][1].update(mode=True),
            lambda f: f["scene"]["verbs"][1].update(mode=256),
            lambda f: f["scene"]["verbs"][1].update(x=-1),
            lambda f: f["scene"]["verbs"][1]["name"].update(size=2, bytes="41ff"),
            lambda f: f["scene"]["verbs"][1]["name"].update(size=3, bytes="41ff04"),
            lambda f: f["scene"]["verbs"][1]["name"].update(pc=0, size=1, bytes="7a"),
            lambda f: f["scene"]["verbs"][1]["name"].update(size=508),
            lambda f: f["scene"].pop("verbs"),
            lambda f: f["events"]["records"][1]["after_verb"].update(slot=2),
            lambda f: f["events"]["records"][1].update(before_ui_revision=1),
            lambda f: f["events"]["records"][1].update(after_ui_revision=2),
            lambda f: f["events"]["records"][1].update(before_ui_revision=True),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                fixture = verb_fixture()
                mutate(fixture)
                with self.assertRaises(SceneInputError):
                    build_scene_packet(**fixture)
        # A zero outside escape arguments cannot be hidden within the name span.
        with self.assertRaises(SceneInputError):
            build_scene_packet(**verb_fixture(b"A\0B"))
        for short in (b"A\xff", b"A\xff\x04", b"A\xff\x04\x00"):
            with self.subTest(short=short), self.assertRaises(SceneInputError):
                build_scene_packet(**verb_fixture(short))

    def test_older_snapshot_does_not_invent_verb_inventory(self):
        packet = build_scene_packet(**raw_fixture())
        self.assertNotIn("verbs", packet)
        self.assertFalse(packet["qualification"]["verb_state"])

    def test_full_actor_facts_and_detached_outputs(self):
        fixture = raw_fixture()
        original = deepcopy(fixture)
        packet = build_scene_packet(**fixture)
        self.assertEqual(packet["actors"][1]["name"], {"pc": 17, "size": 2, "bytes": "4142"})
        self.assertEqual(packet["actors"][1]["palette"][4], 9)
        self.assertEqual(packet["control"]["default_talk_color"], 7)
        self.assertEqual(len(packet["disassembly"]["retirements"]), 6)
        self.assertEqual(len(packet["committed_changes"]), 4)
        self.assertTrue(packet["disassembly"]["static_listing_complete"])
        self.assertEqual(fixture, original)
        packet["actors"][1]["palette"][4] = 200
        packet["committed_changes"][0]["after_actor"]["x"] = 500
        fixture["decode_pages"][0]["records"][0]["op"] = "changed"
        self.assertEqual(fixture["scene"], original["scene"])
        self.assertEqual(packet["disassembly"]["static_pages"][0]["records"][0]["op"], "move")

    def test_all_masks_preserve_current_facts_without_history_or_render_claims(self):
        expected = None
        for mask in range(4):
            with self.subTest(mask=mask):
                fixture = raw_fixture()
                rows = [row for row in fixture["events"]["records"] if mask & (1 << row["channel"])]
                fixture["scene"]["observation"]["mask"] = mask
                fixture["events"] = envelope(fixture["scene"], rows)
                packet = build_scene_packet(**fixture)
                current = (packet["actors"], packet["resources"], packet["control"])
                if expected is None:
                    expected = current
                self.assertEqual(current, expected)
                for key in ("history_complete", "actor_visibility", "room_rendering", "costume_decode",
                            "screen_presentation", "control_variable_history_complete"):
                    self.assertFalse(packet["qualification"][key])
                self.assertFalse(packet["disassembly"]["static_reachability_qualified"])

    def test_snapshot_without_optional_journal(self):
        fixture = raw_fixture()
        fixture["events"] = None
        packet = build_scene_packet(**fixture)
        self.assertEqual(packet["committed_changes"], [])
        self.assertEqual(packet["qualification"]["history_scope"], "not_supplied")
        self.assertIsNone(packet["evidence"]["events_sha256"])

    def test_capacity_zero_and_grow_after_drop_gaps(self):
        for retained, capacity in (([], 0), ([0, 1, 6, 7], 4)):
            with self.subTest(retained=retained):
                fixture = raw_fixture()
                rows = [fixture["events"]["records"][index] for index in retained]
                stored = [sum(row["channel"] == channel for row in rows) for channel in (0, 1)]
                observation = fixture["scene"]["observation"]
                observation.update(count=len(rows), capacity=capacity, stored=stored,
                                   dropped=[observation["eligible"][i] - stored[i] for i in (0, 1)])
                fixture["events"]["records"] = rows
                fixture["events"]["observation"] = deepcopy(observation)
                packet = build_scene_packet(**fixture)
                self.assertEqual(packet["observation"]["dropped"], observation["dropped"])
                self.assertFalse(packet["qualification"]["history_complete"])

    def test_resource_bindings_and_scalar_updates_between_control_events(self):
        packet = build_scene_packet(**runtime_fixture())
        self.assertEqual(packet["control"]["vars"]["21"], 99)
        changes = packet["committed_changes"]
        self.assertEqual([row["kind"] for row in changes], ["resource", "control", "control"])
        self.assertEqual(changes[1]["after_control"]["vars"]["21"], 7)
        self.assertEqual(changes[2]["before_control"]["vars"]["21"], 99)
        self.assertTrue(packet["resources"]["entries"][0]["resident"])
        self.assertFalse(packet["qualification"]["screen_presentation"])

    def test_declared_locked_slot_without_available_bytes(self):
        fixture = runtime_fixture()
        fixture["scene"]["resources"]["entries"].append(
            {"type": "costume", "id": 2, "size": 0, "available": False,
             "resident": False, "locked": True, "sha256": ""})
        packet = build_scene_packet(**fixture)
        self.assertFalse(packet["resources"]["entries"][-1]["available"])
        self.assertTrue(packet["resources"]["entries"][-1]["locked"])

    def test_identity_epoch_and_counter_rejections(self):
        mutations = {
            "code": lambda f: f.update(code=f["code"][:-1] + b"\x80"),
            "source version bool": lambda f: f["scene"]["source"].update(version=True),
            "event source": lambda f: f["events"]["source"].update(version=1),
            "event epoch": lambda f: f["events"].update(epoch=0),
            "generation": lambda f: f["events"].update(control_generation=3),
            "stale record generation": lambda f: f["events"]["records"][2].update(control_generation=1),
            "future record": lambda f: f["events"]["records"][-1].update(retired=7),
            "count": lambda f: f["scene"]["observation"].update(count=9),
            "observer calls below eligibility": lambda f: f["scene"]["observation"].update(helper_calls=5),
            "observer calls above retirement": lambda f: f["scene"]["observation"].update(helper_calls=7),
            "loss": lambda f: f["events"]["observation"].update(dropped=[1, 0]),
            "sequence": lambda f: f["events"]["records"][1].update(seq=1),
            "unexplained gap": lambda f: f["events"]["records"][-1].update(seq=11),
            "channel": lambda f: f["events"]["records"][0].update(channel=1),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                fixture = raw_fixture()
                mutate(fixture)
                with self.assertRaises(SceneInputError):
                    build_scene_packet(**fixture)

    def test_actor_name_palette_and_control_bounds_rejections(self):
        mutations = {
            "duplicate actor": lambda f: f["scene"]["actors"][2].update(id=1),
            "short palette": lambda f: f["scene"]["actors"][1]["palette"].pop(),
            "palette byte": lambda f: f["scene"]["actors"][1]["palette"].__setitem__(0, 256),
            "palette bool": lambda f: f["scene"]["actors"][1]["palette"].__setitem__(0, True),
            "name bytes": lambda f: f["scene"]["actors"][1]["name"].update(bytes="4143"),
            "name bounds": lambda f: f["scene"]["actors"][1]["name"].update(pc=len(f["code"])),
            "name terminator": lambda f: f["scene"]["actors"][1]["name"].update(size=1, bytes="41"),
            "control bool": lambda f: f["scene"]["control"].update(cursor_visible=True),
            "control variable": lambda f: f["scene"]["control"]["vars"].update({"21": 65536}),
            "missing control variable": lambda f: f["scene"]["control"]["vars"].pop("38"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                fixture = raw_fixture()
                mutate(fixture)
                with self.assertRaises(SceneInputError):
                    build_scene_packet(**fixture)

    def test_unassigned_and_assigned_empty_name_remain_distinct(self):
        fixture = raw_fixture()
        fixture["scene"]["actors"][2]["name"] = {"pc": 19, "size": 0, "bytes": ""}
        packet = build_scene_packet(**fixture)
        self.assertEqual(packet["actors"][0]["name"]["pc"], 0)
        self.assertEqual(packet["actors"][2]["name"], {"pc": 19, "size": 0, "bytes": ""})

    def test_instruction_and_witness_tampering_rejections(self):
        mutations = {
            "instruction bytes": lambda f: f["events"]["records"][0].update(bytes="00000000"),
            "decoded extent": lambda f: f["events"]["records"][0]["decoded"].update(next=5),
            "resolved immediate": lambda f: f["events"]["records"][1]["resolved"].__setitem__(1, 99),
            "destination index": lambda f: f["events"]["records"][0]["destination"].update(index=256),
            "static/live disagreement": lambda f: f["decode_pages"][0]["records"][0].update(op="add"),
            "same retirement": lambda f: f["events"]["records"][2]["resolved"].__setitem__(0, 2),
            "invented branch": lambda f: f["events"]["records"][0].update(branch_taken=False),
            "scene kind": lambda f: f["events"]["records"][2].update(kind="rendered_room"),
            "unchanged actor": lambda f: f["events"]["records"][2].update(
                after_actor=deepcopy(f["events"]["records"][2]["before_actor"])),
            "page stop": lambda f: f["decode_pages"][0].update(stop="limit"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                fixture = raw_fixture()
                mutate(fixture)
                with self.assertRaises(SceneInputError):
                    build_scene_packet(**fixture)

    def test_resource_identity_and_declaration_rejections(self):
        mutations = {
            "duplicate slot": lambda f: f["scene"]["resources"]["entries"].append(
                deepcopy(f["scene"]["resources"]["entries"][0])),
            "out of range": lambda f: f["scene"]["resources"]["entries"][0].update(id=3),
            "unavailable resident": lambda f: f["scene"]["resources"]["entries"][0].update(available=False),
            "invalid hash": lambda f: f["scene"]["resources"]["entries"][0].update(sha256="AB" * 32),
            "historical identity": lambda f: f["events"]["records"][1]["before_resource"].update(sha256="a" * 64),
            "manifest identity": lambda f: f["events"]["source"].update(manifest_sha256="a" * 64),
            "active code extent": lambda f: f["scene"]["resources"]["entries"][1].update(size=5),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                fixture = runtime_fixture()
                mutate(fixture)
                with self.assertRaises(SceneInputError):
                    build_scene_packet(**fixture)

    def test_static_decode_fault_has_no_invented_extent_or_retirement(self):
        code = b"\x1a"
        scene = scene_for(code)
        scene["checkpoint"].update(status=5, fault=2, fault_opcode=0x1a)
        events = envelope(scene, [])
        fault = {"pc": 0, "opcode": 0x1a, "op": "move", "fault": 2, "size": 0, "next": 0,
                 "branch": -1, "conditional": 0, "subop": 0, "payload_pc": 0, "payload_size": 0, "args": []}
        pages = pages_for(scene, [fault])
        pages[0]["stop"] = "decode_fault"
        packet = build_scene_packet(code=code, scene=scene, events=events, decode_pages=pages)
        self.assertEqual(packet["committed_changes"], [])
        self.assertEqual(packet["disassembly"]["retirements"], [])
        self.assertFalse(packet["disassembly"]["static_listing_complete"])
        pages[0]["records"][0]["bytes"] = "1a"
        with self.assertRaises(SceneInputError):
            build_scene_packet(code=code, scene=scene, events=events, decode_pages=pages)

    def test_not_taken_out_of_range_branch_and_actual_successor(self):
        code = bytes.fromhex("2801f0ff00")
        scene = scene_for(code)
        scene["checkpoint"].update(retired=1, pc=4, status=2)
        row = instruction(code, 0, 4, "zero", ((1, 1, 1),), branch=-12, conditional=1)
        event = record(row, 1, resolved=[0], branch_taken=False)
        events = envelope(scene, [event])
        pages = pages_for(scene, [row, instruction(code, 4, 1, "stop")])
        packet = build_scene_packet(code=code, scene=scene, events=events, decode_pages=pages)
        self.assertEqual(packet["disassembly"]["retirements"][0]["decoded"]["branch"], -12)
        self.assertFalse(packet["disassembly"]["retirements"][0]["branch_taken"])
        events["records"][0]["branch_taken"] = True
        with self.assertRaises(SceneInputError):
            build_scene_packet(code=code, scene=scene, events=events, decode_pages=pages)

    def test_supported_static_room_intent_does_not_become_a_commit(self):
        code = bytes.fromhex("7201")
        scene = scene_for(code)
        scene["checkpoint"].update(status=6, fault_opcode=0x72)
        events = envelope(scene, [])
        row = instruction(code, 0, 2, "load_room", ((0, 1, 1),))
        packet = build_scene_packet(code=code, scene=scene, events=events, decode_pages=pages_for(scene, [row]))
        self.assertEqual(packet["checkpoint"]["status"], 6)
        self.assertEqual(packet["committed_changes"], [])
        self.assertFalse(packet["qualification"]["room_rendering"])

    def test_selected_listing_pages_and_no_reachability_claim(self):
        fixture = raw_fixture()
        rows = fixture["decode_pages"][0]["records"]
        first, second = deepcopy(fixture["decode_pages"][0]), deepcopy(fixture["decode_pages"][0])
        first.update(limit=3, records=rows[:3], next_pc=13, stop="limit")
        second.update(start_pc=13, records=rows[3:])
        fixture["decode_pages"] = [first, second]
        self.assertTrue(build_scene_packet(**fixture)["disassembly"]["static_listing_complete"])
        fixture["decode_pages"] = [second]
        self.assertFalse(build_scene_packet(**fixture)["disassembly"]["static_listing_complete"])
        fixture["decode_pages"] = [second, first]
        with self.assertRaises(SceneInputError):
            build_scene_packet(**fixture)

    def test_cli_creates_complete_packet_and_refuses_overwrite(self):
        fixture = raw_fixture()
        with tempfile.TemporaryDirectory(prefix="scumm-packet-authored-") as directory:
            root = Path(directory)
            (root / "code.bin").write_bytes(fixture["code"])
            (root / "scene.json").write_text(json.dumps(fixture["scene"]), encoding="utf-8")
            (root / "events.json").write_text(json.dumps(fixture["events"]), encoding="utf-8")
            command = [sys.executable, str(Path(__file__).with_name("processor_scene.py")),
                       "--code", str(root / "code.bin"), "--scene", str(root / "scene.json"),
                       "--events", str(root / "events.json"), "--output", str(root / "packet.json")]
            first = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(first.returncode, 0, first.stderr)
            packet_bytes = (root / "packet.json").read_bytes()
            packet = json.loads(packet_bytes)
            self.assertEqual(packet["actors"][1]["name"]["bytes"], "4142")
            second = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual((root / "packet.json").read_bytes(), packet_bytes)


if __name__ == "__main__":
    unittest.main()
