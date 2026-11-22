"""Compact scene capture boundaries and explicit, authored native acceptance.

Host tests fake only QOM payloads. Native tests need an explicitly selected
candidate; they reuse the production engine, decoder and compositor.
"""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest


NATIVE = Path(__file__).resolve().parents[1] / "native/qemu-agi"


def load(name):
    key = "_fdisbull_agi_" + name
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, NATIVE / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


pack, harness = load("runtime_pack"), load("runtime_harness")


@pytest.fixture
def boundary():
    class Boundary(harness.QemuAGIRuntime):
        def __init__(self):
            self.package_sha256 = "a" * 64
            self.binary_sha256 = "b" * 64
            self.context_id = "owner-one"
            self._logic_hashes = {0: "c" * 64, 1: "d" * 64}
            self._logic_sizes = {0: 100, 1: 100}
            self._view_hashes = {3: "e" * 64}
            self.calls = []
            self.after_event = None
            self.compact = {
                "schema": harness.CHECKPOINT_SCHEMA,
                "source": {"sha256": self.package_sha256, "profile": harness.PROFILE,
                           "logic_id": 0, "logic_sha256": self._logic_hashes[0]},
                "guest": {"logic": 0, "pc": 0, "status": "ready", "retired": 0,
                          "scene_revision": 0, "presentation_revision": 0,
                          "cycle_count": 0, "cycle_active": 0, "clock_ticks": 0,
                          "ticks": 0, "input_enabled": 1, "cycle_delay": 2,
                          "fault": None, "pending_effect": None,
                          "state_bytes_sha256": "f" * 64, "state_bytes_size": 123456,
                          "state_encoding": "agi-runtime-native-abi-1"},
                "observation": {"mask": 2, "capacity": 4096, "limit": 65536,
                                "count": 0, "eligible": 0, "dropped": 0,
                                "helper_calls": 0, "epoch": 1,
                                "per_channel": {name: {"stored": 0, "eligible": 0, "dropped": 0}
                                                for name in ("disasm", "scene")}},
                "run": {"retired": 0},
            }
            self.scene = {"width": 160, "height": 168, "picture_shown": 0,
                          "background_evidence_required": "complete_scene_journal",
                          "order_validation": "current_actor_state", "draw_order": [5],
                          "actors": [{"id": 5, "view": 3, "loop": 0, "cel": 0,
                                      "x": 10, "y": 90, "priority": 7, "width": 2,
                                      "height": 2, "drawn": True, "view_sha256": "e" * 64}]}

        def _json_property(self, name):
            self.calls.append(name)
            value = deepcopy(self.compact)
            if name == "agi-runtime-checkpoint-json":
                return value
            if name == "agi-runtime-scene-inputs-json":
                value.update(schema=harness.SCENE_INPUTS_SCHEMA, scene=deepcopy(self.scene))
                return value
            if name == "agi-events-json":
                value = {"schema": harness.EVENTS_SCHEMA, "source": value["source"],
                         "epoch": value["observation"]["epoch"],
                         "observation": value["observation"], "events": []}
                if self.after_event is not None:
                    self.after_event(value)
                return value
            raise AssertionError(name)

        def state(self):
            self.calls.append("full-state")
            return {"schema": harness.STATE_SCHEMA, "observation": deepcopy(self.compact["observation"])}

        def set(self, name, value):
            self.calls.append((name, json.loads(value)))

        def _run_stopped(self, *, step_budget=None):
            self.calls.append(("run-stopped", step_budget))

    return Boundary()


def test_checkpoint_and_scene_inputs_bind_owner_and_current_logic(boundary):
    cp = boundary.checkpoint()
    assert cp["owner"] == {"context": "owner-one", "binary_sha256": "b" * 64}
    scene = boundary.scene_inputs()
    assert scene["scene"]["draw_order"] == [5]
    assert scene["guest"] == cp["guest"] and scene["source"] == cp["source"]
    assert "full-state" not in boundary.calls
    boundary.compact["source"].update(logic_id=1, logic_sha256="d" * 64)
    with pytest.raises(harness.HarnessError, match="LOGIC differs"):
        boundary.checkpoint()


@pytest.mark.parametrize("mutation", [
    lambda cp: cp["guest"].update(retired=True),
    lambda cp: cp["guest"].update(cycle_delay=256),
    lambda cp: cp["guest"].update(state_bytes_sha256="0" * 63),
    lambda cp: cp["guest"].pop("fault"),
    lambda cp: cp["observation"].update(count=1),
    lambda cp: cp["observation"]["per_channel"]["scene"].update(eligible=1),
    lambda cp: cp["run"].update(retired=-1),
])
def test_compact_checkpoint_rejects_incoherent_native_boundary(boundary, mutation):
    mutation(boundary.compact)
    with pytest.raises(harness.HarnessError):
        boundary.checkpoint()


