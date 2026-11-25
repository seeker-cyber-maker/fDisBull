"""Measure a shared original-Doom leveltime interval on QEMU and DOSBox-X.

The two engines use different guest clocks and audio capture paths.  This test
records each engine's own elapsed-time and capture-frontier units; it does not
assert timing equality or sample alignment.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import time

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.le import load_runtime_le_carrier
from fdisbull.project import Project
from support.doom_le_dosbox import CODE_OFFSET, DATA_OFFSET, placement, read as dosbox_read, reach_site
from support.doom_le_qemu import PINS, runtime_inputs, stage_game


START_TIC = 64
END_TIC = 128
MAX_AUDIO_FRAMES = 160_000
QEMU_GAME_ARGUMENTS = "-warp 1 1 -skill 2 -nomonsters -config D:\\DEFAULT.CFG"
DOSBOX_GAME_ARGUMENTS = "-warp 1 1 -skill 2 -nomonsters -config DEFAULT.CFG"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_hashes(source):
    return {name: _sha(source / name) for name in PINS}


def _directory_sha(path):
    root = Path(path)
    digest = hashlib.sha256()
    for item in sorted(root.rglob("*"), key=lambda value: value.relative_to(root).as_posix()):
        relative = item.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "little"))
        digest.update(relative)
        if item.is_symlink():
            target = item.readlink().as_posix().encode("utf-8")
            digest.update(b"L" + len(target).to_bytes(4, "little") + target)
        elif item.is_file():
            digest.update(b"F" + bytes.fromhex(_sha(item)))
    return digest.hexdigest()


def _read_qemu_word(debug, address):
    return bytes.fromhex(debug.memory(address, length=4, space="virtual")["hex"])


def _qemu_rebind_at_endpoint(debug, pc, counter, expected_tic):
    """Reacquire source identity at a stopped tic without advancing the guest."""
    before_registers = debug.registers()
    before_pc = int(before_registers["linear_pc"], 0)
    before_tic = int.from_bytes(_read_qemu_word(debug, counter), "little")
    assert before_pc == pc and before_tic == expected_tic, (before_pc, before_tic)
    admitted = debug.dos_source_admit(
        expected_source_sha256=PINS["DOOM.EXE"], timeout_ms=20_000)
    assert admitted["status"] == "admitted", admitted
    binding = debug.dos_source_bind(
        expected_source_sha256=PINS["DOOM.EXE"], timeout_ms=20_000)
    after_registers = debug.registers()
    after_pc = int(after_registers["linear_pc"], 0)
    after_tic = int.from_bytes(_read_qemu_word(debug, counter), "little")
    assert binding["live"] and binding["source_sha256"] == PINS["DOOM.EXE"], binding
    assert after_pc == before_pc and after_tic == before_tic == expected_tic, (
        before_pc, after_pc, before_tic, after_tic)
    return binding


def _qemu_boot_to_protected(debug):
    """Qualify and bind source in small virtual-time increments near startup."""
    from fdisbull.qemu_dos_le_match import SourceMatchError

    for _ in range(1600):  # At most 40 virtual seconds; no guest input is sent.
        stop = debug.clock_advance(25_000_000, timeout_ms=10_000)
        regs = debug.registers()
        state = regs["address_state"]
        assert stop["outcome"] not in ("guest_exit", "guest_tsr", "exited"), stop
        if (regs["cpu_mode"] != "protected" or state["code_bits"] != 32
                or state["paging"] is not False or state["a20"] is not True):
            continue
        try:
            admitted = debug.dos_source_admit(
                expected_source_sha256=PINS["DOOM.EXE"], timeout_ms=20_000)
        except SourceMatchError as exc:
            if str(exc) != "ambiguous source placement within one object":
                raise
            continue
        if admitted["status"] == "admitted":
            binding = debug.dos_source_bind(
                expected_source_sha256=PINS["DOOM.EXE"], timeout_ms=20_000)
            if binding["live"]:
                return binding
    raise AssertionError("Doom did not reach an admitted protected-mode source boundary")


def _qemu_site(project, debug, output):
    binding = _qemu_boot_to_protected(debug)
    project.debug_export(binding["artifact"]["artifact"], output)
    recipe = json.loads(output.read_bytes())["recipe"]
    bases = {row["object_index"]: int(row["runtime_base"], 0)
             if isinstance(row["runtime_base"], str) else row["runtime_base"]
             for row in recipe["placements"]}
    pc, counter = bases[1] + CODE_OFFSET, bases[3] + DATA_OFFSET
    assert binding["live"] and pc > 0 and counter > 0
    code = bytes.fromhex(debug.memory(pc, length=6, space="virtual")["hex"])
    assert code[:2] == b"\xff\x05"
    assert int.from_bytes(code[2:], "little") == counter
    return pc, counter, code


def _qemu_wait_tic(debug, pc, counter, breakpoint_id, expected):
    for _ in range(END_TIC + 8):
        stopped = debug.run(timeout_ms=30_000)
        assert stopped["outcome"] == "breakpoint", stopped
        assert breakpoint_id in stopped["session"]["stop_reason"]["breakpoint_ids"], stopped
        debug.dos_source_binding(refresh=True, timeout_ms=10_000)
        code = bytes.fromhex(debug.memory(pc, length=6, space="virtual")["hex"])
        assert code[:2] == b"\xff\x05" and int.from_bytes(code[2:], "little") == counter
        tick = int.from_bytes(_read_qemu_word(debug, counter), "little")
        assert tick <= expected, (tick, expected)
        if tick == expected:
            return tick, code, breakpoint_id
        debug.delete_breakpoint(breakpoint_id)
        stepped = debug.step(count=1, timeout_ms=10_000)
        assert int(debug.registers()["linear_pc"], 0) != pc, (stepped, debug.registers())
        breakpoint_id = debug.breakpoint(pc)["breakpoint_id"]
    raise AssertionError(f"QEMU did not reach Doom leveltime {expected}")


def _qemu_advance_from_landmark(debug, pc, counter, breakpoint_id, tick):
    """Execute the stopped INC once before resuming toward the next landmark."""
    debug.delete_breakpoint(breakpoint_id)
    stepped = debug.step(count=1, timeout_ms=10_000)
    regs = debug.registers()
    assert int(regs["linear_pc"], 0) != pc, (stepped, regs)
    observed = int.from_bytes(_read_qemu_word(debug, counter), "little")
    assert observed == tick + 1, (observed, tick)
    return debug.breakpoint(pc)["breakpoint_id"]


def _qemu_measure(tmp_path, source, qemu_runtime):
    stage = tmp_path / "qemu"
    stage.mkdir()
    game = stage_game(stage, source)
    owners = []
    database = stage / "doom.fdb"
    qemu_runtime_options = dict(
        backend="qemu-dos", dos_directory=str(game),
        dos_boot_image=str(qemu_runtime["boot_image"]),
        dos_mcopy=str(qemu_runtime["mcopy"]), qemu_transport="pipe",
        qemu_firmware=qemu_runtime["firmware"], qemu_audio="sb16-opl",
        qemu_retrace="precise", qemu_clock="virtual",
        qemu_checkpoint_tool=str(qemu_runtime["checkpoint_tool"]),
        dos_arguments=QEMU_GAME_ARGUMENTS, boot_timeout_ms=35_000)
    with Project.create(database, game / "DOOM.EXE", image="mz") as project:
        with project.debugger(qemu_runtime["executable"], game,
                              _on_spawn=owners.append, **qemu_runtime_options) as debug:
            pc, counter, code = _qemu_site(project, debug, stage / "source-binding.json")
            breakpoint_id = debug.breakpoint(pc)["breakpoint_id"]
            first, _, breakpoint_id = _qemu_wait_tic(
                debug, pc, counter, breakpoint_id, START_TIC)
            binding = _qemu_rebind_at_endpoint(debug, pc, counter, START_TIC)
            clock_start = debug.clock_observe()
            audio_start = debug.audio_start(
                max_frames=MAX_AUDIO_FRAMES, capture_format="s16-stereo")
            assert audio_start["sample_format"] == dict(
                rate=32_000, channels=2, sample_format="s16", bytes_per_frame=4)
            audio_at_start = debug.audio_observe()
            breakpoint_id = _qemu_advance_from_landmark(
                debug, pc, counter, breakpoint_id, START_TIC)
            second, _, _ = _qemu_wait_tic(
                debug, pc, counter, breakpoint_id, END_TIC)
            end_binding = _qemu_rebind_at_endpoint(debug, pc, counter, END_TIC)
            clock_end = debug.clock_observe()
            audio_at_end = debug.audio_observe()
            audio_stop = debug.audio_stop()
            artifact = debug.capture_audio("leveltime-window.wav")
            assert audio_stop["dropped_frames"] == 0
            assert audio_at_end["frames"] > audio_at_start["frames"]
            assert audio_stop["frames"] == audio_at_end["frames"]
            result = dict(
                backend="qemu-dos", endpoint_tics=[first, second],
                site=dict(object_index=1, object_offset=CODE_OFFSET,
                          target_object=3, target_offset=DATA_OFFSET,
                          runtime_pc=pc, runtime_counter=counter,
                          instruction_bytes=code.hex()),
                elapsed=dict(unit="virtual_nanoseconds",
                             start=clock_start["virtual_ns"], end=clock_end["virtual_ns"],
                             delta=clock_end["virtual_ns"] - clock_start["virtual_ns"]),
                audio=dict(capture_format=audio_stop["sample_format"],
                           frontier_unit="complete_pcm_frames",
                           start_frames=audio_at_start["frames"],
                           end_frames=audio_at_end["frames"],
                           delta_frames=audio_at_end["frames"] - audio_at_start["frames"],
                           dropped_frames=audio_stop["dropped_frames"],
                           callback_chunks=audio_stop["native"]["chunks"],
                           captured_artifact_sha256=artifact["sha256"]),
                producer_sha256=_sha(qemu_runtime["executable"]),
                boot_image_sha256=_sha(qemu_runtime["boot_image"]),
                mcopy_sha256=_sha(qemu_runtime["mcopy"]),
                checkpoint_tool_sha256=_sha(qemu_runtime["checkpoint_tool"]),
                firmware_tree_sha256=_directory_sha(qemu_runtime["firmware"]),
                source_sha256=PINS["DOOM.EXE"],
                binding_id=binding["binding_id"], capture_epoch=binding["capture_epoch"])
            result["end_binding_id"] = end_binding["binding_id"]
            result["end_capture_epoch"] = end_binding["capture_epoch"]
    assert owners and all(owner.poll() is not None for owner in owners)
    result["owner_reaped"] = True
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


def _dosbox_filesize(capture_dir):
    files = sorted(Path(capture_dir).glob("*.wav"))
    return sum(path.stat().st_size for path in files), len(files)


def _dosbox_measure(tmp_path, source, dosbox_executable):
    stage = tmp_path / "dosbox"
    game = stage / "game"
    game.mkdir(parents=True)
    for name in PINS:
        original = source / name
        assert _sha(original) == PINS[name]
        (game / name).write_bytes(original.read_bytes())
    assert _source_hashes(game) == PINS
    image = load_runtime_le_carrier((game / "DOOM.EXE").read_bytes())
    wrapper = stage / "dosbox-capture-wave"
    wrapper.write_text(
        "#!/bin/sh\nexec " + shlex.quote(str(dosbox_executable))
        + ' "$@" -c "ALIAS CAPW=DX-CAPTURE /A /-D"\n')
    wrapper.chmod(0o700)
    rpc = DOSBoxRPC(wrapper, game)
    owner = rpc.process
    capture_dir = Path(rpc.temporary.name) / "capture"
    try:
        started = rpc.call("session.start", dict(
            target=dict(command="CAPW", arguments=["DOOM.EXE", *DOSBOX_GAME_ARGUMENTS.split()]),
            mounts=[dict(drive="C", host_path=str(game))], break_at="entry"))
        session_id = started["session_id"]
        deadline = time.monotonic() + 180
        last_tic = None

        def call(method, parameters=None):
            assert time.monotonic() < deadline, (
                f"Finite DOSBox Doom timing phase expired at leveltime {last_tic}")
            return rpc.call(method, dict(session_id=session_id, **(parameters or {})))

        view = _DOSBoxSessionView(call)
        registers = call("state.get_registers")
        assert registers["cpu_mode"] == "real"
        # Reach the first exact landmark promptly; measure only after switching
        # to the ordinary DOSBox-X rate at the stopped pre-increment boundary.
        call("execution.timing", dict(fast_forward=True))
        # Existing DOSBox-X oracle locates the protected LE INC and leaves the
        # guest stopped on its first hit.
        reach_site(view, image)
        site = placement(view, image)
        assert site and site["runtime_address"] == site["cs_base"] + site["ip"]
        pc = site["runtime_address"]
        counter = site["runtime_target"]
        assert site["runtime_bytes"] == "ff05" + counter.to_bytes(4, "little").hex()
        address = dict(space="segmented", segment=f"0x{site['cs']:04x}",
                       offset=f"0x{site['runtime_address'] - site['cs_base']:08x}")

        def step_and_wait(expected, *, step_first=True):
            nonlocal last_tic
            for iteration in range(END_TIC + 8):
                if step_first or iteration:
                    step = call("execution.step", dict(mode="into"))
                    assert step["stop_reason"]["kind"] == "step", step
                point = call("breakpoints.create", dict(kind="execution", once=True,
                                 address=address))
                operation = call("execution.continue")
                while True:
                    stopped = call("execution.wait", dict(
                        operation_id=operation["operation_id"], timeout_ms=100))
                    if not stopped.get("running", False):
                        break
                assert stopped["state"] == "stopped"
                assert stopped["stop_reason"]["kind"] == "breakpoint"
                assert stopped["stop_reason"]["breakpoint_id"] == point["breakpoint_id"]
                current = placement(view, image)
                assert current and current["runtime_target"] == counter
                tick = int.from_bytes(dosbox_read(view, "linear", counter, 4), "little")
                last_tic = tick
                assert tick <= expected, (tick, expected)
                if tick == expected:
                    return tick, current
            raise AssertionError(f"DOSBox-X did not reach Doom leveltime {expected}")

        # The source helper already stopped immediately before the first INC.
        first = int.from_bytes(dosbox_read(view, "linear", counter, 4), "little")
        last_tic = first
        while first < START_TIC:
            first, site = step_and_wait(START_TIC)
        assert first == START_TIC
        call("execution.timing", dict(fast_forward=False))
        clock_start = call("execution.timing")
        file_start, files_start = _dosbox_filesize(capture_dir)
        # Allow most of the normal-speed window to run without per-tic debugger
        # stops. Stopping on every INC changes DOSBox-X's observed PIC duration.
        step = call("execution.step", dict(mode="into"))
        assert step["stop_reason"]["kind"] == "step", step
        operation = call("execution.continue")
        sparse_target = clock_start["guest_ticks"] + 1500
        while call("execution.timing")["guest_ticks"] < sparse_target:
            pending = call("execution.wait", dict(
                operation_id=operation["operation_id"], timeout_ms=100))
            assert pending.get("running"), pending
        pause = call("execution.pause")
        paused = call("execution.wait", dict(
            operation_id=pause["operation_id"], timeout_ms=3000))
        assert paused["stop_reason"]["kind"] == "pause", paused
        sparse_tic = int.from_bytes(dosbox_read(view, "linear", counter, 4), "little")
        last_tic = sparse_tic
        assert START_TIC < sparse_tic < END_TIC, sparse_tic
        sparse_points = [dict(leveltime=sparse_tic, target_guest_ticks=sparse_target)]
        for _ in range(8):
            if sparse_tic >= END_TIC - 4:
                break
            # Approach the last few tics with conservative running intervals;
            # avoid both a long series of debugger stops and crossing 128.
            interval = min(440, max(40, (END_TIC - sparse_tic - 3) * 20))
            sparse_target = call("execution.timing")["guest_ticks"] + interval
            operation = call("execution.continue")
            while call("execution.timing")["guest_ticks"] < sparse_target:
                pending = call("execution.wait", dict(
                    operation_id=operation["operation_id"], timeout_ms=100))
                assert pending.get("running"), pending
            pause = call("execution.pause")
            paused = call("execution.wait", dict(
                operation_id=pause["operation_id"], timeout_ms=3000))
            assert paused["stop_reason"]["kind"] == "pause", paused
            next_tic = int.from_bytes(dosbox_read(view, "linear", counter, 4), "little")
            assert sparse_tic <= next_tic < END_TIC, (sparse_tic, next_tic)
            sparse_tic = last_tic = next_tic
            sparse_points.append(dict(leveltime=sparse_tic, target_guest_ticks=sparse_target))
        if sparse_tic < END_TIC - 4:
            raise AssertionError(f"Sparse DOSBox timing approach stalled at {sparse_tic}")
        second, _ = step_and_wait(END_TIC, step_first=False)
        clock_end = call("execution.timing")
        file_end, files_end = _dosbox_filesize(capture_dir)
        assert files_start >= 1 and files_end >= files_start
        assert file_end > file_start, "DOSBox-X WAV flush frontier did not advance"
        result = dict(
            backend="dosbox", endpoint_tics=[first, second],
            site=dict(object_index=1, object_offset=CODE_OFFSET,
                      target_object=3, target_offset=DATA_OFFSET,
                      runtime_pc=pc, runtime_counter=counter,
                      instruction_bytes=site["runtime_bytes"]),
            elapsed=dict(unit="dosbox_pic_guest_ticks",
                         start=clock_start["guest_ticks"], end=clock_end["guest_ticks"],
                         delta=clock_end["guest_ticks"] - clock_start["guest_ticks"]),
            sparse_pauses=sparse_points,
            audio=dict(capture_format=dict(rate=48_000, channels=2,
                                           sample_format="s16", bytes_per_frame=4),
                       frontier_unit="bytes_in_live_wav_writer",
                       start_bytes=file_start, end_bytes=file_end,
                       delta_bytes=file_end - file_start,
                       wav_files_at_start=files_start, wav_files_at_end=files_end,
                       finalized=False,
                       limitation="DOSBox-X file size includes flushed bytes only; buffered samples are unknown"),
            producer_sha256=_sha(dosbox_executable), source_sha256=PINS["DOOM.EXE"])
    finally:
        rpc.close()
    assert owner.poll() is not None and owner.returncode == 0
    result["owner_reaped"] = True
    assert _source_hashes(game) == PINS
    return result


def test_paired_doom_e1m1_leveltime_64_to_128_timing_and_audio_frontiers(tmp_path):
    if os.environ.get("FDISBULL_REQUIRE_DOOM_LEVELTIME_PAIRED") != "1":
        pytest.skip("Set FDISBULL_REQUIRE_DOOM_LEVELTIME_PAIRED=1 with pinned native runtimes")
    source_value = os.environ.get("FDISBULL_DOOM_LE_SOURCE")
    dosbox_value = os.environ.get("FDISBULL_DOSBOX")
    missing = [name for name, value in (("FDISBULL_DOOM_LE_SOURCE", source_value),
                                        ("FDISBULL_DOSBOX", dosbox_value)) if not value]
    if missing:
        pytest.fail("Paired Doom leveltime inputs missing: " + ", ".join(missing))
    source = Path(source_value).expanduser().resolve(strict=True)
    dosbox_executable = Path(dosbox_value).expanduser().resolve(strict=True)
    assert source.is_dir() and dosbox_executable.is_file() and os.access(dosbox_executable, os.X_OK)
    assert _source_hashes(source) == PINS
    qemu_runtime = runtime_inputs()
    assert Path(qemu_runtime["firmware"]).is_dir()
    assert _sha(qemu_runtime["boot_image"])
    assert _sha(qemu_runtime["executable"])
    assert _sha(dosbox_executable)

    qemu = _qemu_measure(tmp_path, source, qemu_runtime)
    dosbox = _dosbox_measure(tmp_path, source, dosbox_executable)
    assert qemu["endpoint_tics"] == dosbox["endpoint_tics"] == [START_TIC, END_TIC]
    assert qemu["source_sha256"] == dosbox["source_sha256"] == PINS["DOOM.EXE"]
    assert qemu["owner_reaped"] and dosbox["owner_reaped"]
    assert _source_hashes(source) == PINS
    receipt = dict(
        format="fdisbull-paired-doom-leveltime-window-1",
        workload="original Doom E1M1, -nomonsters, pinned private inputs",
        inputs=PINS,
        config=dict(
            sha256=PINS["DEFAULT.CFG"],
            qemu_argument="-config D:\\DEFAULT.CFG",
            dosbox_argument="-config DEFAULT.CFG",
            note="QEMU selects D: explicitly; DOSBox-X resolves the pinned file in its mounted game directory."),
        endpoints=dict(kind="pre-increment leveltime boundaries", values=[START_TIC, END_TIC],
                       code_site=dict(object_index=1, offset=CODE_OFFSET),
                       counter=dict(object_index=3, offset=DATA_OFFSET)),
        engines=dict(qemu=qemu, dosbox=dosbox),
        comparison_limitations=[
            "QEMU virtual nanoseconds and DOSBox-X PIC guest ticks are distinct clock units.",
            "QEMU capture is 32 kHz S16 stereo complete PCM frames; DOSBox-X capture is 48 kHz S16 stereo flushed WAV bytes.",
            "DOSBox-X live WAV size excludes buffered samples; QEMU callback timestamps identify delivered chunks, not individual sample onsets.",
            "Matched leveltime bounds align game progress only; no elapsed-time equality, sample alignment, gain or waveform parity is asserted.",
        ])
    (tmp_path / "verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
