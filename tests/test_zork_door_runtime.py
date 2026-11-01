"""Door effects against real Word16 execution of independently authored bytes.

Only the full-game constructor is bypassed. Memory, attributes, frame returns,
output, RNG, fault latching and checkpoints use the actual consumer methods.
The reference executes the raw fixture's lowered callback and both helpers.
"""
from __future__ import annotations

import copy
import itertools
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "player"))
from fdisbull_player.intent_runtime import _empty_stats
from fdisbull_player.scene_runtime import SceneRuntime, _stats
from fdisbull_player.word16 import MAX_FRAMES, MAX_STACK, MAX_TEXT, Word16Error, Word16Runtime
from fdisbull.zork_window import recover_window
from test_zork_window import make_window_fixture


RETURN_PC = 0xC00
CALLER_RETURN_PC = 0xC01


class PhysicalTrace:
    """Observe successful physical effects; optionally interrupt one seam."""
    def _before(self, kind, key):
        identity = (kind, key)
        self.effect_counts[identity] = self.effect_counts.get(identity, 0) + 1
        if self.fault_at == (kind, "before", key, self.effect_counts[identity]):
            raise Word16Error("authored effect fault before " + kind)

    def _after(self, kind, key):
        if self.fault_at == (kind, "after", key, self.effect_counts[(kind, key)]):
            raise Word16Error("authored effect fault after " + kind)

    def _write(self, address, width, value):
        self._before("write", address)
        super()._write(address, width, value)
        self.physical.append(("write", address, width, self._read(address, width)))
        self._after("write", address)

    def _emit(self, value):
        self._before("text", value)
        super()._emit(value)
        self.physical.append(("text", value))
        self._after("text", value)

    def _random(self, n):
        self._before("rng", n)
        result = super()._random(n)
        self.physical.append(("rng", n, result))
        self._after("rng", n)
        return result


class ReferenceRuntime(PhysicalTrace, Word16Runtime):
    pass


class DoorRuntime(PhysicalTrace, SceneRuntime):
    def _record_low_level_block(self, pc, binding=None):
        assert pc not in self.forbidden_source, "Recovered source mechanism executed again"
        return super()._record_low_level_block(pc, binding)


@pytest.fixture(scope="module")
def recovered_source():
    fixture = make_window_fixture()
    return fixture[1], recover_window(*fixture)


def clear_trace(runtime):
    runtime.physical.clear()
    runtime.effect_counts.clear()


def pair(recovered_source, *, action="open", is_open=False, order=(0, 1, 2),
         cursor=0, draw=1, store=4, tape=None):
    source, recovered = recovered_source
    program = copy.deepcopy(source)
    initial = bytes.fromhex(program["memory"]["initial"])
    for pc in (RETURN_PC, CALLER_RETURN_PC):
        program["blocks"][str(pc)] = {
            "guard": initial[pc:pc + 1].hex(), "next": pc + 1,
            "nodes": [{"op": "quit"}],
        }
    binding, document = recovered["udl"], recovered["uil"]
    repeat = is_open == (action == "open")
    if tape is None:
        tape = [{"range": 3 - cursor, "value": draw}] if repeat else []
    result = []
    for cls in (DoorRuntime, ReferenceRuntime):
        runtime = cls.__new__(cls)
        runtime.physical, runtime.effect_counts, runtime.fault_at = [], {}, None
        Word16Runtime.__init__(runtime, program, random_tape=tape)
        if cls is DoorRuntime:
            runtime.enable_scenes = runtime.enable_interactions = True
            runtime.enable_intents = False
            runtime.interaction_uil = copy.deepcopy(document)
            runtime.interaction_udl = copy.deepcopy(binding)
            runtime._interaction_witnesses = runtime._compile_witnesses(binding)
            runtime.scene_udl = {"selection": {"effect_entry": -1}, "movement": {"effect_entry": -1}}
            runtime._dispatch_sites = {}
            runtime.scene_stats, runtime._scene_segments = _stats(), []
            runtime.last_scene_recovery = {**_stats(), "segments": []}
            runtime.udl = {"opening": {"entry": -1, "return_pc": -1},
                           "turn": {"entry": -1, "continue": -1, "return_pc": -1}}
            runtime.recovery_stats, runtime._segments = _empty_stats(), []
            runtime._phase, runtime._active_intent, runtime._next_run_kind = "authored_residual", False, None
            runtime.forbidden_source = set().union(
                *(binding[role]["source_pcs"] for role in ("callback", "helper", "selection")))
        runtime.frames.extend([
            {"locals": [11, 22, 33, 44, 55, 66, 77], "base": 0,
             "resume": CALLER_RETURN_PC, "store": 16},
            {"locals": [], "base": 2, "resume": RETURN_PC, "store": store},
        ])
        runtime.stack[:] = [0x1234, 0xABCD, 91, 92]
        runtime._write_var(binding["action_global"], binding["actions"].get(action, 56 if action == "examine" else 99))
        runtime._write(binding["door"]["address"], 8, 2 | (16 if is_open else 0))
        runtime._write_var(18, 111)  # Existing turn state must remain untouched.
        bag = binding["repeat"]
        names = document["repeat"]["initial_order"]
        for position, index in enumerate(order):
            runtime._write(bag["items_address"] + 2 * position, 16, bag["resources"][names[index]])
        runtime._write(bag["cursor_address"], 16, cursor)
        clear_trace(runtime)
        result.append(runtime)
    return result


