# Extracted from first-party fDisBull v0.34.1; no license reassignment.
# Source commit: 011f1b8cb281edda208026aee9cdb238b800b2d7
# Original path: src/fdisbull/agi_scenes.py
# Original SHA-256: bb2833c63082204945c79cef2d83239b25b5eb9055cc747f505432de12a54d48
# https://github.com/seeker-cyber-maker/fDisBull/blob/011f1b8cb281edda208026aee9cdb238b800b2d7/src/fdisbull/agi_scenes.py

"""Requirements-first AGI scene census, not recovered executable game intent.

The outline inventories typed scene elements before expensive interaction
qualification. The resolve stage adds a bounded, conservative byte-value
analysis. Every logic stays low-level IR, including helpers and dead spans.
Encoding/command references: AGI_LOGIC.md and AGI_SCENE_CENSUS.md.
"""
from collections import Counter, deque
from hashlib import sha256
import json

from .agi_layout import LogicBudgetExceeded, logic_code_span, logic_layout, _ACTION_WIDTHS
from .agi_resources import (DEFAULT_MAX_MESSAGE_BYTES, TextBudget, TextBudgetExceeded,
                            V2Resources, logic_messages)


FORMAT = 'fdisbull-agi-scene-census-1'
DEFAULT_MAX_REPORT_BYTES = 8388608
MIN_REPORT_BYTES = 16384
MAX_REPORT_BYTES = 16777216
_MAX_VALUES = 8
_ACTION_NAMES = '''return increment decrement assignn assignv addn addv subn subv
lindirectv rindirect lindirectn set reset toggle set.v reset.v toggle.v new.room
new.room.v load.logics load.logics.v call call.v load.pic draw.pic show.pic
discard.pic overlay.pic show.pri.screen load.view load.view.v discard.view
animate.obj unanimate.all draw erase position position.v get.posn reposition
set.view set.view.v set.loop set.loop.v fix.loop release.loop set.cel set.cel.v
last.cel current.cel current.loop current.view number.of.loops set.priority
set.priority.v release.priority get.priority stop.update start.update force.update
ignore.horizon observe.horizon set.horizon object.on.water object.on.land
object.on.anything ignore.objs observe.objs distance stop.cycling start.cycling
normal.cycle end.of.loop reverse.cycle reverse.loop cycle.time stop.motion
start.motion step.size step.time move.obj move.obj.v follow.ego wander normal.motion
set.dir get.dir ignore.blocks observe.blocks block unblock get get.v drop put put.v
get.room.v load.sound sound stop.sound print print.v display display.v clear.lines
text.screen graphics set.cursor.char set.text.attribute shake.screen configure.screen
status.line.on status.line.off set.string get.string word.to.string parse get.num
prevent.input accept.input set.key add.to.pic add.to.pic.v status save.game restore.game
init.disk restart.game show.obj random program.control player.control obj.status.v
quit show.mem pause echo.line cancel.line init.joy toggle.monitor version script.size
set.game.id log set.scan.start reset.scan.start reposition.to reposition.to.v trace.on
trace.info print.at print.at.v discard.view.v clear.text.rect set.upper.left set.menu
set.menu.item submit.menu enable.item disable.item menu.input show.obj.v open.dialogue
close.dialogue mul.n mul.v div.n div.v close.window set.simple push.script pop.script
hold.key'''.split()
assert len(_ACTION_NAMES) == len(_ACTION_WIDTHS)
_TEST_NAMES = ('false', 'equaln', 'equalv', 'lessn', 'lessv', 'greatern', 'greaterv',
               'isset', 'isset.v', 'has', 'obj.in.room', 'posn', 'controller',
               'have.key', 'said', 'compare.strings', 'obj.in.box', 'center.posn',
               'right.posn')

