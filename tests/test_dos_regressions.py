"""DOS state and reset regressions through the persistent project interface."""
import struct

import pytest

from fdisbull.project import Project


def _mz(module, relocations=(), *, ss=0, sp=32):
    """Make a small ordinary MZ; fixup positions are module byte offsets."""
    header_size = 64
    size = header_size + len(module)
    header = bytearray(header_size)
    struct.pack_into(
        '<14H', header, 0, 0x5A4D, size % 512, (size + 511) // 512,
        len(relocations), header_size // 16, 0, 0xFFFF, ss, sp,
        0, 0, 0, 28, 0,
    )
    for index, offset in enumerate(relocations):
        struct.pack_into('<HH', header, 28 + index * 4, offset, 0)
    return bytes(header) + bytes(module)


def _project(tmp_path, source, **options):
    binary = tmp_path / 'fixture.exe'
    binary.write_bytes(source)
    return Project.create(tmp_path / 'fixture.fdb', binary, **options)


def _callbacks():
    module = bytearray(256)
    # mov dx,DATA; mov ds,dx; call far CODE:0; ret
    module[:11] = bytes.fromhex('ba08008eda9a00000400c3')
    module[0x40:0x44] = bytes.fromhex('b82a00cb')  # mov ax,42; retf
    module[0x50] = 0xCB  # callback reachable through the relocated data table
    struct.pack_into('<HH', module, 0x80, 0x10, 4)
    module[0xA0:0xA9] = b'DINOSAUR\0'
    return _mz(module, (1, 8, 0x82), ss=15, sp=16)


def test_unrelated_representation_reset_retains_relocated_callbacks(tmp_path):
    with _project(tmp_path, _callbacks()) as project:
        assert project.analyze()['stable']
        before = {(f['context'], f['address']) for f in project.functions()}
        assert ('x86:16:little:cs=1004', '0x10050') in before

        result = project.represent('1008:0020', 'ascii', size=8)
        assert result['analysis']['stable']
        after = {(f['context'], f['address']) for f in project.functions()}
        assert after == before
        assert project.disassembly('1004:0010', lines=1)['instructions'][0]['mnemonic'] == 'retf'


@pytest.mark.parametrize(
    ('representation', 'size', 'raw', 'expected'),
    [
        ('byte', 1, b'\x48', 0x48),
        ('word', 2, b'\x48\x45', 0x4548),
        ('dword', 4, b'\x48\x45\x4c\x4c', 0x4C4C4548),
        ('qword', 8, bytes.fromhex('0807060504030201'), 0x0102030405060708),
        ('ascii', 5, b'HELLO', 'HELLO'),
        ('utf-16le', 10, 'HELLO'.encode('utf-16le'), 'HELLO'),
    ],
)
def test_unused_explicit_data_definition_is_investigated_with_its_value(
    tmp_path, representation, size, raw, expected,
):
    module = bytearray(128)
    module[0] = 0xC3  # no code reference to the data location
    module[0x40:0x40 + len(raw)] = raw
    with _project(tmp_path, _mz(module)) as project:
        assert project.analyze()['stable']
        result = project.represent('1004:0000', representation, size=size)
        assert result['analysis']['stable']
        item = next(item for item in project.items() if item['address'] == '0x10040')
        assert item['representation'] == representation
        assert item['size'] == size
        assert item['value'] == expected


def test_referenced_ascii_definition_changes_value_from_word_to_text(tmp_path):
    module = bytearray(128)
    # mov ax,DATA; mov ds,ax; mov ax,[0]; ret
    module[:9] = bytes.fromhex('b804008ed8a10000c3')
    module[0x40:0x46] = b'HELLO\0'
    with _project(tmp_path, _mz(module, (1,))) as project:
        assert project.analyze()['stable']
        project.represent('1004:0000', 'ascii', size=5)
        item = next(item for item in project.items() if item['address'] == '0x10040')
        assert item['representation'] == 'ascii'
        assert item['value'] == 'HELLO'


@pytest.mark.parametrize('adjustment', ['83c402', 'bc2200'])
def test_sp_change_invalidates_pushed_constant_before_pop_ds(tmp_path, adjustment):
    module = bytearray(128)
    # mov ax,DATA; push ax; adjust SP to discard that value; pop ds; mov ax,[0]; ret
    code = bytes.fromhex('b8040050' + adjustment + '1fa10000c3')
    module[:len(code)] = code
    module[0x40:0x42] = b'\x11\x11'
    with _project(tmp_path, _mz(module, (1,))) as project:
        assert project.analyze()['stable']
        row = project.disassembly('1000:0008', lines=1)['instructions'][0]
        assert row['mnemonic'] == 'mov'
        assert 'ds' not in row['assumptions']['registers']
        assert not any(ref['target'] == '0x10040' for ref in row['references'])


