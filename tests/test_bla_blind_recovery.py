from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bla_blind_recovery.py"
spec = importlib.util.spec_from_file_location("bla_blind_recovery", SCRIPT)
blind = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = blind
spec.loader.exec_module(blind)


def _prepared(tmp_path: Path, monkeypatch) -> Path:
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    fake_fdisbull = prefix / "bin" / "fdisbull"
    fake_fdisbull.write_text("#!/bin/sh\nexit 0\n")
    fake_fdisbull.chmod(0o755)
    python = Path(sys.executable).resolve()
    source = tmp_path / "candidate.dll"
    source.write_bytes(b"owned test image")
    trial = tmp_path / "external" / "trial-a"
    trial.parent.mkdir()
    monkeypatch.setattr(blind, "_admit_storage", lambda parent, size: {
        "mode": "storage_admission", "returncode": 0, "expected_bytes": size
    })
    blind.prepare(target=source, output=trial, python=python, prefix=prefix,
                  storage_waiver=blind.AUTHORIZED_STORAGE_WAIVER)
    return trial


def test_task_exposes_only_opaque_abi_and_submission_contract():
    assert "void opaque_entry(u64, u64, u64*)" in blind.TASK
    assert "bounded_update" not in blind.TASK
    assert "volatile/nonvolatile" in blind.TASK
    assert "oracle" in blind.TASK
    assert "solver.py" in blind.TASK and "REPORT.md" in blind.TASK


def test_storage_refusal_creates_no_trial_or_copied_target(tmp_path, monkeypatch):
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    (prefix / "bin" / "fdisbull").write_text("x")
    target = tmp_path / "candidate.dll"
    target.write_bytes(b"target")
    output = tmp_path / "external" / "trial"
    output.parent.mkdir()
    monkeypatch.setattr(blind, "_admit_storage", lambda *_: {"mode": "storage_admission", "returncode": 1})
    with pytest.raises(RuntimeError, match="storage admission refused"):
        blind.prepare(target=target, output=output, python=Path(sys.executable), prefix=prefix)
    assert not output.exists()


def test_prepare_rejects_repository_or_agent_instruction_ancestry(tmp_path):
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    (prefix / "bin" / "fdisbull").write_text("x")
    target = tmp_path / "candidate.dll"
    target.write_bytes(b"target")
    with pytest.raises(ValueError, match="source repository"):
        blind.prepare(target=target, output=SCRIPT.parents[1] / "blind-trial-never-created",
                      python=Path(sys.executable), prefix=prefix,
                      storage_waiver=blind.AUTHORIZED_STORAGE_WAIVER)


def test_explicit_waiver_is_recorded_without_claiming_admission(tmp_path, monkeypatch):
    trial = _prepared(tmp_path, monkeypatch)
    manifest = json.loads((trial / "trial.json").read_text())
    assert manifest["storage"] == {
        "mode": "explicit_user_waiver", "instruction": blind.AUTHORIZED_STORAGE_WAIVER
    }
    assert manifest["target_sha256"] == blind._sha(trial / "target.dll")
    assert (trial / "target.dll").stat().st_mode & 0o222 == 0


def test_trial_profile_denies_network_and_target_write(tmp_path):
    workspace = tmp_path / "trial"
    workspace.mkdir()
    target = workspace / "target.dll"
    target.write_bytes(b"x")
    profile = blind.make_profile(workspace, tmp_path / "prefix", Path(sys.executable), target,
                                 [str(Path(sys.prefix).resolve())])
    assert "(deny default)" in profile
    assert "network" not in profile.lower()
    assert f'(deny file-write* (literal "{target}"))' in profile
    assert f'(subpath "{workspace}")' in profile


def test_grader_profile_only_allows_tmp_writes(tmp_path):
    workspace = tmp_path / "grade"
    workspace.mkdir()
    profile = blind.sandbox_profile(workspace, tmp_path / "runtime", [tmp_path / "readonly"])
    writable_tmp = workspace / "tmp"
    assert "(deny default)" in profile
    assert f'(allow file-write* (subpath "{writable_tmp}")' in profile
    assert f'(subpath "{workspace}")' in profile  # reads only
    assert "(allow network" not in profile