# Sink roles: (resource domain, operand index, indirect through variable).
# An integer in one domain is never inferred to name a resource in another.
_REFERENCES = {
    18: ('room', 0, False), 19: ('room', 0, True),
    20: ('logic', 0, False), 21: ('logic', 0, True),
    22: ('logic', 0, False), 23: ('logic', 0, True),
    24: ('picture', 0, True), 25: ('picture', 0, True),
    27: ('picture', 0, True), 28: ('picture', 0, True),
    30: ('view', 0, False), 31: ('view', 0, True), 32: ('view', 0, False),
    41: ('view', 1, False), 42: ('view', 1, True),
    92: ('inventory_object', 0, False), 93: ('inventory_object', 0, True),
    94: ('inventory_object', 0, False), 95: ('inventory_object', 0, False),
    96: ('inventory_object', 0, True), 97: ('inventory_object', 0, True),
    98: ('sound', 0, False), 99: ('sound', 0, False),
    101: ('message', 0, False), 102: ('message', 0, True),
    103: ('message', 2, False), 104: ('message', 2, True),
    108: ('message', 0, False), 114: ('message', 1, False),
    115: ('message', 1, False), 118: ('message', 0, False),
    122: ('view', 0, False), 123: ('view', 0, True), 129: ('view', 0, False),
    143: ('message', 0, False), 144: ('message', 0, False),
    151: ('message', 0, False), 152: ('message', 0, True),
    153: ('view', 0, True), 156: ('message', 0, False),
    157: ('message', 0, False), 162: ('view', 0, True),
}
_ACTOR_SETUP = set(range(33, 39)) | set(range(40, 49)) | {54, 55, 56, 63, 147, 148}
_STATE_WRITES = (set(range(1, 18)) | set(range(49, 54)) | set(range(92, 98)) |
                 {39, 57, 69, 87, 117, 118, 130, 165, 166, 167, 168})
_CYCLE_EFFECTS = set(range(70, 88)) | {99, 100, 115, 117, 118, 125, 126, 128, 130, 136, 145, 146, 161}
# Deliberately small no-variable-write whitelist. Other commands are barriers,
# even if a future qualified engine model could preserve some variable facts.
_PRESERVE = set(range(12, 18)) | {20, 21, 24, 25, 27, 28, 30, 31, 32,
                                      41, 42, 43, 44, 45, 46, 47, 48,
                                      54, 55, 56, 63, 98, 145, 146, 153, 254}
# These engine-owned clock/input variables cannot be frozen by script-local
# propagation. The clock can advance inside script execution and modal work.
_VOLATILE = frozenset({11, 12, 13, 14, 19})
_OBLIGATIONS = [
    'qualify logic-0 dispatch and each room/helper execution context',
    'preserve ordered, possibly stateful conditions including said',
    'recover named state meanings from writers and consumers',
    'qualify helper effects, mutable scan entries and unknown targets',
    'qualify room-change abort, entry placement and engine resets',
    'qualify cycle, animation, motion, sound, clock and RNG effects',
    'compare a complete interaction against the selected original runtime',
]


class ReportBudgetExceeded(ValueError):
    pass


def _encoded_chunks(value, max_bytes=None, *, sort_keys=True):
    """Check ASCII JSON chunks before encoding/copying them into any buffer."""
    encoder = json.JSONEncoder(sort_keys=sort_keys, separators=(',', ':'),
                               ensure_ascii=True, allow_nan=False)
    size = 0
    for chunk in encoder.iterencode(value):
        size += len(chunk)  # ensure_ascii makes characters and UTF-8 bytes equal.
        if max_bytes is not None and size > max_bytes:
            raise ReportBudgetExceeded('AGI report byte budget exhausted; no report was written')
        yield chunk.encode('ascii')


def _encoded_size(value, max_bytes):
    return sum(len(chunk) for chunk in _encoded_chunks(value, max_bytes))


def _digest(value, max_bytes=None):
    digest = sha256()
    for chunk in _encoded_chunks(value, max_bytes):
        digest.update(chunk)
    return digest.hexdigest()


