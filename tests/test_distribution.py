"""Check the release guard with hostile additions to an otherwise valid archive."""
from pathlib import Path
import re
import runpy
import zipfile

import pytest


REQUIRED_SOURCE_FILES=('AGENTS.md','CLAUDE.md','docs/AGENT_QUICKSTART.md','scripts/check_agent_skill.py',
                       'player/pyproject.toml','player/fdisbull_player/__init__.py',
                       'player/fdisbull_player/__main__.py','player/fdisbull_player/player.py','player/fdisbull_player/runtime.py','player/fdisbull_player/live.py','player/fdisbull_player/word16.py',
                       'player/fdisbull_player/game_intents.py','player/fdisbull_player/intent_runtime.py','player/fdisbull_player/batch.py',
                       'src/fdisbull/media.py','src/fdisbull/skills/fdisbull-investigate/references/media-modules.md','tests/test_media_modules.py',
                       'src/fdisbull/__init__.py','pyproject.toml','tests/fixtures_formats.py','tests/fixtures_macho.py','tests/fixtures_z_scenes.py',
                       'tests/wine_gui_fixture.c','tests/dosbox_zip_empty_write.cpp','src/fdisbull/wine_guest/agent.c',
                       'src/fdisbull/wine_guest/init.sh','src/fdisbull/wine_guest/broker.py','src/fdisbull/wine_guest/selftest.c',
                       'tests/ida_rpc_vectors.json','src/fdisbull/ida_wire.py','src/fdisbull/ida_remote.py',
                       'src/fdisbull/ida_guest/broker.py','src/fdisbull/ida_guest/init.sh',
                       'src/fdisbull/ida_guest/ui.c','src/fdisbull/ida_guest/SDK-LICENSE.txt','src/fdisbull/ida_trace.py',
                       'src/fdisbull/dos_guest/__init__.py','src/fdisbull/dos_guest/init.sh','src/fdisbull/dos_guest/broker.py',
                       'src/fdisbull/dos_qemu.py','src/fdisbull/dos_runtime.py','src/fdisbull/qemu_machine.py',
                       'src/fdisbull/gdb_rpc.py','src/fdisbull/guest_assets.py',
                       'src/fdisbull/data/dos-runtime-signatures.json','src/fdisbull/data/MICROSOFT-DOS-LICENSE.txt',
                       'src/fdisbull/skills/fdisbull-investigate/SKILL.md',
                       'src/fdisbull/skills/fdisbull-investigate/references/scenes.md',
                       'src/fdisbull/skills/fdisbull-investigate/references/methodology.md',
                       'src/fdisbull/skills/fdisbull-investigate/references/runtime-navigation.md',
                       'src/fdisbull/skills/fdisbull-investigate/references/proofs.md',
                       'src/fdisbull/skills/fdisbull-investigate/references/workflows.md',
                       'src/fdisbull/skills/fdisbull-investigate/references/analysis-approach.md',
                       'tests/test_analysis_approach_skill.py',
                       'src/fdisbull/skills/fdisbull-investigate/references/recovery-research.md',
                       'src/fdisbull/skills/fdisbull-investigate/references/semantic-contracts.md',
                       'src/fdisbull/skills/fdisbull-investigate/references/formats-and-media.md',
                       'src/fdisbull/skills/fdisbull-investigate/references/udl-uil-udc.md')
GAMEFAQS_SKILL_FILES = tuple('src/fdisbull/skills/write-gamefaqs-guide/'+name for name in (
    'SKILL.md', 'references/evidence-and-provenance.md', 'references/guide-structure.md',
    'references/technical-mechanics.md', 'references/source-examples.md',
    'references/routes-and-discoveries.md', 'references/formats-and-engine-reuse.md',
    'references/engine-source-examples.md',
))
REQUIRED_SOURCE_FILES += GAMEFAQS_SKILL_FILES
UDC_EVIDENCE_FILES = {
    'docs/evidence/udc-2026-10-29/dino.json',
    'docs/evidence/udc-2026-10-29/zork.json',
    'docs/evidence/udc-2026-10-29/synthetic.json',
}
OUTPUT_EVIDENCE_FILES = {
    'docs/evidence/output-024/amplification.json',
    'docs/evidence/output-024/dinopark-native.json',
    'docs/evidence/output-024/dinopark-output.json',
    'docs/evidence/output-024/tests.json',
}
SCENE_RECOVERY_EVIDENCE_FILES = {
    'docs/evidence/scene-recovery-2026-10-29/representation-paths.json',
    'docs/evidence/scene-recovery-2026-10-29/scene-pipeline-summary.json',
}
REQUIRED_SOURCE_FILES += tuple(sorted(OUTPUT_EVIDENCE_FILES | SCENE_RECOVERY_EVIDENCE_FILES))
INTEGRATION_EVIDENCE_FILES = {
    'docs/evidence/integration-025/zork.json',
    'docs/evidence/integration-025/dinopark.json',
    'docs/evidence/integration-025/tests.json',
    'docs/evidence/integration-025/packages.json',
}
REQUIRED_SOURCE_FILES += tuple(sorted(INTEGRATION_EVIDENCE_FILES))
REQUIRED_SOURCE_FILES += ('docs/uil-rfcs/0002/vectors.json',
                          'docs/uil-rfcs/0002/replay-summary.json')
