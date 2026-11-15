"""Bounded exact search over the public relational puzzle, using only Python.

This follows the authored native replica's all-different / clue-support design.
It is not an execution or translation of the original Sherlock program. Search
counts at most two completions. A node limit is a work budget, not a wall clock
timeout, and an exhausted search never certifies uniqueness or unsatisfiability.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import product
from typing import Sequence

from .model import ModelError, Puzzle, check_assignment, clue_holds, integer

SOLVER_ID = "sherlock-python-csp"
SOLVER_VERSION = 1
MAX_SOLVE_NODES = 10_000_000
Board = tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class SolveResult:
    status: str
    solutions: tuple[Board, ...]
    nodes: int
    max_nodes: int

    @property
    def solution_count(self) -> int:
        return len(self.solutions)

    def to_dict(self, include_solutions: bool = False) -> dict:
        result = {
            "solver": SOLVER_ID,
            "solver_version": SOLVER_VERSION,
            "status": self.status,
            "solution_count": self.solution_count,
            "solution_count_is_lower_bound": self.status in ("multiple", "unknown"),
            "exhaustive": self.status in ("unique", "unsat"),
            "nodes": self.nodes,
            "max_nodes": self.max_nodes,
        }
        if include_solutions:
            result["solutions"] = [[list(row) for row in board] for board in self.solutions]
        return result


@lru_cache(maxsize=8192)
def _row_support(domains: tuple[int, ...]) -> tuple[int, ...] | None:
    """Return every edge supported by a perfect matching of this one row.

    Forward reachable used-column masks followed by a backward pass give exact
    all-different support in O(width * 2**width), with width at most eight. Cache
    only immutable masks: no puzzle, solution or caller state is retained here.
    """
    if any(mask == 0 for mask in domains):
        return None
    forward = [{0}]
    for domain in domains:
        following = set()
        for used in forward[-1]:
            available = domain & ~used
            while available:
                bit = available & -available
                available ^= bit
                following.add(used | bit)
        if not following:
            return None
        forward.append(following)

    feasible = {(1 << len(domains)) - 1}
    supported = [0] * len(domains)
    for i in range(len(domains) - 1, -1, -1):
        previous = set()
        for used in forward[i]:
            available = domains[i] & ~used
            while available:
                bit = available & -available
                available ^= bit
                if used | bit in feasible:
                    supported[i] |= bit
                    previous.add(used)
        feasible = previous
    return tuple(supported)


@lru_cache(maxsize=2048)
def _clue_tuples(columns: int, kind: str, row_pattern: tuple[int, ...]) -> tuple:
    """Compile at most 8**3 position tuples, including row inequality."""
    tuples = []
    for positions in product(range(columns), repeat=len(row_pattern)):
        if any(row_pattern[i] == row_pattern[j] and positions[i] == positions[j]
               for i in range(len(row_pattern)) for j in range(i)):
            continue
        if clue_holds(kind, positions):
            tuples.append(tuple(1 << col for col in positions))
    return tuple(tuples)


def _compile(puzzle: Puzzle) -> tuple[list, list[int]]:
    constraints = []
    degree = [0] * puzzle.object_count
    for clue in puzzle.clues:
        # Normalize category labels solely for the tuple cache key.
        labels = {}
        pattern = []
        for obj in clue.objects:
            row = obj // puzzle.columns
            if row not in labels:
                labels[row] = len(labels)
            pattern.append(labels[row])
            degree[obj] += 1
        constraints.append((clue.objects, _clue_tuples(puzzle.columns, clue.kind, tuple(pattern))))
    return constraints, degree


def _propagate(domains: list[int], rows: int, columns: int, constraints: list) -> bool:
    changed = True
    while changed:
        changed = False
        for start in range(0, rows * columns, columns):
            old = tuple(domains[start:start + columns])
            supported = _row_support(old)
            if supported is None:
                return False
            if supported != old:
                domains[start:start + columns] = supported
                changed = True

        for objects, allowed in constraints:
            a, b = objects[:2]
            da, db = domains[a], domains[b]
            sa = sb = 0
            if len(objects) == 2:
                for ta, tb in allowed:
                    if da & ta and db & tb:
                        sa |= ta
                        sb |= tb
                if not sa or not sb:
                    return False
                if sa != da or sb != db:
                    domains[a], domains[b] = sa, sb
                    changed = True
            else:
                c = objects[2]
                dc = domains[c]
                sc = 0
                for ta, tb, tc in allowed:
                    if da & ta and db & tb and dc & tc:
                        sa |= ta
                        sb |= tb
                        sc |= tc
                if not sa or not sb or not sc:
                    return False
                if sa != da or sb != db or sc != dc:
                    domains[a], domains[b], domains[c] = sa, sb, sc
                    changed = True
    return True


def solve(puzzle: Puzzle, *, max_nodes: int = 100_000,
          domains: Sequence[int] | None = None) -> SolveResult:
    """Classify public constraints, retaining at most two satisfying boards.

    ``domains[obj]`` is an optional bitmask of allowed columns. Zero domains
    describe a contradictory state, not malformed input. Givens are intersected
    with these masks. The caller's sequence and puzzle are never mutated.

    Every entered search state costs one node, including a root contradiction
    or fully specified solution. A zero budget therefore returns ``unknown``
    without deciding even a trivial instance. ``multiple`` means at least two;
    ``unknown`` may carry zero or one independently verified witness.
    """
    if not isinstance(puzzle, Puzzle):
        raise ModelError("solve requires a Puzzle")
    integer(max_nodes, "max_nodes", 0, MAX_SOLVE_NODES)
    all_columns = (1 << puzzle.columns) - 1
    if domains is None:
        initial = [all_columns] * puzzle.object_count
    else:
        if not isinstance(domains, (tuple, list)) or len(domains) != puzzle.object_count:
            raise ModelError("domains must be an array with one mask per object")
        initial = [integer(mask, "domain mask", 0, all_columns) for mask in domains]
    for given in puzzle.givens:
        initial[given.object] &= 1 << given.column
    if max_nodes == 0:
        return SolveResult("unknown", (), 0, max_nodes)

    constraints, degree = _compile(puzzle)
    solutions: list[Board] = []
    nodes = 0
    exhausted = False

    def search(current: list[int]) -> None:
        nonlocal nodes, exhausted
        if len(solutions) >= 2 or exhausted:
            return
        if nodes == max_nodes:
            exhausted = True
            return
        nodes += 1
        if not _propagate(current, puzzle.rows, puzzle.columns, constraints):
            return

        selected = -1
        priority = (puzzle.columns + 1, 1)
        for obj, mask in enumerate(current):
            count = mask.bit_count()
            candidate = (count, -degree[obj])
            if count > 1 and candidate < priority:
                priority, selected = candidate, obj
        if selected == -1:
            answer = [[-1] * puzzle.columns for _ in range(puzzle.rows)]
            for obj, mask in enumerate(current):
                answer[obj // puzzle.columns][mask.bit_length() - 1] = obj % puzzle.columns
            board = tuple(tuple(row) for row in answer)
            if not check_assignment(puzzle, board)["accepted"]:
                raise RuntimeError("solver completion failed direct assignment verification")
            solutions.append(board)
            return

        available = current[selected]
        while available:
            bit = available & -available
            available ^= bit
            child = current.copy()
            child[selected] = bit
            search(child)
            if len(solutions) >= 2 or exhausted:
                return

    search(initial)
    status = ("multiple" if len(solutions) >= 2 else "unknown" if exhausted else
              "unique" if solutions else "unsat")
    return SolveResult(status, tuple(solutions), nodes, max_nodes)