def test_launch_requires_external_preflight_receipt(tmp_path, monkeypatch):
    trial = _prepared(tmp_path, monkeypatch)
    manifest_path = trial / "trial.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["state"] = "preflight_passed"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="preflight receipt missing"):
        blind.launch(trial)


def test_freezer_rejects_symlink_submission_and_frozen_copy_is_immutable(tmp_path):
    trial = tmp_path / "trial"
    trial.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("must not follow")
    (trial / "solver.py").symlink_to(outside)
    (trial / "REPORT.md").write_text("report")
    with pytest.raises(RuntimeError, match="must not be a symlink"):
        blind._freeze_submission(trial, tmp_path / "frozen-link")
    (trial / "solver.py").unlink()
    (trial / "solver.py").write_text("print('standalone')")
    frozen = tmp_path / "frozen-good"
    hashes = blind._freeze_submission(trial, frozen)
    assert set(hashes) == {"solver.py", "REPORT.md"}
    assert hashes["solver.py"] == blind._sha(frozen / "solver.py")
    assert frozen.joinpath("solver.py").stat().st_mode & 0o222 == 0


def test_event_audit_accepts_only_lab_tool_and_retains_model_usage(tmp_path):
    events = tmp_path / "events.jsonl"
    events.write_text("\n".join(json.dumps(event) for event in (
        {"type": "thread.started", "model": "inherited-selector"},
        {"type": "turn.completed", "usage": {"input_tokens": 7}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "normal model response"}},
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "lab", "tool_name": "run_command"}},
    )))
    tools = tmp_path / "tools.jsonl"
    tools.write_text(json.dumps({"call": 1, "tool": "lab.run_command"}) + "\n")
    result = blind._audit_events(events, tools)
    assert result["status"] == "pass"
    assert result["event_lab_run_command_calls"] == result["tool_receipt_calls"] == 1
    assert any("model" in event for event in result["selector_and_usage_events"])
    assert any("usage" in event for event in result["selector_and_usage_events"])


def test_event_audit_flags_native_tools_other_mcp_and_call_budget(tmp_path):
    events = tmp_path / "events.jsonl"
    events.write_text("\n".join(json.dumps(event) for event in (
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "web", "tool_name": "search"}},
        {"type": "item.completed", "item": {"type": "command_execution"}},
        {"type": "item.completed", "item": {"type": "file_change"}},
        {"type": "item.completed", "item": {"type": "agent_spawn"}},
    )))
    tools = tmp_path / "tools.jsonl"
    tools.write_text(json.dumps({"call": 49, "tool": "lab.run_command", "violation": "tool_call_budget_exceeded"}) + "\n")
    result = blind._audit_events(events, tools)
    assert result["status"] == "boundary_violation"
    kinds = {v["kind"] for v in result["violations"]}
    assert "other_or_unattributed_mcp_tool" in kinds
    assert "forbidden_native_or_external_tool" in kinds
    assert "forbidden_tool_category" in kinds
    assert "tool_call_budget_exceeded" in kinds


@pytest.mark.skipif(not blind._mac_sandbox_available(), reason="requires macOS sandbox-exec")
def test_os_profile_allows_workspace_reads_but_denies_outside_write_and_network(tmp_path):
    workspace = tmp_path / "trial"
    workspace.mkdir()
    (workspace / "tmp").mkdir()
    (workspace / "target.dll").write_bytes(b"immutable")
    outside = tmp_path / "secret.txt"
    outside.write_text("not visible")
    python = Path(sys.executable).resolve()
    python_roots = blind._python_read_paths(python)
    profile_path = tmp_path / "trial.sb"
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    fdisbull = prefix / "bin" / "fdisbull"
    fdisbull.write_text("#!/bin/sh\nprintf 'fdisbull test version\\n'\n")
    fdisbull.chmod(0o755)
    profile_path.write_text(blind.make_profile(workspace, prefix, python,
                                               workspace / "target.dll", python_roots))
    manifest = {"python": str(python), "fdisbull_prefix": str(prefix),
                "sandbox_profile": str(profile_path)}

    def run(code: str):
        return blind._run_sandboxed(workspace, manifest,
                                    f"{blind.shlex.quote(str(python))} -I -c {blind.shlex.quote(code)}", 5)

    assert run("from pathlib import Path; assert Path('target.dll').read_bytes() == b'immutable'").returncode == 0
    outside_probe = ("import errno; from pathlib import Path; "
                     f"\ntry: Path({str(outside)!r}).read_text()\n"
                     "except PermissionError as e: raise SystemExit(0 if e.errno in (errno.EPERM,errno.EACCES) else 18)\n"
                     "raise SystemExit(17)")
    write_probe = ("import errno; from pathlib import Path; "
                   "\ntry: Path('target.dll').write_bytes(b'changed')\n"
                   "except PermissionError as e: raise SystemExit(0 if e.errno in (errno.EPERM,errno.EACCES) else 18)\n"
                   "raise SystemExit(17)")
    network_probe = ("import errno,socket; "
                     "\ntry: s=socket.socket(); s.connect(('198.51.100.1',9))\n"
                     "except OSError as e: raise SystemExit(0 if e.errno in (errno.EPERM,errno.EACCES) else 18)\n"
                     "raise SystemExit(17)")
    assert run(outside_probe).returncode == 0
    assert run(write_probe).returncode == 0
    assert run(network_probe).returncode == 0
    assert blind._run_sandboxed(workspace, manifest, "fdisbull --version", 5).returncode == 0
    assert (workspace / "target.dll").read_bytes() == b"immutable"


