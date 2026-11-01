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
EXCLUDED_SUFFIXES |= {".nes", ".rom", ".gen", ".smd", ".iso", ".cue", ".wav", ".pcm",
                      ".lut", ".4bpp", ".slz", ".sona", ".swav", ".spat", ".tfi", ".chr"}
PLAYER_MODULES = {"__init__.py", "__main__.py", "player.py", "runtime.py", "live.py", "word16.py",
                  "game_intents.py", "intent_runtime.py", "batch.py"}
REQUIRED_PLAYER_SOURCE = {"player/pyproject.toml"} | {"player/fdisbull_player/" + name for name in PLAYER_MODULES}
REQUIRED_TEST_HELPERS = {"tests/fixtures_formats.py", "tests/fixtures_macho.py", "tests/ida_rpc_vectors.json", "tests/dosbox_zip_empty_write.cpp"}
REQUIRED_TEST_HELPERS.add("tests/fixtures_z_scenes.py")
REQUIRED_TEST_HELPERS |= {"tests/rom_asm_sh2_vectors.json", "tests/test_media_modules.py"}
REQUIRED_SOURCE_EVIDENCE = {"docs/evidence/output-024/" + name for name in
                            ("amplification.json", "dinopark-native.json", "dinopark-output.json", "tests.json")}
REQUIRED_SOURCE_EVIDENCE |= {"docs/evidence/scene-recovery-2026-10-29/" + name for name in
                           ("representation-paths.json", "scene-pipeline-summary.json")}
REQUIRED_SOURCE_EVIDENCE |= {"docs/evidence/integration-025/" + name for name in
                           ("zork.json", "dinopark.json", "tests.json", "packages.json")}
REQUIRED_SOURCE_EVIDENCE |= {"docs/uil-rfcs/0002/" + name for name in
                           ("vectors.json", "replay-summary.json")}
REQUIRED_SOURCE_EVIDENCE.add("docs/evidence/integration-026/verification.json")
REQUIRED_SOURCE_EVIDENCE.add("docs/evidence/integration-0261/verification.json")
REQUIRED_SOURCE_EVIDENCE |= {"docs/evidence/rom-asm-2026-10-30/benchmark.json", "docs/evidence/rom-asm-2026-10-30/accuracy.json"}
REQUIRED_SOURCE_EVIDENCE |= {"docs/evidence/rom-asm-2026-10-30/" + name for name in
                           ("benchmark-persistent.json", "capstone-profile.json", "decoder-census.json", "semantic-route.json")}
REQUIRED_TEST_HELPERS |= {"patches/capstone-5.0.9-sh-profile-gating.patch",
                         "scripts/rom_semantic_route/DecompileAuthoredSh2.java", "scripts/rom_semantic_route/README.md"}
