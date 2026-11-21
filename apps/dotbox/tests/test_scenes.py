"""Authored offline scene claims, choices and guide reconciliation."""

from copy import deepcopy
import hashlib
import json
import os

import pytest


def packet():
    return {
        "format": "dotbox-scene-1", "source_sha256": "a" * 64,
        "edition": "authored-1", "scene_id": "station", "observation_id": "frame-7",
        "title": "Outside the station",
        "facts": [
            {"id": "mailbox", "subject": "mailbox", "predicate": "open", "value": False,
             "text": "A closed mailbox stands beside you.", "detail": "Its paint is chipped.",
             "audience": "player", "observation_id": "frame-7", "evidence_ref": "private/frame7.png"},
            {"id": "radio", "subject": "radio", "predicate": "present", "value": True,
             "text": "A radio sits in the window.", "audience": "player",
             "observation_id": "frame-7", "evidence_ref": "private/frame7.png"},
            {"id": "secret", "subject": "hidden_key", "predicate": "present", "value": True,
             "text": "SECRET key behind the counter.", "audience": "internal",
             "observation_id": "frame-7", "evidence_ref": "private/secret.bin"},
            {"id": "old_exit", "subject": "exit", "predicate": "direction", "value": "south",
             "text": "STALE southern exit.", "audience": "player",
             "observation_id": "frame-6", "evidence_ref": "private/frame6.png"},
        ],
        "choices": [
            {"id": "open_mailbox", "label": "Open the mailbox", "requires": ["mailbox"],
             "observation_id": "frame-7", "available": True,
             "route": {"kind": "control", "revision": "b" * 64, "name": "open_mailbox"}},
            {"id": "listen", "label": "Listen to the radio", "requires": ["radio"],
             "observation_id": "frame-7", "available": True,
             "route": {"kind": "ordinary", "reference": "existing-supported-radio-control"}},
            {"id": "look", "label": "Look around", "requires": [],
             "observation_id": "frame-7", "available": True,
             "route": {"kind": "ordinary", "reference": "existing-supported-look-control"}},
            {"id": "secret_choice", "label": "Take the SECRET key", "requires": ["secret"],
             "observation_id": "frame-7", "available": True,
             "route": {"kind": "ordinary", "reference": "existing-key-control"}},
            {"id": "old_choice", "label": "Use the STALE exit", "requires": ["old_exit"],
             "observation_id": "frame-7", "available": True,
             "route": {"kind": "ordinary", "reference": "existing-exit-control"}},
        ],
        "guide_sources": [
            {"id": "manual", "reference": "private/MANUAL_SECRET.txt", "edition": "authored-1",
             "origin_group": "publisher", "sha256": "c" * 64, "locator": "page 2"},
            {"id": "mirror", "reference": "private/MIRROR_SECRET.txt", "edition": "authored-1",
             "origin_group": "publisher"},
            {"id": "other", "reference": "private/OTHER_SECRET.txt", "edition": "unknown",
             "origin_group": "independent"},
        ],
        "guide_claims": [
            {"id": "opened", "source_id": "manual", "subject": "mailbox", "predicate": "open",
             "value": True, "text": "GUIDE says the mailbox is open.", "condition": ""},
            {"id": "closed", "source_id": "mirror", "subject": "mailbox", "predicate": "open",
             "value": False, "text": "GUIDE says the mailbox is closed.", "condition": ""},
            {"id": "barrel", "source_id": "manual", "subject": "barrel", "predicate": "present",
             "value": True, "text": "GUIDE expects a barrel.", "condition": ""},
            {"id": "conditional", "source_id": "manual", "subject": "mailbox", "predicate": "open",
             "value": True, "text": "GUIDE conditional opening.", "condition": "after unlocking"},
            {"id": "uncertain", "source_id": "other", "subject": "mailbox", "predicate": "open",
             "value": True, "text": "GUIDE from an unknown edition.", "condition": ""},
        ],
    }


def test_player_projection_uses_current_visible_claims_without_guide_or_private_leakage():
    from dotbox.scenes import project_scene

    result = project_scene(packet(), choice_limit=1)
    assert [fact["id"] for fact in result["facts"]] == ["mailbox", "radio"]
    assert result["choices"] == [
        {"id": "open_mailbox", "label": "Open the mailbox"},
        {"id": "listen", "label": "Listen to the radio"},
        {"id": "look", "label": "Look around"},
    ]
    assert result["suggested_choice_ids"] == ["open_mailbox"]
    assert result["omitted_choices"] == 2
    assert "closed mailbox" in result["narration"]
    encoded = json.dumps(result)
    assert all(secret not in encoded for secret in ("SECRET", "STALE", "GUIDE", "private/", "barrel", "route"))


