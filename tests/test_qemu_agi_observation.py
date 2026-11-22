"""Explicit native AGI observation acceptance, using authored bytecode only.

Set FDISBULL_QEMU_AGI to the candidate qemu-system-agi executable. An absent
setting skips visibly; an invalid explicit setting fails. Expectations use the
independent raw-byte scalar oracle and literal position/state requirements,
never the production AGI decoder or the target's own disassembly.
"""
from copy import deepcopy
from functools import partial
import hashlib
import importlib.util
import os
from pathlib import Path

import pytest

from agi_scalar_reference import oracle, oracle_selftest


HARNESS = Path(__file__).resolve().parents[1] / "native" / "qemu-agi" / "harness.py"
_spec = importlib.util.spec_from_file_location("qemu_agi_acceptance_harness", HARNESS)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
QemuAGI = partial(_module.QemuAGI,
                 evidence_dir=os.environ.get("FDISBULL_QEMU_AGI_EVIDENCE"))
QMPError, guest_state = _module.QMPError, _module.guest_state

PROFILE = "agi-2917-scalar-position-pilot-1"
# Assign v1/v2, position actor zero twice at (5,6), then position.v at (10,20).
MIXED = bytes.fromhex("03010a03021425000506250005062600010200")
MIXED_PCS = [0, 3, 6, 10, 14, 18]
MIXED_WIDTHS = {0: 3, 3: 3, 6: 4, 10: 4, 14: 4, 18: 1}
ARITHMETIC = bytes.fromhex(
    "0301ff0302000303630c080d08"  # Initial values and set/reset f8.
    "010102020401030501010603010701020803010e0700"
)


@pytest.fixture(scope="module")
def native_binary():
    configured = os.environ.get("FDISBULL_QEMU_AGI")
    if not configured:
        pytest.skip("native AGI acceptance requires explicit FDISBULL_QEMU_AGI")
    path = Path(configured).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        pytest.fail("FDISBULL_QEMU_AGI must name an executable candidate binary")
    oracle_selftest()
    return path


def scalar_oracle(code):
    initial = {f"$agi_v{i}": 0 for i in range(256)}
    initial.update({f"$agi_f{i}": False for i in range(256)})
    result, trace, stack, outcome = oracle({0: code}, 0, 0, set(), {}, initial)
    assert outcome == "return" and stack == []
    return result, [pc for logic, pc in trace]


def assert_source(vm, state, records, code):
    expected = {
        "sha256": hashlib.sha256(code).hexdigest(), "size": len(code),
        "logic_id": 0, "profile": PROFILE,
    }
    assert state["schema"] == "fdisbull-agi-native-state-1"
    assert state["source"] == records["source"] == expected
    assert vm.source_sha256 == expected["sha256"]
    assert vm.program.read_bytes() == code
    assert records["epoch"] == state["observation"]["epoch"]
    assert type(state["run"]["elapsed_ns"]) is int
    assert state["run"]["elapsed_ns"] >= 0
    assert state["run"]["retired"] <= state["guest"]["retired"]


def assert_scalar_result(state, expected, pcs):
    guest = guest_state(state)
    assert guest["variables"] == [expected[f"$agi_v{i}"] for i in range(256)]
    assert guest["flags"] == [int(expected[f"$agi_f{i}"]) for i in range(256)]
    assert guest["retired"] == len(pcs)
    assert guest["pc"] == pcs[-1] + 1  # Last executed opcode is return.
    assert guest["status"] == "return" and guest["fault"] is None
    assert guest["actors"] == [
        {"id": i, "x": 0, "y": 0, "prev_x": 0, "prev_y": 0} for i in range(16)
    ]


def payload(record):
    """Compare semantic records across sessions, excluding session counters."""
    return {key: value for key, value in record.items()
            if key not in {"seq", "control_generation"}}


@pytest.mark.parametrize("mask", [0, 1, 2, 3])
def test_native_scalar_modes_match_independent_raw_oracle(native_binary, mask):
    expected, pcs = scalar_oracle(ARITHMETIC)
    with QemuAGI(native_binary, ARITHMETIC) as vm:
        vm.configure(mask=mask, capacity=128, step_budget=128)
        state = vm.run()
        records = vm.events()
        assert_source(vm, state, records, ARITHMETIC)
        assert_scalar_result(state, expected, pcs)
        retire = records["events"]
        assert [r["pc"] for r in retire] == (pcs if mask & 1 else [])
        assert all(r["kind"] == "retire" for r in retire)
        assert state["observation"]["helper_calls"] == (len(pcs) if mask & 1 else 0)
        assert state["observation"]["per_channel"]["scene"]["eligible"] == 0
        for record in retire:
            offset = record["pc"]
            assert bytes(record["bytes"]) == ARITHMETIC[offset:offset + len(record["bytes"])]
            assert record["opcode"] == ARITHMETIC[offset]


