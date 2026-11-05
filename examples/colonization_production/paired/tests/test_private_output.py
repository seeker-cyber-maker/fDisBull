"""Source-retaining outputs must not enter ordinary checkouts or worktrees."""
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("colonization_native_boundary", ROOT / "tools/new_native.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)

@pytest.mark.parametrize("worktree", [False, True])
def test_checkout_output_refused_before_reading_sources(tmp_path, worktree):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    marker = checkout / ".git"
    if worktree:
        marker.write_text("gitdir: /unused/private-gitdir\n")
    else:
        marker.mkdir()
    destination = checkout / "private" / "native"
    with pytest.raises(ValueError, match="outside a Git checkout"):
        native.build(tmp_path / "missing-originals", destination)
    assert not destination.exists()
