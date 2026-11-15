"""One native selected-DLL process_attach invocation, with an exact MODULE view.

The selected node, empty notification path and authored DLL are observed once.
Other notification, activation-context or dependency calls stop before execution.
"""
import base64
from copy import deepcopy
import hashlib
import json
import time

import capstone
from capstone import x86_const as X
import pytest

from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
from test_wine_loader_dispatch import _accesses, _rows, capture_loader_capsule


def _cells(rows):
    cells = {}
    for row in rows:
        start = int(row['address'], 16)
        for offset, byte in enumerate(bytes.fromhex(row['hex'])):
            assert start + offset not in cells, 'Overlapping native memory rows'
            cells[start + offset] = byte
    return cells


def _admit_outer_instruction(instruction, *, module_entry_address, notification_entry_address,
                             module_seen, active_notification):
    if instruction.mnemonic != 'call':
        return None
    if len(instruction.operands) != 1 or instruction.operands[0].type != X.X86_OP_IMM:
        raise ValueError('Unobserved notification or indirect callee would execute outside the selected path')
    target = instruction.operands[0].imm
    if active_notification is not None:
        raise ValueError('The admitted empty notification path cannot execute a callee')
    if target == notification_entry_address and not module_seen:
        return 'notification'
    if target == module_entry_address and not module_seen:
        return 'module'
    raise ValueError('Unexpected activation, dependency, notification or repeated dispatcher callee')


def _merge_module_observation(document, embedded, first, current, seen):
    """Join exact observed bytes without resetting prefix-written entry cells."""
    inner = embedded['document']
    index = len(document['steps'])
    assert document['steps'][-1]['after'] == inner['entry']
    assert inner['steps'][0]['event']['registers'] == inner['entry']
    assert inner['steps'][-1]['after'] == inner['exit']
    assert inner['steps'][0]['protected_before'] == document['steps'][-1]['protected_after']
    for address, byte in _cells(inner['entry_memory']).items():
        if address in current and current[address] != byte:
            raise ValueError('Embedded MODULE entry memory disagrees with the outer prefix')
        if address not in first:
            first[address] = byte
            seen[address] = index + inner['first_seen_steps'][hex(address)]
        current[address] = byte
    for step in inner['steps']:
        for access in step['accesses']:
            address = int(access['address'], 16)
            if bytes(current[address + k] for k in range(access['width'])) != bytes.fromhex(access['before_hex']):
                raise ValueError('Embedded MODULE access does not join the preceding byte state')
        # Native rows observe before/after the complete instruction, including
        # both rows of one read-modify-write operand. A read's after value must
        # never advance the state before the matching write's old value check.
        for access in step['accesses']:
            if access['kind'] != 'write':
                continue
            address = int(access['address'], 16)
            for offset, byte in enumerate(bytes.fromhex(access['after_hex'])):
                current[address + offset] = byte
        for access in step['accesses']:
            address = int(access['address'], 16)
            if bytes(current[address + k] for k in range(access['width'])) != bytes.fromhex(access['after_hex']):
                raise ValueError('Embedded MODULE access after value disagrees with the completed instruction')
        for row in step['protected_after']:
            for offset, byte in enumerate(bytes.fromhex(row['hex'])):
                if current[int(row['address'], 16) + offset] != byte:
                    raise ValueError('Embedded MODULE protected bytes disagree with its actual write ledger')
                current[int(row['address'], 16) + offset] = byte
        document['steps'].append(deepcopy(step))
    if any(current[address] != byte for address, byte in _cells(inner['exit_memory']).items()):
        raise ValueError('Embedded MODULE exit memory disagrees with its full instruction ledger')
    document['module_span'] = {'first_step': index, 'last_step': len(document['steps']) - 1,
                               'artifact': embedded['artifact']}
    for span in inner['callback_spans']:
        document['callback_spans'].append(span | {'first_step': index + span['first_step'],
            'last_step': index + span['last_step']})
    for epoch in inner['code_versions'][1:]:
        document['code_versions'].append(deepcopy(epoch) | {'after_step': index + epoch['after_step']})


