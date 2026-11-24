"""Raw DOSBox-X CPU ZIP component format checks for the PSE checkpoint candidate."""

from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import zipfile

import pytest

from fdisbull.debugger import DebuggerError
from fdisbull.project import Project


MARKER = b"PSE1"


def _candidate():
    value = os.environ.get("FDISBULL_DOSBOX_LARGE_PAGE_CANDIDATE")
    if not value:
        pytest.skip("Set FDISBULL_DOSBOX_LARGE_PAGE_CANDIDATE to the explicitly built candidate")
    path = Path(value).expanduser().resolve(strict=True)
    assert path.is_file() and os.access(path, os.X_OK)
    return path


def _rewrite_cpu_member(archive: bytes, variant: str) -> bytes:
    with zipfile.ZipFile(BytesIO(archive), "r") as source:
        infos = source.infolist()
        members = {info.filename: source.read(info.filename) for info in infos}
    assert "CPU" in members
    cpu = members["CPU"]
    assert len(cpu) >= 8 and cpu[-8:-4] == MARKER

    if variant == "valid":
        pass
    elif variant == "legacy":
        cpu = cpu[:-8]
    elif variant == "bad-marker":
        cpu = cpu[:-8] + b"BAD!" + cpu[-4:]
    elif variant == "short-trailer":
        cpu = cpu[:-1]
    elif variant == "trailing-byte":
        cpu += b"x"
    elif variant == "short-prefix":
        # Remove the trailer and one byte belonging to the historical CPU entry.
        cpu = cpu[:-9]
    else:
        raise AssertionError(f"unknown format variant: {variant}")
    members["CPU"] = cpu

    output = BytesIO()
    with zipfile.ZipFile(output, "w") as destination:
        for info in infos:
            # writestr recomputes the CRC and sizes for the modified CPU member.
            destination.writestr(info, members[info.filename])
    return output.getvalue()


@pytest.mark.parametrize(
    ("variant", "accepted"),
    [
        ("valid", True),
        ("legacy", True),
        ("bad-marker", False),
        ("short-trailer", False),
        ("trailing-byte", False),
        ("short-prefix", False),
    ],
)
def test_candidate_loads_or_rejects_raw_cpu_zip_entry(tmp_path, variant, accepted):
    executable = _candidate()
    game = tmp_path / "game"
    game.mkdir()
    binary = game / "PSE.COM"
    binary.write_bytes(b"\xEB\xFE")  # Homegrown real-mode infinite loop.
    database = tmp_path / "analysis.fdb"

    with Project.create(database, binary, image="com") as project:
        with project.debugger(str(executable), game) as debug:
            checkpoint = debug._capture_native_checkpoint()
            modified = _rewrite_cpu_member(checkpoint["data"], variant)
            artifact = debug._artifact(
                f"pse-format-{variant}.sav", "state", modified, checkpoint["metadata"])["artifact"]
            if accepted:
                result = debug.load_state(artifact)
                assert result["registers"]["cpu_mode"] == "real"
            else:
                with pytest.raises(DebuggerError, match=r"State load failed \(STATE_FAILED\)"):
                    debug.load_state(artifact)
                # Partial native restores are disposed by load_state on failure.
                assert debug.closed

    assert debug.rpc.process.poll() is not None
