<!-- codex-dos-milestones:start -->
## Current migration status — 2026-11-14

Head: [`d91a1114`](https://gitlab.com/brewster-jennings-group/fdisbull/-/commit/d91a11147d02018b050f8c66b29f30fb682cc8f5). Tested runtime: [`72423fad`](https://gitlab.com/brewster-jennings-group/fdisbull/-/commit/72423fadd263b579ba2193d960f1e35d83fba9df). The final commit records host acceptance and pending native gates only. **DOSBox-X remains default and retained. Still no CI, native rebuild, release, MR merge or shared activation.**

### Automatic DESQview physical qualification — implemented and host verified

`DesqviewProvider.qualify_physical` compares every captured byte through two fresh linear/physical passes, including relocation bytes. It rechecks the stopped CPU, run/source/version/epoch, task/process identity and uncached page mappings. The supported first slice is unlayered base memory, A20-enabled legacy32 non-PAE 4KiB paging, configured RAM, at most 1MiB/256 pages and one ten-second observer deadline intersected with exported parent deadlines.

The tracker records a certificate before mapping. The registry verifies the local owned artifact, snapshot/context/native hashes and exact page coverage, then retains a proof for each source-bound extent. Disjoint source fragments can share a certificate; overlapping reuse and reuse after withdrawal refuse. Physical placement stays outside identity keys. Registry checkpoint restore preserves the previous certificate as historical evidence and requires fresh proof.

A typed physical-only failure withdraws partial maps and retains an episode only after independent stopped CPU and lifecycle coverage revalidation. Owner/epoch/native identity drift, unexpected transport failures and journal failures retain their retirement/fencing contracts. Independent review reproduced and closed a final-observation owner/epoch race.

### Fresh evidence on this exact runtime

- **3,315 host tests passed / 12 input-dependent native skips**, 113 files; all **1,279 Python source/test hashes** remained fixed.
- **297 installed-wheel tests passed**, zero skips, and **161 independent focused host cases passed**. These selections overlap the broader suite.
- All **709 runtime files** match Git source, wheel and one private flat install; **20 critical imports** resolve to that prefix. Wheel SHA-256: `10b82f1f7c9f8e008199d66693f8b00ded479f300799c9827fb5e95b64c86035`.
- Shared selector, installation manifest and seven DOSBox payload hashes are unchanged.

**Fresh native acceptance is pending.** Both native launcher admissions returned exit 2 for `macOS reports warning memory pressure`, including the retry after host processes exited. No ticket was granted, no guest started and no native test ran. Automatic-provider native physical qualification remains `null`; prior `62d01df8` results are historical and were not substituted.

Pending on the frozen wheel: eight native preservation/failure cases, both authored LE profiles, and original-DESQview automatic proofs compared with independent physical witnesses through same-task relocation, genuine handle reuse, source-error recovery and cold reopen/postflight. Offline controls are frozen with 133 passing model/control cases and an independent review; a fresh root rerun passed. These are separate from native acceptance. The live-capture-to-closed-SQL/CAS adapter end-to-end gate remains open, including public-index normalization with artifact ordering retained.

[Current progress note](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117#note_4234349098) · [host acceptance receipt](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/d91a11147d02018b050f8c66b29f30fb682cc8f5/docs/evidence/desqview-automatic-physical-2026-11-14/verification.json) · [contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/d91a11147d02018b050f8c66b29f30fb682cc8f5/docs/runtime-mappings.md) · [dated handoff](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/d91a11147d02018b050f8c66b29f30fb682cc8f5/docs/DOS_QEMU_HANDOFF.md).

### Preserved scope and remaining parity gates

Trials, histories, shared replay, task-private RAM/code layers, hooks, checkpoints and IRQs retain their host contracts; fresh native preservation remains pending. The certificate proves only observed source-capture extents. Whole task RAM, every manager record, continuous residency/execution and allocation lifetime remain unqualified. The raw machine run's local execution timeout may be separate from the observer budget where no parent deadline is exported.

Overall QEMU-DOS/DOSBox-X parity and removal remain unqualified. Broad task/media/input/time/Windows/cold-epoch/fallback campaigns, paged/LDT/bridge LE execution, LE-addressed hooks/layers/checkpoints, IRQ/timer-transparent tracing, component04 boot and the historical DOSBox startup issue remain open. G0/G1/G2 remain; G3-G8 are separate. The inventory is not a completion percentage.

Previous combined continuity/LE native acceptance remains [historical evidence](https://gitlab.com/brewster-jennings-group/fdisbull/-/merge_requests/117#note_4234138179). [Previous description](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/72423fadd263b579ba2193d960f1e35d83fba9df/docs/milestones/archive/117-description-before-physical-qualification-20261114.md). Offline delivery closure stays with Release.
<!-- codex-dos-milestones:end -->

<!-- fdisbull-handoff:6405e801b85c5f849d01529f21ad124009fb23e5e5eda71485f503364aacfb91 -->
