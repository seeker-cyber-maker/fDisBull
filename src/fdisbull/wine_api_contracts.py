"""Prove small observed Wine API implementations from their exact instructions.

Names select the property to check, never the implementation semantics. Only a
complete, straight-line thunk/leaf/RET body is admitted. ExitProcess, loader
code and unknown instructions remain outside this bounded verifier.
"""
from copy import deepcopy
import hashlib
import time

import capstone
from capstone import x86_const as X

from .debug_semantics import PE_TRACE_SEMANTICS
from .pe_region_equivalence import _digest
from .wine_arch import register_names, validate_context


_GPR32 = dict(zip(('eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp'),
                 ('rax', 'rbx', 'rcx', 'rdx', 'rsi', 'rdi', 'rbp', 'rsp'))) | {
                    f'r{i}d': f'r{i}' for i in range(8, 16)}
SCOPE = ('Exact observed single-threaded Wine SetLastError/GetLastError thunk and leaf '
         'instructions through RET, for all DWORD inputs and prior last-error values, '
         'under the observed fixed thunk/frame bytes and explicit Win64 GS/TEB binding; '
         'other implementations, concurrent mutation, faults and OS initialization are not proved')


def _address(value):
    if not isinstance(value, str) or not value.startswith('0x'):
        raise ValueError('Implementation addresses require exact hexadecimal strings')
    number = int(value, 16)
    if not 0 <= number < 1 << 64:
        raise ValueError('Implementation address exceeds PE64 width')
    return number


def _hex(value, *, maximum=512):
    if not isinstance(value, str) or not 2 <= len(value) <= maximum * 2 or len(value) % 2:
        raise ValueError('Bounded exact byte evidence is required')
    raw = bytes.fromhex(value)
    if len(raw) * 2 != len(value):
        raise ValueError('Byte evidence must use canonical unspaced hexadecimal')
    return raw


def _snapshot(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 64:
        raise ValueError('Implementation memory requires 1..64 exact ranges')
    cells = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'address', 'hex'}:
            raise ValueError('Implementation memory rows require exact address and hex fields')
        address, raw = _address(row['address']), _hex(row['hex'])
        if address + len(raw) > 1 << 64:
            raise ValueError('Implementation memory wraps')
        for offset, byte in enumerate(raw):
            if address + offset in cells:
                raise ValueError('Implementation memory ranges overlap')
            cells[address + offset] = byte
    if len(cells) > 512:
        raise ValueError('Implementation memory exceeds 512 bytes')
    return cells