def test_preflight_receipt_is_outside_agent_workspace_and_hides_probe_paths(tmp_path, monkeypatch):
    trial = _prepared(tmp_path, monkeypatch)
    denied = tmp_path / "private-source.py"
    denied.write_text("private fixture")

    commands = []

    def fake_run(_workspace, _manifest, command, _timeout):
        commands.append(command)
        return subprocess.CompletedProcess([], 0, b"fdisbull version test\n", b"")

    monkeypatch.setattr(blind, "_run_sandboxed", fake_run)
    receipt = blind.preflight(trial, denied_paths=[denied])
    receipt_path = trial.parent / f"{trial.name}.preflight.json"
    assert receipt_path.is_file() and not (trial / "preflight.json").exists()
    assert str(denied) not in receipt_path.read_text()
    assert receipt["budget_counted"] is False
    assert all(probe["passed"] for probe in receipt["probes"])
    assert any(command == "fdisbull --version" for command in commands)


@pytest.mark.skipif(not blind._mac_sandbox_available(), reason="requires macOS sandbox-exec")
def test_real_preflight_proves_denied_reads_write_network_and_tool_path(tmp_path, monkeypatch):
    trial = _prepared(tmp_path, monkeypatch)
    denied = tmp_path / "existing-private-input.py"
    denied.write_text("must remain inaccessible")
    receipt = blind.preflight(trial, denied_paths=[denied])
    assert receipt["state"] == "preflight_passed"
    assert receipt["budget_counted"] is False
    assert {probe["kind"] for probe in receipt["probes"]} >= {
        "outside_read_denied", "target_read_allowed", "target_write_denied",
        "network_denied", "fdisbull_runtime_ready",
    }
    assert all(probe["passed"] for probe in receipt["probes"])


def test_codex_command_inherits_model_selector_and_disables_other_tools(tmp_path, monkeypatch):
    trial = _prepared(tmp_path, monkeypatch)
    args = blind._codex_command(trial)
    assert "--model" not in args
    assert "--ignore-user-config" in args
    assert "--ignore-rules" in args
    assert 'approval_policy="never"' in args
    assert "--ephemeral" in args
    assert "features.shell_tool=false" in args
    assert "features.unified_exec=false" in args
    assert "features.apps=false" in args
    assert "features.multi_agent=false" in args
    assert "features.multi_agent_v2=false" in args
    assert "features.plugins=false" in args
    assert "features.remote_plugin=false" in args
    assert "features.plugin_discovery_prefetch=false" in args
    assert "features.skip_host_skill_discovery=true" in args
    assert 'web_search="disabled"' in args
    mcp_args = next(value for value in args if value.startswith("mcp_servers.lab.args="))
    mcp_command = next(value for value in args if value.startswith("mcp_servers.lab.command="))
    assert '"/usr/bin/env"' in mcp_command
    assert '"-i"' in mcp_args and "OPENAI_API_KEY" not in mcp_args and "CODEX_API_KEY" not in mcp_args
