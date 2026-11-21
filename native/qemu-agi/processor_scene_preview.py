"""Detached selected-layer previews for conditional CPU-derived AGI recipes.

No decoder, interpreter, guest, placement repair, or library discovery lives
here. Callers first extract exact v2 resources with ``extract_v2_resource`` (or
an equivalent already verified resource inventory), then add kind/number to
those rows. ``prepare_preview_assets`` uses the existing picture/VIEW readers.
``preview_bound_scene`` accepts a caller-supplied SarienScene-compatible kernel.
Neither a selected path nor these pixels establish an observed room or draw.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import re

from fdisbull.agi_picture import decode_picture
from fdisbull_core.agi_view import decode_view_cel


ASSET_SCHEMA = "fdisbull-agi-conditional-preview-assets-1"
RECIPE_SCHEMA = "fdisbull-agi-bound-scene-recipe-1"
SCHEMA = "fdisbull-agi-conditional-layer-preview-1"
WIDTH, HEIGHT = 160, 168
RENDER_FIELDS = ("view", "loop", "cel", "x", "y", "priority")
BOOL_FIELDS = ("cycling", "animated", "draw_requested")
_RECIPE_FIELDS = {
    "schema", "source", "decoder", "resource_mapping", "source_mappings",
    "entry", "endpoint", "status", "path", "timeline", "branches",
    "operand_bindings", "actor_inputs", "actors", "draw_requests",
    "scene_requests", "resource_requests", "required_inputs", "frontier",
    "budgets", "usage", "coverage", "qualification", "runtime_observed",
    "native_draw_completed", "presentation_established",
    "effective_actor_state_established",
}


class ScenePreviewError(ValueError):
    """A conditional recipe, exact asset, or compositor contract differs."""


def _fields(value, names, label):
    if type(value) is not dict or set(value) != set(names):
        raise ScenePreviewError(f"{label} fields differ")


def _uint(value, label, maximum=255):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ScenePreviewError(f"{label} is outside 0..{maximum}")
    return value


def _text(value, label):
    if type(value) is not str or not value.strip() or len(value) > 1024:
        raise ScenePreviewError(f"{label} requires bounded nonempty text")


def _digest(value, label):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ScenePreviewError(f"{label} requires a SHA-256 identity")
    return value


def _json(value, label):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError) as exc:
        raise ScenePreviewError(f"{label} must be finite JSON") from exc
    if len(raw) > 16 * 1024**2:
        raise ScenePreviewError(f"{label} exceeds the JSON budget")
    return raw


def _same(left, right):
    """Compare private byte-bearing bundles without bool/integer aliases."""
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(_same(value, right[key]) for key, value in left.items())
    if type(left) is list:
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return left == right


def _scope(value):
    _fields(value, {"basis", "logic", "logic_resource_sha256", "reason"}, "Source scope")
    if value["basis"] != "caller_declared_resource_scope":
        raise ScenePreviewError("Resource scope must remain a caller declaration")
    _uint(value["logic"], "Source LOGIC")
    _digest(value["logic_resource_sha256"], "Source LOGIC resource")
    _text(value["reason"], "Source scope reason")


def _resource(value, kind):
    names = {"kind", "number", "volume", "offset", "length", "sha256", "payload"}
    _fields(value, names, "Resource")
    if value["kind"] != kind:
        raise ScenePreviewError("Resource kind differs")
    _uint(value["number"], "Resource number")
    _uint(value["volume"], "Resource volume", 15)
    _uint(value["offset"], "Resource offset", 2**20 - 1)
    _uint(value["length"], "Resource length", 65535)
    _digest(value["sha256"], "Resource payload")
    payload = value["payload"]
    if type(payload) is not bytes or not payload or len(payload) != value["length"] \
            or sha256(payload).hexdigest() != value["sha256"]:
        raise ScenePreviewError("Resource payload length or identity differs")
    return {name: deepcopy(value[name]) for name in names - {"payload"}}


def prepare_preview_assets(*, source_scope, picture_resource, view_resources, cel_requests):
    """Decode exact caller-scoped inputs without changing any input object.

    ``source_scope`` has basis=caller_declared_resource_scope, logic,
    logic_resource_sha256, and reason. Each resource has exactly kind, number,
    volume, offset, length, sha256, payload. ``view_resources`` maps integer VIEW
    numbers to those records. ``cel_requests`` is a unique list of
    {view, loop, cel}; up to 16 VIEWs, 128 cels, and 4 MiB of cel pixels are kept.

    The returned private bundle retains source payloads for revalidation before
    composition. Do not publish this byte-retaining bundle as a source report.
    """
    _scope(source_scope)
    picture_identity = _resource(picture_resource, "picture")
    if type(view_resources) is not dict or not 1 <= len(view_resources) <= 16:
        raise ScenePreviewError("Preview assets require 1..16 explicit VIEW resources")
    identities = {}
    for number, resource in view_resources.items():
        _uint(number, "VIEW key")
        identities[number] = _resource(resource, "view")
        if identities[number]["number"] != number:
            raise ScenePreviewError("VIEW resource number differs from its key")
    if type(cel_requests) is not list or not 1 <= len(cel_requests) <= 128:
        raise ScenePreviewError("Preview assets require 1..128 cel requests")
    requests = []
    for request in cel_requests:
        _fields(request, {"view", "loop", "cel"}, "Cel request")
        requests.append(tuple(_uint(request[name], name) for name in ("view", "loop", "cel")))
    if len(set(requests)) != len(requests) \
            or {row[0] for row in requests} != set(view_resources):
        raise ScenePreviewError("Cel requests duplicate or differ from the VIEW inventory")
    try:
        picture = decode_picture(picture_resource["payload"])
        cels, pixels = [], 0
        for view, loop, cel in requests:
            decoded = decode_view_cel(view_resources[view]["payload"], loop=loop, cel=cel)
            pixels += len(decoded["pixels"])
            if pixels > 4 * 1024**2:
                raise ScenePreviewError("Preview cel pixels exceed the asset budget")
            cels.append({"view": view, "resource": identities[view], **decoded,
                         "pixels_sha256": sha256(decoded["pixels"]).hexdigest()})
    except ValueError as exc:
        raise ScenePreviewError(f"Asset decoding rejected the payload: {exc}") from exc
    return {
        "schema": ASSET_SCHEMA, "source_scope": deepcopy(source_scope),
        "inputs": {"picture_resource": deepcopy(picture_resource),
                   "view_resources": deepcopy(view_resources),
                   "cel_requests": deepcopy(cel_requests)},
        "picture": {"resource": picture_identity, **picture,
                    "visual_sha256": sha256(picture["visual"]).hexdigest(),
                    "priority_sha256": sha256(picture["priority"]).hexdigest()},
        "cels": cels,
    }


def _source_mapping(value, pc, scope):
    _fields(value, {"kind", "original_source_address"}, "Native source mapping")
    address = value["original_source_address"]
    _fields(address, {"logic", "resource_sha256", "code_pc", "payload_offset"},
            "Original source address")
    if pc >= scope.get("code_size", 65536) \
            or value["kind"] != "original" or type(address["logic"]) is not int \
            or address["logic"] != scope["logic"] \
            or address["resource_sha256"] != scope["logic_resource_sha256"] \
            or type(address["code_pc"]) is not int or address["code_pc"] != pc \
            or type(address["payload_offset"]) is not int or address["payload_offset"] != pc + 2:
        raise ScenePreviewError("Native source mapping differs from the declared resource scope")


def _actor_fields(fields, scope, *, caller_inputs=True):
    if type(fields) is not dict or not set(fields) <= set(RENDER_FIELDS + BOOL_FIELDS):
        raise ScenePreviewError("Actor state contains unsupported fields")
    for name, field in fields.items():
        _fields(field, {"value", "provenance"}, "Actor field")
        value, provenance = field["value"], field["provenance"]
        if type(provenance) is not dict:
            raise ScenePreviewError("Actor provenance must be explicit")
        basis = provenance.get("basis")
        if basis == "caller_declared_design_input":
            _fields(provenance, {"basis", "reason", "scope"}, "Caller actor provenance")
            _text(provenance["reason"], "Actor input reason")
            if not caller_inputs or provenance["scope"] != "selected_endpoint":
                raise ScenePreviewError("Caller actor input has the wrong pose scope")
        elif basis in ("native_requested", "unresolved_variable_request"):
            required = {"basis", "pc", "source_mapping", "operation"}
            optional = {"operand_index", "binding"} if basis == "native_requested" else set()
            if basis == "unresolved_variable_request":
                required |= {"operand_index", "variable"}
                _uint(provenance.get("variable"), "Unresolved variable")
                if value is not None:
                    raise ScenePreviewError("Unresolved actor variable has a value")
            if not required <= set(provenance) <= required | optional:
                raise ScenePreviewError("Native actor provenance fields differ")
            pc = _uint(provenance["pc"], "Actor source PC", 65535)
            _text(provenance["operation"], "Actor operation")
            _source_mapping(provenance["source_mapping"], pc, scope)
            if "operand_index" in provenance:
                _uint(provenance["operand_index"], "Actor operand index", 6)
            if "binding" in provenance:
                binding = provenance["binding"]
                _fields(binding, {"variable", "value", "reason"}, "Actor variable binding")
                _uint(binding["variable"], "Bound variable")
                _uint(binding["value"], "Bound value")
                _text(binding["reason"], "Binding reason")
                if type(value) is not int or binding["value"] != value:
                    raise ScenePreviewError("Actor field differs from its variable binding")
        else:
            raise ScenePreviewError("Unsupported actor provenance basis")
        if value is None:
            if basis != "unresolved_variable_request" or name not in RENDER_FIELDS:
                raise ScenePreviewError("Only unresolved variables may have missing field values")
        elif name in BOOL_FIELDS:
            if type(value) is not bool:
                raise ScenePreviewError("Actor boolean field is not a boolean")
        else:
            _uint(value, f"Actor {name}")
            if name == "priority" and basis == "caller_declared_design_input":
                _uint(value, "Caller render priority", 15)
    return [name for name in RENDER_FIELDS if name not in fields or fields[name]["value"] is None]


def _missing(value, expected):
    if type(value) is not list or any(type(name) is not str for name in value) \
            or len(value) != len(set(value)) or set(value) != set(expected):
        raise ScenePreviewError("Missing actor fields differ from the tagged state")


def _recipe(recipe, scope):
    _fields(recipe, _RECIPE_FIELDS, "Conditional recipe")
    raw = _json(recipe, "Conditional recipe")
    if recipe["schema"] != RECIPE_SCHEMA or recipe["qualification"] != "conditional_designer_recipe" \
            or any(recipe[name] is not False for name in ("runtime_observed", "native_draw_completed",
                "presentation_established", "effective_actor_state_established")):
        raise ScenePreviewError("Recipe qualification differs from conditional source requests")
    resource = recipe["resource_mapping"]
    _fields(resource, {"logic", "resource_sha256", "resource_size", "code_start",
                       "code_size", "code_sha256"}, "Recipe LOGIC resource mapping")
    _uint(resource["logic"], "Recipe LOGIC")
    _digest(resource["resource_sha256"], "Recipe LOGIC payload")
    _digest(resource["code_sha256"], "Recipe LOGIC code")
    for name in ("resource_size", "code_start", "code_size"):
        _uint(resource[name], name, 65535)
    if resource["logic"] != scope["logic"] \
            or resource["resource_sha256"] != scope["logic_resource_sha256"] \
            or resource["code_start"] != 2 or not 1 <= resource["code_size"] <= resource["resource_size"] - 2:
        raise ScenePreviewError("Recipe and assets have different original LOGIC scope")
    source = recipe["source"]
    if type(source) is not dict or source.get("sha256") != resource["code_sha256"] \
            or type(source.get("size")) is not int or source["size"] != resource["code_size"]:
        raise ScenePreviewError("Recipe code identity differs from its resource mapping")
    decoder = {"identity": "fdisbull.qemu.agi", "version": "2", "address_unit": "byte",
               "encoding": "agi-2.917", "decode_policy": "structural-1"}
    if not _same(recipe["decoder"], decoder):
        raise ScenePreviewError("Recipe decoder differs from the supported CPU fact profile")
    expected_mapping = [{"kind": "original", "fragment_span": [0, resource["code_size"]],
                         "source": {"logic": resource["logic"],
                                    "resource_sha256": resource["resource_sha256"],
                                    "code_span": [0, resource["code_size"]],
                                    "payload_span": [2, resource["code_size"] + 2]}}]
    if not _same(recipe["source_mappings"], expected_mapping):
        raise ScenePreviewError("Recipe source spans differ from the original LOGIC mapping")
    _fields(recipe["entry"], {"pc", "basis", "runtime_observed"}, "Recipe entry")
    _uint(recipe["entry"]["pc"], "Entry PC", resource["code_size"] - 1)
    if recipe["entry"]["basis"] != "caller_declared_entry" or recipe["entry"]["runtime_observed"] is not False:
        raise ScenePreviewError("Recipe entry must remain a caller declaration")
    _fields(recipe["endpoint"], {"requested", "reached", "stopped_pc", "stop_reason", "boundary"},
            "Recipe endpoint")
    if recipe["status"] != "selected_endpoint_reached" or recipe["endpoint"]["reached"] is not True:
        raise ScenePreviewError("Preview requires the selected recipe endpoint to be reached")
    endpoint = recipe["endpoint"]
    _fields(endpoint["requested"], {"pc", "phase"}, "Requested endpoint")
    _uint(endpoint["requested"]["pc"], "Requested endpoint PC", resource["code_size"] - 1)
    _uint(endpoint["stopped_pc"], "Stopped PC", resource["code_size"] - 1)
    if endpoint["requested"]["phase"] not in ("before", "after") \
            or endpoint["stopped_pc"] != endpoint["requested"]["pc"] \
            or endpoint["stop_reason"] != "selected_endpoint":
        raise ScenePreviewError("Reached endpoint differs from its request")
    scope = {**scope, "code_size": resource["code_size"]}
    actors = {}
    if type(recipe["actors"]) is not list or len(recipe["actors"]) > 256:
        raise ScenePreviewError("Recipe actor inventory exceeds the scene profile")
    for actor in recipe["actors"]:
        _fields(actor, {"actor", "fields", "missing_fields", "draw_request_pcs"}, "Recipe actor")
        number = _uint(actor["actor"], "Actor number")
        if number in actors:
            raise ScenePreviewError("Duplicate recipe actor")
        _missing(actor["missing_fields"], _actor_fields(actor["fields"], scope))
        if type(actor["draw_request_pcs"]) is not list:
            raise ScenePreviewError("Actor draw request PCs must be a list")
        for pc in actor["draw_request_pcs"]:
            _uint(pc, "Actor draw PC", 65535)
        actors[number] = actor
    if type(recipe["draw_requests"]) is not list or len(recipe["draw_requests"]) > 4096:
        raise ScenePreviewError("Recipe draw requests exceed their budget")
    draws = {number: [] for number in actors}
    for request in recipe["draw_requests"]:
        _fields(request, {"pc", "actor", "source_mapping", "requested_pose"}, "Draw request")
        number = _uint(request["actor"], "Draw actor")
        pc = _uint(request["pc"], "Draw source PC", 65535)
        if number not in actors:
            raise ScenePreviewError("Draw request actor is absent from the inventory")
        _source_mapping(request["source_mapping"], pc, scope)
        pose = request["requested_pose"]
        _fields(pose, {"fields", "missing_fields"}, "Draw requested pose")
        _missing(pose["missing_fields"], _actor_fields(pose["fields"], scope, caller_inputs=False))
        draws[number].append(request)
    for number, actor in actors.items():
        if actor["draw_request_pcs"] != [row["pc"] for row in draws[number]]:
            raise ScenePreviewError("Actor draw inventory differs from its source requests")
    return raw, actors, draws


def _background(recipe, picture, scope):
    scope = {**scope, "code_size": recipe["resource_mapping"]["code_size"]}
    scene_requests, resources = recipe["scene_requests"], recipe["resource_requests"]
    if type(scene_requests) is not list or len(scene_requests) > 4096 \
            or type(resources) is not list or len(resources) > 32768:
        raise ScenePreviewError("Scene/resource request inventory exceeds its budget")
    selected = None
    for request in scene_requests:
        _fields(request, {"pc", "operation", "operands", "source_mapping"}, "Scene request")
        if request["operation"] not in ("scene.draw_picture", "scene.show_picture"):
            raise ScenePreviewError("Unsupported scene operation in preview recipe")
        pc = _uint(request["pc"], "Scene source PC", 65535)
        _source_mapping(request["source_mapping"], pc, scope)
        if request["operation"] != "scene.draw_picture":
            continue
        matches = [row for row in resources if type(row) is dict
                   and row.get("pc") == pc and row.get("operation") == "scene.draw_picture"
                   and row.get("domain") == "picture" and row.get("at_barrier") is False]
        if len(matches) != 1:
            raise ScenePreviewError("Picture draw requires one resolved source resource request")
        selected = matches[0]
        _fields(selected, {"pc", "operation", "domain", "operand_index", "operand", "value",
                           "provenance", "source_mapping", "at_barrier"}, "Picture resource request")
        _uint(selected["pc"], "Picture request PC", 65535)
        _uint(selected["operand_index"], "Picture operand index", 6)
        _source_mapping(selected["source_mapping"], pc, scope)
        operands = request["operands"]
        if type(operands) is not list or len(operands) != 1:
            raise ScenePreviewError("Picture draw operand inventory differs")
        expected = {name: selected[name] for name in ("operand_index", "operand", "value", "provenance")}
        if _json(operands[0], "Picture operand") != _json(expected, "Picture resource operand"):
            raise ScenePreviewError("Scene picture operand differs from its resource request")
    if selected is not None:
        _uint(selected["value"], "Source picture value")
        if picture["resource"]["number"] != selected["value"]:
            raise ScenePreviewError("Caller background differs from the selected source picture draw")
    return {"selection_basis": "caller_selected_background",
            "source_picture_request": deepcopy(selected),
            "matches_source_picture_request": selected is not None,
            "effective_picture_state_established": False,
            "resource": deepcopy(picture["resource"])}


def _plane(value, label):
    if type(value) is not bytes or len(value) != WIDTH * HEIGHT or any(color > 15 for color in value):
        raise ScenePreviewError(f"{label} is not a complete EGA indexed plane")


def preview_bound_scene(kernel, recipe, assets, *, layers):
    """Compose explicit layers at the recipe endpoint, without placement repair.

    ``layers`` is an ordered list of {actor, selection_basis}. Basis is either
    explicit_design_layer or selected_path_draw_request. Draw-based selection
    rejects endpoint pose changes after the last draw; only caller-declared
    fills of missing draw fields are accepted. Every selected render field
    must be resolved. Other actors remain explicitly omitted, including ego.
    The entire cel must fit the canvas; this adapter never clips or repairs it.
    """
    _fields(assets, {"schema", "source_scope", "inputs", "picture", "cels"}, "Preview assets")
    if assets["schema"] != ASSET_SCHEMA:
        raise ScenePreviewError("Unsupported preview asset schema")
    _fields(assets["inputs"], {"picture_resource", "view_resources", "cel_requests"}, "Asset inputs")
    # Verify both original payloads and their derived bytes; caller edits to
    # hashes, dimensions, orientation metadata or indexed assets are not trusted.
    verified = prepare_preview_assets(source_scope=assets["source_scope"], **assets["inputs"])
    if not _same(assets, verified):
        raise ScenePreviewError("Prepared asset metadata or decoded bytes differ from the resources")
    scope, picture = verified["source_scope"], verified["picture"]
    recipe_raw, actors, draws = _recipe(recipe, scope)
    background = _background(recipe, picture, scope)
    library_sha256 = _digest(getattr(kernel, "binary_sha256", None), "Scene library")
    if not callable(getattr(kernel, "blit", None)):
        raise ScenePreviewError("Preview requires an explicitly supplied compositor")
    if type(layers) is not list or not 1 <= len(layers) <= 16:
        raise ScenePreviewError("Preview requires 1..16 explicitly ordered layers")
    planned, selected = [], set()
    for layer in layers:
        _fields(layer, {"actor", "selection_basis"}, "Preview layer")
        number = _uint(layer["actor"], "Layer actor")
        basis = layer["selection_basis"]
        if number in selected or number not in actors \
                or basis not in ("explicit_design_layer", "selected_path_draw_request"):
            raise ScenePreviewError("Layer selection is duplicate, absent or unsupported")
        selected.add(number)
        actor = actors[number]
        if actor["missing_fields"]:
            raise ScenePreviewError(f"Actor {number} lacks render fields: {', '.join(actor['missing_fields'])}")
        values = {name: actor["fields"][name]["value"] for name in RENDER_FIELDS}
        _uint(values["priority"], "Render priority", 15)
        draw = draws[number][-1] if draws[number] else None
        if basis == "selected_path_draw_request":
            if draw is None:
                raise ScenePreviewError("Draw-based layer has no selected-path draw request")
            if actor["fields"].get("draw_requested", {}).get("value") is not True:
                raise ScenePreviewError("Endpoint actor no longer has a requested draw")
            requested = draw["requested_pose"]["fields"]
            for name in RENDER_FIELDS:
                at_draw = requested.get(name)
                if at_draw is not None and at_draw["value"] is not None:
                    if at_draw["value"] != values[name]:
                        raise ScenePreviewError("Endpoint render pose differs from its source draw request")
                elif actor["fields"][name]["provenance"]["basis"] != "caller_declared_design_input":
                    raise ScenePreviewError("Missing draw fields require explicit caller design inputs")
        matches = [cel for cel in verified["cels"] if (cel["view"], cel["loop"], cel["cel"]) ==
                   (values["view"], values["loop"], values["cel"])]
        if len(matches) != 1:
            raise ScenePreviewError("Selected actor lacks one exact effective cel")
        cel = matches[0]
        if not 0 <= values["x"] <= WIDTH - cel["width"] \
                or not cel["height"] - 1 <= values["y"] < HEIGHT:
            raise ScenePreviewError("Selected cel does not fit the canvas; clipping/repair is unsupported")
        planned.append((layer, actor, values, cel, draw))
    visual, priority, steps = picture["visual"], picture["priority"], []
    for layer, actor, values, cel, draw in planned:
        result = kernel.blit(visual, priority, cel["pixels"], x=values["x"], baseline=values["y"],
            width=cel["width"], height=cel["height"], transparent=cel["transparent_color"],
            actor_priority=values["priority"])
        _fields(result, {"visual", "priority", "written_pixels", "hidden"}, "Compositor result")
        _plane(result["visual"], "Compositor visual")
        _plane(result["priority"], "Compositor priority")
        _uint(result["written_pixels"], "Written pixels", cel["width"] * cel["height"])
        if type(result["hidden"]) is not bool or result["hidden"] != (result["written_pixels"] == 0):
            raise ScenePreviewError("Compositor hidden/count fields contradict each other")
        visual, priority = result["visual"], result["priority"]
        steps.append({**deepcopy(layer), "pose_scope": "endpoint_requested_design",
                      "fields": deepcopy(actor["fields"]), "draw_request": deepcopy(draw),
                      "cel": {key: deepcopy(value) for key, value in cel.items() if key != "pixels"},
                      "written_pixels": result["written_pixels"], "hidden": result["hidden"]})
    return {
        "schema": SCHEMA, "status": "preview_complete",
        "qualification": "conditional_selected_layer_preview",
        "recipe_sha256": sha256(recipe_raw).hexdigest(), "library_sha256": library_sha256,
        "source_scope": deepcopy(scope), "background": background,
        "input_assets": {"picture": {key: deepcopy(value) for key, value in picture.items()
                                     if key not in ("visual", "priority")},
                         "cels": [{key: deepcopy(value) for key, value in cel.items() if key != "pixels"}
                                  for cel in verified["cels"]]},
        "layers": steps,
        "omitted_actors": [{**deepcopy(actor), "reason": "unresolved_render_fields"
                            if actor["missing_fields"] else "not_selected_for_preview"}
                           for number, actor in actors.items() if number not in selected],
        "visual": visual, "priority": priority,
        "output_assets": {"visual": {"bytes": len(visual), "sha256": sha256(visual).hexdigest()},
                          "priority": {"bytes": len(priority), "sha256": sha256(priority).hexdigest()}},
        "render_contract": {"width": WIDTH, "height": HEIGHT, "anchor": "lower_left_baseline",
                            "top_row": "y-height+1", "bounds_policy": "reject_out_of_bounds",
                            "priority_compositing": True, "position_repair": False,
                            "draw_order": [row["actor"] for row in layers]},
        "runtime_observed": False, "original_room_state_qualified": False,
        "native_draw_committed": False, "position_repair_completed": False,
        "presentation_established": False, "scene_complete": False,
    }
