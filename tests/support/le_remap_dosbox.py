"""Independent stopped-instruction DOSBox-X oracle for the LE remap fixture.

This worker owns its emulator and preserves a real DOS-entry shutdown state.
It deliberately walks page tables and decodes descriptors without fDisBull's
QEMU translation or source-matching helpers.
"""

import json
import os
from pathlib import Path
import re
import sys

from iced_x86 import Decoder
from fdisbull.project import Project
from support.doom_le_dosbox import read
from support.le_translation_native import integer, register


def _reach_start(debug, cfg):
    cs, ip = integer(cfg['start_cs']), integer(cfg['start_ip'])
    # The guest eventually loops through its authored protected code. A timed
    # stop first ensures its descriptor tables exist before setting a breakpoint.
    for _ in range(40):
        op = debug.call('execution.continue')
        wait = debug.call('execution.wait', dict(operation_id=op['operation_id'], timeout_ms=60))
        if wait.get('running'):
            op = debug.call('execution.pause')
            debug.call('execution.wait', dict(operation_id=op['operation_id'], timeout_ms=2000))
        regs = debug.registers()
        if (
            regs['cpu_mode'] == 'protected'
            and regs['code_bits'] == 32
            and integer(regs['cs']) in (cs, integer(cfg['selector_b']))
        ):
            break
    else:
        raise AssertionError(('DOSBox did not reach protected mode', regs))
    if (integer(regs['cs']), integer(regs['ip'])) == (cs, ip):
        return
    bp = debug.call(
        'breakpoints.create',
        dict(
            kind='execution',
            once=True,
            address=dict(space='segmented', segment=f'0x{cs:04x}', offset=f'0x{ip:08x}'),
        ),
    )
    op = debug.call('execution.continue')
    stop = debug.call('execution.wait', dict(operation_id=op['operation_id'], timeout_ms=5000))
    assert stop['stop_reason']['breakpoint_id'] == bp['breakpoint_id'], stop
    regs = debug.registers()
    assert (integer(regs['cs']), integer(regs['ip'])) == (cs, ip), regs


def observation(debug):
    """Read and cross-check an instruction at one stopped protected boundary."""
    regs = debug.registers()
    assert regs['cpu_mode'] == 'protected' and regs['code_bits'] == 32
    cs, ip = integer(regs['cs']), integer(regs['ip'])
    controls = regs['address_context']
    assert controls['a20_enabled']
    paging = controls['paging_enabled']
    cr3 = integer(controls['cr3'])
    evidence = []

    def physical(address, length):
        data = read(debug, 'physical', address, length)
        evidence.append(('physical', address, length, None, data))
        return data

    def walk(linear):
        if not paging:
            return linear
        pde = int.from_bytes(physical((cr3 & 0xFFFFF000) + (linear >> 22) * 4, 4), 'little')
        assert pde & 1
        if pde & 0x80:
            return (pde & 0xffc00000) + (linear & 0x3fffff)
        pte = int.from_bytes(physical((pde & 0xFFFFF000) + ((linear >> 12) & 1023) * 4, 4), 'little')
        assert pte & 1
        return (pte & 0xFFFFF000) + (linear & 4095)

    def checked_linear(address, length):
        data = read(debug, 'linear', address, length)
        evidence.append(('linear', address, length, None, data))
        backing = [walk(address + i) for i in range(length)]
        actual = bytes(physical(p, 1)[0] for p in backing)
        assert data == actual
        return data, backing

    def desc(base, limit, selector):
        index = selector & 0xFFF8
        assert index + 7 <= limit
        raw, _ = checked_linear(base + index, 8)
        address = int.from_bytes(raw[2:4], 'little') | raw[4] << 16 | raw[7] << 24
        bound = int.from_bytes(raw[:2], 'little') | (raw[6] & 15) << 16
        return address, ((bound << 12) | 4095) if raw[6] & 128 else bound, raw

    diagnostic = debug.call('debugger.execute_command', {'command': 'CPU'})['raw_output']
    (gdt,) = re.findall(r'^GDT base=([0-9a-fA-F]+) limit=([0-9a-fA-F]+)$', diagnostic, re.M)
    gbase, glimit = (int(v, 16) for v in gdt)
    (ldt,) = re.findall(
        r'^LDT selector=([0-9a-fA-F]+), base=([0-9a-fA-F]+) limit=([0-9a-fA-F]+)\*1$', diagnostic, re.M
    )
    ldtr, lbase, llimit = (int(v, 16) for v in ldt)
    base, limit = gbase, glimit
    if cs & 4:
        pbase, plimit, parent = desc(gbase, glimit, ldtr)
        assert parent[5] & 0x9F == 0x82 and (pbase, plimit) == (lbase, llimit)
        base, limit = lbase, llimit
    cs_base, cs_limit, descriptor = desc(base, limit, cs)
    assert descriptor[5] & 0x98 == 0x98 and descriptor[6] & 0x40
    assert ip <= cs_limit and cs_base + ip <= 0xFFFFFFFF
    pc = cs_base + ip
    length = min(15, cs_limit - ip + 1, 0x100000000 - pc)
    data, backing = checked_linear(pc, length)
    segmented = read(debug, 'segmented', ip, length, cs)
    evidence.append(('segmented', ip, length, cs, segmented))
    assert segmented == data
    decoded = Decoder(32, data, ip=ip).decode()
    assert not decoded.is_invalid and decoded.len <= length
    # Repeat all observed bytes and registers after page walks and descriptor reads.
    for space, address, count, selector, expected in evidence:
        assert read(debug, space, address, count, selector) == expected
    assert debug.registers() == regs
    return dict(
        cs=cs,
        ip=ip,
        cs_base=cs_base,
        cs_limit=cs_limit,
        pc=pc,
        hex=data[: decoded.len].hex(),
        backing=backing[: decoded.len],
        descriptor=descriptor.hex(),
        ldtr_selector=ldtr,
        paging=paging,
        esi=register(regs, 'si'),
    )


