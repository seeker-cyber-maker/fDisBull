"""Admission refuses unsafe files before compiler/parser work or large reads."""
from pathlib import Path
import os
import struct

import pytest

from fdisbull import uil_desktop as desktop
from test_uil_desktop import desktop_fixture


def sparse(path, size):
    with path.open('xb') as stream:
        stream.seek(size - 1)
        stream.write(b'x')


def forbid_open(monkeypatch, path):
    original = Path.open
    original_os_open = os.open

    def checked(self, *args, **kwargs):
        if self == path:
            raise AssertionError('known oversized file must refuse before open')
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', checked)

    def checked_descriptor(candidate, *args, **kwargs):
        if Path(candidate) == path:
            raise AssertionError('known oversized file must refuse before descriptor open')
        return original_os_open(candidate, *args, **kwargs)

    monkeypatch.setattr(os, 'open', checked_descriptor)


def forbid_parsers(monkeypatch):
    import lief
    for parser in (lief.MachO, lief.ELF, lief.PE):
        monkeypatch.setattr(parser, 'parse', lambda *a, **k: pytest.fail('oversize reached parser'))


def test_metadata_known_oversize_refuses_before_open(tmp_path, monkeypatch):
    path = tmp_path / 'oversized.json'
    sparse(path, 16 * 1024 * 1024 + 1)
    forbid_open(monkeypatch, path)
    with pytest.raises(ValueError, match='budget'):
        desktop.load_desktop_json(path)


@pytest.mark.parametrize('target', ['macos-arm64', 'linux-x64', 'windows-x64'])
def test_image_known_oversize_refuses_before_open_or_parser(tmp_path, monkeypatch, target):
    path = tmp_path / 'oversized.image'
    sparse(path, 128 * 1024 * 1024 + 1)
    forbid_open(monkeypatch, path)
    forbid_parsers(monkeypatch)
    with pytest.raises(ValueError, match='budget'):
        desktop._image(path, target)


@pytest.mark.parametrize('target', ['macos-arm64', 'linux-x64', 'windows-x64'])
def test_object_known_oversize_refuses_before_open_or_parser(tmp_path, monkeypatch, target):
    root = tmp_path / 'shell'
    document = desktop.emit_desktop_shell(*desktop_fixture(), root, target)
    path = root / document['objects'][0]
    sparse(path, 128 * 1024 * 1024 + 1)
    forbid_open(monkeypatch, path)
    forbid_parsers(monkeypatch)
    with pytest.raises(ValueError, match='budget'):
        desktop.seal_desktop_shell(root)


def test_growth_after_descriptor_stat_is_bounded_before_json_parser(tmp_path, monkeypatch):
    path = tmp_path / 'growing.json'
    path.write_bytes(b'{}')
    info = path.stat()
    actual_fstat = os.fstat
    grew = []
    monkeypatch.setattr(desktop, '_METADATA_LIMIT', 16)

    def fstat_then_grow(descriptor):
        result = actual_fstat(descriptor)
        if (result.st_dev, result.st_ino) == (info.st_dev, info.st_ino) and not grew:
            with path.open('ab') as stream:
                stream.write(b' ' * 15)
            grew.append(True)
        return result

    monkeypatch.setattr(os, 'fstat', fstat_then_grow)
    monkeypatch.setattr(desktop.json, 'loads', lambda *a, **k: pytest.fail('oversize reached JSON parser'))
    with pytest.raises(ValueError, match='budget'):
        desktop.load_desktop_json(path)
    assert grew and path.stat().st_size == 17


@pytest.mark.parametrize('target,parser_name', [
    ('macos-arm64', 'MachO'), ('linux-x64', 'ELF'), ('windows-x64', 'PE')])
def test_image_parser_receives_owned_bytes_not_reopened_path(tmp_path, monkeypatch, target, parser_name):
    import lief
    raw = bytearray(160)
    if target == 'windows-x64':
        raw[:2] = b'MZ';struct.pack_into('<I', raw, 60, 64)
        raw[64:68] = b'PE\0\0'
        struct.pack_into('<H', raw, 68, 0x8664)
        struct.pack_into('<H', raw, 88, 0x20b)
    path = tmp_path / 'authored-header'
    path.write_bytes(raw)

    class ReachedParser(Exception):
        pass

    def parser(value):
        assert type(value) is bytes and value == bytes(raw)
        raise ReachedParser

    monkeypatch.setattr(getattr(lief, parser_name), 'parse', parser)
    with pytest.raises(ReachedParser):
        desktop._image(path, target)


def test_compiler_log_symlink_refuses_before_compiler_and_preserves_target(tmp_path, monkeypatch):
    root = tmp_path / 'shell'
    desktop.emit_desktop_shell(*desktop_fixture(), root)
    external = tmp_path / 'preserved.txt'
    external.write_text('external content remains')
    (root / 'compiler-log.json').symlink_to(external)
    import fdisbull.uil_native as native
    monkeypatch.setattr(native, '_compiler', lambda *a, **k: pytest.fail('compiler reached before log refusal'))
    with pytest.raises(ValueError, match='existing|report'):
        desktop.compile_desktop_shell(root, c_compiler='/nonexistent')
    assert external.read_text() == 'external content remains'


def test_source_ancestor_symlink_refuses_before_compiler_or_parser(tmp_path, monkeypatch):
    root = tmp_path / 'shell'
    desktop.emit_desktop_shell(*desktop_fixture(), root)
    outside = tmp_path / 'external-source'
    (root / 'v0').rename(outside)
    (root / 'v0').symlink_to(outside, target_is_directory=True)
    before = {p.name: p.read_bytes() for p in outside.iterdir() if p.is_file()}
    with pytest.raises(ValueError, match='ancestor|containment'):
        desktop.seal_desktop_shell(root)
    assert {p.name: p.read_bytes() for p in outside.iterdir() if p.is_file()} == before


def test_artifact_ancestor_symlink_refuses_before_any_parser(tmp_path, monkeypatch):
    import lief
    root = tmp_path / 'shell'
    document = desktop.emit_desktop_shell(*desktop_fixture(), root, 'macos-arm64')
    for name in document['objects'] + [document['probe'], document['library']]:
        (root / name).write_bytes(b'authored refusal sample')
    parent = (root / document['application']).parent
    outside = tmp_path / 'external-artifact'
    parent.rename(outside)
    parent.symlink_to(outside, target_is_directory=True)
    (outside / 'program').write_bytes(b'preserved external artifact')
    monkeypatch.setattr(lief.MachO, 'parse', lambda *a, **k: pytest.fail('parser reached before containment refusal'))
    with pytest.raises(ValueError, match='ancestor|containment'):
        desktop.seal_desktop_shell(root)
    assert (outside / 'program').read_bytes() == b'preserved external artifact'