def run_equal(candidate, reference):
    actual, expected = candidate.run(), reference.run()
    for key in ("status", "text", "pc", "events", "score", "moves"):
        assert actual[key] == expected[key]
    assert candidate.snapshot() == reference.snapshot()
    assert candidate.physical == reference.physical
    return actual


@pytest.mark.parametrize("is_open,action,text,outcome", [
    (False, "open", "opened\n", "opened"),
    (True, "close", "closed\n", "closed"),
    (True, "open", "reply second\n", "already_open"),
    (False, "close", "reply second\n", "already_closed"),
])
def test_all_four_paths_equal_original_ordered_effects_and_full_state(
        recovered_source, is_open, action, text, outcome):
    candidate, reference = pair(recovered_source, action=action, is_open=is_open, draw=2)
    result = run_equal(candidate, reference)
    binding = candidate.interaction_udl
    assert result["text"] == text and result["moves"] == 111
    assert candidate._read(binding["history"]["address"], 16) == 1
    assert candidate._read(binding["door"]["address"]) == (18 if action == "open" else 2)
    assert candidate.stack == [0x1234, 0xABCD]
    assert candidate.frames[-1]["locals"] == [11, 22, 33, 1, 55, 66, 77]
    assert result["scene_recovery"]["segments"][0]["outcome"] == outcome
    assert result["scene_recovery"]["fallbacks"] == {}
    assert candidate.executed_blocks == {binding["callback"]["entry"], RETURN_PC}
    if action != ("open" if is_open else "close"):
        assert candidate.physical == [
            ("write", binding["history"]["address"], 16, 1),
            ("text", text[:-1]),
            ("write", binding["door"]["address"], 8, 18 if action == "open" else 2),
            ("text", "\n"),
        ]
        assert candidate.random_log == []


BAG_CASES = [(order, cursor, draw) for order in itertools.permutations(range(3))
             for cursor in range(3) for draw in range(1, 4 - cursor)]


@pytest.mark.parametrize("action", ["open", "close"])
@pytest.mark.parametrize("order,cursor,draw", BAG_CASES)
def test_every_live_bag_permutation_and_remaining_draw_matches_source(
        recovered_source, action, order, cursor, draw):
    candidate, reference = pair(recovered_source, action=action, is_open=action == "open",
                                order=order, cursor=cursor, draw=draw)
    result = run_equal(candidate, reference)
    binding = candidate.interaction_udl["repeat"]
    assert candidate.random_log == [{"range": 3 - cursor, "value": draw}]
    bag_writes = [row for row in candidate.physical
                  if row[0] == "write" and binding["cursor_address"] <= row[1] < binding["items_address"] + 6]
    assert len(bag_writes) == 3
    assert bag_writes[-1] == ("write", binding["cursor_address"], 16, 0 if cursor == 2 else cursor + 1)
    if draw == 1:
        assert bag_writes[0] == bag_writes[1]  # Same-slot writes are both real effects.
    if cursor == 2:
        assert candidate.tape_index == 1  # A range-one draw still consumes RNG.
    assert result["scene_recovery"]["fallbacks"] == {}


@pytest.mark.parametrize("store", [0, 1, 7, 20])
def test_return_uses_the_existing_caller_destination_and_discards_only_callee_stack(recovered_source, store):
    candidate, reference = pair(recovered_source, store=store)
    run_equal(candidate, reference)
    assert candidate.pc == RETURN_PC and len(candidate.frames) == 2
    assert candidate.stack == [0x1234, 0xABCD] + ([1] if store == 0 else [])
    if store:
        assert candidate._read_var(store) == 1


