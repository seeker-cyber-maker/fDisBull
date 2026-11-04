#!/usr/bin/env python3
"""Audit teaching sites for the three reported unused SNES Shadowrun keywords.

The exact caller-owned USA ROM is required. Output contains semantic labels,
addresses, counts and hashes, never decoded dialogue or source bytes. This is a
static catalogue audit, not a whole-game reachability proof or an unlock patch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROM_SHA256 = 'e6bc0a595d5c7c4bc0bbb61ffe35a70288a77eb78544ed74682d489a9e6f07f4'
TARGETS = {0x03: 'Arena', 0x24: 'Norbert', 0x29: 'Scalper'}
OPERAND_BYTES = {0x00: 1, 0x02: 1, 0x0a: 1, 0x0c: 1, 0x16: 1,
                 0x2c: 1, 0x34: 1, 0x58: 1,
                 0x04: 2, 0x0e: 2, 0x14: 2, 0x18: 2, 0x2e: 2,
                 0x36: 2, 0x44: 2, 0x46: 2, 0x48: 2, 0x4c: 2, 0x52: 2}
BRANCHES = {0x44, 0x46, 0x48, 0x4c}
NO_FALLTHROUGH = {0x48, 0x50, 0x56}


def word(data: bytes, at: int) -> int:
    if not 0 <= at < len(data) - 1:
        raise ValueError('word outside supplied data')
    return int.from_bytes(data[at:at + 2], 'little')


def dialogue_entries(data: bytes, start: int, limit: int) -> tuple[list[dict], int]:
    """Parse one source record, refusing malformed lengths and repeated selectors."""
    if not 0 <= start <= limit - 5 <= len(data) - 5:
        raise ValueError('invalid dialogue extent')
    at = start + 4
    entries, selectors = [], set()
    for _ in range(256):
        if at >= limit:
            raise ValueError('unterminated dialogue record')
        selector = data[at]
        if selector == 0xf8:
            return entries, at + 1
        if at + 3 > limit or selector in selectors:
            raise ValueError('invalid dialogue selector')
        selectors.add(selector)
        length, control = data[at + 1:at + 3]
        count = control & 15
        has_script = bool(control & 128)
        if length != 4 + count + 2 * has_script or at + 1 + length > limit:
            raise ValueError('invalid dialogue entry length')
        learns = list(data[at + 3:at + 3 + count])
        if any(key >= 64 for key in learns):
            raise ValueError('keyword outside source name table')
        text_at = at + 3 + count + 2 * has_script
        entries.append({'selector': selector, 'learns': learns,
                        'entry_offset': at, 'text_pointer': word(data, text_at),
                        'script': word(data, text_at - 2) if has_script else None})
        at += length + 1
    raise ValueError('dialogue record budget exhausted')


def decode_name(rom: bytes, pointer: int) -> bytes:
    """Read a bounded source Huffman string privately; do not export its bytes."""
    at = ((30 if pointer & 0x8000 else 29) << 15) + (pointer & 0x7fff)
    bits, output = [], bytearray()
    for _ in range(256):
        node = 0
        for _ in range(32):
            if not bits:
                if at + 2 > len(rom):
                    raise ValueError('compressed name outside source')
                value = int.from_bytes(rom[at:at + 2], 'big')
                bits = [(value >> n) & 1 for n in range(15, -1, -1)]
                at += 2
            node += bits.pop(0) * 2
            if node > 0x7ffe:
                raise ValueError('invalid source Huffman node')
            leaf = word(rom, 0xe8000 + node)
            if leaf & 0x8000:
                break
            node = leaf
        else:
            raise ValueError('source Huffman depth exceeded')
        for symbol in ((leaf >> 8) & 127, leaf & 127):
            if symbol == 10:
                return bytes(output)
            if symbol:
                output.append(symbol)
    raise ValueError('source keyword name budget exceeded')


def script_cfg(data: bytes, start: int, end: int, valid: set[int]) -> tuple[dict, dict]:
    """Conservative direct CFG, retaining both arms and local-call returns.

    Branch PCs are relative to the code start after its two-byte header. Local
    calls include their target and fallthrough; ordinary script calls continue
    locally and every script-table root is audited separately.
    """
    todo, seen, occupied = [0], {}, {}
    incoming = defaultdict(set)
    while todo:
        pc = todo.pop()
        if pc in seen:
            continue
        at = start + pc
        if not start <= at < end <= len(data):
            raise ValueError('script target outside declared extent')
        op = data[at]
        if op not in valid:
            raise ValueError('unsupported source script opcode')
        size = 1 + OPERAND_BYTES.get(op, 0)
        if at + size > end:
            raise ValueError('truncated source script instruction')
        for offset in range(at, at + size):
            if offset in occupied and occupied[offset] != at:
                raise ValueError('overlapping source script instructions')
            occupied[offset] = at
        seen[pc] = (at, op, size)
        targets = []
        if op in BRANCHES:
            targets.append(word(data, at + 1))
        if op not in NO_FALLTHROUGH:
            targets.append(pc + size)
        for target in targets:
            incoming[target].add(pc)
            todo.append(target)
    return seen, dict(incoming)


def constant_learn_argument(data: bytes, pc: int, seen: dict, incoming: dict) -> int:
    """Require every incoming edge to supply the same immediate keyword ID."""
    predecessors = incoming.get(pc, set())
    if not predecessors or pc == 0:
        raise ValueError('unqualified learn-keyword entry')
    values = set()
    for previous in predecessors:
        at, op, size = seen[previous]
        if previous + size != pc or op != 0x00:
            raise ValueError('learn-keyword argument is not an exclusive immediate push')
        values.add(data[at + 1])
    if len(values) != 1:
        raise ValueError('ambiguous learn-keyword argument')
    return values.pop()


def audit(rom: bytes) -> dict:
    digest = hashlib.sha256(rom).hexdigest()
    if len(rom) != 1048576 or digest != ROM_SHA256:
        raise ValueError('this audit requires the exact qualified SNES source')
    names = [decode_name(rom, word(rom, 0x68000 + 2 * key)) for key in range(64)]
    for key, label in TARGETS.items():
        if names[key] != label.encode('ascii'):
            raise ValueError('target keyword label mismatch')
    normal = {key for key, name in enumerate(names) if not name.startswith(b'Spare Word ')}
    learns, responses, ranges = defaultdict(list), defaultdict(list), []
    entry_count = 0
    # $80:947A is the source conversation pointer directory; the next
    # source routine starts at $80:9590, after 139 word entries.
    roots = [word(rom, 0x147a + 2 * tag) for tag in range(139)]
    if len(set(roots)) != 139:
        raise ValueError('unexpected conversation directory alias')
    for tag, pointer in enumerate(roots):
        if not 0x80c0 <= pointer < 0x92af:
            raise ValueError('conversation root outside source catalogue')
        at = 0x68000 + (pointer & 0x7fff)
        entries, end = dialogue_entries(rom, at, 0x692af)
        ranges.append((at, end))
        entry_count += len(entries)
        for entry in entries:
            site = {'tag': tag, 'record': pointer,
                    'entry_offset': entry['entry_offset'], 'selector': entry['selector']}
            for key in entry['learns']:
                learns[key].append(site)
            if entry['selector'] in TARGETS:
                responses[entry['selector']].append(site | {
                    'text_pointer': entry['text_pointer'], 'script': entry['script']})
    ranges.sort()
    if (ranges[0][0] != 0x680c0 or ranges[-1][1] != 0x692af or
            any(a[1] != b[0] for a, b in zip(ranges, ranges[1:]))):
        raise ValueError('conversation catalogue has a gap or overlap')
    # $80:F353 dispatches even opcode values through the table at $F27E.
    # $F8F1 is the source illegal-operation trap; $54 routes to it through
    # $F485. $C0/$C2 are the final valid one-byte specializations.
    valid = {op for op in range(0, 196, 2)
             if word(rom, 0x727e + op) != 0xf8f1 and op != 0x54}
    if (word(rom, 0x15604 + 2 * 0x71) != 0x90cf or
            rom[0x15895 + 0x71] != 1 or rom[0x157ba + 0x71] != 0):
        raise ValueError('unqualified source Learn-keyword ABI')
    script_roots = []
    for script in range(936):
        bank = rom[0x15970 + script]
        pointer = word(rom, 0x15d18 + 2 * script)
        if pointer < 0x8000 or not 0x80 <= bank <= 0x9f:
            raise ValueError('unqualified source script root')
        script_roots.append((script, ((bank & 127) << 15) + (pointer & 0x7fff), bank))
    native_learns, all_instructions, raw_writes = [], set(), []
    for script, start, bank in script_roots:
        end = min([a for _, a, b in script_roots if b == bank and a > start] +
                  [((bank & 127) + 1) << 15])
        seen, incoming = script_cfg(rom, start + 2, end, valid)
        all_instructions.update(at for at, _, _ in seen.values())
        for pc, (at, op, _) in seen.items():
            if op == 0x58 and rom[at + 1] == 0x71:
                native_learns.append({'script': script, 'pc': pc, 'offset': at,
                                      'keyword': constant_learn_argument(rom, pc, seen, incoming)})
            if op in (0x2e, 0x36):
                first = word(rom, at + 1)
                last = first + (op == 0x36)
                if first <= 0x3ce3 and last >= 0x3ca3:
                    raw_writes.append({'script': script, 'pc': pc, 'address': first})
    native_ids = {site['keyword'] for site in native_learns}
    missing = normal - set(learns) - native_ids
    if missing != set(TARGETS) or raw_writes:
        raise ValueError('reported unused keyword classification no longer holds')
    return {
        'format': 'shadowrun-snes-keyword-audit-1', 'result': 'pass-bounded-static',
        'source_sha256': digest,
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'catalogue': {'keyword_slots': 64, 'named_keywords': len(normal),
                      'spare_slots': 64 - len(normal), 'conversation_roots': len(roots),
                      'conversation_entries': entry_count,
                      'record_start': ranges[0][0], 'record_end_exclusive': ranges[-1][1],
                      'dialogue_taught_ids': len(learns),
                      'combined_taught_named_ids': len(normal - missing)},
        'scripts': {'roots': len(script_roots), 'valid_opcode_handlers': len(valid),
                    'unique_reachable_instruction_addresses': len(all_instructions),
                    'unresolved_frontier': 0, 'native_learn_sites': native_learns,
                    'fixed_raw_keyword_store_sites': raw_writes},
        'keywords': [
            {'id': key, 'name': label, 'dialogue_teaching_sites': learns[key],
             'native_learn_sites': [site for site in native_learns if site['keyword'] == key],
             'dedicated_responses': responses[key],
             'classification': 'no teaching site in audited catalogues'}
            for key, label in TARGETS.items()],
        'claim': 'The source conversation and script catalogues contain no teaching site for '
                 'these three named keywords. Norbert and Scalper retain dedicated responses; '
                 'Arena has none. Ordinary learned-keyword selection cannot expose an unlearned ID.',
        'limits': ['Static conservative CFG coverage is not proof that every decoded instruction '
                   'is reachable in ordinary play.',
                   'No whole-game native control-flow or arbitrary indirect-write proof; '
                   'memory corruption, debug intervention and other editions are excluded.',
                   'Dedicated response records were not reached by an ordinary gameplay route. '
                   'No keyword was injected or unlocked.']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must be a new receipt path')
    report = audit(args.rom.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': report['result'], 'keywords': [
        {'id': row['id'], 'name': row['name'], 'responses': len(row['dedicated_responses'])}
        for row in report['keywords']], 'output': str(args.output.resolve())}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
