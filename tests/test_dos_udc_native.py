"""Native check of authored COM16 UDC output and narrowly qualified edits.

The bytecode here is a synthetic fixture. This qualifies only its declared
ready flag, register result, fixed data and near-code-pointer table in the
tested DOSBox backend; it is not a general equivalence or game-compatibility
claim.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from fdisbull.debug_state import apply_edits, register_value
from fdisbull.native_udc import capture_native_definition, native_definition_info
from fdisbull.project import Project


_SEGMENT = 0x1000
_READY = 0x0180
_RESULT = 0x0182
_POINTERS = 0x0184
_FLAGS = 0x0CD7
_ASSUMPTIONS = dict.fromkeys((
    'no_code_reads', 'no_code_writes', 'no_computed_entries',
    'address_identity_unobserved', 'timing_unobserved',
), True)
_PROJECTION = {'bindings': {'ax': '$result'}, 'inputs': [], 'outputs': ['ax']}


def _source_image(path: Path) -> bytes:
    # CMP ready,0; JE back to entry; MOV AX,17; JMP store; MOV [0182],AX; HLT.
    # The fixed region at 0180h holds ready, a word result, then a near pointer
    # to the original store block. All bytes are synthetic and authored here.
    code = bytes.fromhex('803e80010074f9b81100eb00a38201f4')
    assert len(code) == 0x10
    image = code + bytes(_READY - 0x100 - len(code))
    image += bytes.fromhex('000000000c01')
    path.write_bytes(image)
    return image


def _plan_groups(project, native_id):
    document = native_definition_info(project, native_id, include_blocks=True)['document']
    groups = document['plan']['blocks']
    root_id = next(iter(document['plan']['entries'].values()))
    root = next(g for g in groups if g['id'] == root_id)
    compute = next(g for g in groups if g['bytes'].startswith('b81100'))
    store = next(g for g in groups if g['bytes'] == 'a38201')
    halt = next(g for g in groups if g['bytes'] == 'f4')
    return document, root, compute, store, halt


def _run_to_halt(tmp_path, backend, image_path, *, expected_ax, root_ip, expected_store_ip):
    run_dir = tmp_path / image_path.stem
    run_dir.mkdir()
    guest_image = run_dir / image_path.name
    guest_image.write_bytes(image_path.read_bytes())
    with Project.create(run_dir / 'analysis.fdb', guest_image, image='com') as project:
        project.analyze()
        with project.debugger(backend, run_dir) as dos:
            # Prove the ready=0 loop takes its conditional edge, then stop at
            # the entry to release only this authored fixture's ready byte.
            branch = dos.breakpoint(f'{_SEGMENT:04x}:{root_ip + 5:04x}')
            first = dos.run(timeout_ms=5000, fast_forward=True)
            assert first['outcome'] == 'breakpoint', first
            flags_waiting = register_value(dos.registers(), 'flags')
            assert flags_waiting & 0x040
            dos.delete_breakpoint(branch['breakpoint_id'])
            entry = dos.breakpoint(f'{_SEGMENT:04x}:{root_ip:04x}')
            taken = dos.run(timeout_ms=5000, fast_forward=True)
            assert taken['outcome'] == 'breakpoint', taken
            assert int(dos.registers()['instruction_pointer'], 16) == root_ip

            before = dos.registers()
            edits = apply_edits(dos,
                [{'address': f'{_SEGMENT:04x}:{_READY:04x}',
                  'expected_hex': '00', 'data_hex': '01'}],
                {'flags': {'expected': register_value(before, 'flags'), 'value': _FLAGS}})
            assert all(e['verified'] for e in edits['memory'] + edits['registers'])
            dos.delete_breakpoint(entry['breakpoint_id'])

            halt_bp = dos.breakpoint(f'{_SEGMENT:04x}:{expected_store_ip[1]:04x}')
            stopped = dos.run(timeout_ms=5000, fast_forward=True)
            assert stopped['outcome'] == 'breakpoint', stopped
            registers = dos.registers()
            assert int(registers['instruction_pointer'], 16) == expected_store_ip[1]
            assert register_value(registers, 'eax') & 0xffff == expected_ax
            flags = register_value(registers, 'flags')
            # CMP 1,0 made the branch untaken. MOV/JMP/store preserve those
            # arithmetic flags; AF is intentionally not relied on.
            assert flags & 0x001 == 0
            assert flags & 0x004 == 0
            assert flags & 0x040 == 0
            assert flags & 0x080 == 0
            assert flags & 0x800 == 0
            assert flags & 0x400 == (_FLAGS & 0x400)
            result = dos.memory(f'{_SEGMENT:04x}:{_RESULT:04x}', length=2)
            pointer = dos.memory(f'{_SEGMENT:04x}:{_POINTERS:04x}', length=2)
            assert int.from_bytes(bytes.fromhex(result['hex']), 'little') == expected_ax
            assert int.from_bytes(bytes.fromhex(pointer['hex']), 'little') == expected_store_ip[0]
            pointed_code = dos.memory(
                f'{_SEGMENT:04x}:{expected_store_ip[0]:04x}', length=3)
            assert pointed_code['hex'] == 'a38201'
            dos.delete_breakpoint(halt_bp['breakpoint_id'])
            return {'flags_waiting': flags_waiting, 'flags_at_halt': flags,
                    'ax': register_value(registers, 'eax') & 0xffff,
                    'result_hex': result['hex'], 'pointer_hex': pointer['hex'],
                    'hlt_ip': expected_store_ip[1]}


def test_authored_com_udc_source_default_equivalent_and_experiment(tmp_path, request):
    backend = os.environ.get('FDISBULL_DOSBOX')
    if not backend:
        if request.config.getoption('--require-native'):
            pytest.fail('required DOSBox backend is missing')
        pytest.skip('Set FDISBULL_DOSBOX to run authored DOS UDC acceptance')

    source = tmp_path / 'AUTHORED.COM'
    original = _source_image(source)
    db_path = tmp_path / 'source.fdb'
    with Project.create(db_path, source, image='com') as project:
        project.analyze()
        capsule = project.code_backings([f'{_SEGMENT:04x}:0100'])
        halt_atom = next(a for a in capsule['blocks'] if a['bytes'] == 'f4')
        native = capture_native_definition(
            project, 'authored-source', [f'{_SEGMENT:04x}:0100'], split_at=[halt_atom['id']])
        document, root, compute, store, halt = _plan_groups(project, native['id'])
        assert document['capsule']['complete'] and document['plan']['complete']
        definition = project.udc_dos_define(
            'authored-com16', native['id'],
            data=[{'id': 'fixed', 'ip': _READY, 'size': 6}],
            references=[{'kind': 'near-code-pointer', 'data': 'fixed',
                         'offset': 4, 'target': store['id'], 'expected_hex': '0c01'}])
        info = project.udc_dos_info(definition['id'], include_blocks=True)
        assert info['semantic_qualification'] == 'unverified'
        assert info['document']['data'][0]['bytes'] == '000000000c01'
        equivalent = project.udc_dos_implementation(
            definition['id'], compute['id'], 'b81100b81100', compute['block_revision'],
            purpose='register-equivalence', projection=_PROJECTION)
        assert equivalent['qualification']['status'] == 'equivalent_under_assumptions'
        experimental = project.udc_dos_implementation(
            definition['id'], compute['id'], 'b82200', compute['block_revision'],
            parent=equivalent['id'])
        assert experimental['purpose'] == 'experiment'
        assert experimental['qualification']['status'] == 'unverified'

        default = project.udc_dos_compile(definition['id'], assumptions=_ASSUMPTIONS)
        proven = project.udc_dos_compile(
            definition['id'], implementations={compute['id']: equivalent['id']},
            assumptions=_ASSUMPTIONS)
        changed = project.udc_dos_compile(
            definition['id'], implementations={compute['id']: experimental['id']},
            assumptions=_ASSUMPTIONS)
        assert default['qualification'] == proven['qualification'] == changed['qualification'] == 'structural_only'
        assert all(not result['native_execution'] for result in (default, proven, changed))
        assert proven['implementations'][compute['id']]['qualification']['status'] == 'equivalent_under_assumptions'
        assert changed['implementations'][compute['id']]['qualification']['status'] == 'unverified'
        assert len({default['sha256'], proven['sha256'], changed['sha256']}) == 3
        for result in (default, proven, changed):
            assert int.from_bytes(bytes.fromhex(result['bytes'])[_POINTERS - 0x100:_POINTERS - 0x100 + 2], 'little') == result['ports'][store['id']]

    images = {}
    for label, result in (('default', default), ('equivalent', proven), ('experimental', changed)):
        path = tmp_path / f'{label}.COM'
        path.write_bytes(bytes.fromhex(result['bytes']))
        images[label] = path
    assert source.read_bytes() == original

    # The same authored inputs are replayed in isolated sessions. The proof is
    # only the declared AX result; flags, memory side effects, branches and
    # runtime behavior remain separately measured below.
    results = {
        'source': _run_to_halt(tmp_path, backend, source, expected_ax=0x11,
                               root_ip=0x100, expected_store_ip=(0x10c, 0x10f)),
        'default': _run_to_halt(tmp_path, backend, images['default'], expected_ax=0x11,
                                root_ip=default['ports'][root['id']],
                                expected_store_ip=(default['ports'][store['id']], default['ports'][halt['id']])),
        'equivalent': _run_to_halt(tmp_path, backend, images['equivalent'], expected_ax=0x11,
                                   root_ip=proven['ports'][root['id']],
                                   expected_store_ip=(proven['ports'][store['id']], proven['ports'][halt['id']])),
        'experimental': _run_to_halt(tmp_path, backend, images['experimental'], expected_ax=0x22,
                                     root_ip=changed['ports'][root['id']],
                                     expected_store_ip=(changed['ports'][store['id']], changed['ports'][halt['id']])),
    }
    assert all(item['flags_waiting'] & 0x040 for item in results.values())
    assert all(not item['flags_at_halt'] & 0x040 for item in results.values())
    assert source.read_bytes() == original
