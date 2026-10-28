# Release status checked on 2026-10-28

## 0.20.0 source finalization

PR #12 is merged. The final source includes the local AGI filesystem-test correction, public Police Quest verifier, API documentation, and a Linux Python 3.13.5 offline kit builder that requires genuine Z3. The native workflow builds the corresponding backend source companion, installs the kit offline, and tests Z3 plus a real authored DOS save/restore session. See [0.20 release notes](RELEASE-0.20.0.md).

The exact final main commit must pass ordinary and native Linux CI before its annotated tag is created. The tag and CI artifacts are distinct from GitHub release publication. Shared system commands continue selecting published 0.19.0 until a separate installation promotion. Game files, native states and databases remain excluded.

## Published 0.19.0 and shared Mac installation

[0.19.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.19.0),
not draft or prerelease, at fixed tag source `57824bd9a06c7f25f6a25172b3f4dcb4dfcfdc95`.
Both final-commit workflows passed before tagging and both tag workflows passed.
Tag CI recorded 1,112 ordinary tests (91 skipped), 66 stable DOSBox, 372 layers
(Python 3.13.5), 16 PE64 and 13 DOS/QEMU/boot checks; no native failures, errors
or skips. All 105 wheel entries match the native-tested wheel. Five published
assets passed download/hash readback.

The shared `current` selector now activates `releases/0.19.0-57824bd`. Mac
qualification passed 372 DOSBox tests, seven boot/GDB checks and three runtime
doctors with native-state restoration. The global commands and a further DOS
runtime check passed after activation; all 1,738 payload entries verified.
The 0.18.0 prefix and unrelated project work remain preserved. No game files,
saved states or project databases entered Git or the installed payload.

See the [publication record](PUBLICATION-0.19.md), [release notes](RELEASE-0.19.0.md)
and [system commands](SYSTEM_INSTALLATION.md). The [development notes](UNRELEASED-0.19.md)
retain their historical candidate/pending-CI statements. Movement/navigation and
content-readiness PR proposals remain separate from this fixed release.

## Published 0.18.0 and shared Mac installation

[0.18.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.18.0),
not draft or prerelease, at fixed source `416b64d9f4bfcf56e2876656d43f1d6a3d6cfdae`.
Both exact-commit workflows passed before tagging and on the tag. Tag CI passed
1,089 ordinary tests (72 skipped), 54 stable DOS, 335 layers (Python 3.13.5),
16 PE64 and 10 DOS/boot checks; all native suites had zero failures/errors/skips.
All 101 wheel entries match the native-tested wheel. Five published assets
were downloaded again and matched against their local bytes and GitHub digests.

The user replaced the DeepSeek delivery request with a system-wide update.
The [shared Mac installation](SYSTEM_INSTALLATION.md) is active at
`/Users/Shared/fDisBull/current`, with global CLI, managed Python and tested
DOSBox/QEMU backends. No new offline archive or DeepSeek delivery was created;
existing deliveries and project environments are preserved. Fresh no-network
Linux Python 3.13.5 passed 335 checks and 51 archive CRC checks. Fresh Mac
qualification passed 335 DOS checks, seven boot/GDB checks and DOS/QEMU and
Wine/QEMU doctors; the actual activated system also passed all three doctors,
seven boot checks and its complete 1,805-entry payload verification.

See the [publication record](PUBLICATION-0.18.md) for hashes, CI links, evidence
and limits. Game files, saved states and project databases are excluded.
The sealed original-game development evidence remains `0.18.0.dev0`.

## Published 0.17.0

[0.17.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.17.0),
not draft or prerelease, at fixed source `4f736f27fed30b4277c931428a675a692e457e76`.
Both exact-commit workflows passed before tagging and on the tag. Tag CI passed
1,079 ordinary tests (65 skipped), 38 stable DOS, 318 layers (Python 3.13.5),
16 PE64 and 10 DOS/boot checks; all native suites had zero failures/errors/skips.
All 99 wheel entry contents match the native-tested wheel. Seven published
assets were downloaded and matched against their GitHub digests and local bytes.

