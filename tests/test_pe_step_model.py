"""A completed PE trace can check a narrow native instruction model."""
import pytest

from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
from fdisbull.pe_step_model import check_pe_step_model
from fdisbull.wine_arch import register_names


@pytest.mark.parametrize('bits,code,ip,flags,dst,src,base', [
    (64, '4889d8', 'rip', 'rflags', 'rax', 'rbx', 0x140001000),
    (32, '89d8', 'eip', 'eflags', 'eax', 'ebx', 0x401000),
])
def test_completed_pe_mov_model_checks_registers_and_flags(bits, code, ip, flags, dst, src, base):
    general = {name: '0x0' for name in register_names(bits) - {ip, flags}}

    def event(address, *, destination, flag_value='0x202'):
        regs = {'general': {**general, dst: hex(destination), src: '0x7'},
                ip: hex(address), flags: flag_value, 'thread': 17}
        return {'address': hex(address), 'project_address': hex(address),
                'bytes': code if address == base else '90', 'registers': regs}

    before = event(base, destination=0)
    after = event(base + len(bytes.fromhex(code)), destination=7)
    events = [before, after]
    normalize_trace('wine-qemu', events, version=1)
    trace = {'semantics': 'completed_steps', 'events': events}
    result = check_pe_step_model(trace, 0)
    assert result['status'] == 'agreement'
    assert result['observed_outputs'] == [dst, 'cf', 'pf', 'af', 'zf', 'sf', 'of']
    assert result['mismatched_outputs'] == []
    trace['semantics'] = PE_TRACE_SEMANTICS
    assert check_pe_step_model(trace, 0)['status'] == 'agreement'

    after['registers']['general'][dst] = '0x8'
    assert check_pe_step_model(trace, 0)['mismatched_outputs'] == [dst]
    after['registers']['general'][dst] = '0x7'
    after['registers'][flags] = '0x242'
    assert check_pe_step_model(trace, 0)['mismatched_outputs'] == ['zf']


def test_pe_model_refuses_unobserved_and_unsupported_steps():
    base = 0x140001000
    general = {name: '0x0' for name in register_names(64) - {'rip', 'rflags'}}
    def event(address, code):
        return {'address': hex(address), 'project_address': hex(address), 'bytes': code,
                'registers': {'rip': hex(address), 'rflags': '0x202',
                              'general': general.copy(), 'thread': 4}}
    events = [event(base, '4889d8'), event(base + 3, '90')]
    normalize_trace('wine-qemu', events, version=1)
    trace = {'semantics': 'completed_steps', 'events': events}
    assert check_pe_step_model(trace, 1)['status'] == 'unknown'
    events[0]['bytes'] = '8b00'  # Memory reads are outside this model.
    assert check_pe_step_model(trace, 0)['status'] == 'unsupported'
    events[0]['bytes'] = '4889d8'
    events[1]['registers']['thread'] = 5
    assert check_pe_step_model(trace, 0)['status'] == 'unknown'
    events[1]['registers']['thread'] = 4
    events[1]['address'] = hex(base + 0x40)
    events[1]['identity']['runtime_address'] = events[1]['address']
    events[1]['registers']['rip'] = events[1]['address']
    assert check_pe_step_model(trace, 0)['status'] == 'unknown'
    events[1]['address'] = hex(base + 3)
    events[1]['identity']['runtime_address'] = events[1]['address']
    events[1]['registers']['rip'] = events[1]['address']
    trace['semantics'] = 'pre_execution_fetch_last_pending'
    assert check_pe_step_model(trace, 0)['status'] == 'unknown'
    with pytest.raises(ValueError, match='index'):
        check_pe_step_model(trace, 2)


@pytest.mark.parametrize('starting_rax', [0xffffffffffffffff, 0x7fffffffffffffff])
def test_pe_add_step_model_agrees_with_independent_cpu_execution(starting_rax):
    unicorn = pytest.importorskip('unicorn')
    from unicorn import x86_const
    code = bytes.fromhex('4883c001')  # add rax, 1
    base = 0x140001000
    cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
    cpu.mem_map(base, 4096)
    cpu.mem_write(base, code)
    cpu.reg_write(x86_const.UC_X86_REG_RAX, starting_rax)
    cpu.reg_write(x86_const.UC_X86_REG_EFLAGS, 0x202)
    cpu.emu_start(base, base + len(code), count=1)
    initial = {name: '0x0' for name in register_names(64) - {'rip', 'rflags'}}
    before = {'address': hex(base), 'project_address': hex(base), 'bytes': code.hex(),
              'execution_bytes': code.hex(), 'ram_bytes': '4889d890',
              'registers': {'rip': hex(base), 'rflags': '0x202', 'thread': 17,
                            'general': {**initial, 'rax': hex(starting_rax)}}}
    after = {'address': hex(base + len(code)), 'project_address': hex(base + len(code)), 'bytes': '90',
             'registers': {'rip': hex(base + len(code)),
                           'rflags': hex(cpu.reg_read(x86_const.UC_X86_REG_EFLAGS)),
                           'thread': 17,
                           'general': {**initial, 'rax': hex(cpu.reg_read(x86_const.UC_X86_REG_RAX))}}}
    normalize_trace('wine-qemu', [before, after], version=1)
    result = check_pe_step_model({'semantics': 'completed_steps', 'events': [before, after]}, 0)
    assert result['status'] == 'agreement'
