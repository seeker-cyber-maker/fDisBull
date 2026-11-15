"""Independent CPU evidence for the authored DLL's typed symbolic contracts.

These homegrown byte programs mirror self_modifying_init_dll_wine.S. Native
Wine observations are verified separately; no loader is simulated as proven.
"""
from copy import deepcopy
import hashlib
import struct

import pytest

pytest.importorskip('z3')
pytest.importorskip('unicorn')

from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
from fdisbull.pe_dll_contracts import expand_dll_callback_contract, validate_dll_callback
from fdisbull.wine_arch import register_names


BASE, CODE, DATA, STACK, CALLER = 0x180000000, 0x180004000, 0x180002000, 0x8008, 0x70000000
PHASES = ('tls-attach', 'dll-attach', 'report', 'tls-detach', 'dll-detach')


def _program(*, tls_marker=0x11, tls_constant=2, tls_detach_bit=1):
    code, labels, fixes = bytearray(), {}, []
    names = ('dll_event_count', 'dll_stage', 'dll_seen_stage', 'dll_detach_flag',
             'dll_report_stage_seen', 'dll_report_count_seen', 'dll_tls_detach_stage_seen',
             'dll_dllmain_detach_stage_seen')
    symbols = {n: DATA + 4 * i for i, n in enumerate(names)}
    symbols.update(dll_data_start=DATA, dll_data_end=DATA + 64, dll_event_log=DATA + 32)
    def mark(n):
        labels[n] = len(code)
    def emit(h):
        code.extend(bytes.fromhex(h))
    def relative(op, target, tail=b'', width=4):
        emit(op)
        fixes.append((len(code), target, width, len(tail)))
        code.extend(bytes(width))
        code.extend(tail)
    def append(marker):
        relative('8b05', 'dll_event_count')
        relative('4c8d0d', 'dll_event_log')
        emit('41c70481')
        code.extend(marker.to_bytes(4, 'little'))
        emit('83c001')
        relative('8905', 'dll_event_count')
    def store(field, value):
        relative('c705', field, value.to_bytes(4, 'little'))
    mark('dll_code_start')
    mark('dll_tls_callback')
    emit('83fa01')
    relative('74', 'tls_attach', width=1)
    emit('85d2')
    relative('74', 'tls_detach', width=1)
    emit('c3')
    mark('tls_attach')
    append(tls_marker)
    store('dll_stage', 1)
    relative('c605', 'dll_report_constant_immediate', bytes([tls_constant]))
    emit('90c3')
    mark('tls_detach')
    relative('8b05', 'dll_stage')
    relative('8905', 'dll_tls_detach_stage_seen')
    append(0x44)
    relative('830d', 'dll_detach_flag', bytes([tls_detach_bit]))
    emit('90c3')
    mark('dll_entry')
    emit('83fa01')
    relative('74', 'dll_attach', width=1)
    emit('85d2')
    relative('74', 'dll_detach', width=1)
    emit('b801000000c3')
    mark('dll_attach')
    relative('8b05', 'dll_stage')
    relative('8905', 'dll_seen_stage')
    append(0x22)
    store('dll_stage', 2)
    relative('c605', 'dll_report_constant_immediate', b'\x03')
    emit('90b801000000c3')
    mark('dll_detach')
    relative('8b05', 'dll_stage')
    relative('8905', 'dll_dllmain_detach_stage_seen')
    append(0x55)
    relative('830d', 'dll_detach_flag', b'\x02')
    emit('90b801000000c3')
    mark('dll_report')
    relative('8b05', 'dll_stage')
    relative('8905', 'dll_report_stage_seen')
    relative('8b05', 'dll_event_count')
    relative('8905', 'dll_report_count_seen')
    append(0x33)
    store('dll_stage', 3)
    emit('b8')
    mark('dll_report_constant_immediate')
    emit('01000000c3')
    mark('dll_code_end')
    symbols.update({n: CODE + v for n, v in labels.items()})
    for position, target, width, tail in fixes:
        code[position:position + width] = (symbols[target] - CODE - position - width - tail).to_bytes(width, 'little', signed=True)
    return bytes(code), symbols