REQUIRED_SOURCE_EVIDENCE.add("docs/evidence/console-udc-2026-10-30/verification.json")
REQUIRED_SOURCE_EVIDENCE.add("docs/evidence/genesis-rom-route-2026-10-30/verification.json")
REQUIRED_SOURCE_EVIDENCE.add("docs/evidence/miniplanets-nes-level-2026-10-31/verification.json")
REQUIRED_TEST_HELPERS |= {"scripts/check_miniplanets_native.py", "scripts/verify_miniplanets_level.py"}
REQUIRED_TEST_HELPERS |= {"scripts/probe_genesis_function.py", "scripts/verify_genesis_rom_route.py"}
REQUIRED_TEST_HELPERS |= {"scripts/check_console_udc.py", "scripts/check_miniplanets_common_native.py",
                         "scripts/check_miniplanets_full_flow.py", "scripts/check_miniplanets_audio.py",
                         "scripts/check_miniplanets_nes_game.py",
                         "scripts/check_miniplanets_nes_audio.py", "scripts/check_miniplanets_nes_timing.py",
                         "scripts/capture_miniplanets_audio.py", "scripts/check_nes_audio_clock.py",
                         "scripts/check_nes_mapper_atomic.py",
                         "scripts/check_native_array_offsets.py",
                         "scripts/check_miniplanets_audio_fast.py",
                         "scripts/check_miniplanets_globe_fast.py", "scripts/check_miniplanets_game_fast.py",
                         "scripts/check_miniplanets_actor_fast.py", "scripts/check_miniplanets_projection_pair.py",
                         "scripts/check_miniplanets_renderer_objects.py", "scripts/check_miniplanets_projection_cache.py",
                         "scripts/check_miniplanets_hud_fast.py", "scripts/check_miniplanets_sprite_fast.py",
                         "scripts/check_miniplanets_objects_native.py", "scripts/check_miniplanets_upload_plan.py",
                         "scripts/check_miniplanets_upload_stress.py", "scripts/check_miniplanets_nes_display.py",
                         "scripts/miniplanets_display_observer.c",
                         "scripts/check_miniplanets_terrain_cache.py", "scripts/check_miniplanets_terrain_cache_sequence.py",
                         "scripts/check_miniplanets_terrain_hints.py",
                         "scripts/check_miniplanets_sparse_hint.py", "scripts/check_miniplanets_terrain_clear.py",
                         "tests/test_game_il.py", "tests/test_miniplanets_full.py",
                         "tests/test_console_udc_host.py", "tests/test_miniplanets_globe_assets.py",
                         "tests/test_miniplanets_nes_game.py", "tests/test_nes_audio_clock.py",
                         "tests/test_miniplanets_nes_timing.py", "tests/test_miniplanets_source_capture.py",
                         "tests/test_nes_game_resources.py",
                         "tests/test_miniplanets_audio.py"}
REQUIRED_SOURCE_EVIDENCE |= {"docs/evidence/miniplanets-full-game-2026-10-31/" + name for name in
                            ("actors.json", "common.json", "reference-flow.json", "projection.json",
                             "audio-clock-verification.json", "audio-verification.json",
                             "phase-intrinsic.json", "array-offsets.json", "profile-r12.json", "domain.json",
                             "profile-r13.json", "bank-race.json", "audio-tempo-protocol-v2.json",
                             "normal-audio-tempo.json", "nes-verification.json",
                             "mapper-atomic-verification.json", "source-review.json",
                             "lowering-exploration.json")}
REQUIRED_SOURCE_EVIDENCE.add("docs/evidence/miniplanets-full-game-2026-10-31/optimization.json")
REQUIRED_SOURCE_EVIDENCE.add("docs/evidence/miniplanets-full-game-2026-10-31/display-optimization.json")
REQUIRED_SOURCE_EVIDENCE.add("docs/evidence/miniplanets-full-game-2026-10-31/uncapped-rendering.json")
REQUIRED_SOURCE_EVIDENCE.add("docs/evidence/miniplanets-full-game-2026-10-31/moving-optimization.json")
REQUIRED_SOURCE_EVIDENCE |= {"docs/MINIPLANETS_FULL_GAME.md",
                            "docs/evidence/miniplanets-full-game-2026-10-31/renderer-fast.json"}
REQUIRED_CONSOLE_RESOURCES = {"game_il.py", "miniplanets_audio.py", "udl_miniplanets_full.py",
                              "udc_nes_game.py", "data/miniplanets_full_contract.json"}
REQUIRED_CONSOLE_RESOURCES |= {"game_sources/" + name for name in
                              ("miniplanets_full.c", "miniplanets_actors.c", "miniplanets_audio_nes.c",
                               "nes_globe_renderer.c", "nes_game_platform.c", "nes_game_start.s", "nes_audio_clock.c",
                               "miniplanets_audio_fast.s", "nes_globe_fast.s", "nes_game_fast.s", "LICENSE.txt")}
