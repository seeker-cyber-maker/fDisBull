import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import sys

from . import JsonLineBackend, LiveSession, LocalRuntime, Player, self_play


def main():
    parser = argparse.ArgumentParser(description="Play a declared text scene slice")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--package", help="local JSON text-slice package")
    source.add_argument("--connect", help="JSON-lines backend host:port")
    parser.add_argument("--live", action="store_true", help="restore and checkpoint each JSON model turn")
    parser.add_argument("--save-dir", help="local checkpoint directory")
    parser.add_argument("--agent-command", help="external JSON-lines agent command, without a shell")
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--max-actions", type=int, default=16)
    parser.add_argument("--wall-seconds", type=float, default=60)
    parser.add_argument("--agent-timeout", type=float, default=10)
    parser.add_argument("--transcript", help="write private structured self-play transcript")
    args = parser.parse_args()
    if args.agent_command and not args.live:
        parser.error("--agent-command requires --live")
    if args.transcript and not args.agent_command:
        parser.error("--transcript requires --agent-command")
    try:
        if args.package:
            with open(args.package, encoding="utf-8") as stream:
                package = json.load(stream)
            digest = hashlib.sha256(json.dumps(package, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ("Library/Application Support" if sys.platform == "darwin" else ".local/share")))
            save_dir = Path(args.save_dir) if args.save_dir else base / "fdisbull-player" / digest
            backend = LocalRuntime(package, save_dir=save_dir)
            return run_mode(backend, args)
        host, port = args.connect.rsplit(":", 1)
        with socket.create_connection((host, int(port))) as sock, sock.makefile("r", encoding="utf-8") as reader, sock.makefile("w", encoding="utf-8") as writer:
            return run_mode(JsonLineBackend(reader, writer), args)
    except (OSError, ValueError, EOFError, json.JSONDecodeError) as exc:
        print(f"Player stopped: {exc}", file=sys.stderr)
        return 1


def run_mode(backend, args):
    if not args.live:
        run(Player(backend))
        return 0
    session = LiveSession(backend, max_actions=args.max_actions)
    if args.agent_command:
        transcript = self_play(session, shlex.split(args.agent_command), args.max_turns, args.max_actions,
                               args.wall_seconds, args.agent_timeout)
        if args.transcript:
            fd = os.open(args.transcript, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(transcript, out, ensure_ascii=False, indent=2)
        print("Session status: " + transcript["status"])
        return 0 if transcript["status"] in ("agent_done", "turn_limit", "wall_limit") else 1
    for line in sys.stdin:
        if len(line.encode("utf-8")) > 1024 * 1024:
            raise ValueError("Turn exceeds line limit")
        request = json.loads(line)
        if not isinstance(request, dict) or set(request) != {"commands"}:
            raise ValueError("Expected an object containing commands")
        result = session.run_turn(request["commands"])
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if session.blocked or "error" in result:
            return 1
    return 0


def run(player):
    print(player.execute("look"))
    for line in sys.stdin:
        if line.strip().casefold() in ("quit", "exit"):
            break
        print(player.execute(line))


if __name__ == "__main__":
    raise SystemExit(main())
