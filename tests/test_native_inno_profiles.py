"""Real parser tests using authored installer structures, never game payloads."""
from hashlib import md5, sha1, sha256
import json
import lzma
import os
from pathlib import Path
import struct
import subprocess

import pytest

from fdisbull.gog_unpack import list_gog, unpack_gog
from fdisbull.native_inno import InnoRefused, NativeInno

PROFILES = ("Inno Setup Setup Data (5.5.7) (u)", "Inno Setup Setup Data (5.6.2) (u)")


def _string(value):
    data = value.encode("utf-16le") if isinstance(value, str) else value
    return struct.pack("<I", len(data)) + data


def _block(raw, compressed):
    if compressed:
        settings = {"id": lzma.FILTER_LZMA1, "dict_size": 1 << 20,
                    "lc": 3, "lp": 0, "pb": 2}
        raw = bytes([93]) + struct.pack("<I", 1 << 20) + lzma.compress(
            raw, format=lzma.FORMAT_RAW, filters=[settings])
    import zlib
    framed = b"".join(struct.pack("<I", zlib.crc32(raw[i:i+4096])) + raw[i:i+4096]
                      for i in range(0, len(raw), 4096))
    header = struct.pack("<IB", len(framed), int(compressed))
    return struct.pack("<I", zlib.crc32(header)) + header + framed


def authored_installer(profile=PROFILES[1], *, compressed=True, compressed_header=True,
                       destination=r"{app}\direct.txt", method=4, bad_md5=False):
    """Two direct/assembled outputs; metadata and content checksums are real.

    The fixture writer declares its layout independently of parser constants.
    This intentionally has no executable machine code despite its .exe suffix.
    """
    import zlib
    direct = b"Authored direct payload.\n"
    pieces = [b"Authored Galaxy first part.\n", b"Second authored part.\n"]
    raw_payloads = [direct, *(zlib.compress(part) for part in pieces)]
    bodies, locations, offset = [], [], 0
    for payload in raw_payloads:
        stored = payload
        if compressed:
            stored = bytes([16]) + lzma.compress(payload, format=lzma.FORMAT_RAW,
                filters=[{"id": lzma.FILTER_LZMA2, "dict_size": 1 << 20}])
        body = b"zlb\x1a" + stored
        locations.append(struct.pack("<IIIQQQ", 0, 0, offset, 0, len(payload), len(stored))
                         + sha1(payload).digest() + struct.pack("<QIIH", 0, 0, 0, 0x80 if compressed else 0))
        bodies.append(body)
        offset += len(body)
    # 28 strings through setup_mutex; 5.6.1 added two before the four opaque fields.
    strings = ["Authored Inno parser fixture", *("" for _ in range(27))]
    if profile != PROFILES[0]:
        strings += ["Authored environment", "Authored associations"]
    strings += [b"", b"", b"", b"x" * 4500]
    counts = [0] * 16
    counts[7] = counts[8] = 3
    ui = bytearray(10)
    ui[5] = method
    header = b"".join(_string(s) for s in strings) + struct.pack("<16I", *counts)
    header += bytes(20 + 8 + 1 + 28 + 12) + bytes(ui) + bytes(8 + 6)
    digest = "0" * 32 if bad_md5 else md5(b"".join(pieces)).hexdigest()
    before = f"before_install('{digest}', 'DATA/assembled.txt', 2)"
    for i in range(3):
        record = [""] * 10
        record[1] = destination if i == 0 else rf"{{app}}\piece{i}"
        if i:
            record[8] = f"after_install('unused', {len(raw_payloads[i])}, {len(pieces[i-1])})"
            if i == 1:
                record[9] = before
        header += b"".join(_string(s) for s in record) + bytes(20)
        header += struct.pack("<IIQHIB", i, 0, 0, 0, 0, 0)
    data_offset = 4096
    header_offset = data_offset + sum(map(len, bodies))
    encoded = profile.encode("ascii").ljust(64, b"\0")
    encoded += _block(header, compressed_header) + _block(b"".join(locations), compressed_header)
    exe_offset = header_offset + len(encoded)
    raw = bytearray(max(100000, exe_offset + 64))
    raw[data_offset:header_offset] = b"".join(bodies)
    raw[header_offset:exe_offset] = encoded
    table = b"rDlPtS" + bytes(6) + struct.pack("<7I", 1, 0, exe_offset, 0, 0, header_offset, data_offset)
    raw[256:300] = table + struct.pack("<I", zlib.crc32(table))
    return bytes(raw), {"app/direct.txt": direct, "DATA/assembled.txt": b"".join(pieces)}


