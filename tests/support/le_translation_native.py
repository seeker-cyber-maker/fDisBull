"""Native comparison worker. Each invocation owns and closes its own emulator."""

import json
import os
from pathlib import Path
import re
import sys

from fdisbull.project import Project
from support.doom_le_dosbox import read as dos_read


def integer(value):
    return int(value, 0) if isinstance(value, str) else value


def register(regs, name):
    values = regs.get('general', regs.get('registers'))
    return integer(values.get('r' + name, values.get('e' + name))) & 0xFFFFFFFF


def dosbox_at_instruction(debug, expected):
    # The authored loader repeatedly executes the target. Install the segmented
    # breakpoint only after the guest loaded the target descriptor table.
    for _ in range(20):
        op = debug.call('execution.continue')
        run = debug.call('execution.wait', dict(operation_id=op['operation_id'], timeout_ms=60))
        assert run.get('running'), run
        op = debug.call('execution.pause')
        debug.call('execution.wait', dict(operation_id=op['operation_id'], timeout_ms=2000))
        regs = debug.registers()
        if (
            regs['cpu_mode'] == 'protected'
            and regs['code_bits'] == 32
            and integer(regs['cs']) == expected['selector']
            and expected['ip'] <= integer(regs['ip']) < expected['ip'] + 9
        ):
            break
    else:
        raise AssertionError(('DOSBox did not reach the authored loop', regs))
    if integer(regs['ip']) != expected['ip']:
        bp = debug.call(
            'breakpoints.create',
            dict(
                kind='execution',
                once=True,
                address=dict(
                    space='segmented',
                    segment=f"0x{expected['selector']:04x}",
                    offset=f"0x{expected['ip']:08x}",
                ),
            ),
        )
        op = debug.call('execution.continue')
        stop = debug.call('execution.wait', dict(operation_id=op['operation_id'], timeout_ms=3000))
        assert stop['stop_reason']['breakpoint_id'] == bp['breakpoint_id']


def dosbox_reference(debug, expected):
    regs = debug.registers()
    cs, ip = integer(regs['cs']), integer(regs['ip'])
    assert (cs, ip) == (expected['selector'], expected['ip'])
    control = regs['address_context']
    assert control['a20_enabled'] and control['paging_enabled'] == expected['paging']
    cr3 = integer(control['cr3'])

    def walk(linear):
        if not control['paging_enabled']:
            return linear, {}

        def word(address):
            return int.from_bytes(dos_read(debug, 'physical', address, 4), 'little')

        pde_address = (cr3 & 0xFFFFF000) + (linear >> 22) * 4
        pde = word(pde_address)
        assert pde & 1 and not pde & 0x80
        pte_address = (pde & 0xFFFFF000) + (linear >> 12 & 1023) * 4
        pte = word(pte_address)
        assert pte & 1
        return (pte & 0xFFFFF000) + (linear & 4095), dict(
            pde_address=pde_address, pte_address=pte_address, pde=pde, pte=pte
        )

    def desc(base, limit, selector):
        idx = selector & 0xFFF8
        assert idx + 7 <= limit
        raw = dos_read(debug, 'linear', base + idx, 8)
        assert raw == dos_read(debug, 'physical', walk(base + idx)[0], 8)
        address = int.from_bytes(raw[2:4], 'little') | raw[4] << 16 | raw[7] << 24
        bound = int.from_bytes(raw[:2], 'little') | (raw[6] & 15) << 16
        return address, ((bound << 12) | 4095) if raw[6] & 128 else bound, raw

    diagnostic = debug.call('debugger.execute_command', {'command': 'CPU'})['raw_output']
    (gdt,) = re.findall(r'^GDT base=([0-9a-fA-F]+) limit=([0-9a-fA-F]+)$', diagnostic, re.M)
    base, limit = [int(v, 16) for v in gdt]
    ldtr = 0
    if cs & 4:
        (row,) = re.findall(
            r'^LDT selector=([0-9a-fA-F]+), base=([0-9a-fA-F]+) limit=([0-9a-fA-F]+)\*1$',
            diagnostic,
            re.M,
        )
        ldtr, lbase, llimit = [int(v, 16) for v in row]
        table_base, table_limit, parent = desc(base, limit, ldtr)
        assert parent[5] & 0x9F == 0x82
        assert (lbase, llimit) == (table_base, table_limit)
        base, limit = lbase, llimit
    code_base, code_limit, raw_desc = desc(base, limit, cs)
    assert raw_desc[5] & 0x98 == 0x98 and raw_desc[6] & 0x40 and ip + 4 <= code_limit
    pc = code_base + ip
    assert pc == expected['pc']
    whole = dos_read(debug, 'segmented', ip, 5, cs)
    assert whole == dos_read(debug, 'linear', pc, 5)
    slices = []
    for consumed, count in ((0, 2), (2, 3)):
        address, tables = walk(pc + consumed)
        assert whole[consumed : consumed + count] == dos_read(debug, 'physical', address, count)
        slices.append(dict(linear=pc + consumed, length=count, physical=address, **tables))
    assert debug.registers() == regs
    return dict(
        bytes=whole.hex(),
        cs=cs,
        cs_base=code_base,
        ip=ip,
        cs_limit=code_limit,
        access=raw_desc[5],
        flags=raw_desc[6] >> 4,
        paging=control['paging_enabled'],
        selector_table='ldt' if cs & 4 else 'gdt',
        ldtr_selector=ldtr,
        instruction_segments=slices,
    )


