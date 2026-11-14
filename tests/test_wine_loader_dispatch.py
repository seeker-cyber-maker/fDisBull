"""Bounded native Wine dispatcher collection, without a loader-wide claim.

The helper single-steps the actual selected thread. Its lazy entry-memory
union is valid only because unsupported implicit/repeated accesses stop before
execution. Protected source bytes are observed after every completed step.
"""
import base64
from copy import deepcopy
import hashlib
import json
import time

import capstone
from capstone import x86_const as X
import pytest
from iced_x86 import Decoder, InstructionInfoFactory, OpAccess

from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace


def _accesses(raw, context, teb):
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    instruction = next(decoder.disasm(raw, int(context['rip'], 16)))
    native = Decoder(64, raw, ip=int(context['rip'], 16)).decode()
    if native.is_invalid or native.len != instruction.size:
        raise ValueError('Native instruction decoders disagree on the dispatcher boundary')
    info = InstructionInfoFactory().info(native)
    reads = {OpAccess.READ, OpAccess.COND_READ, OpAccess.READ_WRITE, OpAccess.READ_COND_WRITE}
    writes = {OpAccess.WRITE, OpAccess.COND_WRITE, OpAccess.READ_WRITE, OpAccess.READ_COND_WRITE}
    if any(p in (0xf2, 0xf3) for p in instruction.prefix) and instruction.mnemonic != 'endbr64':
        raise ValueError('Repeated/string accesses require a separate observed memory contract')
    mnemonic = instruction.mnemonic.split()[-1]
    forbidden = ('movsb', 'movsw', 'movsd', 'movsq', 'stosb', 'stosw', 'stosd', 'stosq',
                 'lodsb', 'lodsw', 'lodsd', 'lodsq', 'cmpsb', 'cmpsw', 'cmpsd', 'cmpsq',
                 'scasb', 'scasw', 'scasd', 'scasq', 'enter', 'leave', 'iret', 'iretq',
                 'xlatb', 'syscall', 'sysenter', 'int', 'int3', 'retf', 'retfq',
                 'xsave', 'xsavec', 'xsaves', 'xrstor', 'xrstors', 'fxsave', 'fxrstor')
    # MOVSD/MOVSQ with an explicit XMM operand is not a string instruction.
    if mnemonic in forbidden and not (mnemonic == 'movsd' and instruction.operands):
        raise ValueError('Unsupported special/implicit loader memory operation: ' + mnemonic)
    general = {n: int(v, 16) for n, v in context['general'].items()}
    result = []
    def add(kind, address, width):
        if not 1 <= width <= 16 or not 0 <= address < 1 << 64 or address + width > 1 << 64:
            raise ValueError('Loader access exceeds scalar/vector observation bounds')
        result.append({'kind': kind, 'address': hex(address), 'width': width})
    if mnemonic not in ('lea', 'nop'):
        for operand_index, operand in enumerate(instruction.operands):
            if operand.type != X.X86_OP_MEM:
                continue
            pointer = operand.mem.disp
            for r, scale in ((operand.mem.base, 1), (operand.mem.index, operand.mem.scale)):
                if not r:
                    continue
                name = instruction.reg_name(r)
                if name == 'rip':
                    value = instruction.address + instruction.size
                else:
                    full = {'eax': 'rax', 'ebx': 'rbx', 'ecx': 'rcx', 'edx': 'rdx',
                            'esi': 'rsi', 'edi': 'rdi', 'ebp': 'rbp', 'esp': 'rsp'}.get(name, name)
                    if full.endswith('d') and full[:-1] in general:
                        full = full[:-1]
                    if full not in general:
                        raise ValueError('Unexposed loader address register: ' + name)
                    value = general[full] & (0xffffffff if name != full else (1 << 64) - 1)
                    if mnemonic == 'pop' and full == 'rsp':
                        raise ValueError('POP memory destination requires post-increment address semantics')
                pointer += value * scale
            pointer &= (1 << (instruction.addr_size * 8)) - 1
            segment = instruction.reg_name(operand.mem.segment) if operand.mem.segment else None
            if segment:
                if segment != 'gs' or teb is None:
                    raise ValueError('Unbound loader memory segment: ' + segment)
                pointer += teb
            # Capstone 5 marks a MOVUPS memory destination as READ. Use iced's
            # instruction-fact access classification instead of trusting that
            # incorrect flag or guessing a store from the sampled byte change.
            access = info.op_access(operand_index)
            if access not in reads | writes:
                raise ValueError('Decoder does not define loader memory operand access')
            if access in reads:
                add('read', pointer, operand.size)
            if access in writes:
                add('write', pointer, operand.size)
    stack = general['rsp']
    if mnemonic in ('call', 'push', 'pushfq'):
        if mnemonic == 'push' and instruction.operands and instruction.operands[0].size == 2:
            raise ValueError('Narrow PUSH is outside the native Win64 dispatcher profile')
        add('write', stack - 8, 8)
    elif mnemonic in ('ret', 'pop', 'popfq'):
        add('read', stack, 8)
    explicit = 0 if mnemonic in ('lea', 'nop') else sum(op.type == X.X86_OP_MEM for op in instruction.operands)
    implicit = int(mnemonic in ('call', 'push', 'pushfq', 'ret', 'pop', 'popfq'))
    actual = [m for m in info.used_memory() if m.access != OpAccess.NO_MEM_ACCESS]
    if len(actual) != explicit + implicit:
        raise ValueError('An unclassified implicit memory operand remains in the dispatcher instruction')
    return instruction, result


