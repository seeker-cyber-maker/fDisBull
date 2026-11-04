"""Source-bound logical verb selector; the caller owns its window and clock.

Append SOURCE after the task interpreter, which supplies the shared WRAM array.
The caller starts once, provides each published held word, performs the final
poll with the then-current held word, then delivers the selected event.
"""
from pathlib import Path

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_snes_choice.c'