def test_native_position_modes_are_neutral_and_filter_duplicate_positions(native_binary):
    states, observations = {}, {}
    for mask in (0, 1, 2, 3):
        with QemuAGI(native_binary, MIXED) as vm:
            vm.configure(mask=mask, capacity=128, step_budget=128)
            state = vm.run()
            records = vm.events()
            assert_source(vm, state, records, MIXED)
            states[mask] = guest_state(state)
            observations[mask] = records["events"]
            retire = [r for r in records["events"] if r["kind"] == "retire"]
            position = [r for r in records["events"] if r["kind"] == "position"]
            assert [r["pc"] for r in retire] == (MIXED_PCS if mask & 1 else [])
            assert [r["pc"] for r in position] == ([6, 14] if mask & 2 else [])
            assert state["observation"]["helper_calls"] == (6 if mask & 1 else 3 if mask & 2 else 0)
            assert state["observation"]["eligible"] == len(retire) + len(position)
            for record in records["events"]:
                pc = record["pc"]
                assert record["bytes"] == list(MIXED[pc:pc + MIXED_WIDTHS[pc]])
                assert record["opcode"] == MIXED[pc]
                assert record["next_pc"] == pc + MIXED_WIDTHS[pc]
                assert record["retired"] == MIXED_PCS.index(pc) + 1
            if position:
                assert position[0]["actor"] == position[1]["actor"] == 0
                assert position[0]["before"] == {"x": 0, "y": 0, "prev_x": 0, "prev_y": 0}
                assert position[0]["after"] == position[1]["before"] == {
                    "x": 5, "y": 6, "prev_x": 5, "prev_y": 6,
                }
                assert position[1]["after"] == {"x": 10, "y": 20, "prev_x": 10, "prev_y": 20}
    assert all(value == states[0] for value in states.values())
    assert states[0]["variables"][1:3] == [10, 20]
    assert states[0]["actors"][0] == {"id": 0, "x": 10, "y": 20, "prev_x": 10, "prev_y": 20}
    assert observations[0] == []
    for bit, kind in ((1, "retire"), (2, "position")):
        assert [payload(r) for r in observations[bit]] == [
            payload(r) for r in observations[3] if r["kind"] == kind
        ]


@pytest.mark.parametrize("mask", [0, 1, 2, 3])
@pytest.mark.parametrize("same_variable", [False, True])
def test_native_get_position_preserves_unclamped_actor_and_ordered_alias(native_binary, mask, same_variable):
    # actor15 has the highest admitted ID; 255 stays 255 rather than clamping.
    code = bytes([37, 15, 255, 0, 39, 15, 5, 5 if same_variable else 6, 0])
    with QemuAGI(native_binary, code) as vm:
        vm.configure(mask=mask, capacity=16, step_budget=16)
        state = vm.run()
        records = vm.events()
        assert_source(vm, state, records, code)
        guest = state["guest"]
        assert guest["status"] == "return" and guest["fault"] is None
        assert guest["retired"] == 3 and guest["pc"] == len(code)
        expected_variables = [0] * 256
        expected_variables[5] = 0 if same_variable else 255
        assert guest["variables"] == expected_variables
        assert guest["flags"] == [0] * 256
        assert guest["actors"] == [
            {"id": i, "x": 255 if i == 15 else 0, "y": 0,
             "prev_x": 255 if i == 15 else 0, "prev_y": 0}
            for i in range(16)
        ]
        retire = [r for r in records["events"] if r["kind"] == "retire"]
        position = [r for r in records["events"] if r["kind"] == "position"]
        assert [r["pc"] for r in retire] == ([0, 4, 8] if mask & 1 else [])
        assert [r["pc"] for r in position] == ([0] if mask & 2 else [])
        assert state["observation"]["helper_calls"] == (3 if mask & 1 else 1 if mask & 2 else 0)


