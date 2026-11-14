import copy
import unittest

from sherlock_benchmark.model import Given, ModelError, Puzzle, make_submission
from sherlock_benchmark.session import MAX_ACTIONS, Session


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.puzzle = Puzzle(3, 3)
        self.session = Session(self.puzzle)

    def move(self, op, item=0, row=0, column=0):
        return self.session.apply(dict(op=op, row=row, column=column, item=item))

    def test_placement_housekeeping_and_undo_redo(self):
        initial = self.session.observe()
        now = self.move("place", item=2, column=1)
        self.assertEqual(now["candidates"][0][1], [2])
        self.assertEqual(now["candidates"][0][0], [0, 1])
        self.session.apply({"op": "undo"})
        self.assertEqual(self.session.observe()["candidates"], initial["candidates"])
        self.session.apply({"op": "redo"})
        self.assertEqual(self.session.observe()["candidates"], now["candidates"])

    def test_invalid_move_is_atomic(self):
        self.move("place")
        checkpoint = self.session.checkpoint()
        with self.assertRaises(ModelError):
            self.move("eliminate")
        self.assertEqual(self.session.checkpoint(), checkpoint)
        with self.assertRaises(ModelError):
            self.move("place", item=True)
        self.assertEqual(self.session.checkpoint(), checkpoint)

    def test_what_if_exit_next_fail_and_no_nesting(self):
        self.move("what_if_enter")
        checkpoint = self.session.checkpoint()
        with self.assertRaises(ModelError):
            self.move("what_if_enter", item=1, row=1)
        self.assertEqual(self.session.checkpoint(), checkpoint)
        self.session.apply({"op": "what_if_next"})
        self.assertEqual(self.session.observe()["what_if"], {"object": 1, "column": 0})
        self.session.apply({"op": "what_if_fail"})
        self.assertEqual(self.session.observe()["candidates"][0][0], [0, 2])
        self.assertIsNone(self.session.observe()["what_if"])
        self.move("what_if_enter", item=2)
        self.session.apply({"op": "what_if_exit"})
        self.assertEqual(self.session.observe()["candidates"][0][0], [0, 2])

    def test_restart_checkpoint_preserves_history_and_assumption(self):
        self.move("eliminate", item=2)
        self.move("what_if_enter", item=1)
        self.session.apply({"op": "undo"})
        data = self.session.checkpoint()
        resumed = Session.from_checkpoint(self.puzzle, data)
        self.assertEqual(resumed.checkpoint(), data)
        resumed.apply({"op": "redo"})
        self.assertEqual(resumed.observe()["what_if"], {"object": 1, "column": 0})
        resumed.apply({"op": "what_if_exit"})
        self.assertEqual(resumed.observe()["candidates"][0][0], [0, 1])

    def test_checkpoint_rejects_tampering_and_changed_givens(self):
        session = Session(Puzzle(3, 3, givens=(Given(0, 0),)))
        data = session.checkpoint()
        other = copy.deepcopy(data)
        other["frame"]["domains"][0] = 2
        with self.assertRaises(ModelError):
            Session.from_checkpoint(session.puzzle, other)
        other = copy.deepcopy(data)
        other["challenge_id"] = self.puzzle.challenge_id
        with self.assertRaises(ModelError):
            Session.from_checkpoint(session.puzzle, other)

    def test_complete_what_if_waits_for_keep(self):
        self.move("what_if_enter")
        for row in range(3):
            for item in range(3):
                self.move("place", row=row, column=item, item=item)
        observation = self.session.observe()
        self.assertTrue(observation["complete"])
        self.assertFalse(observation["won"])
        with self.assertRaises(ModelError):
            self.session.apply({"op": "submit_state"})
        self.session.apply({"op": "what_if_keep"})
        self.assertTrue(self.session.observe()["won"])
        self.assertTrue(self.session.apply({"op": "submit_state"})["accepted"])

    def test_final_answer_does_not_depend_on_elimination_history(self):
        self.move("eliminate")
        board = [[0, 1, 2] for _ in range(3)]
        result = self.session.apply({"op": "submit", "submission": make_submission(self.puzzle, board)})
        self.assertTrue(result["accepted"])

    def test_checkpoint_rejects_impossible_assumption(self):
        self.move("place")
        data = self.session.checkpoint()
        data["frame"]["assumption"] = {"before": data["frame"]["domains"][:], "object": 0, "column": 0}
        with self.assertRaises(ModelError):
            Session.from_checkpoint(self.puzzle, data)

    def test_action_counter_boundary_remains_reloadable(self):
        data = self.session.checkpoint()
        data["actions"] = MAX_ACTIONS - 1
        session = Session.from_checkpoint(self.puzzle, data)
        session.apply({"op": "place", "row": 0, "column": 0, "item": 0})
        at_limit = session.checkpoint()
        self.assertEqual(Session.from_checkpoint(self.puzzle, at_limit).checkpoint(), at_limit)
        with self.assertRaises(ModelError):
            session.apply({"op": "reset"})
        self.assertEqual(session.checkpoint(), at_limit)


if __name__ == "__main__":
    unittest.main()
