"""Explicit service startup and small play commands; no hidden agent backend."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys

from .client import Client, private_file
from .service import PlayService


MAX_DEFINITION = 48 * 1024


def read_definition(path):
    """Read a small declarative JSON object without following special files."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Harness definition must be a regular JSON file.")
        if info.st_size > MAX_DEFINITION:
            raise ValueError("Harness definition exceeds 48 KiB.")
        data = source.read(MAX_DEFINITION + 1)
    if len(data) > MAX_DEFINITION:
        raise ValueError("Harness definition exceeds 48 KiB.")

    def reject_constant(value):
        raise ValueError("Harness definition contains a non-JSON number.")

    definition = json.loads(data, parse_constant=reject_constant)
    if not isinstance(definition, dict):
        raise ValueError("Harness definition must be a JSON object.")
    return definition


def parser():
    p = argparse.ArgumentParser(prog="dotbox")
    commands = p.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("guide", "Read the installed play instructions."),
        ("doctor", "Check the installed offline learning kit."),
        ("kit-export", "Export native source resources and guides."),
        ("inspect", "Inspect bounded frozen-file windows without a game."),
        ("learn", "Retain the next question and its bounded probe allowance."),
        ("scene", "Present grounded scene choices or an internal reconstruction checklist."),
        ("agi", "Inspect bounded AGI V2 logic and state references offline."),
        ("route", "Plan and check state-bound walking routes without executing input."),
        ("rts", "Inspect RTS worlds and prepare independent action primitives without input."),
    ):
        commands.add_parser(name, help=help_text).add_argument("arguments", nargs=argparse.REMAINDER)
    probe = commands.add_parser("probe", help="Print a noninvasive runtime inventory.")
    probe.add_argument("arguments", nargs=argparse.REMAINDER)
    serve = commands.add_parser("serve", help="Own one visible DOSBox-X session until explicit shutdown.")
    serve.add_argument("--directory", required=True, help="Private session directory (0700).")
    serve.add_argument("--project", required=True)
    serve.add_argument("--program", help="Original executable, required to create a new project.")
    serve.add_argument("--game-dir", required=True)
    serve.add_argument("--executable", required=True, help="Prepared DOSBox-X with DotBox ownership extension.")
    serve.add_argument("--image", choices=("com", "mz"))
    serve.add_argument("--window-scale", type=int, choices=(2, 3, 4, 5),
                       help="Optional integer display scale; native game coordinates stay unchanged.")
    serve.add_argument("--manual-control", action="store_true", help="Diagnostic native handoff/RPC input instead of default desktop-harness input; does not read WebRTC ownership.")
    serve.add_argument("--ownership-viewer", help="SHA-256 binding for the selected viewer; enable the separate authenticated ownership publisher.")
    coordinate = commands.add_parser("coordinate", help="Serve ownership coordination without an emulator or game backend.")
    coordinate.add_argument("--directory", required=True, help="Private coordinator directory (0700).")
    coordinate.add_argument("--ownership-viewer", required=True, help="SHA-256 binding for the selected viewer.")
    for name in ("status", "frame", "control", "play", "pause", "key", "type", "click", "close",
                 "harness-list", "harness-info", "harness-save", "act",
                 "turn-claim", "turn-check", "turn-release", "coordinator-close"):
        command = commands.add_parser(name)
        command.add_argument("--session", required=True, help="Path to private session.json descriptor.")
        if name not in ("status", "frame", "harness-list", "harness-info",
                        "turn-claim", "turn-check", "turn-release", "coordinator-close"):
            command.add_argument("--lease", required=True, help="Previously saved status/response JSON; prevents stale-owner actions.")
        if name == "frame":
            command.add_argument("--output", required=True, help="New PNG destination.")
        elif name == "turn-claim":
            command.add_argument("--controller-id", required=True, help="Stable identity for the sole cooperating action controller.")
        elif name in ("turn-check", "turn-release"):
            command.add_argument("--turn-lease", required=True, help="Private JSON turn-claim receipt; separate from native control generation.")
        elif name == "control":
            command.add_argument("owner", choices=("agent", "human"))
            command.add_argument("--resume", action="store_true")
        elif name == "key":
            command.add_argument("key")
            command.add_argument("--hold-ms", type=int, default=80)
        elif name == "type":
            command.add_argument("text")
        elif name == "click":
            command.add_argument("x", type=int)
            command.add_argument("y", type=int)
            command.add_argument("--button", choices=("left", "right", "middle"), default="left")
            command.add_argument("--mode-id", type=int, required=True)
            command.add_argument("--frame-id", type=int, required=True)
        elif name == "harness-info":
            command.add_argument("revision")
        elif name == "harness-save":
            command.add_argument("--definition", required=True, help="Declarative JSON file, at most 48 KiB.")
            command.add_argument("--parent", help="Parent revision for a new immutable branch.")
        elif name == "act":
            command.add_argument("revision")
            command.add_argument("name")
    return p


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "probe":
        from .runtime_probe import main as probe_main
        return probe_main(argv[1:])
    if argv and argv[0] in ("guide", "doctor", "kit-export"):
        from .kit import main as kit_main
        return kit_main(argv)
    if argv and argv[0] == "inspect":
        from .inspection import main as inspect_main
        return inspect_main(argv[1:])
    if argv and argv[0] == "learn":
        from .learning import main as learn_main
        return learn_main(argv[1:])
    if argv and argv[0] == "scene":
        from .scenes import main as scene_main
        return scene_main(argv[1:])
    if argv and argv[0] == "agi":
        from .agi import main as agi_main
        return agi_main(argv[1:])
    if argv and argv[0] == "route":
        from .navigation import main as route_main
        return route_main(argv[1:])
    if argv and argv[0] == "rts":
        from .rts import main as rts_main
        return rts_main(argv[1:])
    args = parser().parse_args(argv)
    try:
        if args.command in ("serve", "coordinate"):
            if args.command == "serve":
                from .backend import DOSBoxBackend
                config = {name: getattr(args, name) for name in ("project", "program", "game_dir", "executable", "image")}
                if args.window_scale is not None:
                    config['window_scale'] = args.window_scale
                service = PlayService(lambda: DOSBoxBackend(config), args.directory, manual_control=args.manual_control,
                                      ownership_viewer=args.ownership_viewer)
            else:
                from .coordination import CoordinationService
                service = CoordinationService(args.directory, args.ownership_viewer)
            previous = {sig: signal.signal(sig, lambda *_: service.request_stop())
                        for sig in (signal.SIGINT, signal.SIGTERM)}
            try:
                service.run(on_ready=lambda result: print(json.dumps(result), flush=True))
            finally:
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
            return 0
        params = {}
        if args.command == "turn-claim":
            params = {"controller_id": args.controller_id}
        elif args.command in ("turn-check", "turn-release"):
            document = json.loads(private_file(args.turn_lease, limit=8192))
            if not isinstance(document, dict):
                raise ValueError("Expected an object turn-claim receipt")
            params = {"lease": document.get("result", document)}
        if args.command == "harness-save":
            params = {"definition": read_definition(args.definition)}
            if args.parent is not None:
                params["parent"] = args.parent
        elif args.command == "harness-info":
            params = {"revision": args.revision}
        elif args.command == "act":
            params = {"revision": args.revision, "name": args.name}
        client = Client(args.session)
        lease = None
        if hasattr(args, "lease"):
            document = json.loads(Path(args.lease).read_text())
            lease = document.get("session") or document.get("result") or document
        if args.command == "control":
            params = {"owner": args.owner, "resume": args.resume}
        elif args.command == "key":
            params = {"key": args.key, "hold_ms": args.hold_ms}
        elif args.command == "type":
            params = {"text": args.text}
        elif args.command == "click":
            params = {name: getattr(args, name) for name in ("x", "y", "button", "mode_id", "frame_id")}
        response = client.request(args.command, params, lease=lease)
        if args.command == "frame" and response["ok"]:
            frame = response["result"]
            image = base64.b64decode(frame["png_base64"], validate=True)
            if hashlib.sha256(image).hexdigest() != frame["sha256"]:
                raise ValueError("Frame digest mismatch.")
            with Path(args.output).open("xb") as destination:
                destination.write(image)
            response["result"] = {k: v for k, v in frame.items() if k != "png_base64"} | {"output": str(Path(args.output).absolute())}
        print(json.dumps(response), flush=True)
        return 0 if response["ok"] else 1
    except (ValueError, OSError, KeyError, ImportError, RuntimeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1
