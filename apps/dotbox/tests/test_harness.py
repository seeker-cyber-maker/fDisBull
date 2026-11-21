"""Persistent controls use independent SQLite storage without a guest or fDisBull."""

from copy import deepcopy

import pytest

from dotbox.harness import HarnessLibrary
from dotbox.store import ControlStore


def controls(*, name="playground", key="right"):
    return {
        "format": "fdisbull-macro-set-1",
        "name": name,
        "macros": {
            "move": {
                "authority": "player-input",
                "steps": [{"op": "keyboard.press", "key": key,
                           "hold_ms": 40, "gap_ms": 40}],
            },
        },
    }


@pytest.fixture
def project(tmp_path):
    program = tmp_path / "PLAY.COM"
    program.write_bytes(bytes.fromhex("b8 00 4c cd 21"))
    with ControlStore(tmp_path / "play.fdb", program) as opened:
        yield opened


def test_controls_survive_project_reopen_without_redefinition(tmp_path):
    program = tmp_path / "PLAY.COM"
    program.write_bytes(bytes.fromhex("b8 00 4c cd 21"))
    path = tmp_path / "play.fdb"
    with ControlStore(path, program) as project:
        library = HarnessLibrary(project)
        saved = library.save(controls())
        revision = saved["revision"]
        assert saved["id"] == revision
        assert library.save(deepcopy(controls()))["revision"] == revision
        assert len(library.list()["revisions"]) == 1

    with ControlStore(path) as project:
        library = HarnessLibrary(project)
        info = library.info(revision)
        assert info["revision"] == revision
        assert info["definition"] == controls()
        assert info["binding"]["version_sha256"] == project.version(1)["sha256"]
        assert info["binding"]["source_sha256"] == project.source_binding_sha256(1)
        plan = library.plan(revision, "move")
        assert plan["revision"] == revision and plan["name"] == "move"
        assert plan["steps"] == [{"op": "key", "params": {
            "key": "right", "modifiers": [], "hold_ms": 40, "gap_ms": 40}}]
        assert plan["queued_guest_ms"] == 80
        assert library.list()["truncated"] is False


def test_legacy_keyboard_document_keeps_its_known_immutable_manifest_id(project):
    # A fixed canonical manifest from the source-attested standalone format.
    # Keep this literal ID so a future format rewrite cannot silently re-key it.
    expected = "55f36aba98a6b281094ac7fb634c01b671cf86fb1f4c7cdff0b30c5381feda5b"
    saved = HarnessLibrary(project).save(controls())
    assert saved["revision"] == expected
    document = project.db.execute(
        "SELECT document FROM dotbox_control_sets WHERE id=?", (expected,)).fetchone()[0]
    project.db.execute("UPDATE dotbox_control_sets SET created='2026-11-14T00:00:00+00:00' WHERE id=?", (expected,))
    assert HarnessLibrary(project).info(expected)["definition"] == controls()
    assert HarnessLibrary(project).save(controls())["revision"] == expected
    assert project.db.execute(
        "SELECT document FROM dotbox_control_sets WHERE id=?", (expected,)).fetchone()[0] == document


def test_explicit_old_revisions_and_sibling_branches_remain_usable(project):
    library = HarnessLibrary(project)
    original = library.save(controls())["revision"]
    left = library.save(controls(key="left"), parent=original)["revision"]
    up = library.save(controls(key="up"), parent=original)["revision"]

    assert len({original, left, up}) == 3
    assert library.info(original)["parent"] is None
    assert library.info(left)["parent"] == library.info(up)["parent"] == original
    for revision, expected in ((original, "right"), (left, "left"), (up, "up")):
        assert library.plan(revision, "move")["steps"][0]["params"]["key"] == expected
    assert {item["revision"] for item in library.list()["revisions"]} == {original, left, up}


def test_parent_must_exist_and_have_the_same_vocabulary_name(project):
    library = HarnessLibrary(project)
    original = library.save(controls())["revision"]
    before = library.list()
    with pytest.raises(ValueError):
        library.save(controls(name="other"), parent=original)
    with pytest.raises(ValueError):
        library.save(controls(key="left"), parent="0" * 64)
    assert library.list() == before


