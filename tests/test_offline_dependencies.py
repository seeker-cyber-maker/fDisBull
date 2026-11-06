import importlib.util
import io
from argparse import Namespace
from pathlib import Path
import sys
import tarfile
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deps = load_script("offline_dependencies")
kit = load_script("build_offline_kit")


def make_wheel(path, name, version):
    path.parent.mkdir(parents=True, exist_ok=True)
    distribution = name.replace("-", "_")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"{distribution}-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        )
        archive.writestr(f"{distribution}/__init__.py", "")


def fake_wheelhouse(tmp_path):
    requirements = deps.load_requirements(ROOT, ("proof",))
    wheelhouse = tmp_path / "wheelhouse"
    wheels = {}
    sources = {}
    for requirement in requirements:
        name = deps.requirement_name(requirement)
        version = requirement.split("==", 1)[1] if "==" in requirement else "12.3.0"
        filename = f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
        path = wheelhouse / filename
        make_wheel(path, name, version)
        entry = deps.inspect_wheel(path)
        wheels[name] = entry
        sources[name] = path
    return requirements, wheels, sources


def build_fake_bundle(tmp_path):
    requirements, wheels, sources = fake_wheelhouse(tmp_path)
    archive = tmp_path / "fdisbull-dependencies.tar.gz"
    deps.write_bundle(requirements, ("proof",), wheels, sources, archive)
    return requirements, archive


def test_requirements_are_canonical_and_proof_included():
    requirements = deps.load_requirements(ROOT, ("proof",))
    assert "capstone==5.0.9" in requirements
    assert "iced-x86==1.21.0" in requirements
    assert "lief==1.0.0" in requirements
    assert "pillow>=10.4,<13" in requirements
    assert "z3-solver==5.3.2.0" in requirements
    assert deps.canonical_requirement(" Pillow >= 10.4, < 13 ") == "pillow>=10.4,<13"
    assert deps.fingerprint(requirements, ("proof",)) == deps.fingerprint(
        list(reversed(requirements)), ("proof",)
    )


def test_bundle_is_reproducible_and_extractable(tmp_path):
    requirements, wheels, sources = fake_wheelhouse(tmp_path)
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    deps.write_bundle(requirements, ("proof",), wheels, sources, first)
    deps.write_bundle(requirements, ("proof",), wheels, sources, second)
    assert first.read_bytes() == second.read_bytes()
    extracted = deps.extract_bundle(first, tmp_path / "extracted")
    assert (extracted / "manifest.json").is_file()
    assert len(list((extracted / "wheels").glob("*.whl"))) == len(requirements)
    assert deps.load_bundle(first)["manifest"]["fingerprint"] == deps.fingerprint(
        requirements, ("proof",)
    )


def test_build_from_wheelhouse_writes_bundle(tmp_path):
    requirements, _, _ = fake_wheelhouse(tmp_path)
    wheelhouse = tmp_path / "wheelhouse"
    output = tmp_path / "built.tar.gz"
    result = deps.build(
        Namespace(
            project_root=ROOT,
            output=output,
            previous=None,
            wheelhouse=wheelhouse,
            extra=[],
            no_extras=False,
            python=sys.executable,
            require_reuse=False,
        )
    )
    assert result["status"] == "built"
    assert deps.load_bundle(output)["manifest"]["requirements"] == requirements
    assert output.with_name(output.name + ".sha256").is_file()


def test_reuse_copies_previous_bundle_without_downloading(tmp_path):
    _, previous = build_fake_bundle(tmp_path)
    output = tmp_path / "reused.tar.gz"
    result = deps.build(
        Namespace(
            project_root=ROOT,
            output=output,
            previous=previous,
            wheelhouse=None,
            extra=[],
            no_extras=False,
            python=sys.executable,
            require_reuse=True,
        )
    )
    assert result["status"] == "reused"
    assert output.read_bytes() == previous.read_bytes()
    assert (
        output.with_name(output.name + ".sha256")
        .read_text()
        .startswith(result["sha256"])
    )


def test_changed_constraint_reports_rebuild(tmp_path):
    requirements, previous = build_fake_bundle(tmp_path)
    changed = list(requirements)
    changed[0] = "capstone==6.0.0"
    difference = deps.compare_specs(deps.load_bundle(previous), changed, ("proof",))
    assert difference["changed"] is True
    assert difference["version_changed"] == ["capstone"]


