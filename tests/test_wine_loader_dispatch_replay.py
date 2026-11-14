"""Independent CPU replay of the complete observed Wine dispatch capsule.

This is a concrete check against native inputs, separate from symbolic proof.
The native FP save values seed the opaque initial FP registers; replay does not
claim that the debugger measured that hidden context at entry.
"""


def replay_wine_loader_capsule(capsule, *, opaque_save_registers=None):
    """Replay all instructions; optionally restrict opaque initial FP saves.

    A computed vector excluded from the allowlist is never seeded from its
    eventual store. Its producing instructions must establish the value.
    """
    import capstone
    import unicorn
    from unicorn import x86_const as reg

    assert capsule['status'] == 'complete' and capsule['summaries'] == []
    cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    pages = set()
    for row in capsule['entry_memory']:
        address, length = int(row['address'], 16), len(bytes.fromhex(row['hex']))
        pages.update(range(address & ~4095, (address + length + 4095) & ~4095, 4096))
    for step in capsule['steps']:
        address = int(step['code_read']['address'], 16)
        pages.update(range(address & ~4095, (address + 15 + 4095) & ~4095, 4096))
    pages.add(int(capsule['exit']['rip'], 16) & ~4095)
    for page in pages:
        cpu.mem_map(page, 4096)
    for row in capsule['entry_memory']:
        cpu.mem_write(int(row['address'], 16), bytes.fromhex(row['hex']))
    # Source callback bytes are mutable. Loader code is immutable for this
    # invocation and comes from its actual retained native reads.
    subject = capsule['subject_module']
    sb = int(subject['base'], 16)
    for step in capsule['steps']:
        address = int(step['code_read']['address'], 16)
        if not sb <= address < sb + subject['size']:
            cpu.mem_write(address, bytes.fromhex(step['code_read']['hex']))
    entry = capsule['entry']
    for name, value in entry['general'].items():
        cpu.reg_write(getattr(reg, 'UC_X86_REG_' + name.upper()), int(value, 16))
    cpu.reg_write(reg.UC_X86_REG_EFLAGS, int(entry['rflags'], 16))
    cpu.reg_write(reg.UC_X86_REG_GS_BASE, int(capsule['thread_info']['teb'], 16))
    opaque = {}
    for step in capsule['steps']:
        event = step['event']
        ins = next(decoder.disasm(bytes.fromhex(event['bytes']), int(event['address'], 16)))
        if ins.mnemonic in ('stmxcsr', 'fnstcw', 'movdqa', 'movups', 'movaps'):
            writes = [a for a in step['accesses'] if a['kind'] == 'write']
            assert len(writes) == 1
            value = int.from_bytes(bytes.fromhex(writes[0]['after_hex']), 'little')
            name = ('MXCSR' if ins.mnemonic == 'stmxcsr' else 'FPCW'
                    if ins.mnemonic == 'fnstcw' else ins.reg_name(ins.operands[1].reg).upper())
            if opaque_save_registers is None or name in opaque_save_registers:
                assert name not in opaque or opaque[name] == value, 'Hidden FP input changes inside the captured path'
                opaque[name] = value
    for name, value in opaque.items():
        cpu.reg_write(getattr(reg, 'UC_X86_REG_' + name), value)

    accesses = []
    def access(guest, kind, address, width, value, user):
        accesses.append(('write' if kind == unicorn.UC_MEM_WRITE else 'read', address, width))
    cpu.hook_add(unicorn.UC_HOOK_MEM_READ | unicorn.UC_HOOK_MEM_WRITE, access)
    mask = 0xffffffff
    for index, step in enumerate(capsule['steps']):
        event, after = step['event'], step['after']
        address = int(event['address'], 16)
        raw = bytes.fromhex(event['bytes'])
        assert bytes(cpu.mem_read(address, len(raw))) == raw, (index, 'instruction fetch')
        ins = next(decoder.disasm(raw, address))
        accesses.clear()
        cpu.emu_start(address, 0, count=1)
        expected = [(a['kind'], int(a['address'], 16), a['width']) for a in step['accesses']]
        # Unicorn lowers one 16-byte SIMD store to two adjacent 8-byte hooks.
        # Compare ordered byte footprints, retaining read/write distinctions.
        footprint = lambda rows: [(kind, address + offset) for kind, address, width in rows
                                  for offset in range(width)]
        assert footprint(accesses) == footprint(expected), (index, ins.mnemonic, accesses, expected)
        assert cpu.reg_read(reg.UC_X86_REG_RIP) == int(after['rip'], 16), index
        for name, value in after['general'].items():
            assert cpu.reg_read(getattr(reg, 'UC_X86_REG_' + name.upper())) == int(value, 16), (index, name)
        if ins.mnemonic in ('and', 'or', 'xor', 'test'):
            mask &= ~0x10
        elif ins.mnemonic in ('add', 'sub', 'cmp'):
            mask = 0xffffffff
        assert (cpu.reg_read(reg.UC_X86_REG_EFLAGS) ^ int(after['rflags'], 16)) & mask == 0, index
        for row in step['accesses']:
            address = int(row['address'], 16)
            assert bytes(cpu.mem_read(address, row['width'])) == bytes.fromhex(row['after_hex']), index
        for row in step['protected_after']:
            raw = bytes.fromhex(row['hex'])
            assert bytes(cpu.mem_read(int(row['address'], 16), len(raw))) == raw, (index, 'protected memory')
    for row in capsule['exit_memory']:
        raw = bytes.fromhex(row['hex'])
        assert bytes(cpu.mem_read(int(row['address'], 16), len(raw))) == raw
    return {'status': 'native_dispatch_capsule_replayed', 'instructions': len(capsule['steps']),
            'registers': 'all captured GPRs and RIP', 'flags': 'all captured defined FLAGS bits',
            'memory': 'every classified access, all per-step protected bytes and complete exit union',
            'fp_context': 'opaque initial values instantiated from actual save stores',
            'scope': 'Concrete observed invocation with explicit GS binding; no universal loader proof'}