@pytest.mark.parametrize("opcode", range(1, 8))
@pytest.mark.parametrize("taken", [False, True])
def test_native_condition_results_and_control_trace_match_oracle(native_binary, opcode, taken):
    if opcode in (1, 2):
        value = 128 if taken else 127
    elif opcode in (3, 4):
        value = 127 if taken else 128
    else:
        value = 129 if taken else 128
    prefix = bytes([3, 1, value, 3, 2, 128, 12 if taken else 13, 7])
    terms = bytes([7, 7]) if opcode == 7 else bytes([opcode, 1, 2 if opcode % 2 == 0 else 128])
    code = prefix + b"\xff" + terms + b"\xff\x06\x00" + bytes.fromhex("03030afe030003031400")
    expected, pcs = scalar_oracle(code)
    with QemuAGI(native_binary, code) as vm:
        vm.configure(mask=1, capacity=128, step_budget=128)
        state = vm.run()
        records = vm.events()
        assert_source(vm, state, records, code)
        assert_scalar_result(state, expected, pcs)
        assert state["guest"]["variables"][3] == (10 if taken else 20)
        assert [record["pc"] for record in records["events"]] == pcs


@pytest.mark.parametrize("value,flag,last", [(5, True, 3), (0, False, 3), (0, True, 3), (5, False, 2)])
def test_native_ordered_boolean_group_results_match_oracle(native_binary, value, flag, last):
    prefix = bytes([3, 1, value, 3, 3, last, 12 if flag else 13, 7])
    terms = bytes.fromhex("fc010105fd0707fc050302")
    code = prefix + b"\xff" + terms + b"\xff\x06\x00" + bytes.fromhex("03020afe030003021400")
    expected, pcs = scalar_oracle(code)
    with QemuAGI(native_binary, code) as vm:
        vm.configure(mask=1, capacity=128, step_budget=128)
        state = vm.run()
        assert_scalar_result(state, expected, pcs)
        assert [record["pc"] for record in vm.events()["events"]] == pcs


def test_native_mid_session_mode_flips_visit_warm_pcs_without_reset(native_binary):
    # addn v1,1; position.v actor0,v1,v1; goto PC0. Three instructions per lap.
    code = bytes.fromhex("05010126000101fef6ff")
    with QemuAGI(native_binary, code) as vm:
        vm.configure(capacity=128, step_budget=9)
        last_generation = -1
        for segment, mask in enumerate((0, 1, 2, 3, 0, 3), start=1):
            before = guest_state(vm.state())
            vm.clear_events()
            vm.configure(mask=mask)
            assert guest_state(vm.state()) == before
            state = vm.run()
            records = vm.events()
            assert_source(vm, state, records, code)
            guest, observation = state["guest"], state["observation"]
            assert guest["status"] == "budget" and guest["fault"] is None
            assert guest["pc"] == 0 and guest["retired"] == segment * 9
            assert guest["variables"][1] == segment * 3
            assert guest["actors"][0] == {
                "id": 0, "x": segment * 3, "y": segment * 3,
                "prev_x": segment * 3, "prev_y": segment * 3,
            }
            assert state["run"]["retired"] == 9
            assert observation["control_generation"] > last_generation
            last_generation = observation["control_generation"]
            assert observation["helper_calls"] == (9 if mask & 1 else 3 if mask & 2 else 0)
            retire = [r for r in records["events"] if r["kind"] == "retire"]
            position = [r for r in records["events"] if r["kind"] == "position"]
            assert [r["pc"] for r in retire] == ([0, 3, 7] * 3 if mask & 1 else [])
            assert [r["pc"] for r in position] == ([3] * 3 if mask & 2 else [])
            assert all(r["control_generation"] == last_generation for r in records["events"])


def test_native_restart_retains_controls_and_code_but_resets_guest(native_binary):
    with QemuAGI(native_binary, MIXED) as vm:
        initial = guest_state(vm.state())
        vm.configure(mask=3, capacity=64, step_budget=128)
        first = vm.run()
        first_events = vm.events()
        vm.restart()
        restarted = vm.state()
        assert guest_state(restarted) == initial
        assert restarted["source"] == first["source"]
        assert restarted["observation"]["mask"] == 3
        assert restarted["observation"]["capacity"] == 64
        assert restarted["observation"]["count"] == restarted["observation"]["helper_calls"] == 0
        assert restarted["observation"]["epoch"] > first["observation"]["epoch"]
        second = vm.run()
        assert guest_state(first) == guest_state(second)
        assert [payload(r) for r in vm.events()["events"]] == [payload(r) for r in first_events["events"]]


