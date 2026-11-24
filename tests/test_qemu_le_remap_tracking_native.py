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


def prepare(stage, runtime, paging_mode="legacy-4k"):
    stage = Path(stage)
    build = stage / 'build'
    build.mkdir(parents=True)
    f = build_paged_ldt_fixture(build, runtime['nasm'], tracking=True, paging_mode=paging_mode)
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
        paging_mode=paging_mode,
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


@pytest.mark.parametrize('paging_mode', ['legacy-4m', 'pae-4k', 'pae-2m'])
def test_native_large_and_pae_remap_cold_restore(tmp_path, process_runtime, paging_mode):  # noqa: F811
    if not os.environ.get('FDISBULL_QEMU_IMG'):
        pytest.skip('Select QEMU machine checkpoint profile')
    cfg = prepare(tmp_path, process_runtime, paging_mode)
    hot, cold = phases(tmp_path, 'qemu')
    assert hot['checkpoint'] == cold['checkpoint']
    assert hot['events'][cfg['checkpoint_index']:] == cold['events']
    assert hot['binding_id'] != cold['binding_id'] and hot['epoch'] != cold['epoch']
    events = hot['events']
    for base in (0, cfg['cycle']):
        visits = [e for e in events[base:base + cfg['cycle']] if e['ip'] == cfg['target_ip']]
        assert [(e['cs'], e['backing'][0]) for e in visits] == [
            (cfg['start_cs'], cfg['first_target']),
            (cfg['start_cs'], cfg['second_target']),
            (cfg['selector_b'], cfg['second_target']),
        ]
        assert all(e['qualified'] and e['hex'] == '46' for e in visits)
        expected_size = {'legacy-4m': 0x400000, 'pae-4k': 0x1000, 'pae-2m': 0x200000}[paging_mode]
        for event in visits:
            assert event['page_size'] == expected_size
            assert event['paging_mode'] == ('legacy-32' if paging_mode == 'legacy-4m' else 'pae')
            assert event['entries'] and event['page_attributes']
        assert events[base + cfg['cycle']]['esi'] == (events[base]['esi'] + 3) & 0xffffffff
    assert hashlib.sha256(Path(cfg['source']).read_bytes()).hexdigest() == cfg['sha256']


def test_dosbox_large_page_cold_restore_observations(tmp_path, process_runtime):  # noqa: F811
    """Unassisted refusal and separately labelled guest-assisted observation."""
    if not os.environ.get('FDISBULL_DOSBOX'):
        pytest.skip('Select DOSBox-X')
    cfg = prepare(tmp_path, process_runtime, 'legacy-4m')
    helper = Path(__file__).parent / 'support' / 'le_remap_dosbox.py'
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join(str(p) for p in sys.path if p)}

    def invoke(phase, assisted=False):
        args = [sys.executable, str(helper), str(tmp_path), phase]
        if assisted:
            args.append('guest-paging')
        return subprocess.run(args, env=env, capture_output=True, text=True, timeout=180)

    before = invoke('before')
    partial = json.loads((tmp_path / 'dosbox-before-partial.json').read_text())
    assert partial['status'] == 'before-shutdown-restore'
    cpuid = bytes.fromhex(partial['cpu_probe'])
    assert int.from_bytes(cpuid[:4], 'little') & 8
    assert int.from_bytes(cpuid[4:], 'little') == 0
    (tmp_path / 'dosbox-before.json').write_text(json.dumps(partial))
    cold = invoke('after')
    if before.returncode == 0 and cold.returncode == 0:
        after = json.loads((tmp_path / 'dosbox-after.json').read_text())
        assert after['events'] == partial['events'][cfg['checkpoint_index']:]
    else:
        # This exception is accepted only for the exact measured reference image.
        binary = Path(os.environ['FDISBULL_DOSBOX'])
        assert hashlib.sha256(binary.read_bytes()).hexdigest() == (
            'df2080bcd2e65aa8a8511ca0692d45d9b9f5355d673a83967c4abdab9672c47e')
        assert not int.from_bytes(cpuid[:4], 'little') & 64
        assert before.returncode != 0 and cold.returncode != 0
        assert all('Restored CPU differs from saved state: address_context' in r.stderr
                   for r in (before, cold))
        saved = partial['checkpoint_context']
        observed = json.loads((tmp_path / 'dosbox-after-checkpoint-unassisted-observed.json').read_text())
        assert len(observed) == 1 and saved != observed[0]
        assert saved['cr4'] == '0x00000010' and observed[0]['cr4'] == '0x00000000'
        assisted = invoke('after', assisted=True)
        assert assisted.returncode != 0 and 'Restored CPU differs from saved state: address_context' in assisted.stderr
        after = json.loads((tmp_path / 'dosbox-after-partial.json').read_text())
        assert after['events'] == partial['events'][cfg['checkpoint_index']:]
        assert after['cpu_probe'] == partial['cpu_probe']
    if os.environ.get('FDISBULL_QEMU_IMG'):
        native, native_cold = phases(tmp_path, 'qemu')
        assert native['events'][cfg['checkpoint_index']:] == native_cold['events']
        for q, d in zip(native['events'], partial['events'], strict=True):
            assert (q['cs'], q['ip'], q['pc']) == (d['cs'], d['ip'], d['pc'])
            if q['qualified']:
                for field in ('hex', 'backing', 'cs_base', 'cs_limit'):
                    assert q[field] == d[field]


