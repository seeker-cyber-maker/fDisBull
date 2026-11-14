"""Actual DOS input consumption, stopped surfaces and clock-domain witnesses.

The guest code is authored independently of the QMP queue. A successful native
receipt is checked separately from BIOS/IRQ consumption and the guest's draw.
Supply the same native runtime variables as the DOS process witness suite.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import struct
import time

from PIL import Image
import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_io_fixture import bios_keyboard_display, raw_keyboard_mouse
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, number, process_record,
    process_runtime, read_bytes,
)


@pytest.fixture(scope="module")
def io_process_disk(process_runtime, tmp_path_factory):
    # FreeDOS actively polls BIOS ticks during its F5/F8 boot-key window. A
    # fixed instruction clock can stretch that unrelated delay in host time.
    # Omit that delay only in this I/O fixture, for both clock profiles;
    # keep the shared DOS baseline, production staging and budgets unchanged.
    directory = tmp_path_factory.mktemp("native-qemu-io-baseline")
    return prepare_dos_baseline(
        process_runtime["boot_image"], directory / "dos-io-baseline.img",
        process_runtime["mcopy"], config=b"SWITCHES=/F\r\n" + BASELINE_CONFIG,
    )


@pytest.fixture
def witness(tmp_path, process_runtime, io_process_disk):
    sequence = 0

    @contextmanager
    def launch(builder=bios_keyboard_display, **extra):
        nonlocal sequence
        sequence += 1
        directory = tmp_path / (builder.__name__ + str(sequence))
        directory.mkdir()
        code, symbols = builder(directory, process_runtime["nasm"])
        binary, project = create_project(directory, code)
        with project:
            with project.debugger(process_runtime["executable"], directory,
                    **launch_options(process_runtime, io_process_disk, **extra)) as debug:
                info = process_record(debug)
                symbols = {key: com_address(info, value) if key.endswith("_ip")
                           else value for key, value in symbols.items()}
                park(debug, symbols["ready_ip"])
                yield project, debug, symbols, directory
            assert debug.vm.process.poll() is not None
        assert binary.read_bytes() == code
        assert digest(io_process_disk["image"]) == io_process_disk["prepared_sha256"]

    return launch


def word(debug, symbols, name):
    return struct.unpack("<H", read_bytes(debug, symbols[name], 2))[0]


def park(debug, address, *, timeout_ms=5000):
    point = debug.breakpoint(address)
    try:
        result = debug.run(timeout_ms=timeout_ms)
        assert result["outcome"] == "breakpoint", result
        assert point["breakpoint_id"] in result["session"]["stop_reason"]["breakpoint_ids"]
        return result
    finally:
        debug.delete_breakpoint(point["breakpoint_id"])


def surface(project, debug, directory, name):
    artifact = debug.capture_surface(name + ".png")
    metadata = artifact["metadata"]
    assert metadata["source"] == "qemu_display_surface"
    assert metadata["stopped"] is True
    assert metadata["completed_guest_frame"] is None
    assert metadata["capture_id"]
    assert metadata["clocks"]["before"]["epoch"] == metadata["clocks"]["after"]["epoch"]
    assert metadata["clocks"]["before"]["session"]["state"] == "stopped"
    assert metadata["clocks"]["after"]["session"]["state"] == "stopped"
    path = directory / (name + ".png")
    project.debug_export(artifact["artifact"], path)
    with Image.open(path) as image:
        image = image.convert("RGB")
        assert image.width % 320 == image.height % 200 == 0
        scale_x, scale_y = image.width // 320, image.height // 200
        pixels = {"key": image.getpixel((10 * scale_x, 10 * scale_y)),
                  "mouse": image.getpixel((20 * scale_x, 10 * scale_y))}
    return artifact, pixels


def assert_accepted(result):
    receipt = result["input_delivery"]
    assert receipt["delivery"] == "qmp_accepted", result
    assert receipt["guest_consumed"] is None


def test_native_bios_consumption_and_guest_draw_are_separate(witness):
    with witness() as (project, debug, symbols, directory):
        database = project.path
        before, pixels = surface(project, debug, directory, "initial")
        assert pixels["key"] == (0, 0, 0)
        assert word(debug, symbols, "key_count_ip") == 0

        lease = debug.keyboard_key_down("a")["lease"]
        debug.keyboard_key_up(lease)
        assert debug.input_state()["pending_edges"] == 2
        assert word(debug, symbols, "key_count_ip") == 0
        stopped_registers = debug.registers()
        with pytest.raises(ValueError, match="Queued physical input"):
            debug.step()
        with pytest.raises(ValueError, match="Queued physical input"):
            debug.trace("pending-input-must-not-step.json", count=1)
        assert debug.registers() == stopped_registers
        assert debug.input_state()["pending_edges"] == 2

        result = park(debug, symbols["before_draw_ip"])
        assert_accepted(result)
        assert debug.input_state()["pending_edges"] == 0
        assert word(debug, symbols, "key_count_ip") == 1
        assert word(debug, symbols, "last_key_ip") == 0x1e61
        assert word(debug, symbols, "draw_count_ip") == 0
        consumed, pixels = surface(project, debug, directory, "consumed-before-draw")
        assert pixels["key"] == (0, 0, 0)

        park(debug, symbols["after_draw_ip"])
        assert word(debug, symbols, "draw_count_ip") == 1
        drawn, pixels = surface(project, debug, directory, "after-draw")
        assert pixels["key"] == (255, 0, 0)
        captures = [before, consumed, drawn]
        assert len({a["metadata"]["capture_id"] for a in captures}) == 3

    # Stored pixels and their conservative clock/frame provenance survive a
    # project reopen without pretending the original guest is still live.
    with Project(database) as reopened:
        assert reopened.debug_runs()["live_state_verified"] is False
        for index, artifact in enumerate(captures):
            row = reopened.db.execute("SELECT metadata FROM debug_artifacts WHERE id=?",
                                      (artifact["artifact"],)).fetchone()
            assert json.loads(row["metadata"]) == artifact["metadata"]
            path = directory / ("reopened-" + str(index) + ".png")
            reopened.debug_export(artifact["artifact"], path)
            assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_native_irq_keyboard_make_break_and_ps2_mouse_packets(witness):
    with witness(raw_keyboard_mouse) as (project, debug, symbols, directory):
        assert word(debug, symbols, "setup_status_ip") == 1
        assert read_bytes(debug, symbols["setup_ack_ip"], 1) == b"\xfa"
        lease = debug.keyboard_key_down("a")["lease"]
        result = debug.run(timeout_ms=250)
        assert result["outcome"] == "timeout"
        assert_accepted(result)
        assert word(debug, symbols, "keyboard_count_ip") == 1
        assert read_bytes(debug, symbols["keyboard_bytes_ip"], 1) == b"\x1e"
        _, pixels = surface(project, debug, directory, "key-held")
        assert pixels["key"] == (255, 0, 0)

        debug.keyboard_key_up(lease)
        assert_accepted(debug.run(timeout_ms=250))
        assert word(debug, symbols, "keyboard_count_ip") == 2
        assert read_bytes(debug, symbols["keyboard_bytes_ip"], 2) == b"\x1e\x9e"
        _, pixels = surface(project, debug, directory, "key-released")
        assert pixels["key"] == (0, 0, 255)

        debug.mouse_move_relative(5, 0)
        mouse_lease = debug.mouse_button_down("left")["lease"]
        assert_accepted(debug.run(timeout_ms=250))
        assert word(debug, symbols, "mouse_packet_count_ip") == 1
        assert read_bytes(debug, symbols["last_mouse_packet_ip"], 3) == b"\x09\x05\x00"
        _, pixels = surface(project, debug, directory, "mouse-held")
        assert pixels["mouse"] == (0, 255, 0)

        debug.mouse_button_up(mouse_lease)
        assert_accepted(debug.run(timeout_ms=250))
        assert word(debug, symbols, "mouse_packet_count_ip") == 2
        assert word(debug, symbols, "mouse_byte_count_ip") == 6
        assert read_bytes(debug, symbols["mouse_bytes_ip"], 6) == b"\x09\x05\x00\x08\x00\x00"
        _, pixels = surface(project, debug, directory, "mouse-released")
        assert pixels["mouse"] == (0, 0, 0)
        assert debug.input_state()["leases"] == {}


def test_native_early_breakpoint_does_not_fabricate_input_consumption(witness):
    with witness() as (_, debug, symbols, _):
        lease = debug.keyboard_key_down("a")["lease"]
        debug.keyboard_key_up(lease)
        result = park(debug, symbols["ready_ip"])
        receipt = result["input_delivery"]
        assert receipt["guest_consumed"] is None
        # GDB's continue and QMP's admission are distinct channels. An early
        # stop can win, or QMP can accept before the guest handles the IRQ.
        if receipt["delivery"] == "not_dispatched":
            assert debug.input_state()["pending_edges"] == 2
            debug.input_cancel_pending()
            assert debug.input_state()["pending_edges"] == 0
        else:
            assert receipt["delivery"] == "qmp_accepted", receipt
            assert debug.input_state()["pending_edges"] == 0
        assert word(debug, symbols, "key_count_ip") == 0
        assert word(debug, symbols, "draw_count_ip") == 0


@pytest.mark.parametrize("profile", ["standard", "instruction"])
def test_native_guest_ticks_pause_and_clock_domains_stay_distinct(witness, profile):
    with witness(qemu_clock=profile) as (_, debug, _, _):
        before = debug.clock_observe()
        ticks = read_bytes(debug, 0x46c, 4)
        time.sleep(.08)
        paused = debug.clock_observe()
        assert read_bytes(debug, 0x46c, 4) == ticks
        assert before["epoch"] == paused["epoch"]
        assert paused["host_monotonic_ns"] > before["host_monotonic_ns"]
        assert paused["sequence"] > before["sequence"]
        assert paused["counter"]["value"] == before["counter"]["value"]
        result = debug.run(timeout_ms=300)
        assert result["outcome"] == "timeout"
        after = debug.clock_observe()
        assert read_bytes(debug, 0x46c, 4) != ticks
        for observation in (before, paused, after):
            assert observation["virtual_ns"] is None
            assert observation["guest_ms"] is None
            assert observation["session"]["state"] == "stopped"
            assert observation["counter"]["unit"] == "instructions"
        if profile == "instruction":
            assert after["counter"]["state"] == "observed"
            assert after["counter"]["source"] == "query-replay.icount"
            assert after["counter"]["value"] > before["counter"]["value"]
        else:
            assert after["counter"]["state"] == "unsupported"
            assert after["counter"]["value"] is None


def test_native_closed_session_leases_do_not_reach_another_guest(witness):
    with witness(raw_keyboard_mouse) as (_, debug, symbols, _):
        lease = debug.keyboard_key_down("a")["lease"]
        session = debug.input_state()["session_id"]
        assert_accepted(debug.run(timeout_ms=250))
        assert word(debug, symbols, "keyboard_count_ip") == 1
        assert lease in debug.input_state()["leases"]
        # Closing an owned VM terminates the only destination for this held
        # physical key. Its Python lease must not survive into another VM.
    with witness(raw_keyboard_mouse) as (_, debug, symbols, _):
        assert debug.input_state()["session_id"] != session
        assert debug.input_state()["pending_edges"] == 0
        assert debug.input_state()["leases"] == {}
        with pytest.raises(ValueError, match="lease"):
            debug.keyboard_key_up(lease)
        assert word(debug, symbols, "keyboard_count_ip") == 0


def test_native_json_script_input_observation_then_new_source_trace(
        tmp_path, process_runtime, io_process_disk):
    from fdisbull.cli import respond
    from fdisbull.debugger import DebugWorkspace

    code, symbols = bios_keyboard_display(tmp_path, process_runtime["nasm"])
    binary, project = create_project(tmp_path, code)
    with project:
        pass
    database = tmp_path / "program.fdb"
    workspace = DebugWorkspace()

    def invoke(method, **params):
        reply = respond({"method": method,
                         "params": {"project": str(database), **params}},
                        debugger=workspace)
        assert reply["ok"], reply
        return reply["result"]

    try:
        started = invoke("debug-launch", executable=str(process_runtime["executable"]),
                         game_dir=str(tmp_path), **launch_options(
                             process_runtime, io_process_disk, qemu_clock="instruction"))
        run = started["run"]
        active = invoke("debug-dos-process", run=run)
        ready = com_address(active, symbols["ready_ip"])
        before_draw = com_address(active, symbols["before_draw_ip"])
        point = invoke("debug-breakpoint", run=run, address=ready)
        assert invoke("debug-run", run=run, timeout_ms=5000)["outcome"] == "breakpoint"
        invoke("debug-delete-breakpoint", run=run, breakpoint_id=point["breakpoint_id"])
        script = {"format": "fdisbull-script-1", "backend": "qemu-dos", "steps": [
            {"op": "clock-observe", "as": "before"},
            {"op": "breakpoint", "address": before_draw, "as": "consumed"},
            {"op": "keyboard.key-down", "key": "a", "as": "key"},
            {"op": "keyboard.key-up", "lease": "$key.lease"},
            {"op": "run", "timeout_ms": 3000, "as": "natural"},
            {"op": "assert", "value": "$natural.input_delivery.delivery",
             "equals": "qmp_accepted"},
            {"op": "delete-breakpoint", "breakpoint_id": "$consumed.breakpoint_id"},
            {"op": "clock-observe", "as": "after"},
            {"op": "capture-surface", "name": "script-consumed.png", "as": "surface"},
            {"op": "trace", "name": "after-input-trace.json", "count": 1,
             "timeout_ms": 3000, "as": "trace"},
        ]}
        report = invoke("debug-script", run=run, timeout_ms=15000, script=script)
        assert report["ok"] and report["completed_steps"] == len(script["steps"]), report
        natural = report["steps"][4]["result"]
        assert_accepted(natural)
        assert report["steps"][7]["result"]["counter"]["value"] > report["steps"][0]["result"]["counter"]["value"]
        capture = report["steps"][8]["result"]
        trace = report["steps"][9]["result"]
        counts = invoke("debug-memory", run=run,
                        address=com_address(active, symbols["key_count_ip"]),
                        length=4, space="physical")
        assert bytes.fromhex(counts["hex"]) == b"\x01\x00\x00\x00"
        observed = invoke("debug-clock-observe", run=run)
        assert observed["counter"]["state"] == "observed"
        assert invoke("debug-input-state", run=run)["pending_edges"] == 0
        assert invoke("debug-stop", run=run)["process_reaped"]
    finally:
        workspace.close()

    assert binary.read_bytes() == code
    assert digest(io_process_disk["image"]) == io_process_disk["prepared_sha256"]
    with Project(database) as reopened:
        path = tmp_path / "saved-after-input-trace.json"
        reopened.debug_export(trace["artifact"], path)
        document = json.loads(path.read_text())
        assert document["complete"] and document["requested_count"] == 1
        assert len(document["events"]) == 1
        # The natural run and its IRQ/BIOS work are outside this newly started
        # source window. Its only record begins at the independent draw fence.
        assert number(document["events"][0]["address"]) == before_draw
        assert document["events"][0]["bytes"] == "90"
        assert document["collector"]["steps"] == document["collector"]["attempted_steps"] == 1
        assert document["events"][0]["observation"]["instruction_completed"] is None
        image_path = tmp_path / "saved-script-consumed.png"
        reopened.debug_export(capture["artifact"], image_path)
        with Image.open(image_path) as image:
            assert image.convert("RGB").getpixel((image.width // 32, image.height // 20)) == (0, 0, 0)
        assert capture["metadata"]["completed_guest_frame"] is None


@pytest.mark.parametrize("device", ["keyboard", "mouse"])
def test_native_failed_script_reaps_guest_with_its_held_input(witness, device):
    with witness(raw_keyboard_mouse) as (_, debug, symbols, _):
        if device == "keyboard":
            down = {"op": "keyboard.key-down", "key": "a", "as": "held"}
            counter = symbols["keyboard_count_ip"]
        else:
            down = {"op": "mouse.button-down", "button": "left", "as": "held"}
            counter = symbols["mouse_packet_count_ip"]
        report = debug.script({"format": "fdisbull-script-1", "backend": "qemu-dos",
            "steps": [down,
                {"op": "run", "timeout_ms": 250, "expect": "timeout"},
                {"op": "memory", "address": counter, "length": 2,
                 "space": "physical", "as": "consumed"},
                {"op": "assert", "value": "$consumed.hex", "equals": "0100"},
                {"op": "assert", "value": False, "equals": True},
            ]}, timeout_ms=5000)
        assert not report["ok"] and report["error"]["index"] == 4, report
        assert_accepted(report["steps"][1]["result"])
        assert report["input_cleanup"]["closed"] is True
        assert debug.vm.process.poll() is not None
        state = debug.input_state()
        assert state["valid"] is False
        assert state["leases"] == {} and state["pending_edges"] == 0
