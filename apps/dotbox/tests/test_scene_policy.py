"""Behavioral checks for provider state, useful choices and passive look."""

from copy import deepcopy
import json

import pytest


def _fact(identity, subject, predicate, value, text, *, audience="player"):
    return {"id": identity, "subject": subject, "predicate": predicate,
            "value": value, "text": text, "audience": audience,
            "observation_id": "observation-1", "evidence_ref": "private/observation-1.json"}


def _choice(identity, label, *, requires=(), **policy):
    return {"id": identity, "label": label, "requires": list(requires),
            "observation_id": "observation-1", "available": True,
            "route": {"kind": "ordinary", "reference": "qualified-input-" + identity},
            **policy}


def _packet():
    return {"format": "dotbox-scene-1", "source_sha256": "a" * 64,
            "edition": "authored-state-policy-1", "scene_id": "hall",
            "observation_id": "observation-1", "title": "Hall",
            "facts": [_fact("window_open", "window", "open", False,
                            "The window is closed.")],
            "choices": [
                _choice("open_window", "Open the window", requires=["window_open"],
                        enabled=True, ready=True),
                _choice("close_window", "Close the window", requires=["window_open"],
                        enabled=False, ready=True),
            ],
            "guide_sources": [], "guide_claims": []}


def _state_context(revision=1):
    return {"provider_id": "provider-private-marker", "session_id": "session-private-marker",
            "branch_id": "branch-private-marker", "revision": revision,
            "context_token": "opaque-private-token-do-not-narrate"}


def _outcome(*, complete=False, effects="unknown"):
    return {"id": "outcome_private_marker", "action_sent": True,
            "complete": complete, "effects": effects, "phase": "interface",
            "evidence_ref": "private/unseen-switch-receipt.json"}


def _ids(view):
    return [choice["id"] for choice in view["choices"]]


def test_provider_window_transition_removes_open_and_refuses_old_intent():
    from dotbox.scenes import project_scene, select_choice

    closed = _packet()
    closed["state_context"] = _state_context()
    before = project_scene(closed)
    assert _ids(before) == ["open_window"]

    opened = deepcopy(closed)
    opened["facts"][0].update(value=True, text="The window is open.")
    opened["choices"][0]["enabled"] = False
    opened["choices"][1]["enabled"] = True
    opened["state_context"]["revision"] = 2
    after = project_scene(opened)
    assert _ids(after) == ["close_window"]
    assert "Open the window" not in after["choice_prompt"]
    with pytest.raises(ValueError, match="Stale"):
        select_choice(opened, "open_window", before["scene_sha256"], before["observation_id"])
    with pytest.raises(ValueError, match="not currently offered"):
        select_choice(opened, "open_window", after["scene_sha256"], after["observation_id"])
    assert select_choice(opened, "close_window", after["scene_sha256"],
                         after["observation_id"])["execution"] == "not_performed"


@pytest.mark.parametrize("locked", [True, False, None])
def test_closed_door_and_lock_state_remain_independent_provider_observations(locked):
    from dotbox.scenes import project_scene, select_choice

    document = _packet()
    document["facts"] = [
        _fact("door_open", "door", "open", False, "The door is closed."),
        _fact("door_locked", "door", "locked", locked,
              "The lock has not been checked." if locked is None else
              "The door is locked." if locked else "The door is unlocked."),
    ]
    document["choices"] = [_choice("try_door", "Try the door", requires=["door_open"],
                                    enabled=True, ready=True)]
    view = project_scene(document)
    assert {fact["predicate"]: fact["value"] for fact in view["facts"]} == {
        "open": False, "locked": locked}
    assert _ids(view) == ["try_door"]
    assert select_choice(document, "try_door", view["scene_sha256"],
                         view["observation_id"])["execution"] == "not_performed"
    if locked is None:
        assert "unlocked" not in view["narration"]


@pytest.mark.parametrize("gate", ["enabled", "ready"])
@pytest.mark.parametrize("state", [False, None])
def test_false_or_unknown_provider_gate_excludes_selection_even_if_available(gate, state):
    from dotbox.scenes import project_scene, select_choice

    document = _packet()
    document["choices"][0][gate] = state
    view = project_scene(document)
    assert _ids(view) == []
    with pytest.raises(ValueError, match="not currently offered"):
        select_choice(document, "open_window", view["scene_sha256"], view["observation_id"])


def test_confirmed_effect_does_not_make_a_busy_input_route_ready():
    from dotbox.scenes import project_scene, select_choice

    document = _packet()
    document["facts"][0].update(value=True, text="The window is open.")
    document["choices"][0]["enabled"] = False
    document["choices"][1].update(enabled=True, ready=False)
    document["outcome"] = _outcome(effects="applied-confirmed")
    view = project_scene(document)
    assert view["facts"][0]["value"] is True
    assert "window is open" in view["narration"]
    assert _ids(view) == []
    with pytest.raises(ValueError, match="not currently offered"):
        select_choice(document, "close_window", view["scene_sha256"], view["observation_id"])


def test_action_acknowledgment_does_not_change_observed_flags_or_admission():
    from dotbox.scenes import project_scene

    document = _packet()
    document["outcome"] = _outcome(effects="unknown")
    before = deepcopy(document)
    view = project_scene(document)
    assert view["facts"][0]["value"] is False
    assert _ids(view) == ["open_window"]
    assert document == before


