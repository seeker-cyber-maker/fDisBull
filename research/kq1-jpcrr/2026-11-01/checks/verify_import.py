"""Check this sanitized import without launching Java, a guest, or a capture."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-root", type=Path, required=True,
                        help="Private original extraction, used only for witness correspondence")
    args = parser.parse_args()
    source = args.original_root / "tools/route_support.py"
    manifest = json.loads((ROOT / "provenance/import-manifest.json").read_text())
    original = next(row for row in manifest["archive_members"]
                    if row["source_path"] == "tools/route_support.py")
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original["sha256"]
    tree = ast.parse(source.read_text())
    assignment = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "ACTOR_LAYOUT_EVIDENCE"
                              for target in node.targets))
    # literal_eval reads the two constant witness lists; no original code executes.
    rows = {key.value: ast.literal_eval(value)
            for key, value in zip(assignment.keys, assignment.values)
            if isinstance(key, ast.Constant) and key.value in ("dispatch", "code")}
    support = load("sanitized_route_support", ROOT / "tools/route_support.py")
    evidence = support.ACTOR_LAYOUT_EVIDENCE
    ram = bytearray(0xA0000)
    cs_base, ds_base = 0x10000, 0x20000
    witnesses = []
    for group in ("dispatch", "code"):
        assert len(rows[group]) == len(evidence[group])
        for old, new in zip(rows[group], evidence[group]):
            raw = bytes.fromhex(old["bytes"])
            assert new["length"] == len(raw)
            assert new["sha256"] == hashlib.sha256(raw).hexdigest()
            assert "bytes" not in new
            address = (ds_base + evidence["dispatch_offset"] + evidence["dispatch_stride"] * old["opcode"]
                       if group == "dispatch" else cs_base + old["offset"])
            ram[address:address + len(raw)] = raw
            witnesses.append((address, len(raw)))
    def check(value):
        result = support.verify_native_actor_layout(value, cs_base=cs_base, ds_base=ds_base)
        assert all("expected" not in row and "observed" not in row for row in result["checks"])
        return result
    for value in (ram, bytes(ram), memoryview(ram)):
        result = check(value)
        assert result["complete"] and len(result["checks"]) == 43
        assert all(row["match"] for row in result["checks"])
    for address, _ in witnesses:
        ram[address] ^= 1
        result = check(ram)
        assert not result["complete"]
        assert sum(not row["match"] for row in result["checks"]) == 1
        ram[address] ^= 1
    truncated = check(ram[:max(address + length for address, length in witnesses) - 1])
    assert not truncated["complete"]
    assert any(row["observed_sha256"] is None for row in truncated["checks"])
    assert not support.verify_native_actor_layout(ram, cs_base=-0xA0000, ds_base=ds_base)["complete"]

    audit = load("sanitized_movie_audit", ROOT / "tools/audit_movie.py")
    movie_results = []
    reference = args.original_root / "provenance/reference-original-bios.jrsr"
    for movie in sorted((ROOT / "movies").glob("*.jrsr")):
        result = audit.audit_movie(movie, reference)
        assert result["ok"] and not result["held_keys_at_end"]
        assert result["power_on_structure"]["no_embedded_savestate_or_manifest"]
        assert result["boot_prefix"]["unchanged_keyboard_events"]
        movie_results.append({"movie": movie.name, "ok": result["ok"],
                              "keyboard_edges": result["keyboard_edge_count"],
                              "sha256": result["movie_sha256"]})

    def command(script, *arguments):
        return subprocess.run([sys.executable, "-B", str(ROOT / "tools" / script), *arguments],
                              text=True, capture_output=True)
    for script in ("replay_batch.py", "scan_landmarks.py", "run_stock_replay.py", "audit_movie.py"):
        assert command(script, "--help").returncode == 0
    assert command("scan_landmarks.py", "private.jmd", "--out", "private-output").returncode == 2
    destination = ROOT / "checks/dry-run-must-not-create"
    assert not destination.exists()
    dry = command("replay_batch.py", "--jar", "private.jar", "--library", "private-library",
                  "--out", str(destination), "--dry-run")
    assert dry.returncode == 0 and not destination.exists(), dry.stderr
    jobs = [json.loads(line) for line in dry.stdout.splitlines()]
    assert len(jobs) == 4 and all(job["event"] == "dry_run" for job in jobs)
    for job in jobs:
        cmd = job["command"]
        assert Path(cmd[1]) == ROOT / "tools/run_stock_replay.py"
        assert Path(cmd[cmd.index("--movie") + 1]).parent == ROOT / "movies"
    assert command("replay_batch.py", "--jar", "private.jar", "--library", "private-library",
                   "--out", str(destination), "--stop-ns", "0", "--dry-run").returncode == 2
    assert command("replay_batch.py", "--jar", "private.jar", "--library", "private-library",
                   "--out", str(ROOT / "checks"), "--dry-run").returncode == 2
    for path in ROOT.rglob("*.py"):
        ast.parse(path.read_text())
    for row in manifest["archive_members"]:
        if row["import_path"]:
            path = ROOT / row["import_path"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row["import_sha256"]
    implementation = [ROOT / "tools" / name for name in
                      ("route_support.py", "scan_landmarks.py", "replay_batch.py")]
    implementation.append(Path(__file__).resolve())
    print(json.dumps({"ok": True, "platform": platform.system(), "python": platform.python_version(),
                      "implementation_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                                for path in implementation},
                      "witnesses": len(witnesses), "mutated_witness_refusals": len(witnesses),
                      "memory_input_types": 3, "truncated_and_negative_base_refused": True,
                      "movies": movie_results, "cli_help_checks": 4,
                      "batch_dry_run_jobs": len(jobs), "guest_launches": 0,
                      "all_import_hashes_match_manifest": True}, indent=2))


if __name__ == "__main__":
    main()
