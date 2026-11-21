"""Bounded offline scene projections and selection intents, without execution.

Observation semantics and input-route applicability are caller reports. A guide
claim is an expectation, never an observation or an instruction to this module.
Describing supplied facts does not send an in-game look command.
"""

import argparse
import hashlib
import json
import re
import sqlite3
import sys


FORMAT = "dotbox-scene-1"
MAX_DOCUMENT_BYTES = 48 * 1024
MAX_FILE_BYTES = 96 * 1024
CLAIM = "Caller-reported observation semantics; no independent scene recognition or live verification"


def _encode(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("Scene must contain bounded JSON data") from error


def _text(value, name, limit=2048, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError(f"{name} must be {'possibly empty' if empty else 'nonempty'} text of at most {limit} characters")
    return value


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9.:-]{0,127}", value):
        raise ValueError("Expected a scene identifier")
    return value


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Expected a lowercase SHA-256 identity")
    return value


def _fields(record, required, optional=""):
    required, optional = set(required.split()), set(optional.split())
    if not isinstance(record, dict) or not required <= set(record) or set(record) - required - optional:
        raise ValueError("Missing or unsupported scene fields")


def _records(value, name, limit):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"{name} must be a list of at most {limit} records")
    seen = set()
    for record in value:
        if not isinstance(record, dict):
            raise ValueError(f"Each {name} record must be an object")
        identity = _identifier(record.get("id"))
        if identity in seen:
            raise ValueError(f"Duplicate {name} identifier")
        seen.add(identity)
    return value


def _scalar(value):
    if type(value) not in (str, bool, int, type(None)):
        raise ValueError("Fact and guide values require a string, boolean, integer or null")
    if isinstance(value, str):
        _text(value, "value", empty=True)