def reenter(runtime, binding, *, selection=False):
    runtime.halted, runtime.halt_reason = False, None
    role = "selection" if selection else "callback"
    runtime.frames.append({"locals": [binding["repeat"]["table_address"]] + [0] * 5 if selection else [],
                           "base": len(runtime.stack), "resume": RETURN_PC, "store": 20 if selection else 4})
    runtime.pc = binding[role]["entry"]
    clear_trace(runtime)


def test_residual_shuffle_use_changes_the_next_semantic_response_without_a_private_bag(recovered_source):
    tape = [{"range": 3, "value": 3}, {"range": 2, "value": 2}, {"range": 1, "value": 1}]
    candidate, reference = pair(recovered_source, action="close", tape=tape)
    assert run_equal(candidate, reference)["text"] == "reply third\n"
    binding = candidate.interaction_udl
    forbidden = candidate.forbidden_source
    candidate.forbidden_source = set()
    for runtime in (candidate, reference):
        reenter(runtime, binding, selection=True)
    assert run_equal(candidate, reference)["text"] == ""
    assert candidate._read_var(20) == binding["repeat"]["resources"]["window.repeat.first"]
    candidate.forbidden_source = forbidden
    for runtime in (candidate, reference):
        reenter(runtime, binding)
    assert run_equal(candidate, reference)["text"] == "reply second\n"
    assert candidate._read(binding["repeat"]["cursor_address"], 16) == 0
    assert candidate.random_log == tape


@pytest.mark.parametrize("mutation,reason", [
    ("cursor", "door_response_bag_outside_qualified_domain"),
    ("foreign-item", "door_response_bag_outside_qualified_domain"),
    ("duplicate-item", "door_response_bag_outside_qualified_domain"),
    ("pointer", "door_source_dependency_changed:window-response-pointer"),
    ("count", "door_source_dependency_changed:window-response-count"),
])
def test_unqualified_live_response_state_falls_back_before_effects(recovered_source, mutation, reason):
    runtime, _ = pair(recovered_source, action="close")
    bag = runtime.interaction_udl["repeat"]
    address, value = {
        "cursor": (bag["cursor_address"], 3),
        "foreign-item": (bag["items_address"], 99),
        "duplicate-item": (bag["items_address"], runtime._read(bag["items_address"] + 2, 16)),
        "pointer": (bag["pointer_address"], bag["table_address"] + 2),
        "count": (bag["table_address"], 5),
    }[mutation]
    runtime._write(address, 16, value)
    clear_trace(runtime)
    before = runtime.snapshot()
    assert runtime._door_interaction() is False
    assert runtime.snapshot() == before and runtime.physical == []
    assert runtime.scene_stats["fallbacks"] == {reason: 1}


@pytest.mark.parametrize("guard", ["window-layout", "window-callback-value", "window-helper", "text-d00"])
def test_changed_source_dependency_never_executes_a_stale_semantic_replacement(recovered_source, guard):
    runtime, _ = pair(recovered_source)
    start = runtime._interaction_witnesses[guard][0]
    runtime.memory[start] ^= 1
    before = runtime.snapshot()
    assert runtime._door_interaction() is False
    assert runtime.snapshot() == before and runtime.physical == []
    assert runtime.scene_stats["fallbacks"] == {"door_source_dependency_changed:" + guard: 1}


def test_changing_the_door_does_not_need_the_unused_live_response_permutation(recovered_source):
    candidate, reference = pair(recovered_source)
    for runtime in (candidate, reference):
        runtime._write(candidate.interaction_udl["repeat"]["items_address"], 16, 0)
        clear_trace(runtime)
    assert run_equal(candidate, reference)["text"] == "opened\n"


def test_memory_output_falls_back_without_effects_and_original_stream_behavior_remains(recovered_source):
    candidate, reference = pair(recovered_source)
    candidate.forbidden_source = set()
    table = 0x640
    for runtime in (candidate, reference):
        runtime._host("output_stream", [3, table])
        clear_trace(runtime)
    before = candidate.snapshot()
    assert candidate._door_interaction() is False
    assert candidate.snapshot() == before and candidate.physical == []
    assert run_equal(candidate, reference)["text"] == ""
    for runtime in (candidate, reference):
        runtime._host("output_stream", [-3])
    # Memory streams preserve ZSCII13; headless screen prose uses Python newline.
    assert candidate.memory[table:table + 9] == b"\x00\x07opened\r"
    assert candidate.snapshot() == reference.snapshot()


