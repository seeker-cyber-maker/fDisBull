"""Independent door correspondence checks over authored encoded source.

The raw fixture is shared with producer tests, but expected semantics are
checked by the standalone player. Mutations refresh content hashes so a digest
failure cannot stand in for rejecting a false game-intent correspondence.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "player"))
from fdisbull_player.door_bindings import validate_binding
from fdisbull_player.scene_bindings import SourceReader, _digest
from fdisbull_player.word16 import Word16Error, validate_program
from fdisbull.zork_window import recover_window
from test_zork_window import make_window_fixture


def binding_fixture(shift=0):
    fixture = make_window_fixture(shift)
    recovered = recover_window(*fixture)
    return fixture, recovered


def check(fixture, recovered):
    _, program, scene, mapping, dispatch = fixture
    return validate_binding(SourceReader(program), recovered["uil"], recovered["udl"],
                            scene, mapping, dispatch["uil"], dispatch["udl"])


def refresh_hashes(fixture, recovered):
    image, program, _, _, _ = fixture
    recovered["udl"]["initial_image_sha256"] = hashlib.sha256(image).hexdigest()
    recovered["udl"]["source"] = copy.deepcopy(program["source"])
    recovered["udl"]["uil_sha256"] = _digest(recovered["uil"])
    for row in recovered["udl"]["witnesses"].values():
        raw = image[row["start"]:row["end"]]
        row["bytes"], row["sha256"] = raw.hex(), hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("shift", [0, 0x200])
def test_encoded_source_passes_independent_binding_check_after_relocation(shift):
    fixture, recovered = binding_fixture(shift)
    before = copy.deepcopy((fixture, recovered))
    assert check(fixture, recovered) is recovered["udl"]
    assert (fixture, recovered) == before


def _set(path, value):
    def mutate(uil, udl):
        node = {"uil": uil, "udl": udl}
        for part in path[:-1]:
            node = node[part]
        node[path[-1]] = value
    return mutate


@pytest.mark.parametrize("mutate", [
    pytest.param(_set(("uil", "resources", "window.opened"), "invented opening"), id="invented-narrative"),
    pytest.param(_set(("uil", "actions", "open", "resource"), "window.closed"), id="swapped-messages"),
    pytest.param(_set(("udl", "return_value"), 0), id="unhandled-result"),
    pytest.param(_set(("udl", "return_value"), True), id="boolean-return"),
    pytest.param(_set(("udl", "history", "value"), True), id="boolean-history-write"),
    pytest.param(_set(("udl", "history", "value"), 2), id="different-history-write"),
    pytest.param(_set(("udl", "history", "global"), 69), id="wrong-history-variable"),
    pytest.param(_set(("udl", "history", "consumer_action"), 99), id="wrong-history-consumer"),
    pytest.param(_set(("udl", "history", "consumer_text_dependencies"), []), id="missing-hint-text-dependency"),
    pytest.param(_set(("udl", "action_global"), 135), id="wrong-live-action"),
    pytest.param(_set(("udl", "actions", "open"), 35), id="close-number-as-open"),
    pytest.param(_set(("udl", "door", "mask"), 8), id="wrong-open-mask"),
    pytest.param(_set(("udl", "door", "attribute"), 12), id="wrong-open-attribute"),
    pytest.param(_set(("udl", "callback", "property"), 16), id="wrong-callback-property"),
    pytest.param(_set(("udl", "callback", "locals"), [0]), id="wrong-callback-frame"),
    pytest.param(_set(("udl", "helper", "locals"), [1, 0, 0]), id="changed-local-default"),
    pytest.param(_set(("udl", "repeat", "pointer_global"), 69), id="wrong-shared-pointer"),
    pytest.param(_set(("udl", "repeat", "count"), 2), id="missing-bag-member"),
    pytest.param(_set(("udl", "repeat", "initial_cursor"), 1), id="wrong-initial-cursor"),
    pytest.param(_set(("udl", "resources", "window.opened", "dependencies"), []), id="unguarded-text"),
    pytest.param(_set(("udl", "qualification", "all_game_intent_recovered"), True), id="false-completeness"),
], ids=lambda value: str(value))
def test_false_semantic_bindings_are_rejected_with_recomputed_hashes(mutate):
    fixture, recovered = binding_fixture()
    mutate(recovered["uil"], recovered["udl"])
    refresh_hashes(fixture, recovered)
    assert recovered["udl"]["uil_sha256"] == _digest(recovered["uil"])
    with pytest.raises(Word16Error):
        check(fixture, recovered)


@pytest.mark.parametrize("path", [
    ("action_global",), ("actions", "open"), ("return_value",),
    ("door", "object"), ("door", "record"), ("door", "address"), ("door", "mask"),
    ("history", "global"), ("history", "address"), ("history", "value"),
    ("callback", "packed"), ("callback", "header"), ("callback", "entry"),
    ("repeat", "pointer_global"), ("repeat", "pointer_address"),
    ("repeat", "table_address"), ("repeat", "cursor_address"),
    ("repeat", "items_address"), ("repeat", "count"), ("repeat", "initial_cursor"),
    ("repeat", "resources", "window.repeat.first"),
])
def test_integer_equality_does_not_admit_float_source_bindings(path):
    fixture, recovered = binding_fixture()
    node = recovered["udl"]
    for field in path[:-1]:
        node = node[field]
    node[path[-1]] = float(node[path[-1]])
    refresh_hashes(fixture, recovered)
    with pytest.raises(Word16Error):
        check(fixture, recovered)


@pytest.mark.parametrize("role", ["helper", "selection"])
@pytest.mark.parametrize("alias", [0.0, False])
def test_routine_default_locals_require_words_not_equality_aliases(role, alias):
    fixture, recovered = binding_fixture()
    recovered["udl"][role]["locals"][0] = alias
    refresh_hashes(fixture, recovered)
    with pytest.raises(Word16Error):
        check(fixture, recovered)


@pytest.mark.parametrize("primitive", [
    "presentation.dismiss_initial_hint", "door.open", "door.close",
    "narration.choose_shuffled_response", "narration.emit",
])
def test_named_primitive_must_correspond_to_its_actual_source_operations(primitive):
    fixture, recovered = binding_fixture()
    udl = recovered["udl"]
    udl["primitives"][primitive]["source_operations"] = [udl["callback"]["entry"]]
    refresh_hashes(fixture, recovered)
    with pytest.raises(Word16Error, match="primitive source correspondence"):
        check(fixture, recovered)


def test_primitive_source_addresses_are_typed_integers():
    fixture, recovered = binding_fixture()
    pcs = recovered["udl"]["primitives"]["door.open"]["source_operations"]
    pcs[0] = float(pcs[0])
    refresh_hashes(fixture, recovered)
    with pytest.raises(Word16Error):
        check(fixture, recovered)


@pytest.mark.parametrize("field,value", [
    ("order", "cursor advance; draw; one slot write"),
    ("repeat_scope", "without replacement forever"),
])
def test_response_definition_cannot_hide_write_order_or_overstate_cycle_scope(field, value):
    fixture, recovered = binding_fixture()
    recovered["udl"]["primitives"]["narration.choose_shuffled_response"][field] = value
    refresh_hashes(fixture, recovered)
    with pytest.raises(Word16Error, match="primitive source correspondence"):
        check(fixture, recovered)


@pytest.mark.parametrize("guard", [
    "window-layout", "window-abbreviations", "window-callback",
    "window-helper", "window-selection", "window-hint-consumer",
    "window-object-pointer", "window-callback-value", "text-d00",
])
def test_initial_bytes_do_not_replace_live_dependency_coverage(guard):
    fixture, recovered = binding_fixture()
    recovered["udl"]["runtime_guards"].remove(guard)
    refresh_hashes(fixture, recovered)
    with pytest.raises(Word16Error, match="omit"):
        check(fixture, recovered)


def test_extra_unused_stack_read_is_not_erased_by_symbolic_substitution():
    fixture, recovered = binding_fixture()
    pc = recovered["udl"]["helper"]["source_pcs"][5]
    fixture[1]["blocks"][str(pc)]["nodes"].insert(
        0, {"op": "read_var", "index": 0, "dest": "unused_extra_pop"})
    refresh_hashes(fixture, recovered)
    with pytest.raises(Word16Error, match="operand consumption"):
        check(fixture, recovered)


@pytest.mark.parametrize("role,index,kind", [
    ("callback", 0, "branch"),
    ("helper", 1, "branch"),
    ("helper", 6, "attribute"),
    ("helper", 8, "return"),
    ("selection", 13, "branch"),
    ("selection", 10, "drop-write"),
])
def test_retained_ir_must_establish_branch_effect_and_return_meaning(role, index, kind):
    fixture, recovered = binding_fixture()
    pc = recovered["udl"][role]["source_pcs"][index]
    nodes = fixture[1]["blocks"][str(pc)]["nodes"]
    if kind == "branch":
        branch = next(node for node in nodes if node["op"] == "if")
        branch["then"], branch["else"] = branch["else"], branch["then"]
    elif kind == "attribute":
        next(node for node in nodes if node["op"] == "library")["name"] = "attribute.clear"
    elif kind == "return":
        next(node for node in nodes if node["op"] == "return")["value"] = 0
    else:
        nodes[:] = [node for node in nodes if node["op"] != "write_mem"]
    refresh_hashes(fixture, recovered)
    with pytest.raises(Word16Error, match="source operation contradicts"):
        check(fixture, recovered)


@pytest.mark.parametrize("kind", ["return", "stack-read"])
def test_boolean_ir_literals_cannot_alias_integer_machine_operations(kind):
    fixture, recovered = binding_fixture()
    index = 8 if kind == "return" else 3
    pc = recovered["udl"]["helper"]["source_pcs"][index]
    nodes = fixture[1]["blocks"][str(pc)]["nodes"]
    if kind == "return":
        next(node for node in nodes if node["op"] == "return")["value"] = True
    else:
        next(node for node in nodes if node["op"] == "read_var")["index"] = False
    # Boolean expressions are legal IR, but these machine operations require
    # integers at execution. Python True==1 must not certify equivalence.
    validate_program(fixture[1])
    refresh_hashes(fixture, recovered)
    with pytest.raises(Word16Error):
        check(fixture, recovered)


def test_live_bag_state_cannot_be_promoted_to_a_byte_equality_guard():
    fixture, recovered = binding_fixture()
    udl = recovered["udl"]
    udl["runtime_guards"].append(udl["repeat"]["initial_witness"])
    refresh_hashes(fixture, recovered)
    with pytest.raises(Word16Error, match="mutable state aliases"):
        check(fixture, recovered)


def test_residual_callback_continuation_is_a_source_boundary_not_an_arbitrary_entry():
    fixture, recovered = binding_fixture()
    recovered["udl"]["callback"]["residual_continue"] += 1
    refresh_hashes(fixture, recovered)
    with pytest.raises(Word16Error, match="residual continuation"):
        check(fixture, recovered)
