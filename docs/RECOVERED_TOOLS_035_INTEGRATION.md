# Recovered tooling and documentation — 0.35 source integration

This record maps preserved contributions to current source. Historical reports and
proposals retain their dates and original qualification limits. Importing their
text is not new native execution, package acceptance, installation or publication.
No Drive watcher/service is installed or started by this source integration.

## Preserved source origins

- `b3f9dead` → `scripts/drive_library_sync.py`
- `b3f9dead` → `scripts/drive_sync_watcher.swift`
- `b3f9dead` → `scripts/fdb_backup.py`
- `b3f9dead` → `tests/test_drive_library_sync.py`
- `b3f9dead` → `tests/test_fdb_backup.py`
- `b3f9dead` → `docs/DRIVE_SYNC.md`
- `bc1bcee6` → `src/fdisbull/debug_fuzz.py`
- `bc1bcee6` → `src/fdisbull/debug_fuzz_native.py`
- `bc1bcee6` → `tests/test_debug_fuzz.py`
- `bc1bcee6` → `tests/test_debug_fuzz_native.py`
- `d2d78717` → `src/fdisbull/agent_friction.py`
- `d2d78717` → `tests/test_agent_friction.py`
- `d2d78717` → `docs/AGENT_FRICTION_HARNESS_PILOT.md`
- `d2d78717` → `src/fdisbull/skills/fdisbull-investigate/references/friction-to-feature.md`
- `d2d78717` → `docs/THREAD_REVIEW_COMPILER_INFLUENCE_HARNESS_20261110.md`
- `d87ae33e` → `scripts/check_native_crash_recovery.py`
- `d87ae33e` → `docs/CRASH_REPLAY.md`
- `e795a9ff` → `src/fdisbull/rtlink.py`
- `e795a9ff` → `src/fdisbull/dos_launch_profile.py`
- `e795a9ff` → `src/fdisbull/dos_tools.py`
- `e795a9ff` → `tests/test_dos_launch_profile.py`
- `e795a9ff` → `tests/test_dos_launch_profile_native.py`
- `e795a9ff` → `tests/test_dos_tools_delivery.py`
- `e795a9ff` → `tests/test_rtlink.py`
- `e795a9ff` → `docs/DOS_FORMATS_AND_RTLINK.md`
- `09ab554c` → `docs/SWEDING.md`
- `09ab554c` → `tests/test_sweding_examples.py`
- `464bdc5c` → `docs/FACTORIO_PYTHON_MEDIA_BOUNDARY.md`
- `5d9118ae` → `docs/DINOPARK_SAVE_TRAVEL_FEEDBACK.md`
- `641b7e95` → `docs/DIAGNOSTIC_RECOVERY_STUDY_2026-10-30.md`
- `874f0a8b` → `docs/evidence/desqview-checkpoint-public-cold-reopen-2026-11-14/README.md`
- `874f0a8b` → `docs/evidence/desqview-checkpoint-public-cold-reopen-2026-11-14/verification.json`
- `b57f51d5` → `docs/XCOM_TFTD_ENTITY_STATE_CONTINUATION_2026-11-05.md`
- `cbeb6ce6` → `docs/uil-rfcs/0002/AGENT_FIRST_TOPOLOGY.md`
- `cbeb6ce6` → `docs/uil-rfcs/0002/ILLUSTRATION_NOTES.md`
- `cbeb6ce6` → `docs/uil-rfcs/0002/LABELS_ORCHESTRATION_AND_ROUNDTRIPS.md`
- `cbeb6ce6` → `docs/uil-rfcs/0002/PIPELINE_MAP.md`
- `cbeb6ce6` → `docs/uil-rfcs/0002/RESEARCH_AND_VERIFICATION.md`
- `cbeb6ce6` → `docs/uil-rfcs/0002/SEMANTIC_PORTS_AND_SERVICES.md`
- `cbeb6ce6` → `docs/uil-rfcs/0002/check_component_witnesses.py`
- `cbeb6ce6` → `docs/uil-rfcs/0002/component-witness-results.json`
- `cbeb6ce6` → `docs/uil-rfcs/0002/pipeline-map.mmd`
- `da5f55a0` → `docs/FF7_GAMEFAQS_LOCALIZATION_CASE_STUDY.md`
- `f8a70aad` → `docs/UDC_MODULE_LAYERS.md`

## Current source behavior and remaining qualification gates

- `fdisbull fuzz CONFIG` supplies a finite Windows route campaign with a private
  source-bound configuration. Pure tests substitute adapters; no Wine/native guest
  was launched for this integration. The capability entry stays experimental.
- `fdisbull-dos` is an additive console entry for bounded RTLink inspection,
  private bank export/disassembly, and existing debugger launch with bounded ASCII
  argument tokens and an explicit validated read-only Mode-1 CD input. It does not
  flatten RTLink banks into a runnable executable or change the canonical loader.
- The Drive helper scripts and FSEvents Swift source are included for review and
  explicit use. No helper is installed, scheduled or activated by this change.
- DOSBox headless launch forces noninteractive video/audio settings; a finalizer
  reaps only its owned process and descriptors. EOF retains a bounded native-log
  tail. Shutdown receipts distinguish terminal host ownership from confirmed guest
  exit and a clean reaped process; interrupted cleanup remains an explicit failure.
- Generic DOSBox RPC tracking invalidates source lifetimes before mutations and
  observes stopped/exit responses without recursive observer reads. Startup
  attachment requires the native `lifecycle.dos_guest_exit` capability. Existing
  QEMU tracker/provider/containment implementation remains the owner there.
- Stable and layers DOSBox cleanup patches were composed against pinned upstream
  `029bd65c5dcc7cdc7f2e14e35278620d9707d969` and their full postimage manifests
  checked without compilation. Unified CI consumes the existing layers source
  profile; the QEMU9.2.4 patch/build contract is unchanged. A fresh matching DOSBox
  backend build and native qualification are still required by n8n; retained older
  helper identities cannot qualify the changed patch.

## CI ownership conflict disposition

`263cfcca` itself adds zlib headers; its older branch also contains `a896955c`
(removal of a commit-message skip-marker veto for deliberate GitLab web/API runs)
and `1b0a05e9` (manual-only policy tests). Existing automation deliberately prevents
push/MR/tag fan-out and uses GitLab `ci.skip` on mirrored source. This integration
changes no active workflow. n8n owns the explicit reconciliation in `be68826e`;
the two semantic choices must remain separate: mirror/push suppression and deliberate
operator/API dispatch after a skipped source commit. Zlib is already in current
native dependency preparation. No pipeline was dispatched or polled here.

## Exact contribution mapping

See the [source integration record](evidence/recovered-tools-035-20261114/source-integration.json)
for all23 original heads, ported behavior, historical-only dispositions, focused
checks and both DOSBox patch identities. It explicitly retains the combined
capability-catalog wire-size gate for the final integration owner.

## Focused validation

The final pure/source regression selection passed336 tests with6 native-input skips.
The source environment was explicit (`PYTHONPATH=src`), so subprocess checks used
the candidate rather than a system installation. This is separate from required
exact-SHA Linux/native/offline package qualification. The combined capability
wire-size test remains an explicitly recorded integration-owner issue.
