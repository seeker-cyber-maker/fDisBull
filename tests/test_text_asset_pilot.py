"""Authored fixtures only. Private Zork acceptance is a separate harness."""
from __future__ import annotations
import copy
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import zipfile

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
ROOT = REPOSITORY / "examples" / "text_asset_pilot"
sys.path.insert(0, str(REPOSITORY / "player"))
sys.path.insert(0, str(ROOT))
import asset_package as ap
import pilot
from fdisbull.zork_uil import compile_story
from fdisbull_player.word16 import Word16Runtime, Word16Error


def packed_codes(codes):
    codes = list(codes)
    while len(codes) % 3: codes.append(5)
    words = [(codes[i] << 10) | (codes[i + 1] << 5) | codes[i + 2]
             for i in range(0, len(codes), 3)]
    words[-1] |= 0x8000
    return b"".join(n.to_bytes(2, "big") for n in words)


def text(value):
    codes = []
    for c in value:
        if c == " ": codes.append(0)
        elif "a" <= c <= "z": codes.append(ord(c) - ord("a") + 6)
        else:
            n = {"\n": 13, "\t": 9, "\v": 11}[c]
            codes += [5, 6, n >> 5, n & 31]
    return packed_codes(codes)


def fixture(tmp_path, code=None, patches=()):
    raw = bytearray(0x800)
    raw[0] = 3
    for at, value in ((2, 1), (4, 0x400), (6, 0x400), (8, 900),
                      (10, 544), (12, 64), (14, 0x400), (24, 640), (26, 0x400)):
        raw[at:at + 2] = value.to_bytes(2, "big")
    raw[18:24] = b"000001"
    raw[613:615] = (615).to_bytes(2, "big")
    raw[900:904] = bytes([0, 4, 0, 0])
    raw[0x300] = 32
    raw[0x350] = 8
    code = code if code is not None else b"\xb2" + text("alpha") + bytes.fromhex("e40f03000350") + b"\xb2" + text("omega") + b"\xba"
    raw[0x400:0x400 + len(code)] = code
    for at, value in patches: raw[at:at + len(value)] = value
    raw[28:30] = (sum(raw[64:]) & 65535).to_bytes(2, "big")
    source = tmp_path / "authored.z3"
    source.write_bytes(raw)
    program, _ = compile_story(source)
    return program


def small_package():
    entries = {"greeting": ("text", "text/plain;charset=utf-8", b"alpha", [], {})}
    return ap.pack({"id": "authored.component", "entry": "greeting", "requires": pilot.PORTS}, entries)


def rewrite(data, change):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    change(members)
    return ap.zip_bytes(members)


def mutate_manifest(data, change):
    def edit(members):
        manifest = ap.parse_json(members["manifest.json"])
        change(manifest)
        members["manifest.json"] = ap.canonical(manifest)
    return rewrite(data, edit)


def test_package_deterministic_and_roundtrip():
    data = small_package()
    assert data == small_package()
    assert ap.Package(data).get("greeting", "text") == b"alpha"


def test_identical_payloads_deduplicate():
    entries = {name: ("text", "text/plain", b"same", [], {}) for name in ("a", "b")}
    data = ap.pack({"id": "component", "entry": "a", "requires": {}}, entries)
    pkg = ap.Package(data)
    assert len(pkg.blobs) == 1
    assert len(pkg.manifest["assets"]) == 2


@pytest.mark.parametrize("name", ["../escape", "/absolute", "blobs/../escape", "other.bin", "C:\\bad"])
def test_unsafe_or_undeclared_archive_members_refused(name):
    data = rewrite(small_package(), lambda members: members.update({name: b"bad"}))
    with pytest.raises(ap.PackageError): ap.Package(data)


def test_tamper_refused():
    def tamper(members):
        name = next(n for n in members if n.startswith("blobs/"))
        members[name] = b"wrong"
    with pytest.raises(ap.PackageError, match="digest"):
        ap.Package(rewrite(small_package(), tamper))


def test_duplicate_zip_member_refused():
    data = small_package()
    stream = io.BytesIO(data)
    with pytest.warns(UserWarning):
        with zipfile.ZipFile(stream, "a") as archive:
            archive.writestr("manifest.json", b"{}")
    with pytest.raises(ap.PackageError, match="duplicate"):
        ap.Package(stream.getvalue())


def test_symlink_refused():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        info = zipfile.ZipInfo("manifest.json")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, b"{}")
    with pytest.raises(ap.PackageError, match="symlink"):
        ap.Package(stream.getvalue())


def test_compression_refused_in_stored_profile():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", b"{}")
    with pytest.raises(ap.PackageError, match="compression"):
        ap.Package(stream.getvalue())


