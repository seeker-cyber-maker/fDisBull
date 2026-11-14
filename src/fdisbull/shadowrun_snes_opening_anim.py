"""Source-bound opening sprite allocation and animation sort metadata."""
from pathlib import Path
SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_snes_opening_anim.c'

def source_fragment():
    return SOURCE.read_text()