def test_detail_levels_preserve_facts_choices_and_identity_without_adding_information():
    from dotbox.scenes import project_scene

    views = [project_scene(packet(), detail=level) for level in ("brief", "normal", "detailed")]
    for key in ("facts", "choices", "scene_sha256", "observation_id", "suggested_choice_ids", "choice_prompt"):
        assert views[0][key] == views[1][key] == views[2][key]
    assert "radio sits" not in views[0]["narration"]
    assert "radio sits" in views[1]["narration"]
    assert "paint is chipped" not in views[1]["narration"]
    assert "paint is chipped" in views[2]["narration"]
    for view in views:
        assert all(secret not in json.dumps(view) for secret in ("SECRET", "STALE", "GUIDE", "private/"))


@pytest.mark.parametrize("indices, limit, expected", [
    ([0], 3, "You can choose: Open the mailbox."),
    ([0, 1, 2], 3, "You can choose: Open the mailbox; Listen to the radio; Look around."),
    ([], 3, ""),
    ([0, 1, 2], 1, "You can choose: Open the mailbox. 2 more options are available."),
])
def test_choice_prompt_describes_only_the_suggested_eligible_choices(indices, limit, expected):
    from dotbox.scenes import project_scene

    document = packet()
    document["choices"] = [document["choices"][index] for index in indices]
    view = project_scene(document, choice_limit=limit)
    assert view["choice_prompt"] == expected
    assert len(view["choices"]) == len(indices)
    assert view["omitted_choices"] == max(0, len(indices) - limit)


def test_checklist_preserves_disagreement_without_voting_or_inventing_absence():
    from dotbox.scenes import reconstruction_checklist

    result = reconstruction_checklist(packet())
    groups = {group["subject"]: group for group in result["groups"]}
    mailbox = groups["mailbox"]
    assert mailbox["status"] == "observed" and mailbox["guide_disagreement"]
    assert mailbox["expected_values"] == [True, False]
    assert mailbox["source_count"] == 2 and mailbox["origin_group_count"] == 1
    claims = {claim["id"]: claim for claim in mailbox["claims"]}
    assert claims["opened"]["status"] == "contradicted"
    assert claims["closed"]["status"] == "matched"
    assert claims["conditional"]["status"] == "pending"
    assert claims["conditional"]["pending_reasons"] == ["condition_unchecked"]
    assert claims["uncertain"]["pending_reasons"] == ["edition_unverified"]
    assert groups["barrel"]["status"] == "unresolved"
    assert groups["barrel"]["current_observations"] == []
    assert groups["radio"]["status"] == "observed" and groups["radio"]["claims"] == []
    assert result["scope"] == "internal_only"
    assert "never truth votes" in result["count_scope"]


def test_agreeing_guides_without_observation_remain_unresolved():
    from dotbox.scenes import reconstruction_checklist

    document = packet()
    document["facts"][0]["observation_id"] = "older-frame"
    document["guide_sources"][2]["edition"] = "authored-1"
    group = next(group for group in reconstruction_checklist(document)["groups"] if group["subject"] == "mailbox")
    assert group["status"] == "unresolved"
    assert group["source_count"] == 3 and group["origin_group_count"] == 2
    assert group["guide_disagreement"]
    assert [claim["status"] for claim in group["claims"]] == ["unresolved", "unresolved", "pending", "unresolved"]


@pytest.mark.parametrize("packet_edition, source_edition, reason", [
    ("authored-1", "different-edition", "edition_mismatch"),
    ("unknown", "unknown", "edition_unverified"),
    ("authored-1", "UNKNOWN", "edition_unverified"),
])
def test_mismatched_and_unknown_editions_never_confirm_a_claim(packet_edition, source_edition, reason):
    from dotbox.scenes import reconstruction_checklist

    document = packet()
    document["edition"] = packet_edition
    document["guide_sources"][1]["edition"] = source_edition
    group = next(group for group in reconstruction_checklist(document)["groups"] if group["subject"] == "mailbox")
    claim = next(claim for claim in group["claims"] if claim["id"] == "closed")
    assert claim["status"] == "pending" and claim["pending_reasons"] == [reason]


