"""A tiny authored DOS loader for an explicit MZ/BW/MZ/LE carrier.

DOS executes the outer stub. It opens its own pathname from the standard DOS
PSP environment trailer and reads the complete carrier through INT21h. Its
actual protected-mode loader copies and relocates the two declared LE objects;
no host-side register or memory writes prepare the protected program.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct

from fdisbull.dos import load_mz
from fdisbull.le import load_runtime_le_carrier
from support.dos_process_fixture import assemble

CODE_BASE = 0x120000
DATA_BASE = 0x130000
OUTSIDE_BASE = 0x140000
COUNTER_OFFSET = 128
BUFFER_OFFSET = 0x1000

# The paged variants map the same guest linear code onto noncontiguous RAM.
PAGED_CODE_PHYSICAL = (0x200000, 0x205000, 0x20a000)
PAGED_DATA_PHYSICAL = 0x210000
PAGED_ENTRY_OFFSET = 4094
PAGED_LDT_CODE_SELECTOR = 0x0c  # LDT index 1, ring 0; GDT CS is 0x08.
PAGED_TRACKING_SELECTOR_B = 0x1c  # LDT index 3, ring 0.
PAGED_TRACKING_CONTROLLER = 0x2100
PAGED_TRACKING_TARGET = 0x1400
PAGED_TRACKING_PHYSICAL = 0x215000
PAGED_TRACKING_SIGNATURE_SIZE = 128


def build_fixture(directory, nasm):
    """Write authored source/listings and return the actual executable layout."""
    from test_le_loader import le_file
    from test_le_runtime_carrier import bound_le

    directory = Path(directory)
    # Eight distinct offset32 sites establish the initialized data placement.
    # The ninth site is an executed absolute store to a separate mutable cell.
    prefix = b''.join(b'\xb8'+bytes(4)+b'\x90'*3 for _ in range(8))
    body = bytes.fromhex('31c0 40 a300000000 83f803 75f5 ba') + struct.pack('<I', OUTSIDE_BASE) + b'\xff\xe2'
    code = prefix + body + bytes((i*73+19) % 256 for i in range(160))
    data = bytearray((i*37+11) % 256 for i in range(256))
    data[COUNTER_OFFSET:COUNTER_OFFSET+4] = bytes(4)
    sites = [(i*8+1, i) for i in range(8)] + [(68, COUNTER_OFFSET)]
    fixups = b''.join(struct.pack('<BBhBH', 7, 0, site, 2, target) for site, target in sites)
    carrier = bytearray(bound_le(le_file(code=code, data=bytes(data), fixups=[fixups, b''],
        object_sizes=(len(code), len(data)), object_bases=(0x10000, 0x20000))))
    parsed = load_runtime_le_carrier(bytes(carrier))
    fragments = parsed.metadata['file_mappings']
    code_file = next(row['file_offset'] for row in fragments if row['virtual_address']==0x10000)
    data_file = next(row['file_offset'] for row in fragments if row['virtual_address']==0x20000)
    patches = '\n'.join(f'    mov dword [{CODE_BASE+site:#x}],{DATA_BASE+target:#x}' for site, target in sites)
    source = f'''
bits 16
org 0
start:
    push cs
    pop ds
    mov ax,cs
    sub ax,0x10
    mov es,ax
    mov ax,[es:0x2c]
    test ax,ax
    jz failed
    mov es,ax
    xor di,di
    xor ax,ax
    cld
next_environment:
    mov cx,0x7fff
    repne scasb
    jne failed
    cmp byte [es:di],0
    jne next_environment
    inc di
    cmp word [es:di],1
    jb failed
    add di,2
    push ds
    push es
    pop ds
    mov dx,di
    mov ax,0x3d00
    int 0x21
    pop ds
    jc failed
    mov bx,ax
    mov dx,{BUFFER_OFFSET:#x}
    mov cx,{len(carrier)}
    mov ah,0x3f
    int 0x21
    jc failed
    cmp ax,{len(carrier)}
    jne failed
    mov ah,0x3e
    int 0x21
    cli
    in al,0x92
    or al,2
    and al,0xfe
    out 0x92,al
    xor ebp,ebp
    mov bp,cs
    shl ebp,4
    lea eax,[ebp+gdt]
    mov [gdtr+2],eax
    lea eax,[ebp+protected_entry]
    mov [protected_jump],eax
    lgdt [gdtr]
    mov eax,cr0
    or al,1
    mov cr0,eax
    jmp dword far [protected_jump]
failed:
    mov ax,0x4c7f
    int 0x21
bits 32
protected_entry:
    mov ax,0x10
    mov ds,ax
    mov es,ax
    mov ss,ax
    mov esp,0x180000
    cld
    lea esi,[ebp+{BUFFER_OFFSET+code_file:#x}]
    mov edi,{CODE_BASE:#x}
    mov ecx,{len(code)}
    rep movsb
    lea esi,[ebp+{BUFFER_OFFSET+data_file:#x}]
    mov edi,{DATA_BASE:#x}
    mov ecx,{len(data)}
    rep movsb
{patches}
    mov dword [{OUTSIDE_BASE:#x}],0x90feeb90
    mov eax,{CODE_BASE:#x}
    jmp eax
align 8
gdt:
    dq 0
    dq 0x00cf9a000000ffff
    dq 0x00cf92000000ffff
gdt_end:
gdtr:
    dw gdt_end-gdt-1
    dd 0
protected_jump:
    dd 0
    dw 8
'''
    bootstrap = assemble(directory, 'le-dos-bootstrap', source, nasm)
    if len(bootstrap)>448:
        raise ValueError('Authored DOS bootstrap exceeds the outer MZ module')
    carrier[64:512] = bootstrap.ljust(448, b'\0')
    # Outer declared end stays512: the runtime parser must find BW exactly there.
    # The additional allocation holds the self-read buffer and original stack.
    struct.pack_into('<H', carrier, 0x0a, (65536-448)//16)
    struct.pack_into('<H', carrier, 0x10, 0xfffe)
    target = directory/'LETRACE.EXE'
    target.write_bytes(carrier)
    classic = load_mz(bytes(carrier))
    runtime = load_runtime_le_carrier(bytes(carrier))
    if classic.metadata['dos'].get('secondary_format') is not None:
        raise ValueError('Authored carrier changed the classic MZ launch gate')
    if runtime.metadata['le']['carrier']['application_offset'] != 1024:
        raise ValueError('Authored carrier lost its declared BW linkage')
    assert runtime.regions[0].data[68:72] == struct.pack('<I', 0x20000+COUNTER_OFFSET)
    return dict(path=target, sha256=hashlib.sha256(carrier).hexdigest(), size=len(carrier),
        bootstrap_size=len(bootstrap), code_base=CODE_BASE, data_base=DATA_BASE,
        outside_base=OUTSIDE_BASE, counter_address=DATA_BASE+COUNTER_OFFSET,
        entry_offset=0, increment_offset=66, store_offset=67, outside_jump_offset=82,
        code_file_offset=code_file, data_file_offset=data_file,
        code_size=len(code), data_size=len(data), offset32_sites=sites,
        source_view='embedded-le', carrier='mz-bw-mz-le')


def build_paged_ldt_fixture(directory, nasm, *, paging=True, ldt=True, tracking=False,
                            paging_mode="legacy-4k", dirty_overlay_writes=False,
                            dirty_overlay_cmpxchg=False, cmpxchg_lock=False,
                            dirty_overlay_atomic_batch=False):
    """Build a bounded MZ/BW/MZ/LE carrier with paging and an LDT CS.

    The protected-mode loader optionally copies the LE logical pages to three
    distinct physical pages, installs an identity page table with those three
    code pages remapped, optionally loads a real LDT, then enters the code
    through either the LDT or GDT selector. The entry instruction starts at
    byte 4094, so its four-byte fixup crosses the logical page boundary.  This is an
    authored carrier for native engine checks, not a general DOS extender.
    """
    from test_le_loader import le_file
    from test_le_runtime_carrier import bound_le

    high_physical = paging_mode in ('pae-4k-high', 'pae-2m-high', 'pse36-4m-high')
    pse36 = paging_mode == 'pse36-4m-high'
    base_mode = 'legacy-4m' if pse36 else paging_mode.removesuffix('-high')
    if paging_mode not in ('legacy-4k', 'legacy-4m', 'pae-4k', 'pae-2m',
                           'pae-4k-high', 'pae-2m-high', 'pse36-4m-high'):
        raise ValueError('unknown paging mode')
    if paging_mode != 'legacy-4k' and not tracking:
        raise ValueError('large and PAE modes require tracking')
    paging_mode = base_mode
    code_base = CODE_BASE if paging_mode == 'legacy-4k' else 0x400000
    code_physical = (PAGED_CODE_PHYSICAL if paging_mode == 'legacy-4k'
                     else (0x800000, 0x801000, 0x802000))
    tracking_physical = (PAGED_TRACKING_PHYSICAL if paging_mode == 'legacy-4k' else {
        'legacy-4m': 0xc01000, 'pae-2m': 0xa01000, 'pae-4k': 0x810000,
    }[paging_mode])
    remap_address = {'legacy-4k': 0x301484, 'legacy-4m': 0x300004,
                     'pae-4k': 0x302008, 'pae-2m': 0x301010}[paging_mode]
    remap_a = {'legacy-4k': code_physical[1] | 3, 'legacy-4m': 0x800083,
               'pae-4k': code_physical[1] | 3, 'pae-2m': 0x800083}[paging_mode]
    remap_b = {'legacy-4k': tracking_physical | 3, 'legacy-4m': 0xc00083,
               'pae-4k': tracking_physical | 3, 'pae-2m': 0xa00083}[paging_mode]
    if pse36:
        remap_a |= 0x2000
        remap_b |= 0x2000
    if dirty_overlay_writes and not tracking:
        raise ValueError('dirty overlay write witness requires tracking')
    if dirty_overlay_cmpxchg and not dirty_overlay_writes:
        raise ValueError('CMPXCHG overlay witness requires dirty overlay writes')
    if dirty_overlay_atomic_batch and not dirty_overlay_writes:
        raise ValueError('atomic batch witness requires dirty overlay writes')
    if tracking and not (paging and ldt):
        raise ValueError('tracking mode requires paging and the LDT')

    directory = Path(directory)
    # The first instruction starts at the last two bytes of page zero.  Its
    # immediate is an LE offset32 fixup to the declared data object.
    code = bytearray(b'\x90' * (3 * 4096))
    code[PAGED_ENTRY_OFFSET:PAGED_ENTRY_OFFSET + 5] = b'\xb8\0\0\0\0'
    # Increment through the loaded pointer, then jump back to the MOV.
    code[PAGED_ENTRY_OFFSET + 5:PAGED_ENTRY_OFFSET + 10] = b'\xff\x00\xeb\xf7\x90'
    # Keep the target visibly initialized, and place eight additional
    # offset32 sites in page two for the source matcher witness.
    data = bytearray((0x40 + i * 3) & 0xff for i in range(256))
    data[COUNTER_OFFSET:COUNTER_OFFSET + 4] = bytes(4)
    fixup = struct.pack('<BBhBH', 7, 0, PAGED_ENTRY_OFFSET + 1, 2, COUNTER_OFFSET)
    # A duplicate record on page one is required for a fixup which crosses a
    # logical-page boundary. Page two carries the independent witness sites.
    duplicate = struct.pack('<BBhBH', 7, 0, -1, 2, COUNTER_OFFSET)
    witness_sites = tuple(2 * 4096 + i * 8 + 1 for i in range(8))
    for site in witness_sites:
        code[site - 1:site + 4] = b'\xb8\0\0\0\0'
    witness_records = b''.join(
        struct.pack('<BBhBH', 7, 0, site - 2 * 4096, 2, i * 4)
        for i, site in enumerate(witness_sites)
    )
    if tracking:
        # The stable controller runs on logical page 2. It calls the same
        # LE target before and after changing logical page 1's PTE, then calls
        # it through a second LDT code selector before restoring the PTE.
        # The alternate page is copied from the fully relocated original.
        code[PAGED_TRACKING_TARGET:PAGED_TRACKING_TARGET + 2] = b'\x46\xcb'  # inc esi; retf
        code[PAGED_TRACKING_TARGET + 2:PAGED_TRACKING_TARGET + 2 + PAGED_TRACKING_SIGNATURE_SIZE] = bytes(
            (i * 73 + 19) & 0xff for i in range(PAGED_TRACKING_SIGNATURE_SIZE))
        if dirty_overlay_writes:
            # Both stores use the same linear alias and backing 4K page. The
            # first dirties that page; the second overlaps an execute layer.
            # The watched byte and its sibling writes are on logical page 1,
            # separate from the executing controller on logical page 2.
            watched = code_base + 0x1f01
            atomic_target = code_base + 0x1f00
            # The batch-only operand bytes are part of the authored LE image;
            # legacy scalar witnesses retain their original initialized NOPs.
            if dirty_overlay_atomic_batch:
                code[0x1f00:0x1f08] = bytes.fromhex('8877665544332211')
            # A separate batch-only DWORD straddles logical pages one and
            # two. End at offset 0x2000 to avoid the LE fixup at 0x2001.
            # Its overlay covers only the second page's backing.
            split_target = code_base + 0x1ffd
            if dirty_overlay_atomic_batch:
                code[0x1ffd:0x2001] = bytes.fromhex('44332211')
            unrelated = code_base + 0x1f10
            sentinel = code_base + 0x1f11
            controller = bytearray(b'\xc6\x05' + struct.pack('<I', unrelated) + b'\xa5')
            if dirty_overlay_atomic_batch:
                result_base = code_base + 0x1f40
                result_flags = result_base
                result_eax = result_base + 0x10
                result_edx = result_base + 0x20

                def mov_imm(reg_opcode, value):
                    return bytes((reg_opcode,)) + struct.pack('<I', value)

                def cmpxchg8b():
                    # 0F C7 /1 with absolute disp32 uses ModR/M 0D.
                    return (b'\xf0' if cmpxchg_lock else b'') + b'\x0f\xc7\x0d' + struct.pack('<I', atomic_target)

                def capture_results(index):
                    # Capture flags and the architectural EAX:EDX result pair.
                    delta = index * 4
                    return (b'\x9c\x8f\x05' + struct.pack('<I', result_flags + delta)
                            + b'\xa3' + struct.pack('<I', result_eax + delta)
                            + b'\x89\x15' + struct.pack('<I', result_edx + delta))

                controller += mov_imm(0xb8, 0x55667789) + mov_imm(0xba, 0x11223344)
                controller += mov_imm(0xbb, 0x44332211) + mov_imm(0xb9, 0x88776655)
                cmp_failed = code_base + PAGED_TRACKING_CONTROLLER + len(controller)
                controller += cmpxchg8b() + capture_results(0)
                controller += mov_imm(0xb8, 0x55667788) + mov_imm(0xba, 0x11223344)
                controller += mov_imm(0xbb, 0x44332211) + mov_imm(0xb9, 0x88776655)
                cmp_succeeded = code_base + PAGED_TRACKING_CONTROLLER + len(controller)
                controller += cmpxchg8b() + capture_results(1)
                controller += mov_imm(0xb8, 0x44332211) + mov_imm(0xba, 0x88776655)
                controller += mov_imm(0xbb, 0x44332211) + mov_imm(0xb9, 0x88776655)
                cmp_same = code_base + PAGED_TRACKING_CONTROLLER + len(controller)
                controller += cmpxchg8b() + capture_results(2)
                split_store = code_base + PAGED_TRACKING_CONTROLLER + len(controller)
                controller += b'\xc7\x05' + struct.pack('<I', split_target) + struct.pack('<I', 0xa1b2c3d4)
                sentinel_store = code_base + PAGED_TRACKING_CONTROLLER + len(controller)
                controller += b'\xc6\x05' + struct.pack('<I', sentinel) + b'\xcc\xeb\xfe'
                dirty_write_offsets = dict(
                    watched=watched, unrelated=unrelated, sentinel=sentinel,
                    atomic_target=atomic_target, atomic_result_flags=result_flags,
                    atomic_result_eax=result_eax, atomic_result_edx=result_edx,
                    cmp_failed=cmp_failed, cmp_succeeded=cmp_succeeded,
                    cmp_same=cmp_same, split_target=split_target,
                    split_store=split_store, split_page0=split_target & ~0xfff,
                    split_page1=(split_target + 3) & ~0xfff,
                    overlay_page=(atomic_target & ~0xfff),
                    unrelated_store=code_base + PAGED_TRACKING_CONTROLLER,
                    sentinel_store=sentinel_store, cmpxchg_lock=cmpxchg_lock,
                )
            elif dirty_overlay_cmpxchg:
                # Record the failed compare's architectural accumulator and flags
                # before the changed-value success reaches the dirty execute byte.
                result_al = code_base + 0x1f20
                result_flags = code_base + 0x1f21
                lock = b'\xf0' if cmpxchg_lock else b''
                compare = lock + b'\x0f\xb0\x1d' + struct.pack('<I', watched)  # [watched], BL
                controller += b'\xb0\x44\xb3\x5a'  # AL mismatch, BL replacement
                failed_pc = code_base + PAGED_TRACKING_CONTROLLER + len(controller)
                controller += compare
                controller += b'\xa2' + struct.pack('<I', result_al)
                controller += b'\x9c\x58\xa3' + struct.pack('<I', result_flags)
                result_ram = code_base + 0x1f2d
                controller += b'\xa0' + struct.pack('<I', watched)
                controller += b'\xa2' + struct.pack('<I', result_ram)
                # AL now holds the original RAM byte. This successful compare
                # changes it to BL and must report the overlay conflict after
                # the instruction has committed to guest RAM.
                controller += b'\xb0\x90'
                succeeded_pc = code_base + PAGED_TRACKING_CONTROLLER + len(controller)
                controller += compare
                controller += b'\x9c\x58\xa3' + struct.pack('<I', result_flags + 4)
                # After the changed-value write, compare against the same
                # byte without changing RAM; this succeeds and sets ZF.
                controller += b'\xb0\x5a\xb3\x5a'
                same_pc = code_base + PAGED_TRACKING_CONTROLLER + len(controller)
                controller += compare
                controller += b'\x9c\x58\xa3' + struct.pack('<I', result_flags + 8)
                cmp_failed, cmp_succeeded = failed_pc, succeeded_pc
            else:
                controller += b'\xc6\x05' + struct.pack('<I', watched) + b'\x5a'
                cmp_failed = cmp_succeeded = None
            if not dirty_overlay_atomic_batch:
                controller += b'\xc6\x05' + struct.pack('<I', sentinel) + b'\xcc\xeb\xfe'
                sentinel_store = code_base + PAGED_TRACKING_CONTROLLER + len(controller) - 9
                dirty_write_offsets = dict(watched=watched, unrelated=unrelated,
                                           sentinel=sentinel, overlay_page=watched & ~0xfff,
                                           unrelated_store=code_base + PAGED_TRACKING_CONTROLLER,
                                           watched_store=code_base + PAGED_TRACKING_CONTROLLER + 7,
                                           sentinel_store=sentinel_store)
                if dirty_overlay_cmpxchg:
                    dirty_write_offsets.update(cmp_failed=cmp_failed, cmp_succeeded=cmp_succeeded,
                                               cmp_result_al=result_al, cmp_result_flags=result_flags,
                                               cmp_result_ram=result_ram,
                                               cmp_same=same_pc,
                                               cmpxchg_lock=cmpxchg_lock)
        else:
            controller = bytearray()
            controller += b'\x9a' + struct.pack('<IH', PAGED_TRACKING_TARGET, PAGED_LDT_CODE_SELECTOR)
            controller += b'\xc7\x05' + struct.pack('<II', remap_address, remap_b)
            controller += bytes.fromhex('0f20d8 0f22d8')
            controller += b'\x9a' + struct.pack('<IH', PAGED_TRACKING_TARGET, PAGED_LDT_CODE_SELECTOR)
            controller += b'\x9a' + struct.pack('<IH', PAGED_TRACKING_TARGET, PAGED_TRACKING_SELECTOR_B)
            controller += b'\xc7\x05' + struct.pack('<II', remap_address, remap_a)
            controller += bytes.fromhex('0f20d8 0f22d8')
            controller += b'\x9a' + struct.pack('<IH', OUTSIDE_BASE, 8)
            controller += b'\xeb' + struct.pack('b', -(len(controller) + 2))
        code[PAGED_TRACKING_CONTROLLER:PAGED_TRACKING_CONTROLLER + len(controller)] = controller
        signature_start = PAGED_TRACKING_CONTROLLER + len(controller)
        code[signature_start:signature_start + PAGED_TRACKING_SIGNATURE_SIZE] = bytes(
            (i * 109 + 41) & 0xff for i in range(PAGED_TRACKING_SIGNATURE_SIZE))
    entry_offset = PAGED_TRACKING_CONTROLLER if tracking else PAGED_ENTRY_OFFSET
    application = le_file(code=bytes(code), data=bytes(data),
                          fixups=[fixup, duplicate, witness_records, b''],
                          object_sizes=(len(code), len(data)),
                          object_bases=(0x10000, 0x20000),
                          entry_offset=entry_offset)
    carrier = bytearray(bound_le(application))
    # Reserve a second outer MZ sector so the larger protected bootstrap fits
    # without changing the inner LE byte coordinates.  The declared BW link
    # is updated, never discovered by signature search.
    carrier[512:512] = b'\0' * 512
    struct.pack_into('<HH', carrier, 2, 0, 2)
    carrier[1024:1026] = b'BW'
    struct.pack_into('<I', carrier, 1024 + 28, 1536)
    parsed = load_runtime_le_carrier(bytes(carrier))
    header = parsed.metadata['le']['header_offset']
    page_table = header + struct.unpack_from('<I', carrier, header + 0x48)[0]
    data_pages = parsed.metadata['le']['carrier']['application_offset'] + struct.unpack_from('<I', carrier, header + 0x80)[0]
    # Logical page order is [code0, code1, code2, data0].  File physical
    # order is deliberately permuted [code1, code0, code2, data0].
    physical = [bytes(carrier[data_pages + i * 4096:data_pages + (i + 1) * 4096])
                for i in range(4)]
    physical[0], physical[1] = physical[1], physical[0]
    for i, page in enumerate(physical):
        carrier[data_pages + i * 4096:data_pages + (i + 1) * 4096] = page
    for logical, physical_index in enumerate((2, 1, 3, 4)):
        carrier[page_table + logical * 4:page_table + logical * 4 + 4] = (
            physical_index.to_bytes(3, 'big') + b'\0')
    parsed = load_runtime_le_carrier(bytes(carrier))
    mappings = parsed.metadata['file_mappings']
    code_files = [row['file_offset'] for row in mappings
                  if 0x10000 <= row['virtual_address'] < 0x13000]
    data_file = next(row['file_offset'] for row in mappings
                     if row['virtual_address'] == 0x20000)
    # The loader is deliberately compact: it copies each declared logical
    # page to its physical backing, creates a page table, and then switches
    # to the LDT code selector.  The page-table identity entries cover the
    # loader itself and are overwritten only for code/data pages.
    runtime_code_pages = code_physical if paging else (code_base,
                                                              code_base + 0x1000,
                                                              code_base + 0x2000)
    runtime_data = PAGED_DATA_PHYSICAL if paging and paging_mode == 'legacy-4k' else DATA_BASE
    copies = '\n'.join(
        f'    lea esi,[ebp+{BUFFER_OFFSET + file:#x}]\n'
        f'    mov edi,{phys:#x}\n    mov ecx,0x1000\n    rep movsb'
        for file, phys in zip(code_files, runtime_code_pages))
    paging_setup = f'''
    xor eax,eax
    mov edi,0x300000
    mov ecx,2048
    rep stosd
    mov dword [0x300000],0x301003
    mov edi,0x301000
    mov eax,3
    mov ecx,1024
.identity:
    stosd
    add eax,0x1000
    loop .identity
    mov dword [0x301480],{runtime_code_pages[0] | 3:#x}
    mov dword [0x301484],{runtime_code_pages[1] | 3:#x}
    mov dword [0x301488],{runtime_code_pages[2] | 3:#x}
    mov dword [0x3014c0],{runtime_data | 3:#x}
    mov eax,0x300000
    mov cr3,eax
    mov eax,cr0
    or eax,0x80000000
    mov cr0,eax
    jmp short .paging
.paging:
'''
    if paging_mode == 'legacy-4m':
        paging_setup = """
    mov eax,1
    cpuid
    mov [0x1f0000],edx
    mov eax,cr4
    mov [0x1f0004],eax
    xor eax,eax
    mov edi,0x300000
    mov ecx,1024
    rep stosd
    mov dword [0x300000],0x000083
    mov dword [0x300004],0x800083
    mov dword [0x300008],0x800083
    mov dword [0x30000c],0xc00083
    mov eax,cr4
    or eax,0x10
    mov cr4,eax
    mov eax,0x300000
    mov cr3,eax
    mov eax,cr0
    or eax,0x80000000
    mov cr0,eax
    jmp short .paging
