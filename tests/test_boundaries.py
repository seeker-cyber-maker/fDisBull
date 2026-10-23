"""Stored byte positions and native boundary evidence, without analysis writes."""
import struct

import pytest

from fdisbull.boundaries import BoundaryMixin
from fdisbull.project import Project


def _project(tmp_path, data, **options):
    path = tmp_path / 'input.bin'
    path.write_bytes(data)
    cls = Project if issubclass(Project, BoundaryMixin) else type('BoundaryProject', (BoundaryMixin, Project), {})
    return cls.create(tmp_path / 'analysis.fdb', path, **options)


def _mz(module):
    size = 64 + len(module)
    header = bytearray(64)
    struct.pack_into('<14H', header, 0, 0x5A4D, size % 512, (size + 511) // 512,
                     0, 4, 0, 0xFFFF, 0, 32, 0, 0, 0, 28, 0)
    return bytes(header) + bytes(module)


def test_locate_identifies_each_instruction_byte_without_skipping(tmp_path):
    with _project(tmp_path, bytes.fromhex('b82a000000c39090'), arch='x86', base=0x1000) as project:
        project.analyze()
        positions = [project.locate(0x1000 + i)['instructions'][0]['position'] for i in range(5)]
        assert positions == ['begin', 'part', 'part', 'part', 'end']
        last = project.locate(0x1004)['instructions'][0]
        assert last['address'] == '0x1000' and last['end'] == '0x1004'
        assert last['end_exclusive'] == '0x1005' and last['byte_offset'] == 4
        assert project.locate(0x1005)['instructions'][0]['position'] == 'single'
        assert project.locate(0x1006)['classification'] == 'unexplored'
        assert project.locate(0x1006)['instructions'] == []
        assert project.locate(0x1008)['classification'] == 'outside'


def test_locate_retains_overlapping_instruction_interpretations(tmp_path):
    with _project(tmp_path, bytes.fromhex('b89090c300c3'), arch='x86', base=0x1000) as project:
        project.analyze()
        project.analyze(start=0x1001)
        result = project.locate(0x1002)
        assert result['classification'] == 'code' and result['overlap']
        assert {(item['address'], item['position']) for item in result['instructions']} == {
            ('0x1000', 'part'), ('0x1002', 'single'),
        }


def test_locate_data_ranges_use_shared_name_and_representation(tmp_path):
    with _project(tmp_path, b'\xc3HELLO\0', arch='x86', base=0x1000) as project:
        project.analyze()
        project.represent(0x1001, 'ascii', size=5)
        project.annotate(0x1001, 'greeting', kind='name')
        result = project.locate(0x1003)
        assert result['classification'] == 'data'
        assert result['data'][0]['position'] == 'part'
        assert result['data'][0]['end'] == '0x1005'
        assert result['presentation']['name'] == 'greeting'
        assert result['presentation']['representation'] == 'ascii'


def test_locate_keeps_dos_cs_aliases_and_can_select_one(tmp_path):
    module = bytearray(64)
    module[:3] = bytes.fromhex('e90d00')
    module[16] = 0xC3
    with _project(tmp_path, _mz(module)) as project:
        project.analyze()
        project.analyze(start='1001:0000')
        result = project.locate('0x10010')
        assert {item['segmented_address'] for item in result['instructions']} == {'1000:0010', '1001:0000'}
        assert result['overlap']
        chosen = project.locate('1001:0000')
        assert len(chosen['instructions']) == 1
        assert chosen['instructions'][0]['context'] == 'x86:16:little:cs=1001'


@pytest.mark.parametrize(
    ('bits', 'data'),
    [
        (16, '558becc9c3'),
        (32, '5589e55dc3'),
        (64, '554889e54883ec20c9c3'),
    ],
)
def test_native_x86_frame_setup_and_return_evidence(tmp_path, bits, data):
    with _project(tmp_path, bytes.fromhex(data), arch='x86', bits=bits, base=0x1000) as project:
        project.analyze()
        before = project.db.total_changes
        result = project.function_patterns()
        assert {'prologue', 'epilogue', 'return'} <= {item['kind'] for item in result['items']}
        prologue = next(item for item in result['items'] if item['kind'] == 'prologue')
        assert prologue['address'] == '0x1000' and prologue['function_entry_known']
        assert all(item['status'] == 'candidate' for item in result['items'])
        assert project.db.total_changes == before


def test_native_arm64_frame_and_return_patterns(tmp_path):
    data = bytes.fromhex('fd7bbfa9fd030091fd7bc1a8c0035fd6')
    with _project(tmp_path, data, arch='arm64', base=0x1000) as project:
        project.analyze()
        result = project.function_patterns()
        assert {'prologue', 'epilogue', 'return'} <= {item['kind'] for item in result['items']}
        setup = next(item for item in result['items'] if item['kind'] == 'prologue')
        assert setup['pattern'] == 'arm64_frame_setup'
        assert setup['end_exclusive'] == '0x1008'


