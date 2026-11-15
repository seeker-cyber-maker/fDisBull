"""Deterministic, bounded generation and public/private separation tests."""

import json
import unittest

from sherlock_benchmark.generator import (
    GENERATOR_ID, GENERATOR_VERSION, GenerationError, _SplitMix64, generate,
)
from sherlock_benchmark.model import ModelError, Puzzle, check_assignment
from sherlock_benchmark.solver import solve


class GeneratorTests(unittest.TestCase):
    def test_splitmix64_fixed_width_reference_words(self):
        rng = _SplitMix64(0)
        self.assertEqual([rng.word() for _ in range(3)], [
            0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4, 0x06C45D188009454F,
        ])

    def test_reproducible_seed_and_limits(self):
        for seed in (0, 1, 42, (1 << 64) - 1):
            with self.subTest(seed=seed):
                first = generate(seed, rows=3, columns=3)
                second = generate(seed, rows=3, columns=3)
                self.assertEqual(first.puzzle, second.puzzle)
                self.assertEqual(first.manifest, second.manifest)
                self.assertEqual(first.manifest["seed"], str(seed))
                self.assertEqual(first.manifest["generator"], GENERATOR_ID)
                self.assertEqual(first.manifest["generator_version"], GENERATOR_VERSION)

    def test_version_one_public_identity_vector(self):
        # Freeze a development-only seed mapping so algorithm changes require
        # an intentional version/fixture update rather than silent drift.
        generated = generate(42, rows=3, columns=3)
        self.assertEqual(generated.puzzle.challenge_id,
                         "sha256:022fe45f9aed7021398222b47642eebd749778fd74a2429afd450f2591e28975")

    def test_minimum_maximum_and_rectangular_boards_reprove_unique(self):
        for rows, columns in ((3, 3), (3, 8), (8, 3), (6, 6), (8, 8)):
            with self.subTest(rows=rows, columns=columns):
                generated = generate(42, rows=rows, columns=columns)
                puzzle = generated.puzzle
                self.assertEqual((puzzle.rows, puzzle.columns), (rows, columns))
                result = solve(puzzle, max_nodes=100_000)
                self.assertEqual(result.status, "unique")
                self.assertEqual(result.to_dict(include_solutions=True)["solutions"][0],
                                 generated.manifest["witness"])
                self.assertTrue(check_assignment(puzzle, generated.manifest["witness"])["accepted"])
                self.assertEqual(generated.manifest["final_check"]["status"], "unique")
                self.assertLessEqual(generated.manifest["total_nodes"], 100_000)

    def test_public_puzzle_roundtrip_has_no_private_material(self):
        generated = generate(314159, rows=3, columns=4)
        public = json.loads(json.dumps(generated.puzzle.to_dict()))
        self.assertEqual(Puzzle.from_dict(public), generated.puzzle)
        forbidden = {"seed", "witness", "solution", "solutions", "generator", "rng", "limits",
                     "final_check", "total_nodes", "construction_clues"}

        def walk(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & forbidden)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(public)
        self.assertEqual(generated.manifest["challenge_id"], public["challenge_id"])

    def test_generation_budget_exhaustion_returns_no_puzzle(self):
        for nodes, clues in ((0, 256), (1, 256), (100_000, 0), (100_000, 1)):
            with self.subTest(nodes=nodes, clues=clues):
                with self.assertRaises(GenerationError) as context:
                    generate(0, rows=3, columns=3, max_nodes=nodes, max_clues=clues)
                self.assertLessEqual(context.exception.nodes, nodes)
                self.assertFalse(hasattr(context.exception, "puzzle"))

    def test_exact_total_budget_gate_and_pruning_switch(self):
        first = generate(42, rows=3, columns=3)
        needed = first.manifest["total_nodes"]
        exact = generate(42, rows=3, columns=3, max_nodes=needed)
        self.assertEqual(exact.puzzle, first.puzzle)
        self.assertEqual(exact.manifest["total_nodes"], needed)
        with self.assertRaises(GenerationError):
            generate(42, rows=3, columns=3, max_nodes=needed - 1)
        unpruned = generate(42, rows=3, columns=3, prune=False)
        self.assertFalse(unpruned.manifest["limits"]["prune"])
        self.assertEqual(unpruned.manifest["removed_clues"], 0)
        self.assertEqual(solve(unpruned.puzzle).status, "unique")

    def test_strict_generation_inputs(self):
        for seed in (-1, 1 << 64, True, "42", 42.0):
            with self.subTest(seed=seed), self.assertRaises(ModelError):
                generate(seed)
        for kwargs in ({"rows": 2}, {"columns": 9}, {"max_nodes": True},
                       {"max_clues": 513}, {"prune": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ModelError):
                generate(0, **kwargs)


if __name__ == "__main__":
    unittest.main()
