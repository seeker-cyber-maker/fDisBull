"""Composable RTS requests and a single-owner provider dispatch boundary.

No game, native RPC, or desktop input is opened by this module. A provider must
qualify each semantic binding and enforce its own atomic observation/ownership
fence inside execute(). This contract does not qualify an arbitrary provider.
"""

from copy import deepcopy
import hashlib
import inspect
import json
import secrets
import threading

from .rts_world import validate_world, world_digest, diff_world


PRIMITIVES = {
    "pan_view": "Change the camera independently of unit orders.",
    "select_entity": "Select one observed entity without issuing its next command.",
    "select_group": "Select a logical group, or request separately supported native selection.",
    "choose_action": "Choose a command independently of submitting its target.",
    "select_target": "Submit a target for the currently observed pending command.",
    "context_click": "Invoke a qualified right-click binding; its meaning is context dependent.",
    "drag_pointer": "Perform one bounded held-pointer gesture through a qualified binding.",
    "respond_to_event": "Explicitly respond to a current mission or interface event.",
}
MAX_REQUEST_BYTES = 16 * 1024


class ActionRefused(ValueError):
    """The operation was not dispatched through this controller."""


class ActionUncertain(RuntimeError):
    """Provider state or delivery is uncertain; this controller cannot mutate again."""

    def __init__(self, message, *, receipt=None):
        super().__init__(message)
        self.receipt = deepcopy(receipt)


