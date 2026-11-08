"""Independent guest witnesses for explicit native virtual-clock advancement.

FDISBULL_QEMU_CLOCK selects the privately patched QEMU executable. This suite
never substitutes it for FDISBULL_QEMU_DOS. The ordinary DOS boot-image,
mcopy, firmware and NASM variables supply the remaining private prerequisites.
FDISBULL_REQUIRE_QEMU_CLOCK=1 turns missing prerequisites into failures.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import struct
import time
import uuid

import pytest

from fdisbull.project import Project
from fdisbull.dosbox_rpc import DebuggerError
from support.dos_process_fixture import (
    BASELINE_CONFIG, com_exit, digest, prepare_dos_baseline, resident_com,
)
from support.qemu_clock_fixture import (
    PIT_DIVISOR, PIT_INPUT_HZ, busy_clock, halted_clock, pit_clock,
)
from test_qemu_dos_process_native import (
    assert_completion, com_address, create_project, launch_options,
    process_record, read_bytes,
)


@pytest.fixture(scope="module")
def clock_runtime():
    selected = {
        "executable": os.environ.get("FDISBULL_QEMU_CLOCK"),
        "boot_image": os.environ.get("FDISBULL_QEMU_DOS_BOOT_IMAGE"),
        "mcopy": os.environ.get("FDISBULL_QEMU_DOS_MCOPY"),
        "nasm": os.environ.get("NASM") or shutil.which("nasm"),
    }
    missing = [name for name, value in selected.items() if not value]
    if missing:
        message = "Native QEMU clock inputs missing: " + ", ".join(missing)
        if os.environ.get("FDISBULL_REQUIRE_QEMU_CLOCK") == "1":
            pytest.fail(message)
        pytest.skip(message)
    # Preserve the mcopy multicall invocation name, as in the DOS process lane.
    runtime = {name: (Path(value).expanduser().absolute() if name == "mcopy"
                     else Path(value).expanduser().resolve(strict=True))
               for name, value in selected.items()}
    for name, path in runtime.items():
        assert path.is_file(), (name, path)
        if name != "boot_image":
            assert os.access(path, os.X_OK), (name, path)
    runtime["firmware"] = (os.environ.get("FDISBULL_QEMU_CLOCK_FIRMWARE")
                           or os.environ.get("FDISBULL_QEMU_DOS_FIRMWARE"))
    return runtime


@pytest.fixture(scope="module")
def clock_disk(clock_runtime, tmp_path_factory):
    directory = tmp_path_factory.mktemp("native-qemu-clock-baseline")
    # Skip only the FreeDOS boot-key polling window. The kernel and shell still
    # execute the same authored process loader as the existing native lane.
    return prepare_dos_baseline(
        clock_runtime["boot_image"], directory / "dos-clock-baseline.img",
        clock_runtime["mcopy"], config=b"SWITCHES=/F\r\n" + BASELINE_CONFIG,
    )


def park(debug, address):
    point = debug.breakpoint(address)
    try:
        result = debug.run(timeout_ms=5000)
        assert result["outcome"] == "breakpoint", result
        assert point["breakpoint_id"] in result["session"]["stop_reason"]["breakpoint_ids"]
        return result
    finally:
        debug.delete_breakpoint(point["breakpoint_id"])


@pytest.fixture
def clock_witness(tmp_path, clock_runtime, clock_disk):
    @contextmanager
    def launch(builder):
        code, offsets = builder(tmp_path, clock_runtime["nasm"])
        binary, project = create_project(tmp_path, code)
        debug = None
        try:
            with project:
                try:
                    with project.debugger(clock_runtime["executable"], tmp_path,
                            **launch_options(clock_runtime, clock_disk,
                                             qemu_clock="virtual")) as debug:
                        info = process_record(debug)
                        symbols = {key: com_address(info, value)
                                   for key, value in offsets.items()}
                        park(debug, symbols["ready_ip"])
                        yield project, debug, symbols
                finally:
                    if debug is not None:
                        assert debug.vm.process.poll() is not None
        finally:
            assert binary.read_bytes() == code
            assert digest(clock_disk["image"]) == clock_disk["prepared_sha256"]
    return launch


def dword(debug, symbols, name):
    return struct.unpack("<I", read_bytes(debug, symbols[name], 4))[0]


def observation(debug):
    result = debug.clock_observe()
    assert type(result["virtual_ns"]) is int and result["virtual_ns"] >= 0, result
    assert result["session"]["state"] == "stopped"
    assert result["counter"]["state"] == "observed"
    assert result["counter"]["unit"] == "instructions"
    assert result["counter"]["source"] == "query-replay.icount"
    assert type(result["counter"]["value"]) is int
    return result


def budget_receipt(result, delta_ns, *, before=None, reached=True):
    assert result["timed_out"] is False, result
    assert result["session"]["state"] == "stopped", result
    budget = result["clock_budget"]
    assert budget["token"]
    for key in ("requested_delta_ns", "start_ns", "deadline_ns", "stopped_ns", "elapsed_ns"):
        assert type(budget[key]) is int and budget[key] >= 0, budget
    assert budget["requested_delta_ns"] == delta_ns
    assert budget["deadline_ns"] == budget["start_ns"] + delta_ns
    assert budget["elapsed_ns"] == budget["stopped_ns"] - budget["start_ns"]
    assert budget["deadline_reached"] is reached, budget
    assert isinstance(budget["native"], dict) and budget["native"], budget
    if before is not None:
        assert budget["start_ns"] == before["virtual_ns"], (before, budget)
    if reached:
        assert type(budget["fired_ns"]) is int
        assert budget["deadline_ns"] <= budget["fired_ns"] <= budget["stopped_ns"], budget
        assert type(budget["overshoot_ns"]) is int and budget["overshoot_ns"] >= 0
        assert budget["elapsed_ns"] >= delta_ns
    else:
        assert budget["fired_ns"] is None and budget["overshoot_ns"] is None, budget
        assert budget["stopped_ns"] < budget["deadline_ns"], budget
    return budget


def test_native_busy_clock_observes_paused_time_and_fresh_budget_tokens(clock_witness):
    with clock_witness(busy_clock) as (_, debug, symbols):
        before = observation(debug)
        time.sleep(.05)
        paused = observation(debug)
        assert paused["epoch"] == before["epoch"]
        assert paused["sequence"] > before["sequence"]
        assert paused["host_monotonic_ns"] > before["host_monotonic_ns"]
        assert paused["virtual_ns"] == before["virtual_ns"]
        assert paused["counter"]["value"] == before["counter"]["value"]
        assert dword(debug, symbols, "loop_count_ip") == 0

        first = budget_receipt(debug.clock_advance(5_000_000, timeout_ms=3000),
                               5_000_000, before=paused)
        middle = observation(debug)
        assert middle["virtual_ns"] == first["stopped_ns"]
        assert middle["counter"]["value"] > paused["counter"]["value"]
        first_count = dword(debug, symbols, "loop_count_ip")
        assert first_count > 0
        second = budget_receipt(debug.clock_advance(5_000_000, timeout_ms=3000),
                                5_000_000, before=middle)
        assert second["token"] != first["token"]
        assert dword(debug, symbols, "loop_count_ip") > first_count
        assert observation(debug)["virtual_ns"] == second["stopped_ns"]
        capture = debug.capture_surface('virtual-clock.png')['metadata']
        assert capture['clock_stability'] == 'virtual_clock_and_instruction_counter_unchanged'
        assert capture['clocks']['before']['virtual_ns'] == second['stopped_ns']
        assert capture['clocks']['after']['virtual_ns'] == second['stopped_ns']
        assert capture['completed_guest_frame'] is None


def test_native_unbudgeted_debug_stop_cannot_idle_warp_to_a_device_timer(clock_witness):
    with clock_witness(busy_clock) as (_, debug, symbols):
        before = observation(debug)
        park(debug, symbols['first_write_ip'])
        after = observation(debug)
        # The authored CLI path is one NOP between these two stops. There is
        # no HLT or IRQ execution authorizing a jump to an unrelated timer.
        assert 0 <= after['counter']['value'] - before['counter']['value'] < 100
        assert 0 <= after['virtual_ns'] - before['virtual_ns'] < 100_000


def test_native_cli_hlt_advances_virtual_clock_without_guest_instructions(clock_witness):
    with clock_witness(halted_clock) as (_, debug, symbols):
        before = observation(debug)
        bios_ticks = read_bytes(debug, 0x46c, 4)
        receipt = budget_receipt(debug.clock_advance(20_000_000, timeout_ms=3000),
                                 20_000_000, before=before)
        after = observation(debug)
        instruction_delta = after["counter"]["value"] - before["counter"]["value"]
        assert instruction_delta >= 0
        assert after["virtual_ns"] == receipt["stopped_ns"]
        assert receipt["elapsed_ns"] > instruction_delta * 128
        assert dword(debug, symbols, "unexpected_wakes_ip") == 0
        assert read_bytes(debug, 0x46c, 4) == bios_ticks


def test_native_pit_irqs_wake_hlt_and_track_observed_virtual_time(clock_witness):
    with clock_witness(pit_clock) as (_, debug, symbols):
        before = observation(debug)
        assert dword(debug, symbols, "irq_count_ip") == 0
        assert dword(debug, symbols, "wake_count_ip") == 0
        receipt = budget_receipt(debug.clock_advance(20_000_000, timeout_ms=3000),
                                 20_000_000, before=before)
        after = observation(debug)
        interrupts = dword(debug, symbols, "irq_count_ip")
        wakes = dword(debug, symbols, "wake_count_ip")
        expected = receipt["elapsed_ns"] * PIT_INPUT_HZ // (PIT_DIVISOR * 1_000_000_000)
        # The first pending IRQ and a stop inside the final handler can straddle
        # the interval boundaries. They do not justify an arbitrary tick count.
        assert expected - 2 <= interrupts <= expected + 2, (receipt, interrupts, wakes)
        assert interrupts > 0 and 0 < wakes <= interrupts
        assert interrupts - wakes <= 1
        instruction_delta = after["counter"]["value"] - before["counter"]["value"]
        assert instruction_delta > 0
        assert receipt["elapsed_ns"] > instruction_delta * 128
        assert after["virtual_ns"] == receipt["stopped_ns"]


@pytest.mark.parametrize("stop_kind", ["breakpoint", "watchpoint"])
def test_native_early_stop_cancels_budget_without_hiding_stop_or_replaying_input(
        clock_witness, stop_kind):
    with clock_witness(busy_clock) as (_, debug, symbols):
        point = (debug.breakpoint(symbols["first_write_ip"]) if stop_kind == "breakpoint"
                 else debug.breakpoint(symbols["loop_count_ip"], access="w", length=4))
        lease = debug.keyboard_key_down("a")["lease"]
        debug.keyboard_key_up(lease)
        before = observation(debug)
        try:
            result = debug.clock_advance(1_000_000, timeout_ms=3000)
            assert result["outcome"] == stop_kind, result
            assert point["breakpoint_id"] in result["session"]["stop_reason"]["breakpoint_ids"]
            early = budget_receipt(result, 1_000_000, before=before, reached=False)
            after = observation(debug)
            instruction_delta = after['counter']['value'] - before['counter']['value']
            # The authored early writer is reached before any HLT. A debugger
            # request waiting for the main loop must not become an idle warp.
            assert 0 < instruction_delta < 10
            assert early['elapsed_ns'] == instruction_delta * 128
        finally:
            debug.delete_breakpoint(point["breakpoint_id"])
        delivery = result["input_delivery"]
        assert delivery["guest_consumed"] is None
        if delivery["delivery"] == "not_dispatched":
            assert debug.input_state()["pending_edges"] == 2
            debug.input_cancel_pending()
        else:
            assert delivery["delivery"] == "qmp_accepted", delivery
        assert debug.input_state()["pending_edges"] == 0
        assert debug.input_state()["leases"] == {}

        # This ordinary continue must pass the old timer's deadline and reach
        # the authored fence. A stale timer would stop it before that fence.
        later = park(debug, symbols["late_boundary_ip"])
        assert "clock_budget" not in later
        assert "input_delivery" not in later
        assert dword(debug, symbols, "loop_count_ip") == 65536
        assert observation(debug)["virtual_ns"] > before["virtual_ns"] + 1_000_000


def test_native_cancel_before_continue_leaves_no_timer_or_deferred_stop(clock_witness):
    with clock_witness(busy_clock) as (_, debug, symbols):
        before = observation(debug)
        token = uuid.uuid4().hex
        armed = debug.vm.qmp.call('x-fdisbull-arm-clock-budget',
                                 {'delta-ns': 1_000_000, 'token': token})
        assert armed['budget-state'] == 'armed' and not armed['running']
        assert armed['virtual-ns'] == before['virtual_ns']
        with pytest.raises(DebuggerError, match='token mismatch'):
            debug.vm.qmp.call('x-fdisbull-cancel-clock-budget', {'token': 'wrong-token'})
        unchanged = debug.vm.qmp.call('x-fdisbull-query-clock')
        assert unchanged['budget-state'] == 'armed' and unchanged['budget-token'] == token
        final = debug.vm.qmp.call('x-fdisbull-cancel-clock-budget', {'token': token})
        assert final['budget-state'] == 'cancelled' and final['pending-stop'] is False
        assert final['virtual-ns'] == final['budget-stopped-ns'] == before['virtual_ns']
        assert 'budget-fired-ns' not in final
        assert debug.vm.qmp.call('x-fdisbull-cancel-clock-budget', {'token': token}) == final
        park(debug, symbols['late_boundary_ip'])
        assert dword(debug, symbols, 'loop_count_ip') == 65536
        assert observation(debug)['virtual_ns'] > armed['budget-deadline-ns']


def test_native_reset_invalidates_clock_and_closes_the_owned_process(clock_witness):
    with clock_witness(busy_clock) as (_, debug, _):
        before = observation(debug)['virtual_clock']['native']
        # Production uses -no-reboot and therefore exits on a reset request.
        # This probe explicitly enables native reset only to exercise the
        # extension's invalidation hook in a surviving emulator process.
        debug.vm.qmp.call('set-action', {'reboot': 'reset'})
        debug.vm.qmp.call('system_reset')
        deadline = time.monotonic() + 2
        while True:
            reset = debug.vm.qmp.call('x-fdisbull-query-clock', timeout_ms=1000)
            if reset['epoch'] != before['epoch']:
                break
            assert time.monotonic() < deadline, reset
        assert reset['budget-state'] == 'invalidated'
        assert reset['budget-supported'] is False
        with pytest.raises(DebuggerError, match='virtual clock'):
            debug.clock_observe()
        assert debug.vm.process.poll() is not None
        assert debug.dos_process_info()['machine_closed'] is True


@pytest.mark.parametrize("resident", [False, True], ids=["dos-exit", "dos-tsr"])
def test_native_clock_budget_preserves_dos_completion(
        tmp_path, clock_runtime, clock_disk, resident):
    code = resident_com(exit_code=37)[0] if resident else com_exit(37)
    binary, project = create_project(tmp_path, code)
    with project:
        with project.debugger(clock_runtime["executable"], tmp_path,
                **launch_options(clock_runtime, clock_disk, qemu_clock="virtual")) as debug:
            process_record(debug)
            before = observation(debug)
            result = debug.clock_advance(1_000_000_000, timeout_ms=5000)
            assert_completion(debug, result, resident=resident, exit_code=37)
            budget_receipt(result, 1_000_000_000, before=before, reached=False)
        assert debug.vm.process.poll() is not None
    assert binary.read_bytes() == code
    assert digest(clock_disk["image"]) == clock_disk["prepared_sha256"]


def test_native_public_json_and_saved_script_preserve_clock_receipts(
        tmp_path, clock_runtime, clock_disk):
    from fdisbull.cli import respond
    from fdisbull.debugger import DebugWorkspace

    code, symbols = busy_clock(tmp_path, clock_runtime["nasm"])
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
        started = invoke("debug-launch", executable=str(clock_runtime["executable"]),
                         game_dir=str(tmp_path), **launch_options(
                             clock_runtime, clock_disk, qemu_clock="virtual"))
        run = started["run"]
        active = invoke("debug-dos-process", run=run)
        point = invoke("debug-breakpoint", run=run,
                       address=com_address(active, symbols["ready_ip"]))
        assert invoke("debug-run", run=run, timeout_ms=5000)["outcome"] == "breakpoint"
        invoke("debug-delete-breakpoint", run=run, breakpoint_id=point["breakpoint_id"])
        before = invoke("debug-clock-observe", run=run)
        direct = invoke("debug-clock-advance", run=run, delta_ns=2_000_000, timeout_ms=3000)
        budget_receipt(direct, 2_000_000, before=before)

        script = {"format": "fdisbull-script-1", "backend": "qemu-dos", "steps": [
            {"op": "clock-observe", "as": "before"},
            {"op": "clock-advance", "delta_ns": 5_000_000, "timeout_ms": 3000, "as": "advance"},
            {"op": "assert", "value": "$advance.clock_budget.deadline_reached", "equals": True},
            {"op": "clock-observe", "as": "after"},
            {"op": "assert", "value": "$after.virtual_ns", "equals": "$advance.clock_budget.stopped_ns"},
        ]}
        report = invoke("debug-script", run=run, timeout_ms=10000, script=script)
        assert report["ok"] and report["completed_steps"] == len(script["steps"]), report
        receipt = budget_receipt(report["steps"][1]["result"], 5_000_000,
                                 before=report["steps"][0]["result"])
        assert receipt["token"] != direct["clock_budget"]["token"]
        assert invoke("debug-stop", run=run)["process_reaped"]
    finally:
        workspace.close()

    with Project(database) as reopened:
        path = tmp_path / "saved-clock-route-result.json"
        reopened.debug_export(report["artifact"], path)
        saved = json.loads(path.read_text())
        assert saved["ok"] is True
        assert saved["steps"][1]["result"]["clock_budget"] == receipt
        assert reopened.debug_runs()["live_state_verified"] is False
    assert binary.read_bytes() == code
    assert digest(clock_disk["image"]) == clock_disk["prepared_sha256"]