.paging:
"""
    elif paging_mode.startswith('pae'):
        code_entry = '0x302003' if paging_mode == 'pae-4k' else '0x800083'
        paging_setup = f"""
    xor eax,eax
    mov edi,0x300000
    mov ecx,3072
    rep stosd
    mov dword [0x300000],0x301001
    mov dword [0x301000],0x000083
    mov dword [0x301008],0x200083
    mov dword [0x301010],{code_entry}
    mov dword [0x301018],0x600083
    mov dword [0x301020],0x800083
    mov dword [0x301028],0xa00083
    mov dword [0x301030],0xc00083
    mov edi,0x302000
    mov eax,0x400003
    mov ecx,512
.identity_pae:
    stosd
    add edi,4
    add eax,0x1000
    loop .identity_pae
    mov dword [0x302000],0x800003
    mov dword [0x302008],0x801003
    mov dword [0x302010],0x802003
    mov eax,cr4
    or eax,0x30
    mov cr4,eax
    mov eax,0x300000
    mov cr3,eax
    mov eax,cr0
    or eax,0x80000000
    mov cr0,eax
    jmp short .paging
.paging:
"""
    if not paging:
        paging_setup = ''
    ldt_setup = '    mov ax,0x18\n    lldt ax\n' if ldt else ''
    jump_selector = PAGED_LDT_CODE_SELECTOR if ldt else 8
    entry_ip = entry_offset if ldt else code_base + entry_offset
    patches = '\n'.join(
        f'    mov dword [{code_base + site:#x}],{DATA_BASE + target:#x}'
        for site, target in [(PAGED_ENTRY_OFFSET + 1, COUNTER_OFFSET)] +
                            [(site, i * 4) for i, site in enumerate(witness_sites)])
    tracking_clone = f'''
    mov esi,{code_physical[1]:#x}
    mov edi,{tracking_physical:#x}
    mov ecx,0x1000
    rep movsb
''' if tracking else ''
    if paging_mode in ('legacy-4m', 'pae-2m'):
        clone_size = 0x400000 if paging_mode == 'legacy-4m' else 0x200000
        clone_target = 0xc00000 if paging_mode == 'legacy-4m' else 0xa00000
        tracking_clone = f"\n mov esi,0x400000\n mov edi,{clone_target:#x}\n mov ecx,{clone_size:#x}\n rep movsb\n"
    # A temporary 2 MiB linear window at 0x600000 addresses RAM above 4 GiB.
    # The carrier is first copied and relocated through the ordinary mappings;
    # all high backing is then populated by guest instructions before use.
    high_setup = ''
    if high_physical and not pse36:
        second_copy = ("mov esi,0x401000\n    mov edi,0x610000\n    mov ecx,0x1000"
                       if paging_mode == 'pae-4k' else
                       "mov dword [0x301018],0xa00083\n    mov eax,cr3\n    mov cr3,eax\n"
                       "    mov esi,0x400000\n    mov edi,0x600000\n    mov ecx,0x200000")
        final_entries = ("mov dword [0x302004],1\n    mov dword [0x30200c],1\n"
                         "    mov dword [0x302014],1" if paging_mode == 'pae-4k'
                         else "mov dword [0x301014],1")
        high_setup = f"""
    mov dword [0x301018],0x800083
    mov dword [0x30101c],1
    mov eax,cr3
    mov cr3,eax
    mov esi,0x400000
    mov edi,0x600000
    mov ecx,{'0x3000' if paging_mode == 'pae-4k' else '0x200000'}
    rep movsb
    {second_copy}
    rep movsb
    ; Poison the low aliases after copying, to detect physical truncation.
    mov word [0x801400],0x0b0f
    mov word [{tracking_physical + (PAGED_TRACKING_TARGET & 0xfff):#x}],0x0b0f
    {final_entries}
    mov eax,cr3
    mov cr3,eax
"""
    if pse36:
        high_setup = '''
    ; PSE-36 PDE bit 13 carries physical address bit 32.
    mov dword [0x30000c],0x802083
    mov eax,cr3
    mov cr3,eax
    mov esi,0x400000
    mov edi,0xc00000
    mov ecx,0x400000
    rep movsb
    mov dword [0x300008],0xc00083
    mov dword [0x30000c],0xc02083
    mov eax,cr3
    mov cr3,eax
    mov esi,0x800000
    mov edi,0xc00000
    mov ecx,0x400000
    rep movsb
    mov dword [0x300008],0x800083
    mov dword [0x30000c],0xc00083
    mov eax,cr3
    mov cr3,eax
    mov word [0x801400],0x0b0f
    mov word [0xc01400],0x0b0f
    mov dword [0x300004],0x802083
    mov eax,cr3
    mov cr3,eax
'''
    if high_physical:
        code_physical = tuple(phys + 0x100000000 for phys in code_physical)
        tracking_physical += 0x100000000
        runtime_code_pages = code_physical
    outside_init = f'    mov word [{OUTSIDE_BASE:#x}],0xcb47\n' if tracking else ''
    descriptor = '0x00cf9a400000ffff' if paging_mode != 'legacy-4k' else '0x00cf9a120000ffff'
    ldt_extra = f'    dq {descriptor}\n' if tracking else ''
    source = f'''
bits 16
org 0
start:
    push cs
    pop ds
    mov ax,cs
    sub ax,0x10
    mov es,ax
    mov ax,[es:0x2c]
    test ax,ax
    jz failed
    mov es,ax
    xor di,di
    xor ax,ax
    cld
next_environment:
    mov cx,0x7fff
    repne scasb
    jne failed
    cmp byte [es:di],0
    jne next_environment
    inc di
    cmp word [es:di],1
    jb failed
    add di,2
    push ds
    push es
    pop ds
    mov dx,di
    mov ax,0x3d00
    int 0x21
    pop ds
    jc failed
    mov bx,ax
    mov dx,{BUFFER_OFFSET:#x}
    mov cx,{len(carrier)}
    mov ah,0x3f
    int 0x21
    jc failed
    cmp ax,{len(carrier)}
    jne failed
    mov ah,0x3e
    int 0x21
    cli
    in al,0x92
    or al,2
    and al,0xfe
    out 0x92,al
    xor ebp,ebp
    mov bp,cs
    shl ebp,4
    lea eax,[ebp+ldt]
    mov word [gdt+0x1a],ax
    shr eax,16
    mov byte [gdt+0x1c],al
    mov byte [gdt+0x1f],ah
    lea eax,[ebp+gdt]
    mov [gdtr+2],eax
    lea eax,[ebp+protected_entry]
    mov [protected_jump],eax
    lgdt [gdtr]
    mov eax,cr0
    or al,1
    mov cr0,eax
    jmp dword far [protected_jump]
failed:
    mov ax,0x4c7e
    int 0x21
bits 32
protected_entry:
    mov ax,0x10
    mov ds,ax
    mov es,ax
    mov ss,ax
    mov esp,0x180000
{copies}
    ; Copy the declared data object to a physical page, then build identity
    ; PDE/PTEs and replace only the code/data linear mappings.
    lea esi,[ebp+{BUFFER_OFFSET + data_file:#x}]
    mov edi,{runtime_data:#x}
    mov ecx,{len(data)}
    rep movsb
{outside_init}
{paging_setup}{patches}{tracking_clone}{high_setup}
{ldt_setup}
    jmp dword {jump_selector}:{entry_ip:#x}
align 8
gdt:
    dq 0
    dq 0x00cf9a000000ffff
    dq 0x00cf92000000ffff
    dq 0x00008200000000ff
gdt_end:
ldt:
    dq 0
    dq {descriptor}
    dq 0x00cf92000000ffff
{ldt_extra.rstrip()}
ldt_end:
gdtr:
    dw gdt_end-gdt-1
    dd 0
protected_jump:
    dd 0
    dw 8
'''
    bootstrap = assemble(directory, 'le-paged-ldt-bootstrap', source, nasm)
    if len(bootstrap) > 960:
        raise ValueError(f'Paged/LDT DOS bootstrap exceeds outer MZ module: {len(bootstrap)} bytes')
    carrier[64:1024] = bootstrap.ljust(960, b'\0')
    struct.pack_into('<H', carrier, 0x0a, (65536 - 960) // 16)
    struct.pack_into('<H', carrier, 0x10, 0xfffe)
    suffix = ('paged' if paging else 'flat') + ('-ldt' if ldt else '-gdt')
    target = directory / ('LE' + suffix.upper() + '.EXE')
    target.write_bytes(carrier)
    image = load_runtime_le_carrier(bytes(carrier))
    pages = image.metadata['le']['pages']
    return dict(path=target, sha256=hashlib.sha256(carrier).hexdigest(), size=len(carrier),
                bootstrap_size=len(bootstrap), code_base=code_base,
                data_base=DATA_BASE, entry_offset=entry_offset, entry_ip=entry_ip,
                entry_address=code_base + entry_offset,
                data_physical=runtime_data,
                code_physical=runtime_code_pages,
                ldt_code_selector=PAGED_LDT_CODE_SELECTOR if ldt else None,
                witness_sites=witness_sites,
                page_map=tuple((p['index'], p['physical_page']) for p in pages),
                code_file_offsets=tuple(code_files), data_file_offset=data_file,
                cross_page_fixup_offsets=(PAGED_ENTRY_OFFSET + 1, -1),
                counter_address=DATA_BASE + COUNTER_OFFSET, paging=paging, ldt=ldt,
                carrier='mz-bw-mz-le-' + suffix,
                source_view='embedded-le', tracking=tracking,
                tracking_start_cs=PAGED_LDT_CODE_SELECTOR if tracking else None,
                tracking_start_ip=entry_offset if tracking else None,
                tracking_start_pc=code_base + entry_offset if tracking else None,
                tracking_controller=PAGED_TRACKING_CONTROLLER if tracking else None,
                tracking_target=PAGED_TRACKING_TARGET if tracking else None,
                tracking_target_physical=(code_physical[1] + (PAGED_TRACKING_TARGET & 0xfff)) if tracking else None,
                tracking_alternate_physical=(tracking_physical + (PAGED_TRACKING_TARGET & 0xfff)) if tracking else None,
                tracking_selector_b=PAGED_TRACKING_SELECTOR_B if tracking else None,
                tracking_steps=19 if tracking else None,
                tracking_signature_size=PAGED_TRACKING_SIGNATURE_SIZE if tracking else None,
                dirty_write_offsets=dirty_write_offsets if dirty_overlay_writes else None,
                tracking_milestones=((PAGED_LDT_CODE_SELECTOR, PAGED_TRACKING_CONTROLLER, code_physical[2] + (PAGED_TRACKING_CONTROLLER & 0xfff)),
                    (PAGED_LDT_CODE_SELECTOR, PAGED_TRACKING_TARGET, code_physical[1] + (PAGED_TRACKING_TARGET & 0xfff)),
                    (PAGED_LDT_CODE_SELECTOR, PAGED_TRACKING_TARGET, tracking_physical + (PAGED_TRACKING_TARGET & 0xfff)),
                    (PAGED_TRACKING_SELECTOR_B, PAGED_TRACKING_TARGET, tracking_physical + (PAGED_TRACKING_TARGET & 0xfff)),
                    (8, OUTSIDE_BASE, OUTSIDE_BASE)) if tracking else ())