REQUIRED_SOURCE_FILES += ('docs/evidence/integration-026/verification.json',)
REQUIRED_SOURCE_FILES += ('docs/evidence/integration-0261/verification.json',)
ROM_ASM_RESOURCES = (
    'src/fdisbull/ghidra_scripts/RomAsm.java',
    'src/fdisbull/ghidra_scripts/RomAsmServer.java',
    'tests/rom_asm_sh2_vectors.json',
    'docs/evidence/rom-asm-2026-10-30/benchmark.json',
    'docs/evidence/rom-asm-2026-10-30/accuracy.json',
    'docs/evidence/rom-asm-2026-10-30/benchmark-persistent.json',
    'docs/evidence/rom-asm-2026-10-30/capstone-profile.json',
    'docs/evidence/rom-asm-2026-10-30/decoder-census.json',
    'docs/evidence/rom-asm-2026-10-30/semantic-route.json',
    'patches/capstone-5.0.9-sh-profile-gating.patch',
    'scripts/rom_semantic_route/DecompileAuthoredSh2.java',
    'scripts/rom_semantic_route/README.md',
)
REQUIRED_SOURCE_FILES += ("docs/evidence/genesis-rom-route-2026-10-30/verification.json", "scripts/probe_genesis_function.py", "scripts/verify_genesis_rom_route.py")
REQUIRED_SOURCE_FILES += ("docs/evidence/miniplanets-nes-level-2026-10-31/verification.json", "scripts/check_miniplanets_native.py", "scripts/verify_miniplanets_level.py")
REQUIRED_SOURCE_FILES += ROM_ASM_RESOURCES
REQUIRED_SOURCE_FILES += ("docs/evidence/console-udc-2026-10-30/verification.json", "src/fdisbull/data/console-udc-demo.json")
CONSOLE_GAME_RESOURCES = tuple('src/fdisbull/' + name for name in (
    'game_il.py', 'miniplanets_audio.py', 'udl_miniplanets_full.py', 'udc_nes_game.py',
    'data/miniplanets_full_contract.json',
    'game_sources/miniplanets_full.c', 'game_sources/miniplanets_actors.c',
    'game_sources/miniplanets_audio_nes.c', 'game_sources/nes_globe_renderer.c',
    'game_sources/nes_game_platform.c', 'game_sources/nes_game_start.s',
    'game_sources/nes_audio_clock.c',
    'game_sources/miniplanets_audio_fast.s', 'game_sources/nes_globe_fast.s',
    'game_sources/nes_game_fast.s', 'game_sources/LICENSE.txt',
    'game_sources/nes_display_fast.s',
))
CONSOLE_GAME_HELPERS = (
    'scripts/check_console_udc.py', 'scripts/check_miniplanets_common_native.py',
    'scripts/check_miniplanets_full_flow.py', 'scripts/check_miniplanets_audio.py',
    'scripts/check_miniplanets_nes_game.py',
    'scripts/check_miniplanets_nes_audio.py', 'scripts/check_miniplanets_nes_timing.py',
    'scripts/capture_miniplanets_audio.py', 'scripts/check_nes_audio_clock.py',
    'scripts/check_nes_mapper_atomic.py',
    'scripts/check_native_array_offsets.py',
    'scripts/check_miniplanets_audio_fast.py',
    'scripts/check_miniplanets_globe_fast.py', 'scripts/check_miniplanets_game_fast.py',
    'scripts/check_miniplanets_actor_fast.py', 'scripts/check_miniplanets_projection_pair.py',
    'scripts/check_miniplanets_renderer_objects.py', 'scripts/check_miniplanets_projection_cache.py',
    'scripts/check_miniplanets_hud_fast.py', 'scripts/check_miniplanets_sprite_fast.py',
    'scripts/check_miniplanets_objects_native.py', 'scripts/check_miniplanets_upload_plan.py',
    'scripts/check_miniplanets_upload_stress.py', 'scripts/check_miniplanets_nes_display.py',
    'scripts/miniplanets_display_observer.c',
    'scripts/check_miniplanets_terrain_cache.py', 'scripts/check_miniplanets_terrain_cache_sequence.py',
    'scripts/check_miniplanets_terrain_hints.py',
    'scripts/check_miniplanets_sparse_hint.py', 'scripts/check_miniplanets_terrain_clear.py',
    'tests/test_game_il.py', 'tests/test_miniplanets_full.py',
    'tests/test_console_udc_host.py', 'tests/test_miniplanets_globe_assets.py',
    'tests/test_miniplanets_nes_game.py', 'tests/test_nes_audio_clock.py',
    'tests/test_miniplanets_nes_timing.py', 'tests/test_miniplanets_source_capture.py',
    'tests/test_nes_game_resources.py',
    'tests/test_miniplanets_audio.py',
)
CONSOLE_GAME_EVIDENCE = tuple('docs/evidence/miniplanets-full-game-2026-10-31/' + name for name in (
    'actors.json', 'common.json', 'reference-flow.json', 'projection.json', 'renderer-fast.json',
    'audio-clock-verification.json', 'audio-verification.json', 'phase-intrinsic.json',
    'array-offsets.json', 'profile-r12.json', 'domain.json',
    'profile-r13.json', 'bank-race.json', 'audio-tempo-protocol-v2.json',
    'normal-audio-tempo.json', 'nes-verification.json',
    'mapper-atomic-verification.json', 'source-review.json', 'lowering-exploration.json',
    'optimization.json',
    'display-optimization.json',
    'uncapped-rendering.json',
    'moving-optimization.json',
))
CONSOLE_GAME_EVIDENCE += ('docs/MINIPLANETS_FULL_GAME.md',)
CONSOLE_GAME_RESOURCES += tuple('src/fdisbull/' + name for name in (
    'genesis_replay.py', 'udc_genesis_game.py', 'presentation_il.py', 'psg_il.py',
    'data/miniplanets_presentation.uil.json', 'data/miniplanets_psg.uil.json',
    'game_sources/miniplanets_presentation_uil.c', 'game_sources/miniplanets_psg_uil.c',
    'game_sources/genesis_game_platform.c', 'game_sources/genesis_game_start.s',
    'game_sources/genesis_game_renderer.c', 'game_sources/genesis_game_audio.c',
    'game_sources/genesis_game_audio.S',
))
CONSOLE_GAME_HELPERS += (
    'scripts/check_genesis_game.py', 'scripts/check_genesis_game_audio_source.py',
    'scripts/check_genesis_game_renderer.py', 'scripts/check_genesis_vdp_presentation.py',
    'scripts/check_genesis_presentation.py',
    'scripts/check_miniplanets_psg_uil.py', 'scripts/check_presentation_uil.py',
    'tests/test_genesis_replay.py', 'tests/test_genesis_replay_targets.py',
    'tests/test_genesis_replay_review.py', 'tests/test_udc_genesis_game.py',
    'tests/test_genesis_game_audio.py', 'tests/test_presentation_il.py', 'tests/test_psg_il.py',
)
CONSOLE_GAME_EVIDENCE += (
    'docs/GENESIS_UIL_REPLAY.md',
    'docs/evidence/miniplanets-full-game-2026-10-31/genesis-replay.json',
    'docs/evidence/miniplanets-full-game-2026-10-31/genesis-presentation.json',
)
CONSOLE_GAME_RESOURCES += (
    'src/fdisbull/nes_multicart.py', 'src/fdisbull/game_sources/genesis_game_copy.s',
)
CONSOLE_GAME_HELPERS += (
    'scripts/check_genesis_copy.py', 'scripts/check_genesis_performance.py',
    'scripts/check_genesis_stage_performance.py', 'scripts/check_genesis_seeded_states.py',
    'scripts/check_nes_multicart.py', 'tests/test_nes_multicart.py',
    'tests/test_nes_multicart_cli.py', 'tests/test_nes_multicart_review.py',
)
CONSOLE_GAME_EVIDENCE += (
    'docs/GENESIS_PERFORMANCE.md', 'docs/NES_MULTICART.md',
    'docs/CONSOLE_INTAKE_2026_10_31.md',
    'docs/evidence/miniplanets-full-game-2026-10-31/genesis-performance.json',
    'docs/evidence/nes-multicart-2026-10-31/verification.json',
    'docs/evidence/console-intake-2026-10-31/intake.json',
)
CONSOLE_GAME_RESOURCES += tuple('src/fdisbull/' + name for name in (
    'mario_minus_world.py', 'udl_shadowrun.py', 'udc_nes_shadowrun.py',
    'shadowrun_camera.py', 'shadowrun_interaction.py', 'shadowrun_scene_assets.py',
    'shadowrun_replay.py',
))
CONSOLE_GAME_RESOURCES += tuple('src/fdisbull/game_sources/shadowrun_' + name + '.c' for name in (
    'input', 'heading', 'direction', 'move', 'player_move', 'player_walk',
    'collision', 'collision_resolve', 'walk', 'opening', 'camera', 'interaction',
    'nes_opening', 'nes_atlas', 'opening_camera', 'opening_stoker', 'player_fallback',
))
CONSOLE_GAME_HELPERS += (
    'scripts/check_mario_minus_world.py', 'scripts/capture_genesis_scene.py',
    'scripts/check_shadowrun_interaction.py', 'scripts/check_shadowrun_camera.py',
    'scripts/check_shadowrun_camera_frames.py', 'scripts/check_shadowrun_player_cases.py',
    'scripts/check_shadowrun_opening_route.py', 'tests/test_shadowrun_camera.py',
    'tests/test_mario_minus_world.py', 'tests/test_shadowrun_movement.py',
    'tests/test_shadowrun_scene_assets.py', 'tests/test_shadowrun_interaction.py',
    'tests/test_udl_shadowrun.py', 'tests/test_shadowrun_replay.py',
    'tests/test_shadowrun_route_check.py',
)
CONSOLE_GAME_EVIDENCE += (
    'docs/MARIO_MINUS_WORLD.md', 'docs/SHADOWRUN_INTERACTION.md',
    'docs/SHADOWRUN_SOURCE_RESEARCH.md', 'docs/SHADOWRUN_UIL_OPENING.md',
    'docs/evidence/mario-minus-world-2026-11-01/verification.json',
) + tuple('docs/evidence/shadowrun-uil-2026-11-01/' + name + '.json' for name in (
    'verification', 'camera', 'assets', 'interaction', 'source-research',
))
CONSOLE_GAME_RESOURCES += tuple('src/fdisbull/' + name for name in (
    'shadowrun_animation.py', 'shadowrun_combat.py', 'shadowrun_dialogue.py',
    'shadowrun_inventory.py', 'shadowrun_nes_animation.py', 'shadowrun_systems.py',
    'shadowrun_world.py',
))
CONSOLE_GAME_RESOURCES += tuple('src/fdisbull/game_sources/shadowrun_' + name + '.c' for name in (
    'animation', 'combat', 'dialogue', 'inventory', 'nes_animation',
))
CONSOLE_GAME_HELPERS += (
    'scripts/check_shadowrun_combat.py', 'scripts/check_shadowrun_dialogue_extra.py',
    'scripts/check_shadowrun_dialogue_world.py', 'scripts/check_shadowrun_field_combat.py',
    'scripts/check_shadowrun_hp.py', 'scripts/check_shadowrun_inventory.py',
    'scripts/check_shadowrun_nes_animation.py', 'scripts/check_shadowrun_system_nes.py',
    'tests/test_shadowrun_animated_replay.py', 'tests/test_shadowrun_animation.py',
    'tests/test_shadowrun_combat_inventory.py', 'tests/test_shadowrun_dialogue_world.py',
    'tests/test_shadowrun_systems.py',
)
CONSOLE_GAME_EVIDENCE += (
    'docs/SHADOWRUN_ANIMATION_AUDIO.md', 'docs/SHADOWRUN_COMBAT_INVENTORY.md',
    'docs/SHADOWRUN_DIALOGUE_WORLD.md', 'docs/SHADOWRUN_FULL_GAME_PROGRESS.md',
) + tuple('docs/evidence/shadowrun-full-2026-11-01/' + name + '.json' for name in (
    'combat', 'dialogue-world-qualification', 'dialogue-world', 'field-combat', 'hp', 'inventory',
    'verification', 'native-nes', 'animation',
))
CONSOLE_GAME_RESOURCES += (
    'src/fdisbull/game_sources/shadowrun_debug_place.c',
    'src/fdisbull/game_sources/shadowrun_field_action.c',
    'src/fdisbull/game_sources/shadowrun_field_motion.c',
    'src/fdisbull/game_sources/shadowrun_hostile.c',
    'src/fdisbull/game_sources/shadowrun_hostile_animation.c',
    'src/fdisbull/game_sources/shadowrun_hostile_burst.c',
    'src/fdisbull/game_sources/shadowrun_hostile_cycle.c',
    'src/fdisbull/game_sources/shadowrun_courtyard_adapter.c',
    'src/fdisbull/game_sources/shadowrun_enemy_east_slide.c',
    'src/fdisbull/game_sources/shadowrun_enemy_east_slide_exit.c',
    'src/fdisbull/game_sources/shadowrun_enemy_outer_slide.c',
    'src/fdisbull/game_sources/shadowrun_hostile_expiry_cycle.c',
    'src/fdisbull/game_sources/shadowrun_hostile_moving_attack_reentry.c',
    'src/fdisbull/game_sources/shadowrun_hostile_moving_idle_18.c',
    'src/fdisbull/game_sources/shadowrun_hostile_moving_pose_58.c',
    'src/fdisbull/game_sources/shadowrun_hostile_moving_relaunch_repeat.c',
    'src/fdisbull/game_sources/shadowrun_menu.c',
    'src/fdisbull/game_sources/shadowrun_player_combat_slide.c',
    'src/fdisbull/game_sources/shadowrun_player_combat_wall.c',
    'src/fdisbull/game_sources/shadowrun_player_reaction_direction_down.c',
    'src/fdisbull/game_sources/shadowrun_player_reaction_direction_expired.c',
    'src/fdisbull/game_sources/shadowrun_macos_app.m',
    'src/fdisbull/game_sources/shadowrun_hostile_moving_idle.c',
    'src/fdisbull/game_sources/shadowrun_hostile_moving_relaunch.c',
    'src/fdisbull/game_sources/shadowrun_player_reaction_idle_walk.c',
    'src/fdisbull/game_sources/shadowrun_assisted_pursuit.c',
    'src/fdisbull/game_sources/shadowrun_hostile_expired_pose.c',
    'src/fdisbull/game_sources/shadowrun_hostile_moving_attack.c',
    'src/fdisbull/game_sources/shadowrun_hostile_pursuit_route.c',
    'src/fdisbull/game_sources/shadowrun_hostile_zero_counter.c',
    'src/fdisbull/game_sources/shadowrun_player_reaction_held.c',
    'src/fdisbull/game_sources/shadowrun_party_clock.c',
    'src/fdisbull/game_sources/shadowrun_hostile_moving_pose.c',
    'src/fdisbull/game_sources/shadowrun_player_combat_walk.c',
    'src/fdisbull/game_sources/shadowrun_player_reaction_direction.c',
    'src/fdisbull/game_sources/shadowrun_hostile_cycle_transaction.c',
    'src/fdisbull/game_sources/shadowrun_hostile_motion.c',
    'src/fdisbull/game_sources/shadowrun_linked_actors.c',
    'src/fdisbull/game_sources/shadowrun_linked_heading.c',
    'src/fdisbull/game_sources/shadowrun_linked_motion.c',
    'src/fdisbull/game_sources/shadowrun_linked_spawn.c',
    'src/fdisbull/game_sources/shadowrun_nes_play.c',
    'src/fdisbull/game_sources/shadowrun_play.c',
    'src/fdisbull/game_sources/shadowrun_play_actors.c',
    'src/fdisbull/game_sources/shadowrun_play_shot.c',
    'src/fdisbull/game_sources/shadowrun_projectile_lifecycle.c',
    'src/fdisbull/game_sources/shadowrun_targeting.c',
    'src/fdisbull/shadowrun_city.py',
    'src/fdisbull/shadowrun_city_view.py',
    'src/fdisbull/shadowrun_field_combat.py',
    'src/fdisbull/shadowrun_hostile.py',
    'src/fdisbull/shadowrun_hostile_animation.py',
    'src/fdisbull/shadowrun_hostile_burst.py',
    'src/fdisbull/shadowrun_hostile_cycle.py',
    'src/fdisbull/shadowrun_enemy_east_slide.py',
    'src/fdisbull/shadowrun_enemy_outer_slide.py',
    'src/fdisbull/shadowrun_hostile_expiry_cycle.py',
    'src/fdisbull/shadowrun_hostile_moving_attack_reentry.py',
    'src/fdisbull/shadowrun_hostile_moving_idle_18.py',
    'src/fdisbull/shadowrun_hostile_moving_pose_58.py',
    'src/fdisbull/shadowrun_hostile_moving_relaunch_repeat.py',
    'src/fdisbull/shadowrun_menu.py',
    'src/fdisbull/shadowrun_player_combat_slide.py',
    'src/fdisbull/shadowrun_player_combat_wall.py',
    'src/fdisbull/shadowrun_player_reaction_direction_down.py',
    'src/fdisbull/shadowrun_macos.py',
    'src/fdisbull/udc_macos.py',
    'src/fdisbull/shadowrun_hostile_moving_idle.py',
    'src/fdisbull/shadowrun_hostile_moving_relaunch.py',
    'src/fdisbull/shadowrun_player_reaction_idle_walk.py',
    'src/fdisbull/shadowrun_ai.py',
    'src/fdisbull/shadowrun_hostile_expired_pose.py',
    'src/fdisbull/shadowrun_hostile_moving_attack.py',
    'src/fdisbull/shadowrun_hostile_pursuit_route.py',
    'src/fdisbull/shadowrun_hostile_zero_counter.py',
    'src/fdisbull/shadowrun_nes_rom_reader.py',
    'src/fdisbull/shadowrun_player_reaction_held.py',
    'src/fdisbull/shadowrun_party_clock.py',
    'src/fdisbull/shadowrun_hostile_moving_pose.py',
    'src/fdisbull/shadowrun_player_combat_walk.py',
    'src/fdisbull/shadowrun_player_reaction_direction.py',
    'src/fdisbull/shadowrun_hostile_motion.py',
    'src/fdisbull/shadowrun_linked_actors.py',
    'src/fdisbull/shadowrun_linked_heading.py',
    'src/fdisbull/shadowrun_nes_play.py',
    'src/fdisbull/shadowrun_play.py',
    'src/fdisbull/shadowrun_projectile_lifecycle.py',
    'src/fdisbull/shadowrun_targeting.py',
    'src/fdisbull/shadowrun_z.py',
)
CONSOLE_GAME_HELPERS += (
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
)
CONSOLE_GAME_RESOURCES += (
    'src/fdisbull/game_sources/shadowrun_ai_slots.c',
    'src/fdisbull/game_sources/shadowrun_assisted_arena.c',
    'src/fdisbull/game_sources/shadowrun_assisted_burst.c',
    'src/fdisbull/game_sources/shadowrun_assisted_controller.c',
    'src/fdisbull/game_sources/shadowrun_assisted_hostile_pose.c',
    'src/fdisbull/game_sources/shadowrun_assisted_player.c',
    'src/fdisbull/game_sources/shadowrun_enemy_combat_clock.c',
    'src/fdisbull/game_sources/shadowrun_enemy_idle.c',
    'src/fdisbull/game_sources/shadowrun_enemy_move.c',
    'src/fdisbull/game_sources/shadowrun_enemy_outer.c',
    'src/fdisbull/game_sources/shadowrun_enemy_overlap.c',
    'src/fdisbull/game_sources/shadowrun_enemy_overlap_one.c',
    'src/fdisbull/game_sources/shadowrun_enemy_projection.c',
    'src/fdisbull/game_sources/shadowrun_enemy_service.c',
    'src/fdisbull/game_sources/shadowrun_enemy_visible.c',
    'src/fdisbull/game_sources/shadowrun_enemy_waypoint.c',
    'src/fdisbull/game_sources/shadowrun_enemy_wound.c',
    'src/fdisbull/game_sources/shadowrun_enemy_wound_animation.c',
    'src/fdisbull/game_sources/shadowrun_enemy_wound_outer.c',
    'src/fdisbull/game_sources/shadowrun_hostile_attack_first.c',
    'src/fdisbull/game_sources/shadowrun_hostile_direct.c',
    'src/fdisbull/game_sources/shadowrun_hostile_follow.c',
    'src/fdisbull/game_sources/shadowrun_hostile_idle_service.c',
    'src/fdisbull/game_sources/shadowrun_hostile_linked.c',
    'src/fdisbull/game_sources/shadowrun_hostile_move.c',
    'src/fdisbull/game_sources/shadowrun_hostile_north.c',
    'src/fdisbull/game_sources/shadowrun_hostile_path_finish.c',
    'src/fdisbull/game_sources/shadowrun_hostile_pursuit.c',
    'src/fdisbull/game_sources/shadowrun_hostile_received_hit.c',
    'src/fdisbull/game_sources/shadowrun_hostile_relaunch.c',
    'src/fdisbull/game_sources/shadowrun_hostile_self_hit.c',
    'src/fdisbull/game_sources/shadowrun_hostile_stationary.c',
    'src/fdisbull/game_sources/shadowrun_hostile_waypoint.c',
    'src/fdisbull/game_sources/shadowrun_nes_bank.s',
    'src/fdisbull/game_sources/shadowrun_player_attack.c',
    'src/fdisbull/game_sources/shadowrun_player_damage.c',
    'src/fdisbull/game_sources/shadowrun_player_reaction.c',
    'src/fdisbull/game_sources/shadowrun_player_reaction_resume.c',
    'src/fdisbull/game_sources/shadowrun_player_reaction_step.c',
    'src/fdisbull/shadowrun_ai_play.py',
    'src/fdisbull/shadowrun_assisted_arena.py',
    'src/fdisbull/shadowrun_enemy_combat_clock.py',
    'src/fdisbull/shadowrun_enemy_idle.py',
    'src/fdisbull/shadowrun_enemy_move.py',
    'src/fdisbull/shadowrun_enemy_outer.py',
    'src/fdisbull/shadowrun_enemy_overlap.py',
    'src/fdisbull/shadowrun_enemy_overlap_one.py',
    'src/fdisbull/shadowrun_enemy_projection.py',
    'src/fdisbull/shadowrun_enemy_service.py',
    'src/fdisbull/shadowrun_enemy_visible.py',
    'src/fdisbull/shadowrun_enemy_waypoint.py',
    'src/fdisbull/shadowrun_enemy_wound.py',
    'src/fdisbull/shadowrun_enemy_wound_animation.py',
    'src/fdisbull/shadowrun_enemy_wound_outer.py',
    'src/fdisbull/shadowrun_hostile_attack_first.py',
    'src/fdisbull/shadowrun_hostile_direct.py',
    'src/fdisbull/shadowrun_hostile_follow.py',
    'src/fdisbull/shadowrun_hostile_idle_service.py',
    'src/fdisbull/shadowrun_hostile_linked.py',
    'src/fdisbull/shadowrun_hostile_move.py',
    'src/fdisbull/shadowrun_hostile_north.py',
    'src/fdisbull/shadowrun_hostile_path_finish.py',
    'src/fdisbull/shadowrun_hostile_pursuit.py',
    'src/fdisbull/shadowrun_hostile_received_hit.py',
    'src/fdisbull/shadowrun_hostile_relaunch.py',
    'src/fdisbull/shadowrun_hostile_self_hit.py',
    'src/fdisbull/shadowrun_hostile_stationary.py',
    'src/fdisbull/shadowrun_hostile_waypoint.py',
    'src/fdisbull/shadowrun_nes_ai.py',
    'src/fdisbull/shadowrun_nes_banked.py',
    'src/fdisbull/shadowrun_player_attack.py',
    'src/fdisbull/shadowrun_player_damage.py',
    'src/fdisbull/shadowrun_player_reaction.py',
    'src/fdisbull/shadowrun_player_reaction_resume.py',
    'src/fdisbull/shadowrun_player_reaction_step.py',
)
CONSOLE_GAME_HELPERS += (
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
)
CONSOLE_GAME_EVIDENCE += (
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
)

