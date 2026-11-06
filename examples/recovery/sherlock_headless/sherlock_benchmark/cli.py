"""JSON CLI and line-oriented session; no server, GUI, compiler or emulator."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import stat
import sys
import time

from . import __version__
from .evaluation import corpus_id, evaluate
from .generator import GENERATOR_ID, GENERATOR_VERSION, GenerationError, generate
from .model import (MAX_JSON_BYTES, ModelError, Puzzle, RULESET, canonical_bytes,
                    loads_json, make_submission, rules_document, verify)
from .session import Session
from .solver import MAX_SOLVE_NODES, SOLVER_ID, SOLVER_VERSION, solve

MAX_CORPUS = 1000
MAX_JSONL_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class _ParseFailure:
    message: str
    record_index: int


def runtime_info() -> dict:
    digest = sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        payload = path.read_bytes()
        digest.update(path.name.encode("ascii") + b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return {"engine": "sherlock-headless-benchmark", "version": __version__,
            "engine_source_sha256": digest.hexdigest(), "ruleset": RULESET,
            "python": platform.python_version(), "implementation": platform.python_implementation(),
            "platform": platform.system(), "solver": SOLVER_ID, "solver_version": SOLVER_VERSION,
            "generator": GENERATOR_ID, "generator_version": GENERATOR_VERSION}


def emit(value):
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True)


def read_bytes(path: str, limit=MAX_JSON_BYTES) -> bytes:
    if path == "-":
        data = sys.stdin.buffer.read(limit + 1)
    else:
        # Refuse special files rather than hanging on FIFOs supplied as results.
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ModelError("input path must name a regular file")
            data = stream.read(limit + 1)
    if len(data) > limit:
        raise ModelError(f"input exceeds {limit} bytes")
    return data


def read_document(path):
    return loads_json(read_bytes(path))


def read_puzzle(path) -> Puzzle:
    return Puzzle.from_dict(read_document(path))


def read_jsonl(path, *, tolerate_bad=False):
    raw = read_bytes(path, MAX_JSONL_BYTES)
    lines = raw.splitlines()
    if len(lines) > MAX_CORPUS * 4:
        raise ModelError("too many JSONL records (maximum 4000)")
    records = []
    for index, line in enumerate(lines):
        try:
            records.append(loads_json(line))
        except ModelError as exc:
            if not tolerate_bad:
                raise ModelError(f"JSONL record {index}: {exc}") from exc
            # A failed parse cannot provide a trusted ID. It remains an explicit
            # malformed entry, and its missing expected answer stays a failure.
            records.append(_ParseFailure(str(exc), index))
    return records


def read_corpus(path):
    puzzles = [Puzzle.from_dict(x) for x in read_jsonl(path)]
    if len(puzzles) > MAX_CORPUS:
        raise ModelError(f"corpus exceeds {MAX_CORPUS} puzzles")
    corpus_id(puzzles)  # Includes nonempty and duplicate-ID checks.
    return puzzles


def write_new(path, value, *, private=True):
    target = Path(path)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600 if private else 0o644)
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical_bytes(value) + b"\n")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ModelError(message)


def decimal(value):
    if not value or not value.isascii() or not value.isdecimal() or len(value) > 20:
        raise argparse.ArgumentTypeError("expected at most 20 unsigned decimal digits")
    return int(value)


def parser():
    p = Parser(prog="sherlock-bench", description="Headless relational puzzle game and JSON benchmark")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("version", help="print engine, rules and runtime identities")
    commands.add_parser("rules", help="print complete machine-readable rule definitions")
    gen = commands.add_parser("generate", help="emit a solver-certified unique public puzzle")
    corpus = commands.add_parser("corpus", help="create public JSONL and a separate private manifest")
    for cmd in (gen, corpus):
        cmd.add_argument("--seed", required=True, type=decimal)
        cmd.add_argument("--rows", default=6, type=decimal)
        cmd.add_argument("--columns", default=6, type=decimal)
        cmd.add_argument("--max-nodes", default=100000, type=decimal)
        cmd.add_argument("--max-clues", default=256, type=decimal)
        cmd.add_argument("--no-prune", action="store_true")
    gen.add_argument("--manifest", help="new private JSON path; contains seed and witness")
    corpus.add_argument("--count", default=20, type=decimal)
    corpus.add_argument("--output", required=True, help="new directory; must not already exist")
    for name in ("solve", "analyze", "verify", "serve"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--puzzle", required=True, help="public puzzle JSON file, or - for stdin")
        if name in ("solve", "analyze"):
            cmd.add_argument("--max-nodes", default=100000, type=decimal)
        if name == "solve":
            cmd.add_argument("--submission", action="store_true", help="emit only a valid submission envelope")
        elif name == "verify":
            cmd.add_argument("--submission", required=True, help="answer JSON file, or - for stdin")
        elif name == "serve":
            cmd.add_argument("--state", help="resume a checkpoint bound to this puzzle")
    grade = commands.add_parser("evaluate", help="grade recorded agent JSONL submissions")
    grade.add_argument("--corpus", required=True)
    grade.add_argument("--submissions", required=True)
    baseline = commands.add_parser("baseline", help="solve public corpus; emit JSONL submissions")
    baseline.add_argument("--corpus", required=True)
    baseline.add_argument("--max-nodes", default=100000, type=decimal)
    baseline.add_argument("--report", help="new JSON path for trusted timing/search measurements")
    return p


def run(args) -> int:
    command = args.command
    if command == "version":
        emit({"format": "sherlock-benchmark-version-1", **runtime_info()})
        return 0
    if command == "rules":
        emit(rules_document())
        return 0
    if command in ("generate", "corpus"):
        count = 1 if command == "generate" else args.count
        if not 1 <= count <= MAX_CORPUS or args.seed + count - 1 > 2**64 - 1:
            raise ModelError("invalid corpus count or seed range")
        output = Path(args.output) if command == "corpus" else None
        if output is not None and output.exists():
            raise ModelError("corpus output directory already exists")
        results = [generate(args.seed + i, rows=args.rows, columns=args.columns,
                            max_nodes=args.max_nodes, max_clues=args.max_clues, prune=not args.no_prune)
                   for i in range(count)]
        if command == "generate":
            if args.manifest:
                write_new(args.manifest, {**results[0].manifest, "runtime": runtime_info()})
            emit(results[0].puzzle.to_dict())
        else:
            puzzles = [result.puzzle for result in results]
            identity = corpus_id(puzzles)  # Refuse duplicate instances rather than masking them.
            output.mkdir(mode=0o700, parents=False, exist_ok=False)
            public = output / "public.jsonl"
            with public.open("xb") as stream:
                for puzzle in puzzles:
                    stream.write(canonical_bytes(puzzle.to_dict()) + b"\n")
            manifest = {"format": "sherlock-benchmark-private-corpus-1", "corpus_id": identity,
                        "runtime": runtime_info(), "records": [r.manifest for r in results],
                        "warning": "Organizer data: includes seeds and solutions. Do not give this file to agents."}
            write_new(output / "private-manifest.json", manifest)
            emit({"format": "sherlock-benchmark-corpus-receipt-1", "corpus_id": identity,
                  "puzzles": count, "public": str(public), "private_manifest": str(output / "private-manifest.json"),
                  "runtime": runtime_info()})
        return 0
    if command in ("solve", "analyze", "verify", "serve"):
        if args.puzzle == "-" and (command == "serve" or getattr(args, "submission", None) == "-"):
            raise ModelError("stdin may supply only one input; serve requires a puzzle file")
        puzzle = read_puzzle(args.puzzle)
        if command == "verify":
            verdict = verify(puzzle, read_document(args.submission))
            emit({"format": "sherlock-benchmark-verification-1", **verdict, "runtime": runtime_info()})
            return 0 if verdict["accepted"] else 1
        if command == "serve":
            if args.state == "-":
                raise ModelError("serve requires a checkpoint file, leaving stdin for requests")
            session = Session.from_checkpoint(puzzle, read_document(args.state)) if args.state else Session(puzzle)
            for raw in iter(lambda: sys.stdin.buffer.readline(MAX_JSON_BYTES + 1), b""):
                try:
                    if len(raw) > MAX_JSON_BYTES:
                        raise ModelError("session request exceeds the input size limit")
                    response = session.apply(loads_json(raw))
                    emit({"ok": True, "result": response})
                except ModelError as exc:
                    emit({"ok": False, "error": {"code": "invalid_request", "message": str(exc)}})
                    if len(raw) > MAX_JSON_BYTES:
                        return 2
            return 0
        result = solve(puzzle, max_nodes=args.max_nodes)
        if command == "solve" and args.submission:
            if not result.solutions:
                emit({"format": "sherlock-benchmark-error-1", "error": "no_solution_found",
                      "analysis": result.to_dict(), "challenge_id": puzzle.challenge_id})
                return 4 if result.status == "unknown" else 1
            emit(make_submission(puzzle, result.solutions[0]))
            return 0
        doc = {"format": "sherlock-benchmark-analysis-1", "challenge_id": puzzle.challenge_id,
               **result.to_dict(), "runtime": runtime_info()}
        if command == "solve" and result.solutions:
            doc["submission"] = make_submission(puzzle, result.solutions[0])
        emit(doc)
        return 4 if result.status == "unknown" else 0
    if command == "evaluate":
        if args.corpus == args.submissions == "-":
            raise ModelError("stdin may supply only one input")
        puzzles = read_corpus(args.corpus)
        responses = read_jsonl(args.submissions, tolerate_bad=True)
        report = evaluate(puzzles, responses)
        report["runtime"] = runtime_info()
        report["parse_errors"] = [{"submission_index": i, "message": r.message}
                                  for i, r in enumerate(responses)
                                  if isinstance(r, _ParseFailure)]
        emit(report)
        return 0
    if command == "baseline":
        puzzles = read_corpus(args.corpus)
        records, submissions = [], []
        for puzzle in puzzles:
            start = time.perf_counter()
            result = solve(puzzle, max_nodes=args.max_nodes)
            duration = time.perf_counter() - start
            records.append({"challenge_id": puzzle.challenge_id, **result.to_dict(), "elapsed_seconds": duration})
            if result.solutions:
                submissions.append(make_submission(puzzle, result.solutions[0]))
        if args.report:
            write_new(args.report, {"format": "sherlock-benchmark-baseline-1", "runtime": runtime_info(),
                                   "corpus_id": corpus_id(puzzles), "records": records,
                                   "evaluation": evaluate(puzzles, submissions)})
        for submission in submissions:
            emit(submission)
        return 0 if len(submissions) == len(puzzles) else 4
    raise ModelError("unknown command")


def main(argv=None):
    try:
        return run(parser().parse_args(argv))
    except GenerationError as exc:
        emit({"format": "sherlock-benchmark-error-1", "error": "generation_exhausted",
              "message": str(exc), "nodes": exc.nodes, "solver_calls": exc.solver_calls,
              "runtime": runtime_info()})
        return 4
    except (ModelError, OSError) as exc:
        emit({"format": "sherlock-benchmark-error-1", "error": "invalid_input_or_io",
              "message": str(exc)})
        return 2
    except KeyboardInterrupt:
        emit({"format": "sherlock-benchmark-error-1", "error": "interrupted"})
        return 130
