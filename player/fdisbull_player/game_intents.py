"""Pure, address-free evaluator for a small game-intent UIL profile.

The retained word16 program is executable low-level IR. This module is a
different layer: its entities, conditions, outcomes and effects describe game
behavior without object numbers, attribute bits, program counters or source
globals. A UDL adapter supplies and applies the source-specific correspondence.

Definitions are executable data. Their admission conditions, ordered outcome
rules and steps are interpreted here; resource strings and game entity IDs are
supplied by the producer. The primitive vocabulary is closed and versioned.
Residual IR effects are explicit requests to a separately qualified adapter;
this evaluator never executes their original code or an arbitrary host callable.

Unknown semantic values use None. They never count as false evidence. Unsupported
conditions return ``outcome='unrecovered'`` with no effects and an unchanged copy
of the input state, allowing a caller to select an explicit residual IR path.
Malformed definitions and states raise GameIntentError instead.
"""

from __future__ import annotations

import copy


FORMAT = "fdisbull-game-intent-uil-1"
MAX_ENTITIES = 1024
MAX_STEPS = 256
MAX_RESOURCES = 128
MAX_TEXT = 256 * 1024

_ENTITY_BOOL_FIELDS = {
    "is_container", "supports_opening", "is_open", "opaque", "reachable",
    "plain_listing",
}
_ENTITY_FIELDS = {"name", "contents", *_ENTITY_BOOL_FIELDS}
_FIELD_TYPES = {
    f"{selector}.{field}": bool
    for selector in ("target", "first_content")
    for field in _ENTITY_BOOL_FIELDS
}
_FIELD_TYPES.update({
    "target.id": str,
    "target.contents_count": int,
    "first_content.id": str,
    "current_scene": str,
    "discourse.referent": str,
    "discourse.scene": str,
    "turn.count": int,
})


class GameIntentError(ValueError):
    """A malformed or unsupported game-intent document/state."""


class _Unrecovered(Exception):
    """A well-formed invocation lies outside the known semantic domain."""


def _keys(value, required, optional=(), label="record"):
    if not isinstance(value, dict):
        raise GameIntentError(f"{label} must be an object")
    if set(value) - set(required) - set(optional) or set(required) - set(value):
        raise GameIntentError(f"{label} has missing or unknown fields")


def _identifier(value, label="identifier"):
    if not isinstance(value, str) or not value or len(value) > 160:
        raise GameIntentError(f"Invalid {label}")
    if any(ord(character) < 32 for character in value):
        raise GameIntentError(f"Invalid {label}")
    return value


def _text(value, label="text"):
    if not isinstance(value, str) or len(value.encode("utf-8")) > MAX_TEXT:
        raise GameIntentError(f"Invalid or excessive {label}")
    return value


def _conditions(conditions):
    if not isinstance(conditions, list) or len(conditions) > MAX_STEPS:
        raise GameIntentError("Conditions must be a bounded list")
    for condition in conditions:
        if (not isinstance(condition, dict)
                or not isinstance(condition.get("field"), str)
                or condition["field"] not in _FIELD_TYPES):
            raise GameIntentError("Unknown semantic condition field")
        field_type = _FIELD_TYPES[condition["field"]]
        if "eq" in condition:
            _keys(condition, ("field", "eq"), label="equality condition")
            if type(condition["eq"]) is not field_type:
                raise GameIntentError("Condition value has the wrong semantic type")
        elif "range" in condition:
            _keys(condition, ("field", "range"), label="range condition")
            bounds = condition["range"]
            if (field_type is not int or not isinstance(bounds, list)
                    or len(bounds) != 2 or any(type(x) is not int for x in bounds)
                    or bounds[0] > bounds[1]):
                raise GameIntentError("Invalid semantic range condition")
        else:
            raise GameIntentError("A condition needs eq or range")


def _steps(steps, resources):
    if not isinstance(steps, list) or len(steps) > MAX_STEPS:
        raise GameIntentError("Steps must be a bounded list")
    for step in steps:
        if not isinstance(step, dict):
            raise GameIntentError("A semantic step must be an object")
        if "residual_ir" in step:
            _keys(step, ("residual_ir",), label="residual IR step")
            _identifier(step["residual_ir"], "residual binding identifier")
            continue
        intent = step.get("intent")
        if intent == "container.open":
            _keys(step, ("intent", "entity"), label="container opening")
            if step["entity"] != "target":
                raise GameIntentError("Container opening requires the target entity")
        elif intent == "narration.emit":
            _keys(step, ("intent", "resource"), label="narration resource")
            _identifier(step["resource"], "narration resource identity")
            if step["resource"] not in resources:
                raise GameIntentError("Narration names an undeclared resource")
        elif intent == "narration.name":
            _keys(step, ("intent", "entity"), label="entity narration")
            if step["entity"] not in ("target", "first_content"):
                raise GameIntentError("Unknown narrated entity selector")
        elif intent == "discourse.remember_mentioned_object":
            _keys(step, ("intent", "entity", "scene"), label="discourse update")
            if step["entity"] not in ("target", "first_content") or step["scene"] != "current_scene":
                raise GameIntentError("Unsupported discourse selector")
        elif intent == "turn.count_player_action":
            _keys(step, ("intent", "cycle"), label="player-turn accounting")
            if type(step["cycle"]) is not int or not 1 <= step["cycle"] <= 1_000_000:
                raise GameIntentError("Invalid player-turn cycle")
        else:
            raise GameIntentError(f"Unknown game intent: {intent!r}")