The [0.17 publication/delivery record](DELIVERY-0.17.md) describes the updated
Linux/DOS offline kit, complete copied Mac backends and pristine boot inputs.
Fresh no-network Linux 3.13.5 passed 318 checks and 49 state-archive CRC checks;
the actual sealed ZIP separately passed extraction, executable-mode restoration,
verification, installation and 20 keyboard/scene checks. Copied Mac acceptance
passed 318 DOS checks, seven boot/GDB checks and isolated DOS/QEMU and Wine/QEMU
doctors. Game files, native states, databases and vendor IDA servers/keys are
excluded. The source tag and package bytes remain fixed; these later publication
notes do not relabel the immutable 0.17.0.dev0 original-game evidence.

## Earlier published 0.16.0

[**0.16.0 is published**](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.16.0),
not draft or prerelease, at `e1e3fb4913d6d8fae7893c2c9b8edf364d144953`.
Both pre-tag workflows and tag workflows passed. Tag CI reported **1,077 ordinary
tests passed, 61 skipped**, plus **32 stable DOS, 312 layers (Python 3.13.5),
16 PE64 and 10 DOS/QEMU/boot checks**, without native skips. All 95 wheel entry
contents match the native-tested wheel. All seven published assets were
downloaded and matched against GitHub digests and the audited original files.

The [0.16 publication/delivery record](DELIVERY-0.16.md) documents the updated
Linux/DOS offline kit and full copied Mac delivery. Fresh no-network Linux
3.13.5 acceptance passed 312 native checks, 46 save/load archive CRC checks and
a separate clean-path verifier/install/14-check run. Copied Mac DOS passed 312
checks; DOS/QEMU and isolated Wine doctors passed. Earlier failed probes remain
explicitly preserved. Source-tag/package bytes stay fixed; these publication
notes are later records on main. Game files, captured states and databases are
excluded from Git and delivery.

## Earlier 0.14.0 publication

[v0.14.0](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.14.0)
is published, not draft or prerelease, and targets
`6a0aeb3830eb544cd744d3410881c1c951a5ffb7`. Five unchanged tag-CI assets were
downloaded again and matched against GitHub digests and local CI files.
The tag remains fixed; later publication documentation on `main` does not
change the package bytes. See the [release notes](RELEASE-0.14.0.md) and
[publication/delivery record](DELIVERY-0.14.md).

Ordinary and native Linux CI passed before tagging and on the tag.
[Tag package CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40222623197)
passed **817 tests, 45 skipped**. [Tag native CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40222623209)
passed **15 stable DOS, 38 layers/endpoint, 14 PE64 and 10 DOS/QEMU/boot checks**,
without native skips. All 84 wheel entry contents match.

The versioned full Mac/QEMU delivery and compact offline Linux/DOS kit passed
directory and ZIP integrity/exclusion checks before the latest pointers were
updated. Copied Mac gates passed 48 DOS/boot, 4 optional IDA checks and a real
Wine smoke; the clean Mac offline suite passed 51 checks. The separate Linux
x86-64 Python 3.13.5 offline installation/CLI probe passed, but native tests
reported **49 passed, 2 native-state restore CRC failures**. Those historical
failed receipts are retained; that initial probe did not qualify state restoration.
The later statefix1 and 0.16 acceptance are recorded separately above. The
reported external DeepSeek environment has not been accessed or changed.
Games, saved states, project databases and vendor IDA server/keys are excluded.
Earlier deliveries and evidence remain unchanged.

## Linux native-state correction

The separate [statefix1 offline kit](LINUX_STATE_CRC_FIX.md) corrects the original
Linux probe's native ZIP CRC failures. Its clean Python 3.13.5 build passed 52
checks; the copied kit passed 51 checks plus 6 repeated original cases, with no
failures or skips. This is a separate backend correction. The published v0.14.0 tag,
package assets and original full Mac/QEMU delivery remain unchanged. Earlier
failed receipts retain their original scope and bytes.

## Earlier published 0.13.0 release

The earlier **0.13.0** package release remains available. [v0.13.0](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.13.0) is published, not draft and not prerelease, and targets `eabfc2afb772d4cb78401893eebf15c8b0f6ad17`. Its five assets are the unchanged tag-CI wheel/sdist/tool ZIP plus `SHA256SUMS` and `VERIFICATION-0.13.0.json`. Uploaded assets were downloaded again and checked against GitHub SHA-256 digests. See [release notes](RELEASE-0.13.0.md), [verification gates](VERIFICATION-0.13.md) and [publication evidence](../experimental/wine/evidence/2026-10-24/published-0.13.0/asset-readback.json).

