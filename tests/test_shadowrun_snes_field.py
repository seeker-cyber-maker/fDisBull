"""The SNES stage must refuse unsupported controls before committing actors."""
import hashlib
from fdisbull.game_il import GameMachine,author_program
from fdisbull.shadowrun_snes_field import SOURCE

def test_snes_unqualified_chord_refuses_without_actor_mutation():
    rom=bytes(1048576);wram=bytes(131072)
    regions=[{'id':i,'length':len(b),'sha256':hashlib.sha256(b).hexdigest()} for i,b in enumerate((rom,wram))]
    machine=GameMachine(author_program(SOURCE.read_text(),regions),{0:rom,1:wram})
    machine.set_state({'shadowrun_snes_player_x':1428,'shadowrun_snes_player_y':2008,'shadowrun_snes_player_z':256,'shadowrun_snes_flags':0xa167,'shadowrun_snes_frame_status':1})
    machine.call('shadowrun_snes_frame',9);s=machine.snapshot()
    assert s['shadowrun_snes_frame_status']==2
    assert (s['shadowrun_snes_player_x'],s['shadowrun_snes_player_y'],s['shadowrun_snes_player_z'],s['shadowrun_snes_flags'])==(1428,2008,256,0xa167)
