"""Address-free scene selection and movement intents.

This reference evaluator reads named scenes, live Boolean conditions and named
open/closed doors. A producer resolves source table entries and packed addresses
into this document before execution; none of those mechanisms exists here.
The separate UDL adapter owns source correspondence and residual implementation.

Selecting an exit requests travel but does not claim that arrival, narration,
scoring or a turn completed. ``evaluate_relocation`` is a separate primitive:
it moves a named actor and changes the current scene at a qualified boundary.
The surrounding game can still reject movement before that boundary or perform
lighting, event, scoring and description work afterwards.

Missing facts use None (or a missing map entry), never guessed false. Unknown
selection or relocation returns no effects and an unchanged copy of its input.
A resolved residual handler remains an explicit low-level request; the evaluator
never executes source code or arbitrary host callbacks.
"""

from __future__ import annotations

import copy


FORMAT = "fdisbull-scene-intent-uil-1"
DIRECTIONS = frozenset({
    "north", "south", "east", "west", "northeast", "northwest", "southeast",
    "southwest", "up", "down", "in", "out", "land",
})
MAX_SCENES = 1024
MAX_DECLARATIONS = 2048
MAX_RESOURCES = 4096
MAX_TEXT_BYTES = 2 * 1024 * 1024
_REQUIRED_RESOURCES = {
    "default_blocked", "default_closed_prefix", "default_closed_suffix", "newline",
}


class SceneIntentError(ValueError):
    """The semantic document, invocation or state is malformed."""


def _keys(value, required, optional=(), label="record"):
    if (not isinstance(value, dict) or set(required) - set(value)
            or set(value) - set(required) - set(optional)):
        raise SceneIntentError(f"{label} has missing or unknown fields")


def _identifier(value, label="identity"):
    if (not isinstance(value, str) or not value or len(value) > 160
            or any(ord(character) < 32 for character in value)):
        raise SceneIntentError(f"Invalid {label}")
    return value


def _text(value, label="text", *, nonempty=False):
    if not isinstance(value, str) or nonempty and not value:
        raise SceneIntentError(f"Invalid {label}")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as exc:
        raise SceneIntentError(f"Invalid Unicode in {label}") from exc
    if size > MAX_TEXT_BYTES:
        raise SceneIntentError(f"Excessive {label}")
    return size


def _map(value, limit, label, *, minimum=0):
    if not isinstance(value, dict) or not minimum <= len(value) <= limit:
        raise SceneIntentError(f"Invalid or excessive {label}")
    for name in value:
        _identifier(name, label + " identity")


def _resource(document, name):
    _identifier(name, "resource identity")
    if name not in document["resources"]:
        raise SceneIntentError("Unknown narration resource")


def _handler(document, name, role):
    _identifier(name, "residual handler identity")
    entry = document["handlers"].get(name)
    if entry is None or entry["role"] != role:
        raise SceneIntentError("Unknown residual handler or incompatible role")


def _scene(document, name):
    _identifier(name, "scene identity")
    if name not in document["scenes"]:
        raise SceneIntentError("Unknown scene destination")


