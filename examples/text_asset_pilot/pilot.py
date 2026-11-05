#!/usr/bin/env python3
"""Text-first component package pilot: recovery, linking, cooking and execution.

The game die reuses fDisBull's existing low-level word16 IR. It is not newly
recovered game-intent UIL. Static text becomes guarded UTF-8 assets. The old
codec remains an explicit fallback for unresolved or modified text sources.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import io
import json
import os
import re
from pathlib import Path
import sys
import tempfile
import zipfile

from asset_package import (Package, PackageError, canonical, exact, link, pack,
                           parse_json, private_output, sha, zip_bytes, MAX_MEMBER)
try:  # Cooked output contains only this stdlib runtime, not the analysis tool.
    import word16_runtime as word16
except ModuleNotFoundError:
    from fdisbull_player import word16

DIE_FORMAT = "fdisbull-word16-reference-die-1"
INDEX_FORMAT = "fdisbull-text-bindings-1"
STATE_FORMAT = "fdisbull-text-package-state-1"
CONTRACTS = {
    "command": {"version": 1, "input": "none", "output": "utf8-line-or-eof",
                "semantics": "one command; EOF ends host session without a game turn"},
    "present": {"version": 1, "input": "text-turn-v1: utf8 narrative, scalar status map, ordered event receipts", "output": "ack-or-error",
                "semantics": "ordered narrative/status/events; never execute text as commands"},
}
PORTS = {name: sha(canonical(value)) for name, value in CONTRACTS.items()}


def shell(name):
    if name not in ("terminal", "jsonl"):
        raise PackageError("unknown shell implementation")
    return {"id": "text-shell." + name + ".v1", "target": "python3-stdlib",
            "provides": {name + "." + pin: contract for pin, contract in PORTS.items()}}


def connect(package, name):
    # This implementation only realizes the explicitly declared text contracts.
    if package.manifest["component"]["requires"] != PORTS:
        raise PackageError("unsupported die interface")
    return link(package, shell(name), {pin: name + "." + pin for pin in PORTS})


def bounded_gunzip(data):
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
        out = stream.read(MAX_MEMBER + 1)
    if len(out) > MAX_MEMBER:
        raise PackageError("decoded program exceeds budget")
    return out


def binding_key(address, limit=None):
    return str(address) + ":" + ("*" if limit is None else str(limit))


def spans(points):
    result = []
    for pos in sorted(points):
        if result and pos == result[-1][0] + result[-1][1]:
            result[-1][1] += 1
        else:
            result.append([pos, 1])
    return result


class TextCollector(word16.Word16Runtime):
    """Use the existing decoder with byte-read instrumentation at build time."""
    def _read(self, address, width=8):
        value = super()._read(address, width)
        if hasattr(self, "read_points"):
            self.read_points.update(range(address, address + width // 8))
        return value

    def collect(self, address, limit=None):
        self.read_points = set()
        text = super()._decode_text(address, limit=limit)
        return text, spans(self.read_points)


def static_text_requests(program):
    """Constant text references only. Never infer reachability from a decode."""
    requests = set()
    def evaluate(expr, env):
        if type(expr) is int:
            return expr
        if not isinstance(expr, dict):
            raise ValueError("not a static expression")
        if set(expr) == {"tmp"}:
            return env[expr["tmp"]]
        args = [evaluate(arg, env) for arg in expr["args"]]
        op = expr["calc"]
        if op == "mul": return args[0] * args[1]
        if op == "add": return args[0] + args[1]
        if op == "sub": return args[0] - args[1]
        if op == "u16": return args[0] & 65535
        raise ValueError("not a supported constant expression")
    for block in program["blocks"].values():
        env = {}
        for node in block["nodes"]:
            try:
                if node["op"] == "let":
                    env[node["name"]] = evaluate(node["value"], env)
                elif node["op"] == "library" and node["name"] == "text.decode":
                    requests.add((evaluate(node["args"][0], env), None))
            except (ValueError, KeyError, TypeError):
                if node.get("name") in env:
                    del env[node["name"]]
            if node["op"] == "read_var":
                env.pop(node["dest"], None)
    # Object-name requests remain source-specific binding metadata, not UIL IDs.
    data = bytes.fromhex(program["memory"]["initial"])
    base = program["layout"]["objects"] + 62
    first = int.from_bytes(data[base + 7:base + 9], "big")
    count, remainder = divmod(first - base, 9)
    if not remainder and 1 <= count <= 255:
        for number in range(count):
            at = base + 9 * number + 7
            table = int.from_bytes(data[at:at + 2], "big")
            if 0 <= table < len(data) and data[table]:
                requests.add((table + 1, table + 1 + 2 * data[table]))
    return sorted(requests, key=lambda pair: (pair[0], -1 if pair[1] is None else pair[1]))


def bundle_program(program):
    """Normalize the preserved die's data and verified static text references."""
    word16.validate_program(program)
    original = canonical(program)
    collector = TextCollector(program)
    entries, bindings, rejected = {}, {}, 0
    for address, limit in static_text_requests(program):
        try:
            text, guards = collector.collect(address, limit)
        except word16.Word16Error:
            rejected += 1  # Invalid alternate decodes are not silently admitted.
            continue
        payload = text.encode("utf-8")
        asset_id = "text." + sha(payload)
        entries[asset_id] = ("text", "text/plain;charset=utf-8", payload, [],
                             {"normalization": "none", "control_codes": "preserved"})
        bindings[binding_key(address, limit)] = {"asset": asset_id, "reads": guards}
    index = {"format": INDEX_FORMAT, "bindings": bindings,
             "miss_policy": "explicit-legacy-codec-fallback"}
    entries["text.index"] = ("binding", "application/json", canonical(index),
                              sorted({item["asset"] for item in bindings.values()}), {})
    initial = bytes.fromhex(program["memory"]["initial"])
    entries["state.initial"] = ("state-template", "application/octet-stream", initial, [], {})
    # Own the internal storage layout without changing the existing UIL format.
    body = copy.deepcopy(program)
    writable_end = body.pop("memory")["writable_end"]
    die = {"format": DIE_FORMAT, "program": body,
           "memory": {"asset": "state.initial", "writable_end": writable_end},
           "text_index": "text.index", "program_sha256": sha(original)}
    payload = gzip.compress(canonical(die), mtime=0)
    entries["die.program"] = ("reference-die", "application/gzip", payload,
                               ["state.initial", "text.index"],
                               {"encoding": "gzip-json", "inner_format": DIE_FORMAT})
    report = {"format": "fdisbull-text-normalization-receipt-1",
              "source": program["source"], "program_sha256": sha(original),
              "static_text_bindings": len(bindings),
              "unique_text_payloads": len(entries) - 3,
              "rejected_static_text_candidates": rejected,
              "candidate_blocks": len(program["blocks"]),
              "not_claimed": ["whole-game intent recovery", "all-path text closure",
                              "removal of original-derived data", "native machine-code generation"]}
    entries["provenance.receipt"] = ("provenance", "application/json", canonical(report), [], {})
    component = {"id": "zmachine-v3.word16-reference", "entry": "die.program", "requires": PORTS}
    data = pack(component, entries, {"profile": "text-assets-pilot-1", "private_game_content": True})
    return data, report


