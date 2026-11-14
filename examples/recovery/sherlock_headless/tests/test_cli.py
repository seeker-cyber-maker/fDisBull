"""Black-box CLI tests at the same JSON seam an agent consumes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sherlock_benchmark.model import Given, Puzzle, make_submission


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.puzzle = Puzzle(3, 3, givens=tuple(Given(r * 3 + i, i) for r in range(3) for i in range(3)))
        self.path = self.root / "puzzle.json"
        self.path.write_text(json.dumps(self.puzzle.to_dict()))

    def cli(self, *args, data=None):
        run = subprocess.run([sys.executable, "-m", "sherlock_benchmark", *map(str, args)],
                             input=data, capture_output=True, text=True, timeout=30)
        self.assertEqual(run.stderr, "", run.stderr)
        return run.returncode, [json.loads(line) for line in run.stdout.splitlines()]

    def test_solve_verify_and_zero_budget(self):
        code, docs = self.cli("solve", "--puzzle", self.path, "--submission")
        self.assertEqual(code, 0)
        code, verdict = self.cli("verify", "--puzzle", self.path, "--submission", "-", data=json.dumps(docs[0]))
        self.assertEqual(code, 0)
        self.assertTrue(verdict[0]["accepted"])
        code, docs = self.cli("analyze", "--puzzle", self.path, "--max-nodes", "0")
        self.assertEqual(code, 4)
        self.assertEqual(docs[0]["status"], "unknown")

    def test_invalid_input_and_wrong_identity(self):
        code, docs = self.cli("generate", "--seed", "-1")
        self.assertEqual(code, 2)
        answer = make_submission(self.puzzle, [[0, 1, 2]] * 3)
        answer["challenge_id"] = "sha256:" + "0" * 64
        code, docs = self.cli("verify", "--puzzle", self.path, "--submission", "-", data=json.dumps(answer))
        self.assertEqual(code, 1)
        self.assertEqual(docs[0]["status"], "wrong_challenge")
        code, docs = self.cli("verify", "--puzzle", "-", "--submission", "-", data="")
        self.assertEqual(code, 2)

    def test_session_rejects_bad_request_then_remains_usable(self):
        code, docs = self.cli("serve", "--puzzle", self.path,
                              data='{"op":"eliminate","row":0,"column":0,"item":0}\n{"op":"observe"}\n')
        self.assertEqual(code, 0)
        self.assertFalse(docs[0]["ok"])
        self.assertTrue(docs[1]["result"]["won"])

    def test_small_corpus_baseline_and_bad_json_accounting(self):
        output = self.root / "corpus"
        code, docs = self.cli("corpus", "--seed", "21", "--rows", "3", "--columns", "3",
                              "--count", "2", "--output", output)
        self.assertEqual(code, 0, docs)
        public = output / "public.jsonl"
        text = public.read_text()
        for private in ('"seed"', '"solution"', '"witness"'):
            self.assertNotIn(private, text)
        report = self.root / "baseline.json"
        code, submissions = self.cli("baseline", "--corpus", public, "--report", report)
        self.assertEqual(code, 0, submissions)
        response_path = self.root / "answers.jsonl"
        response_path.write_text("\n".join(json.dumps(x) for x in submissions) + "\n")
        code, docs = self.cli("evaluate", "--corpus", public, "--submissions", response_path)
        self.assertEqual(code, 0)
        self.assertEqual(docs[0]["summary"]["solved_at_1"], 1)
        response_path.write_text(json.dumps(submissions[0]) + "\n{invalid JSON\n")
        code, docs = self.cli("evaluate", "--corpus", public, "--submissions", response_path)
        self.assertEqual(code, 0)
        self.assertEqual(docs[0]["summary"]["solved_at_1"], 0.5)
        self.assertEqual(docs[0]["summary"]["malformed_entries"], 1)
        self.assertEqual(len(docs[0]["parse_errors"]), 1)

    def test_manifest_exclusive_write_and_budget_failure(self):
        manifest = self.root / "manifest.json"
        manifest.write_text("preserve me")
        code, docs = self.cli("generate", "--seed", "42", "--rows", "3", "--columns", "3", "--manifest", manifest)
        self.assertEqual(code, 2)
        self.assertEqual(manifest.read_text(), "preserve me")
        code, docs = self.cli("generate", "--seed", "42", "--max-nodes", "0")
        self.assertEqual(code, 4)
        self.assertNotIn("clues", docs[0])


if __name__ == "__main__":
    unittest.main()
