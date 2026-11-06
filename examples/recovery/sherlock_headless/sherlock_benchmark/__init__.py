"""Authored, dependency-free headless Sherlock-style puzzle benchmark."""

__version__ = "0.1.0"

from .model import Clue, Given, ModelError, Puzzle, check_assignment, make_submission, verify

__all__ = ["Clue", "Given", "ModelError", "Puzzle", "check_assignment", "make_submission", "verify"]
