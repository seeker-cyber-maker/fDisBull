"""Bounded source-bound CHIP-8 traversal; descriptors are static candidates."""
from __future__ import annotations

from collections import deque
import hashlib
import json
from pathlib import Path
import sqlite3

from . import chip8, chip8_packages
from .chip8_intake import inspect_project

FORMAT = 'fdisbull-chip8-source-map-1'
_LIMIT = 8 * 1024 * 1024
_ASSUMPTION = 'original source fetch bytes remain unchanged'
_RESET_ASSUMPTION = 'initial PC is 0x200 and return stack is empty'
_REACHABILITY = 'original-source-conditional'


def decode(data, address):
    return chip8.decode(data, address)


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _producer():
    directory = Path(__file__).parent
    result = {}
    for key, name in (('source_map_sha256', 'chip8_source_map.py'), ('udl_sha256', 'chip8_udl.py'), ('decoder_sha256', 'chip8.py')):
        try:
            data = (directory / name).read_bytes()
        except OSError as error:
            raise ValueError('CHIP-8 source map producer unavailable') from error
        if len(data) > 1024 * 1024:
            raise ValueError('CHIP-8 source map producer exceeds limit')
        result[key] = _hash(data)
    return result


def _options(max_instructions, max_states, max_call_depth):
    values = (max_instructions, max_states, max_call_depth)
    if any(type(v) is not int or not 1 <= v <= maximum for v, maximum in zip(values, (1792, 8192, 16))):
        raise ValueError('Invalid CHIP-8 source map traversal budget')
    return dict(max_instructions=max_instructions, max_states=max_states, max_call_depth=max_call_depth)


def _identity(project, closure, version, expected):
    if project.db.in_transaction:
        raise ValueError('CHIP-8 source mapping requires no caller transaction')
    v = project.version(version)['id']
    guard = chip8_packages._source_guard(project, v)
    intake = inspect_project(project, version=v, expected_intake_sha256=expected)
    package = chip8_packages.info(project, closure, version=v, expected_intake_sha256=expected)
    if chip8_packages._source_guard(project, v) != guard:
        raise ValueError('CHIP-8 source changed during mapping admission')
    regions = project.regions(v)
    if len(regions) != 1:
        raise ValueError('CHIP-8 original source region unavailable')
    source = dict(intake_sha256=intake['intake_sha256'], source_sha256=intake['source']['sha256'],
                  mapped_sha256=intake['project']['mapped_sha256'], closure=closure,
                  closure_sha256=package['sha256'], packages=package['packages'])
    return v, guard, intake, package, bytes(regions[0].data), source


def _closure_guard(project, package, intake):
    rows = []
    for table, key in [('chip8_package_closures', package['closure'])] + [
            ('chip8_package_definitions', item['id']) for item in package['packages'].values()]:
        row = project.db.execute('SELECT id,sha256,document FROM ' + table + ' WHERE id=?', (key,)).fetchone()
        if row is None:
            raise ValueError('CHIP-8 package binding unavailable')
        rows.append([row['id'], row['sha256'], row['document']])
    if package['analysis'] is not None:
        rows.append(chip8_packages._analysis(project, intake))
    return _hash(_raw(rows))