@pytest.fixture
def no_external_tools(monkeypatch):
    monkeypatch.setenv("PATH", "")
    def forbidden(*args, **kwargs):
        raise AssertionError("Native unpacking must not start an external process")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    for name in ("posix_spawn", "posix_spawnp", "fork", "execv", "execve"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, forbidden)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("compressed", [False, True])
@pytest.mark.parametrize("compressed_header", [False, True])
def test_full_native_round_trip(tmp_path, no_external_tools, profile, compressed, compressed_header):
    raw, expected = authored_installer(profile, compressed=compressed, compressed_header=compressed_header)
    source = tmp_path / "authored.exe"
    source.write_bytes(raw)
    listed = list_gog(source)
    assert listed["files"] == sorted(expected)
    assert listed["extractor"] == {"implementation": "fdisbull-native-inno", "profile": profile,
                                    "requires_innoextract": False}
    native = NativeInno.open(source)
    assert native.describe()["format"] == profile
    for name, data in expected.items():
        assert native.extract_one(name) == data
    output = tmp_path / "out"
    result = unpack_gog(source, output)
    assert result["installer_executed"] is False
    assert result["extractor"]["profile"] == profile
    assert {item["path"]: item["sha256"] for item in result["files"]} == {
        name: sha256(data).hexdigest() for name, data in expected.items()}
    assert all((output / name).read_bytes() == data for name, data in expected.items())
    assert source.read_bytes() == raw
    with pytest.raises(ValueError, match="already exists"):
        unpack_gog(source, output)
    assert all((output / name).read_bytes() == data for name, data in expected.items())


@pytest.mark.parametrize("profile", PROFILES)
def test_filter_and_native_manifest(tmp_path, no_external_tools, profile):
    raw, expected = authored_installer(profile)
    source = tmp_path / "authored.exe"
    source.write_bytes(raw)
    result = unpack_gog(source, tmp_path / "selected", include=["APP/"])
    assert [item["path"] for item in result["files"]] == ["app/direct.txt"]
    native = NativeInno.open(source)
    native.extract_selected(tmp_path / "native", ["app/direct.txt"])
    manifest = json.loads((tmp_path / "native/gog-native-manifest.json").read_text())
    assert manifest["profile"] == profile


@pytest.mark.parametrize("profile", ["Inno Setup Setup Data (5.5.6) (u)",
                                      "Inno Setup Setup Data (6.0.0) (u)",
                                      "Inno Setup Setup Data (5.6.2)"])
def test_unknown_versions_refuse_without_fallback(tmp_path, no_external_tools, profile):
    raw, _ = authored_installer(profile)
    source = tmp_path / "unknown.exe"
    source.write_bytes(raw)
    with pytest.raises(InnoRefused, match="unsupported data profile"):
        unpack_gog(source, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("method", [1, 2, 3, 255])
def test_unsupported_compressor_is_not_guessed(tmp_path, no_external_tools, profile, method):
    raw, _ = authored_installer(profile, method=method)
    source = tmp_path / "unknown.exe"
    source.write_bytes(raw)
    with pytest.raises(InnoRefused, match="compression method"):
        unpack_gog(source, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("damage", ["loader_crc", "header_crc", "payload_sha1", "galaxy_md5"])
def test_corruption_refuses_and_cleans_own_output(tmp_path, no_external_tools, profile, damage):
    raw, _ = authored_installer(profile, compressed=False, bad_md5=damage == "galaxy_md5")
    raw = bytearray(raw)
    if damage == "loader_crc":
        raw[296] ^= 1
    elif damage == "header_crc":
        header_offset = struct.unpack_from("<I", raw, 288)[0]
        raw[header_offset + 64] ^= 1
    elif damage == "payload_sha1":
        raw[4100] ^= 1
    source = tmp_path / "bad.exe"
    source.write_bytes(raw)
    with pytest.raises(InnoRefused):
        unpack_gog(source, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    assert source.read_bytes() == raw


@pytest.mark.parametrize("destination", [r"{app}\..\outside", r"{app}\a:b", r"{app}\bad\x00name".replace(r"\x00", "\x00")])
def test_real_parser_rejects_unsafe_paths(tmp_path, no_external_tools, destination):
    raw, _ = authored_installer(destination=destination)
    source = tmp_path / "unsafe.exe"
    source.write_bytes(raw)
    with pytest.raises(ValueError):
        unpack_gog(source, tmp_path / "out")
    assert not (tmp_path / "out").exists()