def serialize_report(report, max_report_bytes=DEFAULT_MAX_REPORT_BYTES):
    """Return only an admitted complete JSON report, including its final newline."""
    if type(max_report_bytes) is not int or not MIN_REPORT_BYTES <= max_report_bytes <= MAX_REPORT_BYTES:
        raise ValueError('max_report_bytes must be an integer in 16384..16777216')
    data = bytearray()
    for chunk in _encoded_chunks(report, max_report_bytes - 1, sort_keys=False):
        data.extend(chunk)
    data.extend(b'\n')
    return bytes(data)


_InstructionBudget = LogicBudgetExceeded


def _decode(payload, budget, byte_budget, *, usage=None):
    if usage is None:
        usage = {}
    usage.update(instructions_attempted=0, code_bytes_admitted=0)
    start, end = logic_code_span(payload)
    if end - start > byte_budget:
        raise _InstructionBudget('Global code-byte budget cannot cover this complete LOGIC', 'code_bytes')
    if budget < 1:
        raise _InstructionBudget('Global instruction budget cannot cover this complete LOGIC')
    # Reserve the whole eligible span before parsing. Errors cannot refund work;
    # an overlarge span rejected above consumed no instruction/code-byte budget.
    usage['code_bytes_admitted'] = end - start
    layout = logic_layout(payload, max_instructions=budget, usage=usage)
    starts = layout['instructions']
    # The original 2.917 trace command can consume an extra byte when tracing
    # is already active. A fixed-width listing cannot prove that CFG; retaining
    # the whole resource as opaque is preferable to losing an alternate path.
    if any(payload[pc] == 149 for pc in starts):
        raise ValueError('Context-dependent trace.on layout is outside this census profile')
    ends = starts[1:] + [layout['code_end']]
    instructions = []
    for pc, end in zip(starts, ends):
        op = payload[pc]
        row = {'offset': pc, 'end_offset': end, 'opcode': op,
               'operation': 'if' if op == 255 else 'goto' if op == 254 else _ACTION_NAMES[op],
               'operands': list(payload[pc + 1:end]), 'successors': []}
        if op == 255:
            cursor = pc + 1
            tokens = []
            or_count = None
            while payload[cursor] != 255:
                at = cursor
                test = payload[cursor]
                cursor += 1
                if test in (252, 253):
                    tokens.append({'offset': at, 'marker': 'or' if test == 252 else 'not'})
                    if test == 252:
                        if or_count == 0:
                            raise ValueError('Empty AGI OR group')
                        or_count = 0 if or_count is None else None
                    continue
                stop = layout['conditions'][at]['end']
                item = {'offset': at, 'opcode': test, 'operation': _TEST_NAMES[test],
                        'operands': list(payload[cursor:stop])}
                if test == 14:
                    item['word_groups'] = [int.from_bytes(payload[p:p + 2], 'little')
                                           for p in range(cursor + 1, stop, 2)]
                    item['stateful'] = True
                tokens.append(item)
                if or_count is not None:
                    or_count += 1
                cursor = stop
            row['conditions'] = tokens
            row['successors'] = [
                {'kind': 'true', 'offset': end},
                {'kind': 'false', 'offset': end + int.from_bytes(payload[end - 2:end], 'little', signed=True)},
            ]
        elif op == 254:
            row['successors'] = [{'kind': 'branch', 'offset': end + int.from_bytes(payload[pc + 1:end], 'little', signed=True)}]
        elif op not in (0, 18, 19):
            row['successors'] = [{'kind': 'fallthrough', 'offset': end}]
        instructions.append(row)
    roots = sorted({2} | {i['end_offset'] for i in instructions if i['opcode'] == 145})
    return layout, instructions, roots


def _finite(values):
    values = frozenset(values)
    return values if len(values) <= _MAX_VALUES else None