@pytest.mark.parametrize("capacity", [0, 1, 2, 7, 8, 9])
def test_native_capacity_drops_new_events_without_stopping_guest(native_binary, capacity):
    with QemuAGI(native_binary, MIXED) as vm:
        vm.configure(mask=3, capacity=64, step_budget=128)
        full = vm.run()
        full_events = vm.events()["events"]
        assert len(full_events) == 8
        vm.restart()
        vm.configure(capacity=capacity)
        limited = vm.run()
        records = vm.events()["events"]
        observation = limited["observation"]
        assert guest_state(limited) == guest_state(full)
        assert observation["eligible"] == 8
        assert observation["count"] == min(capacity, 8) == len(records)
        assert observation["dropped"] == max(0, 8 - capacity)
        assert [payload(r) for r in records] == [payload(r) for r in full_events[:capacity]]
        for channel, kind, total in (("disasm", "retire", 6), ("scene", "position", 2)):
            stored = sum(record["kind"] == kind for record in records)
            assert observation["per_channel"][channel] == {
                "eligible": total, "stored": stored, "dropped": total - stored,
            }


def test_native_rejected_capacity_shrink_and_bad_controls_do_not_mutate_guest(native_binary):
    with QemuAGI(native_binary, MIXED) as vm:
        vm.configure(mask=3, capacity=64, step_budget=128)
        before = vm.run()
        records = vm.events()
        for name, value in (("agi-observation-capacity", 1),
                            ("agi-observation-capacity", 65537),
                            ("agi-observation-mask", 4), ("agi-step-budget", 0)):
            with pytest.raises(QMPError):
                vm.set(name, value)
            assert vm.state() == before
            assert vm.events() == records
        vm.clear_events()
        vm.configure(capacity=1)
        after = vm.state()
        assert guest_state(after) == guest_state(before)
        assert after["observation"]["count"] == 0
        assert after["observation"]["capacity"] == 1
        assert vm.events()["events"] == []


def test_native_qom_reads_and_writes_reject_while_cpu_runs(native_binary):
    code = bytes.fromhex("050101fefaff")
    with QemuAGI(native_binary, code, timeout=3.0) as vm:
        vm.configure(mask=0, capacity=0, step_budget=1_000_000_000)
        assert vm.state()["guest"]["status"] == "ready"
        try:
            vm.qmp("cont")
            assert vm.qmp("query-status")["running"] is True
            # Bypass the harness's own stopped check: this tests the target.
            for name in ("agi-state-json", "agi-events-json"):
                with pytest.raises(QMPError, match="stopped|running"):
                    vm.qmp("qom-get", {"path": vm.cpu_path, "property": name})
            with pytest.raises(QMPError, match="stopped|running"):
                vm.qmp("qom-set", {
                    "path": vm.cpu_path, "property": "agi-observation-mask", "value": 3,
                })
        finally:
            vm.qmp("stop")
        assert vm.qmp("query-status")["running"] is False
        assert vm.state()["observation"]["mask"] == 0


def test_native_capacity_growth_preserves_prefix_and_exposes_sequence_gap(native_binary):
    code = bytes.fromhex("050101fefaff")
    with QemuAGI(native_binary, code) as vm:
        vm.configure(mask=1, capacity=1, step_budget=4)
        first = vm.run()
        prefix = vm.events()["events"]
        assert len(prefix) == 1
        assert first["observation"]["eligible"] == 4
        assert first["observation"]["dropped"] == 3
        vm.configure(capacity=4, step_budget=2)
        second = vm.run()
        records = vm.events()["events"]
        assert records[:1] == prefix and len(records) == 3
        assert records[1]["seq"] - records[0]["seq"] == 4
        assert records[2]["seq"] - records[1]["seq"] == 1
        assert [record["retired"] for record in records] == [1, 5, 6]
        assert second["guest"]["retired"] == 6
        assert second["guest"]["variables"][1] == 3
        assert second["observation"]["eligible"] == 6
        assert second["observation"]["count"] == 3
        assert second["observation"]["dropped"] == 3
        assert second["observation"]["per_channel"] == {
            "disasm": {"eligible": 6, "stored": 3, "dropped": 3},
            "scene": {"eligible": 0, "stored": 0, "dropped": 0},
        }