CONSOLE_GAME_RESOURCES += (
    'src/fdisbull/game_sources/shadowrun_snes_rng.c',
    'src/fdisbull/shadowrun_snes_rng.py',
    'src/fdisbull/game_sources/shadowrun_snes_vertical.c',
    'src/fdisbull/shadowrun_snes_vertical.py',
    'src/fdisbull/game_sources/shadowrun_snes_conversation.c',
    'src/fdisbull/game_sources/shadowrun_snes_conversation_bridge.c',
    'src/fdisbull/game_sources/shadowrun_snes_dialogue_select.c',
    'src/fdisbull/game_sources/shadowrun_snes_transition.c',
    'src/fdisbull/shadowrun_snes_conversation.py',
    'src/fdisbull/shadowrun_snes_dialogue_select.py',
    'src/fdisbull/shadowrun_snes_transition.py',
    'src/fdisbull/game_sources/shadowrun_snes_action_collision.c',
    'src/fdisbull/game_sources/shadowrun_snes_camera.c',
    'src/fdisbull/game_sources/shadowrun_snes_choice.c',
    'src/fdisbull/game_sources/shadowrun_snes_dialogue.c',
    'src/fdisbull/game_sources/shadowrun_snes_field.c',
    'src/fdisbull/game_sources/shadowrun_snes_flags.c',
    'src/fdisbull/game_sources/shadowrun_snes_interaction.c',
    'src/fdisbull/game_sources/shadowrun_snes_live.c',
    'src/fdisbull/game_sources/shadowrun_snes_macos_app.m',
    'src/fdisbull/game_sources/shadowrun_snes_menu.c',
    'src/fdisbull/game_sources/shadowrun_snes_npc.c',
    'src/fdisbull/game_sources/shadowrun_snes_opening.c',
    'src/fdisbull/game_sources/shadowrun_snes_opening_anim.c',
    'src/fdisbull/game_sources/shadowrun_snes_opening_collision.c',
    'src/fdisbull/game_sources/shadowrun_snes_opening_window.c',
    'src/fdisbull/game_sources/shadowrun_snes_scene_collision.c',
    'src/fdisbull/game_sources/shadowrun_snes_scene_init.c',
    'src/fdisbull/game_sources/shadowrun_snes_script.c',
    'src/fdisbull/game_sources/shadowrun_snes_target.c',
    'src/fdisbull/game_sources/shadowrun_snes_task_init.c',
    'src/fdisbull/game_sources/shadowrun_snes_text.c',
    'src/fdisbull/shadowrun_snes_action_collision.py',
    'src/fdisbull/shadowrun_snes_camera.py',
    'src/fdisbull/shadowrun_snes_choice.py',
    'src/fdisbull/shadowrun_snes_dialogue.py',
    'src/fdisbull/shadowrun_snes_field.py',
    'src/fdisbull/shadowrun_snes_interaction.py',
    'src/fdisbull/shadowrun_snes_live.py',
    'src/fdisbull/shadowrun_snes_macos.py',
    'src/fdisbull/shadowrun_snes_menu.py',
    'src/fdisbull/shadowrun_snes_npc.py',
    'src/fdisbull/shadowrun_snes_opening.py',
    'src/fdisbull/shadowrun_snes_opening_anim.py',
    'src/fdisbull/shadowrun_snes_opening_collision.py',
    'src/fdisbull/shadowrun_snes_opening_window.py',
    'src/fdisbull/shadowrun_snes_scene_init.py',
    'src/fdisbull/shadowrun_snes_script.py',
    'src/fdisbull/shadowrun_snes_scripted.py',
    'src/fdisbull/shadowrun_snes_target.py',
    'src/fdisbull/shadowrun_snes_task_init.py',
    'src/fdisbull/shadowrun_snes_text.py',
)

