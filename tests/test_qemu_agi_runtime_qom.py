"""Actual QEMU package/QOM acceptance; explicitly skipped without a candidate.

All bytecode, messages, views and package variants are authored here. Python
only drives QMP and checks native output; it does not execute AGI semantics.
"""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native/qemu-agi"


def load(name):
    key = "_fdisbull_agi_" + name
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, NATIVE / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


pack = load("runtime_pack")
harness = load("runtime_harness")


@pytest.fixture(scope="module")
def binary():
    configured = os.environ.get("FDISBULL_QEMU_AGI")
    if not configured:
        pytest.skip("runtime QOM acceptance requires explicit FDISBULL_QEMU_AGI")
    path = Path(configured).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        pytest.fail("FDISBULL_QEMU_AGI must name an executable native candidate")
    return path


def package(code=b"\0", messages=(), **kwargs):
    return pack.build_package(logics=[{"id": 0, "code": code, "messages": list(messages)}], **kwargs)


def runtime(binary, value):
    return harness.QemuAGIRuntime(binary, value, timeout=20)


def test_qom_complete_architecture_observation_neutrality_and_scene(binary):
    # Two-by-two solid green cel, one loop. Original AGI RLE, not host pixels.
    view = bytes([0, 0, 1, 0, 0, 7, 0, 1, 3, 0, 2, 2, 15, 0x22, 0, 0x22, 0])
    code = bytes([3, 50, 7, 1, 50, 30, 1, 33, 1, 37, 1, 20, 80,
                  41, 1, 1, 35, 1, 70, 1, 0])
    data = pack.dump_package(package(code, views=[{"id": 1, "data": view}]))
    guests, images = [], []
    for mask, capacity in [(0, 0), (1, 4096), (2, 4096), (3, 1)]:
        with runtime(binary, data) as vm:
            vm.configure(mask=mask, capacity=capacity)
            state = vm.run(step_budget=100)
            guest = state["guest"]
            assert state["source"] == {
                "sha256": sha256(data).hexdigest(), "profile": pack.PROFILE,
                "logic_id": 0, "logic_sha256": sha256(code).hexdigest(),
            }
            assert guest["status"] == "return" and guest["retired"] == 9
            assert guest["variables"][50] == 8 and guest["loaded_views"][1] == 1
            assert guest["view_order_count"] == 1 and guest["view_order"][0] == 1
            assert len(guest["picture_order"]) == 256 and not guest["picture_order_count"]
            assert len(guest["actors"]) == 256 and guest["actors"][1]["drawn"]
            assert len(guest["stack"]) == 64 and len(guest["script"]) == 4096
            assert guest["script_entry_encoding"] == "agi-replay-byte-pairs-1"
            assert guest["script_count"] == 1 and guest["script"][0]["pair"] == [1, 1]
            assert len(guest["sound"]["channels"]) == 4
            assert len(guest["sound"]["last_output"]["events"]) == 16
            assert len(guest["strings"]) == 25 and len(guest["menu_items"]) == 256
            assert len(guest["state_bytes_sha256"]) == 64
            assert guest["state_encoding"] == "agi-runtime-native-abi-1"
            assert guest["state_bytes_size"] > 100000
            assert len(guest["picture_visual_hex"]) == 160 * 168 * 2
            assert len(guest["window_text_hex"]) == len(guest["window_fg_hex"]) == len(guest["window_bg_hex"]) == 2000
            assert (guest["window_x"], guest["window_y"], guest["window_width"], guest["window_height"]) == (0, 0, 0, 0)
            assert guest["window_ticks_remaining"] == 0
            assert vm.state()["guest"] == guest  # serialization is read-only
            guests.append(guest)
            scene = vm.scene()
            visual = bytes.fromhex(scene["visual"])
            wanted = bytearray([15] * (160 * 168))
            for y in (79, 80):
                wanted[y * 160 + 20:y * 160 + 22] = b"\x02\x02"
            assert visual == wanted
            images.append((scene["visual"], scene["priority"]))
            assert vm.state()["guest"] == guest
            events = vm.events()
            assert events["source"] == state["source"]
            assert len(events["events"]) == state["observation"]["count"]
            if not mask:
                assert not events["events"] and not state["observation"]["eligible"]
            if capacity == 1:
                assert len(events["events"]) == 1 and state["observation"]["dropped"] > 0
    assert all(guest == guests[0] for guest in guests[1:])
    assert all(image == images[0] for image in images[1:])


@pytest.mark.parametrize("command", [
    '{"action":"seed","variables":{"4":17},"flags":{"5":2}}',
    '{"action":"seed","variables":{"01":1}}',
    '{"action":"seed","variables":{"256":1}}',
    '{"action":"seed","variables":{"5":true}}',
    '{"action":"tick","ticks":0}',
    '{"action":"tick","ticks":1.0}',
    '{"action":"tick","ticks":4097}',
    '{"action":"sound-tick","ticks":0}',
    '{"action":"sound-tick","ticks":1.0}',
    '{"action":"sound-tick","ticks":4097}',
    '{"action":"clock","ticks":0}',
    '{"action":"clock","ticks":1.0}',
    '{"action":"clock","ticks":4097}',
    '{"action":"sound-device","device":2}',
    '{"action":"sound-device","device":true}',
    '{"action":"sound-clear","epoch":1,"through":1}',
    '{"action":"sound-clear","epoch":true,"through":0}',
    '{"action":"key","key":65536,"pressed":true}',
    '{"action":"key","key":1,"pressed":1}',
    '{"action":"controller","controller":-1}',
    '{"action":"input","text":"\\u0000"}',
    '{"action":"input","text":"😀"}',
    '{"action":"cycle","unexpected":1}',
    '{"action":"tick","action":"cycle","ticks":1}',
    "{'action':'cycle'}",
    '[]',
])
def test_qom_command_validation_is_atomic(binary, command):
    with runtime(binary, package()) as vm:
        before = vm.state()
        with pytest.raises(harness.QMPError):
            vm.set("agi-runtime-command", command)
        assert vm.state() == before


