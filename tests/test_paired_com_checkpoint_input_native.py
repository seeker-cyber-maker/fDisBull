"""Opt-in paired native checkpoint-and-input witness for an authored COM.

The guest polls BIOS INT 16h with AH=01h and stops after the no-key result,
before the branch back to the poll. Each backend captures its own native
checkpoint. The checkpoint is consumed once in the originating Python owner
and once from a fresh Python/backend owner. This is a bounded authored COM
checkpoint/input witness, not DOSBox/QEMU state-format or Doom parity. Fresh
DOSBox-X restores stop at the pre-exit boundary by default for compatibility
with installed binaries. An explicit candidate gate also requires cold DOSBox-X
to observe the authored guest exit.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import digest, prepare_dos_baseline


# 0100: mov ah,01 / int 16h / jz 0100
# 0106: mov ah,00 / int 16h / store AL and marker at 0140
# 0112: wait for two BIOS ticks after storing the input, then exit 37
_COM = bytes.fromhex(
    "b401cd1674fab400cd16a24001c6064101a5"
    "b400cd1a89164201b400cd1a2b16420183fa0272f3b8254ccd21"
).ljust(0x42, b"\0")
_POLL_RETURN_IP = 0x104
_EXIT_IP = 0x12A
_KEY_OFFSET = 0x40
_MARKER = 0xA5
_REQUIRE_DOSBOX_COLD_EXIT = "FDISBULL_REQUIRE_DOSBOX_COLD_COM_GUEST_EXIT"


def _runtime():
    if os.environ.get("FDISBULL_REQUIRE_PAIRED_COM_CHECKPOINT_INPUT") != "1":
        pytest.skip("Set FDISBULL_REQUIRE_PAIRED_COM_CHECKPOINT_INPUT=1 for the paired native checkpoint gate")
    if os.environ.get("FDISBULL_REQUIRE_QEMU_DOS_OS") != "1":
        pytest.fail("The paired gate requires the explicitly admitted QEMU DOS runtime environment")
    names = {
        "dosbox": "FDISBULL_DOSBOX",
        "qemu": "FDISBULL_QEMU_DOS",
        "boot_image": "FDISBULL_QEMU_DOS_BOOT_IMAGE",
        "mcopy": "FDISBULL_QEMU_DOS_MCOPY",
        "firmware": "FDISBULL_QEMU_DOS_FIRMWARE",
        "qemu_img": "FDISBULL_QEMU_IMG",
    }
    values = {name: os.environ.get(variable) for name, variable in names.items()}
    missing = [names[name] for name, value in values.items() if not value]
    if missing:
        pytest.fail("Missing paired COM checkpoint inputs: " + ", ".join(missing))
    result = {name: Path(value).expanduser().resolve(strict=True)
              for name, value in values.items() if name != "mcopy"}
    # Keep mtools' selected command name when it is a multicall symlink.
    result["mcopy"] = Path(values["mcopy"]).expanduser().absolute()
    for name in ("dosbox", "qemu", "mcopy", "qemu_img"):
        path = result[name]
        if not path.is_file() or not os.access(path, os.X_OK):
            pytest.fail(f"{name} must name an executable file: {path}")
    if not result["boot_image"].is_file():
        pytest.fail(f"boot_image must name a file: {result['boot_image']}")
    if not result["firmware"].is_dir():
        pytest.fail(f"firmware must name a directory: {result['firmware']}")
    return result


def _number(value):
    return int(value, 0) if isinstance(value, str) else value


def _ip(registers):
    value = registers.get("instruction_pointer", registers.get("ip"))
    assert value is not None, registers
    return int(value, 16) if isinstance(value, str) and not value.lower().startswith("0x") else _number(value)


def _register_word(registers, *names):
    value = None
    for name in names:
        for values in (registers.get("general", {}), registers.get("registers", {}), registers):
            if name in values:
                value = values[name]
                break
        if value is not None:
            break
    assert value is not None, registers
    return int(value, 16) if isinstance(value, str) and not value.lower().startswith("0x") else _number(value)


def _owner(debug, backend):
    return debug.rpc.process if backend == "dosbox" else debug.vm.process


def _open(project, runtime, game, disk, backend):
    if backend == "dosbox":
        return project.debugger(str(runtime["dosbox"]), game)
    return project.debugger(
        str(runtime["qemu"]), game, backend="qemu-dos",
        dos_boot_image=str(disk), dos_mcopy=str(runtime["mcopy"]),
        dos_startup_batch="FDAUTO.BAT",
        qemu_transport="pipe", qemu_firmware=str(runtime["firmware"]),
        qemu_clock="virtual", qemu_checkpoint_tool=str(runtime["qemu_img"]),
        boot_timeout_ms=30000,
    )


def _idle_keyboard(debug, backend):
    if backend == "dosbox":
        state = debug.keyboard_state()["keyboard"]
        assert state["pending_events"] == 0 and state["owned_keys"] == 0, state
        return state
    state = debug.input_state()
    assert state["pending_edges"] == 0 and state["leases"] == {}, state
    assert not debug._input_schedule_bound()
    return state


def _break_at(debug, backend, address):
    source_offset = address - 0x100
    if backend == "dosbox":
        return debug.breakpoint(debug.static_base + source_offset)
    process = debug.dos_process_info()
    base = _number(process["source_mapping"]["runtime_base"])
    return debug.breakpoint(base + source_offset)


def _reach_landmark(debug, backend):
    # This point is immediately after INT 16h/AH=01 returned ZF=1 and before
    # the guest branches back to poll. It is the common authored pre-input PC.
    assert debug.registers().get("cpu_mode") == "real"
    poll = _break_at(debug, backend, _POLL_RETURN_IP)
    stopped = debug.run(timeout_ms=15000)
    assert stopped["outcome"] == "breakpoint", stopped
    registers = debug.registers()
    assert _ip(registers) == _POLL_RETURN_IP
    flags = _register_word(registers, "flags", "eflags", "rflags")
    assert flags & 0x40, registers  # BIOS INT 16h/AH=01h reported ZF=1 (no key).
    _idle_keyboard(debug, backend)
    return poll


def _verify_after_input(debug, backend, breakpoint, *, verify_exit=True):
    _idle_keyboard(debug, backend)
    receipt = debug.keyboard_press("k", hold_ms=40, gap_ms=40)
    assert receipt
    stopped = debug.run(timeout_ms=15000)
    assert stopped["outcome"] == "breakpoint", stopped
    assert _ip(debug.registers()) == _EXIT_IP

    # The COM stores AL from BIOS INT 16h/AH=00h and then writes the marker.
    # Read the guest-owned bytes before INT 21h terminates the process.
    address = (debug.static_base + _KEY_OFFSET if backend == "dosbox" else
               _number(debug.dos_process_info()["source_mapping"]["runtime_base"]) + _KEY_OFFSET)
    memory = debug.memory(address, length=2, **({} if backend == "dosbox" else {"space": "physical"}))
    assert bytes.fromhex(memory["hex"]) == b"k" + bytes([_MARKER]), memory
    registers = debug.registers()
    assert _register_word(registers, "ax", "eax", "rax") & 0xFFFF == 0x4C25, registers

    if backend == "qemu":
        observed = debug.input_schedule_observe()
        assert observed["state"] == "dispatched", observed
        assert observed["press"]["dispatched_count"] == len(observed["press"]["steps"]), observed
        assert debug.input_state()["pending_edges"] == 0 and debug.input_state()["leases"] == {}
        input_receipt = observed
    else:
        after = debug.keyboard_state()["keyboard"]
        assert after["pending_events"] == 0 and after["owned_keys"] == 0, after
        input_receipt = receipt

    debug.delete_breakpoint(breakpoint["breakpoint_id"])
    if verify_exit:
        exited = debug.run(timeout_ms=5000)
        assert exited["outcome"] == "guest_exit", dict(stop=exited, registers=debug.registers())
        if backend == "dosbox":
            assert exited["session"]["stop_reason"]["guest_exit"]["requested_exit_code"] == 37
        else:
            assert exited["process"]["termination"]["code"] == 37
    return dict(key_byte=ord("k"), marker=_MARKER, exit_boundary_reached=True,
                guest_exit_observed=verify_exit, guest_exit_code=37 if verify_exit else None,
                input_receipt=input_receipt)


def _fresh_child(control_path):
    control = json.loads(Path(control_path).read_text())
    runtime = {name: Path(path) for name, path in control["runtime"].items()}
    with Project(control["database"]) as project:
        with _open(project, runtime, Path(control["game"]), Path(control["disk"]), control["backend"]) as debug:
            fresh_owner = _owner(debug, control["backend"])
            assert fresh_owner.pid != control["origin_owner_pid"]
            _idle_keyboard(debug, control["backend"])
            debug.load_state(control["artifact"])
            assert _ip(debug.registers()) == _POLL_RETURN_IP
            if control["backend"] == "qemu":
                assert debug.vm.process is not fresh_owner and fresh_owner.poll() is not None
            breakpoint = _break_at(debug, control["backend"], _EXIT_IP)
            strict_dosbox_exit = os.environ.get(_REQUIRE_DOSBOX_COLD_EXIT) == "1"
            result = _verify_after_input(debug, control["backend"], breakpoint,
                verify_exit=(control["backend"] == "qemu" or
                             (control["backend"] == "dosbox" and strict_dosbox_exit)))
            owner = _owner(debug, control["backend"])
            owner_pid = owner.pid
    assert owner.poll() is not None
    print(json.dumps(dict(passed=True, backend=control["backend"], pid=os.getpid(),
                          owner_pid=owner_pid, owner_returncode=owner.returncode,
                          **result), sort_keys=True))


def _capture_and_hot_restore(project, runtime, game, disk, backend):
    with _open(project, runtime, game, disk, backend) as debug:
        origin_owner = _owner(debug, backend)
        poll = _reach_landmark(debug, backend)
        # Keep a stop-breakpoint identity out of the checkpoint controls.
        debug.delete_breakpoint(poll["breakpoint_id"])
        saved = debug.save_state("paired-com-pre-input.sav")
        info = project.debug_state_info(saved["artifact"])
        assert info["sha256"] == saved["sha256"]
        if backend == "qemu":
            assert saved["metadata"]["format"] == "fdisbull-qemu-dos-process-qcow2-v2"
        else:
            assert saved["metadata"]["format"] == "dosbox-x-native"
        # Each backend captures and restores only its own serializer artifact.
        # Reloading through the same debug session is the hot path.
        debug.load_state(saved["artifact"])
        if backend == "qemu":
            assert origin_owner.poll() is not None and debug.vm.process is not origin_owner
        assert _ip(debug.registers()) == _POLL_RETURN_IP
        exit_breakpoint = _break_at(debug, backend, _EXIT_IP)
        result = _verify_after_input(debug, backend, exit_breakpoint)
        final_owner = _owner(debug, backend)
        origin_pid = origin_owner.pid
    assert final_owner.poll() is not None
    return dict(artifact=saved["artifact"], sha256=saved["sha256"],
                origin_owner_pid=origin_pid, owner_returncode=final_owner.returncode,
                result=result)


def test_paired_authored_com_hot_and_fresh_owner_checkpoint_input(tmp_path):
    runtime = _runtime()
    boot_hash = digest(runtime["boot_image"])
    disk = prepare_dos_baseline(runtime["boot_image"], tmp_path / "baseline.img", runtime["mcopy"])
    source_hash = hashlib.sha256(_COM).hexdigest()
    observations = {}
    for backend in ("dosbox", "qemu"):
        game = tmp_path / backend
        game.mkdir()
        # The source is present in each backend's exact private game directory.
        backend_source = game / "CHECK.COM"
        backend_source.write_bytes(_COM)
        with Project.create(tmp_path / f"{backend}.fdb", backend_source, image="com") as project:
            project.analyze(max_instructions=64)
            observations[backend] = _capture_and_hot_restore(
                project, runtime, game, disk["image"], backend)
        assert backend_source.read_bytes() == _COM
        assert hashlib.sha256(backend_source.read_bytes()).hexdigest() == source_hash
    assert digest(runtime["boot_image"]) == boot_hash

    # Cross a real host boundary, opening a fresh backend owner for each
    # independently captured artifact. The private FDB/state remains in tmp_path.
    controls = []
    for backend in ("dosbox", "qemu"):
        control = dict(database=str(tmp_path / f"{backend}.fdb"), game=str(tmp_path / backend),
                       disk=str(disk["image"]), backend=backend,
                       runtime={name: str(value) for name, value in runtime.items()},
                       artifact=observations[backend]["artifact"],
                       origin_owner_pid=observations[backend]["origin_owner_pid"])
        control_path = tmp_path / f"{backend}-fresh-owner.json"
        control_path.write_text(json.dumps(control))
        controls.append(control_path)
    env = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = source_root + os.pathsep + env.get("PYTHONPATH", "")
    children = []
    for control_path in controls:
        completed = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                     "--checkpoint-child", str(control_path)],
                                   cwd=str(Path(__file__).resolve().parents[1]), env=env,
                                   capture_output=True, text=True, timeout=240)
        assert completed.returncode == 0, completed.stderr[-4000:]
        child = json.loads(completed.stdout.splitlines()[-1])
        assert child["passed"] and child["pid"] != os.getpid()
        assert child["key_byte"] == ord("k") and child["marker"] == _MARKER
        assert child["exit_boundary_reached"]
        cold_exit_expected = (child["backend"] == "qemu" or
                              (child["backend"] == "dosbox" and
                               os.environ.get(_REQUIRE_DOSBOX_COLD_EXIT) == "1"))
        assert child["guest_exit_observed"] == cold_exit_expected
        assert child["guest_exit_code"] == (37 if cold_exit_expected else None)
        children.append(child)

    receipt = dict(
        format="fdisbull-paired-com-cold-input-process-identity-1",
        source_sha256=source_hash,
        runtime_sha256={name: digest(runtime[name]) for name in
                        ("dosbox", "qemu", "boot_image", "mcopy", "qemu_img")},
        strict_dosbox_cold_exit=os.environ.get(_REQUIRE_DOSBOX_COLD_EXIT) == "1",
        hot={backend: dict(guest_exit_observed=value["result"]["guest_exit_observed"],
                           guest_exit_code=value["result"]["guest_exit_code"],
                           owner_returncode=value["owner_returncode"],
                           checkpoint_sha256=value["sha256"])
             for backend, value in observations.items()},
        cold={child["backend"]: dict(guest_exit_observed=child["guest_exit_observed"],
                                    guest_exit_code=child["guest_exit_code"],
                                    owner_returncode=child["owner_returncode"],
                                    exit_boundary_reached=child["exit_boundary_reached"],
                                    key_byte=child["key_byte"], marker=child["marker"])
              for child in children},
        limits="Authored COM only; each engine retains its own native checkpoint format")
    (Path(tmp_path) / "paired-com-cold-identity.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--checkpoint-child":
    _fresh_child(sys.argv[2])
