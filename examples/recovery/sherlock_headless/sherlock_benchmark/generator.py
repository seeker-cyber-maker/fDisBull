"""Deterministic generation with an explicit, solver-certified uniqueness gate.

Only ``GenerationResult.puzzle`` is public. The separate manifest contains the
seed and witness and belongs to the benchmark organizer, not the agent. This is
an authored generator; its seeds and difficulty have no original-game mapping.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Clue, MAX_CLUES, ModelError, Puzzle, check_assignment, clue_holds, integer
from .solver import MAX_SOLVE_NODES, SOLVER_ID, SOLVER_VERSION, Board, SolveResult, solve

GENERATOR_ID = "sherlock-python-constraints"
GENERATOR_VERSION = 1
SOLVE_SLICE_NODES = 2_000
_MASK64 = (1 << 64) - 1


class GenerationError(RuntimeError):
    """A bounded generation failed; it carries no publishable puzzle."""

    def __init__(self, message: str, *, nodes: int = 0, solver_calls: int = 0):
        super().__init__(message)
        self.nodes = nodes
        self.solver_calls = solver_calls


@dataclass(frozen=True)
class GenerationResult:
    puzzle: Puzzle
    manifest: dict


class _SplitMix64:
    """Fixed unsigned arithmetic and modulo sampling, part of generator v1."""

    def __init__(self, seed: int):
        self.state = seed & _MASK64

    def word(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & _MASK64
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _MASK64
        return value ^ (value >> 31)

    def below(self, bound: int) -> int:
        return self.word() % bound

    def shuffle(self, values: list) -> None:
        for i in range(len(values) - 1, 0, -1):
            j = self.below(i + 1)
            values[i], values[j] = values[j], values[i]


def _positions(board: Board, columns: int) -> tuple[int, ...]:
    result = [0] * (len(board) * columns)
    for row, values in enumerate(board):
        for col, item in enumerate(values):
            result[row * columns + item] = col
    return tuple(result)


def _canonical(kind: str, objects: tuple[int, ...]) -> Clue:
    if kind in ("same_column", "not_same_column", "next_to"):
        objects = tuple(sorted(objects))
    elif kind == "same_column_excluding":
        objects = (*sorted(objects[:2]), objects[2])
    elif kind == "xor_same_column":
        objects = (objects[0], *sorted(objects[1:]))
    elif kind in ("between", "not_between") and objects[0] > objects[2]:
        objects = (objects[2], objects[1], objects[0])
    return Clue(kind, objects)


def _make_pool(board: Board, positions: tuple[int, ...], rng: _SplitMix64) -> list[Clue]:
    """All useful binary truths plus a bounded sample of triple truths.

    All within-row ordering pairs are included. Consequently every different
    permutation board violates some candidate, even if the sampled triple pool
    is unhelpful. This does not guarantee completion within the caller's budget.
    Sampling is by fixed loops and stable integer operations, not set order.
    """
    rows, columns = len(board), len(board[0])
    objects = rows * columns
    pool: list[Clue] = []
    seen = set()

    def add(kind: str, operands: tuple[int, ...]) -> None:
        clue = _canonical(kind, operands)
        if clue not in seen:
            seen.add(clue)
            pool.append(clue)

    for a in range(objects):
        for b in range(a + 1, objects):
            pa, pb = positions[a], positions[b]
            if a // columns != b // columns:
                add("same_column" if pa == pb else "not_same_column", (a, b))
            if abs(pa - pb) == 1:
                add("next_to", (a, b))
            if pa < pb:
                add("left_of", (a, b))
            elif pb < pa:
                add("left_of", (b, a))

    def obj(row: int, col: int) -> int:
        return row * columns + board[row][col]

    def other_column(col: int) -> int:
        chosen = rng.below(columns - 1)
        return chosen + (chosen >= col)

    # Eight samples per object per triple relation keep the 8x8 pool bounded.
    for _ in range(8 * objects):
        selected_rows = list(range(rows))
        rng.shuffle(selected_rows)
        col = rng.below(columns)
        a, b, c = (obj(row, col) for row in selected_rows[:3])
        add("same_column", (a, b, c))
        excluded = obj(rng.below(rows), other_column(col))
        add("same_column_excluding", (a, b, excluded))
        # Canonicalize the two OR arms by ID; neither is always the true arm.
        add("xor_same_column", (a, b, excluded))

        left = rng.below(columns - 2)
        outer_a = obj(rng.below(rows), left)
        outer_c = obj(rng.below(rows), left + 2)
        middle = obj(rng.below(rows), left + 1)
        add("between", (outer_a, middle, outer_c))
        nonmiddle = [candidate for candidate in range(objects)
                     if positions[candidate] != left + 1 and candidate not in (outer_a, outer_c)]
        add("not_between", (outer_a, nonmiddle[rng.below(len(nonmiddle))], outer_c))
    return pool


def generate(seed: int, *, rows: int = 6, columns: int = 6,
             max_nodes: int = 100_000, max_clues: int = 256,
             prune: bool = True) -> GenerationResult:
    """Generate one unique puzzle, or raise without returning a candidate.

    Determinism covers seed, generator version, dimensions and all limits. The
    total node budget is shared by construction, optional pruning and a final
    check. Individual checks use a fixed bounded slice. An inconclusive pruning
    check keeps its clue; an exhausted total budget fails generation.

    Clues are not promised to be minimum in number, nor to match Sherlock's
    Type A/B deduction guarantees or human difficulty. No original data is used.
    """
    integer(seed, "seed", 0, _MASK64)
    integer(rows, "rows", 3, 8)
    integer(columns, "columns", 3, 8)
    integer(max_nodes, "max_nodes", 0, MAX_SOLVE_NODES)
    integer(max_clues, "max_clues", 0, MAX_CLUES)
    if type(prune) is not bool:
        raise ModelError("prune must be a boolean")
    if max_nodes == 0 or max_clues == 0:
        raise GenerationError("generation budget permits no work")

    rng = _SplitMix64(seed ^ 0x534845524C4F434B)
    target_rows = []
    for _ in range(rows):
        items = list(range(columns))
        rng.shuffle(items)
        target_rows.append(tuple(items))
    target: Board = tuple(target_rows)
    target_positions = _positions(target, columns)
    pool = _make_pool(target, target_positions, rng)
    active = set()
    clues: list[Clue] = []
    type_counts: dict[tuple, int] = {}
    nodes = calls = 0

    def fail(message: str) -> None:
        raise GenerationError(message, nodes=nodes, solver_calls=calls)

    def analyze(candidate: Puzzle) -> SolveResult:
        nonlocal nodes, calls
        if nodes == max_nodes:
            fail("total solver-node budget exhausted; no puzzle returned")
        result = solve(candidate, max_nodes=min(SOLVE_SLICE_NODES, max_nodes - nodes))
        nodes += result.nodes
        calls += 1
        if result.status == "unsat":
            raise RuntimeError("a target-true generation candidate became unsatisfiable")
        return result

    information = {"same_column": 20, "not_same_column": 2,
                   "same_column_excluding": 24, "xor_same_column": 12,
                   "next_to": 12, "left_of": 8, "between": 26, "not_between": 18}
    while True:
        puzzle = Puzzle(rows, columns, tuple(clues))
        result = analyze(puzzle)
        if result.status == "unique":
            if result.solutions[0] != target:
                raise RuntimeError("unique generated completion differs from the true target")
            break
        if len(clues) == max_clues:
            fail("clue limit reached before uniqueness was proved")
        if nodes == max_nodes:
            fail("total solver-node budget exhausted before uniqueness was proved")
        alternatives = [_positions(board, columns) for board in result.solutions if board != target]
        best = -1
        best_score = -1_000_000
        for i, clue in enumerate(pool):
            if i in active:
                continue
            cuts = sum(not clue_holds(clue.kind, tuple(pos[obj] for obj in clue.objects))
                       for pos in alternatives)
            if alternatives and not cuts:
                continue
            bucket = (clue.kind, len(clue.objects))
            count = type_counts.get(bucket, 0)
            score = (128 * cuts + (32 if count == 0 else 0) + information[clue.kind]
                     + (10 if bucket == ("same_column", 3) else 0)
                     - 2 * count + rng.below(16))
            if score > best_score:
                best, best_score = i, score
        if best < 0:
            fail("candidate pool exhausted before uniqueness was proved")
        selected = pool[best]
        active.add(best)
        clues.append(selected)
        bucket = (selected.kind, len(selected.objects))
        type_counts[bucket] = type_counts.get(bucket, 0) + 1

    construction_clues = len(clues)
    removed = unknown_prunes = 0
    if prune:
        for index in range(len(clues) - 1, -1, -1):
            candidate = Puzzle(rows, columns, tuple(clues[:index] + clues[index + 1:]))
            result = analyze(candidate)
            if result.status == "unique":
                del clues[index]
                removed += 1
            elif result.status == "unknown":
                unknown_prunes += 1
            if nodes == max_nodes:
                fail("total solver-node budget exhausted during pruning; no puzzle returned")

    puzzle = Puzzle(rows, columns, tuple(clues))
    final = analyze(puzzle)
    if final.status != "unique":
        fail("final uniqueness check was inconclusive; no puzzle returned")
    if final.solutions != (target,) or not check_assignment(puzzle, target)["accepted"]:
        raise RuntimeError("generated witness failed final direct verification")
    manifest = {
        "format": "sherlock-benchmark-generation-1",
        "challenge_id": puzzle.challenge_id,
        "generator": GENERATOR_ID,
        "generator_version": GENERATOR_VERSION,
        "seed": str(seed),
        "rng": "splitmix64-modulo-fisher-yates-v1",
        "rows": rows,
        "columns": columns,
        "limits": {"max_nodes": max_nodes, "max_clues": max_clues,
                   "prune": prune, "solve_slice_nodes": SOLVE_SLICE_NODES},
        "solver": SOLVER_ID,
        "solver_version": SOLVER_VERSION,
        "total_nodes": nodes,
        "solver_calls": calls,
        "construction_clues": construction_clues,
        "removed_clues": removed,
        "inconclusive_pruning_checks": unknown_prunes,
        "final_check": final.to_dict(),
        "witness": [list(row) for row in target],
        "direct_verification": "accepted",
        "difficulty_claim": "unique only; no Type A/B or human-difficulty certification",
    }
    return GenerationResult(puzzle, manifest)