Both workflows passed before tagging and again on the tag. [Tag package CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40099730231) passed **769 tests, 31 skipped**. [Tag native CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40099730260) passed **15 stable DOS, 32 DOS layers and 13 PE64 tests**, with **no native skips**. All 65 wheel entry contents match between package CI and installed-wheel PE acceptance.

The [0.13 DeepSeek delivery](DELIVERY-0.13.md) contains the published packages, copied Mac ARM64 QEMU 11.1.2, firmware, kernel and matching prepared 0.13 Wine boot image. Its copied package/backend pair separately passed a 193.22-second real smoke with watches, self-CRC/layers, branch toggling, native checkpoint restore, checked memory/RAX edits, clicks/grids, traces, static isolation and offline exports. Full native fork/export/asset-list qualification is in tag CI. This is tested for this Mac with its existing Homebrew libraries; arbitrary-host portability is not claimed. Games, saved machine states and local databases are excluded, and earlier deliveries remain unchanged.

## Earlier published 0.12.0 release

The earlier **0.12.0** release remains available, described in the [release notes](RELEASE-0.12.0.md). [v0.12.0](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.12.0) is published, not draft and not prerelease, and targets `7f8c9d48e01c60a289834ad289282b572c0adad1`. The attached wheel, source distribution and tool ZIP are unchanged tag-CI outputs. Their SHA-256 hashes and exact CI/backend identities are attached as `SHA256SUMS` and `VERIFICATION-0.12.0.json`.

Both required workflows passed on the exact source commit before tagging and again on the tag. [Tag package CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40045173566) passed **764 tests, 29 skipped**. [Tag native CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40045173515) passed **15 established DOS, 32 DOS layers and 6 PE64 Wine/QEMU tests**, with **no native skips**. All 60 wheel entry contents match between package CI and real PE native acceptance. [Published verification](VERIFICATION-0.12.md) distinguishes these results from the preserved earlier development receipts.

The [0.12 DeepSeek delivery](DELIVERY-0.12.md) is in `~/Conversions/DinoParkTycoon/fdisbull-deliveries/fdisbull-0.12.0-7f8c9d4/`. Its copied Mac ARM64 QEMU 11.1.2, kernel, Wine runtime and exact published package separately passed all **6 PE tests with no skips**, including two fresh VMs, actual input, breakpoint rearming, memory editing, traces and offline exports. A matching ZIP, checksum, complete payload manifest and latest pointer are supplied. Earlier DOS deliveries and DinoPark findings are preserved. No game inputs, saved machine states or project databases enter the packages or delivery.

Publication notes on `main` do not alter the fixed release tag or its package bytes. Frozen package documentation retains the status at build time; these publication records describe the completed release.

## Earlier published 0.11.0 release

[v0.11.0](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.11.0) remains published, not draft and not prerelease, and targets commit `a2167479a6ee474e8a4e2a7965c8ef46c618df54`. Its wheel, source distribution and tool ZIP are the unmodified tag-CI outputs; `SHA256SUMS` and `VERIFICATION-0.11.0.json` remain attached with their identities and provenance.

The [tag-triggered ordinary Linux run](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40014891689) completed successfully with **759 passed and 28 skipped**, and checked all three tool packages. The [tag-triggered native Linux matrix](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40014891475) separately built and verified both pinned backend profiles: **15 passed** with the established backend and **32 passed** with the layers backend, with **no native skips**. Both workflows also passed on the same release commit before promotion and tagging. [Release verification](VERIFICATION-0.11.md) records the scope and preserved runtime evidence.

`main` is now the only GitHub and local branch. The fully merged `codex/takeover` branch was removed. The unfinished experimental checkpoint is preserved at tag `archive/dosbox-headless-2026-10-23`, targeting `7cc45b1cd0439ae0306d20a33f28f1619f13036a`, before removal of its branch. The release tag remains fixed; later README/publication documentation changes on `main` do not alter the published packages.

