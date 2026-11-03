"""Explicit Windows process-width facts shared by host debugger operations."""

REGISTERS64 = frozenset(('rax','rbx','rcx','rdx','rsi','rdi','rbp','rsp',
                        'r8','r9','r10','r11','r12','r13','r14','r15','rip','rflags'))
REGISTERS32 = frozenset(('eax','ebx','ecx','edx','esi','edi','ebp','esp','eip','eflags'))


def register_names(bits):
    if bits == 32:return REGISTERS32
    if bits == 64:return REGISTERS64
    raise ValueError('Windows PE contexts require an explicit 32-bit or 64-bit profile')


def context_bits(registers):
    if 'eip' in registers and 'rip' not in registers:return 32
    if 'rip' in registers and 'eip' not in registers:return 64
    raise ValueError('Windows context must expose one architecture-specific instruction pointer')


def ip_name(registers):return 'eip' if context_bits(registers) == 32 else 'rip'


def flags_name(registers):return 'eflags' if context_bits(registers) == 32 else 'rflags'


def instruction_pointer(registers):return registers[ip_name(registers)]


def validate_context(registers, bits):
    if not isinstance(registers,dict) or context_bits(registers) != bits:
        raise ValueError('Observed Windows thread context differs from the project architecture')
    names=register_names(bits);ip=ip_name(registers);flags=flags_name(registers)
    general=registers.get('general')
    if not isinstance(general,dict) or set(general) != names-{ip,flags}:
        raise ValueError('Incomplete or mixed-width Windows register context')
    for name in names:
        value=registers[name] if name in (ip,flags) else general[name]
        if not isinstance(value,str) or not value.startswith('0x'):
            raise ValueError('Windows register values require explicit hexadecimal strings')
        number=int(value,16)
        if not 0<=number<2**(32 if name==flags else bits):
            raise ValueError('Windows register value exceeds its declared architecture')
    return registers