def test_persisted_row_from_another_source_is_not_accepted(tmp_path):
    first_program, second_program = tmp_path / "A.COM", tmp_path / "B.COM"
    first_program.write_bytes(bytes.fromhex("b8 00 4c cd 21"))
    second_program.write_bytes(bytes.fromhex("90 b8 00 4c cd 21"))
    with ControlStore(tmp_path / "a.fdb", first_program) as first:
        revision = HarnessLibrary(first).save(controls())["revision"]
        # Deliberately contaminate a second project with a persisted metadata
        # row. This exercises the source binding check, rather than merely an
        # unknown-revision lookup, without adding an import API to DotBox.
        record = tuple(first.db.execute(
            "SELECT * FROM dotbox_control_sets WHERE id=?", (revision,)).fetchone())
        with ControlStore(tmp_path / "b.fdb", second_program) as second:
            HarnessLibrary(second).save(controls())
            with second.transaction(True):
                second.db.execute("INSERT INTO dotbox_control_sets VALUES (?,?,?,?,?,?,?)", record)
            with pytest.raises(ValueError, match="binding|source|version"):
                HarnessLibrary(second).info(revision)


def test_unknown_revision_or_control_is_not_substituted(project):
    library = HarnessLibrary(project)
    revision = library.save(controls())["revision"]
    with pytest.raises(ValueError):
        library.info("0" * 64)
    with pytest.raises(ValueError):
        library.plan(revision, "unlearned")
    assert len(library.list()["revisions"]) == 1


@pytest.mark.parametrize("invalid_step", [
    {"op": "run", "guest_ms": 10},
    {"op": "memory", "address": 0, "size": 1},
    {"op": "keyboard.state"},
    {"op": "keyboard.key-down", "key": "left"},
    {"op": "macro", "name": "move"},
    {"op": "keyboard.press", "key": "$args.direction"},
    {"op": "keyboard.press", "key": "left", "as": "input"},
    {"op": "keyboard.press", "key": "left", "unexpected": True},
    {"op": "keyboard.press", "key": "left", "hold_ms": True},
    {"op": "keyboard.press", "key": "left", "gap_ms": 0},
    {"op": "keyboard.press", "key": "left", "modifiers": ["ctrl", "ctrl"]},
    {"op": "keyboard.type", "text": "not ASCII: \u2603"},
    {"op": "keyboard.type", "text": "$input.accepted"},
])
def test_invalid_later_step_rejects_the_whole_definition_before_saving(project, invalid_step):
    library = HarnessLibrary(project)
    definition = controls()
    definition["macros"]["move"]["steps"].append(invalid_step)
    with pytest.raises(ValueError):
        library.save(definition)
    assert library.list() == {"revisions": [], "truncated": False}


@pytest.mark.parametrize("change", [
    {"authority": "diagnostic"},
    {"authority": "authoring"},
    {"parameters": {"direction": {"type": "string"}}},
    {"outputs": {"accepted": "$input.accepted"}},
    {"parameters": []}, {"parameters": None}, {"outputs": []}, {"outputs": None},
])
def test_runtime_parameters_outputs_and_other_authorities_are_not_starting_controls(project, change):
    library = HarnessLibrary(project)
    definition = controls()
    definition["macros"]["move"].update(change)
    with pytest.raises(ValueError):
        library.save(definition)
    assert not library.list()["revisions"]


def test_all_controls_are_validated_before_any_revision_is_saved(project):
    library = HarnessLibrary(project)
    definition = controls()
    definition["macros"]["later"] = {
        "steps": [{"op": "keyboard.type", "text": "\x00"}],
    }
    with pytest.raises(ValueError):
        library.save(definition)
    assert not library.list()["revisions"]


