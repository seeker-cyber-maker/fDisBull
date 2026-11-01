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
                  "game_intents.py", "intent_runtime.py", "batch.py",
                  "scene_intents.py", "scene_bindings.py", "scene_runtime.py",
                  "door_intents.py", "door_bindings.py"}
REQUIRED_PLAYER_SOURCE = {"player/pyproject.toml"} | {"player/fdisbull_player/" + name for name in PLAYER_MODULES}
REQUIRED_TEST_HELPERS = {"tests/fixtures_formats.py", "tests/fixtures_macho.py", "tests/ida_rpc_vectors.json", "tests/dosbox_zip_empty_write.cpp"}
REQUIRED_TEST_HELPERS.add("tests/fixtures_z_scenes.py")
REQUIRED_TEST_HELPERS.add("tests/test_analysis_approach_skill.py")
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
REQUIRED_CONSOLE_RESOURCES |= {
    'game_sources/shadowrun_debug_place.c',
    'game_sources/shadowrun_field_action.c',
    'game_sources/shadowrun_field_motion.c',
    'game_sources/shadowrun_hostile.c',
    'game_sources/shadowrun_hostile_animation.c',
    'game_sources/shadowrun_hostile_burst.c',
    'game_sources/shadowrun_hostile_cycle.c',
    'game_sources/shadowrun_courtyard_adapter.c',
    'game_sources/shadowrun_enemy_east_slide.c',
    'game_sources/shadowrun_enemy_east_slide_exit.c',
    'game_sources/shadowrun_enemy_outer_slide.c',
    'game_sources/shadowrun_hostile_expiry_cycle.c',
    'game_sources/shadowrun_hostile_moving_attack_reentry.c',
    'game_sources/shadowrun_hostile_moving_idle_18.c',
    'game_sources/shadowrun_hostile_moving_pose_58.c',
    'game_sources/shadowrun_hostile_moving_relaunch_repeat.c',
    'game_sources/shadowrun_menu.c',
    'game_sources/shadowrun_player_combat_slide.c',
    'game_sources/shadowrun_player_combat_wall.c',
    'game_sources/shadowrun_player_reaction_direction_down.c',
    'game_sources/shadowrun_player_reaction_direction_expired.c',
    'game_sources/shadowrun_macos_app.m',
    'game_sources/shadowrun_hostile_moving_idle.c',
    'game_sources/shadowrun_hostile_moving_relaunch.c',
    'game_sources/shadowrun_player_reaction_idle_walk.c',
    'game_sources/shadowrun_assisted_pursuit.c',
    'game_sources/shadowrun_hostile_expired_pose.c',
    'game_sources/shadowrun_hostile_moving_attack.c',
    'game_sources/shadowrun_hostile_pursuit_route.c',
    'game_sources/shadowrun_hostile_zero_counter.c',
    'game_sources/shadowrun_player_reaction_held.c',
    'game_sources/shadowrun_party_clock.c',
    'game_sources/shadowrun_hostile_moving_pose.c',
    'game_sources/shadowrun_player_combat_walk.c',
    'game_sources/shadowrun_player_reaction_direction.c',
    'game_sources/shadowrun_hostile_cycle_transaction.c',
    'game_sources/shadowrun_hostile_motion.c',
    'game_sources/shadowrun_linked_actors.c',
    'game_sources/shadowrun_linked_heading.c',
    'game_sources/shadowrun_linked_motion.c',
    'game_sources/shadowrun_linked_spawn.c',
    'game_sources/shadowrun_nes_play.c',
    'game_sources/shadowrun_play.c',
    'game_sources/shadowrun_play_actors.c',
    'game_sources/shadowrun_play_shot.c',
    'game_sources/shadowrun_projectile_lifecycle.c',
    'game_sources/shadowrun_targeting.c',
    'shadowrun_city.py',
    'shadowrun_city_view.py',
    'shadowrun_field_combat.py',
    'shadowrun_hostile.py',
    'shadowrun_hostile_animation.py',
    'shadowrun_hostile_burst.py',
    'shadowrun_hostile_cycle.py',
    'shadowrun_enemy_east_slide.py',
    'shadowrun_enemy_outer_slide.py',
    'shadowrun_hostile_expiry_cycle.py',
    'shadowrun_hostile_moving_attack_reentry.py',
    'shadowrun_hostile_moving_idle_18.py',
    'shadowrun_hostile_moving_pose_58.py',
    'shadowrun_hostile_moving_relaunch_repeat.py',
    'shadowrun_menu.py',
    'shadowrun_player_combat_slide.py',
    'shadowrun_player_combat_wall.py',
    'shadowrun_player_reaction_direction_down.py',
    'shadowrun_macos.py',
    'udc_macos.py',
    'shadowrun_hostile_moving_idle.py',
    'shadowrun_hostile_moving_relaunch.py',
    'shadowrun_player_reaction_idle_walk.py',
    'shadowrun_ai.py',
    'shadowrun_hostile_expired_pose.py',
    'shadowrun_hostile_moving_attack.py',
    'shadowrun_hostile_pursuit_route.py',
    'shadowrun_hostile_zero_counter.py',
    'shadowrun_nes_rom_reader.py',
    'shadowrun_player_reaction_held.py',
    'shadowrun_party_clock.py',
    'shadowrun_hostile_moving_pose.py',
    'shadowrun_player_combat_walk.py',
    'shadowrun_player_reaction_direction.py',
    'shadowrun_hostile_motion.py',
    'shadowrun_linked_actors.py',
    'shadowrun_linked_heading.py',
    'shadowrun_nes_play.py',
    'shadowrun_play.py',
    'shadowrun_projectile_lifecycle.py',
    'shadowrun_targeting.py',
    'shadowrun_z.py',
}
REQUIRED_TEST_HELPERS |= {
    'scripts/check_shadowrun_captured_combat.py',
    'scripts/check_shadowrun_original_route.py',
    'scripts/check_shadowrun_play_natural_original.py',
    'scripts/check_shadowrun_field_action.py',
    'scripts/check_shadowrun_field_actor.py',
    'scripts/check_shadowrun_field_actor_nes.py',
    'scripts/check_shadowrun_field_motion.py',
    'scripts/check_shadowrun_field_nes.py',
    'scripts/check_shadowrun_field_target.py',
    'scripts/check_shadowrun_hostile.py',
    'scripts/check_shadowrun_hostile_animation.py',
    'scripts/check_shadowrun_hostile_burst.py',
    'scripts/check_shadowrun_hostile_cycle.py',
    'scripts/probe_shadowrun_enemy_east_slide_continued.py',
    'scripts/probe_shadowrun_enemy_outer_slide.py',
    'scripts/check_shadowrun_courtyard_route.py',
    'scripts/check_shadowrun_courtyard_waypoint.py',
    'scripts/check_shadowrun_courtyard_waypoint_idle.py',
    'scripts/check_shadowrun_enemy_east_slide.py',
    'scripts/check_shadowrun_enemy_east_slide_continued.py',
    'scripts/check_shadowrun_enemy_east_slide_exit.py',
    'scripts/check_shadowrun_enemy_east_slide_repeated.py',
    'scripts/check_shadowrun_enemy_outer_slide.py',
    'scripts/check_shadowrun_extended_macos.py',
    'scripts/check_shadowrun_extended_terminal.py',
    'scripts/check_shadowrun_hostile_expiry_cycle.py',
    'scripts/check_shadowrun_hostile_expiry_cycle_effect1.py',
    'scripts/check_shadowrun_hostile_moving_idle_18.py',
    'scripts/check_shadowrun_hostile_moving_idle_18_zero.py',
    'scripts/check_shadowrun_hostile_moving_pose_58.py',
    'scripts/check_shadowrun_hostile_moving_pose_58_zero.py',
    'scripts/check_shadowrun_hostile_moving_relaunch_repeat.py',
    'scripts/check_shadowrun_hostile_moving_relaunch_repeat_chain.py',
    'scripts/check_shadowrun_hostile_moving_relaunch_repeat_zero.py',
    'scripts/check_shadowrun_hostile_retreat_attack.py',
    'scripts/check_shadowrun_hostile_retreat_shot.py',
    'scripts/check_shadowrun_menu.py',
    'scripts/check_shadowrun_player_combat_slide.py',
    'scripts/check_shadowrun_player_combat_slide_continued.py',
    'scripts/check_shadowrun_player_combat_turn_up.py',
    'scripts/check_shadowrun_player_combat_wall.py',
    'scripts/check_shadowrun_player_reaction_direction_down.py',
    'scripts/check_shadowrun_macos.py',
    'scripts/check_shadowrun_hostile_moving_idle.py',
    'scripts/check_shadowrun_hostile_moving_relaunch.py',
    'scripts/check_shadowrun_hostile_moving_relaunch_chain.py',
    'scripts/check_shadowrun_hostile_zero_effect.py',
    'scripts/check_shadowrun_player_reaction_idle_walk.py',
    'scripts/check_shadowrun_arena_return_fire.py',
    'scripts/check_shadowrun_hostile_expired_pose.py',
    'scripts/check_shadowrun_hostile_moving_attack.py',
    'scripts/check_shadowrun_hostile_moving_shot.py',
    'scripts/check_shadowrun_hostile_positive_reentry.py',
    'scripts/check_shadowrun_hostile_pursuit_constructor.py',
    'scripts/check_shadowrun_hostile_pursuit_route.py',
    'scripts/check_shadowrun_hostile_terminal_reentry.py',
    'scripts/check_shadowrun_hostile_zero_counter.py',
    'scripts/check_shadowrun_hostile_zero_relaunch.py',
    'scripts/check_shadowrun_player_reaction_held.py',
    'scripts/check_shadowrun_hostile_terminal.py',
    'scripts/check_shadowrun_stationary_terminal.py',
    'scripts/check_shadowrun_stationary_nes.py',
    'scripts/check_shadowrun_arena_restart.py',
    'scripts/check_shadowrun_arena_refusal.py',
    'scripts/check_shadowrun_party_clock.py',
    'scripts/check_shadowrun_hostile_moving_pose.py',
    'scripts/check_shadowrun_player_combat_walk.py',
    'scripts/check_shadowrun_moving_arena.py',
    'scripts/check_shadowrun_moving_nes.py',
    'scripts/check_shadowrun_player_reaction_direction.py',
    'scripts/check_shadowrun_player_reaction_direction_route.py',
    'scripts/check_shadowrun_hostile_motion.py',
    'scripts/check_shadowrun_hostile_same_loop.py',
    'scripts/check_shadowrun_linked_actor.py',
    'scripts/check_shadowrun_linked_actors.py',
    'scripts/check_shadowrun_linked_heading.py',
    'scripts/check_shadowrun_linked_motion.py',
    'scripts/check_shadowrun_linked_spawn.py',
    'scripts/check_shadowrun_play_armor.py',
    'scripts/check_shadowrun_play_combat.py',
    'scripts/check_shadowrun_play_debug.py',
    'scripts/check_shadowrun_play_directions.py',
    'scripts/check_shadowrun_play_equipment.py',
    'scripts/check_shadowrun_play_reequip.py',
    'scripts/check_shadowrun_play_repeat.py',
    'scripts/check_shadowrun_play_right.py',
    'scripts/check_shadowrun_play_route.py',
    'scripts/check_shadowrun_play_scheduler.py',
    'scripts/check_shadowrun_play_shot.py',
    'scripts/check_shadowrun_play_target.py',
    'scripts/check_shadowrun_play_weapon.py',
    'scripts/check_shadowrun_projectile_animation.py',
    'scripts/check_shadowrun_projectile_lifecycle.py',
    'scripts/check_shadowrun_target_b_capture.py',
    'scripts/check_shadowrun_target_camera.py',
    'scripts/check_shadowrun_targeting.py',
    'scripts/check_shadowrun_z_play.py',
    'scripts/check_shadowrun_z_arena.py',
    'tests/test_genesis_scene_trace.py',
    'tests/test_shadowrun_city.py',
    'tests/test_shadowrun_city_view.py',
    'tests/test_shadowrun_field_action.py',
    'tests/test_shadowrun_hostile.py',
    'tests/test_shadowrun_hostile_cycle.py',
    'tests/test_shadowrun_menu.py',
    'tests/test_shadowrun_macos.py',
    'tests/test_udc_macos.py',
    'tests/test_shadowrun_nes_rom_reader.py',
    'tests/test_shadowrun_party_clock.py',
    'tests/test_shadowrun_ai_api.py',
    'tests/test_shadowrun_hostile_motion.py',
    'tests/test_shadowrun_linked_actors.py',
    'tests/test_shadowrun_linked_heading.py',
    'tests/test_shadowrun_play.py',
    'tests/test_shadowrun_projectile_lifecycle.py',
    'tests/test_shadowrun_targeting.py',
}
REQUIRED_CONSOLE_RESOURCES |= {
    'game_sources/shadowrun_ai_slots.c',
    'game_sources/shadowrun_assisted_arena.c',
    'game_sources/shadowrun_assisted_burst.c',
    'game_sources/shadowrun_assisted_controller.c',
    'game_sources/shadowrun_assisted_hostile_pose.c',
    'game_sources/shadowrun_assisted_player.c',
    'game_sources/shadowrun_enemy_combat_clock.c',
    'game_sources/shadowrun_enemy_idle.c',
    'game_sources/shadowrun_enemy_move.c',
    'game_sources/shadowrun_enemy_outer.c',
    'game_sources/shadowrun_enemy_overlap.c',
    'game_sources/shadowrun_enemy_overlap_one.c',
    'game_sources/shadowrun_enemy_projection.c',
    'game_sources/shadowrun_enemy_service.c',
    'game_sources/shadowrun_enemy_visible.c',
    'game_sources/shadowrun_enemy_waypoint.c',
    'game_sources/shadowrun_enemy_wound.c',
    'game_sources/shadowrun_enemy_wound_animation.c',
    'game_sources/shadowrun_enemy_wound_outer.c',
    'game_sources/shadowrun_hostile_attack_first.c',
    'game_sources/shadowrun_hostile_direct.c',
    'game_sources/shadowrun_hostile_follow.c',
    'game_sources/shadowrun_hostile_idle_service.c',
    'game_sources/shadowrun_hostile_linked.c',
    'game_sources/shadowrun_hostile_move.c',
    'game_sources/shadowrun_hostile_north.c',
    'game_sources/shadowrun_hostile_path_finish.c',
    'game_sources/shadowrun_hostile_pursuit.c',
    'game_sources/shadowrun_hostile_received_hit.c',
    'game_sources/shadowrun_hostile_relaunch.c',
    'game_sources/shadowrun_hostile_self_hit.c',
    'game_sources/shadowrun_hostile_stationary.c',
    'game_sources/shadowrun_hostile_waypoint.c',
    'game_sources/shadowrun_nes_bank.s',
    'game_sources/shadowrun_player_attack.c',
    'game_sources/shadowrun_player_damage.c',
    'game_sources/shadowrun_player_reaction.c',
    'game_sources/shadowrun_player_reaction_resume.c',
    'game_sources/shadowrun_player_reaction_step.c',
    'shadowrun_ai_play.py',
    'shadowrun_assisted_arena.py',
    'shadowrun_enemy_combat_clock.py',
    'shadowrun_enemy_idle.py',
    'shadowrun_enemy_move.py',
    'shadowrun_enemy_outer.py',
    'shadowrun_enemy_overlap.py',
    'shadowrun_enemy_overlap_one.py',
    'shadowrun_enemy_projection.py',
    'shadowrun_enemy_service.py',
    'shadowrun_enemy_visible.py',
    'shadowrun_enemy_waypoint.py',
    'shadowrun_enemy_wound.py',
    'shadowrun_enemy_wound_animation.py',
    'shadowrun_enemy_wound_outer.py',
    'shadowrun_hostile_attack_first.py',
    'shadowrun_hostile_direct.py',
    'shadowrun_hostile_follow.py',
    'shadowrun_hostile_idle_service.py',
    'shadowrun_hostile_linked.py',
    'shadowrun_hostile_move.py',
    'shadowrun_hostile_north.py',
    'shadowrun_hostile_path_finish.py',
    'shadowrun_hostile_pursuit.py',
    'shadowrun_hostile_received_hit.py',
    'shadowrun_hostile_relaunch.py',
    'shadowrun_hostile_self_hit.py',
    'shadowrun_hostile_stationary.py',
    'shadowrun_hostile_waypoint.py',
    'shadowrun_nes_ai.py',
    'shadowrun_nes_banked.py',
    'shadowrun_player_attack.py',
    'shadowrun_player_damage.py',
    'shadowrun_player_reaction.py',
    'shadowrun_player_reaction_resume.py',
    'shadowrun_player_reaction_step.py',
}
REQUIRED_TEST_HELPERS |= {
    'scripts/check_shadowrun_actor_natural_prefix.py',
    'scripts/check_shadowrun_actor_route.py',
    'scripts/check_shadowrun_actor_service.py',
    'scripts/check_shadowrun_ai_control.py',
    'scripts/check_shadowrun_ai_native.py',
    'scripts/check_shadowrun_arena_frames.py',
    'scripts/check_shadowrun_arena_nes.py',
    'scripts/check_shadowrun_arena_play_nes.py',
    'scripts/check_shadowrun_assisted_arena.py',
    'scripts/check_shadowrun_enemy_combat_clock.py',
    'scripts/check_shadowrun_enemy_idle.py',
    'scripts/check_shadowrun_enemy_move.py',
    'scripts/check_shadowrun_enemy_outer.py',
    'scripts/check_shadowrun_enemy_overlap.py',
    'scripts/check_shadowrun_enemy_overlap_one.py',
    'scripts/check_shadowrun_enemy_projection.py',
    'scripts/check_shadowrun_enemy_service.py',
    'scripts/check_shadowrun_enemy_visible.py',
    'scripts/check_shadowrun_enemy_waypoint.py',
    'scripts/check_shadowrun_enemy_wound.py',
    'scripts/check_shadowrun_enemy_wound_animation.py',
    'scripts/check_shadowrun_enemy_wound_outer.py',
    'scripts/check_shadowrun_hostile_attack_first.py',
    'scripts/check_shadowrun_hostile_chain.py',
    'scripts/check_shadowrun_hostile_direct.py',
    'scripts/check_shadowrun_hostile_follow.py',
    'scripts/check_shadowrun_hostile_follow_chain.py',
    'scripts/check_shadowrun_hostile_idle_service.py',
    'scripts/check_shadowrun_hostile_linked.py',
    'scripts/check_shadowrun_hostile_linked_launch.py',
    'scripts/check_shadowrun_hostile_move.py',
    'scripts/check_shadowrun_hostile_north.py',
    'scripts/check_shadowrun_hostile_path_finish.py',
    'scripts/check_shadowrun_hostile_pursuit.py',
    'scripts/check_shadowrun_hostile_received_hit.py',
    'scripts/check_shadowrun_hostile_received_seeds.py',
    'scripts/check_shadowrun_hostile_relaunch.py',
    'scripts/check_shadowrun_hostile_relaunch_chain.py',
    'scripts/check_shadowrun_hostile_self_hit.py',
    'scripts/check_shadowrun_hostile_stationary.py',
    'scripts/check_shadowrun_hostile_waypoint.py',
    'scripts/check_shadowrun_mmc3_cadence.py',
    'scripts/check_shadowrun_player_attack.py',
    'scripts/check_shadowrun_player_damage.py',
    'scripts/check_shadowrun_player_reaction.py',
    'scripts/check_shadowrun_player_reaction_frames.py',
    'scripts/check_shadowrun_player_reaction_impact.py',
    'scripts/check_shadowrun_player_reaction_resume.py',
    'scripts/check_shadowrun_player_reaction_step.py',
    'tests/test_shadowrun_ai_play.py',
    'tests/test_shadowrun_assisted_arena.py',
    'tests/test_shadowrun_enemy_dispatch.py',
    'tests/test_shadowrun_enemy_service.py',
    'tests/test_shadowrun_player_damage.py',
}
REQUIRED_SOURCE_EVIDENCE |= {
    'docs/SHADOWRUN_AI_EXPERIMENT.md',
    'docs/SHADOWRUN_MACOS_ARM64.md',
    'docs/SHADOWRUN_MACOS_EXTENDED.md',
    'docs/evidence/shadowrun-extended-2026-11-01/source.json',
    'docs/evidence/shadowrun-extended-2026-11-01/menu-intro.json',
    'docs/evidence/shadowrun-extended-2026-11-01/verification.json',
    'docs/evidence/shadowrun-extended-2026-11-01/suite.json',
    'docs/evidence/shadowrun-extended-2026-11-01/integration.json',
    'docs/GENESIS_NES_RESEARCH_HANDOFF.md',
    'docs/evidence/shadowrun-ai-2026-11-01/source.json',
    'docs/evidence/shadowrun-ai-2026-11-01/nes.json',
    'docs/evidence/shadowrun-ai-2026-11-01/skill.json',
    'docs/evidence/shadowrun-ai-2026-11-01/verification.json',
    'docs/evidence/shadowrun-ai-2026-11-01/suite.json',
    'docs/evidence/shadowrun-ai-2026-11-01/z.json',
    'docs/evidence/shadowrun-macos-2026-11-01/verification.json',
    'docs/SHADOWRUN_CITY_Z.md',
    'docs/SHADOWRUN_PLAYABLE_FIELD.md',
    'docs/evidence/shadowrun-play-2026-11-01/source-field.json',
    'docs/evidence/shadowrun-play-2026-11-01/nes-play.json',
    'docs/evidence/shadowrun-play-2026-11-01/city-z.json',
    'docs/evidence/shadowrun-play-2026-11-01/suite.json',
    'docs/evidence/shadowrun-play-2026-11-01/verification.json',
    'docs/SHADOWRUN_NES_PLAY.md',
    'docs/SHADOWRUN_PREPARED_FIELD_ACTION.md',
    'docs/SHADOWRUN_TARGETING.md',
    'docs/evidence/shadowrun-assisted-original-b-target.json',
}
REQUIRED_PE_RESOURCES = {"wine_guest/agent.c", "wine_guest/init.sh", "wine_guest/broker.py", "wine_guest/selftest.c"}
REQUIRED_PE_RESOURCES |= {"ida_guest/ui.c", "ida_guest/init.sh", "ida_guest/broker.py", "ida_guest/SDK-LICENSE.txt", "ida_wire.py", "ida_remote.py", "ida_trace.py"}
REQUIRED_PE_RESOURCES |= {"dos_guest/__init__.py", "dos_guest/init.sh", "dos_guest/broker.py", "dos_qemu.py", "dos_runtime.py", "qemu_machine.py", "gdb_rpc.py", "guest_assets.py", "wine_deltas.py"}
REQUIRED_PE_RESOURCES.add("ghidra_scripts/RomAsm.java")
REQUIRED_PE_RESOURCES.add("ghidra_scripts/RomAsmServer.java")
REQUIRED_KNOWLEDGE_RESOURCES = {"data/dinopark-e55-terminal.json", "media.py", "capabilities.py", "capture_audit.py",
                                "skills/fdisbull-investigate/references/media-modules.md", "data/console-udc-demo.json"}