def validate_uil(document):
    """Validate all definitions, including unused scenes and exit alternatives.

    Equal display names are permitted; semantic scene and exit identities must
    stay distinct. Self-loops and cyclic routes are legal and do not trigger
    traversal. Initial traits document starting conditions only. They never
    substitute for current game facts during evaluation.
    """
    _keys(document, ("format", "id", "entry_scene", "resources", "scenes",
                     "facts", "doors", "handlers", "missing_exit"),
          label="scene-intent UIL")
    if document["format"] != FORMAT:
        raise SceneIntentError("Unsupported scene-intent UIL format")
    _identifier(document["id"], "UIL identity")
    _map(document["resources"], MAX_RESOURCES, "resources")
    if not _REQUIRED_RESOURCES <= set(document["resources"]):
        raise SceneIntentError("Required narration resources are missing")
    text_bytes = sum(_text(value, "narration resource")
                     for value in document["resources"].values())
    if text_bytes > MAX_TEXT_BYTES:
        raise SceneIntentError("Narration resource byte budget exceeded")
    _map(document["facts"], MAX_DECLARATIONS, "facts")
    for fact in document["facts"].values():
        _keys(fact, ("type", "initial"), label="Boolean fact")
        if fact["type"] != "boolean" or type(fact["initial"]) is not bool:
            raise SceneIntentError("Fact declaration requires a Boolean initial value")
    _map(document["doors"], MAX_DECLARATIONS, "doors")
    for door in document["doors"].values():
        _keys(door, ("name", "initial_open"), label="door")
        text_bytes += _text(door["name"], "door name", nonempty=True)
        if type(door["initial_open"]) is not bool:
            raise SceneIntentError("Door declaration requires a Boolean initial state")
    _map(document["handlers"], MAX_DECLARATIONS, "residual handlers", minimum=1)
    for handler in document["handlers"].values():
        _keys(handler, ("representation", "role"), label="residual handler")
        if (handler["representation"] != "low_level_ir"
                or handler["role"] not in ("room_event", "exit")):
            raise SceneIntentError("Handler must explicitly retain its low-level body")
    _handler(document, document["missing_exit"], "exit")
    _map(document["scenes"], MAX_SCENES, "scenes", minimum=1)
    _scene(document, document["entry_scene"])
    exit_ids = set()
    for scene in document["scenes"].values():
        _keys(scene, ("name", "exits"), ("description", "on_event", "initial_traits"), "scene")
        text_bytes += _text(scene["name"], "scene name", nonempty=True)
        if text_bytes > MAX_TEXT_BYTES:
            raise SceneIntentError("Scene text byte budget exceeded")
        if "initial_traits" in scene:
            traits = scene["initial_traits"]
            _keys(traits, ("land", "naturally_lit", "ruined"), label="initial traits")
            if any(type(value) is not bool for value in traits.values()):
                raise SceneIntentError("Initial scene traits must be Boolean")
        if "description" in scene:
            description = scene["description"]
            if not isinstance(description, dict):
                raise SceneIntentError("Invalid scene description")
            if description.get("kind") == "static":
                _keys(description, ("kind", "resource"), label="static scene description")
                _resource(document, description["resource"])
            elif description.get("kind") == "residual":
                _keys(description, ("kind", "handler"), label="residual scene description")
                _handler(document, description["handler"], "room_event")
            else:
                raise SceneIntentError("Unknown scene description kind")
        if "on_event" in scene:
            event = scene["on_event"]
            _keys(event, ("kind", "handler"), label="scene event")
            if event["kind"] != "residual":
                raise SceneIntentError("Scene event body must be explicitly residual")
            _handler(document, event["handler"], "room_event")
        exits = scene["exits"]
        if not isinstance(exits, dict) or set(exits) - DIRECTIONS:
            raise SceneIntentError("Scene exits require named directions")
        for exit_rule in exits.values():
            if not isinstance(exit_rule, dict):
                raise SceneIntentError("Invalid exit rule")
            kind = exit_rule.get("kind")
            if not isinstance(kind, str):
                raise SceneIntentError("Unknown exit rule kind")
            required = {
                "direct": ("id", "kind", "destination"),
                "blocked": ("id", "kind", "failure_resource"),
                "conditional": ("id", "kind", "destination", "fact"),
                "door": ("id", "kind", "destination", "door"),
                "routine": ("id", "kind", "residual"),
            }.get(kind)
            if required is None:
                raise SceneIntentError("Unknown exit rule kind")
            optional = ("failure_resource",) if kind in ("conditional", "door") else ()
            _keys(exit_rule, required, optional, "exit rule")
            identity = _identifier(exit_rule["id"], "exit identity")
            if identity in exit_ids:
                raise SceneIntentError("Duplicate exit identity")
            exit_ids.add(identity)
            if "destination" in exit_rule:
                _scene(document, exit_rule["destination"])
            if "failure_resource" in exit_rule:
                _resource(document, exit_rule["failure_resource"])
            if kind == "conditional":
                _identifier(exit_rule["fact"], "condition identity")
                if exit_rule["fact"] not in document["facts"]:
                    raise SceneIntentError("Exit names an undeclared condition")
            if kind == "door":
                _identifier(exit_rule["door"], "door identity")
                if exit_rule["door"] not in document["doors"]:
                    raise SceneIntentError("Exit names an undeclared door")
            if kind == "routine":
                _handler(document, exit_rule["residual"], "exit")
    return document


def initial_state(document):
    """Build the declared initial selection state, without initializing a VM."""
    validate_uil(document)
    return {
        "current_scene": document["entry_scene"],
        "facts": {name: item["initial"] for name, item in document["facts"].items()},
        "doors": {name: item["initial_open"] for name, item in document["doors"].items()},
    }


def _selection_state(document, state):
    _keys(state, ("current_scene", "facts", "doors"), label="scene selection state")
    if state["current_scene"] is not None:
        _identifier(state["current_scene"], "current scene")
    for field in ("facts", "doors"):
        values = state[field]
        if not isinstance(values, dict) or set(values) - set(document[field]):
            raise SceneIntentError("State names an undeclared " + field + " entry")
        if any(value is not None and type(value) is not bool for value in values.values()):
            raise SceneIntentError("Live conditions and doors must be Boolean or unknown")