@pytest.mark.parametrize("action,text,returned", [("examine", "initial hint\n", 1), ("other", "", 0)])
def test_other_callback_actions_execute_their_residual_source(recovered_source, action, text, returned):
    candidate, reference = pair(recovered_source, action=action, tape=[])
    candidate.forbidden_source = set()
    result = run_equal(candidate, reference)
    assert result["text"] == text and candidate._read_var(4) == returned
    assert candidate._read(candidate.interaction_udl["history"]["address"], 16) == 0
    assert result["scene_recovery"]["segments"] == []
    assert result["scene_recovery"]["fallbacks"] == {"door_action_remains_residual": 1}


def test_recovered_hint_dismissal_changes_the_real_residual_examination_path(recovered_source):
    candidate, reference = pair(recovered_source)
    assert run_equal(candidate, reference)["text"] == "opened\n"
    candidate.forbidden_source = set()
    for runtime in (candidate, reference):
        runtime._write_var(candidate.interaction_udl["action_global"], 56)
        reenter(runtime, candidate.interaction_udl)
    result = run_equal(candidate, reference)
    assert result["text"] == "" and candidate._read_var(4) == 0
    assert result["scene_recovery"]["segments"] == []


def test_untaped_rng_state_and_ordered_draw_match_original_execution(recovered_source):
    candidate, reference = pair(recovered_source, action="close")
    for runtime in (candidate, reference):
        runtime.random_tape = None
    prior_rng = copy.deepcopy(candidate.rng)
    run_equal(candidate, reference)
    assert candidate.rng != prior_rng and candidate.rng == reference.rng
    assert len(candidate.random_log) == 1 and candidate.random_log[0]["range"] == 3
    assert [row[0] for row in candidate.physical] == [
        "write", "rng", "write", "write", "write", "text", "text",
    ]


@pytest.mark.parametrize("kind", ["resume", "store", "boolean-store", "local", "base", "boolean-base", "locals", "root"])
def test_invalid_callback_or_return_frame_is_a_no_effect_fallback(recovered_source, kind):
    runtime, _ = pair(recovered_source)
    frame = runtime.frames[-1]
    if kind == "resume": frame["resume"] = RETURN_PC + 7
    elif kind == "store": frame["store"] = 256
    elif kind == "boolean-store": frame["store"] = True
    elif kind == "local": frame["store"] = 8
    elif kind == "base": frame["base"] = len(runtime.stack) + 1
    elif kind == "boolean-base": frame["base"] = False
    elif kind == "locals": frame["locals"] = [0]
    else: runtime.frames[:] = runtime.frames[:1]
    before = runtime.snapshot()
    assert runtime._door_interaction() is False
    assert runtime.snapshot() == before and runtime.physical == []


@pytest.mark.parametrize("kind", ["temporary-stack", "return-stack", "change-depth", "repeat-depth"])
def test_removed_helpers_do_not_remove_existing_resource_budget_refusals(recovered_source, kind):
    runtime, _ = pair(recovered_source, action="close" if kind == "repeat-depth" else "open")
    if kind.endswith("stack"):
        runtime.stack[:] = [0] * MAX_STACK
        if kind == "return-stack":
            runtime.frames[-1].update(base=MAX_STACK, store=0)
    else:
        count = MAX_FRAMES if kind == "change-depth" else MAX_FRAMES - 1
        caller = copy.deepcopy(runtime.frames[-2])
        runtime.frames[1:1] = [copy.deepcopy(caller) for _ in range(count - len(runtime.frames))]
    before = runtime.snapshot()
    assert runtime._door_interaction() is False
    assert runtime.snapshot() == before and runtime.physical == []


def test_step_budget_stops_after_the_complete_interaction_at_the_original_continuation(recovered_source):
    candidate, _ = pair(recovered_source)
    first = candidate.run(max_steps=1)
    assert first["status"] == "budget_exhausted" and first["pc"] == RETURN_PC
    assert first["text"] == "opened\n" and len(candidate.frames) == 2
    assert first["scene_recovery"]["segments"][0]["status"] == "completed"
    checkpoint = candidate.snapshot()
    resumed, _ = pair(recovered_source)
    resumed.restore(checkpoint)
    second = resumed.run(max_steps=1)
    assert second["status"] == "halted" and second["text"] == ""
    assert second["scene_recovery"]["segments"] == []
    assert resumed.physical == []


