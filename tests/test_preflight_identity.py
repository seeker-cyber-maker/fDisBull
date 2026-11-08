"""Runtime identity, capability preflight and durable primary-version tests."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fdisbull import __version__
from fdisbull.cli import main, respond
from fdisbull.runtime_identity import (
    candidate_number,
    identity,
    release_version,
)

REPO = Path(__file__).resolve().parents[1]


def test_identity_final_release_fields():
    report = identity()
    assert report["format"] == "fdisbull-runtime-identity-1"
    assert report["runtime_version"] == __version__
    assert report["primary_version"] == "0.34.1"
    assert report["candidate_number"] is None
    assert report["candidate_label"] is None
    assert report["runtime_version"] == report["distribution_version"]
    assert report["metadata_normalization"] is None


def test_release_and_candidate_mapping_matches_pep440():
    from fdisbull import runtime_identity as module

    original = module._metadata_version
    try:
        module._metadata_version = lambda: "0.34.1rc9"
        assert module.release_version() == "0.34.1"
        assert module.candidate_number() == 9
        report = module.identity()
        assert report["candidate_label"] == "0.34.1-rc9"
        assert report["distribution_version"] == "0.34.1rc9"
        # PEP 440 normalized equivalent stays in distribution metadata. The
        # runtime constant still says 0.34.1, so the report records the
        # candidate/metadata-vs-runtime mismatch as a diagnostic.
        assert report["metadata_normalization"] == "distribution_metadata_mismatch"
        # Numeric RC ordering: rc9 < rc10 must follow from the parsed integer.
        numbers = []
        for suffix in ("rc9", "rc10"):
            module._metadata_version = lambda suffix=suffix: "0.34.1" + suffix
            numbers.append(module.candidate_number())
        assert numbers == [9, 10]
    finally:
        module._metadata_version = original


def test_metadata_mismatch_is_diagnostic_not_repaired():
    from fdisbull import runtime_identity as module

    original = module._metadata_version
    try:
        module._metadata_version = lambda: "0.30.0"
        report = module.identity()
        assert report["runtime_version"] == __version__
        assert report["distribution_version"] == "0.30.0"
        assert report["metadata_normalization"] == "distribution_metadata_mismatch"
    finally:
        module._metadata_version = original


def test_identity_context_is_optional_and_retained():
    report = identity(schema=1, backend="dosbox")
    assert report["context"] == {"schema": 1, "backend": "dosbox"}
    assert identity()["context"] is None


@pytest.fixture()
def manifest(tmp_path):
    path = tmp_path / "expectations.json"
    path.write_text(
        json.dumps(
            {
                "capabilities": [
                    {
                        "type": "module",
                        "name": "fdisbull.decoder",
                        "attribute": "decode",
                    },
                    {
                        "type": "module",
                        "name": "fdisbull.absent_module",
                        "attribute": "x",
                    },
                    {"type": "skill", "name": "fdisbull-investigate", "references": []},
                    {"type": "dependency", "name": "fdisbull", "requirement": "any"},
                    {
                        "type": "dependency",
                        "name": "not-installed-anywhere",
                        "requirement": ">=1",
                    },
                ],
            }
        )
    )
    return path


def test_preflight_reports_ready_and_missing_per_capability(manifest, capsys):
    assert main(["preflight", "--expectations", str(manifest)]) == 1
    out = json.loads(capsys.readouterr().out)
    body = out["result"]
    assert body["format"] == "fdisbull-preflight-1"
    assert body["status"] == "issues_found"
    # Absent module + absent dependency fail; the rest are ready.
    assert body["summary"]["missing"] == 2
    assert body["summary"]["ready"] == 3
    by_name = {item["name"]: item for item in body["checks"]}
    assert by_name["fdisbull.decoder"]["status"] == "ready"
    assert by_name["fdisbull.absent_module"]["status"] == "missing"
    assert by_name["fdisbull-investigate"]["status"] == "ready"
    assert by_name["fdisbull"]["status"] == "ready"
    assert by_name["not-installed-anywhere"]["status"] == "missing"
    assert body["runtime_identity"]["primary_version"] == "0.34.1"
    # Independent checks continue after ordinary failures.
    assert body["summary"]["total"] == len(body["checks"])


def test_preflight_missing_manifest_is_explicit(tmp_path):
    reply = respond(
        {
            "method": "preflight",
            "params": {"expectations": str(tmp_path / "absent.json")},
        }
    )
    assert reply["ok"]
    body = reply["result"]
    assert body["status"] == "missing_expectations"
    assert "unreadable" in body["error"]


def test_preflight_invalid_manifest_json_is_explicit(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    reply = respond({"method": "preflight", "params": {"expectations": str(path)}})
    assert reply["ok"]
    assert reply["result"]["status"] == "missing_expectations"


def test_preflight_unknown_capability_type_is_refused(tmp_path):
    path = tmp_path / "odd.json"
    path.write_text(
        json.dumps({"capabilities": [{"type": "cantrip", "name": "spell"}]})
    )
    reply = respond({"method": "preflight", "params": {"expectations": str(path)}})
    assert reply["ok"]
    body = reply["result"]
    assert body["status"] == "refused"
    assert "cantrip" in body["error"]


def test_preflight_writes_standalone_report_with_context(manifest, tmp_path):
    out = tmp_path / "report.json"
    reply = respond(
        {
            "method": "preflight",
            "params": {"expectations": str(manifest), "output": str(out)},
        }
    )
    assert reply["ok"]
    assert out.is_file()
    standalone = json.loads(out.read_text())
    assert standalone["format"] == "fdisbull-preflight-1"
    # Standalone diagnostics carry the full execution context.
    assert standalone["runtime_identity"]["format"] == "fdisbull-runtime-identity-1"
    assert "written_to" not in standalone or standalone["written_to"] == str(out)


def test_preflight_never_creates_fdb_or_launches_backend(manifest, monkeypatch):
    import fdisbull.preflight as module

    def forbidden(*args, **kwargs):
        raise AssertionError("preflight launched a process or created a project")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    from fdisbull.project import Project

    monkeypatch.setattr(Project, "create", forbidden)
    reply = respond({"method": "preflight", "params": {"expectations": str(manifest)}})
    assert reply["ok"]


def test_version_json_prints_full_identity(capsys):
    import pytest as _pytest

    with _pytest.raises(SystemExit) as exit_info:
        main(["--version-json"])
    assert exit_info.value.code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["format"] == "fdisbull-runtime-identity-1"
    assert report["primary_version"] == "0.34.1"
    assert report["runtime_version"] == __version__


def test_plain_version_stays_a_plain_string():
    result = subprocess.run(
        [sys.executable, "-m", "fdisbull", "--version"],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO / "src")},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == __version__


def test_capabilities_expose_candidate_fields():
    from fdisbull.capabilities import capabilities

    report = capabilities()
    package = report["package"]
    assert package["primary_version"] == "0.34.1"
    assert package["candidate_number"] is None
    assert package["runtime_version"] == __version__


def test_durable_project_records_primary_version(tmp_path):
    # A candidate-tagged runtime writes the primary version line only.
    pytest.importorskip("lief")
    from fdisbull.project import Project
    from fdisbull import runtime_identity as module

    # A minimal MZ module (the documented loader fixture shape); only the
    # provenance record is read, nothing is executed.
    import struct

    header = bytearray(64)
    struct.pack_into("<14H", header, 0, 0x5A4D, 96, 1, 0, 4, 0, 0xFFFF, 0, 32, 0, 0, 0, 28, 0)
    binary = tmp_path / "SELFTEST.COM"
    binary.write_bytes(bytes(header) + b"\xc3" + bytes(31))
    original = module.release_version
    try:
        module.release_version = lambda: "0.34.1"
        database = tmp_path / "private.fdb"
        with Project.create(database, binary) as project:
            record = json.loads(
                project.db.execute(
                    "SELECT document FROM target_sources WHERE version=1"
                ).fetchone()[0]
            )
        assert record["loader"]["version"] == "0.34.1"
        # An RC runtime would write the same primary version here.
    finally:
        module.release_version = original
