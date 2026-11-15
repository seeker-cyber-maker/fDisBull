<!-- codex-dos-milestones:start -->
## Bounded ordinary Doom machine recovery and normal guest exit

Native QEMU now has a local ordinary original-Doom path through fresh E1M1 gameplay, physical movement, capture, intervening movement, exact hot recovery, recovery in a separate Python process and a later normal DOS exit from that checkpoint. Arguments remain `-nosound -nomouse`; no LE binding, IRQ-mask change, direct guest-code/RAM/register edit or injected initial state is used.

**QEMU is still not qualified as a 1:1 DOSBox-X replacement. DOSBox-X remains the default and retained backend. DESQview completion stays deferred unless it blocks ordinary DOS.**

### Delivered recovery boundary

New explicit `save_machine_state` / `load_machine_state` APIs, live JSON and saved-script routes use capability `owned_machine_checkpoints`, kind `machine-state`, format `fdisbull-qemu-owned-machine-qcow2-v1`. Offline inspection is available.

Restore verifies a fresh owned machine/private disk and supported native controls, retires MZ/LE/tracker authority, advances epochs and reports **`source_binding_restored=False`**. Ordinary process checkpoints, source histories/trials and selected-undo anchors keep their stronger contracts. Source/task-private controls and active scheduler/provenance owners refuse in this separate mode; their existing source-bound paths remain preserved.

Normal `save_state` still refuses Doom with **`DOS process allocation ownership changed`** without changing CPU/cached-process/PID or source-state count. No ownership comparison was relaxed.

### Actual native qualification

The owned checkpoint is **29,271,726 bytes**, SHA-256 `7975550c822161f2a7c8e6fd75df073dc149552b28b5316214424b52d1dfd079`. Physical movement changes CPU and screen; hot restore reproduces the saved CPU and exact PNG under a fresh owner/epoch. A separate Python host reopens the Project, replaces its fresh entry owner, restores the same CPU/PNG and advances 100 ms successfully.

A separate bounded continuation restores the same archive and follows inspected Escape/Q/Enter/Y plus an additional Enter/shutdown allowance. The helper reports **`guest_exit`, normal DOS code 0**, no residency, and retired source ranges. The final operation stops after 51,760,000 ns; its release edge is cancelled at guest stop. No complete final key cycle or exclusive causal role is inferred. The recovery trial itself ended after Quit selection and does not claim exit.

All owned guests are reaped; original inputs, native kit and frozen prefix stay unchanged. Exit cleanup is retained through handle/group aggregate checks without concrete exit-job PID/PGID retention; raw TERMINATED bytes are not retained.

### Exact local checks and package

Runtime: `01d5c891c988916e964b049750211c5c32120a1f`. Final source: `9de41cd14c2377b8076f61d5f77690368092b910` (documentation changes preserve all runtime bytes). Tool-only wheel SHA-256: `d6b5226a3f0a81cf13baf109644b036fb00fe478d7d400bb3e3e069ab54b544c`. All **711 runtime payload files** match committed source, wheel and private installation.

- **397 installed host cases pass; 26 native cases pass; zero skips.**
- Three new native cases cover actual AH=4Ah shrink, open-handle disk rollback, changed CPU/RAM, physical/linear layers, linear hooks, hot/cold recovery, exit/TSR source retirement, restoration of an original strong source checkpoint, and instrumented clock/PCM/display/retrace/key state.
- The other 23 native cases preserve existing history/trial/selected-undo/frame/task-private-layer/hook/RNG/checkpoint/IRQ and ordinary workload/file-service gates.
- An independent fresh-host reader verifies 15 Python exports and three public JSON replies/two exact exports on copied closed evidence, with no guest and no canonical Project mutation.

Review hardens completion locking and primary-error retention. Failed fixture/operator-window trials and the actual new-kind 16 MiB publication failure remain retained. The new kind now shares the existing 128 MiB state limit; other-kind 16 MiB and aggregate 256 MiB limits stay intact. Counts describe verification, not completion percentages.

[Qualification](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/9de41cd14c2377b8076f61d5f77690368092b910/docs/evidence/qemu-owned-machine-recovery-2026-11-14/README.md), [sanitized receipt](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/9de41cd14c2377b8076f61d5f77690368092b910/docs/evidence/qemu-owned-machine-recovery-2026-11-14/verification.json), [API contract](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/9de41cd14c2377b8076f61d5f77690368092b910/docs/DOS_OWNED_MACHINE_CHECKPOINTS.md), [prior description](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/9de41cd14c2377b8076f61d5f77690368092b910/docs/milestones/archive/117-description-before-owned-machine-20261114.md).

Protected source-bound LE checkpoint/history continuity, broader audio/mouse/device/media/timing compatibility, portable delivery and the older strict DOSBox-X ATTT cold-reference display gap remain open.

**No CI, native rebuild, release, merge, default switch or shared activation. Original commercial inputs, screens, checkpoints and FDB/CAS remain private.**
<!-- codex-dos-milestones:end -->

<!-- fdisbull-handoff:6405e801b85c5f849d01529f21ad124009fb23e5e5eda71485f503364aacfb91 -->
