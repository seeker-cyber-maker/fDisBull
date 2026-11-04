"""Bounded source live-camera fragment for shared scene composition."""
from pathlib import Path

SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_snes_camera.c'


def source_fragment():
    """Return the fragment; caller supplies scene_read, scene_write and rom8."""
    return SOURCE.read_text()