@pytest.mark.parametrize("changed", [
    {"authority": "diagnostic"},
    {"steps": [{"op": "memory", "address": 0, "size": 1}]},
    {"steps": [{"op": "keyboard.press", "key": "right", "hold_ms": 600, "gap_ms": 600}]},
])
def test_general_core_macro_records_cannot_bypass_the_play_facade(project, changed):
    library = HarnessLibrary(project)
    supported = library.save(controls())["revision"]
    definition = controls(name="general_debugger")
    definition["macros"]["move"].update(changed)
    # A rehashed record inserted outside the public save API must not bypass
    # DotBox's smaller policy when its immutable ID is selected.
    import hashlib
    import json
    row = dict(project.db.execute(
        "SELECT * FROM dotbox_control_sets WHERE id=?", (supported,)).fetchone())
    document = {"definition": definition, "binding": library.info(supported)["binding"],
                "author": "other-tool", "parent": None}
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
    general = hashlib.sha256(encoded.encode()).hexdigest()
    with project.transaction(True):
        project.db.execute("INSERT INTO dotbox_control_sets VALUES (?,?,?,?,?,?,?)", (
            general, 1, None, row["created"], "other-tool", general, encoded))
    with pytest.raises(ValueError):
        library.info(general)
    with pytest.raises(ValueError):
        library.plan(general, "move")
    assert library.info(supported)["revision"] == supported


def test_step_limit_is_per_expanded_control(project):
    library = HarnessLibrary(project)
    definition = controls()
    definition["macros"]["move"]["steps"] = [
        {"op": "keyboard.press", "key": "right", "hold_ms": 1, "gap_ms": 1}
        for _ in range(16)
    ]
    revision = library.save(definition)["revision"]
    assert len(library.plan(revision, "move")["steps"]) == 16
    definition["macros"]["move"]["steps"].append(
        {"op": "keyboard.press", "key": "right", "hold_ms": 1, "gap_ms": 1})
    with pytest.raises(ValueError):
        library.save(definition, parent=revision)
    assert len(library.list()["revisions"]) == 1


def test_text_character_count_contributes_to_total_duration(project):
    library = HarnessLibrary(project)
    definition = controls()
    definition["macros"]["move"]["steps"] = [
        {"op": "keyboard.press", "key": "right", "hold_ms": 200, "gap_ms": 200},
        {"op": "keyboard.type", "text": "abc", "hold_ms": 100, "gap_ms": 100},
    ]
    revision = library.save(definition)["revision"]
    assert library.plan(revision, "move")["queued_guest_ms"] == 1000
    definition["macros"]["move"]["steps"][1]["text"] = "abcd"
    with pytest.raises(ValueError):
        library.save(definition, parent=revision)
    assert len(library.list()["revisions"]) == 1


def test_separate_controls_have_separate_duration_budgets(project):
    library = HarnessLibrary(project)
    definition = controls()
    definition["macros"] = {
        name: {"steps": [{"op": "keyboard.press", "key": key,
                          "hold_ms": 350, "gap_ms": 350}]}
        for name, key in (("move_left", "left"), ("move_right", "right"))
    }
    revision = library.save(definition)["revision"]
    assert library.plan(revision, "move_left")["queued_guest_ms"] == 700
    assert library.plan(revision, "move_right")["queued_guest_ms"] == 700


def test_control_count_limit_rejects_excess_without_changing_stored_revisions(project):
    library = HarnessLibrary(project)
    definition = controls()
    definition["macros"] = {
        f"move_{index}": {"steps": [{"op": "keyboard.press", "key": "right"}]}
        for index in range(32)
    }
    revision = library.save(definition)["revision"]
    definition["macros"]["too_many"] = {
        "steps": [{"op": "keyboard.press", "key": "right"}],
    }
    with pytest.raises(ValueError):
        library.save(definition, parent=revision)
    assert len(library.info(revision)["definition"]["macros"]) == 32
    assert len(library.list()["revisions"]) == 1


def mouse_controls(*, x=159, y=88, width=320, height=200, name="playground"):
    return {"format": "dotbox-control-set-1", "name": name, "controls": {
        "choose": {"authority": "player-input", "steps": [{
            "op": "mouse.click", "x": x, "y": y, "width": width, "height": height,
            "button": "left", "hold_ms": 80}]}}}