class AssetRuntime(word16.Word16Runtime):
    """Substitute asset reads, with exact dependency guards, behind the die."""
    def __init__(self, package, *, seed=12, strict_text=False):
        die = parse_json(bounded_gunzip(package.get(package.manifest["component"]["entry"], "reference-die")))
        exact(die, ("format", "program", "memory", "text_index", "program_sha256"), "reference die")
        if die["format"] != DIE_FORMAT:
            raise PackageError("unsupported die format")
        exact(die["memory"], ("asset", "writable_end"), "memory binding")
        program = die["program"]
        if "memory" in program:
            raise PackageError("duplicate memory realization")
        initial = package.get(die["memory"]["asset"], "state-template")
        program["memory"] = {"initial": initial.hex(), "writable_end": die["memory"]["writable_end"]}
        if sha(canonical(program)) != die["program_sha256"]:
            raise PackageError("reconstructed die identity mismatch")
        index = parse_json(package.get(die["text_index"], "binding"))
        exact(index, ("format", "bindings", "miss_policy"), "text bindings")
        if index["format"] != INDEX_FORMAT or index["miss_policy"] != "explicit-legacy-codec-fallback":
            raise PackageError("unsupported text binding contract")
        if not isinstance(index["bindings"], dict):
            raise PackageError("invalid text bindings")
        self.text_bindings = {}
        for key, entry in index["bindings"].items():
            exact(entry, ("asset", "reads"), "text binding")
            if not isinstance(key, str) or not re.fullmatch(r"[0-9]+:(\*|[0-9]+)", key):
                raise PackageError("invalid text address binding")
            guards = entry["reads"]
            if not isinstance(guards, list) or not guards:
                raise PackageError("missing text dependency guards")
            previous_end = -1
            for guard in guards:
                if (not isinstance(guard, list) or len(guard) != 2
                        or any(type(n) is not int for n in guard)
                        or not 0 <= guard[0] < len(initial) or guard[1] < 1
                        or guard[0] + guard[1] > len(initial) or guard[0] < previous_end):
                    raise PackageError("invalid text dependency span")
                previous_end = guard[0] + guard[1]
            try:
                text = package.get(entry["asset"], "text").decode("utf-8")
            except UnicodeDecodeError as exc:
                raise PackageError("invalid UTF-8 asset") from exc
            if len(text) > word16.MAX_TEXT:
                raise PackageError("oversized text asset")
            self.text_bindings[key] = (text, guards)
        self.asset_hits = self.codec_misses = self.codec_calls = self.changed_dependencies = 0
        self.strict_text = strict_text
        self.asset_package_digest = package.digest
        super().__init__(program, seed=seed)

    def _decode_text(self, address, seen=(), limit=None):
        entry = self.text_bindings.get(binding_key(address, limit))
        if not seen and entry is not None:
            text, guards = entry
            if all(self.memory[at:at + size] == self.initial[at:at + size] for at, size in guards):
                self.asset_hits += 1
                return text
            self.changed_dependencies += 1
        self.codec_calls += 1
        if not seen: self.codec_misses += 1
        if self.strict_text:
            raise word16.Word16Error("text asset closure failure: " + binding_key(address, limit))
        return super()._decode_text(address, seen=seen, limit=limit)

    def save_package_state(self):
        return {"format": STATE_FORMAT, "package_sha256": self.asset_package_digest,
                "state": self.snapshot()}

    def restore_package_state(self, checkpoint):
        exact(checkpoint, ("format", "package_sha256", "state"), "package checkpoint")
        if checkpoint["format"] != STATE_FORMAT or checkpoint["package_sha256"] != self.asset_package_digest:
            raise PackageError("checkpoint asset-package identity mismatch")
        self.restore(checkpoint["state"])


