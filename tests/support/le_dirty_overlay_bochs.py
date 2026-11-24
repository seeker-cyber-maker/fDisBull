"""Independent Bochs live and unprimed-restore oracle for dirty overlay writes.

The stage config contains source, sha256, paging_mode and dirty_write_offsets;
boot.img is a DOS baseline. The checkpoint is taken before unrelated_store.
Bochs has no overlay here: these observations qualify guest RAM effects only.
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

from support.le_remap_bochs import Bochs, prepare_bochs_media, walk_linear


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _observation(debug, offsets, pc, paging_mode):
    context = debug.context()
    assert context['cs_base'] + context['ip'] == pc, (context, pc)
    assert context['cr0'] & 0x80000001 == 0x80000001
    pae = paging_mode != 'pse36-4m-high'
    assert bool(context['cr4'] & 0x20) == pae
    if not pae:
        assert context['cr4'] & 0x10
    values = {}
    for name in ('unrelated', 'watched', 'sentinel'):
        linear = offsets[name]
        physical, page_size, walk = walk_linear(debug, context, linear)
        expected_size = {'pae-4k-high': 0x1000, 'pae-2m-high': 0x200000,
                         'pse36-4m-high': 0x400000}[paging_mode]
        assert page_size == expected_size
        entries = [entry['value'] for entry in walk]
        assert physical >= 2**32
        page = debug.cmd(f'page {linear:#x}')
        match = re.search(r'linear page 0x([0-9a-fA-F]+) maps to physical page 0x([0-9a-fA-F]+)', page)
        assert match and int(match[1], 16) == linear & ~0xfff, page
        assert int(match[2], 16) + (linear & 0xfff) == physical, page
        raw = debug.read(linear, 1)
        assert raw == debug.read(physical, 1, physical=True)
        values[name] = dict(linear=linear, physical=physical, hex=raw.hex(), entries=entries)
    assert len({v['physical'] & ~0xfff for v in values.values()}) == 1
    return dict(context=context, pc=pc, values=values)


def run(stage, phase):
    stage = Path(stage).resolve()
    assert phase in ('before', 'after')
    cfg = json.loads((stage / 'config.json').read_text())
    assert cfg['paging_mode'] in ('pse36-4m-high', 'pae-4k-high', 'pae-2m-high')
    offsets = cfg['dirty_write_offsets']
    source = Path(cfg['source'])
    assert _hash(source) == cfg['sha256']
    binary = Path(os.environ['FDISBULL_BOCHS']).resolve(strict=True)
    share = Path(os.environ.get('FDISBULL_BOCHS_SHARE', binary.parent.parent / 'share' / 'bochs'))
    disk = stage / 'dirty-bochs.img'
    checkpoint = stage / 'dirty-bochs-state'
    receipt = stage / 'dirty-bochs-before.json'
    if phase == 'before':
        disk, config = prepare_bochs_media(
            stage, source, share, True, disk_name='dirty-bochs.img',
            batch_name='dirty-bochs-auto.bat', config_name='dirty-bochsrc',
            log_name='dirty-bochs.log')
        args = [str(binary), '-q', '-debugger', '-f', str(config)]
    else:
        prior = json.loads(receipt.read_text())
        assert prior['binary_sha256'] == _hash(binary) and prior['media_sha256'] == _hash(disk)
        args = [str(binary), '-q', '-debugger', '-r', str(checkpoint)]
    debug = Bochs(args)
    try:
        initial_context = debug.context()
        if phase == 'before':
            debug.cmd(f"lb {offsets['unrelated_store']:#x}")
            stopped = debug.cmd('c')
            assert 'Breakpoint' in stopped, stopped
            debug.cmd('d 1')
        else:
            # Inspect only; do not execute an instruction before this check.
            assert debug.proc.pid != prior['pid']
            assert initial_context == prior['checkpoint_context']
        first = _observation(debug, offsets, offsets['unrelated_store'], cfg['paging_mode'])
        initial_watched = '77' if 'atomic_target' in offsets else '90'
        assert {k: v['hex'] for k, v in first['values'].items()} == {
            'unrelated': '90', 'watched': initial_watched, 'sentinel': '90'}
        if phase == 'before':
            checkpoint.mkdir()
            saved = debug.cmd(f'restore "__save_state__" "{checkpoint}"')
            assert 'native save state' in saved and ': OK' in saved, saved
        if 'atomic_target' in offsets:
            compare_sites = {offsets[name]: name for name in
                             ('cmp_failed', 'cmp_succeeded', 'cmp_same')}
            seen = []
            steps = {}
            spans = {}
            for name, linear, count in (
                ('atomic', offsets['atomic_target'], 8),
                ('split', offsets['split_target'], 4),
            ):
                spans[name] = [walk_linear(debug, first['context'], linear + i)[0]
                               for i in range(count)]
                assert [debug.read(physical, 1, physical=True)[0]
                        for physical in spans[name]] == list(debug.read(linear, count))

            low_aliases = {
                name: bytes(debug.read(address & 0xffffffff, 1, physical=True)[0]
                            for address in addresses).hex()
                for name, addresses in spans.items()
            }

            def batch_step(name):
                debug.cmd('s')
                state = debug.context()
                regs = debug.cmd('regs')

                def reg(pattern):
                    found = re.search(pattern, regs, re.MULTILINE)
                    assert found, (pattern, regs)
                    return int(found.group(1).replace('_', ''), 16)

                pc_after = state['cs_base'] + state['ip']
                return dict(
                    pc=pc_after,
                    atomic=debug.read(offsets['atomic_target'], 8).hex(),
                    split=debug.read(offsets['split_target'], 4).hex(),
                    sentinel=debug.read(offsets['sentinel'], 1).hex(),
                    eax=reg(r'^rax:\s*([0-9a-fA-F_]+)') & 0xffffffff,
                    edx=reg(r'^rdx:\s*([0-9a-fA-F_]+)') & 0xffffffff,
                    zf=bool(reg(r'^eflags(?:\s*:|)\s*(?:0x)?([0-9a-fA-F_]+)') & (1 << 6)),
                )

            pc = offsets['unrelated_store']
            for _ in range(160):
                if pc == offsets['sentinel_store']:
                    break
                if pc in compare_sites:
                    name = compare_sites[pc]
                    seen.append(name)
                    steps[name] = batch_step(name)
                elif pc == offsets['split_store']:
                    steps['split_store'] = batch_step('split_store')
                else:
                    debug.cmd('s')
                context = debug.context()
                pc = context['cs_base'] + context['ip']
            assert pc == offsets['sentinel_store'], hex(pc)
            assert seen == ['cmp_failed', 'cmp_succeeded', 'cmp_same'], seen
            assert debug.read(offsets['atomic_target'], 8).hex() == '1122334455667788'
            assert debug.read(offsets['split_target'], 4).hex() == 'd4c3b2a1'
            flags = [int.from_bytes(debug.read(offsets['atomic_result_flags'] + i * 4, 4), 'little')
                     for i in range(3)]
            eax = [int.from_bytes(debug.read(offsets['atomic_result_eax'] + i * 4, 4), 'little')
                   for i in range(3)]
            edx = [int.from_bytes(debug.read(offsets['atomic_result_edx'] + i * 4, 4), 'little')
                   for i in range(3)]
            assert [bool(value & (1 << 6)) for value in flags] == [False, True, True]
            assert eax == [0x55667788, 0x55667788, 0x44332211]
            assert edx == [0x11223344, 0x11223344, 0x88776655]
            final = _observation(debug, offsets, offsets['sentinel_store'], cfg['paging_mode'])
            observation = dict(final=final, flags=flags, eax=eax, edx=edx,
                               split=debug.read(offsets['split_target'], 4).hex(),
                               atomic=debug.read(offsets['atomic_target'], 8).hex(),
                               backing=spans, low_aliases=low_aliases, steps=steps, seen=seen)
            if phase == 'after':
                assert observation == prior['observations']
        elif 'cmp_failed' in offsets:
            # Run native guest instructions without host intervention until
            # the sentinel store. Bochs has no execution overlay; this records
            # ordinary x86 RAM, accumulator, and flag semantics independently.
            pc = offsets['unrelated_store']
            compare_sites = {
                offsets['cmp_failed']: 'failed',
                offsets['cmp_succeeded']: 'changed',
                offsets['cmp_same']: 'same',
            }
            steps = {}
            for _ in range(32):
                if pc == offsets['sentinel_store']:
                    break
                compare = compare_sites.get(pc)
                debug.cmd('s')
                context = debug.context()
                pc = context['cs_base'] + context['ip']
                if compare:
                    steps[compare] = dict(pc=pc, ram=debug.read(offsets['watched'], 1).hex(),
                                          sentinel=debug.read(offsets['sentinel'], 1).hex())
            assert pc == offsets['sentinel_store'], hex(pc)
            assert list(steps) == ['failed', 'changed', 'same']
            final = _observation(debug, offsets, offsets['sentinel_store'], cfg['paging_mode'])
            assert {k: v['hex'] for k, v in final['values'].items()} == {
                'unrelated': 'a5', 'watched': '5a', 'sentinel': '90'}
            raw = debug.read(offsets['cmp_result_flags'], 12)
            flags = [int.from_bytes(raw[i:i + 4], 'little') for i in (0, 4, 8)]
            failed_al = debug.read(offsets['cmp_result_al'], 1)[0]
            failed_ram = debug.read(offsets['cmp_result_ram'], 1)[0]
            assert failed_al == 0x90
            assert failed_ram == 0x90
            assert flags[0] & (1 << 6) == 0, flags
            assert flags[1] & (1 << 6) and flags[2] & (1 << 6), flags
            observation = dict(final=final, failed_al=failed_al, failed_ram=failed_ram, flags=flags,
                               steps=steps)
            if phase == 'after':
                assert observation == prior['observations']
        else:
            debug.cmd('s')
            second = _observation(debug, offsets, offsets['watched_store'], cfg['paging_mode'])
            assert {k: v['hex'] for k, v in second['values'].items()} == {
                'unrelated': 'a5', 'watched': '90', 'sentinel': '90'}
            debug.cmd('s')
            third = _observation(debug, offsets, offsets['sentinel_store'], cfg['paging_mode'])
            assert {k: v['hex'] for k, v in third['values'].items()} == {
                'unrelated': 'a5', 'watched': '5a', 'sentinel': '90'}
            observation = [first, second, third]
            if phase == 'after':
                assert observation == prior['observations']
    except BaseException:
        debug.abort()
        raise
    else:
        debug.close()
    result = dict(phase=phase, checkpoint=str(checkpoint), checkpoint_context=first['context'],
                  observations=observation, initial_context=initial_context,
                  restore_before_guest_execution=phase == 'after', paging_mode=cfg['paging_mode'], binary_sha256=_hash(binary),
                  media_sha256=_hash(disk), source_sha256=_hash(source), pid=debug.proc.pid,
                  exit_code=debug.proc.returncode)
    (stage / f'dirty-bochs-{phase}.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    run(Path(sys.argv[1]), sys.argv[2])