def test_qom_seed_input_keys_controllers_cycle_and_explicit_ticks(binary):
    data = package(words=[{"text": "look", "id": 7}])
    with runtime(binary, data) as vm:
        state = vm.seed(variables={50: 9}, flags={80: 1})
        assert state["guest"]["variables"][50] == 9
        assert state["guest"]["flags"][80] == 1
        assert vm.input("look")["guest"]["word_ids"][0] == 7
        assert vm.controller(200)["guest"]["controllers"][200] == 1
        assert vm.key(0x4D00, True)["guest"]["actors"][0]["direction"] == 3
        prepared = vm.cycle()["guest"]
        assert prepared["cycle_active"] == 1 and prepared["ticks"] == 0
        before = vm.state()
        with pytest.raises(harness.QMPError):
            vm.tick()
        assert vm.state() == before
        after = vm.run(step_budget=10)["guest"]
        assert after["status"] == "return" and after["cycle_active"] == 0
        assert after["ticks"] == after["cycle_count"] == 1
        after = vm.tick(20)["guest"]
        assert after["ticks"] == 21 and after["variables"][11] == 1
        with pytest.raises(harness.QMPError):
            vm.set("agi-runtime-command", '{"action":"seed","variables":{"50":1}}')


def test_qom_cp437_message_string_and_typed_completion(binary):
    code = bytes([114, 1, 1, 101, 2, 115, 2, 3, 0, 0, 40, 0])
    with runtime(binary, package(code, ["é" * 41, "%s1", "Name?"])) as vm:
        state = vm.run(step_budget=50)
        assert state["guest"]["strings"][1] == "é" * 40
        raw_strings = bytes.fromhex(state["guest"]["strings_hex"])
        assert raw_strings[41:82] == b"\x82" * 40 + b"\0"
        ticket = vm.pending()
        assert ticket["effect"]["text"] == "é" * 40
        assert ticket["effect"]["reply"] == "ack"
        before = vm.state()
        with pytest.raises(harness.QMPError):
            vm.set("agi-runtime-command", json.dumps({
                "action": "complete", "id": ticket["effect"]["id"] + 1, "accepted": True,
            }))
        assert vm.state() == before
        vm.complete(ticket, accepted=True)
        vm.run(step_budget=50)
        ticket = vm.pending()
        assert ticket["effect"]["reply"] == "text"
        completed = vm.complete(ticket, accepted=True, text="é" * 40)
        assert completed["guest"]["strings"][2] == "é" * 40
        assert completed["guest"]["pending_effect"] is None
        assert vm.run(step_budget=50)["guest"]["status"] == "return"


def test_qom_cp437_message_and_object_native_byte_limits(binary):
    # U+253C is three UTF-8 bytes but one CP437 byte (C5). The native
    # message/OBJECT bounds must not accidentally become UTF-8 byte bounds.
    message = "┼" * 4095
    name = "┼" * 255
    value = package(bytes([101, 1, 0]), [message], objects=[
        {"name": name, "room": 7}, {"name": name, "room": 8},
    ])
    with runtime(binary, value) as vm:
        state = vm.run(step_budget=10)
        assert state["guest"]["inventory"][:2] == [7, 8]
        ticket = vm.pending()
        assert ticket["effect"]["text"] == message
        assert len(ticket["effect"]["text"].encode("utf-8")) == 12285
        vm.complete(ticket, accepted=True)
        assert vm.run(step_budget=10)["guest"]["status"] == "return"


def test_qom_numeric_completion_requires_explicit_value(binary):
    with runtime(binary, package(bytes([118, 1, 77, 0]), ["Number?"])) as vm:
        vm.run(step_budget=10)
        ticket = vm.pending()
        before = vm.state()
        with pytest.raises(harness.QMPError):
            vm.set("agi-runtime-command", json.dumps({
                "action": "complete", "id": ticket["effect"]["id"], "accepted": True,
            }))
        assert vm.state() == before
        assert vm.complete(ticket, accepted=True, number=123)["guest"]["variables"][77] == 123


def test_qom_sound_state_and_explicit_native_output_ticks(binary):
    # Channel zero: one tick of tone then a terminator. Other channels end
    # immediately. Device zero selects the original PC speaker channel.
    sound = bytes([8, 0, 15, 0, 17, 0, 19, 0,
                   1, 0, 0x37, 0x80, 0x90, 0xFF, 0xFF]) + b"\xff\xff" * 3
    value = package(bytes([3, 22, 0, 98, 1, 99, 1, 80, 0]),
                    sounds=[{"id": 1, "data": sound}])
    with runtime(binary, value) as vm:
        start = vm.run(step_budget=20)["guest"]
        assert start["retired"] == 4 and start["status"] == "return"
        assert start["sound"]["active"] == 1 and start["sound_active"] == 1
        assert start["sound"]["remaining"] == start["sound_remaining"] == 2
        assert start["sound"]["ticks_per_second"] == 60
        assert start["sound"]["channel_count"] == 1 and start["flags"][80] == 0
        first = vm.sound_tick()["guest"]
        assert first["ticks"] == first["clock_ticks"] == 0
        assert first["sound"]["ticks"] == 1 and first["retired"] == 4
        assert first["sound"]["channels"][0]["tone"] == 0x8037
        output = first["sound"]["last_output"]
        assert output["count"] == 1
        assert output["events"][0] == {
            "sequence": 1, "tick": 1, "kind": 1, "channel": 0,
            "value": 10560, "enabled": 1,
        }
        ended = vm.sound_tick()["guest"]
        assert ended["sound"]["active"] == ended["sound_active"] == 0
        assert ended["sound"]["remaining"] == ended["sound_remaining"] == 0
        assert ended["flags"][80] == 1 and ended["sound"]["ticks"] == 2
        assert ended["sound"]["last_output"]["events"][0]["enabled"] == 0


