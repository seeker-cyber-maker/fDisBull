"""Check the release guard with hostile additions to an otherwise valid archive."""
from pathlib import Path
import re
import runpy
import zipfile

import pytest


REQUIRED_SOURCE_FILES=('AGENTS.md','CLAUDE.md','docs/AGENT_QUICKSTART.md','docs/MACOS_ARM64_ANALYSIS.md',
                       'docs/CAPABILITIES.md','docs/MACOS_APP_REPLICATION.md',
                       'src/fdisbull/capabilities.py','tests/test_capabilities.py',
                       'scripts/check_agent_skill.py',
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
                       'src/fdisbull/ghidra_arm64.py','src/fdisbull/macos_lldb.py',
                       'src/fdisbull/_macos_lldb_driver.py','src/fdisbull/data/FdisbullGhidraArm64.txt',
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
REQUIRED_SOURCE_FILES += ('tests/fixtures/frame_capture.S',
                          'docs/verification/kq1-tas-2026-10-31.json')
REQUIRED_SOURCE_FILES += ('src/fdisbull/capture_audit.py', 'tests/test_capture_audit.py')
REQUIRED_SOURCE_FILES += ('tests/fixtures_common_uil.py',)
REQUIRED_SOURCE_FILES += ('docs/evidence/common-uil-2026-11-01/verification.json',)
REQUIRED_SOURCE_FILES += ('tests/fixtures_common_uil_native.py', 'docs/evidence/common-uil-native-2026-11-01/verification.json')


def source_archive(path,files=REQUIRED_SOURCE_FILES):
    with zipfile.ZipFile(path,'w') as output:
        for required in files:output.writestr('fdisbull-test/'+required,'')


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


def test_distribution_check_requires_runtime_navigation_reference(tmp_path):
    check=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/check_dist.py'))['check_archive']
    archive=tmp_path/'fdisbull-missing-runtime-navigation.zip'
    reference='src/fdisbull/skills/fdisbull-investigate/references/runtime-navigation.md'
    source_archive(archive,tuple(path for path in REQUIRED_SOURCE_FILES if path!=reference))
    with pytest.raises(ValueError,match='runtime-navigation[.]md'):
        check(archive)


@pytest.mark.parametrize('required',[
    'AGENTS.md','CLAUDE.md','docs/AGENT_QUICKSTART.md','docs/MACOS_ARM64_ANALYSIS.md',
    'docs/CAPABILITIES.md','docs/MACOS_APP_REPLICATION.md',
    'src/fdisbull/capabilities.py','tests/test_capabilities.py',
    'src/fdisbull/skills/fdisbull-investigate/references/workflows.md',
    'src/fdisbull/skills/fdisbull-investigate/references/udl-uil-udc.md',
    'src/fdisbull/skills/fdisbull-investigate/references/semantic-contracts.md',
    'src/fdisbull/skills/fdisbull-investigate/references/formats-and-media.md',
    'src/fdisbull/skills/fdisbull-investigate/references/media-modules.md',
    'src/fdisbull/media.py',
    'tests/test_media_modules.py',
    'src/fdisbull/data/FdisbullGhidraArm64.txt',
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
