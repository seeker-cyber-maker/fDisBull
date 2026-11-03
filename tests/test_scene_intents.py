"""Authored scene rules prove selection without any source VM or story image."""

import copy
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "player"))
from fdisbull_player.scene_intents import (
    FORMAT, SceneIntentError, evaluate_exit, initial_state, validate_uil,
)


def document():
    """A tiny authored world with every supported exit encoding's meaning."""
    return {
        "format": FORMAT,
        "id": "authored.harbor",
        "entry_scene": "courtyard",
        "resources": {
            "default_blocked": "There is no passage.",
            "default_closed_prefix": "The ",
            "default_closed_suffix": " is shut.",
            "newline": "\n",
            "wall": "A wall blocks the way.",
            "tide": "The tide covers the steps.",
            "entrance": "A quiet courtyard.",
        },
        "facts": {"tide_is_low": {"type": "boolean", "initial": False}},
        "doors": {"iron_gate": {"name": "iron gate", "initial_open": False}},
        "handlers": {
            "guarded_route": {"representation": "low_level_ir", "role": "exit"},
            "missing_direction": {"representation": "low_level_ir", "role": "exit"},
            "square_events": {"representation": "low_level_ir", "role": "room_event"},
        },
        "missing_exit": "missing_direction",
        "scenes": {
            "courtyard": {
                "name": "Courtyard",
                "description": {"kind": "static", "resource": "entrance"},
                "initial_traits": {"land": True, "naturally_lit": True, "ruined": False},
                "exits": {
                    "north": {"id": "courtyard.north", "kind": "direct", "destination": "square"},
                    "east": {"id": "courtyard.east", "kind": "blocked", "failure_resource": "wall"},
                    "south": {"id": "courtyard.south", "kind": "conditional", "fact": "tide_is_low", "destination": "dock", "failure_resource": "tide"},
                    "west": {"id": "courtyard.west", "kind": "door", "door": "iron_gate", "destination": "square"},
                    "up": {"id": "courtyard.up", "kind": "routine", "residual": "guarded_route"},
                },
            },
            "square": {
                "name": "Passage",
                "description": {"kind": "residual", "handler": "square_events"},
                "on_event": {"kind": "residual", "handler": "square_events"},
                "exits": {"south": {"id": "square.south", "kind": "direct", "destination": "courtyard"}},
            },
            "dock": {
                "name": "Passage",  # Equal display names must not collapse distinct scenes.
                "exits": {"land": {"id": "dock.land", "kind": "direct", "destination": "courtyard"}},
            },
        },
    }


def text(plan):
    return "".join(effect["text"] for effect in plan["effects"] if effect["type"] == "narrate")


def test_direct_exit_is_an_explicit_named_destination_without_arrival_claim():
    doc = document()
    state = initial_state(doc)
    frozen = copy.deepcopy((doc, state))
    result = evaluate_exit(doc, state, "north")
    assert result["status"] == "travel"
    assert result["outcome"] == "direct"
    assert result["origin"] == "courtyard"
    assert result["destination"] == "square"
    assert result["handler"] is None
    assert result["effects"] == [{"type": "travel_requested", "from": "courtyard", "destination": "square"}]
    assert result["executed_intents"] == ["scene.select_exit"]
    assert result["next_state"] == state
    assert (doc, state) == frozen
    # Modifying a result must not alter caller-owned state.
    result["next_state"]["facts"]["tide_is_low"] = True
    assert state["facts"]["tide_is_low"] is False


def test_explicit_blocked_exit_retains_narrative_and_no_travel():
    result = evaluate_exit(document(), initial_state(document()), "east")
    assert result["status"] == "refused"
    assert result["outcome"] == "blocked"
    assert result["destination"] is None
    assert text(result) == "A wall blocks the way.\n"
    assert [effect["type"] for effect in result["effects"]] == ["narrate", "narrate"]


def test_conditional_rule_reads_live_fact_instead_of_freezing_initial_value():
    doc = document()
    state = initial_state(doc)
    result = evaluate_exit(doc, state, "south")
    assert result["outcome"] == "condition_false"
    assert text(result) == "The tide covers the steps.\n"
    state["facts"]["tide_is_low"] = True
    result = evaluate_exit(doc, state, "south")
    assert result["outcome"] == "condition_true"
    assert result["destination"] == "dock"
    assert not text(result)
    state["facts"]["tide_is_low"] = False
    assert evaluate_exit(doc, state, "south")["status"] == "refused"


@pytest.mark.parametrize("value", [None, "missing"])
def test_unknown_fact_is_not_false_and_commits_no_effects(value):
    doc = document()
    state = initial_state(doc)
    if value == "missing":
        state["facts"].clear()
    else:
        state["facts"]["tide_is_low"] = value
    result = evaluate_exit(doc, state, "south")
    assert result["status"] == "unknown"
    assert result["effects"] == result["executed_intents"] == []
    assert result["next_state"] == state
    assert result["reason"] == "condition_unknown:tide_is_low"