@pytest.mark.parametrize("clock", ["world", "sound"])
def test_qom_sound_journal_keeps_all_batch_outputs_and_acknowledges_exact_capture(binary, clock):
    # Two one-tick speaker records followed by the terminator. A single
    # world tick contains three sound ticks; capture must retain all three.
    sound = bytes([8, 0, 20, 0, 22, 0, 24, 0,
                   1, 0, 0x37, 0x80, 0x90,
                   1, 0, 0x10, 0x81, 0x90, 0xFF, 0xFF]) + b"\xff\xff" * 3
    value = package(bytes([3, 22, 0, 98, 1, 99, 1, 80, 0]),
                    sounds=[{"id": 1, "data": sound}])
    guests, captures = [], []
    for mask in (0, 3):
        with runtime(binary, value) as vm:
            vm.configure(mask=mask, capacity=4096)
            vm.run(step_budget=20)
            empty = vm._json_property("agi-runtime-sound-json")
            assert empty["count"] == empty["eligible"] == empty["dropped"] == 0
            if clock == "world":
                vm.tick()
            else:
                vm.sound_tick(3)
            before = vm.state()
            captured = vm._json_property("agi-runtime-sound-json")
            assert captured["schema"] == "fdisbull-agi-runtime-sound-events-1"
            assert captured["source"] == before["source"]
            assert captured["columns"] == [
                "seq", "native_epoch", "sequence", "tick", "kind", "channel", "value", "enabled",
            ]
            assert captured["events"] == [
                [1, 0, 1, 1, 1, 0, 10560, 1],
                [2, 0, 2, 2, 1, 0, 3084, 1],
                [3, 0, 3, 3, 1, 0, 0, 0],
            ]
            assert captured["count"] == captured["eligible"] == captured["last_seq"] == 3
            assert captured["dropped"] == 0 and captured["capacity"] == 262144
            assert vm.state() == before  # journal reads are nondestructive
            with pytest.raises(harness.QMPError):
                vm.set("agi-runtime-command", json.dumps({
                    "action": "sound-clear", "epoch": empty["epoch"], "through": empty["last_seq"],
                }))
            assert vm.state() == before
            vm.set("agi-runtime-command", json.dumps({
                "action": "sound-clear", "epoch": captured["epoch"], "through": captured["last_seq"],
            }))
            after = vm.state()
            assert after["guest"] == before["guest"]
            assert after["observation"] == before["observation"]
            cleared = vm._json_property("agi-runtime-sound-json")
            assert cleared["count"] == cleared["eligible"] == cleared["dropped"] == 0
            assert cleared["last_seq"] == 3 and cleared["epoch"] == captured["epoch"] + 1
            guests.append(before["guest"])
            captures.append(captured)
    assert guests[0] == guests[1]
    assert captures[0] == captures[1]


def test_qom_sound_journal_overflow_is_explicit_and_full_capture_fits_transport(binary):
    # Four zero-duration records play for65536 sound ticks. PCjr emits volume
    # commands every tick, deliberately filling the bounded output journal.
    streams = [bytes([0, 0, 0x37, high, control, 0xFF, 0xFF])
               for high, control in [(0x80, 0x90), (0xA0, 0xB0), (0xC0, 0xD0), (0xE0, 0xF0)]]
    sound = b"".join((8 + 7 * i).to_bytes(2, "little") for i in range(4)) + b"".join(streams)
    value = package(bytes([3, 22, 1, 98, 1, 99, 1, 80, 0]),
                    sounds=[{"id": 1, "data": sound}])
    with runtime(binary, value) as vm:
        vm.configure(mask=0, capacity=0)
        vm.sound_device(1)
        vm.run(step_budget=20)
        for _ in range(6):
            vm.tick(4096)
        before = vm.state()
        assert before["guest"]["flags"][80] == 1
        captured = vm._json_property("agi-runtime-sound-json")
        assert captured["count"] == len(captured["events"]) == captured["capacity"] == 262144
        assert captured["eligible"] == captured["count"] + captured["dropped"]
        assert captured["dropped"] > 0 and captured["last_seq"] == captured["eligible"]
        assert captured["events"][0][0] == 1 and captured["events"][-1][0] == 262144
        # The outer QMP string wrapping was already read under the actual
        #32MiB transport budget. Clearing needs an explicit current receipt.
        vm.set("agi-runtime-command", json.dumps({
            "action": "sound-clear", "epoch": captured["epoch"], "through": captured["last_seq"],
        }))
        assert vm.state()["guest"] == before["guest"]
        assert vm._json_property("agi-runtime-sound-json")["count"] == 0
        vm.restart()
        vm.run(step_budget=20)
        vm.sound_tick()
        restarted = vm._json_property("agi-runtime-sound-json")
        assert restarted["native_epoch"] == 1
        assert restarted["events"][0][:3] == [captured["last_seq"] + 1, 1, 1]


@pytest.mark.parametrize("accepted,expected", [(True, "quit"), (False, "ready")])
def test_qom_choice_uses_boolean_acceptance(binary, accepted, expected):
    with runtime(binary, package(bytes([134, 0, 0]))) as vm:
        vm.run(step_budget=10)
        ticket = vm.pending()
        assert ticket["effect"]["reply"] == "choice"
        assert vm.complete(ticket, accepted=accepted)["guest"]["status"] == expected


