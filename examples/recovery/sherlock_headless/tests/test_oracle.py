"""Independent finite oracle for the documented relational rules.

Expected answers come from complete row-permutation enumeration and predicates
written here, not from the production verifier, solver, or generator witness.
The authored fixtures contain no original Sherlock puzzle or media data.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
from itertools import permutations, product
import json
import random
import unittest

from sherlock_benchmark.generator import GenerationError, generate
from sherlock_benchmark.model import (
    Clue,
    Given,
    MAX_JSON_BYTES,
    ModelError,
    Puzzle,
    check_assignment,
    loads_json,
    make_submission,
    verify,
)
from sherlock_benchmark.solver import solve


Board = tuple[tuple[int, ...], ...]


def reference_holds(kind: str, places: tuple[int, ...]) -> bool:
    """Arithmetic specification, without any production helper calls."""
    if kind == "same_column":
        return len(set(places)) == 1
    if kind == "not_same_column":
        return len(set(places)) == 2
    if kind == "same_column_excluding":
        return len(set(places[:2])) == 1 and len(set(places)) == 2
    if kind == "xor_same_column":
        return sum(place == places[0] for place in places[1:]) == 1
    if kind == "next_to":
        lower, upper = sorted(places)
        return upper - lower == 1
    if kind == "left_of":
        return places[1] - places[0] > 0
    if kind == "between":
        return set((places[0], places[2])) == {places[1] - 1, places[1] + 1}
    if kind == "not_between":
        lower, upper = sorted((places[0], places[2]))
        return upper - lower == 2 and places[1] != lower + 1
    raise AssertionError(f"The test oracle has no rule for {kind!r}")


def reference_accepts(puzzle: Puzzle, board: Board) -> bool:
    def column(obj: int) -> int:
        row, item = divmod(obj, puzzle.columns)
        return board[row].index(item)

    return (
        all(column(g.object) == g.column for g in puzzle.givens)
        and all(reference_holds(c.kind, tuple(column(obj) for obj in c.objects))
                for c in puzzle.clues)
    )


def all_boards(rows: int, columns: int):
    return product(tuple(permutations(range(columns))), repeat=rows)


def oracle_solutions(puzzle: Puzzle) -> set[Board]:
    return {board for board in all_boards(puzzle.rows, puzzle.columns)
            if reference_accepts(puzzle, board)}


SINGLE_CLUES = (
    Clue("same_column", (0, 3)),
    Clue("same_column", (0, 3, 6)),
    Clue("not_same_column", (0, 3)),
    Clue("same_column_excluding", (0, 3, 6)),
    Clue("xor_same_column", (0, 3, 6)),
    Clue("next_to", (0, 3)),
    Clue("left_of", (0, 3)),
    Clue("between", (0, 3, 6)),
    Clue("not_between", (0, 3, 6)),
)


class RuleTruthTableTests(unittest.TestCase):
    def test_handwritten_true_and_false_cases(self) -> None:
        # Positions in this board: 0/5/7 are in the middle column;
        # 2/4/6 are on the left; 1/3/8 are on the right.
        board = ((2, 0, 1), (1, 2, 0), (0, 1, 2))
        cases = [
            ("same_column", (0, 5), True),
            ("same_column", (0, 3), False),
            ("same_column", (0, 5, 7), True),
            ("same_column", (0, 5, 6), False),
            ("not_same_column", (0, 3), True),
            ("not_same_column", (0, 5), False),
            ("same_column_excluding", (0, 5, 6), True),
            ("same_column_excluding", (0, 3, 6), False),
            ("same_column_excluding", (0, 5, 7), False),
            ("xor_same_column", (0, 5, 6), True),
            ("xor_same_column", (0, 3, 7), True),
            ("xor_same_column", (0, 5, 7), False),
            ("xor_same_column", (0, 3, 6), False),
            ("next_to", (6, 0), True),
            ("next_to", (6, 3), False),  # Edges do not wrap around.
            ("next_to", (0, 5), False),
            ("left_of", (6, 3), True),  # Any distance, not only adjacent.
            ("left_of", (3, 6), False),
            ("left_of", (0, 5), False),
            ("between", (6, 0, 3), True),
            ("between", (3, 0, 6), True),  # Either orientation.
            ("between", (6, 3, 0), False),
            ("not_between", (6, 4, 3), True),
            ("not_between", (6, 0, 3), False),
            ("not_between", (6, 0, 7), False),  # Outer distance still must be two.
        ]
        for kind, objects, expected in cases:
            with self.subTest(kind=kind, objects=objects, expected=expected):
                puzzle = Puzzle(3, 3, clues=(Clue(kind, objects),))
                self.assertEqual(reference_accepts(puzzle, board), expected)
                self.assertEqual(check_assignment(puzzle, board)["accepted"], expected)

    def test_between_requires_consecutive_columns_on_wider_boards(self) -> None:
        # a=0, b=7 and c=14 occupy columns 0, 2, 4 respectively.
        board = (tuple(range(5)),) * 3
        for kind in ("between", "not_between"):
            puzzle = Puzzle(3, 5, clues=(Clue(kind, (0, 7, 14)),))
            with self.subTest(kind=kind):
                self.assertFalse(reference_accepts(puzzle, board))
                self.assertFalse(check_assignment(puzzle, board)["accepted"])

    def test_verifier_matches_every_tiny_board_for_every_rule(self) -> None:
        boards = tuple(all_boards(3, 3))
        self.assertEqual(len(boards), 216)
        for clue in SINGLE_CLUES:
            puzzle = Puzzle(3, 3, clues=(clue,))
            for board in boards:
                with self.subTest(clue=clue, board=board):
                    self.assertEqual(check_assignment(puzzle, board)["accepted"],
                                     reference_accepts(puzzle, board))

    def test_columns_do_not_have_a_cross_category_all_different_rule(self) -> None:
        for rows, columns in ((3, 3), (3, 8), (8, 3), (8, 8)):
            with self.subTest(rows=rows, columns=columns):
                puzzle = Puzzle(rows, columns)
                board = [list(range(columns)) for _ in range(rows)]
                self.assertTrue(check_assignment(puzzle, board)["accepted"])


class ExhaustiveSolverTests(unittest.TestCase):
    def assert_matches_oracle(self, puzzle: Puzzle) -> None:
        expected = oracle_solutions(puzzle)
        result = solve(puzzle, max_nodes=100_000)
        status = "unsat" if not expected else "unique" if len(expected) == 1 else "multiple"
        self.assertEqual(result.status, status)
        self.assertEqual(result.solution_count, min(2, len(expected)))
        witnesses = set(result.solutions)
        self.assertEqual(len(witnesses), result.solution_count)
        self.assertTrue(witnesses.issubset(expected))
        if len(expected) <= 1:
            self.assertEqual(witnesses, expected)

    def test_all_relations_match_exhaustive_solution_counts(self) -> None:
        for clue in SINGLE_CLUES:
            with self.subTest(clue=clue):
                self.assert_matches_oracle(Puzzle(3, 3, clues=(clue,)))

    def test_unique_ambiguous_and_unsatisfiable_examples(self) -> None:
        cases = (
            Puzzle(3, 3),
            Puzzle(3, 3, clues=(Clue("same_column", (0, 3)),
                                Clue("not_same_column", (0, 3)))),
            Puzzle(3, 3, givens=(Given(2, 0), Given(0, 1), Given(4, 0),
                                 Given(5, 1), Given(6, 0), Given(7, 1))),
            # Different items of the same row cannot occupy the same column.
            Puzzle(3, 3, givens=(Given(0, 0), Given(1, 0))),
            # Same-row objects in a clue still obey the row permutation.
            Puzzle(3, 3, clues=(Clue("same_column", (0, 1)),)),
            Puzzle(3, 3, clues=(Clue("next_to", (0, 1)),)),
        )
        for puzzle in cases:
            with self.subTest(puzzle=puzzle.to_dict()):
                self.assert_matches_oracle(puzzle)

    def test_mixed_constraints_against_independent_enumeration(self) -> None:
        pool = SINGLE_CLUES + (
            Clue("left_of", (1, 8)),
            Clue("next_to", (2, 7)),
            Clue("between", (4, 1, 8)),
            Clue("not_between", (2, 7, 5)),
            Clue("xor_same_column", (4, 6, 2)),
            Clue("same_column_excluding", (1, 8, 4)),
            Clue("not_same_column", (2, 6)),
            Clue("same_column", (2, 4, 7)),
        )
        rng = random.Random(20261106)
        for index in range(24):
            clues = tuple(rng.sample(pool, 1 + index % 6))
            givens = () if index % 3 else (Given(rng.randrange(9), rng.randrange(3)),)
            with self.subTest(index=index, clues=clues, givens=givens):
                self.assert_matches_oracle(Puzzle(3, 3, clues=clues, givens=givens))

    def test_rectangular_board_uses_columns_for_object_encoding(self) -> None:
        self.assert_matches_oracle(Puzzle(4, 3, clues=(
            Clue("same_column", (0, 9)),
            Clue("between", (1, 4, 11)),
            Clue("xor_same_column", (6, 4, 10)),
        )))
        board = ((3, 1, 0, 2), (2, 0, 3, 1), (1, 3, 2, 0))
        givens = tuple(Given(row * 4 + item, column)
                       for row, values in enumerate(board)
                       for column, item in enumerate(values))
        puzzle = Puzzle(3, 4, givens=givens)
        result = solve(puzzle)
        self.assertEqual(result.status, "unique")
        self.assertEqual(result.solutions, (board,))

    def test_budget_exhaustion_is_unknown_including_trivially_solvable_input(self) -> None:
        for puzzle in (Puzzle(3, 3), Puzzle(3, 3, givens=tuple(
                Given(row * 3 + item, item) for row in range(3) for item in range(3)))):
            with self.subTest(puzzle=puzzle):
                result = solve(puzzle, max_nodes=0)
                self.assertEqual(result.status, "unknown")
                self.assertEqual(result.solution_count, 0)
                self.assertEqual(result.nodes, 0)
                self.assertNotIn("solutions", result.to_dict())

    def test_candidate_domains_match_independent_board_filtering(self) -> None:
        puzzle = Puzzle(3, 3, clues=(Clue("next_to", (0, 3)),))
        full = [0b111] * 9
        cases = [
            full,
            [0] + full[1:],
            [0b001, 0b001, 0b111] + full[3:],
            [0b001, 0b110, 0b110, 0b010] + full[4:],
            [0b001, 0b010, 0b100, 0b010, 0b100, 0b001,
             0b100, 0b001, 0b010],
        ]
        for domains in cases:
            with self.subTest(domains=domains):
                expected = {
                    board for board in oracle_solutions(puzzle)
                    if all(domains[obj] & (1 << board[obj // 3].index(obj % 3))
                           for obj in range(9))
                }
                result = solve(puzzle, domains=domains)
                status = "unsat" if not expected else "unique" if len(expected) == 1 else "multiple"
                self.assertEqual(result.status, status)
                self.assertEqual(result.solution_count, min(2, len(expected)))
                self.assertTrue(set(result.solutions).issubset(expected))


class IndependentGenerationTests(unittest.TestCase):
    def test_generated_tiny_puzzles_are_unique_without_trusting_the_witness(self) -> None:
        for seed in (0, 1, 42, 20261106, 2**64 - 1):
            with self.subTest(seed=seed):
                generated = generate(seed, rows=3, columns=3)
                expected = oracle_solutions(generated.puzzle)
                self.assertEqual(len(expected), 1)
                witness = tuple(tuple(row) for row in generated.manifest["witness"])
                self.assertIn(witness, expected)
                self.assertEqual(generated.manifest["challenge_id"], generated.puzzle.challenge_id)
                self.assertEqual(generated.manifest["final_check"]["status"], "unique")

    def test_same_seed_reproduces_public_puzzle_and_private_manifest(self) -> None:
        first = generate(20261106, rows=3, columns=3)
        second = generate(20261106, rows=3, columns=3)
        self.assertEqual(first.puzzle.to_dict(), second.puzzle.to_dict())
        self.assertEqual(first.manifest, second.manifest)

    def test_public_export_contains_no_private_generation_fields(self) -> None:
        generated = generate(17, rows=3, columns=3)
        public = generated.puzzle.to_dict()

        def check(value):
            if isinstance(value, dict):
                self.assertTrue(set(value).isdisjoint({
                    "seed", "witness", "solution", "solutions", "manifest",
                    "rng", "rng_state", "total_nodes", "solver_calls",
                }))
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)

        check(public)
        # The private manifest is a separate artifact, not a mutable part of
        # the public puzzle's identity or constraint objects.
        generated.manifest["witness"][0][0] = 999
        generated.manifest["seed"] = "changed"
        self.assertEqual(generated.puzzle.to_dict(), public)
        self.assertEqual(Puzzle.from_dict(public), generated.puzzle)

    def test_exhausted_generation_has_no_publishable_puzzle(self) -> None:
        with self.assertRaises(GenerationError):
            generate(0, rows=3, columns=3, max_nodes=0)


class PublicIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.puzzle = Puzzle(3, 3, clues=(Clue("left_of", (0, 5)),), givens=(Given(6, 0),))
        self.board = [list(range(3)) for _ in range(3)]

    def test_public_id_matches_independent_canonical_hash_and_roundtrip(self) -> None:
        public = self.puzzle.to_dict()
        identifier = public.pop("challenge_id")
        encoded = json.dumps(public, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        expected = "sha256:" + hashlib.sha256(encoded.encode("ascii")).hexdigest()
        self.assertEqual(identifier, expected)
        document = self.puzzle.to_dict()
        restored = Puzzle.from_dict(loads_json(json.dumps(document, indent=2)))
        self.assertEqual(restored, self.puzzle)
        self.assertEqual(set(document), {
            "format", "ruleset", "rows", "columns", "clues", "givens", "challenge_id",
        })

    def test_tampered_clue_given_dimension_and_identity_are_rejected(self) -> None:
        changes = (
            lambda value: value["clues"][0].update(kind="next_to"),
            lambda value: value["clues"][0].update(objects=[0, 4]),
            lambda value: value["givens"][0].update(column=1),
            lambda value: value.update(rows=4),
            lambda value: value.update(challenge_id="sha256:" + "0" * 64),
        )
        for change in changes:
            public = self.puzzle.to_dict()
            change(public)
            with self.subTest(document=public):
                with self.assertRaises(ModelError):
                    Puzzle.from_dict(public)

    def test_extra_private_or_authoritative_fields_are_not_public_inputs(self) -> None:
        for key, value in (("seed", 42), ("solution", self.board), ("accepted", True),
                           ("generator", {"seed": 42}), ("metadata", {})):
            public = self.puzzle.to_dict()
            public[key] = value
            with self.subTest(key=key):
                with self.assertRaises(ModelError):
                    Puzzle.from_dict(public)

    def test_verifier_rejects_wrong_challenge_and_does_not_mutate_answer(self) -> None:
        other = Puzzle(3, 3)
        submission = make_submission(other, self.board)
        before = deepcopy(submission)
        verdict = verify(self.puzzle, submission)
        self.assertFalse(verdict["accepted"])
        self.assertEqual(verdict["status"], "wrong_challenge")
        self.assertEqual(verdict["challenge_id"], self.puzzle.challenge_id)
        self.assertEqual(submission, before)

    def test_dimensions_and_indices_are_strict_integers(self) -> None:
        for rows, columns in ((2, 3), (3, 2), (9, 3), (3, 9), (True, 3), (3, False), (3.0, 3)):
            with self.subTest(rows=rows, columns=columns):
                with self.assertRaises(ModelError):
                    Puzzle(rows, columns)
        for malformed in (True, 0.0, "0", None, -1, 3):
            board = deepcopy(self.board)
            board[0][0] = malformed
            with self.subTest(item=malformed):
                self.assertEqual(check_assignment(self.puzzle, board)["status"], "invalid_board")

    def test_unknown_relation_and_bad_operands_are_rejected(self) -> None:
        factories = (
            lambda: Clue("made_up_relation", (0, 3)),
            lambda: Clue("between", (0, 3)),
            lambda: Clue("left_of", (0, 0)),
            lambda: Clue("left_of", (True, 3)),
            lambda: Puzzle(3, 3, clues=(Clue("left_of", (0, 9)),)),
            lambda: Puzzle(3, 3, givens=(Given(0, 3),)),
        )
        for index, factory in enumerate(factories):
            with self.subTest(index=index):
                with self.assertRaises(ModelError):
                    factory()

    def test_strict_json_reader_rejects_ambiguous_or_nonfinite_input(self) -> None:
        malformed = (
            '{"challenge_id":"a","challenge_id":"b"}',
            '{"nested":{"key":0,"key":1}}',
            "NaN", "Infinity", "-Infinity", "1e400", "-1e400",
            "\ufeff{}", "{} {}", "[1,]", "// comment\n{}", b"\xff",
            " " * (MAX_JSON_BYTES + 1),
        )
        for index, document in enumerate(malformed):
            with self.subTest(index=index):
                with self.assertRaises(ModelError):
                    loads_json(document)


if __name__ == "__main__":
    unittest.main()