def test_absolute_mouse_revisions_survive_reopen_and_keep_legacy_parent(tmp_path):
    program = tmp_path / "PLAY.COM"
    program.write_bytes(bytes.fromhex("b8 00 4c cd 21"))
    path = tmp_path / "play.fdb"
    with ControlStore(path, program) as opened:
        library = HarnessLibrary(opened)
        legacy = library.save(controls())["revision"]
        definition = mouse_controls()
        definition["controls"]["move"] = controls()["macros"]["move"]
        first = library.save(definition, parent=legacy)["revision"]
        changed = deepcopy(definition)
        changed["controls"]["choose"]["steps"][0]["x"] = 19
        newer = library.save(changed, parent=first)["revision"]
        assert library.save(changed, parent=first)["revision"] == newer
    with ControlStore(path) as opened:
        library = HarnessLibrary(opened)
        assert library.info(first)["definition"] == definition
        assert library.info(first)["parent"] == legacy
        assert library.plan(first, "choose")["steps"] == [{"op": "click", "params": {
            "x": 159, "y": 88, "width": 320, "height": 200, "button": "left", "hold_ms": 80}}]
        assert library.plan(newer, "choose")["steps"][0]["params"]["x"] == 19
        assert library.plan(first, "move")["steps"][0]["op"] == "key"
        assert {row["revision"] for row in library.list()["revisions"]} == {legacy, first, newer}
        assert library.info(first)["binding"]["source_sha256"] == opened.source_binding_sha256(1)


@pytest.mark.parametrize("field,value", [
    ("x", True), ("x", 1.0), ("x", -1), ("x", 320),
    ("y", False), ("y", 2.5), ("y", -1), ("y", 200),
    ("width", True), ("width", 0), ("width", 4097), ("width", 320.0),
    ("height", False), ("height", 0), ("height", 4097),
    ("button", "double"), ("hold_ms", True), ("hold_ms", 0), ("hold_ms", 1001),
    ("dx", 2), ("dy", 2), ("relative", False), ("frame_id", 12),
    ("mode_id", 4), ("session_id", "old-session"), ("generation", 0),
    ("unexpected", "ignored"),
])
def test_invalid_absolute_mouse_fields_reject_whole_revision(project, field, value):
    library = HarnessLibrary(project)
    definition = mouse_controls()
    definition["controls"]["choose"]["steps"][0][field] = value
    with pytest.raises(ValueError):
        library.save(definition)
    assert library.list() == {"revisions": [], "truncated": False}
    assert not project.db.execute("SELECT 1 FROM sqlite_master WHERE name='dotbox_control_sets'").fetchone()


@pytest.mark.parametrize("missing", ["x", "y", "width", "height"])
def test_mouse_requires_absolute_position_and_original_dimensions(project, missing):
    definition = mouse_controls()
    del definition["controls"]["choose"]["steps"][0][missing]
    with pytest.raises(ValueError):
        HarnessLibrary(project).save(definition)


@pytest.mark.parametrize("extra", [
    {"op": "mouse.click", "x": 1, "y": 2, "width": 320, "height": 200},
    {"op": "keyboard.press", "key": "enter"},
])
def test_mixed_or_multiple_mouse_steps_reject_before_save(project, extra):
    definition = mouse_controls()
    definition["controls"]["choose"]["steps"].append(extra)
    with pytest.raises(ValueError, match="exactly one"):
        HarnessLibrary(project).save(definition)


@pytest.mark.parametrize("change", [
    {"authority": "diagnostic"}, {"authority": "authoring"},
    {"parameters": {}}, {"outputs": {}}, {"unknown": True},
    {"steps": None},
])
def test_mouse_control_declarations_reject_unsafe_authority_and_unknowns(project, change):
    definition = mouse_controls()
    definition["controls"]["choose"].update(change)
    with pytest.raises(ValueError):
        HarnessLibrary(project).save(definition)


def test_mouse_definition_budget_and_json_policy_precede_storage(project):
    library = HarnessLibrary(project)
    for value in ("x" * (48 * 1024), float("nan"), {"nested": object()}):
        definition = mouse_controls()
        definition["provenance"] = value
        with pytest.raises(ValueError):
            library.save(definition)
    definition = mouse_controls()
    definition["controls"]["other"] = {"steps": [{"op": "keyboard.press", "key": "bogus-key"}]}
    with pytest.raises(ValueError):
        library.save(definition)
    assert not library.list()["revisions"]