def test_qom_snapshot_restore_is_bound_and_failed_restore_is_atomic(binary):
    with runtime(binary, package(bytes([125, 3, 50, 9, 126, 0]))) as vm:
        vm.seed(variables={50: 7})
        vm.run(step_budget=10)
        saved = vm.snapshot()
        assert saved[:8] == b"FDBAGIS1"
        vm.complete(vm.pending(), accepted=True)
        state = vm.run(step_budget=10)
        assert state["guest"]["variables"][50] == 9
        ticket = vm.pending()
        assert ticket["effect"]["reply"] == "restore"
        corrupt = bytes([saved[0] ^ 1]) + saved[1:]
        before = vm.state()
        with pytest.raises(harness.QMPError):
            vm.restore(ticket, corrupt)
        assert vm.state() == before
        restored = vm.restore(ticket, saved)["guest"]
        assert restored["variables"][50] == 7 and restored["flags"][12] == 1
        assert restored["status"] == "ready" and restored["pending_effect"] is None


def malformed_package(kind):
    value = deepcopy(package())
    if kind == "duplicate_id":
        value["logics"].append(deepcopy(value["logics"][0]))
    elif kind == "hash":
        value["logics"][0]["sha256"] = "0" * 64
    elif kind == "entry_boolean":
        value["entry_logic"] = True
    elif kind == "entry_float":
        value["entry_logic"] = 0.0
    elif kind == "entry_missing":
        value["entry_logic"] = 1
    elif kind == "implicit_seed":
        value["variables"] = {"0": 1}
    elif kind == "missing_array":
        del value["words"]
    elif kind == "uppercase_hex":
        value["logics"][0].update(code="0A", sha256=sha256(b"\x0a").hexdigest())
    elif kind == "empty_resource":
        value["views"] = [{"id": 1, "data": "", "sha256": sha256(b"").hexdigest()}]
    elif kind == "nul":
        value["logics"][0]["messages"] = ["a\0b"]
    elif kind == "unicode":
        value["logics"][0]["messages"] = ["😀"]
    elif kind == "long_message":
        value["logics"][0]["messages"] = ["a" * 4096]
    elif kind == "long_object":
        value["objects"] = [{"name": "a" * 256, "room": 0}]
    elif kind == "duplicate_word":
        value["words"] = [{"text": "look", "id": 1}, {"text": "look", "id": 2}]
    elif kind == "uppercase_word":
        value["words"] = [{"text": "Look", "id": 1}]
    elif kind == "profile":
        value["profile"] = "unknown"
    encoded = json.dumps(value, ensure_ascii=False).encode("utf-8")
    if kind == "duplicate_key":
        encoded = encoded.replace(b'{"schema":', b'{"schema":"ignored","schema":', 1)
    elif kind == "single_quotes":
        encoded = encoded.replace(b'"', b"'")
    elif kind == "raw_nul":
        encoded += b"\0"
    return encoded