def test_pae_semantics_against_restored_legacy_reference(tmp_path, process_runtime):  # noqa: F811
    """Compare common source-level behavior, not unlike page-table formats."""
    if not os.environ.get('FDISBULL_DOSBOX') or not os.environ.get('FDISBULL_QEMU_IMG'):
        pytest.skip('Select DOSBox-X and QEMU machine checkpoint profile')
    reference_dir = tmp_path / 'reference'
    reference_dir.mkdir()
    ref_cfg = prepare(reference_dir, process_runtime)
    ref, ref_cold = phases(reference_dir, 'dosbox')
    assert ref['events'][ref_cfg['checkpoint_index']:] == ref_cold['events']
    for mode in ('pae-4k', 'pae-2m'):
        stage = tmp_path / mode
        stage.mkdir()
        cfg = prepare(stage, process_runtime, mode)
        native, cold = phases(stage, 'qemu')
        assert native['events'][cfg['checkpoint_index']:] == cold['events']
        def normalized(events, initial):
            return [(e['cs'], e['ip'], (e['esi'] - initial) & 0xffffffff) for e in events]
        assert normalized(native['events'], native['events'][0]['esi']) == normalized(
            ref['events'], ref['events'][0]['esi'])
        assert normalized(cold['events'], native['events'][0]['esi']) == normalized(
            ref_cold['events'], ref['events'][0]['esi'])
        native_targets = [e['hex'] for e in native['events'] if e['ip'] == cfg['target_ip']]
        ref_targets = [e['hex'] for e in ref['events'] if e['ip'] == ref_cfg['target_ip']]
        assert native_targets == ref_targets and all(value == '46' for value in native_targets)