def run(stage, phase, *, assisted=False):
    stage = Path(stage)
    assert phase in ('before', 'after')
    cfg = json.loads((stage / 'config.json').read_text())
    source = Path(cfg['source'])
    count, checkpoint_index = integer(cfg['boundaries']), integer(cfg['checkpoint_index'])
    assert 0 <= checkpoint_index < count
    owners = []
    def observed_load(debug, artifact, label):
        observed = []
        original = debug.registers
        def capture(*args, **kwargs):
            value = original(*args, **kwargs)
            observed.append(value.get('address_context'))
            return value
        debug.registers = capture
        try:
            return debug.load_state(artifact)
        finally:
            debug.registers = original
            (stage / f'dosbox-{phase}-{label}-{'guest-primed' if assisted else 'unassisted'}-observed.json').write_text(
                json.dumps(observed, indent=2))
    with (
        Project.create(stage / 'dosbox.fdb', source, image='mz')
        if phase == 'before'
        else Project(stage / 'dosbox.fdb') as project
    ):
        with project.debugger(
            os.environ['FDISBULL_DOSBOX'], source.parent, _on_spawn=owners.append
        ) as debug:
            entry_context = debug.registers().get('address_context')
            entry = debug.save_state('dos-entry.sav')['artifact']
            if phase == 'before':
                _reach_start(debug, cfg)
                assert observation(debug)['pc'] == integer(cfg['start_pc'])
                start, checkpoint = 0, None
            else:
                checkpoint = json.loads((stage / 'dosbox-before.json').read_text())['checkpoint']
                if assisted:
                    _reach_start(debug, cfg)  # Assisted setup before checkpoint restore.
                observed_load(debug, checkpoint, 'checkpoint')
                start = checkpoint_index
            events = []
            for index in range(start, count):
                if phase == 'before' and index == checkpoint_index:
                    checkpoint_context = debug.registers().get('address_context')
                    checkpoint = debug.save_state()['artifact']
                events.append(observation(debug))
                if index + 1 < count:
                    debug.call('execution.step', {'mode': 'into'})
            # Preserve observed boundaries even if the subsequent shutdown restore fails.
            probe = read(debug, 'physical', 0x1f0000, 8).hex() if cfg.get('paging_mode') == 'legacy-4m' else None
            partial = dict(checkpoint=checkpoint, events=events, status='before-shutdown-restore', cpu_probe=probe, entry_context=entry_context, checkpoint_context=checkpoint_context if phase == 'before' else None)
            (stage / ('dosbox-' + phase + '-partial.json')).write_text(json.dumps(partial, indent=2))
            observed_load(debug, entry, 'entry')
            assert debug.registers()['cpu_mode'] == 'real'
    exits = [owner.poll() for owner in owners]
    assert exits and all(code == 0 for code in exits), exits
    result = dict(checkpoint=checkpoint, events=events, owners=exits)
    (stage / ('dosbox-' + phase + '.json')).write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    run(Path(sys.argv[1]), sys.argv[2], assisted=len(sys.argv) == 4 and sys.argv[3] == 'guest-paging')
