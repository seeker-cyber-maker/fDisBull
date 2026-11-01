# Release status checked on 2026-11-01 (America/New_York)

## 0.29.0 published on GitLab; local shared installation active

`v0.29.0` is an annotated GitLab tag and GitLab Release at this commit. The
local candidate was promoted at user direction; hosted Linux CI, the hosted
native matrix and the macOS backend rebuild remain pending and are explicitly
not claimed.

Package bytes are published under two generic packages:

- `fdisbull-tool-packages` `0.29.0-20261101` (wheel, player wheel, sdist, tool
  ZIP);
- `fdisbull-release-packages` `0.29.0-20261101` (offline kit, dependency kit,
  source companion, dependency checksum, `SHA256SUMS`, `BUILD.json`).

All ten remote files were downloaded and SHA-256 matched the local delivery.
The release branch is `release/0.29.0`; the package build source is
`c03dc4f9d4b5b9d0b374f6423e21962bfb0b07c9`.

The shared selector `/Users/Shared/fDisBull/current` points to
`releases/0.29.0-c03dc4f` at source
`c03dc4f9d4b5b9d0b374f6423e21962bfb0b07c9`. `INSTALLATION.json` records
`active_verified`; the complete 3,221-entry payload passed before and after
activation.

The fresh Python 3.13.18 prefix passed **818 installed-package tests** with no
failures, errors or skips. DOSBox, DOS-in-QEMU and Wine/QEMU doctors passed
native-state restoration; the global DOSBox alias also passed. The installed
player restored `hall`/`key` state across two fresh processes. The backend was
inherited from the 0.28.0 prefix by an APFS clone; it was requalified, not
rebuilt. The 0.28.0 prefix and guarded rollback helper remain available, and
rollback preflight was checked without switching.

These checks qualify this host and prefix only. Historical published entries
below describe their own source cuts. See
[installation](SYSTEM_INSTALLATION.md), [release notes](RELEASE-0.29.0.md), and
the [candidate evidence](evidence/0.29.0-release/README.md).

---

# Release status checked on 2026-10-30 (America/New_York)

## Published 0.25.0 and active shared installation

[0.25.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.25.0) at annotated tag `v0.25.0`, source `70eb4e38bf4bf8d47e52e38b8fab6a6cd718f15e`. Both main workflows passed before tagging. Tag ordinary CI passed 1,919 tests (103 skipped); complete tag native CI passed 779 stable-DOS, 1,090 layers-DOS, 16 PE64 and 13 DOS/boot tests without native failures, errors or skips. The genuine-Z3 offline kit and both installed skills passed. All eight public assets passed unauthenticated download/hash readback.

The shared selector now selects `releases/0.25.0-70eb4e3`. Its installed gate passed 1,107 tests, the three native runtime doctors passed with restore, and all 3,040 sealed payload entries passed. Global aliases/player persistence and the qualified Zork continuation were checked after activation. The 0.24 prefix and wrappers remain available for guarded rollback. Game files, native states and project databases stayed outside Git and delivery.

See [publication evidence](PUBLICATION-0.25.md), [installation commands](SYSTEM_INSTALLATION.md), [source verification and limits](VERIFICATION-0.25.md), and the [remaining PR requirements](PR_BACKLOG.md). The following older status entries are historical; their pending or current-version statements describe their respective source cuts.

---

# Release status checked on 2026-10-28 (America/New_York)

## Published 0.21.0 and activated shared Mac installation

[0.21.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.21.0)
at fixed source `a253600b94f7006f8962ada842eba699279fdbfe`. The exact-source
[ordinary tag workflow](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40801426999)
passed 1,333 tests with 100 skips. The [tag-native workflow](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40801427016)
passed 218 stable-backend, 529 layers-backend, 16 installed-wheel PE64, and 13
DOS-in-QEMU/boot-context tests. There were zero native failures, errors, or
skips. The layers job also built and verified the Linux x86-64 offline kit with
genuine Z3. Eight public assets were downloaded and matched against their
GitHub SHA-256 digests.

