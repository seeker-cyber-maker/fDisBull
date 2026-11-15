"""Narrow delivery guard fixtures; fake archives are not runtime qualification."""
import io
from pathlib import Path
import runpy
import tarfile
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = runpy.run_path(str(ROOT / "scripts/check_native_gog_distribution.py"))["check_native_gog"]


def modules():
    return {name: (ROOT / "src/fdisbull" / name).read_bytes()
            for name in ("native_inno.py", "gog_unpack.py")}


def make_zip(path, content, prefix="fdisbull"):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
        for name, data in content.items():
            out.writestr(prefix + "/" + name, data)


@pytest.mark.parametrize("kind", ["wheel", "source-zip", "source-tar"])
def test_delivery_guard_accepts_matching_modules(tmp_path, kind):
    content = modules()
    if kind == "source-tar":
        path = tmp_path / "fdisbull-0.32.0.tar.gz"
        with tarfile.open(path, "w:gz") as out:
            for name, data in content.items():
                info = tarfile.TarInfo("fdisbull-0.32.0/src/fdisbull/" + name)
                info.size = len(data)
                out.addfile(info, io.BytesIO(data))
    else:
        path = tmp_path / ("fdisbull-0.32.0-py3-none-any.whl" if kind == "wheel" else "fdisbull-0.32.0-tool.zip")
        make_zip(path, content, "fdisbull" if kind == "wheel" else "fdisbull-0.32.0/src/fdisbull")
    result = CHECK(path)
    assert result["artifacts_checked"] == 1
    assert result["runtime_validation"] == "not_run"


@pytest.mark.parametrize("missing", ["native_inno.py", "gog_unpack.py"])
def test_missing_decoder_rejected_despite_version_label(tmp_path, missing):
    content = modules()
    del content[missing]
    path = tmp_path / "fdisbull-0.32.0-py3-none-any.whl"
    make_zip(path, content)
    with pytest.raises(ValueError, match="lacks native"):
        CHECK(path)


def test_legacy_wrapper_rejected_even_when_native_module_is_bundled(tmp_path):
    content = modules()
    content["gog_unpack.py"] = b"import subprocess\n"
    path = tmp_path / "fdisbull-0.32.0-py3-none-any.whl"
    make_zip(path, content)
    with pytest.raises(ValueError, match="not wired"):
        CHECK(path)


def test_native_wrapper_with_external_fallback_is_rejected(tmp_path):
    content = modules()
    content["gog_unpack.py"] += b"\nimport subprocess\n"
    path = tmp_path / "fdisbull-0.32.0-py3-none-any.whl"
    make_zip(path, content)
    with pytest.raises(ValueError, match="imports subprocess"):
        CHECK(path)


def test_offline_kit_requires_identical_packaged_decoder_sources(tmp_path):
    wheel = tmp_path / "fdisbull-0.32.0-py3-none-any.whl"
    source = tmp_path / "fdisbull-0.32.0-tool.zip"
    kit = tmp_path / "kit.zip"
    make_zip(wheel, modules())
    content = modules()
    for drift in (False, True):
        if drift:
            content["native_inno.py"] += b"\n# Different source cut.\n"
        make_zip(source, content, "fdisbull-0.32.0/src/fdisbull")
        with zipfile.ZipFile(kit, "w") as out:
            out.write(wheel, "kit/packages/" + wheel.name)
            out.write(source, "kit/packages/" + source.name)
        if drift:
            with pytest.raises(ValueError, match="differs across"):
                CHECK(kit)
        else:
            assert CHECK(kit)["artifacts_checked"] == 2


def test_release_selector_includes_native_decoder_and_its_tests():
    selector = runpy.run_path(str(ROOT / "scripts/build_release.py"))["release_files"]
    names = {path.relative_to(ROOT).as_posix() for path in selector(ROOT)}
    assert {"src/fdisbull/native_inno.py", "src/fdisbull/gog_unpack.py",
            "scripts/check_native_gog_distribution.py", "tests/test_native_inno_profiles.py",
            "tests/test_native_inno_distribution.py"} <= names
