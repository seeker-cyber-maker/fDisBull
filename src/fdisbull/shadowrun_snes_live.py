"""Prepared-scene player and collision profile; autonomous scripts unqualified."""
import hashlib
from pathlib import Path
from .game_il import author_program, GameMachine
from .shadowrun_snes_field import ROM_SHA256, SNAPSHOT_SHA256, SAVE_SHA256

SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_snes_live.c'
FLAGS_SOURCE = Path(__file__).parent / 'game_sources' / 'shadowrun_snes_flags.c'
ACTOR_ARRAYS = {'live_x': 0x0e44, 'live_y': 0x0e9c, 'live_z': 0x0ef4,
    'live_flags': 0x1474, 'live_left': 0x421c, 'live_right': 0x4274,
    'live_top': 0x42cc, 'live_bottom': 0x4324, 'live_height': 0x437c,
    'live_depth': 0x0f4c, 'live_sort_mode': 0x0fa4, 'live_sort_delta': 0x0ffc}

def machine_from_capture(rom, snapshot, save_ram):
    if len(rom) != 1048576 or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('wrong SNES source')
    if len(snapshot) != 131072 or hashlib.sha256(snapshot).hexdigest() != SNAPSHOT_SHA256:
        raise ValueError('wrong captured scene')
    if len(save_ram) != 8192 or hashlib.sha256(save_ram).hexdigest() != SAVE_SHA256:
        raise ValueError('wrong captured save RAM')
    raw = SOURCE.read_bytes()
    program = author_program(raw.decode(), evidence={'kind': 'bounded-snes-collision-rebuild',
        'source_sha256': ROM_SHA256, 'snapshot_sha256': SNAPSHOT_SHA256,
        'authoring_sha256': hashlib.sha256(raw).hexdigest(),
        'scope': 'collision rebuild component only; no actor dispatch or autonomous movement'})
    m = GameMachine(program, {})
    w = lambda p: int.from_bytes(snapshot[p:p+2], 'little')
    count = w(0x14cc) // 2 + 1
    if count > 44 or w(0x14cc) & 1:
        raise ValueError('unsupported actor list')
    state = {name: [w(base + i * 2) for i in range(44)] for name, base in ACTOR_ARRAYS.items()}
    state.update(live_order=[w(0x14ce+i*2) for i in range(count)] + [0]*(44-count),
        live_order_count=count, live_first_node=w(0xde86),
        live_heads=[w(0xe088+i*2) for i in range(256)],
        live_records=[w(0xecfc+i*2) for i in range(264)],
        live_node_record=[w(0xef18+i*2) for i in range(1072)],
        live_node_next=[w(0xf778+i*2) for i in range(1073)],
        live_owners=list(snapshot[0x1e214:0x1e214+1584]))
    m.set_state(state)
    if SOURCE.read_bytes() != raw:
        raise ValueError('source changed')
    return m, {}

# Read mutable dynamic lists/records before falling back to the captured WRAM.
# Static heads and rectangles remain in region 1.
_OVERLAY = '''
u16 live_overlay_read16(u8 region,u32 at) {
 u16 i;
 if(region==1U) {
  if(at>=0xe088UL && at<0xe288UL && !(at&1UL))return live_heads[(at-0xe088UL)>>1];
  if(at>=0xecfcUL && at<0xef0cUL && !(at&1UL))return live_records[(at-0xecfcUL)>>1];
  if(at>=0xef18UL && at<0xf778UL && !(at&1UL))return live_node_record[(at-0xef18UL)>>1];
  if(at>=0xf778UL && at<0xffdaUL && !(at&1UL))return live_node_next[(at-0xf778UL)>>1];
  if(at>=0x1e214UL && at<0x1e842UL) {i=(u16)(at-0x1e214UL);return (u16)((u16)live_owners[i]|((u16)live_owners[i+1U]<<8));}
 }
 return (u16)((u16)rom8(region,at)|((u16)rom8(region,at+1UL)<<8));
}
'''
_FRAME = '''
u8 live_walking;
u16 live_elapsed;
void shadowrun_snes_frame(u8 pad) {
 u16 joy,dir;
 shadowrun_snes_frame_status=2U;
 if(live_elapsed>=200U)return;
 if(pad!=0U && pad!=1U && pad!=2U && pad!=4U && pad!=8U)return;
 shadowrun_snes_rebuild();
 if(!live_status)return;
 shadowrun_snes_player_update(pad);
 if(shadowrun_snes_frame_status!=1U)return;
 if(pad) {
  if(pad==8U)joy=1U;else if(pad==4U)joy=2U;else if(pad==2U)joy=4U;else joy=8U;
  dir=shadowrun_snes_read16(0,0x5f15UL+(u32)(joy<<1));
  if(dir>=16U) {shadowrun_snes_frame_status=2U;return;}
  dir=(dir-shadowrun_snes_rotation-shadowrun_snes_rotation)&14U;
  shadowrun_snes_flag_requested_direction=dir>>1;
  if(!live_walking){shadowrun_snes_flag_walk_start();if(!shadowrun_snes_flag_animation_status){shadowrun_snes_frame_status=2U;return;}}
  shadowrun_snes_flag_walk_tick();
  if(!shadowrun_snes_flag_animation_status){shadowrun_snes_frame_status=2U;return;}
  live_walking=1U;
 } else if(live_walking) {
  shadowrun_snes_flag_walk_stop();
  if(!shadowrun_snes_flag_animation_status){shadowrun_snes_frame_status=2U;return;}
  live_walking=0U;
 }
 live_x[33]=shadowrun_snes_player_x;live_y[33]=shadowrun_snes_player_y;
 live_z[33]=shadowrun_snes_player_z;live_flags[33]=shadowrun_snes_flags;
 live_depth[33]=(u16)(live_x[33]+live_y[33])>>1;
 shadowrun_snes_sort();
 if(!live_sort_supported){shadowrun_snes_frame_status=2U;return;}
 shadowrun_snes_flag_x=shadowrun_snes_player_x;shadowrun_snes_flag_y=shadowrun_snes_player_y;
 shadowrun_snes_flag_z=shadowrun_snes_player_z;shadowrun_snes_flag_depth=live_depth[33];
 shadowrun_snes_flags_in=shadowrun_snes_flags;
 shadowrun_snes_flags_project();
 if(!shadowrun_snes_flag_status){shadowrun_snes_frame_status=2U;return;}
 shadowrun_snes_flags=shadowrun_snes_flags_out;live_flags[33]=shadowrun_snes_flags;
 live_elapsed+=1U;
}
'''