@pytest.mark.parametrize("location,phase", [
    ("history", "before"), ("history", "after"),
    ("opening-text", "after"), ("door", "before"), ("door", "after"),
    ("selected-slot", "after"), ("cursor", "before"), ("cursor", "after"),
    ("reply-text", "after"), ("return-store", "before"),
])
def test_effect_faults_keep_the_executed_prefix_and_never_replay_source(recovered_source, location, phase):
    repeated = location in ("selected-slot", "cursor", "reply-text")
    runtime, _ = pair(recovered_source, action="close" if repeated else "open", draw=2,
                      store=20 if location == "return-store" else 4)
    binding = runtime.interaction_udl
    bag = binding["repeat"]
    kind, key = {
        "history": ("write", binding["history"]["address"]),
        "opening-text": ("text", "opened"),
        "door": ("write", binding["door"]["address"]),
        "selected-slot": ("write", bag["items_address"] + 2),
        "cursor": ("write", bag["cursor_address"]),
        "reply-text": ("text", "reply second"),
        "return-store": ("write", runtime.layout["globals"] + 8),
    }[location]
    before = runtime.snapshot()
    runtime.fault_at = (kind, phase, key, 1)
    with pytest.raises(Word16Error, match="authored effect fault"):
        runtime.run()
    event = runtime.last_scene_recovery["segments"][0]
    assert event["status"] == "commit_fault" and event["interrupted_effect_status"] == "unknown"
    assert runtime.last_scene_recovery["fallbacks"] == {}
    assert runtime.executed_blocks == {binding["callback"]["entry"]}
    assert runtime._read(binding["history"]["address"], 16) == (0 if location == "history" and phase == "before" else 1)
    if location == "history":
        assert event["completed_effects"] == [] and runtime._text == []
    if location in ("opening-text", "door"):
        assert runtime._text == ["opened"]
        assert runtime._read(binding["door"]["address"]) == (18 if location == "door" and phase == "after" else 2)
    if repeated:
        assert runtime.random_log == [{"range": 3, "value": 2}] and runtime.tape_index == 1
    if location == "selected-slot":
        first = bag["resources"]["window.repeat.first"]
        assert runtime._read(bag["items_address"], 16) == runtime._read(bag["items_address"] + 2, 16) == first
        assert runtime._read(bag["cursor_address"], 16) == 0
    if location == "cursor":
        assert runtime._read(bag["cursor_address"], 16) == (1 if phase == "after" else 0)
        assert runtime._text == []
    if location == "reply-text":
        assert runtime._text == ["reply second"] and runtime._read(bag["cursor_address"], 16) == 1
    if location == "return-store":
        assert runtime._text == ["opened", "\n"] and len(runtime.frames) == 2
        assert runtime._read_var(20) == 0
    after, physical = runtime.snapshot(), list(runtime.physical)
    runtime.fault_at = None
    with pytest.raises(Word16Error, match="faulted"):
        runtime.run()
    assert runtime.snapshot() == after and runtime.physical == physical
    runtime.restore(before)
    clear_trace(runtime)
    assert runtime.run()["status"] == "halted"


def test_real_output_budget_fault_preserves_history_without_claiming_door_change(recovered_source):
    runtime, _ = pair(recovered_source)
    runtime._text_size = MAX_TEXT
    with pytest.raises(Word16Error, match="output budget"):
        runtime.run()
    binding = runtime.interaction_udl
    assert runtime.physical == [("write", binding["history"]["address"], 16, 1)]
    assert runtime._read(binding["door"]["address"]) == 2
    assert runtime.last_scene_recovery["segments"][0]["completed_effects"] == [
        {"type": "hint_dismissed", "fact": runtime.interaction_uil["history_fact"]},
    ]
    assert runtime.last_scene_recovery["segments"][0]["status"] == "commit_fault"


@pytest.mark.parametrize("tape", [[], [{"range": 2, "value": 1}]])
def test_real_random_tape_failure_leaves_bag_unmodified_and_history_recorded(recovered_source, tape):
    runtime, _ = pair(recovered_source, action="close", tape=tape)
    binding = runtime.interaction_udl
    bag = binding["repeat"]
    before = bytes(runtime.memory[bag["cursor_address"]:bag["items_address"] + 6])
    with pytest.raises(Word16Error, match="Random tape"):
        runtime.run()
    assert bytes(runtime.memory[bag["cursor_address"]:bag["items_address"] + 6]) == before
    assert runtime.physical == [("write", binding["history"]["address"], 16, 1)]
    assert runtime.tape_index == 0 and runtime.random_log == []
    assert runtime.last_scene_recovery["segments"][0]["completed_realizations"] == []