CONSOLE_GAME_EVIDENCE += (
    'docs/SHADOWRUN_SNES_TRANSITIONS.md',
    'docs/evidence/shadowrun-snes-transitions-2026-11-03/broad-regression.json',
    'docs/evidence/shadowrun-snes-transitions-2026-11-03/components.json',
    'docs/evidence/shadowrun-snes-transitions-2026-11-03/coverage.json',
    'docs/evidence/shadowrun-snes-transitions-2026-11-03/native-app.json',
    'docs/evidence/shadowrun-snes-transitions-2026-11-03/native-contract.json',
    'docs/evidence/shadowrun-snes-transitions-2026-11-03/original-routes.json',
    'docs/evidence/shadowrun-snes-transitions-2026-11-03/prefix-comparison.json',
    'docs/evidence/shadowrun-snes-transitions-2026-11-03/regression.json',
    'docs/SHADOWRUN_SNES_OPENING.md',
    'docs/SHADOWRUN_SNES_INTERACTIONS.md',
    'docs/evidence/shadowrun-snes-interactions-2026-11-03/broad-regression.json',
    'docs/evidence/shadowrun-snes-interactions-2026-11-03/cancellation-comparison.json',
    'docs/evidence/shadowrun-snes-interactions-2026-11-03/coverage.json',
    'docs/evidence/shadowrun-snes-interactions-2026-11-03/door-comparison.json',
    'docs/evidence/shadowrun-snes-interactions-2026-11-03/native-app.json',
    'docs/evidence/shadowrun-snes-interactions-2026-11-03/native-contract.json',
    'docs/evidence/shadowrun-snes-interactions-2026-11-03/opening-comparison.json',
    'docs/evidence/shadowrun-snes-interactions-2026-11-03/patch-comparison.json',
    'docs/evidence/shadowrun-snes-interactions-2026-11-03/repeat-comparison.json',
    'docs/evidence/shadowrun-snes-interactions-2026-11-03/scalpel-comparison.json',
    'docs/evidence/shadowrun-snes-interactions-2026-11-03/scripted-comparison.json',
    'docs/evidence/shadowrun-snes-opening-2026-11-03/broad-regression.json',
    'docs/evidence/shadowrun-snes-opening-2026-11-03/components.json',
    'docs/evidence/shadowrun-snes-opening-2026-11-03/native-app.json',
    'docs/evidence/shadowrun-snes-opening-2026-11-03/native-refusal.json',
    'docs/evidence/shadowrun-snes-opening-2026-11-03/observer-neutrality.json',
    'docs/evidence/shadowrun-snes-opening-2026-11-03/opening-comparison.json',
    'docs/evidence/shadowrun-snes-opening-2026-11-03/scripted-profile-regression.json',
)

