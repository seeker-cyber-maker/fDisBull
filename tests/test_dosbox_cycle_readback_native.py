"""Opt-in read-only DOSBox-X CPU cycle-mode qualification on authored COM code."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_native_cycle_mode_readback_for_auto_and_fixed(tmp_path):
    if os.environ.get("FDISBULL_REQUIRE_DOSBOX_CYCLE_READBACK") != "1":
        pytest.skip("Set FDISBULL_REQUIRE_DOSBOX_CYCLE_READBACK=1 and FDISBULL_DOSBOX")
    value = os.environ.get("FDISBULL_DOSBOX")
    if not value:
        pytest.fail("FDISBULL_DOSBOX is required for native cycle readback")
    native = Path(value).expanduser().resolve(strict=True)
    assert native.is_file() and os.access(native, os.X_OK)
    assert not tmp_path.resolve().is_relative_to(Path(__file__).resolve().parents[1])

    observations = {}
    for arm, setting in (("auto", "cpu cycles=auto"),
                         ("fixed", "cpu cycles=fixed 157600")):
        stage = tmp_path / arm
        stage.mkdir()
        (stage / "WAIT.COM").write_bytes(b"\xeb\xfe")
        launcher = stage / "dosbox-cycles"
        launcher.write_text(
            "#!" + sys.executable + "\nimport os, sys\n"
            + "native=" + repr(str(native)) + "\n"
            + "setting=" + repr(setting) + "\n"
            + "os.execv(native, [native, *sys.argv[1:], '-set', setting])\n"
        )
        launcher.chmod(0o700)
        rpc = DOSBoxRPC(launcher, stage)
        owner = rpc.process
        try:
            started = rpc.call("session.start", dict(
                target=dict(command="WAIT.COM", arguments=[]),
                mounts=[dict(drive="C", host_path=str(stage))], break_at="entry"))
            timing = rpc.call("execution.timing", dict(session_id=started["session_id"]))
            fields = ("cpu_cycle_max", "cpu_cycle_auto_adjust",
                      "cpu_cycle_auto_detect", "cpu_cycle_auto_adjust_skipped")
            assert all(field in timing for field in fields), timing
            observations[arm] = {field: timing[field] for field in fields}
        finally:
            rpc.close()
        assert owner.poll() == 0

    assert observations["auto"] == dict(
        cpu_cycle_max=3000, cpu_cycle_auto_adjust=False,
        cpu_cycle_auto_detect=True, cpu_cycle_auto_adjust_skipped=False)
    assert observations["fixed"] == dict(
        cpu_cycle_max=157600, cpu_cycle_auto_adjust=False,
        cpu_cycle_auto_detect=False, cpu_cycle_auto_adjust_skipped=False)
    (tmp_path / "cycle-readback.json").write_text(json.dumps(dict(
        format="fdisbull-dosbox-cycle-readback-1", binary_sha256=_sha(native),
        authored_com_sha256=_sha(tmp_path / "auto" / "WAIT.COM"),
        observations=observations), sort_keys=True, indent=2) + "\n")
