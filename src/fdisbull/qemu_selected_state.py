"""Shared replay of selected CPU/RAM evidence; no machine execution or writes.

Backend adapters retain artifact loading, runtime identities and recovery policy.
The replay validates the ordered projection chain before any inverse is applied.
"""
from copy import deepcopy

from .debug_cpu_deltas import _fingerprint


def replay(history, target, *, format, load_document, remaining_ms):
    """Return the current and selected projections from verified delta records.

    ``load_document(entry, parent_sha256)`` checks the backend's artifact wrapper
    and returns its document. No backend CPU widths or address semantics are
    inferred here; admission and native inverse preparation remain adapters.
    """
    cpu = deepcopy(history['initial_cpu'])
    ram = list(history['initial_ram'])
    selected = (deepcopy(cpu), list(ram)) if target == 0 else None
    parent = history['anchor']['sha256']
    for entry in history['entries'][:history['cursor']]:
        remaining_ms()
        doc = load_document(entry, parent)
        if (doc.get('format') != format or doc.get('history') != history['id']
                or doc.get('identity') != history['identity'] or doc.get('binding') != history['binding']
                or doc.get('ranges') != history['ranges'] or doc.get('parent_sha256') != parent
                or doc.get('index') != entry['index'] or doc.get('before') != _fingerprint(cpu, ram)):
            raise ValueError('Selected CPU delta history chain differs')
        for name, change in doc['registers'].items():
            if name not in cpu or cpu[name] != change['before'] or type(change['after']) is not int or change['after'] < 0:
                raise ValueError('Selected CPU delta register chain differs')
            cpu[name] = change['after']
        for change in doc['memory']:
            number, offset = change['range'], change['offset']
            before, after = bytes.fromhex(change['before_hex']), bytes.fromhex(change['after_hex'])
            if (type(number) is not int or not 0 <= number < len(ram) or type(offset) is not int or offset < 0
                    or not before or len(before) != len(after) or offset + len(before) > len(ram[number])
                    or ram[number][offset:offset + len(before)] != before):
                raise ValueError('Selected CPU delta memory chain differs')
            ram[number] = ram[number][:offset] + after + ram[number][offset + len(before):]
        if doc.get('after') != _fingerprint(cpu, ram):
            raise ValueError('Selected CPU delta after-state hash differs')
        if entry['index'] == target:
            selected = (deepcopy(cpu), list(ram))
        parent = entry['sha256']
    if selected is None:
        raise ValueError('Selected CPU delta target is unavailable')
    return (cpu, ram), selected
