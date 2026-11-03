"""Authored interaction rules, independent of a source game or virtual machine."""

import copy
import itertools
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "player"))
from fdisbull_player.door_intents import (
    FORMAT, MAX_BAG_SIZE, MAX_RESOURCES, MAX_TEXT_BYTES, DoorIntentError,
    evaluate_interaction, select_response, validate_uil,
)


def document():
    return {
        "format": FORMAT,
        "id": "authored.harbor_gate",
        "door": "iron_gate",
        "history_fact": "gate_hint_dismissed",
        "resources": {
            "opening": "The gate swings outward.",
            "closing": "The gate clicks shut.",
            "again_a": "It is already that way.",
            "again_b": "There is nothing to change.",
            "again_c": "That has already been done.",
            "line_end": "\n",
        },
        "actions": {
            "open": {"is_open": True, "resource": "opening"},
            "close": {"is_open": False, "resource": "closing"},
        },
        "repeat": {
            "id": "gate_repeat_feedback",
            "resources": ["again_a", "again_b", "again_c"],
            "initial_order": ["again_a", "again_b", "again_c"],
            "initial_cursor": 0,
        },
        "newline_resource": "line_end",
    }


def state(is_open=False, *, hint=False, bag=True):
    return {
        "door_open": is_open,
        "hint_dismissed": hint,
        "response_bag": {
            "order": ["again_a", "again_b", "again_c"], "cursor": 0,
        } if bag else None,
    }


@pytest.mark.parametrize("is_open,action,outcome,changed", [
    (False, "open", "opened", True),
    (True, "close", "closed", True),
    (True, "open", "already_open", False),
    (False, "close", "already_closed", False),
])
def test_four_live_state_action_cases_keep_exact_effect_order(is_open, action, outcome, changed):
    doc, current = document(), state(is_open)
    frozen = copy.deepcopy((doc, current))
    result = evaluate_interaction(doc, current, action)

    assert result["status"] == "handled"
    assert result["outcome"] == outcome
    assert result["effects"][0] == {
        "type": "hint_dismissed", "fact": "gate_hint_dismissed",
    }
    assert result["effects"][-1] == {
        "type": "narrate", "resource": "line_end", "text": "\n",
    }
    if changed:
        resource = "opening" if action == "open" else "closing"
        assert result["effects"][1:-1] == [
            {"type": "narrate", "resource": resource, "text": doc["resources"][resource]},
            {"type": "door_state_changed", "door": "iron_gate",
             "was_open": is_open, "is_open": not is_open},
        ]
        assert result["executed_intents"] == [
            "presentation.dismiss_initial_hint", "narration.emit",
            "door." + action, "narration.emit",
        ]
    else:
        assert result["effects"][1:-1] == [{
            "type": "shuffled_response", "bag": "gate_repeat_feedback",
        }]
        assert result["executed_intents"] == [
            "presentation.dismiss_initial_hint", "narration.choose_shuffled_response",
            "narration.emit",
        ]
    assert result["next_state"] == {
        "door_open": action == "open", "hint_dismissed": True,
        "response_bag": current["response_bag"],
    }
    assert (doc, current) == frozen
    result["next_state"]["response_bag"]["order"].reverse()
    assert (doc, current) == frozen


@pytest.mark.parametrize("hint", [False, True, None])
def test_hint_assignment_is_unconditional_even_when_previous_value_is_unknown(hint):
    result = evaluate_interaction(document(), state(False, hint=hint), "open")
    assert result["status"] == "handled"
    assert result["effects"][0]["type"] == "hint_dismissed"
    assert result["next_state"]["hint_dismissed"] is True


@pytest.mark.parametrize("action,is_open", [("open", False), ("close", True)])
def test_missing_repeat_bag_does_not_block_a_state_change(action, is_open):
    result = evaluate_interaction(document(), state(is_open, bag=False), action)
    assert result["status"] == "handled"
    assert result["next_state"]["response_bag"] is None