CONSOLE_GAME_HELPERS += (
    'scripts/check_shadowrun_snes_interactions.py',
    'scripts/check_shadowrun_snes_opening.py',
    'scripts/snes9x_controller_adapter.py',
    'scripts/snes9x_checkpoint_adapter.py',
    'scripts/snes9x_trace_adapter.py',
)

REQUIRED_SOURCE_FILES += CONSOLE_GAME_RESOURCES + CONSOLE_GAME_HELPERS + CONSOLE_GAME_EVIDENCE


def source_archive(path,files=REQUIRED_SOURCE_FILES):
    with zipfile.ZipFile(path,'w') as output:
        for required in files:output.writestr('fdisbull-test/'+required,'')


@pytest.mark.parametrize('required', ROM_ASM_RESOURCES)
def test_distribution_requires_rom_asm_resources(tmp_path, required):
    check=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/check_dist.py'))['check_archive']
    archive=tmp_path/'fdisbull-missing-rom-asm.zip'
    source_archive(archive,tuple(path for path in REQUIRED_SOURCE_FILES if path!=required))
    with pytest.raises(ValueError,match=re.escape(required)):
        check(archive)


@pytest.mark.parametrize('unwanted',[
    'local.fdb','local.fdb-wal','local.db','local.sqlite','local.sqlite3',
    'checkpoint.sav','checkpoint.STATE','GAME.EXE','GAME.COM','VARS.DAT',
])
def test_distribution_check_rejects_game_state_and_database_files(tmp_path,unwanted):
    check=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/check_dist.py'))['check_archive']
    archive=tmp_path/'fdisbull-test-tool.zip'
    source_archive(archive)
    assert check(archive)==len(REQUIRED_SOURCE_FILES)
    with zipfile.ZipFile(archive,'a') as output:
        output.writestr('fdisbull-test/docs/'+unwanted,'local bytes')
    with pytest.raises(ValueError,match='Excluded binary/data file'):
        check(archive)