REQUIRED_CONSOLE_RESOURCES.add("game_sources/nes_display_fast.s")
REQUIRED_CONSOLE_RESOURCES |= {
    "genesis_replay.py", "udc_genesis_game.py", "presentation_il.py", "psg_il.py",
    "data/miniplanets_presentation.uil.json", "data/miniplanets_psg.uil.json",
    "game_sources/miniplanets_presentation_uil.c", "game_sources/miniplanets_psg_uil.c",
    "game_sources/genesis_game_platform.c", "game_sources/genesis_game_start.s",
    "game_sources/genesis_game_renderer.c", "game_sources/genesis_game_audio.c",
    "game_sources/genesis_game_audio.S",
}
REQUIRED_SOURCE_EVIDENCE |= {
    "docs/GENESIS_UIL_REPLAY.md",
    "docs/evidence/miniplanets-full-game-2026-10-31/genesis-replay.json",
    "docs/evidence/miniplanets-full-game-2026-10-31/genesis-presentation.json",
}
REQUIRED_TEST_HELPERS |= {
    "scripts/check_genesis_game.py", "scripts/check_genesis_game_audio_source.py",
    "scripts/check_genesis_game_renderer.py", "scripts/check_genesis_vdp_presentation.py",
    "scripts/check_genesis_presentation.py",
    "scripts/check_miniplanets_psg_uil.py", "scripts/check_presentation_uil.py",
    "tests/test_genesis_replay.py", "tests/test_genesis_replay_targets.py",
    "tests/test_genesis_replay_review.py", "tests/test_udc_genesis_game.py",
    "tests/test_genesis_game_audio.py", "tests/test_presentation_il.py",
    "tests/test_psg_il.py",
}
REQUIRED_CONSOLE_RESOURCES |= {"nes_multicart.py", "game_sources/genesis_game_copy.s"}
REQUIRED_CONSOLE_RESOURCES |= {
    "mario_minus_world.py", "udl_shadowrun.py", "udc_nes_shadowrun.py",
    "shadowrun_camera.py", "shadowrun_interaction.py", "shadowrun_scene_assets.py",
    "shadowrun_replay.py",
} | {"game_sources/shadowrun_" + name + ".c" for name in
     ("input", "heading", "direction", "move", "player_move", "player_walk",
      "collision", "collision_resolve", "walk", "opening", "camera", "interaction",
      "nes_opening", "nes_atlas", "opening_camera", "opening_stoker", "player_fallback")}
REQUIRED_TEST_HELPERS |= {
    "scripts/check_mario_minus_world.py", "scripts/capture_genesis_scene.py",
    "scripts/check_shadowrun_interaction.py", "scripts/check_shadowrun_camera.py",
    "scripts/check_shadowrun_camera_frames.py", "scripts/check_shadowrun_player_cases.py",
    "scripts/check_shadowrun_opening_route.py", "tests/test_shadowrun_camera.py",
    "tests/test_mario_minus_world.py", "tests/test_shadowrun_movement.py",
    "tests/test_shadowrun_scene_assets.py", "tests/test_shadowrun_interaction.py",
    "tests/test_udl_shadowrun.py",
    "tests/test_shadowrun_replay.py",
    "tests/test_shadowrun_route_check.py",
}
REQUIRED_SOURCE_EVIDENCE |= {
    "docs/MARIO_MINUS_WORLD.md", "docs/SHADOWRUN_INTERACTION.md",
    "docs/SHADOWRUN_SOURCE_RESEARCH.md", "docs/SHADOWRUN_UIL_OPENING.md",
    "docs/evidence/mario-minus-world-2026-11-01/verification.json",
} | {"docs/evidence/shadowrun-uil-2026-11-01/" + name + ".json" for name in
     ("verification", "camera", "assets", "interaction", "source-research")}
REQUIRED_CONSOLE_RESOURCES |= {
    "shadowrun_animation.py", "shadowrun_combat.py", "shadowrun_dialogue.py",
    "shadowrun_inventory.py", "shadowrun_nes_animation.py", "shadowrun_systems.py",
    "shadowrun_world.py",
} | {"game_sources/shadowrun_" + name + ".c" for name in
     ("animation", "combat", "dialogue", "inventory", "nes_animation")}
