"""Bounded source text decoder; game text remains private runtime state."""
import hashlib
from pathlib import Path

from .game_il import GameMachine, author_program
from .shadowrun_snes_field import ROM_SHA256

SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_snes_text.c'


def text_machine(rom,text_id=0x3b):
    """Decode a bounded source-table entry; the caller qualifies its ID."""
    if len(rom)!=1048576 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256:
        raise ValueError('wrong SNES source')
    if type(text_id) is not int or not 0<=text_id<=0x133f:
        raise ValueError('source text table index out of range')
    raw=SOURCE.read_bytes()
    program=author_program(raw.decode(),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],evidence={
      'kind':'source-bound-snes-text-byte-stream','source_sha256':ROM_SHA256,
      'authoring_sha256':hashlib.sha256(raw).hexdigest(),'text_id':text_id,
      'source_range':'80:FE9B-FE86,81:AEC0','scope':'one bounded source-table byte stream; caller qualifies ID; window layout and rendering excluded'})
    m=GameMachine(program,{0:rom});m.set_state({'shadowrun_snes_text_id':text_id})
    if SOURCE.read_bytes()!=raw:raise ValueError('text source changed')
    return m