def validate_uil(document):
    """Validate every condition and branch, including currently unselected ones."""
    _keys(document, ("format", "id", "resources", "interaction", "turn"),
          ("description",), label="game-intent UIL")
    if document["format"] != FORMAT:
        raise GameIntentError("Unsupported game-intent UIL format")
    _identifier(document["id"], "UIL identity")
    if "description" in document:
        _text(document["description"], "description")
    resources = document["resources"]
    if not isinstance(resources, dict) or len(resources) > MAX_RESOURCES:
        raise GameIntentError("Resources must be a bounded text map")
    for name, value in resources.items():
        _identifier(name, "resource identity")
        _text(value, "narration resource")
    if sum(len(value.encode("utf-8")) for value in resources.values()) > MAX_TEXT:
        raise GameIntentError("Narration resources exceed the byte budget")
    interaction = document["interaction"]
    _keys(interaction, ("id", "parameters", "requires", "outcomes"), label="interaction")
    _identifier(interaction["id"], "interaction identity")
    if interaction["parameters"] != {"target": "entity"}:
        raise GameIntentError("This profile requires one entity parameter named target")
    _conditions(interaction["requires"])
    outcomes = interaction["outcomes"]
    if not isinstance(outcomes, list) or not 1 <= len(outcomes) <= 32:
        raise GameIntentError("An interaction requires a bounded outcome list")
    outcome_ids = set()
    for outcome in outcomes:
        _keys(outcome, ("id", "when", "steps"), label="interaction outcome")
        name = _identifier(outcome["id"], "outcome identity")
        if name == "unrecovered" or name in outcome_ids:
            raise GameIntentError("Duplicate or reserved outcome identity")
        outcome_ids.add(name)
        _conditions(outcome["when"])
        _steps(outcome["steps"], resources)
    if sum(len(outcome["steps"]) for outcome in outcomes) > MAX_STEPS:
        raise GameIntentError("Interaction steps exceed the budget")
    turn = document["turn"]
    _keys(turn, ("id", "requires", "steps"), label="turn accounting")
    _identifier(turn["id"], "turn-accounting identity")
    _conditions(turn["requires"])
    _steps(turn["steps"], resources)
    if (len(turn["steps"]) != 1
            or turn["steps"][0].get("intent") != "turn.count_player_action"):
        raise GameIntentError("Turn accounting must count exactly one player action")
    return document


def _validate_state(state):
    _keys(state, ("entities", "current_scene", "discourse", "turn"), label="semantic state")
    entities = state["entities"]
    if not isinstance(entities, dict) or len(entities) > MAX_ENTITIES:
        raise GameIntentError("Entities must be a bounded identity map")
    for name, entity in entities.items():
        _identifier(name, "entity identity")
        _keys(entity, _ENTITY_FIELDS, label="entity state")
        if entity["name"] is not None:
            _text(entity["name"], "entity name")
        for field in _ENTITY_BOOL_FIELDS:
            if entity[field] is not None and type(entity[field]) is not bool:
                raise GameIntentError(f"Entity {field} must be boolean or unknown")
        contents = entity["contents"]
        if contents is not None:
            if not isinstance(contents, list) or len(contents) > MAX_ENTITIES:
                raise GameIntentError("Entity contents must be a bounded list or unknown")
            for child in contents:
                _identifier(child, "contained entity identity")
            if len(set(contents)) != len(contents):
                raise GameIntentError("Duplicate contained entity identity")
    if state["current_scene"] is not None:
        _identifier(state["current_scene"], "scene identity")
    _keys(state["discourse"], ("referent", "scene"), label="discourse state")
    for value in state["discourse"].values():
        if value is not None:
            _identifier(value, "discourse identity")
    _keys(state["turn"], ("count",), label="turn state")
    if state["turn"]["count"] is not None and type(state["turn"]["count"]) is not int:
        raise GameIntentError("Player-turn count must be an integer or unknown")


def _entity_id(state, arguments, selector):
    target = arguments.get("target")
    if selector == "target":
        return target if target in state["entities"] else None
    entity = state["entities"].get(target)
    contents = entity["contents"] if entity is not None else None
    return contents[0] if contents else None


def _field(state, arguments, field):
    if field == "current_scene":
        return state["current_scene"]
    selector, name = field.split(".", 1)
    if selector in ("turn", "discourse"):
        return state[selector][name]
    identity = _entity_id(state, arguments, selector)
    if name == "id":
        return identity
    entity = state["entities"].get(identity)
    if entity is None:
        return None
    if name == "contents_count":
        return len(entity["contents"]) if entity["contents"] is not None else None
    return entity[name]


