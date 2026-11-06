"""Deterministic grading of submitted documents against a trusted corpus.

This module evaluates data.  It never launches candidate programs or treats
candidate-provided scores, timings, puzzles, or answers as ground truth.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
import hashlib
import json
from typing import Any

from .model import ModelError, Puzzle, verify


EVALUATOR_VERSION = 1
EVALUATION_FORMAT = "sherlock-benchmark-evaluation-1"
CORPUS_FORMAT = "sherlock-benchmark-corpus-1"
_RESULT_STATUSES = (
    "solved",
    "missing",
    "duplicate",
    "invalid_submission",
    "wrong_challenge",
    "invalid_board",
    "unsatisfied",
)


def _corpus(puzzles: Sequence[Puzzle]) -> tuple[Puzzle, ...]:
    if not isinstance(puzzles, Sequence) or isinstance(puzzles, (str, bytes, bytearray)):
        raise ModelError("The trusted corpus must be a sequence of puzzles.")
    result = tuple(puzzles)
    if not result:
        raise ModelError("The trusted corpus must contain at least one puzzle.")
    seen: set[str] = set()
    for index, puzzle in enumerate(result):
        if not isinstance(puzzle, Puzzle):
            raise ModelError(f"Trusted corpus entry {index} is not a Puzzle.")
        if puzzle.challenge_id in seen:
            raise ModelError(f"The trusted corpus repeats challenge {puzzle.challenge_id}.")
        seen.add(puzzle.challenge_id)
    return result


def _corpus_id(puzzles: Sequence[Puzzle]) -> str:
    # Corpus order is intentionally not part of its identity.  Each challenge
    # already commits to its dimensions, complete public rules, and clues.
    document = {
        "format": CORPUS_FORMAT,
        "challenge_ids": sorted(puzzle.challenge_id for puzzle in puzzles),
    }
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode("ascii")).hexdigest()


def corpus_id(puzzles: Sequence[Puzzle]) -> str:
    """Return an order-independent content ID for a nonempty unique corpus.

    This detects repeated public challenge documents; it does not detect every
    puzzle made equivalent by item/category renaming or geometric symmetry.
    """
    return _corpus_id(_corpus(puzzles))


def evaluate(puzzles: Sequence[Puzzle], submissions: Sequence[object]) -> dict[str, Any]:
    """Grade one submitted document per trusted challenge.

    Every trusted puzzle stays in the solved-at-one denominator.  Two or more
    documents naming the same challenge fail that challenge as ``duplicate``,
    even if one document contains a correct answer.  Entries without a usable
    challenge ID and entries for unknown IDs are reported separately.

    ``malformed_entries`` counts entries that cannot be routed to a challenge
    because they are not JSON objects or lack a nonempty string challenge ID.
    A routed document with a malformed envelope is ``invalid_submission`` in
    the puzzle results.  Submissions are parsed JSON values, not JSON text;
    callers must use the package's strict JSON reader for external files.
    """
    trusted = _corpus(puzzles)
    if not isinstance(submissions, Sequence) or isinstance(submissions, (str, bytes, bytearray)):
        raise ModelError("Submissions must be a sequence of parsed JSON documents.")

    expected = {puzzle.challenge_id: puzzle for puzzle in trusted}
    indexed: dict[str, list[tuple[int, object]]] = defaultdict(list)
    errors: list[dict[str, Any]] = []
    malformed_entries = 0
    unknown_entries = 0
    for index, submission in enumerate(submissions):
        challenge_id = submission.get("challenge_id") if isinstance(submission, dict) else None
        if not isinstance(challenge_id, str) or not challenge_id:
            malformed_entries += 1
            errors.append({
                "submission_index": index,
                "code": "malformed_entry",
                "message": "A submission must be an object with a nonempty string challenge_id.",
            })
        elif challenge_id not in expected:
            unknown_entries += 1
            errors.append({
                "submission_index": index,
                "code": "unknown_challenge",
                "challenge_id": challenge_id,
                "message": "This challenge_id is not in the trusted corpus.",
            })
        else:
            indexed[challenge_id].append((index, submission))

    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    grouped: dict[tuple[int, int], Counter[str]] = defaultdict(Counter)
    duplicate_entries = 0
    for puzzle in trusted:
        entries = indexed[puzzle.challenge_id]
        result: dict[str, Any] = {
            "challenge_id": puzzle.challenge_id,
            "rows": puzzle.rows,
            "columns": puzzle.columns,
            "submission_indices": [index for index, _ in entries],
            "accepted": False,
        }
        if not entries:
            result["status"] = "missing"
        elif len(entries) > 1:
            result["status"] = "duplicate"
            duplicate_entries += len(entries)
            for index, _ in entries:
                errors.append({
                    "submission_index": index,
                    "code": "duplicate_submission",
                    "challenge_id": puzzle.challenge_id,
                    "message": "Multiple responses named this challenge; none receives credit.",
                })
        else:
            index, submission = entries[0]
            verdict = verify(puzzle, submission)
            status = "solved" if verdict["accepted"] else verdict["status"]
            if status not in _RESULT_STATUSES:
                raise RuntimeError(f"Verifier returned unsupported status: {status!r}")
            result.update(status=status, accepted=verdict["accepted"], verification=verdict)
            if status == "invalid_submission":
                errors.append({
                    "submission_index": index,
                    "code": "invalid_submission",
                    "challenge_id": puzzle.challenge_id,
                    "message": "The submission envelope does not match the submission format.",
                })
        counts[result["status"]] += 1
        grouped[(puzzle.rows, puzzle.columns)]["puzzles"] += 1
        grouped[(puzzle.rows, puzzle.columns)][result["status"]] += 1
        results.append(result)

    by_dimensions = []
    for (rows, columns), group in sorted(grouped.items()):
        by_dimensions.append({
            "rows": rows,
            "columns": columns,
            "puzzles": group["puzzles"],
            **{status: group[status] for status in _RESULT_STATUSES},
            "solved_at_1": group["solved"] / group["puzzles"],
        })

    return {
        "format": EVALUATION_FORMAT,
        "evaluator_version": EVALUATOR_VERSION,
        "corpus_id": _corpus_id(trusted),
        "summary": {
            "puzzles": len(trusted),
            "submissions": len(submissions),
            **{status: counts[status] for status in _RESULT_STATUSES},
            "solved_at_1": counts["solved"] / len(trusted),
            "malformed_entries": malformed_entries,
            "unknown_entries": unknown_entries,
            "duplicate_entries": duplicate_entries,
        },
        "results": results,
        "by_dimensions": by_dimensions,
        "submission_errors": sorted(errors, key=lambda entry: entry["submission_index"]),
        "policy": {
            "attempts_per_puzzle": 1,
            "duplicate_responses": "fail_challenge",
            "missing_responses": "fail_challenge",
            "unknown_responses": "reported_without_changing_denominator",
            "candidate_metrics": "not_used",
        },
    }