def cook_zipapp(package_bytes, shell_name):
    """A runnable Python executable, explicitly NOT an ELF/native compiler."""
    package = Package(package_bytes)
    receipt = connect(package, shell_name)
    root = Path(__file__).resolve().parent
    members = {
        "asset_package.py": (root / "asset_package.py").read_bytes(),
        "pilot.py": Path(__file__).read_bytes(),
        "word16_runtime.py": Path(word16.__file__).read_bytes(),
        "game.bundle": package_bytes,
        "link.json": canonical(receipt),
        "__main__.py": b"from pilot import main\nraise SystemExit(main(['play', '--embedded'] + __import__('sys').argv[1:]))\n",
    }
    artifact = zip_bytes(members, prefix=b"#!/usr/bin/env python3\n")
    return artifact, {"format": "fdisbull-text-cook-receipt-1", "link": receipt,
                      "files": {name: sha(data) for name, data in members.items()},
                      "artifact_sha256": sha(artifact), "artifact_bytes": len(artifact),
                      "requires": "Python >=3.10 standard library; not a native ELF"}


def _atomic_state(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".state-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value))
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def play(args):
    if args.embedded:
        if args.package:
            raise PackageError("embedded mode cannot also select an external package")
        with zipfile.ZipFile(sys.argv[0]) as archive:
            package = Package(archive.read("game.bundle"))
            declared_link = parse_json(archive.read("link.json"))
        selected = declared_link["shell"]["id"].split(".")[1]
        if args.shell and args.shell != selected:
            raise PackageError("cook a new connector to change an embedded shell")
        receipt = connect(package, selected)
        if declared_link != receipt:
            raise PackageError("cooked connector identity mismatch")
    else:
        if not args.package:
            raise PackageError("package path required")
        package = Package.read(args.package)
        selected = args.shell or "terminal"
        receipt = connect(package, selected)
    # Output paths must never overwrite the executable, package, input, or one another.
    protected = {Path(p).resolve() for p in (sys.argv[0], args.package, args.commands, args.resume) if p}
    output_names = [Path(p) for p in (args.checkpoint, args.transcript, args.metrics) if p]
    if any(p.is_symlink() for p in output_names):
        raise PackageError("output must not be a symlink")
    outputs = [p.resolve() for p in output_names]
    if len(outputs) != len(set(outputs)) or any(p in protected for p in outputs):
        raise PackageError("output aliases an input or another output")
    for p in outputs:
        if p.is_symlink() or any((parent / ".git").exists() for parent in p.parents):
            raise PackageError("unsafe/private output destination")
    commands = None
    if args.commands:
        with open(args.commands, "rb") as stream:
            raw_commands = stream.read(1024 * 1024 + 1)
            if len(raw_commands) > 1024 * 1024: raise PackageError("command file too large")
            commands = parse_json(raw_commands)
        if (not isinstance(commands, list) or len(commands) > 10000
                or any(not isinstance(c, str) or len(c) > 4096 for c in commands)):
            raise PackageError("commands require a bounded JSON string list")
    runtime = AssetRuntime(package, seed=args.seed, strict_text=args.strict_text)
    if args.resume:
        with open(args.resume, "rb") as stream:
            runtime.restore_package_state(parse_json(stream.read(word16.MAX_CHECKPOINT_BYTES + 1)))
    turns = []
    transcript_bytes = 0
    def present(result, command):
        nonlocal transcript_bytes
        # This text-only realization refuses sound rather than claiming to play it.
        if any(event.get("type") == "sound" for event in result["events"]):
            raise PackageError("audio event requires an audio-capable shell")
        turn = {"seq": len(turns), "command": command, "status": result["status"],
                "text": result["text"], "values": {key: result[key] for key in ("location", "score", "moves")},
                "events": result["events"]}
        transcript_bytes += len(canonical(turn))
        if len(turns) >= 10000 or transcript_bytes > 64 * 1024 * 1024:
            raise PackageError("session receipt budget exceeded")
        turns.append(turn)
        if selected == "jsonl":
            sys.stdout.write(canonical(turn).decode("utf-8") + "\n")
        else:
            sys.stdout.write(result["text"])
            # The terminal shell routes non-narrative presentation to stderr.
            # This includes upper-window text; no text is parsed as host code.
            auxiliary = [e for e in result["events"] if e.get("type") != "text"
                         or e.get("window") != 0 or not e.get("screen")]
            sys.stderr.write(canonical({"seq": turn["seq"], "status": result["status"],
                             "score": result["score"], "moves": result["moves"],
                             "location": result["location"], "events": auxiliary}).decode() + "\n")
        sys.stdout.flush()
        if args.checkpoint: _atomic_state(args.checkpoint, runtime.save_package_state())
        return result
    result = present(runtime.run(), None)
    if commands is not None:
        for command in commands:
            if result["status"] != "input": break
            result = present(runtime.command(command), command)
    else:
        while result["status"] == "input":
            line = sys.stdin.readline(16385)
            if not line: break
            if len(line) > 16384:
                raise PackageError("host input exceeds line budget")
            if selected == "jsonl":
                request = parse_json(line)
                exact(request, ("command",), "command request")
                command = request["command"]
                if not isinstance(command, str): raise PackageError("command must be text")
            else:
                command = line.rstrip("\r\n")
            result = present(runtime.command(command), command)
    if args.transcript: _atomic_state(args.transcript, turns)
    if args.metrics:
        _atomic_state(args.metrics, {"package_sha256": package.digest,
                      "link_sha256": receipt["link_sha256"], "turns": len(turns),
                      "text_asset_hits": runtime.asset_hits, "codec_misses": runtime.codec_misses,
                      "legacy_codec_calls_including_abbreviations": runtime.codec_calls,
                      "changed_dependencies": runtime.changed_dependencies,
                      "state_sha256": sha(canonical(runtime.snapshot()))})
    return 2 if result["status"] == "budget_exhausted" else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    build = sub.add_parser("build", help="compile owned v3 story into an asset package")
    build.add_argument("story")
    build.add_argument("output")
    cook = sub.add_parser("cook", help="link a package to a standalone Python shell")
    cook.add_argument("package")
    cook.add_argument("output")
    cook.add_argument("--shell", choices=("terminal", "jsonl"), default="terminal")
    run = sub.add_parser("play", help="run a package or embedded cooked product")
    run.add_argument("package", nargs="?")
    run.add_argument("--embedded", action="store_true")
    run.add_argument("--shell", choices=("terminal", "jsonl"))
    run.add_argument("--seed", type=int, default=12)
    run.add_argument("--commands")
    run.add_argument("--resume")
    run.add_argument("--checkpoint")
    run.add_argument("--transcript")
    run.add_argument("--metrics")
    run.add_argument("--strict-text", action="store_true")
    check = sub.add_parser("inspect")
    check.add_argument("package")
    args = parser.parse_args(argv)
    try:
        if args.action == "build":
            from fdisbull.zork_uil import compile_story
            out = private_output(args.output)
            before = sha(Path(args.story).read_bytes())
            program, _ = compile_story(args.story)
            if before != sha(Path(args.story).read_bytes()) or before != program["source"]["sha256"]:
                raise PackageError("source changed during recovery")
            data, report = bundle_program(program)
            Package(data)  # Validate the actual serialized delivery before write.
            with out.open("xb") as stream: stream.write(data)
            print(json.dumps({**report, "package_sha256": sha(data), "package_bytes": len(data)}))
        elif args.action == "cook":
            out = private_output(args.output)
            data, report = cook_zipapp(Path(args.package).read_bytes(), args.shell)
            with out.open("xb") as stream: stream.write(data)
            out.chmod(0o755)
            print(json.dumps(report))
        elif args.action == "inspect":
            pkg = Package.read(args.package)
            print(json.dumps({"package_sha256": pkg.digest, "component": pkg.manifest["component"],
                              "assets": len(pkg.manifest["assets"]), "blobs": len(pkg.blobs)}))
        else:
            return play(args)
        return 0
    except (PackageError, word16.Word16Error, OSError, ValueError) as exc:
        parser.exit(1, f"text-asset-pilot: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
