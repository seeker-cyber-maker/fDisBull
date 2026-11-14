"""Independent CPU checks of the hash-bound Wine TLS leaf proof profile.

Instruction bytes were observed in the retained Ubuntu Wine 9.0 AMD64 runtime:
kernelbase GetLastError and ntdll RtlSetLastWin32Error. The DLLs themselves are
not fixtures; these tiny instruction sequences exercise the proof semantics.
"""
from copy import deepcopy
import hashlib
import time

import pytest

pytest.importorskip('z3')
pytest.importorskip('unicorn')

from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
from fdisbull.wine_api_contracts import validate_wine_api_contract
from fdisbull.wine_arch import register_names


ENTRY, BODY, SLOT, CALLER, STACK, TEB = 0x1000, 0x2000, 0x3000, 0x5000, 0x8008, 0x10000


def _observation(name='SetLastError', *, argument=0x1234, last_error=0x88776655,
                 wrong_argument=False):
    import unicorn
    from unicorn import x86_const as reg
    cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
    for address in (ENTRY, BODY, SLOT, CALLER, 0x8000, TEB):
        cpu.mem_map(address, 4096)
    prefix = bytes.fromhex('488da42400000000') if name == 'GetLastError' else b''
    thunk = prefix + b'\xff\x25' + (SLOT - ENTRY - len(prefix) - 6).to_bytes(4, 'little', signed=True)
    operation = '895068' if wrong_argument else '894868'
    leaf = bytes.fromhex('f30f1efa65488b042530000000' + ('8b4068' if name == 'GetLastError' else operation) + 'c3')
    cpu.mem_write(ENTRY, thunk)
    cpu.mem_write(BODY, leaf)
    cpu.mem_write(SLOT, BODY.to_bytes(8, 'little'))
    cpu.mem_write(CALLER, b'\x90')
    cpu.mem_write(STACK, CALLER.to_bytes(8, 'little'))
    cpu.mem_write(TEB + 0x30, TEB.to_bytes(8, 'little'))
    cpu.mem_write(TEB + 0x68, last_error.to_bytes(4, 'little'))
    cpu.reg_write(reg.UC_X86_REG_GS_BASE, TEB)
    for index, n in enumerate(sorted(register_names(64) - {'rip', 'rflags'})):
        cpu.reg_write(getattr(reg, 'UC_X86_REG_' + n.upper()), 0x11110000 + index)
    cpu.reg_write(reg.UC_X86_REG_RSP, STACK)
    cpu.reg_write(reg.UC_X86_REG_RCX, argument)
    cpu.reg_write(reg.UC_X86_REG_RDX, argument)  # Wrong-source mutation agrees on this sample.
    cpu.reg_write(reg.UC_X86_REG_EFLAGS, 0xad7)
    modules = [dict(name='kernel32.dll', base=hex(ENTRY), size=4096, generation=3, bits=64),
               dict(name='kernelbase.dll' if name == 'GetLastError' else 'ntdll.dll',
                    base=hex(BODY), size=4096, generation=4, bits=64)]
    rows = [{'address': hex(a), 'length': n} for a, n in
            ((SLOT, 8), (STACK, 8), (TEB + 0x30, 8), (TEB + 0x68, 4))]
    def snapshot():
        return [{'address': r['address'], 'hex': bytes(cpu.mem_read(int(r['address'], 16), r['length'])).hex()}
                for r in rows]
    initial = snapshot()
    events, code_reads, accesses, pending = [], [], [], []
    def complete_writes():
        for row in pending:
            row['after_hex'] = bytes(cpu.mem_read(int(row['address'], 16), row['width'])).hex()
        pending.clear()
    def hook(guest, address, size, _):
        complete_writes()
        events.append({'address': hex(address), 'project_address': hex(CALLER) if address == CALLER else None,
            'bytes': bytes(guest.mem_read(address, size)).hex(),
            'registers': {'rip': hex(address), 'rflags': hex(guest.reg_read(reg.UC_X86_REG_EFLAGS)),
                'thread': 17, 'general': {n: hex(guest.reg_read(getattr(reg, 'UC_X86_REG_' + n.upper())))
                                       for n in register_names(64) - {'rip', 'rflags'}}}})
        if address != CALLER:
            raw = bytes(guest.mem_read(address, 15))
            owner = next(m for m in modules if int(m['base'], 16) <= address < int(m['base'], 16) + m['size'])
            code_reads.append({'event_index': len(events) - 1, 'address': hex(address), 'hex': raw.hex(),
                               'sha256': hashlib.sha256(raw).hexdigest(), 'module': deepcopy(owner)})
    def memory(guest, kind, address, width, value, _):
        row = {'event_index': len(events) - 1, 'kind': 'write' if kind == unicorn.UC_MEM_WRITE else 'read',
               'address': hex(address), 'width': width,
               'before_hex': bytes(guest.mem_read(address, width)).hex()}
        row['after_hex'] = row['before_hex']
        accesses.append(row)
        if kind == unicorn.UC_MEM_WRITE:
            pending.append(row)
    cpu.hook_add(unicorn.UC_HOOK_CODE, hook)
    cpu.hook_add(unicorn.UC_HOOK_MEM_READ | unicorn.UC_HOOK_MEM_WRITE, memory)
    cpu.emu_start(ENTRY, CALLER + 1, count=32)
    complete_writes()
    assert events[-1]['address'] == hex(CALLER)
    normalize_trace('wine-qemu', events, version=1)
    events[-1]['observation']['instruction_completed'] = False
    final = snapshot()
    actual_error = int.from_bytes(bytes(cpu.mem_read(TEB + 0x68, 4)), 'little')
    assert actual_error == (last_error if name == 'GetLastError' else argument & 0xffffffff)
    assert int(events[-1]['registers']['general']['rax'], 16) == (last_error if name == 'GetLastError' else TEB)
    return {'format': 'fdisbull-wine-import-call-1', 'status': 'complete',
        'identity': {'run': 'independent-unicorn-implementation', 'source_version': 1,
                     'source_sha256': 'a' * 64, 'version_sha256': 'b' * 64},
        'import': {'name': name, 'target': hex(ENTRY), 'return_address': hex(CALLER)},
        'resolution': {'target': hex(ENTRY)}, 'modules_before': {'modules': modules},
        'contexts': {'entry': events[0]['registers'], 'return': events[-1]['registers']},
        'implementation': {'format': 'fdisbull-wine-api-implementation-1', 'status': 'complete',
            'bits': 64, 'semantics': PE_TRACE_SEMANTICS,
            'thread_info': {'thread': 17, 'bits': 64, 'teb': hex(TEB),
                'teb_source': 'CREATE_PROCESS_DEBUG_EVENT.lpThreadLocalBase', 'gs_base_register_observed': False},
            'segment_binding': {'segment': 'gs', 'offset': '0x30', 'teb': hex(TEB), 'gs_base_register_observed': False},
            'events': events, 'memory': {'entry': initial, 'exit': final},
            'code_reads': code_reads, 'accesses': accesses}}