def test_tampered_wheel_is_rejected(tmp_path):
    _, previous = build_fake_bundle(tmp_path)
    tampered = tmp_path / "tampered.tar.gz"
    with (
        tarfile.open(previous, "r:gz") as source,
        tarfile.open(tampered, "w:gz") as target,
    ):
        for member in source.getmembers():
            info = tarfile.TarInfo(member.name)
            info.mode = member.mode
            info.type = member.type
            if member.isfile():
                data = source.extractfile(member).read()
                if member.name.endswith(".whl"):
                    data += b"tampered"
                info.size = len(data)
                target.addfile(info, io.BytesIO(data))
            else:
                target.addfile(info)
    with pytest.raises(ValueError, match="SHA256SUMS|hash mismatch"):
        deps.load_bundle(tampered)


def test_offline_kit_accepts_dependency_bundle(tmp_path):
    _, bundle = build_fake_bundle(tmp_path)
    wheels = kit.dependency_bundle_wheels(bundle)
    assert len(wheels) == 5
    assert {path.suffix for path in wheels} == {".whl"}
    assert all(path.is_file() for path in wheels)


def test_split_dos_and_windows_dependency_profiles_and_chat_release(tmp_path):
    dos_reqs = deps.load_requirements(ROOT, deps.resolve_extras("dos"), profile="dos")
    win_reqs = deps.load_requirements(
        ROOT, deps.resolve_extras("windows"), profile="windows"
    )
    assert [deps.requirement_name(r) for r in dos_reqs] == [
        "capstone",
        "iced-x86",
        "lief",
        "pillow",
        "z3-solver",
    ]
    assert [deps.requirement_name(r) for r in win_reqs] == [
        "dncil",
        "dnfile",
        "pefile",
        "unicorn",
    ]
    shared_wheelhouse = tmp_path / "shared_wheelhouse"
    for requirement in (*dos_reqs, *win_reqs):
        name = deps.requirement_name(requirement)
        version = requirement.split("==", 1)[1] if "==" in requirement else "12.3.0"
        make_wheel(
            shared_wheelhouse / f"{name.replace('-', '_')}-{version}-py3-none-any.whl",
            name,
            version,
        )
    make_wheel(
        shared_wheelhouse / f"fdisbull-{kit.VERSION}-py3-none-any.whl",
        "fdisbull",
        kit.VERSION,
    )
    make_wheel(
        shared_wheelhouse / f"fdisbull_player-{kit.VERSION}-py3-none-any.whl",
        "fdisbull-player",
        kit.VERSION,
    )
    dos_bundle = tmp_path / "dos-deps.tar.gz"
    win_bundle = tmp_path / "windows-deps.tar.gz"
    dos_res = deps.build(
        Namespace(
            project_root=ROOT,
            output=dos_bundle,
            previous=None,
            wheelhouse=shared_wheelhouse,
            profile="dos",
            extra=[],
            no_extras=False,
            python=sys.executable,
            require_reuse=False,
        )
    )
    win_res = deps.build(
        Namespace(
            project_root=ROOT,
            output=win_bundle,
            previous=None,
            wheelhouse=shared_wheelhouse,
            profile="windows",
            extra=[],
            no_extras=False,
            python=sys.executable,
            require_reuse=False,
        )
    )
    assert set(deps.load_bundle(dos_bundle)["manifest"]["wheels"]) == {
        "capstone",
        "iced-x86",
        "lief",
        "pillow",
        "z3-solver",
    }
    assert set(deps.load_bundle(win_bundle)["manifest"]["wheels"]) == {
        "dncil",
        "dnfile",
        "pefile",
        "unicorn",
    }
    assert dos_res["fingerprint"] != win_res["fingerprint"]
    chat_release = tmp_path / "chat-release.tar.gz"
    rel_res = deps.build_chat_release(
        Namespace(
            project_root=ROOT,
            wheelhouse=shared_wheelhouse,
            output=chat_release,
            tool_zip=None,
            source_commit="b" * 40,
        )
    )
    assert rel_res["status"] == "built"
    assert set(rel_res["wheels"]) == {"fdisbull", "fdisbull-player"}
    with tarfile.open(chat_release, "r:gz") as tar:
        installer = (
            tar.extractfile(f"fdisbull-{kit.VERSION}-chat-release/install.sh")
            .read()
            .decode()
        )
    assert "--dos-deps" in installer
    assert "--windows-deps" in installer
