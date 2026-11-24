"""Trace the guest changing its own code mapping and LDT selector on both engines."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from fdisbull.le import load_runtime_le_carrier
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline
from support.qemu_dos_le_fixture import build_paged_ldt_fixture
from test_qemu_dos_process_native import process_runtime as process_runtime


def prepare(stage, runtime):
    stage = Path(stage)
    build = stage / 'build'
    build.mkdir(parents=True)
    f = build_paged_ldt_fixture(build, runtime['nasm'], tracking=True)
    game = stage / 'game'
    game.mkdir()
    source = game / 'REMAP.EXE'
    shutil.copyfile(f['path'], source)
    prepare_dos_baseline(
        runtime['boot_image'],
        stage / 'boot.img',
        runtime['mcopy'],
        config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG,
    )
    # Save on the second visit to the target: same CS/IP, new physical page.
    cfg = dict(
        source=str(source),
        sha256=f['sha256'],
        start_pc=f['entry_address'],
        start_ip=f['entry_ip'],
        start_cs=f['ldt_code_selector'],
        boundaries=39,
        checkpoint_index=7,
        cycle=19,
        target_ip=f['tracking_target'],
        selector_b=f['tracking_selector_b'],
        first_target=f['tracking_target_physical'],
        second_target=f['tracking_alternate_physical'],
    )
    (stage / 'config.json').write_text(json.dumps(cfg, indent=2))
    return cfg


def phases(stage, backend):
    helper = Path(__file__).parent / 'support' / f'le_remap_{backend}.py'
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join(str(p) for p in sys.path if p)}
    for phase in ('before', 'after'):
        subprocess.run(
            [sys.executable, str(helper), str(stage), phase], env=env, check=True, timeout=180
        )
    return [json.loads((stage / f'{backend}-{phase}.json').read_text()) for phase in ('before', 'after')]


def test_tracking_observes_guest_remaps_selectors_and_cold_restore(tmp_path, process_runtime):  # noqa: F811
    if not os.environ.get('FDISBULL_DOSBOX') or not os.environ.get('FDISBULL_QEMU_IMG'):
        pytest.skip('Select the DOSBox-X and QEMU machine checkpoint profile')
    cfg = prepare(tmp_path, process_runtime)
    original = Path(cfg['source']).read_bytes()
    img = load_runtime_le_carrier(original)
    ref, ref_cold = phases(tmp_path, 'dosbox')
    tracked, tracked_cold = phases(tmp_path, 'qemu')
    for hot, cold in ((ref, ref_cold), (tracked, tracked_cold)):
        assert hot['checkpoint'] == cold['checkpoint'] and len(hot['events']) == cfg['boundaries']
        assert hot['events'][cfg['checkpoint_index'] :] == cold['events']
    assert (
        tracked['binding_id'] != tracked_cold['binding_id'] and tracked['epoch'] != tracked_cold['epoch']
    )
    assert set(tracked['artifacts']).isdisjoint(tracked_cold['artifacts'])
    events = tracked['events']
    for i, (q, d) in enumerate(zip(events, ref['events'], strict=True)):
        assert (q['cs'], q['ip'], q['pc']) == (d['cs'], d['ip'], d['pc']), i
        assert (q['esi'] - events[0]['esi']) & 0xFFFFFFFF == (
            d['esi'] - ref['events'][0]['esi']
        ) & 0xFFFFFFFF
        if d['cs'] == 8:
            assert q['qualified'] is False and 'obj' not in q
            continue
        assert q['qualified'] and q['obj'] == 1 and q['offset'] == d['ip']
        for field in ('hex', 'backing', 'cs_base', 'cs_limit'):
            assert q[field] == d[field], (i, field)
        qdesc, ddesc = bytes.fromhex(q['descriptor']), bytes.fromhex(d['descriptor'])
        assert qdesc[:5] == ddesc[:5] and qdesc[6:] == ddesc[6:] and qdesc[5] & ~1 == ddesc[5] & ~1
        assert d['paging'] and d['ldtr_selector'] == 0x18
        data = img.regions[0].data[q['offset'] : q['offset'] + len(q['backing'])]
        assert (
            data.hex() == d['hex'] and hashlib.sha256(data).hexdigest() == q['source_instruction_sha256']
        )
    for base in (0, cfg['cycle']):
        visits = [e for e in events[base : base + cfg['cycle']] if e['ip'] == cfg['target_ip']]
        assert [(e['cs'], e['backing'][0]) for e in visits] == [
            (cfg['start_cs'], cfg['first_target']),
            (cfg['start_cs'], cfg['second_target']),
            (cfg['selector_b'], cfg['second_target']),
        ]
        assert all(e['hex'] == '46' for e in visits)
        assert [e['qualified'] for e in events[base + 16 : base + 19]] == [False, False, True]
        assert events[base + cfg['cycle']]['esi'] == (events[base]['esi'] + 3) & 0xFFFFFFFF
    assert hashlib.sha256(Path(cfg['source']).read_bytes()).hexdigest() == cfg['sha256']