def validate_scene(packet):
    """Validate a closed, bounded document and return an independent JSON copy."""
    _fields(packet, "format source_sha256 edition scene_id observation_id title facts choices guide_sources guide_claims",
            "selection_sha256 state_context outcome")
    encoded = _encode(packet)
    if len(encoded.encode()) > MAX_DOCUMENT_BYTES:
        raise ValueError("Scene exceeds the 48 KiB canonical JSON budget")
    if packet["format"] != FORMAT:
        raise ValueError("Unsupported scene format")
    _sha(packet["source_sha256"])
    if "selection_sha256" in packet:
        _sha(packet["selection_sha256"])
    _identifier(packet["scene_id"])
    _text(packet["edition"], "edition", 256)
    _text(packet["title"], "title", 512)
    _text(packet["observation_id"], "observation_id")
    if "state_context" in packet:
        context = packet["state_context"]
        _fields(context, "provider_id session_id branch_id revision context_token")
        for name in ("provider_id", "session_id", "branch_id"):
            _text(context[name], name, 256)
        _text(context["context_token"], "context_token")
        if type(context["revision"]) is not int or not 0 <= context["revision"] <= 2**63 - 1:
            raise ValueError("State revision must be an integer in 0..2^63-1")
    if "outcome" in packet:
        outcome = packet["outcome"]
        _fields(outcome, "id action_sent complete effects phase evidence_ref")
        for name in ("id", "evidence_ref"):
            _text(outcome[name], "outcome " + name)
        if any(type(outcome[name]) is not bool for name in ("action_sent", "complete")):
            raise ValueError("Outcome action_sent and complete must be boolean")
        if outcome["effects"] not in ("applied-confirmed", "partial", "none-confirmed", "unknown"):
            raise ValueError("Unsupported provider effect status")
        if outcome["phase"] not in ("state", "interface", "persistence", "unspecified"):
            raise ValueError("Unsupported provider outcome phase")
    slots = {}
    facts = _records(packet["facts"], "facts", 32)
    for fact in facts:
        _fields(fact, "id subject predicate value text audience observation_id evidence_ref", "detail entity_id")
        for name in ("subject", "predicate"):
            _text(fact[name], name, 256)
        for name in ("text", "observation_id", "evidence_ref"):
            _text(fact[name], name)
        if "detail" in fact:
            _text(fact["detail"], "detail", empty=True)
        if "entity_id" in fact:
            _text(fact["entity_id"], "entity_id", 256)
        if fact["audience"] not in ("player", "internal"):
            raise ValueError("Fact audience must be player or internal")
        _scalar(fact["value"])
        if fact["observation_id"] == packet["observation_id"]:
            keys = [("subject", fact["subject"], fact["predicate"])]
            if "entity_id" in fact:
                keys.append(("entity", fact["entity_id"], fact["predicate"]))
            value = _encode(fact["value"])
            for slot in keys:
                if slot in slots and slots[slot] != value:
                    raise ValueError("Contradictory current facts for the same subject/predicate or entity/predicate")
                slots[slot] = value
    fact_ids = {fact["id"] for fact in facts}
    for choice in _records(packet["choices"], "choices", 32):
        _fields(choice, "id label requires observation_id available route", "enabled ready suggestion")
        _text(choice["label"], "label", 256)
        _text(choice["observation_id"], "observation_id")
        if type(choice["available"]) is not bool:
            raise ValueError("Choice availability must be boolean")
        for name in ("enabled", "ready"):
            if name in choice and type(choice[name]) not in (bool, type(None)):
                raise ValueError("Choice enabled and ready must be boolean or null (unknown)")
        if choice.get("suggestion", "normal") not in ("prefer", "normal", "on_request"):
            raise ValueError("Choice suggestion must be prefer, normal or on_request")
        required = choice["requires"]
        if not isinstance(required, list) or len(required) > 32:
            raise ValueError("Choice requires must be a list of at most 32 fact identifiers")
        for identity in required:
            _identifier(identity)
        if len(set(required)) != len(required) or not set(required) <= fact_ids:
            raise ValueError("Choice requires duplicate or unknown facts")
        route = choice["route"]
        if not isinstance(route, dict):
            raise ValueError("Choice route must be an object")
        if route.get("kind") == "control":
            _fields(route, "kind revision name")
            _sha(route["revision"])
            _identifier(route["name"])
        elif route.get("kind") == "ordinary":
            _fields(route, "kind reference")
            _text(route["reference"], "route reference")
        else:
            raise ValueError("Choice route must reference a control or ordinary supported input route")
    sources = _records(packet["guide_sources"], "guide_sources", 3)
    for source in sources:
        _fields(source, "id reference edition origin_group", "sha256 locator")
        _text(source["reference"], "source reference")
        for name in ("edition", "origin_group"):
            _text(source[name], name, 256)
        if "sha256" in source:
            _sha(source["sha256"])
        if "locator" in source:
            _text(source["locator"], "locator")
    source_ids = {source["id"] for source in sources}
    for claim in _records(packet["guide_claims"], "guide_claims", 64):
        _fields(claim, "id source_id subject predicate value text condition")
        if _identifier(claim["source_id"]) not in source_ids:
            raise ValueError("Guide claim references an unknown source")
        for name in ("subject", "predicate"):
            _text(claim[name], name, 256)
        _scalar(claim["value"])
        _text(claim["text"], "guide text")
        _text(claim["condition"], "condition", empty=True)
    return json.loads(encoded)


def _digest(packet):
    return hashlib.sha256(_encode(packet).encode()).hexdigest()


def _current(packet):
    return [fact for fact in packet["facts"] if fact["observation_id"] == packet["observation_id"]]


def _offered(packet):
    visible = {fact["id"] for fact in _current(packet) if fact["audience"] == "player"}
    return [choice for choice in packet["choices"] if choice["available"]
            and choice.get("enabled", True) is True and choice.get("ready", True) is True
            and choice["observation_id"] == packet["observation_id"] and set(choice["requires"]) <= visible]


