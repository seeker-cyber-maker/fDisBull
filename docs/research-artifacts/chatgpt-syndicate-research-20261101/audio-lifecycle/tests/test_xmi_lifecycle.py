"""Authored fixtures only; these checks do not execute the original driver."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
from xmi_lifecycle import FormatError, analyze, chunks, events

EOT = bytes([255, 47, 0])
BEGIN = bytes([176, 116, 0])
END = bytes([176, 117, 127])


def chunk(kind: bytes, payload: bytes) -> bytes:
    return kind + len(payload).to_bytes(4, 'big') + payload + (b'\0' if len(payload) & 1 else b'')


def asset(payload: bytes) -> bytes:
    return chunk(b'FORM', b'XMID' + chunk(b'EVNT', payload))


class CensusTests(unittest.TestCase):
    def test_bounded_nested_chunk(self):
        [(offset, payload)] = list(chunks(asset(EOT)))
        self.assertEqual((offset, payload), (20, EOT))

    def test_multiple_streams(self):
        data = chunk(b'CAT ', b'XMID' + asset(EOT) + asset(b'\x01' + EOT))
        self.assertEqual(len(list(chunks(data))), 2)

    def test_delay_units_and_eot(self):
        result = analyze(b'\x7f\x01' + EOT)
        self.assertEqual(result['delay_ticks_linear_pass'], 128)
        self.assertEqual(result['eot_offset'], 2)

    def test_note_duration_vlq(self):
        rows, _ = events(bytes([144, 60, 100, 129, 0]) + EOT)
        self.assertEqual(rows[0]['duration'], 128)
        self.assertEqual(rows[0]['size'], 5)

    def test_two_note_statuses_in_admitted_profile(self):
        rows, _ = events(bytes([128, 60, 0, 1, 144, 61, 100, 2]) + EOT)
        self.assertEqual([row.get('duration') for row in rows[:2]], [1, 2])

    def test_program_event_width(self):
        rows, _ = events(bytes([192, 4]) + EOT)
        self.assertEqual(rows[0]['size'], 2)

    def test_zero_tail_retained(self):
        result = analyze(EOT + b'\0')
        self.assertEqual(result['tail_size'], 1)
        self.assertTrue(result['tail_all_zero'])

    def test_nonzero_tail_not_discarded(self):
        result = analyze(EOT + b'\x7f')
        self.assertFalse(result['tail_all_zero'])

    def test_unbounded_no_delay(self):
        result = analyze(BEGIN + END + EOT)
        self.assertTrue(result['loops'][0]['unbounded_by_zero_count'])
        self.assertEqual(result['loops'][0]['positive_delay_records'], 0)

    def test_delay_outside_loop_is_not_body_delay(self):
        result = analyze(BEGIN + END + b'\x01' + EOT)
        self.assertEqual(result['loops'][0]['positive_delay_records'], 0)
        self.assertEqual(result['delay_records'], 1)

    def test_delay_inside_loop(self):
        result = analyze(BEGIN + b'\x03' + END + EOT)
        self.assertEqual(result['loops'][0]['positive_delay_records'], 1)
        self.assertEqual(result['loops'][0]['delay_ticks_linear_body'], 3)

    def test_finite_repeat(self):
        result = analyze(bytes([176, 116, 2]) + END + EOT)
        self.assertFalse(result['loops'][0]['unbounded_by_zero_count'])

    def test_unmatched_lexical_controls_reported(self):
        self.assertIn('repeat end without lexical begin', analyze(END + EOT)['lexical_issues'])
        self.assertIn('unclosed lexical repeat', analyze(BEGIN + EOT)['lexical_issues'])

    def test_slot_overflow_is_not_accepted_as_four_loops(self):
        result = analyze(BEGIN * 5 + END * 5 + EOT)
        self.assertEqual(len(result['loops']), 5)
        self.assertIn('more than four lexical repeat slots', result['lexical_issues'])

    def test_truncated_chunk_rejected(self):
        with self.assertRaises(FormatError):
            list(chunks(asset(EOT)[:-1]))

    def test_event_extent_rejected(self):
        with self.assertRaises(FormatError):
            events(bytes([255, 1, 8, 42]))

    def test_vlq_budget(self):
        with self.assertRaises(FormatError):
            events(bytes([255, 1, 128, 128, 128, 128, 0]))

    def test_missing_end_rejected(self):
        with self.assertRaises(FormatError):
            events(b'\x01')

    def test_unsupported_system_rejected(self):
        with self.assertRaises(FormatError):
            events(bytes([248]) + EOT)

    def test_nonzero_eot_payload_rejected(self):
        with self.assertRaises(FormatError):
            events(bytes([255, 47, 1, 0]))

    def test_cli_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='authored-xmi-') as temporary:
            root = Path(temporary)
            source, output = root / 'authored.xmi', root / 'receipt.json'
            source.write_bytes(asset(BEGIN + b'\x03' + END + EOT))
            command = [sys.executable, str(TOOLS / 'xmi_lifecycle.py'), str(source), '--output', str(output)]
            first = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = output.read_bytes()
            self.assertEqual(len(json.loads(original)['files']), 1)
            second = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(output.read_bytes(), original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
