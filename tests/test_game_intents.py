"""Authored game-domain fixtures, independent of any original story layout."""

import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "player"))
from fdisbull_player.game_intents import (
    FORMAT, GameIntentError, evaluate_interaction, evaluate_turn, validate_uil,
)


def document():
    """An authored chest/letter rule; no licensed Zork data or object IDs."""
    emit = lambda resource: {"intent": "narration.emit", "resource": resource}
    opening = [
        {"intent": "container.open", "entity": "target"},
        {"residual_ir": "post_open_source_flag"},
    ]
    return {
        "format": FORMAT,
        "id": "authored.container-interaction",
        "resources": {
            "already_open": "The lid is already raised.",
            "opened_empty": "The empty chest opens.",
            "opening_prefix": "Inside ",
            "opening_middle": " you find ",
            "article": "a ",
            "punctuation": ".",
            "newline": "\n",
        },
        "interaction": {
            "id": "open_container",
            "parameters": {"target": "entity"},
            "requires": [
                {"field": "target.is_container", "eq": True},
                {"field": "target.supports_opening", "eq": True},
                {"field": "target.reachable", "eq": True},
                {"field": "target.opaque", "eq": True},
            ],
            "outcomes": [
                {"id": "already_open", "when": [
                    {"field": "target.is_open", "eq": True},
                ], "steps": [emit("already_open"), emit("newline")]},
                {"id": "opened_empty", "when": [
                    {"field": "target.is_open", "eq": False},
                    {"field": "target.contents_count", "eq": 0},
                ], "steps": opening + [emit("opened_empty"), emit("newline")]},
                {"id": "opened_contents", "when": [
                    {"field": "target.is_open", "eq": False},
                    {"field": "target.contents_count", "eq": 1},
                    {"field": "first_content.plain_listing", "eq": True},
                ], "steps": opening + [
                    emit("opening_prefix"),
                    {"intent": "narration.name", "entity": "target"},
                    emit("opening_middle"), emit("article"),
                    {"intent": "narration.name", "entity": "first_content"},
                    {"intent": "discourse.remember_mentioned_object",
                     "entity": "first_content", "scene": "current_scene"},
                    emit("punctuation"), emit("newline"),
                ]},
            ],
        },
        "turn": {
            "id": "count_player_action",
            "requires": [{"field": "turn.count", "range": [0, 999]}],
            "steps": [{"intent": "turn.count_player_action", "cycle": 1000}],
        },
    }


def state():
    def entity(name, *, container=False, contents=()):
        return {
            "name": name, "is_container": container, "supports_opening": container,
            "is_open": False, "opaque": True, "reachable": True,
            "contents": list(contents), "plain_listing": True,
        }
    return {
        "entities": {
            "oak-chest": entity("the oak chest", container=True, contents=["sealed-letter"]),
            "sealed-letter": entity("sealed letter"),
        },
        "current_scene": "attic",
        "discourse": {"referent": "oak-chest", "scene": "attic"},
        "turn": {"count": 17},
    }


def text(result):
    return "".join(effect["text"] for effect in result["effects"] if effect["type"] == "narrate")


def test_contents_outcome_has_domain_effects_in_source_relevant_order():
    before = state()
    frozen = copy.deepcopy(before)
    result = evaluate_interaction(document(), before, {"target": "oak-chest"})
    assert before == frozen
    assert result["outcome"] == "opened_contents"
    assert text(result) == "Inside the oak chest you find a sealed letter.\n"
    assert [effect["type"] for effect in result["effects"]] == [
        "container_opened", "residual_ir", "narrate", "narrate", "narrate",
        "narrate", "narrate", "referent_changed", "narrate", "narrate",
    ]
    assert result["effects"][1] == {"type": "residual_ir", "binding": "post_open_source_flag"}
    assert result["effects"][7] == {
        "type": "referent_changed", "entity": "sealed-letter", "scene": "attic",
        "previous": {"referent": "oak-chest", "scene": "attic"},
    }
    expected = copy.deepcopy(before)
    expected["entities"]["oak-chest"]["is_open"] = True
    expected["discourse"] = {"referent": "sealed-letter", "scene": "attic"}
    assert result["next_state"] == expected
    assert "container.open" in result["executed_intents"]
    assert "discourse.remember_mentioned_object" in result["executed_intents"]
    assert "post_open_source_flag" not in result["executed_intents"]
    # The open intent is not secretly an entire game turn.
    assert result["next_state"]["turn"] == {"count": 17}


