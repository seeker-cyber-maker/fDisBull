"""Run the first-use skill exercise, including a deliberately wrong source rule."""
from pathlib import Path

import pytest


def exercise():
    pytest.importorskip('unicorn')
    pytest.importorskip('iced_x86')
    text = (Path(__file__).parents[1] / 'src/fdisbull/skills/fdisbull-investigate/references/reconstruction.md').read_text()
    return text.split('```python\n')[1].split('```')[0]


def test_first_use_exercise_runs_without_project_or_game_data():
    exec(compile(exercise(), 'skill-exercise', 'exec'), {})


def test_first_use_exercise_detects_zeroing_retained_state():
    bad = exercise().replace('83fa00750201d8', '83fa00740431c0eb0201d8')
    with pytest.raises(AssertionError):
        exec(compile(bad, 'deliberately-wrong-rule', 'exec'), {})