def run(stage, backend, phase):
    cfg = json.loads((stage / 'config.json').read_text())
    source = Path(cfg['source'])
    db = stage / (backend + '.fdb')
    is_qemu = backend == 'qemu'
    options = (
        dict(
            backend='qemu-dos',
            dos_boot_image=str(stage / 'boot.img'),
            dos_mcopy=os.environ['FDISBULL_QEMU_DOS_MCOPY'],
            dos_startup_batch='FDAUTO.BAT',
            qemu_transport='pipe',
            qemu_firmware=os.environ['FDISBULL_QEMU_DOS_FIRMWARE'],
            qemu_checkpoint_tool=os.environ['FDISBULL_QEMU_IMG'],
        )
        if is_qemu
        else {}
    )
    executable = os.environ['FDISBULL_QEMU_DOS' if is_qemu else 'FDISBULL_DOSBOX']
    before_file = stage / (backend + '-before.json')
    owners = []
    with Project.create(db, source, image='mz') if phase == 'before' else Project(db) as project:
        with project.debugger(executable, source.parent, _on_spawn=owners.append, **options) as debug:
            # The fixture owns private page and descriptor tables while running.
            # DOSBox-X's host stop returns through DOS, which needs its real-mode context.
            if not is_qemu:
                dos_entry = debug.save_state('dos-entry.sav')['artifact']
            if phase == 'before':
                if is_qemu:
                    bp = debug.breakpoint(cfg['pc'])['breakpoint_id']
                    stop = debug.run(timeout_ms=8000)
                    assert (
                        stop['outcome'] == 'breakpoint'
                        and bp in stop['session']['stop_reason']['breakpoint_ids']
                    ), stop
                    debug.delete_breakpoint(bp)
                    state = debug.save_machine_state()['artifact']
                else:
                    dosbox_at_instruction(debug, cfg)
                    state = debug.save_state()['artifact']
            else:
                state = json.loads(before_file.read_text())['checkpoint']
                if is_qemu:
                    restored = debug.load_machine_state(state, timeout_ms=60000)
                    assert (
                        restored['machine_state_restored'] and not restored['protected_source_rebound']
                    )
                else:
                    debug.load_state(state)
            if is_qemu:
                assert integer(debug.registers()['linear_pc']) == cfg['pc']
                captured = debug.capture_code(cfg['pc'], space='linear', length=5, view='execute')
                assert captured['metadata']['offline_analysis'] == 'qualified-paged-le-source-capture'
                artifact = captured['artifact']
                next_artifact = debug.capture_code(cfg['pc'] + 5, space='linear', length=2, view='ram')[
                    'artifact'
                ]
                read_data = lambda: int.from_bytes(
                    bytes.fromhex(debug.memory(cfg['target'], length=4, space='virtual')['hex']),
                    'little',
                )
                step = debug.step
            else:
                observation = dosbox_reference(debug, cfg)
                read_data = lambda: int.from_bytes(dos_read(debug, 'linear', cfg['target'], 4), 'little')
                step = lambda: debug.call('execution.step', {'mode': 'into'})
            counter = read_data()
            step()
            assert register(debug.registers(), 'ax') == cfg['target']
            step()
            assert read_data() == (counter + 1) & 0xFFFFFFFF
            if not is_qemu:
                debug.load_state(dos_entry)
                assert debug.registers()['cpu_mode'] == 'real'
    exit_codes = [owner.poll() for owner in owners]
    assert exit_codes and all(code == 0 for code in exit_codes), exit_codes
    if is_qemu:
        with Project(db) as offline:
            a = offline.debug_analyze_le_code(artifact)
            (fixup,) = a['fixups']
            assert fixup['target_object'] == 2 and a['source_location']['object_offset'] == cfg['offset']
            assert len(fixup['source_file_fragments']) == 2 and not a['execution_proven']
            observation = dict(
                bytes=a['runtime_bytes'],
                cs=a['selector']['cs'],
                cs_base=a['selector']['cs_base'],
                ip=integer(a['instruction_selector_offset']),
                cs_limit=a['selector']['cs_limit'],
                access=(a['selector']['cs_attributes'] >> 8) & 255,
                flags=(a['selector']['cs_attributes'] >> 20) & 15,
                **a['address_translation'],
            )
            observation.update(
                artifact=artifact,
                run=a['run'],
                canonical=a['canonical_bytes'],
                source=a['source_sha256'],
                fixup=fixup,
            )
            next_analysis = offline.debug_analyze_le_code(next_artifact)
            assert next_analysis['runtime_bytes'] == 'ff00' and next_analysis['fixups'] == []
            assert next_analysis['selector']['ip'] == cfg['ip']
            assert integer(next_analysis['instruction_selector_offset']) == cfg['ip'] + 5
            assert next_analysis['source_location']['object_offset'] == cfg['offset'] + 5
            assert len(offline.versions()) == 1
    result = dict(checkpoint=state, counter=counter, observation=observation)
    (stage / (backend + '-' + phase + '.json')).write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    run(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