def project_scene(packet, detail="normal", choice_limit=3):
    """Project player-visible claims only; the shortlist never removes choices."""
    packet = validate_scene(packet)
    if detail not in ("brief", "normal", "detailed"):
        raise ValueError("Detail must be brief, normal or detailed")
    if type(choice_limit) is not int or not 1 <= choice_limit <= 32:
        raise ValueError("choice_limit must be an integer in 1..32")
    facts = [{key: fact[key] for key in ("id", "subject", "predicate", "value", "text", "detail") if key in fact}
             for fact in _current(packet) if fact["audience"] == "player"]
    offered = _offered(packet)
    choices = [{key: choice[key] for key in ("id", "label")} for choice in offered]
    candidates = [choice for choice in offered if choice.get("suggestion") != "on_request"]
    candidates.sort(key=lambda choice: choice.get("suggestion") != "prefer")
    suggested = candidates[:choice_limit]
    omitted = len(choices) - len(suggested)
    prompt = "You can choose: " + "; ".join(choice["label"] for choice in suggested) + "." if suggested else ""
    if omitted and suggested:
        prompt += f" {omitted} more {'option is' if omitted == 1 else 'options are'} available."
    elif omitted:
        prompt = "Other actions are available on request."
    parts = [packet["title"]]
    for fact in facts[:1] if detail == "brief" else facts:
        parts.append(fact["text"])
        if detail == "detailed" and fact.get("detail"):
            parts.append(fact["detail"])
    result = {"format": "dotbox-scene-view-1", "scene_sha256": _digest(packet),
            "scene_id": packet["scene_id"], "observation_id": packet["observation_id"],
            "title": packet["title"], "detail": detail, "facts": facts, "choices": choices,
            "suggested_choice_ids": [choice["id"] for choice in suggested], "choice_prompt": prompt,
            "omitted_choices": omitted, "narration": "\n".join(parts), "claim": CLAIM}
    if "state_context" in packet:
        result["state_revision"] = packet["state_context"]["revision"]
    return result


def look_scene(packet, detail="normal"):
    """Describe permitted current facts without selecting or sending a game action."""
    view = project_scene(packet, detail=detail)
    result = {key: view[key] for key in ("scene_sha256", "scene_id", "observation_id", "title",
                                        "detail", "facts", "narration", "claim")}
    result.update(format="dotbox-scene-description-1", execution="not_performed")
    if "state_revision" in view:
        result["state_revision"] = view["state_revision"]
    return result


def _edition_status(first, second):
    if "unknown" in (first.strip().casefold(), second.strip().casefold()):
        return "unverified"
    return "match" if first == second else "mismatch"


def reconstruction_checklist(packet):
    """Internal expectations and disagreements; conditions are never evaluated."""
    packet = validate_scene(packet)
    sources, groups = {source["id"]: source for source in packet["guide_sources"]}, {}

    def group(record):
        key = record["subject"], record["predicate"]
        return groups.setdefault(key, {"subject": key[0], "predicate": key[1],
                                       "current_observations": [], "claims": []})

    for fact in _current(packet):
        group(fact)["current_observations"].append(fact)
    for claim in packet["guide_claims"]:
        target, source = group(claim), sources[claim["source_id"]]
        edition = _edition_status(packet["edition"], source["edition"])
        reasons = (["condition_unchecked"] if claim["condition"] else [])
        if edition != "match":
            reasons.append("edition_" + edition)
        observations = target["current_observations"]
        status = ("pending" if reasons else "unresolved" if not observations else
                  "matched" if _encode(claim["value"]) == _encode(observations[0]["value"]) else "contradicted")
        target["claims"].append({**claim, "edition_status": edition, "status": status, "pending_reasons": reasons})
    for target in groups.values():
        applicable = [claim for claim in target["claims"] if not claim["pending_reasons"]]
        values = {_encode(claim["value"]): claim["value"] for claim in applicable}
        used_sources = {claim["source_id"] for claim in applicable}
        target.update(status="observed" if target["current_observations"] else "unresolved" if applicable else "pending",
                      expected_values=list(values.values()), guide_disagreement=len(values) > 1,
                      source_count=len(used_sources),
                      origin_group_count=len({sources[identity]["origin_group"] for identity in used_sources}))
    return {"format": "dotbox-reconstruction-checklist-1", "scope": "internal_only",
            "scene_sha256": _digest(packet), "source_sha256": packet["source_sha256"],
            "scene_id": packet["scene_id"], "observation_id": packet["observation_id"],
            "guide_sources": packet["guide_sources"], "groups": list(groups.values()), "claim": CLAIM,
            "count_scope": "Applicable same-edition unconditional sources; origin groups are caller reports, never truth votes",
            "condition_scope": "Nonempty condition text is retained unchecked; no condition evaluator"}