def _path(phase, *, data=None, code=None, seed=0x11110000, variant=None):
    import unicorn
    from unicorn import x86_const as reg
    original, symbols = _program(**(variant or {}))
    code = original if code is None else code
    data = bytes(64) if data is None else data
    cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
    for page in (CODE, DATA, 0x8000, CALLER):
        cpu.mem_map(page, 4096)
    cpu.mem_write(CODE, code)
    cpu.mem_write(DATA, data)
    cpu.mem_write(STACK, CALLER.to_bytes(8, 'little'))
    cpu.mem_write(CALLER, b'\x90')
    for i, name in enumerate(sorted(register_names(64) - {'rip', 'rflags'})):
        cpu.reg_write(getattr(reg, 'UC_X86_REG_' + name.upper()), seed + i)
    reason = None if phase == 'report' else 1 if phase.endswith('attach') else 0
    if reason is not None:
        cpu.reg_write(reg.UC_X86_REG_RDX, 0xaabbccdd00000000 | reason)
    cpu.reg_write(reg.UC_X86_REG_RSP, STACK)
    cpu.reg_write(reg.UC_X86_REG_EFLAGS, 0x202)
    target = symbols['dll_report' if phase == 'report' else 'dll_tls_callback' if phase.startswith('tls-') else 'dll_entry']
    def context():
        return {'rip': hex(cpu.reg_read(reg.UC_X86_REG_RIP)), 'rflags': hex(cpu.reg_read(reg.UC_X86_REG_EFLAGS)),
            'thread': 17, 'general': {n: hex(cpu.reg_read(getattr(reg, 'UC_X86_REG_' + n.upper())))
                                    for n in register_names(64) - {'rip', 'rflags'}}}
    def memory():
        return [{'address': hex(a), 'hex': bytes(cpu.mem_read(a, n)).hex()}
                for a, n in ((CODE, len(code)), (DATA, 64), (STACK, 8))]
    steps = []
    def hook(guest, address, size, _):
        current, snapshot = context(), memory()
        if steps:
            steps[-1].update(after=current, memory_after=snapshot)
        if address == CALLER:
            guest.emu_stop()
            return
        event = {'address': hex(address), 'project_address': None, 'registers': current,
                 'bytes': bytes(guest.mem_read(address, size)).hex(), 'active_layers': []}
        event['ram_bytes'] = event['execution_bytes'] = event['bytes']
        normalize_trace('wine-qemu', [event], version=1)
        steps.append({'event': event, 'memory_before': snapshot})
    cpu.hook_add(unicorn.UC_HOOK_CODE, hook)
    cpu.emu_start(target, CALLER + 1, count=128)
    assert steps[-1]['event']['bytes'] == 'c3'
    source = hashlib.sha256(original + bytes(64)).hexdigest()
    module = {'name': 'authored.dll', 'base': hex(BASE), 'size': 0x7000, 'bits': 64, 'generation': 5}
    observation = {'format': 'fdisbull-native-dll-callback-1', 'status': 'complete', 'run': 'independent-unicorn',
        'controller_source_sha256': 'a' * 64, 'subject_source_sha256': source, 'subject_module': module,
        'entry': steps[0]['event']['registers'], 'exit': steps[-1]['after'], 'return_address': hex(CALLER),
        'steps': steps, 'semantics': PE_TRACE_SEMANTICS}
    contract = {'phase': phase, 'source_sha256': source, 'module': module, 'symbols': symbols,
        'entry_memory': [{'address': hex(DATA), 'hex': data.hex()},
                         {'address': hex(STACK), 'hex': CALLER.to_bytes(8, 'little').hex()}],
        'entry_code': {'address': hex(CODE), 'hex': code.hex(), 'sha256': hashlib.sha256(code).hexdigest()},
        'entry_rsp': hex(STACK), 'return_address': hex(CALLER), 'reason': reason}
    return observation, contract