@pytest.mark.parametrize("code,status", [(b"\x00", "return"), (b"\x18", "fault")])
def test_native_terminal_stop_is_sticky_without_false_retirements(native_binary, code, status):
    with QemuAGI(native_binary, code, timeout=3.0) as vm:
        vm.configure(mask=3, capacity=16, step_budget=16)
        first = vm.run()
        records = vm.events()
        assert first["guest"]["status"] == status
        second = vm.run()
        assert guest_state(second) == guest_state(first)
        assert second["run"]["retired"] == 0
        assert second["run"]["elapsed_ns"] == 0
        assert second["run"]["invocation"] > first["run"]["invocation"]
        assert second["observation"] == first["observation"]
        assert vm.events() == records


@pytest.mark.parametrize("mask", [0, 1, 2, 3])
@pytest.mark.parametrize("code,fault_name,fault_pc,retired", [
    (bytes.fromhex("03010718"), "unsupported_opcode", 3, 1),
    (bytes.fromhex("0301"), "truncated_instruction", 0, 0),
    (bytes.fromhex("2510010200"), "invalid_actor", 0, 0),
    (bytes.fromhex("fefe7f"), "invalid_branch_target", 0, 0),
    (bytes.fromhex("ff0800ff000000"), "unsupported_condition", 0, 0),
    (bytes.fromhex("030109"), "fetch_out_of_bounds", 3, 1),
    (b"\xff" + bytes([7, 0]) * 9 + b"\xff\x00\x00\x00", "condition_limit", 0, 0),
    (bytes.fromhex("fffdfd0700ff000000"), "unsupported_condition", 0, 0),
])
def test_native_faults_do_not_emit_false_retirement(native_binary, mask, code, fault_name, fault_pc, retired):
    with QemuAGI(native_binary, code) as vm:
        vm.configure(mask=mask, capacity=64, step_budget=128)
        state = vm.run()
        records = vm.events()
        assert_source(vm, state, records, code)
        assert state["guest"]["status"] == "fault"
        assert state["guest"]["fault"]["name"] == fault_name
        assert state["guest"]["fault"]["pc"] == fault_pc
        assert state["guest"]["retired"] == retired
        assert state["run"]["retired"] == retired
        assert len(records["events"]) == (retired if mask & 1 else 0)
        assert all(record["kind"] == "retire" and record["pc"] != fault_pc
                   for record in records["events"])
        assert state["guest"]["variables"][1] == (code[2] if retired else 0)


def test_native_untaken_out_of_range_if_target_does_not_fault(native_binary):
    # v1 starts zero: true condition falls through; only the unused skip is huge.
    code = bytes.fromhex("ff010100ffff7f00")
    expected, pcs = scalar_oracle(code)
    with QemuAGI(native_binary, code) as vm:
        vm.configure(mask=3, capacity=16, step_budget=128)
        state = vm.run()
        assert_scalar_result(state, expected, pcs)
        assert [r["pc"] for r in vm.events()["events"]] == pcs


@pytest.mark.parametrize("code", [
    bytes.fromhex("ff010101ff0080") + bytes(32769),
    bytes.fromhex("fe0300000000fefaff"),
], ids=["unsigned-if-32768-byte-skip", "signed-backward-goto"])
def test_native_if_skip_is_unsigned_and_goto_is_signed(native_binary, code):
    expected, pcs = scalar_oracle(code)
    with QemuAGI(native_binary, code) as vm:
        vm.configure(mask=1, capacity=16, step_budget=128)
        state = vm.run()
        assert_scalar_result(state, expected, pcs)
        assert [r["pc"] for r in vm.events()["events"]] == pcs


def test_native_records_bind_source_and_are_detached_from_returned_json(native_binary):
    identities = []
    for literal in (7, 8):
        code = bytes([3, 1, literal, 0])
        with QemuAGI(native_binary, code) as vm:
            vm.configure(mask=1, capacity=16, step_budget=128)
            state = vm.run()
            records = vm.events()
            assert_source(vm, state, records, code)
            identities.append(records["source"]["sha256"])
            retained = deepcopy(records)
            records["events"][0]["bytes"][2] = 255
            records["source"]["sha256"] = "0" * 64
            assert vm.events() == retained
            assert vm.state() == state
    assert identities[0] != identities[1]
