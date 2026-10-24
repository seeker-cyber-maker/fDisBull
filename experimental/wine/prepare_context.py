"""Assemble only the explicit inputs for the Wine/DOSBox qualification image."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


WHEEL_SHA256 = "c8c877392e7f804cb9f14e344de2e55667cc928db5998f79c6b101f747a9e47b"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dosbox-source", required=True, type=Path,
                        help="Git checkout containing the pinned upstream commit")
    parser.add_argument("--wheel", required=True, type=Path,
                        help="Unmodified published fdisbull 0.11.0 wheel")
    parser.add_argument("--output", required=True, type=Path,
                        help="New, local build-context directory")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    source = args.dosbox_source.expanduser().resolve()
    wheel = args.wheel.expanduser().resolve()
    output = args.output.expanduser().resolve()
    patch_dir = root / "experimental/dosbox-x/layers"
    manifest = json.loads((patch_dir / "source-manifest.json").read_text())
    if wheel.name != "fdisbull-0.11.0-py3-none-any.whl" or sha256(wheel) != WHEEL_SHA256:
        raise SystemExit("Expected the unmodified, published 0.11.0 wheel")
    if sha256(patch_dir / "headless-agent.patch") != manifest["patch_sha256"]:
        raise SystemExit("DOSBox patch does not match its declared manifest")
    subprocess.run(["git", "-C", str(source), "cat-file", "-e",
                    manifest["baseline_commit"] + "^{commit}"], check=True)
    output.mkdir(parents=True, exist_ok=False)
    copies = {
        "Containerfile": root / "experimental/wine/Containerfile",
        "probe.sh": root / "experimental/wine/probes/probe.sh",
        "target64.c": root / "experimental/wine/probes/target64.c",
        "controller64.c": root / "experimental/wine/probes/controller64.c",
        "headless-agent.patch": patch_dir / "headless-agent.patch",
        "source-manifest.json": patch_dir / "source-manifest.json",
        wheel.name: wheel,
    }
    for name in ("conftest.py", "test_dos_loader.py", "test_debugger.py",
                 "test_code_layers.py", "test_screenshot_grid.py"):
        copies["tests/" + name] = root / "tests" / name
    for name, path in copies.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    # Archive the named commit, never the working tree or any local game files.
    with (output / "dosbox-source.tar").open("wb") as stream:
        subprocess.run(["git", "-C", str(source), "archive", "--format=tar",
                        "--prefix=dosbox-x/", manifest["baseline_commit"]],
                       stdout=stream, check=True)
    receipt = {
        "source_commit": subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
        "dosbox_upstream_commit": manifest["baseline_commit"],
        "inputs": {str(path.relative_to(output)): sha256(path)
                   for path in sorted(output.rglob("*")) if path.is_file()},
    }
    (output / "context-inputs.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
