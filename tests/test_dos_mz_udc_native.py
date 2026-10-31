"""Native acceptance of the authored COM-layout MZ output scaffold.

The fixture is synthetic. This test qualifies the emitted startup shim,
single-segment relocation, fixed data and selected code paths only; it is not an
arbitrary MZ linker or game-compatibility claim.
"""
from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest

from fdisbull.debug_state import apply_edits, register_value
from fdisbull.native_udc import capture_native_definition
from fdisbull.project import Project
from tests.test_dos_udc_native import (
    _ASSUMPTIONS,
    _FLAGS,
    _POINTERS,
    _READY,
    _RESULT,
    _plan_groups,
    _source_image,
)

_STATIC_SEGMENT = 0x1000


def _run_mz(tmp_path, backend, image_path: Path, *, expected_ax: int,
            root_ip: int, expected_store_ip: tuple[int, int]):
    run_dir = tmp_path / image_path.stem
    run_dir.mkdir()
    guest_image = run_dir / image_path.name
    guest_image.write_bytes(image_path.read_bytes())

    with Project.create(run_dir / 'analysis.fdb', guest_image) as project:
        project.analyze()
        with project.debugger(backend, run_dir, version=1) as dos:
            initial = dos.registers()
            runtime_cs = register_value(initial, 'cs')
            assert int(initial['instruction_pointer'], 16) == 0x00f7
            assert register_value(initial, 'ss') == runtime_cs
            assert register_value(initial, 'esp') & 0xffff == 0xfffe
            initial_ax = register_value(initial, 'eax') & 0xffff
            initial_flags = register_value(initial, 'flags')

            # The emitted stub saves AX, initializes DS and ES from the
            # loader-relocated CS immediate, and restores AX before COM entry.
            entered = dos.breakpoint(f'{_STATIC_SEGMENT:04x}:0100')
            stopped = dos.run(timeout_ms=5000, fast_forward=True)
            assert stopped['outcome'] == 'breakpoint', stopped
            at_com_entry = dos.registers()
            assert int(at_com_entry['instruction_pointer'], 16) == 0x0100
            assert register_value(at_com_entry, 'eax') & 0xffff == initial_ax
            assert register_value(at_com_entry, 'flags') == initial_flags
            assert register_value(at_com_entry, 'esp') & 0xffff == 0xfffe
            for name in ('cs', 'ds', 'es', 'ss'):
                assert register_value(at_com_entry, name) == runtime_cs
            relocation = dos.memory(f'{_STATIC_SEGMENT:04x}:00f9', length=2)
            assert int.from_bytes(bytes.fromhex(relocation['hex']), 'little') == runtime_cs
            dos.delete_breakpoint(entered['breakpoint_id'])

            # The authored ready flag is initially zero, so the source loop's
            # conditional edge is taken. Release it only after observing that
            # edge, then stop before the store block's terminating HLT.
            branch = dos.breakpoint(f'{_STATIC_SEGMENT:04x}:{root_ip + 5:04x}')
            first = dos.run(timeout_ms=5000, fast_forward=True)
            assert first['outcome'] == 'breakpoint', first
            flags_waiting = register_value(dos.registers(), 'flags')
            assert flags_waiting & 0x040
            dos.delete_breakpoint(branch['breakpoint_id'])

            entry = dos.breakpoint(f'{_STATIC_SEGMENT:04x}:{root_ip:04x}')
            taken = dos.run(timeout_ms=5000, fast_forward=True)
            assert taken['outcome'] == 'breakpoint', taken
            assert int(dos.registers()['instruction_pointer'], 16) == root_ip
            before = dos.registers()
            edits = apply_edits(
                dos,
                [{'address': f'{_STATIC_SEGMENT:04x}:{_READY:04x}',
                  'expected_hex': '00', 'data_hex': '01'}],
                {'flags': {'expected': register_value(before, 'flags'),
                           'value': _FLAGS}},
            )
            assert all(e['verified'] for e in edits['memory'] + edits['registers'])
            dos.delete_breakpoint(entry['breakpoint_id'])

            halt = dos.breakpoint(f'{_STATIC_SEGMENT:04x}:{expected_store_ip[1]:04x}')
            finished = dos.run(timeout_ms=5000, fast_forward=True)
            assert finished['outcome'] == 'breakpoint', finished
            registers = dos.registers()
            assert int(registers['instruction_pointer'], 16) == expected_store_ip[1]
            assert register_value(registers, 'eax') & 0xffff == expected_ax
            flags = register_value(registers, 'flags')
            assert flags & 0x001 == 0
            assert flags & 0x004 == 0
            assert flags & 0x040 == 0
            assert flags & 0x080 == 0
            assert flags & 0x800 == 0
            assert flags & 0x400 == (_FLAGS & 0x400)

            result = dos.memory(f'{_STATIC_SEGMENT:04x}:{_RESULT:04x}', length=2)
            pointer = dos.memory(f'{_STATIC_SEGMENT:04x}:{_POINTERS:04x}', length=2)
            assert int.from_bytes(bytes.fromhex(result['hex']), 'little') == expected_ax
            assert int.from_bytes(bytes.fromhex(pointer['hex']), 'little') == expected_store_ip[0]
            store_bytes = dos.memory(
                f'{_STATIC_SEGMENT:04x}:{expected_store_ip[0]:04x}', length=3)
            assert store_bytes['hex'] == 'a38201'
            dos.delete_breakpoint(halt['breakpoint_id'])
            return {
                'runtime_cs': runtime_cs,
                'initial_ax': initial_ax,
                'initial_flags': initial_flags,
                'flags_waiting': flags_waiting,
                'flags_at_pre_hlt': flags,
                'ax': register_value(registers, 'eax') & 0xffff,
                'result_hex': result['hex'],
                'pointer_hex': pointer['hex'],
                'store_bytes': store_bytes['hex'],
            }


