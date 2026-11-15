"""Staged, source-bound scene-transition fragment for shared-state callers."""
from pathlib import Path

SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_snes_transition.c'


def source_fragment():
    """Return the transition source; the caller supplies scene/task helpers.

    Requests yield cursor closure, task reset, display/sprite reset, task
    creation, or room presentation. The owner must finish each exact effect
    before resuming and restore its whole transaction on unsupported status.
    """
    return SOURCE.read_text()