def test_internal_observation_can_reconcile_a_checklist_but_never_a_player_choice():
    from dotbox.scenes import project_scene, reconstruction_checklist

    document = packet()
    document["guide_claims"].append({"id": "secret_expected", "source_id": "manual",
        "subject": "hidden_key", "predicate": "present", "value": True,
        "text": "SECRET guide expectation.", "condition": ""})
    group = next(group for group in reconstruction_checklist(document)["groups"] if group["subject"] == "hidden_key")
    assert group["claims"][0]["status"] == "matched"
    assert group["current_observations"][0]["audience"] == "internal"
    assert "SECRET" not in json.dumps(project_scene(document, detail="detailed"))


@pytest.mark.parametrize("value", [True, 0])
def test_conflicting_current_values_are_rejected_including_boolean_integer_aliases(value):
    from dotbox.scenes import validate_scene

    document = packet()
    conflict = {**document["facts"][0], "id": "conflict", "value": value, "audience": "internal"}
    document["facts"].append(conflict)
    with pytest.raises(ValueError, match="Contradictory"):
        validate_scene(document)
    conflict["observation_id"] = "old-frame"
    validate_scene(document)  # Historical contradictions cannot overwrite the current observation.


def test_guide_scalar_comparison_does_not_equate_false_and_zero():
    from dotbox.scenes import reconstruction_checklist

    document = packet()
    document["guide_claims"][1]["value"] = 0
    group = next(group for group in reconstruction_checklist(document)["groups"] if group["subject"] == "mailbox")
    assert next(claim for claim in group["claims"] if claim["id"] == "closed")["status"] == "contradicted"


def test_known_ordinary_action_needs_no_complete_scene_or_guides():
    from dotbox.scenes import project_scene, select_choice

    document = packet()
    document["facts"], document["guide_sources"], document["guide_claims"] = [], [], []
    document["choices"] = [document["choices"][2]]
    view = project_scene(document)
    assert view["facts"] == [] and view["choices"] == [{"id": "look", "label": "Look around"}]
    intent = select_choice(document, "look", view["scene_sha256"], view["observation_id"])
    assert intent["execution"] == "not_performed"


@pytest.mark.parametrize("change", [{"available": False}, {"observation_id": "old-frame"}])
def test_unavailable_or_stale_choices_are_not_offered(change):
    from dotbox.scenes import project_scene, select_choice

    document = packet()
    document["choices"][0].update(change)
    view = project_scene(document)
    assert "open_mailbox" not in [choice["id"] for choice in view["choices"]]
    with pytest.raises(ValueError, match="not currently offered"):
        select_choice(document, "open_mailbox", view["scene_sha256"], view["observation_id"])


def test_selection_binds_exact_document_and_observation_and_refuses_hidden_choices():
    from dotbox.scenes import project_scene, select_choice

    document = packet()
    view = project_scene(document)
    expected = hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    assert view["scene_sha256"] == expected
    with pytest.raises(ValueError, match="Stale"):
        select_choice(document, "open_mailbox", "d" * 64, view["observation_id"])
    with pytest.raises(ValueError, match="Stale"):
        select_choice(document, "open_mailbox", expected, "frame-6")
    for name in ("secret_choice", "old_choice", "nonexistent"):
        with pytest.raises(ValueError, match="not currently offered"):
            select_choice(document, name, expected, view["observation_id"])
    document["guide_claims"][0]["text"] += " Revised source claim."
    with pytest.raises(ValueError, match="Stale"):
        select_choice(document, "open_mailbox", expected, view["observation_id"])


def test_offline_apis_are_defensive_and_never_execute_or_start_learning(monkeypatch):
    from dotbox import backend, client, learning
    from dotbox.scenes import project_scene, reconstruction_checklist, select_choice, validate_scene

    def forbidden(*args, **kwargs):
        pytest.fail("An offline scene API attempted a live or learning operation")
    for owner in (client.Client, backend.DOSBoxBackend, learning.LearningStore):
        monkeypatch.setattr(owner, "__init__", forbidden)
    document = packet()
    document["selection_sha256"] = "d" * 64
    before = deepcopy(document)
    copied = validate_scene(document)
    copied["facts"][0]["text"] = "Changed independent copy"
    view = project_scene(document)
    reconstruction_checklist(document)
    first = select_choice(document, "open_mailbox", view["scene_sha256"], view["observation_id"])
    second = select_choice(document, "open_mailbox", view["scene_sha256"], view["observation_id"])
    assert first == second  # The human and autonomous driver consume the same choice intent.
    assert first["route"] == before["choices"][0]["route"]
    assert first["source_sha256"] == before["source_sha256"]
    assert first["selection_sha256"] == "d" * 64
    assert first["execution"] == "not_performed" and first["live_applicability"] == "unverified"
    first["route"]["name"] = "changed_copy"
    assert document == before


