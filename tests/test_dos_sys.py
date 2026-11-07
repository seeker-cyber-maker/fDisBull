"""Authored DOS driver examples; no original third-party bytes are fixtures."""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from fdisbull.image_views import image_views
from fdisbull.inspection import identify_header, inspect_binary
from fdisbull.loader import load_image
from fdisbull.project import Project


def driver(*, chain=False, block=False):
    data = bytearray(b'\x90' * (0x90 if chain else 0x60))
    struct.pack_into('<HHHHH8s', data, 0, 0x40 if chain else 0xffff,
                     0 if chain else 0xffff, 0 if block else 0x8000,
                     0x20, 0x30, b'\x01' + bytes(7) if block else b'AUTHOR$ ')
    data[0x20] = data[0x30] = 0xcb  # Independent far-return entry points.
    if chain:
        struct.pack_into('<HHHHH8s', data, 0x40, 0xffff, 0xffff, 0x8000,
                         0x60, 0x70, b'SECOND$ ')
        data[0x60] = data[0x70] = 0xcb
    return bytes(data)


def mz_driver(module=None, *, relocation=False):
    module = driver() if module is None else module
    size = 64 + len(module)
    header = bytearray(64)
    struct.pack_into('<14H', header, 0, 0x5a4d, size % 512, (size + 511) // 512,
                     int(relocation), 4, 0, 0xffff, 0, 0, 0, 0, 0, 28, 0)
    if relocation:
        struct.pack_into('<HH', header, 28, 0x50, 0)
    return bytes(header) + module


def driver_with_le_inventory():
    source = bytearray(mz_driver())
    offset = len(source)
    struct.pack_into('<I', source, 60, offset)
    header = bytearray(196 + 48)
    header[:2] = b'LE'
    struct.pack_into('<HH', header, 8, 2, 4)
    for at, value in ((0x10, 0x8020), (0x14, 1), (0x40, 196), (0x44, 2)):
        struct.pack_into('<I', header, at, value)
    # These are descriptor facts only: page contents/fixups are not supplied.
    # Logical object indices may exceed a header's physical-page count;
    # descriptors alone do not validate that logical/physical relationship.
    struct.pack_into('<6I', header, 196, 16, 0, 0x1005, 1, 1, 0)
    struct.pack_into('<6I', header, 220, 16, 0x1000, 0x2005, 2, 1, 0)
    return bytes(source + header)


class DOSDriverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='fdisbull-sys-')
        self.directory = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def source(self, data, name='driver.bin'):
        path = self.directory / name
        path.write_bytes(data)
        return path

    def test_auto_and_explicit_flat_driver_have_both_header_roots(self):
        path = self.source(driver())
        for selector in (None, 'auto', 'sys'):
            with self.subTest(selector=selector):
                image = load_image(path, image=selector)
                self.assertEqual((image.format, image.arch, image.bits), ('SYS', 'x86', 16))
                self.assertEqual(image.entry, 0x10020)
                self.assertEqual({seed.address for seed in image.seeds}, {0x10020, 0x10030})
                self.assertNotIn(0x10000, {seed.address for seed in image.seeds})
                self.assertIsNone(image.metadata['dos']['psp_segment'])
                self.assertIsNone(image.metadata['dos']['stack_ss'])
                self.assertIsNone(image.metadata['dos']['sp'])

    def test_mz_driver_uses_header_roots_instead_of_mz_process_entry(self):
        original = mz_driver(relocation=True)
        image = load_image(self.source(original))
        self.assertEqual(image.format, 'SYS')
        self.assertEqual(image.source_bytes, original)
        self.assertEqual(image.metadata['dos']['header_size'], 64)
        self.assertEqual(image.regions[0].data[0x50:0x52], b'\x90\xa0')
        self.assertEqual(image.metadata['dos_driver']['headers'][0]['file_offset'], 64)
        self.assertEqual({seed.address for seed in image.seeds}, {0x10020, 0x10030})
        self.assertEqual([view['image'] for view in image_views(original)], ['mz', 'sys'])
        self.assertEqual(load_image(self.source(original), image='mz').format, 'MZ')

    def test_mz_driver_does_not_require_a_process_stack_or_psp(self):
        data = bytearray(mz_driver())
        struct.pack_into('<HH', data, 14, 0xefff, 0xffff)
        struct.pack_into('<H', data, 22, 0x8000)
        path = self.source(bytes(data))
        image = load_image(path, image='sys', load_segment=0)
        self.assertEqual(image.entry, 0x20)
        self.assertEqual(image.metadata['dos']['selected_entry_cs'], 0)
        self.assertIsNone(image.metadata['dos']['stack_linear'])
        with self.assertRaises(ValueError):
            load_image(path, image='mz')

    def test_chained_and_block_headers_are_structural_not_filename_guesses(self):
        image = load_image(self.source(driver(chain=True), 'renamed.payload'))
        self.assertEqual(len(image.metadata['dos_driver']['headers']), 2)
        self.assertEqual({seed.address for seed in image.seeds}, {0x10020, 0x10030, 0x10060, 0x10070})
        block = load_image(self.source(driver(block=True), 'block.payload'))
        header = block.metadata['dos_driver']['headers'][0]
        self.assertEqual(header['device_type'], 'block')
        self.assertEqual(header['unit_count'], 1)
        self.assertIsNone(header['name'])
        with self.assertRaises(ValueError):
            load_image(self.source(b'ordinary data without a driver header', 'deceptive.sys'))

    def test_malformed_header_chains_and_entry_targets_are_rejected(self):
        cases = []
        for offset, value in ((0, 0), (0, 0x100), (2, 1), (6, 0), (8, 0xffff)):
            data = bytearray(driver(chain=True))
            struct.pack_into('<H', data, offset, value)
            cases.append(bytes(data))
        cycle = bytearray(driver(chain=True))
        struct.pack_into('<HH', cycle, 0x40, 0, 0)
        cases.append(bytes(cycle))
        cases.extend((driver()[:17], b'\xff' * 4 + bytes(40)))
        for index, data in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaises(ValueError):
                    load_image(self.source(data), image='sys')

    def test_identification_and_inspection_expose_sys_without_a_suffix(self):
        data = driver()
        header = identify_header(data)
        self.assertEqual(header['format'], 'DOS SYS')
        self.assertTrue(header['valid'])
        self.assertEqual([view['image'] for view in header['image_views']], ['sys'])
        inspected = inspect_binary(data)
        self.assertEqual(inspected['selected_image'], 'sys')
        self.assertEqual(inspected['dos_driver']['headers'][0]['name'], 'AUTHOR$')
        self.assertEqual(inspect_binary(mz_driver())['selected_image'], 'sys')

    def test_catalog_recognizes_structural_driver_bytes(self):
        from fdisbull.format_registry import identify_file, format_catalog
        report = identify_file(self.source(driver(), 'opaque.payload'))
        self.assertEqual(report['identification']['format_id'], 'dos-sys')
        self.assertFalse(report['input_executed'])
        formats = format_catalog(catalog_path=self.directory / 'formats.sqlite')['formats']
        self.assertTrue(any(item['format_id'] == 'dos-sys' for item in formats))
        oversized = identify_file(self.source(driver()), max_binary_bytes=32)
        self.assertEqual(oversized['identification']['status'], 'recognized-unsupported-size')
        self.assertIsNone(oversized['identification']['header_valid'])

    def test_embedded_le_widths_are_inventory_not_permission_to_load(self):
        source = self.source(driver_with_le_inventory())
        image = load_image(source)
        inventory = image.metadata['dos_driver']['embedded_le']
        self.assertEqual(inventory['default_widths'], [16, 32])
        self.assertTrue(inventory['metadata_valid'])
        self.assertFalse(inventory['analysis_available'])
        self.assertEqual(inventory['page_count'], 1)
        self.assertEqual(inventory['logical_page_extent'], 2)
        self.assertIn('unvalidated', inventory['page_count_relationship'])
        self.assertFalse(any('page range' in item for item in inventory['unsupported_features']))
        views = image_views(source.read_bytes())
        self.assertEqual([view['image'] for view in views], ['mz', 'sys', 'le'])
        self.assertFalse(views[-1]['available'])
        self.assertEqual(views[-1]['object_inventory']['object_count'], 2)
        inspected = inspect_binary(source.read_bytes(), image='le')
        self.assertEqual(inspected['le_inventory']['default_widths'], [16, 32])
        with self.assertRaises(ValueError):
            load_image(source, image='le')

    def test_mz_relocations_cannot_change_a_driver_offset_or_name(self):
        data = bytearray(mz_driver(relocation=True))
        struct.pack_into('<HH', data, 28, 6, 0)
        with self.assertRaisesRegex(ValueError, 'device-header field'):
            load_image(self.source(bytes(data)), image='sys')

    def test_analysis_starts_with_unknown_caller_registers_and_survives_restart(self):
        path = self.directory / 'driver.fdb'
        with Project.create(path, self.source(driver(chain=True))) as project:
            states = project.db.execute('SELECT registers FROM dos_states WHERE version=1').fetchall()
            self.assertEqual(len(states), 4)
            self.assertTrue(all(json.loads(row[0]) == {} for row in states))
            result = project.analyze(max_instructions=20)
            self.assertTrue(result['stable'])
            self.assertEqual(result['decoded'], 4)
            self.assertEqual(len(project.functions()), 4)
            self.assertTrue(all(item['cs'] == 0x1000 for item in project.functions()))
            self.assertEqual(project.information()['header']['format'], 'DOS SYS')
        with Project(path) as reopened:
            self.assertEqual(reopened.status()['counts']['instructions'], 4)
            self.assertEqual(reopened.disassembly()['instructions'][0]['address'], '0x10020')
            self.assertTrue(reopened.analyze(max_instructions=20)['stable'])

    def test_one_driver_entry_does_not_supply_another_entrys_ds(self):
        data = bytearray(driver())
        data[0x20:0x23] = b'\x0e\x1f\xcb'  # PUSH CS; POP DS; RETF.
        data[0x30:0x34] = b'\xa1\x40\0\xcb'  # MOV AX, DS:[40h]; RETF.
        with Project.create(self.directory / 'registers.fdb', self.source(bytes(data))) as project:
            project.analyze(max_instructions=40)
            row = project.db.execute('SELECT registers FROM dos_states WHERE version=1 AND address=?', ('0000000000010030',)).fetchone()
            self.assertEqual(json.loads(row[0]), {})
            instruction = project.disassembly('1000:0030')['instructions'][0]
            self.assertFalse(any(ref.get('role') == 'memory' for ref in instruction['references']))

    def test_nondefault_segment_queries_reset_and_export_keep_driver_context(self):
        from fdisbull.render import render_snapshot
        with Project.create(self.directory / 'context.fdb', self.source(driver()), load_segment=0x2100) as project:
            project.analyze(max_instructions=20)
            snapshot = project.disassembly('2100:0020')
            self.assertEqual(snapshot['instructions'][0]['context'], 'x86:16:little:cs=2100')
            self.assertEqual(project.cfg('2100:0020')['context'], 'x86:16:little:cs=2100')
            self.assertEqual(project.information('header')['dos_driver']['headers'][0]['strategy_address'], 0x21020)
            project.refresh_dos_state(max_instructions=20)
            self.assertEqual(len(project.functions()), 2)
            output = self.directory / 'driver.svg'
            render_snapshot(snapshot, output)
            self.assertTrue(ET.parse(output).getroot().tag.endswith('svg'))
            self.assertIn('retf', output.read_text())

    def test_sys_cannot_be_launched_as_an_ordinary_dos_process(self):
        from fdisbull.debugger import DebugSession
        with Project.create(self.directory / 'no-launch.fdb', self.source(driver())) as project:
            with self.assertRaisesRegex(ValueError, 'Runtime launch requires'):
                DebugSession(project, '/not/a/backend', str(self.directory))

    def test_driver_call_fallthrough_does_not_inherit_a_c_register_contract(self):
        data = bytearray(driver())
        # PUSH CS; POP DS; CALL 40h; MOV AX, DS:[50h]; RETF.
        data[0x20:0x29] = bytes.fromhex('0e1fe81b00a15000cb')
        data[0x40] = 0xc3
        with Project.create(self.directory / 'calls.fdb', self.source(bytes(data))) as project:
            project.analyze(max_instructions=50)
            row = project.db.execute('SELECT registers FROM dos_states WHERE version=1 AND address=?', ('0000000000010025',)).fetchone()
            self.assertEqual(json.loads(row[0]), {})
            self.assertTrue(any(item['kind'] == 'call' and item['source'] == '0x10022'
                                for item in project.xrefs('1000:0040')))

    def test_mode_control_writes_stop_before_reusing_real_mode_context(self):
        for index, raw in enumerate((bytes.fromhex('0f22c090cb'), bytes.fromhex('0f01f090cb'))):
            with self.subTest(encoding=raw.hex()):
                data = bytearray(driver())
                data[0x20:0x25] = raw
                with Project.create(self.directory / f'mode-{index}.fdb', self.source(bytes(data))) as project:
                    project.analyze(max_instructions=20)
                    first = project.disassembly('1000:0020')['instructions'][0]
                    self.assertEqual(first['flow'], 'stop')
                    addresses = {row[0] for row in project.db.execute('SELECT address FROM instructions WHERE version=1')}
                    self.assertNotIn('0000000000010023', addresses)
                    detail = project.db.execute('SELECT detail FROM work WHERE address=?', ('0000000000010020',)).fetchone()[0]
                    self.assertIn('execution-mode control write', detail)
        data = bytearray(driver())
        data[0x20:0x25] = bytes.fromhex('0f20c090cb')  # Reading CR0 does not change mode.
        with Project.create(self.directory / 'mode-read.fdb', self.source(bytes(data))) as project:
            self.assertEqual(project.analyze(max_instructions=20)['decoded'], 4)

    def test_fresh_cli_processes_import_analyze_restart_and_render_sys(self):
        source = self.source(driver())
        project = self.directory / 'cli.fdb'
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))

        def command(*arguments):
            result = subprocess.run([sys.executable, '-m', 'fdisbull', *map(str, arguments)],
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            document = json.loads(result.stdout)
            self.assertTrue(document['ok'], document)
            return document['result']

        self.assertEqual(command('import', source, project, '--image', 'sys')['format'], 'SYS')
        self.assertTrue(command('analyze', project, '--max-instructions', 20)['stable'])
        source.unlink()
        self.assertEqual(command('status', project)['counts']['instructions'], 2)
        output = self.directory / 'cli.svg'
        command('render', project, output)
        self.assertTrue(ET.parse(output).getroot().tag.endswith('svg'))

    def test_patch_rebuilds_driver_roots_and_keeps_the_parent_immutable(self):
        source = self.source(driver())
        original = source.read_bytes()
        with Project.create(self.directory / 'patch.fdb', source) as project:
            project.analyze(max_instructions=20)
            parent = project.disassembly()['instructions']
            # Change Interrupt's header offset to the same validated far RET.
            child = project.patch('1000:0008', '2000')['version']
            self.assertTrue(project.analyze(version=child, max_instructions=20)['stable'])
            headers = project.information('header', version=child)['dos_driver']['headers']
            self.assertEqual(headers[0]['interrupt_offset'], 0x20)
            self.assertEqual(project.disassembly(version=1)['instructions'], parent)
            child_source = bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?', (child,)).fetchone()[0])
            self.assertEqual(child_source[8:10], b'\x20\0')
            self.assertEqual(bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()[0]), original)
        self.assertEqual(source.read_bytes(), original)

    def test_strategy_patch_changes_version_entry_without_changing_the_parent(self):
        path = self.directory / 'strategy.fdb'
        source = self.source(mz_driver())
        with Project.create(path, source) as project:
            project.analyze(max_instructions=20)
            child = project.patch('1000:0006', '3000')['version']
            project.analyze(version=child, max_instructions=20)
            self.assertEqual(project.status(version=child)['entry'], '0x10030')
            self.assertEqual(project.status(version=1)['entry'], '0x10020')
            self.assertEqual(project.disassembly(version=child)['instructions'][0]['address'], '0x10030')
            retained = bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?', (child,)).fetchone()[0])
        source.unlink()
        with Project(path) as project:
            self.assertEqual(project.status(version=child)['entry'], '0x10030')
            candidate = self.source(retained, 'authored-child.bin')
            self.assertTrue(project.source_candidate(candidate, version=child)['exact_match'])

    def test_invalid_header_patch_rolls_back_the_child(self):
        with Project.create(self.directory / 'rollback.fdb', self.source(driver())) as project:
            before = project.versions()
            with self.assertRaises(ValueError):
                project.patch('1000:0006', '0000')
            self.assertEqual(project.versions(), before)


if __name__ == '__main__':
    unittest.main()
