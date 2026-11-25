"""Compare Doom E1M1 progress during a bounded guest-time interval.

This opt-in private-input test acquires the pre-increment leveltime 64
landmark, settles DOSBox-X back to ordinary speed, and starts both backends
at the resulting Doom leveltime. It advances each for one uninterrupted
1800 ms guest-time budget, then records leveltime, BDA ticks and engine clocks.
It does not capture audio or require conditional breakpoints.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.le import load_runtime_le_carrier
from fdisbull.project import Project
from support.doom_le_dosbox import (
    CODE_OFFSET, DATA_OFFSET, placement, read as dosbox_read, reach_site,
)
from support.doom_le_qemu import PINS, runtime_inputs as qemu_runtime_inputs, stage_game
from test_doom_leveltime_paired_native import (
    _qemu_rebind_at_endpoint, _qemu_site, _qemu_wait_tic,
)


START_TIC = 64
BUDGET_MS = 1800
BDA_TICKS_PER_DAY = 0x1800B0
BDA_TICKS_PHYSICAL = 0x46C
QEMU_GAME_ARGUMENTS = "-warp 1 1 -skill 2 -nomonsters -config D:\\DEFAULT.CFG"
DOSBOX_GAME_ARGUMENTS = "-warp 1 1 -skill 2 -nomonsters -config DEFAULT.CFG"
DOSBOX_TOTAL_DEADLINE_SECONDS = 180
DOSBOX_WINDOW_DEADLINE_SECONDS = 60
DOSBOX_SPEED_SETTLE_MS = 250
DOSBOX_MAX_WINDOW_OVERSHOOT_MS = 250
QEMU_WINDOW_DEADLINE_MS = 60_000


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_hashes(source: Path) -> dict:
    return {name: _sha(source / name) for name in PINS}


def _bda_ticks_qemu(debug) -> int:
    raw = bytes.fromhex(debug.memory(
        BDA_TICKS_PHYSICAL, length=4, space="physical")["hex"])
    return int.from_bytes(raw, "little")


def _qemu_measure(tmp_path: Path, source: Path, runtime: dict,
                  target_start_tic: int, *, budget_ms: int = BUDGET_MS) -> dict:
    if type(budget_ms) is not int or not 1 <= budget_ms <= 60_000:
        raise ValueError("QEMU timing budget_ms must be an integer in 1..60000")
    budget_ns = budget_ms * 1_000_000
    stage = tmp_path / "qemu"
    stage.mkdir()
    game = stage_game(stage, source)
    owners = []
    qemu_options = dict(
        backend="qemu-dos", dos_directory=str(game),
        dos_boot_image=str(runtime["boot_image"]),
        dos_mcopy=str(runtime["mcopy"]), qemu_transport="pipe",
        qemu_firmware=runtime["firmware"], qemu_audio="sb16-opl",
        qemu_retrace="precise", qemu_clock="virtual",
        qemu_checkpoint_tool=str(runtime["checkpoint_tool"]),
        dos_arguments=QEMU_GAME_ARGUMENTS, boot_timeout_ms=35_000)
    with Project.create(stage / "doom.fdb", game / "DOOM.EXE", image="mz") as project:
        with project.debugger(runtime["executable"], game, _on_spawn=owners.append,
                              **qemu_options) as debug:
            pc, counter, code = _qemu_site(project, debug, stage / "source-binding.json")
            start_breakpoint = debug.breakpoint(pc)["breakpoint_id"]
            start_tic, _, start_breakpoint = _qemu_wait_tic(
                debug, pc, counter, start_breakpoint, target_start_tic)
            binding = _qemu_rebind_at_endpoint(debug, pc, counter, target_start_tic)
            start_bda = _bda_ticks_qemu(debug)
            start_clock = debug.clock_observe()["virtual_ns"]
            debug.delete_breakpoint(start_breakpoint)

            # The native clock budget owns one uninterrupted continue and its
            # timer stop; no repeated execution breakpoint targets the INC.
            stopped = debug.clock_advance(budget_ns,
                                          timeout_ms=QEMU_WINDOW_DEADLINE_MS)
            budget = stopped["clock_budget"]
            assert budget["deadline_reached"], stopped
            assert budget["elapsed_ns"] >= budget_ns, stopped
            assert stopped["outcome"] not in ("guest_exit", "guest_tsr", "exited"), stopped
            end_tic = int.from_bytes(bytes.fromhex(debug.memory(
                counter, length=4, space="virtual")["hex"]), "little")
            end_bda = _bda_ticks_qemu(debug)
            end_clock = debug.clock_observe()["virtual_ns"]
            assert end_tic > start_tic, (stopped, end_tic)

            result = dict(
                backend="qemu-dos", start_tic=start_tic, end_tic=end_tic,
                leveltime_delta=end_tic - start_tic,
                source_sha256=PINS["DOOM.EXE"], instruction_bytes=code.hex(),
                site=dict(object_index=1, object_offset=CODE_OFFSET,
                          target_object=3, target_offset=DATA_OFFSET,
                          runtime_pc=pc, runtime_counter=counter),
                bda=dict(address_physical=hex(BDA_TICKS_PHYSICAL),
                         start=start_bda, end=end_bda,
                         delta=(end_bda - start_bda) % BDA_TICKS_PER_DAY,
                         tick_period_ns=54_925_493),
                engine_clock=dict(unit="QEMU_CLOCK_VIRTUAL_nanoseconds",
                                  start=start_clock, end=end_clock,
                                  delta=end_clock - start_clock),
                guest_time_budget=dict(unit="nanoseconds", requested=budget_ns,
                                       elapsed=budget["elapsed_ns"],
                                       overshoot=budget["overshoot_ns"]),
                intermediate_execution_breakpoints=0,
                uninterrupted_guest_continues=1,
                end_stop=stopped["outcome"], audio_capture=False,
                runtime_sha256=_sha(runtime["executable"]),
                boot_image_sha256=_sha(runtime["boot_image"]),
                mcopy_sha256=_sha(runtime["mcopy"]),
                checkpoint_tool_sha256=_sha(runtime["checkpoint_tool"]),
                source_binding_id=binding["binding_id"])
    assert owners and all(owner.poll() is not None for owner in owners)
    assert all(owner.returncode == 0 for owner in owners), [owner.returncode for owner in owners]
    result["owner_reaped"] = True
    result["owner_returncodes"] = [owner.returncode for owner in owners]
    assert _source_hashes(source) == PINS
    return result


class _DOSBoxSessionView:
    def __init__(self, call):
        self._call = call

    def call(self, method, params=None):
        return self._call(method, params)

    def registers(self):
        result = self.call("state.get_registers")
        result.update(cs=result["segments"]["cs"], ip=result["instruction_pointer"])
        return result


def _dosbox_measure(
    tmp_path: Path,
    source: Path,
    executable: Path,
    *,
    poll_wait_ms: int = 100,
    max_window_overshoot_ms: int = DOSBOX_MAX_WINDOW_OVERSHOOT_MS,
    target_start_tic: int | None = None,
    budget_ms: int = BUDGET_MS,
) -> dict:
    if type(budget_ms) is not int or not 1 <= budget_ms <= 60_000:
        raise ValueError("DOSBox-X timing budget_ms must be an integer in 1..60000")
    if type(poll_wait_ms) is not int or not 1 <= poll_wait_ms <= 100:
        raise ValueError("DOSBox-X timing poll_wait_ms must be an integer in 1..100")
    if (type(max_window_overshoot_ms) is not int
            or not 0 <= max_window_overshoot_ms <= 5_000):
        raise ValueError("DOSBox-X max_window_overshoot_ms must be an integer in 0..5000")
    if target_start_tic is not None and (
            type(target_start_tic) is not int or not START_TIC <= target_start_tic <= 200):
        raise ValueError("DOSBox-X target_start_tic must be None or an integer in 64..200")
    stage = tmp_path / "dosbox"
    game = stage / "game"
    game.mkdir(parents=True)
    for name, expected in PINS.items():
        original = source / name
        assert _sha(original) == expected
        (game / name).write_bytes(original.read_bytes())
    assert _source_hashes(game) == PINS
    image = load_runtime_le_carrier((game / "DOOM.EXE").read_bytes())
    rpc = DOSBoxRPC(executable, game)
    owner = rpc.process
    total_deadline = time.monotonic() + DOSBOX_TOTAL_DEADLINE_SECONDS
    last_tic = None

    def call(method, parameters=None, *, timeout_ms=15_000):
        assert time.monotonic() < total_deadline, (
            f"DOSBox-X total deadline expired at leveltime {last_tic}")
        return rpc.call(method, parameters, timeout_ms=timeout_ms)

    try:
        started = call("session.start", dict(
            target=dict(command="DOOM.EXE", arguments=DOSBOX_GAME_ARGUMENTS.split()),
            mounts=[dict(drive="C", host_path=str(game))], break_at="entry"))
        session_id = started["session_id"]

        def session_call(method, parameters=None, *, timeout_ms=15_000):
            return call(method, dict(session_id=session_id, **(parameters or {})),
                        timeout_ms=timeout_ms)

        view = _DOSBoxSessionView(session_call)
        initial_timing = session_call("execution.timing")
        assert initial_timing["fast_forward"] is False, initial_timing
        registers = session_call("state.get_registers")
        assert registers["cpu_mode"] == "real", registers
        # Match the proven landmark acquisition path: use fast-forward while
        # finding the protected source site and tic64. Record settling back
        # to ordinary speed before sampling the measured interval.
        acquisition_start = session_call("execution.timing", dict(fast_forward=True))
        assert acquisition_start["fast_forward"] is True, acquisition_start
        reach_site(view, image)
        site = placement(view, image)
        assert site and site["runtime_address"] == site["cs_base"] + site["ip"]
        pc, counter = site["runtime_address"], site["runtime_target"]
        assert site["runtime_bytes"] == "ff05" + counter.to_bytes(4, "little").hex()
        address = dict(space="segmented", segment=f"0x{site['cs']:04x}",
                       offset=f"0x{pc - site['cs_base']:08x}")

        def tic_at_stop():
            nonlocal last_tic
            last_tic = int.from_bytes(dosbox_read(view, "linear", counter, 4), "little")
            return last_tic

        def wait_for_tic(breakpoint_id: str, operation_id: str,
                         *, deadline: float | None = None) -> None:
            deadline = min(total_deadline, deadline or (
                time.monotonic() + DOSBOX_WINDOW_DEADLINE_SECONDS))
            while time.monotonic() < deadline:
                stopped = session_call("execution.wait", dict(
                    operation_id=operation_id, timeout_ms=100), timeout_ms=1_000)
                if stopped.get("running"):
                    continue
                assert stopped["state"] == "stopped", stopped
                assert stopped["stop_reason"]["kind"] == "breakpoint", stopped
                assert stopped["stop_reason"]["breakpoint_id"] == breakpoint_id, stopped
                current = placement(view, image)
                assert current and current["runtime_address"] == pc, current
                return
            raise TimeoutError("DOSBox-X did not reach its start breakpoint before the deadline")

        # Advance to the start landmark before sampling either clock. These
        # per-tic stops are outside the measured window.
        tic = tic_at_stop()
        assert tic <= START_TIC, tic
        while tic < START_TIC:
            stepped = session_call("execution.step", dict(mode="into"))
            assert stepped["stop_reason"]["kind"] == "step", stepped
            tic = tic_at_stop()
            assert tic <= START_TIC, tic
            point = session_call("breakpoints.create", dict(
                kind="execution", once=True, address=address))
            operation = session_call("execution.continue")
            wait_for_tic(point["breakpoint_id"], operation["operation_id"])
            tic = tic_at_stop()
        assert tic == START_TIC, tic

        speed_transition = session_call("execution.timing", dict(fast_forward=False))
        assert speed_transition["fast_forward"] is False, speed_transition
        settle_start = session_call("execution.timing")
        settle_operation = session_call("execution.continue")
        settle_deadline = min(total_deadline,
                              time.monotonic() + DOSBOX_WINDOW_DEADLINE_SECONDS)
        while time.monotonic() < settle_deadline:
            settle_now = session_call("execution.timing")
            if settle_now["guest_ticks"] - settle_start["guest_ticks"] >= DOSBOX_SPEED_SETTLE_MS:
                break
            pending = session_call("execution.wait", dict(
                operation_id=settle_operation["operation_id"], timeout_ms=100),
                timeout_ms=1_000)
            assert pending.get("running"), pending
        else:
            raise TimeoutError("DOSBox-X did not complete ordinary-speed settling")
        settle_pause = session_call("execution.pause")
        settle_stopped = session_call("execution.wait", dict(
            operation_id=settle_pause["operation_id"], timeout_ms=3_000))
        assert not settle_stopped.get("running"), settle_stopped
        assert settle_stopped["stop_reason"]["kind"] == "pause", settle_stopped
        settle_end = session_call("execution.timing")
        settle_tic = tic_at_stop()
        assert settle_end["fast_forward"] is False, settle_end
        assert settle_end["guest_ticks"] - settle_start["guest_ticks"] >= DOSBOX_SPEED_SETTLE_MS

        start_tic = settle_tic
        post_settle_acquisition = dict(
            requested_target_tic=target_start_tic,
            start_tic=settle_tic,
            end_tic=settle_tic,
            source_site_hits=0,
            ordinary_speed=True,
            endpoint="not_requested",
            elapsed_pic_guest_ms=0)
        if target_start_tic is not None:
            assert settle_tic <= target_start_tic, (
                "DOSBox-X passed the requested post-settle Doom tic before acquisition: "
                f"settle={settle_tic}, target={target_start_tic}")
            acquisition_start_clock = session_call("execution.timing")["guest_ticks"]
            acquisition_deadline = min(
                total_deadline,
                time.monotonic() + DOSBOX_WINDOW_DEADLINE_SECONDS)
            previous_tic = None
            hits = 0
            tic = settle_tic
            while True:
                if time.monotonic() >= acquisition_deadline:
                    raise TimeoutError(
                        f"DOSBox-X did not reach source-bound Doom tic {target_start_tic} "
                        "after ordinary-speed settling")
                point = session_call("breakpoints.create", dict(
                    kind="execution", once=True, address=address))
                operation = session_call("execution.continue")
                wait_for_tic(point["breakpoint_id"], operation["operation_id"],
                             deadline=acquisition_deadline)
                tic = tic_at_stop()
                hits += 1
                assert tic <= target_start_tic, (
                    "DOSBox-X passed the requested source-bound start tic: "
                    f"observed={tic}, target={target_start_tic}")
                if previous_tic is not None:
                    assert tic > previous_tic, (
                        "Doom leveltime did not advance between ordinary-speed "
                        f"source-site hits: {previous_tic} -> {tic}")
                previous_tic = tic
                if tic == target_start_tic:
                    break
                if hits > target_start_tic - settle_tic + 3:
                    raise AssertionError(
                        "DOSBox-X exceeded the bounded source-site hit count while "
                        "acquiring the requested start tic")
            start_tic = tic
            acquisition_end_clock = session_call("execution.timing")["guest_ticks"]
            post_settle_acquisition = dict(
                requested_target_tic=target_start_tic,
                start_tic=settle_tic,
                end_tic=start_tic,
                source_site_hits=hits,
                ordinary_speed=True,
                endpoint="source-site pre-increment breakpoint",
                elapsed_pic_guest_ms=(acquisition_end_clock
                                      - acquisition_start_clock),
                start_pic_guest_ticks=acquisition_start_clock,
                end_pic_guest_ticks=acquisition_end_clock)
        start_bda = int.from_bytes(
            dosbox_read(view, "physical", BDA_TICKS_PHYSICAL, 4), "little")
        start_clock = session_call("execution.timing")["guest_ticks"]
        operation = session_call("execution.continue")
        window_deadline = min(total_deadline,
                              time.monotonic() + DOSBOX_WINDOW_DEADLINE_SECONDS)
        while time.monotonic() < window_deadline:
            timing = session_call("execution.timing")
            if timing["guest_ticks"] - start_clock >= budget_ms:
                break
            pending = session_call("execution.wait", dict(
                operation_id=operation["operation_id"], timeout_ms=poll_wait_ms),
                timeout_ms=1_000)
            assert pending.get("running"), pending
        else:
            raise TimeoutError(
                f"DOSBox-X did not reach its {budget_ms} ms guest-time budget")

        pause = session_call("execution.pause")
        stopped = session_call("execution.wait", dict(
            operation_id=pause["operation_id"], timeout_ms=3_000))
        assert not stopped.get("running"), stopped
        assert stopped["stop_reason"]["kind"] == "pause", stopped
        end_bda = int.from_bytes(
            dosbox_read(view, "physical", BDA_TICKS_PHYSICAL, 4), "little")
        end_clock = session_call("execution.timing")["guest_ticks"]
        end_tic = tic_at_stop()
        assert end_tic > start_tic, end_tic
        (stage / "dosbox-window-endpoint.json").write_text(json.dumps(dict(
            source_sha256=PINS["DOOM.EXE"], start_tic=start_tic,
            end_tic=end_tic, start_bda=start_bda, end_bda=end_bda,
            start_guest_ticks=start_clock, end_guest_ticks=end_clock,
            requested_guest_ms=budget_ms,
            observed_overshoot_ms=end_clock - start_clock - budget_ms,
            poll_wait_ms=poll_wait_ms,
            maximum_accepted_overshoot_ms=max_window_overshoot_ms,
            endpoint_atomic=False), sort_keys=True, indent=2) + "\n")
        assert budget_ms <= end_clock - start_clock <= budget_ms + max_window_overshoot_ms, (
            start_clock, end_clock)
        result = dict(
            backend="dosbox", start_tic=start_tic, end_tic=end_tic,
            acquisition_landmark_tic=START_TIC,
            leveltime_delta=end_tic - start_tic,
            source_sha256=PINS["DOOM.EXE"],
            site=dict(object_index=1, object_offset=CODE_OFFSET,
                      target_object=3, target_offset=DATA_OFFSET,
                      runtime_pc=pc, runtime_counter=counter,
                      instruction_bytes=site["runtime_bytes"]),
            bda=dict(address_physical=hex(BDA_TICKS_PHYSICAL),
                     start=start_bda, end=end_bda,
                     delta=(end_bda - start_bda) % BDA_TICKS_PER_DAY,
                     tick_period_ns=54_925_493),
            engine_clock=dict(unit="PIC_Ticks_milliseconds",
                              start=start_clock, end=end_clock,
                              delta=end_clock - start_clock),
            guest_time_budget=dict(unit="milliseconds", requested=budget_ms,
                                   elapsed=end_clock - start_clock,
                                   overshoot=end_clock - start_clock - budget_ms,
                                   poll_wait_ms=poll_wait_ms,
                                   max_overshoot_ms=max_window_overshoot_ms,
                                   endpoint_atomic=False),
            pre_window_acquisition=dict(
                initial_fast_forward=initial_timing["fast_forward"],
                acquisition_fast_forward=acquisition_start["fast_forward"],
                transition_fast_forward=speed_transition["fast_forward"],
                transition_guest_ticks=speed_transition["guest_ticks"],
                settle_requested_ms=DOSBOX_SPEED_SETTLE_MS,
                settle_start_guest_ticks=settle_start["guest_ticks"],
                settle_end_guest_ticks=settle_end["guest_ticks"],
                settle_elapsed_guest_ticks=(settle_end["guest_ticks"]
                                            - settle_start["guest_ticks"]),
                settle_start_tic=START_TIC, settle_end_tic=settle_tic),
            post_settle_target_acquisition=post_settle_acquisition,
            end_stop=stopped["stop_reason"]["kind"],
            intermediate_execution_breakpoints=0,
            uninterrupted_guest_continues=1, audio_capture=False,
            runtime_sha256=_sha(executable),
            source_image_sha256=_sha(game / "DOOM.EXE"))
    finally:
        rpc.close()
    assert owner.poll() is not None and owner.returncode == 0
    result["owner_reaped"] = True
    result["owner_returncode"] = owner.returncode
    assert _source_hashes(game) == PINS
    return result


def test_paired_doom_e1m1_timing_uses_guest_bda_clock(tmp_path):
    if os.environ.get("FDISBULL_REQUIRE_DOOM_TIMING_BDA_PAIRED") != "1":
        pytest.skip("Set FDISBULL_REQUIRE_DOOM_TIMING_BDA_PAIRED=1 with pinned private runtimes")
    source_value = os.environ.get("FDISBULL_DOOM_LE_SOURCE")
    dosbox_value = os.environ.get("FDISBULL_DOSBOX")
    missing = [name for name, value in (("FDISBULL_DOOM_LE_SOURCE", source_value),
                                        ("FDISBULL_DOSBOX", dosbox_value)) if not value]
    if missing:
        pytest.fail("Paired Doom BDA timing inputs missing: " + ", ".join(missing))
    source = Path(source_value).expanduser().resolve(strict=True)
    dosbox = Path(dosbox_value).expanduser().resolve(strict=True)
    assert source.is_dir() and dosbox.is_file() and os.access(dosbox, os.X_OK)
    assert _source_hashes(source) == PINS
    qemu_runtime = qemu_runtime_inputs()
    assert Path(qemu_runtime["firmware"]).is_dir()
    assert _sha(qemu_runtime["boot_image"])
    assert _sha(qemu_runtime["executable"])
    assert _sha(dosbox)

    dosbox_result = _dosbox_measure(tmp_path, source, dosbox)
    qemu_result = _qemu_measure(tmp_path, source, qemu_runtime,
                                dosbox_result["start_tic"])
    assert dosbox_result["start_tic"] >= START_TIC
    assert qemu_result["start_tic"] == dosbox_result["start_tic"]
    assert dosbox_result["owner_reaped"] and qemu_result["owner_reaped"]
    assert dosbox_result["intermediate_execution_breakpoints"] == qemu_result["intermediate_execution_breakpoints"] == 0
    assert dosbox_result["uninterrupted_guest_continues"] == qemu_result["uninterrupted_guest_continues"] == 1
    assert dosbox_result["audio_capture"] is qemu_result["audio_capture"] is False
    assert _source_hashes(source) == PINS

    receipt = dict(
        format="fdisbull-paired-doom-bda-timing-control-1",
        scope="original Doom E1M1 progress during one uninterrupted 1800 ms guest-time budget per backend, both starting at the same post-settle pre-increment leveltime; DOSBox-X acquires tic64 with fast-forward, then records ordinary-speed settling before its measured start",
        source_sha256=PINS["DOOM.EXE"],
        private_input_sha256=PINS,
        native_runtime_sha256=dict(dosbox=dosbox_result["runtime_sha256"],
                                   qemu=qemu_result["runtime_sha256"]),
        interval=dict(acquisition_landmark_kind="pre-increment leveltime",
                       acquisition_landmark_value=START_TIC,
                       measured_start_tic=dosbox_result["start_tic"],
                       requested_guest_ms=BUDGET_MS,
                       bda_ticks_physical=hex(BDA_TICKS_PHYSICAL),
                       bda_tick_period_ns=54_925_493),
        engines=dict(dosbox=dosbox_result, qemu=qemu_result),
        interpretation_limitations=[
            "The requested interval is 1800 ms in each backend's own guest-time domain; observed overshoot is retained.",
            "DOSBox-X uses fast-forward only for pre-window acquisition, then settles for a recorded 250 PIC guest ticks at ordinary speed; QEMU acquires the same post-settle pre-increment tic without a speed-mode switch.",
            "BDA ticks have approximately 54.9 ms resolution and boundary-phase uncertainty.",
            "Engine clocks are reported in their native units and are not treated as a shared clock.",
            "The test compares one bounded interval; it does not qualify broader gameplay or audio parity.",
            "Commercial media, screenshots, audio, project databases and VM states remain private.",
        ])
    (tmp_path / "paired-bda-timing.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n")
