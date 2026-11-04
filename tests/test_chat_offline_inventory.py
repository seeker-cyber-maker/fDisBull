import importlib.util
from pathlib import Path
import subprocess

import pytest

SPEC = importlib.util.spec_from_file_location('chat_inventory', Path(__file__).parents[1] / 'scripts/prepare_chat_offline_inventory.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_resolves_ldd_names_and_ignores_vdso(monkeypatch):
    monkeypatch.setattr(module, 'run', lambda args: '''\
linux-vdso.so.1 (0x1234)
libm.so.6 => /lib/x86_64-linux-gnu/libm.so.6 (0xabcd)
/lib64/ld-linux-x86-64.so.2 (0xabcd)
''')
    result = module.ldd_dependencies(Path('/a'), Path('/usr/bin/ldd'))
    assert result == {'libm.so.6': '/lib/x86_64-linux-gnu/libm.so.6',
                      'ld-linux-x86-64.so.2': '/lib64/ld-linux-x86-64.so.2'}


def test_missing_or_unrecognized_ldd_fails(monkeypatch):
    monkeypatch.setattr(module, 'run', lambda args: 'libbad.so => not found\n')
    with pytest.raises(ValueError, match='unresolved'):
        module.ldd_dependencies(Path('/a'), Path('/ldd'))
    monkeypatch.setattr(module, 'run', lambda args: 'unexpected output\n')
    with pytest.raises(ValueError, match='unrecognized'):
        module.ldd_dependencies(Path('/a'), Path('/ldd'))


def test_static_ldd_and_actual_failure_are_distinct(monkeypatch):
    def static(args):
        raise subprocess.CalledProcessError(1, args, stderr='not a dynamic executable')
    monkeypatch.setattr(module, 'run', static)
    assert module.ldd_dependencies(Path('/a'), Path('/ldd')) == {}
    def fail(args):
        raise subprocess.CalledProcessError(1, args, stderr='permission denied')
    monkeypatch.setattr(module, 'run', fail)
    with pytest.raises(ValueError, match='permission denied'):
        module.ldd_dependencies(Path('/a'), Path('/ldd'))


def test_refuses_nonempty_stage(tmp_path):
    (tmp_path / 'preserved').write_text('keep')
    with pytest.raises(ValueError, match='empty'):
        module.prepare({}, tmp_path)
    assert (tmp_path / 'preserved').read_text() == 'keep'


def test_resolved_vendored_library_keeps_private_origin(tmp_path):
    vendor = tmp_path / 'libjpeg-abc.so'; vendor.write_bytes(b'vendored')
    dest = 'python/lib/python3.13/site-packages/pillow.libs/libjpeg-abc.so'
    assert module.dependency_destination('libjpeg-abc.so', vendor, {dest: vendor}) == dest
    other = tmp_path / 'other'; other.write_bytes(b'other')
    assert module.dependency_destination('libjpeg-abc.so', other, {dest: vendor}) == 'lib/libjpeg-abc.so'
    duplicate = 'python/lib/python3.13/lib-dynload/libjpeg-abc.so'
    with pytest.raises(ValueError, match='ambiguous'):
        module.dependency_destination('libjpeg-abc.so', vendor, {dest: vendor, duplicate: vendor})
