"""Lift the initial Zork I world from the MIT-licensed ZIL source into Z.

The source is compiled ZIL, not the retail v88 story.  This tool reads only the
top-level ROOM/OBJECT/DIRECTIONS forms and preserves unsupported exit forms as
explicit unknowns.  It does not execute ZIL, evaluate conditions or claim that
the retail story has the same map.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path

from zlang import Exit, Room, ZObject, ZWorld, build_graph, validate, write_artifacts

ROOM_RE = re.compile(r"<ROOM\s+([A-Z0-9_-]+)")
OBJECT_RE = re.compile(r"<OBJECT\s+([A-Z0-9_-]+)")
DIRECTIONS_RE = re.compile(r"<DIRECTIONS\b")

DEFAULT_DIRECTIONS = (
    "NORTH",
    "EAST",
    "WEST",
    "SOUTH",
    "NE",
    "NW",
    "SE",
    "SW",
    "UP",
    "DOWN",
    "IN",
    "OUT",
    "LAND",
)


class ZilString(str):
    """A quoted ZIL string, kept distinct from an atom."""


def _inside_string(segment: str) -> bool:
    in_string = False
    escaped = False
    for char in segment:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
    return in_string


def _skipped(text: str, start: int) -> bool:
    if start and text[start - 1] == "'":
        return True
    line_start = text.rfind("\n", 0, start) + 1
    segment = text[line_start:start]
    return _inside_string(segment) or ";" in segment


def _span(text: str, start: int) -> str:
    depth = 0
    in_string = False
    escaped = False
    index = start
    while index < len(text):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
        elif char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
        index += 1
    raise ValueError(f"unterminated ZIL form at byte {start}")


def _tokenize(raw: str) -> list[object]:
    tokens: list[object] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char.isspace():
            index += 1
            continue
        if char == ";":
            tokens.append(";")
            index += 1
            continue
        if char in "<(":
            tokens.append("(")
            index += 1
            continue
        if char in ">)":
            tokens.append(")")
            index += 1
            continue
        if char == '"':
            index += 1
            value: list[str] = []
            while index < len(raw):
                char = raw[index]
                if char == "\\" and index + 1 < len(raw):
                    value.append(raw[index + 1])
                    index += 2
                    continue
                if char == '"':
                    index += 1
                    break
                value.append(char)
                index += 1
            else:
                raise ValueError("unterminated ZIL string")
            tokens.append(ZilString("".join(value)))
            continue
        end = index
        while end < len(raw) and not raw[end].isspace() and raw[end] not in '<>()";':
            end += 1
        if end == index:
            raise ValueError(f"unexpected ZIL character {raw[index]!r}")
        tokens.append(raw[index:end])
        index = end
    return tokens


def _parse_form(raw: str) -> list[object]:
    stack: list[list[object]] = []
    root: list[object] | None = None
    for token in _tokenize(raw):
        if token == "(":
            node: list[object] = []
            if stack:
                stack[-1].append(node)
            else:
                if root is not None:
                    raise ValueError("multiple ZIL roots in one form")
                root = node
            stack.append(node)
        elif token == ")":
            if not stack:
                raise ValueError("unmatched ZIL closing delimiter")
            stack.pop()
        else:
            if not stack:
                raise ValueError("ZIL atom outside a form")
            stack[-1].append(token)
    if stack or root is None:
        raise ValueError("unterminated or empty ZIL form")
    return root


def _forms(text: str, pattern: re.Pattern[str]) -> list[list[object]]:
    found: list[list[object]] = []
    for match in pattern.finditer(text):
        if _skipped(text, match.start()):
            continue
        found.append(_parse_form(_span(text, match.start())))
    return found


def _property(form: list[object], name: str) -> list[object] | None:
    for item in form[2:]:
        if isinstance(item, list) and item and item[0] == name:
            return item
    return None


def _values(form: list[object], name: str) -> tuple[str, ...]:
    value = _property(form, name)
    if not value:
        return ()
    result: list[str] = []
    for item in value[1:]:
        if isinstance(item, ZilString):
            continue
        if isinstance(item, str) and item.startswith(";"):
            break
        if isinstance(item, str):
            result.append(item)
    return tuple(sorted(result))


def _flags(form: list[object]) -> tuple[str, ...]:
    return _values(form, "FLAGS")


def _text(form: list[object], name: str) -> str | None:
    value = _property(form, name)
    if not value or len(value) < 2:
        return None
    item = value[1]
    return str(item) if isinstance(item, ZilString) else None


def _strings(form: list[object], name: str) -> tuple[str, ...]:
    return _values(form, name)


def _lift_exit(direction: str, args: list[object], *, with_text: bool) -> Exit:
    if not args:
        return Exit(direction=direction, kind="unknown")
    head = args[0]
    if head == "TO":
        if len(args) < 2 or not isinstance(args[1], str):
            return Exit(direction=direction, kind="unknown")
        target = str(args[1])
        condition: tuple[str, ...] = ()
        else_blocked = False
        index = 2
        while index < len(args):
            token = args[index]
            if token == "IF":
                stop = index + 1
                while stop < len(args) and args[stop] != "ELSE":
                    stop += 1
                condition = tuple(
                    str(item)
                    for item in args[index + 1 : stop]
                    if isinstance(item, str) and not isinstance(item, ZilString)
                )
                index = stop
            elif token == "ELSE":
                value = args[index + 1] if index + 1 < len(args) else None
                if isinstance(value, ZilString):
                    else_blocked = True
                index += 2
            else:
                index += 1
        return Exit(
            direction=direction,
            kind="conditional" if condition else "passage",
            target=target,
            condition=condition,
            else_blocked=else_blocked,
        )
    if head == "PER":
        routine = args[1] if len(args) > 1 and isinstance(args[1], str) else None
        return Exit(direction=direction, kind="routine", routine=routine)
    if isinstance(head, ZilString):
        return Exit(
            direction=direction,
            kind="blocked",
            message=str(head) if with_text else None,
        )
    return Exit(direction=direction, kind="unknown")


def _git_head(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def lift(source_root: Path, *, entry: str, with_text: bool = False) -> ZWorld:
    directions = DEFAULT_DIRECTIONS
    source_files: dict[str, str] = {}
    room_forms: dict[str, list[object]] = {}
    object_forms: dict[str, list[object]] = {}
    for path in sorted(source_root.glob("*.zil")):
        text = path.read_text(encoding="utf-8")
        if not any(
            pattern.search(text) for pattern in (ROOM_RE, OBJECT_RE, DIRECTIONS_RE)
        ):
            continue
        source_files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for form in _forms(text, DIRECTIONS_RE):
            values = tuple(
                str(item)
                for item in form[1:]
                if isinstance(item, str) and not isinstance(item, ZilString)
            )
            if values:
                directions = values
        for form in _forms(text, ROOM_RE):
            name = str(form[1])
            if name in room_forms:
                raise ValueError(f"duplicate ROOM {name} in {path.name}")
            room_forms[name] = form
        for form in _forms(text, OBJECT_RE):
            name = str(form[1])
            if name in object_forms:
                raise ValueError(f"duplicate OBJECT {name} in {path.name}")
            object_forms[name] = form

    rooms: dict[str, Room] = {}
    for name, form in room_forms.items():
        exits = []
        for item in form[2:]:
            if not isinstance(item, list) or not item or not isinstance(item[0], str):
                continue
            direction = str(item[0])
            if direction not in directions:
                continue
            args = item[1:]
            if direction == "IN" and not any(
                arg in {"TO", "PER"} or isinstance(arg, ZilString) for arg in args
            ):
                continue
            exits.append(_lift_exit(direction, args, with_text=with_text))
        rooms[name] = Room(
            id=name,
            flags=_flags(form),
            exits=exits,
            desc=_text(form, "DESC") if with_text else None,
        )

    objects: dict[str, ZObject] = {}
    for name, form in object_forms.items():
        location = None
        value = _property(form, "IN")
        if value and len(value) > 1 and isinstance(value[1], str):
            if value[1] == "TO" and len(value) > 2 and isinstance(value[2], str):
                location = str(value[2])
            else:
                location = str(value[1])
        objects[name] = ZObject(
            id=name,
            location=location,
            flags=_flags(form),
            desc=_text(form, "DESC") if with_text else None,
            synonyms=_strings(form, "SYNONYM") if with_text else (),
            adjectives=_strings(form, "ADJECTIVE") if with_text else (),
        )

    return ZWorld(
        name="zork1-zil",
        source_url="https://github.com/historicalsource/zork1",
        source_commit=_git_head(source_root),
        license="MIT",
        entry=entry,
        directions=directions,
        rooms=rooms,
        objects=objects,
        source_files=source_files,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("/Volumes/CODEX/Codex_Projects/zork1-open-source"),
        help="checkout of the MIT-licensed Zork I ZIL source",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("generated"))
    parser.add_argument("--entry", default="WEST-OF-HOUSE")
    parser.add_argument(
        "--with-text", action="store_true", help="retain descriptions and blocked prose"
    )
    parser.add_argument("--no-svg", action="store_true", help="skip Graphviz output")
    args = parser.parse_args()

    world = lift(args.source_root, entry=args.entry, with_text=args.with_text)
    problems = validate(world)
    errors = [problem for problem in problems if problem["severity"] == "error"]
    if errors:
        for problem in errors:
            print(
                f"error: {problem['code']} {problem['subject']}: {problem['message']}"
            )
        return 1
    paths = write_artifacts(world, args.out_dir, svg=not args.no_svg)
    graph = build_graph(world)
    print(
        f"{world.name}: {graph['stats']['rooms']} rooms, "
        f"{graph['stats']['objects']} objects, {graph['stats']['exits']} exits, "
        f"{graph['stats']['reachable']} reachable, "
        f"{len(problems)} diagnostics"
    )
    for kind, path in paths.items():
        print(f"{kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
