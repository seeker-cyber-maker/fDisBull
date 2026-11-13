import importlib.util
import json
import os
import subprocess
from pathlib import Path
import tarfile
import zipfile

import pytest

SPEC = importlib.util.spec_from_file_location('chatkit', Path(__file__).parents[1] / 'scripts/build_chat_offline_kit.py')
kit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(kit)


def inventory(tmp):
    files = []
    def add(dest, role='payload', data=b'data'):
        src = tmp / ('input' + str(len(files)))
        src.write_bytes(data)
        files.append(dict(source=str(src), destination=dest, role=role, sha256=kit.sha256(src), size=src.stat().st_size))
    for role, path in [('python', 'python/bin/python3.13'), ('loader', 'lib/ld.so'), ('dosbox', 'native/dosbox'), ('qemu', 'native/qemu'), ('payload', 'lib/libx.so')]:
        add(path, role, b'\x7fELF\x02\x01' + b'\x00' * 12 + b'\x3e\x00')
    for path in ['python/lib/python3.13/encodings/__init__.py', 'python/lib/python3.13/site-packages/fdisbull/__init__.py', 'python/lib/python3.13/site-packages/fdisbull/skills/a.md', 'python/lib/python3.13/site-packages/fdisbull_player/__init__.py', 'python/lib/python3.13/site-packages/z3/__init__.py']:
        add(path)
    for role in ['firmware', 'kernel', 'wine_initramfs', 'dos_initramfs', 'source_companion', 'license', 'python_receipt', 'dosbox_receipt', 'qemu_receipt', 'wine_receipt', 'pe_fixture', 'verifier']:
        add('artifacts/' + role, role)
    for role, name in [('wheel_core', 'fdisbull'), ('wheel_player', 'fdisbull-player'), ('wheel_z3', 'z3-solver'), ('payload', 'iced-x86'), ('payload', 'capstone'), ('payload', 'lief'), ('payload', 'pillow'), ('payload', 'unicorn'), ('payload', 'dnfile'), ('payload', 'dncil'), ('payload', 'pefile'), ('payload', 'tree-sitter'), ('payload', 'tree-sitter-c'), ('payload', 'pycparser'), ('payload', 'zstandard')]:
        wheel = tmp / (name + '.whl')
        with zipfile.ZipFile(wheel, 'w') as z:
            z.writestr(name + '.dist-info/METADATA', f'Name: {name}\nVersion: 1.0\n')
            z.writestr(name + '.dist-info/RECORD', '')
        add('python/lib/python3.13/site-packages/' + name + '.dist-info/METADATA', data=f'Name: {name}\nVersion: 1.0\n'.encode())
        files.append(dict(source=str(wheel), destination='wheels/' + name + '.whl', role=role, sha256=kit.sha256(wheel), size=wheel.stat().st_size))
    objects = [{'path': x['destination'], 'needed': {}} for x in files if Path(x['source']).read_bytes().startswith(b'\x7fELF')]
    objects[0]['needed'] = {'libx.so': 'lib/libx.so'}
    add('receipts/closure.json', 'closure_receipt', json.dumps(dict(schema='fdisbull-elf-closure-v1', complete=True, objects=objects)).encode())
    inv = dict(schema='fdisbull-chat-offline-inventory-v1', wheel_versions={name: '1.0' for name in kit.RUNTIME_WHEELS}, identities=dict(source_commit='a'*40, test_source_commit='b'*40, python='3.13.5', qemu='9.2.4', wine='11', version='1.0'), files=files)
    p = tmp / 'inventory.json'
    p.write_text(json.dumps(inv))
    return p, inv