REQUIRED_TEST_HELPERS |= {
    "scripts/check_shadowrun_combat.py", "scripts/check_shadowrun_dialogue_extra.py",
    "scripts/check_shadowrun_dialogue_world.py", "scripts/check_shadowrun_field_combat.py",
    "scripts/check_shadowrun_hp.py", "scripts/check_shadowrun_inventory.py",
    "scripts/check_shadowrun_nes_animation.py", "scripts/check_shadowrun_system_nes.py",
    "tests/test_shadowrun_animated_replay.py", "tests/test_shadowrun_animation.py",
    "tests/test_shadowrun_combat_inventory.py", "tests/test_shadowrun_dialogue_world.py",
    "tests/test_shadowrun_systems.py",
}
REQUIRED_SOURCE_EVIDENCE |= {
    "docs/SHADOWRUN_ANIMATION_AUDIO.md", "docs/SHADOWRUN_COMBAT_INVENTORY.md",
    "docs/SHADOWRUN_DIALOGUE_WORLD.md", "docs/SHADOWRUN_FULL_GAME_PROGRESS.md",
} | {"docs/evidence/shadowrun-full-2026-11-01/" + name + ".json" for name in
     ("combat", "dialogue-world-qualification", "dialogue-world", "field-combat", "hp", "inventory",
      "verification", "native-nes", "animation")}
REQUIRED_TEST_HELPERS |= {
    "scripts/check_genesis_copy.py", "scripts/check_genesis_performance.py",
    "scripts/check_genesis_stage_performance.py", "scripts/check_genesis_seeded_states.py",
    "scripts/check_nes_multicart.py", "tests/test_nes_multicart.py",
    "tests/test_nes_multicart_cli.py", "tests/test_nes_multicart_review.py",
}
REQUIRED_SOURCE_EVIDENCE |= {
    "docs/GENESIS_PERFORMANCE.md", "docs/NES_MULTICART.md",
    "docs/CONSOLE_INTAKE_2026_10_31.md",
    "docs/evidence/miniplanets-full-game-2026-10-31/genesis-performance.json",
    "docs/evidence/nes-multicart-2026-10-31/verification.json",
    "docs/evidence/console-intake-2026-10-31/intake.json",
}
REQUIRED_PE_RESOURCES = {"wine_guest/agent.c", "wine_guest/init.sh", "wine_guest/broker.py", "wine_guest/selftest.c"}
REQUIRED_PE_RESOURCES |= {"ida_guest/ui.c", "ida_guest/init.sh", "ida_guest/broker.py", "ida_guest/SDK-LICENSE.txt", "ida_wire.py", "ida_remote.py", "ida_trace.py"}
REQUIRED_PE_RESOURCES |= {"dos_guest/__init__.py", "dos_guest/init.sh", "dos_guest/broker.py", "dos_qemu.py", "dos_runtime.py", "qemu_machine.py", "gdb_rpc.py", "guest_assets.py"}
REQUIRED_PE_RESOURCES.add("ghidra_scripts/RomAsm.java")
REQUIRED_PE_RESOURCES.add("ghidra_scripts/RomAsmServer.java")
REQUIRED_KNOWLEDGE_RESOURCES = {"media.py", "skills/fdisbull-investigate/references/media-modules.md",
                                "data/console-udc-demo.json"}
REQUIRED_KNOWLEDGE_RESOURCES |= {"data/dos-runtime-signatures.json", "data/MICROSOFT-DOS-LICENSE.txt"}
REQUIRED_KNOWLEDGE_RESOURCES |= {"skills/fdisbull-investigate/SKILL.md", "skills/fdisbull-investigate/references/scenes.md",
                                 "skills/fdisbull-investigate/references/methodology.md",
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
    "skills/write-gamefaqs-guide/references/routes-and-discoveries.md",
    "skills/write-gamefaqs-guide/references/formats-and-engine-reuse.md",
    "skills/write-gamefaqs-guide/references/engine-source-examples.md",
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
        if EXCLUDED_DIRECTORIES.intersection(entry.parts):
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
            missing = {"fdisbull/" + name for name in REQUIRED_CONSOLE_RESOURCES} - set(names)
            if missing:
                raise ValueError(f"Wheel is missing console compiler resources: {sorted(missing)}")
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
        required |= {"src/fdisbull/" + name for name in REQUIRED_CONSOLE_RESOURCES}
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
