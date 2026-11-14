"""Bounded source window allocation and lifecycle with explicit dependencies.

Text decoding and FB03 presentation must be separately implemented and
qualified before the caller signals their completion to the window adapter.
Unsupported RNG, eviction and close paths refuse; callers roll back the frame.
"""
from pathlib import Path

SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_snes_opening_window.c'


def source_fragment():
    return SOURCE.read_text()