def test_already_open_has_only_narration_and_preserves_state():
    before = state()
    before["entities"]["oak-chest"]["is_open"] = True
    result = evaluate_interaction(document(), before, {"target": "oak-chest"})
    assert result["outcome"] == "already_open"
    assert result["next_state"] == before
    assert text(result) == "The lid is already raised.\n"
    assert {effect["type"] for effect in result["effects"]} == {"narrate"}
    assert "container.open" not in result["executed_intents"]


def test_empty_container_does_not_change_discourse_or_invent_contents():
    before = state()
    before["entities"]["oak-chest"]["contents"] = []
    result = evaluate_interaction(document(), before, {"target": "oak-chest"})
    assert result["outcome"] == "opened_empty"
    assert text(result) == "The empty chest opens.\n"
    assert result["next_state"]["discourse"] == before["discourse"]
    assert [effect["type"] for effect in result["effects"]] == [
        "container_opened", "residual_ir", "narrate", "narrate",
    ]


@pytest.mark.parametrize("field,value", [
    ("is_container", False), ("supports_opening", False), ("reachable", False),
    ("opaque", False), ("is_open", None), ("contents", None),
])
def test_unsupported_or_unknown_context_is_explicitly_unrecovered(field, value):
    before = state()
    before["entities"]["oak-chest"][field] = value
    result = evaluate_interaction(document(), before, {"target": "oak-chest"})
    assert result["outcome"] == "unrecovered"
    assert result["effects"] == []
    assert result["executed_intents"] == []
    assert result["next_state"] == before
    assert result["reason"]


def test_complex_child_and_multiple_children_do_not_borrow_the_plain_path():
    before = state()
    before["entities"]["sealed-letter"]["plain_listing"] = False
    result = evaluate_interaction(document(), before, {"target": "oak-chest"})
    assert result["outcome"] == "unrecovered"
    assert result["next_state"] == before
    before = state()
    before["entities"]["oak-chest"]["contents"].append("unprojected-object")
    result = evaluate_interaction(document(), before, {"target": "oak-chest"})
    assert result["outcome"] == "unrecovered"
    assert result["effects"] == []


def test_failure_after_a_planned_open_discards_the_whole_plan():
    before = state()
    before["entities"]["sealed-letter"]["name"] = None
    result = evaluate_interaction(document(), before, {"target": "oak-chest"})
    assert result["outcome"] == "unrecovered"
    assert result["effects"] == []
    assert result["next_state"] == before
    assert before["entities"]["oak-chest"]["is_open"] is False


def test_rules_conditions_resources_and_step_order_are_executable_data():
    candidate = document()
    candidate["resources"]["opening_prefix"] = "You uncover "
    candidate["interaction"]["outcomes"][2]["steps"][2:4] = [
        {"intent": "narration.name", "entity": "target"},
        {"intent": "narration.emit", "resource": "opening_prefix"},
    ]
    result = evaluate_interaction(candidate, state(), {"target": "oak-chest"})
    assert text(result) == "the oak chestYou uncover  you find a sealed letter.\n"
    # The definition's admission rule changes behavior without editing Python.
    candidate["interaction"]["requires"].append({"field": "current_scene", "eq": "cellar"})
    result = evaluate_interaction(candidate, state(), {"target": "oak-chest"})
    assert result["outcome"] == "unrecovered"
    # A different condition changes outcome selection, not just its annotation.
    candidate = document()
    candidate["interaction"]["outcomes"][0]["when"] = [
        {"field": "target.is_open", "eq": False},
    ]
    result = evaluate_interaction(candidate, state(), {"target": "oak-chest"})
    assert result["outcome"] == "already_open"
    assert result["next_state"]["entities"]["oak-chest"]["is_open"] is False


