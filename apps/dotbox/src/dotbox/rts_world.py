"""Bounded provider-reported RTS observations, without a second game engine.

Validation establishes shape and internal consistency, not source authenticity,
visibility, object lifetime, control authority or live readiness. Projection
creates ordinary scene facts and no actions. Diffs compare reports, never run
scripts or infer destruction from an omitted object.
"""

import hashlib
import json
import re

from . import scenes


FORMAT = "dotbox-rts-world-1"
MAX_ENTITIES = 1024
MAX_EVENTS = 64
MAX_GROUPS = 32
MAX_DOCUMENT_BYTES = 1024 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9.:-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MIN, _MAX = -(1 << 31), (1 << 31) - 1
_TOP = "format source_sha256 edition observation_id state_context player_faction map camera phase entities selection groups events evidence_ref"
_ENTITY = "id kind label identity_scope incarnation_id observation_id visibility audience owner_faction controller_faction relation_to_player commandable position evidence_ref"
_GROUP = "id label kind entity_ids observation_id audience evidence_ref"
_EVENT = "id kind text audience blocking observation_id evidence_ref"


def _fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError("RTS record requires exactly the documented fields")


def _text(value, *, limit=256, nullable=False):
    if value is None and nullable:
        return
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("Expected bounded nonempty RTS text")
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise ValueError("RTS text must contain valid Unicode") from error


def _id(value):
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError("Invalid RTS identifier")


def _integer(value, minimum=0, maximum=(1 << 63) - 1, *, nullable=False):
    if value is None and nullable:
        return
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid bounded RTS integer")


def _tri(value):
    if type(value) not in (bool, type(None)):
        raise ValueError("Expected an explicit boolean or unknown null")


def _enum(value, choices):
    if not isinstance(value, str) or value not in choices:
        raise ValueError("Unknown RTS enumeration value")


def _encoded(value):
    try:
        # Match the existing scene/action canonical JSON convention, including
        # ASCII escaping. Character counts are not canonical-byte budgets.
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError) as error:
        raise ValueError("RTS observations require finite JSON") from error


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _rectangle(value):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("Expected a half-open RTS rectangle")
    for number in value:
        _integer(number, _MIN, _MAX)
    if value[0] >= value[2] or value[1] >= value[3]:
        raise ValueError("RTS rectangle must have positive extent")


def _inside(inner, outer):
    return (outer[0] <= inner[0] < inner[2] <= outer[2]
            and outer[1] <= inner[1] < inner[3] <= outer[3])


def _records(value, maximum):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError("RTS record list exceeds its declared limit")
    seen = set()
    for record in value:
        if not isinstance(record, dict):
            raise ValueError("Expected an RTS record")
        _id(record.get("id"))
        if record["id"] in seen:
            raise ValueError("Duplicate RTS record identifier")
        seen.add(record["id"])
    return seen


def _refs(value, entity_ids):
    if not isinstance(value, list) or len(value) > MAX_ENTITIES:
        raise ValueError("RTS references require a bounded list")
    for identity in value:
        _id(identity)
    if len(set(value)) != len(value) or not set(value) <= entity_ids:
        raise ValueError("Duplicate or unresolved current RTS entity reference")


def _current(record, observation):
    _text(record["observation_id"], limit=2048)
    if record["observation_id"] != observation:
        raise ValueError("RTS record is not from the current observation")
    _enum(record["audience"], ("player", "internal"))
    _text(record["evidence_ref"], limit=2048)


