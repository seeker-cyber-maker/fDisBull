#!/usr/bin/env python3
"""Check built archives for tool-only contents and complete test-source helpers."""

from __future__ import annotations

import argparse
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
import tarfile
import zipfile

EXCLUDED_DIRECTORIES = {"examples", "history", "experimental", "build", "dist", ".git", "__pycache__"}
EXCLUDED_SUFFIXES = {".fdb", ".db", ".sqlite", ".sqlite3", ".sav", ".state", ".exe", ".com", ".dll", ".bin", ".dat", ".so", ".dylib", ".o", ".pyc"}
PLAYER_MODULES = {"__init__.py", "__main__.py", "player.py", "runtime.py", "live.py", "word16.py",
                  "game_intents.py", "intent_runtime.py", "batch.py"}
REQUIRED_PLAYER_SOURCE = {"player/pyproject.toml"} | {"player/fdisbull_player/" + name for name in PLAYER_MODULES}
REQUIRED_TEST_HELPERS = {"tests/fixtures_formats.py", "tests/fixtures_macho.py", "tests/ida_rpc_vectors.json", "tests/dosbox_zip_empty_write.cpp"}
REQUIRED_TEST_HELPERS.add("tests/fixtures_z_scenes.py")
REQUIRED_SOURCE_EVIDENCE = {"docs/evidence/output-024/" + name for name in
                            ("amplification.json", "dinopark-native.json", "dinopark-output.json", "tests.json")}
REQUIRED_SOURCE_EVIDENCE.add("docs/evidence/source-search-pilot/verification.json")
REQUIRED_SOURCE_EVIDENCE.add("docs/evidence/civd-source-maps/verification.json")
REQUIRED_SOURCE_EVIDENCE |= {"docs/evidence/civd-food-swaps/" + name for name in
                             ("verification.json","shared-uil.json","source-ui-inventory.json")}
REQUIRED_SOURCE_EVIDENCE |= {"docs/evidence/scene-recovery-2026-10-29/" + name for name in
                           ("representation-paths.json", "scene-pipeline-summary.json")}
REQUIRED_SOURCE_EVIDENCE |= {"docs/evidence/integration-025/" + name for name in
                           ("zork.json", "dinopark.json", "tests.json", "packages.json")}
REQUIRED_SOURCE_EVIDENCE |= {"docs/uil-rfcs/0002/" + name for name in
                           ("vectors.json", "replay-summary.json")}
REQUIRED_SOURCE_EVIDENCE.add("docs/evidence/integration-026/verification.json")
REQUIRED_SOURCE_EVIDENCE.add("docs/evidence/civd-food-arm64/verification.json")
REVIEWED_SOURCE_RECIPES = {'examples/recovery/civd_food_arm64.py', 'examples/recovery/civd_food_swap.py'}
REVIEWED_SOURCE_RECIPES |= {'examples/recovery/civd_food_web.py','examples/recovery/run_web_blocks.mjs'}
REVIEWED_SOURCE_RECIPES.add('examples/recovery/run_web_browser.mjs')
REVIEWED_SOURCE_RECIPES |= {'examples/recovery/civd_browser_shell.py',
    'examples/recovery/web_shell_study.mjs','examples/recovery/run_browser_shell.mjs'}
REQUIRED_SOURCE_EVIDENCE |= REVIEWED_SOURCE_RECIPES
REQUIRED_SOURCE_EVIDENCE.add('docs/evidence/civd-food-web/verification.json')
REQUIRED_SOURCE_EVIDENCE |= {'docs/evidence/civd-browser-shell/verification.json','tests/web_shell_checks.mjs'}
REQUIRED_PE_RESOURCES = {"wine_guest/agent.c", "wine_guest/init.sh", "wine_guest/broker.py", "wine_guest/selftest.c"}
REQUIRED_PE_RESOURCES |= {"ida_guest/ui.c", "ida_guest/init.sh", "ida_guest/broker.py", "ida_guest/SDK-LICENSE.txt", "ida_wire.py", "ida_remote.py", "ida_trace.py"}
REQUIRED_PE_RESOURCES |= {"dos_guest/__init__.py", "dos_guest/init.sh", "dos_guest/broker.py", "dos_qemu.py", "dos_runtime.py", "qemu_machine.py", "gdb_rpc.py", "guest_assets.py"}
REQUIRED_KNOWLEDGE_RESOURCES = {"data/dos-runtime-signatures.json", "data/MICROSOFT-DOS-LICENSE.txt"}
REQUIRED_KNOWLEDGE_RESOURCES.add("data/civd-z-screen-families.json")
REQUIRED_KNOWLEDGE_RESOURCES.add('web_runtime/block.mjs')
REQUIRED_KNOWLEDGE_RESOURCES |= {'web_runtime/shell.mjs','web_runtime/app.mjs','web_runtime/index.html'}
REQUIRED_KNOWLEDGE_RESOURCES |= {"skills/fdisbull-investigate/SKILL.md", "skills/fdisbull-investigate/references/scenes.md",
                                 "skills/fdisbull-investigate/references/methodology.md",
                                 "skills/fdisbull-investigate/references/reconstruction.md",
                                 "skills/fdisbull-investigate/references/sweding.md",
                                 "skills/fdisbull-investigate/references/runtime-navigation.md",
                                 "skills/fdisbull-investigate/references/proofs.md",
                                 "skills/fdisbull-investigate/references/workflows.md",
                                 "skills/fdisbull-investigate/references/recovery-research.md",
                                 "skills/fdisbull-investigate/references/semantic-contracts.md",
                                 "skills/fdisbull-investigate/references/formats-and-media.md",
                                 "skills/fdisbull-investigate/references/udl-uil-udc.md"}