@pytest.mark.parametrize('name', ['SetLastError', 'GetLastError'])
@pytest.mark.parametrize('argument,prior', [(0, 0xffffffff), (1, 0), (0xffffffff, 1),
                                             (0x11223344aabbccdd, 0x87654321)])
def test_actual_leaf_profile_proves_every_dword_and_exact_sample(name, argument, prior):
    observation = _observation(name, argument=argument, last_error=prior)
    frozen = deepcopy(observation)
    proof = validate_wine_api_contract(observation)
    assert proof['status'] == 'proved_for_observed_implementation', proof
    assert proof['checked']['all_dword_arguments'] and proof['checked']['all_initial_last_error_values']
    assert proof['precise_effects']['flags'] == 'unchanged'
    assert proof['precise_effects']['rsp'] == 'entry_rsp + 8'
    assert len(proof['precise_effects']['memory_writes']) == (1 if name == 'SetLastError' else 0)
    assert proof['segment_binding']['gs_base_register_observed'] is False
    assert proof['sha256']
    assert observation == frozen


def test_wrong_argument_register_agrees_on_sample_but_fails_universal_property():
    observation = _observation(wrong_argument=True)
    proof = validate_wine_api_contract(observation)
    assert proof['status'] == 'contract_mismatch', proof
    witness = proof['counterexample']['entry_general']
    assert int(witness['rcx'], 16) & 0xffffffff != int(witness['rdx'], 16) & 0xffffffff


@pytest.mark.parametrize('change', ['code_hash', 'project_address', 'module_owner', 'missing_ret',
                                     'missing_access', 'wrong_access', 'flags', 'nonvolatile', 'teb_self'])
def test_incomplete_or_forged_implementation_evidence_stays_unknown(change):
    observation = _observation()
    body = observation['implementation']
    if change == 'code_hash':
        body['code_reads'][0]['sha256'] = '0' * 64
    elif change == 'project_address':
        body['events'][0]['project_address'] = hex(ENTRY)
        body['events'][0]['identity']['project_address'] = hex(ENTRY)
    elif change == 'module_owner':
        body['code_reads'][0]['module']['generation'] += 1
    elif change == 'missing_ret':
        body['events'].pop(-2)
        body['code_reads'].pop()
    elif change == 'missing_access':
        body['accesses'].pop()
    elif change == 'wrong_access':
        body['accesses'][0]['address'] = hex(SLOT + 1)
    elif change == 'flags':
        body['events'][2]['registers']['rflags'] = '0x202'
    elif change == 'nonvolatile':
        body['events'][2]['registers']['general']['rbx'] = '0x123'
    elif change == 'teb_self':
        row = next(r for r in body['memory']['entry'] if r['address'] == hex(TEB + 0x30))
        row['hex'] = '00' * 8
    proof = validate_wine_api_contract(observation)
    assert proof['status'] == 'unknown', proof


