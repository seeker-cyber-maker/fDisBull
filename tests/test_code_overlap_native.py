"""Native acceptance for entry-qualified TEST/STOSB code backings.

Inputs are tiny authored COM byte strings. The fixtures test only the declared
entry streams and their explicit native effects; they are not general semantic
equivalence evidence for arbitrary code layouts.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from fdisbull.debug_state import apply_edits, register_value
from fdisbull.native_udc import (
    capture_native_definition,
    compile_native_definition,
    native_definition_info,
)
from fdisbull.project import Project


_ASSUMPTIONS = {name: True for name in (
    'no_code_reads', 'no_code_writes', 'no_computed_entries',
    'address_identity_unobserved', 'timing_unobserved',
)}
_BASE_FLAGS = 0x0CD7  # reserved bit 1, CF/PF/AF/ZF/SF/DF/OF set
_SENTINEL = 0x3C
_LOAD_SEGMENT = 0x1000
_LOAD_IP = 0x0100
_ENTRY_A = 0x0106
_ENTRY_PREFIX = bytes.fromhex('30e4cd16eb00')  # XOR AH,AH; BIOS key wait; JMP to entry A.
_DATA_IP = 0x0200


def _backend():
    value = os.environ.get('FDISBULL_DOSBOX')
    if not value:
        pytest.skip('Set FDISBULL_DOSBOX for authored native overlap acceptance')
    backend = Path(value).resolve(strict=True)
    if not backend.is_file() or not os.access(backend, os.X_OK):
        pytest.fail('FDISBULL_DOSBOX must name an executable native DOSBox backend')
    return backend


def _source_fixture(kind: str):
    if kind == 'overlap16':
        # A: TEST AL,0xaa; B: STOSB; both reach the same RET at +2.
        semantic, b, join, size_b, immediate = bytes.fromhex('a8aac3'), 0x107, 0x108, 1, 0xAA
    if kind == 'overlap32addr':
        # A: TEST AL,0x67; ordinary STOSB; B: addr32 STOSB; shared HLT.
        semantic, b, join, size_b, immediate = bytes.fromhex('a867aaf4'), 0x107, 0x109, 2, 0x67
    if kind == 'naive_concat':
        # This flattened stream adds STOSB after TEST and changes entry A.
        semantic, b, join, size_b, immediate = bytes.fromhex('a8aaaac3'), 0x107, 0x109, 1, 0xAA
    if kind not in ('overlap16', 'overlap32addr', 'naive_concat'):
        raise ValueError(kind)
    return _ENTRY_PREFIX + semantic, _ENTRY_A, b, join, 2, size_b, 1, immediate


def _image(code: bytes, *, address_limit: bool):
    image = bytearray(0xFF00 if address_limit else 0x101)
    image[:len(code)] = code
    image[0x100] = _SENTINEL  # CS:0200 maps to COM file offset 0x100.
    if address_limit:
        image[-1] = _SENTINEL  # CS:ffff maps to the final COM byte.
    return bytes(image)


def _source_project(tmp_path, kind: str):
    code, ip_a, ip_b, ip_join, size_a, size_b, size_join, _ = _source_fixture(kind)
    game = tmp_path / 'SOURCE.COM'
    game.write_bytes(_image(code, address_limit=(kind == 'overlap32addr')))
    project = Project.create(tmp_path / 'source.fdb', game, image='com')
    project.analyze(start=f'{_LOAD_SEGMENT:04x}:{ip_a:04x}')
    project.represent(f'{_LOAD_SEGMENT:04x}:{ip_b:04x}', 'code', size=size_b)
    return project, game


def _compiled_program(tmp_path, kind: str):
    code, ip_a, ip_b, ip_join, size_a, size_b, size_join, immediate = _source_fixture(kind)
    project, game = _source_project(tmp_path, kind)
    try:
        entries = [f'{_LOAD_SEGMENT:04x}:{ip_a:04x}', f'{_LOAD_SEGMENT:04x}:{ip_b:04x}']
        captured = capture_native_definition(project, 'native-overlap', entries, version=1)
        definition_id = captured['id']
        assert captured['graph_complete']
        database = project.path
        project.db.close()
        with Project(database) as persisted:
            info = native_definition_info(persisted, definition_id)
            assert info['id'] == definition_id and info['graph_complete']
            assert info['version'] == 1 and info['original_layout_available']
            detail = native_definition_info(persisted, definition_id, include_blocks=True)
            document = detail['document']['capsule']
            assert document['complete'] and document['unresolved'] == []
            assert document['coverage']['shared_occurrence_bytes'] >= 1
            original = compile_native_definition(persisted, definition_id)
            original_bytes = bytes.fromhex(original['bytes'])
            source_bytes = game.read_bytes()
            assert original['mode'] == 'original-layout'
            assert Path(original['filename']).name == game.name
            assert original['qualification'] == 'original_bytes_only'
            assert original['byte_identity'] and not original['source_layout_modified']
            assert original_bytes == source_bytes
            assert original_bytes[ip_b - _LOAD_IP] == source_bytes[ip_b - _LOAD_IP] == (0xAA if kind == 'overlap16' else 0x67)
            relayout_result = compile_native_definition(
                persisted, definition_id, mode='relayout', assumptions=_ASSUMPTIONS,
                base=ip_a)
            assert relayout_result['qualification'] == 'structural_only'
            assert relayout_result['source_layout_modified']
            assert relayout_result['layout']['qualification'] == 'structural_only'
            layout = relayout_result['layout']
            assert relayout_result['bytes'] == layout['bytes']
            entry_a_id, entry_b_id = document['entries']
            compiled_bytes = bytes.fromhex(relayout_result['bytes'])
            assert game.read_bytes() == source_bytes  # Capture/compile did not edit the authored source.
        source_join = f'0x{_LOAD_SEGMENT * 16 + ip_join:x}'
        join_occurrence = next(item for item in layout['occurrences']
                               if item['source_address'] == source_join)
        program = {
            'code': _ENTRY_PREFIX + compiled_bytes,
            'entry_a': layout['entries'][entry_a_id],
            'entry_b': layout['entries'][entry_b_id],
            'join': int(join_occurrence['output_address'], 16),
            'size_a': size_a,
            'size_b': size_b,
            'size_join': size_join,
            'immediate': immediate,
            'address_limit': kind == 'overlap32addr',
            'layout': layout,
            'document': document,
            'native_definition_id': definition_id,
            'original_sha256': original['sha256'],
            'original_byte_identity': original['byte_identity'],
            'original_filename': original['filename'],
        }
        return program
    finally:
        try:
            project.db.close()
        except Exception:
            pass


def _run_entry(tmp_path, backend, *, program, entry, al, df, destination_override=None):
    tmp_path.mkdir(parents=True, exist_ok=False)
    game = tmp_path / 'RUN.COM'
    game.write_bytes(_image(program['code'], address_limit=program['address_limit']))
    with Project.create(tmp_path / 'run.fdb', game, image='com') as project:
        project.analyze(start=f'{_LOAD_SEGMENT:04x}:{program["entry_a"]:04x}')
        project.represent(f'{_LOAD_SEGMENT:04x}:{program["entry_b"]:04x}',
                          'code', size=program['size_b'])
        with project.debugger(backend, tmp_path) as dos:
            start = dos.breakpoint(f'{_LOAD_SEGMENT:04x}:{program["entry_a"]:04x}')
            waiting = dos.run(guest_ms=100, timeout_ms=5000,
                              fast_forward=True, stop_on_hook=True)
            assert waiting['outcome'] == 'guest_time', waiting
            dos.keyboard_press('a')
            stopped = dos.run(guest_ms=100, timeout_ms=5000,
                              fast_forward=True, stop_on_hook=True)
            assert stopped['outcome'] == 'breakpoint', {'breakpoint': start, 'run': stopped}
            dos.delete_breakpoint(start['breakpoint_id'])

            before = dos.registers()
            assert before['cpu_mode'] == 'real'
            cs = int(before['segments']['cs'], 16)
            destination = (_DATA_IP if destination_override is None
                           else destination_override)
            flags_in = (_BASE_FLAGS & ~0x0400) | (0x0400 if df else 0)
            entry_ip = program['entry_a'] if entry == 'A' else program['entry_b']
            memory_edits = ([] if destination_override is not None else
                [{'address': f'{_LOAD_SEGMENT:04x}:{destination:04x}',
                  'expected_hex': f'{_SENTINEL:02x}', 'data_hex': f'{_SENTINEL:02x}'}])
            apply_edits(
                dos,
                memory_edits,
                {
                    'eax': {'expected': register_value(before, 'eax'), 'value': al},
                    'edi': {'expected': register_value(before, 'edi'), 'value': destination},
                    'es': {'expected': register_value(before, 'es'), 'value': cs},
                    'flags': {'expected': register_value(before, 'flags'), 'value': flags_in},
                    'eip': {'expected': register_value(before, 'eip'), 'value': entry_ip},
                },
            )
            join = dos.breakpoint(f'{_LOAD_SEGMENT:04x}:{program["join"]:04x}')
            result = dos.run(guest_ms=100, timeout_ms=5000,
                             fast_forward=True, stop_on_hook=True)
            assert result['outcome'] == 'breakpoint'
            regs = dos.registers()
            assert register_value(regs, 'eip') == program['join']
            observed = (None if destination_override is not None else
                        dos.memory(f'{_LOAD_SEGMENT:04x}:{destination:04x}', length=1))
            dos.delete_breakpoint(join['breakpoint_id'])
            return {
                'memory': None if observed is None else bytes.fromhex(observed['hex'])[0],
                'edi': register_value(regs, 'edi'),
                'flags': register_value(regs, 'flags'),
                'destination': destination,
                'entry_ip': entry_ip,
                'join_ip': program['join'],
            }


def _assert_test_flags(flags: int, al: int, immediate: int, df: int):
    value = al & immediate
    assert flags & 0x001 == 0  # TEST clears CF.
    assert flags & 0x800 == 0  # TEST clears OF.
    assert bool(flags & 0x080) == bool(value & 0x80)
    assert bool(flags & 0x040) == (value == 0)
    assert bool(flags & 0x004) == (value.bit_count() % 2 == 0)
    assert bool(flags & 0x400) == bool(df)
    # AF is architecturally undefined after TEST, so it is intentionally not asserted.


def _check_program(tmp_path, backend, program, *, test_immediate, native_label,
                   entry_a_stores=False):
    for al in (0x00, 0x55, 0xAA, 0xFF):
        for df in (0, 1):
            result_a = _run_entry(tmp_path / f'{native_label}-A-{al:02x}-{df}', backend,
                                  program=program, entry='A', al=al, df=df)
            if entry_a_stores:
                assert result_a['memory'] == al, (native_label, 'A', hex(al), df)
                assert result_a['edi'] == (_DATA_IP - 1 if df else _DATA_IP + 1)
            else:
                assert result_a['memory'] == _SENTINEL, (native_label, 'A', hex(al), df)
                assert result_a['edi'] == _DATA_IP
            _assert_test_flags(result_a['flags'], al, test_immediate, df)

            result_b = _run_entry(tmp_path / f'{native_label}-B-{al:02x}-{df}', backend,
                                  program=program, entry='B', al=al, df=df)
            assert result_b['memory'] == al, (native_label, 'B', hex(al), df)
            assert result_b['edi'] == (_DATA_IP - 1 if df else _DATA_IP + 1)
            expected_flags = (_BASE_FLAGS & ~0x0400) | (0x0400 if df else 0)
            assert result_b['flags'] == expected_flags, (native_label, 'B', hex(al), df)


def test_native_source_and_rebuilt_overlapping_test_stosb_entries(tmp_path):
    backend = _backend()
    source_program = {
        'code': _source_fixture('overlap16')[0],
        'entry_a': _ENTRY_A, 'entry_b': 0x107, 'join': 0x108,
        'size_a': 2, 'size_b': 1, 'size_join': 1,
        'address_limit': False, 'source_fixture': True,
    }
    _check_program(tmp_path / 'source', backend, source_program,
                   test_immediate=0xAA, native_label='source16')

    layout_dir = tmp_path / 'layout-input'
    layout_dir.mkdir()
    rebuilt = _compiled_program(layout_dir, 'overlap16')
    rebuilt['source_fixture'] = False
    _check_program(tmp_path / 'rebuilt', backend, rebuilt,
                   test_immediate=0xAA, native_label='rebuilt16')


def test_native_67_stosb_address_override_in_both_layouts(tmp_path):
    backend = _backend()
    source_program = {
        'code': _source_fixture('overlap32addr')[0],
        'entry_a': _ENTRY_A, 'entry_b': 0x107, 'join': 0x109,
        'size_a': 2, 'size_b': 2, 'size_join': 1,
        'address_limit': True, 'source_fixture': True,
    }
    _check_program(tmp_path / 'source', backend, source_program,
                   test_immediate=0x67, native_label='source32addr', entry_a_stores=True)

    layout_dir = tmp_path / 'layout-input'
    layout_dir.mkdir()
    rebuilt = _compiled_program(layout_dir, 'overlap32addr')
    rebuilt['source_fixture'] = False
    _check_program(tmp_path / 'rebuilt', backend, rebuilt,
                   test_immediate=0x67, native_label='rebuilt32addr', entry_a_stores=True)

    # At the 16-bit offset boundary, ordinary STOSB wraps DI while the 67
    # address-size override increments the full EDI register. The readback is
    # limited to the register effect; this boundary byte is outside the mapped
    # COM image used by the standard memory assertions above.
    ordinary = _run_entry(tmp_path / 'boundary16', backend,
                          program={
                              'code': _source_fixture('overlap16')[0],
                              'entry_a': _ENTRY_A, 'entry_b': 0x107, 'join': 0x108,
                              'size_a': 2, 'size_b': 1, 'size_join': 1,
                              'address_limit': False, 'source_fixture': True,
                          },
                          entry='B', al=0x55, df=0, destination_override=0xFFFF)
    address32 = _run_entry(tmp_path / 'boundary32', backend,
                           program=source_program, entry='B', al=0x55, df=0,
                           destination_override=0xFFFF)
    assert ordinary['edi'] == 0
    assert address32['edi'] == 0x10000


def test_native_negative_naive_concatenation_adds_an_extra_store(tmp_path):
    backend = _backend()
    source = {
        'code': _source_fixture('overlap16')[0],
        'entry_a': _ENTRY_A, 'entry_b': 0x107, 'join': 0x108,
        'size_a': 2, 'size_b': 1, 'size_join': 1,
        'address_limit': False, 'source_fixture': True,
    }
    naive = {
        'code': _source_fixture('naive_concat')[0],
        'entry_a': _ENTRY_A, 'entry_b': 0x107, 'join': 0x109,
        'size_a': 2, 'size_b': 1, 'size_join': 1,
        'address_limit': False, 'source_fixture': True,
    }
    expected = _run_entry(tmp_path / 'separate-streams', backend, program=source,
                          entry='A', al=0xAA, df=0)
    flattened = _run_entry(tmp_path / 'naive-concat', backend, program=naive,
                           entry='A', al=0xAA, df=0)
    assert expected['memory'] == _SENTINEL
    assert expected['edi'] == _DATA_IP
    assert flattened['memory'] == 0xAA
    assert flattened['edi'] == _DATA_IP + 1
    _assert_test_flags(flattened['flags'], 0xAA, 0xAA, 0)