def test_selected_entry_cs_survives_representation_reset_and_restart(tmp_path):
    module = bytearray(65552)
    # A relocated selector supplies the second CS candidate, beyond the header CS window.
    struct.pack_into('<H', module, 0, 0x1000)
    module[65536] = 0xC3
    with _project(tmp_path, _mz(module, (0,)), entry=0x20000) as project:
        assert project.analyze()['stable']
        assert project.disassembly('2000:0000', lines=1)['instructions'][0]['mnemonic'] == 'ret'
        result = project.represent('2000:0001', 'byte')
        assert result['analysis']['stable']
        assert project.disassembly('2000:0000', lines=1)['instructions'][0]['mnemonic'] == 'ret'
        project_path = project.path
    with Project(project_path) as reopened:
        assert reopened.analyze()['stable']
        assert reopened.disassembly('2000:0000', lines=1)['instructions'][0]['context'] == 'x86:16:little:cs=2000'


@pytest.mark.parametrize(
    ('call', 'callee_offset', 'callee_address', 'relocations', 'expected_sp', 'return_code'),
    [
        ('66e801000000c3', 7, '1000:0007', (), 28, '66c3'),
        ('669a000000000400c3', 0x40, '1004:0000', (6,), 24, '66cb'),
    ],
)
def test_operand32_call_uses_its_actual_stack_width(
    tmp_path, call, callee_offset, callee_address, relocations, expected_sp, return_code,
):
    module = bytearray(128)
    call_bytes = bytes.fromhex(call)
    module[:len(call_bytes)] = call_bytes
    # mov bp,sp; mov ax,[bp]; operand-size32 return
    callee = bytes.fromhex('89e58b4600' + return_code)
    module[callee_offset:callee_offset + len(callee)] = callee
    with _project(tmp_path, _mz(module, relocations, sp=32)) as project:
        assert project.analyze()['stable']
        rows = project.disassembly(callee_address, lines=2)['instructions']
        # A conservative join with a deferred candidate may discard SP/BP.
        # It must never preserve the incorrect 16-bit CALL adjustment.
        assert rows[0]['assumptions']['registers'].get('sp') in (None, expected_sp)
        assert rows[1]['assumptions']['registers'].get('bp') in (None, expected_sp)
        targets = {ref['target'] for ref in rows[1]['references']}
        assert not targets or targets == {hex(0x10000 + expected_sp)}


@pytest.mark.parametrize('budget', [1, 10000])
def test_newly_proven_cs_reopens_data_callback_investigation(tmp_path, budget):
    module = bytearray(256)
    # DS is established before an indirect far call proves another code segment.
    module[:10] = bytes.fromhex('ba08008edaff1e0000c3')
    module[0x40] = 0xCB
    module[0x50] = 0xCB
    struct.pack_into('<HHHH', module, 0x80, 0, 4, 0x10, 4)
    with _project(tmp_path, _mz(module, (1, 0x82, 0x86))) as project:
        for _ in range(64):
            result = project.analyze(max_instructions=budget)
            if result['stable']:
                break
            assert result['pending'] > 0
        else:
            pytest.fail('DOS queues did not converge within the bounded fixture')
        functions = {function['segmented_address'] for function in project.functions()}
        assert '1004:0000' in functions  # actual indirect call
        assert '1004:0010' in functions  # relocated callback, newly corroborated CS
        assert project.disassembly('1004:0010', lines=1)['instructions'][0]['mnemonic'] == 'retf'
        again = project.analyze(max_instructions=budget)
        assert again['stable'] and again['attempted'] == 0 and again['new_facts'] == 0


def test_retracting_indirect_call_retracts_its_learned_cs_and_callbacks(tmp_path):
    module = bytearray(256)
    module[:10] = bytes.fromhex('ba08008edaff1e0000c3')
    module[0x40] = module[0x50] = 0xCB
    struct.pack_into('<HHHH', module, 0x80, 0, 4, 0x10, 4)
    with _project(tmp_path, _mz(module, (1, 0x82, 0x86))) as project:
        assert project.analyze()['stable']
        assert {'1004:0000', '1004:0010'} <= {
            function['segmented_address'] for function in project.functions()
        }
        # Removing the only instruction establishing CS1004 also removes the
        # corroboration used to promote this segment's relocated callbacks.
        result = project.represent('1000:0005', 'byte')
        assert result['analysis']['stable']
        assert not any(function['cs'] == 0x1004 for function in project.functions())
        segment = next(item for item in project.segments() if item['selector'] == 0x1004)
        assert 'code' not in segment['roles']
