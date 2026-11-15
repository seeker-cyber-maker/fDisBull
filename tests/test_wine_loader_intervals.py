"""Finite native Wine intervals with explicit architectural end boundaries."""
import base64
from copy import deepcopy
import hashlib
import json
import time

import pytest
from capstone import x86_const as X

from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
from test_wine_loader_dispatch import _accesses, _rows


def _check_interval_boundary(role, instruction, entry, ending, boundary, read):
    old, new = (int(context['general']['rsp'], 16) for context in (entry, ending))
    if int(ending['rip'], 16) != int(boundary['stop_address'], 16) or new - old != boundary['expected_stack_delta']:
        raise ValueError('Native interval did not reach its exact address/stack boundary')
    if role == 'attach_success_tail':
        if boundary['kind'] != 'ret' or instruction.mnemonic != 'ret':
            raise ValueError('Attach success tail requires its actual completed RET')
    elif role == 'detach_selection_prefix':
        if boundary['kind'] != 'callee-entry' or instruction.mnemonic != 'call':
            raise ValueError('Detach selection requires the actual CALL into the selected dispatcher')
        if int(ending['general']['rdx'], 16) & 0xffffffff:
            raise ValueError('Detach selection did not establish DLL_PROCESS_DETACH')
    else:
        raise ValueError('Unknown native loader interval role')


