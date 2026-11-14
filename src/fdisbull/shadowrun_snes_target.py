"""Bounded source cursor/target fragment for composition with shared WRAM."""
from pathlib import Path

SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_snes_target.c'


def source_fragment():
    """Return the fragment; caller provides scene_read, scene_write and rom8.

    The owner must establish target_geometry_known for each visited actor and
    complete requested window effects before calling target_resume. A refusal
    must roll back the entire enclosing frame.
    """
    return SOURCE.read_text()
