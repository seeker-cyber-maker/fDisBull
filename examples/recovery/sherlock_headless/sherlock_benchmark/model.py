"""Public constraint contract and direct answer verifier, independent of search.

Objects are row-local items encoded as ``row * columns + item``. Boards use
``board[row][column] = item``. Every row is a permutation; columns have no
all-different rule across categories. See RULES.md for documentary provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any, Sequence

PUZZLE_FORMAT = "sherlock-benchmark-puzzle-1"
SUBMISSION_FORMAT = "sherlock-benchmark-submission-1"
RULESET = "sherlock7-relations-v1"
MAX_CLUES = 512
MAX_JSON_BYTES = 4 * 1024 * 1024
ARITIES = {
    "same_column": (2, 3),
    "not_same_column": (2,),
    "same_column_excluding": (3,),
    "xor_same_column": (3,),
    "next_to": (2,),
    "left_of": (2,),
    "between": (3,),
    "not_between": (3,),
}
PREDICATES = {
    "same_column": "all operand columns are equal (two or three objects)",
    "not_same_column": "a != b",
    "same_column_excluding": "a == b and c != a (c is the marked/excluded object)",
    "xor_same_column": "(a == b) XOR (a == c), exactly one equality",
    "next_to": "abs(a - b) == 1",
    "left_of": "a < b (any positive distance)",
    "between": "abs(a - c) == 2 and 2*b == a+c",
    "not_between": "abs(a - c) == 2 and 2*b != a+c",
}


class ModelError(ValueError):
    """Invalid public document or model. A valid but unsatisfiable puzzle is allowed."""


def integer(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ModelError(f"{name} must be an integer in {low}..{high}")
    return value


def exact_keys(value: Any, keys: set[str], name: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise ModelError(f"{name} must have exactly these fields: {', '.join(sorted(keys))}")
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def loads_json(data: str | bytes) -> Any:
    """Strict bounded JSON reader: no duplicate keys, NaN, infinity or BOM."""
    if not isinstance(data, (str, bytes)):
        raise ModelError("JSON input must be text or bytes")
    try:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        if len(raw) > MAX_JSON_BYTES:
            raise ModelError(f"JSON input exceeds {MAX_JSON_BYTES} bytes")
        text = raw.decode("utf-8")
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ModelError(f"duplicate JSON key: {key}")
                result[key] = value
            return result
        def bad_constant(value):
            raise ModelError(f"non-finite JSON number: {value}")
        def finite_float(value):
            number = float(value)
            if not math.isfinite(number):
                raise ModelError("JSON number overflows a finite float")
            return number
        return json.loads(text, object_pairs_hook=pairs, parse_constant=bad_constant,
                          parse_float=finite_float)
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, ModelError):
            raise
        raise ModelError(f"invalid JSON: {exc}") from exc


@dataclass(frozen=True)
class Clue:
    kind: str
    objects: tuple[int, ...]

    def __post_init__(self):
        if type(self.kind) is not str or self.kind not in ARITIES:
            raise ModelError("unknown clue kind")
        if not isinstance(self.objects, (tuple, list)):
            raise ModelError("clue objects must be an array")
        object.__setattr__(self, "objects", tuple(self.objects))
        if len(self.objects) not in ARITIES[self.kind]:
            raise ModelError(f"wrong operand count for {self.kind}")
        for obj in self.objects:
            integer(obj, "clue object", 0, 63)
        if len(set(self.objects)) != len(self.objects):
            raise ModelError("a clue cannot repeat the same object")

    def to_dict(self) -> dict:
        return {"kind": self.kind, "objects": list(self.objects)}


@dataclass(frozen=True)
class Given:
    object: int
    column: int

    def __post_init__(self):
        integer(self.object, "given object", 0, 63)
        integer(self.column, "given column", 0, 7)

    def to_dict(self) -> dict:
        return {"object": self.object, "column": self.column}


@dataclass(frozen=True)
class Puzzle:
    rows: int
    columns: int
    clues: tuple[Clue, ...] = ()
    givens: tuple[Given, ...] = ()

    def __post_init__(self):
        integer(self.rows, "rows", 3, 8)
        integer(self.columns, "columns", 3, 8)
        if not isinstance(self.clues, (tuple, list)) or not isinstance(self.givens, (tuple, list)):
            raise ModelError("clues and givens must be arrays")
        object.__setattr__(self, "clues", tuple(self.clues))
        object.__setattr__(self, "givens", tuple(self.givens))
        if len(self.clues) > MAX_CLUES:
            raise ModelError(f"at most {MAX_CLUES} clues are supported")
        if len(self.givens) > self.object_count:
            raise ModelError("too many givens")
        seen = set()
        for clue in self.clues:
            if not isinstance(clue, Clue):
                raise ModelError("clues must contain Clue values")
            for obj in clue.objects:
                integer(obj, "clue object", 0, self.object_count - 1)
        for given in self.givens:
            if not isinstance(given, Given):
                raise ModelError("givens must contain Given values")
            integer(given.object, "given object", 0, self.object_count - 1)
            integer(given.column, "given column", 0, self.columns - 1)
            if given.object in seen:
                raise ModelError("duplicate given object")
            seen.add(given.object)

    @property
    def object_count(self) -> int:
        return self.rows * self.columns

    def _spec(self) -> dict:
        return {"format": PUZZLE_FORMAT, "ruleset": RULESET, "rows": self.rows,
                "columns": self.columns, "clues": [c.to_dict() for c in self.clues],
                "givens": [g.to_dict() for g in self.givens]}

    @property
    def challenge_id(self) -> str:
        return "sha256:" + sha256(canonical_bytes(self._spec())).hexdigest()

    def to_dict(self) -> dict:
        return {**self._spec(), "challenge_id": self.challenge_id}

    @classmethod
    def from_dict(cls, value: Any) -> Puzzle:
        exact_keys(value, {"format", "ruleset", "rows", "columns", "clues", "givens", "challenge_id"},
                   "puzzle")
        if value["format"] != PUZZLE_FORMAT or value["ruleset"] != RULESET:
            raise ModelError("unsupported puzzle format or ruleset")
        if type(value["clues"]) is not list or type(value["givens"]) is not list:
            raise ModelError("clues and givens must be JSON arrays")
        clues = []
        for c in value["clues"]:
            exact_keys(c, {"kind", "objects"}, "clue")
            if type(c["objects"]) is not list:
                raise ModelError("clue objects must be a JSON array")
            clues.append(Clue(c["kind"], c["objects"]))
        givens = []
        for g in value["givens"]:
            exact_keys(g, {"object", "column"}, "given")
            givens.append(Given(g["object"], g["column"]))
        puzzle = cls(value["rows"], value["columns"], tuple(clues), tuple(givens))
        if type(value["challenge_id"]) is not str or value["challenge_id"] != puzzle.challenge_id:
            raise ModelError("challenge_id does not match the canonical public puzzle")
        return puzzle


def clue_holds(kind: str, positions: Sequence[int]) -> bool:
    """Evaluate a documented predicate over operand columns, without search."""
    if kind not in ARITIES or len(positions) not in ARITIES[kind]:
        raise ModelError("invalid predicate or arity")
    a, b = positions[:2]
    if kind == "same_column":
        return all(p == a for p in positions[1:])
    if kind == "not_same_column":
        return a != b
    if kind == "next_to":
        return abs(a - b) == 1
    if kind == "left_of":
        return a < b
    c = positions[2]
    if kind == "same_column_excluding":
        return a == b and c != a
    if kind == "xor_same_column":
        return (a == b) != (a == c)
    if kind == "between":
        return abs(a - c) == 2 and 2 * b == a + c
    return abs(a - c) == 2 and 2 * b != a + c


def check_assignment(puzzle: Puzzle, board: Any) -> dict:
    """Accept any satisfying complete board, even for nonunique puzzles.

    This routine never imports the solver, generator, seed or a witness answer.
    """
    def invalid(message):
        return {"accepted": False, "status": "invalid_board", "violations": [message]}
    if not isinstance(board, (list, tuple)) or len(board) != puzzle.rows:
        return invalid(f"board must contain {puzzle.rows} rows")
    pos = [0] * puzzle.object_count
    for r, row in enumerate(board):
        if not isinstance(row, (list, tuple)) or len(row) != puzzle.columns:
            return invalid(f"row {r} must contain {puzzle.columns} items")
        if any(type(v) is not int or not 0 <= v < puzzle.columns for v in row):
            return invalid(f"row {r} has a non-integer or out-of-range item")
        if len(set(row)) != puzzle.columns:
            return invalid(f"row {r} is not a permutation")
        for col, item in enumerate(row):
            pos[r * puzzle.columns + item] = col
    violations = []
    for i, given in enumerate(puzzle.givens):
        if pos[given.object] != given.column:
            violations.append({"kind": "given", "index": i, "object": given.object,
                               "expected_column": given.column, "actual_column": pos[given.object]})
    for i, clue in enumerate(puzzle.clues):
        values = tuple(pos[obj] for obj in clue.objects)
        if not clue_holds(clue.kind, values):
            violations.append({"kind": "clue", "index": i, "relation": clue.kind,
                               "objects": list(clue.objects), "columns": list(values)})
    return {"accepted": not violations, "status": "unsatisfied" if violations else "accepted",
            "violations": violations}


def make_submission(puzzle: Puzzle, board: Sequence[Sequence[int]]) -> dict:
    return {"format": SUBMISSION_FORMAT, "challenge_id": puzzle.challenge_id,
            "board": [list(row) for row in board]}


def verify(puzzle: Puzzle, submission: Any) -> dict:
    base = {"challenge_id": puzzle.challenge_id}
    try:
        exact_keys(submission, {"format", "challenge_id", "board"}, "submission")
        if submission["format"] != SUBMISSION_FORMAT or type(submission["challenge_id"]) is not str:
            raise ModelError("unsupported submission format or invalid challenge_id")
    except ModelError as exc:
        return {**base, "accepted": False, "status": "invalid_submission", "violations": [str(exc)]}
    if submission["challenge_id"] != puzzle.challenge_id:
        return {**base, "accepted": False, "status": "wrong_challenge",
                "violations": ["submission belongs to a different challenge"]}
    return {**base, **check_assignment(puzzle, submission["board"])}


def rules_document() -> dict:
    return {"format": "sherlock-benchmark-rules-1", "ruleset": RULESET,
            "dimensions": {"rows": [3, 8], "columns": [3, 8]},
            "object_id": "row * columns + item; all indices are zero based",
            "board": "board[row][column] is the row-local item ID; each row is a permutation",
            "column_rule": "different categories may use the same item number in a column",
            "predicate_arguments": "a, b, c are the board columns of objects in their listed order",
            "clues": {k: {"arity": list(ARITIES[k]), "predicate": v} for k, v in PREDICATES.items()},
            "submission": {"format": SUBMISSION_FORMAT, "challenge_id": "copy from public puzzle",
                           "board": "rectangular array of row-local item IDs"}}
