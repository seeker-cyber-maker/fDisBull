"""Z: a source-addressable world language for Zork-like maps.

A Z document is a small S-expression graph, not a Z-machine program.  It records
the initial room/exit/object structure with explicit blocked, conditional and
routine-computed exits.  The compiler emits a JSON graph, a text index and an
optional Graphviz SVG.  Dynamic state, parser semantics and story prose are out
of scope unless ``desc``/message fields are explicitly retained.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PSEUDO_LOCATIONS = {"LOCAL-GLOBALS", "GLOBAL-OBJECTS"}


class ZError(ValueError):
    """A Z document or operation is malformed."""


@dataclass(frozen=True)
class Exit:
    direction: str
    kind: str  # passage | conditional | blocked | routine | unknown
    target: str | None = None
    condition: tuple[str, ...] = ()
    else_blocked: bool = False
    message: str | None = None
    routine: str | None = None


@dataclass
class Room:
    id: str
    flags: tuple[str, ...] = ()
    exits: list[Exit] = field(default_factory=list)
    desc: str | None = None

    def exit(self, direction: str) -> Exit | None:
        for candidate in self.exits:
            if candidate.direction == direction:
                return candidate
        return None


@dataclass
class ZObject:
    id: str
    location: str | None = None
    flags: tuple[str, ...] = ()
    desc: str | None = None
    synonyms: tuple[str, ...] = ()
    adjectives: tuple[str, ...] = ()


@dataclass
class ZWorld:
    name: str
    source_url: str
    source_commit: str
    license: str
    entry: str
    directions: tuple[str, ...]
    rooms: dict[str, Room] = field(default_factory=dict)
    objects: dict[str, ZObject] = field(default_factory=dict)
    source_files: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Reader


def _tokenize(text: str) -> list[object]:
    tokens: list[object] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char == ";":
            newline = text.find("\n", index)
            index = len(text) if newline < 0 else newline + 1
            continue
        if char in "()":
            tokens.append(char)
            index += 1
            continue
        if char == '"':
            index += 1
            value: list[str] = []
            while index < len(text):
                char = text[index]
                if char == "\\" and index + 1 < len(text):
                    value.append(text[index + 1])
                    index += 2
                    continue
                if char == '"':
                    index += 1
                    break
                value.append(char)
                index += 1
            else:
                raise ZError("unterminated Z string")
            tokens.append(_ZString("".join(value)))
            continue
        end = index
        while end < len(text) and not text[end].isspace() and text[end] not in '();"':
            end += 1
        if end == index:
            raise ZError(f"unexpected Z character {text[index]!r}")
        tokens.append(text[index:end])
        index = end
    return tokens


class _ZString(str):
    """A quoted Z string, kept distinct from an atom."""


def _parse_forms(text: str) -> list[object]:
    tokens = _tokenize(text)
    stack: list[list[object]] = []
    root: list[object] = []
    for token in tokens:
        if token == "(":
            node: list[object] = []
            if stack:
                stack[-1].append(node)
            else:
                root.append(node)
            stack.append(node)
        elif token == ")":
            if not stack:
                raise ZError("unmatched closing delimiter")
            stack.pop()
        else:
            if not stack:
                if isinstance(token, str):
                    raise ZError(f"atom outside a form: {token!r}")
                continue
            stack[-1].append(token)
    if stack:
        raise ZError("unterminated Z form")
    return root


def _atom(value: object, what: str = "atom") -> str:
    if not isinstance(value, str) or isinstance(value, _ZString):
        raise ZError(f"expected {what}, got {value!r}")
    return value


def _string(value: object, what: str = "string") -> str:
    if not isinstance(value, _ZString):
        raise ZError(f"expected {what}, got {value!r}")
    return str(value)


def _string_or_atom(value: object) -> str:
    if not isinstance(value, str):
        raise ZError(f"expected text, got {value!r}")
    return str(value)


def parse_z(text: str) -> ZWorld:
    forms = _parse_forms(text)
    if len(forms) != 1:
        raise ZError(f"expected one top-level form, found {len(forms)}")
    root = forms[0]
    if not isinstance(root, list) or not root or _atom(root[0]) != "z-world":
        raise ZError("root form must be (z-world ...)")
    if len(root) < 2:
        raise ZError("z-world requires a name")
    world = ZWorld(
        name=_string_or_atom(root[1]),
        source_url="",
        source_commit="",
        license="",
        entry="",
        directions=(),
    )
    for item in root[2:]:
        if not isinstance(item, list) or not item:
            raise ZError(f"invalid z-world member {item!r}")
        key = _atom(item[0])
        if key == "source":
            if len(item) != 4:
                raise ZError("(source URL COMMIT LICENSE) requires three values")
            world.source_url = _string_or_atom(item[1])
            world.source_commit = _string_or_atom(item[2])
            world.license = _string_or_atom(item[3])
        elif key == "source-file":
            if len(item) != 3:
                raise ZError("(source-file PATH SHA256) requires two values")
            world.source_files[_string_or_atom(item[1])] = _string(item[2])
        elif key == "entry":
            if len(item) != 2:
                raise ZError("(entry ROOM) requires one value")
            world.entry = _atom(item[1], "room id")
        elif key == "directions":
            world.directions = tuple(_atom(value, "direction") for value in item[1:])
        elif key == "room":
            room = _parse_room(item)
            if room.id in world.rooms:
                raise ZError(f"duplicate room {room.id}")
            world.rooms[room.id] = room
        elif key == "object":
            obj = _parse_object(item)
            if obj.id in world.objects:
                raise ZError(f"duplicate object {obj.id}")
            world.objects[obj.id] = obj
        else:
            raise ZError(f"unknown z-world member {key}")
    return world


def _parse_room(form: list[object]) -> Room:
    if len(form) < 2:
        raise ZError("(room ID ...) requires an id")
    room = Room(id=_atom(form[1], "room id"))
    for item in form[2:]:
        if not isinstance(item, list) or not item:
            raise ZError(f"invalid room member {item!r}")
        key = _atom(item[0])
        if key == "desc":
            room.desc = _string(item[1], "room description") if len(item) > 1 else ""
        elif key == "flags":
            room.flags = tuple(sorted(_atom(value, "flag") for value in item[1:]))
        else:
            room.exits.append(_parse_exit(key, item[1:]))
    return room


def _parse_exit(direction: str, args: list[object]) -> Exit:
    if len(args) == 1 and isinstance(args[0], list):
        args = args[0]
    if not args:
        return Exit(direction=direction, kind="unknown")
    head = args[0]
    if head == "to":
        if len(args) < 2:
            raise ZError(f"{direction}: (to TARGET ...) requires a target")
        target = _atom(args[1], "target room")
        condition: tuple[str, ...] = ()
        else_blocked = False
        for arg in args[2:]:
            if not isinstance(arg, list) or not arg:
                raise ZError(f"{direction}: invalid to-clause {arg!r}")
            if _atom(arg[0]) == "if":
                condition = tuple(_atom(value, "condition token") for value in arg[1:])
            elif _atom(arg[0]) == "else":
                if len(arg) != 2:
                    raise ZError(f"{direction}: (else ...) requires one clause")
                value = arg[1]
                if isinstance(value, list) and value and _atom(value[0]) == "blocked":
                    else_blocked = True
                else:
                    raise ZError(f"{direction}: only (else (blocked)) is supported")
            else:
                raise ZError(f"{direction}: unknown to-clause {arg!r}")
        return Exit(
            direction=direction,
            kind="conditional" if condition else "passage",
            target=target,
            condition=condition,
            else_blocked=else_blocked,
        )
    if head == "blocked":
        message = _string(args[1], "blocked message") if len(args) > 1 else None
        return Exit(direction=direction, kind="blocked", message=message)
    if head == "per":
        if len(args) != 2:
            raise ZError(f"{direction}: (per ROUTINE) requires one routine")
        return Exit(
            direction=direction, kind="routine", routine=_atom(args[1], "routine")
        )
    if head == "unknown":
        return Exit(direction=direction, kind="unknown")
    raise ZError(f"{direction}: unknown exit kind {head!r}")


def _parse_object(form: list[object]) -> ZObject:
    if len(form) < 2:
        raise ZError("(object ID ...) requires an id")
    obj = ZObject(id=_atom(form[1], "object id"))
    for item in form[2:]:
        if not isinstance(item, list) or not item:
            raise ZError(f"invalid object member {item!r}")
        key = _atom(item[0])
        if key == "in":
            obj.location = _atom(item[1], "location") if len(item) > 1 else None
        elif key == "flags":
            obj.flags = tuple(sorted(_atom(value, "flag") for value in item[1:]))
        elif key == "desc":
            obj.desc = _string(item[1], "object description") if len(item) > 1 else ""
        elif key == "synonym":
            obj.synonyms = tuple(sorted(_atom(value, "synonym") for value in item[1:]))
        elif key == "adjective":
            obj.adjectives = tuple(
                sorted(_atom(value, "adjective") for value in item[1:])
            )
        else:
            raise ZError(f"unknown object member {key}")
    return obj


# ---------------------------------------------------------------------------
# Writer


def _q(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _exit_z(exit_: Exit) -> str:
    if exit_.kind == "passage":
        return f"(to {exit_.target})"
    if exit_.kind == "conditional":
        parts = [f"(to {exit_.target}", f"(if {' '.join(exit_.condition)})"]
        if exit_.else_blocked:
            parts.append("(else (blocked))")
        return " ".join(parts) + ")"
    if exit_.kind == "blocked":
        return (
            "(blocked)" if exit_.message is None else f"(blocked {_q(exit_.message)})"
        )
    if exit_.kind == "routine":
        return f"(per {exit_.routine})"
    return "(unknown)"


def world_to_z(world: ZWorld) -> str:
    lines = [f"(z-world {_q(world.name)}"]
    lines.append(
        f"  (source {_q(world.source_url)} {_q(world.source_commit)} {_q(world.license)})"
    )
    for path, digest in sorted(world.source_files.items()):
        lines.append(f"  (source-file {_q(path)} {_q(digest)})")
    lines.append(f"  (entry {world.entry})")
    lines.append("  (directions " + " ".join(world.directions) + ")")
    order = {name: index for index, name in enumerate(world.directions)}
    for room_id in sorted(world.rooms):
        room = world.rooms[room_id]
        lines.append(f"  (room {room.id}")
        if room.desc is not None:
            lines.append(f"    (desc {_q(room.desc)})")
        if room.flags:
            lines.append("    (flags " + " ".join(room.flags) + ")")
        exits = sorted(
            room.exits,
            key=lambda exit_: (order.get(exit_.direction, len(order)), exit_.direction),
        )
        for exit_ in exits:
            lines.append(f"    ({exit_.direction} {_exit_z(exit_)})")
        lines.append("  )")
    for obj_id in sorted(world.objects):
        obj = world.objects[obj_id]
        lines.append(f"  (object {obj.id}")
        if obj.location is not None:
            lines.append(f"    (in {obj.location})")
        if obj.desc is not None:
            lines.append(f"    (desc {_q(obj.desc)})")
        if obj.flags:
            lines.append("    (flags " + " ".join(obj.flags) + ")")
        if obj.synonyms:
            lines.append("    (synonym " + " ".join(obj.synonyms) + ")")
        if obj.adjectives:
            lines.append("    (adjective " + " ".join(obj.adjectives) + ")")
        lines.append("  )")
    lines.append(")")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Validation and graph


def _edge_targets(world: ZWorld) -> Iterable[tuple[str, Exit]]:
    for room_id in sorted(world.rooms):
        for exit_ in world.rooms[room_id].exits:
            yield room_id, exit_


def _reachable(world: ZWorld) -> dict[str, int]:
    if world.entry not in world.rooms:
        return {}
    depths = {world.entry: 0}
    queue = [world.entry]
    while queue:
        room_id = queue.pop(0)
        for exit_ in world.rooms[room_id].exits:
            if (
                exit_.target
                and exit_.target in world.rooms
                and exit_.target not in depths
            ):
                depths[exit_.target] = depths[room_id] + 1
                queue.append(exit_.target)
    return depths


def validate(world: ZWorld) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    directions = set(world.directions)
    if not world.entry:
        problems.append(
            {
                "severity": "error",
                "code": "missing-entry",
                "subject": "",
                "message": "no entry room",
            }
        )
    elif world.entry not in world.rooms:
        problems.append(
            {
                "severity": "error",
                "code": "unknown-entry",
                "subject": world.entry,
                "message": "entry is not a room",
            }
        )
    for room_id, room in world.rooms.items():
        duplicates = [
            direction
            for direction, count in Counter(
                exit_.direction for exit_ in room.exits
            ).items()
            if count > 1
        ]
        for direction in duplicates:
            problems.append(
                {
                    "severity": "error",
                    "code": "duplicate-direction",
                    "subject": room_id,
                    "message": f"duplicate {direction} exit",
                }
            )
    for room_id, exit_ in _edge_targets(world):
        if exit_.direction not in directions:
            problems.append(
                {
                    "severity": "error",
                    "code": "unknown-direction",
                    "subject": room_id,
                    "message": f"unknown direction {exit_.direction}",
                }
            )
        if exit_.kind in {"passage", "conditional"}:
            if not exit_.target:
                problems.append(
                    {
                        "severity": "error",
                        "code": "missing-target",
                        "subject": room_id,
                        "message": f"{exit_.direction} has no target",
                    }
                )
            elif exit_.target not in world.rooms:
                problems.append(
                    {
                        "severity": "error",
                        "code": "unknown-target",
                        "subject": room_id,
                        "message": f"{exit_.direction} -> {exit_.target} is not a room",
                    }
                )
            if exit_.kind == "conditional" and not exit_.condition:
                problems.append(
                    {
                        "severity": "error",
                        "code": "missing-condition",
                        "subject": room_id,
                        "message": f"{exit_.direction} is conditional but has no condition",
                    }
                )
        if exit_.kind == "routine" and not exit_.routine:
            problems.append(
                {
                    "severity": "error",
                    "code": "missing-routine",
                    "subject": room_id,
                    "message": f"{exit_.direction} has no routine",
                }
            )
    for obj in world.objects.values():
        if obj.location is None:
            continue
        if (
            obj.location not in world.rooms
            and obj.location not in world.objects
            and obj.location not in PSEUDO_LOCATIONS
        ):
            problems.append(
                {
                    "severity": "warning",
                    "code": "unresolved-location",
                    "subject": obj.id,
                    "message": f"location {obj.location} is not a room/object/pseudo",
                }
            )
    depths = _reachable(world)
    for room_id in sorted(world.rooms):
        if room_id not in depths:
            problems.append(
                {
                    "severity": "warning",
                    "code": "unreachable-room",
                    "subject": room_id,
                    "message": "not reachable from the entry room",
                }
            )
    return problems


def build_graph(world: ZWorld) -> dict[str, Any]:
    depths = _reachable(world)
    edges: list[dict[str, Any]] = []
    kinds = {"passage": 0, "conditional": 0, "blocked": 0, "routine": 0, "unknown": 0}
    for room_id, exit_ in _edge_targets(world):
        kinds[exit_.kind] = kinds.get(exit_.kind, 0) + 1
        edge: dict[str, Any] = {
            "from": room_id,
            "direction": exit_.direction,
            "kind": exit_.kind,
        }
        if exit_.target:
            edge["to"] = exit_.target
        if exit_.condition:
            edge["condition"] = list(exit_.condition)
        if exit_.else_blocked:
            edge["else"] = "blocked"
        if exit_.routine:
            edge["routine"] = exit_.routine
        edges.append(edge)
    reverse: dict[tuple[str, str], set[str]] = {}
    for edge in edges:
        if edge.get("to"):
            reverse.setdefault((edge["to"], edge["from"]), set()).add(edge["direction"])
    one_way = 0
    for edge in edges:
        if not edge.get("to"):
            continue
        if (edge["from"], edge["to"]) not in reverse:
            one_way += 1
    return {
        "format": "z-world-graph-0",
        "world": world.name,
        "source": {
            "url": world.source_url,
            "commit": world.source_commit,
            "license": world.license,
            "files": dict(sorted(world.source_files.items())),
        },
        "entry": world.entry,
        "directions": list(world.directions),
        "nodes": [
            {
                "id": room.id,
                "flags": list(room.flags),
                "depth": depths.get(room.id),
                "exits": [
                    {
                        "direction": exit_.direction,
                        "kind": exit_.kind,
                        **({"to": exit_.target} if exit_.target else {}),
                        **(
                            {"condition": list(exit_.condition)}
                            if exit_.condition
                            else {}
                        ),
                        **({"else": "blocked"} if exit_.else_blocked else {}),
                        **({"routine": exit_.routine} if exit_.routine else {}),
                        **({"message": exit_.message} if exit_.message else {}),
                    }
                    for exit_ in room.exits
                ],
            }
            for room in sorted(world.rooms.values(), key=lambda room: room.id)
        ],
        "objects": [
            {
                "id": obj.id,
                "location": obj.location,
                "flags": list(obj.flags),
            }
            for obj in sorted(world.objects.values(), key=lambda obj: obj.id)
        ],
        "edges": edges,
        "stats": {
            "rooms": len(world.rooms),
            "objects": len(world.objects),
            "exits": len(edges),
            "kinds": kinds,
            "reachable": len(depths),
            "unreachable": len(world.rooms) - len(depths),
            "one_way": one_way,
        },
        "diagnostics": validate(world),
    }


# ---------------------------------------------------------------------------
# Text and Graphviz renderers


def _exit_text(exit_: Exit) -> str:
    if exit_.kind == "passage":
        return f"-> {exit_.target}"
    if exit_.kind == "conditional":
        text = f"-> {exit_.target} if {' '.join(exit_.condition)}"
        if exit_.else_blocked:
            text += " else blocked"
        return text
    if exit_.kind == "blocked":
        return "[blocked]" + (f" {exit_.message}" if exit_.message else "")
    if exit_.kind == "routine":
        return f"[routine {exit_.routine}]"
    return "[unknown]"


def render_text(world: ZWorld, graph: dict[str, Any]) -> str:
    stats = graph["stats"]
    depths = _reachable(world)
    lines = [
        f"Z world: {world.name}",
        f"source:  {world.source_url} @ {world.source_commit} ({world.license})",
        f"entry:   {world.entry}",
        f"rooms:   {stats['rooms']}   objects: {stats['objects']}   exits: {stats['exits']}",
        "kinds:   "
        + ", ".join(f"{key}={value}" for key, value in stats["kinds"].items()),
        f"reached: {stats['reachable']}/{stats['rooms']}   one-way exits: {stats['one_way']}",
        "",
        "== distance from entry (passages and conditional passages) ==",
    ]
    by_depth: dict[int, list[str]] = {}
    for room_id, depth in depths.items():
        by_depth.setdefault(depth, []).append(room_id)
    for depth in sorted(by_depth):
        lines.append(f"{depth:>2}: " + ", ".join(sorted(by_depth[depth])))
    missing = sorted(set(world.rooms) - set(depths))
    if missing:
        lines.append("--: " + ", ".join(missing))
    lines.extend(["", "== exits =="])
    order = {name: index for index, name in enumerate(world.directions)}
    for room_id in sorted(world.rooms):
        room = world.rooms[room_id]
        lines.append(room_id)
        exits = sorted(
            room.exits,
            key=lambda exit_: (order.get(exit_.direction, len(order)), exit_.direction),
        )
        for exit_ in exits:
            lines.append(f"  {exit_.direction:<5} {_exit_text(exit_)}")
    problems = graph["diagnostics"]
    lines.extend(["", "== diagnostics =="])
    if not problems:
        lines.append("none")
    else:
        for problem in problems:
            lines.append(
                f"{problem['severity']}: {problem['code']} {problem['subject']}: {problem['message']}"
            )
    return "\n".join(lines) + "\n"


def _wrap_label(value: str, width: int = 18) -> str:
    if len(value) <= width:
        return value
    parts = [value[index : index + width] for index in range(0, len(value), width)]
    return "\\n".join(parts)


def render_dot(world: ZWorld, graph: dict[str, Any]) -> str:
    lines = [
        f"digraph {json.dumps(world.name)} {{",
        "  graph [label="
        + json.dumps(f"{world.name}: initial world map")
        + ", labelloc=t, fontsize=20, overlap=false, splines=true, outputorder=edgesfirst];",
        '  node [shape=box, style=rounded, fontname="Helvetica", fontsize=9, margin="0.04,0.02"];',
        '  edge [arrowsize=0.4, color="#888888", penwidth=0.8, fontname="Helvetica", fontsize=7];',
    ]
    for node in graph["nodes"]:
        lines.append(f'  {json.dumps(node["id"])} [label="{_wrap_label(node["id"])}"];')
    routines = sorted(
        {edge["routine"] for edge in graph["edges"] if edge.get("routine")}
    )
    for routine in routines:
        ident = f"routine:{routine}"
        lines.append(
            f'  {json.dumps(ident)} [shape=diamond, style=dashed, label="{_wrap_label(routine)}"];'
        )
    for edge in graph["edges"]:
        if edge["kind"] not in {"passage", "conditional", "routine"}:
            continue
        attrs: list[str] = []
        if edge["kind"] == "conditional":
            attrs.extend(["style=dashed", 'color="#2f6fdf"'])
        elif edge["kind"] == "routine":
            attrs.extend(["style=dotted", 'color="#777777"'])
        if edge.get("condition"):
            attrs.append("label=" + json.dumps(" ".join(edge["condition"])))
        target = edge.get("to") or (
            f"routine:{edge['routine']}" if edge.get("routine") else None
        )
        if not target:
            continue
        line = f"  {json.dumps(edge['from'])} -> {json.dumps(target)}"
        if attrs:
            line += " [" + ", ".join(attrs) + "]"
        lines.append(line + ";")
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_svg(world: ZWorld, graph: dict[str, Any]) -> str:
    engine = shutil.which("fdp") or shutil.which("dot")
    if engine is None:
        raise RuntimeError("Graphviz fdp/dot is required for SVG output")
    result = subprocess.run(
        [engine, "-Tsvg"],
        input=render_dot(world, graph),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Graphviz failed: {result.stderr.strip()[:400]}")
    return result.stdout


def write_artifacts(
    world: ZWorld, out_dir: Path, *, svg: bool = True
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    graph = build_graph(world)
    paths: dict[str, Path] = {}
    z_path = out_dir / f"{world.name}.z"
    z_path.write_text(world_to_z(world))
    paths["z"] = z_path
    json_path = out_dir / f"{world.name}.json"
    json_path.write_text(json.dumps(graph, indent=1, sort_keys=False) + "\n")
    paths["json"] = json_path
    text_path = out_dir / f"{world.name}.txt"
    text_path.write_text(render_text(world, graph))
    paths["text"] = text_path
    if svg:
        svg_path = out_dir / f"{world.name}.svg"
        svg_path.write_text(render_svg(world, graph))
        paths["svg"] = svg_path
    return paths
