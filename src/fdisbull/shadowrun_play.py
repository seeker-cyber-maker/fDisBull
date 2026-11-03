"""Bounded prepared-state field, inventory and single-shot composition.

The input adapter and symbolic presentation are target-specific.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from .game_il import author_program, emit_c
from .shadowrun_inventory import lift_inventory, SOURCE as INVENTORY_SOURCE
from .udl_shadowrun import ROM_SHA256, lift_opening_camera

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_play.c'
DEBUG_SOURCE = SOURCE.with_name('shadowrun_debug_place.c')
SHOT_SOURCE = SOURCE.with_name('shadowrun_play_shot.c')
TARGET_SOURCE = SOURCE.with_name('shadowrun_targeting.c')
ACTOR_SOURCE = SOURCE.with_name('shadowrun_play_actors.c')
ORDERED_SOURCE = SOURCE.with_name('shadowrun_linked_actors.c')
LINKED_SOURCES = tuple(SOURCE.with_name('shadowrun_linked_'+name+'.c') for name in ('heading','spawn','motion'))
SCHEDULER_RANGES = ((0xa8fc,0xa912,'e35713fb2c9457347a8a43e66c8189010a3de92101eabeaf5a6b049bae782e3b'),(0xad1a,0xad86,'c698e4adef517806ace04c5371630dfa1e8536399d4020d55ff8d295993da665'),(0xabfc,0xac4a,'f2b9628b3876b73c835f59527834e45e9a9ca4ffa811ea09a62dd78229a602ef'))
DISPATCH_RANGES = ((0x12168,0x12288,'931732a7930101e5dc2d447e6649fc0698da53d40471466f35b39227cd706caa'),
                   (0x125fa,0x12634,'09e624695f81634a58af20a769cd230523d98d19503097dd4ceca7dc56cf9f90'),
                   (0x36fc,0x37d4,'c0834853610446e2114849c157717f454cbfd39928753d30028d336fa4fc0a64'))


def lift_play(rom: bytes) -> dict:
    """Compose movement, inventory, assisted placement and one captured shot."""
    if hashlib.sha256(rom[0xd4594:0xd4596]).hexdigest() != 'bf60e4349cace6bce0d552e8d783428db66d0d649bd9e430a3627e2ee14ac839':
        raise ValueError('Captured weapon capacity source changed')
    if any(hashlib.sha256(rom[a:b]).hexdigest()!=h for a,b,h in DISPATCH_RANGES + SCHEDULER_RANGES):
        raise ValueError('Reviewed equipment dispatch source changed')
    from .shadowrun_field_combat import lift_field_motion, SOURCE as FIELD_SOURCE, MOTION_SOURCE
    field_program = lift_field_motion(rom)
    field = FIELD_SOURCE.read_bytes()
    motion = MOTION_SOURCE.read_bytes()
    shot = SHOT_SOURCE.read_bytes()
    field_lines = [line for line in field.decode().splitlines() if not line.startswith('typedef ')]
    from .shadowrun_linked_heading import lift_linked_motion
    linked_program=lift_linked_motion(rom)
    from .shadowrun_linked_actors import lift_linked_actors
    ordered_program=lift_linked_actors(rom)
    ordered=ORDERED_SOURCE.read_bytes()
    linked=[path.read_bytes() for path in LINKED_SOURCES]
    linked_lines=['\n'.join(line for line in raw.decode().splitlines() if not line.startswith('typedef ')) for raw in linked]
    from .shadowrun_targeting import lift_targeting
    target_program=lift_targeting(rom)
    target=TARGET_SOURCE.read_bytes()
    actor=ACTOR_SOURCE.read_bytes()
    target_lines=[line for line in target.decode().splitlines() if not line.startswith(('typedef ', 'extern u16 shadowrun_camera_x'))]
    opening = lift_opening_camera(rom)
    inventory = lift_inventory(rom)
    inventory_raw = INVENTORY_SOURCE.read_bytes()
    composition = SOURCE.read_bytes()
    debug = DEBUG_SOURCE.read_bytes()
    lines = [line for line in inventory_raw.decode().splitlines()
             if not line.startswith('typedef ')]
    program = author_program(emit_c(opening) + '\n' + '\n'.join(lines) + '\n' + debug.decode() + '\n' + '\n'.join(field_lines) + '\n' + motion.decode() + '\n' + '\n'.join(linked_lines) + '\n' + '\n'.join(target_lines) + '\n' + actor.decode() + '\n' + ordered.decode() + '\n' + shot.decode() + '\n' + composition.decode(),
        [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}], evidence={
            'kind': 'bounded-opening-inventory-browser-composition',
            'components': [opening['evidence'], inventory['evidence'], field_program['evidence'], linked_program['evidence'], target_program['evidence'], ordered_program['evidence']],
            'shot_adapter_sha256': hashlib.sha256(shot).hexdigest(),
            'composition_sha256': hashlib.sha256(composition).hexdigest(),
            'debug_sha256': hashlib.sha256(debug).hexdigest(),
            'actor_adapter_sha256': hashlib.sha256(actor).hexdigest(),
            'ordered_actor_sha256': hashlib.sha256(ordered).hexdigest(),
            'dispatch_ranges': [list(span) for span in DISPATCH_RANGES],
            'scheduler_ranges': [list(span) for span in SCHEDULER_RANGES],
            'weapon_capacity_word_sha256': 'bf60e4349cace6bce0d552e8d783428db66d0d649bd9e430a3627e2ee14ac839',
            'scope': 'captured scene movement, target-adapted inventory and linked captured-profile combat',
            'excluded': ['other equipment dispatch', 'dynamic NPC AI and line of sight', 'original projectile pool lifecycle', 'scene travel'],
        })
    if (SOURCE.read_bytes()!=composition or DEBUG_SOURCE.read_bytes()!=debug or INVENTORY_SOURCE.read_bytes()!=inventory_raw or SHOT_SOURCE.read_bytes()!=shot or FIELD_SOURCE.read_bytes()!=field or MOTION_SOURCE.read_bytes()!=motion or TARGET_SOURCE.read_bytes()!=target or ACTOR_SOURCE.read_bytes()!=actor or ORDERED_SOURCE.read_bytes()!=ordered or any(path.read_bytes()!=raw for path,raw in zip(LINKED_SOURCES,linked))):
        raise ValueError('Play composition changed during lifting')
    return program


def captured_target_state(memory: bytes) -> dict:
    """Extract seven fixed actor records from one verified prepared RAM image."""
    if len(memory)!=65536: raise ValueError('Expected full Genesis RAM')
    word=lambda a:int.from_bytes(memory[a:a+2], 'big')
    long=lambda a:int.from_bytes(memory[a:a+4], 'big')
    offsets=[0x400+i*0x100 for i in range(7)]
    return {'shadowrun_play_actor_hp':[memory[x+0x4c] for x in offsets],
        'shadowrun_target_x':[word(x) for x in offsets],
        'shadowrun_target_y':[word(x+4) for x in offsets],
        'shadowrun_target_height':[word(x+8) for x in offsets],
        'shadowrun_target_contact':[word(x+12) for x in offsets],
        'shadowrun_target_marker':[word(x+0xa6) for x in offsets],
        'shadowrun_target_index':[word(x+0x3e) for x in offsets],
        'shadowrun_target_flags':[memory[x+0x10] for x in offsets],
        'shadowrun_target_flags_low':[memory[x+0x11] for x in offsets],
        'shadowrun_target_flags_b0':[memory[x+0xb0] for x in offsets],
        'shadowrun_target_backlink':[int(bool(long(x+0xac))) for x in offsets],
        'shadowrun_target_special_callback':[int(long(x+0x3a)==0x15390) for x in offsets],
        'shadowrun_target_player_backlink':int(bool(long(0x1a2)))}


def machine_from_capture(rom: bytes, snapshot_path):
    """Seed the shared GameMachine from a receipt-bound prepared scene capture.

    The result is an assisted prepared state, not a natural boot or a save.
    The supplied source and capture are retained only by the caller/runtime.
    """
    from .game_il import GameMachine
    from .shadowrun_replay import _source_capture
    identity, arrays, _ = _source_capture(snapshot_path, ROM_SHA256)
    if identity['frame'] != 5999 or identity['capture_json_sha256'] != 'b7252b76252a0ebda05d615d775c599859092302eff261cfcdad66b30a1ff42c':
        raise ValueError('Expected the reviewed scene-2 prepared capture')
    raw = arrays['ram']
    memory = bytes(raw[i ^ 1] for i in range(len(raw)))
    word=lambda a:int.from_bytes(memory[a:a+2], 'big')
    long=lambda a:int.from_bytes(memory[a:a+4], 'big')
    if (word(0x10e)==13 or memory[0x110]&10!=10 or word(0x10c)==0 or
            memory[0x19e]&32 or word(0xdf84)!=0 or memory[0xe168]&1 or long(0xddec)!=0x172daa):
        raise ValueError('Capture is outside reviewed opening movement branch')
    values={'shadowrun_player_x':word(0x100),'shadowrun_player_y':word(0x104),
        'shadowrun_player_contact':word(0x10c),'shadowrun_player_kind':word(0x10e),
        'shadowrun_player_flags':memory[0x110],'shadowrun_player_heading':word(0x12e),
        'shadowrun_player_target_heading':word(0x134),'shadowrun_player_equipment_flags':memory[0x19e],
        'shadowrun_player_flags_low':memory[0x111],'shadowrun_player_callback':long(0x13a),
        'shadowrun_player_event_flags':memory[0x1b0],'shadowrun_global_special_mode':word(0xdf84),
        'shadowrun_scene_mode':word(0xddc4),'shadowrun_event_mode':word(0xdf40),
        'shadowrun_global_vector_flags':memory[0xe168],'shadowrun_x_min':word(0xddd6),
        'shadowrun_x_max':word(0xddd2),'shadowrun_y_min':word(0xddd8),'shadowrun_y_max':word(0xddd4),
        'shadowrun_rect_base':long(0xddec),'shadowrun_pad_held':word(0xdd20),
        'shadowrun_camera_x':word(0xddc6),'shadowrun_camera_y':word(0xddc8),
        'shadowrun_camera_min_x':word(0xddca),'shadowrun_camera_max_x':word(0xddce),
        'shadowrun_camera_min_y':word(0xddcc),'shadowrun_camera_max_y':word(0xddd0),
        'shadowrun_camera_scroll_ax':word(0xdd08),'shadowrun_camera_scroll_ay':word(0xdd0a),
        'shadowrun_camera_scroll_bx':word(0xdd0c),'shadowrun_camera_scroll_by':word(0xdd0e),
        'shadowrun_camera_stream_x':word(0xdf38),'shadowrun_camera_stream_y':word(0xdf36),
        'shadowrun_camera_freeze_a':word(0xe100),'shadowrun_camera_freeze_b':word(0xe102),
        'shadowrun_camera_freeze_c':word(0xdfe8),'shadowrun_camera_mode':memory[0xe186],
        'shadowrun_camera_previous_x':memory[0xe173],'shadowrun_camera_previous_y':memory[0xe174],
        'shadowrun_camera_supported':1,'shadowrun_terrain_map':list(memory[0x1700:0x2200])}
    values.update(captured_target_state(memory))
    values.update({f'shadowrun_inventory_cell{i}':memory[0x166+i] for i in range(8)})
    values.update({f'shadowrun_play_phase{i}':memory[0x16e+i] for i in range(8)})
    values.update({'shadowrun_play_shot_eligible':1,'shadowrun_play_shot_timer':word(0x1dc),'shadowrun_field_rng':word(0xf9f8), 'shadowrun_field_death_timer':memory[0xf0ce], 'shadowrun_field_type13_deaths':memory[0xfbfa], 'shadowrun_field_party_counter_a':memory[0x18d], 'shadowrun_field_party_counter_b':memory[0x28d], 'shadowrun_field_party_counter_c':memory[0x38d],'shadowrun_inventory_equipped_armor':memory[0x176], 'shadowrun_play_action_gate':memory[0xf09f], 'shadowrun_play_weapon_slot':memory[0x156], 'shadowrun_play_weapon_item':memory[0x157], 'shadowrun_play_ammo':memory[0x14e], 'shadowrun_play_weapon_aux':memory[0x19d]})
    machine=GameMachine(lift_play(rom), {0:rom})
    machine.set_state(values)
    return machine
