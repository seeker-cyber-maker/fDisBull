"""Search budget, domain and result-contract tests. Rule oracles are separate."""

import unittest

from sherlock_benchmark.model import Clue, Given, ModelError, Puzzle, check_assignment
from sherlock_benchmark.solver import MAX_SOLVE_NODES, solve


class SolverTests(unittest.TestCase):
    def test_empty_is_multiple_and_witnesses_are_distinct(self):
        puzzle = Puzzle(3, 3)
        result = solve(puzzle)
        self.assertEqual(result.status, "multiple")
        self.assertEqual(result.solution_count, 2)
        self.assertNotEqual(result.solutions[0], result.solutions[1])
        for board in result.solutions:
            self.assertTrue(check_assignment(puzzle, board)["accepted"])
        self.assertNotIn("solutions", result.to_dict())
        self.assertEqual(len(result.to_dict(include_solutions=True)["solutions"]), 2)
        self.assertTrue(result.to_dict()["solution_count_is_lower_bound"])

    def test_zero_budget_does_not_decide_even_complete_board(self):
        puzzle = Puzzle(3, 3, givens=tuple(Given(obj, obj % 3) for obj in range(9)))
        result = solve(puzzle, max_nodes=0)
        self.assertEqual((result.status, result.nodes, result.solution_count), ("unknown", 0, 0))
        result = solve(puzzle, max_nodes=1)
        self.assertEqual((result.status, result.nodes, result.solution_count), ("unique", 1, 1))
        self.assertEqual(result.solutions[0], ((0, 1, 2),) * 3)
        self.assertTrue(result.to_dict()["exhaustive"])

    def test_budget_exhaustion_retains_witness_without_claiming_unique(self):
        # There are 6**3 possible row-permutation boards. Deterministic DFS
        # enters the first completion at node seven, then needs another node.
        puzzle = Puzzle(3, 3)
        result = solve(puzzle, max_nodes=7)
        self.assertEqual((result.status, result.nodes, result.solution_count), ("unknown", 7, 1))
        self.assertTrue(check_assignment(puzzle, result.solutions[0])["accepted"])
        self.assertFalse(result.to_dict()["exhaustive"])
        self.assertTrue(result.to_dict()["solution_count_is_lower_bound"])
        self.assertEqual(solve(puzzle, max_nodes=8).status, "multiple")

    def test_contradictory_givens_and_same_row_clues(self):
        candidates = [
            Puzzle(3, 3, givens=(Given(0, 0), Given(1, 0))),
            Puzzle(3, 3, clues=(Clue("same_column", (0, 1)),)),
            Puzzle(3, 3, clues=(Clue("same_column", (0, 3, 1)),)),
            Puzzle(3, 3, clues=(Clue("left_of", (0, 1)), Clue("left_of", (1, 0)))),
        ]
        for puzzle in candidates:
            with self.subTest(puzzle=puzzle):
                result = solve(puzzle)
                self.assertEqual((result.status, result.solution_count), ("unsat", 0))
                self.assertTrue(result.to_dict()["exhaustive"])

    def test_optional_domains_are_intersected_without_mutation(self):
        puzzle = Puzzle(3, 3, givens=(Given(0, 1),))
        domains = [1 << (obj % 3) for obj in range(9)]
        before = domains.copy()
        self.assertEqual(solve(puzzle, domains=domains).status, "unsat")
        self.assertEqual(domains, before)
        domains[0], domains[1] = 2, 1
        result = solve(puzzle, domains=domains)
        self.assertEqual(result.status, "unique")
        self.assertEqual(result.solutions[0][0], (1, 0, 2))
        self.assertTrue(check_assignment(puzzle, result.solutions[0])["accepted"])

    def test_all_different_hall_contradiction(self):
        # Three objects constrained to only two columns cannot form a row,
        # although no individual domain is empty or a singleton.
        puzzle = Puzzle(3, 4)
        domains = [15] * 12
        domains[:3] = [3, 3, 3]
        result = solve(puzzle, domains=domains, max_nodes=1)
        self.assertEqual((result.status, result.nodes), ("unsat", 1))

    def test_domains_retain_only_supported_row_matchings(self):
        puzzle = Puzzle(3, 4, givens=tuple(Given(obj, obj % 4) for obj in range(4, 12)))
        domains = [3, 3, 15, 12] + [15] * 8
        result = solve(puzzle, domains=domains)
        self.assertEqual(result.status, "multiple")
        for board in result.solutions:
            self.assertEqual(set(board[0][:2]), {0, 1})
            self.assertEqual(set(board[0][2:]), {2, 3})

    def test_invalid_budget_and_domain_inputs(self):
        puzzle = Puzzle(3, 3)
        for value in (True, False, -1, 1.0, "1", MAX_SOLVE_NODES + 1):
            with self.subTest(value=value), self.assertRaises(ModelError):
                solve(puzzle, max_nodes=value)
        for domains in ([7] * 8, [True] * 9, [-1] * 9, [8] * 9, "777777777"):
            with self.subTest(domains=domains), self.assertRaises(ModelError):
                solve(puzzle, domains=domains)
        with self.assertRaises(ModelError):
            solve({"rows": 3, "columns": 3})


if __name__ == "__main__":
    unittest.main()