def select_choice(packet, choice_id, expected_scene_sha256, expected_observation_id):
    """Bind one offered choice to this exact document; return an intent only."""
    packet = validate_scene(packet)
    _identifier(choice_id)
    _sha(expected_scene_sha256)
    _text(expected_observation_id, "expected_observation_id")
    digest = _digest(packet)
    if digest != expected_scene_sha256 or packet["observation_id"] != expected_observation_id:
        raise ValueError("Stale scene or observation; project the current packet before choosing")
    choice = next((item for item in _offered(packet) if item["id"] == choice_id), None)
    if choice is None:
        raise ValueError("Choice is not currently offered")
    result = {"format": "dotbox-scene-intent-1", "scene_sha256": digest,
              "source_sha256": packet["source_sha256"], "scene_id": packet["scene_id"],
              "observation_id": packet["observation_id"], "choice_id": choice_id, "route": choice["route"],
              "execution": "not_performed", "live_applicability": "unverified", "claim": CLAIM}
    if "selection_sha256" in packet:
        result["selection_sha256"] = packet["selection_sha256"]
    if "state_context" in packet:
        result["state_context"] = packet["state_context"]
    return result


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _read_packet(path):
    from .inspection import _read_file
    raw, _ = _read_file(path, max_bytes=MAX_FILE_BYTES)
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)


def main(argv=None):
    parser = _Parser(prog="dotbox scene", description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True, parser_class=_Parser)
    for name in ("present", "look", "checklist", "choose", "validate", "record", "memory"):
        command = commands.add_parser(name)
        if name == "memory":
            command.add_argument("--store", required=True)
            command.add_argument("--subject")
            command.add_argument("--limit", type=int, default=128)
        elif name in ("present", "look", "choose"):
            command.add_argument("file", nargs="?")
            command.add_argument("--store")
        else:
            command.add_argument("file")
        if name == "record":
            command.add_argument("--store", required=True)
        if name in ("present", "look"):
            command.add_argument("--detail", choices=("brief", "normal", "detailed"), default="normal")
        if name == "present":
            command.add_argument("--choice-limit", type=int, default=3)
        elif name == "choose":
            command.add_argument("--choice", required=True)
            command.add_argument("--scene-sha256", required=True)
            command.add_argument("--observation-id", required=True)
    try:
        args = parser.parse_args(argv)
        if getattr(args, "store", None) is not None:
            _text(args.store, "store path", 4096)
        if args.operation in ("present", "look", "choose") and bool(args.file) == bool(args.store):
            raise ValueError("Provide exactly one scene file or --store")
        if getattr(args, "store", None):
            from .scene_state import SceneStore
            with SceneStore(args.store, create=args.operation == "record") as state:
                if args.operation == "record":
                    result = state.record(_read_packet(args.file))
                elif args.operation == "memory":
                    result = state.memory(subject=args.subject, limit=args.limit)
                elif args.operation == "present":
                    result = state.present(args.detail, args.choice_limit)
                elif args.operation == "look":
                    result = state.look(args.detail)
                else:
                    result = state.choose(args.choice, args.scene_sha256, args.observation_id)
        elif args.operation == "present":
            packet = _read_packet(args.file)
            result = project_scene(packet, args.detail, args.choice_limit)
        elif args.operation == "look":
            result = look_scene(_read_packet(args.file), args.detail)
        elif args.operation == "checklist":
            result = reconstruction_checklist(_read_packet(args.file))
        elif args.operation == "choose":
            result = select_choice(_read_packet(args.file), args.choice, args.scene_sha256, args.observation_id)
        else:
            packet = validate_scene(_read_packet(args.file))
            result = {"valid": True, "scene_sha256": _digest(packet), "observation_id": packet["observation_id"], "claim": CLAIM}
        print(json.dumps({"ok": True, "result": result}, allow_nan=False))
        return 0
    except (ValueError, OSError, TypeError, RecursionError, sqlite3.Error) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