def validate_wine_api_contract(observation, *, timeout_ms=1000):
    """Validate actual native steps, then prove the selected API's leaf property.

    The input is an immutable import-call document with an ``implementation``
    observation. Every instruction, memory access, module owner and return
    boundary must agree. No imported function is executed by this verifier.
    """
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 10000:
        raise ValueError('timeout_ms must be 1..10000')
    result = {'format': 'fdisbull-wine-api-contract-proof-1', 'status': 'unknown',
              'scope': SCOPE, 'implementation_equivalence': None, 'counterexample': None}
    try:
        if (not isinstance(observation, dict) or observation.get('format') != 'fdisbull-wine-import-call-1'
                or observation.get('status') != 'complete'
                or observation['import']['name'] not in ('SetLastError', 'GetLastError')):
            raise ValueError('A complete SetLastError/GetLastError import observation is required')
        name = observation['import']['name']
        analysis_identity = observation['identity']
        if (type(analysis_identity.get('source_version')) is not int or analysis_identity['source_version'] < 1
                or not isinstance(analysis_identity.get('run'), str) or not 1 <= len(analysis_identity['run']) <= 128
                or any(len(_hex(analysis_identity[key], maximum=32)) != 32
                       for key in ('source_sha256', 'version_sha256'))):
            raise ValueError('An exact originating analysis/run byte identity is required')
        impl = observation['implementation']
        if (not isinstance(impl, dict) or impl.get('format') != 'fdisbull-wine-api-implementation-1'
                or impl.get('status') != 'complete' or impl.get('bits') != 64
                or impl.get('semantics') != PE_TRACE_SEMANTICS):
            raise ValueError('A complete native PE64 implementation trace is required')
        events, reads, accesses = impl['events'], impl['code_reads'], impl['accesses']
        if (not isinstance(events, list) or not 2 <= len(events) <= 33
                or not isinstance(reads, list) or len(reads) != len(events) - 1
                or not isinstance(accesses, list) or len(accesses) > 64):
            raise ValueError('Implementation trace/read/access budgets or completeness are invalid')
        info, binding = impl['thread_info'], impl['segment_binding']
        teb = _address(info['teb'])
        if (info.get('bits') != 64 or info.get('teb_source') not in {
                'CREATE_PROCESS_DEBUG_EVENT.lpThreadLocalBase', 'CREATE_THREAD_DEBUG_EVENT.lpThreadLocalBase'}
                or info.get('gs_base_register_observed') is not False
                or binding != {'segment': 'gs', 'offset': '0x30', 'teb': hex(teb),
                               'gs_base_register_observed': False} or teb + 0x70 > 1 << 64):
            raise ValueError('An explicit observed-thread GS/TEB convention is required')
        before, after = _snapshot(impl['memory']['entry']), _snapshot(impl['memory']['exit'])
        if set(before) != set(after):
            raise ValueError('Implementation memory snapshots must cover identical cells')
        names = sorted(register_names(64) - {'rip', 'rflags'})
        for index, event in enumerate(events):
            validate_context(event['registers'], 64)
            address = _address(event['address'])
            identity, observed = event['identity'], event['observation']
            if (_address(event['registers']['rip']) != address
                    or identity.get('context') != 'flat'
                    or identity.get('source_version') != analysis_identity['source_version']
                    or identity.get('runtime_address') != event['address']
                    or identity.get('project_address') != event.get('project_address')
                    or observed.get('registers_stage') != 'before-instruction'
                    or (index < len(events) - 1 and observed.get('instruction_completed') is not True)):
                raise ValueError('Implementation event lacks exact completed native identity')
            if index < len(events) - 1 and event.get('project_address') is not None:
                raise ValueError('A foreign DLL instruction must not carry a fabricated project address')
            if event['registers'].get('thread') != info['thread']:
                raise ValueError('Implementation trace changes its observed thread')
        if (events[0]['registers'] != observation['contexts']['entry']
                or events[-1]['registers'] != observation['contexts']['return']
                or events[0]['address'] != observation['import']['target']
                or events[0]['address'] != observation['resolution']['target']
                or events[-1]['address'] != observation['import']['return_address']):
            raise ValueError('Implementation entry/RET is not bound to its actual imported call')
        modules = observation['modules_before']['modules']
        if not isinstance(modules, list) or len(modules) > 256:
            raise ValueError('Observed loaded-module identity is required')
        code, sources = {}, []
        for index, (event, read) in enumerate(zip(events[:-1], reads, strict=True)):
            if (not isinstance(read, dict) or set(read) != {'event_index', 'address', 'hex', 'sha256', 'module'}
                    or read['event_index'] != index or read['address'] != event['address']):
                raise ValueError('Each DLL instruction requires its exact indexed native code read')
            raw_read = _hex(read['hex'], maximum=64)
            raw = _hex(event.get('execution_bytes', event.get('bytes')), maximum=15)
            if (hashlib.sha256(raw_read).hexdigest() != read['sha256'] or not raw_read.startswith(raw)):
                raise ValueError('Instruction bytes disagree with their hashed native read')
            address = _address(event['address'])
            owners = [m for m in modules if _address(m['base']) <= address
                      and address + len(raw) <= _address(m['base']) + m['size']]
            if len(owners) != 1 or any(read['module'].get(k) != owners[0].get(k)
                    for k in ('name', 'base', 'size', 'generation')):
                raise ValueError('DLL instruction has an absent or ambiguous loaded-module owner')
            if owners[0].get('bits') != 64 or not owners[0]['name'].casefold().endswith('.dll'):
                raise ValueError('An implementation body instruction is not owned by an observed DLL')
            for offset, byte in enumerate(raw):
                if address + offset in before or (address + offset in code and code[address + offset] != byte):
                    raise ValueError('Implementation code aliases data or changes during the admitted body')
                code[address + offset] = byte
            sources.append({'address': event['address'], 'hex': raw.hex(),
                'sha256': hashlib.sha256(raw).hexdigest(), 'read_sha256': read['sha256'],
                'module': deepcopy(read['module'])})
        import z3 as z
        deadline = time.monotonic() + timeout_ms / 1000
        initial = {n: z.BitVec('api_entry_' + n, 64) for n in names}
        initial_flags = z.BitVec('api_entry_flags', 32)
        initial_memory = {a: z.BitVec(f'api_entry_ram_{a:x}', 8) for a in before}
        regs, flags, memory = dict(initial), initial_flags, dict(initial_memory)
        initial_context = events[0]['registers']
        stack = _address(initial_context['general']['rsp'])
        caller = _address(events[-1]['address'])
        required = set(range(teb + 0x30, teb + 0x38)) | set(range(teb + 0x68, teb + 0x6c)) | set(range(stack, stack + 8))
        if not required <= set(before) or len(required) != 20:
            raise ValueError('TEB self, DWORD last-error and caller return-slot evidence is required without aliasing')
        last_error_cells = set(range(teb + 0x68, teb + 0x6c))
        word = lambda mem, start, width: z.Concat(*[mem[start + k] for k in reversed(range(width))])
        if (int.from_bytes(bytes(before[teb + 0x30 + k] for k in range(8)), 'little') != teb
                or int.from_bytes(bytes(before[stack + k] for k in range(8)), 'little') != caller):
            raise ValueError('TEB self or architectural return word contradicts the observed bindings')
        assumptions = [initial['rsp'] == stack, (initial_flags & 2) == 2]
        assumptions += [v == before[a] for a, v in initial_memory.items() if a not in last_error_cells]
        samples = [(initial[n], z.BitVecVal(_address(initial_context['general'][n]), 64)) for n in names]
        samples += [(initial_flags, z.BitVecVal(_address(initial_context['rflags']), 32))]
        samples += [(v, z.BitVecVal(before[a], 8)) for a, v in initial_memory.items()]
        def concrete(value):
            evaluated = z.simplify(z.substitute(value, *samples))
            if not z.is_bv_value(evaluated):
                raise ValueError('An observed implementation expression is not concrete')
            return evaluated.as_long()
        footprint, footprint_cells, segment_reads, returns, obligations = [], set(), 0, 0, []
        access_index = 0
        def access(index, kind, address, width, value=None):
            nonlocal access_index
            if address < 0 or address + width > 1 << 64 or any(address + k not in memory for k in range(width)):
                raise ValueError('An implementation access escapes its complete memory evidence')
            prior = word(memory, address, width)
            if access_index >= len(accesses):
                raise ValueError('A native implementation memory footprint was omitted')
            row = accesses[access_index]
            access_index += 1
            if (not isinstance(row, dict) or set(row) != {'event_index', 'kind', 'address', 'width', 'before_hex', 'after_hex'}
                    or row['event_index'] != index or row['kind'] != kind or _address(row['address']) != address
                    or row['width'] != width or _hex(row['before_hex'], maximum=8) != concrete(prior).to_bytes(width, 'little')):
                raise ValueError('Native memory access evidence contradicts the decoded instruction')
            if kind == 'write':
                for k in range(width):
                    memory[address + k] = z.Extract(k * 8 + 7, k * 8, value)
            following_value = value if kind == 'write' else prior
            if _hex(row['after_hex'], maximum=8) != concrete(following_value).to_bytes(width, 'little'):
                raise ValueError('Native memory after-access evidence contradicts the instruction')
            footprint.append({'event_index': index, 'kind': kind, 'address': hex(address), 'width': width})
            footprint_cells.update(range(address, address + width))
            return prior
        decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        decoder.detail = True
        for index, event in enumerate(events[:-1]):
            if time.monotonic() >= deadline:
                raise ValueError('API implementation proof deadline exhausted')
            address = _address(event['address'])
            raw = _hex(event.get('execution_bytes', event.get('bytes')), maximum=15)
            following = events[index + 1]
            next_address = _address(following['address'])
            decoded = list(decoder.disasm(raw, address))
            if len(decoded) != 1 or decoded[0].size != len(raw):
                raise ValueError('DLL instruction bytes do not decode exactly')
            ins = decoded[0]
            sequential = address + len(raw)
            if raw in (b'\xf3\x0f\x1e\xfa', b'\x90', b'\x66\x90'):
                expected_pc = sequential
            elif raw == bytes.fromhex('65488b042530000000'):
                regs['rax'] = access(index, 'read', teb + 0x30, 8)
                segment_reads += 1
                expected_pc = sequential
            elif raw[:2] == b'\xff\x25' and len(raw) == 6:
                slot = sequential + int.from_bytes(raw[2:], 'little', signed=True)
                target = access(index, 'read', slot, 8)
                obligations.append(target == next_address)
                expected_pc = next_address
            elif ((raw[0] == 0xe9 and len(raw) == 5) or (raw[0] == 0xeb and len(raw) == 2)):
                expected_pc = sequential + int.from_bytes(raw[1:], 'little', signed=True)
            elif ins.mnemonic == 'lea' and len(ins.operands) == 2:
                dest, src = ins.operands
                if (dest.type != X.X86_OP_REG or src.type != X.X86_OP_MEM or dest.size != 8
                        or ins.reg_name(dest.reg) != 'rsp' or ins.reg_name(src.mem.base) != 'rsp'
                        or src.mem.index or src.mem.disp):
                    raise ValueError('Only the actual no-op RSP hotpatch LEA is admitted')
                expected_pc = sequential
            elif ins.mnemonic == 'mov' and len(ins.operands) == 2:
                dest, src = ins.operands
                if (dest.type == X.X86_OP_REG and dest.size == 4 and src.type == X.X86_OP_MEM
                        and ins.reg_name(src.mem.base) == 'rax' and not src.mem.index and not src.mem.segment
                        and src.mem.disp == 0x68):
                    name32 = _GPR32.get(ins.reg_name(dest.reg))
                    if name32 is None:
                        raise ValueError('Unsupported API DWORD result register')
                    location = regs['rax'] + 0x68
                    obligations.append(location == teb + 0x68)
                    regs[name32] = z.ZeroExt(32, access(index, 'read', concrete(location), 4))
                elif (dest.type == X.X86_OP_MEM and dest.size == 4 and src.type == X.X86_OP_REG and src.size == 4
                        and ins.reg_name(dest.mem.base) == 'rax' and not dest.mem.index and not dest.mem.segment
                        and dest.mem.disp == 0x68):
                    name32 = _GPR32.get(ins.reg_name(src.reg))
                    if name32 is None:
                        raise ValueError('Unsupported API DWORD argument register')
                    location = regs['rax'] + 0x68
                    obligations.append(location == teb + 0x68)
                    access(index, 'write', concrete(location), 4, z.Extract(31, 0, regs[name32]))
                else:
                    raise ValueError('Instruction is outside the observed bounded TLS leaf profile')
                expected_pc = sequential
            elif raw == b'\xc3':
                if index != len(events) - 2:
                    raise ValueError('Only the final API RET may leave the observed implementation')
                location = regs['rsp']
                obligations.append(location == stack)
                target = access(index, 'read', concrete(location), 8)
                obligations.append(target == caller)
                regs['rsp'] = regs['rsp'] + 8
                returns += 1
                expected_pc = caller
            else:
                raise ValueError('Instruction is outside the complete thunk/TLS/RET proof profile')
            if expected_pc != next_address:
                raise ValueError('Actual instruction control flow contradicts the next native PC')
            next_context = following['registers']
            if (any(concrete(regs[n]) != _address(next_context['general'][n]) for n in names)
                    or concrete(flags) != _address(next_context['rflags'])):
                raise ValueError('Actual GPR/FLAGS transition contradicts the instruction model')
        if returns != 1 or segment_reads != 1 or access_index != len(accesses):
            raise ValueError('Implementation RET, GS self read or complete footprint is missing/duplicated')
        if set(before) != footprint_cells | last_error_cells:
            raise ValueError('Implementation snapshots must cover exactly the modeled footprint and last-error cell')
        if any(concrete(memory[a]) != byte for a, byte in after.items()):
            raise ValueError('Native implementation exit memory contradicts its modeled writes')
        solver = z.Solver()
        def prove(claim):
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining <= 0:
                raise ValueError('API implementation proof deadline exhausted')
            solver.set(timeout=remaining)
            solver.push()
            solver.add(*assumptions, z.Not(claim))
            status = solver.check()
            model = solver.model() if status == z.sat else None
            solver.pop()
            if status == z.unknown:
                raise ValueError('API implementation solver could not discharge its obligation')
            return status == z.unsat, model
        for obligation in obligations:
            if not prove(obligation)[0]:
                raise ValueError('API pointer/RET target is not proved for its complete entry contract')
        expected = dict(initial)
        expected['rsp'] = initial['rsp'] + 8
        expected['rax'] = z.BitVecVal(teb, 64) if name == 'SetLastError' else z.ZeroExt(32, word(initial_memory, teb + 0x68, 4))
        differences = [regs[n] != expected[n] for n in names] + [flags != initial_flags]
        for a in before:
            wanted = (z.Extract((a - teb - 0x68) * 8 + 7, (a - teb - 0x68) * 8, initial['rcx'])
                      if name == 'SetLastError' and a in last_error_cells else initial_memory[a])
            differences.append(memory[a] != wanted)
        good, witness = prove(z.Not(z.Or(*differences)))
        result.update(api=name, observed_instruction_count=len(events) - 1,
            source={'import_observation_sha256': _digest({k: v for k, v in observation.items()
                                                         if k != 'implementation_contract'}),
                    'import_observation_excludes': ['implementation_contract'], 'implementation_sha256': _digest(impl),
                    'analysis_identity': deepcopy(analysis_identity), 'code_sources': sources}, footprint=footprint,
            segment_binding={'teb': hex(teb), 'segment': 'gs', 'self_offset': '0x30',
                'last_error_offset': '0x68', 'gs_base_register_observed': False,
                'assumption': 'Win64 GS/TEB convention; observed DEBUGEVENT TEB, self word and actual GS-load destination agree'},
            solver={'name': 'z3', 'version': z.get_version_string(), 'timeout_ms_total': timeout_ms},
            precise_effects={'rax': hex(teb) if name == 'SetLastError' else 'zero_extend_u32(entry_last_error)',
                'rsp': 'entry_rsp + 8', 'other_gpr': 'unchanged', 'flags': 'unchanged',
                'memory_writes': [{'address': hex(teb + 0x68), 'length': 4, 'value': 'low32(entry_rcx)'}]
                                 if name == 'SetLastError' else [],
                'other_memory': 'No other write instructions in the complete admitted implementation',
                'termination': 'Complete acyclic thunk/leaf path through actual RET'},
            checked={'all_dword_arguments': True, 'all_initial_last_error_values': True,
                     'all_initial_gpr_and_flags': 'Except fixed observed RSP/thunk/frame/GS binding',
                     'native_sample': 'Every GPR, FLAGS, PC and complete decoded memory footprint agrees'})
        if not good:
            value = lambda v: hex(witness.eval(v, model_completion=True).as_long())
            return result | {'status': 'contract_mismatch', 'counterexample': {
                'entry_general': {n: value(v) for n, v in initial.items()},
                'entry_flags': value(initial_flags),
                'entry_last_error': value(word(initial_memory, teb + 0x68, 4))}}
        result['status'] = 'proved_for_observed_implementation'
        result['sha256'] = _digest(result)
        return result
    except (ValueError, TypeError, KeyError, IndexError, ImportError) as error:
        return result | {'reason': str(error)}
