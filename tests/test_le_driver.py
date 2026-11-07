"""Authored LE modules only: mixed code widths and symbolic loader fixups."""
from __future__ import annotations

import hashlib
import json
import struct
import unittest

from fdisbull.le_driver import disassemble_le_driver, inspect_le_driver


def le_driver(*, payloads=(b'\xb8\x34\x12\x90\x90\xc3', b'\xc3'),
              flags=(0x1005, 0x2005), sizes=None, records=None, bare=False,
              entry=(0, 0), page_flags=None, physical_order=None,
              imports=(), procedures=b''):
    """Construct a small LE file directly from documented field offsets.

    All content is authored here. Logical pages can use a different order from
    physical file pages; uninitialized bytes are never generated as code.
    """
    sizes = tuple(map(len, payloads)) if sizes is None else sizes
    counts = [(len(p) + 4095) // 4096 for p in payloads]
    count = sum(counts)
    records = [b''] * count if records is None else records
    page_flags = [0] * count if page_flags is None else page_flags
    if physical_order is None:
        physical_order = []
        physical = 0
        for flag in page_flags:
            if flag == 0:
                physical += 1
                physical_order.append(physical)
            else:
                physical_order.append(0)
    h = 0 if bare else 0x80
    objects = 196
    page_map = objects + len(payloads) * 24
    fixup_pages = page_map + count * 4
    physical_count = max(physical_order, default=0)
    physical_records = [b''] * physical_count
    for physical, record in zip(physical_order, records):
        if physical:
            if physical_records[physical - 1] and physical_records[physical - 1] != record:
                raise ValueError('authored physical-page aliases need identical fixup records')
            physical_records[physical - 1] = record
        elif record:
            raise ValueError('authored zero-fill page cannot have physical fixup records')
    fixup_records = fixup_pages + (physical_count + 1) * 4
    record_data = b''.join(physical_records)
    module_data = b''.join(bytes([len(name)]) + name for name in imports)
    modules = fixup_records + len(record_data)
    procs = modules + len(module_data)
    fixup_size = procs + len(procedures) - fixup_pages
    data_start = (h + fixup_pages + fixup_size + 15) & ~15
    result = bytearray(data_start)
    if not bare:
        result[:2] = b'MZ'
        struct.pack_into('<H', result, 24, 64)
        struct.pack_into('<I', result, 60, h)
    result[h:h + 2] = b'LE'
    struct.pack_into('<HH', result, h + 8, 2, 4)
    physical_payloads = {}
    logical = 0
    for payload in payloads:
        for start in range(0, len(payload), 4096):
            if page_flags[logical] == 0:
                physical_payloads[physical_order[logical]] = payload[start:start + 4096]
            logical += 1
    last = max(physical_payloads, default=0)
    last_size = len(physical_payloads[last]) if last else 0
    for field, value in {
        0x10: 0x8020, 0x14: physical_count, 0x18: entry[0], 0x1c: entry[1],
        0x28: 4096, 0x2c: last_size, 0x30: fixup_size,
        0x40: objects, 0x44: len(payloads), 0x48: page_map,
        0x68: fixup_pages, 0x6c: fixup_records,
        0x70: modules if imports else 0, 0x74: len(imports),
        0x78: procs if procedures else 0, 0x80: data_start,
    }.items():
        struct.pack_into('<I', result, h + field, value)
    logical = 0
    for index, (payload, size, flag, pages) in enumerate(zip(payloads, sizes, flags, counts)):
        struct.pack_into('<6I', result, h + objects + index * 24,
                         size, index * 0x10000, flag, logical + 1 if pages else 0, pages, 0)
        for _ in range(pages):
            p = h + page_map + logical * 4
            result[p:p + 4] = physical_order[logical].to_bytes(3, 'big') + bytes([page_flags[logical]])
            logical += 1
    cursor = 0
    for index, record in enumerate([*physical_records, b'']):
        struct.pack_into('<I', result, h + fixup_pages + index * 4, cursor)
        cursor += len(record)
    result[h + fixup_records:h + fixup_records + len(record_data)] = record_data
    result[h + modules:h + modules + len(module_data)] = module_data
    result[h + procs:h + procs + len(procedures)] = procedures
    for physical in range(1, last + 1):
        part = physical_payloads.get(physical, b'')
        result += part.ljust(last_size if physical == last else 4096, b'\0')
    return bytes(result)


def internal(source_type, source_offset, target_object, target_offset=0, *, target_flags=0):
    result = struct.pack('<BBh', source_type, target_flags, source_offset)
    result += target_object.to_bytes(2 if target_flags & 0x40 else 1, 'little')
    if source_type & 0xf != 2:
        result += target_offset.to_bytes(4 if target_flags & 0x10 else 2, 'little')
    return result


def device_payload(size=64, *, strategy=24, interrupt=59):
    """Authored device-header structure and independent tiny handlers."""
    result = bytearray(size)
    struct.pack_into('<5H8s', result, 0, 0xffff, 0xffff, 0x8000,
                     strategy, interrupt, b'AUTHDRV$')
    result[strategy:strategy + 2] = b'\x90\xcb'
    result[interrupt:interrupt + 2] = b'\xf8\xcb'
    return bytes(result)


class LEDriverTests(unittest.TestCase):
    def test_mixed_widths_are_object_local_and_zero_entry_stays_absent(self):
        data = le_driver()
        report = inspect_le_driver(data)
        self.assertEqual(report['format'], 'LE')
        self.assertIsNone(report['bits'])
        self.assertIsNone(report['entrypoint'])
        self.assertEqual([o['bits'] for o in report['objects']], [16, 32])
        self.assertEqual(report['source_sha256'], hashlib.sha256(data).hexdigest())
        code16 = disassemble_le_driver(data, 1)
        self.assertEqual([i['size'] for i in code16['instructions']], [3, 1, 1, 1])
        self.assertEqual(code16['instructions'][0]['mnemonic'], 'mov')
        self.assertIn('ax,', code16['instructions'][0]['operands'])
        self.assertEqual(code16['stop_reason'], 'return')
        data32 = le_driver(flags=(0x2005, 0x2005))
        self.assertEqual([i['size'] for i in disassemble_le_driver(data32, 1)['instructions']], [5, 1])
        json.dumps(report)
        json.dumps(code16)

    def test_bare_le_and_declared_entry_keep_object_coordinates(self):
        report = inspect_le_driver(le_driver(bare=True, entry=(2, 0)))
        self.assertEqual(report['header_offset'], 0)
        self.assertEqual(report['entrypoint']['object'], 2)
        self.assertEqual(report['entrypoint']['offset'], 0)
        report = inspect_le_driver(le_driver(entry=(0, 123)))
        self.assertIsNone(report['entrypoint'])

    def test_device_header_entry_is_data_with_independent_object_roots(self):
        data = le_driver(payloads=(device_payload(),), flags=(0x1005,), entry=(1, 0))
        report = inspect_le_driver(data)
        device = report['objects'][0]['dos_device']
        self.assertEqual(device['headers'][0]['name'], 'AUTHDRV$')
        self.assertEqual(device['headers'][0]['file_offset'], report['pages'][0]['file_offset'])
        self.assertEqual([(root['role'], root['object'], root['offset']) for root in device['entry_roots']],
                         [('strategy', 1, 24), ('interrupt', 1, 59)])
        self.assertTrue(all(root['initial_registers'] == {} for root in device['entry_roots']))
        self.assertEqual(report['header']['start_obj'], 1)
        self.assertEqual(report['header']['eip'], 0)
        self.assertEqual(report['entrypoint']['classification'], 'dos_device_header')
        self.assertFalse(report['entrypoint']['code_view_available'])
        for offset in (0, 1, 17):
            view = disassemble_le_driver(data, 1, offset=offset)
            self.assertEqual(view['stop_reason'], 'dos_device_header')
            self.assertEqual(view['instructions'], [])
            self.assertEqual(view['dos_device']['entry_roots'], device['entry_roots'])
        for offset in (24, 59):
            view = disassemble_le_driver(data, 1, offset=offset)
            self.assertEqual(view['stop_reason'], 'return')
            self.assertEqual(len(view['instructions']), 2)
        absent = inspect_le_driver(le_driver(payloads=(device_payload(),), flags=(5,)))
        self.assertIsNone(absent['entrypoint'])
        self.assertEqual(len(absent['objects'][0]['dos_device']['entry_roots']), 2)

    def test_device_header_probe_refuses_malformed_or_unbacked_structure(self):
        payload = device_payload()
        for field, value in ((0, 0xffff), (2, 1), (6, 6), (8, len(payload)), (10, 0)):
            with self.subTest(field=field):
                broken = bytearray(payload)
                if field == 0:
                    struct.pack_into('<HH', broken, 0, value, 0)
                else:
                    struct.pack_into('<H', broken, field, value)
                report = inspect_le_driver(le_driver(payloads=(bytes(broken),), flags=(5,), entry=(1, 0)))
                self.assertNotIn('dos_device', report['objects'][0])
                self.assertNotIn('classification', report['entrypoint'])
        for changes in ({'flags': (0x2005,)}, {'flags': (5,), 'page_flags': [3]}):
            with self.subTest(changes=changes):
                report = inspect_le_driver(le_driver(payloads=(payload,), **changes))
                self.assertNotIn('dos_device', report['objects'][0])
        truncated = le_driver(payloads=(payload[:18],), flags=(5,), sizes=(64,))
        self.assertNotIn('dos_device', inspect_le_driver(truncated)['objects'][0])

    def test_fixup_affected_device_header_fields_do_not_establish_roots(self):
        data = le_driver(payloads=(device_payload(),), flags=(5,),
                         records=[internal(5, 6, 1, 24)], entry=(1, 0))
        report = inspect_le_driver(data)
        self.assertNotIn('dos_device', report['objects'][0])
        self.assertIn('dos_device_header_has_fixups', {item['code'] for item in report['diagnostics']})

    def test_device_roots_use_physical_source_fragments_after_page_reordering(self):
        data = le_driver(payloads=(device_payload(4128, interrupt=4104),), flags=(5,),
                         physical_order=[2, 1], entry=(1, 0))
        report = inspect_le_driver(data)
        device = report['objects'][0]['dos_device']
        self.assertEqual(device['headers'][0]['file_offset'], report['pages'][0]['file_offset'])
        root = device['entry_roots'][1]
        self.assertEqual(root['offset'], 4104)
        self.assertEqual(root['file_offset'], report['pages'][1]['file_offset'] + 8)
        self.assertLess(root['file_offset'], device['headers'][0]['file_offset'])
        view = disassemble_le_driver(data, 1, offset=root['offset'])
        self.assertEqual(view['stop_reason'], 'return')
        self.assertEqual(view['instructions'][0]['file_offset'], root['file_offset'])

    def test_chained_device_headers_are_data_even_inside_an_object(self):
        payload = bytearray(device_payload(128))
        struct.pack_into('<HH', payload, 0, 64, 0)
        struct.pack_into('<5H8s', payload, 64, 0xffff, 0xffff, 0x8000, 100, 104, b'SECOND $')
        payload[63] = 0xb8  # Would consume the following header as its immediate.
        payload[100:102] = payload[104:106] = b'\x90\xcb'
        data = le_driver(payloads=(bytes(payload),), flags=(5,), entry=(1, 64))
        report = inspect_le_driver(data)
        self.assertEqual(report['objects'][0]['dos_device']['header_count'], 2)
        self.assertEqual(report['entrypoint']['header_index'], 1)
        self.assertFalse(report['entrypoint']['code_view_available'])
        self.assertEqual(disassemble_le_driver(data, 1, offset=64)['stop_reason'], 'dos_device_header')
        self.assertEqual(disassemble_le_driver(data, 1, offset=63)['stop_reason'],
                         'instruction_overlaps_device_header')

    def test_selector_fixup_has_no_fabricated_runtime_selector(self):
        record = internal(0x12, 1, 2)
        data = le_driver(payloads=(b'\xb8\0\0\xcb', b'\xc3'), records=[record, b''])
        report = inspect_le_driver(data)
        fixup = report['fixups'][0]
        self.assertEqual(fixup['source_type'], 'selector16')
        self.assertEqual(fixup['source_width'], 2)
        self.assertEqual(fixup['target']['object'], 2)
        self.assertIsNone(fixup['target']['selector'])
        self.assertFalse(fixup['applied'])
        instruction = disassemble_le_driver(data, 1)['instructions'][0]
        self.assertEqual(instruction['fixups'][0]['index'], 0)
        self.assertEqual(instruction['bytes'], 'b80000')
        self.assertEqual(instruction['operand_status'], 'symbolic_fixups')

    def test_far_pointer_fixups_remain_symbolic_at_both_widths(self):
        for bits, source_type, code in ((16, 3, b'\x9a' + bytes(4) + b'\xcb'),
                                        (32, 6, b'\x9a' + bytes(6) + b'\xcb')):
            with self.subTest(bits=bits):
                data = le_driver(payloads=(code, b'\xc3'), flags=(5 | (0x2000 if bits == 32 else 0), 0x2005),
                                 records=[internal(source_type, 1, 2), b''])
                report = disassemble_le_driver(data, 1)
                instruction = report['instructions'][0]
                self.assertEqual(instruction['bits'], bits)
                self.assertIsNone(instruction['target_location'])
                self.assertEqual(instruction['symbolic_targets'][0]['object'], 2)
                self.assertIsNone(instruction['symbolic_targets'][0]['selector'])
                self.assertEqual(instruction['bytes'], code[:-1].hex())

    def test_source_list_and_relative_fixups_have_bounded_sources(self):
        code = b'\xb8' + bytes(4) + b'\xb9' + bytes(4) + b'\xc3'
        record = struct.pack('<BBBBHhh', 0x27, 0, 2, 2, 0, 1, 6)
        data = le_driver(payloads=(code, b'\xc3'), flags=(0x2005, 0x2005), records=[record, b''])
        fixup = inspect_le_driver(data)['fixups'][0]
        self.assertEqual([s['offset'] for s in fixup['sources']], [1, 6])
        self.assertEqual(len(disassemble_le_driver(data, 1)['instructions']), 3)
        call = le_driver(payloads=(b'\xe8' + bytes(4) + b'\xc3', b'\xc3'), flags=(0x2005, 0x2005),
                         records=[internal(8, 1, 2), b''])
        instruction = disassemble_le_driver(call, 1)['instructions'][0]
        self.assertIsNone(instruction['target_location'])
        self.assertEqual(instruction['fixups'][0]['source_type'], 'relative32')

    def test_imports_and_entry_ordinals_are_metadata_not_bound_addresses(self):
        code = b'\xb8' + bytes(4) + b'\xc3'
        records = (
            (struct.pack('<BBhBB', 7, 0x81, 1, 1, 3), 'import_ordinal'),
            (struct.pack('<BBhBIH', 7, 0x16, 1, 1, 0, 2), 'import_name'),
            (struct.pack('<BBhB', 7, 3, 1, 7), 'internal_entry'),
        )
        for record, kind in records:
            with self.subTest(kind=kind):
                data = le_driver(payloads=(code, b'\xc3'), flags=(0x2005, 0x2005), records=[record, b''],
                                 imports=(b'LIBRARY',), procedures=b'\x04Proc')
                fixup = inspect_le_driver(data)['fixups'][0]
                self.assertEqual(fixup['target']['kind'], kind)
                self.assertFalse(fixup['applied'])
                self.assertIsNone(disassemble_le_driver(data, 1)['instructions'][0]['target_location'])
                if kind == 'import_name':
                    self.assertEqual(fixup['target']['name'], 'Proc')
                    self.assertEqual(fixup['addend'], 2)

    def test_cross_page_bytes_preserve_noncontiguous_file_provenance(self):
        code = b'\x90' * 4094 + b'\xb8' + bytes(4) + b'\xc3'
        records = [internal(7, 4095, 2), internal(7, -1, 2), b'']
        data = le_driver(payloads=(code, b'\xc3'), flags=(0x2005, 0x2005), records=records,
                         physical_order=[1, 3, 2])
        report = disassemble_le_driver(data, 1, offset=4094)
        ins = report['instructions'][0]
        self.assertEqual(ins['bytes'], 'b800000000')
        self.assertEqual([f['size'] for f in ins['file_fragments']], [2, 3])
        self.assertIsNone(ins['file_offset'])
        self.assertEqual(len(ins['fixups']), 2)
        self.assertEqual(report['instructions'][1]['offset'], 4099)

    def test_fixups_overlapping_opcodes_or_entered_operands_block_decode(self):
        data = le_driver(payloads=(b'\xb8' + bytes(4) + b'\xc3', b'\xc3'), flags=(0x2005, 0x2005),
                         records=[internal(7, 0, 2), b''])
        report = disassemble_le_driver(data, 1)
        self.assertEqual(report['instructions'], [])
        self.assertEqual(report['stop_reason'], 'fixup_overlaps_instruction_structure')
        operand = le_driver(payloads=(b'\xb8' + bytes(4) + b'\xc3', b'\xc3'), flags=(0x2005, 0x2005),
                            records=[internal(7, 1, 2), b''])
        report = disassemble_le_driver(operand, 1, offset=2)
        self.assertEqual(report['instructions'], [])
        self.assertEqual(report['stop_reason'], 'fixup_overlaps_instruction_structure')

    def test_opaque_fixups_block_the_object_instead_of_guessed_skipping(self):
        for record in (b'\x04\0\0\0\x01\0\0', internal(7, 1, 2, target_flags=8)):
            with self.subTest(record=record.hex()):
                data = le_driver(payloads=(b'\xb8' + bytes(4) + b'\xc3', b'\xc3'), flags=(0x2005, 0x2005),
                                 records=[record, b''])
                report = inspect_le_driver(data)
                self.assertFalse(report['objects'][0]['fixups_complete'])
                view = disassemble_le_driver(data, 1)
                self.assertEqual(view['instructions'], [])
                self.assertEqual(view['stop_reason'], 'unsupported_fixups')

    def test_zero_fill_and_iterated_pages_are_not_decoded_as_file_bytes(self):
        for flag, stop in ((3, 'non_file_backed'), (1, 'unsupported_page_encoding')):
            with self.subTest(flag=flag):
                data = le_driver(page_flags=[0, flag])
                report = disassemble_le_driver(data, 2)
                self.assertEqual(report['instructions'], [])
                self.assertEqual(report['stop_reason'], stop)

    def test_explicit_vxd_abi_consumes_inline_service_but_unknown_does_not(self):
        code = b'\xcd\x20' + struct.pack('<I', 0x00010002) + b'\xc3'
        data = le_driver(payloads=(code, b'\xc3'), flags=(0x2005, 0x2005))
        unknown = disassemble_le_driver(data, 1)
        self.assertEqual(unknown['instructions'][0]['size'], 2)
        self.assertEqual(unknown['stop_reason'], 'ambiguous_int20')
        explicit = disassemble_le_driver(data, 1, abi='windows-vxd')
        instruction = explicit['instructions'][0]
        self.assertEqual(instruction['size'], 6)
        self.assertEqual(instruction['flow'], 'service')
        self.assertEqual(instruction['vxd_service']['identifier'], 0x10002)
        self.assertEqual(instruction['vxd_service']['device_id'], 1)
        self.assertEqual(instruction['vxd_service']['ordinal_raw'], 2)
        self.assertEqual(explicit['stop_reason'], 'external_service')
        self.assertNotIn('exit', instruction['text'])

    def test_incomplete_or_fixup_affected_vxd_service_is_qualified(self):
        short = le_driver(payloads=(b'\xcd\x20\0\0', b'\xc3'), flags=(0x2005, 0x2005))
        report = disassemble_le_driver(short, 1, abi='windows-vxd')
        self.assertEqual(report['instructions'], [])
        self.assertEqual(report['stop_reason'], 'truncated_vxd_service')
        data = le_driver(payloads=(b'\xcd\x20' + bytes(4), b'\xc3'), flags=(0x2005, 0x2005),
                         records=[internal(7, 2, 2), b''])
        instruction = disassemble_le_driver(data, 1, abi='windows-vxd')['instructions'][0]
        self.assertIsNone(instruction['vxd_service']['identifier'])
        self.assertEqual(instruction['operand_status'], 'symbolic_fixups')

    def test_vxd_abi_does_not_reclassify_a_16_bit_initialization_object(self):
        data = le_driver(payloads=(b'\xcd\x20' + bytes(4), b'\xc3'))
        report = disassemble_le_driver(data, 1, abi='windows-vxd')
        self.assertEqual(report['instructions'][0]['size'], 2)
        self.assertEqual(report['stop_reason'], 'ambiguous_int20')

    def test_bounds_and_public_budgets_reject_invalid_inputs(self):
        data = le_driver()
        for count in (True, False, 0, -1, 4097, 1.5, '2'):
            with self.subTest(count=count), self.assertRaises(ValueError):
                disassemble_le_driver(data, 1, max_instructions=count)
        for obj in (True, 0, 3, 1.0):
            with self.subTest(obj=obj), self.assertRaises(ValueError):
                disassemble_le_driver(data, obj)
        for offset in (True, -1, 7, 1.0):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                disassemble_le_driver(data, 1, offset=offset)
        with self.assertRaises(ValueError):
            disassemble_le_driver(data, 1, abi='dos')
        for invalid in (bytearray(data), b'', data[:100], b'LX' + data[2:]):
            with self.subTest(length=len(invalid)), self.assertRaises(ValueError):
                inspect_le_driver(invalid)
        bounded = disassemble_le_driver(data, 1, max_instructions=1)
        self.assertEqual(len(bounded['instructions']), 1)
        self.assertEqual(bounded['stop_reason'], 'instruction_budget')
        self.assertTrue(bounded['budget_exhausted'])

    def test_invalid_tables_and_truncated_fixups_fail_with_value_errors(self):
        data = le_driver()
        for field, value in ((0x40, 0xfffffff0), (0x44, 4097), (0x14, 16385),
                             (0x28, 8192), (0x18, 3), (0x48, 196)):
            changed = bytearray(data)
            struct.pack_into('<I', changed, 0x80 + field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                inspect_le_driver(bytes(changed))
        for record in (b'\x07\0\x01', internal(7, 4095, 2), internal(2, 1, 3)):
            changed = le_driver(records=[record, b''])
            with self.subTest(record=record.hex()), self.assertRaises(ValueError):
                inspect_le_driver(changed)

    def test_unbacked_entry_is_reported_without_making_a_seed(self):
        # Only the final physical page is short; non-final pages really contain
        # their padding bytes and therefore cannot establish this condition.
        data = le_driver(sizes=(6, 100), entry=(2, 20))
        report = inspect_le_driver(data)
        self.assertEqual(report['entrypoint']['offset'], 20)
        self.assertFalse(report['entrypoint']['file_backed'])
        self.assertFalse(report['entrypoint']['code_view_available'])

    def test_tail_object_beyond_declared_map_preserves_other_objects(self):
        data = bytearray(le_driver())
        # The next table starts after only one page-map entry. Preserve the
        # second descriptor, but do not consume that next table as a map entry.
        struct.pack_into('<I', data, 0x80 + 0x58, 196 + 48 + 4)
        report = inspect_le_driver(bytes(data))
        self.assertEqual(len(report['objects']), 2)
        self.assertEqual(len(report['pages']), 1)
        self.assertTrue(report['objects'][0]['mapping_complete'])
        self.assertFalse(report['objects'][1]['mapping_complete'])
        self.assertFalse(report['coverage']['object_mappings_complete'])
        self.assertEqual(report['objects'][1]['first_page'], 2)
        self.assertEqual(disassemble_le_driver(bytes(data), 1)['stop_reason'], 'return')
        blocked = disassemble_le_driver(bytes(data), 2)
        self.assertEqual(blocked['instructions'], [])
        self.assertEqual(blocked['stop_reason'], 'unsupported_object_mapping')

    def test_zero_fill_logical_page_does_not_shift_physical_fixups(self):
        code = b'\xb8' + bytes(4) + b'\xc3'
        data = le_driver(payloads=(b'\0' * 16, code, b'\xc3'), flags=(0x2003, 0x2005, 0x2005),
                         page_flags=[3, 0, 0], records=[b'', internal(7, 1, 3), b''])
        report = inspect_le_driver(data)
        self.assertEqual(report['physical_page_count'], 2)
        self.assertEqual(report['logical_page_count'], 3)
        self.assertEqual([p['physical_page'] for p in report['pages']], [0, 1, 2])
        self.assertEqual(report['fixup_section']['index_domain'], 'physical_page')
        self.assertEqual(report['fixups'][0]['sources'][0]['object'], 2)
        self.assertEqual(report['fixups'][0]['sources'][0]['offset'], 1)
        instruction = disassemble_le_driver(data, 2)['instructions'][0]
        self.assertEqual(instruction['fixups'][0]['target']['object'], 3)

    def test_two_objects_may_reference_the_same_physical_page(self):
        code = b'\xb8' + bytes(4) + b'\xc3'
        record = internal(7, 1, 1)
        data = le_driver(payloads=(code, code), flags=(0x2005, 0x2005),
                         physical_order=[1, 1], records=[record, record])
        report = inspect_le_driver(data)
        self.assertEqual(report['physical_page_count'], 1)
        self.assertEqual(report['logical_page_count'], 2)
        self.assertEqual(report['pages'][0]['file_offset'], report['pages'][1]['file_offset'])
        self.assertEqual({f['sources'][0]['object'] for f in report['fixups']}, {1, 2})
        one, two = [disassemble_le_driver(data, obj)['instructions'][0] for obj in (1, 2)]
        self.assertEqual(one['bytes'], two['bytes'])
        self.assertEqual(one['file_offset'], two['file_offset'])
        self.assertNotEqual(one['location']['object'], two['location']['object'])

    def test_overlapping_fixups_are_not_silently_merged(self):
        code = b'\xb8' + bytes(8)
        records = internal(7, 1, 2) + internal(7, 2, 2)
        with self.assertRaises(ValueError):
            inspect_le_driver(le_driver(payloads=(code, b'\xc3'), records=[records, b'']))

    def test_outside_target_expression_is_retained_but_never_followed(self):
        data = le_driver(payloads=(b'\xb8' + bytes(4) + b'\xc3', b'\xc3'),
                         flags=(0x2005, 0x2005),
                         records=[internal(7, 1, 2, 0xffffffff, target_flags=0x10), b''])
        report = inspect_le_driver(data)
        self.assertEqual(report['fixups'][0]['target']['offset'], 0xffffffff)
        self.assertFalse(report['fixups'][0]['target']['offset_within_object'])
        self.assertIn('fixup_target_outside_object', {d['code'] for d in report['diagnostics']})
        view = disassemble_le_driver(data, 1)
        self.assertIsNone(view['instructions'][0]['target_location'])
        self.assertFalse(view['instructions'][0]['fixups'][0]['applied'])

    def test_unconditional_control_transfer_is_a_bounded_stop(self):
        data = le_driver(payloads=(b'\xeb\x02\x90\x90\xc3', b'\xc3'))
        result = disassemble_le_driver(data, 1)
        self.assertEqual(len(result['instructions']), 1)
        self.assertEqual(result['instructions'][0]['target_location']['offset'], 4)
        self.assertEqual(result['stop_reason'], 'jump')


if __name__ == '__main__':
    unittest.main()