@pytest.mark.parametrize("mutation", [
    lambda scene: scene.update(draw_order=[True]),
    lambda scene: scene.update(draw_order=[]),
    lambda scene: scene["actors"][0].update(view_sha256="0" * 64),
    lambda scene: scene["actors"][0].update(drawn=1),
    lambda scene: scene["actors"][0].update(x=159),
    lambda scene: scene["actors"][0].update(y=0),
])
def test_scene_inputs_rejects_wrong_order_resource_or_extent(boundary, mutation):
    mutation(boundary.scene)
    with pytest.raises(harness.HarnessError):
        boundary.scene_inputs()


@pytest.mark.parametrize("method,args", [("clock", (2,)), ("cycle", ()), ("run", ())])
@pytest.mark.parametrize("capture,expected", [(None, None), ("checkpoint", harness.CHECKPOINT_SCHEMA),
                                             ("state", harness.STATE_SCHEMA)])
def test_capture_selection_is_explicit_and_preserves_default(boundary, method, args, capture, expected):
    result = getattr(boundary, method)(*args, capture=capture)
    assert result is None if expected is None else result["schema"] == expected
    assert ("full-state" in boundary.calls) == (capture == "state")
    assert ("agi-runtime-checkpoint-json" in boundary.calls) == (capture == "checkpoint")
    if method == "run":
        assert boundary.calls[0] == ("run-stopped", None)


@pytest.mark.parametrize("method", ["clock", "cycle", "run"])
def test_invalid_capture_is_refused_before_mutation(boundary, method):
    for capture in (False, 1, "scene", []):
        with pytest.raises(ValueError, match="capture"):
            getattr(boundary, method)(capture=capture)
    assert not boundary.calls
    assert getattr(boundary, method)()["schema"] == harness.STATE_SCHEMA


def test_events_use_compact_coherent_bracket_and_refuse_stale_owner(boundary):
    cp = boundary.checkpoint()
    boundary.calls.clear()
    assert boundary.events(checkpoint=cp)["events"] == []
    assert boundary.calls == ["agi-runtime-checkpoint-json", "agi-events-json", "agi-runtime-checkpoint-json"]
    stale = deepcopy(cp)
    stale["owner"]["context"] = "another-child"
    with pytest.raises(harness.HarnessError, match="stale"):
        boundary.events(checkpoint=stale)
    boundary.after_event = lambda event: event["source"].update(logic_id=1, logic_sha256="d" * 64)
    with pytest.raises(harness.HarnessError, match="coherent"):
        boundary.events(checkpoint=cp)


def test_events_refuse_loss_and_oversized_batches_before_transfer(boundary):
    obs = boundary.compact["observation"]
    obs.update(eligible=1, dropped=1)
    obs["per_channel"]["scene"].update(eligible=1, dropped=1)
    cp = boundary.checkpoint()
    boundary.calls.clear()
    with pytest.raises(harness.HarnessError, match="dropped records"):
        boundary.events(checkpoint=cp)
    assert "agi-events-json" not in boundary.calls
    assert boundary.events(checkpoint=cp, allow_dropped=True)["events"] == []
    obs.update(capacity=4097, count=4097, eligible=4097, dropped=0)
    obs["per_channel"]["scene"].update(stored=4097, eligible=4097, dropped=0)
    cp = boundary.checkpoint()
    boundary.calls.clear()
    with pytest.raises(harness.HarnessError, match="at most 4096"):
        boundary.events(checkpoint=cp)
    assert "agi-events-json" not in boundary.calls


def test_events_detect_mutation_during_capture(boundary):
    cp = boundary.checkpoint()
    boundary.after_event = lambda event: boundary.compact["guest"].update(clock_ticks=1)
    with pytest.raises(harness.HarnessError, match="coherent"):
        boundary.events(checkpoint=cp)


@pytest.fixture(scope="module")
def binary():
    configured = os.environ.get("FDISBULL_QEMU_AGI")
    if not configured:
        pytest.skip("native compact acceptance requires explicit FDISBULL_QEMU_AGI")
    path = Path(configured).expanduser().resolve()
    assert path.is_file() and os.access(path, os.X_OK)
    expected = os.environ.get("FDISBULL_QEMU_AGI_EXPECTED_SHA256")
    if expected:
        assert sha256(path.read_bytes()).hexdigest() == expected
    return path


def authored(code=b"\0", messages=(), views=()):
    return pack.build_package(logics=[{"id": 0, "code": code, "messages": list(messages)}], views=list(views))


def assert_checkpoint_matches(cp, full):
    assert cp["source"] == full["source"]
    assert cp["observation"] == full["observation"]
    assert cp["run"] == full["run"]
    for field, value in cp["guest"].items():
        expected = full["guest"]["variables"][10] if field == "cycle_delay" else full["guest"][field]
        assert value == expected, field
    assert not set(cp["guest"]) & {"actors", "script", "variables", "picture_visual_hex", "picture_priority_hex", "state_bytes_hex"}


