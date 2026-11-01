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