REQUIRED_KNOWLEDGE_RESOURCES |= {
    "skills/write-gamefaqs-guide/SKILL.md",
    "skills/write-gamefaqs-guide/references/evidence-and-provenance.md",
    "skills/write-gamefaqs-guide/references/guide-structure.md",
    "skills/write-gamefaqs-guide/references/technical-mechanics.md",
    "skills/write-gamefaqs-guide/references/source-examples.md",
}


def archive_names(path: Path) -> list[str]:
    if path.suffix in {".whl", ".zip"}:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError(f"Corrupt ZIP: {path}")
            return [item.filename for item in archive.infolist() if not item.is_dir()]
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
            if any(item.issym() or item.islnk() for item in members):
                raise ValueError(f"Source archive contains links: {path}")
            return [item.name for item in members if item.isfile()]
    raise ValueError(f"Unsupported distribution archive: {path}")


def check_archive(path: Path) -> int:
    names = archive_names(path)
    if not names:
        raise ValueError(f"Empty archive: {path}")
    entries = [PurePosixPath(name) for name in names]
    for entry in entries:
        if entry.is_absolute() or ".." in entry.parts:
            raise ValueError(f"Invalid archive path: {entry}")
        excluded = EXCLUDED_DIRECTORIES.intersection(entry.parts)
        relative = PurePosixPath(*entry.parts[1:]).as_posix()
        reviewed_recipe = (path.suffix != ".whl" and excluded == {"examples"}
                           and relative in REVIEWED_SOURCE_RECIPES)
        if excluded and not reviewed_recipe:
            raise ValueError(f"Excluded directory in {path.name}: {entry}")
        if entry.suffix.lower() in EXCLUDED_SUFFIXES or ".fdb-" in entry.name.lower():
            raise ValueError(f"Excluded binary/data file in {path.name}: {entry}")
    if path.suffix == ".whl":
        roots = {entry.parts[0] for entry in entries}
        player_metadata = {name for name in roots if name.startswith("fdisbull_player-") and name.endswith(".dist-info")}
        core_metadata = {name for name in roots if name.startswith("fdisbull-") and name.endswith(".dist-info")}
        if len(player_metadata) == 1 and roots == {"fdisbull_player", *player_metadata}:
            metadata = next(iter(player_metadata))
            expected = {"fdisbull_player/" + name for name in PLAYER_MODULES}
            package_files = {name for name in names if name.startswith("fdisbull_player/")}
            if package_files != expected:
                raise ValueError(f"Player wheel has missing or unexpected modules: {sorted(expected ^ package_files)}")
            with zipfile.ZipFile(path) as archive:
                try: message = BytesParser().parsebytes(archive.read(metadata + "/METADATA"))
                except KeyError: raise ValueError("Player wheel is missing METADATA") from None
            if message.get("Name", "").lower().replace("_", "-") != "fdisbull-player":
                raise ValueError("Player wheel distribution metadata has wrong Name")
        elif len(core_metadata) == 1 and roots == {"fdisbull", *core_metadata}:
            if "fdisbull/__init__.py" not in names:
                raise ValueError("Wheel is missing fdisbull/__init__.py")
            missing = {"fdisbull/" + name for name in REQUIRED_PE_RESOURCES} - set(names)
            if missing:
                raise ValueError(f"Wheel is missing PE backend sources: {sorted(missing)}")
            missing={"fdisbull/"+name for name in REQUIRED_KNOWLEDGE_RESOURCES}-set(names)
            if missing:raise ValueError(f"Wheel is missing DOS analysis resources: {sorted(missing)}")
        else:
            raise ValueError(f"Wheel contains unexpected package or metadata roots: {sorted(roots)}")
    else:
        roots = {entry.parts[0] for entry in entries}
        if len(roots) != 1 or not next(iter(roots)).startswith("fdisbull-"):
            raise ValueError(f"Unexpected source archive root: {sorted(roots)}")
        relative = {PurePosixPath(*entry.parts[1:]).as_posix() for entry in entries}
        required = REQUIRED_TEST_HELPERS | REQUIRED_PLAYER_SOURCE | {"src/fdisbull/__init__.py", "pyproject.toml", "tests/wine_gui_fixture.c"}
        required |= {"src/fdisbull/" + name for name in REQUIRED_PE_RESOURCES}
        required |= {"src/fdisbull/" + name for name in REQUIRED_KNOWLEDGE_RESOURCES}
        required |= {"AGENTS.md", "CLAUDE.md", "docs/AGENT_QUICKSTART.md"}
        required |= {"scripts/check_agent_skill.py"}
        required |= REQUIRED_SOURCE_EVIDENCE
        missing = required - relative
        if missing:
            raise ValueError(f"Source archive is missing required files: {sorted(missing)}")
    return len(names)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="*", type=Path)
    args = parser.parse_args()
    archives = args.archives or sorted(
        path for path in (Path(__file__).resolve().parents[1] / "dist").glob("*")
        if path.suffix in {".whl", ".zip"} or path.name.endswith(".tar.gz")
    )
    if not archives:
        parser.error("No distribution archives found; build them first")
    for path in archives:
        print(f"OK {path.name}: {check_archive(path)} tool-only entries")


if __name__ == "__main__":
    main()
