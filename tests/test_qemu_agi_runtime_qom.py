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
            assert len(guest["actors"]) == 256 and guest["actors"][1]["drawn"]
            assert len(guest["stack"]) == 64 and len(guest["script"]) == 4096
            assert len(guest["strings"]) == 25 and len(guest["menu_items"]) == 256
            assert len(guest["state_bytes_sha256"]) == 64
            assert guest["state_encoding"] == "agi-runtime-native-abi-1"
            assert guest["state_bytes_size"] > 100000
            assert len(guest["picture_visual_hex"]) == 160 * 168 * 2
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