def _encode(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("RTS request must contain finite JSON") from error


def _digest(value):
    return hashlib.sha256(_encode(value).encode()).hexdigest()


def _fields(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise ValueError("Missing or unsupported RTS action fields")


def _text(value, name, limit=256):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonempty text of at most {limit} characters")
    return value


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in {low}..{high}")


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Expected a lowercase SHA-256 identity")


def _point(value, bounds):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("Expected a two-integer coordinate")
    for coordinate in value:
        _integer(coordinate, "coordinate", -(2**31), 2**31 - 1)
    if not bounds[0] <= value[0] < bounds[2] or not bounds[1] <= value[1] < bounds[3]:
        raise ActionRefused("Target lies outside the declared coordinate bounds")


def _entity(world, identity, *, commandable=False):
    _text(identity, "entity_id")
    entity = next((item for item in world["entities"] if item["id"] == identity), None)
    if entity is None:
        raise ActionRefused("Entity is not in the current observation")
    if entity["audience"] != "player" or entity["visibility"] != "visible":
        raise ActionRefused("Entity is not currently visible to the player")
    if commandable and entity["commandable"] is not True:
        raise ActionRefused("Current player commandability is not established")
    return entity


def _members(world, identities, *, commandable=False):
    if (not isinstance(identities, list) or not 1 <= len(identities) <= 128
            or any(not isinstance(item, str) for item in identities)
            or len(set(identities)) != len(identities)):
        raise ValueError("Group requires 1..128 distinct entity IDs")
    return [_entity(world, item, commandable=commandable) for item in identities]


def _target(world, target):
    if isinstance(target, dict) and set(target) == {"entity_id"}:
        _entity(world, target["entity_id"])
    elif isinstance(target, dict) and set(target) == {"position"}:
        _point(target["position"], world["map"]["bounds"])
    else:
        raise ValueError("Target requires exactly one entity_id or world position")


def _arguments(world, primitive, arguments):
    if not isinstance(primitive, str) or primitive not in PRIMITIVES:
        raise ValueError("Unknown RTS action primitive")
    if len(_encode(arguments).encode()) > MAX_REQUEST_BYTES:
        raise ValueError("RTS arguments exceed the 16 KiB budget")
    args = deepcopy(arguments)
    if primitive == "pan_view":
        _fields(args, "position")
        _point(args["position"], world["map"]["bounds"])
    elif primitive == "select_entity":
        _fields(args, "entity_id")
        _entity(world, args["entity_id"])
    elif primitive == "select_group":
        _fields(args, "group_id entity_ids mode")
        _text(args["group_id"], "group_id")
        if args["mode"] not in ("logical", "native"):
            raise ValueError("Group mode must be logical or native")
        _members(world, args["entity_ids"], commandable=args["mode"] == "native")
    elif primitive == "choose_action":
        _fields(args, "action_id")
        _text(args["action_id"], "action_id")
        _members(world, world["selection"]["entity_ids"], commandable=True)
    elif primitive in ("select_target", "context_click"):
        _fields(args, "target")
        _target(world, args["target"])
        if primitive == "select_target":
            if world["selection"]["pending_action"] is None:
                raise ActionRefused("No currently observed command is awaiting a target")
            _members(world, world["selection"]["entity_ids"], commandable=True)
    elif primitive == "drag_pointer":
        _fields(args, "surface start end button max_guest_ms max_frames timeout_ms")
        _text(args["surface"], "surface")
        if args["button"] not in ("left", "right", "middle"):
            raise ValueError("Unsupported drag button")
        width, height = world["camera"]["frame_size"]
        for name in ("start", "end"):
            _point(args[name], [0, 0, width, height])
        _integer(args["max_guest_ms"], "aggregate guest milliseconds", 1, 4000)
        _integer(args["max_frames"], "aggregate frames", 1, 400)
        _integer(args["timeout_ms"], "aggregate host timeout", 1, 15000)
    else:
        _fields(args, "event_id response_id")
        _text(args["event_id"], "event_id")
        _text(args["response_id"], "response_id")
        if not any(event["id"] == args["event_id"] and event["audience"] == "player"
                   for event in world["events"]):
            raise ActionRefused("Response requires a current player-visible event")
    return args


def _guards(world, primitive, args):
    if primitive == "select_group" and args["mode"] == "logical":
        return
    if world["phase"]["input_ready"] is not True:
        raise ActionRefused("Current input readiness is not established")
    if primitive != "respond_to_event":
        if world["phase"]["name"] != "gameplay":
            raise ActionRefused("Ordinary RTS input requires the gameplay phase")
        if any(event["blocking"] is not False for event in world["events"]):
            raise ActionRefused("A current event blocks input or has unknown blocking status")
    elif world["phase"]["name"] == "unknown":
        raise ActionRefused("Event response requires a known interface phase")
    if primitive in ("pan_view", "select_entity", "select_group", "select_target", "context_click", "drag_pointer"):
        if world["camera"]["frame_id"] is None or world["camera"]["mode_id"] is None:
            raise ActionRefused("Pointer bindings require a current frame and mode")


def prepare_action(world, primitive, arguments):
    """Validate one offline request; no admission, execution token, or input.

    This does not prescribe a preceding or following action. For example, a
    selected command and a target are independent requests, not a Move macro.
    """
    world = validate_world(world)
    args = _arguments(world, primitive, arguments)
    _guards(world, primitive, args)
    request = {"format": "dotbox-rts-request-1", "primitive": primitive, "arguments": args,
               "world_sha256": world_digest(world), "source_sha256": world["source_sha256"],
               "edition": world["edition"], "observation_id": world["observation_id"],
               "state_context": deepcopy(world["state_context"]), "execution": "not_performed"}
    request_digest(request)  # Enforce the complete request bound before admission.
    return request


def check_action(request, world):
    """Rebuild against the supplied world; equality never grants live input."""
    _fields(request, "format primitive arguments world_sha256 source_sha256 edition observation_id state_context execution")
    expected = prepare_action(world, request["primitive"], request["arguments"])
    if _encode(request) != _encode(expected):
        raise ActionRefused("Stale or changed RTS action request; prepare from the current observation")
    return deepcopy(expected)


def request_digest(request):
    """Canonical request identity for a provider's admission and receipt.

    Uses UTF-8 of sorted compact JSON with ASCII escapes and no NaN/Infinity,
    the same canonical convention as world and scene document identities.
    """
    _fields(request, "format primitive arguments world_sha256 source_sha256 edition observation_id state_context execution")
    if request["format"] != "dotbox-rts-request-1" or request["execution"] != "not_performed":
        raise ValueError("Expected a prepared RTS request")
    if len(_encode(request).encode()) > MAX_REQUEST_BYTES:
        raise ValueError("RTS request exceeds the 16 KiB budget")
    return _digest(request)


def _admission(value, request):
    _fields(value, "format request_sha256 binding_id binding_sha256 control_token enabled ready evidence_ref")
    if value["format"] != "dotbox-rts-admission-1" or value["request_sha256"] != _digest(request):
        raise ActionRefused("Admission does not bind this exact request")
    for name in ("binding_id", "control_token", "evidence_ref"):
        _text(value[name], name, 2048)
    _sha(value["binding_sha256"])
    if value["enabled"] is not True or value["ready"] is not True:
        raise ActionRefused("Provider has not admitted an enabled and ready binding")
    return deepcopy(value)


def _fence(admission):
    return tuple(admission[name] for name in ("request_sha256", "binding_id", "binding_sha256", "control_token"))


def _receipt(value, request):
    _fields(value, "format request_sha256 action_sent accepted complete effects evidence_ref observation")
    if value["format"] != "dotbox-rts-receipt-1" or value["request_sha256"] != _digest(request):
        raise ValueError("Provider receipt does not bind this request")
    for name in ("action_sent", "accepted", "complete"):
        if type(value[name]) not in (bool, type(None)):
            raise ValueError("Receipt milestones require a boolean or explicit unknown")
    if value["effects"] not in ("applied-confirmed", "partial", "none-confirmed", "unknown"):
        raise ValueError("Unsupported effect status")
    _text(value["evidence_ref"], "evidence_ref", 2048)
    # Do not copy an unvalidated potentially recursive after-observation before
    # retaining the separately validated delivery/acceptance milestones.
    return dict(value)


class RtsController:
    """One synchronous owner, one pending request, no queue or automatic replay.

    Provider protocol:
      observe() -> coherent validated world (read only).
      admit(request) -> admission or None (read only).
      execute(request, *, expected_admission) -> receipt.

    execute MUST atomically recheck the exact world/context, immutable binding,
    ownership/control token and input readiness before effects, and retain that
    fence throughout any held gesture. It must bound all phases, verify source
    consumption before held movement, release only its own known input, and
    stop without further calls on uncertain transport or foreign ownership.
    This class performs no native cleanup and cannot supply those guarantees
    for a provider that lacks them. Existing desktop/native policy is unchanged.
    """

    def __init__(self, provider):
        if any(not callable(getattr(provider, name, None)) for name in ("observe", "admit", "execute")):
            raise ValueError("Provider must implement observe, admit, and execute")
        self._provider = provider
        self._thread = threading.get_ident()
        self._in_provider = False
        self._pending = None
        self._uncertain = False
        self._last_receipt = None
        self._head = None
        self._logical = None
        self._group_revision = 0

    @property
    def uncertain(self):
        return self._uncertain

    @property
    def last_receipt(self):
        return deepcopy(self._last_receipt)

    def _check(self):
        if threading.get_ident() != self._thread:
            raise ActionRefused("RTS controller has a different owning thread")
        if self._in_provider:
            raise ActionRefused("RTS provider calls cannot reenter the controller")
        if self._uncertain:
            raise ActionUncertain("Provider uncertainty is latched; independently recover before creating a new controller",
                                  receipt=self._last_receipt)

    def _call(self, method, *args, **kwargs):
        self._in_provider = True
        returned = False
        try:
            result = getattr(self._provider, method)(*deepcopy(args), **deepcopy(kwargs))
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError("RTS providers must return synchronous completed calls")
            returned = True
            return result
        except Exception as error:
            self._uncertain = True
            self._pending = None
            raise ActionUncertain(f"Provider {method} failed; no automatic retry or cleanup was attempted",
                                  receipt=self._last_receipt) from error
        finally:
            if not returned:
                self._uncertain = True
                self._pending = None
            self._in_provider = False  # Host bookkeeping only; never native cleanup.

    def _remember(self, world):
        world = validate_world(world)
        if self._head is not None:
            # Coherent observations cannot regress, reuse a revision with a
            # different payload, or cross a provider/session/restore binding.
            diff_world(self._head, world)
        self._head = world
        return deepcopy(world)

    def observe(self):
        self._check()
        try:
            return self._remember(self._call("observe"))
        except Exception as error:
            self._uncertain = True
            self._pending = None
            raise ActionUncertain("Provider returned an invalid observation", receipt=self._last_receipt) from error

    def prepare(self, world, primitive, arguments):
        self._check()
        self._pending = None  # Replacing an intention never queues the old one.
        try:
            world = self._remember(world)
        except (ValueError, TypeError, RecursionError) as error:
            raise ActionRefused("Supplied world is invalid or conflicts with the controller's observation head") from error
        request = prepare_action(world, primitive, arguments)
        logical = primitive == "select_group" and request["arguments"]["mode"] == "logical"
        admission = None
        if not logical:
            reported = self._call("admit", request)
            if reported is None:
                raise ActionRefused("Provider has no qualified binding for this primitive and context")
            admission = _admission(reported, request)
        plan = {"format": "dotbox-rts-intent-1", "token": secrets.token_hex(24),
                "request": request, "group_revision": self._group_revision}
        self._pending = {"plan": deepcopy(plan), "world": validate_world(world), "admission": admission}
        return deepcopy(plan)

    def cancel(self):
        """Discard a prepared intention without provider calls or game input."""
        if threading.get_ident() != self._thread:
            raise ActionRefused("RTS controller has a different owning thread")
        if self._in_provider:
            raise ActionRefused("RTS provider calls cannot reenter the controller")
        self._pending = None

    def execute(self, plan):
        self._check()
        pending = self._pending
        if (not isinstance(plan, dict) or pending is None
                or plan.get("token") != pending["plan"]["token"]):
            raise ActionRefused("Unknown, foreign, cancelled, or consumed action token")
        self._pending = None  # Consume before any provider call, including observation.
        if _encode(plan) != _encode(pending["plan"]):
            raise ActionRefused("Prepared action was modified")
        world = self.observe()
        request = check_action(pending["plan"]["request"], world)
        if pending["admission"] is None:
            args = request["arguments"]
            self._group_revision += 1
            self._logical = {"group_id": args["group_id"], "group_revision": self._group_revision,
                             "world": world, "members": deepcopy(args["entity_ids"])}
            return {"format": "dotbox-rts-result-1", "scope": "planner", "execution": "not_performed",
                    "request_sha256": _digest(request), "logical_selection": self.logical_selection(world),
                    "native_selection": deepcopy(world["selection"]), "receipt": None, "changes": None}
        reported = self._call("admit", request)
        if reported is None:
            raise ActionRefused("Binding is no longer admitted")
        current = _admission(reported, request)
        if _fence(current) != _fence(pending["admission"]):
            raise ActionRefused("Control ownership or binding changed; prepare a new action")
        returned = self._call("execute", request, expected_admission=current)
        self._uncertain = True  # Remains latched if receipt validation is interrupted.
        try:
            receipt = _receipt(returned, request)
            # Keep acknowledged milestones even if a subsequent observation fails.
            self._last_receipt = {key: value for key, value in receipt.items() if key != "observation"}
            if receipt["action_sent"] is None:
                raise ValueError("Delivery state is unknown")
            changes = None
            if receipt["observation"] is not None:
                after = self._remember(receipt["observation"])
                changes = diff_world(world, after)
                receipt["observation"] = after
        except Exception as error:
            self._uncertain = True
            raise ActionUncertain("Provider outcome is uncertain; token consumed and further mutation blocked",
                                  receipt=self._last_receipt) from error
        self._uncertain = False
        return {"format": "dotbox-rts-result-1", "scope": "game", "execution": "provider_returned",
                "request_sha256": _digest(request), "receipt": receipt, "changes": changes}

    def logical_selection(self, world):
        """Resolve planner membership without input, substitution, or native claims."""
        world = validate_world(world)
        if self._logical is None:
            return {"status": "empty", "group_revision": self._group_revision, "entity_ids": []}
        old = self._logical["world"]
        binding = lambda item: (item["source_sha256"], item["edition"], *(item["state_context"][key]
                           for key in ("provider_id", "session_id", "branch_id")))
        same_binding = binding(old) == binding(world)
        if self._head is not None:
            try:
                diff_world(self._head, world)
            except ValueError:
                same_binding = False
        if world["state_context"]["revision"] < old["state_context"]["revision"]:
            same_binding = False
        if (world["state_context"]["revision"] == old["state_context"]["revision"]
                and world_digest(old) != world_digest(world)):
            same_binding = False
        old_entities = {item["id"]: item for item in old["entities"]}
        current = {item["id"]: item for item in world["entities"]}
        valid, unresolved = [], []
        for identity in self._logical["members"]:
            before, now = old_entities[identity], current.get(identity)
            same = same_binding and now is not None and before["identity_scope"] == now["identity_scope"]
            if same and before["identity_scope"] == "incarnation":
                same = before["incarnation_id"] == now["incarnation_id"]
            elif same:
                same = old["observation_id"] == world["observation_id"] and world_digest(old) == world_digest(world)
            (valid if same else unresolved).append(identity)
        return {"status": "current" if not unresolved else "stale", "group_id": self._logical["group_id"],
                "group_revision": self._logical["group_revision"], "entity_ids": valid,
                "unresolved_entity_ids": unresolved, "native_selection": False,
                "observation_id": world["observation_id"], "revision": world["state_context"]["revision"]}