def capture_process_attach(debug, *, name, entry_address, module_entry_address,
                           notification_entry_address, dll_base, protected_ranges,
                           extra_ranges=(), module_extra_ranges=(), subject_symbols,
                           subject_source_sha256, subject_module, loader_module,
                           on_boundary=None, max_steps=1024, timeout_ms=600000):
    """Trace the actual outer invocation and delegate its one MODULE body once.

    The full observation embeds exactly the already-retained MODULE steps. The
    original nested artifact, callback epochs and live observation hooks remain
    available to the existing binder; no instruction is executed a second time.
    """
    if type(max_steps) is not int or not 1 <= max_steps <= 10000:
        raise ValueError('max_steps must be 1..10000')
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('timeout_ms must be 1..600000')
    if on_boundary is not None and not callable(on_boundary):
        raise ValueError('on_boundary must be callable')
    deadline = time.monotonic() + timeout_ms / 1000
    document = {'format': 'fdisbull-wine-process-attach-1', 'status': 'partial',
        'run': debug.run_id, 'semantics': PE_TRACE_SEMANTICS, 'steps': [],
        'summaries': [], 'notification_spans': [], 'callback_spans': [], 'code_versions': [],
        'controller_source_sha256': debug.project.meta['source_sha256'],
        'subject_source_sha256': subject_source_sha256, 'subject_module': deepcopy(subject_module),
        'loader_module': deepcopy(loader_module), 'protected_ranges': deepcopy(protected_ranges),
        'extra_ranges': deepcopy(list(extra_ranges)),
        'scope': 'Actual source-bound selected-node process_attach normal path and original RET; '
                 'other DLLs, outer scheduling, faults, exceptions and process lifetime remain unproved'}
    first, current, seen = {}, {}, {}
    embedded, notification = None, None

    def call(method, params=None):
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            raise TimeoutError('Native process_attach total deadline exhausted')
        return debug.call(method, params, timeout_ms=remaining + 1000)

    def read(address, width):
        raw = base64.b64decode(call('read', {'address': address, 'length': width})['data_base64'], validate=True)
        if len(raw) != width:
            raise ValueError('Incomplete native process_attach memory read')
        return raw

    def retain(address, raw, step):
        for offset, byte in enumerate(raw):
            cell = address + offset
            if cell not in first:
                first[cell], seen[cell] = byte, step
            current[cell] = byte

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

    def owner(address, width):
        matches = [m for m in modules['modules'] if int(m['base'], 16) <= address
                   and address + width <= int(m['base'], 16) + m['size']]
        if len(matches) != 1 or any(matches[0].get(k) != loader_module.get(k)
                for k in ('name', 'base', 'size', 'bits', 'generation')):
            raise ValueError('An outer process_attach instruction would leave the selected Wine source image')
        return deepcopy(matches[0])

    def signal(kind, payload):
        if on_boundary is not None:
            on_boundary(kind, payload)

    try:
        entry = call('registers')
        if int(entry['rip'], 16) != entry_address:
            raise ValueError('Selected process_attach is not at its declared source entry')
        stack, node = (int(entry['general'][n], 16) for n in ('rsp', 'rcx'))
        module_link = int.from_bytes(read(node, 8), 'little')
        modref = module_link - 0xa0
        if module_link < 0xa0 or int.from_bytes(read(modref + 0x30, 8), 'little') != dll_base:
            raise ValueError('Selected process_attach node does not identify the authored DLL')
        caller = int.from_bytes(read(stack, 8), 'little')
        modules, thread = call('modules'), debug.thread_info()
        teb = int(thread['teb'], 16)
        owner(entry_address, 1)
        document.update(entry=entry, return_address=hex(caller), modules_before=modules,
            thread_info=thread, segment_binding={'segment': 'gs', 'teb': hex(teb),
                'gs_base_register_observed': False, 'source': 'Win64 convention plus observed debug-event TEB'},
            selection={'dll_base': hex(dll_base), 'modref': hex(modref), 'node': hex(node),
                       'reserved': entry['general']['rdx']},
            boundary={'start_address': hex(entry_address), 'stop_address': hex(caller),
                      'kind': 'ret', 'expected_stack_delta': 8})
        protected = snapshot(protected_ranges, 0)
        snapshot(extra_ranges, 0)
        for address, width in ((stack, 8), (node, 8), (modref + 0x30, 8)):
            retain(address, read(address, width), 0)
        document['code_versions'].append({'after_step': 0, 'images': images(protected)})
        signal('process_entry', document)
        while len(document['steps']) < max_steps:
            index = len(document['steps'])
            before = call('registers')
            if before['thread'] != entry['thread']:
                raise ValueError('The outer process_attach invocation changed native thread')
            pc = int(before['rip'], 16)
            if pc == module_entry_address:
                if embedded is not None or notification is not None:
                    raise ValueError('Repeated or nested selected MODULE invocation')
                signal('module_entry', {'registers': before, 'modref': hex(modref)})
                remaining = int((deadline - time.monotonic()) * 1000)
                if remaining < 1:
                    raise TimeoutError('Native process_attach deadline exhausted before MODULE')
                # The original body collector emits all live callback snapshots
                # while it executes, and seals its own journal artifact once.
                embedded = capture_loader_capsule(debug, name=name.removesuffix('.json') + '-module.json',
                    dll_base=dll_base, protected_ranges=protected_ranges, extra_ranges=module_extra_ranges,
                    entry_address=module_entry_address, max_steps=max_steps - index, timeout_ms=remaining,
                    subject_symbols=subject_symbols, subject_source_sha256=subject_source_sha256,
                    subject_module=subject_module, loader_module=loader_module, on_boundary=on_boundary)
                inner = embedded['document']
                if inner['status'] != 'complete' or inner['entry'] != before:
                    raise ValueError('The embedded MODULE observation did not complete at its actual entry')
                _merge_module_observation(document, embedded, first, current, seen)
                protected = deepcopy(inner['steps'][-1]['protected_after'])
                signal('module_observed', embedded)
                continue
            raw = read(pc, 15)
            instruction, accesses = _accesses(raw, before, teb)
            instruction_owner = owner(pc, instruction.size)
            admitted = _admit_outer_instruction(instruction, module_entry_address=module_entry_address,
                notification_entry_address=notification_entry_address, module_seen=embedded is not None,
                active_notification=notification)
            footprint = []
            for access in accesses:
                address, width = int(access['address'], 16), access['width']
                prior = read(address, width)
                retain(address, prior, index)
                footprint.append(access | {'before_hex': prior.hex()})
            event, state = debug._step_instruction(deadline)
            if event is None or state['stop_reason']['kind'] != 'step':
                document['interrupted_state'] = state
                raise ValueError('Native process_attach instruction did not complete exactly')
            assert event['registers'] == before
            event['project_address'] = None
            normalize_trace('wine-qemu', [event], version=debug.version['id'])
            assert bytes.fromhex(event['bytes']) == raw[:instruction.size]
            after = call('registers')
            for access in footprint:
                following = read(int(access['address'], 16), access['width'])
                access['after_hex'] = following.hex()
                retain(int(access['address'], 16), following, index + 1)
            following_protected = snapshot(protected_ranges, index + 1)
            document['steps'].append({'event': event, 'after': after,
                'code_read': {'address': hex(pc), 'hex': raw.hex(), 'sha256': hashlib.sha256(raw).hexdigest(),
                              'module': instruction_owner}, 'accesses': footprint,
                'protected_before': protected, 'protected_after': following_protected})
            if images(protected) != images(following_protected) or any(a['kind'] == 'write' and any(
                    int(r['address'], 16) < int(a['address'], 16) + a['width'] and int(a['address'], 16) <
                    int(r['address'], 16) + len(r['hex']) // 2 for r in images(protected)) for a in footprint):
                document['code_versions'].append({'after_step': index + 1,
                    'images': deepcopy(images(following_protected)), 'classified_code_write': True})
            protected = following_protected
            if admitted == 'notification':
                notification = {'first_step': index + 1, 'entry': after,
                    'return_address': hex(pc + instruction.size)}
            elif admitted == 'module':
                if int(after['rip'], 16) != module_entry_address:
                    raise ValueError('Actual selected MODULE CALL destination differs')
            elif instruction.mnemonic == 'ret':
                if notification is not None:
                    if (int(after['rip'], 16) != int(notification['return_address'], 16)
                            or int(after['general']['rsp'], 16) != int(notification['entry']['general']['rsp'], 16) + 8):
                        raise ValueError('Empty notification helper did not complete its original balanced RET')
                    document['notification_spans'].append(notification | {'last_step': index, 'exit': after})
                    notification = None
                else:
                    if (embedded is None or len(document['notification_spans']) != 1 or int(after['rip'], 16) != caller
                            or int(after['general']['rsp'], 16) != stack + 8):
                        raise ValueError('Selected process_attach did not complete its original balanced RET')
                    document.update(status='complete', exit=after, modules_after=call('modules'))
                    signal('process_exit', document)
                    break
        else:
            raise ValueError('Selected process_attach exceeded its finite instruction budget')
    finally:
        document.update(entry_memory=_rows(first), exit_memory=_rows(current),
                        first_seen_steps={hex(a): step for a, step in seen.items()})
        receipt = debug._artifact(name, 'wine-process-attach', json.dumps(document, indent=2).encode(),
            {'status': document['status'], 'steps': len(document['steps'])})
    return {'artifact': receipt, 'document': document, 'module_capsule': embedded}


def derive_attach_success_tail(debug, full, *, name, extra_ranges):
    """Retain a byte-exact suffix view; never execute the attach tail again."""
    source = full['document']
    assert source['status'] == 'complete'
    start = source['module_span']['last_step'] + 1
    steps = deepcopy(source['steps'][start:])
    assert steps
    state = _cells(source['entry_memory'])
    for step in source['steps'][:start]:
        for access in step['accesses']:
            if access['kind'] == 'write':
                address = int(access['address'], 16)
                state.update({address + k: b for k, b in enumerate(bytes.fromhex(access['after_hex']))})
    keep = set()
    for row in source['protected_ranges'] + list(extra_ranges):
        address = int(row['address'], 16)
        keep.update(range(address, address + row['length']))
    for step in steps:
        for access in step['accesses']:
            keep.update(range(int(access['address'], 16), int(access['address'], 16) + access['width']))
    entry_cells = {a: state[a] for a in keep}
    exit_cells = dict(entry_cells)
    for step in steps:
        for access in step['accesses']:
            if access['kind'] == 'write':
                address = int(access['address'], 16)
                exit_cells.update({address + k: b for k, b in enumerate(bytes.fromhex(access['after_hex']))})
    entry, ending = steps[0]['event']['registers'], steps[-1]['after']
    assert int(ending['general']['rsp'], 16) - int(entry['general']['rsp'], 16) == 0x80
    copied = ('run', 'semantics', 'controller_source_sha256', 'subject_source_sha256',
              'loader_module', 'subject_module', 'protected_ranges', 'modules_before',
              'modules_after', 'thread_info', 'segment_binding')
    document = {key: deepcopy(source[key]) for key in copied}
    document.update(format='fdisbull-wine-loader-interval-1', status='complete', role='attach_success_tail',
        entry=deepcopy(entry), exit=deepcopy(ending), steps=steps, summaries=[], extra_ranges=deepcopy(extra_ranges),
        boundary={'start_address': entry['rip'], 'stop_address': ending['rip'], 'kind': 'ret', 'expected_stack_delta': 0x80},
        derived_from={'artifact': full['artifact'], 'first_step': start, 'last_step': len(source['steps']) - 1},
        code_versions=[{'after_step': 0, 'images': [deepcopy(row) for row in steps[0]['protected_before']
                                                if (row.get('role') or '').endswith('code')]}],
        entry_memory=_rows(entry_cells), exit_memory=_rows(exit_cells),
        first_seen_steps={hex(a): max(0, source['first_seen_steps'][hex(a)] - start) for a in keep},
        scope='Exact retained suffix of the single native selected process_attach invocation; no reexecution')
    receipt = debug._artifact(name, 'wine-loader-interval', json.dumps(document, indent=2).encode(),
                              {'status': 'complete', 'steps': len(steps), 'role': 'attach_success_tail'})
    return {'artifact': receipt, 'document': document}


def replay_process_attach(observation, *, module_capsule):
    """Check one native invocation with computed insertion vectors unseeded."""
    from test_wine_loader_dispatch_replay import replay_wine_loader_capsule
    assert observation['format'] == 'fdisbull-wine-process-attach-1'
    assert observation['status'] == module_capsule['status'] == 'complete'
    span, steps = observation['module_span'], observation['steps']
    assert steps[span['first_step']:span['last_step'] + 1] == module_capsule['steps']
    assert steps[span['first_step']]['event']['registers'] == module_capsule['entry']
    assert steps[span['last_step']]['after'] == module_capsule['exit']
    current = observation['entry']
    for step in steps:
        assert step['event']['registers'] == current
        current = step['after']
    assert current == observation['exit']
    boundary = observation['boundary']
    assert boundary == {'start_address': observation['entry']['rip'], 'stop_address': current['rip'],
                        'kind': 'ret', 'expected_stack_delta': 8}
    final = _decode(steps[-1]['event']['bytes'], int(steps[-1]['event']['address'], 16))
    assert final.mnemonic == 'ret'
    assert int(current['general']['rsp'], 16) == int(observation['entry']['general']['rsp'], 16) + 8
    for epoch in observation['code_versions']:
        index = epoch['after_step']
        assert type(index) is int and 0 <= index <= len(steps)
        rows = steps[index - 1]['protected_after'] if index else steps[0]['protected_before']
        assert epoch['images'] == [row for row in rows if (row.get('role') or '').endswith('code')]
    saves = frozenset({'MXCSR', 'FPCW'} | {'XMM' + str(i) for i in range(6, 16)})
    replay = replay_wine_loader_capsule(observation, opaque_save_registers=saves)
    return replay | {'status': 'native_process_attach_replayed',
        'opaque_save_registers': sorted(saves), 'computed_vectors': 'XMM0/XMM1 executed from MOVQ/PUNPCKLQDQ',
        'module_instructions': len(module_capsule['steps']), 'code_epochs': len(observation['code_versions']),
        'scope': 'Concrete selected-node source process_attach through its original RET; '
                 'other DLLs, outer scheduling and universal behavior remain unproved'}


def _decode(raw, address=0x1000):
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    return next(decoder.disasm(bytes.fromhex(raw), address))


@pytest.mark.parametrize('raw,seen,notification,expected', [
    ('e8fb0f0000', False, None, 'module'),
    ('e8fb1f0000', False, None, 'notification'),
    ('90', False, None, None)])
def test_selected_process_attach_admits_only_its_declared_callees(raw, seen, notification, expected):
    assert _admit_outer_instruction(_decode(raw), module_entry_address=0x2000,
        notification_entry_address=0x3000, module_seen=seen, active_notification=notification) == expected


@pytest.mark.parametrize('raw,seen,notification', [
    ('ffd0', False, None), ('e8fb2f0000', False, None),
    ('e8fb0f0000', True, None), ('e8fb1f0000', False, {'entry': {}})])
def test_unmodeled_loader_callees_are_rejected_before_native_execution(raw, seen, notification):
    with pytest.raises(ValueError):
        _admit_outer_instruction(_decode(raw), module_entry_address=0x2000,
            notification_entry_address=0x3000, module_seen=seen, active_notification=notification)


def test_embedded_module_join_preserves_prefix_and_rmw_bytes_and_reindexes_epochs():
    entry, ending = {'rip': '0x2000'}, {'rip': '0x2100'}
    old_code = [{'address': '0x3000', 'hex': '01', 'role': 'dll-code'}]
    new_code = [{'address': '0x3000', 'hex': '02', 'role': 'dll-code'}]
    prefix = {'after': entry, 'protected_after': old_code}
    step = {'event': {'registers': entry}, 'after': ending, 'protected_before': old_code,
        'protected_after': new_code, 'accesses': [
            {'kind': 'read', 'address': '0x100', 'width': 1, 'before_hex': '02', 'after_hex': '03'},
            {'kind': 'write', 'address': '0x100', 'width': 1, 'before_hex': '02', 'after_hex': '03'},
            {'kind': 'read', 'address': '0x200', 'width': 1, 'before_hex': '08', 'after_hex': '08'},
            {'kind': 'write', 'address': '0x3000', 'width': 1, 'before_hex': '01', 'after_hex': '02'}]}
    inner = {'entry': entry, 'exit': ending, 'steps': [step],
        'entry_memory': _rows({0x100: 2, 0x200: 8, 0x3000: 1}),
        'exit_memory': _rows({0x100: 3, 0x200: 8, 0x3000: 2}),
        'first_seen_steps': {'0x100': 0, '0x200': 1, '0x3000': 0},
        'callback_spans': [{'role': 'tls-attach', 'first_step': 0, 'last_step': 0}],
        'code_versions': [{'after_step': 0, 'images': old_code},
                          {'after_step': 1, 'images': new_code, 'classified_code_write': True}]}
    document = {'steps': [prefix], 'callback_spans': [], 'code_versions': []}
    first, current, seen = {0x100: 1, 0x3000: 1}, {0x100: 2, 0x3000: 1}, {0x100: 0, 0x3000: 0}
    _merge_module_observation(document, {'artifact': {'artifact': 'module'}, 'document': inner}, first, current, seen)
    assert first == {0x100: 1, 0x200: 8, 0x3000: 1}
    assert current == {0x100: 3, 0x200: 8, 0x3000: 2} and seen[0x200] == 2
    assert document['steps'][1:] == inner['steps']
    assert document['module_span']['first_step'] == document['module_span']['last_step'] == 1
    assert document['callback_spans'][0]['first_step'] == document['callback_spans'][0]['last_step'] == 1
    assert document['code_versions'][0]['after_step'] == 2
    for bad_entry, bad_exit in ((4, 3), (2, 9)):
        malformed = deepcopy(inner)
        malformed['exit_memory'] = _rows({0x100: bad_exit, 0x200: 8, 0x3000: 2})
        with pytest.raises(ValueError):
            _merge_module_observation({'steps': [prefix], 'callback_spans': [], 'code_versions': []},
                {'artifact': {}, 'document': malformed}, {0x100: 1, 0x3000: 1},
                {0x100: bad_entry, 0x3000: 1}, {0x100: 0, 0x3000: 0})


def test_tail_view_uses_captured_prefix_writes_without_executing_again():
    from types import SimpleNamespace
    original_word, actual_word = (n.to_bytes(8, 'little') for n in (0x1111, 0x2000))
    entry = {'rip': '0x1000', 'general': {'rsp': '0x8000'}}
    added = {'rip': '0x1004', 'general': {'rsp': '0x8078'}}
    ending = {'rip': '0x2000', 'general': {'rsp': '0x8080'}}
    protected = [{'address': '0x3000', 'hex': '90', 'role': 'dll-code'}]
    steps = [
        {'after': entry, 'accesses': [{'kind': 'write', 'address': '0x8078', 'width': 8,
                                     'before_hex': original_word.hex(), 'after_hex': actual_word.hex()}]},
        {'event': {'registers': entry}, 'after': added, 'accesses': [],
         'protected_before': protected, 'protected_after': protected},
        {'event': {'registers': added}, 'after': ending,
         'accesses': [{'kind': 'read', 'address': '0x8078', 'width': 8,
                       'before_hex': actual_word.hex(), 'after_hex': actual_word.hex()}],
         'protected_before': protected, 'protected_after': protected}]
    source = {key: {} for key in ('run', 'semantics', 'controller_source_sha256', 'subject_source_sha256',
        'loader_module', 'subject_module', 'modules_before', 'modules_after', 'thread_info', 'segment_binding')}
    source.update(status='complete', steps=steps, module_span={'last_step': 0},
        protected_ranges=[{'address': '0x3000', 'length': 1, 'role': 'dll-code'}],
        entry_memory=_rows({0x8078 + k: byte for k, byte in enumerate(original_word)} | {0x3000: 0x90}),
        first_seen_steps={hex(a): 0 for a in range(0x8078, 0x8080)} | {'0x3000': 0})
    sealed = []
    def artifact(name, kind, raw, metadata):
        sealed.append((name, kind, json.loads(raw), metadata))
        return {'artifact': 'tail'}
    full = {'artifact': {'artifact': 'full'}, 'document': source}
    untouched = deepcopy(full)
    view = derive_attach_success_tail(SimpleNamespace(_artifact=artifact), full, name='tail.json',
        extra_ranges=[{'address': '0x8078', 'length': 8, 'role': 'caller-word'}])
    cells = _cells(view['document']['entry_memory'])
    assert bytes(cells[a] for a in range(0x8078, 0x8080)) == actual_word
    assert view['document']['steps'] == source['steps'][1:] and full == untouched
    assert len(sealed) == 1 and sealed[0][1] == 'wine-loader-interval'


def test_cpu_replay_computes_insertion_vectors_without_native_value_seeding(monkeypatch):
    import unicorn
    from unicorn import x86_const as reg
    names = ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp',
             'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15')
    entry = {'rip': '0x1000', 'rflags': '0x202', 'general': {n: '0x0' for n in names}}
    entry['general'].update(rax='0x1111222233334444', rbx='0xaaaabbbbccccdddd', rdx='0x5000', rsp='0x8000')
    opcodes = ['66480f6ec0', '66480f6ecb', '660f6cc1', '0f1102', 'c3']
    code = bytes.fromhex(''.join(opcodes)) + b'\x90' * 15
    value = (0x1111222233334444).to_bytes(8, 'little') + (0xaaaabbbbccccdddd).to_bytes(8, 'little')
    protected = [{'address': '0x3000', 'hex': '90', 'role': 'dll-code'}]
    word = {'address': '0x8000', 'hex': (0x2000).to_bytes(8, 'little').hex()}
    current, pc, steps = deepcopy(entry), 0x1000, []
    for index, opcode in enumerate(opcodes):
        after = deepcopy(current)
        after['rip'] = hex(pc + len(bytes.fromhex(opcode)))
        accesses = []
        if index == 3:
            accesses = [{'kind': 'write', 'address': '0x5000', 'width': 16,
                         'before_hex': '00' * 16, 'after_hex': value.hex()}]
        elif index == 4:
            after['rip'], after['general']['rsp'] = '0x2000', '0x8008'
            accesses = [{'kind': 'read', 'address': '0x8000', 'width': 8,
                         'before_hex': word['hex'], 'after_hex': word['hex']}]
        steps.append({'event': {'address': hex(pc), 'bytes': opcode, 'registers': current}, 'after': after,
            'code_read': {'address': hex(pc), 'hex': code[pc - 0x1000:pc - 0x1000 + 15].hex()},
            'accesses': accesses, 'protected_before': protected, 'protected_after': protected})
        current, pc = after, pc + len(bytes.fromhex(opcode))
    observation = {'format': 'fdisbull-wine-process-attach-1', 'status': 'complete', 'summaries': [],
        'entry': entry, 'exit': current, 'steps': steps, 'subject_module': {'base': '0x3000', 'size': 4096},
        'thread_info': {'teb': '0x9000'}, 'module_span': {'first_step': 0, 'last_step': 3},
        'boundary': {'start_address': '0x1000', 'stop_address': '0x2000', 'kind': 'ret', 'expected_stack_delta': 8},
        'entry_memory': protected + [word, {'address': '0x5000', 'hex': '00' * 16}],
        'exit_memory': protected + [word, {'address': '0x5000', 'hex': value.hex()}],
        'code_versions': [{'after_step': 0, 'images': protected}]}
    module = {'status': 'complete', 'entry': entry, 'exit': steps[3]['after'], 'steps': steps[:4]}
    original = unicorn.Uc.reg_write
    def forbid_computed_vector_seed(cpu, identifier, native_value):
        assert identifier not in (reg.UC_X86_REG_XMM0, reg.UC_X86_REG_XMM1)
        return original(cpu, identifier, native_value)
    monkeypatch.setattr(unicorn.Uc, 'reg_write', forbid_computed_vector_seed)
    result = replay_process_attach(observation, module_capsule=module)
    assert result['status'] == 'native_process_attach_replayed' and result['instructions'] == 5
    bad = deepcopy(observation)
    bad['steps'][3]['accesses'][0]['after_hex'] = '00' * 16
    with pytest.raises(AssertionError):
        replay_process_attach(bad, module_capsule=bad | {'entry': entry, 'exit': bad['steps'][3]['after'], 'steps': bad['steps'][:4]})