def capture_loader_interval(debug, *, name, role, start_address, stop_address, boundary_kind,
                            expected_stack_delta, protected_ranges, extra_ranges=(),
                            loader_module, subject_module, subject_source_sha256,
                            max_steps=128, timeout_ms=180000):
    """Collect a source-bounded tail or selector, never executing another callee.

    Only the terminal selector CALL is admitted. Unexpected activation-context,
    debug-logging or other calls stop before execution and retain a partial
    artifact. A complete interval ends before executing its destination.
    """
    expected = {'attach_success_tail': ('ret', 0x80), 'detach_selection_prefix': ('callee-entry', -0x50)}
    if role not in expected or (boundary_kind, expected_stack_delta) != expected[role]:
        raise ValueError('Loader interval role requires its declared RET/CALL stack contract')
    if type(max_steps) is not int or not 1 <= max_steps <= 2048:
        raise ValueError('max_steps must be 1..2048')
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('timeout_ms must be 1..600000')
    deadline = time.monotonic() + timeout_ms / 1000
    boundary = {'start_address': hex(start_address), 'stop_address': hex(stop_address),
                'kind': boundary_kind, 'expected_stack_delta': expected_stack_delta}
    document = {'format': 'fdisbull-wine-loader-interval-1', 'status': 'partial', 'role': role,
        'run': debug.run_id, 'boundary': boundary, 'semantics': PE_TRACE_SEMANTICS,
        'controller_source_sha256': debug.project.meta['source_sha256'],
        'subject_source_sha256': subject_source_sha256, 'loader_module': deepcopy(loader_module),
        'subject_module': deepcopy(subject_module), 'protected_ranges': deepcopy(protected_ranges),
        'extra_ranges': deepcopy(list(extra_ranges)), 'steps': [], 'code_versions': [], 'summaries': [],
        'scope': 'Exact stopped-boundary native loader interval; no other module/callee or whole-loader claim'}
    first_seen, current, seen_at = {}, {}, {}
    def call(method, params=None):
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            raise TimeoutError('Native loader interval total deadline exhausted')
        return debug.call(method, params, timeout_ms=remaining + 1000)
    def read(address, length):
        raw = base64.b64decode(call('read', {'address': address, 'length': length})['data_base64'], validate=True)
        if len(raw) != length:
            raise ValueError('Incomplete native loader interval memory read')
        return raw
    def retain(address, raw, step):
        for k, byte in enumerate(raw):
            a = address + k
            if a not in first_seen:
                first_seen[a], seen_at[a] = byte, step
            current[a] = byte
    def snapshot(ranges, step):
        rows = []
        for item in ranges:
            address = int(item['address'], 16) if isinstance(item['address'], str) else item['address']
            raw = read(address, item['length'])
            retain(address, raw, step)
            rows.append({'address': hex(address), 'hex': raw.hex(), 'role': item.get('role')})
        return rows
    def images(rows):
        return [row for row in rows if (row.get('role') or '').endswith('code')]
    try:
        entry = call('registers')
        if int(entry['rip'], 16) != start_address:
            raise ValueError('Native interval is not at its declared source start')
        modules, info = call('modules'), debug.thread_info()
        teb = int(info['teb'], 16)
        document.update(entry=entry, modules_before=modules, thread_info=info,
            segment_binding={'segment': 'gs', 'teb': hex(teb), 'gs_base_register_observed': False,
                             'source': 'Observed debug-event TEB plus explicit Win64 convention'})
        protected = snapshot(protected_ranges, 0)
        snapshot(extra_ranges, 0)
        document['code_versions'].append({'after_step': 0, 'images': images(protected)})
        for index in range(max_steps):
            before = call('registers'); pc = int(before['rip'], 16)
            if before['thread'] != entry['thread']:
                raise ValueError('Native interval changed selected thread')
            raw = read(pc, 15)
            instruction, accesses = _accesses(raw, before, teb)
            owners = [m for m in modules['modules'] if int(m['base'], 16) <= pc
                      and pc + instruction.size <= int(m['base'], 16) + m['size']]
            if len(owners) != 1 or any(owners[0].get(k) != loader_module.get(k)
                    for k in ('name', 'base', 'size', 'bits', 'generation')):
                raise ValueError('Native interval would execute outside its selected Wine loader image')
            if instruction.mnemonic == 'call':
                if role != 'detach_selection_prefix' or len(instruction.operands) != 1 or instruction.operands[0].type != X.X86_OP_IMM or instruction.operands[0].imm != stop_address:
                    raise ValueError('Unmodeled callee reached before the bounded loader interval completed')
            elif instruction.mnemonic == 'ret' and role != 'attach_success_tail':
                raise ValueError('Selector returned before reaching its selected dispatcher CALL')
            footprint = []
            for access in accesses:
                address, width = int(access['address'], 16), access['width']
                prior = read(address, width)
                retain(address, prior, index)
                footprint.append(access | {'before_hex': prior.hex()})
            event, state = debug._step_instruction(deadline)
            if event is None or state['stop_reason']['kind'] != 'step':
                document['interrupted_state'] = state
                raise ValueError('Native loader interval instruction did not complete exactly')
            assert event['registers'] == before
            event['project_address'] = None
            normalize_trace('wine-qemu', [event], version=debug.version['id'])
            assert bytes.fromhex(event['bytes']) == raw[:instruction.size]
            after = call('registers')
            for access in footprint:
                address, width = int(access['address'], 16), access['width']
                following = read(address, width)
                access['after_hex'] = following.hex()
                retain(address, following, index + 1)
            following_protected = snapshot(protected_ranges, index + 1)
            document['steps'].append({'event': event, 'after': after,
                'code_read': {'address': hex(pc), 'hex': raw.hex(), 'sha256': hashlib.sha256(raw).hexdigest(),
                              'module': deepcopy(owners[0])}, 'accesses': footprint,
                'protected_before': protected, 'protected_after': following_protected})
            code_write = any(a['kind'] == 'write' and any(int(r['address'], 16) < int(a['address'], 16) + a['width']
                and int(a['address'], 16) < int(r['address'], 16) + len(r['hex']) // 2 for r in images(protected)) for a in footprint)
            if code_write or images(protected) != images(following_protected):
                document['code_versions'].append({'after_step': index + 1, 'images': images(following_protected),
                                                  'classified_code_write': code_write})
            protected = following_protected
            if int(after['rip'], 16) == stop_address:
                _check_interval_boundary(role, instruction, entry, after, boundary, read)
                if role == 'detach_selection_prefix':
                    wm = int(after['general']['rcx'], 16)
                    pointer = read(wm + 0x30, 8)
                    if int.from_bytes(pointer, 'little') != int(subject_module['base'], 16):
                        raise ValueError('First selected dispatcher belongs to another DLL; it was not executed')
                    retain(wm + 0x30, pointer, index + 1)
                    document['selection'] = {'modref': hex(wm), 'dll_base': subject_module['base'],
                        'reason_low32': 0, 'base_pointer_address': hex(wm + 0x30), 'base_pointer_hex': pointer.hex()}
                document.update(status='complete', exit=after, modules_after=call('modules'))
                break
            if instruction.mnemonic in ('call', 'ret'):
                raise ValueError('Interval architectural boundary differs; destination was not executed')
        else:
            raise ValueError('Native loader interval exceeded its finite instruction budget')
    finally:
        document.update(entry_memory=_rows(first_seen), exit_memory=_rows(current),
                        first_seen_steps={hex(a): step for a, step in seen_at.items()})
        receipt = debug._artifact(name, 'wine-loader-interval', json.dumps(document, indent=2).encode(),
                                  {'status': document['status'], 'steps': len(document['steps']), 'role': role})
    return {'artifact': receipt, 'document': document}


def replay_wine_loader_interval(interval):
    """Independently replay one concrete caller fragment and its exact boundary."""
    import capstone
    from test_wine_loader_dispatch_replay import replay_wine_loader_capsule

    assert interval['format'] == 'fdisbull-wine-loader-interval-1'
    expected = {'attach_success_tail': ('ret', 0x80),
                'detach_selection_prefix': ('callee-entry', -0x50)}
    role, boundary = interval['role'], interval['boundary']
    assert (boundary['kind'], boundary['expected_stack_delta']) == expected[role]
    steps = interval['steps']
    assert steps and int(interval['entry']['rip'], 16) == int(boundary['start_address'], 16)
    current = interval['entry']
    for step in steps:
        assert step['event']['registers'] == current, 'Discontinuous native caller context'
        current = step['after']
    assert current == interval['exit'], 'Caller exit does not match the final completed instruction'
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    final = next(decoder.disasm(bytes.fromhex(steps[-1]['event']['bytes']),
                               int(steps[-1]['event']['address'], 16)))
    _check_interval_boundary(role, final, interval['entry'], current, boundary, None)
    for epoch in interval['code_versions']:
        index = epoch['after_step']
        assert type(index) is int and 0 <= index <= len(steps)
        rows = steps[index - 1]['protected_after'] if index else steps[0]['protected_before']
        assert epoch['images'] == [row for row in rows if (row.get('role') or '').endswith('code')]
    replay = replay_wine_loader_capsule(interval)
    return replay | {'status': 'native_loader_interval_replayed', 'role': role,
        'boundary': deepcopy(boundary), 'code_epochs': len(interval['code_versions']),
        'scope': 'Concrete source-bound caller fragment with its actual RET/CALL boundary; '
                 'outer scheduling, surrounding loader intervals and universal behavior remain unproved'}


def _context(ip, stack, reason=0):
    return {'rip': hex(ip), 'general': {'rsp': hex(stack), 'rdx': hex(reason)}}


@pytest.mark.parametrize('role,kind,delta,mnemonic', [
    ('attach_success_tail', 'ret', 0x80, 'ret'),
    ('detach_selection_prefix', 'callee-entry', -0x50, 'call')])
def test_native_interval_requires_actual_ret_or_call_and_exact_stack_change(role, kind, delta, mnemonic):
    from types import SimpleNamespace
    entry, exit = _context(0x1000, 0x8008), _context(0x2000, 0x8008 + delta)
    boundary = {'stop_address': '0x2000', 'kind': kind, 'expected_stack_delta': delta}
    _check_interval_boundary(role, SimpleNamespace(mnemonic=mnemonic), entry, exit, boundary, None)
    for bad in (_context(0x2001, 0x8008 + delta), _context(0x2000, 0x8010 + delta)):
        with pytest.raises(ValueError, match='address/stack boundary'):
            _check_interval_boundary(role, SimpleNamespace(mnemonic=mnemonic), entry, bad, boundary, None)
    with pytest.raises(ValueError):
        _check_interval_boundary(role, SimpleNamespace(mnemonic='jmp'), entry, exit, boundary, None)


def test_detach_interval_cannot_borrow_an_attach_reason():
    from types import SimpleNamespace
    with pytest.raises(ValueError, match='DLL_PROCESS_DETACH'):
        _check_interval_boundary('detach_selection_prefix', SimpleNamespace(mnemonic='call'),
            _context(0x1000, 0x8008), _context(0x2000, 0x7fb8, 1),
            {'stop_address': '0x2000', 'kind': 'callee-entry', 'expected_stack_delta': -0x50}, None)


def test_independent_interval_cpu_replay_checks_actual_ret_and_memory():
    names = ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp',
             'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15')
    entry = {'rip': '0x1000', 'rflags': '0x202', 'general': {name: '0x0' for name in names}}
    entry['general']['rsp'] = '0x8000'
    added = deepcopy(entry)
    added.update(rip='0x1004', rflags='0x206')
    added['general']['rsp'] = '0x8078'
    exit = deepcopy(added)
    exit.update(rip='0x2000')
    exit['general']['rsp'] = '0x8080'
    protected = [{'address': '0x3000', 'hex': '90', 'role': 'dll-code'}]
    stack = {'address': '0x8078', 'hex': (0x2000).to_bytes(8, 'little').hex()}
    interval = {'format': 'fdisbull-wine-loader-interval-1', 'status': 'complete',
        'role': 'attach_success_tail', 'summaries': [], 'entry': entry, 'exit': exit,
        'boundary': {'start_address': '0x1000', 'stop_address': '0x2000',
                     'kind': 'ret', 'expected_stack_delta': 0x80},
        'subject_module': {'base': '0x3000', 'size': 4096}, 'thread_info': {'teb': '0x4000'},
        'entry_memory': [stack] + protected, 'exit_memory': [stack] + protected,
        'code_versions': [{'after_step': 0, 'images': protected}], 'steps': []}
    for before, after, raw, padded, accesses in (
            (entry, added, '4883c478', '4883c478c3' + '90' * 10, []),
            (added, exit, 'c3', 'c3' + '90' * 14,
             [{'kind': 'read', 'address': stack['address'], 'width': 8,
               'before_hex': stack['hex'], 'after_hex': stack['hex']}])):
        interval['steps'].append({'event': {'address': before['rip'], 'bytes': raw, 'registers': before},
            'after': after, 'code_read': {'address': before['rip'], 'hex': padded}, 'accesses': accesses,
            'protected_before': protected, 'protected_after': protected})
    replay = replay_wine_loader_interval(interval)
    assert replay['status'] == 'native_loader_interval_replayed' and replay['instructions'] == 2
    corrupted = deepcopy(interval)
    corrupted['steps'][1]['accesses'][0]['after_hex'] = '00' * 8
    with pytest.raises(AssertionError):
        replay_wine_loader_interval(corrupted)