The earlier [DOS DeepSeek delivery](DELIVERY-0.11.md) remains in `~/Conversions/DinoParkTycoon/fdisbull-deliveries/fdisbull-0.11.0-a216747/`, with a sibling published ZIP and checksums. The exact published wheel passed all **32 focused native tests** against the tested Mac layers backend; the copied delivery pair additionally passed the **two checkpoint/marked-click tests**. Game inputs, saved states and project databases are excluded. Its payload is unchanged; `LATEST.json` now selects 0.12.0.

## Historical candidate receipts

[0.10 candidate verification](VERIFICATION-0.10.md), [candidate release notes](RELEASE-0.10.0.md), and [candidate delivery instructions](LOCAL_DELIVERY.md) describe the state at their creation. Statements there that the candidate was uncommitted or unpublished are historical, not current release status. They remain intact so their source identities and evidence are not rewritten after publication.

The earlier published 0.10.0 local delivery remains in:

```text
~/Conversions/DinoParkTycoon/fdisbull-deliveries/fdisbull-0.10.0-6ba413e/
```

Its sibling bundle is `fdisbull-native-debugger-0.10.0-published-2026-10-23-6ba413e.zip`, SHA-256 `ffc5994091662bec26e7c577d1518098bee10429a3338392f7773b088cc37146`. This is the user-designated local delivery, not a portable emulator download for arbitrary hosts. Its tested native Mac backend remains SHA-256 `e749b6e50775de2807c2515f83e455dc705cdf6ddcdfb257e781f215d987865a`.

[v0.10.0](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.10.0), commit `6ba413e2f535c6294b3ddb767a5bc12a6a388162`, remains published. Its [tag CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/39994442024) reported 756 passed and 11 skipped, without Linux native acceptance. These historical package and backend identities remain unchanged.

## 0.11 implementation and earlier local receipts

The 0.11 work adds RAM/execution layers, breakpoint actions, temporal code captures, branch helpers, virtual caves and optional screenshot coordinate grids. [Layer verification](VERIFICATION-LAYERS.md) and its immutable receipts describe the earlier `0.11.0.dev0` snapshots, including their then-uncommitted status. They record the tested Mac backend, actual game branch comparison, software self-integrity experiment and native-coordinate clicking evidence. Those earlier source identities and results remain intact.

The [native acceptance workflow](../.github/workflows/native-debugger.yml) builds both pinned backend profiles and runs the existing tests with `--require-native`. A workflow file alone is not a passing Linux result: the release commit must have successful runs for both matrix profiles. The original Python/package workflow remains a separate check. Current results are attached to the tested commit in GitHub Actions.

Runtime snapshots and alternate fetch bytes do not yet automatically create and connect a new static interpretation and its references. The current capability is explicit preservation, decoding, layer control and observation; automatic self-modified-code reanalysis remains a separate step.

## Local review and grid refinements

The latest source supports eight-pixel grid lines with readable 32-pixel labels, and a `click-frame` operation that captures, marks the selected point and queues its mode-bound click in one client request. A complete actual-DinoPark route was sent through one `debug-script` request: 35 guest seconds of intro skip, a marked `(160,160)` OLD GAME click, 1,500 guest milliseconds of execution and an after-frame showing the Load Game dialog. Both frames remain 320×200. All 192 input files and the existing `TinyDinoPark/Scripts/original/grid.py` helper stayed unchanged.

The existing tests now report **32 passed** with the layers backend and `--require-native`, and **15 passed** with the published backend. Both an absent backend variable and a nonexistent executable are rejected before collection with exit status 4. Without the new required mode, the original optional behavior was observed as 5 passed and 26 skipped, illustrating why a broad green Python run is not native acceptance.

The pre-release full Mac run with the required backend reported **759 passed, 3 skipped, 2 failed and 23 setup errors**, exit status 1. The same 25 failing/error identities match the recorded 0.10 Mac baseline. Initial `actionlint` validation checked workflow syntax only; it did not establish Linux native acceptance. [Selected follow-up evidence](../experimental/dosbox-x/layers/evidence/2026-10-23/grid8-followup/verification.json) supplements the earlier immutable receipts; the release gates use actual workflow executions for the committed release source.