@pytest.mark.parametrize("code,messages,budget,status", [
    (bytes([1, 50, 0]), (), 1, "budget"),
    (bytes([1, 50, 0]), (), 10, "return"),
    (bytes([101, 1, 0]), ("Authored prompt",), 10, "pending"),
    (bytes([255]), (), 10, "fault"),
])
def test_native_compact_preserves_actual_stop_and_architectural_digest(binary, code, messages, budget, status):
    with harness.QemuAGIRuntime(binary, authored(code, messages), timeout=20) as vm:
        assert_checkpoint_matches(vm.checkpoint(), vm.state())
        cp = vm.run(step_budget=budget, capture="checkpoint")
        assert cp["guest"]["status"] == status
        assert_checkpoint_matches(cp, vm.state())
        assert vm.checkpoint() == cp


def test_native_scene_inputs_share_order_and_are_observation_neutral(binary, monkeypatch):
    # Stationary actor20 precedes fixed-priority actor3 and tied updating1/2.
    view = bytes([0, 0, 1, 0, 0, 7, 0, 1, 3, 0, 2, 2, 15, 0x22, 0, 0x22, 0])
    code = bytearray([30, 1])
    for actor, x, y in ((20, 10, 90), (2, 20, 80), (1, 30, 80), (3, 40, 100)):
        code.extend([33, actor, 37, actor, x, y, 41, actor, 1, 35, actor])
    code.extend([58, 20, 54, 3, 4, 0])
    data = authored(bytes(code), views=[{"id": 1, "data": view}])
    guests, planes = [], []
    for mask in range(4):
        with harness.QemuAGIRuntime(binary, data, timeout=20) as vm:
            vm.configure(mask=mask, capacity=4096, step_budget=100)
            cp = vm.run(capture="checkpoint")
            full = vm.state()
            assert_checkpoint_matches(cp, full)
            before_events = vm.events(checkpoint=cp)
            scene = vm.scene_inputs()
            assert scene["scene"]["draw_order"] == [20, 3, 1, 2]
            assert [actor["id"] for actor in scene["scene"]["actors"]] == [20, 3, 1, 2]
            assert all(actor["view_sha256"] == sha256(view).hexdigest() for actor in scene["scene"]["actors"])
            native = vm.scene()  # independent acceptance control only, never builder input
            assert vm.checkpoint() == cp and vm.state() == full
            assert vm.events(checkpoint=cp) == before_events
            assert len(json.dumps(scene)) < 8000
            assert len(json.dumps(cp)) < 4000
            guests.append(full["guest"])
            planes.append((native["visual"], native["priority"]))
            # No full state serialization for an explicitly compact steady state.
            monkeypatch.setattr(vm, "state", lambda: pytest.fail("full state queried"))
            vm.clock(2, capture=None)
            vm.cycle(capture=None)
            assert vm.run(capture="checkpoint")["guest"]["status"] == "return"
    assert all(guest == guests[0] for guest in guests[1:])
    assert all(plane == planes[0] for plane in planes[1:])


def test_native_compact_journal_retained_until_final_capture_and_loss_is_explicit(binary):
    data = authored(bytes([3, 50, 1, 24, 50, 25, 50, 0]))  # load/draw.pic from v50 each cycle
    data["pictures"] = [{"id": 1, "data": "ff", "sha256": sha256(b"\xff").hexdigest()}]
    with harness.QemuAGIRuntime(binary, data, timeout=20) as vm:
        vm.configure(mask=2, capacity=4096, step_budget=100)
        for _ in range(3):
            vm.clock(2, capture=None)
            vm.cycle(capture=None)
            cp = vm.run(capture="checkpoint")
        events = vm.events(checkpoint=cp)
        assert cp["observation"]["per_channel"]["disasm"]["stored"] == 0
        assert len(events["events"]) == cp["observation"]["per_channel"]["scene"]["eligible"]
        assert sum(event["opcode"] == 25 for event in events["events"]) == 3
        assert [event["seq"] for event in events["events"]] == list(range(1, len(events["events"]) + 1))
        old = cp
        vm.clear_events()
        with pytest.raises(harness.HarnessError, match="stale"):
            vm.events(checkpoint=old)
    with harness.QemuAGIRuntime(binary, data, timeout=20) as vm:
        vm.configure(mask=3, capacity=1, step_budget=100)
        cp = vm.run(capture="checkpoint")
        with pytest.raises(harness.HarnessError, match="dropped records"):
            vm.events(checkpoint=cp)
        assert len(vm.events(checkpoint=cp, allow_dropped=True)["events"]) == 1