def test_full_lifecycle_formal_transfers_compose_known_source_progression():
    data, code, proofs = bytes(64), None, []
    for phase in PHASES:
        observation, contract = _path(phase, data=data, code=code)
        frozen = deepcopy((observation, contract))
        proof = validate_dll_callback(observation, contract=contract)
        assert proof['status'] == 'proved_for_authored_dll_callback', proof
        assert proof['generic_constraints']['event_count_unsigned_range'] == [0, 7]
        assert proof['transfer']['termination_bound_instructions'] == len(observation['steps'])
        assert proof['checks']['source_effect_difference'] == 'unsat'
        assert expand_dll_callback_contract(proof, observation, contract) == {'observation': observation, 'contract': contract}
        assert (observation, contract) == frozen
        data = bytes.fromhex(next(r['hex'] for r in proof['post_memory'] if r['address'] == hex(DATA)))
        code = bytes.fromhex(proof['post_code']['hex'])
        proofs.append(proof)
    words = struct.unpack('<16I', data)
    assert words == (5, 3, 1, 3, 2, 2, 3, 3, 0x11, 0x22, 0x33, 0x44, 0x55, 0, 0, 0)
    assert [len(p['code_versions']) for p in proofs] == [2, 2, 1, 1, 1]
    assert [p['transfer']['defined_flags_mask'] for p in proofs] == [0xffffffff] * 3 + [0xffffffef] * 2


@pytest.mark.parametrize('phase', PHASES)
def test_generic_proof_accepts_last_log_slot_arbitrary_globals_and_gprs(phase):
    words = [0xfedc0000 + i for i in range(16)]
    words[0], words[1], words[3] = 7, 0x87654321, 0xf001ff00
    observation, contract = _path(phase, data=struct.pack('<16I', *words), seed=0x2233445500000000)
    proof = validate_dll_callback(observation, contract=contract)
    assert proof['status'] == 'proved_for_authored_dll_callback', proof
    assert 'dll_entry_rcx' in proof['symbols']
    assert proof['source']['dll_source_sha256'] != proof['source']['controller_source_sha256']


@pytest.mark.parametrize('variant,phase', [({'tls_marker': 0x12}, 'tls-attach'),
                                           ({'tls_constant': 3}, 'tls-attach'),
                                           ({'tls_detach_bit': 2}, 'tls-detach')])
def test_executed_instruction_mutation_can_match_replay_but_fail_source_contract(variant, phase):
    observation, contract = _path(phase, variant=variant)
    proof = validate_dll_callback(observation, contract=contract)
    assert proof['status'] == 'contract_mismatch', proof
    assert proof['counterexample']


@pytest.mark.parametrize('problem', ['reason', 'count_overflow', 'missing_step', 'memory', 'code_fetch',
                                      'flags', 'architectural_flags', 'analysis_version', 'foreign_address', 'source_identity', 'generation'])
def test_unadmitted_or_forged_native_evidence_stays_unknown(problem):
    data = struct.pack('<I', 8) + bytes(60) if problem == 'count_overflow' else None
    observation, contract = _path('tls-attach', data=data)
    if problem == 'reason':
        contract['reason'] = 0
    elif problem == 'missing_step':
        observation['steps'].pop(5)
    elif problem == 'memory':
        observation['steps'][4]['memory_after'][1]['hex'] = 'ff' + observation['steps'][4]['memory_after'][1]['hex'][2:]
    elif problem == 'code_fetch':
        observation['steps'][0]['event']['execution_bytes'] = '83fa02'
    elif problem == 'flags':
        observation['steps'][0]['after']['rflags'] = '0x202'
    elif problem == 'architectural_flags':
        observation['entry']['rflags'] = '0x200'
    elif problem == 'analysis_version':
        for step in observation['steps']:
            step['event']['identity']['source_version'] = 0
    elif problem == 'foreign_address':
        observation['steps'][0]['event']['project_address'] = hex(CODE)
    elif problem == 'source_identity':
        contract['source_sha256'] = observation['controller_source_sha256']
    elif problem == 'generation':
        contract = deepcopy(contract)
        contract['module']['generation'] += 1
    proof = validate_dll_callback(observation, contract=contract)
    assert proof['status'] == 'unknown', proof


def test_expansion_requires_exact_original_observation_and_predecessor():
    observation, contract = _path('tls-attach')
    proof = validate_dll_callback(observation, contract=contract)
    assert proof['status'] == 'proved_for_authored_dll_callback', proof
    changed = deepcopy(contract)
    changed['entry_rsp'] = hex(STACK + 8)
    with pytest.raises(ValueError, match='exact original'):
        expand_dll_callback_contract(proof, observation, changed)