def test_conditional_without_message_uses_declared_default():
    doc = document()
    del doc["scenes"]["courtyard"]["exits"]["south"]["failure_resource"]
    result = evaluate_exit(doc, initial_state(doc), "south")
    assert text(result) == "There is no passage.\n"


def test_closed_door_narrates_then_updates_the_mentioned_object():
    doc = document()
    result = evaluate_exit(doc, initial_state(doc), "west")
    assert result["status"] == "refused"
    assert result["outcome"] == "door_closed"
    assert text(result) == "The iron gate is shut.\n"
    assert [effect["type"] for effect in result["effects"]] == [
        "narrate", "narrate", "narrate", "narrate", "referent_changed"]
    assert result["effects"][-1] == {"type": "referent_changed", "entity": "iron_gate", "scene": "courtyard"}
    assert result["executed_intents"] == [
        "scene.select_exit", "narration.emit", "narration.name", "discourse.remember_mentioned_object"]


def test_closed_door_with_custom_message_does_not_invent_a_discourse_write():
    doc = document()
    doc["scenes"]["courtyard"]["exits"]["west"]["failure_resource"] = "wall"
    result = evaluate_exit(doc, initial_state(doc), "west")
    assert text(result) == "A wall blocks the way.\n"
    assert all(effect["type"] == "narrate" for effect in result["effects"])


def test_door_rechecks_current_open_state_and_unknown_is_not_closed():
    doc = document()
    state = initial_state(doc)
    state["doors"]["iron_gate"] = True
    result = evaluate_exit(doc, state, "west")
    assert result["status"] == "travel" and result["outcome"] == "door_open"
    assert result["destination"] == "square"
    state["doors"]["iron_gate"] = None
    result = evaluate_exit(doc, state, "west")
    assert result["status"] == "unknown" and result["effects"] == []
    assert result["reason"] == "door_state_unknown:iron_gate"
    state["doors"].clear()
    assert evaluate_exit(doc, state, "west")["status"] == "unknown"


@pytest.mark.parametrize("direction,outcome,handler", [
    ("up", "routine", "guarded_route"),
    ("down", "missing_exit", "missing_direction"),
])
def test_resolved_residual_body_is_explicit_and_not_executed(direction, outcome, handler):
    doc = document()
    result = evaluate_exit(doc, initial_state(doc), direction)
    assert result["status"] == "residual" and result["outcome"] == outcome
    assert result["handler"] == handler
    assert result["destination"] is None
    assert result["effects"] == [{"type": "residual_ir", "binding": handler}]
    assert result["executed_intents"] == ["scene.select_exit"]
    assert result["next_state"] == initial_state(doc)


@pytest.mark.parametrize("scene", [None, "outside_this_model"])
def test_unknown_scene_is_not_guessed_from_the_document_entry(scene):
    doc = document()
    state = initial_state(doc)
    state["current_scene"] = scene
    result = evaluate_exit(doc, state, "north")
    assert result["status"] == "unknown"
    assert result["effects"] == [] and result["next_state"] == state


def test_distinct_scene_identities_can_share_names_and_cycles_are_finite_choices():
    doc = document()
    state = initial_state(doc)
    state["current_scene"] = "dock"
    result = evaluate_exit(doc, state, "land")
    assert result["origin"] == "dock" and result["destination"] == "courtyard"
    doc["scenes"]["dock"]["exits"]["land"]["destination"] = "dock"
    result = evaluate_exit(doc, state, "land")
    assert result["destination"] == "dock"


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(format="unknown-format"),
    lambda d: d.update(entry_scene="nowhere"),
    lambda d: d.update(stack=[]),
    lambda d: d["scenes"]["dock"].update(address=1234),
    lambda d: d["scenes"]["dock"]["exits"]["land"].update(kind=[]),
    lambda d: d["scenes"]["dock"]["exits"]["land"].update(destination="nowhere"),
    lambda d: d["scenes"]["dock"]["exits"]["land"].update(id="courtyard.north"),
    lambda d: d["scenes"]["courtyard"]["exits"]["south"].update(fact="unknown_fact"),
    lambda d: d["scenes"]["courtyard"]["exits"]["west"].update(door="unknown_door"),
    lambda d: d["scenes"]["courtyard"]["exits"]["east"].update(failure_resource="unknown_resource"),
    lambda d: d["scenes"]["courtyard"]["exits"]["up"].update(residual="square_events"),
    lambda d: d["scenes"]["square"]["description"].update(handler="guarded_route"),
    lambda d: d["scenes"]["square"]["on_event"].update(kind="execute_python"),
    lambda d: d["handlers"]["guarded_route"].update(representation="game_intent_uil"),
    lambda d: d["handlers"]["guarded_route"].update(entry=1234),
    lambda d: d["facts"]["tide_is_low"].update(initial=1),
    lambda d: d["doors"]["iron_gate"].update(initial_open=0),
    lambda d: d["scenes"]["courtyard"]["initial_traits"].update(land=1),
    lambda d: d["resources"].pop("newline"),
    lambda d: d.update(missing_exit="square_events"),
])
def test_every_definition_is_checked_even_when_not_selected(mutate):
    doc = document()
    state = initial_state(doc)
    mutate(doc)
    with pytest.raises(SceneIntentError):
        evaluate_exit(doc, state, "north")


