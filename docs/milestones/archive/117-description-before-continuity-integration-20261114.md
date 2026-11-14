<!-- codex-dos-milestones:start -->
## Current migration status — 2026-11-13

Head: [`11043050`](https://gitlab.com/brewster-jennings-group/fdisbull/-/commit/110430501f39c7ca15d7c44bf150159a985a2289); installed/tested runtime: [`d8adf49d`](https://gitlab.com/brewster-jennings-group/fdisbull/-/commit/d8adf49dfa41176cefdab729778813fe6f3c2f6b). The final commit adds acceptance documentation only. **DOSBox-X remains default and retained. No CI, release, merge, shared activation or native rebuild.**

### Continuous protected-mode LE source binding and traces

Explicit `dos_source_bind`, status/refresh and unbind keep an owned source recipe separate from the initial MZ mapping and OS/task lifetime. Run endpoints and each retained stepped boundary are checked against original source, observed CS/GDT, stable physical/linear RAM, code anchors and relocation witnesses. Supported complete offset32 operands require exact whole-instruction reconstruction. Mutation, restore and owner/epoch changes retire the recipe.

The existing native DOS trace collector, predicates, scripts and cold query/search consume a distinct embedded-LE namespace. The stopped-only admission contract stays unchanged. No LE source-addressed hook/layer/checkpoint authority follows. [Public contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/110430501f39c7ca15d7c44bf150159a985a2289/docs/QEMU_DOS_PROTECTED_SOURCE.md).

### Local acceptance

- Host preservation: **3,023 passed / 12 runtime-input skips**. Final source and fresh private install each passed **139** focused checks; five additional installed preflight and 33 documentation/package checks passed. Overlapping counts are not additive.
- **Eight native pytest cases passed, zero skips**: authored real-loader standard/virtual LE traces plus six composed DOS/CHIP-8 history/trial/selected-state/frame/layer/hook/checkpoint/IRQ checks. Independent immutable cold audit agrees.
- Untouched Doom: **eight distinct qualified source sites**, exact current predicate with zero extra steps, complete cold 8/1 queries with zero unknowns, and four byte-identical exports. Independent read-only audit agrees. Executed-fixup coverage comes from the authored fixture; the Doom interval overlaps none. The observed step mask 7 suppresses IRQs/timers and does not establish retirement or IRQ/timer-transparent tracing.
- A later ordinary Doom run correctly withdrew authority on budget expiry; explicit refresh refused changed GDT identity. Continuing source authority across that interval is unqualified.
- All **708 runtime files** match source/wheel/private install; all **1,273 Python source/test hashes** stayed fixed. All guests closed/reaped and retained input pins/shared selector stayed unchanged. Failed setup precursor is retained separately. Both local-hub/GitLab branch heads read back at the final head; GitLab pushes used `ci.skip`.

[Full acceptance note](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117#note_4233887122) · [sanitized receipt](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/110430501f39c7ca15d7c44bf150159a985a2289/docs/evidence/qemu-dos-le-binding-2026-11-13/verification.json) · [dated handoff](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/110430501f39c7ca15d7c44bf150159a985a2289/docs/DOS_QEMU_HANDOFF.md).

### Remaining gates and history

Trials, histories, shared replay, task-private RAM/code layers, hooks, checkpoints and IRQs remain retained under their separate contracts. Paged/LDT and bridge execution, LE hooks/layers/protected checkpoint binding, broad task/driver and media/input/time campaigns, Windows shared-core, cold-epoch/fallback campaigns, component04 boot and the historical DOSBox startup issue remain open. Overall parity and DOSBox-X removal are unqualified. G0/G1/G2 remain; G3-G8 are separate. The 141-surface/seven-campaign inventory is not a completion percentage.

The separately authorized DESQview source-ambiguity/task-continuity candidate remains a distinct source/native tuple; its qualification is an integration handoff, not integration into this LE runtime.

[Prior protected-source acceptance](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117#note_4232505062) · [archived previous description](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/110430501f39c7ca15d7c44bf150159a985a2289/docs/milestones/archive/117-description-before-continuous-le-20261113.md) · [shared debugger reuse](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/110430501f39c7ca15d7c44bf150159a985a2289/docs/QEMU_DEBUGGER_REUSE.md).

Offline delivery closure stays with Release.
<!-- codex-dos-milestones:end -->

<!-- fdisbull-handoff:6405e801b85c5f849d01529f21ad124009fb23e5e5eda71485f503364aacfb91 -->
