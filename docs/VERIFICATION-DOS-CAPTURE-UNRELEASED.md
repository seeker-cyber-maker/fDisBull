# Unreleased DOS input names and screenshot hooks — 27 October 2026

This is the historical pre-integration record. A subsequent
[0.19 continuation investigation](DOS_CONTINUE_CALLBACK_FIX.md) established a
deterministic BIOS callback-loss mechanism and corrected it in both DOSBox
patch variants. The failed receipts and original claim limits below remain
unchanged; later positive qualification is recorded separately.

This record covers working-source changes after publication documentation commit
`2544b60`. The published tag and active shared 0.18.0 remain fixed at `416b64d`.
The private verification wheel retains development metadata `0.18.0`; it is not
an additional release asset or a replacement for the published package.

The [evidence manifest](evidence/dos-capture-unreleased-2026-10-27/MANIFEST.json)
binds exact source hashes, fresh native/installed-wheel XML reports, and the
four failing pre-fix reproductions. [The receipt](evidence/dos-capture-unreleased-2026-10-27/VERIFICATION.json)
records counts and limits. These are authored redistributable MZ fixtures, not
new AGI or DinoPark gameplay evidence. New hosted Linux CI remains a release gate.

## Fresh results and open gate

- Broad Mac ARM64 / Python 3.13.17 native/package selection: **377 passed,
  1 failed, no errors or skips**. The failing unchanged scene test was
  `test_relative_outcomes_repeat_restore_and_compact_saved_script`: after a
  native restore, the expected one-step counter increment was observed as two.
  The scene system correctly rejected the unmatched result. Its saved evidence
  is included without state or database bytes. This is not a green broad gate.
- Installed private candidate: **46 passed, zero skips**, covering all hook,
  alias, direct DOS debugger and deterministic pause-boundary checks. All 102
  comparable wheel entries match the actual installed package; the audit passed
  103 tool-only entries. This environment uses genuine existing dependencies.
- Final real DOS-in-QEMU alias/prepared-capture checks: **2 passed, no skips**.
- Separate PE/IDA preflight/guard checks: **14 passed**. These are not fresh PE
  runtime acceptance for the new feature; screenshot hooks remain DOS-only.
- Four new review reproductions failed against the earlier installed private
  candidate before the fixes. Corrected focused checks passed.

A declared baseline characterization ran the unchanged installed published
0.18.0, with source injection disabled, up to 20 times and stopped on its first
failure. Attempts 1–18 passed; attempt 19 timed out in an initial scene action,
before restoration. This confirms an intermittent baseline failure but does not
establish that the two failing paths have the same cause or clear the new-source
failure. The earlier passes are not qualification by repeated retries. The
broad gate remains open; new-source hosted ordinary/native CI has not run.

## Established behavior

- A structurally parsed MZ imports and runs with an extensionless `AGI`, a long
  name with spaces, `.BIN`, `.COM`, or state-like host suffix. Runtime launch
  aliases preserve source bytes/name, neighboring-resource access and native
  checkpoint reopening. DOS-in-QEMU aliases remain inside the guest. Final
  alias-expanded upload limits reject before spawning.
- Persistent, hash-checked screenshot policies suspend selected layers or
  temporarily enable a clear-color layer, execute bounded preparation, capture
  real pixels and restore the original ordered stack. The fixture verifies
  visible/hidden pixels, grids, click-frame, reopened projects, version isolation,
  post failures and failure evidence. No fake framebuffer is used.
- A completed frame must follow the last pre-hook layer change. Explicit
  freshness-only policies cannot bypass validation. Breakpoints, incomplete
  waits and hook errors cannot become successful captures.
- A final-pause race preserves the original terminal stop. Deterministic
  transport models exercise both native-supported response orderings; this is
  not a claim of reproducing every scheduling race in a real guest.
- Alias cleanup detects completed changes and atomically protects pathname
  replacements. Simultaneous writes through external open handles during
  teardown remain unsupported; the alias is disposable, not a user output file.

## Review and verification boundaries

Terra's read-only review identified late-layer freshness, explicit freshness-only
bypass, final upload-budget and alias replacement cases. Four new reproductions
failed against the earlier installed candidate, then passed against corrected
source. The pause-boundary model separately reproduced closing a stopped session
and misreporting a terminal breakpoint as guest-time completion. Both paths now
preserve the terminal result without replay or an extra continue.

Luna independently audited the earlier receipts and supervised the final
source regression. After the failure was retained, the coordinator built and
qualified a separate wheel for focused feature checks; no release was published. A first supervision attempt
failed before collection because environment assignments were omitted; its log
is retained privately and is not counted as a product test result. Earlier
source-qualification setup failures (missing native ZIP source path and missing
build tools in the deliberately minimal shared runtime) are likewise retained.
The corrected runs use genuine installed dependencies and real native backends.

The shared system installation was independently reverified after source work:
1,805 payload entries match and global `fdisbull --version` remains 0.18.0.
Existing game/project environments, sealed previous deliveries and unrelated
worktree evidence were preserved. Games, saved states, project databases,
compiled test guests and emulator runtime images are excluded from this evidence
and from proposed source additions. Only tool source, tests, docs and structured
verification reports are prepared here. No new DeepSeek delivery was made.