@pytest.mark.parametrize("mutate", [
    lambda s: s["facts"].update(tide_is_low=1),
    lambda s: s["doors"].update(iron_gate=0),
    lambda s: s["facts"].update(unknown_fact=False),
    lambda s: s["doors"].update(unknown_door=True),
    lambda s: s.update(current_scene=1),
    lambda s: s.update(memory=[]),
])
def test_malformed_state_is_refused_before_any_effect(mutate):
    doc = document()
    state = initial_state(doc)
    mutate(state)
    frozen = copy.deepcopy(state)
    with pytest.raises(SceneIntentError):
        evaluate_exit(doc, state, "north")
    assert state == frozen


@pytest.mark.parametrize("direction", ["n", "diagonal", "", 1, None])
def test_evaluator_has_no_invented_text_command_parser(direction):
    with pytest.raises(SceneIntentError):
        evaluate_exit(document(), initial_state(document()), direction)


def test_pure_evaluator_imports_without_source_packages_or_word16(tmp_path):
    source = Path(__file__).resolve().parents[1] / "player/fdisbull_player/scene_intents.py"
    # A fresh isolated process loads just this file; neither package nor VM is available.
    script = """import importlib.util, json, pathlib, sys
p = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('isolated_scene_intents', p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
doc = json.loads(sys.argv[2])
result = m.evaluate_exit(doc, m.initial_state(doc), 'north')
assert result['destination'] == 'square'
assert not any(name.startswith(('fdisbull', 'fdisbull_player')) for name in sys.modules)
print(result['status'])
"""
    import json
    result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(source), json.dumps(document())],
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "travel"


def test_relocation_changes_actor_and_scene_as_one_named_effect_without_a_turn():
    from fdisbull_player.scene_intents import evaluate_relocation
    state = {"current_scene": "courtyard", "actor": {"id": "wanderer", "scene": "courtyard"}}
    frozen = copy.deepcopy(state)
    result = evaluate_relocation(document(), state, "square")
    assert result["status"] == "moved"
    assert result["next_state"] == {"current_scene": "square", "actor": {"id": "wanderer", "scene": "square"}}
    assert result["effects"] == [{"type": "actor_relocated", "actor": "wanderer", "origin": "courtyard", "destination": "square"}]
    assert result["executed_intents"] == ["scene.move_actor"]
    assert state == frozen
    assert "turn" not in result["next_state"]


@pytest.mark.parametrize("origin,actor_scene,destination,reason", [
    (None, "courtyard", "square", "current_scene_unknown"),
    ("outside", "outside", "square", "current_scene_unknown"),
    ("courtyard", None, "square", "actor_scene_unknown"),
    ("courtyard", "dock", "square", "actor_scene_mismatch"),
    ("courtyard", "courtyard", None, "destination_unknown"),
    ("courtyard", "courtyard", "outside", "destination_unknown"),
])
def test_relocation_unsupported_context_is_unchanged(origin, actor_scene, destination, reason):
    from fdisbull_player.scene_intents import evaluate_relocation
    state = {"current_scene": origin, "actor": {"id": "wanderer", "scene": actor_scene}}
    result = evaluate_relocation(document(), state, destination)
    assert result["status"] == "unknown" and result["reason"] == reason
    assert result["effects"] == result["executed_intents"] == []
    assert result["next_state"] == state


def test_relocation_to_same_scene_retains_an_explicit_occurrence():
    from fdisbull_player.scene_intents import evaluate_relocation
    state = {"current_scene": "courtyard", "actor": {"id": "wanderer", "scene": "courtyard"}}
    result = evaluate_relocation(document(), state, "courtyard")
    assert result["status"] == "moved" and result["next_state"] == state
    assert result["effects"][0]["type"] == "actor_relocated"


@pytest.mark.parametrize("state,destination", [
    ({"current_scene": "courtyard", "actor": {"id": 4, "scene": "courtyard"}}, "square"),
    ({"current_scene": "courtyard", "actor": {"id": "wanderer", "scene": "courtyard", "object_number": 4}}, "square"),
    ({"current_scene": "courtyard", "actor": {"id": "wanderer", "scene": "courtyard"}}, 1234),
    ({"current_scene": True, "actor": {"id": "wanderer", "scene": "courtyard"}}, "square"),
])
def test_relocation_rejects_malformed_or_source_layout_state(state, destination):
    from fdisbull_player.scene_intents import evaluate_relocation
    with pytest.raises(SceneIntentError):
        evaluate_relocation(document(), state, destination)


def test_total_names_and_resources_share_one_text_budget(monkeypatch):
    import fdisbull_player.scene_intents as module
    doc = document()
    # Every fragment fits separately; the combined document must still be bounded.
    monkeypatch.setattr(module, "MAX_TEXT_BYTES", 200)
    doc["scenes"]["dock"]["name"] = "n" * 180
    with pytest.raises(SceneIntentError, match="byte budget"):
        validate_uil(doc)
