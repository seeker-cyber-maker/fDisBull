"""CI policy and dependency cache invariants; no native build required."""
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / '.github/ci' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cache = load('native_cache')
policy = load('event_policy')


class CacheContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('.github/ci/native-build.sh', '.github/ci/native_cache.py',
                     'experimental/dosbox-x/source-manifest.json',
                     'experimental/dosbox-x/headless-agent.patch'):
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / name).read_bytes())
        self.directory = self.root / '.native-cache/dosbox'
        self.directory.mkdir(parents=True)
        (self.directory / 'dosbox-x').write_bytes(b'\x7fELFsynthetic-binary-for-inventory-tests')
        (self.directory / 'dosbox-x').chmod(0o755)
        self.libpatch = patch.object(cache, 'runtime_libraries', return_value={'/test/libc.so': 'identity'})
        self.libpatch.start()
        self.addCleanup(self.libpatch.stop)
        self.expected = self.identity()

    def identity(self, probe=lambda args: 'stable-build-tools-and-packages'):
        return cache.identity(self.root, 'dosbox', 'experimental/dosbox-x', probe)

    def test_same_inputs_reuse_and_application_changes_do_not_invalidate(self):
        cache.seal(self.directory, self.expected)
        self.assertTrue(cache.validate(self.directory, self.identity()))
        (self.root / 'application.py').write_text('a new application commit')
        self.assertEqual(self.expected, self.identity())

    def test_patch_manifest_script_and_profile_each_invalidate(self):
        for name in self.expected['inputs']:
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(original + b'changed')
                self.assertNotEqual(self.expected, self.identity())
                path.write_bytes(original)
        (self.root / 'other-profile').mkdir()
        for name in ('source-manifest.json', 'headless-agent.patch'):
            shutil.copyfile(self.root / 'experimental/dosbox-x' / name, self.root / 'other-profile' / name)
        self.assertNotEqual(self.expected, cache.identity(self.root, 'dosbox', 'other-profile', lambda args: 'stable-build-tools-and-packages'))

    def test_toolchain_packages_architecture_os_and_build_flags_invalidate(self):
        self.assertNotEqual(self.expected, self.identity(lambda args: 'different-toolchain-or-package-version'))
        for method in ('machine', 'system'):
            with patch.object(cache.platform, method, return_value='different'):
                self.assertNotEqual(self.expected, self.identity())
        for name in ('CFLAGS', 'ImageVersion', 'PKG_CONFIG_PATH'):
            with patch.dict(os.environ, {name: 'changed'}):
                self.assertNotEqual(self.expected, self.identity())

    def test_qemu_source_pin_and_flags_are_content_addressed(self):
        original = cache.identity(self.root, 'qemu', 'qemu-9.2.4', lambda args: 'tools')
        path = self.root / '.github/ci/native-build.sh'
        path.write_text(path.read_text().replace('qemu-9.2.4', 'qemu-9.2.5'))
        changed = cache.identity(self.root, 'qemu', 'qemu-9.2.4', lambda args: 'tools')
        self.assertNotEqual(original, changed)

    def test_missing_corrupt_extra_truncated_and_mode_changed_cache_rebuild(self):
        for kind in ('missing', 'corrupt', 'extra', 'truncated', 'mode', 'receipt', 'identity'):
            with self.subTest(kind=kind):
                self.directory.mkdir(parents=True, exist_ok=True)
                binary = self.directory / 'dosbox-x'
                binary.write_bytes(b'\x7fELFtest')
                binary.chmod(0o755)
                cache.seal(self.directory, self.expected)
                expected = copy.deepcopy(self.expected)
                if kind == 'missing': binary.unlink()
                if kind == 'corrupt': binary.write_bytes(b'\x7fELFchanged')
                if kind == 'extra': (self.directory / 'extra').write_text('unrecorded')
                if kind == 'truncated': binary.write_bytes(b'')
                if kind == 'mode': binary.chmod(0o644)
                if kind == 'receipt': (self.directory / 'receipt.json').write_text('{')
                if kind == 'identity': expected['architecture'] = 'other'
                self.assertFalse(cache.validate(self.directory, expected))
                self.assertFalse(self.directory.exists())
        self.assertFalse(cache.validate(self.directory, self.expected))

    def test_corrupt_regular_file_cache_root_is_removed_for_rebuild(self):
        shutil.rmtree(self.directory)
        self.directory.write_bytes(b'not a cache directory')
        self.assertFalse(cache.validate(self.directory, self.expected))
        self.assertFalse(self.directory.exists())
        self.directory.mkdir()
        (self.directory / 'dosbox-x').write_bytes(b'\x7fELFrebuilt')
        (self.directory / 'dosbox-x').chmod(0o755)
        cache.seal(self.directory, self.expected)
        self.assertTrue(cache.validate(self.directory, self.expected))

    def test_symlink_is_rejected_without_modifying_target(self):
        outside = self.root / 'outside'
        outside.write_text('untouched')
        (self.directory / 'receipt.json').symlink_to(outside)
        self.assertFalse(cache.validate(self.directory, self.expected))
        self.assertEqual(outside.read_text(), 'untouched')
        self.directory.symlink_to(self.root / 'experimental', target_is_directory=True)
        self.assertFalse(cache.validate(self.directory, self.expected))
        self.assertTrue((self.root / 'experimental').is_dir())

    def test_qemu_requires_firmware_even_when_receipt_lists_existing_files(self):
        expected = {'backend': 'qemu'}
        (self.directory / 'dosbox-x').rename(self.directory / 'qemu-system-x86_64')
        with self.assertRaisesRegex(ValueError, 'firmware'):
            cache.seal(self.directory, expected)
        firmware = self.directory / 'pc-bios/bios-256k.bin'
        firmware.parent.mkdir()
        firmware.write_bytes(b'synthetic firmware inventory')
        cache.seal(self.directory, expected)
        self.assertTrue(cache.validate(self.directory, expected))
        firmware.unlink()
        self.assertFalse(cache.validate(self.directory, expected))

    def test_runtime_library_change_rejects_cache(self):
        cache.seal(self.directory, self.expected)
        with patch.object(cache, 'runtime_libraries', return_value={'/test/libc.so': 'changed'}):
            self.assertFalse(cache.validate(self.directory, self.expected))

    def test_real_elf_receipt_and_runtime_libraries(self):
        self.libpatch.stop()
        shutil.copyfile('/bin/true', self.directory / 'dosbox-x')
        (self.directory / 'dosbox-x').chmod(0o755)
        cache.seal(self.directory, self.expected)
        receipt = json.loads((self.directory / 'receipt.json').read_text())
        self.assertGreater(len(receipt['runtime_libraries']), 0)
        self.assertTrue(cache.validate(self.directory, self.expected))

    def test_cold_option_removes_payload_before_validation(self):
        with patch.dict(os.environ, {'NATIVE_COLD_CACHE': 'true'}), patch.object(cache.sys, 'argv', ['native_cache.py', 'key', 'dosbox', '--profile', 'experimental/dosbox-x']), patch.object(cache.Path, 'cwd', return_value=self.root):
            cache.main()
        self.assertFalse(self.directory.exists())