@pytest.mark.parametrize("mutate", [
    lambda doc: doc.update(extra=True),
    lambda doc: doc["facts"][0].update(extra=True),
    lambda doc: doc["choices"][0]["route"].update(steps=["injected input"]),
    lambda doc: doc["choices"][0].update(requires=["missing_fact"]),
    lambda doc: doc["choices"][0].update(available=1),
    lambda doc: doc["guide_claims"][0].update(source_id="missing_source"),
    lambda doc: doc["guide_sources"][0].update(sha256="C" * 64),
    lambda doc: doc["facts"][0].update(value=0.5),
    lambda doc: doc["facts"][0].update(value={"executable": "code"}),
    lambda doc: doc["facts"].append(deepcopy(doc["facts"][0])),
])
def test_invalid_bindings_unknown_fields_and_non_scalar_values_are_refused(mutate):
    from dotbox.scenes import validate_scene

    document = packet()
    mutate(document)
    with pytest.raises(ValueError):
        validate_scene(document)


@pytest.mark.parametrize("name, maximum", [("facts", 32), ("choices", 32), ("guide_sources", 3), ("guide_claims", 64)])
def test_record_counts_are_bounded(name, maximum):
    from dotbox.scenes import validate_scene

    document = packet()
    document[name] = [document[name][0]] * (maximum + 1)
    with pytest.raises(ValueError, match="at most"):
        validate_scene(document)


def test_canonical_document_budget_is_enforced_independently_of_field_limits():
    from dotbox.scenes import validate_scene

    document = packet()
    template = document["facts"][0]
    document["facts"] = [{**template, "id": f"fact_{n}", "text": "a" * 2048} for n in range(32)]
    document["choices"] = []
    with pytest.raises(ValueError, match="48 KiB"):
        validate_scene(document)


@pytest.mark.parametrize("options", [{"choice_limit": 0}, {"choice_limit": 33}, {"choice_limit": True}, {"detail": "inventive"}])
def test_projection_options_are_bounded(options):
    from dotbox.scenes import project_scene

    with pytest.raises(ValueError):
        project_scene(packet(), **options)


@pytest.mark.parametrize("operation", ["present", "checklist", "choose", "validate"])
def test_cli_commands_use_explicit_frozen_json_without_mutation(tmp_path, capsys, operation):
    from dotbox.scenes import main, project_scene

    path = tmp_path / "scene.json"
    before = json.dumps(packet(), indent=2).encode()
    path.write_bytes(before)
    arguments = [operation, str(path)]
    view = project_scene(packet())
    if operation == "choose":
        arguments += ["--choice", "open_mailbox", "--scene-sha256", view["scene_sha256"], "--observation-id", "frame-7"]
    assert main(arguments) == 0
    output = capsys.readouterr()
    assert not output.err
    result = json.loads(output.out)
    assert result["ok"] is True and result["result"]["scene_sha256"] == view["scene_sha256"]
    assert path.read_bytes() == before


def test_cli_refuses_symlinks_special_files_and_oversized_reads(tmp_path, capsys):
    from dotbox.scenes import MAX_FILE_BYTES, main

    source = tmp_path / "scene.json"
    source.write_text(json.dumps(packet()))
    link = tmp_path / "link.json"
    link.symlink_to(source)
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (MAX_FILE_BYTES + 1))
    for path in (link, fifo, tmp_path, oversized):
        assert main(["present", str(path)]) == 1
        output = capsys.readouterr()
        assert output.out == "" and json.loads(output.err)["ok"] is False


def test_cli_refuses_duplicate_json_fields_and_reports_parser_errors(tmp_path, capsys):
    from dotbox.scenes import main

    path = tmp_path / "scene.json"
    path.write_text(json.dumps(packet()).replace('"title":', '"title": "conflicting", "title":', 1))
    assert main(["present", str(path)]) == 1
    assert "Duplicate JSON field" in json.loads(capsys.readouterr().err)["error"]
    assert main(["choose", str(path)]) == 1
    output = capsys.readouterr()
    assert output.out == "" and json.loads(output.err)["ok"] is False