def _rows(cells):
    result = []
    for address, value in sorted(cells.items()):
        if result and int(result[-1]['address'], 16) + len(result[-1]['hex']) // 2 == address:
            result[-1]['hex'] += f'{value:02x}'
        else:
            result.append({'address': hex(address), 'hex': f'{value:02x}'})
    return result


def capture_loader_capsule(debug, *, name, dll_base, protected_ranges, extra_ranges=(),
                           entry_address=None, max_steps=2048, timeout_ms=180000, modref_offset=0x30,
                           subject_symbols=None, subject_source_sha256=None,
                           subject_module=None, loader_module=None, on_boundary=None):
    """Capture one actual MODULE_InitDLL invocation through its original RET.

    Returns ``{'artifact': receipt, 'document': document}``. On failure a partial
    artifact is still retained before the exception reaches the sole controller.
    Range rows carry ``address``, ``length`` and an optional ``role``. Only the
    protected ranges are reread in full after every step; other bytes enter the
    initial-memory union at their first observed access before any store.
    """
    if type(max_steps) is not int or not 1 <= max_steps <= 10000:
        raise ValueError('max_steps must be 1..10000')
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('timeout_ms must be 1..600000')
    if on_boundary is not None and not callable(on_boundary):
        raise ValueError('on_boundary must be callable')
    deadline = time.monotonic() + timeout_ms / 1000
    document = {'format': 'fdisbull-wine-loader-dispatch-capsule-1', 'status': 'partial',
        'run': debug.run_id, 'semantics': PE_TRACE_SEMANTICS, 'steps': [], 'code_versions': [],
        'summaries': [], 'callback_spans': [], 'callbacks': [],
        'scope': 'Actual bounded selected-thread Wine dispatcher invocation; no universal loader, '
                 'page-guard coverage, hidden-memory, scheduling or process-lifetime claim'}
    first_seen, current, seen_at = {}, {}, {}
    active_callback = None
    def call(method, params=None):
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            raise TimeoutError('Native loader capsule total deadline exhausted')
        return debug.call(method, params, timeout_ms=remaining + 1000)
    def read(address, length):
        raw = base64.b64decode(call('read', {'address': address, 'length': length})['data_base64'], validate=True)
        if len(raw) != length:
            raise ValueError('Incomplete dispatcher memory read')
        return raw
    def retain(address, raw, step):
        for k, byte in enumerate(raw):
            cell = address + k
            if cell not in first_seen:
                first_seen[cell], seen_at[cell] = byte, step
            current[cell] = byte
    def snapshot(ranges, step):
        rows = []
        for item in ranges:
            address = int(item['address'], 16) if isinstance(item['address'], str) else item['address']
            raw = read(address, item['length'])
            retain(address, raw, step)
            rows.append({'address': hex(address), 'hex': raw.hex(), 'role': item.get('role')})
        return rows
    def owner(address, length):
        matches = [m for m in modules['modules'] if int(m['base'], 16) <= address
                   and address + length <= int(m['base'], 16) + m['size']]
        if len(matches) != 1:
            raise ValueError('Dispatcher instruction has absent or ambiguous loaded-module identity')
        return deepcopy(matches[0])
    try:
        entry = call('registers')
        start = int(entry['rip'], 16)
        if entry_address is not None and start != entry_address:
            raise ValueError('Native dispatcher is not stopped at its declared entry')
        reason = int(entry['general']['rdx'], 16) & 0xffffffff
        if reason not in (0, 1):
            raise ValueError('The dispatcher capsule admits process attach/detach reasons only')
        modref, stack = (int(entry['general'][n], 16) for n in ('rcx', 'rsp'))
        assert int.from_bytes(read(modref + modref_offset, 8), 'little') == dll_base
        caller = int.from_bytes(read(stack, 8), 'little')
        modules = call('modules')
        thread = debug.thread_info()
        teb = int(thread['teb'], 16)
        document.update(entry=entry, return_address=hex(caller), modules_before=modules,
            thread_info=thread, segment_binding={'segment': 'gs', 'teb': hex(teb),
                'gs_base_register_observed': False, 'source': 'Win64 TEB convention plus observed native debug-event TEB'},
            selection={'dll_base': hex(dll_base), 'modref': hex(modref), 'modref_base_offset': hex(modref_offset),
                       'reason_low32': reason}, protected_ranges=deepcopy(protected_ranges),
            extra_ranges=deepcopy(list(extra_ranges)))
        document['controller_source_sha256'] = debug.project.meta['source_sha256']
        document['subject_source_sha256'] = subject_source_sha256
        observed_loader = owner(start, 1)
        if loader_module is not None and any(loader_module.get(k) != observed_loader.get(k)
                for k in ('name', 'base', 'size', 'generation')):
            raise ValueError('Declared Wine dispatcher owner differs from its native loaded module')
        document['loader_module'] = deepcopy(loader_module or observed_loader)
        document['subject_module'] = deepcopy(subject_module)
        ds = {n: int(v, 16) if isinstance(v, str) else v for n, v in (subject_symbols or {}).items()}
        protected = snapshot(protected_ranges, 0)
        snapshot(extra_ranges, 0)
        retain(stack, read(stack, 8), 0)
        retain(modref + modref_offset, read(modref + modref_offset, 8), 0)
        document['code_versions'].append({'after_step': 0, 'images': [r for r in protected if (r.get('role') or '').endswith('code')]})
        if on_boundary is not None:
            on_boundary('capsule_entry', document)
        for index in range(max_steps):
            before = call('registers')
            if before['thread'] != entry['thread']:
                raise ValueError('Dispatcher capsule changed its selected native thread')
            pc = int(before['rip'], 16)
            if active_callback is None and ds and pc in (ds['dll_tls_callback'], ds['dll_entry'], ds.get('dll_report')):
                callback_reason = int(before['general']['rdx'], 16) & 0xffffffff
                role = ('report' if pc == ds.get('dll_report') else
                    ('tls-' if pc == ds['dll_tls_callback'] else 'dll-') +
                    ('attach' if callback_reason == 1 else 'detach' if callback_reason == 0 else 'thread'))
                callback_stack = int(before['general']['rsp'], 16)
                callback_word = read(callback_stack, 8)
                retain(callback_stack, callback_word, index)
                active_callback = {'format': 'fdisbull-native-dll-callback-1', 'status': 'partial',
                    'run': debug.run_id, 'controller_source_sha256': document['controller_source_sha256'],
                    'subject_source_sha256': subject_source_sha256,
                    'subject_module': deepcopy(subject_module or owner(pc, 1)), 'source_role': role,
                    'entry': before, 'return_address': hex(int.from_bytes(callback_word, 'little')),
                    'steps': [], 'semantics': PE_TRACE_SEMANTICS, 'capsule_first_step': index}
                if on_boundary is not None:
                    on_boundary('callback_entry', active_callback)
            callback_pre = None
            if active_callback is not None:
                callback_stack = int(active_callback['entry']['general']['rsp'], 16)
                callback_pre = [
                    {'address': hex(ds['dll_code_start']), 'hex': read(ds['dll_code_start'], ds['dll_code_end']-ds['dll_code_start']).hex()},
                    {'address': hex(ds['dll_data_start']), 'hex': read(ds['dll_data_start'], 64).hex()},
                    {'address': hex(callback_stack), 'hex': read(callback_stack, 8).hex()}]
            raw = read(pc, 15)
            instruction, accesses = _accesses(raw, before, teb)
            code_read = {'address': hex(pc), 'hex': raw.hex(), 'sha256': hashlib.sha256(raw).hexdigest(),
                         'module': owner(pc, instruction.size)}
            access_rows = []
            for access in accesses:
                address, width = int(access['address'], 16), access['width']
                prior = read(address, width)
                retain(address, prior, index)
                access_rows.append(access | {'before_hex': prior.hex()})
            event, state = debug._step_instruction(deadline)
            if event is None or state['stop_reason']['kind'] != 'step':
                document['interrupted_state'] = state
                raise ValueError('Native dispatcher instruction did not complete exactly')
            assert event['registers'] == before
            event['project_address'] = debug.project_address(pc)
            normalize_trace('wine-qemu', [event], version=debug.version['id'], delta=debug.delta)
            assert bytes.fromhex(event['bytes']) == raw[:instruction.size]
            after = call('registers')
            for access in access_rows:
                address, width = int(access['address'], 16), access['width']
                following = read(address, width)
                access['after_hex'] = following.hex()
                retain(address, following, index + 1)
            following_protected = snapshot(protected_ranges, index + 1)
            step = {'event': event, 'after': after, 'code_read': code_read, 'accesses': access_rows,
                    'protected_before': protected, 'protected_after': following_protected}
            document['steps'].append(step)
            if active_callback is not None:
                callback_post = [
                    {'address': hex(ds['dll_code_start']), 'hex': read(ds['dll_code_start'], ds['dll_code_end']-ds['dll_code_start']).hex()},
                    {'address': hex(ds['dll_data_start']), 'hex': read(ds['dll_data_start'], 64).hex()},
                    {'address': hex(callback_stack), 'hex': read(callback_stack, 8).hex()}]
                callback_event = deepcopy(event)
                callback_event['project_address'] = None
                callback_event['identity']['project_address'] = None
                active_callback['steps'].append({'event': callback_event, 'after': after,
                    'memory_before': callback_pre, 'memory_after': callback_post})
                if int(after['rip'], 16) == int(active_callback['return_address'], 16):
                    if instruction.mnemonic != 'ret' or int(after['general']['rsp'], 16) != callback_stack + 8:
                        raise ValueError('An authored callback did not complete its original balanced RET')
                    active_callback.update(status='complete', exit=after)
                    if on_boundary is not None:
                        on_boundary('callback_return', active_callback)
                    document['callback_spans'].append({'role': active_callback['source_role'],
                        'first_step': active_callback['capsule_first_step'], 'last_step': index})
                    document['callbacks'].append(active_callback)
                    active_callback = None
            code_before = [r for r in protected if (r.get('role') or '').endswith('code')]
            code_after = [r for r in following_protected if (r.get('role') or '').endswith('code')]
            code_write = any(a['kind'] == 'write' and any(int(r['address'], 16) < int(a['address'], 16) + a['width']
                and int(a['address'], 16) < int(r['address'], 16) + len(r['hex']) // 2 for r in code_before) for a in access_rows)
            if code_write or code_before != code_after:
                document['code_versions'].append({'after_step': index + 1, 'images': deepcopy(code_after),
                    'classified_code_write': code_write})
            protected = following_protected
            if int(after['rip'], 16) == caller:
                if instruction.mnemonic != 'ret' or int(after['general']['rsp'], 16) != stack + 8:
                    raise ValueError('Dispatcher caller boundary was reached without its original balanced RET')
                document.update(status='complete', exit=after, modules_after=call('modules'))
                if on_boundary is not None:
                    on_boundary('capsule_exit', document)
                break
        else:
            raise ValueError('Native dispatcher exceeded its finite instruction budget')
    finally:
        if active_callback is not None:
            document['callbacks'].append(active_callback)
        document.update(entry_memory=_rows(first_seen), exit_memory=_rows(current),
            first_seen_steps={hex(a): index for a, index in seen_at.items()})
        receipt = debug._artifact(name, 'wine-loader-dispatch-capsule', json.dumps(document, indent=2).encode(),
                                  {'status': document['status'], 'steps': len(document['steps'])})
    return {'artifact': receipt, 'document': document}


def _context():
    return {'rip': '0x1000', 'rflags': '0x202', 'thread': 17,
            'general': {'rax': '0x3000', 'rsp': '0x8008', 'rcx': '0x2000'}}


@pytest.mark.parametrize('raw,expected', [
    ('488b014889', [('read', '0x2000', 8)]),
    ('e801000000', [('write', '0x8000', 8)]),
    ('ffd0', [('write', '0x8000', 8)]),
    ('ff10', [('read', '0x3000', 8), ('write', '0x8000', 8)]),
    ('c3', [('read', '0x8008', 8)]),
    ('53', [('write', '0x8000', 8)]),
    ('5b', [('read', '0x8008', 8)]),
    ('0f11442410', [('write', '0x8018', 16)]),
    ('65488b042530000000', [('read', '0x9030', 8)]),
    ('488d01', []),
])
def test_native_dispatcher_footprints_include_actual_stack_and_vector_widths(raw, expected):
    _, accesses = _accesses(bytes.fromhex(raw), _context(), 0x9000)
    assert [(r['kind'], r['address'], r['width']) for r in accesses] == expected


@pytest.mark.parametrize('raw', ['f3aa', 'c8f00000', 'c9', '0f05', 'cc'])
def test_unknown_repeated_or_special_implicit_memory_is_rejected_before_execution(raw):
    with pytest.raises(ValueError):
        _accesses(bytes.fromhex(raw), _context(), 0x9000)