The shared selector at `/Users/Shared/fDisBull/current` now selects
`releases/0.21.0-a253600`. The sealed installed payload contains 2,430 entries;
Mac installed-wheel qualification passed 546 tests with zero skips, and the DOS,
DOS/QEMU, and Wine/QEMU runtime doctors passed with native-state restoration.
After activation, the global DOS doctor and global `fdisbull-player` checks for
cross-process save/resume passed. Core and standalone-player global Python entry
points resolve to 0.21.0. The former `releases/0.20.0-4f7791b` prefix remains
available through `current/share/rollback-to-0.20.py`; rollback was preflight-checked without changing the active selection. Existing projects and captured
states were preserved.

The Mac checks qualify this host's installed prefix only. They do not establish
portability to other macOS machines; interactive dot-mode remains unqualified.
No full AGI interpreter or UIL/world equivalence is claimed. Voice remains
future work: local Qwen TTS availability is user-reported, while speech
recognition and a complete voice interaction are unqualified. No new DeepSeek
delivery was made.

See the [publication record](PUBLICATION-0.21.md) for the eight asset hashes,
CI identities, installation evidence, and scope limits. The evidence manifest
is [here](../experimental/remote-debugger/evidence/2026-10-28-published-0.21/MANIFEST.json).
The frozen tag/source-finalization snapshots remain documented in the
[candidate record](UNRELEASED-0.21.md), [release notes](RELEASE-0.21.0.md), and
[verification record](VERIFICATION-0.21.md); those historical pending statements
do not describe the current published/default state.

### Historical 0.21.0 source finalization and release gates

The following paragraphs describe the 0.21.0 source-finalization snapshot,
before exact-commit CI and promotion. Their pending statements are historical;
the current published and activated state is recorded above.

The 0.21.0 source candidate adds progressive scene workflows, a separate text
player, automatic turn persistence, bounded story sessions and qualified
assisted travel. Its feature scope and current bounded
evidence are in the [release notes](RELEASE-0.21.0.md),
[candidate record](UNRELEASED-0.21.md) and
[verification record](VERIFICATION-0.21.md). This preparation record precedes the
exact-commit CI readback and tag. Publication and shared-system activation are
separate actions; the latest published and installed release remains 0.20.0 below.

Promotion requires both the ordinary Linux workflow and native Linux workflow
to pass on the exact final source commit before tagging. Workflow configuration
is a gate definition, not run evidence. The completed workflow and commit
identities are recorded in GitHub Actions and the annotated release tag after readback. macOS development-host results do
not replace Linux CI, and no system installation or package publication is
implied by candidate verification.

## Previous published 0.20.0: earlier shared Mac installation

This records the 0.20.0 publication and activation as they stood then; 0.21.0
above is the current published and activated release.

[0.20.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.20.0) at fixed source `4f7791baa2cca7bb3c62fc9a997dc8f86316c98d`.
Both main workflows passed before tagging; both complete tag workflows also
passed. Tag results are 1,236 ordinary checks (98 skipped), 109 stable DOSBox,
415 layers, 16 PE64 and 13 DOS/QEMU/boot checks, with zero native skips. Seven
assets, including the genuine Z3 offline kit and corresponding backend source,
passed public download/hash readback.

At that time, the shared selector activated `releases/0.20.0-4f7791b`. Qualification passed
415 installed-wheel Mac DOSBox checks, seven boot/GDB checks, nine proof checks,
and three runtime doctors with native-state restoration. Global commands and a
further direct-DOS doctor passed after activation. The complete 1796-entry
payload verified. The 0.19.0 prefix remains available for guarded rollback;
private projects, game files and captured states were preserved.

See the [publication record](PUBLICATION-0.20.md), [release notes](RELEASE-0.20.0.md)
and [system commands](SYSTEM_INSTALLATION.md). Future proof/world/intent RFCs
remain separate from this fixed implementation release.

## Published 0.19.0 and shared Mac installation

This section records the earlier publication and activation, superseded by 0.20.0 above.

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