def test_distribution_check_requires_methodology_reference(tmp_path):
    check=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/check_dist.py'))['check_archive']
    archive=tmp_path/'fdisbull-missing-methodology.zip'
    methodology='src/fdisbull/skills/fdisbull-investigate/references/methodology.md'
    source_archive(archive,tuple(path for path in REQUIRED_SOURCE_FILES if path!=methodology))
    with pytest.raises(ValueError,match='methodology[.]md'):
        check(archive)


@pytest.mark.parametrize('required', CONSOLE_GAME_RESOURCES + CONSOLE_GAME_HELPERS + CONSOLE_GAME_EVIDENCE)
def test_distribution_requires_complete_console_compiler_and_evidence(tmp_path, required):
    check = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/check_dist.py'))['check_archive']
    archive = tmp_path / 'fdisbull-missing-console.zip'
    source_archive(archive, tuple(path for path in REQUIRED_SOURCE_FILES if path != required))
    with pytest.raises(ValueError, match=re.escape(required)):
        check(archive)


@pytest.mark.parametrize('required', CONSOLE_GAME_RESOURCES)
def test_core_wheel_requires_installed_console_compiler_sources(tmp_path, required):
    checker = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/check_dist.py'))
    resources = checker['REQUIRED_PE_RESOURCES'] | checker['REQUIRED_KNOWLEDGE_RESOURCES'] | checker['REQUIRED_CONSOLE_RESOURCES']
    missing = required.removeprefix('src/')
    archive = tmp_path / 'fdisbull-test.whl'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('fdisbull-test.dist-info/METADATA', 'Name: fdisbull\n')
        output.writestr('fdisbull/__init__.py', '')
        for name in resources:
            path = 'fdisbull/' + name
            if path != missing:
                output.writestr(path, '')
    with pytest.raises(ValueError, match=re.escape(missing)):
        checker['check_archive'](archive)