@pytest.mark.parametrize("current,action,reason", [
    (state(None), "open", "door_state_unknown"),
    (state(True, bag=False), "open", "response_bag_unknown"),
    (state(False, bag=False), "close", "response_bag_unknown"),
    (state(False), "examine", "unsupported_action"),
])
def test_unrecovered_domain_has_no_effect_and_keeps_independent_input_state(current, action, reason):
    doc = document()
    frozen = copy.deepcopy((doc, current))
    result = evaluate_interaction(doc, current, action)
    assert result == {
        "status": "unknown", "outcome": "unrecovered", "reason": reason,
        "effects": [], "executed_intents": [], "next_state": current,
    }
    assert (doc, current) == frozen
    result["next_state"]["hint_dismissed"] = True
    assert (doc, current) == frozen


# All choices for a three-item bag, specified as independent expected position
# permutations. The expected table is not calculated by calling a swap helper.
CHOICES = [
    (0, 1, 0, (0, 1, 2), 1),
    (0, 2, 1, (1, 0, 2), 1),
    (0, 3, 2, (2, 1, 0), 1),
    (1, 1, 1, (0, 1, 2), 2),
    (1, 2, 2, (0, 2, 1), 2),
    (2, 1, 2, (0, 1, 2), 0),
]


@pytest.mark.parametrize("order", list(itertools.permutations(("again_a", "again_b", "again_c"))))
@pytest.mark.parametrize("cursor,draw,chosen,positions,next_cursor", CHOICES)
def test_every_permutation_cursor_and_legal_draw(order, cursor, draw, chosen, positions, next_cursor):
    doc = document()
    bag = {"order": list(order), "cursor": cursor}
    frozen = copy.deepcopy((doc, bag))
    result = select_response(doc, bag, draw)
    expected_resource = order[chosen]
    assert result == {
        "resource": expected_resource,
        "text": doc["resources"][expected_resource],
        "chosen_position": chosen,
        "cursor_position": cursor,
        "next_bag": {"order": [order[index] for index in positions], "cursor": next_cursor},
    }
    assert (doc, bag) == frozen
    result["next_bag"]["order"].reverse()
    assert (doc, bag) == frozen


def test_cycle_is_without_replacement_but_boundary_can_repeat_last_response():
    doc = document()
    bag = state()["response_bag"]
    selected = []
    for draw in (3, 1, 1, 3):
        result = select_response(doc, bag, draw)
        selected.append(result["resource"])
        bag = result["next_bag"]
    assert selected == ["again_c", "again_b", "again_a", "again_a"]
    assert bag == {"order": ["again_a", "again_b", "again_c"], "cursor": 1}


def test_same_slot_still_exposes_both_positions_for_ordered_realization():
    result = select_response(document(), state()["response_bag"], 1)
    assert result["chosen_position"] == result["cursor_position"] == 0
    assert result["next_bag"] == {"order": ["again_a", "again_b", "again_c"], "cursor": 1}