REQUIRED_KNOWLEDGE_RESOURCES |= {"data/dos-runtime-signatures.json", "data/MICROSOFT-DOS-LICENSE.txt"}
REQUIRED_KNOWLEDGE_RESOURCES |= {"skills/fdisbull-investigate/SKILL.md", "skills/fdisbull-investigate/references/scenes.md",
                                 "skills/fdisbull-investigate/references/methodology.md",
                                 "skills/fdisbull-investigate/references/runtime-navigation.md",
                                 "skills/fdisbull-investigate/references/proofs.md",
                                 "skills/fdisbull-investigate/references/workflows.md",
                                 "skills/fdisbull-investigate/references/analysis-approach.md",
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


# Additional resources retained from the main integration line.
REQUIRED_TEST_HELPERS |= {
    "tests/fixtures_common_uil.py", "tests/fixtures_common_uil_native.py",
    "tests/test_uil_desktop.py", "tests/test_uil_desktop_admission.py",
    "tests/test_uil_desktop_cli.py", "tests/test_uil_native_arena_functions.py",
    "tests/test_capture_audit.py", "tests/test_media_modules.py",
    "tests/fixtures/frame_capture.S", "tests/test_macos_capture.py",
    "tests/test_macos_session.py", "tests/macos_capture_fixture.swift",
    "scripts/check_macos_capture_native.py",
}
REQUIRED_SOURCE_EVIDENCE |= {
    "docs/evidence/common-uil-2026-11-01/verification.json",
    "docs/evidence/common-uil-native-2026-11-01/verification.json",
    "docs/evidence/common-uil-desktop-2026-11-01/verification.json",
    "docs/verification/kq1-tas-2026-10-31.json",
}
REQUIRED_KNOWLEDGE_RESOURCES |= {"media.py", "capabilities.py", "capture_audit.py",
                                 "skills/fdisbull-investigate/references/media-modules.md"}
REQUIRED_MACOS_RESOURCES = {"ghidra_arm64.py", "macos_lldb.py", "_macos_lldb_driver.py",
                            "data/FdisbullGhidraArm64.txt", "macos_capture.py", "macos_session.py",
                            "data/FdisbullMacCapture.swift"}
REQUIRED_NATIVE_RUNTIME_RESOURCES = {"uil_desktop.py"} | {
    "native_runtime/" + name for name in
    ("memory-desktop.c", "memory-desktop.h", "memory-appkit.m", "memory-x11.c", "memory-win32.c")}
REQUIRED_KNOWLEDGE_RESOURCES |= REQUIRED_NATIVE_RUNTIME_RESOURCES
REQUIRED_SOURCE_EVIDENCE |= {
    "docs/evidence/source-search-pilot/verification.json",
    "docs/evidence/civd-source-maps/verification.json",
    "docs/evidence/civd-food-swaps/verification.json",
    "docs/evidence/civd-food-swaps/shared-uil.json",
    "docs/evidence/civd-food-swaps/source-ui-inventory.json",
    "docs/evidence/civd-food-arm64/verification.json",
    "docs/evidence/civd-food-web/verification.json",
    "docs/evidence/civd-browser-shell/verification.json",
    "docs/evidence/snake-browser/verification.json",
}
REQUIRED_TEST_HELPERS |= {"tests/web_shell_checks.mjs", "tests/memory_shell_checks.mjs"}
REQUIRED_KNOWLEDGE_RESOURCES |= {"data/civd-z-screen-families.json", "web_runtime/block.mjs",
                                 "web_runtime/shell.mjs", "web_runtime/app.mjs",
                                 "web_runtime/index.html", "web_runtime/memory.mjs",
                                 "web_runtime/memory-shell.mjs", "web_runtime/memory-canvas.mjs",
                                 "web_runtime/memory-index.html"}

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
