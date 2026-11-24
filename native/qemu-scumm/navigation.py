"""Source-bound SCUMM v2 room inspection and movement proposals.

This independently authored host layer reads the v2 room format and follows
its stored routing table. It does not run a CPU, mutate a scene, or provide a
fallback pathfinder. See NAVIGATION.md for the pinned behavioral references,
integer geometry rules, explicit caller assumptions and qualification limits.

SPDX-License-Identifier: GPL-2.0-or-later
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import re


GEOMETRY_SCHEMA = "fdisbull-scumm-v2-room-navigation-1"
PLAN_SCHEMA = "fdisbull-scumm-v2-movement-plan-1"
CHECK_SCHEMA = "fdisbull-scumm-v2-movement-check-1"
PACKET_SCHEMA = "fdisbull-scumm-processor-scene-packet-1"
RESOURCE_TYPES = ("costume", "room", "script", "sound")
U64_MAX = (1 << 64) - 1
COORDINATES = {"space": "scumm-v2-actor", "x_pixel_multiplier": 8, "y_pixel_multiplier": 2}


class NavigationInputError(ValueError):
    """A source, capture, request or room structure cannot be admitted."""


def _need(condition, message):
    if not condition:
        raise NavigationInputError(message)


def _object(value, required, name):
    _need(type(value) is dict and set(required) <= value.keys(),
          f"{name} requires an object with {', '.join(required)}")
    return value


def _integer(value, minimum, maximum, name):
    _need(type(value) is int and minimum <= value <= maximum,
          f"{name} must be an integer in {minimum}..{maximum}")
    return value


def _hash(value, name):
    _need(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
          f"{name} requires a lowercase SHA-256")


def _json_bytes(value):
    try:
        result = json.dumps(value, sort_keys=True, separators=(",", ":"),
                            allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError) as error:
        raise NavigationInputError("Inputs must contain finite ordinary JSON values") from error
    _need(len(result) <= 32 * 1024 * 1024, "JSON input exceeds the 32 MiB bound")
    return result


def _digest(value):
    return sha256(_json_bytes(value)).hexdigest()


def _source(source):
    _object(source, ("version", "code_sha256", "code_size", "profile", "manifest_sha256",
                     "source_receipt_sha256", "script_id"), "source")
    _integer(source["version"], 2, 2, "source.version")
    _need(source["profile"] == "amiga-v2-isolated", "Navigation requires the explicit isolated v2 resource profile")
    _integer(source["code_size"], 1, 65536, "source.code_size")
    _integer(source["script_id"], 1, 255, "source.script_id")
    for field in ("code_sha256", "manifest_sha256", "source_receipt_sha256"):
        _hash(source[field], "source." + field)
    _json_bytes(source)


def _point(value, name):
    _need(type(value) in (list, tuple) and len(value) == 2, f"{name} requires two actor-coordinate integers")
    return [_integer(component, -32768, 32767, name + " coordinate") for component in value]


def _u16(data, offset):
    return data[offset] | data[offset + 1] << 8


def inspect_room(room_bytes, *, room_id, source):
    """Return bounded initial geometry from a whole decoded v2 room resource.

    ``source`` is the recorded processor source identity. This standalone
    inspection computes the supplied room's identity; resource-bank admission
    is checked separately by ``plan_movement`` against the complete packet.
    Neither inspection nor plan creation makes the room current or resident.
    """
    _source(source)
    _integer(room_id, 1, 255, "room_id")
    _need(type(room_bytes) is bytes and 28 <= len(room_bytes) <= 65535,
          "Room must be immutable whole decoded bytes with a complete v2 header")
    _need(_u16(room_bytes, 0) == len(room_bytes), "Room length header differs from the supplied span")
    table_offset = room_bytes[0x15]
    _need(28 <= table_offset < len(room_bytes), "Box table offset overlaps the fixed header or leaves the room")
    count = room_bytes[table_offset]
    table_size = 1 + 8 * count
    matrix_offset = table_offset + table_size
    matrix_size = count * (count + 1)
    _need(matrix_offset + matrix_size <= len(room_bytes), "Box table or routing matrix exceeds the room span")

    boxes = []
    field_names = ("uy", "ly", "ulx", "urx", "llx", "lrx", "mask", "flags")
    for index in range(count):
        offset = table_offset + 1 + 8 * index
        box = {"id": index, **dict(zip(field_names, room_bytes[offset:offset + 8]))}
        _need(box["uy"] <= box["ly"], f"Box {index} has inverted vertical bounds")
        _need(box["ulx"] <= box["urx"] and box["llx"] <= box["lrx"],
              f"Box {index} has inverted horizontal bounds")
        box["corners"] = [[box["ulx"], box["uy"]], [box["urx"], box["uy"]],
                          [box["lrx"], box["ly"]], [box["llx"], box["ly"]]]
        boxes.append(box)

    matrix = room_bytes[matrix_offset:matrix_offset + matrix_size]
    # The shared native matrix-address helper recognizes a leading marker.
    # Retain that rule, but never read beyond the v2 room-declared matrix span.
    prefix_size = int(bool(matrix) and matrix[0] == 0xff)
    _need(prefix_size + count <= len(matrix), "Routing matrix lacks its row-offset directory")
    row_offsets = list(matrix[prefix_size:prefix_size + count])
    next_hops = []
    for index, relative in enumerate(row_offsets):
        row_start = prefix_size + count + relative
        _need(row_start + count <= len(matrix), f"Routing row {index} exceeds the matrix span")
        row = [value if value < 128 else value - 256 for value in matrix[row_start:row_start + count]]
        _need(all(value < count for value in row), f"Routing row {index} names an undeclared box")
        next_hops.append(row)

    return deepcopy({
        "schema": GEOMETRY_SCHEMA, "source": source,
        "room": {"id": room_id, "size": len(room_bytes), "sha256": sha256(room_bytes).hexdigest()},
        "coordinates": COORDINATES,
        "dimensions": {"width_pixels": _u16(room_bytes, 4), "height_pixels": _u16(room_bytes, 6)},
        "box_table": {"offset": table_offset, "size": table_size, "count": count},
        "boxes": boxes,
        "matrix": {"offset": matrix_offset, "size": matrix_size, "prefix_size": prefix_size,
                   "row_offsets": row_offsets, "next_hops": next_hops},
        "flags_origin": "initial_room_bytes",
        "qualification": {"resource_bank_admission_checked": False, "current_room_established": False,
                          "live_box_flags_established": False, "native_execution_performed": False},
    })


def _packet_binding(packet, geometry, actor_id, requested_start):
    _object(packet, ("schema", "source", "checkpoint", "observation", "actors", "resources", "control",
                     "evidence", "qualification"), "scene packet")
    _need(packet["schema"] == PACKET_SCHEMA, "Unsupported scene packet schema")
    _source(packet["source"])
    _need(packet["source"] == geometry["source"], "Packet and geometry source identities differ")
    qualification = _object(packet["qualification"], ("current_snapshot",), "packet qualification")
    _need(qualification["current_snapshot"] is True, "Packet does not qualify its recorded model snapshot")
    evidence = _object(packet["evidence"], ("code_sha256", "scene_sha256"), "packet evidence")
    _hash(evidence["code_sha256"], "evidence.code_sha256")
    _hash(evidence["scene_sha256"], "evidence.scene_sha256")
    _need(evidence["code_sha256"] == packet["source"]["code_sha256"], "Packet code evidence contradicts its source")
    snapshot = {"schema": "fdisbull-scumm-scene-1"}
    snapshot.update({key: packet[key] for key in
                     ("source", "checkpoint", "observation", "actors", "resources", "control")})
    if "verbs" in packet:
        snapshot["verbs"] = packet["verbs"]
    _need(_digest(snapshot) == evidence["scene_sha256"], "Snapshot facts contradict the packet capture evidence")
    checkpoint = _object(packet["checkpoint"], ("trace_epoch", "control_generation", "retired", "pc",
                                                "status", "fault", "fault_opcode", "blocked_reason"),
                         "scene checkpoint")
    for key in ("trace_epoch", "control_generation", "retired"):
        _integer(checkpoint[key], 0, U64_MAX, "checkpoint." + key)
    _integer(checkpoint["pc"], 0, packet["source"]["code_size"], "checkpoint.pc")
    _integer(checkpoint["status"], 0, 6, "checkpoint.status")
    for key in ("fault", "fault_opcode"):
        _integer(checkpoint[key], 0, 255, "checkpoint." + key)
    _need(type(checkpoint["blocked_reason"]) is str and len(checkpoint["blocked_reason"]) <= 128,
          "Checkpoint block reason must be a bounded string")

    actors = packet["actors"]
    _need(type(actors) is list and len(actors) == 32, "Packet must contain its complete actor inventory")
    actors_by_id = {}
    for actor in actors:
        _object(actor, ("id", "bound", "x", "y", "room"), "packet actor")
        index = _integer(actor["id"], 0, 31, "packet actor.id")
        _need(index not in actors_by_id, "Packet has duplicate actor IDs")
        _integer(actor["bound"], 0, 1, "packet actor.bound")
        for coordinate in ("x", "y"):
            _integer(actor[coordinate], 0, 65535, "packet actor." + coordinate)
        _integer(actor["room"], 0, 255, "packet actor.room")
        actors_by_id[index] = actor
    actor = actors_by_id[actor_id]
    control = _object(packet["control"], ("current_room",), "packet control")
    _integer(control["current_room"], 0, 255, "packet control.current_room")

    resources = _object(packet["resources"], ("counts", "entries"), "packet resources")
    counts = _object(resources["counts"], RESOURCE_TYPES, "packet resource counts")
    for resource_type in RESOURCE_TYPES:
        _integer(counts[resource_type], 0, 256, "packet resource count")
    entries = resources["entries"]
    _need(type(entries) is list and len(entries) <= 1024, "Packet resource entries must be bounded")
    resources_by_slot = {}
    for entry in entries:
        _object(entry, ("type", "id", "size", "available", "resident", "locked", "sha256"), "packet resource")
        _need(entry["type"] in RESOURCE_TYPES, "Packet resource has an unknown type")
        index = _integer(entry["id"], 0, 255, "packet resource.id")
        _need(index < counts[entry["type"]], "Packet resource exceeds its declared count")
        slot = entry["type"], index
        _need(slot not in resources_by_slot, "Packet has duplicate resource slots")
        for flag in ("available", "resident", "locked"):
            _need(type(entry[flag]) is bool, "Resource flags must be JSON booleans")
        _integer(entry["size"], 0, 65535, "packet resource.size")
        if entry["available"]:
            _need(entry["size"] >= 4, "Available resource lacks its length/header extent")
            _hash(entry["sha256"], "packet resource.sha256")
        else:
            _need(entry["size"] == 0 and entry["sha256"] == "" and not entry["resident"],
                  "Unavailable resource claims resident bytes or a byte identity")
        resources_by_slot[slot] = entry
    room = geometry["room"]
    entry = resources_by_slot.get(("room", room["id"]))
    _need(entry is not None and entry["available"], "Requested room bytes are not available in this packet's bank")
    _need(entry["size"] == room["size"] and entry["sha256"] == room["sha256"],
          "Room bytes differ from the source-bound packet resource")

    return {
        "packet_sha256": _digest(packet), "checkpoint": deepcopy(checkpoint),
        "actor": {key: actor[key] for key in ("id", "bound", "x", "y", "room")},
        "room_resource": deepcopy(entry),
        "start_matches_recorded_position": [actor["x"], actor["y"]] == requested_start,
        "recorded_room_matches_requested": actor["room"] == room["id"],
        "recorded_current_room": control["current_room"],
    }


def _restriction_inputs(flags, player_ids, actor_id, boxes):
    _need(type(player_ids) in (list, tuple) and len(player_ids) <= 31,
          "player_ids must explicitly list at most 31 actor IDs")
    players = [_integer(value, 1, 31, "player ID") for value in player_ids]
    _need(len(set(players)) == len(players), "player_ids contains duplicates")
    players.sort()
    _object(flags, ("policy",), "flags policy")
    if flags["policy"] == "room_initial":
        _need(set(flags) == {"policy"}, "room_initial flags policy has unexpected fields")
        effective = [box["flags"] for box in boxes]
    elif flags["policy"] == "override":
        _need(set(flags) == {"policy", "values"}, "override flags policy requires only policy and values")
        values = flags["values"]
        _need(type(values) is list and len(values) == len(boxes), "Override flags must cover every declared box")
        effective = [_integer(value, 0, 255, "override box flag") for value in values]
    else:
        raise NavigationInputError("Explicit flags policy must be room_initial or override")
    return {"actor_id": actor_id, "player_ids": players, "is_player": actor_id in players,
            "flags_policy": flags["policy"], "flags": effective,
            "origin": "caller_declared", "live_flags_verified": False, "live_player_classification_verified": False}


def _restricted(flags, bit, is_player):
    return bool(flags & bit) and not (flags & 0x20 and not is_player)


def _box_adjustment(box, point):
    """Clamp an actor anchor using v2's integer horizontal-slice rule."""
    x, y = point
    top, bottom = box["uy"], box["ly"]
    if y < top:
        row, left, right = top, box["ulx"], box["urx"]
    elif y >= bottom:
        row, left, right = bottom, box["llx"], box["lrx"]
    else:
        row = y
        upper = [top, box["ulx"], box["urx"]]
        lower = [bottom, box["llx"], box["lrx"]]
        # All six endpoints are bytes, so subdivision reaches any interior
        # integer row in at most eight iterations. Preserve midpoint rounding.
        for _ in range(9):
            middle = [(a + b) // 2 for a, b in zip(upper, lower)]
            if middle[0] == y:
                left, right = middle[1:]
                break
            if middle[0] < y:
                upper = middle
            else:
                lower = middle
        else:
            raise NavigationInputError("Box subdivision failed its byte-coordinate bound")
    adjusted = [max(left, min(right, x)), row]
    horizontal = abs(x - adjusted[0])
    vertical = abs(y - adjusted[1]) // 4
    distance = max(horizontal, vertical) + min(horizontal, vertical) // 2
    return adjusted, distance


def _adjust_endpoint(point, boxes, restrictions):
    result = {"requested": point[:], "point": point[:], "box": None, "distance": None}
    best_distance = 255
    for box in reversed(boxes):
        if _restricted(restrictions["flags"][box["id"]], 0x80, restrictions["is_player"]):
            continue
        adjusted, distance = _box_adjustment(box, point)
        if distance < best_distance:
            result.update(point=adjusted, box=box["id"], distance=distance)
            best_distance = distance
        if distance == 0:
            break
    return result


def _trunc_div(numerator, denominator):
    _need(denominator != 0, "Degenerate projection denominator")
    magnitude = abs(numerator) // abs(denominator)
    return -magnitude if (numerator < 0) != (denominator < 0) else magnitude


def _edge_projection(start, end, point):
    """Integer projection expressed once in dominant-axis coordinates.

    Preserve truncation towards zero at each scalar division, then clamp to
    the segment. This is a geometric calculation, not a native motion tick.
    """
    delta = [end[index] - start[index] for index in (0, 1)]
    if delta == [0, 0]:
        return start[:]
    if 0 in delta:
        varying = 0 if delta[0] else 1
        result = start[:]
        result[varying] = max(min(start[varying], end[varying]),
                              min(max(start[varying], end[varying]), point[varying]))
        return result
    major = int(abs(delta[1]) >= abs(delta[0]))
    minor = 1 - major
    long_delta, short_delta = delta[major], delta[minor]
    origin_term = _trunc_div(start[major] * short_delta, long_delta)
    point_term = _trunc_div(point[major] * long_delta, short_delta)
    projected_major = _trunc_div((origin_term + point_term - start[minor] + point[minor])
                                * short_delta * long_delta, sum(value * value for value in delta))
    if projected_major < min(start[major], end[major]):
        return (start if start[major] < end[major] else end)[:]
    if projected_major > max(start[major], end[major]):
        return (start if start[major] > end[major] else end)[:]
    result = [0, 0]
    result[major] = projected_major
    result[minor] = _trunc_div(projected_major * short_delta, long_delta) - origin_term + start[minor]
    return result


def _nearest_boundary(box, point):
    corners = box["corners"]
    candidates = [_edge_projection(corners[index], corners[(index + 1) % 4], point) for index in range(4)]
    # min preserves the first candidate in a tie: top, right, bottom, left.
    return min(candidates, key=lambda candidate: sum((a - b) ** 2 for a, b in zip(candidate, point)))


def plan_movement(packet, room_bytes, *, room_id, start, goal, actor_id, player_ids, flags, max_hops=255):
    """Create a bounded candidate using exact room bytes and explicit policy.

    Both endpoints undergo deterministic v2 box adjustment. In particular,
    the start box is a host proposal, not a recovered native walkbox field.
    The stored next-hop matrix is authoritative for this selected policy;
    unavailable/locked/cyclic routes never trigger an alternative path search.
    """
    _object(packet, ("source",), "scene packet")
    actor_id = _integer(actor_id, 1, 31, "actor_id")
    max_hops = _integer(max_hops, 0, 255, "max_hops")
    start, goal = _point(start, "start"), _point(goal, "goal")
    geometry = inspect_room(room_bytes, room_id=room_id, source=packet["source"])
    scene_binding = _packet_binding(packet, geometry, actor_id, start)
    boxes = geometry["boxes"]
    restrictions = _restriction_inputs(flags, player_ids, actor_id, boxes)
    adjusted_start = _adjust_endpoint(start, boxes, restrictions)
    adjusted_goal = _adjust_endpoint(goal, boxes, restrictions)
    proposal = {
        "schema": PLAN_SCHEMA, "source": deepcopy(geometry["source"]), "room": deepcopy(geometry["room"]),
        "coordinates": deepcopy(COORDINATES), "geometry_sha256": _digest(geometry), "scene_binding": scene_binding,
        "request": {"room_id": room_id, "start": start, "goal": goal, "actor_id": actor_id,
                    "player_ids": restrictions["player_ids"][:], "flags": deepcopy(flags), "max_hops": max_hops},
        "restrictions": restrictions, "adjustment": {"start": adjusted_start, "goal": adjusted_goal},
        "status": "planned", "reason": "adjusted_goal_reached", "box_path": [], "waypoints": [],
        "legs": [], "blocked_next_box": None, "hops": 0,
        "execution": "not_performed", "live_applicability": "unverified",
        "qualification": {"candidate_only": True, "room_resource_binding_verified": True,
                          "start_box_origin": "host_endpoint_adjustment", "current_room_established": False,
                          "native_actor_initialized": False, "live_box_flags_established": False,
                          "native_timing_established": False, "continuous_walkable_path_verified": False,
                          "actor_collision_avoidance_verified": False, "original_engine_equivalence": False,
                          "native_execution_performed": False, "screen_presentation": False},
    }
    if not boxes:
        proposal.update(status="no_walkboxes", reason="room_has_no_walkboxes")
        return proposal
    if adjusted_start["box"] is None or adjusted_goal["box"] is None:
        which = "start" if adjusted_start["box"] is None else "goal"
        proposal.update(status="no_eligible_box", reason=which + "_has_no_eligible_box")
        return proposal

    current = adjusted_start["box"]
    destination = adjusted_goal["box"]
    point = adjusted_start["point"][:]
    proposal["box_path"].append(current)
    proposal["waypoints"].append(point[:])
    visited = {current}

    def append_waypoint(value):
        if proposal["waypoints"][-1] != value:
            proposal["waypoints"].append(value[:])

    while current != destination:
        if proposal["hops"] == max_hops:
            proposal.update(status="budget_exhausted", reason="hop_budget_exhausted")
            break
        next_box = geometry["matrix"]["next_hops"][current][destination]
        if next_box < 0:
            proposal.update(status="no_route", reason="room_matrix_has_no_next_box")
            break
        locked = _restricted(restrictions["flags"][next_box], 0x40, restrictions["is_player"])
        if not locked and next_box in visited:
            proposal.update(status="routing_cycle", reason="room_matrix_repeats_a_box")
            break
        next_boundary = _nearest_boundary(boxes[next_box], point)
        boundary = _nearest_boundary(boxes[current], next_boundary)
        proposal["legs"].append({"from_box": current, "next_box": next_box,
                                  "next_box_projection": next_boundary[:], "boundary": boundary[:], "locked": locked})
        append_waypoint(boundary)
        if locked:
            proposal.update(status="locked", reason="next_box_is_locked_for_actor", blocked_next_box=next_box)
            break
        current, point = next_box, boundary
        visited.add(current)
        proposal["box_path"].append(current)
        proposal["hops"] += 1
    else:
        append_waypoint(adjusted_goal["point"])
    return deepcopy(proposal)


def check_movement_plan(packet, room_bytes, proposal, *, room_id, start, goal, actor_id,
                        player_ids, flags, max_hops=255):
    """Recompute from the exact sources and request; never trust cached geometry.

    A mismatch returns ``valid=False``. Malformed source/request inputs raise
    ``NavigationInputError``. A valid match still authorizes no execution.
    """
    expected = plan_movement(packet, room_bytes, room_id=room_id, start=start, goal=goal,
                             actor_id=actor_id, player_ids=player_ids, flags=flags, max_hops=max_hops)
    try:
        supplied = _json_bytes(proposal)
    except NavigationInputError:
        supplied = None
    matches = supplied == _json_bytes(expected)
    return {"schema": CHECK_SCHEMA, "valid": matches, "reason": "match" if matches else "proposal_mismatch",
            "expected_status": expected["status"], "expected_plan_sha256": _digest(expected),
            "supplied_plan_sha256": None if supplied is None else sha256(supplied).hexdigest(),
            "execution": "not_performed", "live_applicability": "unverified"}