@pytest.mark.parametrize("kind", [
    "duplicate_id", "hash", "entry_boolean", "entry_float", "entry_missing",
    "implicit_seed", "missing_array", "uppercase_hex", "empty_resource", "nul",
    "unicode", "long_message", "long_object", "duplicate_word", "uppercase_word",
    "profile", "duplicate_key", "single_quotes", "raw_nul",
])
def test_qom_native_loader_rejects_malformed_packages(binary, tmp_path, kind):
    # Intentionally bypass the Python validator to exercise native admission.
    path = tmp_path / "invalid.json"
    path.write_bytes(malformed_package(kind))
    result = subprocess.run([
        str(binary), "-M", f"agi-test,runtime-package={path}",
        "-accel", "tcg,thread=single", "-S", "-display", "none", "-serial", "none",
        "-monitor", "none", "-nodefaults", "-no-user-config",
    ], stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
    assert result.returncode != 0
    assert b"AGI_RUNTIME" in result.stderr or b"JSON parse error" in result.stderr


def test_qom_public_sound_capture_binds_and_clears_native_output(binary):
    sound = bytes([8, 0, 15, 0, 17, 0, 19, 0,
                   1, 0, 0x37, 0x80, 0x90, 0xFF, 0xFF]) + b"\xff\xff" * 3
    value = package(bytes([98, 1, 99, 1, 80, 0]), sounds=[{"id": 1, "data": sound}])
    with runtime(binary, value) as vm:
        vm.configure(mask=0, capacity=0)
        vm.run(step_budget=20)
        vm.sound_tick(2)
        before = vm.state()
        capture = vm.sound_events()
        assert capture["context"] == vm.context_id
        assert capture["binary_sha256"] == vm.binary_sha256
        assert capture["count"] == 2 and not capture["dropped"]
        assert [row[7] for row in capture["events"]] == [1, 0]
        assert vm.state() == before
        forged = deepcopy(capture)
        forged["events"][0][6] += 1
        with pytest.raises(harness.HarnessError):
            vm.clear_sound_events(forged)
        assert vm.state() == before
        after = vm.clear_sound_events(capture)
        assert after["guest"] == before["guest"]
        assert after["observation"] == before["observation"]
        assert vm.sound_events()["count"] == 0
        with pytest.raises(harness.HarnessError):
            vm.clear_sound_events(capture)


def test_qom_clock_advances_system_and_audio_without_actor_ticks(binary):
    with runtime(binary, package(bytes([101, 1, 136, 0]), ["Wait"])) as vm:
        vm.key(0x4D00, True)
        vm.run(step_budget=10)
        before = vm.state()["guest"]
        assert before["pending_effect"]["opcode"] == 101
        after = vm.clock(20)["guest"]
        assert after["clock_ticks"] == 20 and after["variables"][11] == 1
        assert after["sound"]["ticks"] == 60
        assert after["actors"] == before["actors"] and after["ticks"] == 0
        assert after["retired"] == before["retired"]
        assert after["pending_effect"] == before["pending_effect"]
        vm.complete(vm.pending(), accepted=True)
        vm.run(step_budget=10)
        paused = vm.state()
        assert paused["guest"]["pending_effect"]["opcode"] == 136
        with pytest.raises(harness.QMPError):
            vm.clock()
        assert vm.state() == paused


def test_qom_hardware_choice_is_explicit_and_independent_of_report_variables(binary):
    streams = [bytes([1, 0, 0x37, high, control, 0xFF, 0xFF])
               for high, control in [(0x80, 0x90), (0xA0, 0xB0), (0xC0, 0xD0), (0xE0, 0xF0)]]
    sound = b"".join((8 + 7 * i).to_bytes(2, "little") for i in range(4)) + b"".join(streams)
    value = package(bytes([3, 22, 0, 98, 1, 99, 1, 80, 0]),
                    sounds=[{"id": 1, "data": sound}])
    with runtime(binary, value) as vm:
        initial = vm.state()["guest"]
        assert initial["sound_device"] == 0
        assert [initial["variables"][i] for i in (20, 22, 24, 26)] == [0, 1, 38, 3]
        configured = vm.sound_device(1)["guest"]
        assert configured["sound_device"] == 1 and configured["variables"][22] == 3
        started = vm.run(step_budget=20)["guest"]
        assert started["variables"][22] == 0  # guest can overwrite its report
        assert started["sound_device"] == 1 and started["sound"]["channel_count"] == 4
        before = vm.state()
        with pytest.raises(harness.QMPError):
            vm.sound_device(0)
        assert vm.state() == before
        vm.restart()
        restarted = vm.state()["guest"]
        assert restarted["sound_device"] == 1 and restarted["variables"][22] == 3


def test_qom_simple_description_preserves_native_bytes_and_empty_disables(binary):
    with runtime(binary, package(bytes([114, 1, 1, 170, 1, 125, 170, 0, 0]), ["é" * 40])) as vm:
        enabled = vm.run(step_budget=20)["guest"]
        assert enabled["simple_save"] == 1 and enabled["simple_description"] == "é" * 40
        assert bytes.fromhex(enabled["simple_description_hex"]) == b"\x82" * 40 + b"\0"
        vm.complete(vm.pending(), accepted=True)
        disabled = vm.run(step_budget=20)["guest"]
        assert disabled["simple_save"] == 0 and disabled["simple_description"] == ""
        assert bytes.fromhex(disabled["simple_description_hex"])[0] == 0


def presentation_view():
    # Two loops share one cel. Loop0 resolves its mirror here in native code;
    # a short second row is padded with transparency before being mirrored.
    return bytes([0, 0, 2, 20, 0, 9, 0, 9, 0, 1, 3, 0, 2, 2, 0x9F,
                  0x21, 0x31, 0, 0x41, 0]) + b"\x82p\x82e\0"


@pytest.mark.parametrize("opcode,args,kind", [
    (29, b"", "priority-plane"),
    (110, b"\x02", "shake-screen"),
    (124, b"", "inventory"),
    (129, b"\x07", "show-object"),
    (162, b"\x32", "show-object"),
    (133, b"\x33", "actor-status"),
])
def test_qom_native_device_queries_and_runtime_service_capture(binary, opcode, args, kind):
    services = load("runtime_services")
    view = presentation_view()
    # Bind and draw actor3, then change inventory locations before the request.
    prefix = bytes([30, 7, 33, 3, 41, 3, 7, 37, 3, 20, 80, 35, 3,
                    95, 0, 52, 92, 1])
    code = prefix + bytes([opcode]) + args + b"\0"
    value = package(code, views=[{"id": 7, "data": view}], objects=[
        {"name": "épée", "room": 255}, {"name": "clé", "room": 4},
    ])
    with runtime(binary, value) as vm:
        vm.configure(mask=3, capacity=4096)
        vm.seed(variables={50: 7, 51: 3, 52: 4})
        vm.run(step_budget=100)
        before, events = vm.state(), vm.events()
        query = vm.presentation()
        assert query["schema"] == "fdisbull-agi-runtime-presentation-1"
        assert query["source"] == before["source"]
        assert query["request"] == {k: v for k, v in before["guest"]["pending_effect"].items()
                                     if k != "text"}
        payload = query["presentation"]
        assert payload["kind"] == kind
        if opcode in (29, 110):
            scene = vm.scene()
            assert payload["visual"] == scene["visual"]
            assert payload["priority"] == scene["priority"]
            pixels = bytes.fromhex(payload["visual"])
            assert pixels[79 * 160 + 20:79 * 160 + 22] == b"\x03\x02"
            assert pixels[80 * 160 + 20:80 * 160 + 22] == b"\x0f\x04"
            if opcode == 29:
                assert payload["presented_plane"] == "priority"
            else:
                assert payload["frame_count"] == 8 and payload["restore_original"]
                assert payload["coordinate_space"] == "display-pixels"
                assert payload["frames"] == [
                    {"index": i, "dx": 0 if i & 1 else -3, "dy": 0 if i & 1 else -3}
                    for i in range(8)
                ]
                assert payload["picture_scale_x"] == 2 and payload["picture_scale_y"] == 1
                assert payload["text_hex"] == before["guest"]["text_hex"]
        elif opcode == 124:
            assert payload["selectable"] is False
            assert payload["entries"] == [
                {"id": 0, "name": "épée", "name_hex": "82708265", "room": 4, "carried": False},
                {"id": 1, "name": "clé", "name_hex": "636c82", "room": 255, "carried": True},
            ]
        elif opcode in (129, 162):
            assert payload["view"] == 7 and payload["view_sha256"] == sha256(view).hexdigest()
            assert payload["loop"] == payload["cel"] == 0
            assert (payload["width"], payload["height"], payload["transparent"]) == (2, 2, 15)
            assert payload["mirrored"] is True and payload["pixels"] == "03020f04"
            assert payload["description"] == "épée" and payload["description_hex"] == "82708265"
            assert payload["description_offset"] == 20
            assert (payload["x"], payload["y"]) == (79, 112)
        else:
            assert payload["variable"] == 51
            assert payload["actor"] == before["guest"]["actors"][3]
        assert vm.state() == before and vm.events() == events
        host = services.RuntimeServices(vm)
        handled = host.handle()
        assert handled["status"] == "presentation"
        assert handled["state"]["guest"]["pending_effect"] is None
        assert handled["state"]["guest"]["retired"] == before["guest"]["retired"] + 1
        entry = host.ledger["entries"][0]
        assert entry["status"] == "completed" and entry["presentation"] == payload
        assert entry["request"]["effect"]["id"] == query["request"]["id"]
        assert vm.run(step_budget=100)["guest"]["status"] == "return"


@pytest.mark.parametrize("accepted", [False, True])
def test_qom_inventory_selection_requires_a_caller_choice(binary, accepted):
    services = load("runtime_services")
    value = package(bytes([124, 0]), objects=[
        {"name": "left behind", "room": 1}, {"name": "carried", "room": 255},
    ])
    with runtime(binary, value) as vm:
        vm.seed(flags={13: 1})
        vm.run(step_budget=10)
        host = services.RuntimeServices(vm)
        before = vm.state()
        waiting = host.handle()
        assert waiting["status"] == "choice_required"
        assert waiting["required"] == ["accepted", "number"]
        assert waiting["presentation"]["kind"] == "inventory"
        assert waiting["presentation"]["selectable"] is True
        assert waiting["presentation"]["selection_variable"] == 25
        assert vm.state() == before and not host.ledger["entries"]
        if accepted:
            with pytest.raises(harness.QMPError):
                host.handle(choice={"accepted": True, "number": 0})
            assert vm.state() == before
            handled = host.handle(choice={"accepted": True, "number": 1})
        else:
            handled = host.handle(choice={"accepted": False})
        assert handled["state"]["guest"]["variables"][25] == (1 if accepted else 255)
        assert handled["state"]["guest"]["pending_effect"] is None


def test_qom_joystick_request_requires_an_explicit_device_result(binary):
    services = load("runtime_services")
    with runtime(binary, package(bytes([139, 0]))) as vm:
        vm.run(step_budget=10)
        host = services.RuntimeServices(vm)
        before = vm.state()
        waiting = host.handle()
        assert waiting["status"] == "choice_required"
        assert waiting["required"] == ["accepted", "calibrated"]
        payload = waiting["presentation"]
        assert payload == {
            "kind": "joystick-calibration", "device": "joystick", "completion": "ack",
            "requires_host_result": True, "guest_calibration_storage": False,
        }
        assert vm.state() == before and not host.ledger["entries"]
        with pytest.raises(ValueError):
            host.handle(choice={"accepted": True, "calibrated": False})
        with pytest.raises(ValueError):
            host.handle(choice={"accepted": True})
        assert vm.state() == before
        # An authored test device supplies a result; this makes no claim about
        # real joystick hardware or an implicit physical calibration service.
        handled = host.handle(choice={"accepted": True, "calibrated": True})
        assert handled["status"] == "device_completed"
        assert handled["state"]["guest"]["pending_effect"] is None
        assert host.ledger["entries"][0]["result_source"] == "caller"


@pytest.mark.parametrize("damage", ["description_offset", "description_nul", "row_extent"])
def test_qom_bad_preview_resource_preserves_pending_state(binary, damage):
    services = load("runtime_services")
    view = bytearray(presentation_view())
    if damage == "description_offset":
        view[3:5] = (len(view) + 1).to_bytes(2, "little")
    elif damage == "description_nul":
        del view[-1]
    else:
        view[15] = 0x23
    value = package(bytes([129, 7, 0]), views=[{"id": 7, "data": bytes(view)}])
    with runtime(binary, value) as vm:
        vm.configure(mask=3, capacity=4096)
        vm.run(step_budget=10)
        before, events = vm.state(), vm.events()
        assert before["guest"]["pending_effect"]["opcode"] == 129
        with pytest.raises(harness.QMPError):
            vm.presentation()
        assert vm.state() == before and vm.events() == events
        host = services.RuntimeServices(vm)
        with pytest.raises(harness.QMPError):
            host.handle()
        assert vm.state() == before and not host.ledger["entries"]


@pytest.mark.parametrize("count", [0, 255])
def test_qom_shake_plan_has_bounded_exact_phase_count(binary, count):
    with runtime(binary, package(bytes([110, count, 0]))) as vm:
        vm.run(step_budget=10)
        before = vm.state()
        payload = vm.presentation()["presentation"]
        assert payload["count"] == count
        assert payload["frame_count"] == len(payload["frames"]) == 4 * count
        assert payload["restore_original"] is True
        if count:
            assert payload["frames"][0] == {"index": 0, "dx": -3, "dy": -3}
            assert payload["frames"][-1] == {"index": 1019, "dx": 0, "dy": 0}
        assert vm.state() == before


def test_qom_presentation_without_request_or_for_unrelated_text_is_neutral(binary):
    with runtime(binary, package(bytes([101, 1, 0]), ["Text only"])) as vm:
        before = vm.state()
        empty = vm.presentation()
        assert empty["request"] is None and empty["presentation"] is None
        assert vm.state() == before
        vm.run(step_budget=10)
        before = vm.state()
        text = vm.presentation()
        assert text["request"]["opcode"] == 101 and text["presentation"] is None
        assert vm.state() == before


def test_qom_presentation_is_bound_to_current_called_logic(binary):
    code0, code7 = bytes([22, 7, 0]), bytes([29, 0])
    value = pack.build_package(logics=[
        {"id": 0, "code": code0, "messages": []},
        {"id": 7, "code": code7, "messages": []},
    ])
    with runtime(binary, value) as vm:
        vm.run(step_budget=10)
        before = vm.state()
        query = vm.presentation()
        assert query["source"] == before["source"]
        assert query["source"]["logic_id"] == query["request"]["logic"] == 7
        assert query["source"]["logic_sha256"] == sha256(code7).hexdigest()
        assert query["request"]["pc"] == 0 and query["request"]["next_pc"] == 1
        assert vm.state() == before


@pytest.mark.parametrize("instruction", [
    bytes([101, 1]), bytes([102, 50]), bytes([151, 1, 2, 3, 20]), bytes([152, 50, 2, 3, 20]),
])
def test_qom_timed_print_countdown_retires_once_with_observation_neutrality(binary, instruction):
    code = instruction + bytes([3, 60, 9, 0])
    outcomes = []
    for mask in (0, 1, 2, 3):
        with runtime(binary, package(code, ["Timed é text"])) as vm:
            vm.configure(mask=mask, capacity=4096)
            vm.seed(variables={21: 2, 19: 55, 50: 1})
            original = vm.state()["guest"]
            waiting = vm.run(step_budget=20)["guest"]
            assert waiting["window_open"] == 1 and waiting["window_ticks_remaining"] == 20
            assert waiting["variables"][19] == 0 and waiting["variables"][21] == 2
            assert waiting["retired"] == waiting["pc"] == 0
            assert waiting["pending_effect"]["text"] == "Timed é text"
            saved_ticket = vm.pending()
            before = vm.state()
            with pytest.raises(harness.QMPError):
                vm.snapshot()
            assert vm.state() == before
            # Neither a bounded raw run nor the60Hz audio-only API supplies
            # a20Hz window timer tick or implicitly executes an actor phase.
            assert vm.run(step_budget=1)["guest"] == waiting
            after_audio = vm.sound_tick(2)["guest"]
            assert after_audio["window_ticks_remaining"] == 20
            assert after_audio["clock_ticks"] == after_audio["ticks"] == 0
            almost = vm.clock(19)["guest"]
            assert almost["window_ticks_remaining"] == 1 and almost["retired"] == 0
            assert almost["pending_effect"] == waiting["pending_effect"]
            assert almost["actors"] == waiting["actors"] and almost["ticks"] == 0
            before = vm.state()
            with pytest.raises(harness.QMPError):
                vm.set("agi-runtime-command", '{"action":"clock","ticks":4097}')
            assert vm.state() == before
            expired = vm.clock()["guest"]
            assert expired["window_ticks_remaining"] == expired["window_open"] == 0
            assert expired["variables"][21] == 0 and expired["pending_effect"] is None
            assert expired["status"] == "ready" and expired["retired"] == 1
            assert expired["pc"] == len(instruction) and expired["variables"][60] == 0
            assert expired["clock_ticks"] == 20 and expired["sound"]["ticks"] == 62
            assert expired["actors"] == waiting["actors"] and expired["ticks"] == 0
            for field in ("text_hex", "text_fg_hex", "text_bg_hex"):
                assert expired[field] == original[field]
            assert vm.snapshot().startswith(b"FDBAGIS1")
            before = vm.state()
            with pytest.raises(harness.QMPError):
                vm.set("agi-runtime-command", json.dumps({
                    "action": "complete", "id": saved_ticket["effect"]["id"], "accepted": True,
                }))
            assert vm.state() == before
            assert vm.clock()["guest"]["retired"] == 1
            events = vm.events()["events"]
            assert sum(e["opcode"] == instruction[0] and e["channel_id"] == 0 for e in events) == bool(mask & 1)
            assert sum(e["opcode"] == instruction[0] and e["channel_id"] == 1 for e in events) == bool(mask & 2)
            one = vm.run(step_budget=1)["guest"]
            assert one["retired"] == 2 and one["variables"][60] == 9
            assert one["status"] == "budget"
            outcomes.append(vm.run(step_budget=10)["guest"])
    assert all(value == outcomes[0] for value in outcomes[1:])


@pytest.mark.parametrize("delay", [0, 2])
def test_qom_enter_dismisses_modal_print_without_implicit_time(binary, delay):
    with runtime(binary, package(bytes([101, 1, 0]), ["Enter"])) as vm:
        vm.seed(variables={21: delay})
        vm.run(step_budget=10)
        before = vm.state()["guest"]
        assert before["window_ticks_remaining"] == 10 * delay
        assert vm.key(0x0D, False)["guest"] == before
        other = vm.key(0x20, True)["guest"]
        assert other["pending_effect"] == before["pending_effect"]
        entered = vm.key(0x0D, True)["guest"]
        assert entered["pending_effect"] is None and entered["retired"] == 1
        assert entered["window_ticks_remaining"] == entered["window_open"] == 0
        assert entered["variables"][21] == entered["keypress"] == 0
        assert entered["clock_ticks"] == entered["ticks"] == entered["sound"]["ticks"] == 0
        assert vm.key(0x0D, False)["guest"]["retired"] == 1


def test_qom_nonblocking_print_consumes_flag_without_starting_timer(binary):
    with runtime(binary, package(bytes([101, 1, 0]), ["Nonmodal"])) as vm:
        vm.seed(variables={21: 2}, flags={15: 1})
        opened = vm.run(step_budget=10)["guest"]
        assert opened["status"] == "return" and opened["retired"] == 2
        assert opened["flags"][15] == 0 and opened["variables"][21] == 2
        assert opened["window_open"] == 1 and opened["window_ticks_remaining"] == 0
        assert opened["pending_effect"] is None
        assert vm.snapshot().startswith(b"FDBAGIS1")
        later = vm.clock(25)["guest"]
        assert later["window_open"] == 1 and later["variables"][21] == 2
        assert later["text_hex"] == opened["text_hex"] and later["retired"] == 2


def test_qom_timed_completion_preserves_normal_cycle_finish_order(binary):
    with runtime(binary, package(bytes([101, 1, 0]), ["Cycle wait"])) as vm:
        vm.seed(variables={21: 1})
        vm.cycle()
        waiting = vm.run(step_budget=10)["guest"]
        assert waiting["cycle_active"] == 1 and waiting["ticks"] == waiting["cycle_count"] == 0
        ready = vm.clock(10)["guest"]
        assert ready["retired"] == 1 and ready["pending_effect"] is None
        assert ready["cycle_active"] == 1 and ready["ticks"] == ready["cycle_count"] == 0
        returned = vm.run(step_budget=10)["guest"]
        assert returned["cycle_active"] == 0 and returned["ticks"] == returned["cycle_count"] == 1
        assert returned["retired"] == 2
        assert vm.clock()["guest"]["ticks"] == 1


def test_qom_timed_service_records_once_and_enforces_output_capacity(binary):
    services = load("runtime_services")
    code = bytes([3, 21, 1, 101, 1, 3, 21, 1, 101, 2, 0])
    with runtime(binary, package(code, ["First timed output", "Second timed output"])) as vm:
        vm.run(step_budget=20)
        host = services.RuntimeServices(vm, max_outputs=1)
        before = vm.state()
        waiting = host.handle()
        assert waiting["status"] == "waiting" and waiting["reason"] == "timed"
        assert waiting["window_ticks_remaining"] == 10 and waiting["ticks_per_second"] == 20
        assert vm.state() == before
        assert host.ledger["entries"][0]["text"] == "First timed output"
        assert host.ledger["entries"][0]["timed"] is True
        assert host.ledger["entries"][0]["status"] == "recorded"
        assert host.handle()["ledger_sequence"] == waiting["ledger_sequence"]
        assert len(host.ledger["entries"]) == 1
        vm.clock(9)
        assert host.handle()["window_ticks_remaining"] == 1
        assert len(host.ledger["entries"]) == 1
        assert vm.clock()["guest"]["pending_effect"] is None
        assert host.handle()["status"] == "idle"
        vm.run(step_budget=20)
        before = vm.state()
        with pytest.raises(harness.HarnessError, match="capacity"):
            host.handle()
        assert vm.state() == before and len(host.ledger["entries"]) == 1


@pytest.mark.parametrize("accepted", [True, False])
def test_qom_timed_service_accepts_explicit_early_completion(binary, accepted):
    services = load("runtime_services")
    with runtime(binary, package(bytes([101, 1, 0]), ["Explicit early acknowledgement"])) as vm:
        vm.seed(variables={21: 255})
        vm.run(step_budget=10)
        host = services.RuntimeServices(vm)
        assert host.handle()["window_ticks_remaining"] == 2550
        result = host.handle(choice={"accepted": accepted})
        guest = result["state"]["guest"]
        assert guest["retired"] == 1 and guest["pending_effect"] is None
        assert guest["variables"][21] == guest["window_ticks_remaining"] == 0
        assert guest["clock_ticks"] == guest["ticks"] == 0
        assert sum(entry.get("text") == "Explicit early acknowledgement"
                   for entry in host.ledger["entries"]) == 1


def test_qom_native_simple_mode_drives_memory_slots_and_empty_disables(binary):
    services = load("runtime_services")
    code = bytes([114, 1, 1, 170, 1, 125, 3, 60, 9, 126, 170, 0, 125, 0])
    with runtime(binary, package(code, ["épée slot"])) as vm:
        vm.seed(variables={60: 7})
        host = services.RuntimeServices(vm)
        vm.run(step_budget=20)
        assert host.handle()["status"] == "saved"
        assert set(host.slots) == {"épée slot"}
        assert vm.run(step_budget=20)["guest"]["variables"][60] == 9
        restored = host.handle()
        assert restored["status"] == "restored"
        assert restored["state"]["guest"]["variables"][60] == 7
        # Resume to the restore instruction again, then explicitly cancel it
        # so the guest can disable simple mode with an empty string.
        vm.run(step_budget=20)
        host.handle(choice={"accepted": False})
        pending = vm.run(step_budget=20)["guest"]
        assert pending["simple_save"] == 0 and pending["simple_description"] == ""
        assert host.handle()["status"] == "choice_required"


def test_qom_native_simple_restore_missing_slot_preserves_request(binary):
    services = load("runtime_services")
    with runtime(binary, package(bytes([114, 1, 1, 170, 1, 126, 0]), ["missing"])) as vm:
        vm.run(step_budget=20)
        host = services.RuntimeServices(vm)
        before = vm.state()
        with pytest.raises(harness.HarnessError, match="does not exist"):
            host.handle()
        assert vm.state() == before and host.ledger["entries"] == []


def test_qom_log_capture_preserves_native_room_and_echo(binary):
    services = load("runtime_services")
    with runtime(binary, package(bytes([144, 1, 0]), ["From room %v0"])) as vm:
        vm.seed(variables={0: 7})
        vm.input("look")
        vm.run(step_budget=10)
        host = services.RuntimeServices(vm)
        assert host.handle()["status"] == "output"
        entry = host.ledger["entries"][0]
        assert entry["operation"] == "log" and entry["text"] == "From room 7"
        assert entry["room"] == 7 and entry["input"] == "look"