def test_on_request_verb_remains_explicitly_selectable_without_entering_shortlist():
    from dotbox.scenes import project_scene, select_choice

    document = _packet()
    document["choices"].insert(0, _choice("lick_window", "Lick the window",
                                          requires=["window_open"], suggestion="on_request"))
    view = project_scene(document, choice_limit=1)
    assert _ids(view) == ["lick_window", "open_window"]
    assert view["suggested_choice_ids"] == ["open_window"]
    assert "Lick" not in view["choice_prompt"]
    assert view["omitted_choices"] == 1
    intent = select_choice(document, "lick_window", view["scene_sha256"], view["observation_id"])
    assert intent["choice_id"] == "lick_window" and intent["execution"] == "not_performed"

    document["choices"][0]["suggestion"] = "prefer"
    assert project_scene(document, choice_limit=1)["suggested_choice_ids"] == ["lick_window"]


def test_preferred_actions_rank_stably_and_unready_preference_cannot_override_provider():
    from dotbox.scenes import project_scene

    document = _packet()
    document["choices"] = [
        _choice("normal_first", "Inspect the room"),
        _choice("preferred_first", "Take the key", suggestion="prefer"),
        _choice("requested", "Lick the wall", suggestion="on_request"),
        _choice("preferred_second", "Go through the door", suggestion="prefer"),
        _choice("normal_second", "Listen", suggestion="normal"),
        _choice("busy", "Turn the handle", suggestion="prefer", ready=False),
    ]
    view = project_scene(document, choice_limit=4)
    assert _ids(view) == ["normal_first", "preferred_first", "requested", "preferred_second", "normal_second"]
    assert view["suggested_choice_ids"] == ["preferred_first", "preferred_second", "normal_first", "normal_second"]
    assert view["omitted_choices"] == 1
    assert "Turn the handle" not in view["choice_prompt"]


def test_only_on_request_choices_do_not_promote_an_arbitrary_verb():
    from dotbox.scenes import project_scene

    document = _packet()
    document["choices"] = [_choice("lick", "Lick the wall", suggestion="on_request")]
    view = project_scene(document)
    assert _ids(view) == ["lick"]
    assert view["suggested_choice_ids"] == []
    assert view["omitted_choices"] == 1
    assert view["choice_prompt"] == "Other actions are available on request."


def test_private_state_and_unseen_effects_bind_selection_without_leaking_to_player():
    from dotbox.scenes import look_scene, project_scene, select_choice

    document = _packet()
    document["state_context"] = _state_context()
    document["outcome"] = _outcome(complete=True, effects="applied-confirmed")
    document["facts"].append(_fact("remote_flag", "unseen_remote_door", "locked", False,
                                   "SECRET remote door unlocked.", audience="internal"))
    for view in (project_scene(document), look_scene(document)):
        encoded = json.dumps(view)
        assert all(secret not in encoded for secret in (
            "provider-private-marker", "session-private-marker", "branch-private-marker",
            "opaque-private-token-do-not-narrate", "outcome_private_marker", "private/",
            "unseen_remote_door", "SECRET", "applied-confirmed", "evidence_ref", "context_token"))

    view = project_scene(document)
    intent = select_choice(document, "open_window", view["scene_sha256"], view["observation_id"])
    assert intent["state_context"] == document["state_context"]
    intent["state_context"]["context_token"] = "changed-copy"
    assert document["state_context"]["context_token"] == "opaque-private-token-do-not-narrate"

    advanced = deepcopy(document)
    advanced["state_context"]["revision"] += 1
    advanced["state_context"]["context_token"] = "new-provider-token"
    assert advanced["scene_id"] == document["scene_id"]
    assert advanced["observation_id"] == document["observation_id"]
    with pytest.raises(ValueError, match="Stale"):
        select_choice(advanced, "open_window", view["scene_sha256"], view["observation_id"])


def test_passive_look_uses_current_description_without_execution_or_mutating_input(monkeypatch):
    from dotbox import backend, client, learning, scene_state
    from dotbox.scenes import look_scene, project_scene

    def forbidden(*args, **kwargs):
        pytest.fail("Passive look attempted a live operation or opened a store")

    for owner in (client.Client, backend.DOSBoxBackend, learning.LearningStore, scene_state.SceneStore):
        monkeypatch.setattr(owner, "__init__", forbidden)
    document = _packet()
    document["facts"][0]["detail"] = "Its frame has chipped green paint."
    document["state_context"] = _state_context()
    before = deepcopy(document)
    description = look_scene(document, detail="detailed")
    assert description["format"] == "dotbox-scene-description-1"
    assert description["narration"] == project_scene(document, detail="detailed")["narration"]
    assert description["facts"][0]["value"] is False
    assert description["execution"] == "not_performed"
    assert all(key not in description for key in ("choices", "suggested_choice_ids", "choice_prompt", "route"))
    description["facts"][0]["text"] = "Modified returned copy"
    assert document == before


def test_passive_look_does_not_rewrite_legacy_game_input_choice():
    from dotbox.scenes import look_scene, project_scene, select_choice

    document = _packet()
    document["choices"] = [_choice("look", "Look around")]
    view = project_scene(document)
    before = deepcopy(document)
    assert look_scene(document)["execution"] == "not_performed"
    intent = select_choice(document, "look", view["scene_sha256"], view["observation_id"])
    assert intent["route"] == {"kind": "ordinary", "reference": "qualified-input-look"}
    assert intent["execution"] == "not_performed"
    assert document == before


def test_cli_look_returns_description_and_preserves_observation_file(tmp_path, capsys):
    from dotbox.scenes import main

    path = tmp_path / "observation.json"
    raw = json.dumps(_packet()).encode()
    path.write_bytes(raw)
    assert main(["look", str(path), "--detail", "brief"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    result = json.loads(output.out)["result"]
    assert result["format"] == "dotbox-scene-description-1"
    assert result["execution"] == "not_performed"
    assert "choice_prompt" not in result
    assert path.read_bytes() == raw