def _join(left, right):
    # Missing means top/unknown, not zero. An unvisited CFG node is separately
    # represented by None; it must not destroy a first known predecessor.
    result = {}
    for var in left.keys() & right.keys():
        value = _finite(left[var] | right[var])
        if value is not None:
            result[var] = value
    return result


def _transfer(row, incoming):
    env = dict(incoming)
    op, args = row['opcode'], row['operands']
    def put(var, values):
        if values is None or var in _VOLATILE:
            env.pop(var, None)
        else:
            env[var] = values
    def get(var):
        return env.get(var) if var not in _VOLATILE else None
    if op in (1, 2):
        values = get(args[0])
        put(args[0], None if values is None else frozenset(
            min(255, v + 1) if op == 1 else max(0, v - 1) for v in values))
    elif op == 3:
        put(args[0], frozenset({args[1]}))
    elif op == 4:
        put(args[0], get(args[1]))
    elif op in (5, 6, 7, 8, 165, 166, 167, 168):
        left = get(args[0])
        right = get(args[1]) if op in (6, 8, 166, 168) else frozenset({args[1]})
        values = None
        if left is not None and right is not None and not (op in (167, 168) and 0 in right):
            if op in (5, 6): values = _finite((a + b) % 256 for a in left for b in right)
            elif op in (7, 8): values = _finite((a - b) % 256 for a in left for b in right)
            elif op in (165, 166): values = _finite((a * b) % 256 for a in left for b in right)
            else: values = _finite(a // b for a in left for b in right)
        put(args[0], values)
    elif op == 10:
        indexes = get(args[1])
        values = [get(i) for i in indexes] if indexes is not None else [None]
        put(args[0], None if None in values else _finite(v for group in values for v in group))
    elif op in (9, 11):
        indexes = get(args[0])
        values = get(args[1]) if op == 9 else frozenset({args[1]})
        if indexes is None:
            return {}
        for index in indexes:
            # A multi-target store is a weak update: each candidate can also
            # keep its old value. Never turn an unknown old value into known.
            prior = get(index)
            value = values if len(indexes) == 1 else (
                _finite(prior | values) if prior is not None and values is not None else None)
            put(index, value)
    elif op == 255:
        env.pop(19, None)
    elif op not in _PRESERVE:
        # This includes calls, modal output, motion, restore and unknown effects.
        return {}
    return env


def _values(instructions, roots, budget):
    by_offset = {row['offset']: row for row in instructions}
    states = {pc: {} for pc in roots if pc in by_offset}
    pending = deque(states)
    queued = set(states)
    updates = 0
    while pending and updates < budget:
        pc = pending.popleft()
        queued.remove(pc)
        updates += 1
        outgoing = _transfer(by_offset[pc], states[pc])
        for edge in by_offset[pc]['successors']:
            target = edge['offset']
            if target not in by_offset:
                continue
            old = states.get(target)
            merged = outgoing if old is None else _join(old, outgoing)
            if old is None or merged != old:
                states[target] = dict(merged)
                if target not in queued:
                    pending.append(target)
                    queued.add(target)
    return states, {'fixed_point': not pending, 'updates': updates,
                    'pending_offsets': sorted(pending)}


def _target(kind, operand, indirect, env, *, stage, fixed, reached):
    target = {'kind': kind, 'operand': operand, 'mode': 'variable' if indirect else 'literal'}
    if not indirect:
        target.update(values=[operand], resolution='literal')
    else:
        target['variable'] = operand
        values = env.get(operand) if fixed and reached else None
        target.update(values=sorted(values) if values is not None else None,
                      resolution='finite_set' if values is not None else 'unresolved')
        if values is None:
            target['reason'] = ('outline_stage' if stage == 'outline' else
                                'analysis_budget' if not fixed else
                                'outside_entry_flow' if not reached else 'unknown_reaching_value')
    return target


def inspect_scenes(game_dir, *, profile, stage='resolve', include_ir=False,
                   include_text=False, max_updates=200000, max_instructions=100000,
                   max_code_bytes=1048576, max_message_bytes=DEFAULT_MAX_MESSAGE_BYTES,
                   max_report_bytes=DEFAULT_MAX_REPORT_BYTES):
    """Inventory all AGI2.917 logics; resolve only bounded local value facts.

    No game is executed, no original file is changed, and no candidate is
    promoted to UIL. Explicit text/IR output can contain target-derived material
    and belongs in a private investigation, not a tool package or public PR.
    """
    if profile != '2.917':
        raise ValueError('only explicit DOS AGI 2.917 resource profile is supported')
    if stage not in ('outline', 'resolve'):
        raise ValueError('stage must be outline or resolve')
    if type(include_ir) is not bool or type(include_text) is not bool:
        raise ValueError('include_ir and include_text must be Boolean')
    if type(max_updates) is not int or not 1 <= max_updates <= 2000000:
        raise ValueError('max_updates must be an integer in 1..2000000')
    if type(max_instructions) is not int or not 1 <= max_instructions <= 1000000:
        raise ValueError('max_instructions must be an integer in 1..1000000')
    if type(max_code_bytes) is not int or not 1 <= max_code_bytes <= 4194304:
        raise ValueError('max_code_bytes must be an integer in 1..4194304')
    text_budget = TextBudget(max_message_bytes)
    if type(max_report_bytes) is not int or not MIN_REPORT_BYTES <= max_report_bytes <= MAX_REPORT_BYTES:
        raise ValueError('max_report_bytes must be an integer in 16384..16777216')
    resources = V2Resources(game_dir, text_budget=text_budget, include_text=include_text)
    vocabulary = resources.vocabulary()
    inventory = resources.objects()
    word_groups = ({group['number']: group for group in vocabulary['groups']}
                   if vocabulary['status'] == 'decoded' else None)
    manifest = resources.manifest()
    resource_rows = {kind: resources.resources(kind) for kind in ('logic', 'picture', 'view', 'sound')}
    directory_status = {row['kind']: row['status'] for row in manifest['directories']}
    available = {kind: ({row['number']: row['status'] for row in rows}
                        if directory_status[kind] == 'ok' else None)
                 for kind, rows in resource_rows.items()}
    available['inventory_object'] = ({obj['number']: 'ok' for obj in inventory['objects']}
                                     if inventory['status'] == 'decoded' else None)
    logics = []
    budget = max_updates
    counts = Counter()
    room_sources = {}
    decode_cache = {}
    retained_entry_bytes = 0

    def admit_entry(entry):
        nonlocal retained_entry_bytes
        # Bound accumulation before another alias/resource can multiply detail.
        retained_entry_bytes += _encoded_size(entry, max_report_bytes - retained_entry_bytes)

    for resource in resource_rows['logic']:
        number = resource['number']
        source = {key: value for key, value in resource.items() if key != 'payload'}
        entry = {'logic': number, 'source': source, 'representation': 'low_level_ir',
                 'qualification': 'unrecovered_game_intent', 'references': []}
        logics.append(entry)
        if resource['status'] != 'ok':
            entry.update(status='resource_error', error=resource['error'])
            counts['resource_errors'] += 1
            admit_entry(entry)
            continue
        payload = resource['payload']
        identity = resource['sha256']
        if identity in decode_cache:
            cached = decode_cache[identity]
            counts['logic_aliases'] += 1
            entry['decode_work'] = {'instructions_attempted': 0, 'code_bytes_admitted': 0,
                                    'reused_logic': cached['logic']}
        else:
            counts['logic_decode_attempts'] += 1
            work = {'instructions_attempted': 0, 'code_bytes_admitted': 0}
            cached = {'logic': number}
            try:
                cached['decoded'] = _decode(payload, max_instructions - counts['instructions_attempted'],
                                            max_code_bytes - counts['code_bytes_admitted'], usage=work)
            except _InstructionBudget as error:
                cached.update(status='instruction_budget', error=str(error), budget_scope=error.scope)
            except ValueError as error:
                cached.update(status='layout_error', error=str(error))
            finally:
                counts['instructions_attempted'] += work['instructions_attempted']
                counts['code_bytes_admitted'] += work['code_bytes_admitted']
            entry['decode_work'] = work
            decode_cache[identity] = cached
        if 'decoded' not in cached:
            entry.update({key: value for key, value in cached.items() if key != 'logic'})
            entry['opaque_resource'] = True
            counts['instruction_budget_stops' if cached['status'] == 'instruction_budget' else 'layout_errors'] += 1
            admit_entry(entry)
            continue
        layout, instructions, roots = cached['decoded']
        if 'ir_sha256' not in cached:
            # Stream a bounded-by-code IR fingerprint; never build its JSON text.
            cached['ir_sha256'] = _digest(instructions)
        entry.update(status='decoded', code_span=[2, layout['code_end']],
                     instruction_count=len(instructions), entry_offsets=roots)
        counts['decoded_logics'] += 1
        counts['instructions'] += len(instructions)
        counts['code_bytes'] += layout['code_end'] - 2
        counts['conditions'] += len(layout['conditions'])
        try:
            if 'message_error' in cached:
                raise ValueError(cached['message_error'])
            messages = logic_messages(payload, include_text=include_text,
                                      _budget=text_budget, _source_key=identity)
            entry['messages'] = messages
            entry['message_status'] = 'decoded'
            counts['message_tables'] += 1
        except TextBudgetExceeded as error:
            messages = error.partial
            entry.update(messages=messages, message_status='budget', message_error=str(error),
                         message_budget={'scope': 'expanded_text_bytes', 'declared_slots': error.total,
                                         'retained_slots': len(messages)})
            counts['message_budget_stops'] += 1
        except ValueError as error:
            messages = []
            cached['message_error'] = str(error)
            entry.update(message_status='error', message_error=str(error))
            counts['message_errors'] += 1
        counts['message_slots'] += len(messages)
        counts['present_messages'] += sum(m['offset'] is not None for m in messages)
        if stage == 'resolve':
            states, analysis = _values(instructions, roots, budget)
            budget -= analysis['updates']
        else:
            states, analysis = {}, {'fixed_point': False, 'updates': 0, 'pending_offsets': roots}
        entry['value_analysis'] = {**analysis, 'scope': 'script_local_all_entries',
                                   'max_values': _MAX_VALUES, 'volatile_variables': sorted(_VOLATILE)}
        counts['updates'] += analysis['updates']
        if stage == 'resolve' and not analysis['fixed_point']:
            counts['budget_stops'] += 1
        entry['elements'] = {
            'condition_sites': [i['offset'] for i in instructions if i['opcode'] == 255],
            'state_change_sites': [i['offset'] for i in instructions if i['opcode'] in _STATE_WRITES],
            'actor_setup_sites': [i['offset'] for i in instructions if i['opcode'] in _ACTOR_SETUP],
            'cycle_effect_sites': [i['offset'] for i in instructions if i['opcode'] in _CYCLE_EFFECTS],
        }
        entry['conditions'] = [{'offset': i['offset'], 'ordered_tokens': i['conditions'],
                                'successors': i['successors'], 'qualification': 'low_level_ir'}
                               for i in instructions if i['opcode'] == 255]
        entry['command_patterns'] = [
            {'offset': token['offset'], 'condition_site': row['offset'],
             'word_groups': [{'number': group,
                              'dictionary_status': ('not_decoded' if word_groups is None else
                                                    'ok' if group in word_groups else 'absent'),
                              'role': ('any_word' if group == 1 else 'rest_of_input' if group == 9999
                                       else 'ignored' if group == 0 else 'word_group')}
                             for group in token['word_groups']],
             'evaluation': 'ordered_stateful_test', 'qualification': 'low_level_ir'}
            for row in instructions for token in row.get('conditions', []) if token.get('opcode') == 14
        ]
        counts['command_patterns'] += len(entry['command_patterns'])
        message_status = ({m['number']: ('ok' if m['offset'] is not None else 'absent') for m in messages}
                          if entry['message_status'] == 'decoded' else None)
        for row in instructions:
            op = row['opcode']
            if op not in _REFERENCES:
                continue
            kind, arg, indirect = _REFERENCES[op]
            pc = row['offset']
            reached = pc in states
            target = _target(kind, row['operands'][arg], indirect, states.get(pc, {}),
                             stage=stage, fixed=analysis['fixed_point'], reached=reached)
            if kind == 'message': target['owner_logic'] = number
            ref = {'id': f'logic.{number}@{pc}', 'offset': pc, 'operation': row['operation'],
                   'target': target,
                   'entry_flow': ('not_analyzed' if stage == 'outline' else
                                  'unknown_budget' if not analysis['fixed_point'] else
                                  'possible' if reached else 'outside_known_entries')}
            if target['values'] is not None:
                domain = message_status if kind == 'message' else available.get('logic' if kind == 'room' else kind)
                ref['resource_status'] = [{'number': n, 'status': domain.get(n, 'absent') if domain is not None else 'not_decoded'}
                                          for n in target['values']]
            entry['references'].append(ref)
            counts['references'] += 1
            counts['unresolved_references'] += target['values'] is None
            counts['variable_references'] += indirect
            counts['resolved_variable_references'] += indirect and target['values'] is not None
            if kind == 'room' and target['values'] is not None:
                # These are lexical transition targets, including dead code.
                # Source reachability is retained on every incoming reference.
                for room in target['values']:
                    room_sources.setdefault(room, []).append({'logic': number, 'reference': ref['id'],
                                                             'entry_flow': ref['entry_flow']})
        entry['ir'] = {'format': 'fdisbull-agi-structural-ir-1', 'resource_sha256': source['sha256'],
                       'sha256': cached['ir_sha256'], 'instruction_count': len(instructions),
                       'body_included': include_ir,
                       'semantic_status': 'all_operations_retained_as_low_level_ir'}
        if include_ir:
            entry['ir']['instructions'] = instructions
        admit_entry(entry)
    manifest = resources.manifest()
    issues = [{'kind': kind, **{k: v for k, v in row.items() if k != 'payload'}}
              for kind, rows in resource_rows.items() for row in rows if row['status'] != 'ok']
    by_logic = {entry['logic']: entry for entry in logics}
    presentation_candidates = [
        {'logic': entry['logic'], 'classification': 'background_producing_logic',
         'references': [ref['id'] for ref in entry['references']
                        if ref['operation'] in ('draw.pic', 'overlay.pic')],
         'room_ownership': 'unqualified'}
        for entry in logics if any(ref['operation'] in ('draw.pic', 'overlay.pic')
                                  for ref in entry['references'])
    ]
    dispatch_candidates = [
        {'logic': entry['logic'], 'reference': ref['id'],
         'classification': 'logic_0_call_through_current_room_variable',
         'qualification': 'operand_relation_only', 'guards_and_context': 'unqualified'}
        for entry in logics if entry['logic'] == 0
        for ref in entry['references']
        if ref['operation'] == 'call.v' and ref['target']['variable'] == 0
    ]
    candidates = []
    for room in sorted(room_sources):
        logic = by_logic.get(room)
        candidates.append({'id': f'room.{room}', 'room': room,
                           'classification': 'static_room_target_candidate',
                           'incoming': room_sources[room],
                           'logic_status': logic['status'] if logic else 'absent',
                           'logic_binding': 'requires_qualified_room_dispatch',
                           'element_source': f'logic.{room}' if logic else None})
    directory_ok = all(d['status'] == 'ok' for d in manifest['directories'])
    has_logics = bool(resource_rows['logic'])
    coverage = {key: counts[key] for key in (
        'decoded_logics', 'resource_errors', 'layout_errors', 'instructions', 'code_bytes', 'conditions',
        'message_tables', 'message_slots', 'present_messages', 'message_errors', 'references',
        'unresolved_references', 'variable_references', 'resolved_variable_references',
        'command_patterns', 'updates', 'budget_stops', 'instruction_budget_stops',
        'logic_decode_attempts', 'logic_aliases', 'instructions_attempted', 'code_bytes_admitted',
        'message_budget_stops')}
    coverage.update(present_logics=len(logics), scene_candidates=len(candidates),
                    expanded_text_bytes=text_budget.used, unique_text_bytes=text_budget.unique_bytes,
                    text_cache_hits=text_budget.cache_hits,
                    auxiliary_text_budget_stops=sum(item['status'] == 'budget' for item in (vocabulary, inventory)),
                    vocabulary_status=vocabulary['status'], inventory_status=inventory['status'],
                    vocabulary_groups=len(vocabulary['groups']),
                    vocabulary_entries=len(vocabulary['entries']), inventory_objects=len(inventory['objects']),
                    background_producing_logics=len(presentation_candidates),
                    room_dispatch_sites=len(dispatch_candidates),
                    resource_entries={kind: len(rows) for kind, rows in resource_rows.items()},
                    resource_census_complete=directory_ok,
                    resource_integrity_complete=directory_ok and not issues,
                    logic_layout_complete=has_logics and not counts['resource_errors'] and not counts['layout_errors'] and not counts['instruction_budget_stops'],
                    value_analysis_complete=stage == 'resolve' and has_logics and not counts['budget_stops'] and not counts['resource_errors'] and not counts['layout_errors'] and not counts['instruction_budget_stops'],
                    scene_discovery_complete=False, accepted_uil_interactions=0)
    if not include_text:
        vocabulary = {k: v for k, v in vocabulary.items() if k not in ('groups', 'entries')}
        vocabulary['groups'] = [{'number': group['number'], 'role': group['role'],
                                 'word_count': len(group['words'])}
                                for group in (word_groups or {}).values()]
        vocabulary['literal_entries_included'] = False
        inventory = {**inventory, 'objects': [{k: v for k, v in obj.items() if k != 'name'}
                                              for obj in inventory['objects']]}
    else:
        vocabulary['literal_entries_included'] = True
    result = {'format': FORMAT, 'profile': profile, 'stage': stage,
              'qualification': 'static_scene_candidates_only', 'executable': False,
              'budgets': {'max_instructions': max_instructions, 'max_updates': max_updates,
                          'max_code_bytes': max_code_bytes, 'max_message_bytes': max_message_bytes,
                          'max_report_bytes': max_report_bytes},
              'source': manifest, 'coverage': coverage, 'resource_issues': issues,
              'vocabulary': vocabulary, 'inventory': inventory,
              'scenes': candidates, 'presentation_candidates': presentation_candidates,
              'dispatch_candidates': dispatch_candidates, 'logics': logics,
              'requirements': {
                  'identity': 'typed room targets; logic numbers alone are not scenes',
                  'entry': 'initial and possible saved scan entries; dispatch unresolved',
                  'presentation': 'typed picture/view/sound/message references',
                  'conditions': 'ordered source tests retained as low-level IR',
                  'state_changes': 'source sites retained; game meaning unresolved',
                  'progression': 'literal/finite targets with entry-flow qualification',
                  'turn_effects': 'cycle-driven engine; no turn model recovered'},
              'remaining_obligations': list(_OBLIGATIONS)}
    # Adding the SHA-256 field costs 76 ASCII bytes; the CLI adds one newline.
    result['sha256'] = _digest(result, max_report_bytes - 77)
    return result
