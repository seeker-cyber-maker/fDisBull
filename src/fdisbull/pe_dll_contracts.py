"""Symbolic contracts for bounded authored PE64 DLL callbacks.

Raw foreign-module observations remain raw observations. This verifier does
not relabel them as authenticated main-project instruction traces or prove the
Windows/Wine loader. It proves typed instruction transfer under an explicit
callback frame, source code epoch and bounded predecessor-state invariant.
"""
from copy import deepcopy
import hashlib
import time

import capstone
from capstone import x86_const as X
from iced_x86 import Decoder

from .debug_semantics import PE_TRACE_SEMANTICS
from .pe_guard_model import ARITHMETIC_MASK, FLAG_BITS, condition_name, decision
from .pe_region_equivalence import _arithmetic_flags, _condition, _digest
from .wine_arch import register_names, validate_context


_R32 = dict(zip(('eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp'),
               ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp'))) | {
                   f'r{i}d': f'r{i}' for i in range(8, 16)}
_PHASES = {'tls-attach': (0x11, 1), 'dll-attach': (0x22, 1),
           'report': (0x33, None), 'tls-detach': (0x44, 0), 'dll-detach': (0x55, 0)}
_LAYOUT = ('dll_event_count', 'dll_stage', 'dll_seen_stage', 'dll_detach_flag',
           'dll_report_stage_seen', 'dll_report_count_seen', 'dll_tls_detach_stage_seen',
           'dll_dllmain_detach_stage_seen')
SCOPE = ('Complete bounded authored DLL callback transfer for all irrelevant GPRs, defined FLAGS '
         'and globals with event_count 0..7, under the explicit reason/frame/source-code contract. '
         'The exact supplied predecessor invariant is checked separately. Loader invocation, '
         'cross-callback frame preservation, other threads and external effects remain assumptions')


def _address(value):
    if not isinstance(value, str) or not value.startswith('0x'):
        raise ValueError('DLL addresses require explicit hexadecimal strings')
    number = int(value, 16)
    if not 0 <= number < 1 << 64:
        raise ValueError('DLL address exceeds PE64 width')
    return number


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Exact SHA-256 byte identity is required')
    return value


def _cells(rows, maximum=1024):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
        raise ValueError('DLL evidence requires bounded exact memory rows')
    result = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'address', 'hex'}:
            raise ValueError('DLL memory requires exact address/hex rows')
        raw = bytes.fromhex(row['hex'])
        if not raw or len(raw) * 2 != len(row['hex']):
            raise ValueError('DLL memory requires canonical nonempty hex')
        address = _address(row['address'])
        if address + len(raw) > 1 << 64:
            raise ValueError('DLL memory wraps')
        for k, b in enumerate(raw):
            if address + k in result:
                raise ValueError('DLL memory rows overlap')
            result[address + k] = b
    if len(result) > maximum:
        raise ValueError('DLL memory evidence exceeds its byte budget')
    return result


def _rows(cells):
    result = []
    for address, byte in sorted(cells.items()):
        if result and int(result[-1]['address'], 16) + len(result[-1]['hex']) // 2 == address:
            result[-1]['hex'] += f'{byte:02x}'
        else:
            result.append({'address': hex(address), 'hex': f'{byte:02x}'})
    return result