def machine_from_live_capture(rom, snapshot, save_ram):
    """Prepared frame model; actor scripts and autonomous motion are unqualified."""
    from .shadowrun_snes_field import SOURCE as FIELD_SOURCE
    # Reuse the captured-state validation and initialization of the rebuild.
    component, _ = machine_from_capture(rom, snapshot, save_ram)
    live = SOURCE.read_text().replace('typedef unsigned char u8;\ntypedef unsigned int u16;\n', '')
    field = FIELD_SOURCE.read_text()
    flags = FLAGS_SOURCE.read_text().replace('typedef unsigned int u16;\ntypedef unsigned char u8;\ntypedef unsigned long u32;\nu8 rom8(u8 region,u32 offset);\n', '')
    bound = ' if(x<1356U || x>1581U || y<1795U || y>2023U)return;'
    if field.count(bound) != 1: raise ValueError('unexpected coordinate guard')
    field = field.replace(bound, '')
    old = ''' return (u16)((u16)rom8(region,at)|((u16)rom8(region,at+1UL)<<8));'''
    if field.count(old) != 1 or field.count('void shadowrun_snes_frame(u8 pad)') != 1:
        raise ValueError('unexpected movement source')
    field = field.replace(old, ' return live_overlay_read16(region,at);')
    field = field.replace('void shadowrun_snes_frame(u8 pad)', 'void shadowrun_snes_player_update(u8 pad)')
    # The function prototype must precede its use, while mutable arrays must
    # precede the overlay definition. The source is one restricted C unit.
    field = field.replace('u16 shadowrun_snes_read16(u8 region,u32 at) {',
                          'u16 live_overlay_read16(u8 region,u32 at);\nu16 shadowrun_snes_read16(u8 region,u32 at) {')
    text = field + '\n' + live + '\n' + flags + '\n' + _OVERLAY + '\n' + _FRAME
    regions = [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256},
               {'id': 1, 'length': len(snapshot), 'sha256': SNAPSHOT_SHA256}]
    program = author_program(text, regions, evidence={'kind': 'bounded-snes-live-collision-player',
        'source_sha256': ROM_SHA256, 'snapshot_sha256': SNAPSHOT_SHA256,
        'authoring_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'scope': 'prepared scene, fixed captured 7F tables, 200-update analysis limit; autonomous actors and scripts unqualified'})
    m = GameMachine(program, {0: rom, 1: snapshot})
    m.set_state(component.snapshot())
    w = lambda n: int.from_bytes(snapshot[n:n+2], 'little')
    if w(0xcde) != 0x42 or w(0x1096) != 0:
        raise ValueError('unexpected player slot or source action')
    m.set_state({'shadowrun_snes_player_x': w(0xe86), 'shadowrun_snes_player_y': w(0xede),
        'shadowrun_snes_player_z': w(0xf36), 'shadowrun_snes_velocity_x': w(0xd7e),
        'shadowrun_snes_velocity_y': w(0xdd6), 'shadowrun_snes_flags': w(0x14b6),
        'shadowrun_snes_rotation': int.from_bytes(save_ram[0x1ffd:0x1fff], 'little'),
        'shadowrun_snes_left': w(0x425e), 'shadowrun_snes_right': w(0x42b6),
        'shadowrun_snes_top': w(0x430e), 'shadowrun_snes_bottom': w(0x4366),
        'shadowrun_snes_height': w(0x43be), 'shadowrun_snes_frame_status': 1,
        'shadowrun_snes_flag_phase': w(0x404e), 'shadowrun_snes_flag_timer': w(0x3ff6),
        'shadowrun_snes_flag_selector': w(0x124e), 'shadowrun_snes_flag_sprite': w(0x3f9e),
        'shadowrun_snes_flag_direction': w(0x11f6),
        'shadowrun_snes_flag_camera_x': w(0xce0) >> 2,
        'shadowrun_snes_flag_camera_y': w(0xce2) >> 2, 'live_walking': 0})
    return m, {0: rom, 1: snapshot}
