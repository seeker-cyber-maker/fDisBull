"""Authored asset/recipe contracts; no guest, compiler or native library loads.

The fake compositor verifies orchestration only. Sarien's actual rasterization
remains covered by its separately supplied native-library batch.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "native" / "qemu-agi"))
from processor_scene_preview import (
    ASSET_SCHEMA, RECIPE_SCHEMA, RENDER_FIELDS, ScenePreviewError,
    prepare_preview_assets, preview_bound_scene,
)


CODE = bytes(64)
LOGIC = len(CODE).to_bytes(2, "little") + CODE
SCOPE = {"basis": "caller_declared_resource_scope", "logic": 7,
         "logic_resource_sha256": sha256(LOGIC).hexdigest(),
         "reason": "Authored fixture resources belong to this declared input set"}
PICTURE = bytes((0xf0, 1, 0xf6, 0, 0, 0xff))
# Both effective loops share one authored RLE cel. Loop 1 mirrors [2, 3].
VIEW = bytes((0, 0, 2, 0, 0, 9, 0, 9, 0, 1, 3, 0, 2, 1, 0x80, 0x21, 0x31, 0))


def source_mapping(pc):
    return {"kind": "original", "original_source_address": {
        "logic": 7, "resource_sha256": SCOPE["logic_resource_sha256"],
        "code_pc": pc, "payload_offset": pc + 2}}


def native(value, pc, operation="object.position", operand_index=1):
    provenance = {"basis": "native_requested", "pc": pc,
                  "source_mapping": source_mapping(pc), "operation": operation}
    if operand_index is not None:
        provenance["operand_index"] = operand_index
    return {"value": value, "provenance": provenance}


def caller(value):
    return {"value": value, "provenance": {"basis": "caller_declared_design_input",
            "reason": "Explicit authored scene design", "scope": "selected_endpoint"}}


def missing(fields):
    return [name for name in RENDER_FIELDS if name not in fields or fields[name]["value"] is None]


def recipe():
    source_fields = {"view": native(10, 0, "object.set_view"),
                     "x": native(10, 3), "y": native(20, 3, operand_index=2)}
    actor_fields = {**deepcopy(source_fields), "loop": caller(0), "cel": caller(0),
                    "priority": caller(8), "draw_requested": native(True, 9, "object.draw", None)}
    design = {name: caller(value) for name, value in
              dict(view=10, loop=1, cel=0, x=30, y=40, priority=4).items()}
    ego = {"draw_requested": native(True, 11, "object.draw", None)}
    return {
        "schema": RECIPE_SCHEMA,
        "source": {"sha256": sha256(CODE).hexdigest(), "size": len(CODE),
                   "logic_id": 0, "profile": "authored-contract-fixture"},
        "decoder": {"identity": "fdisbull.qemu.agi", "version": "2", "address_unit": "byte",
                    "encoding": "agi-2.917", "decode_policy": "structural-1"},
        "resource_mapping": {"logic": 7, "resource_sha256": sha256(LOGIC).hexdigest(),
                             "resource_size": len(LOGIC), "code_start": 2,
                             "code_size": len(CODE), "code_sha256": sha256(CODE).hexdigest()},
        "source_mappings": [{"kind": "original", "fragment_span": [0, len(CODE)],
                             "source": {"logic": 7, "resource_sha256": sha256(LOGIC).hexdigest(),
                                        "code_span": [0, len(CODE)], "payload_span": [2, len(LOGIC)]}}],
        "entry": {"pc": 0, "basis": "caller_declared_entry", "runtime_observed": False},
        "endpoint": {"requested": {"pc": 12, "phase": "before"}, "reached": True,
                     "stopped_pc": 12, "stop_reason": "selected_endpoint", "boundary": None},
        "status": "selected_endpoint_reached", "path": [], "timeline": [], "branches": [],
        "operand_bindings": [], "actor_inputs": [],
        "actors": [{"actor": 3, "fields": actor_fields, "missing_fields": [], "draw_request_pcs": [9]},
                   {"actor": 4, "fields": design, "missing_fields": [], "draw_request_pcs": []},
                   {"actor": 0, "fields": ego, "missing_fields": list(RENDER_FIELDS),
                    "draw_request_pcs": [11]}],
        "draw_requests": [
            {"pc": 9, "actor": 3, "source_mapping": source_mapping(9),
             "requested_pose": {"fields": source_fields, "missing_fields": missing(source_fields)}},
            {"pc": 11, "actor": 0, "source_mapping": source_mapping(11),
             "requested_pose": {"fields": {}, "missing_fields": list(RENDER_FIELDS)}},
        ],
        "scene_requests": [], "resource_requests": [], "required_inputs": [], "frontier": [],
        "budgets": {}, "usage": {}, "coverage": {},
        "qualification": "conditional_designer_recipe", "runtime_observed": False,
        "native_draw_completed": False, "presentation_established": False,
        "effective_actor_state_established": False,
    }


def resource(kind, number, payload):
    return {"kind": kind, "number": number, "volume": 1, "offset": 0,
            "length": len(payload), "sha256": sha256(payload).hexdigest(), "payload": payload}


def asset_inputs():
    return {"source_scope": deepcopy(SCOPE), "picture_resource": resource("picture", 20, PICTURE),
            "view_resources": {10: resource("view", 10, VIEW)},
            "cel_requests": [{"view": 10, "loop": 0, "cel": 0},
                             {"view": 10, "loop": 1, "cel": 0}]}


def layers():
    return [{"actor": 4, "selection_basis": "explicit_design_layer"},
            {"actor": 3, "selection_basis": "selected_path_draw_request"}]


class FakeCompositor:
    binary_sha256 = sha256(b"authored compositor contract double").hexdigest()

    def __init__(self):
        self.calls = []

    def blit(self, visual, priority, cel, **values):
        self.calls.append({"visual": visual, "priority": priority, "cel": cel, **values})
        # A test-only marker verifies that each returned plane reaches the next
        # call. This does not emulate rasterization, priority or AGI placement.
        result = bytes((len(self.calls),)) + visual[1:]
        return {"visual": result, "priority": priority, "written_pixels": 1, "hidden": False}


def add_picture_request(value, *, pc=1):
    operand = {"role": "picture", "kind": "variable", "width": 8, "access": "read", "index": 0}
    provenance = {"basis": "caller_declared_operand_input", "reason": "Authored v0 binding"}
    use = {"operand_index": 0, "operand": operand, "value": value, "provenance": provenance}
    scene = {"pc": pc, "operation": "scene.draw_picture", "operands": [deepcopy(use)],
             "source_mapping": source_mapping(pc)}
    request = {"pc": pc, "operation": "scene.draw_picture", "domain": "picture", **use,
               "source_mapping": source_mapping(pc), "at_barrier": False}
    return scene, request


def test_authored_asset_and_layer_batch():
    inputs, design = asset_inputs(), recipe()
    originals = deepcopy((inputs, design))
    assets = prepare_preview_assets(**inputs)
    assert assets["schema"] == ASSET_SCHEMA
    assert assets["picture"]["visual"] == b"\x01" + b"\x0f" * (160 * 168 - 1)
    assert assets["picture"]["priority"] == b"\x04" * (160 * 168)
    assert [(cel["pixels"], cel["mirrored"]) for cel in assets["cels"]] == [
        (b"\x02\x03", False), (b"\x03\x02", True)]
    original_assets = deepcopy(assets)
    kernel = FakeCompositor()
    result = preview_bound_scene(kernel, design, assets, layers=layers())
    assert [call["cel"] for call in kernel.calls] == [b"\x03\x02", b"\x02\x03"]
    assert [(call["x"], call["baseline"], call["actor_priority"]) for call in kernel.calls] == [
        (30, 40, 4), (10, 20, 8)]
    assert kernel.calls[1]["visual"][0] == 1 and result["visual"][0] == 2
    assert all(call["width"] == 2 and call["height"] == 1 and call["transparent"] == 0
               for call in kernel.calls)
    assert result["render_contract"]["draw_order"] == [4, 3]
    assert result["render_contract"]["bounds_policy"] == "reject_out_of_bounds"
    assert result["layers"][0]["draw_request"] is None
    assert result["layers"][1]["draw_request"]["pc"] == 9
    assert result["layers"][1]["fields"]["loop"]["provenance"]["basis"] == "caller_declared_design_input"
    assert result["omitted_actors"][0]["actor"] == 0
    assert result["omitted_actors"][0]["missing_fields"] == list(RENDER_FIELDS)
    assert result["background"]["selection_basis"] == "caller_selected_background"
    assert result["background"]["matches_source_picture_request"] is False
    assert result["qualification"] == "conditional_selected_layer_preview"
    assert all(result[name] is False for name in ("runtime_observed", "original_room_state_qualified",
        "native_draw_committed", "position_repair_completed", "presentation_established", "scene_complete"))
    assert result["output_assets"]["visual"]["sha256"] == sha256(result["visual"]).hexdigest()
    assert result["library_sha256"] == kernel.binary_sha256
    assert (inputs, design) == originals and assets == original_assets


def test_source_picture_matching_batch():
    assets = prepare_preview_assets(**asset_inputs())
    for values in ([20], [19, 20], [None, 20]):
        design = recipe()
        for pc, value in enumerate(values, start=1):
            scene, request = add_picture_request(value, pc=pc)
            design["scene_requests"].append(scene)
            design["resource_requests"].append(request)
        result = preview_bound_scene(FakeCompositor(), design, assets, layers=layers())
        assert result["background"]["matches_source_picture_request"] is True
        assert result["background"]["source_picture_request"]["value"] == 20
    for case in ("wrong_number", "unresolved", "missing", "duplicate", "barrier", "operand_drift"):
        design = recipe()
        scene, request = add_picture_request(None if case == "unresolved" else 19 if case == "wrong_number" else 20)
        design["scene_requests"] = [scene]
        design["resource_requests"] = [] if case == "missing" else [request]
        if case == "duplicate":
            design["resource_requests"].append(deepcopy(request))
        if case == "barrier":
            request["at_barrier"] = True
        if case == "operand_drift":
            scene["operands"][0]["value"] = 19
        kernel = FakeCompositor()
        with pytest.raises(ScenePreviewError):
            preview_bound_scene(kernel, design, assets, layers=layers())
        assert not kernel.calls, case


def test_asset_rejection_batch():
    for case in ("hash", "length", "kind", "number", "boolean_number", "extra_field", "scope",
                 "duplicate_cel", "absent_cel", "extra_view", "no_reason", "mutable_payload"):
        inputs = asset_inputs()
        row = inputs["picture_resource"]
        if case == "hash": row["sha256"] = "0" * 64
        elif case == "length": row["length"] += 1
        elif case == "kind": row["kind"] = "view"
        elif case == "number": inputs["view_resources"][10]["number"] = 11
        elif case == "boolean_number": row["number"] = True
        elif case == "extra_field": row["status"] = "ok"
        elif case == "scope": inputs["source_scope"]["basis"] = "observed_game"
        elif case == "duplicate_cel": inputs["cel_requests"].append(deepcopy(inputs["cel_requests"][0]))
        elif case == "absent_cel": inputs["cel_requests"][0]["cel"] = 1
        elif case == "extra_view": inputs["view_resources"][11] = resource("view", 11, VIEW)
        elif case == "no_reason": inputs["source_scope"]["reason"] = "  "
        elif case == "mutable_payload": row["payload"] = bytearray(row["payload"])
        with pytest.raises(ScenePreviewError):
            prepare_preview_assets(**inputs)
    for case in ("pixels", "plane", "geometry", "mirror", "boolean_alias", "bundle_field"):
        assets = prepare_preview_assets(**asset_inputs())
        if case == "pixels": assets["cels"][0]["pixels"] = b"\x03\x02"
        elif case == "plane": assets["picture"]["visual"] = bytes(160 * 168)
        elif case == "geometry": assets["cels"][0]["width"] = 1
        elif case == "mirror": assets["cels"][1]["mirrored"] = False
        elif case == "boolean_alias": assets["cels"][0]["loop"] = False
        elif case == "bundle_field": assets["implicit_defaults"] = True
        kernel = FakeCompositor()
        with pytest.raises(ScenePreviewError):
            preview_bound_scene(kernel, recipe(), assets, layers=layers())
        assert not kernel.calls, case


def test_recipe_and_layer_rejection_batch():
    assets = prepare_preview_assets(**asset_inputs())
    for case in ("schema", "unknown_field", "observed", "blocked", "scope", "native_source",
                 "missing_field", "missing_inventory", "bad_provenance", "unknown_actor_field",
                 "priority", "outside_right", "outside_bottom", "duplicate_layer", "absent_actor",
                 "draw_without_request", "draw_pose_changed", "native_fill_after_draw", "erased",
                 "draw_inventory", "inexact_mapping", "bool_field", "forged_draw_input"):
        design, selection = recipe(), layers()
        fields = design["actors"][0]["fields"]
        if case == "schema": design["schema"] += "-future"
        elif case == "unknown_field": design["assume_complete"] = True
        elif case == "observed": design["runtime_observed"] = True
        elif case == "blocked": design["status"] = "blocked"
        elif case == "scope": design["resource_mapping"]["logic"] = 8
        elif case == "native_source": design["source"]["sha256"] = "0" * 64
        elif case == "missing_field":
            del fields["loop"]
            design["actors"][0]["missing_fields"] = ["loop"]
        elif case == "missing_inventory": design["actors"][0]["missing_fields"] = ["loop"]
        elif case == "bad_provenance": fields["loop"]["provenance"]["basis"] = "observed"
        elif case == "unknown_actor_field": fields["flags"] = caller(1)
        elif case == "priority": fields["priority"]["value"] = 16
        elif case == "outside_right": design["actors"][1]["fields"]["x"]["value"] = 159
        elif case == "outside_bottom": design["actors"][1]["fields"]["y"]["value"] = 168
        elif case == "duplicate_layer": selection.append(deepcopy(selection[0]))
        elif case == "absent_actor": selection[0]["actor"] = 15
        elif case == "draw_without_request": selection[0]["selection_basis"] = "selected_path_draw_request"
        elif case == "draw_pose_changed": fields["x"] = native(11, 13)
        elif case == "native_fill_after_draw": fields["loop"] = native(0, 13, "object.set_loop")
        elif case == "erased": fields["draw_requested"] = native(False, 13, "object.erase", None)
        elif case == "draw_inventory": design["actors"][0]["draw_request_pcs"] = []
        elif case == "inexact_mapping": fields["x"]["provenance"]["source_mapping"]["original_source_address"]["payload_offset"] += 1
        elif case == "bool_field": fields["draw_requested"]["value"] = 1
        elif case == "forged_draw_input": design["draw_requests"][0]["requested_pose"]["fields"]["view"] = caller(10)
        kernel = FakeCompositor()
        with pytest.raises(ScenePreviewError):
            preview_bound_scene(kernel, design, assets, layers=selection)
        assert not kernel.calls, case


def test_design_layer_can_inspect_endpoint_after_draw_pose_change():
    design = recipe()
    design["actors"][0]["fields"]["x"] = native(11, 13)
    design["actors"][0]["fields"]["draw_requested"] = native(False, 15, "object.erase", None)
    result = preview_bound_scene(FakeCompositor(), design, prepare_preview_assets(**asset_inputs()),
                                layers=[{"actor": 3, "selection_basis": "explicit_design_layer"}])
    assert result["layers"][0]["fields"]["x"]["value"] == 11
    assert result["layers"][0]["draw_request"]["requested_pose"]["fields"]["x"]["value"] == 10
    assert result["layers"][0]["pose_scope"] == "endpoint_requested_design"


def test_compositor_contract_rejection_batch():
    assets = prepare_preview_assets(**asset_inputs())
    for case in ("identity", "plane", "count", "hidden", "extra"):
        class BadCompositor(FakeCompositor):
            def blit(self, *args, **kwargs):
                result = super().blit(*args, **kwargs)
                if case == "plane": result["visual"] = b"\x00"
                elif case == "count": result["written_pixels"] = 3
                elif case == "hidden": result["hidden"] = True
                elif case == "extra": result["native_draw_committed"] = True
                return result
        kernel = BadCompositor()
        if case == "identity": kernel.binary_sha256 = "not-an-identity"
        with pytest.raises(ScenePreviewError):
            preview_bound_scene(kernel, recipe(), assets, layers=layers())