def test_exitprocess_and_unobserved_gs_measurement_are_not_upgraded_to_proofs():
    observation = _observation()
    observation['import']['name'] = 'ExitProcess'
    assert validate_wine_api_contract(observation)['status'] == 'unknown'
    observation = _observation()
    observation['implementation']['thread_info']['gs_base_register_observed'] = True
    assert validate_wine_api_contract(observation)['status'] == 'unknown'


def test_segment_override_cannot_be_treated_as_a_flat_teb_write():
    observation = _observation(argument=0x1234, last_error=0x1234)
    body = observation['implementation']
    # A coincidentally unchanged slot would hide a wrong-address store in the
    # boundary sample. Prefixing GS must therefore reject the flat-store rule.
    index = next(i for i, e in enumerate(body['events']) if e['bytes'] == '894868')
    event = body['events'][index]
    event['bytes'] = event['execution_bytes'] = '65894868'
    read = body['code_reads'][index]
    raw = b'\x65' + bytes.fromhex(read['hex'])
    read['hex'], read['sha256'] = raw.hex(), hashlib.sha256(raw).hexdigest()
    # Keep the four-byte prefixed instruction and following RET coherent.
    following = body['events'][index + 1]
    shifted = hex(int(following['address'], 16) + 1)
    following['address'] = following['registers']['rip'] = shifted
    following['identity']['runtime_address'] = shifted
    body['code_reads'][index + 1]['address'] = shifted
    proof = validate_wine_api_contract(observation)
    assert proof['status'] == 'unknown', proof
    assert 'profile' in proof['reason']


class _ImplementationPeer:
    """Finite native-RPC collaborator using independent CPU evidence above."""
    def __init__(self, observation):
        self.observation = observation
        self.original = deepcopy(observation['implementation'])
        self.version, self.position, self.steps = {'id': 1}, 0, 0
        self.memory = {}
        for row in self.original['memory']['entry'] + self.original['code_reads']:
            self.memory.update({int(row['address'], 16) + k: b for k, b in enumerate(bytes.fromhex(row['hex']))})
        self.memory.update({CALLER + k: b for k, b in enumerate(b'\x90' + bytes(14))})

    def project_address(self, address):
        return hex(CALLER) if address == CALLER else None

    def registers(self):
        return deepcopy(self.original['events'][self.position]['registers'])

    def read(self, address, length):
        return bytes(self.memory[address + k] for k in range(length))

    def call(self, method):
        assert method == 'thread-info'
        return deepcopy(self.original['thread_info'])

    def _step_instruction(self, deadline):
        assert deadline > time.monotonic()
        event = deepcopy(self.original['events'][self.position])
        event['active_layers'] = []
        event.pop('identity')
        event.pop('observation')
        for row in self.original['accesses']:
            if row['event_index'] == self.position and row['kind'] == 'write':
                self.memory.update({int(row['address'], 16) + k: b
                                    for k, b in enumerate(bytes.fromhex(row['after_hex']))})
        self.steps += 1
        self.position += 1
        return event, {'stop_reason': {'kind': 'step'}}


@pytest.mark.parametrize('name', ['SetLastError', 'GetLastError'])
def test_collector_retains_each_native_step_and_exact_memory_footprint(name):
    from fdisbull.wine_import_calls import _trace_implementation
    observation = _observation(name)
    peer = _ImplementationPeer(observation)
    expected_steps = len(observation['implementation']['events']) - 1
    observation.pop('implementation')
    _trace_implementation(peer, observation, deadline=time.monotonic() + 5,
        call=peer.call, read=peer.read, registers=peer.registers)
    assert peer.steps == expected_steps
    proof = validate_wine_api_contract(observation)
    assert proof['status'] == 'proved_for_observed_implementation', proof
    assert all(e['project_address'] is None for e in observation['implementation']['events'][:-1])
    assert observation['implementation']['events'][-1]['observation']['instruction_completed'] is False


def test_collector_refuses_unknown_code_before_execution_and_preserves_the_read():
    from fdisbull.wine_import_calls import _trace_implementation
    observation = _observation()
    peer = _ImplementationPeer(observation)
    peer.memory[ENTRY], peer.memory[ENTRY + 1] = 0x0f, 0x0b  # UD2
    observation.pop('implementation')
    with pytest.raises(ValueError, match='before native execution'):
        _trace_implementation(peer, observation, deadline=time.monotonic() + 5,
            call=peer.call, read=peer.read, registers=peer.registers)
    assert peer.steps == 0
    assert observation['implementation']['status'] == 'partial'
    assert observation['implementation']['code_reads'][0]['hex'].startswith('0f0b')
