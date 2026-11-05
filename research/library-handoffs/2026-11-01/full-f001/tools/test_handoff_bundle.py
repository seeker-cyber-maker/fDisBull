"""Authored packaging tests; no game, network, or installed fDisBull required."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile
import handoff_bundle as h


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'root'; self.root.mkdir()
        (self.root / 'a.txt').write_text('old\n')
        (self.root / 'b.txt').write_text('keep\n')

    def seal(self):
        return h.snapshot(self.root, 'F001')

    def clone(self):
        self.seal()
        current = self.base / 'current'
        shutil.copytree(self.root, current)
        return current

    def test_verify_full(self):
        self.seal(); self.assertEqual(h.verify(self.root)['file_count'], 2)

    def test_snapshot_refuses_overwrite(self):
        self.seal()
        with self.assertRaises(ValueError): self.seal()

    def test_content_tamper_refused(self):
        self.seal(); (self.root / 'a.txt').write_text('tamper')
        with self.assertRaises(ValueError): h.verify(self.root)

    def test_extra_file_refused(self):
        self.seal(); (self.root / 'unexpected.txt').write_text('extra')
        with self.assertRaises(ValueError): h.verify(self.root)

    def test_missing_file_refused(self):
        self.seal(); (self.root / 'a.txt').unlink()
        with self.assertRaises(ValueError): h.verify(self.root)

    def test_checksum_tamper_refused(self):
        self.seal(); (self.root / 'SHA256SUMS').write_text('bad')
        with self.assertRaises(ValueError): h.verify(self.root)

    def test_symlink_refused(self):
        (self.root / 'link').symlink_to(self.root / 'a.txt')
        with self.assertRaises(ValueError): h.scan(self.root)

    def test_unsafe_names_refused(self):
        for name in ['../x', '/x', 'a/../x', 'a//b', 'a\\b', 'C:x', 'a\nb']:
            with self.subTest(name=name), self.assertRaises(ValueError): h.safe_name(name)

    def test_manifest_duplicate_refused(self):
        self.seal(); m = json.loads((self.root / 'MANIFEST.json').read_text())
        m['files'].append(m['files'][0]); m['file_count'] += 1
        with self.assertRaises(ValueError): h.read_manifest(h.encoded(m))

    def test_delta_add_modify_delete(self):
        current = self.clone()
        (current / 'a.txt').write_text('new\n'); (current / 'b.txt').unlink()
        (current / 'c.txt').write_text('added\n')
        out = self.base / 'D001.zip'
        r = h.delta(self.root / 'MANIFEST.json', current, out, 'D001')
        self.assertEqual((r['added'], r['modified'], r['deleted']), (1, 1, 1))
        self.assertTrue((self.root / 'b.txt').exists())
        self.assertEqual((self.root / 'a.txt').read_text(), 'old\n')
        with zipfile.ZipFile(out) as z:
            self.assertEqual(set(z.namelist()), {'DELTA.json', 'RESULT_MANIFEST.json', 'SHA256SUMS', 'payload/a.txt', 'payload/c.txt'})

    def test_empty_delta_contains_no_payload(self):
        current = self.clone()
        r = h.delta(self.root / 'MANIFEST.json', current, self.base / 'empty.zip', 'D001')
        self.assertEqual((r['added'], r['modified'], r['deleted'], r['unchanged']), (0, 0, 0, 2))

    def test_wrong_parent_refused(self):
        current = self.clone(); out = self.base / 'D001.zip'
        h.delta(self.root / 'MANIFEST.json', current, out, 'D001')
        m = json.loads((self.root / 'MANIFEST.json').read_text()); m['id'] = 'different'
        wrong = self.base / 'wrong.json'; wrong.write_bytes(h.encoded(m))
        with self.assertRaises(ValueError): h.verify_delta(out, wrong)

    def test_delta_refuses_overwrite_and_inside_root(self):
        current = self.clone(); out = self.base / 'D001.zip'
        h.delta(self.root / 'MANIFEST.json', current, out, 'D001')
        with self.assertRaises(ValueError): h.delta(self.root / 'MANIFEST.json', current, out, 'D002')
        with self.assertRaises(ValueError): h.delta(self.root / 'MANIFEST.json', current, current / 'inside.zip', 'D002')

    def test_parent_id_cannot_be_reused(self):
        current = self.clone()
        with self.assertRaises(ValueError): h.delta(self.root / 'MANIFEST.json', current, self.base / 'x.zip', 'F001')

    def test_tampered_delta_refused(self):
        current = self.clone(); (current / 'a.txt').write_text('new')
        out = self.base / 'D001.zip'; bad = self.base / 'bad.zip'
        h.delta(self.root / 'MANIFEST.json', current, out, 'D001')
        with zipfile.ZipFile(out) as z, zipfile.ZipFile(bad, 'w') as w:
            for name in z.namelist():
                w.writestr(name, b'tampered' if name == 'payload/a.txt' else z.read(name))
        with self.assertRaises(ValueError): h.verify_delta(bad, self.root / 'MANIFEST.json')

    def test_unchanged_files_omitted(self):
        current = self.clone(); (current / 'a.txt').write_text('different')
        out = self.base / 'D001.zip'
        r = h.delta(self.root / 'MANIFEST.json', current, out, 'D001')
        self.assertEqual(r['unchanged'], 1)
        with zipfile.ZipFile(out) as z: self.assertNotIn('payload/b.txt', z.namelist())


if __name__ == '__main__':
    unittest.main(verbosity=2)
