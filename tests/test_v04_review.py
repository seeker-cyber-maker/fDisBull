"""Independent regressions at module-snapshot and representation boundaries."""
import shutil
import struct
import subprocess
import sys

import pytest

from fdisbull.loader import load_image
from fdisbull.modules import analyze_module
from fdisbull.project import Project
from fixtures_formats import pe64


@pytest.fixture
def entryless_rx_elf(tmp_path):
    compiler = shutil.which('gcc')
    if not compiler or sys.platform != 'linux':
        pytest.skip('the ELF fixture requires a Linux C/linker toolchain')
    binary = tmp_path / 'library.so'
    subprocess.run(
        [compiler, '-shared', '-fPIC', '-Wl,-z,noseparate-code', '-x', 'c', '-', '-o', str(binary)],
        input='int exported(void) { return 7; }\n', text=True, capture_output=True, check=True,
    )
    return binary


def test_zero_elf_entry_is_absent_even_when_its_header_is_rx_mapped(entryless_rx_elf):
    image = load_image(entryless_rx_elf, module=True)
    assert any(region.executable and region.start == 0 for region in image.regions)
    assert not image.metadata['entrypoint_present']
    assert not any(seed.address == 0 and seed.source.startswith('entry') for seed in image.seeds)


def test_unbound_zero_got_pointer_does_not_invent_code_at_elf_header(entryless_rx_elf, tmp_path):
    with Project.create(tmp_path / 'library.fdb', entryless_rx_elf, module=True) as project:
        assert project.analyze()['stable']
        assert project.locate(0)['instructions'] == []
        assert not any(item['kind'] in ('resolved_call', 'resolved_branch') for item in project.xrefs(0))


def test_export_selection_and_saved_project_share_one_source_snapshot(tmp_path, monkeypatch):
    import fdisbull.inspection as inspection

    binary = tmp_path / 'changing.dll'
    original = bytearray(pe64())
    struct.pack_into('<H', original, 0x96, 0x2022)
    binary.write_bytes(original)
    project_path = tmp_path / 'selected.fdb'
    inspect = inspection.inspect_binary
    changed = False

    def change_source_after_selection_capture(data, **options):
        nonlocal changed
        result = inspect(data, **options)
        if not changed:
            changed = True
            newer = bytearray(original)
            struct.pack_into('<I', newer, 0x340, 0x1020)
            newer[0x220] = 0xC3
            binary.write_bytes(newer)
        return result

    monkeypatch.setattr(inspection, 'inspect_binary', change_source_after_selection_capture)
    result = analyze_module(binary, project_path, export='helper')
    with Project(project_path) as project:
        saved = next(item for item in project.information('exports')['items'] if item['original_name'] == 'helper')
        assert saved['address'] == hex(result['selected_export']['address']) == '0x140001010'
        assert result['analysis_roots'] == ['0x140001010']
        source = project.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()[0]
        assert bytes(source) == bytes(original)
        assert binary.read_bytes() != bytes(source)


def _dos_reference_to_string():
    module = bytearray(128)
    module[:9] = bytes.fromhex('b804008ed8a10000c3')
    module[0x40:0x46] = b'HELLO\0'
    size = 64 + len(module)
    header = bytearray(64)
    struct.pack_into('<14H', header, 0, 0x5A4D, size % 512, (size + 511) // 512,
                     1, 4, 0, 0xFFFF, 0, 32, 0, 0, 0, 28, 0)
    struct.pack_into('<HH', header, 28, 1, 0)
    return bytes(header) + bytes(module)


@pytest.mark.parametrize('dos', [False, True])
def test_unexplored_byte_inside_inferred_string_prevents_overlapping_data_facts(tmp_path, dos):
    binary = tmp_path / 'held.bin'
    if dos:
        source, options, held = _dos_reference_to_string(), {}, 0x10042
    else:
        raw = bytearray(64)
        raw[:8] = bytes.fromhex('488d3d19000000c3')
        raw[0x20:0x26] = b'HELLO\0'
        source, options, held = bytes(raw), dict(arch='x86', base=0x1000), 0x1022
    binary.write_bytes(source)
    with Project.create(tmp_path / 'held.fdb', binary, **options) as project:
        assert project.analyze()['stable']
        before = project.regions(1)[0].data
        project.represent(held, 'unexplored', size=1, defer=True)
        assert project.analyze()['stable']
        for item in project.items():
            start = int(item['address'], 0)
            assert not start <= held < start + item['size']
        result = project.locate(held)
        assert result['held'] and result['classification'] == 'unexplored'
        assert result['data'] == []
        assert project.regions(1)[0].data == before