def evaluate_exit(document, state, direction):
    """Select an explicit destination or ordered refusal/residual plan.

    No source table, source stack or instruction is consulted. Returned travel
    requests do not mutate the current scene: ``scene.move_actor`` has a separate
    qualified boundary. Narration and discourse entries are an ordered effect
    plan for the consumer, and ``next_state`` remains the selection input.
    """
    validate_uil(document)
    _selection_state(document, state)
    if not isinstance(direction, str) or direction not in DIRECTIONS:
        raise SceneIntentError("Expected a named direction, not a command string")
    origin = state["current_scene"]
    result = {"status": "unknown", "outcome": "unrecovered", "exit_id": None,
              "origin": origin, "direction": direction, "destination": None,
              "handler": None, "effects": [], "executed_intents": [],
              "next_state": copy.deepcopy(state), "reason": None}
    if origin is None or origin not in document["scenes"]:
        result["reason"] = "current_scene_unknown"
        return result
    rule = document["scenes"][origin]["exits"].get(direction)

    def residual(handler, outcome):
        result.update(status="residual", outcome=outcome, handler=handler,
                      effects=[{"type": "residual_ir", "binding": handler}],
                      executed_intents=["scene.select_exit"])
        return result

    if rule is None:
        # The original missing-exit path can have darkness/RNG consequences.
        # It is deliberately not rewritten as the ordinary blocked message.
        return residual(document["missing_exit"], "missing_exit")
    result["exit_id"] = rule["id"]
    kind = rule["kind"]
    if kind == "routine":
        return residual(rule["residual"], "routine")
    decision = None
    if kind == "conditional":
        decision = state["facts"].get(rule["fact"])
        if decision is None:
            result["reason"] = "condition_unknown:" + rule["fact"]
            return result
    elif kind == "door":
        decision = state["doors"].get(rule["door"])
        if decision is None:
            result["reason"] = "door_state_unknown:" + rule["door"]
            return result
    if kind == "direct" or decision is True:
        outcome = {"direct": "direct", "conditional": "condition_true", "door": "door_open"}[kind]
        destination = rule["destination"]
        result.update(status="travel", outcome=outcome, destination=destination,
                      effects=[{"type": "travel_requested", "from": origin,
                                "destination": destination}],
                      executed_intents=["scene.select_exit"])
        return result
    outcome = {"blocked": "blocked", "conditional": "condition_false", "door": "door_closed"}[kind]
    effects = []
    intents = ["scene.select_exit", "narration.emit"]

    def emit(resource):
        effects.append({"type": "narrate", "text": document["resources"][resource],
                        "resource": resource})

    failure = rule.get("failure_resource")
    if failure is not None or kind != "door":
        emit(failure if failure is not None else "default_blocked")
        emit("newline")
    else:
        # The default closed-door message mentions the door, establishing the
        # subsequent pronoun referent. A custom message does not do that write.
        door = rule["door"]
        emit("default_closed_prefix")
        effects.append({"type": "narrate", "text": document["doors"][door]["name"],
                        "entity": door})
        emit("default_closed_suffix")
        emit("newline")
        effects.append({"type": "referent_changed", "entity": door, "scene": origin})
        intents.extend(["narration.name", "discourse.remember_mentioned_object"])
    result.update(status="refused", outcome=outcome, effects=effects, executed_intents=intents)
    return result


def evaluate_relocation(document, state, destination):
    """Move a named actor and the current scene at a qualified game boundary.

    This primitive does not infer passage eligibility, narration, scoring,
    lighting, callbacks, time or randomness. Those obligations belong before or
    after the primitive in a containing interaction. Source-specific object-tree
    layout and the calling convention belong to its UDL realization.
    """
    validate_uil(document)
    _keys(state, ("current_scene", "actor"), label="relocation state")
    _keys(state["actor"], ("id", "scene"), label="actor state")
    _identifier(state["actor"]["id"], "actor identity")
    for value in (state["current_scene"], state["actor"]["scene"], destination):
        if value is not None:
            _identifier(value, "relocation scene")
    result = {"status": "unknown", "next_state": copy.deepcopy(state),
              "effects": [], "executed_intents": [], "reason": None}
    origin = state["current_scene"]
    if origin is None or origin not in document["scenes"]:
        result["reason"] = "current_scene_unknown"
    elif destination is None or destination not in document["scenes"]:
        result["reason"] = "destination_unknown"
    elif state["actor"]["scene"] is None:
        result["reason"] = "actor_scene_unknown"
    elif state["actor"]["scene"] != origin:
        result["reason"] = "actor_scene_mismatch"
    else:
        result["next_state"]["current_scene"] = destination
        result["next_state"]["actor"]["scene"] = destination
        result.update(status="moved",
                      effects=[{"type": "actor_relocated", "actor": state["actor"]["id"],
                                "origin": origin, "destination": destination}],
                      executed_intents=["scene.move_actor"])
    return result