@pytest.mark.parametrize("size", [1, MAX_BAG_SIZE])
def test_generic_bag_size_bounds_are_not_bound_to_one_game(size):
    doc = document()
    names = ["response_" + str(index) for index in range(size)]
    doc["resources"].update({name: "Reply " + name for name in names})
    doc["repeat"]["resources"] = names
    doc["repeat"]["initial_order"] = list(reversed(names))
    validate_uil(doc)
    bag = {"order": list(names), "cursor": size - 1}
    result = select_response(doc, bag, 1)
    assert result["resource"] == names[-1]
    assert result["next_bag"] == {"order": names, "cursor": 0}


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(address=1234),
    lambda d: d.update(format="unknown"),
    lambda d: d.update(id=""),
    lambda d: d.update(door="x" * 161),
    lambda d: d.update(history_fact="bad\nname"),
    lambda d: d.update(id="bad\ud800"),
    lambda d: d["resources"].update({"bad\x00": "unused"}),
    lambda d: d["resources"].update({"unused": "bad\ud800"}),
    lambda d: d["resources"].update({"oversized": "é" * (MAX_TEXT_BYTES // 2 + 1)}),
    lambda d: d["resources"].update({"extra_" + str(i): "" for i in range(MAX_RESOURCES)}),
    lambda d: d["actions"].update(examine={"is_open": True, "resource": "opening"}),
    lambda d: d["actions"]["open"].update(is_open=False),
    lambda d: d["actions"]["close"].update(is_open=0),
    lambda d: d["actions"]["open"].update(resource="missing"),
    lambda d: d["actions"]["open"].update(turns=1),
    lambda d: d["repeat"].update(resources=[]),
    lambda d: d["repeat"].update(resources=["again_a", "again_a", "again_c"]),
    lambda d: d["repeat"].update(initial_order=["again_a", "again_b"]),
    lambda d: d["repeat"].update(initial_order=["again_a", "again_b", "opening"]),
    lambda d: d["repeat"].update(initial_cursor=True),
    lambda d: d["repeat"].update(initial_cursor=1),
    lambda d: d["repeat"].update(random_address=1000),
    lambda d: d.update(newline_resource="missing"),
    lambda d: d["resources"].update(line_end="not a newline"),
])
def test_invalid_definition_is_rejected_even_when_field_would_be_unused(mutate):
    doc = document()
    mutate(doc)
    with pytest.raises(DoorIntentError):
        validate_uil(doc)


def test_text_budget_applies_to_the_whole_catalogue_not_only_each_resource():
    doc = document()
    doc["resources"]["unused_a"] = "a" * (MAX_TEXT_BYTES // 2)
    doc["resources"]["unused_b"] = "b" * (MAX_TEXT_BYTES // 2)
    with pytest.raises(DoorIntentError, match="byte budget"):
        validate_uil(doc)


def test_bag_size_limit_is_independent_of_the_larger_resource_catalogue_limit():
    doc = document()
    names = ["response_" + str(index) for index in range(MAX_BAG_SIZE + 1)]
    doc["resources"].update({name: "Reply" for name in names})
    doc["repeat"]["resources"] = names
    doc["repeat"]["initial_order"] = list(names)
    with pytest.raises(DoorIntentError, match="response bag"):
        validate_uil(doc)


@pytest.mark.parametrize("mutate", [
    lambda s: s.update(door_open=0),
    lambda s: s.update(hint_dismissed="false"),
    lambda s: s.update(turn_count=1),
    lambda s: s.pop("response_bag"),
    lambda s: s.update(response_bag=[]),
    lambda s: s["response_bag"].update(order=["again_a"]),
    lambda s: s["response_bag"].update(order=["again_a", "again_a", "again_c"]),
    lambda s: s["response_bag"].update(order=["again_a", "again_b", "missing"]),
    lambda s: s["response_bag"].update(cursor=True),
    lambda s: s["response_bag"].update(cursor=-1),
    lambda s: s["response_bag"].update(cursor=3),
    lambda s: s["response_bag"].update(seed=12),
])
def test_malformed_state_is_not_treated_as_missing_or_false(mutate):
    current = state()
    mutate(current)
    with pytest.raises(DoorIntentError):
        evaluate_interaction(document(), current, "open")


@pytest.mark.parametrize("draw", [None, True, 0, -1, 3, 1.0, "1"])
def test_draw_is_a_bounded_one_based_integer_from_remaining_suffix(draw):
    bag = {"order": ["again_a", "again_b", "again_c"], "cursor": 1}
    with pytest.raises(DoorIntentError):
        select_response(document(), bag, draw)


def test_selecting_feedback_requires_known_bag_without_manufacturing_initial_state():
    with pytest.raises(DoorIntentError):
        select_response(document(), None, 1)


@pytest.mark.parametrize("action", [None, 1, {}, [], "x" * 161, "open\n"])
def test_malformed_action_is_rejected(action):
    with pytest.raises(DoorIntentError):
        evaluate_interaction(document(), state(), action)


def test_names_and_text_are_supplied_by_document_with_no_game_specific_defaults():
    doc = document()
    doc["door"] = "hangar_shutter"
    doc["history_fact"] = "shutter_hint_dismissed"
    doc["resources"]["opening"] = "The shutter rolls upward."
    result = evaluate_interaction(doc, state(), "open")
    assert result["effects"][0]["fact"] == "shutter_hint_dismissed"
    assert result["effects"][1]["text"] == "The shutter rolls upward."
    assert result["effects"][2]["door"] == "hangar_shutter"
    assert all("turn" not in effect["type"] for effect in result["effects"])
