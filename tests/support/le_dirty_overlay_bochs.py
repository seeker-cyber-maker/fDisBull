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
        assert {k: v['hex'] for k, v in first['values'].items()} == {
            'unrelated': '90', 'watched': '90', 'sentinel': '90'}
        if phase == 'before':
            checkpoint.mkdir()
            saved = debug.cmd(f'restore "__save_state__" "{checkpoint}"')
            assert 'native save state' in saved and ': OK' in saved, saved
        debug.cmd('s')
        second = _observation(debug, offsets, offsets['watched_store'], cfg['paging_mode'])
        assert {k: v['hex'] for k, v in second['values'].items()} == {
            'unrelated': 'a5', 'watched': '90', 'sentinel': '90'}
        debug.cmd('s')
        third = _observation(debug, offsets, offsets['sentinel_store'], cfg['paging_mode'])
        assert {k: v['hex'] for k, v in third['values'].items()} == {
            'unrelated': 'a5', 'watched': '5a', 'sentinel': '90'}
        if phase == 'after':
            assert [first, second, third] == prior['observations']
    except BaseException:
        debug.abort()
        raise
    else:
        debug.close()
    result = dict(phase=phase, checkpoint=str(checkpoint), checkpoint_context=first['context'],
                  observations=[first, second, third], initial_context=initial_context,
                  restore_before_guest_execution=phase == 'after', paging_mode=cfg['paging_mode'], binary_sha256=_hash(binary),
                  media_sha256=_hash(disk), source_sha256=_hash(source), pid=debug.proc.pid,
                  exit_code=debug.proc.returncode)
    (stage / f'dirty-bochs-{phase}.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    run(Path(sys.argv[1]), sys.argv[2])