def test_archive_relocatable_and_no_source_paths(tmp_path):
    inv, _ = inventory(tmp_path)
    out = tmp_path / 'kit.zip'
    kit.build(inv, out)
    with zipfile.ZipFile(out) as tar:
        names = tar.namelist()
        assert 'fdisbull-chat-offline/bin/fdisbull' in names
        assert 'fdisbull-chat-offline/bin/python' in names
        wrapper = tar.read('fdisbull-chat-offline/bin/fdisbull').decode()
        manifest = tar.read('fdisbull-chat-offline/MANIFEST.json').decode()
        assert 'unset PYTHONPATH PYTHONHOME' in wrapper
        assert '--inhibit-cache' in wrapper
        assert ' -s -P ' in wrapper
        assert 'dirname' not in wrapper
        assert str(tmp_path) not in wrapper + manifest
        assert json.loads(manifest)['qualification'] == 'not-qualified-by-builder'
        readme = tar.read('fdisbull-chat-offline/README.txt')
        entry = next(x for x in json.loads(manifest)['files'] if x['destination'] == 'README.txt')
        assert entry['sha256'] == __import__('hashlib').sha256(readme).hexdigest()
        assert b'./bin/fdisbull agent-skill --reference SKILL.md' in readme
        assert b'no pip or downloads are needed' in readme


def test_rejects_missing_dependency_and_tamper(tmp_path):
    inv, data = inventory(tmp_path)
    item = next(x for x in data['files'] if x['destination'] == 'lib/libx.so')
    Path(item['source']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        kit.load_inventory(inv)
    data['files'].remove(item)
    inv.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='unresolved library'):
        kit.load_inventory(inv)


@pytest.mark.parametrize('path', ['../escape', '/absolute', 'x/../escape', 'foo/save.fdb', 'bin/fdisbull'])
def test_rejects_unsafe_destination(path):
    with pytest.raises(ValueError):
        kit.destination(path)


def test_rejects_wrong_elf_architecture(tmp_path):
    inv, data = inventory(tmp_path)
    item = next(x for x in data['files'] if x['role'] == 'python')
    src = Path(item['source'])
    src.write_bytes(b'\x7fELF\x02\x01' + b'\x00' * 12 + b'\xb7\x00')
    item['sha256'] = kit.sha256(src)
    inv.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='x86-64'):
        kit.load_inventory(inv)


def test_rejects_missing_extra_wheel(tmp_path):
    inv, data = inventory(tmp_path)
    data['files'] = [x for x in data['files'] if x['destination'] != 'wheels/unicorn.whl']
    inv.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='wheelhouse distributions'):
        kit.load_inventory(inv)


def test_shared_zip_omits_wheels_and_limits_size(tmp_path):
    inv, data = inventory(tmp_path)
    data['profile'] = 'shared'
    data['files'] = [x for x in data['files'] if x['role'] not in ('wine_initramfs', 'dos_initramfs')]
    for role, dest in [('runtime_base', 'runtime/base.cpio.xz'), ('runtime_recipe', 'runtime/recipe.json'), ('runtime_preparer', 'tools/preparer.py'), ('windows_runtime_base', 'runtime/windows-base.cpio.xz'), ('windows_runtime_recipe', 'runtime/windows-recipe.json')]:
        p = tmp_path / role
        p.write_bytes(b'input')
        data['files'].append(dict(source=str(p), destination=dest, role=role, sha256=kit.sha256(p), size=p.stat().st_size))
    inv.write_text(json.dumps(data))
    out = tmp_path / 'shared.zip'
    with pytest.raises(ValueError, match='candidate retained unqualified'):
        kit.build(inv, out, max_bytes=1)
    with zipfile.ZipFile(out) as z:
        assert not any('/wheels/' in n for n in z.namelist())
        manifest = json.loads(z.read('fdisbull-chat-offline/MANIFEST.json'))
        assert len(manifest['wheel_artifacts']) == len(kit.RUNTIME_WHEELS)
        wrapper = z.read('fdisbull-chat-offline/bin/prepare-runtimes').decode()
        assert '--kit' in wrapper and '${0%/*}' in wrapper
        assert b'./bin/prepare-runtimes --cache /absolute/writable/cache' in z.read('fdisbull-chat-offline/README.txt')
        assert ' -s -P ' in wrapper and ' -I ' not in wrapper


