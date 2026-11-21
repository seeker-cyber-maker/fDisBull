"""Authored native acceptance for the explicit AGI draw-intent profile.

The catalog, bytecode and expected states below are authored independently of
the production resource decoder and scene collector. No original game bytes
are used. Native execution requires an explicit FDISBULL_QEMU_AGI_INTENT;
this module never discovers, builds or replaces a runtime.

A complete run permits at most 36 owned children and 120 seconds of wall time,
with 5-second QMP deadlines and at most 128 retirements per invocation. The
current matrix uses 30 children. The two TCG logs are read only below 2 MiB
each; retained harness diagnostics are bounded to 1 MiB plus the small authored
catalog per child. The enclosing runner must enforce the same wall deadline.
Failures are retained and are never automatically retried by this module.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "native" / "qemu-agi"))
from draw_intent_harness import QemuAGIDrawIntent, intent_guest_state
from harness import HarnessError, QemuAGI
from visual_binding_harness import QemuAGIViewBinding, binding_guest_state


PROFILE = "agi-2917-draw-intent-pilot-1"
STATE_SCHEMA = "fdisbull-agi-intent-state-1"
EVENTS_SCHEMA = "fdisbull-agi-intent-events-1"

# One authored VIEW 10, one loop, one 2x3 cel, with an explicit horizon of 5.
# This directly assembles the documented FDBAGIV1 format; no VIEW parser runs.
CATALOG = (b"FDBAGIV1" + bytes((5, 0, 1, 0, 10, 1))
           + hashlib.sha256(b"authored-draw-intent-view-10").digest()
           + bytes((1, 2, 3)))


def actor(index=0, **changed):
    value = {
        "id": index, "x": 0, "y": 0, "prev_x": 0, "prev_y": 0,
        "view_bound": False, "view": 0, "loop": 0, "cel": 0,
        "width": 0, "height": 0, "animated": False, "update": False,
        "cycling": False, "ignore_horizon": False, "update_pos": False,
        "view_replaced": False, "motion": "normal", "cycle": "normal",
        "direction": 0,
    }
    value.update(changed)
    return value


def pending_draw(pc, number=0):
    return {
        "kind": "draw", "reason": "draw_requires_host", "pc": pc,
        "opcode": 35, "bytes": [35, number], "actor": number,
        "retired": False, "committed": False, "completion_available": False,
    }


def assert_descriptor(state, pc, number=0):
    pending = state["guest"]["pending_effect"]
    assert pending == pending_draw(pc, number)
    assert all(pending[key] is False for key in (
        "retired", "committed", "completion_available"))
    assert type(pending["pc"]) is type(pending["opcode"]) is type(pending["actor"]) is int
    assert all(type(value) is int for value in pending["bytes"])


@pytest.fixture(scope="module")
def native_launch():
    configured = os.environ.get("FDISBULL_QEMU_AGI_INTENT")
    if not configured:
        pytest.skip("native intent acceptance requires explicit FDISBULL_QEMU_AGI_INTENT")
    binary = Path(configured).expanduser().resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        pytest.fail("FDISBULL_QEMU_AGI_INTENT must name an executable candidate binary")
    evidence = os.environ.get("FDISBULL_QEMU_AGI_EVIDENCE")
    started, children = time.monotonic(), 0

    @contextmanager
    def launch(code, *, profile="intent", extra_args=()):
        nonlocal children
        assert children < 36, "authored native intent child budget exhausted"
        assert time.monotonic() - started < 120, "authored native intent wall budget exhausted"
        assert profile in {"intent", "binding", "scalar"}
        children += 1
        options = {"timeout": 5, "evidence_dir": evidence, "extra_args": extra_args}
        if profile == "intent":
            vm = QemuAGIDrawIntent(binary, code, CATALOG, **options)
        elif profile == "binding":
            vm = QemuAGIViewBinding(binary, code, CATALOG, **options)
        else:
            vm = QemuAGI(binary, code, **options)
        with vm:
            yield vm
        assert time.monotonic() - started < 120, "authored native intent wall budget exhausted"

    return launch


def test_native_intent_identity_initial_state_and_startup_only_selection(native_launch):
    code = bytes((71, 15, 0))
    with native_launch(code) as vm:
        initial = vm.state()
        assert initial["schema"] == STATE_SCHEMA
        assert initial["source"] == {
            "sha256": hashlib.sha256(code).hexdigest(), "size": len(code),
            "logic_id": 0, "profile": PROFILE,
            "catalog_sha256": hashlib.sha256(CATALOG).hexdigest(),
        }
        assert initial["catalog"] == {
            "sha256": hashlib.sha256(CATALOG).hexdigest(), "size": len(CATALOG),
            "view_count": 1, "loop_count": 1, "cel_count": 1, "horizon": 5,
        }
        guest = initial["guest"]
        assert guest["pc"] == guest["retired"] == 0
        assert guest["status"] == "ready" and guest["fault"] is None
        assert guest["pending_effect"] is None
        assert guest["actors"] == [actor(i) for i in range(16)]
        assert guest["variables"] == guest["flags"] == [0] * 256
        assert guest["loaded_views"] == [] and guest["horizon"] == 5
        events = vm.events()
        assert events["schema"] == EVENTS_SCHEMA
        assert events["source"] == initial["source"] and events["events"] == []
        with pytest.raises(HarnessError):
            binding_guest_state(initial)
        assert vm.qmp("qom-get", {"path": "/machine", "property": "draw-intent"}) is True
        with pytest.raises(HarnessError):
            vm.qmp("qom-set", {"path": "/machine", "property": "draw-intent", "value": False})
        assert vm.state() == initial
        vm.configure(mask=0, capacity=0, step_budget=128)
        result = vm.run()
        assert result["guest"]["status"] == "return"
        assert result["guest"]["actors"][15] == actor(15, cycling=True)
        assert result["guest"]["pending_effect"] is None


def test_native_draw_intent_requires_catalog_at_startup(native_launch):
    with pytest.raises(HarnessError):
        with native_launch(b"\0", profile="scalar",
                           extra_args=("-M", "agi-test,draw-intent=on")):
            pytest.fail("draw-intent startup without a catalog unexpectedly succeeded")


def test_native_cycle_controls_are_pure_and_animation_reset_is_explicit(native_launch):
    code = bytes((70, 15, 71, 15, 71, 15, 70, 15, 70, 15,
                  33, 15, 70, 15, 33, 15, 0))
    expected = [
        actor(15), actor(15, cycling=True), actor(15, cycling=True),
        actor(15), actor(15),
        actor(15, animated=True, update=True, cycling=True),
        actor(15, animated=True, update=True),
        actor(15, animated=True, update=True),
        actor(15, animated=True, update=True),
    ]
    with native_launch(code) as vm:
        vm.configure(mask=3, capacity=32, step_budget=1)
        for index, expected_actor in enumerate(expected):
            state = vm.run()
            assert state["guest"]["actors"] == [*[actor(i) for i in range(15)], expected_actor]
            assert state["guest"]["retired"] == index + 1
            assert state["run"]["retired"] == 1
            assert state["guest"]["pending_effect"] is None
        assert state["guest"]["status"] == "return"
        assert state["guest"]["variables"] == state["guest"]["flags"] == [0] * 256
        assert state["guest"]["loaded_views"] == []
        records = vm.events()["events"]
        assert [r["pc"] for r in records if r["kind"] == "retire"] == list(range(0, 17, 2))
        changes = [r for r in records if r["kind"] == "actor"]
        assert [r["pc"] for r in changes] == [2, 6, 10, 12]
        assert all(r["actor"] == 15 for r in changes)
        assert len(records) == 13
        for left, right in zip(changes, changes[1:]):
            assert left["after"] == right["before"]
        assert changes[0]["before"] == {k: v for k, v in actor(15).items() if k != "id"}
        assert changes[-1]["after"] == {k: v for k, v in expected[-1].items() if k != "id"}


@pytest.mark.parametrize("animated", [False, True], ids=["unanimated", "animated"])
@pytest.mark.parametrize("x,y", [(20, 80), (255, 0)], ids=["in-bounds", "uncorrected-position"])
def test_native_draw_defers_atomically_and_preserves_requested_pose(native_launch, animated, x, y):
    prefix = bytes((30, 10)) + (bytes((33, 0)) if animated else b"")
    prefix += bytes((41, 0, 10, 37, 0, x, y))
    pc, retired = len(prefix), 3 + int(animated)
    code = prefix + bytes((35, 0, 70, 0, 3, 200, 99, 0))
    with native_launch(code) as vm:
        vm.configure(mask=3, capacity=64, step_budget=retired)
        before = vm.run()
        before_events = vm.events()["events"]
        assert before["guest"]["status"] == "budget"
        assert before["guest"]["pc"] == pc and before["guest"]["retired"] == retired
        expected_actor = actor(
            x=x, y=y, prev_x=x, prev_y=y, view_bound=True, view=10,
            width=2, height=3, animated=animated, update=animated,
            cycling=animated, update_pos=True, view_replaced=True,
        )
        assert before["guest"]["actors"][0] == expected_actor
        after = vm.run(step_budget=1)
        assert after["guest"]["status"] == "effect"
        assert after["guest"]["fault"] is None
        assert_descriptor(after, pc)
        for field, value in before["guest"].items():
            if field not in {"status", "pending_effect"}:
                assert after["guest"][field] == value, field
        assert after["run"]["retired"] == 0
        assert after["guest"]["actors"][0] == expected_actor
        assert after["guest"]["variables"][200] == 0
        assert vm.events()["events"] == before_events
        assert len(before_events) == retired * 2
        for field in ("count", "eligible", "dropped", "helper_calls", "per_channel"):
            assert after["observation"][field] == before["observation"][field]


MASK_PROGRAM = bytes((
    30, 10, 33, 0, 41, 0, 10, 37, 0, 20, 80, 70, 0, 71, 0,
    35, 0, 3, 200, 99, 0,
))
MASK_PCS = [0, 2, 4, 7, 11, 13]


def test_native_pending_continue_clear_configure_and_restart(native_launch):
    with native_launch(MASK_PROGRAM) as vm:
        initial = vm.state()
        initial_guest = intent_guest_state(initial)
        vm.configure(mask=3, capacity=64, step_budget=128)
        pending = vm.run()
        pending_events = vm.events()
        assert pending["guest"]["status"] == "effect"
        assert_descriptor(pending, 15)
        assert pending["run"]["retired"] == 6
        # Direct continuation is a complete no-op, including run clocks/counters.
        assert vm.run() == pending
        assert vm.events() == pending_events
        pending_guest = intent_guest_state(pending)
        copied = intent_guest_state(pending)
        copied["pending_effect"]["bytes"][1] = 15
        copied["actors"][0]["x"] = 99
        assert intent_guest_state(vm.state()) == pending_guest
        vm.clear_events()
        cleared = vm.state()
        assert intent_guest_state(cleared) == pending_guest
        assert cleared["observation"]["epoch"] > pending["observation"]["epoch"]
        assert vm.events()["events"] == []
        vm.configure(mask=0, capacity=0, step_budget=1)
        configured = vm.state()
        assert intent_guest_state(configured) == pending_guest
        assert vm.run() == configured
        assert vm.events()["events"] == []
        vm.restart()
        reset = vm.state()
        assert intent_guest_state(reset) == initial_guest
        assert reset["source"] == initial["source"] and reset["catalog"] == initial["catalog"]
        vm.configure(mask=3, capacity=64, step_budget=128)
        replayed = vm.run()
        assert intent_guest_state(replayed) == pending_guest
        assert_descriptor(replayed, 15)


def test_native_all_observation_masks_preserve_complete_pending_guest(native_launch):
    states, journals = {}, {}
    with native_launch(MASK_PROGRAM) as vm:
        for mask in (0, 1, 2, 3):
            if mask:
                vm.restart()
            vm.configure(mask=mask, capacity=64, step_budget=128)
            state = vm.run()
            states[mask] = intent_guest_state(state)
            rows = vm.events()["events"]
            journals[mask] = rows
            assert_descriptor(state, 15)
            assert state["guest"]["status"] == "effect"
            assert state["guest"]["retired"] == 6 and state["guest"]["pc"] == 15
            assert state["guest"]["variables"][200] == 0
            assert state["guest"]["actors"][0] == actor(
                x=20, y=80, prev_x=20, prev_y=80, view_bound=True, view=10,
                width=2, height=3, animated=True, update=True, cycling=True,
                update_pos=True, view_replaced=True,
            )
            assert [r["pc"] for r in rows if r["kind"] == "retire"] == (MASK_PCS if mask & 1 else [])
            assert [r["pc"] for r in rows if r["kind"] != "retire"] == (MASK_PCS if mask & 2 else [])
            assert all(r["opcode"] != 35 for r in rows)
            assert state["observation"]["helper_calls"] == (6 if mask else 0)
            assert state["observation"]["count"] == state["observation"]["eligible"] == len(rows)
            assert state["observation"]["dropped"] == 0
        assert states[0] == states[1] == states[2] == states[3]
        normalize = lambda rows: [{k: v for k, v in r.items()
                                   if k not in {"seq", "control_generation"}} for r in rows]
        assert normalize(journals[1]) == normalize([r for r in journals[3] if r["kind"] == "retire"])
        assert normalize(journals[2]) == normalize([r for r in journals[3] if r["kind"] != "retire"])


@pytest.mark.parametrize("capacity", [0, 1])
def test_native_pending_request_survives_observation_saturation(native_launch, capacity):
    with native_launch(MASK_PROGRAM) as vm:
        vm.configure(mask=3, capacity=capacity, step_budget=128)
        state = vm.run()
        assert_descriptor(state, 15)
        assert state["guest"]["status"] == "effect" and state["guest"]["retired"] == 6
        assert state["guest"]["actors"][0]["cycling"] is True
        assert state["guest"]["loaded_views"] == [10]
        assert state["guest"]["variables"][200] == 0
        assert state["observation"]["count"] == capacity
        assert state["observation"]["eligible"] == 12
        assert state["observation"]["dropped"] == 12 - capacity
        assert state["observation"]["per_channel"] == {
            "disasm": {"eligible": 6, "stored": capacity, "dropped": 6 - capacity},
            "scene": {"eligible": 6, "stored": 0, "dropped": 6},
        }
        rows = vm.events()["events"]
        assert len(rows) == capacity
        if capacity:
            assert rows[0]["kind"] == "retire" and rows[0]["pc"] == 0


FAULT_PREFIX = bytes((30, 10, 33, 0, 37, 0, 10, 80, 41, 0, 10))
FAULT_CASES = [
    (bytes((35, 16)), "invalid_actor", 3),
    (bytes((35, 255)), "invalid_actor", 3),
    (bytes((35, 1)), "view_unbound", 10),
    (bytes((70, 16)), "invalid_actor", 3),
    (bytes((70, 255)), "invalid_actor", 3),
    (bytes((71, 16)), "invalid_actor", 3),
    (bytes((71, 255)), "invalid_actor", 3),
    (bytes((35,)), "truncated_instruction", 2),
    (bytes((70,)), "truncated_instruction", 2),
    (bytes((71,)), "truncated_instruction", 2),
    (bytes((36, 0)), "unsupported_opcode", 1),
]


@pytest.mark.parametrize("instruction,name,number", FAULT_CASES,
                         ids=[f"{row[0].hex()}-{row[1]}" for row in FAULT_CASES])
def test_native_intent_faults_are_atomic(native_launch, instruction, name, number):
    # No appended return: a one-byte instruction is genuinely truncated at EOF.
    code = FAULT_PREFIX + instruction
    with native_launch(code) as vm:
        vm.configure(mask=3, capacity=32, step_budget=4)
        before = vm.run()
        events = vm.events()["events"]
        assert before["guest"]["status"] == "budget"
        assert before["guest"]["pc"] == 11 and before["guest"]["retired"] == 4
        after = vm.run(step_budget=1)
        assert after["guest"]["status"] == "fault"
        assert after["guest"]["fault"] == {
            "code": number, "name": name, "pc": 11, "opcode": instruction[0],
        }
        assert after["guest"]["pending_effect"] is None
        assert after["run"]["retired"] == 0
        for field, value in before["guest"].items():
            if field not in {"status", "fault"}:
                assert after["guest"][field] == value, field
        assert vm.events()["events"] == events
        for field in ("count", "eligible", "dropped", "helper_calls", "per_channel"):
            assert after["observation"][field] == before["observation"][field]


@pytest.mark.parametrize("profile", ["scalar", "binding"])
@pytest.mark.parametrize("opcode", [35, 70, 71])
def test_native_prior_profiles_refuse_new_operations_without_schema_changes(native_launch, profile, opcode):
    code = bytes((37, 0, 10, 20, opcode, 0, 0))
    with native_launch(code, profile=profile) as vm:
        vm.configure(mask=3, capacity=16, step_budget=128)
        state, events = vm.run(), vm.events()
        prefix = "native" if profile == "scalar" else "binding"
        assert state["schema"] == f"fdisbull-agi-{prefix}-state-1"
        assert events["schema"] == f"fdisbull-agi-{prefix}-events-1"
        expected_source = {
            "sha256": hashlib.sha256(code).hexdigest(), "size": len(code), "logic_id": 0,
            "profile": "agi-2917-scalar-position-pilot-1" if profile == "scalar"
                       else "agi-2917-view-binding-pilot-1",
        }
        if profile == "binding":
            expected_source["catalog_sha256"] = hashlib.sha256(CATALOG).hexdigest()
        assert state["source"] == events["source"] == expected_source
        assert "pending_effect" not in state["guest"]
        assert state["guest"]["status"] == "fault"
        assert state["guest"]["fault"] == {
            "code": 1, "name": "unsupported_opcode", "pc": 4, "opcode": opcode,
        }
        assert state["guest"]["retired"] == 1 and state["guest"]["pc"] == 4
        expected_actor = ({"id": 0, "x": 10, "y": 20, "prev_x": 10, "prev_y": 20}
                          if profile == "scalar" else actor(x=10, y=20, prev_x=10, prev_y=20))
        assert state["guest"]["actors"][0] == expected_actor
        assert [r["kind"] for r in events["events"]] == [
            "retire", "position" if profile == "scalar" else "actor"]
        with pytest.raises(HarnessError):
            intent_guest_state(state)


def test_native_intent_zero_mask_omits_diagnostics_with_positive_tcg_control(native_launch, tmp_path):
    code = bytes((30, 10, 33, 0, 70, 0, 71, 0, 41, 0, 10, 35, 0, 0))
    guests = {}
    for mask in (0, 3):
        log = tmp_path / f"intent-mask-{mask}.tcg.log"
        with native_launch(code, extra_args=("-d", "op", "-D", str(log))) as vm:
            vm.configure(mask=mask, capacity=32, step_budget=128)
            state = vm.run()
            guests[mask] = intent_guest_state(state)
            assert_descriptor(state, 11)
            assert state["guest"]["status"] == "effect" and state["guest"]["retired"] == 5
            assert state["observation"]["helper_calls"] == (5 if mask else 0)
        assert 0 < log.stat().st_size <= 2 * 1024 * 1024
        content = log.read_text(encoding="utf-8")
        helpers = {name: len(re.findall(r"\bcall\s+" + name + r"\b", content))
                   for name in ("agi_observe", "agi_binding", "agi_draw", "agi_retire")}
        assert helpers["agi_binding"] == 5
        assert helpers["agi_draw"] == 1
        assert helpers["agi_retire"] == 5
        assert helpers["agi_observe"] == (5 if mask else 0)
    assert guests[0] == guests[3]
