"""Observed PE64 import boundaries and opt-in bounded implementation evidence.

The export resolver reads the stopped target's actual mapped PE images. Names
and hashes establish observation identity, not publisher authenticity or proof
of an API's complete effects on Windows/Wine state.
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
import time

from iced_x86 import Decoder

from .external_files import _file_name


_APIS = {'SetLastError', 'GetLastError', 'ExitProcess'}
_NONVOLATILE = ('rbx', 'rbp', 'rdi', 'rsi', 'r12', 'r13', 'r14', 'r15')


def _address(value):
    if not isinstance(value, str) or not value.startswith('0x'):
        raise ValueError('Expected an exact hexadecimal process address')
    result = int(value, 16)
    if not 0 <= result < 1 << 64:
        raise ValueError('Process address exceeds PE64 width')
    return result


def resolve_loaded_export(module_state, module, symbol, read):
    """Resolve one bounded AMD64 export/forwarder from actually loaded images.

    ``read(address, length)`` returns exact bytes from the stopped process.
    Every underlying read is retained for offline inspection and hash checking.
    API-set inference and unresolved/ambiguous module names fail closed.
    """
    if (not isinstance(module_state, dict) or not isinstance(module_state.get('modules'), list)
            or len(module_state['modules']) > 256
            or type(module_state.get('module_revision')) is not int
            or not isinstance(module, str) or not isinstance(symbol, str)
            or not 1 <= len(symbol) <= 256):
        raise ValueError('Invalid loaded-module export request')
    modules, reads, chain, visiting = [], [], [], set()
    total = 0
    for row in module_state['modules']:
        if (not isinstance(row, dict) or not isinstance(row.get('name'), str)
                or type(row.get('size')) is not int or not 0 < row['size'] <= 1 << 30
                or type(row.get('generation')) is not int or row['generation'] < 1
                or row.get('bits') not in (32, 64)):
            raise ValueError('Invalid observed loaded-module identity')
        base = _address(row['base'])
        if base + row['size'] > 1 << 64:
            raise ValueError('Loaded module exceeds PE64 width')
        modules.append(dict(row, _base=base))

    def named(name):
        normalized = name.casefold()
        if not normalized.endswith('.dll'):
            normalized += '.dll'
        found = [m for m in modules if m['name'].casefold() == normalized and m['bits'] == 64]
        if len(found) != 1:
            raise ValueError('Unresolved or ambiguous loaded AMD64 module: ' + name)
        return found[0]

    def span(m, rva, length):
        if (type(rva) is not int or type(length) is not int or rva < 0 or length < 1
                or rva > m['size'] or length > m['size'] - rva):
            raise ValueError('Export structure escapes its observed module')

    def fetch(m, rva, length):
        nonlocal total
        span(m, rva, length)
        total += length
        if total > 524288 or len(reads) >= 2048:
            raise ValueError('Loaded-export observation budget exhausted')
        raw = read(m['_base'] + rva, length)
        if not isinstance(raw, bytes) or len(raw) != length:
            raise ValueError('Incomplete loaded-module memory observation')
        reads.append({'address': hex(m['_base'] + rva), 'hex': raw.hex(),
                      'sha256': hashlib.sha256(raw).hexdigest()})
        return raw

    def string(m, rva, *, end=None):
        result = bytearray()
        limit = min(m['size'], m['size'] if end is None else end)
        for offset in range(0, 256, 32):
            length = min(32, limit - rva - offset)
            if length <= 0:
                break
            raw = fetch(m, rva + offset, length)
            stop = raw.find(b'\0')
            result.extend(raw if stop < 0 else raw[:stop])
            if stop >= 0:
                if not result or any(byte < 33 or byte > 126 for byte in result):
                    raise ValueError('Invalid bounded export string')
                return result.decode('ascii')
        raise ValueError('Unterminated bounded export string')

    current_module, current_symbol = module, symbol
    for _ in range(8):
        m = named(current_module)
        key = (m['_base'], current_symbol)
        if key in visiting:
            raise ValueError('Loaded-export forwarder cycle')
        visiting.add(key)
        dos = fetch(m, 0, 64)
        pe = struct.unpack_from('<I', dos, 60)[0]
        if dos[:2] != b'MZ' or not 64 <= pe <= 1048576:
            raise ValueError('Invalid loaded PE DOS header')
        coff = fetch(m, pe, 24)
        machine, sections = struct.unpack_from('<HH', coff, 4)
        optional_size = struct.unpack_from('<H', coff, 20)[0]
        if coff[:4] != b'PE\0\0' or machine != 0x8664 or not 1 <= sections <= 96 or optional_size < 120:
            raise ValueError('Loaded export requires an AMD64 PE32+ image')
        optional = fetch(m, pe + 24, 120)
        if (struct.unpack_from('<H', optional)[0] != 0x20b
                or struct.unpack_from('<I', optional, 56)[0] != m['size']
                or struct.unpack_from('<I', optional, 108)[0] < 1):
            raise ValueError('Loaded PE optional header contradicts module identity')
        export_rva, export_size = struct.unpack_from('<II', optional, 112)
        if export_size < 40:
            raise ValueError('Loaded module has no bounded export directory')
        span(m, export_rva, export_size)
        directory = fetch(m, export_rva, 40)
        ordinal_base, functions, names, function_table, name_table, ordinal_table = struct.unpack_from('<IIIIII', directory, 16)
        if not 1 <= functions <= 65536 or not 0 <= names <= 65536:
            raise ValueError('Loaded export table exceeds its budget')
        span(m, function_table, functions * 4)
        if names:
            span(m, name_table, names * 4)
            span(m, ordinal_table, names * 2)
        ordinal = None
        if current_symbol.startswith('#'):
            if not current_symbol[1:].isdigit():
                raise ValueError('Invalid forwarded ordinal')
            ordinal = int(current_symbol[1:]) - ordinal_base
        else:
            low, high = 0, names
            while low < high:
                middle = (low + high) // 2
                name_rva = struct.unpack('<I', fetch(m, name_table + middle * 4, 4))[0]
                found = string(m, name_rva)
                if found == current_symbol:
                    ordinal = struct.unpack('<H', fetch(m, ordinal_table + middle * 2, 2))[0]
                    break
                if found < current_symbol:
                    low = middle + 1
                else:
                    high = middle
        if ordinal is None or not 0 <= ordinal < functions:
            raise ValueError('Named export is absent from its loaded module')
        rva = struct.unpack('<I', fetch(m, function_table + ordinal * 4, 4))[0]
        if not rva:
            raise ValueError('Named export is an empty slot')
        item = {'module': m['name'], 'base': m['base'], 'size': m['size'],
                'generation': m['generation'], 'symbol': current_symbol, 'rva': hex(rva)}
        chain.append(item)
        if export_rva <= rva < export_rva + export_size:
            forward = string(m, rva, end=export_rva + export_size)
            if '.' not in forward:
                raise ValueError('Invalid export forwarder')
            current_module, current_symbol = forward.rsplit('.', 1)
            item['forwarder'] = forward
            continue
        section_table = fetch(m, pe + 24 + optional_size, sections * 40)
        executable = False
        for offset in range(0, len(section_table), 40):
            virtual_size, virtual_address, raw_size = struct.unpack_from('<III', section_table, offset + 8)
            characteristics = struct.unpack_from('<I', section_table, offset + 36)[0]
            size = max(virtual_size, raw_size)
            if (characteristics & 0x20000000 and virtual_address <= rva < virtual_address + size
                    and virtual_address + size <= m['size']):
                executable = True
        if not executable:
            raise ValueError('Resolved export is not in an observed executable PE section')
        target = m['_base'] + rva
        owners = [row for row in modules if row['_base'] <= target < row['_base'] + row['size']]
        if len(owners) != 1:
            raise ValueError('Resolved export belongs to ambiguous module spans')
        fetch(m, rva, min(16, m['size'] - rva))
        return {'target': hex(target), 'module_revision': module_state['module_revision'],
                'chain': chain, 'reads': reads,
                'scope': 'Observed loaded PE64 export identity; implementation effects remain an explicit API contract'}
    raise ValueError('Loaded-export forwarder depth exceeds eight')


def _ranges(rows, maximum):
    if rows is None:
        return []
    if not isinstance(rows, list) or len(rows) > 32:
        raise ValueError('Import-call observations require bounded memory ranges')
    result, cells = [], set()
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'address', 'length'}
                or type(row['length']) is not int or not 1 <= row['length'] <= maximum):
            raise ValueError('Import-call memory ranges require address and bounded length')
        address = _address(row['address'])
        span = set(range(address, address + row['length']))
        if address + row['length'] > 1 << 64 or cells & span:
            raise ValueError('Import-call memory ranges overlap or wrap')
        cells |= span
        result.append({'address': hex(address), 'length': row['length']})
    if len(cells) > maximum:
        raise ValueError('Import-call observation byte budget exceeded')
    return result


def _trace_implementation(session, document, *, deadline, call, read, registers):
    """Collect only the closed TLS thunk/leaf profile, refusing before unknown code."""
    import capstone
    from capstone import x86_const as X
    from .debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
    implementation = {'format': 'fdisbull-wine-api-implementation-1', 'status': 'partial',
        'bits': 64, 'semantics': PE_TRACE_SEMANTICS, 'events': [], 'code_reads': [],
        'accesses': [], 'memory': {'entry': [], 'exit': []}}
    # Install immediately: every later failure retains reads and completed steps.
    document['implementation'] = implementation
    thread = call('thread-info')
    implementation['thread_info'] = thread
    entry = document['contexts']['entry']
    if (thread.get('bits') != 64 or thread.get('thread') != entry['thread']
            or thread.get('gs_base_register_observed') is not False
            or thread.get('teb_source') not in {'CREATE_PROCESS_DEBUG_EVENT.lpThreadLocalBase',
                                              'CREATE_THREAD_DEBUG_EVENT.lpThreadLocalBase'}):
        raise ValueError('Native implementation tracing requires an observed selected-thread TEB')
    teb, stack = _address(thread['teb']), _address(entry['general']['rsp'])
    if teb + 0x70 > 1 << 64 or stack + 8 > 1 << 64:
        raise ValueError('Native implementation TEB/frame address wraps')
    implementation['segment_binding'] = {'segment': 'gs', 'offset': '0x30',
        'teb': hex(teb), 'gs_base_register_observed': False}
    initial = {}
    def rows(cells):
        result = []
        for address, byte in sorted(cells.items()):
            if result and int(result[-1]['address'], 16) + len(result[-1]['hex']) // 2 == address:
                result[-1]['hex'] += f'{byte:02x}'
            else:
                result.append({'address': hex(address), 'hex': f'{byte:02x}'})
        return result
    def remember(address, raw):
        for k, byte in enumerate(raw):
            initial.setdefault(address + k, byte)
        implementation['memory']['entry'] = rows(initial)
    for address, length in ((teb + 0x30, 8), (teb + 0x68, 4), (stack, 8)):
        remember(address, read(address, length))
    if int.from_bytes(bytes(initial[teb + 0x30 + k] for k in range(8)), 'little') != teb:
        raise ValueError('Observed selected TEB self word does not equal its debug-event identity')
    caller = _address(document['import']['return_address'])
    if int.from_bytes(bytes(initial[stack + k] for k in range(8)), 'little') != caller:
        raise ValueError('Observed API entry return word differs from the actual caller')
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    current = entry
    for index in range(32):
        if time.monotonic() >= deadline:
            raise ValueError('Native API implementation trace deadline exhausted')
        address = _address(current['rip'])
        if address == caller:
            break
        if session.project_address(address) is not None:
            raise ValueError('An API implementation entered authored main-module code before RET')
        owners = [m for m in document['modules_before']['modules']
                  if _address(m['base']) <= address < _address(m['base']) + m['size']]
        if len(owners) != 1 or owners[0].get('bits') != 64 or not owners[0]['name'].casefold().endswith('.dll'):
            raise ValueError('API instruction lacks one observed foreign AMD64 DLL owner')
        owner = {key: owners[0][key] for key in ('name', 'base', 'size', 'generation')}
        raw = read(address, min(15, _address(owner['base']) + owner['size'] - address))
        implementation['code_reads'].append({'event_index': index, 'address': hex(address), 'hex': raw.hex(),
            'sha256': hashlib.sha256(raw).hexdigest(), 'module': owner})
        decoded = list(decoder.disasm(raw, address, count=1))
        if not decoded:
            raise ValueError('Native API instruction could not be decoded before stepping')
        ins = decoded[0]
        executed = raw[:ins.size]
        access = None
        if executed in (b'\xf3\x0f\x1e\xfa', b'\x90', b'\x66\x90', bytes.fromhex('488da42400000000')):
            pass
        elif executed == bytes.fromhex('65488b042530000000'):
            access = ('read', teb + 0x30, 8)
        elif executed[:2] == b'\xff\x25' and len(executed) == 6:
            access = ('read', address + 6 + int.from_bytes(executed[2:], 'little', signed=True), 8)
        elif ((executed[0] == 0xe9 and len(executed) == 5) or
              (executed[0] == 0xeb and len(executed) == 2)):
            pass
        elif ins.mnemonic == 'mov' and len(ins.operands) == 2:
            dest, src = ins.operands
            if (dest.type == X.X86_OP_REG and dest.size == 4 and src.type == X.X86_OP_MEM
                    and ins.reg_name(src.mem.base) == 'rax' and not src.mem.index
                    and not src.mem.segment and src.mem.disp == 0x68):
                access = ('read', _address(current['general']['rax']) + 0x68, 4)
            elif (dest.type == X.X86_OP_MEM and dest.size == 4 and src.type == X.X86_OP_REG and src.size == 4
                    and ins.reg_name(dest.mem.base) == 'rax' and not dest.mem.index
                    and not dest.mem.segment and dest.mem.disp == 0x68):
                access = ('write', _address(current['general']['rax']) + 0x68, 4)
            else:
                raise ValueError('Unknown API instruction refused before native execution')
            if access[1] != teb + 0x68:
                raise ValueError('Native API DWORD access does not address the observed TEB slot')
        elif executed == b'\xc3':
            access = ('read', _address(current['general']['rsp']), 8)
            if access[1] != stack:
                raise ValueError('Native API RET does not use its original caller frame')
        else:
            raise ValueError('Unknown API instruction refused before native execution')
        record = None
        if access is not None:
            kind, pointer, width = access
            if not 0 <= pointer <= (1 << 64) - width:
                raise ValueError('Native API operand address wraps')
            prior = read(pointer, width)
            remember(pointer, prior)
            record = {'event_index': index, 'kind': kind, 'address': hex(pointer), 'width': width,
                      'before_hex': prior.hex(), 'after_hex': None}
            implementation['accesses'].append(record)
        event, state = session._step_instruction(deadline)
        if (event is None or state.get('stop_reason', {}).get('kind') != 'step'
                or event.get('active_layers') or event.get('registers') != current
                or event.get('execution_bytes', event.get('bytes')) != executed.hex()
                or event.get('ram_bytes', event.get('bytes')) != executed.hex()):
            raise ValueError('Native API instruction did not complete as its observed exact byte sequence')
        event['project_address'] = None
        normalize_trace('wine-qemu', [event], version=session.version['id'])
        implementation['events'].append(event)
        if record is not None:
            record['after_hex'] = read(access[1], access[2]).hex()
        current = registers()
        if current['thread'] != entry['thread']:
            raise ValueError('Native API instruction trace changed its selected thread')
        if executed == bytes.fromhex('65488b042530000000') and _address(current['general']['rax']) != teb:
            raise ValueError('Actual GS self load disagrees with the explicit observed-thread TEB binding')
    if _address(current['rip']) != caller:
        raise ValueError('Native API implementation did not return within 32 instructions')
    final_raw = read(caller, 15)
    ins = Decoder(64, final_raw, ip=caller).decode()
    if ins.is_invalid:
        raise ValueError('Native API caller boundary has no valid observed instruction')
    final = {'address': hex(caller), 'project_address': session.project_address(caller),
        'bytes': final_raw[:ins.len].hex(), 'execution_bytes': final_raw[:ins.len].hex(),
        'ram_bytes': final_raw[:ins.len].hex(), 'registers': current}
    normalize_trace('wine-qemu', [final], version=session.version['id'])
    final['observation'].update(instruction_completed=False,
        evidence='Actual stopped caller boundary after native imported RET; not executed')
    implementation['events'].append(final)
    ending = {}
    for row in rows(initial):
        address, length = _address(row['address']), len(row['hex']) // 2
        ending.update({address + k: b for k, b in enumerate(read(address, length))})
    implementation['memory']['exit'] = rows(ending)
    implementation['status'] = 'complete'
    return current


def observe_import_call(session, *, name='import-call.json', memory_ranges=None,
                        code_ranges=None, timeout_ms=60000, trace_implementation=False):
    """Execute one current FF15 import call and preserve its real boundaries.

    Returning calls run opaquely to their owned caller breakpoint. ExitProcess
    is terminal and must produce the actual process-exit debug event. No return
    register, TLS formula or unknown OS-memory effect is invented here.
    ``trace_implementation`` instead single-steps the closed Set/GetLastError
    thunk/TLS/RET profile and validates its exact machine-code effects.
    """
    _file_name(name)
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('Import-call timeout must be 1..600000 ms')
    if type(trace_implementation) is not bool:
        raise ValueError('trace_implementation must be boolean')
    ram, code = _ranges(memory_ranges, 256), _ranges(code_ranges, 512)
    if getattr(session, 'bits', 64) != 64 or session.closed:
        raise ValueError('Import-call observation requires a live PE64 session')
    deadline = time.monotonic() + timeout_ms / 1000
    document = {'format': 'fdisbull-wine-import-call-1', 'status': 'partial',
        'identity': {'run': session.run_id, 'source_version': session.version['id'],
            'source_sha256': session.project.meta['source_sha256'],
            'version_sha256': session.version['sha256']},
        'memory': {}, 'code': {}, 'contexts': {},
        'scope': 'Observed imported-call entry/return or actual process exit; DLL instructions, '
                 'TLS/OS effects and unobserved memory remain outside this observation'}
    if trace_implementation:
        document['scope'] = ('Observed imported-call boundaries and complete bounded native DLL thunk/TLS/RET '
            'steps; exact effects are checked separately against those bytes under explicit GS/TEB binding. '
            'Other implementations, library initialization, OS-private effects and timing remain unproved')
    breakpoint = None

    def remaining():
        result = int((deadline - time.monotonic()) * 1000)
        if result < 1:
            raise ValueError('Import-call total observation deadline exhausted')
        return result

    def call(method, params=None):
        return session.call(method, params, timeout_ms=remaining())

    def read(address, length):
        raw = base64.b64decode(call('read', {'address': address, 'length': length})['data_base64'], validate=True)
        if len(raw) != length:
            raise ValueError('Incomplete native import-call memory observation')
        return raw

    def registers():
        # Keep native context dictionaries byte-for-byte compatible with trace
        # events. Public registers() adds host presentation fields which are
        # not part of the native instruction boundary.
        from .wine_arch import validate_context
        result = call('registers')
        validate_context(result, 64)
        return result

    def snapshot(label):
        for field, ranges in (('memory', ram), ('code', code)):
            document[field][label] = [{'address': row['address'],
                'hex': read(_address(row['address']), row['length']).hex()} for row in ranges]

    try:
        if call('status').get('state') != 'stopped':
            raise ValueError('Import-call observation requires a stopped thread')
        if getattr(session, '_layers', []) or getattr(session, '_pending_exec', None) is not None:
            raise ValueError('Import-call observations exclude active execution/data layers')
        before = registers()
        document['contexts']['before'] = before
        site = _address(before['rip'])
        if session.project_address(site) is None:
            raise ValueError('Import CALL must belong to the observed main PE image')
        raw = read(site, 6)
        if raw[:2] != b'\xff\x15':
            raise ValueError('Import-call observation requires an exact RIP-relative FF15 CALL')
        slot = site + 6 + struct.unpack_from('<i', raw, 2)[0]
        if not 0 <= slot <= (1 << 64) - 8:
            raise ValueError('Import-call IAT address wraps')
        imports = session.project._document(session.version['id']).get('imports', [])
        matches = [row for row in imports if row.get('address') == slot - session.delta and row.get('kind') == 'iat']
        if len(matches) != 1 or matches[0].get('name') not in _APIS or matches[0]['module'].casefold() != 'kernel32.dll':
            raise ValueError('CALL does not identify one supported source import')
        imported = matches[0]
        if trace_implementation and imported['name'] == 'ExitProcess':
            raise ValueError('Bounded implementation tracing is available only for SetLastError/GetLastError')
        state = call('modules')
        document['modules_before'] = state
        resolution = resolve_loaded_export(state, imported['module'], imported['name'], read)
        iat = read(slot, 8)
        target = int.from_bytes(iat, 'little')
        document['import'] = {'module': imported['module'], 'name': imported['name'],
            'iat_address': hex(slot - session.delta), 'runtime_iat_address': hex(slot),
            'iat_hex': iat.hex(), 'target': hex(target), 'callsite': hex(site),
            'return_address': hex(site + 6), 'instruction_hex': raw.hex()}
        document['resolution'] = resolution
        if target != _address(resolution['target']):
            raise ValueError('Observed IAT target differs from its loaded named export')
        stack = _address(before['general']['rsp'])
        if stack & 15:
            raise ValueError('External Win64 CALL requires a 16-byte aligned caller stack')
        document['shadow_store'] = {'address': hex(stack), 'before_hex': read(stack, 32).hex()}
        snapshot('before')
        trace = session.trace(name[:220] + '.instruction.json', count=1, timeout_ms=remaining())
        document['trace'] = trace
        from .runtime_patch_analysis import _artifact
        _, traced = _artifact(session.project, trace['artifact'], 'trace')
        events = traced.get('events', [])
        if (traced.get('complete') is not True or len(events) != 1
                or traced.get('run') != session.run_id or traced.get('version') != session.version['id']
                or traced.get('mapping', {}).get('source_sha256') != session.project.meta['source_sha256']
                or traced.get('mapping', {}).get('version_sha256') != session.version['sha256']
                or events[0].get('execution_bytes', events[0].get('bytes')) != raw.hex()
                or events[0].get('ram_bytes', events[0].get('bytes')) != raw.hex()
                or events[0]['observation'].get('instruction_completed') is not True
                or events[0].get('active_layers')
                or events[0]['registers']['general'] != before['general']
                or events[0]['registers']['rflags'] != before['rflags']
                or events[0]['registers']['thread'] != before['thread']
                or events[0]['address'] != before['rip']):
            raise ValueError('Import CALL lacks its exact completed native instruction evidence')
        entry = registers()
        document['contexts']['entry'] = entry
        if (entry['rip'] != hex(target) or entry['thread'] != before['thread']
                or _address(entry['general']['rsp']) != stack - 8
                or int.from_bytes(read(stack - 8, 8), 'little') != site + 6):
            raise ValueError('Native import entry contradicts CALL target, thread or return frame')
        entry_raw = read(target, 15)
        ins = Decoder(64, entry_raw, ip=target).decode()
        if ins.is_invalid:
            raise ValueError('Observed API entry instruction is invalid')
        document['entry_instruction'] = {'address': hex(target), 'project_address': None,
            'bytes': entry_raw[:ins.len].hex(), 'execution_bytes': entry_raw[:ins.len].hex(),
            'ram_bytes': entry_raw[:ins.len].hex(), 'registers': entry,
            'identity': {'source_version': session.version['id'], 'context': 'flat',
                'runtime_address': hex(target), 'project_address': None},
            'observation': {'registers_stage': 'before-instruction', 'instruction_completed': False,
                'evidence': 'Observed native imported API entry; instruction not yet executed'},
            'read': {'address': hex(target), 'hex': entry_raw.hex(),
                'sha256': hashlib.sha256(entry_raw).hexdigest()}}
        snapshot('entry')
        document['shadow_store']['entry_hex'] = read(stack, 32).hex()
        if read(slot, 8) != iat:
            raise ValueError('IAT changed while entering the imported call')
        if imported['name'] != 'ExitProcess' and not trace_implementation:
            breakpoint = session.breakpoint(site + 6 - session.delta)
            document['return_breakpoint'] = breakpoint
        if trace_implementation:
            _trace_implementation(session, document, deadline=deadline, call=call, read=read, registers=registers)
            outcome = {'outcome': 'implementation-return', 'session': call('status')}
        else:
            outcome = session.run(timeout_ms=remaining())
        document['outcome'] = outcome
        if imported['name'] == 'ExitProcess':
            if outcome.get('outcome') != 'exited' or outcome.get('session', {}).get('state') != 'exited':
                raise ValueError('ExitProcess did not produce an actual process-exit event')
            document['terminal'] = {'exit_code': outcome['session']['exit_code'],
                'argument_low32': _address(before['general']['rcx']) & 0xffffffff}
            if document['terminal']['exit_code'] != document['terminal']['argument_low32']:
                raise ValueError('Observed process exit code differs from ExitProcess argument')
        else:
            after = registers()
            document['contexts']['return'] = after
            if (outcome.get('outcome') != ('implementation-return' if trace_implementation else 'breakpoint')
                    or after['rip'] != hex(site + 6)
                    or after['thread'] != before['thread'] or _address(after['general']['rsp']) != stack):
                raise ValueError('Imported call did not return to its observed caller frame')
            if breakpoint is not None:
                document['breakpoint_cleanup'] = session.delete_breakpoint(breakpoint['breakpoint_id'])
                breakpoint = None
            changed = [n for n in _NONVOLATILE if after['general'][n] != before['general'][n]]
            document['abi_observation'] = {'nonvolatile_gpr_changed': changed,
                'volatile_gpr_flags': 'Observed only; no preservation assumption',
                'simd_state': 'Unobserved', 'shadow_store_effects': 'Observed bytes; not assumed preserved'}
            if changed:
                raise ValueError('Imported call changed a nonvolatile Win64 GPR')
            snapshot('return')
            document['shadow_store']['return_hex'] = read(stack, 32).hex()
            after_modules = call('modules')
            document['modules_after'] = after_modules
            if after_modules['module_revision'] != state['module_revision'] or after_modules['modules'] != state['modules']:
                raise ValueError('Loaded module identity changed during the imported call')
        document['status'] = 'complete'
        if trace_implementation:
            from .wine_api_contracts import validate_wine_api_contract
            proof = validate_wine_api_contract(document)
            document['implementation_contract'] = proof
            if proof['status'] != 'proved_for_observed_implementation':
                raise ValueError('Observed API implementation did not discharge its machine-code contract: '
                                 + proof.get('reason', proof['status']))
    except Exception as error:
        document['status'] = 'partial'
        document['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        if breakpoint is not None:
            try:
                document['breakpoint_cleanup'] = session.delete_breakpoint(breakpoint['breakpoint_id'])
            except Exception as error:
                document['status'] = 'partial'
                document['breakpoint_cleanup_error'] = {'type': type(error).__name__, 'message': str(error)}
    return session._artifact(name, 'import-call', json.dumps(document, indent=2).encode(),
        {'status': document['status'], 'api': document.get('import', {}).get('name'),
         'terminal': 'terminal' in document})
