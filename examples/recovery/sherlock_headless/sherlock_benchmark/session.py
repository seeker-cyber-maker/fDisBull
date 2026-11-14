"""Headless candidate play. Moves express a player's choices, not oracle hints.

Automatic housekeeping uses only a row's one-to-one assignment, never the
hidden construction witness or search. Wrong deductions can survive until
submission. What-if failure is a player's assertion, not a proof certificate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import ModelError, Puzzle, check_assignment, exact_keys, integer, make_submission, verify

HISTORY_LIMIT = 256
MAX_ACTIONS = 2**53 - 1
STATE_FORMAT = "sherlock-benchmark-state-1"


class StateError(ModelError):
    pass


def _housekeep(puzzle: Puzzle, source) -> tuple[int, ...]:
    d = list(source)
    n = puzzle.columns
    changed = True
    while changed:
        changed = False
        for r in range(puzzle.rows):
            start = r * n
            fixed = 0
            for mask in d[start:start + n]:
                if not mask:
                    raise StateError("move leaves an item with no possible column")
                if mask & (mask - 1) == 0:
                    if fixed & mask:
                        raise StateError("move places two items in one cell")
                    fixed |= mask
            for i in range(start, start + n):
                if d[i] & (d[i] - 1):
                    m = d[i] & ~fixed
                    if not m:
                        raise StateError("move removes all positions of an item")
                    if m != d[i]:
                        d[i], changed = m, True
            for col in range(n):
                owners = [i for i in range(start, start + n) if d[i] & (1 << col)]
                if not owners:
                    raise StateError("move leaves a cell with no candidates")
                if len(owners) == 1 and d[owners[0]] != 1 << col:
                    d[owners[0]], changed = 1 << col, True
    return tuple(d)


@dataclass(frozen=True)
class Frame:
    domains: tuple[int, ...]
    # (pre-assumption domains, assumed object, assumed column); never nested.
    assumption: tuple[tuple[int, ...], int, int] | None = None

    def to_dict(self):
        assumption = None
        if self.assumption is not None:
            before, obj, column = self.assumption
            assumption = {"before": list(before), "object": obj, "column": column}
        return {"domains": list(self.domains), "assumption": assumption}


class Session:
    def __init__(self, puzzle: Puzzle):
        self.puzzle = puzzle
        initial = [(1 << puzzle.columns) - 1] * puzzle.object_count
        for g in puzzle.givens:
            initial[g.object] = 1 << g.column
        self.initial = Frame(_housekeep(puzzle, initial))
        self.frame = self.initial
        self.undo_stack: list[Frame] = []
        self.redo_stack: list[Frame] = []
        self.actions = 0

    def _record(self, frame: Frame):
        if frame != self.frame:
            self.undo_stack.append(self.frame)
            del self.undo_stack[:-HISTORY_LIMIT]
            self.redo_stack.clear()
            self.frame = frame
        self.actions += 1

    def _target(self, request):
        row = integer(request["row"], "row", 0, self.puzzle.rows - 1)
        col = integer(request["column"], "column", 0, self.puzzle.columns - 1)
        item = integer(request["item"], "item", 0, self.puzzle.columns - 1)
        return row * self.puzzle.columns + item, col

    def _change(self, domains, obj, col, place):
        d = list(domains)
        if place and not d[obj] & (1 << col):
            raise StateError("cannot place an eliminated candidate")
        d[obj] = (1 << col) if place else d[obj] & ~(1 << col)
        return _housekeep(self.puzzle, d)

    def board(self):
        if any(mask & (mask - 1) for mask in self.frame.domains):
            return None
        board = [[0] * self.puzzle.columns for _ in range(self.puzzle.rows)]
        for obj, mask in enumerate(self.frame.domains):
            row, item = divmod(obj, self.puzzle.columns)
            board[row][mask.bit_length() - 1] = item
        return board

    def observe(self) -> dict:
        n = self.puzzle.columns
        board = self.board()
        correct = board is not None and check_assignment(self.puzzle, board)["accepted"]
        assumption = self.frame.assumption
        return {"format": "sherlock-benchmark-observation-1", "puzzle": self.puzzle.to_dict(),
                "candidates": [[[item for item in range(n)
                                  if self.frame.domains[r * n + item] & (1 << c)]
                                 for c in range(n)] for r in range(self.puzzle.rows)],
                "board": board, "complete": board is not None,
                "won": bool(correct and assumption is None),
                "what_if": None if assumption is None else {"object": assumption[1], "column": assumption[2]},
                "actions": self.actions, "undo_depth": len(self.undo_stack),
                "redo_depth": len(self.redo_stack), "history_limit": HISTORY_LIMIT,
                "assistance": "row_housekeeping_only"}

    def checkpoint(self) -> dict:
        return {"format": STATE_FORMAT, "challenge_id": self.puzzle.challenge_id,
                "frame": self.frame.to_dict(), "undo": [f.to_dict() for f in self.undo_stack],
                "redo": [f.to_dict() for f in self.redo_stack], "actions": self.actions}

    @classmethod
    def from_checkpoint(cls, puzzle: Puzzle, data: Any) -> Session:
        exact_keys(data, {"format", "challenge_id", "frame", "undo", "redo", "actions"}, "checkpoint")
        if data["format"] != STATE_FORMAT or data["challenge_id"] != puzzle.challenge_id:
            raise StateError("checkpoint format or challenge identity mismatch")
        session = cls(puzzle)
        def domains(value):
            if type(value) is not list or len(value) != puzzle.object_count:
                raise StateError("checkpoint domains have the wrong shape")
            d = tuple(integer(v, "domain", 1, (1 << puzzle.columns) - 1) for v in value)
            for g in puzzle.givens:
                if d[g.object] != 1 << g.column:
                    raise StateError("checkpoint changes a given")
            if _housekeep(puzzle, d) != d:
                raise StateError("checkpoint is not in canonical housekeeping state")
            return d
        def frame(value):
            exact_keys(value, {"domains", "assumption"}, "frame")
            d = domains(value["domains"])
            a = value["assumption"]
            if a is None:
                return Frame(d)
            exact_keys(a, {"before", "object", "column"}, "assumption")
            before = domains(a["before"])
            obj = integer(a["object"], "assumed object", 0, puzzle.object_count - 1)
            col = integer(a["column"], "assumed column", 0, puzzle.columns - 1)
            if before[obj] == 1 << col or not before[obj] & (1 << col) or d[obj] != 1 << col:
                raise StateError("checkpoint assumption does not match its state")
            if any(new & ~old for old, new in zip(before, d)):
                raise StateError("checkpoint reintroduces a candidate inside what-if")
            return Frame(d, (before, obj, col))
        def stack(value):
            if type(value) is not list or len(value) > HISTORY_LIMIT:
                raise StateError("checkpoint history exceeds its limit")
            return [frame(v) for v in value]
        session.frame = frame(data["frame"])
        session.undo_stack = stack(data["undo"])
        session.redo_stack = stack(data["redo"])
        session.actions = integer(data["actions"], "actions", 0, MAX_ACTIONS)
        return session

    def apply(self, request: Any) -> dict:
        if type(request) is not dict or type(request.get("op")) is not str:
            raise StateError("request must be an object with a string op")
        op = request["op"]
        if op in {"place", "eliminate", "what_if_enter", "what_if_exit", "what_if_keep",
                  "what_if_fail", "what_if_next", "undo", "redo", "reset"} and self.actions == MAX_ACTIONS:
            raise StateError("session action counter exhausted; start a new session")
        if op in {"place", "eliminate", "what_if_enter"}:
            exact_keys(request, {"op", "row", "column", "item"}, "move")
            obj, col = self._target(request)
            if op == "what_if_enter":
                if self.frame.assumption is not None:
                    raise StateError("nested what-if is not supported")
                if self.frame.domains[obj] == 1 << col:
                    raise StateError("what-if requires an unresolved candidate")
                d = self._change(self.frame.domains, obj, col, True)
                new = Frame(d, (self.frame.domains, obj, col))
            else:
                new = Frame(self._change(self.frame.domains, obj, col, op == "place"), self.frame.assumption)
            self._record(new)
        elif op in {"what_if_exit", "what_if_keep", "what_if_fail", "what_if_next"}:
            exact_keys(request, {"op"}, "move")
            if self.frame.assumption is None:
                raise StateError("there is no active what-if")
            before, obj, col = self.frame.assumption
            if op == "what_if_exit":
                new = Frame(before)
            elif op == "what_if_keep":
                new = Frame(self.frame.domains)
            elif op == "what_if_fail":
                new = Frame(self._change(before, obj, col, False))
            else:
                n = self.puzzle.columns
                row, item = divmod(obj, n)
                choices = [i for i in range(n) if before[row * n + i] & (1 << col)]
                next_item = choices[(choices.index(item) + 1) % len(choices)]
                next_obj = row * n + next_item
                new = Frame(self._change(before, next_obj, col, True), (before, next_obj, col))
            self._record(new)
        elif op in {"undo", "redo"}:
            exact_keys(request, {"op"}, "move")
            source, dest = (self.undo_stack, self.redo_stack) if op == "undo" else (self.redo_stack, self.undo_stack)
            if not source:
                raise StateError(f"nothing to {op}")
            dest.append(self.frame)
            del dest[:-HISTORY_LIMIT]
            self.frame = source.pop()
            self.actions += 1
        elif op == "reset":
            exact_keys(request, {"op"}, "move")
            self._record(self.initial)
        elif op == "observe":
            exact_keys(request, {"op"}, "request")
        elif op == "checkpoint":
            exact_keys(request, {"op"}, "request")
            return self.checkpoint()
        elif op == "submit":
            exact_keys(request, {"op", "submission"}, "request")
            return {"format": "sherlock-benchmark-verification-1", **verify(self.puzzle, request["submission"])}
        elif op == "submit_state":
            exact_keys(request, {"op"}, "request")
            if self.frame.assumption is not None:
                raise StateError("keep or exit what-if before submitting the current state")
            board = self.board()
            if board is None:
                raise StateError("current state is incomplete")
            return {"format": "sherlock-benchmark-verification-1", **verify(self.puzzle, make_submission(self.puzzle, board))}
        else:
            raise StateError(f"unknown operation: {op}")
        return self.observe()