def test_foreign_firmware_elf_is_guest_data(tmp_path):
    inv, data = inventory(tmp_path)
    item = next(x for x in data['files'] if x['role'] == 'firmware')
    p = Path(item['source'])
    p.write_bytes(b'\x7fELF\x01\x02' + b'\x00' * 14)
    item.update(destination='native/qemu/share/qemu/openbios-ppc', size=p.stat().st_size, sha256=kit.sha256(p))
    inv.write_text(json.dumps(data))
    kit.load_inventory(inv)
    item['destination'] = 'native/foreign-elf'
    inv.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='unsupported ELF architecture'):
        kit.load_inventory(inv)


def test_closure_accepts_vendored_host_elf_and_rejects_host_path(tmp_path):
    inv, data = inventory(tmp_path)
    library = next(x for x in data['files'] if x['destination'] == 'lib/libx.so')
    library['destination'] = 'python/lib/python3.13/site-packages/pillow.libs/libx.so'
    receipt = next(x for x in data['files'] if x['role'] == 'closure_receipt')
    path = Path(receipt['source'])
    closure = json.loads(path.read_text())
    for obj in closure['objects']:
        if obj['path'] == 'lib/libx.so':
            obj['path'] = library['destination']
        if obj['needed']:
            obj['needed']['libx.so'] = library['destination']
    path.write_text(json.dumps(closure))
    receipt.update(size=path.stat().st_size, sha256=kit.sha256(path))
    inv.write_text(json.dumps(data))
    kit.load_inventory(inv)
    closure['objects'][0]['needed']['libx.so'] = '/usr/lib/libx.so'
    path.write_text(json.dumps(closure))
    receipt.update(size=path.stat().st_size, sha256=kit.sha256(path))
    inv.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='unresolved library'):
        kit.load_inventory(inv)


def test_qemu_wrapper_passes_private_firmware_and_preserves_arguments(tmp_path):
    root = tmp_path / 'kit with spaces'
    (root / 'bin').mkdir(parents=True)
    (root / 'lib').mkdir()
    loader = root / 'lib/loader'
    loader.write_text('#!/bin/sh\nprintf "%s\\0" "$@"\n')
    loader.chmod(0o755)
    script = root / 'bin/qemu'
    script.write_text(kit.wrapper('lib/loader', 'native/qemu/bin/qemu-system-x86_64', qemu=True))
    script.chmod(0o755)
    result = subprocess.run([str(script), '-machine', 'pc with spaces', '-S'], check=True, capture_output=True)
    assert result.stdout.split(b'\0')[:-1] == [
        b'--inhibit-cache', b'--library-path', str(root / 'lib').encode(),
        str(root / 'native/qemu/bin/qemu-system-x86_64').encode(), b'-L',
        str(root / 'native/qemu/share/qemu').encode(), b'-machine', b'pc with spaces', b'-S']
    assert ' -L ' not in kit.wrapper('lib/loader', 'native/dosbox')


@pytest.mark.parametrize('path,role', [
    ('native/qemu/share/qemu/other.bmp', 'firmware'),
    ('targets/qemu-nsis.bmp', 'firmware'),
    ('native/qemu/share/qemu/qemu-nsis.bmp', 'payload'),
    ('native/qemu/share/qemu/qemu-nsis.bmp', None),
    ('native/qemu/share/qemu/screenshot.png', 'firmware'),
])
def test_installer_bitmap_exception_keeps_private_images_forbidden(path, role):
    with pytest.raises(ValueError, match='prohibited'):
        kit.destination(path, role=role)