def validate_world(packet):
    """Validate the closed snapshot and return an independent JSON copy.

    Positions use the map's declared integer space. Camera world/screen bounds
    are separate half-open rectangles; declaring them does not qualify a live
    transform. Visible objects may have unknown positions. Player audience is
    the provider's disclosure assertion, never something inferred from faction.
    """
    encoded = _encoded(packet)
    if len(encoded) > MAX_DOCUMENT_BYTES:
        raise ValueError("RTS observation exceeds one MiB canonical JSON")
    _fields(packet, _TOP)
    if packet["format"] != FORMAT:
        raise ValueError("Unsupported RTS world format")
    if not isinstance(packet["source_sha256"], str) or _SHA.fullmatch(packet["source_sha256"]) is None:
        raise ValueError("Expected a lowercase source SHA-256")
    _text(packet["edition"])
    _text(packet["observation_id"], limit=2048)
    _text(packet["evidence_ref"], limit=2048)
    _text(packet["player_faction"], nullable=True)
    context = packet["state_context"]
    _fields(context, "provider_id session_id branch_id revision context_token")
    for key in ("provider_id", "session_id", "branch_id"):
        _text(context[key])
    _integer(context["revision"])
    _text(context["context_token"], limit=2048)
    _fields(packet["map"], "space bounds")
    _text(packet["map"]["space"], limit=128)
    bounds = packet["map"]["bounds"]
    _rectangle(bounds)
    camera = packet["camera"]
    _fields(camera, "world_bounds screen_bounds frame_size frame_id mode_id evidence_ref")
    _rectangle(camera["world_bounds"])
    _rectangle(camera["screen_bounds"])
    if not _inside(camera["world_bounds"], bounds):
        raise ValueError("RTS camera world bounds leave the declared map")
    if not isinstance(camera["frame_size"], list) or len(camera["frame_size"]) != 2:
        raise ValueError("RTS frame size requires width and height")
    for extent in camera["frame_size"]:
        _integer(extent, 1, 65535)
    if not _inside(camera["screen_bounds"], [0, 0, *camera["frame_size"]]):
        raise ValueError("RTS camera screen bounds leave the frame")
    _integer(camera["frame_id"], nullable=True)
    _integer(camera["mode_id"], nullable=True)
    _text(camera["evidence_ref"], limit=2048)
    _fields(packet["phase"], "name input_ready evidence_ref")
    _text(packet["phase"]["name"], limit=128)
    _tri(packet["phase"]["input_ready"])
    _text(packet["phase"]["evidence_ref"], limit=2048)
    entity_ids = _records(packet["entities"], MAX_ENTITIES)
    incarnations = set()
    for entity in packet["entities"]:
        _fields(entity, _ENTITY)
        _current(entity, packet["observation_id"])
        _text(entity["kind"], limit=64)
        _text(entity["label"])
        _enum(entity["identity_scope"], ("observation", "incarnation"))
        _text(entity["incarnation_id"], nullable=True)
        if entity["identity_scope"] == "incarnation":
            if entity["incarnation_id"] is None or entity["incarnation_id"] in incarnations:
                raise ValueError("Incarnation scope requires a unique explicit provider incarnation ID")
            incarnations.add(entity["incarnation_id"])
        elif entity["incarnation_id"] is not None:
            raise ValueError("Observation scope cannot assert an incarnation ID")
        _enum(entity["visibility"], ("visible", "known_offscreen", "hidden", "unknown"))
        for key in ("owner_faction", "controller_faction"):
            _text(entity[key], nullable=True)
        _enum(entity["relation_to_player"], ("self", "ally", "enemy", "neutral", "unknown"))
        _tri(entity["commandable"])
        position = entity["position"]
        if position is not None:
            if not isinstance(position, list) or len(position) != 2:
                raise ValueError("RTS position requires x,y or unknown null")
            for number in position:
                _integer(number, _MIN, _MAX)
            if not (bounds[0] <= position[0] < bounds[2] and bounds[1] <= position[1] < bounds[3]):
                raise ValueError("RTS entity position leaves the declared map")
    _fields(packet["selection"], "entity_ids pending_action evidence_ref")
    _refs(packet["selection"]["entity_ids"], entity_ids)
    _text(packet["selection"]["pending_action"], limit=128, nullable=True)
    _text(packet["selection"]["evidence_ref"], limit=2048)
    _records(packet["groups"], MAX_GROUPS)
    for group in packet["groups"]:
        _fields(group, _GROUP)
        _current(group, packet["observation_id"])
        _text(group["label"])
        if group["kind"] != "logical":
            raise ValueError("RTS groups are explicitly logical, not native selection")
        _refs(group["entity_ids"], entity_ids)
    _records(packet["events"], MAX_EVENTS)
    for event in packet["events"]:
        _fields(event, _EVENT)
        _current(event, packet["observation_id"])
        _text(event["kind"], limit=64)
        _text(event["text"], limit=2048)
        _tri(event["blocking"])
    return json.loads(encoded)