@pytest.mark.parametrize("value", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'])
def test_json_ambiguities_refused(value):
    with pytest.raises(ap.PackageError): ap.parse_json(value)


@pytest.mark.parametrize("edit", [
    lambda m: m.update(format="future"),
    lambda m: m["assets"]["greeting"].update(bytes=-1),
    lambda m: m["assets"]["greeting"].update(dependencies=["missing"]),
    lambda m: m["assets"]["greeting"].update(dependencies=["greeting"]),
    lambda m: m["component"].update(entry=[]),
])
def test_manifest_fail_closed(edit):
    with pytest.raises(ap.PackageError):
        ap.Package(mutate_manifest(small_package(), edit))


def test_missing_payload_refused():
    def edit(members):
        del members[next(n for n in members if n.startswith("blobs/"))]
    with pytest.raises(ap.PackageError, match="missing"):
        ap.Package(rewrite(small_package(), edit))


def test_wrong_asset_kind_refused():
    with pytest.raises(ap.PackageError): ap.Package(small_package()).get("greeting", "image")


def test_link_keeps_package_identity_but_changes_shell():
    pkg = ap.Package(small_package())
    a, b = pilot.connect(pkg, "terminal"), pilot.connect(pkg, "jsonl")
    assert a["package_sha256"] == b["package_sha256"]
    assert a["link_sha256"] != b["link_sha256"]


def test_missing_wire_refused():
    with pytest.raises(ap.PackageError, match="every required"):
        ap.link(ap.Package(small_package()), pilot.shell("terminal"), {})


def test_mismatched_contract_negative_control():
    pkg = ap.Package(small_package())
    wrong = pilot.shell("terminal")
    wrong["provides"]["terminal.present"] = "0" * 64
    with pytest.raises(ap.PackageError, match="incompatible"):
        ap.link(pkg, wrong, {p: "terminal." + p for p in pilot.PORTS})


def test_word16_asset_input_output_state_equivalence(tmp_path):
    program = fixture(tmp_path)
    baseline = Word16Runtime(program)
    data, _ = pilot.bundle_program(program)
    asset = pilot.AssetRuntime(ap.Package(data), strict_text=True)
    assert asset.run() == baseline.run()
    assert asset.command("hello") == baseline.command("hello")
    assert asset.snapshot() == baseline.snapshot()
    assert asset.asset_hits == 2
    assert asset.codec_misses == 0


def test_mutable_text_guard_and_strict_refusal(tmp_path):
    program = fixture(tmp_path, bytes.fromhex("8703a0ba"), [(0x3a0, text("alpha"))])
    data, _ = pilot.bundle_program(program)
    runtime = pilot.AssetRuntime(ap.Package(data))
    runtime.memory[0x3a0:0x3a4] = text("omega")
    assert runtime.run()["text"] == "omega"
    assert runtime.changed_dependencies == 1
    assert runtime.codec_misses == 1
    strict = pilot.AssetRuntime(ap.Package(data), strict_text=True)
    strict.memory[0x3a0:0x3a4] = text("omega")
    with pytest.raises(Word16Error, match="closure failure"): strict.run()


def test_abbreviation_dependency_guard(tmp_path):
    code = b"\xb2" + packed_codes([1, 0]) + b"\xba"
    program = fixture(tmp_path, code, [(640, (0x3a0 // 2).to_bytes(2, "big")),
                                      (0x3a0, text("alpha")), (0x3b0, text("omega"))])
    data, _ = pilot.bundle_program(program)
    runtime = pilot.AssetRuntime(ap.Package(data))
    runtime.memory[640:642] = (0x3b0 // 2).to_bytes(2, "big")
    assert runtime.run()["text"] == "omega"
    assert runtime.changed_dependencies == 1


def test_memory_text_stream_preserves_control_bytes(tmp_path):
    program = fixture(tmp_path, b"\xb2" + text("a\t\v\nb") + b"\xba")
    data, _ = pilot.bundle_program(program)
    baseline = Word16Runtime(program)
    asset = pilot.AssetRuntime(ap.Package(data), strict_text=True)
    for runtime in (baseline, asset):
        runtime._host("output_stream", [3, 0x360])
        assert runtime.run()["text"] == ""
        runtime._host("output_stream", [-3])
        assert runtime.memory[0x360:0x367] == b"\x00\x05a\x09\x0b\x0db"
    assert baseline.snapshot() == asset.snapshot()


def test_checkpoint_cross_shell_and_wrong_package(tmp_path):
    program = fixture(tmp_path)
    data, _ = pilot.bundle_program(program)
    pkg = ap.Package(data)
    a = pilot.AssetRuntime(pkg)
    a.run()
    checkpoint = a.save_package_state()
    pilot.connect(pkg, "terminal")
    pilot.connect(pkg, "jsonl")
    b = pilot.AssetRuntime(pkg)
    b.restore_package_state(checkpoint)
    assert a.command("hello") == b.command("hello")
    wrong = copy.deepcopy(checkpoint)
    wrong["package_sha256"] = "0" * 64
    with pytest.raises(ap.PackageError, match="identity"):
        b.restore_package_state(wrong)


def test_cooked_app_is_deterministic_and_source_independent(tmp_path):
    program = fixture(tmp_path)
    data, _ = pilot.bundle_program(program)
    app, _ = pilot.cook_zipapp(data, "jsonl")
    assert app == pilot.cook_zipapp(data, "jsonl")[0]
    path = tmp_path / "standalone.pyz"
    path.write_bytes(app)
    (tmp_path / "authored.z3").unlink()
    run = subprocess.run([sys.executable, "-I", str(path)], input='{"command":"hello"}\n',
                         text=True, capture_output=True, timeout=15, cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    turns = [json.loads(line) for line in run.stdout.splitlines()]
    assert [turn["text"] for turn in turns] == ["alpha", "omega"]
    assert turns[-1]["status"] == "halted"


def test_game_output_refused_inside_git(tmp_path):
    (tmp_path / ".git").mkdir()
    with pytest.raises(ap.PackageError, match="outside Git"):
        ap.private_output(tmp_path / "game.bundle")
