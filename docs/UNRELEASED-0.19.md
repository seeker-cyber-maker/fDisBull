# fDisBull 0.19.0.dev0 — integrated development source

This is working source after fixed release `v0.18.0` (`416b64d`) and its
publication documentation (`2544b60`). It is not a new tag, published release or
replacement shared installation. The explicit development version distinguishes
candidate wheels from the existing published 0.18.0 assets.

## Implemented changes

- [Structure-based DOS target eligibility and guarded launch aliases](DOS_INPUT_NAMES.md)
  support extensionless/long host names while preserving source identity,
  neighboring resources and native checkpoint reopening. QEMU uploads include
  alias bytes in their preflight limits.
- [Persistent screenshot pre/post scripts](SCREENSHOT_HOOKS.md) suspend or
  temporarily enable rendering layers, verify a frame after the last pre-hook
  layer change, preserve unexpected stops and restore the original layer stack
  even on failure. These hooks currently support DOS, not PE64/raw machines.
- The final bounded-run pause path preserves a terminal stop that wins its race
  with the budget pause. It observes the existing operation without replay or
  another continue.
- Both DOSBox source patch variants include [callback-safe continuation](DOS_CONTINUE_CALLBACK_FIX.md).
  Resuming at the BIOS keyboard callback no longer skips the handler and
  returns a stale key value. A forced-boundary regression fails on the old
  backend and passes on the corrected builds, including checkpoint restoration.
- The bundled investigation skill returns its entrypoint plus scene,
  methodology and runtime-navigation references, with package-closure checks.
  Cost/reward and confidence remain separate decision criteria.
- Combined keyboard regressions cover mid-dialog same/fresh-process restoration
  and delayed modifier polling. These tests do not establish a production
  keyboard repair or justify changing input-duration defaults.

## Locally integrated PR source

The working tree includes reviewed changes from PRs #2 and #8 for the skill,
#3 for UIL ownership/RFC design, #4 for keyboard sampling, #5 for UI capture
boundaries, #6 for the PQ1 runtime-resource finding, and #1 for keyboard restore
coverage. These are locally reconciled source changes; the GitHub PRs have not
been merged by this integration. PR #7 remains a separate draft stacked on #3.

New skill functionality belongs here, not in the immutable 0.18 release notes.
The historical native failure on PR #2 remains evidence; later green CI does not
diagnose that failure or qualify this combined checkout automatically.

## Proposed work remains distinct

[UI capture boundaries](UI_CAPTURE_BOUNDARIES.md) distinguish post-dispatch,
post-state, post-interface and post-persistence evidence. Current pre/post hooks
prepare/clean up a capture; they do not automatically infer those application
phases or prove control readiness from a new frame alone.

[PQ1 resource layers](PQ1_RUNTIME_RESOURCE_LAYER_FINDING.md) need a separate
runtime resource identity/resolver for heap-loaded bytes. Imported-MZ static
region guards remain intact. The [navigation capability ladder](PQ1_CONDITIONAL_NAVIGATION_FINDING.md)
records supported observations and future capabilities; it does not supply an
AGI adapter, semantic resolver, conditional heap watch or teleport API.

The [UIL export boundary](UIL_BOUNDARY.md) and [RFC process](UIL_RFC_PROCESS.md)
remain design documents. No UIL exporter/runtime, C/C++ decompiler or source-view
debugger is implemented by this integration.

## Verification gate

Earlier [capture/alias qualification](VERIFICATION-DOS-CAPTURE-UNRELEASED.md)
records positive focused/installed-wheel checks and a broad native scene test
failure. The unchanged published package also failed that test under a separate
bounded baseline characterization. Its cause was not established by retries.

The combined development source needs fresh package, ordinary Linux and native
Linux verification before a release tag or shared-installation promotion.
Mac qualification of the corrected backends passed **386 layers** and
**66 stable** checks with no failures/errors/skips. All three development
package formats passed the tool-only audit (105 wheel, 287 tool ZIP, 295 sdist
entries). The initial Linux ordinary qualification inherited stale helper/source
files; its failed mixed-source run is retained separately from the corrected
qualification rather than counted as a package pass.
The corrected, network-disabled Linux x86-64 / Python 3.13.5 qualification passed
**1,112 ordinary tests, 91 native-dependent skips**, with no failures/errors.
All 105 wheel entry contents match the separately built Mac qualification wheel.
An independently installed Mac candidate passed **66 focused native checks**.
These local results are distinct from the pending hosted ordinary/native CI.
Original game inputs, native saved states, project databases and vendor IDA
executables/keys remain excluded. Existing deliveries and unrelated work remain
preserved.
