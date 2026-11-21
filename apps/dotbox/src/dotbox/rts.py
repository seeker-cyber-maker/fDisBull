"""Offline RTS observations and composable requests; never opens an input path."""

import argparse
import json
import os
import stat
import sys

from . import scenes
from .rts_actions import PRIMITIVES, prepare_action, check_action
from .rts_world import validate_world, world_digest, project_scene, diff_world


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON value")


def _json(text):
    return json.loads(text, object_pairs_hook=_unique, parse_constant=_constant)


def _read(path):
    limit = 2 * 1024 * 1024
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("RTS input must be a regular JSON file of at most 2 MiB")
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("RTS input exceeds 2 MiB")
    return _json(data)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    parser = _Parser(prog="dotbox rts", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("primitives", help="List independent primitives and their scope.")
    for name in ("validate", "project", "look", "prepare"):
        command = commands.add_parser(name)
        command.add_argument("world")
        if name in ("project", "look"):
            command.add_argument("--max-entities", type=int, default=8)
        if name == "look":
            command.add_argument("--detail", choices=("brief", "normal", "detailed"), default="normal")
        if name == "prepare":
            command.add_argument("--primitive", required=True, choices=tuple(PRIMITIVES))
            command.add_argument("--arguments", required=True, help="One bounded JSON argument object.")
    command = commands.add_parser("check")
    command.add_argument("request")
    command.add_argument("world")
    command = commands.add_parser("diff")
    command.add_argument("before")
    command.add_argument("after")
    try:
        args = parser.parse_args(argv)
        if args.command == "primitives":
            result = {"format": "dotbox-rts-primitives-1", "execution": "not_performed",
                      "primitives": [{"id": key, "description": value} for key, value in PRIMITIVES.items()],
                      "claim": "A vocabulary; availability requires a qualified current provider binding."}
        elif args.command == "diff":
            result = diff_world(_read(args.before), _read(args.after))
        else:
            world = validate_world(_read(args.world))
            if args.command == "validate":
                result = {"valid": True, "world_sha256": world_digest(world), "observation_id": world["observation_id"],
                          "entity_count": len(world["entities"]), "event_count": len(world["events"]),
                          "execution": "not_performed", "claim": "Validated caller-reported observation; no live recognition."}
            elif args.command in ("project", "look"):
                result = project_scene(world, max_entities=args.max_entities)
                if args.command == "look":
                    result = scenes.look_scene(result, detail=args.detail)
            elif args.command == "prepare":
                if len(args.arguments.encode()) > 16 * 1024:
                    raise ValueError("RTS arguments exceed 16 KiB")
                result = prepare_action(world, args.primitive, _json(args.arguments))
            else:
                result = check_action(_read(args.request), world)
        print(json.dumps({"ok": True, "result": result}, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