def test_omitting_a_semantic_effect_changes_the_executable_definition():
    candidate = document()
    candidate["interaction"]["outcomes"][2]["steps"].pop(0)
    result = evaluate_interaction(candidate, state(), {"target": "oak-chest"})
    assert result["outcome"] == "opened_contents"
    assert result["next_state"]["entities"]["oak-chest"]["is_open"] is False
    assert "container.open" not in result["executed_intents"]


@pytest.mark.parametrize("count,after", [(0, 1), (17, 18), (998, 999), (999, 0)])
def test_turn_counting_has_an_explicit_cycle_without_scheduler_effects(count, after):
    before = state()
    before["turn"]["count"] = count
    result = evaluate_turn(document(), before)
    assert result["outcome"] == "turn_counted"
    assert result["effects"] == [{"type": "turn_counted", "before": count, "after": after, "cycle": 1000}]
    assert result["executed_intents"] == ["turn.count_player_action"]
    expected = copy.deepcopy(before)
    expected["turn"]["count"] = after
    assert result["next_state"] == expected
    assert before["turn"]["count"] == count


@pytest.mark.parametrize("count", [-1, 1000, 65535, None])
def test_turn_outside_recovered_domain_is_not_modulo_normalized(count):
    before = state()
    before["turn"]["count"] = count
    result = evaluate_turn(document(), before)
    assert result["outcome"] == "unrecovered"
    assert result["effects"] == []
    assert result["next_state"] == before


def test_turn_cycle_and_admission_are_definition_data():
    candidate = document()
    candidate["turn"]["requires"] = [{"field": "turn.count", "range": [0, 9]}]
    candidate["turn"]["steps"][0]["cycle"] = 10
    before = state()
    before["turn"]["count"] = 9
    assert evaluate_turn(candidate, before)["effects"] == [
        {"type": "turn_counted", "before": 9, "after": 0, "cycle": 10},
    ]


@pytest.mark.parametrize("steps", [[], [
    {"intent": "turn.count_player_action", "cycle": 1000},
    {"intent": "turn.count_player_action", "cycle": 1000},
]])
def test_turn_accounting_cannot_claim_success_with_zero_or_two_actions(steps):
    candidate = document()
    candidate["turn"]["steps"] = steps
    with pytest.raises(GameIntentError, match="exactly one"):
        evaluate_turn(candidate, state())


@pytest.mark.parametrize("mutation", [
    lambda d: d["interaction"]["outcomes"][2]["steps"].append({"intent": "execute_python", "code": "pass"}),
    lambda d: d["interaction"]["requires"].append({"field": "memory.0x80a3", "eq": 1}),
    lambda d: d["interaction"]["requires"].append({"field": "target.is_open", "eq": 1}),
    lambda d: d["interaction"]["requires"].append({"field": [], "eq": True}),
    lambda d: d["interaction"]["outcomes"][2]["steps"].append({"residual_ir": "flag", "code": "pass"}),
    lambda d: d["interaction"]["outcomes"][2]["steps"].append({"intent": "narration.emit", "resource": []}),
    lambda d: d["resources"].pop("article"),
])
def test_validation_rejects_hidden_unselected_branch_or_vm_escape(mutation):
    candidate = document()
    mutation(candidate)
    with pytest.raises(GameIntentError):
        validate_uil(candidate)


def test_nested_inputs_and_definition_remain_unchanged_after_evaluation():
    candidate, before, arguments = document(), state(), {"target": "oak-chest"}
    saved = copy.deepcopy((candidate, before, arguments))
    result = evaluate_interaction(candidate, before, arguments)
    result["next_state"]["entities"]["oak-chest"]["contents"].clear()
    assert (candidate, before, arguments) == saved
