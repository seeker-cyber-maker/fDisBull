"""Bounded source NPC controller; callers qualify dispatch and movement separately."""
import hashlib
from pathlib import Path

from .game_il import GameMachine, author_program
from .shadowrun_snes_field import ROM_SHA256

SOURCE=Path(__file__).parent/'game_sources/shadowrun_snes_npc.c'
INTRO_SHA256='faa776f34a5b2d9f0aad328ffc44d9d4065523a77caf3d412d46b2d9258f52ab'
FIELDS={'npc_x':0x0e44,'npc_y':0x0e9c,'npc_z':0x0ef4,'npc_target_x':0x416c,
        'npc_target_y':0x41c4,'npc_timer':0x40bc,'npc_control':0x4114,
        'npc_flags':0x1474,'npc_direction':0x11b4,'npc_action':0x1054,
        'npc_task':0x136c,'npc_velocity_x':0x0d3c,'npc_velocity_y':0x0d94,
        'npc_velocity_z':0x0dec,'npc_depth':0x0f4c}


def control_from_capture(rom, snapshot, slot):
    if len(rom)!=1048576 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256:
        raise ValueError('wrong SNES source')
    if len(snapshot)!=131072 or type(slot) is not int or slot&1 or not 0<=slot<88:
        raise ValueError('qualified word-indexed actor slot and WRAM required')
    raw=SOURCE.read_bytes()
    program=author_program(raw.decode(),[{'id':0,'length':len(rom),'sha256':ROM_SHA256}],
        evidence={'kind':'source-npc-coordinate-target-control',
                  'source_range':'80:C7DC-C8E2; unchanged-direction branch of80:AA3C',
                  'snapshot_sha256':hashlib.sha256(snapshot).hexdigest(),
                  'authoring_sha256':hashlib.sha256(raw).hexdigest(),
                  'slot':slot,'scope':'coordinate-target controller and noncolliding kinematic projection; source script dispatch, rendering flags, animation and colliding/gravity actors excluded'})
    machine=GameMachine(program,{0:rom})
    machine.set_state({name:int.from_bytes(snapshot[base+slot:base+slot+2],'little') for name,base in FIELDS.items()})
    if SOURCE.read_bytes()!=raw:raise ValueError('NPC source changed')
    return machine


def demo_from_capture(rom,snapshot,save_ram):
    """Two source NPCs in a prepared, noncolliding walking projection.

    Both controllers evolve their own countdown/target state. The entire frame
    refuses when either reaches an unqualified direction, task or physics edge.
    Rendering flags, animation and the rest of the original scene are excluded.
    """
    if hashlib.sha256(snapshot).hexdigest()!=INTRO_SHA256:
        raise ValueError('wrong captured NPC intro scene')
    actors=[control_from_capture(rom,snapshot,slot) for slot in (0x44,0x46)]
    source=SOURCE.read_text()
    declarations='u8 shadowrun_snes_view=2;u8 shadowrun_snes_frame_status;'
    declarations+='u16 shadowrun_snes_player_x,shadowrun_snes_player_y,shadowrun_snes_player_z;'
    declarations+='u16 demo_actor_id[2];'
    declarations+=''.join('u16 demo_'+name[4:]+'[2];' for name in FIELDS)
    load=''.join(name+'=demo_'+name[4:]+'[i];' for name in FIELDS)
    save=''.join('demo_'+name[4:]+'[i]='+name+';' for name in FIELDS)
    wrapper='''void shadowrun_snes_frame(u8 pad) {
      u16 i;shadowrun_snes_frame_status=2U;if(pad)return;
      for(i=0U;i<2U;i+=1U) { LOAD
        shadowrun_snes_npc_frame(0U);
        if(shadowrun_snes_npc_frame_status!=1U)return;
        SAVE
      }
      shadowrun_snes_player_x=demo_x[0];shadowrun_snes_player_y=demo_y[0];
      shadowrun_snes_player_z=demo_z[0];shadowrun_snes_frame_status=1U;
    }'''.replace('LOAD',load).replace('SAVE',save)
    program=author_program(source+'\n'+declarations+'\n'+wrapper,
        [{'id':0,'length':len(rom),'sha256':ROM_SHA256}],
        evidence={'kind':'prepared-two-npc-kinematic-projection','source_sha256':ROM_SHA256,
                  'snapshot_sha256':INTRO_SHA256,'source_frame':2000,
                  'authoring_sha256':hashlib.sha256(source.encode()).hexdigest(),
                  'scope':'two noncolliding coordinate-target controllers and kinematics; no source script dispatch, rendering flags, animation or scene equivalence'})
    machine=GameMachine(program,{0:rom})
    state={'demo_actor_id':[0x44,0x46]}
    state.update({'demo_'+name[4:]:[a.snapshot()[name] for a in actors] for name in FIELDS})
    state.update(shadowrun_snes_player_x=state['demo_x'][0],
                 shadowrun_snes_player_y=state['demo_y'][0],shadowrun_snes_player_z=state['demo_z'][0])
    machine.set_state(state)
    return machine,{0:rom}
