"""Source fragments for mutable opening collision and actor ordering.

The caller appends the returned fragment after scene_init's bank declarations
and before its opening frame wrapper. No later source snapshots are consumed.
"""
from pathlib import Path

from .shadowrun_snes_field import SOURCE as FIELD_SOURCE
from .shadowrun_snes_live import SOURCE as LIVE_SOURCE

SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_snes_opening_collision.c'


def source_fragment():
    live = LIVE_SOURCE.read_text().replace(
        'typedef unsigned char u8;\ntypedef unsigned int u16;\n', '', 1)
    field = FIELD_SOURCE.read_text()
    start = field.index('u16 shadowrun_snes_collision(')
    end = field.index('\nvoid shadowrun_snes_frame(', start)
    collision = field[start:end]
    replacement = {
        'shadowrun_snes_collision_supported': 'opening_collision_supported',
        'shadowrun_snes_collision(': 'opening_collision_impl(',
        'shadowrun_snes_read16': 'opening_bank_read16',
        'shadowrun_snes_player_z': 'opening_col_z',
        'shadowrun_snes_flags': 'opening_col_flags',
        'shadowrun_snes_left': 'opening_col_left',
        'shadowrun_snes_right': 'opening_col_right',
        'shadowrun_snes_top': 'opening_col_top',
        'shadowrun_snes_bottom': 'opening_col_bottom',
        'shadowrun_snes_height': 'opening_col_height',
    }
    for old, new in replacement.items():
        collision = collision.replace(old, new)
    old = '''} else if(owner!=0x42U) {
      /* The source's other live-actor special branch has not been qualified. */
      if(owner==opening_bank_read16(1,0x0cdeUL) && (opening_col_flags&3U)==3U) { }
      else hit=zhi-z;
     }'''
    new = '''} else if(owner!=opening_col_player) {
      /* Other dynamic-owner collision effects remain unqualified. */
      return 0;
     }'''
    if collision.count(old) != 1:
        raise ValueError('unexpected player collision source')
    collision = collision.replace(old, new)
    adapter = SOURCE.read_text()
    marker = 'void opening_load_order(void) {'
    if adapter.count(marker) != 1:
        raise ValueError('unexpected opening collision adapter')
    adapter = adapter.replace(marker, collision + '\n' + marker)
    return live + '\n' + adapter
