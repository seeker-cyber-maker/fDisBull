"""Separate Shadowrun AI-play composition and native-code preparation.

The previously qualified static-NPC play program remains unchanged.  This
module's code-selection helper only omits uncalled procedural definitions in a
new target build; it does not modify the GameIL model or claim native behavior.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .game_il import _parser, author_program, emit_c, GameMachine, validate_program
from .shadowrun_play import lift_play, machine_from_capture
from .shadowrun_enemy_move import lift_enemy_move, SOURCE as MOVE_SOURCE
from .shadowrun_enemy_service import lift_enemy_service, SOURCE as SERVICE_SOURCE
from .shadowrun_enemy_outer import SOURCE as OUTER_SOURCE
from .shadowrun_enemy_projection import lift_enemy_projection, SOURCE as PROJECTION_SOURCE
from .shadowrun_enemy_overlap import lift_enemy_overlap, SOURCE as OVERLAP_SOURCE
from .shadowrun_enemy_overlap_one import lift_enemy_overlap_one, SOURCE as OVERLAP_ONE_SOURCE
from .shadowrun_enemy_visible import lift_enemy_visible, SOURCE as VISIBLE_SOURCE
from .shadowrun_replay import _source_capture
from .udl_shadowrun import ROM_SHA256

SLOT_SOURCE = Path(__file__).parent / 'game_sources/shadowrun_ai_slots.c'


def lift_actor_service(rom):
    """Compose the qualified service, without inventing its scheduler."""
    baseline = lift_play(rom)
    movement = lift_enemy_move(rom)
    service = lift_enemy_service(rom)
    projection = lift_enemy_projection(rom)
    overlap = lift_enemy_overlap(rom)
    overlap_one = lift_enemy_overlap_one(rom)
    visible = lift_enemy_visible(rom)
    move, scheduler, slots = MOVE_SOURCE.read_bytes(), SERVICE_SOURCE.read_bytes(), SLOT_SOURCE.read_bytes()
    outer, projected, overlap_raw = (p.read_bytes() for p in (OUTER_SOURCE, PROJECTION_SOURCE, OVERLAP_SOURCE))
    overlap_one_raw = OVERLAP_ONE_SOURCE.read_bytes()
    visible_raw = VISIBLE_SOURCE.read_bytes()
    if movement['evidence']['authoring_sha256'][-1] != hashlib.sha256(move).hexdigest():
        raise ValueError('Movement source changed between component lifts')
    if service['evidence']['authoring_sha256'][-1] != hashlib.sha256(scheduler).hexdigest():
        raise ValueError('Scheduler source changed between component lifts')
    if projection['evidence']['authoring_sha256'] != [hashlib.sha256(x).hexdigest() for x in (outer,projected)]:
        raise ValueError('Outer projection changed between component lifts')
    if overlap['evidence']['authoring_sha256'] != hashlib.sha256(overlap_raw).hexdigest():
        raise ValueError('Overlap source changed between component lifts')
    if overlap_one['evidence']['authoring_sha256'] != [hashlib.sha256(x).hexdigest() for x in (overlap_raw,overlap_one_raw)]:
        raise ValueError('Per-actor overlap source changed between component lifts')
    if visible['evidence']['authoring_sha256'][-1] != hashlib.sha256(visible_raw).hexdigest():
        raise ValueError('Visible-contact source changed between component lifts')
    source = '\n'.join(line for line in b'\n'.join((move,scheduler,outer,projected,overlap_raw,overlap_one_raw,visible_raw)).decode().splitlines()
                       if not line.startswith('typedef '))
    program = author_program(emit_c(baseline) + '\n' + source + '\n' + slots.decode(),
        [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}], evidence={
            'kind': 'bounded-scene-actor-service-composition',
            'actor_profile': 'source-qualified-movement-service-only',
            'components': [baseline['evidence'], movement['evidence'], service['evidence'], projection['evidence'], overlap['evidence'], overlap_one['evidence'], visible['evidence']],
            'slot_adapter_sha256': hashlib.sha256(slots).hexdigest(),
            'scope': 'explicit caller-supplied actor service; no waypoint scheduler, AI or enemy fire'})
    if (MOVE_SOURCE.read_bytes()!=move or SERVICE_SOURCE.read_bytes()!=scheduler or SLOT_SOURCE.read_bytes()!=slots or
        any(p.read_bytes()!=raw for p,raw in zip((OUTER_SOURCE,PROJECTION_SOURCE,OVERLAP_SOURCE,OVERLAP_ONE_SOURCE,VISIBLE_SOURCE),(outer,projected,overlap_raw,overlap_one_raw,visible_raw)))):
        raise ValueError('Actor composition changed during lifting')
    return program


def actor_service_from_capture(rom, snapshot_path):
    """Seed the diagnostic actor service from the same receipt-bound capture."""
    baseline = machine_from_capture(rom, snapshot_path)
    identity, arrays, _ = _source_capture(snapshot_path, ROM_SHA256)
    if identity['frame'] != 5999 or identity['capture_json_sha256'] != 'b7252b76252a0ebda05d615d775c599859092302eff261cfcdad66b30a1ff42c':
        raise ValueError('Expected the reviewed scene-2 prepared capture')
    raw = arrays['ram']
    memory = bytes(raw[i ^ 1] for i in range(len(raw)))
    offsets = [0x400 + i * 0x100 for i in range(7)]
    overlap_offsets = [0x100 + i * 0x100 for i in range(10)]
    word = lambda a: int.from_bytes(memory[a:a+2], 'big')
    long = lambda a: int.from_bytes(memory[a:a+4], 'big')
    values = {
        'shadowrun_ai_slot_heading': [word(x+0x2e) for x in offsets],
        'shadowrun_ai_slot_target_heading': [word(x+0x34) for x in offsets],
        'shadowrun_ai_slot_transition_heading': [word(x+0x36) for x in offsets],
        'shadowrun_ai_slot_kind': [word(x+0x0e) for x in offsets],
        'shadowrun_ai_slot_distance': [word(x+0xc8) for x in offsets],
        'shadowrun_ai_slot_move_state': [word(x+0x38) for x in offsets],
        'shadowrun_ai_slot_collision_state': [word(x+0xb8) for x in offsets],
        'shadowrun_ai_slot_speed': [word(x+0xca) for x in offsets],
        'shadowrun_ai_slot_animation': [word(x+0x16) for x in offsets],
        'shadowrun_ai_slot_callback': [long(x+0x3a) for x in offsets],
        'shadowrun_ai_slot_equipment_flags': [memory[x+0x9e] for x in offsets],
        'shadowrun_ai_slot_attribute': [memory[x+0x78] for x in offsets],
        'shadowrun_ai_slot_visible_class': [memory[x+0x4d] for x in offsets],
        'shadowrun_ai_slot_max_hp': [memory[x+0x9c] for x in offsets],
        'shadowrun_ai_slot_corners': [memory[x+0xd0+i] for x in offsets for i in range(4)],
        'shadowrun_ai_slot_service_timer': [word(x+0xb6) for x in offsets],
        'shadowrun_ai_slot_action_timer': [word(x+0xdc) for x in offsets],
        'shadowrun_ai_slot_waypoint_x': [word(x+0x96) for x in offsets],
        'shadowrun_ai_slot_waypoint_y': [word(x+0x98) for x in offsets],
        'shadowrun_ai_slot_direction': [memory[x+0xb1] for x in offsets],
        'shadowrun_ai_service_pause': memory[0xe175],
        'shadowrun_ai_visible_alert': memory[0xe16f],
        'shadowrun_ai_combat_global': word(0xdf84),
        'shadowrun_ai_overlap_flags': [memory[x+0x10] for x in overlap_offsets],
        'shadowrun_ai_overlap_x': [word(x) for x in overlap_offsets],
        'shadowrun_ai_overlap_y': [word(x+4) for x in overlap_offsets],
        'shadowrun_ai_overlap_target': [long(x+0xa2) for x in overlap_offsets],
        'shadowrun_ai_overlap_attacker': [long(x+0xac) for x in overlap_offsets],
        'shadowrun_ai_slot_status': [1, 1, 1, 0, 0, 0, 0],
    }
    if any(values['shadowrun_ai_slot_kind'][i] != 11 or
           values['shadowrun_ai_slot_callback'][i] != 0xb574 for i in range(3)):
        raise ValueError('Captured actor service profile changed')
    machine = GameMachine(lift_actor_service(rom), {0: rom})
    machine.set_state(baseline.snapshot())
    machine.set_state(values)
    return machine


def emit_reachable_c(program, *, roots):
    """Emit only procedures reachable from explicit native entry points.

    Procedural GameIL rejects indirect calls and recursion. Globals and all
    declarations remain intact, and external calls such as ``rom16`` remain
    external. An unknown root or an indirect call fails closed.
    """
    tree = validate_program(program)
    _, generator, _ = _parser()
    functions = {item.decl.name: item for item in tree.ext
                 if type(item).__name__ == 'FuncDef'}
    if (not isinstance(roots, (tuple, list)) or not roots or
            any(not isinstance(name, str) or name not in functions for name in roots)):
        raise ValueError('Native entry points must name existing procedures')
    calls = {}
    for name, function in functions.items():
        found = set()
        def walk(node):
            if type(node).__name__ == 'FuncCall':
                if type(node.name).__name__ != 'ID':
                    raise ValueError('Indirect calls cannot be pruned safely')
                found.add(node.name.name)
            for _, child in node.children():
                walk(child)
        walk(function.body)
        calls[name] = found
    reachable = set()
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name in reachable:
            continue
        reachable.add(name)
        pending.extend(callee for callee in calls[name] if callee in functions)
    tree.ext = [item for item in tree.ext
                if type(item).__name__ != 'FuncDef' or item.decl.name in reachable]
    return generator.CGenerator().visit(tree) + '\n', {
        'roots': list(roots), 'included': sorted(reachable),
        'omitted': sorted(set(functions) - reachable),
        'scope': 'native definition selection; full GameIL remains authoritative'}