def validate_dll_callback(observation, *, contract, timeout_ms=5000):
    """Prove generic callback transfer and specialize its exact predecessor.

    ``entry_memory`` fixes the 64 owned global bytes and eight caller return
    bytes for lifecycle composition. The generic proof leaves all global bytes
    symbolic except that event_count is bounded by the eight-slot event log.
    """
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 10000:
        raise ValueError('timeout_ms must be 1..10000')
    result = {'format': 'fdisbull-pe-dll-callback-proof-1', 'status': 'unknown',
              'scope': SCOPE, 'transfer': None, 'counterexample': None}
    try:
        if (not isinstance(contract, dict) or set(contract) != {'phase', 'source_sha256', 'module', 'symbols',
                'entry_memory', 'entry_code', 'entry_rsp', 'return_address', 'reason'}
                or contract['phase'] not in _PHASES):
            raise ValueError('An exact authored DLL phase/frame/source contract is required')
        phase = contract['phase']
        marker, reason = _PHASES[phase]
        if contract['reason'] != reason or (reason is not None and type(contract['reason']) is not int):
            raise ValueError('Callback reason must match its explicit process attach/detach phase')
        source = _sha(contract['source_sha256'])
        if (not isinstance(observation, dict) or observation.get('format') != 'fdisbull-native-dll-callback-1'
                or observation.get('status') != 'complete' or observation.get('semantics') != PE_TRACE_SEMANTICS
                or observation['subject_source_sha256'] != source
                or not isinstance(observation['run'], str) or not observation['run']):
            raise ValueError('A complete raw source-bound DLL callback observation is required')
        _sha(observation['controller_source_sha256'])
        module = contract['module']
        if (not isinstance(module, dict) or module.get('bits') != 64
                or type(module.get('generation')) is not int or module['generation'] < 1
                or type(module.get('size')) is not int or not 1 <= module['size'] <= 1 << 30
                or any(module.get(k) != observation['subject_module'].get(k)
                       for k in ('name', 'base', 'size', 'bits', 'generation'))):
            raise ValueError('The callback DLL owner differs from its independent source identity')
        base = _address(module['base'])
        if base + module['size'] > 1 << 64 or not isinstance(module.get('name'), str):
            raise ValueError('DLL owner identity wraps or lacks its observed module name')
        symbols = {name: _address(value) if isinstance(value, str) else value for name, value in contract['symbols'].items()}
        required = {*_LAYOUT, 'dll_event_log', 'dll_data_start', 'dll_data_end', 'dll_code_start', 'dll_code_end',
                    'dll_report_constant_immediate', 'dll_tls_callback', 'dll_entry', 'dll_report'}
        if (not required <= set(symbols) or any(type(v) is not int or not 0 <= v < 1 << 64 for v in symbols.values())
                or symbols['dll_data_end'] - symbols['dll_data_start'] != 64
                or any(symbols[n] != symbols['dll_data_start'] + 4 * i for i, n in enumerate(_LAYOUT))
                or symbols['dll_event_log'] != symbols['dll_data_start'] + 32):
            raise ValueError('Authored DLL source symbols do not describe the declared bounded state layout')
        code_row = contract['entry_code']
        if not isinstance(code_row, dict) or set(code_row) != {'address', 'hex', 'sha256'}:
            raise ValueError('The complete current DLL code epoch is required')
        code = _cells([{'address': code_row['address'], 'hex': code_row['hex']}], 512)
        if (_sha(code_row['sha256']) != hashlib.sha256(bytes.fromhex(code_row['hex'])).hexdigest()
                or _address(code_row['address']) != symbols['dll_code_start']
                or len(code) != symbols['dll_code_end'] - symbols['dll_code_start']
                or any(not base <= a < base + module['size'] for a in [*code, symbols['dll_data_start'], symbols['dll_data_end'] - 1])
                or any(symbols['dll_report_constant_immediate'] + k not in code for k in range(4))):
            raise ValueError('DLL code epoch/source/module ranges disagree')
        entry_rsp, caller = _address(contract['entry_rsp']), _address(contract['return_address'])
        fixed = _cells(contract['entry_memory'], 72)
        globals_cells = set(range(symbols['dll_data_start'], symbols['dll_data_end']))
        stack_cells = set(range(entry_rsp, entry_rsp + 8))
        if (len(globals_cells | stack_cells) != 72 or set(fixed) != globals_cells | stack_cells
                or set(code) & set(fixed) or entry_rsp + 8 > 1 << 64
                or int.from_bytes(bytes(fixed[entry_rsp + k] for k in range(8)), 'little') != caller):
            raise ValueError('Predecessor invariant must cover disjoint globals and the complete callback return word')
        steps = observation['steps']
        if not isinstance(steps, list) or not 1 <= len(steps) <= 128:
            raise ValueError('DLL callback must have 1..128 completed steps')
        entry, exit_context = observation['entry'], observation['exit']
        validate_context(entry, 64)
        validate_context(exit_context, 64)
        target = symbols['dll_report' if phase == 'report' else 'dll_tls_callback' if phase.startswith('tls-') else 'dll_entry']
        if (_address(entry['rip']) != target or _address(entry['general']['rsp']) != entry_rsp
                or observation['return_address'] != contract['return_address']
                or _address(exit_context['rip']) != caller
                or _address(entry['rflags']) & 2 != 2
                or (reason is not None and _address(entry['general']['rdx']) & 0xffffffff != reason)):
            raise ValueError('DLL callback entry/frame/reason differs from its source contract')
        import z3 as z
    except (ValueError, TypeError, KeyError, ImportError) as error:
        return result | {'reason': str(error)}
    deadline = time.monotonic() + timeout_ms / 1000
    names = sorted(register_names(64) - {'rip', 'rflags'})
    initial = {n: z.BitVec('dll_entry_' + n, 64) for n in names}
    initial_flags = z.BitVec('dll_entry_flags', 32)
    initial_ram = {a: z.BitVec(f'dll_entry_ram_{a:x}', 8) for a in sorted(fixed)}
    regs, flags = dict(initial), initial_flags
    memory = initial_ram | {a: z.BitVecVal(b, 8) for a, b in code.items()}
    initial_memory = dict(memory)
    word = lambda cells, a, width: cells[a] if width == 1 else z.Concat(*[cells[a + k] for k in reversed(range(width))])
    count = word(initial_ram, symbols['dll_event_count'], 4)
    assumptions = [initial['rsp'] == entry_rsp, (initial_flags & 2) == 2, z.ULE(count, 7)]
    assumptions += [initial_ram[a] == fixed[a] for a in stack_cells]
    if reason is not None:
        assumptions.append(z.Extract(31, 0, initial['rdx']) == reason)
    sample_pairs = [(initial[n], z.BitVecVal(_address(entry['general'][n]), 64)) for n in names]
    sample_pairs += [(initial_flags, z.BitVecVal(_address(entry['rflags']), 32))]
    sample_pairs += [(initial_ram[a], z.BitVecVal(b, 8)) for a, b in fixed.items()]
    cache = {}
    def observed(expression):
        if z.is_bv_value(expression):
            return expression.as_long()
        key = expression.get_id()
        if key not in cache:
            value = z.simplify(z.substitute(expression, *sample_pairs))
            if not z.is_bv_value(value):
                raise ValueError('A sampled DLL expression is not concrete')
            cache[key] = (expression, value.as_long())
        return cache[key][1]
    solver = z.Solver()
    def query(expression):
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            raise ValueError('DLL symbolic proof deadline exhausted')
        solver.set(timeout=remaining)
        solver.push()
        solver.add(*assumptions, expression)
        status = solver.check()
        model = solver.model() if status == z.sat else None
        solver.pop()
        if status == z.unknown:
            raise ValueError('DLL symbolic solver returned unknown')
        return status, model
    def witness(model):
        value = lambda v: hex(model.eval(v, model_completion=True).as_long())
        return {'entry_general': {n: value(v) for n, v in initial.items()}, 'entry_flags': value(initial_flags),
                'entry_memory': {hex(a): value(v) for a, v in initial_ram.items()}}
    try:
        if int.from_bytes(bytes(fixed[symbols['dll_event_count'] + k] for k in range(4)), 'little') > 7:
            raise ValueError('The exact predecessor event count exceeds its bounded event log')
        if query(z.BoolVal(True))[0] != z.sat:
            raise ValueError('DLL callback contract is infeasible')
        domains, accesses, obligations, epochs, code_writes = [], [], [], [], []
        undefined_symbols = {}
        undefined, returns = 0, 0
        source_version = None
        def image():
            return {'address': code_row['address'],
                    'hex': bytes(observed(memory[a]) for a in sorted(code)).hex()}
        epochs.append({'after_step': 0, **image()})
        runs = []
        for a in sorted(memory):
            if runs and runs[-1][1] == a:
                runs[-1][1] += 1
            else:
                runs.append([a, a + 1])
        def byte_at(pointer):
            simple = z.simplify(pointer)
            if z.is_bv_value(simple):
                return memory.get(simple.as_long(), z.BitVecVal(0, 8))
            value = z.BitVecVal(0, 8)
            for a, b in memory.items():
                value = z.If(pointer == a, b, value)
            return value
        decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        decoder.detail = True
        for index, step in enumerate(steps):
            if time.monotonic() >= deadline:
                raise ValueError('DLL symbolic model construction deadline exhausted')
            event, after = step['event'], step['after']
            validate_context(event['registers'], 64)
            validate_context(after, 64)
            native_before, native_after = _cells(step['memory_before']), _cells(step['memory_after'])
            if (set(native_before) != set(memory) or set(native_after) != set(memory)
                    or (index == 0 and native_before != fixed | code)
                    or (index and (event['registers'] != steps[index - 1]['after']
                                   or native_before != _cells(steps[index - 1]['memory_after'])))
                    or (not index and event['registers'] != entry)):
                raise ValueError('DLL callback step/frame/memory continuity is incomplete')
            identity, observation_meta = event['identity'], event['observation']
            if source_version is None:
                source_version = identity['source_version']
                if type(source_version) is not int or source_version < 1:
                    raise ValueError('Raw DLL observations require their actual controller-analysis version association')
            if (event.get('project_address') is not None or identity.get('project_address') is not None
                    or identity.get('source_version') != source_version or identity.get('context') != 'flat'
                    or identity.get('runtime_address') != event['address']
                    or observation_meta.get('registers_stage') != 'before-instruction'
                    or observation_meta.get('instruction_completed') is not True or event.get('active_layers')
                    or event['registers']['thread'] != entry['thread'] or after['thread'] != entry['thread']
                    or event['registers']['rip'] != event['address']):
                raise ValueError('DLL step must retain its raw foreign-module completed native identity')
            address = _address(event['address'])
            raw = bytes.fromhex(event.get('execution_bytes', event.get('bytes', '')))
            if (not 1 <= len(raw) <= 15 or event.get('ram_bytes', raw.hex()) != raw.hex()
                    or any(address + k not in code for k in range(len(raw)))):
                raise ValueError('DLL instruction fetch escapes its explicit code epoch')
            valid_fetch = z.And(*[memory[address + k] == byte for k, byte in enumerate(raw)])
            obligations.append(('instruction_fetch', index, z.And(*domains), valid_fetch))
            if any(observed(memory[a]) != b for a, b in native_before.items()):
                raise ValueError('DLL before-step memory contradicts its symbolic predecessor')
            native = list(decoder.disasm(raw, address))
            if len(native) != 1 or native[0].size != len(raw) or any(native[0].prefix):
                raise ValueError('DLL instruction is not one exact unprefixed typed instruction')
            ins = native[0]
            sequential, next_pc = address + len(raw), _address(after['rip'])
            def register(op):
                name = ins.reg_name(op.reg)
                if op.size == 8 and name in regs:
                    return name, 64
                if op.size == 4 and name in _R32:
                    return _R32[name], 32
                raise ValueError('Only full or DWORD GPR operands are supported')
            def location(op):
                if op.mem.segment:
                    raise ValueError('Segment-overridden DLL data operands remain unsupported')
                pointer = z.BitVecVal(op.mem.disp % (1 << 64), 64)
                for r, scale in ((op.mem.base, 1), (op.mem.index, op.mem.scale)):
                    if r:
                        name = ins.reg_name(r)
                        value = z.BitVecVal(sequential, 64) if name == 'rip' else regs.get(name)
                        if value is None:
                            raise ValueError('Unknown DLL address register')
                        pointer = pointer + value * scale
                pointer = z.simplify(z.substitute(pointer, (initial['rsp'], z.BitVecVal(entry_rsp, 64))))
                return pointer, op.size
            def memory_access(pointer, width, value=None):
                nonlocal memory
                pointer = z.simplify(z.substitute(pointer, (initial['rsp'], z.BitVecVal(entry_rsp, 64))))
                if width not in (1, 4, 8):
                    raise ValueError('Unsupported DLL memory width')
                sampled = observed(pointer)
                if sampled + width > 1 << 64 or any(sampled + k not in memory for k in range(width)):
                    raise ValueError('Sampled DLL memory access escapes its declared ordinary RAM/code')
                valid = z.Or(*[z.And(z.UGE(pointer, start), z.ULE(pointer, end - width))
                               for start, end in runs if end - start >= width])
                obligations.append(('memory_safety', index, z.And(*domains), valid))
                old = (byte_at(pointer) if width == 1 else z.Concat(*[byte_at(pointer + k) for k in reversed(range(width))])) if value is None else None
                accesses.append(('read' if value is None else 'write', pointer, width, old if value is None else value))
                if value is not None:
                    write_cells = set(memory)
                    if not z.is_bv_value(z.simplify(pointer)):
                        # Reduce only after proving the excluded regions cannot
                        # alias this store under its preceding guards. The proof
                        # still leaves every event-log index 0..7 symbolic.
                        for region in (set(code), stack_cells, set(range(symbols['dll_data_start'], symbols['dll_event_log']))):
                            noalias = z.Or(z.ULE(pointer, min(region) - width) if min(region) >= width else z.BoolVal(False),
                                           z.UGE(pointer, max(region) + 1) if max(region) + 1 < 1 << 64 else z.BoolVal(False))
                            if query(z.And(*domains, z.Not(noalias)))[0] == z.unsat:
                                write_cells -= region
                    alignment = None
                    if not z.is_bv_value(z.simplify(pointer)):
                        if query(z.And(*domains, (pointer & 3) != (sampled & 3)))[0] == z.unsat:
                            alignment = sampled & 3
                    for k in range(width):
                        target = z.simplify(pointer + k)
                        byte = z.Extract(k * 8 + 7, k * 8, value)
                        if z.is_bv_value(target):
                            if target.as_long() in memory:
                                memory[target.as_long()] = byte
                        else:
                            memory = {a: z.If(target == a, byte, previous)
                                      if a in write_cells and (alignment is None or a & 3 == (alignment + k) & 3) else previous
                                      for a, previous in memory.items()}
                    if any(sampled + k in code for k in range(width)):
                        code_writes.append({'step': index, 'address': hex(sampled), 'width': width})
                        epochs.append({'after_step': index + 1, **image()})
                return old
            def read(op):
                if op.type == X.X86_OP_REG:
                    name, width = register(op)
                    return regs[name] if width == 64 else z.Extract(31, 0, regs[name])
                if op.type == X.X86_OP_IMM:
                    return z.BitVecVal(op.imm % (1 << (8 * op.size)), 8 * op.size)
                if op.type == X.X86_OP_MEM:
                    return memory_access(*location(op))
                raise ValueError('Unsupported DLL operand')
            def write(op, value):
                if op.type == X.X86_OP_REG:
                    name, width = register(op)
                    if value.size() != width:
                        raise ValueError('DLL register write width differs from its operand')
                    regs[name] = value if width == 64 else z.ZeroExt(32, value)
                elif op.type == X.X86_OP_MEM:
                    pointer, width = location(op)
                    value = z.Extract(width * 8 - 1, 0, value) if value.size() >= width * 8 else z.SignExt(width * 8 - value.size(), value)
                    memory_access(pointer, width, value)
                else:
                    raise ValueError('Unsupported DLL destination')
            iced = Decoder(64, raw, ip=address).decode()
            if iced.is_jcc_short_or_near or iced.is_jmp_short_or_near:
                condition = condition_name(iced)
                predicate = _condition(z, condition, flags)
                taken = decision(condition, _address(event['registers']['rflags']))
                if next_pc != (iced.near_branch_target if taken else sequential):
                    raise ValueError('DLL branch successor contradicts native FLAGS')
                domains.append(predicate if taken else z.Not(predicate))
            elif raw == b'\xc3':
                if index != len(steps) - 1:
                    raise ValueError('Only the final DLL RET may leave the callback')
                pointer = regs['rsp']
                target = memory_access(pointer, 8)
                obligations.append(('return_frame', index, z.And(*domains),
                                    z.And(pointer == entry_rsp, target == caller)))
                regs['rsp'] = pointer + 8
                returns += 1
                if next_pc != caller:
                    raise ValueError('DLL RET did not reach its actual caller')
            else:
                if next_pc != sequential:
                    raise ValueError('Unsupported nonsequential DLL control flow')
                ops = ins.operands
                if raw == b'\x90':
                    pass
                elif ins.mnemonic in ('mov', 'movabs') and len(ops) == 2:
                    write(ops[0], read(ops[1]))
                elif ins.mnemonic == 'lea' and len(ops) == 2 and ops[1].type == X.X86_OP_MEM:
                    name, width = register(ops[0])
                    if width != 64:
                        raise ValueError('DLL LEA requires a full-width destination')
                    regs[name] = location(ops[1])[0]
                elif ins.mnemonic in ('cmp', 'test', 'add', 'sub', 'or', 'and', 'xor') and len(ops) == 2:
                    a, b = read(ops[0]), read(ops[1])
                    if a.size() not in (32, 64) or b.size() != a.size():
                        raise ValueError('DLL arithmetic requires exact DWORD/full-width operands')
                    op = ins.mnemonic
                    value = (a - b if op in ('cmp', 'sub') else a + b if op == 'add' else
                             a | b if op == 'or' else a ^ b if op == 'xor' else a & b)
                    logical = op in ('test', 'or', 'and', 'xor')
                    undefined_name = f'dll_undefined_af_{index}'
                    undefined_symbols[undefined_name] = 'Bool'
                    flags = _arithmetic_flags(z, 'and' if op == 'test' else op, a, b, value, flags,
                                              z.Bool(undefined_name))
                    undefined = (1 << FLAG_BITS['af']) if logical else 0
                    if op not in ('cmp', 'test'):
                        write(ops[0], value)
                else:
                    raise ValueError('DLL instruction lies outside the typed callback proof profile')
            if (any(observed(regs[n]) != _address(after['general'][n]) for n in names)
                    or observed(flags & (0xffffffff ^ undefined)) != _address(after['rflags']) & (0xffffffff ^ undefined)
                    or any(observed(memory[a]) != b for a, b in native_after.items())):
                raise ValueError('Native DLL step GPR/defined FLAGS/memory contradicts the symbolic instruction transfer')
        if returns != 1 or steps[-1]['after'] != exit_context:
            raise ValueError('DLL callback lacks its complete actual RET boundary')
        for kind, index, prefix, valid in obligations:
            status, model = query(z.And(prefix, z.Not(valid)))
            if status != z.unsat:
                return result | {'reason': 'DLL prior-guard obligation is not proved: ' + kind,
                                 'counterexample': witness(model) | {'step': index}}
        domain = z.And(*domains)
        if query(z.Not(domain))[0] != z.unsat:
            return result | {'reason': 'The native DLL path does not cover every admitted callback input'}
        expected = dict(initial_memory)
        old_stage, old_flag = (word(initial_ram, symbols[n], 4) for n in ('dll_stage', 'dll_detach_flag'))
        log_pointer = z.BitVecVal(symbols['dll_event_log'], 64) + z.ZeroExt(32, count) * 4
        def expected_store(pointer, width, value):
            for k in range(width):
                byte = z.Extract(k * 8 + 7, k * 8, value)
                if isinstance(pointer, int):
                    expected[pointer + k] = byte
                else:
                    expected.update({a: z.If(pointer + k == a, byte, previous)
                                     if symbols['dll_event_log'] <= a < symbols['dll_data_end'] and
                                     (a - symbols['dll_event_log']) % 4 == k else previous
                                     for a, previous in expected.items()})
        expected_store(log_pointer, 4, z.BitVecVal(marker, 32))
        expected_store(symbols['dll_event_count'], 4, count + 1)
        if phase == 'tls-attach':
            expected_store(symbols['dll_stage'], 4, z.BitVecVal(1, 32))
            expected[symbols['dll_report_constant_immediate']] = z.BitVecVal(2, 8)
        elif phase == 'dll-attach':
            expected_store(symbols['dll_seen_stage'], 4, old_stage)
            expected_store(symbols['dll_stage'], 4, z.BitVecVal(2, 32))
            expected[symbols['dll_report_constant_immediate']] = z.BitVecVal(3, 8)
        elif phase == 'report':
            expected_store(symbols['dll_report_stage_seen'], 4, old_stage)
            expected_store(symbols['dll_report_count_seen'], 4, count)
            expected_store(symbols['dll_stage'], 4, z.BitVecVal(3, 32))
        else:
            field = 'dll_tls_detach_stage_seen' if phase == 'tls-detach' else 'dll_dllmain_detach_stage_seen'
            expected_store(symbols[field], 4, old_stage)
            expected_store(symbols['dll_detach_flag'], 4, old_flag | (1 if phase == 'tls-detach' else 2))
        expected_regs = dict(initial)
        expected_regs['rsp'] = initial['rsp'] + 8
        expected_regs['r9'] = z.BitVecVal(symbols['dll_event_log'], 64)
        expected_regs['rax'] = (z.BitVecVal(1, 64) if phase.startswith('dll-') else
            z.ZeroExt(32, word(initial_memory, symbols['dll_report_constant_immediate'], 4)) if phase == 'report'
            else z.ZeroExt(32, count + 1))
        last = old_flag | (1 if phase == 'tls-detach' else 2) if phase.endswith('detach') else count + 1
        parity = z.Extract(0, 0, last)
        for bit in range(1, 8):
            parity = parity ^ z.Extract(bit, bit, last)
        expected_flags = initial_flags & ((~ARITHMETIC_MASK) & 0xffffffff)
        expected_flags |= z.If(parity == 0, z.BitVecVal(1 << FLAG_BITS['pf'], 32), z.BitVecVal(0, 32))
        if phase.endswith('detach'):
            expected_flags |= z.If(z.Extract(31, 31, last) == 1,
                                   z.BitVecVal(1 << FLAG_BITS['sf'], 32), z.BitVecVal(0, 32))
        mask = 0xffffffff ^ undefined
        deviations = [regs[n] != expected_regs[n] for n in names]
        deviations += [(flags & mask) != (expected_flags & mask)]
        deviations += [memory[a] != expected[a] for a in memory]
        expected_accesses = []
        def effect(kind, address, width, value):
            expected_accesses.append((kind, z.BitVecVal(address, 64) if isinstance(address, int) else address,
                                      width, value))
        seen = ('dll_seen_stage' if phase == 'dll-attach' else 'dll_report_stage_seen' if phase == 'report'
                else 'dll_tls_detach_stage_seen' if phase == 'tls-detach' else
                'dll_dllmain_detach_stage_seen' if phase == 'dll-detach' else None)
        if seen is not None:
            effect('read', symbols['dll_stage'], 4, old_stage)
            effect('write', symbols[seen], 4, old_stage)
        if phase == 'report':
            effect('read', symbols['dll_event_count'], 4, count)
            effect('write', symbols['dll_report_count_seen'], 4, count)
        effect('read', symbols['dll_event_count'], 4, count)
        effect('write', log_pointer, 4, z.BitVecVal(marker, 32))
        effect('write', symbols['dll_event_count'], 4, count + 1)
        if phase in ('tls-attach', 'dll-attach', 'report'):
            effect('write', symbols['dll_stage'], 4, z.BitVecVal({'tls-attach': 1, 'dll-attach': 2, 'report': 3}[phase], 32))
            if phase != 'report':
                effect('write', symbols['dll_report_constant_immediate'], 1,
                       z.BitVecVal(2 if phase == 'tls-attach' else 3, 8))
        else:
            effect('read', symbols['dll_detach_flag'], 4, old_flag)
            effect('write', symbols['dll_detach_flag'], 4, last)
        effect('read', entry_rsp, 8, word(initial_ram, entry_rsp, 8))
        if len(accesses) != len(expected_accesses):
            deviations.append(z.BoolVal(True))
        for actual, expected_access in zip(accesses, expected_accesses):
            if actual[0] != expected_access[0] or actual[2] != expected_access[2]:
                deviations.append(z.BoolVal(True))
            else:
                deviations += [actual[1] != expected_access[1], actual[3] != expected_access[3]]
        status, model = query(z.Or(*deviations))
        if status == z.sat:
            return result | {'status': 'contract_mismatch', 'reason': 'Symbolic callback transfer differs from its independent source phase rule',
                             'counterexample': witness(model)}
        budget = {'remaining': 250000}
        def expression(value):
            text = z.simplify(value).sexpr()
            if len(text) > 16384 or len(text) > budget['remaining']:
                raise ValueError(f'DLL symbolic transfer presentation budget exhausted (expression={len(text)}, remaining={budget["remaining"]})')
            budget['remaining'] -= len(text)
            return text
        specialized = [(v, z.BitVecVal(fixed[a], 8)) for a, v in initial_ram.items()]
        post = {}
        for a, value in memory.items():
            concrete = z.simplify(z.substitute(value, *specialized))
            if not z.is_bv_value(concrete):
                raise ValueError('Exact predecessor does not specialize the callback memory transfer')
            post[a] = concrete.as_long()
        transfer = {'registers': {n: expression(regs[n]) for n in names}, 'flags': expression(flags & mask),
            'defined_flags_mask': mask, 'memory_bytes': {hex(a): expression(memory[a]) for a in sorted(initial_ram)},
            'code_bytes': {hex(a): expression(memory[a]) for a in sorted(code)}, 'guard': expression(domain),
            'ordered_accesses': [{'kind': k, 'address': expression(a), 'width': w, 'value': expression(v)} for k, a, w, v in accesses],
            'termination_bound_instructions': len(steps)}
        result.update(status='proved_for_authored_dll_callback', phase=phase, contract=deepcopy(contract),
            symbols={**{str(v): 64 for v in initial.values()}, str(initial_flags): 32,
                     **{str(v): 8 for v in initial_ram.values()}, **undefined_symbols},
            source={'observation_sha256': _digest(observation), 'contract_sha256': _digest(contract),
                'dll_source_sha256': source, 'dll_module': deepcopy(module),
                'controller_source_sha256': observation['controller_source_sha256'], 'run': observation['run'],
                'controller_analysis_version': source_version,
                'identity_note': 'Foreign DLL bytes keep module identity; controller analysis version is association only'},
            transfer=transfer, post_memory=_rows({a: post[a] for a in initial_ram}),
            post_code={'address': code_row['address'], 'hex': bytes(post[a] for a in sorted(code)).hex()},
            code_versions=epochs, code_writes=code_writes,
            generic_constraints={'entry_rsp': hex(entry_rsp), 'return_address': hex(caller), 'reason_low32': reason,
                'event_count_unsigned_range': [0, 7], 'globals': 'Otherwise symbolic',
                'flags': 'Architectural bit1 set; final undefined AF excluded when required'},
            checks={'prior_guard_obligations': len(obligations), 'path_cover': 'complete',
                'source_effect_difference': 'unsat', 'native_steps': 'all GPR, defined FLAGS, code and declared memory',
                'predecessor_invariant': 'Exact entry globals/frame admitted; post-state specializes generic transfer'})
        result['sha256'] = _digest(result)
        return result
    except (ValueError, TypeError, KeyError, IndexError) as error:
        return result | {'reason': str(error)}


def expand_dll_callback_contract(proof, observation, contract):
    """Expand exactly the immutable raw callback evidence and its source contract."""
    if (not isinstance(proof, dict) or proof.get('status') != 'proved_for_authored_dll_callback'
            or proof.get('sha256') != _digest({k: v for k, v in proof.items() if k != 'sha256'})
            or proof.get('source', {}).get('observation_sha256') != _digest(observation)
            or proof['source'].get('contract_sha256') != _digest(contract)):
        raise ValueError('DLL contract expansion requires its exact original evidence and contract')
    return {'observation': deepcopy(observation), 'contract': deepcopy(contract)}
