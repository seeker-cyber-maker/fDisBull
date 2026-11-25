"""Opt-in paired authored COM gate for legacy core-control obligations.

Requires pinned caller-owned DOSBox-X, QEMU, FreeDOS image and mcopy inputs.
No target media is stored in this repository. This gate covers only one small
authored COM loop and normal exit; it is not broad DOS or debugger parity.
"""
import hashlib
import os

import pytest

from fdisbull.project import Project
from test_qemu_dosbox_parity_native import (
    _com_fixture, _ip, _launch_qemu, _owned_process, _word, parity_inputs,
)


@pytest.fixture(scope="module", autouse=True)
def require_paired_core_control_gate(request):
    if os.environ.get("FDISBULL_REQUIRE_QEMU_CORE_CONTROL") != "1":
        pytest.skip("Requires the separately admitted paired core-control owner gate")
    assert request.config.option.maxfail == 1
    assert not getattr(request.config.option, "numprocesses", None)
    assert os.environ.get("FDISBULL_REQUIRE_QEMU_DOS_OS") == "1"


def _observe_controls(runtime, directory, *, qemu):
    directory.mkdir(parents=True, exist_ok=True)
    code = _com_fixture()
    source = directory / "TARGET.COM"
    source.write_bytes(code)
    with Project.create(directory / "core-control.fdb", source, image="com") as project:
        project.analyze(max_instructions=32)
        session = (_launch_qemu(project, runtime, directory) if qemu
                   else project.debugger(str(runtime["dosbox"]), directory))
        with session as debug:
            assert debug.contexts()["selected"] == ("machine" if qemu else "dos-cpu")
            initial = debug.registers()
            assert _ip(initial) == 0x100
            if qemu:
                process = debug.dos_process_info()
                assert process["state"] == "active"
                raw_base = process["source_mapping"]["runtime_base"]
                source_base = int(raw_base, 0) if isinstance(raw_base, str) else raw_base
            else:
                source_base = debug.static_base
            point = debug.breakpoint(source_base + 0x0A)
            if qemu:
                # QEMU's supported public listing is its session alias map.
                # The legacy breakpoints.list RPC route is not implemented.
                assert point["breakpoint_id"] in debug.breakpoints
                listing_surface = "public session breakpoint alias map"
            else:
                listed = debug.call("breakpoints.list")
                assert isinstance(listed["breakpoints"], list)
                assert any(row["breakpoint_id"] == point["breakpoint_id"]
                           for row in listed["breakpoints"])
                listing_surface = "legacy breakpoints.list reply"
            stop = debug.run(timeout_ms=5000, **({} if qemu else {"fast_forward": True}))
            assert stop["outcome"] == "breakpoint", stop
            assert _ip(debug.registers()) == 0x10A
            debug.delete_breakpoint(point["breakpoint_id"])

            if qemu:
                continued = debug.resume()
                assert continued["state"] == "running"
                running = debug.status()
                assert running["state"] == "running"
                paused = debug.pause()
                assert paused["state"] == "stopped"
            else:
                continued = debug.call("execution.continue")
                running = debug.call("execution.wait", {
                    "operation_id": continued["operation_id"], "timeout_ms": 10,
                })
                assert running["running"] is True
                paused = debug.call("execution.pause")
                observed = debug.call("execution.wait", {
                    "operation_id": paused["operation_id"], "timeout_ms": 2000,
                })
                assert observed.get("running", False) is False
                assert observed.get("stop_reason", {}).get("kind")
            assert debug.status()["state"] == "stopped"
            result = {
                "selected_context": debug.contexts()["selected"],
                "listing_surface": listing_surface,
                "stop": stop["outcome"],
                "pause_stop": paused["state"] if qemu else observed["stop_reason"]["kind"],
                "paused_ip": _ip(debug.registers()),
            }
            owner = _owned_process(debug, qemu=qemu)
    assert owner.poll() is not None
    assert source.read_bytes() == code
    return result


def _observe_exit(runtime, directory, *, qemu):
    directory.mkdir(parents=True, exist_ok=True)
    code = bytes.fromhex("b8254ccd21")  # mov ax,4c25h; int 21h
    source = directory / "TARGET.COM"
    source.write_bytes(code)
    with Project.create(directory / ("qemu-exit.fdb" if qemu else "dosbox-exit.fdb"),
                        source, image="com") as project:
        session = (_launch_qemu(project, runtime, directory) if qemu
                   else project.debugger(str(runtime["dosbox"]), directory))
        with session as debug:
            result = debug.run(timeout_ms=5000, **({} if qemu else {"fast_forward": True}))
            assert result["outcome"] == "guest_exit", result
            if qemu:
                assert result["process"]["termination"]["code"] == 37
                owner = _owned_process(debug, qemu=True)
            else:
                assert result["session"]["stop_reason"]["guest_exit"]["requested_exit_code"] == 37
                owner = _owned_process(debug, qemu=False)
    assert owner.poll() == 0
    assert source.read_bytes() == code
    return dict(outcome="guest_exit", code=37, source_sha256=hashlib.sha256(code).hexdigest())


def test_paired_authored_com_core_control_and_selected_process_exit(tmp_path, parity_inputs):
    dosbox = _observe_controls(parity_inputs, tmp_path / "dosbox", qemu=False)
    qemu = _observe_controls(parity_inputs, tmp_path / "qemu", qemu=True)
    # Compare common observations only. Listing and operation schemas remain
    # backend-specific; QEMU's legacy listing RPC gap is explicit.
    assert dosbox["listing_surface"] == "legacy breakpoints.list reply"
    assert qemu["listing_surface"] == "public session breakpoint alias map"
    assert dosbox["stop"] == qemu["stop"] == "breakpoint"
    assert dosbox["paused_ip"] == qemu["paused_ip"] == 0x10A

    dosbox_exit = _observe_exit(parity_inputs, tmp_path / "exit-dosbox", qemu=False)
    qemu_exit = _observe_exit(parity_inputs, tmp_path / "exit-qemu", qemu=True)
    assert dosbox_exit == qemu_exit