@pytest.mark.parametrize('suffix', ['nes', 'rom', 'gen', 'smd', 'iso', 'cue', 'wav', 'pcm',
                                    'lut', '4bpp', 'slz', 'sona', 'swav', 'spat', 'tfi', 'chr'])
def test_distribution_rejects_console_roms_and_derived_assets(tmp_path, suffix):
    check = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/check_dist.py'))['check_archive']
    archive = tmp_path / 'fdisbull-private-asset.zip'
    source_archive(archive)
    with zipfile.ZipFile(archive, 'a') as output:
        output.writestr('fdisbull-test/src/fdisbull/game_sources/private.' + suffix, 'retained private bytes')
    with pytest.raises(ValueError, match='Excluded binary/data file'):
        check(archive)


def test_distribution_check_requires_runtime_navigation_reference(tmp_path):
    check=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/check_dist.py'))['check_archive']
    archive=tmp_path/'fdisbull-missing-runtime-navigation.zip'
    reference='src/fdisbull/skills/fdisbull-investigate/references/runtime-navigation.md'
    source_archive(archive,tuple(path for path in REQUIRED_SOURCE_FILES if path!=reference))
    with pytest.raises(ValueError,match='runtime-navigation[.]md'):
        check(archive)


@pytest.mark.parametrize('required',[
    'AGENTS.md','CLAUDE.md','docs/AGENT_QUICKSTART.md',
    'src/fdisbull/skills/fdisbull-investigate/references/workflows.md',
    'src/fdisbull/skills/fdisbull-investigate/references/analysis-approach.md',
    'src/fdisbull/skills/fdisbull-investigate/references/udl-uil-udc.md',
    'src/fdisbull/skills/fdisbull-investigate/references/semantic-contracts.md',
    'src/fdisbull/skills/fdisbull-investigate/references/formats-and-media.md',
    'src/fdisbull/skills/fdisbull-investigate/references/media-modules.md',
    'src/fdisbull/media.py',
    'tests/test_media_modules.py',
])
def test_distribution_check_requires_agent_onboarding_resources(tmp_path,required):
    check=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/check_dist.py'))['check_archive']
    archive=tmp_path/'fdisbull-missing-agent-resource.zip'
    source_archive(archive,tuple(path for path in REQUIRED_SOURCE_FILES if path!=required))
    with pytest.raises(ValueError,match=re.escape(required)):
        check(archive)