def test_jump_is_only_candidate_tail_exit_evidence(tmp_path):
    with _project(tmp_path, bytes.fromhex('eb029090c3'), arch='x86', base=0x1000) as project:
        project.analyze()
        jump = next(item for item in project.function_patterns()['items'] if item['kind'] == 'tail_jump')
        assert jump['status'] == 'candidate'
        assert 'intra-function' in jump['qualification']


def test_optional_scan_reports_native_candidates_without_classifying_code(tmp_path):
    data = bytes.fromhex('c3909090554889e5c3')
    with _project(tmp_path, data, arch='x86', base=0x1000) as project:
        project.analyze()
        assert not any(item['kind'] == 'prologue' for item in project.function_patterns()['items'])
        before = project.db.total_changes
        result = project.function_patterns(scan_unexplored=True)
        found = next(item for item in result['items'] if item['kind'] == 'prologue')
        assert found['address'] == '0x1004' and found['source'] == 'unexplored_bytes'
        assert project.locate(0x1004)['classification'] == 'unexplored'
        assert project.db.total_changes == before


def test_held_unexplored_range_is_not_data_or_raw_pattern_evidence(tmp_path):
    data = bytes.fromhex('c3909090554889e5c3')
    with _project(tmp_path, data, arch='x86', base=0x1000) as project:
        project.analyze()
        project.represent(0x1004, 'unexplored', size=4)
        result = project.locate(0x1005)
        assert result['classification'] == 'unexplored' and result['held']
        assert result['data'] == []
        assert not any(item['address'] == '0x1004' for item in project.function_patterns(scan_unexplored=True)['items'])


def test_patterns_paginate_and_queries_preserve_parent_version(tmp_path):
    with _project(tmp_path, bytes.fromhex('5589e5c9c3'), arch='x86', bits=32, base=0x1000) as project:
        project.analyze()
        original = project.function_patterns()['items']
        project.patch(0x1000, 'c3')
        project.analyze()
        assert not any(item['kind'] == 'prologue' for item in project.function_patterns()['items'])
        assert project.function_patterns(version=1)['items'] == original
        page = project.function_patterns(version=1, limit=1, offset=1)
        assert page['items'] == original[1:2] and page['has_more']
        assert project.locate(0x1001, version=1)['classification'] == 'code'
        assert project.locate(0x1001)['classification'] == 'unexplored'


def test_raw_dos_pattern_context_is_explicitly_a_candidate(tmp_path):
    module = bytearray(64)
    module[0] = 0xC3
    module[16:21] = bytes.fromhex('558becc9c3')
    with _project(tmp_path, _mz(module)) as project:
        project.analyze()
        result = project.function_patterns(scan_unexplored=True)
        found = next(item for item in result['items'] if item['kind'] == 'prologue')
        assert found['segmented_address'] == '1000:0010'
        assert found['context_status'] == 'candidate' and result['warnings']
        assert not project.locate('1000:0010')['decoded']


def test_bad_boundary_query_options_are_rejected(tmp_path):
    with _project(tmp_path, b'\xc3', arch='x86') as project:
        with pytest.raises(ValueError):
            project.locate(0, cs=0x1000)
        with pytest.raises(ValueError):
            project.function_patterns(scan_unexplored=1)
        with pytest.raises(ValueError):
            project.function_patterns(limit=True)


def test_high_address_last_byte_uses_an_unambiguous_exclusive_end(tmp_path):
    base = (1 << 64) - 5
    with _project(tmp_path, bytes.fromhex('b82a000000'), arch='x86', base=base) as project:
        project.analyze()
        last = project.locate((1 << 64) - 1)['instructions'][0]
        assert last['position'] == 'end'
        assert last['end'] == '0xffffffffffffffff'
        assert last['end_exclusive'] == '0x10000000000000000'


def test_optional_candidate_scan_reports_a_reached_work_bound(tmp_path):
    data = b'\xc3\x90\x90\x90' + bytes.fromhex('c8000000') * 4097
    with _project(tmp_path, data, arch='x86', base=0x1000) as project:
        project.analyze()
        before = project.db.total_changes
        result = project.function_patterns(scan_unexplored=True)
        assert result['scan']['partial']
        assert result['scan']['candidate_checks'] == result['scan']['candidate_limit'] == 4096
        assert result['warnings']
        assert project.db.total_changes == before


def test_optional_scan_reports_unvisited_bytes_after_its_byte_bound(tmp_path):
    data = b'\xc3' + bytes(4 * 1024 * 1024) + bytes.fromhex('554889e5c3')
    with _project(tmp_path, data, arch='x86', base=0x1000) as project:
        project.analyze()
        result = project.function_patterns(scan_unexplored=True)
        assert result['scan']['partial']
        assert result['scan']['scanned_bytes'] == result['scan']['byte_limit'] == 4 * 1024 * 1024
        assert not any(item['kind'] == 'prologue' for item in result['items'])
