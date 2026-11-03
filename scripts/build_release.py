#!/usr/bin/env python3
"""Build the tool-only source ZIP from an explicit set of source directories."""

from __future__ import annotations

import argparse
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = ("README.md", "AGENTS.md", "CLAUDE.md", "pyproject.toml", "MANIFEST.in", "player/pyproject.toml")
DOC_EXAMPLE_FILES = (
    "docs/CLOUD-0.27.0-MANIFEST.json",
    "docs/uil-rfcs/0001/README.md",
    "docs/uil-rfcs/0001/check_examples.py",
    "docs/uil-rfcs/0001/commit.js",
    "docs/uil-rfcs/0001/commit.py",
    "docs/uil-rfcs/0001/commit.rs",
    "docs/uil-rfcs/0001/native-observation.json",
    "docs/uil-rfcs/0001/native_probe.py",
    "docs/uil-rfcs/0001/source-definition-observation.json",
    "docs/uil-rfcs/0001/vectors.json",
    "docs/uil-rfcs/0002/vectors.json",
    "docs/uil-rfcs/0002/replay-summary.json",
)
SOURCE_PATTERNS = (
    ("src/fdisbull/native_runtime", "*.c"),
    ("src/fdisbull/native_runtime", "*.h"),
    ("src/fdisbull/native_runtime", "*.m"),
    ("src/fdisbull/web_runtime", "*.mjs"),
    ("src/fdisbull/web_runtime", "*.html"),
    ("docs/evidence/common-uil-2026-11-01", "verification.json"),
    ("docs/evidence/common-uil-native-2026-11-01", "verification.json"),
    ("docs/evidence/common-uil-desktop-2026-11-01", "verification.json"),
    ("docs/evidence/source-search-pilot", "verification.json"),
    ("docs/evidence/civd-source-maps", "verification.json"),
    ("docs/evidence/civd-food-swaps", "verification.json"),
    ("docs/evidence/civd-food-swaps", "shared-uil.json"),
    ("docs/evidence/civd-food-swaps", "source-ui-inventory.json"),
    ("src/fdisbull", "*.py"),
    ("player/fdisbull_player", "*.py"),
    ("src/fdisbull/data", "*.json"),
    ("src/fdisbull/data", "*.txt"),
    ("src/fdisbull/data", "*.swift"),
    ("src/fdisbull/skills", "*.md"),
    ("src/fdisbull/wine_guest", "*.c"),
    ("src/fdisbull/wine_guest", "*.sh"),
    ("src/fdisbull/ida_guest", "*.c"),
    ("src/fdisbull/ida_guest", "*.sh"),
    ("src/fdisbull/ida_guest", "SDK-LICENSE.txt"),
    ("src/fdisbull/dos_guest", "*.sh"),
    ("src/fdisbull/ghidra_scripts", "*.java"),
    ("src/fdisbull/game_sources", "*.c"),
    ("src/fdisbull/game_sources", "*.m"),
    ("src/fdisbull/game_sources", "*.s"),
    ("src/fdisbull/game_sources", "*.S"),
    ("src/fdisbull/game_sources", "*.cfg"),
    ("src/fdisbull/game_sources", "LICENSE.txt"),
    ("tests", "*.py"),
    ("tests", "wine_gui_fixture.c"),
    ("tests", "dosbox_zip_empty_write.cpp"),
    ("tests", "ida_rpc_vectors.json"),
    ("tests", "rom_asm_sh2_vectors.json"),
    ("docs", "*.md"),
    ("docs/evidence/spatial-2026-10-29", "verification.json"),
    ("docs/evidence/zork-2026-10-29", "verification.json"),
    ("docs/evidence/zork-uil-2026-10-29", "verification.json"),
    ("docs/evidence/zork-intents-2026-10-29", "verification.json"),
    ("docs/evidence/scene-recovery-2026-10-29", "representation-paths.json"),
    ("docs/evidence/scene-recovery-2026-10-29", "scene-pipeline-summary.json"),
    ("docs/evidence/zmachine-processor-2026-10-29", "verification.json"),
    ("docs/evidence/udc-2026-10-29", "dino.json"),
    ("docs/evidence/udc-2026-10-29", "zork.json"),
    ("docs/evidence/udc-2026-10-29", "synthetic.json"),
    ("docs/evidence/output-024", "amplification.json"),
    ("docs/evidence/output-024", "dinopark-native.json"),
    ("docs/evidence/output-024", "dinopark-output.json"),
    ("docs/evidence/output-024", "tests.json"),
    ("docs/evidence/integration-025", "zork.json"),
    ("docs/evidence/integration-025", "dinopark.json"),
    ("docs/evidence/integration-025", "tests.json"),
    ("docs/evidence/integration-025", "packages.json"),
    ("docs/evidence/integration-026", "verification.json"),
    ("docs/evidence/integration-0261", "verification.json"),
    ("docs/evidence/rom-asm-2026-10-30", "benchmark.json"),
    ("docs/evidence/rom-asm-2026-10-30", "accuracy.json"),
    ("docs/evidence/rom-asm-2026-10-30", "benchmark-persistent.json"),
    ("docs/evidence/rom-asm-2026-10-30", "capstone-profile.json"),
    ("docs/evidence/rom-asm-2026-10-30", "decoder-census.json"),
    ("docs/evidence/rom-asm-2026-10-30", "semantic-route.json"),
    ("docs/evidence/console-udc-2026-10-30", "verification.json"),
    ("docs/evidence/genesis-rom-route-2026-10-30", "verification.json"),
    ("docs/evidence/miniplanets-nes-level-2026-10-31", "verification.json"),
    ("docs/evidence/miniplanets-full-game-2026-10-31", "*.json"),
    ("docs/evidence/nes-multicart-2026-10-31", "verification.json"),
    ("docs/evidence/console-intake-2026-10-31", "intake.json"),
    ("docs/evidence/mario-minus-world-2026-11-01", "*.json"),
    ("docs/evidence/shadowrun-uil-2026-11-01", "*.json"),
    ("docs/evidence/shadowrun-full-2026-11-01", "*.json"),
    ("docs/evidence", "shadowrun-assisted-original-b-target.json"),
    ("docs/evidence/shadowrun-play-2026-11-01", "*.json"),
    ("docs/evidence/shadowrun-ai-2026-11-01", "*.json"),
    ("docs/evidence/shadowrun-macos-2026-11-01", "verification.json"),
    ("docs/evidence/shadowrun-extended-2026-11-01", "*.json"),
    ("patches", "capstone-5.0.9-sh-profile-gating.patch"),
    ("scripts/rom_semantic_route", "*.java"),
    ("scripts/rom_semantic_route", "README.md"),
    ("docs/evidence/agi-scenes-2026-10-30", "verification.json"),
    ("docs/evidence/kq1-bow-2026-10-30", "verification.json"),    ("scripts", "*.py"),
    ("scripts", "miniplanets_display_observer.c"),
    ("docs/evidence/civd-browser-shell", "verification.json"),
    ("docs/evidence/civd-food-arm64", "verification.json"),
    ("docs/evidence/civd-food-web", "verification.json"),
    ("docs/evidence/snake-browser", "verification.json"),
    ("docs/verification", "kq1-tas-2026-10-31.json"),
    ("examples/recovery", "civd_food_swap.py"),
    ("examples/recovery", "civd_food_arm64.py"),
    ("examples/recovery", "civd_food_web.py"),
    ("examples/recovery", "run_web_blocks.mjs"),
    ("examples/recovery", "run_web_browser.mjs"),
    ("examples/recovery", "civd_browser_shell.py"),
    ("examples/recovery", "web_shell_study.mjs"),
    ("examples/recovery", "run_browser_shell.mjs"),
    ("examples/recovery", "snake_model.py"),
    ("examples/recovery", "snake_original.py"),
    ("examples/recovery", "snake_browser.py"),
    ("examples/recovery", "run_snake_browser.mjs"),
    ("examples/recovery", "snake_browser_study.mjs"),
    ("examples/recovery", "prepare_snake_rng_study.py"),
    ("examples/recovery", "snake_rng_study.mjs"),
    ("examples/recovery", "run_snake_rng_switch.mjs"),
    ("examples/recovery", "snake_macos.py"),
    ("examples/recovery", "verify_snake_macos.py"),
    ("examples/recovery", "verify_snake_appkit.py"),
    ("examples/recovery", "snake_desktop.py"),
    ("examples/recovery", "verify_snake_desktop.py"),
    ("tests/fixtures", "frame_capture.S"),
    ("tests", "macos_capture_fixture.swift"),
    ("tests", "memory_shell_checks.mjs"),
    ("tests", "web_shell_checks.mjs"),
)


def release_files(root: Path) -> list[Path]:
    """Select tool sources plus the exact authored RFC fixture allowlist."""
    files = [root / name for name in (*ROOT_FILES, *DOC_EXAMPLE_FILES)]
    for directory, pattern in SOURCE_PATTERNS:
        candidates = ((root / directory).glob(pattern) if directory == "player/fdisbull_player"
                      else (root / directory).rglob(pattern))
        if directory == "docs":
            fixture_root = root / "docs/uil-rfcs/0001"
            files.extend(path for path in candidates if fixture_root not in path.parents)
        else:
            files.extend(candidates)
    selected = []
    for path in sorted(set(files)):
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Release input must be a regular file: {path}")
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts:
            continue
        selected.append(path)
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    files = release_files(ROOT)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    destination = args.output_dir / f"fdisbull-{version}-tool.zip"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, f"fdisbull-{version}/{path.relative_to(ROOT).as_posix()}")
    print(f"Built {destination} ({len(files)} source files)")


if __name__ == "__main__":
    main()
