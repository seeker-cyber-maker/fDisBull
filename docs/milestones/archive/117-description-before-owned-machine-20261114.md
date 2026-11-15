# Archived !117 description before owned-machine recovery

Provider readback before this milestone update. This text is historical evidence.

<!-- codex-dos-milestones:start -->
## Ordinary protected-DOS gameplay; checkpoint recovery remains open

Native QEMU now has a local ordinary original-Doom witness through launch, main/episode/skill menus, fresh E1M1 and selected forward movement/turning, using `-nosound -nomouse`. No prepared state, LE binding, IRQ-mask change or guest-code/RAM/register edit is used. The unchanged earlier runtime also reaches its built-in demo: the retained 90-second `R_Init` observation did not establish a permanent stall.

**QEMU is still not qualified as a 1:1 DOSBox-X replacement. DOSBox-X remains the default and retained backend. Further DESQview completion is deferred unless it blocks ordinary DOS.**

### Loading correction and actual native behavior

New workspace volumes at least 32 MiB prefer 4 KiB clusters only when all file and directory allocation fits; otherwise they retain the previous layout. Smaller volumes, limits, parsing and exact retained-checkpoint paths remain unchanged. Independent review caught and corrected a preferred FAT-size rounding edge before packaging.

A same-controller comparison from original MZ entry to first observed BDA mode-13 write uses **1,666,377,668 counted instructions / 213.296341504 virtual seconds** on the earlier layout, versus **254,130,371 / 32.528687488** on the candidate. The baseline-to-candidate instruction ratio is 6.5572. This is a graphics-initialization boundary, **not wall speed, whole-game timing or a completed-frame claim**. Both runs separately advance one virtual second after that measurement for capture.

Six individually inspected physical keys produce menus, new game and visible movement/turning. All nine stored images match their artifacts; all keys have complete two-edge dispatch receipts. General guest consumption is not inferred merely from dispatch.

### Actual remaining checkpoint blocker

Normal public `save_state` refuses with **`DOS process allocation ownership changed`**. The later protected-PC/source guard is not reached. CPU, cached process documents and PID are unchanged after refusal; state count stays **0 → 0** and the capture is unchanged. A subsequent one-second virtual advance succeeds and renders gameplay.

The cached process document is not a fresh MCB scan. This probe does not identify the changed allocation field or distinguish a legitimate resize from other ownership changes. Next: establish extender allocation evolution and truthful source/recovery authority. No raw snapshot bypass, disabled ownership comparison or fabricated `source_binding_restored` flag is used.

### Exact local verification

Runtime: [`43b7da39`](https://gitlab.com/brewster-jennings-group/fdisbull/-/commit/43b7da3957ab94f18271eab2876ac01888919555). Tool-only wheel SHA-256: `630e97c7d1bed4f2e821547b8d1e97e5312ebecb9108328e1185920bc00ef37e`. All **710** source/wheel/private-install payload members match; the sole runtime-member change from `29f45ab6` is the FAT builder. Final test/documentation source `cbf5e4303eb8ff609426ab99fc07817eee92dd79` preserves those runtime bytes.

- **176 affected host cases pass**, including 27 focused FAT cases; counts overlap.
- **23 native cases pass, zero skips**: existing histories, trials, selected undo, frame ownership, task-private layers, hooks, RNG/checkpoints, IRQs, containment, paired small-game controls and native readiness; relative files/open-handle recovery, COM/MZ CRUD and real short-write/full-disk keep refusal/restore.
- Original inputs and frozen packages remain unchanged; successful gameplay and comparison guests close/reap normally. Earlier action-window expiry, supervisor estimate interruption and rejected geometry remain separate retained trials.

[Startup/gameplay qualification](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/cbf5e4303eb8ff609426ab99fc07817eee92dd79/docs/evidence/qemu-doom-ordinary-startup-2026-11-14/README.md), [sanitized receipt](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/cbf5e4303eb8ff609426ab99fc07817eee92dd79/docs/evidence/qemu-doom-ordinary-startup-2026-11-14/verification.json).

Protected recovery, Doom guest exit, audio/mouse/device/media/timing, portable delivery, the older strict DOSBox-X ATTT cold-reference display gap and broader compatibility remain open. Earlier reader/CHIP-8/DESQview evidence remains bound to its original qualifications in [the prior description](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/cbf5e4303eb8ff609426ab99fc07817eee92dd79/docs/milestones/archive/117-description-before-doom-startup-20261114.md).

**No CI, native rebuild, release, merge, default switch or shared activation.** Original commercial files, images, states and FDB/CAS remain private.
<!-- codex-dos-milestones:end -->

<!-- fdisbull-handoff:6405e801b85c5f849d01529f21ad124009fb23e5e5eda71485f503364aacfb91 -->