class EventContracts(unittest.TestCase):
    repo = 'owner/repository'
    sha = 'abc123'

    def pull(self):
        return {'state': 'open', 'mergeable': True, 'head': {'sha': self.sha, 'ref': 'feature', 'repo': {'full_name': self.repo}}}

    def run_push(self, pulls, ref='refs/heads/feature'):
        return policy.should_run('push', ref, self.repo, pulls, self.sha)

    def test_first_push_runs_then_matching_mergeable_pr_deduplicates(self):
        self.assertTrue(self.run_push([]))
        self.assertFalse(self.run_push([self.pull()]))

    def test_fork_same_branch_stale_pr_conflict_and_unknown_keep_push(self):
        for field, value in (('mergeable', False), ('mergeable', None), ('state', 'closed')):
            pull = self.pull()
            pull[field] = value
            self.assertTrue(self.run_push([pull]))
        for field, value in (('repo', {'full_name': 'fork/repository'}), ('repo', None), ('sha', 'old'), ('ref', 'other')):
            pull = self.pull()
            pull['head'][field] = value
            self.assertTrue(self.run_push([pull]))

    def test_main_integration_release_tags_pr_manual_always_run(self):
        for ref in ('refs/heads/main', 'refs/heads/integration/test', 'refs/heads/codex/v025-integration', 'refs/heads/release/test', 'refs/tags/v0.27.0'):
            self.assertTrue(self.run_push([self.pull()], ref))
        for event in ('pull_request', 'workflow_dispatch'):
            self.assertTrue(policy.should_run(event, 'refs/heads/feature', self.repo, [self.pull()], self.sha))

    def test_api_errors_fail_open_without_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'outputs'
            with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/feature', 'GITHUB_REPOSITORY': self.repo, 'GITHUB_SHA': self.sha, 'GITHUB_OUTPUT': str(output)}), patch.object(policy.urllib.request, 'urlopen', side_effect=OSError('unavailable')):
                policy.main()
            self.assertEqual(output.read_text(), 'run=true\n')


