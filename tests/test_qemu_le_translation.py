import pytest

from fdisbull.qemu_le_translation import parse_hmp, translate_linear, observe_descriptor


HMP = '''CR0=80000001 CR2=00000000 CR3=00001000 CR4=00000000
EFER=0000000000000000
GDT=     00004000 000000ff
LDT=0028 00005000 000000ff 00008200 DPL=0 LDT
'''


def test_native_monitor_line_endings():
    assert parse_hmp(HMP.replace('\n', '\r\n')) == parse_hmp(HMP)


def test_nonidentity_cross_page_and_offline_replay():
    context = parse_hmp(HMP)
    memory = bytearray(0x10000)
    memory[0x1004:0x1008] = (0x2003).to_bytes(4, 'little')
    memory[0x2ffc:0x3000] = (0x7003).to_bytes(4, 'little')
    memory[0x3000:0x3004] = (0x9003).to_bytes(4, 'little')
    # The second page is in a different page table.
    memory[0x1008:0x100c] = (0x3003).to_bytes(4, 'little')
    memory[0x7ffe:0x8000] = b'ab'
    memory[0x9000:0x9002] = b'cd'
    reads = {}
    def physical(a, n):
        data = bytes(memory[a:a+n]); reads[a, n] = data
        return data
    data, walks = translate_linear(context, 0x7ffffe, 4, physical, lambda a, n: b'abcd'[a-0x7ffffe:a-0x7ffffe+n])
    assert data == b'abcd'
    assert [w['physical'] for w in walks] == [0x7ffe, 0x9000]
    assert walks[0]['pde_address'] == 0x1004 and walks[1]['pte_address'] == 0x3000
    replay, replay_walks = translate_linear(context, 0x7ffffe, 4, lambda a, n: reads[a, n])
    assert (replay, replay_walks) == (data, walks)
    with pytest.raises(ValueError, match='differ'):
        translate_linear(context, 0x7ffffe, 4, physical, lambda a, n: b'X' * n)


def test_descriptor_tables_and_cached_ldtr():
    context = parse_hmp(HMP)
    mem = bytearray(0x6000)
    mem[0x4008:0x4010] = bytes.fromhex('ffff3412789acf56')
    mem[0x5000:0x5008] = bytes.fromhex('ffff3412789acf56')
    mem[0x4028:0x4030] = bytes.fromhex('ff00005000820000')
    read = lambda a, n: bytes(mem[a:a+n])
    gdt = observe_descriptor(context, 8, read)
    ldt = observe_descriptor(context, 4, read)
    assert gdt['table'] == 'gdt' and ldt['table'] == 'ldt'
    assert gdt['descriptor']['base'] == 0x56781234
    assert gdt['descriptor']['limit'] == 0xffffffff
    assert ldt['descriptor']['raw'] == 'ffff3412789acf56'
    assert ldt['ldtr_parent']['descriptor']['base'] == 0x5000
    mem[0x402a] = 0x51
    with pytest.raises(ValueError, match='differs from GDT'):
        observe_descriptor(context, 4, read)
    mem[0x402a] = 0x50
    context['ldtr']['selector'] = 0
    with pytest.raises(ValueError, match='LDTR'):
        observe_descriptor(context, 4, read)
    context['ldtr']['selector'] = 0x28
    context['ldtr']['attributes'] = 0
    with pytest.raises(ValueError, match='LDTR'):
        observe_descriptor(context, 4, read)


@pytest.mark.parametrize('replace, message', [
    (('CR4=00000000', 'CR4=00000020'), 'PAE'),
    (('CR0=80000001', 'CR0=00000000'), 'protected'),
    (('CR3=00001000', 'CR3=00001001'), 'CR3'),
])
def test_unsupported_modes_fail_closed(replace, message):
    with pytest.raises(ValueError, match=message):
        translate_linear(parse_hmp(HMP.replace(*replace)), 0, 1, lambda a, n: bytes(n))


def test_absent_and_large_pages_fail_closed():
    context = parse_hmp(HMP)
    for pde, message in [(0, 'not present'), (0x2083, 'Large')]:
        with pytest.raises(ValueError, match=message):
            translate_linear(context, 0, 1, lambda a, n: pde.to_bytes(4, 'little'))


def test_incomplete_or_ambiguous_hmp_fails():
    with pytest.raises(ValueError):
        parse_hmp(HMP + 'CR3=00001000\n')
    with pytest.raises(ValueError):
        parse_hmp(HMP.replace('LDT=', 'BAD='))


def test_unpaged_protected_identity_and_native_null_ldtr():
    context = parse_hmp(HMP.replace('CR0=80000001', 'CR0=00000001').replace(
        'LDT=0028 00005000 000000ff 00008200 DPL=0 LDT',
        'LDT=0000 00000000 0000ffff 00008200 DPL=0 LDT'))
    data, walks = translate_linear(context, 0xfff, 2, lambda a, n: b'x' * n, lambda a, n: b'x' * n)
    assert data == b'xx'
    assert walks == [dict(linear=0xfff, length=1, physical=0xfff, paging=False),
                     dict(linear=0x1000, length=1, physical=0x1000, paging=False)]
    with pytest.raises(ValueError, match='LDTR'):
        observe_descriptor(context, 4, lambda a, n: bytes(n))