def world_digest(packet):
    """Digest every validated field, including internal events and evidence."""
    return _digest(validate_world(packet))


def _binding(packet):
    context = packet["state_context"]
    return [packet["source_sha256"], packet["edition"],
            *[context[key] for key in ("provider_id", "session_id", "branch_id")]]


def _entity_identity(packet, entity):
    if entity["identity_scope"] == "incarnation":
        key = ["incarnation", *_binding(packet), entity["incarnation_id"]]
    else:
        key = ["observation", *_binding(packet), packet["observation_id"],
               packet["state_context"], entity["id"]]
    return "rts.entity:" + _digest(key)


def project_scene(packet, max_entities=8):
    """Project current visible player records into the real bounded scene API.

    At most eight public events are prioritized, then selected visible entities,
    then other visible entities, and up to four fully visible logical groups.
    Entity count can be below max_entities when the 32-fact budget is full.
    The byte budget can shed complete optional rows, retaining the first
    selected entity as long as possible. Exact evidence/context is never
    shortened. If indispensable context alone exceeds 48 KiB, validation
    explicitly refuses the projection rather than weaken its binding.
    Omission counters count eligible public records only. No choices, executable
    routes, ownership grants or inferred event effects are produced.
    """
    packet = validate_world(packet)
    _integer(max_entities, 0, MAX_ENTITIES)
    observation = packet["observation_id"]
    subject = "rts.world:" + _digest(_binding(packet))
    result = {"format": scenes.FORMAT, "source_sha256": packet["source_sha256"],
              "edition": packet["edition"], "scene_id": "rts.observation",
              "observation_id": observation, "title": "Observed world",
              "state_context": packet["state_context"], "facts": [], "choices": [],
              "guide_sources": [], "guide_claims": []}

    def add(identity, predicate, value, text, *, audience="internal", target=subject,
            evidence=None, entity_id=None, detail=None):
        fact = {"id": identity, "subject": target, "predicate": predicate, "value": value,
                "text": text, "audience": audience, "observation_id": observation,
                "evidence_ref": evidence or packet["evidence_ref"]}
        if entity_id is not None:
            fact["entity_id"] = entity_id
        if detail is not None:
            fact["detail"] = detail
        result["facts"].append(fact)

    visible = [e for e in packet["entities"] if e["visibility"] == "visible" and e["audience"] == "player"]
    visible_ids = {e["id"] for e in visible}
    selected = set(packet["selection"]["entity_ids"])
    visible.sort(key=lambda e: e["id"] not in selected)
    camera = packet["camera"]["world_bounds"]
    add("world_digest", "world_digest", _digest(packet), "Complete provider snapshot digest.")
    add("phase", "phase", packet["phase"]["name"], "Current phase: " + packet["phase"]["name"] + ".",
        audience="player", evidence=packet["phase"]["evidence_ref"])
    add("input_ready", "input_ready", packet["phase"]["input_ready"],
        "Provider readiness assertion; not an ownership or action grant.", evidence=packet["phase"]["evidence_ref"])
    add("camera_left", "camera_left", camera[0], f"Viewport origin is ({camera[0]}, {camera[1]}) in {packet['map']['space']}.",
        audience="player", evidence=packet["camera"]["evidence_ref"])
    add("camera_top", "camera_top", camera[1], "Observed viewport top coordinate.", evidence=packet["camera"]["evidence_ref"])
    selection_count = len(selected & visible_ids)
    add("selection_count", "selection_count", selection_count,
        f"{selection_count} visible {'entity is' if selection_count == 1 else 'entities are'} reported selected.",
        audience="player", evidence=packet["selection"]["evidence_ref"])
    pending = packet["selection"]["pending_action"]
    add("pending_action", "pending_action", pending,
        "Pending action: " + pending + "." if pending is not None else "No pending action is reported.",
        audience="player", evidence=packet["selection"]["evidence_ref"])
    add("freshness", "freshness", "provider_report_only",
        "This describes the recorded observation; live state and input permission require a fresh check.", audience="player")
    events = [event for event in packet["events"] if event["audience"] == "player"]
    events.sort(key=lambda event: {True: 0, None: 1, False: 2}[event["blocking"]])
    shown_events = events[:8]
    for index, event in enumerate(shown_events):
        add(f"event_{index}", "blocking", event["blocking"], event["text"], audience="player",
            target="rts.event:" + _digest([*_binding(packet), event["id"]]), evidence=event["evidence_ref"],
            detail="Reported event kind: " + event["kind"] + "; no response is executed by this view.")
    entity_limit = min(max_entities, (32 - len(result["facts"]) - 3) // 2)
    shown_entities = visible[:entity_limit]
    for index, entity in enumerate(shown_entities):
        entity_id = _entity_identity(packet, entity)
        position = entity["position"]
        location = f" at ({position[0]}, {position[1]})" if position is not None else " at an unknown position"
        text = entity["label"] + location + "; relation to player: " + entity["relation_to_player"] + "."
        add(f"entity_{index}", "relation_to_player", entity["relation_to_player"], text,
            audience="player", target=entity_id, evidence=entity["evidence_ref"], entity_id=entity_id,
            detail="Identity scope: " + entity["identity_scope"] + "; affiliation does not establish command authority.")
        add(f"entity_{index}_commandable", "commandable", entity["commandable"],
            "Separate provider commandability assertion.", target=entity_id, evidence=entity["evidence_ref"], entity_id=entity_id)
    groups = [group for group in packet["groups"] if group["audience"] == "player"
              and set(group["entity_ids"]) <= visible_ids]
    shown_groups = groups[:min(4, 32 - len(result["facts"]) - 3)]
    for index, group in enumerate(shown_groups):
        count = len(group["entity_ids"])
        add(f"group_{index}", "logical_member_count", count,
            f"Logical group {group['label']} contains {count} visible {'entity' if count == 1 else 'entities'}.",
            audience="player", target="rts.group:" + _digest([*_binding(packet), observation, group["id"]]),
            evidence=group["evidence_ref"], detail="This grouping does not select entities or issue a group order.")
    for name, eligible, shown in (("entities", visible, shown_entities), ("events", events, shown_events), ("groups", groups, shown_groups)):
        add("omitted_" + name, "omitted_" + name, len(eligible) - len(shown),
            "Eligible public " + name + " omitted by this scene budget.")
    if len(_encoded(result)) > scenes.MAX_DOCUMENT_BYTES:
        # Repeated observation/evidence strings can exhaust bytes before facts.
        # A bounded note replaces optional omission counters without changing
        # any source text, observation identifier or evidence reference.
        result["facts"] = [fact for fact in result["facts"] if not fact["id"].startswith("omitted_")]
        freshness = next(fact for fact in result["facts"] if fact["id"] == "freshness")
        while True:
            freshness["detail"] = (f"Scene budget omitted {len(visible) - len(shown_entities)} eligible public entities, "
                f"{len(events) - len(shown_events)} events and {len(groups) - len(shown_groups)} logical groups. "
                "The complete observation remains bound by its digest.")
            if len(_encoded(result)) <= scenes.MAX_DOCUMENT_BYTES:
                break
            if shown_groups:
                shown_groups.pop()
                remove = {f"group_{len(shown_groups)}"}
            elif len(shown_entities) > 1:
                shown_entities.pop()
                remove = {f"entity_{len(shown_entities)}", f"entity_{len(shown_entities)}_commandable"}
            elif shown_events:
                shown_events.pop()
                remove = {f"event_{len(shown_events)}"}
            elif shown_entities:
                shown_entities.pop()
                remove = {"entity_0", "entity_0_commandable"}
            else:
                # Exact required context itself cannot fit. The ordinary
                # scene validator below provides the controlled budget error.
                break
            result["facts"] = [fact for fact in result["facts"] if fact["id"] not in remove]
    return scenes.validate_scene(result)


def _changed(before, after, fields):
    return {name: {"before": before[name], "after": after[name]}
            for name in fields if before[name] != after[name]}


def _record_delta(before, after, fields):
    first, second = ({record["id"]: record for record in records} for records in (before, after))
    return {"newly_reported": [second[key] for key in second if key not in first],
            "no_longer_reported": [first[key] for key in first if key not in second],
            "changed": [{"id": key, "fields": change, "before_evidence": first[key]["evidence_ref"],
                         "after_evidence": second[key]["evidence_ref"]}
                        for key in second if key in first
                        if (change := _changed(first[key], second[key], fields))]}


def diff_world(before, after):
    """Return internal report differences within one monotonically ordered branch.

    Cross-observation entity comparison requires the same explicit provider
    incarnation ID. Reused observation-scoped IDs never prove continuity.
    Newly/no-longer observed records do not imply spawn, death or visibility
    changes. Events are compared only as supplied reports; none are synthesized
    from entity changes. Identical same-revision observations are idempotent.
    """
    before, after = validate_world(before), validate_world(after)
    if _binding(before) != _binding(after):
        raise ValueError("RTS diff requires the same source, edition, provider, session and branch")
    first_revision, last_revision = (p["state_context"]["revision"] for p in (before, after))
    before_digest, after_digest = _digest(before), _digest(after)
    if last_revision < first_revision or (last_revision == first_revision and before_digest != after_digest):
        raise ValueError("RTS diff refuses stale or conflicting same-revision observations")
    result = {"format": "dotbox-rts-world-diff-1", "scope": "internal_provider_reports_only",
              "before_digest": before_digest, "after_digest": after_digest,
              "before_observation_id": before["observation_id"], "after_observation_id": after["observation_id"],
              "before_revision": first_revision, "after_revision": last_revision,
              "state_context": after["state_context"], "entity_changes": [], "newly_observed": [],
              "no_longer_observed": [], "context_changes": {},
              "events": {"newly_reported": [], "no_longer_reported": [], "changed": []},
              "groups": {"newly_reported": [], "no_longer_reported": [], "changed": []},
              "omissions_are_not_destruction": True,
              "claim": "Observed report comparison only; no inferred causes, scripts, events, entity lifetimes or action authority"}
    if before_digest == after_digest:
        return result
    first = {e["incarnation_id"]: e for e in before["entities"] if e["identity_scope"] == "incarnation"}
    second = {e["incarnation_id"]: e for e in after["entities"] if e["identity_scope"] == "incarnation"}
    matched = first.keys() & second.keys()
    fields = "id kind label visibility audience owner_faction controller_faction relation_to_player commandable position".split()
    for incarnation in sorted(matched):
        a, b = first[incarnation], second[incarnation]
        changes = _changed(a, b, fields)
        if changes:
            result["entity_changes"].append({"before_id": a["id"], "after_id": b["id"],
                "incarnation_id": incarnation, "fields": changes,
                "before_evidence": a["evidence_ref"], "after_evidence": b["evidence_ref"]})
    for packet, target in ((before, "no_longer_observed"), (after, "newly_observed")):
        result[target] = [{key: entity[key] for key in ("id", "identity_scope", "incarnation_id", "observation_id", "evidence_ref")}
                          for entity in packet["entities"]
                          if entity["identity_scope"] != "incarnation" or entity["incarnation_id"] not in matched]
    result["context_changes"] = _changed(before, after, ("player_faction", "map", "camera", "phase", "selection"))
    result["events"] = _record_delta(before["events"], after["events"], ("kind", "text", "audience", "blocking"))
    result["groups"] = _record_delta(before["groups"], after["groups"], ("label", "kind", "entity_ids", "audience"))
    result["groups"]["membership_continuity"] = "Reference lists are current declarations; matching observation-scoped IDs do not prove the same members"
    return result
