"""Compatibility imports and independently distributed shared-kernel artifacts."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import zipfile

import pytest

from fdisbull import memory_search as compatibility
from fdisbull_core import memory_search as shared


ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("shared_distribution_guard", ROOT / "scripts/check_dist.py")
guard = module_from_spec(spec)
spec.loader.exec_module(guard)


def shared_wheel(path, *, extra=None, dependency=None, missing=None):
    metadata = "fdisbull_core-0.1.0.dev4.dist-info"
    files = {
        "fdisbull_core/__init__.py": b'__version__ = "0.1.0.dev4"\n',
        "fdisbull_core/memory_search.py": b"# authored package fixture\n",
        "fdisbull_core/pipe_rpc.py": b"# authored transport fixture\n",
        "fdisbull_core/agi_scene.py": b"# authored scene consumer fixture\n",
        metadata + "/METADATA": (
            "Metadata-Version: 2.1\nName: fdisbull-core\nVersion: 0.1.0.dev4\n"
            "Requires-Python: >=3.12\n" + (f"Requires-Dist: {dependency}\n" if dependency else "")
        ).encode(),
        metadata + "/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        metadata + "/RECORD": b"",
    }
    if extra:
        files[extra] = b"unexpected"
    if missing:
        files.pop(missing)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


def test_legacy_public_imports_resolve_to_one_shared_implementation():
    names = {"MAX_CANDIDATES", "MAX_INTERVALS", "MAX_RESULT_ROWS", "MAX_SNAPSHOT_BYTES",
             "plan_edit", "refine_search", "search_results", "snapshot_metadata",
             "start_search", "validate_search", "validate_snapshot"}
    assert set(compatibility.__all__) == names
    for name in names:
        assert getattr(compatibility, name) is getattr(shared, name)


def test_separate_shared_wheel_is_accepted(tmp_path):
    path = shared_wheel(tmp_path / "fdisbull_core-0.1.0.dev4-py3-none-any.whl")
    assert guard.check_archive(path) == 7


@pytest.mark.parametrize("extra", ["fdisbull/__init__.py", "dotbox/__init__.py",
                                    "fdisbull_core/unexpected.py"])
def test_shared_wheel_rejects_product_code_and_unlisted_modules(tmp_path, extra):
    path = shared_wheel(tmp_path / "fdisbull_core-0.1.0.dev4-py3-none-any.whl", extra=extra)
    with pytest.raises(ValueError):
        guard.check_archive(path)


@pytest.mark.parametrize("required", ["memory_search.py", "pipe_rpc.py", "agi_scene.py"])
def test_shared_wheel_requires_kernel_and_no_runtime_dependencies(tmp_path, required):
    path = tmp_path / "fdisbull_core-0.1.0.dev4-py3-none-any.whl"
    shared_wheel(path, missing="fdisbull_core/" + required)
    with pytest.raises(ValueError, match="missing|modules"):
        guard.check_archive(path)
    shared_wheel(path, dependency="fdisbull==0.34.1")
    with pytest.raises(ValueError, match="dependenc"):
        guard.check_archive(path)