def _matches(conditions, state, arguments):
    """Conjunction with explicit unknown propagation and ordered evaluation."""
    unknown = None
    for condition in conditions:
        actual = _field(state, arguments, condition["field"])
        if actual is None:
            unknown = condition["field"]
            continue
        if "eq" in condition:
            expected = condition["eq"]
            matched = type(actual) is type(expected) and actual == expected
        else:
            low, high = condition["range"]
            matched = type(actual) is int and low <= actual <= high
        if not matched:
            return False
    if unknown is not None:
        raise _Unrecovered(f"Unknown semantic condition: {unknown}")
    return True


def _known_entity(state, arguments, selector):
    identity = _entity_id(state, arguments, selector)
    if identity not in state["entities"]:
        raise _Unrecovered(f"Unknown entity selected by {selector}")
    return identity, state["entities"][identity]


def _execute_steps(document, state, arguments, steps):
    effects, executed = [], []
    for step in steps:
        if "residual_ir" in step:
            effects.append({"type": "residual_ir", "binding": step["residual_ir"]})
            continue
        intent = step["intent"]
        if intent == "container.open":
            identity, entity = _known_entity(state, arguments, step["entity"])
            if not all(entity[field] is True for field in ("is_container", "supports_opening", "reachable")):
                raise _Unrecovered("Opening requires a reachable, openable container")
            if entity["is_open"] is not False:
                raise _Unrecovered("Opening requires a known closed container")
            entity["is_open"] = True
            effects.append({"type": "container_opened", "entity": identity,
                            "was_open": False, "is_open": True})
        elif intent == "narration.emit":
            resource = step["resource"]
            effects.append({"type": "narrate", "resource": resource,
                            "text": document["resources"][resource]})
        elif intent == "narration.name":
            identity, entity = _known_entity(state, arguments, step["entity"])
            if entity["name"] is None:
                raise _Unrecovered("Narrated entity name is unknown")
            effects.append({"type": "narrate", "entity": identity, "text": entity["name"]})
        elif intent == "discourse.remember_mentioned_object":
            identity, _ = _known_entity(state, arguments, step["entity"])
            scene = state["current_scene"]
            if scene is None:
                raise _Unrecovered("Discourse update requires a known current scene")
            previous = dict(state["discourse"])
            state["discourse"] = {"referent": identity, "scene": scene}
            effects.append({"type": "referent_changed", "entity": identity,
                            "scene": scene, "previous": previous})
        elif intent == "turn.count_player_action":
            before, cycle = state["turn"]["count"], step["cycle"]
            if type(before) is not int or not 0 <= before < cycle:
                raise _Unrecovered("Player-turn count lies outside its declared cycle")
            after = (before + 1) % cycle
            state["turn"]["count"] = after
            effects.append({"type": "turn_counted", "before": before,
                            "after": after, "cycle": cycle})
        else:
            # All branches are validated before evaluation; this is defensive.
            raise GameIntentError("Unsupported game intent during evaluation")
        executed.append(intent)
    return effects, executed


def _unrecovered(state, reason):
    return {"outcome": "unrecovered", "effects": [],
            "next_state": copy.deepcopy(state), "executed_intents": [],
            "reason": reason}


def evaluate_interaction(document, state, arguments):
    """Evaluate one declared interaction without mutating caller-owned data.

    Outcome clauses use first-match order. A successful result is an effect plan,
    not authorization to execute source code. The UDL adapter must independently
    qualify its original-state binding before applying any effect.
    """
    validate_uil(document)
    _validate_state(state)
    _keys(arguments, ("target",), label="interaction arguments")
    _identifier(arguments["target"], "target identity")
    working = copy.deepcopy(state)
    interaction = document["interaction"]
    try:
        if arguments["target"] not in working["entities"]:
            raise _Unrecovered("Target entity is outside the semantic projection")
        if not _matches(interaction["requires"], working, arguments):
            raise _Unrecovered("Interaction admission conditions are not satisfied")
        for outcome in interaction["outcomes"]:
            if _matches(outcome["when"], working, arguments):
                effects, executed = _execute_steps(document, working, arguments, outcome["steps"])
                return {"outcome": outcome["id"], "effects": effects,
                        "next_state": working, "executed_intents": executed}
        raise _Unrecovered("No declared outcome covers this semantic state")
    except _Unrecovered as error:
        return _unrecovered(state, str(error))


def evaluate_turn(document, state):
    """Count a player action under an explicit cycle and admission contract.

    This primitive does not claim to execute a turn scheduler, callbacks, timers
    or randomness. Those behaviors must remain explicit outside this evaluator.
    """
    validate_uil(document)
    _validate_state(state)
    working = copy.deepcopy(state)
    try:
        if not _matches(document["turn"]["requires"], working, {}):
            raise _Unrecovered("Turn-accounting admission conditions are not satisfied")
        effects, executed = _execute_steps(document, working, {}, document["turn"]["steps"])
        return {"outcome": "turn_counted", "effects": effects,
                "next_state": working, "executed_intents": executed}
    except _Unrecovered as error:
        return _unrecovered(state, str(error))