def test_mouse_row_hash_and_source_binding_are_verified(tmp_path):
    first_program, second_program = tmp_path / "A.COM", tmp_path / "B.COM"
    first_program.write_bytes(bytes.fromhex("b8 00 4c cd 21"))
    second_program.write_bytes(bytes.fromhex("90 b8 00 4c cd 21"))
    with ControlStore(tmp_path / "a.fdb", first_program) as first:
        library = HarnessLibrary(first)
        revision = library.save(mouse_controls())["revision"]
        record = tuple(first.db.execute("SELECT * FROM dotbox_control_sets WHERE id=?", (revision,)).fetchone())
        with ControlStore(tmp_path / "b.fdb", second_program) as second:
            # Establish the schema through a normal save, then inject the exact
            # valid first-project row without altering its hash or binding.
            HarnessLibrary(second).save(mouse_controls())
            with second.transaction(True):
                second.db.execute("INSERT INTO dotbox_control_sets VALUES (?,?,?,?,?,?,?)", record)
            with pytest.raises(ValueError, match="source binding"):
                HarnessLibrary(second).plan(revision, "choose")
        with first.transaction(True):
            first.db.execute("UPDATE dotbox_control_sets SET document=replace(document, '159', '158') WHERE id=?", (revision,))
        with pytest.raises(ValueError, match="hash mismatch"):
            library.info(revision)


def test_mouse_revision_rejects_a_different_selected_byte_version(project):
    library = HarnessLibrary(project)
    revision = library.save(mouse_controls())["revision"]
    with pytest.raises(ValueError, match="version"):
        HarnessLibrary(project, version=2).info(revision)
    assert HarnessLibrary(project, version=1).info(revision)["revision"] == revision


def test_dotbox_and_legacy_children_preserve_explicit_parent_chains(project):
    library = HarnessLibrary(project)
    first = library.save(mouse_controls())["revision"]
    sibling = library.save(mouse_controls(x=1), parent=first)["revision"]
    legacy = library.save(controls(), parent=first)["revision"]
    assert library.info(legacy)["parent"] == first
    assert library.info(legacy)["definition"]["format"] == "fdisbull-macro-set-1"
    assert library.plan(legacy, "move")["steps"][0]["op"] == "key"
    assert library.plan(first, "choose")["steps"][0]["params"]["x"] == 159
    assert library.plan(sibling, "choose")["steps"][0]["params"]["x"] == 1
    with pytest.raises(ValueError):
        library.save(mouse_controls(name="other"), parent=first)
    with pytest.raises(ValueError):
        library.save(mouse_controls(), parent="0" * 64)


@pytest.mark.parametrize('mutation', ['authority', 'operation', 'extra', 'definition'])
def test_rehashed_persisted_mouse_documents_still_enforce_the_play_schema(project, mutation):
    import hashlib
    import json
    library = HarnessLibrary(project)
    revision = library.save(mouse_controls())["revision"]
    row = dict(project.db.execute("SELECT * FROM dotbox_control_sets WHERE id=?", (revision,)).fetchone())
    document = json.loads(row['document'])
    if mutation == 'authority':
        document['definition']['controls']['choose']['authority'] = 'diagnostic'
    elif mutation == 'operation':
        document['definition']['controls']['choose']['steps'][0]['op'] = 'memory.write'
    elif mutation == 'extra':
        document['definition']['controls']['choose']['steps'][0]['dx'] = 10
    else:
        document['definition'] = []
    encoded = json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False)
    forged = hashlib.sha256(encoded.encode()).hexdigest()
    with project.transaction(True):
        project.db.execute('INSERT INTO dotbox_control_sets VALUES (?,?,?,?,?,?,?)', (
            forged, row['version'], row['parent'], row['created'], row['author'], forged, encoded))
    with pytest.raises(ValueError):
        library.info(forged)
    assert library.info(revision)['revision'] == revision


def test_legacy_format_cannot_smuggle_mouse_into_core_macros(project):
    from dotbox.input_macros import PRIMITIVES
    before = set(PRIMITIVES)
    definition = controls()
    definition['macros']['move']['steps'] = mouse_controls()['controls']['choose']['steps']
    with pytest.raises(ValueError):
        HarnessLibrary(project).save(definition)
    assert set(PRIMITIVES) == before and 'mouse.click' not in PRIMITIVES
    assert not HarnessLibrary(project).list()['revisions']
