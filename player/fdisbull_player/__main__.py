import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import socket
import sys

from . import BatchSession, JsonLineBackend, LiveSession, LocalRuntime, Player, ProcessBackend, self_play


def main():
    parser = argparse.ArgumentParser(description="Play a declared text scene slice")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--package", help="local JSON text-slice package")
    source.add_argument("--uil", help="executable word16 IR (.json or .json.gz; legacy option name)")
    source.add_argument("--intents", help="partial game-intent UIL package with explicit residual IR")
    source.add_argument("--scenes", help="recovered scene rules, direct handler links and explicit residual IR")
    source.add_argument("--connect", help="JSON-lines backend host:port")
    source.add_argument("--backend-command", help="local content-service command, without a shell")
    parser.add_argument("--backend-timeout", type=float, default=60,
                        help="local service request deadline or socket inactivity limit, seconds (0 < value <= 60)")
    parser.add_argument("--live", action="store_true", help="restore and checkpoint each JSON model turn")
    parser.add_argument("--save-dir", help="local checkpoint directory")
    parser.add_argument("--agent-command", help="external JSON-lines agent command, without a shell")
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--max-actions", type=int, default=16)
    parser.add_argument("--wall-seconds", type=float, default=60)
    parser.add_argument("--agent-timeout", type=float, default=10)
    parser.add_argument("--transcript", help="write private structured self-play transcript")
    parser.add_argument("--quiet", action="store_true", help="print only session status; requires an agent and transcript")
    parser.add_argument("--seed", type=int, default=12, help="reproducible seed for --uil, --intents or --scenes")
    parser.add_argument("--commands", help="JSON command list for --uil, --intents or --scenes")
    parser.add_argument("--checkpoint", help="durable continuation after each --uil, --intents or --scenes command")
    parser.add_argument("--resume", help="resume a compatible --uil, --intents or --scenes checkpoint")
    parser.add_argument('--batch-plan', help='JSON ordered command plan; read batch operations as JSON lines')
    parser.add_argument('--batch-journal', help='private durable journal for --batch-plan')
    args = parser.parse_args()
    if bool(args.batch_plan) != bool(args.batch_journal):
        parser.error('--batch-plan and --batch-journal are required together')
    if args.batch_plan and (args.live or args.agent_command or args.transcript or args.quiet or args.uil or args.intents or args.scenes):
        parser.error('--batch-plan uses its own JSON operation protocol with a qualified scene provider')
    if args.uil or args.intents or args.scenes:
        if args.live or args.agent_command or args.save_dir or args.quiet:
            parser.error('--uil, --intents and --scenes use --checkpoint/--resume and their own command loop')
        if args.scenes:
            from .scene_runtime import main as run_program
        elif args.intents:
            from .intent_runtime import main as run_program
        else:
            from .word16 import main as run_program
        options = [args.scenes or args.intents or args.uil, '--seed', str(args.seed)]
        for flag in ('commands', 'checkpoint', 'resume', 'transcript'):
            if getattr(args, flag):
                options.extend(['--' + flag, getattr(args, flag)])
        try:
            return run_program(options)
        except (OSError, ValueError, EOFError) as exc:
            print(f"Program player stopped: {exc}", file=sys.stderr)
            return 1
    if args.commands or args.checkpoint or args.resume:
        parser.error('--commands, --checkpoint and --resume require --uil, --intents or --scenes')
    if args.backend_command is not None and not args.backend_command.strip():
        parser.error('--backend-command must not be blank')
    if not math.isfinite(args.backend_timeout) or not 0 < args.backend_timeout <= 60:
        parser.error('--backend-timeout must be finite and between 0 and 60 seconds')
    if args.backend_command and args.save_dir:
        parser.error('--save-dir belongs to --package; the content service owns checkpoints')
    if args.agent_command and not args.live:
        parser.error("--agent-command requires --live")
    if args.transcript and not args.agent_command:
        parser.error("--transcript requires --agent-command")
    if args.quiet and not (args.agent_command and args.transcript):
        parser.error('--quiet requires --agent-command and --transcript')
    try:
        if args.backend_command:
            backend = ProcessBackend(shlex.split(args.backend_command), timeout=args.backend_timeout)
            try:
                return run_mode(backend, args)
            finally:
                backend.close()
        if args.package:
            with open(args.package, encoding="utf-8") as stream:
                package = json.load(stream)
            digest = hashlib.sha256(json.dumps(package, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ("Library/Application Support" if sys.platform == "darwin" else ".local/share")))
            save_dir = Path(args.save_dir) if args.save_dir else base / "fdisbull-player" / digest
            backend = LocalRuntime(package, save_dir=save_dir)
            return run_mode(backend, args)
        host, port = args.connect.rsplit(":", 1)
        with socket.create_connection((host, int(port)), timeout=args.backend_timeout) as sock, sock.makefile("r", encoding="utf-8") as reader, sock.makefile("w", encoding="utf-8") as writer:
            return run_mode(JsonLineBackend(reader, writer), args)
    except (OSError, ValueError, EOFError, json.JSONDecodeError) as exc:
        print(f"Player stopped: {exc}", file=sys.stderr)
        return 1


def run_mode(backend, args):
    if args.batch_plan:
        with open(args.batch_plan, encoding='utf-8') as source:
            plan = source.read(65537)
        if len(plan.encode()) > 65536:
            raise ValueError('Batch plan exceeds 65536 bytes')
        batch = BatchSession(Player(backend), args.batch_journal, json.loads(plan))
        for line in sys.stdin:
            if len(line.encode()) > 4096:
                raise ValueError('Batch operation exceeds 4096 bytes')
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError('Invalid batch operation')
            op = request.get('op')
            if op in ('run', 'resume') and set(request) <= {'op', 'max_steps'}:
                result = getattr(batch, op)(max_steps=request.get('max_steps', 128))
            elif op in ('checkpoint', 'recover') and set(request) == {'op', 'name'}:
                result = getattr(batch, op)(request['name'])
            elif op == 'inspect' and set(request) == {'op'}:
                result = batch.inspect()
            else:
                raise ValueError('Invalid batch operation')
            print(json.dumps({k:v for k,v in result.items() if k not in ('steps', 'batch')}, ensure_ascii=False), flush=True)
        return 0
    if not args.live:
        run(Player(backend))
        return 0
    session = LiveSession(backend, max_actions=args.max_actions)
    if args.agent_command:
        transcript = self_play(session, shlex.split(args.agent_command), args.max_turns, args.max_actions,
                               args.wall_seconds, args.agent_timeout,
                               emit=(lambda message: None) if args.quiet else print)
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
    while True:
        if sys.stdin.isatty():
            print('> ', end='', flush=True)
        line = sys.stdin.readline(4097)
        if not line:
            break
        if len(line.encode('utf-8')) > 4096:
            raise ValueError('Command exceeds the 4096-byte limit')
        if line.strip().casefold() in ("quit", "exit"):
            break
        print(player.execute(line))


if __name__ == "__main__":
    raise SystemExit(main())
