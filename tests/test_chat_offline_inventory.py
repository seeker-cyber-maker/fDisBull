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


@pytest.mark.parametrize('member,expected', [
    ('z3/__init__.py', 'python/lib/python3.13/site-packages/z3/__init__.py'),
    ('z3_solver-5.3.2.0.data/purelib/z3/a.py', 'python/lib/python3.13/site-packages/z3/a.py'),
    ('z3_solver-5.3.2.0.data/platlib/z3/a.so', 'python/lib/python3.13/site-packages/z3/a.so'),
    ('z3_solver-5.3.2.0.data/data/bin/z3', 'python/bin/z3'),
    ('z3_solver-5.3.2.0.data/data/share/z3/LICENSE', 'python/share/z3/LICENSE'),
])
def test_wheel_install_schemes_share_one_mapper(member, expected):
    assert module.kit.wheel_destination(member, 'z3_solver-5.3.2.0.dist-info') == expected


@pytest.mark.parametrize('member', [
    '/bin/z3', '../bin/z3', 'z3_solver-5.3.2.0.data/data/../../z3',
    'z3_solver-5.3.2.0.data/data//bin/z3', 'other.data/data/bin/z3',
    'z3_solver-5.3.2.0.data/scripts/z3', 'z3_solver-5.3.2.0.data/headers/z3.h',
    'z3_solver-5.3.2.0.data/unknown/z3',
])
def test_wheel_install_mapping_refuses_unsafe_or_unverified_schemes(member):
    with pytest.raises(ValueError):
        module.kit.wheel_destination(member, 'z3_solver-5.3.2.0.dist-info')


def test_wheel_data_verifies_prefix_bin_bytes_instead_of_site_packages(tmp_path):
    prefix = tmp_path / 'python'; (prefix / 'bin').mkdir(parents=True)
    payload = b'\x7fELF-authored-z3'
    target = prefix / 'bin/z3'; target.write_bytes(payload)
    member = 'z3_solver-5.3.2.0.data/data/bin/z3'
    assert module.installed_wheel_member(prefix, member, payload, 'z3_solver-5.3.2.0.dist-info') == (target, 'python/bin/z3')
    target.write_bytes(b'changed')
    with pytest.raises(ValueError, match='missing or changed'):
        module.installed_wheel_member(prefix, member, payload, 'z3_solver-5.3.2.0.dist-info')
    target.unlink()
    with pytest.raises(ValueError, match='missing or changed'):
        module.installed_wheel_member(prefix, member, payload, 'z3_solver-5.3.2.0.dist-info')


def test_wheel_data_refuses_installed_symlink_escape(tmp_path):
    prefix = tmp_path / 'python'; (prefix / 'bin').mkdir(parents=True)
    outside = tmp_path / 'outside'; outside.write_bytes(b'payload')
    (prefix / 'bin/z3').symlink_to(outside)
    with pytest.raises(ValueError, match='missing or changed'):
        module.installed_wheel_member(prefix, 'z3_solver-5.3.2.0.data/data/bin/z3', b'payload', 'z3_solver-5.3.2.0.dist-info')
