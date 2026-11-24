"""Public paged and LDT LE code capture against independent DOSBox-X reads."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

import pytest

from fdisbull.le import load_runtime_le_carrier
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline
from support.qemu_dos_le_fixture import build_paged_ldt_fixture
from test_qemu_dos_process_native import process_runtime as process_runtime


def prepare(stage, runtime, paging, ldt):
    stage = Path(stage)
    build = stage / 'build'
    build.mkdir(parents=True)
    fixture = build_paged_ldt_fixture(build, runtime['nasm'], paging=paging, ldt=ldt)
    game = stage / 'game'
    game.mkdir()
    source = game / 'LETABLE.EXE'
    shutil.copyfile(fixture['path'], source)
    image = load_runtime_le_carrier(source.read_bytes())
    offset, pc = fixture['entry_offset'], fixture['entry_address']
    selected = [
        f
        for f in image.metadata['le']['fixups']
        if f['source_object'] == 1 and f['source_offset'] == offset + 1 and f.get('duplicate_of') is None
    ]
    (fix,) = selected
    assert fix['width'] == 4 and fix['target_object'] == 2
    assert [f['size'] for f in fix['file_fragments']] == [1, 3]
    canonical = image.regions[0].data[offset : offset + 5].hex()
    prepare_dos_baseline(
        runtime['boot_image'],
        stage / 'boot.img',
        runtime['mcopy'],
        config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG,
    )
    cfg = dict(
        source=str(source),
        sha256=fixture['sha256'],
        paging=paging,
        ldt=ldt,
        pc=pc,
        ip=fixture['entry_ip'],
        offset=offset,
        selector=fixture['ldt_code_selector'] if ldt else 8,
        canonical=canonical,
        target=fixture['counter_address'],
        physical=[fixture['code_physical'][0] + 4094, fixture['code_physical'][1]],
    )
    (stage / 'config.json').write_text(json.dumps(cfg, indent=2))
    return cfg


@pytest.mark.parametrize(
    'paging,ldt',
    [(True, False), (False, True), (True, True)],
    ids=['paged-gdt', 'unpaged-ldt', 'paged-ldt'],
)
def test_paired_le_translation_after_cold_restore(tmp_path, process_runtime, paging, ldt):  # noqa: F811
    if not os.environ.get('FDISBULL_DOSBOX') or not os.environ.get('FDISBULL_QEMU_IMG'):
        pytest.skip('Select DOSBox-X and qemu-img for paired LE checkpoint verification')
    cfg = prepare(tmp_path, process_runtime, paging, ldt)
    helper = Path(__file__).parent / 'support' / 'le_translation_native.py'
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join(str(p) for p in sys.path if p)}
    paired = {}
    for backend in ('dosbox', 'qemu'):
        phases = []
        for phase in ('before', 'after'):
            subprocess.run(
                [sys.executable, str(helper), str(tmp_path), backend, phase],
                check=True,
                timeout=80,
                env=env,
            )
            phases.append(json.loads((tmp_path / f'{backend}-{phase}.json').read_bytes()))
        before, after = phases
        assert before['checkpoint'] == after['checkpoint'] and before['counter'] == after['counter']
        a, b = before['observation'], after['observation']
        if backend == 'qemu':
            assert a['run'] != b['run'] and a['artifact'] != b['artifact']
        for key in a.keys() - {'run', 'artifact'}:
            assert a[key] == b[key], key
        paired[backend] = a
    native, reference = paired['qemu'], paired['dosbox']
    for key in (
        'cs',
        'cs_base',
        'cs_limit',
        'flags',
        'ip',
        'paging',
        'selector_table',
        'ldtr_selector',
        'bytes',
    ):
        assert native[key] == reference[key], key
    # Architecturally the CPU may set the descriptor accessed bit when loading CS.
    assert native['access'] & ~1 == reference['access'] & ~1
    assert native['canonical'] == cfg['canonical'] and native['canonical'] != native['bytes']
    assert (
        native['source'] == hashlib.sha256(Path(cfg['source']).read_bytes()).hexdigest() == cfg['sha256']
    )
    assert native['bytes'] == 'b8' + cfg['target'].to_bytes(4, 'little').hex()
    assert native['cs_base'] + native['ip'] == cfg['pc']
    assert native['selector_table'] == ('ldt' if ldt else 'gdt')
    assert native['cs_base'] == (0x120000 if ldt else 0)
    fixup = native['fixup']
    raw = Path(cfg['source']).read_bytes()
    kind, flags, site, obj, offset = struct.unpack_from('<BBhBH', raw, fixup['record_file_offset'])
    assert (kind, flags, site, obj, offset) == (
        7,
        0,
        4095,
        fixup['target_object'],
        fixup['target_offset'],
    )
    assert fixup['target_object'] == 2 and fixup['target_offset'] == 128
    fragments = fixup['source_file_fragments']
    assert [(f['word_offset'], f['size']) for f in fragments] == [(0, 1), (1, 3)]
    assert fragments[1]['file_offset'] < fragments[0]['file_offset']
    actual, expected = native['instruction_segments'], reference['instruction_segments']
    assert len(actual) == len(expected) == 2
    for i, (walk, independent) in enumerate(zip(actual, expected)):
        assert walk['physical'] == cfg['physical'][i]
        for field, value in independent.items():
            if field in ('pde', 'pte'):
                # Accessed and dirty bits depend on each emulator's access history.
                assert walk[field] & ~0x60 == value & ~0x60
            else:
                assert walk[field] == value, field
        assert walk['paging'] is paging
        if paging:
            assert walk['physical'] != walk['linear']