@pytest.mark.parametrize('required',GAMEFAQS_SKILL_FILES)
def test_distribution_check_requires_complete_gamefaqs_skill(tmp_path,required):
    check=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/check_dist.py'))['check_archive']
    archive=tmp_path/'fdisbull-missing-gamefaqs-resource.zip'
    source_archive(archive,tuple(path for path in REQUIRED_SOURCE_FILES if path!=required))
    with pytest.raises(ValueError,match=re.escape(required)):
        check(archive)


def test_release_allowlists_include_only_the_public_udc_and_output_receipts():
    root = Path(__file__).resolve().parents[1]
    build = runpy.run_path(str(root/'scripts/build_release.py'))
    selected = {path.relative_to(root).as_posix() for path in build['release_files'](root)}
    assert set(ROM_ASM_RESOURCES) <= selected
    assert {path for path in selected if path.startswith('docs/evidence/udc-2026-10-29/')} == UDC_EVIDENCE_FILES

    manifest_lines = (root/'MANIFEST.in').read_text().splitlines()
    manifest_receipts = {line.removeprefix('include ') for line in manifest_lines
                         if line.startswith('include docs/evidence/udc-2026-10-29/')}
    assert manifest_receipts == UDC_EVIDENCE_FILES
    assert all((root/path).is_file() for path in UDC_EVIDENCE_FILES)
    assert {path for path in selected if path.startswith('docs/evidence/output-024/')} == OUTPUT_EVIDENCE_FILES
    output_receipts = {line.removeprefix('include ') for line in manifest_lines
                       if line.startswith('include docs/evidence/output-024/')}
    assert output_receipts == OUTPUT_EVIDENCE_FILES
    assert all((root/path).is_file() for path in OUTPUT_EVIDENCE_FILES)
    assert set(CONSOLE_GAME_RESOURCES + CONSOLE_GAME_HELPERS + CONSOLE_GAME_EVIDENCE) <= selected
    assert all((root / path).is_file() for path in CONSOLE_GAME_RESOURCES + CONSOLE_GAME_HELPERS + CONSOLE_GAME_EVIDENCE)


def test_shadowrun_play_evidence_selection_covers_flat_and_release_receipts():
    root = Path(__file__).resolve().parents[1]
    build = runpy.run_path(str(root / 'scripts/build_release.py'))
    checker = runpy.run_path(str(root / 'scripts/check_dist.py'))
    flat = 'docs/evidence/shadowrun-assisted-original-b-target.json'
    directory = 'docs/evidence/shadowrun-play-2026-11-01'
    manifest = (root / 'MANIFEST.in').read_text().splitlines()
    assert 'include ' + flat in manifest
    assert 'recursive-include ' + directory + ' *.json' in manifest
    assert ('docs/evidence', 'shadowrun-assisted-original-b-target.json') in build['SOURCE_PATTERNS']
    assert (directory, '*.json') in build['SOURCE_PATTERNS']
    assert flat in checker['REQUIRED_SOURCE_EVIDENCE']
    selected = {path.relative_to(root).as_posix() for path in build['release_files'](root)}
    assert flat in selected
    assert {p.relative_to(root).as_posix() for p in (root / directory).rglob('*.json') if p.is_file()} <= selected


def test_core_wheel_requires_analysis_approach_reference(tmp_path):
    checker = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/check_dist.py'))
    resources = checker['REQUIRED_PE_RESOURCES'] | checker['REQUIRED_KNOWLEDGE_RESOURCES'] | checker['REQUIRED_CONSOLE_RESOURCES']
    missing = 'fdisbull/skills/fdisbull-investigate/references/analysis-approach.md'
    archive = tmp_path / 'fdisbull-test.whl'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('fdisbull-test.dist-info/METADATA', 'Name: fdisbull\n')
        output.writestr('fdisbull/__init__.py', '')
        for name in resources:
            path = 'fdisbull/' + name
            if path != missing:
                output.writestr(path, '')
    with pytest.raises(ValueError, match='analysis-approach[.]md'):
        checker['check_archive'](archive)