# Evaluate only the expression forms present in our workflow concurrency policy.
# This evaluates the actual YAML expression rather than a second policy model.
def expression(text, context):
    text = re.sub(r'!(?!=)', 'not ', text).replace('&&', ' and ').replace('||', ' or ').strip()
    def node(item):
        if isinstance(item, ast.Constant): return item.value
        if isinstance(item, ast.Name): return context[item.id]
        if isinstance(item, ast.Attribute): return node(item.value)[item.attr]
        if isinstance(item, ast.BoolOp):
            value = node(item.values[0])
            for child in item.values[1:]:
                if isinstance(item.op, ast.And) and value or isinstance(item.op, ast.Or) and not value:
                    value = node(child)
            return value
        if isinstance(item, ast.UnaryOp) and isinstance(item.op, ast.Not): return not node(item.operand)
        if isinstance(item, ast.Compare) and len(item.ops) == 1:
            return node(item.left) != node(item.comparators[0]) if isinstance(item.ops[0], ast.NotEq) else node(item.left) == node(item.comparators[0])
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Name):
            values = [node(value) for value in item.args]
            if item.func.id == 'startsWith': return values[0].startswith(values[1])
            if item.func.id == 'endsWith': return values[0].endswith(values[1])
            if item.func.id == 'format': return values[0].format(*values[1:])
        raise AssertionError(ast.dump(item))
    return node(ast.parse(text, mode='eval').body)


class WorkflowContracts(unittest.TestCase):
    def context(self, event='pull_request', ref='refs/pull/56/merge', number=56, run=1, workflow='native'):
        return {'github': {'workflow': workflow, 'event_name': event, 'ref': ref, 'run_id': run, 'event': {'pull_request': {'number': number}}}}

    def value(self, text, field, context):
        line = next(line for line in text.splitlines() if line.strip().startswith(field + ':'))
        raw = line.split(':', 1)[1].strip()
        matches = list(re.finditer(r'\$\{\{(.*?)\}\}', raw))
        if len(matches) == 1 and matches[0].span() == (0, len(raw)):
            return expression(matches[0].group(1), context)
        return re.sub(r'\$\{\{(.*?)\}\}', lambda match: str(expression(match.group(1), context)), raw)

    def test_concurrency_cancels_only_same_feature_or_pr_identity(self):
        for file in ('ci.yml', 'native-debugger.yml'):
            text = (ROOT / '.github/workflows' / file).read_text()
            for event, ref in (('pull_request', 'refs/pull/56/merge'), ('push', 'refs/heads/feature')):
                a = self.context(event, ref, run=1)
                b = self.context(event, ref, run=2)
                self.assertEqual(self.value(text, 'group', a), self.value(text, 'group', b))
                self.assertTrue(self.value(text, 'cancel-in-progress', a))
            self.assertNotEqual(self.value(text, 'group', self.context(number=56)), self.value(text, 'group', self.context(number=57)))
            self.assertNotEqual(self.value(text, 'group', self.context(workflow='native')), self.value(text, 'group', self.context(workflow='ordinary')))
            for event, ref in (('push', 'refs/heads/main'), ('push', 'refs/heads/integration/test'), ('push', 'refs/heads/codex/v025-integration'), ('push', 'refs/heads/release/test'), ('push', 'refs/tags/v0.27.0'), ('workflow_dispatch', 'refs/heads/feature')):
                a = self.context(event, ref, run=1)
                b = self.context(event, ref, run=2)
                self.assertNotEqual(self.value(text, 'group', a), self.value(text, 'group', b))
                self.assertFalse(self.value(text, 'cancel-in-progress', a))

    def test_trusted_namespace_is_never_saved_by_pr_tag_manual_or_feature(self):
        text = (ROOT / '.github/workflows/native-debugger.yml').read_text()
        self.assertEqual(self.value(text, 'NATIVE_CACHE_SCOPE', self.context('push', 'refs/heads/main')), 'trusted-main')
        for event, ref in (('pull_request', 'refs/pull/56/merge'), ('push', 'refs/heads/feature'), ('push', 'refs/tags/v0.27.0'), ('workflow_dispatch', 'refs/heads/main')):
            self.assertNotEqual(self.value(text, 'NATIVE_CACHE_SCOPE', self.context(event, ref)), 'trusted-main')
        self.assertNotIn('restore-keys:', text)
        self.assertNotIn('pull_request_target', text)
        self.assertIn('  contents: read', text)
        self.assertNotIn('write', text.split('permissions:\n')[1].split('jobs:\n')[0])

    def test_native_acceptance_commands_and_names_preserved(self):
        after = (ROOT / '.github/workflows/native-debugger.yml').read_text()
        contract = json.loads((ROOT / '.github/ci/tests/native-required-tests.json').read_text())
        for name in contract['required_test_files']:
            self.assertIn(name, after)
        for contract in ('profile: stable-backend', 'profile: layers-backend',
                         'name: Native debugger (${{ matrix.profile }})',
                         'name: Unified DOS, boot and PE64 (installed wheel)',
                         'python -m pytest -q --require-native',
                         '--junitxml=native-evidence/pe/tests.xml',
                         '--junitxml=native-evidence/unified/tests.xml'):
            self.assertIn(contract, after)
        self.assertIn('needs: [native-debugger, prepare-qemu]', after)
        self.assertNotIn('    paths:', after)


if __name__ == '__main__':
    unittest.main()
