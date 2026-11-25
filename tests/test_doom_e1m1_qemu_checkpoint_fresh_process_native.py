"""Opt-in ordinary Doom E1M1 owned-machine restore in a fresh Python host.

Private game inputs, project state, checkpoint bytes and screenshots stay in
pytest's temporary directory. This proves one QEMU checkpoint continuation;
it does not claim DOSBox-X, full gameplay, timing, or engine parity.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest
from PIL import Image

from fdisbull.project import Project
from support.doom_le_qemu import CODE_OFFSET, DATA_OFFSET, PINS, qualified_stop
from support.doom_gameplay import (
    DOOM_ARGUMENTS,
    advance,
    capture_statusbar,
    decode_ammo_from_wad,
    digest,
    runtime_inputs,
    stage_game,
)


LEVELTIME_TARGET_OFFSET = 40
STACK_SAMPLE_BYTES = 64


def _normalized_frame_sha256(path: Path) -> str:
    with Image.open(path) as image:
        normalized = image.convert("RGB").resize((320, 200), Image.Resampling.NEAREST)
        return hashlib.sha256(normalized.tobytes()).hexdigest()


def _clock_receipt(result):
    budget = result["clock_budget"]
    return {key: budget[key] for key in (
        "clock_domain", "epoch", "requested_delta_ns", "start_ns", "deadline_ns",
        "fired_ns", "stopped_ns", "elapsed_ns", "deadline_reached", "overshoot_ns")}


def _input_semantics(receipt):
    press = receipt["press"]
    return dict(clock_domain=receipt["clock_domain"], start_ns=receipt["start_ns"],
        deadline_ns=receipt["deadline_ns"], edge_count=receipt["edge_count"],
        key=press["key"], modifiers=press["modifiers"], hold_ms=press["hold_ms"],
        gap_ms=press["gap_ms"], gap_applied=press["gap_applied"],
        steps=[{key: step[key] for key in ("key", "down", "delay_ns", "deadline_ns")
                if key in step} for step in press["steps"]])


def _cpu_differences(expected, actual, fields):
    result = {}
    for field in fields:
        before, after = expected[field], actual[field]
        if before == after:
            continue
        if field == "registers":
            keys = sorted(set(before) | set(after))
            result[field] = {key: dict(origin=before.get(key), restored=after.get(key))
                             for key in keys if before.get(key) != after.get(key)}
        elif field == "address_state":
            keys = sorted(set(before) | set(after))
            result[field] = {key: dict(origin=before.get(key), restored=after.get(key))
                             for key in keys if before.get(key) != after.get(key)}
        else:
            result[field] = dict(origin=before, restored=after)
    return result


def _leveltime_addresses(project, debug, binding, directory):
    exported = Path(directory) / f"leveltime-source-binding-{binding['binding_id']}.json"
    project.debug_export(binding["artifact"]["artifact"], exported)
    recipe = json.loads(exported.read_bytes())["recipe"]
    bases = {row["object_index"]: (int(row["runtime_base"], 0)
            if isinstance(row["runtime_base"], str) else row["runtime_base"])
             for row in recipe["placements"]}
    pc, counter = bases[1] + CODE_OFFSET, bases[3] + DATA_OFFSET
    code = bytes.fromhex(debug.memory(pc, length=6, space="virtual")["hex"])
    assert code[:2] == b"\xff\x05" and int.from_bytes(code[2:], "little") == counter
    return pc, counter, code


def _leveltime(debug, counter):
    return int.from_bytes(bytes.fromhex(debug.memory(
        counter, length=4, space="virtual")["hex"]), "little")


def _reach_leveltime_preincrement(debug, pc, counter, expected):
    code = bytes.fromhex(debug.memory(pc, length=6, space="virtual")["hex"])
    assert code[:2] == b"\xff\x05" and int.from_bytes(code[2:], "little") == counter
    breakpoint_id = debug.breakpoint(pc)["breakpoint_id"]
    for _ in range(48):
        stopped = debug.run(timeout_ms=30000)
        assert stopped["outcome"] == "breakpoint", stopped
        assert breakpoint_id in stopped["session"]["stop_reason"]["breakpoint_ids"], stopped
        code = bytes.fromhex(debug.memory(pc, length=6, space="virtual")["hex"])
        assert code[:2] == b"\xff\x05" and int.from_bytes(code[2:], "little") == counter
        tick = _leveltime(debug, counter)
        assert tick <= expected, (tick, expected)
        if tick == expected:
            return code
        debug.delete_breakpoint(breakpoint_id)
        stepped = debug.step(count=1, timeout_ms=10000)
        assert int(debug.registers()["linear_pc"], 0) != pc, (stepped, debug.registers())
        breakpoint_id = debug.breakpoint(pc)["breakpoint_id"]
    raise AssertionError(f"Doom did not reach pre-increment leveltime {expected}")


def _stack_sample(debug, registers):
    cpu = registers["registers"]
    state = registers["address_state"]
    stack_bits = int(state["stack_bits"])
    stack_mask = (1 << stack_bits) - 1
    stack_offset = int(cpu["rsp"], 0) & stack_mask
    stack_base = int(state["segments"]["ss"]["base"], 0)
    linear = stack_base + stack_offset
    data = bytes.fromhex(debug.memory(linear, length=STACK_SAMPLE_BYTES, space="virtual")["hex"])
    assert len(data) == STACK_SAMPLE_BYTES
    return dict(linear=hex(linear), length=len(data), hex=data.hex(),
                sha256=hashlib.sha256(data).hexdigest())


def _capture_leveltime_landmark(project, debug, game, directory, pc, counter, target, label):
    code = _reach_leveltime_preincrement(debug, pc, counter, target)
    binding = debug.dos_source_bind(expected_source_sha256=PINS["DOOM.EXE"], timeout_ms=20000)
    assert binding["live"] and binding["last_observation"]["qualified"] is True
    registers = debug.registers()
    assert int(registers["linear_pc"], 0) == pc
    assert _leveltime(debug, counter) == target
    assert bytes.fromhex(debug.memory(pc, length=6, space="virtual")["hex"]) == code
    frame = capture_statusbar(project, debug, Path(directory), label)
    ammo = decode_ammo_from_wad(game / "DOOM.WAD", frame["statusbar"])
    stack = _stack_sample(debug, registers)
    image_path = Path(directory) / (label + ".png")
    return dict(leveltime=target, pc=hex(pc), counter=hex(counter), code_hex=code.hex(),
        source_location=binding["last_observation"]["source_location"],
        source_instruction_sha256=binding["last_observation"]["instruction_sha256"],
        cpu=registers, stack=stack, frame_png_sha256=frame["sha256"],
        normalized_frame_sha256=_normalized_frame_sha256(image_path), ammo=ammo["value"])


def _runtime():
    if os.environ.get("FDISBULL_REQUIRE_DOOM_E1M1_FRESH_CHECKPOINT") != "1":
        pytest.skip("Set FDISBULL_REQUIRE_DOOM_E1M1_FRESH_CHECKPOINT=1 for private Doom inputs")
    runtime = runtime_inputs()
    checkpoint_tool = os.environ.get("FDISBULL_QEMU_IMG")
    if not checkpoint_tool:
        pytest.fail("FDISBULL_QEMU_IMG is required for the QEMU owned-machine checkpoint")
    tool = Path(checkpoint_tool).expanduser().resolve(strict=True)
    assert tool.is_file() and os.access(tool, os.X_OK)
    runtime["checkpoint_tool"] = tool
    return runtime


def _open_qemu(project, runtime, game, *, on_spawn=None):
    return project.debugger(
        str(runtime["qemu"]), game, backend="qemu-dos",
        dos_boot_image=str(runtime["boot"]), dos_mcopy=str(runtime["mcopy"]),
        dos_directory=str(game), dos_startup_batch="FDAUTO.BAT",
        qemu_transport="pipe", qemu_firmware=runtime["firmware"],
        qemu_clock="virtual", qemu_checkpoint_tool=str(runtime["checkpoint_tool"]),
        dos_arguments=DOOM_ARGUMENTS, boot_timeout_ms=35000, _on_spawn=on_spawn,
    )


def _resume(control_path: Path):
    control = json.loads(control_path.read_text())
    runtime = _runtime()
    database = Path(control["database"])
    game = Path(control["game"])
    with Project(database) as project:
        assert project.debug_state_info(control["artifact"])["sha256"] == control["artifact_sha256"]
        with _open_qemu(project, runtime, game) as debug:
            initial_owner = debug.vm.process
            initial_run = debug.run_id
            initial_epoch = debug.dos_process_info()["capture_epoch"]
            restored = debug.load_machine_state(
                control["artifact"], timeout_ms=90000, rebind_protected_source=True)
            assert initial_owner.poll() is not None and debug.vm.process is not initial_owner
            assert debug.vm.process.poll() is None and debug.run_id != control["origin_run"]
            assert restored["machine_state_restored"] is True
            assert restored["source_binding_restored"] is False
            assert restored["protected_source_rebound"] is True
            assert restored["capture_epoch"] not in (control["origin_epoch"], initial_epoch)

            registers = debug.registers()
            binding = debug.dos_source_binding()
            assert registers["cpu_mode"] == "protected"
            for field in ("registers", "instruction_pointer", "cpu_mode", "address_state", "linear_pc"):
                assert registers[field] == control["cpu"][field], field
            assert binding["live"] and binding["state"] == "qualified-stopped"
            assert binding["binding_id"] != control["binding_id"]
            assert binding["capture_epoch"] == restored["capture_epoch"]
            assert binding["last_observation"]["qualified"] is True
            for field in ("source_location", "instruction_sha256", "linear_pc"):
                assert binding["last_observation"][field] == control["site"][field], field
            assert int(binding["last_observation"]["linear_pc"], 0) == int(control["cpu"]["linear_pc"], 0)
            landmark_pc, landmark_counter, landmark_code = _leveltime_addresses(
                project, debug, binding, control["directory"])
            assert (landmark_pc, landmark_counter, landmark_code.hex()) == (
                control["leveltime_pc"], control["leveltime_counter"], control["leveltime_code_hex"])
            assert _leveltime(debug, landmark_counter) == control["checkpoint_leveltime"]

            # The application state comes from Doom's rendered ammo patch, with
            # the decoder grounded in the pinned original WAD bytes.
            view = capture_statusbar(project, debug, Path(control["directory"]), "restored-before-shot")
            before = decode_ammo_from_wad(game / "DOOM.WAD", view["statusbar"])
            assert before["value"] == control["ammo"] == 50, before
            key_receipt = debug.keyboard_press("ctrl", hold_ms=300, gap_ms=80)
            assert key_receipt
            advance_result = advance(debug, "qemu-dos", 700)
            after_view = capture_statusbar(project, debug, Path(control["directory"]), "restored-after-shot")
            after = decode_ammo_from_wad(game / "DOOM.WAD", after_view["statusbar"])
            assert after["value"] == 49, after
            forward_cpu = debug.registers()
            forward = dict(key_press=key_receipt, ammo=after["value"], cpu=forward_cpu,
                           clock=_clock_receipt(advance_result),
                           normalized_frame_sha256=_normalized_frame_sha256(
                               Path(control["directory"]) / "restored-after-shot.png"),
                           frame_png_sha256=after_view["sha256"])
            cold_tic_after_budget = _leveltime(debug, landmark_counter)
            assert cold_tic_after_budget < control["target_leveltime"], (
                cold_tic_after_budget, control["target_leveltime"])
            landmark = _capture_leveltime_landmark(
                project, debug, game, control["directory"], landmark_pc, landmark_counter,
                control["target_leveltime"], "restored-at-leveltime-target")
            owner = debug.vm.process
            report = dict(pid=os.getpid(), initial_run=initial_run, restored_run=debug.run_id,
                          artifact=control["artifact"], artifact_sha256=control["artifact_sha256"],
                          cpu=registers, source_location=binding["last_observation"]["source_location"],
                          source_instruction_sha256=binding["last_observation"]["instruction_sha256"],
                          fresh_binding_id=binding["binding_id"], fresh_epoch=binding["capture_epoch"],
                          restored_ammo=before["value"], post_restore_shot_ammo=after["value"],
                          restored_frame_sha256=view["sha256"], post_shot_frame_sha256=after_view["sha256"],
                          forward=forward, leveltime_after_budget=cold_tic_after_budget,
                          leveltime_landmark=landmark)
    assert owner.poll() is not None
    report_path = Path(control_path).with_name("fresh-process-cold-report.json")
    report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps(dict(status="cold-continuation-recorded", pid=os.getpid(),
                          private_report=report_path.name), sort_keys=True))


def test_original_doom_e1m1_qemu_checkpoint_continues_in_fresh_python_process(tmp_path):
    runtime = _runtime()
    game = stage_game(tmp_path / "origin", runtime["source"])
    database = tmp_path / "doom-e1m1-checkpoint.fdb"
    inputs = {name: digest(game / name) for name in PINS}
    assert inputs == PINS
    control = None
    origin_owner = None

    with Project.create(database, game / "DOOM.EXE", image="mz") as project:
        with _open_qemu(project, runtime, game) as debug:
            origin_owner = debug.vm.process
            info = debug.dos_process_info()
            assert info["state"] == "active"
            advance(debug, "qemu-dos", 40000)
            frame = capture_statusbar(project, debug, tmp_path, "origin-before-checkpoint")
            ammo = decode_ammo_from_wad(game / "DOOM.WAD", frame["statusbar"])
            assert ammo["value"] == 50, ammo

            binding = qualified_stop(debug)
            assert binding["live"] and binding["last_observation"]["qualified"] is True
            leveltime_pc, leveltime_counter, leveltime_code = _leveltime_addresses(
                project, debug, binding, tmp_path)
            checkpoint_leveltime = _leveltime(debug, leveltime_counter)
            target_leveltime = checkpoint_leveltime + LEVELTIME_TARGET_OFFSET
            assert target_leveltime < 0xffffffff
            cpu = debug.registers()
            assert cpu["cpu_mode"] == "protected"
            saved = debug.save_machine_state("doom-e1m1-owned-machine.qcow2", max_bytes=128 * 1024 * 1024)
            assert saved["metadata"]["format"] == "fdisbull-qemu-owned-machine-qcow2-v1"
            assert saved["metadata"]["source_binding_restored"] is False
            key_receipt = debug.keyboard_press("ctrl", hold_ms=300, gap_ms=80)
            assert key_receipt
            advance_result = advance(debug, "qemu-dos", 700)
            after_frame = capture_statusbar(project, debug, tmp_path, "origin-after-shot")
            after_ammo = decode_ammo_from_wad(game / "DOOM.WAD", after_frame["statusbar"])
            assert after_ammo["value"] == 49, after_ammo
            origin_forward = dict(key_press=key_receipt, ammo=after_ammo["value"],
                cpu=debug.registers(), clock=_clock_receipt(advance_result),
                normalized_frame_sha256=_normalized_frame_sha256(tmp_path / "origin-after-shot.png"),
                frame_png_sha256=after_frame["sha256"])
            origin_tic_after_budget = _leveltime(debug, leveltime_counter)
            assert origin_tic_after_budget < target_leveltime, (
                origin_tic_after_budget, target_leveltime)
            origin_landmark = _capture_leveltime_landmark(
                project, debug, game, tmp_path, leveltime_pc, leveltime_counter,
                target_leveltime, "origin-at-leveltime-target")
            control = dict(database=str(database), game=str(game), directory=str(tmp_path),
                           artifact=saved["artifact"], artifact_sha256=saved["sha256"],
                           origin_run=debug.run_id, origin_epoch=binding["capture_epoch"],
                           binding_id=binding["binding_id"], site=binding["last_observation"],
                           cpu=cpu, ammo=ammo["value"], origin_forward=origin_forward,
                           leveltime_pc=leveltime_pc, leveltime_counter=leveltime_counter,
                           leveltime_code_hex=leveltime_code.hex(),
                           checkpoint_leveltime=checkpoint_leveltime,
                           target_leveltime=target_leveltime,
                           origin_tic_after_budget=origin_tic_after_budget,
                           origin_landmark=origin_landmark)
    assert origin_owner and origin_owner.poll() is not None

    control_path = tmp_path / "fresh-process-control.json"
    control_path.write_text(json.dumps(control, sort_keys=True))
    cold_report_path = control_path.with_name("fresh-process-cold-report.json")
    environment = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    environment["PYTHONPATH"] = source_root + os.pathsep + environment.get("PYTHONPATH", "")
    child = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(control_path)],
                           cwd=str(Path(__file__).resolve().parents[1]), env=environment,
                           capture_output=True, text=True, timeout=300)
    assert child.returncode == 0, child.stderr[-5000:]
    child_receipt = json.loads(child.stdout.strip().splitlines()[-1])
    assert child_receipt["status"] == "cold-continuation-recorded"
    assert child_receipt["private_report"] == cold_report_path.name
    report = json.loads(cold_report_path.read_text())
    assert report["pid"] == child_receipt["pid"]
    assert report["pid"] != os.getpid()
    assert report["artifact"] == control["artifact"]
    assert report["cpu"]["linear_pc"] == control["cpu"]["linear_pc"]
    assert report["restored_ammo"] == 50 and report["post_restore_shot_ammo"] == 49
    expected = control["origin_forward"]
    actual = report["forward"]
    cpu_fields = ("registers", "instruction_pointer", "cpu_mode", "address_state", "linear_pc")
    stable_clock_fields = tuple(field for field in expected["clock"] if field != "epoch")
    comparison = dict(
        ammo_equal=actual["ammo"] == expected["ammo"],
        key_schedule_equal=_input_semantics(actual["key_press"]) == _input_semantics(expected["key_press"]),
        normalized_frame_equal=actual["normalized_frame_sha256"] == expected["normalized_frame_sha256"],
        cpu_equal={field: actual["cpu"][field] == expected["cpu"][field] for field in cpu_fields},
        clock_equal={field: actual["clock"].get(field) == expected["clock"].get(field)
                     for field in stable_clock_fields},
        clock_epoch_changed=actual["clock"].get("epoch") != expected["clock"].get("epoch"),
        cpu_differences=_cpu_differences(expected["cpu"], actual["cpu"], cpu_fields),
    )
    comparison["exact_continuation"] = (
        comparison["ammo_equal"] and comparison["key_schedule_equal"]
        and comparison["normalized_frame_equal"] and all(comparison["cpu_equal"].values())
        and all(comparison["clock_equal"].values()))
    comparison["bounded_continuation"] = (
        comparison["ammo_equal"] and comparison["key_schedule_equal"]
        and comparison["normalized_frame_equal"] and all(comparison["clock_equal"].values()))
    comparison["classification"] = (
        "exact_cpu_frame_hud_and_clock_continuation" if comparison["exact_continuation"] else
        "bounded_frame_hud_and_clock_match_with_exposed_cpu_divergence"
        if comparison["bounded_continuation"] and not all(comparison["cpu_equal"].values()) else
        "continuation_divergence")
    report["continuation_comparison"] = comparison
    report["origin_forward"] = expected
    origin_landmark = control["origin_landmark"]
    cold_landmark = report["leveltime_landmark"]
    landmark_cpu_fields = ("registers", "instruction_pointer", "cpu_mode", "address_state", "linear_pc")
    landmark_comparison = dict(
        same_tic=origin_landmark["leveltime"] == cold_landmark["leveltime"] == control["target_leveltime"],
        same_pc=origin_landmark["pc"] == cold_landmark["pc"] == hex(control["leveltime_pc"]),
        same_counter=origin_landmark["counter"] == cold_landmark["counter"] == hex(control["leveltime_counter"]),
        same_code=origin_landmark["code_hex"] == cold_landmark["code_hex"] == control["leveltime_code_hex"],
        same_source=(origin_landmark["source_location"] == cold_landmark["source_location"]
                     and origin_landmark["source_instruction_sha256"]
                     == cold_landmark["source_instruction_sha256"]),
        cpu_equal={field: origin_landmark["cpu"][field] == cold_landmark["cpu"][field]
                   for field in landmark_cpu_fields},
        stack_equal=origin_landmark["stack"] == cold_landmark["stack"],
        normalized_frame_equal=(origin_landmark["normalized_frame_sha256"]
                                == cold_landmark["normalized_frame_sha256"]),
        ammo_equal=origin_landmark["ammo"] == cold_landmark["ammo"],
        cpu_differences=_cpu_differences(origin_landmark["cpu"], cold_landmark["cpu"],
                                         landmark_cpu_fields),
        stack_sha256=dict(origin=origin_landmark["stack"]["sha256"],
                          cold=cold_landmark["stack"]["sha256"]),
        frame_sha256=dict(origin=origin_landmark["normalized_frame_sha256"],
                          cold=cold_landmark["normalized_frame_sha256"]),
    )
    landmark_comparison["same_landmark"] = all(landmark_comparison[key] for key in (
        "same_tic", "same_pc", "same_counter", "same_code", "same_source"))
    landmark_comparison["exact_state_match"] = (
        landmark_comparison["same_landmark"] and all(landmark_comparison["cpu_equal"].values())
        and landmark_comparison["stack_equal"] and landmark_comparison["normalized_frame_equal"]
        and landmark_comparison["ammo_equal"])
    landmark_comparison["classification"] = (
        "exact_cpu_stack_frame_and_ammo_match_at_shared_preincrement_tic"
        if landmark_comparison["exact_state_match"] else
        "shared_preincrement_tic_reached_with_bounded_state_differences"
        if landmark_comparison["same_landmark"] else "landmark_mismatch")
    report["origin_leveltime_after_budget"] = control["origin_tic_after_budget"]
    report["cold_leveltime_after_budget"] = report["leveltime_after_budget"]
    report["target_leveltime"] = control["target_leveltime"]
    report["origin_leveltime_landmark"] = origin_landmark
    report["cold_leveltime_landmark"] = cold_landmark
    report["leveltime_landmark_comparison"] = landmark_comparison
    (tmp_path / "fresh-process-result.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    assert comparison["bounded_continuation"], json.dumps(comparison, sort_keys=True)
    assert landmark_comparison["same_landmark"], json.dumps(landmark_comparison, sort_keys=True)
    assert {name: digest(game / name) for name in PINS} == PINS
    assert digest(runtime["boot"]) == runtime["boot_sha256"]


if __name__ == "__main__":
    _resume(Path(sys.argv[1]))
