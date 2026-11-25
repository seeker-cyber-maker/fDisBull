"""Paired persistent before-fetch trace over one authored DOS COM loop.

Set FDISBULL_QEMU_TRACE to the exact QEMU candidate with the trace QMP
extension, FDISBULL_DOSBOX to the selected DOSBox-X build, and provide the
existing private FreeDOS boot image and mcopy selectors. The fixture is
authored here; no private guest output is retained in the repository.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import os
from pathlib import Path
import time

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.project import Project
from support.dos_process_fixture import prepare_dos_baseline
from test_qemu_dos_process_native import (
    com_address, create_project, launch_options, process_record,
)


# Original LOOP fixture stays unchanged for breakpoint and exact-count cases.
PROGRAM = bytes.fromhex("b9030040e2fdebfe")
EXPECTED_OFFSETS = [0x100, 0x103, 0x104, 0x103, 0x104, 0x103, 0x104, 0x106]
# Separate self-modifying COM: MOV CX,2; INC AX; rewrite INC AX as INC BX;
# LOOP twice; JMP $. The second visit to 0103h must bind translated byte 43h.
SMC_PROGRAM = bytes.fromhex("b9020040c606030143e2f8ebfe")
SMC_PATCHED_PROGRAM = bytes.fromhex("b9020043c606030143e2f8ebfe")
SMC_EXPECTED_OFFSETS = [0x100, 0x103, 0x104, 0x109, 0x103, 0x104, 0x109, 0x10b]
SMC_TRANSLATED_BYTES = ["b90200", "40", "c606030143", "e2f8",
                        "43", "c606030143", "e2f8", None]
TRACE_BUDGET = 10
TRACE_COUNT = len(EXPECTED_OFFSETS)
PAGE_SIZE = 2


@pytest.fixture(scope="module")
def paired_runtime(tmp_path_factory):
    qemu = os.environ.get("FDISBULL_QEMU_TRACE")
    dosbox = os.environ.get("FDISBULL_DOSBOX")
    image = os.environ.get("FDISBULL_QEMU_DOS_BOOT_IMAGE")
    mcopy = os.environ.get("FDISBULL_QEMU_DOS_MCOPY")
    missing = [name for name, value in (
        ("FDISBULL_QEMU_TRACE", qemu), ("FDISBULL_DOSBOX", dosbox),
        ("FDISBULL_QEMU_DOS_BOOT_IMAGE", image),
        ("FDISBULL_QEMU_DOS_MCOPY", mcopy)) if not value]
    if missing:
        pytest.skip("Paired native trace needs selected inputs: " + ", ".join(missing))
    qemu_path = Path(qemu).expanduser().resolve(strict=True)
    dosbox_path = Path(dosbox).expanduser().resolve(strict=True)
    image_path = Path(image).expanduser().resolve(strict=True)
    mcopy_path = Path(mcopy).expanduser().absolute()
    for name, path in (("QEMU candidate", qemu_path), ("DOSBox-X", dosbox_path),
                       ("FreeDOS boot image", image_path), ("mcopy", mcopy_path)):
        assert path.is_file(), (name, path)
    assert os.access(qemu_path, os.X_OK) and os.access(dosbox_path, os.X_OK)
    assert os.access(mcopy_path, os.X_OK)
    directory = tmp_path_factory.mktemp("paired-before-fetch-trace")
    disk = prepare_dos_baseline(image_path, directory / "dos-baseline.img", mcopy_path)
    return dict(qemu=qemu_path, dosbox=dosbox_path, disk=disk,
                firmware=os.environ.get("FDISBULL_QEMU_DOS_FIRMWARE"))


def _num(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def _event_offset(event, *, runtime_base=None):
    address = event.get("address") or event.get("pc")
    if isinstance(address, dict):
        for key in ("offset", "ip", "instruction_pointer"):
            if key in address:
                value = _num(address[key])
                if address.get("space") in ("linear", "virtual"):
                    assert runtime_base is not None
                    return value - runtime_base + 0x100
                return value
    for key in ("offset", "ip", "instruction_pointer"):
        if key in event:
            return _num(event[key])
    raise AssertionError(f"Trace event has no normalized PC: {event!r}")


def _page_all(call, *, limit=PAGE_SIZE):
    cursor = None
    events = []
    seen_cursors = set()
    pages = []
    while True:
        page = call("trace.read", {"cursor": cursor, "limit": limit})
        rows = page.get("events")
        assert isinstance(rows, list) and len(rows) <= limit, page
        pages.append(page)
        events.extend(rows)
        next_cursor = page.get("next_cursor")
        if next_cursor is None:
            return events, pages
        assert isinstance(next_cursor, str) and next_cursor not in seen_cursors, page
        seen_cursors.add(next_cursor)
        cursor = next_cursor


def _assert_qemu_fetch_context(result, expected_bytes):
    assert len(result["events"]) == len(expected_bytes)
    cs_base = result["runtime_base"] - 0x100
    cs_selector = cs_base // 16
    for event, expected in zip(result["events"], expected_bytes):
        native = event["native"]
        context = event["fetch_context"]
        translated = context["translated_bytes"]
        x86 = context["x86"]
        assert native["x86-context-valid"] is True, event
        assert native["code-bits"] == 16, event
        assert native["cs-selector"] == cs_selector, event
        assert native["cs-base"] == cs_base, event
        assert x86 == dict(valid=True, code_bits=16, cs_selector=cs_selector,
                           cs_base=cs_base), event
        if expected is None:
            reason = "breakpoint-pre-dispatch-no-translation"
            assert native["code-bytes-valid"] is False, event
            assert native["code-byte-count"] == 0, event
            assert native["code-bytes"] == "", event
            assert native["code-bytes-source"] == "none", event
            assert native["code-bytes-unavailable-reason"] == reason, event
            assert translated == dict(valid=False, hex=None, count=0,
                                      source="none", unavailable_reason=reason), event
        else:
            count = len(bytes.fromhex(expected))
            assert native["code-bytes-valid"] is True, event
            assert native["code-byte-count"] == count, event
            assert native["code-bytes"] == expected, event
            assert native["code-bytes-source"] == "translated-tb", event
            assert native["code-bytes-unavailable-reason"] == "", event
            assert translated == dict(valid=True, hex=expected, count=count,
                                      source="translated-tb", unavailable_reason=None), event


def _qemu_trace(runtime, tmp_path, *, budget=TRACE_BUDGET, stop_ip=0x106,
                program=PROGRAM, breakpoint_ip=0x106, expected_guest_code=None):
    directory = tmp_path / f"qemu-{budget}-{breakpoint_ip}"
    directory.mkdir()
    binary, project = create_project(directory, program)
    with project:
        with project.debugger(str(runtime["qemu"]), directory,
                              **launch_options({"executable": str(runtime["qemu"]),
                                                "mcopy": str(runtime["disk"]["mcopy"])
                                                if "mcopy" in runtime["disk"] else
                                                os.environ["FDISBULL_QEMU_DOS_MCOPY"],
                                                "firmware": runtime["firmware"]},
                                               runtime["disk"])) as debug:
            info = process_record(debug)
            entry = _num(info["entry"]["ip"])
            assert entry == 0x100, info["entry"]
            breakpoint = debug.breakpoint(com_address(info, breakpoint_ip))
            started = debug.call("trace.start", {"detail": "normal",
                                                  "instruction_count": budget})
            assert started.get("active") is True, started
            run = debug.run(timeout_ms=5000)
            assert run["outcome"] != "timeout", run
            registers = debug.registers()
            assert _num(registers["instruction_pointer"]) == stop_ip, (run, registers)
            if stop_ip == breakpoint_ip:
                assert run["outcome"] == "breakpoint", run
                assert breakpoint["breakpoint_id"] in run["session"]["stop_reason"]["breakpoint_ids"]

            pages = []
            events, pages = _page_all(debug.call)
            stopped = debug.call("trace.stop")
            code = bytes.fromhex(debug.memory(com_address(info, 0x100), length=len(program),
                                              space="physical")["hex"])
            expected_code = program if expected_guest_code is None else expected_guest_code
            assert code == expected_code
            return dict(events=events, pages=pages, stopped=stopped,
                        producer_sha256=hashlib.sha256(runtime["qemu"].read_bytes()).hexdigest(),
                        runtime_base=com_address(info, 0x100), code=code,
                        trace_version=started.get("trace_version"),
                        stop_ip=_num(registers["instruction_pointer"]), budget=budget,
                        source_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())


def _dosbox_trace(runtime, tmp_path, *, budget=TRACE_BUDGET, stop_ip=0x106,
                  program=PROGRAM, breakpoint_ip=0x106, expected_guest_code=None):
    game = tmp_path / f"dosbox-{budget}-{breakpoint_ip}"
    game.mkdir()
    binary = game / "TRACE.COM"
    binary.write_bytes(program)
    with closing(DOSBoxRPC(runtime["dosbox"], game)) as rpc:
        start = rpc.call("session.start", {
            "target": {"command": binary.name, "arguments": []},
            "mounts": [{"drive": "C", "host_path": str(game)}],
            "break_at": "entry",
        })
        session_id = start["session_id"]

        def call(method, params=None):
            return rpc.call(method, {"session_id": session_id, **(params or {})},
                            timeout_ms=5000)

        registers = call("state.get_registers")
        segments = registers.get("segments", registers.get("registers", {}))
        cs_value = segments.get("cs")
        cs = int(cs_value, 16) if isinstance(cs_value, str) else int(cs_value)
        breakpoint = call("breakpoints.create", {
            "kind": "execution", "once": False,
            "address": {"space": "segmented", "segment": f"0x{cs:04x}",
                        "offset": f"0x{breakpoint_ip:08x}"},
        })
        started = call("trace.start", {"detail": "normal",
                                       "instruction_count": budget})
        assert started.get("active") is True, started
        operation = call("execution.continue")
        deadline = time.monotonic() + 5
        while True:
            remaining = int((deadline - time.monotonic()) * 1000)
            assert remaining > 0, "DOSBox-X failed to reach the COM loop breakpoint"
            stop = call("execution.wait", {"operation_id": operation["operation_id"],
                                            "timeout_ms": min(250, remaining)})
            if not stop.get("running"):
                break
        if stop_ip == breakpoint_ip:
            assert stop["stop_reason"]["breakpoint_id"] == breakpoint["breakpoint_id"], stop
        stopped_registers = call("state.get_registers")
        stopped_ip_value = stopped_registers.get("instruction_pointer")
        if stopped_ip_value is None:
            values = stopped_registers.get("registers", {})
            stopped_ip_value = values.get("ip", values.get("eip"))
        stopped_ip = _num(stopped_ip_value)
        assert stopped_ip == stop_ip, (stop, stopped_registers)
        pages = []
        events, pages = _page_all(call)
        stopped = call("trace.stop")
        memory = call("memory.read", {
            "address": {"space": "physical", "offset": f"0x{cs * 16 + 0x100:08x}"},
            "length": len(program),
        })
        import base64
        import hashlib as _hashlib
        code = base64.b64decode(memory["data_base64"], validate=True)
        expected_code = program if expected_guest_code is None else expected_guest_code
        assert code == expected_code
        return dict(events=events, pages=pages, stopped=stopped,
                    producer_sha256=_hashlib.sha256(runtime["dosbox"].read_bytes()).hexdigest(),
                    runtime_base=cs * 16 + 0x100, code=code,
                    stop_ip=stopped_ip, budget=budget,
                    source_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())


def test_native_dosbox_qemu_breakpoint_trace_pagination_parity(paired_runtime, tmp_path):
    qemu = _qemu_trace(paired_runtime, tmp_path)
    dosbox = _dosbox_trace(paired_runtime, tmp_path)

    # This preserves the original loop fixture and its eight-PC breakpoint
    # witness. DOSBox contributes only PC order here.
    qemu_offsets = [_event_offset(event, runtime_base=qemu["runtime_base"])
                    for event in qemu["events"]]
    dosbox_offsets = [_event_offset(event) for event in dosbox["events"]]
    assert qemu_offsets == dosbox_offsets == EXPECTED_OFFSETS
    for rows in (qemu["events"], dosbox["events"]):
        sequences = [event.get("sequence") for event in rows]
        assert all(type(value) is int for value in sequences), rows
        assert sequences == list(range(sequences[0], sequences[0] + len(rows)))
    assert all(event.get("native", {}).get("reason") == "before-execution"
               for event in qemu["events"])
    assert [event.get("native", {}).get("origin") for event in qemu["events"]] == [
        "tcg-dispatch",
    ] * 7 + ["breakpoint-pre-dispatch"]
    assert all(event.get("observation", {}).get("instruction_completed") is None
               and event.get("observation", {}).get("registers_stage") == "before-instruction"
               for event in qemu["events"])
    assert qemu["code"] == dosbox["code"] == PROGRAM
    assert qemu["source_sha256"] == dosbox["source_sha256"] == hashlib.sha256(PROGRAM).hexdigest()

    assert len(qemu["pages"]) == len(dosbox["pages"]) == 4
    assert [len(page["events"]) for page in qemu["pages"]] == [2, 2, 2, 2]
    assert [len(page["events"]) for page in dosbox["pages"]] == [2, 2, 2, 2]
    for result in (qemu, dosbox):
        assert result["stopped"].get("active") is False, result["stopped"]
        assert result["stopped"].get("event_count") == TRACE_COUNT, result["stopped"]
        assert result["stopped"].get("dropped_count", 0) == 0, result["stopped"]
        assert len(result["events"]) == TRACE_COUNT
        assert len(result["events"]) <= result["budget"]
        assert result["budget"] == TRACE_BUDGET and result["stop_ip"] == 0x106
    assert qemu["pages"][-1].get("captured_count", TRACE_COUNT) == TRACE_COUNT
    assert qemu["pages"][-1].get("requested_count", TRACE_BUDGET) == TRACE_BUDGET


def test_native_dosbox_qemu_exact_count_stops_before_third_instruction(paired_runtime, tmp_path):
    # Isolated from the breakpoint case so a before-fetch ordering difference
    # at a software breakpoint cannot mask exact-count behavior.
    qemu = _qemu_trace(paired_runtime, tmp_path, budget=3, stop_ip=0x104)
    dosbox = _dosbox_trace(paired_runtime, tmp_path, budget=3, stop_ip=0x104)
    qemu_offsets = [_event_offset(event, runtime_base=qemu["runtime_base"])
                    for event in qemu["events"]]
    dosbox_offsets = [_event_offset(event) for event in dosbox["events"]]
    assert qemu_offsets == dosbox_offsets == [0x100, 0x103, 0x104]
    assert [event.get("native", {}).get("origin") for event in qemu["events"]] == [
        "tcg-dispatch",
    ] * 3
    for result in (qemu, dosbox):
        assert len(result["events"]) == result["stopped"].get("event_count") == 3
        assert result["stopped"].get("active") is False
        assert result["stopped"].get("dropped_count", 0) == 0
        assert result["stop_ip"] == 0x104 and result["budget"] == 3
        assert result["source_sha256"] == hashlib.sha256(PROGRAM).hexdigest()


def test_native_dosbox_qemu_smc_translation_bound_bytes_and_context(paired_runtime, tmp_path):
    qemu = _qemu_trace(paired_runtime, tmp_path, program=SMC_PROGRAM,
                       breakpoint_ip=0x10b, stop_ip=0x10b,
                       expected_guest_code=SMC_PATCHED_PROGRAM)
    dosbox = _dosbox_trace(paired_runtime, tmp_path, program=SMC_PROGRAM,
                           breakpoint_ip=0x10b, stop_ip=0x10b,
                           expected_guest_code=SMC_PATCHED_PROGRAM)
    qemu_offsets = [_event_offset(event, runtime_base=qemu["runtime_base"])
                    for event in qemu["events"]]
    dosbox_offsets = [_event_offset(event) for event in dosbox["events"]]
    assert qemu_offsets == dosbox_offsets == SMC_EXPECTED_OFFSETS
    assert [event.get("native", {}).get("origin") for event in qemu["events"]] == [
        "tcg-dispatch",
    ] * 7 + ["breakpoint-pre-dispatch"]
    assert qemu["trace_version"] == 2
    _assert_qemu_fetch_context(qemu, SMC_TRANSLATED_BYTES)
    assert qemu["code"] == dosbox["code"] == SMC_PATCHED_PROGRAM
    assert qemu["source_sha256"] == dosbox["source_sha256"] == hashlib.sha256(SMC_PROGRAM).hexdigest()
    assert qemu["stopped"].get("event_count") == len(SMC_EXPECTED_OFFSETS)
    assert qemu["stopped"].get("trace_version") == 2
    assert all(page.get("trace_version") == 2 for page in qemu["pages"])
    assert dosbox["stopped"].get("event_count") == len(SMC_EXPECTED_OFFSETS)
