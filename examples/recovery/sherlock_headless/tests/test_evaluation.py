"""Contract tests for batch accounting, identity binding, and failed attempts."""

from __future__ import annotations

from copy import deepcopy
import json
import unittest

from sherlock_benchmark.evaluation import corpus_id, evaluate
from sherlock_benchmark.model import Clue, Given, ModelError, Puzzle, make_submission


def board(rows: int = 3, columns: int = 3) -> list[list[int]]:
    return [list(range(columns)) for _ in range(rows)]


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first = Puzzle(3, 3, givens=(Given(0, 0),))
        self.second = Puzzle(3, 3, givens=(Given(0, 1),))
        self.rectangular = Puzzle(4, 3, clues=(Clue("left_of", (0, 5)),))

    def test_missing_puzzles_remain_in_denominator(self) -> None:
        report = evaluate([self.first, self.second], [make_submission(self.first, board())])
        self.assertEqual(report["format"], "sherlock-benchmark-evaluation-1")
        self.assertEqual(report["evaluator_version"], 1)
        self.assertEqual(report["summary"]["puzzles"], 2)
        self.assertEqual(report["summary"]["solved"], 1)
        self.assertEqual(report["summary"]["missing"], 1)
        self.assertEqual(report["summary"]["solved_at_1"], 0.5)
        self.assertEqual([r["status"] for r in report["results"]], ["solved", "missing"])

    def test_duplicate_answer_fails_even_when_first_or_last_is_correct(self) -> None:
        good = make_submission(self.first, board())
        bad = {"challenge_id": self.first.challenge_id, "claimed_score": 1}
        for responses in ([good, bad], [bad, good], [good, deepcopy(good)]):
            with self.subTest(responses=responses):
                report = evaluate([self.first], responses)
                self.assertEqual(report["summary"]["solved"], 0)
                self.assertEqual(report["summary"]["duplicate"], 1)
                self.assertEqual(report["summary"]["duplicate_entries"], 2)
                self.assertEqual(report["results"][0]["status"], "duplicate")
                self.assertEqual(report["results"][0]["submission_indices"], [0, 1])
                self.assertEqual(len(report["submission_errors"]), 2)

    def test_unroutable_and_unknown_entries_are_reported_without_crashing(self) -> None:
        unknown = make_submission(self.second, board())
        submissions = [None, [], "not a document", {}, {"challenge_id": 1},
                       {"challenge_id": ""}, unknown, make_submission(self.first, board())]
        report = evaluate([self.first], submissions)
        self.assertEqual(report["summary"]["submissions"], 8)
        self.assertEqual(report["summary"]["malformed_entries"], 6)
        self.assertEqual(report["summary"]["unknown_entries"], 1)
        self.assertEqual(report["summary"]["solved_at_1"], 1.0)
        self.assertEqual([e["submission_index"] for e in report["submission_errors"]], list(range(7)))

    def test_unknown_answer_does_not_replace_an_expected_puzzle(self) -> None:
        report = evaluate([self.first], [make_submission(self.second, board())])
        self.assertEqual(report["summary"]["puzzles"], 1)
        self.assertEqual(report["summary"]["missing"], 1)
        self.assertEqual(report["summary"]["unknown_entries"], 1)
        self.assertEqual(report["summary"]["solved_at_1"], 0.0)

    def test_envelope_errors_and_board_errors_have_distinct_outcomes(self) -> None:
        cases = [
            ({"challenge_id": self.first.challenge_id}, "invalid_submission"),
            ({**make_submission(self.first, board()), "accepted": True}, "invalid_submission"),
            ({**make_submission(self.first, board()), "board": []}, "invalid_board"),
            ({**make_submission(self.first, board()), "board": [[0, 0, 2]] * 3}, "invalid_board"),
            ({**make_submission(self.first, board()), "board": [[False, 1, 2]] * 3}, "invalid_board"),
            (make_submission(self.second, board()), "unsatisfied"),
        ]
        for submission, expected in cases:
            puzzle = self.second if expected == "unsatisfied" else self.first
            with self.subTest(expected=expected, submission=submission):
                report = evaluate([puzzle], [submission])
                self.assertEqual(report["summary"]["solved"], 0)
                self.assertEqual(report["results"][0]["status"], expected)
                self.assertFalse(report["results"][0]["accepted"])

    def test_candidate_supplied_metrics_cannot_award_credit(self) -> None:
        dishonest = make_submission(self.second, board())
        dishonest.update(score=1, elapsed_seconds=0, accepted=True)
        report = evaluate([self.second], [dishonest])
        self.assertEqual(report["summary"]["solved"], 0)
        self.assertEqual(report["results"][0]["status"], "invalid_submission")
        self.assertNotIn("elapsed_seconds", json.dumps(report))

    def test_any_valid_solution_is_accepted_for_an_ambiguous_puzzle(self) -> None:
        puzzle = Puzzle(3, 3)
        boards = [board(), [[2, 1, 0], [1, 0, 2], [0, 2, 1]]]
        for solution in boards:
            with self.subTest(solution=solution):
                report = evaluate([puzzle], [make_submission(puzzle, solution)])
                self.assertEqual(report["summary"]["solved"], 1)

    def test_dimensions_are_grouped_separately(self) -> None:
        report = evaluate([self.first, self.second, self.rectangular], [
            make_submission(self.rectangular, board(4, 3)),
            make_submission(self.first, board()),
        ])
        self.assertEqual(len(report["by_dimensions"]), 2)
        square, rectangular = report["by_dimensions"]
        self.assertEqual((square["rows"], square["columns"], square["puzzles"]), (3, 3, 2))
        self.assertEqual(square["solved_at_1"], 0.5)
        self.assertEqual((rectangular["rows"], rectangular["columns"], rectangular["puzzles"]), (4, 3, 1))
        self.assertEqual(rectangular["solved_at_1"], 1.0)

    def test_corpus_identity_is_order_independent_and_content_bound(self) -> None:
        one = [self.first, self.rectangular]
        two = [self.rectangular, self.first]
        self.assertEqual(corpus_id(one), corpus_id(two))
        self.assertEqual(corpus_id(one), evaluate(one, [])["corpus_id"])
        self.assertTrue(corpus_id(one).startswith("sha256:"))
        self.assertNotEqual(corpus_id(one), corpus_id([self.second, self.rectangular]))

    def test_trusted_corpus_duplicates_and_empty_corpora_are_errors(self) -> None:
        for puzzles in ([], [self.first, self.first], [self.first, "not a puzzle"]):
            with self.subTest(puzzles=puzzles):
                with self.assertRaises(ModelError):
                    evaluate(puzzles, [])
                with self.assertRaises(ModelError):
                    corpus_id(puzzles)

    def test_submissions_must_be_parsed_documents_sequence(self) -> None:
        for submissions in (None, "[]", {"submissions": []}, b"[]"):
            with self.subTest(submissions=submissions):
                with self.assertRaises(ModelError):
                    evaluate([self.first], submissions)

    def test_evaluation_does_not_mutate_submissions(self) -> None:
        submissions = [make_submission(self.first, board()), {"challenge_id": "unknown"}, None]
        before = deepcopy(submissions)
        report = evaluate([self.first], submissions)
        self.assertEqual(submissions, before)
        self.assertEqual(report, evaluate([self.first], submissions))
        json.dumps(report, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
