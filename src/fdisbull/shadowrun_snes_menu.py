"""Bounded title-menu controller, separated from input and display timing."""
import hashlib
from pathlib import Path

from .game_il import GameMachine, author_program
from .shadowrun_snes_field import ROM_SHA256

SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_snes_menu.c'


def menu_machine(rom):
    """Author the recovered three-choice controller with a source-edge input.

    Set ``menu_pressed`` to the original $01EA button-edge word, then call
    ``shadowrun_snes_menu_control``. This component does not implement the
    producer of that word, original rendering, or the selected continuation.
    """
    if len(rom) != 1048576 or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('wrong SNES source')
    raw = SOURCE.read_bytes()
    program = author_program(raw.decode(), [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}], evidence={
        'kind': 'source-title-menu-control-component',
        'source_range': '81:E195-E197,81:E274-E30C',
        'source_sha256': ROM_SHA256,
        'authoring_sha256': hashlib.sha256(raw).hexdigest(),
        'scope': 'three title choices; source button-edge word supplied as component input; original display, key-repeat, and intro continuation excluded'})
    return GameMachine(program, {0: rom})
