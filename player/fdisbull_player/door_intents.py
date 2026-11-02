"""Named door interactions and shuffled feedback, without source machinery.

The document supplies the entity, presentation fact, action messages and response
bag. This evaluator sees no addresses, VM variables, packed references or source
stack. A separate UDL adapter qualifies those bindings and realizes the ordered
effects; scene traversal, command admission and turn completion are separate.

Planning an interaction never draws randomness or mutates a response bag. The
``shuffled_response`` effect asks its adapter to draw once, select with
``select_response``, realize the returned bag change and emit that response.
The same response can occur on both sides of a completed bag cycle.
"""

from __future__ import annotations

import copy


FORMAT = "fdisbull-door-interaction-uil-1"
MAX_BAG_SIZE = 32
MAX_RESOURCES = 64
MAX_TEXT_BYTES = 64 * 1024
MAX_IDENTIFIER_LENGTH = 160


class DoorIntentError(ValueError):
    """A door-interaction document, state or supplied draw is malformed."""


def _keys(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise DoorIntentError(f"{label} has missing or unknown fields")


def _identifier(value, label):
    if (not isinstance(value, str) or not value
            or len(value) > MAX_IDENTIFIER_LENGTH
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise DoorIntentError(f"Invalid {label}")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise DoorIntentError(f"Invalid Unicode in {label}") from exc
    return value


def _text_size(value):
    if not isinstance(value, str) or len(value) > MAX_TEXT_BYTES:
        raise DoorIntentError("Invalid or excessive narration resource")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as exc:
        raise DoorIntentError("Invalid Unicode in narration resource") from exc
    if size > MAX_TEXT_BYTES:
        raise DoorIntentError("Excessive narration resource")
    return size


def _resource(document, identity):
    _identifier(identity, "resource identity")
    if identity not in document["resources"]:
        raise DoorIntentError("Unknown narration resource")


def _permutation(order, resources):
    if not isinstance(order, list) or len(order) != len(resources):
        raise DoorIntentError("Response order must include the complete bag")
    for identity in order:
        _identifier(identity, "response identity")
    if len(set(order)) != len(order) or set(order) != set(resources):
        raise DoorIntentError("Response order is not a permutation of the declared bag")


def validate_uil(document):
    """Validate the complete versioned definition, including unused resources.

    Opening means setting the door's named Boolean state to true and closing to
    false. The repeat bag is a finite collection without replacement within a
    cycle. Its initial order may be any declared permutation, beginning at zero.
    """
    _keys(document, ("format", "id", "door", "history_fact", "resources",
                     "actions", "repeat", "newline_resource"), "door-interaction UIL")
    if document["format"] != FORMAT:
        raise DoorIntentError("Unsupported door-interaction UIL format")
    for name in ("id", "door", "history_fact"):
        _identifier(document[name], name)

    resources = document["resources"]
    if not isinstance(resources, dict) or not 1 <= len(resources) <= MAX_RESOURCES:
        raise DoorIntentError("Invalid or excessive narration resource catalogue")
    text_bytes = 0
    for identity, text in resources.items():
        _identifier(identity, "resource identity")
        text_bytes += _text_size(text)
        if text_bytes > MAX_TEXT_BYTES:
            raise DoorIntentError("Narration resource byte budget exceeded")

    _keys(document["actions"], ("open", "close"), "door actions")
    for action, is_open in (("open", True), ("close", False)):
        rule = document["actions"][action]
        _keys(rule, ("is_open", "resource"), "door action")
        if rule["is_open"] is not is_open:
            raise DoorIntentError("Door action changes the declared meaning of open or close")
        _resource(document, rule["resource"])

    repeat = document["repeat"]
    _keys(repeat, ("id", "resources", "initial_order", "initial_cursor"), "response bag")
    _identifier(repeat["id"], "response bag identity")
    names = repeat["resources"]
    if not isinstance(names, list) or not 1 <= len(names) <= MAX_BAG_SIZE:
        raise DoorIntentError("Invalid or excessive response bag")
    for identity in names:
        _resource(document, identity)
    if len(set(names)) != len(names):
        raise DoorIntentError("Response bag identities must be distinct")
    _permutation(repeat["initial_order"], names)
    if type(repeat["initial_cursor"]) is not int or repeat["initial_cursor"] != 0:
        raise DoorIntentError("Initial response cursor must be zero")

    _resource(document, document["newline_resource"])
    if resources[document["newline_resource"]] != "\n":
        raise DoorIntentError("Newline resource must contain exactly one newline")
    return document


def _bag(document, bag):
    _keys(bag, ("order", "cursor"), "live response bag")
    _permutation(bag["order"], document["repeat"]["resources"])
    cursor = bag["cursor"]
    if type(cursor) is not int or not 0 <= cursor < len(bag["order"]):
        raise DoorIntentError("Live response cursor is outside the bag")


def _state(document, state):
    _keys(state, ("door_open", "hint_dismissed", "response_bag"), "interaction state")
    for name in ("door_open", "hint_dismissed"):
        if state[name] is not None and type(state[name]) is not bool:
            raise DoorIntentError(f"{name} requires a Boolean or an explicit unknown")
    if state["response_bag"] is not None:
        _bag(document, state["response_bag"])


def evaluate_interaction(document, state, action):
    """Plan one admitted open/close interaction without changing its inputs.

    Unsupported actions and unknown required state produce no effects. An
    unknown prior hint value is harmless: the effect unconditionally dismisses
    it. An unknown repeat bag is needed only when the door already has the
    requested state. Invalid data is an error, not an invented missing value.

    ``next_state`` describes door and hint effects only. A planned shuffled
    response does not select its resource or predict its bag without a draw.
    ``executed_intents`` follows effect order and can name narration twice.
    """
    validate_uil(document)
    _state(document, state)
    _identifier(action, "action")
    result = {
        "status": "unknown", "outcome": "unrecovered", "effects": [],
        "next_state": copy.deepcopy(state), "executed_intents": [],
    }
    if action not in document["actions"]:
        result["reason"] = "unsupported_action"
        return result
    if state["door_open"] is None:
        result["reason"] = "door_state_unknown"
        return result

    rule = document["actions"][action]
    changed = state["door_open"] != rule["is_open"]
    if not changed and state["response_bag"] is None:
        result["reason"] = "response_bag_unknown"
        return result

    result["status"] = "handled"
    result["outcome"] = ({"open": "opened", "close": "closed"}[action]
                         if changed else "already_" + ("open" if rule["is_open"] else "closed"))
    result["effects"].append({"type": "hint_dismissed", "fact": document["history_fact"]})
    result["executed_intents"].append("presentation.dismiss_initial_hint")
    result["next_state"]["hint_dismissed"] = True

    def narrate(resource):
        result["effects"].append({
            "type": "narrate", "resource": resource, "text": document["resources"][resource],
        })
        result["executed_intents"].append("narration.emit")

    if changed:
        # Presentation precedes the state change; a failed presentation must not
        # be reported as a completed door transition by a realizing adapter.
        narrate(rule["resource"])
        result["effects"].append({
            "type": "door_state_changed", "door": document["door"],
            "was_open": state["door_open"], "is_open": rule["is_open"],
        })
        result["executed_intents"].append("door." + action)
        result["next_state"]["door_open"] = rule["is_open"]
    else:
        result["effects"].append({"type": "shuffled_response", "bag": document["repeat"]["id"]})
        result["executed_intents"].append("narration.choose_shuffled_response")
    narrate(document["newline_resource"])
    return result


def select_response(document, bag_state, draw):
    """Resolve one supplied draw into a response and a new bag, without RNG I/O.

    ``cursor`` is the number of responses already used in the current cycle.
    ``draw`` is one-based within the remaining suffix. The chosen response moves
    to the cursor position and the old cursor response occupies its former
    position. The cursor wraps immediately after the last response of a cycle.

    Positions in the result are zero-based. Both are returned even when equal:
    an adapter with an ordered-write contract must not erase a same-slot swap.
    """
    validate_uil(document)
    _bag(document, bag_state)
    cursor = bag_state["cursor"]
    order = bag_state["order"]
    if type(draw) is not int or not 1 <= draw <= len(order) - cursor:
        raise DoorIntentError("Response draw is outside the remaining bag")
    chosen = cursor + draw - 1
    resource = order[chosen]
    next_order = list(order)
    next_order[chosen] = order[cursor]
    next_order[cursor] = resource
    return {
        "resource": resource, "text": document["resources"][resource],
        "chosen_position": chosen, "cursor_position": cursor,
        "next_bag": {"order": next_order, "cursor": (cursor + 1) % len(order)},
    }