def test_exact_installer_bitmap_is_byte_bound_in_inventory_and_archive(tmp_path, monkeypatch):
    inv, data = inventory(tmp_path)
    # This bundle's firmware shares QEMU's real directory layout.
    qemu = next(x for x in data['files'] if x['role'] == 'qemu')
    qemu['destination'] = 'native/qemu/bin/qemu-system-x86_64'
    closure_entry = next(x for x in data['files'] if x['role'] == 'closure_receipt')
    closure_path = Path(closure_entry['source']); closure = json.loads(closure_path.read_text())
    next(obj for obj in closure['objects'] if obj['path'] == 'native/qemu')['path'] = qemu['destination']
    closure_path.write_text(json.dumps(closure))
    closure_entry.update(size=closure_path.stat().st_size, sha256=kit.sha256(closure_path))
    bitmap = next(x for x in data['files'] if x['role'] == 'firmware')
    payload = b'authored upstream bitmap stand-in'
    Path(bitmap['source']).write_bytes(payload)
    bitmap.update(destination=kit.QEMU_INSTALLER_BITMAP, size=len(payload), sha256=kit.sha256(Path(bitmap['source'])))
    monkeypatch.setattr(kit, 'QEMU_INSTALLER_BITMAP_SIZE', len(payload))
    monkeypatch.setattr(kit, 'QEMU_INSTALLER_BITMAP_SHA256', bitmap['sha256'])
    inv.write_text(json.dumps(data))
    kit.load_inventory(inv)
    output = tmp_path / 'bitmap.zip'; kit.build(inv, output)
    with zipfile.ZipFile(output) as archive:
        assert archive.read('fdisbull-chat-offline/' + kit.QEMU_INSTALLER_BITMAP) == payload
    # Rehashing a replacement cannot bypass the independently pinned identity.
    Path(bitmap['source']).write_bytes(b'X' * len(payload))
    bitmap['sha256'] = kit.sha256(Path(bitmap['source']))
    inv.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='bitmap identity mismatch'):
        kit.load_inventory(inv)


def test_installer_bitmap_size_is_pinned_independently(tmp_path, monkeypatch):
    inv, data = inventory(tmp_path)
    bitmap = next(x for x in data['files'] if x['role'] == 'firmware')
    bitmap['destination'] = kit.QEMU_INSTALLER_BITMAP
    monkeypatch.setattr(kit, 'QEMU_INSTALLER_BITMAP_SHA256', bitmap['sha256'])
    monkeypatch.setattr(kit, 'QEMU_INSTALLER_BITMAP_SIZE', bitmap['size'] + 1)
    inv.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='bitmap identity mismatch'):
        kit.load_inventory(inv)


@pytest.mark.parametrize('module', [None, 'fdisbull', 'fdisbull_player'])
def test_python_wrapper_sets_builtin_locale_and_utf8_before_loader(tmp_path, module):
    root = tmp_path / 'kit with spaces'
    (root / 'bin').mkdir(parents=True); (root / 'lib').mkdir()
    loader = root / 'lib/loader'
    loader.write_text('#!/bin/sh\nprintf "%s\\0" "$LC_ALL" "$LANG" "$PYTHONCOERCECLOCALE" "$PYTHONUTF8" "$PYTHONHOME" "$@"\n')
    loader.chmod(0o755)
    script = root / 'bin/python'
    script.write_text(kit.wrapper('lib/loader', 'python/bin/python3.13', python=True, module=module))
    script.chmod(0o755)
    # Inherited Unicode locale/coercion must not map host locale data; UTF-8
    # is explicitly restored by Python's own mode rather than libc locale data.
    env = dict(os.environ, LC_ALL='C.UTF-8', LANG='C.UTF-8', PYTHONCOERCECLOCALE='1', PYTHONUTF8='0')
    result = subprocess.run([str(script), '-c', 'pass'], env=env, check=True, capture_output=True)
    values = result.stdout.split(b'\0')[:-1]
    assert values[:5] == [b'C', b'C', b'0', b'1', str(root / 'python').encode()]
    expected = [b'--inhibit-cache', b'--library-path', str(root / 'lib').encode(),
                str(root / 'python/bin/python3.13').encode(), b'-s', b'-P']
    if module is not None: expected += [b'-m', module.encode()]
    assert values[5:] == expected + [b'-c', b'pass']
    assert 'PYTHONCOERCECLOCALE' not in kit.wrapper('lib/loader', 'native/qemu', qemu=True)