def _walk(rom, options, decode):
    from . import chip8_udl
    instructions = []
    indexed = {}
    unsupported = set()
    states = []
    state_index = {}
    edges, frontiers = [], []
    queue = deque()
    budgets = False

    def frontier(state, reason, pc, stack, **extra):
        nonlocal budgets
        ident = 'f' + str(len(frontiers))
        frontiers.append(dict(id=ident, state=state, reason=reason, pc=pc, return_stack=list(stack), **extra))
        if reason in ('state_budget', 'instruction_budget', 'call_depth_budget'):
            budgets = True
        return ident

    def add(pc, stack, origin=None, kind='entry', condition=None):
        key = (pc, stack)
        if key not in state_index:
            if len(states) >= options['max_states']:
                f = frontier(origin, 'state_budget', pc, stack)
                if origin is not None:
                    edges.append(dict(source=origin, kind=kind, target=None, frontier=f, condition=condition, assumption=_ASSUMPTION, reachability=_REACHABILITY))
                return
            ident = 's' + str(len(states))
            state_index[key] = ident
            states.append(dict(id=ident, pc=pc, return_stack=list(stack), status='pending', reachability=_REACHABILITY))
            queue.append(key)
        if origin is not None:
            edges.append(dict(source=origin, kind=kind, target=state_index[key], frontier=None, condition=condition, assumption=_ASSUMPTION, reachability=_REACHABILITY))

    add(0x200, ())
    while queue:
        pc, stack = queue.popleft()
        sid = state_index[(pc, stack)]
        state = states[int(sid[1:])]
        reason = None
        if pc >= 0 and pc & 1: reason = 'odd_fetch'
        elif pc < 0 or pc >= 4096: reason = 'out_of_ram'
        elif pc < 0x200 or pc >= 0x200 + len(rom): reason = 'not_source_backed'
        elif pc + 1 >= 0x200 + len(rom): reason = 'truncated_tail'
        if reason:
            state['status'] = 'frontier'; frontier(sid, reason, pc, stack); continue
        if pc not in indexed:
            if len(instructions) >= options['max_instructions']:
                state['status'] = 'frontier'; frontier(sid, 'instruction_budget', pc, stack); continue
            word = rom[pc - 0x200:pc - 0x200 + 2]
            fact = None if pc in unsupported else decode(word, pc)
            if fact is None:
                unsupported.add(pc)
                state['status'] = 'frontier'; frontier(sid, 'unsupported_opcode', pc, stack, word_hex=word.hex()); continue
            desc = chip8_udl.describe(fact)
            item = dict(id='i' + str(len(instructions)), pc=pc, word_hex=word.hex(),
                        span=dict(offset=pc - 0x200, length=2, sha256=_hash(word)), decoded=fact, udl=desc)
            indexed[pc] = item
            instructions.append(item)
        state['status'] = 'instruction'
        item = indexed[pc]; fact = item['decoded']; flow = fact['flow']; name = fact['mnemonic']
        state['instruction'] = item['id']
        if name in ('save', 'bcd'):
            frontier(sid, 'possible_source_write', pc, stack)
        if name in ('save', 'load', 'bcd', 'drw'):
            frontier(sid, 'possible_i_range_fault', pc, stack)
        if name == 'wait_key':
            frontier(sid, 'key_wait', pc, stack)
            add(pc + 2, stack, sid, 'next', 'key_available')
        elif flow == 'conditional':
            add(pc + 2, stack, sid, 'not_taken', 'unknown')
            add(pc + 4, stack, sid, 'taken', 'unknown')
        elif flow == 'jump': add(fact['target'], stack, sid, 'jump')
        elif flow == 'call':
            if len(stack) >= options['max_call_depth']:
                frontier(sid, 'call_depth_budget' if options['max_call_depth'] < 16 else 'stack_overflow', pc, stack)
            else: add(fact['target'], stack + (pc + 2,), sid, 'call')
        elif flow == 'return':
            if not stack: frontier(sid, 'return_underflow', pc, stack)
            else: add(stack[-1], stack[:-1], sid, 'return')
        elif flow == 'indirect_jump': frontier(sid, 'indirect_jump', pc, stack)
        elif name in ('save', 'bcd'):
            add(pc + 2, stack, sid, 'next', 'nonfaulting_write_and_subsequent_fetch_matches_original_source')
        elif name in ('load', 'drw'):
            add(pc + 2, stack, sid, 'next', 'nonfaulting_i_range')
        else: add(pc + 2, stack, sid, 'next')
    used = set()
    for item in instructions:
        used.update((item['span']['offset'], item['span']['offset'] + 1))
    spans = []
    start = None
    for offset in range(len(rom) + 1):
        if offset < len(rom) and offset not in used:
            if start is None: start = offset
        elif start is not None:
            spans.append(dict(offset=start, pc=0x200 + start, length=offset - start, classification='unknown'))
            start = None
    coverage = dict(source_bytes=len(rom), classified_bytes=len(used), unclassified_bytes=len(rom)-len(used),
                    instructions=len(instructions), states=len(states), edges=len(edges), frontiers=len(frontiers),
                    worklist_exhausted=not budgets, budget_exhausted=budgets)
    return dict(instructions=instructions, states=states, edges=edges, frontiers=frontiers,
                unclassified_spans=spans, coverage=coverage)


def _table(project):
    return project.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='chip8_source_maps'").fetchone() is not None


def build(project, closure, *, max_instructions=256, max_states=2048, max_call_depth=16, version=None, expected_intake_sha256=None):
    options = _options(max_instructions, max_states, max_call_depth)
    v, guard, intake, package, rom, source = _identity(project, closure, version, expected_intake_sha256)
    producer = _producer()
    closure_guard = _closure_guard(project, package, intake)
    request = dict(source=source, producer=producer, options=options, assumptions=[_RESET_ASSUMPTION, _ASSUMPTION])
    request_sha = _hash(_raw(request))
    if _table(project):
        row = project.db.execute('SELECT id FROM chip8_source_maps WHERE request_sha256=?', (request_sha,)).fetchone()
        if row is not None:
            return info(project, row['id'], version=v, expected_intake_sha256=expected_intake_sha256)
    result = dict(format=FORMAT, status='bounded-static-candidate', request_sha256=request_sha, **request,
                  **_walk(rom, options, decode))
    data = _raw(result)
    if len(data) > _LIMIT: raise ValueError('CHIP-8 source map exceeds private artifact limit')
    sha = _hash(data); ident = 'chip8-map:' + sha
    if chip8_packages._source_guard(project, v) != guard or _producer() != producer or _closure_guard(project, package, intake) != closure_guard:
        raise ValueError('CHIP-8 source or package changed before mapping publication')
    if not hasattr(project.db, 'store'):
        raise ValueError('CHIP-8 source map requires a private external object store')
    with project.transaction(True):
        if chip8_packages._source_guard(project, v) != guard or _producer() != producer or _closure_guard(project, package, intake) != closure_guard:
            raise ValueError('CHIP-8 source or package changed before mapping publication')
        project.db.execute('CREATE TABLE IF NOT EXISTS chip8_source_maps (id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, document TEXT NOT NULL)')
        existing = project.db.execute('SELECT id,sha256,document FROM chip8_source_maps WHERE request_sha256=?', (request_sha,)).fetchone()
        if existing is None:
            external = project._external_text(data.decode('utf-8'))
            project.db.execute('INSERT INTO chip8_source_maps VALUES (?,?,?,?)', (ident, request_sha, sha, external))
        elif existing['id'] != ident or existing['sha256'] != sha or existing['document'] != data.decode('utf-8'):
            raise ValueError('Stored CHIP-8 source map differs from deterministic publication')
        if chip8_packages._source_guard(project, v) != guard or _producer() != producer or _closure_guard(project, package, intake) != closure_guard:
            raise ValueError('CHIP-8 source or package changed during mapping publication')
    return dict(mapping=ident, sha256=sha, **result)