def test_dosbox_large_page_candidate_paired_unassisted(tmp_path, process_runtime):  # noqa: F811
    """Require a cold, unprimed large-page restore on the explicitly selected candidate."""
    candidate = os.environ.get('FDISBULL_DOSBOX_LARGE_PAGE_CANDIDATE')
    if not candidate:
        pytest.skip('Select DOSBox-X large-page restore candidate')
    assert Path(candidate).is_file()
    assert os.environ.get('FDISBULL_QEMU_IMG'), 'Paired acceptance requires QEMU'
    cfg = prepare(tmp_path, process_runtime, 'legacy-4m')
    helper = Path(__file__).parent / 'support' / 'le_remap_dosbox.py'
    env = {**os.environ, 'FDISBULL_DOSBOX': candidate,
           'FDISBULL_REQUIRE_DOSBOX_LARGE_PAGE_RESTORE': '1',
           'PYTHONPATH': os.pathsep.join(str(p) for p in sys.path if p)}
    for phase in ('before', 'after'):
        subprocess.run([sys.executable, str(helper), str(tmp_path), phase],
                       env=env, check=True, timeout=180)
    ref, cold = [json.loads((tmp_path / f'dosbox-{phase}.json').read_text())
                 for phase in ('before', 'after')]
    assert len(ref['events']) == 39 and len(cold['events']) == 32
    assert ref['events'][cfg['checkpoint_index']:] == cold['events']
    assert ref['checkpoint'] == cold['checkpoint']
    for phase, result in (('before', ref), ('after', cold)):
        assert int(result['entry_context']['cr4'], 16) == 0
        assert result['entry_context'] == result['restored_entry_context']
        observed = json.loads((tmp_path / f'dosbox-{phase}-entry-unassisted-observed.json').read_text())
        assert observed and observed[-1] == result['entry_context']
    checkpoint = json.loads((tmp_path / 'dosbox-before-partial.json').read_text())['checkpoint_context']
    observed = json.loads((tmp_path / 'dosbox-after-checkpoint-unassisted-observed.json').read_text())
    assert checkpoint['cr4'] == '0x00000010' and observed and observed[-1] == checkpoint
    qemu, qemu_cold = phases(tmp_path, 'qemu')
    assert qemu['events'][cfg['checkpoint_index']:] == qemu_cold['events']
    img = load_runtime_le_carrier(Path(cfg['source']).read_bytes())
    for qevents, expected_qualified in ((qemu['events'], 35), (qemu_cold['events'], 28)):
        assert sum(event['qualified'] for event in qevents) == expected_qualified
        assert sum(not event['qualified'] for event in qevents) == 4
    for base in (0, cfg['cycle']):
        visits = [event for event in qemu['events'][base:base + cfg['cycle']]
                  if event['ip'] == cfg['target_ip']]
        assert [(event['cs'], event['backing'][0]) for event in visits] == [
            (cfg['start_cs'], cfg['first_target']),
            (cfg['start_cs'], cfg['second_target']),
            (cfg['selector_b'], cfg['second_target']),
        ]
    for qevents, devents in ((qemu['events'], ref['events']), (qemu_cold['events'], cold['events'])):
        for i, (q, d) in enumerate(zip(qevents, devents, strict=True)):
            assert (q['cs'], q['ip'], q['pc']) == (d['cs'], d['ip'], d['pc']), i
            assert (q['esi'] - qemu['events'][0]['esi']) & 0xffffffff == (
                d['esi'] - ref['events'][0]['esi']) & 0xffffffff, i
            if not q['qualified']:
                assert q['cs'] == 8 and 'obj' not in q
                continue
            assert q['obj'] == 1 and q['offset'] == d['ip']
            data = img.regions[0].data[q['offset']:q['offset'] + len(q['backing'])]
            assert data.hex() == d['hex']
            assert hashlib.sha256(data).hexdigest() == q['source_instruction_sha256']
            for field in ('hex', 'backing', 'cs_base', 'cs_limit'):
                assert q[field] == d[field], (i, field)
            qdesc, ddesc = bytes.fromhex(q['descriptor']), bytes.fromhex(d['descriptor'])
            assert qdesc[:5] == ddesc[:5] and qdesc[6:] == ddesc[6:]
            assert qdesc[5] & ~1 == ddesc[5] & ~1
            assert d['paging'] and d['ldtr_selector'] == 0x18
            assert q['page_size'] == 0x400000
            assert q['paging_mode'] == 'legacy-32'
    assert hashlib.sha256(Path(cfg['source']).read_bytes()).hexdigest() == cfg['sha256']