def test_authored_com_layout_mz_startup_default_equivalent_and_experiment(tmp_path, request):
    backend = os.environ.get('FDISBULL_DOSBOX')
    if not backend:
        if request.config.getoption('--require-native'):
            pytest.fail('required DOSBox backend is missing')
        pytest.skip('Set FDISBULL_DOSBOX to run authored MZ UDC acceptance')

    source = tmp_path / 'AUTHORED.COM'
    original = _source_image(source)
    with Project.create(tmp_path / 'source.fdb', source, image='com') as project:
        project.analyze()
        capsule = project.code_backings(['1000:0100'])
        halt_atom = next(a for a in capsule['blocks'] if a['bytes'] == 'f4')
        native = capture_native_definition(
            project, 'authored-mz-source', ['1000:0100'], split_at=[halt_atom['id']])
        document, root, compute, store, halt = _plan_groups(project, native['id'])
        assert document['capsule']['complete'] and document['plan']['complete']
        definition = project.udc_dos_define(
            'authored-mz-layout', native['id'],
            data=[{'id': 'fixed', 'ip': _READY, 'size': 6}],
            references=[{'kind': 'near-code-pointer', 'data': 'fixed',
                         'offset': 4, 'target': store['id'], 'expected_hex': '0c01'}])
        info = project.udc_dos_info(definition['id'], include_blocks=True)
        assert info['document']['data'][0]['bytes'] == '000000000c01'

        equivalent = project.udc_dos_implementation(
            definition['id'], compute['id'], 'b81100b81100', compute['block_revision'],
            purpose='register-equivalence',
            projection={'bindings': {'ax': '$result'}, 'inputs': [], 'outputs': ['ax']})
        experimental = project.udc_dos_implementation(
            definition['id'], compute['id'], 'b82200', compute['block_revision'],
            parent=equivalent['id'])
        assert equivalent['qualification']['status'] == 'equivalent_under_assumptions'
        assert experimental['qualification']['status'] == 'unverified'

        results = {
            'default': project.udc_dos_compile(
                definition['id'], assumptions=_ASSUMPTIONS, container='mz'),
            'equivalent': project.udc_dos_compile(
                definition['id'], implementations={compute['id']: equivalent['id']},
                assumptions=_ASSUMPTIONS, container='mz'),
            'experimental': project.udc_dos_compile(
                definition['id'], implementations={compute['id']: experimental['id']},
                assumptions=_ASSUMPTIONS, container='mz'),
        }
        assert all(result['qualification'] == 'structural_only'
                   and result['native_execution'] is False
                   for result in results.values())
        assert len({result['sha256'] for result in results.values()}) == 3
        for result in results.values():
            raw = bytes.fromhex(result['bytes'])
            assert raw[:2] == b'MZ'
            assert struct.unpack_from('<H', raw, 0x1c)[0] == 0x00f9
            assert raw[0x20 + 0xf7:0x20 + 0x100] == bytes.fromhex('50b800008ed88ec058')
            module = raw[0x20:]
            assert int.from_bytes(module[0xf9:0xfb], 'little') == 0
            assert result['container']['initial_ip'] == 0x00f7
            assert result['container']['initial_sp'] == 0xfffe
            assert int.from_bytes(module[_POINTERS:_POINTERS + 2], 'little') == result['ports'][store['id']]

    images = {}
    for label, result in results.items():
        path = tmp_path / f'{label}.EXE'
        path.write_bytes(bytes.fromhex(result['bytes']))
        images[label] = path
    assert source.read_bytes() == original

    observed = {}
    for label, result in results.items():
        expected_ax = 0x22 if label == 'experimental' else 0x11
        observed[label] = _run_mz(
            tmp_path, backend, images[label], expected_ax=expected_ax,
            root_ip=result['ports'][root['id']],
            expected_store_ip=(result['ports'][store['id']], result['ports'][halt['id']]))
    assert all(item['flags_waiting'] & 0x040 for item in observed.values())
    assert all(not item['flags_at_pre_hlt'] & 0x040 for item in observed.values())
    assert source.read_bytes() == original