def info(project, mapping, version=None, expected_intake_sha256=None):
    if project.db.in_transaction: raise ValueError('CHIP-8 source mapping requires no caller transaction')
    if not isinstance(mapping, str) or len(mapping) != 74 or not mapping.startswith('chip8-map:') or any(c not in '0123456789abcdef' for c in mapping[10:]):
        raise ValueError('Invalid CHIP-8 source map identity')
    if not _table(project): raise ValueError('CHIP-8 source map unavailable')
    try:
        row = project.db.execute('SELECT * FROM chip8_source_maps WHERE id=?', (mapping,)).fetchone()
        if row is None or not isinstance(row['document'], str): raise ValueError('CHIP-8 source map unavailable')
        data = row['document'].encode('utf-8')
        if len(data) > _LIMIT or _hash(data) != row['sha256'] or mapping != 'chip8-map:' + row['sha256']:
            raise ValueError('CHIP-8 source map hash differs')
        doc = json.loads(data)
        expected_keys = {'format', 'status', 'request_sha256', 'source', 'producer', 'options', 'assumptions', 'instructions', 'states', 'edges', 'frontiers', 'unclassified_spans', 'coverage'}
        if not isinstance(doc, dict) or set(doc) != expected_keys or _raw(doc) != data or doc['format'] != FORMAT or doc['status'] != 'bounded-static-candidate': raise ValueError('Invalid CHIP-8 source map document')
        options = _options(**doc['options'])
        v, guard, intake, package, rom, source = _identity(project, doc['source']['closure'], version, expected_intake_sha256)
        producer = _producer()
        closure_guard = _closure_guard(project, package, intake)
        request = dict(source=source, producer=producer, options=options, assumptions=[_RESET_ASSUMPTION, _ASSUMPTION])
        if any(doc.get(k) != val for k, val in request.items()) or doc['request_sha256'] != _hash(_raw(request)) or row['request_sha256'] != doc['request_sha256']:
            raise ValueError('CHIP-8 source map binding differs')
        from . import chip8_udl
        facts = {}
        for item in doc['instructions']:
            pc = item['pc']; offset = pc - 0x200; word = rom[offset:offset+2]
            if (type(pc) is not int or pc & 1 or offset < 0 or len(word) != 2 or item['word_hex'] != word.hex()
                or item['span'] != dict(offset=offset, length=2, sha256=_hash(word)) or pc in facts
                or item['decoded']['address'] != pc or item['decoded']['bytes'] != word.hex() or item['decoded']['size'] != 2):
                raise ValueError('CHIP-8 source map instruction differs')
            chip8_udl.validate(item['decoded'], item['udl'])
            facts[pc] = item['decoded']
        # Unsupported frontiers must really be outside the declared opcode patterns.
        for frontier in doc['frontiers']:
            if frontier['reason'] == 'unsupported_opcode':
                pc = frontier['pc']; offset = pc - 0x200
                word_bytes = rom[offset:offset + 2]
                if (type(pc) is not int or pc & 1 or offset < 0 or len(word_bytes) != 2 or
                        frontier.get('word_hex') != word_bytes.hex() or
                        any(int.from_bytes(word_bytes, 'big') & mask == value for mask, value, _, _ in chip8._PATTERNS)):
                    raise ValueError('CHIP-8 unsupported frontier differs from source word')
        # Reconstruct the graph from verified stored facts, without invoking the decoder.
        rebuilt = _walk(rom, options, lambda word, pc: facts.get(pc))
        for key, value in rebuilt.items():
            if doc.get(key) != value: raise ValueError('CHIP-8 source map traversal differs')
        if (chip8_packages._source_guard(project, v) != guard or _producer() != producer or
                _closure_guard(project, package, intake) != closure_guard):
            raise ValueError('CHIP-8 source or package changed during mapping inspection')
        return dict(mapping=mapping, sha256=row['sha256'], **doc)
    except (KeyError, TypeError, sqlite3.Error, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid CHIP-8 source map document') from error
