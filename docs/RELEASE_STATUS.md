# Release status checked on 2026-10-23

The current source is **0.12.0**, described in the [release notes](RELEASE-0.12.0.md). Promotion requires successful ordinary Linux and native Linux workflows on the exact source commit before tagging. The native workflow now also requires the installed-wheel PE64 Wine/QEMU acceptance in addition to both DOSBox profiles. [PE64 verification](PE64_VERIFICATION.md) preserves the earlier local development receipts separately from these release gates.

The latest published GitHub package release is **0.11.0**. [v0.11.0](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.11.0) is published, not draft and not prerelease, and targets commit `a2167479a6ee474e8a4e2a7965c8ef46c618df54`. Its wheel, source distribution and tool ZIP are the unmodified tag-CI outputs; `SHA256SUMS` and `VERIFICATION-0.11.0.json` are attached with their identities and provenance.

The [tag-triggered ordinary Linux run](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40014891689) completed successfully with **759 passed and 28 skipped**, and checked all three tool packages. The [tag-triggered native Linux matrix](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40014891475) separately built and verified both pinned backend profiles: **15 passed** with the established backend and **32 passed** with the layers backend, with **no native skips**. Both workflows also passed on the same release commit before promotion and tagging. [Release verification](VERIFICATION-0.11.md) records the scope and preserved runtime evidence.

`main` is now the only GitHub and local branch. The fully merged `codex/takeover` branch was removed. The unfinished experimental checkpoint is preserved at tag `archive/dosbox-headless-2026-10-23`, targeting `7cc45b1cd0439ae0306d20a33f28f1619f13036a`, before removal of its branch. The release tag remains fixed; later README/publication documentation changes on `main` do not alter the published packages.

The current [DeepSeek delivery](DELIVERY-0.11.md) is in `~/Conversions/DinoParkTycoon/fdisbull-deliveries/fdisbull-0.11.0-a216747/`, with a sibling published ZIP, checksums and a `LATEST.json` pointer. The exact published wheel passed all **32 focused native tests** against the tested Mac layers backend; the copied delivery pair additionally passed the **two checkpoint/marked-click tests**. Game inputs, saved states and project databases are excluded. Earlier deliveries are preserved.

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
