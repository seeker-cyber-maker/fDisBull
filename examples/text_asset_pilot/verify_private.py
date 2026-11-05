#!/usr/bin/env python3
"""Two-process, bounded acceptance against the shipped word16 reference.

This isolates the new packaging/provider seam, not original interpreter fidelity.
The recovery stage exits before product subprocesses start: a full conservative
IR graph is large and must not be retained by the product-test process owner.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from asset_package import Package, canonical, private_output, sha
from pilot import AssetRuntime, bundle_program, cook_zipapp


def prepare(story, commands_file, output):
    from fdisbull.zork_uil import compile_story
    from fdisbull_player.word16 import Word16Runtime
    root = private_output(output)
    root.mkdir()
    commands = json.loads(commands_file.read_text())
    if not isinstance(commands, list) or not 2 <= len(commands) <= 1000 or any(type(c) is not str for c in commands):
        raise ValueError("expected 2..1000 command strings")
    started = time.monotonic()
    before = sha(story.read_bytes())
    program, _ = compile_story(story)
    data, normalization = bundle_program(program)
    assert data == bundle_program(program)[0], "nondeterministic bundle"
    (root / "zork-text.bundle").write_bytes(data)
    pkg = Package(data)
    baseline, asset = Word16Runtime(program, seed=12), AssetRuntime(pkg, seed=12)
    assert baseline.run() == asset.run(), "initial output mismatch"
    assert baseline.snapshot() == asset.snapshot(), "initial state mismatch"
    observations = []
    for i, command in enumerate(commands):
        expected, actual = baseline.command(command), asset.command(command)
        assert actual == expected, f"turn output/event mismatch at {i}"
        assert asset.snapshot() == baseline.snapshot(), f"full state mismatch at {i}"
        observations.append({"step": i, "command": command, "state_sha256": sha(canonical(asset.snapshot())),
                             "turn_sha256": sha(canonical(actual)), "status": actual["status"]})
    (root / "commands.json").write_bytes(canonical(commands))
    artifacts = {}
    for name in ("terminal", "jsonl"):
        app, receipt = cook_zipapp(data, name)
        assert app == cook_zipapp(data, name)[0], "nondeterministic target cook"
        path = root / ("zork-" + name + ".pyz")
        path.write_bytes(app)
        path.chmod(0o755)
        (root / ("cook-" + name + ".json")).write_bytes(canonical(receipt))
        artifacts[name] = {"sha256": receipt["artifact_sha256"], "bytes": receipt["artifact_bytes"],
                           "link_sha256": receipt["link"]["link_sha256"]}
    assert sha(story.read_bytes()) == before, "source mutated"
    receipt = {"format": "fdisbull-text-assets-acceptance-1",
               "comparison": "shipped word16 baseline versus asset-provider and cooked products",
               "independent_original_runtime": "not-run", "source": program["source"],
               "commands": len(commands), "matched_output_and_full_state_boundaries": len(commands) + 1,
               "normalization": normalization, "package_sha256": pkg.digest,
               "package_bytes": len(data), "asset_count": len(pkg.manifest["assets"]),
               "blob_count": len(pkg.blobs), "expected_state_sha256": sha(canonical(baseline.snapshot())),
               "checks": {"deterministic_package": True, "deterministic_cooked_apps": True,
                          "full_state_equality": True, "original_file_unchanged": True},
               "artifacts": artifacts, "recovery_seconds": round(time.monotonic() - started, 3)}
    (root / "private-step-hashes.json").write_bytes(canonical(observations))
    (root / "prepared.json").write_bytes(canonical(receipt))
    print(json.dumps({"stage": "prepared", "boundaries": len(commands) + 1, "seconds": receipt["recovery_seconds"]}))


def products(root):
    started = time.monotonic()
    receipt = json.loads((root / "prepared.json").read_text())
    commands = json.loads((root / "commands.json").read_text())
    for name in ("terminal", "jsonl"):
        path = root / ("zork-" + name + ".pyz")
        assert sha(path.read_bytes()) == receipt["artifacts"][name]["sha256"]
        result = subprocess.run([sys.executable, "-I", str(path), "--commands", str(root / "commands.json"),
                                 "--transcript", str(root / (name + "-transcript.json")),
                                 "--metrics", str(root / (name + "-metrics.json"))],
                                capture_output=True, timeout=90, cwd=root)
        assert result.returncode == 0, result.stderr.decode()[:1000]
        (root / (name + "-stdout.txt")).write_bytes(result.stdout)
        (root / (name + "-stderr.txt")).write_bytes(result.stderr)
    assert (root / "terminal-transcript.json").read_bytes() == (root / "jsonl-transcript.json").read_bytes()
    t = json.loads((root / "terminal-metrics.json").read_text())
    j = json.loads((root / "jsonl-metrics.json").read_text())
    assert t["state_sha256"] == j["state_sha256"] == receipt["expected_state_sha256"]
    split = len(commands) // 2
    (root / "prefix.json").write_bytes(canonical(commands[:split]))
    (root / "suffix.json").write_bytes(canonical(commands[split:]))
    save = root / "cross-shell-state.json"
    first = subprocess.run([sys.executable, "-I", str(root / "zork-terminal.pyz"),
                            "--commands", str(root / "prefix.json"), "--checkpoint", str(save)],
                           capture_output=True, timeout=90, cwd=root)
    assert first.returncode == 0, first.stderr.decode()[:1000]
    second = subprocess.run([sys.executable, "-I", str(root / "zork-jsonl.pyz"), "--resume", str(save),
                             "--commands", str(root / "suffix.json"), "--metrics", str(root / "resumed-metrics.json")],
                            capture_output=True, timeout=90, cwd=root)
    assert second.returncode == 0, second.stderr.decode()[:1000]
    resumed = json.loads((root / "resumed-metrics.json").read_text())
    assert resumed["state_sha256"] == t["state_sha256"]
    receipt["checks"].update(shell_transcript_equality=True, cross_shell_fresh_process_restore=True,
                              isolated_python_processes=True)
    receipt["metrics"] = t
    receipt["product_verification_seconds"] = round(time.monotonic() - started, 3)
    (root / "acceptance.json").write_bytes(canonical(receipt))
    print(json.dumps(receipt, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="stage", required=True)
    a = sub.add_parser("prepare")
    a.add_argument("story", type=Path)
    a.add_argument("commands", type=Path)
    a.add_argument("output", type=Path)
    b = sub.add_parser("products")
    b.add_argument("output", type=Path)
    args = ap.parse_args()
    if args.stage == "prepare": prepare(args.story, args.commands, args.output)
    else: products(args.output.resolve())


if __name__ == "__main__":
    main()