def test_live_analysis_status_tracks_current_budget_and_not_old_receipts(tmp_path):
    binary = tmp_path / 'budget.bin'
    binary.write_bytes(bytes.fromhex('e80500000085c07501c3b82a000000c3'))
    with Project.create(tmp_path / 'budget.fdb', binary, arch='x86', base=0x1000) as project:
        initial = project.analysis_status()
        assert not initial['stable'] and initial['pending_code'] == 1
        assert initial['pending_seed_phase']
        partial_receipt = project.analyze(max_instructions=1)
        partial = project.analysis_status()
        assert partial_receipt['budget_exhausted'] and partial_receipt['pending'] > 0
        assert not partial['stable'] and partial['pending_code'] > 0
        assert partial['pending'] == partial_receipt['pending']
        assert project.status()['analysis'] == partial
        assert project.disassembly()['analysis'] == partial
        assert project.analyze()['stable']
        complete = project.analysis_status()
        assert complete['stable'] and complete['pending'] == 0
        assert complete['pending_code'] == complete['pending_data'] == complete['pending_seeds'] == 0
        assert complete['pending_segment_scans'] == 0 and not complete['pending_seed_phase']
        assert partial_receipt['pending'] > 0  # historical receipt is not current queue state
        before = project.db.total_changes
        assert project.status()['analysis'] == complete
        assert project.disassembly()['analysis'] == complete
        assert project.analysis_status() == complete
        assert project.db.total_changes == before


def test_fixed_point_can_retain_unresolved_indirect_issues_without_pending_work(tmp_path):
    binary = tmp_path / 'unknown.bin'
    binary.write_bytes(bytes.fromhex('ffe09090'))  # jmp rax; unexplored padding
    with Project.create(tmp_path / 'unknown.fdb', binary, arch='x86', base=0x1000) as project:
        assert project.analyze()['stable']
        current = project.analysis_status()
        assert current['stable'] and current['pending'] == 0
        assert current['issues'] >= 1
        assert any('unresolved indirect' in issue['detail'] for issue in project.issues())
        assert all(item['state'] != 'pending' for item in project.queue())


def _dos_callback_catalog():
    module = bytearray(256)
    module[:11] = bytes.fromhex('ba08008eda9a00000400c3')
    module[0x40] = module[0x50] = 0xCB
    struct.pack_into('<HH', module, 0x80, 0x10, 4)
    size = 64 + len(module)
    header = bytearray(64)
    struct.pack_into('<14H', header, 0, 0x5A4D, size % 512, (size + 511) // 512,
                     3, 4, 0, 0xFFFF, 15, 16, 0, 0, 0, 28, 0)
    for index, offset in enumerate((1, 8, 0x82)):
        struct.pack_into('<HH', header, 28 + index * 4, offset, 0)
    return bytes(header) + bytes(module)


def test_dos_admitted_seed_count_is_not_pending_work(tmp_path):
    binary = tmp_path / 'catalog.exe'
    binary.write_bytes(_dos_callback_catalog())
    with Project.create(tmp_path / 'catalog.fdb', binary) as project:
        initial = project.analysis_status()
        assert initial['seed_states']['deferred'] > 0
        assert initial['pending_seeds'] == initial['seed_states']['deferred']
        assert not initial['stable']
        project.analyze(max_instructions=1)
        partial = project.analysis_status()
        assert partial['pending_seeds'] > 0
        assert project.analyze()['stable']
        complete = project.analysis_status()
        assert complete['seed_states']['admitted'] >= 2
        assert complete['pending_seeds'] == complete['pending'] == 0
        assert complete['stable']


@pytest.mark.parametrize('base', [0, 0x8000000000000000])
def test_fixed_width_address_order_and_ranges_match_numeric_order(tmp_path, base):
    offsets = [0, 0xF, 0x10, 0xFF, 0x100]
    raw = bytearray(b'\xCC' * 0x101)
    for offset in offsets:
        raw[offset] = 0xC3
    binary = tmp_path / 'addresses.bin'
    binary.write_bytes(raw)
    with Project.create(tmp_path / 'addresses.fdb', binary, arch='x86', base=base) as project:
        for offset in offsets:
            project.analyze(start=base + offset)
        numeric = [base + offset for offset in offsets]
        rows = project.disassembly(base, lines=20)['instructions']
        assert [int(row['address'], 0) for row in rows] == numeric
        assert [int(function['address'], 0) for function in project.functions()] == numeric
        selected = project.disassembly(base + 0x10, lines=2)['instructions']
        assert [int(row['address'], 0) for row in selected] == [base + 0x10, base + 0xFF]
        assert project.locate(base + 0xFF)['instructions'][0]['position'] == 'single'
        stored = [row[0] for row in project.db.execute('SELECT address FROM instructions ORDER BY address')]
        assert all(len(value) == 16 and not value.startswith('0x') for value in stored)
