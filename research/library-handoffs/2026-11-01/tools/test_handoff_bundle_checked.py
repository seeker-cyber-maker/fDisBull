"""Authored packaging tests; no game, network, or installed fDisBull required."""
import json
import builtins
import io
from unittest import mock
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile
import handoff_bundle_checked as h


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



    def test_exclusive_create_race_preserves_other_writer(self):
        current = self.clone()
        out = self.base / 'race.zip'
        original_open = io.open
        injected = []
        def competing_create(file, mode='r', *args, **kwargs):
            if isinstance(file, (str, Path)) and Path(file) == out and 'x' in mode and not injected:
                with builtins.open(out, 'xb') as stream:
                    stream.write(b'other-writer-output')
                injected.append(True)
            return original_open(file, mode, *args, **kwargs)
        with mock.patch.object(io, 'open', competing_create):
            with self.assertRaises(FileExistsError):
                h.delta(self.root / 'MANIFEST.json', current, out, 'D001')
        self.assertEqual(injected, [True])
        self.assertEqual(out.read_bytes(), b'other-writer-output')

    def test_failed_write_preserves_replacement_path(self):
        current = self.clone()
        out = self.base / 'replaced.zip'
        displaced = self.base / 'owned-partial.zip'
        def replace_then_fail(archive, *args, **kwargs):
            out.rename(displaced)
            out.write_bytes(b'replacement-output')
            raise OSError('injected write failure')
        with mock.patch.object(zipfile.ZipFile, 'writestr', replace_then_fail):
            with self.assertRaisesRegex(OSError, 'injected write failure'):
                h.delta(self.root / 'MANIFEST.json', current, out, 'D001')
        self.assertEqual(out.read_bytes(), b'replacement-output')
        self.assertTrue(displaced.exists())

    def test_failed_write_keeps_partial_for_explicit_review(self):
        current = self.clone()
        out = self.base / 'partial.zip'
        with mock.patch.object(zipfile.ZipFile, 'writestr', side_effect=OSError('injected write failure')):
            with self.assertRaisesRegex(OSError, 'injected write failure'):
                h.delta(self.root / 'MANIFEST.json', current, out, 'D001')
        self.assertTrue(out.exists())
        with self.assertRaises(ValueError):
            h.delta(self.root / 'MANIFEST.json', current, out, 'D002')

    def test_verifier_rejects_checksum_consistent_parent_id_reuse(self):
        for modified in (False, True):
            with self.subTest(modified=modified):
                if not (self.root / 'MANIFEST.json').exists():
                    self.seal()
                current = self.base / ('forged-current-' + str(modified))
                shutil.copytree(self.root, current)
                if modified:
                    (current / 'a.txt').write_text('new')
                good = self.base / ('good-' + str(modified) + '.zip')
                bad = self.base / ('bad-' + str(modified) + '.zip')
                h.delta(self.root / 'MANIFEST.json', current, good, 'D001')
                with zipfile.ZipFile(good) as archive:
                    members = {name: archive.read(name) for name in archive.namelist()}
                result = json.loads(members['RESULT_MANIFEST.json'])
                result['id'] = 'F001'
                members['RESULT_MANIFEST.json'] = h.encoded(result)
                delta = json.loads(members['DELTA.json'])
                delta['id'] = 'F001'
                delta['result_manifest_sha256'] = h.sha(members['RESULT_MANIFEST.json'])
                members['DELTA.json'] = h.encoded(delta)
                members['SHA256SUMS'] = ''.join(
                    f"{h.sha(data)}  {name}\n" for name, data in sorted(members.items())
                    if name != 'SHA256SUMS').encode()
                with zipfile.ZipFile(bad, 'w') as archive:
                    for name, data in members.items():
                        archive.writestr(name, data)
                with self.assertRaises(ValueError):
                    h.verify_delta(bad, self.root / 'MANIFEST.json')


if __name__ == '__main__':
    unittest.main(verbosity=2)
