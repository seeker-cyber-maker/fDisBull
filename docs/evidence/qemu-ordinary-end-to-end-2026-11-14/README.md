# Ordinary QEMU DOS workflows: local migration gate

**QEMU is not yet qualified as a 1:1 DOSBox-X replacement.** DOSBox-X remains
the default and retained backend. Ordinary launch, input, readiness, display,
file access, recovery and exit take priority over further DESQview, CHIP-8 or
conversion features. DESQview work remains open for a later pass unless it
blocks an ordinary DOS workflow.

## Delivered behavior

The existing Python `wait`, JSON `debug-wait` and saved-script `wait` routes now
support the explicit QEMU virtual-clock profile. Numeric register/status and
explicit machine-memory observations are sampled while stopped. One host
deadline covers admission, execution and persistence; native stops, hooks and
exit evidence take precedence over another poll. See the
[timing contract](../../DOS_QEMU_TIMING.md#observation-driven-native-waits).

A real-game trial exposed a short readiness slice cutting a timed key press
before its release. For a verified, wholly undelivered fixed input plan, wait
now admits the nominal input span plus one poll interval as its initial slice,
within the unchanged total guest budget. It retains the token and actual
dispatch receipt. Unsupported, interrupted, partially delivered or oversized
plans refuse; a late interrupted prefix stops without a second continue. No
input is silently replayed, cancelled or released. A matched predicate can
still precede input completion, which the caller must inspect before saving.

## Same-input original-game comparisons

These are bounded, source-assisted workflows through untouched repository game fixtures, not
complete compatibility campaigns or identical timing/raster claims.

| Original target | Paired DOSBox-X / QEMU result | Scope |
|---|---|---|
| ATTT.COM | Complete winning round, reset and genuine guest exit pass | Same `q,4,w,5,e,Space,Escape` input; seven scalar/text observations per backend, stored nonuniform images and exact cold artifact exports. A separate QEMU-only test passes save, owner replacement, cold restore and replay. |
| Five Dice | Complete game and genuine guest exit pass | Same `1,r,r,r,s,s,s` input; eight RNG/state observations, independently calculated scores 25/12/0 and total 37. The QEMU caller explicitly recovers interrupted held input before exit. |
| Snake MZ | Keyboard growth, direction, run/pause and genuine guest exit pass | Eight manual-state comparisons and stored graphics; positive clock-driven progression and pause stability per backend. QEMU boots the copied FreeDOS component and launches a nested executable through `dos_directory`. |

The three games do not exercise external game assets or save files. Separate
authored COM witnesses pass relative asset reads, file modification/rename and
cold restore of an open handle/position after the original host root is moved.
Those witnesses qualify that bounded file-service route, not arbitrary game
save formats or directory compatibility.

The native wait test passes JSON readiness, saved-script readiness, explicit
input drain, checkpoint, cold project/owner reopen and genuine exit. Its
4,096-byte delivery limit produces a completed output reference: the complete
response is exported and checked by size/SHA without repeating `debug-wait`.
The virtual clock and sole wait-event count remain unchanged during recovery.

## Retained failures and unknowns

1. **Ordinary Doom has not reached gameplay in this candidate.** A public
   FreeDOS directory launch of the original EXE/WAD, explicitly with
   `-nosound -nomouse`, reaches `R_Init`. Nine stored observations across
   90 seconds of QEMU virtual time show only alternating cursor imagery.
   Registers change; this is not evidence that the CPU stopped executing.
   Every requested 10-second virtual budget reaches its exact deadline.
   The controller's 180-second hard deadline ends the owned group. No menu
   input or checkpoint is attempted. Root cause remains unknown; earlier
   assisted/source-bound Doom observations do not qualify this ordinary route.
2. **Strict paired ATTT cold restore fails on the retained DOSBox-X reference.**
   In the separately retained older `daab62e5` package trial, after restore and
   the winning input, scalar win state is correct but the
   saved display is black, 360x400, with BDA mode 0 / 40 columns. The original
   program contains no `INT 10h` mode change. The strict mode-3/80-column and
   nonuniform-image oracle remains intact. A fresh complete paired round
   passes; it does not replace the failing restore trial. Cause is unresolved.
3. **Delivery remains a private same-Mac runtime kit.** Ninety-three copied
   native/runtime files are byte-identical to their inputs, including QEMU,
   qemu-img, mcopy, firmware and the FreeDOS component. Absolute Homebrew
   libraries, host Python, NASM and the retained DOSBox-X build remain external
   dependencies. This is not a portable/offline package or shared activation.
4. Legacy scene/frame probes and coordinate mouse workflows, broader audio,
   media/device/timing compatibility, protected-game recovery and fallback
   campaigns remain unqualified. No completed-guest-frame, arbitrary input
   consumption or general protected-mode checkpoint claim is made here.

Resolve the ordinary protected-game startup boundary before expanding
DESQview. Then demonstrate menu-to-gameplay, controlled input/display and
mid-program/cross-session recovery through public APIs, with a same-input
DOSBox-X comparison. Retain both backends while those gates are open.

## Exact candidate and verification

Runtime commit: `29f45ab69374ed5ac604a70c4fecd385492f1d5d`.
Private tool-only wheel SHA-256:
`0e9199f5fb0c3bf908aafc41177b6ad1743da1894ec774a95567cea2164b5762`.
All **710** runtime files agree across committed source, wheel and private
install. Later test/documentation commits must preserve those bytes.

- Broad affected source checks: **3,434 passed / 12 input-dependent skips**,
  with 1,285 Python source/test identities stable throughout that run.
- Final integrated native selection: **19 passed / zero skips** on the frozen
  runtime, including the corrected consumer below and existing preservation
  cases. Originals, installed payload and pinned dependencies remain unchanged;
  the owned group is absent after exit.
- Earlier native main selection: **18 passed / one test-consumer failure**. The actual
  wait completed successfully at 432 ms virtual time; the consumer mistook
  bounded delivery's `complete=false` for operation failure. The corrected
  export/no-replay consumer then passed its one native case on the same frozen
  runtime. Both results remain recorded separately.
- Eleven of the final passing native cases preserve DOS/CHIP-8 histories, trials,
  selected undo, frame ownership, layers, hooks, RNG/checkpoints, IRQs,
  containment and public raw restart across both QEMU contexts.
- The strict paired cold-restore failure is a separate retained comparison,
  not removed from the suite or counted as passing.

Counts overlap and measure verification quality, not percentage completion.
The [sanitized receipt](verification.json) binds the exact raw reports and
distinguishes failed candidates, delivery-consumer corrections and open gates.
The independently verified [combined public-reader supplement](combined-public-readback.md)
adds exact installed-prefix Project/JSON/CLI reopening and export checks against
retained `daab62e5` DESQview captures, including 193 replies and 72 exact JSON
exports. It qualifies the new reader against historical data and supplies no
new live DESQview restore authority. Its separate installed host selection
passes 221 cases with zero skips on the same 710-file runtime.
Original commercial inputs, images, states, FDB/CAS and raw observations remain
private. No CI, native rebuild, release, merge, default change or shared
installation change is part of this slice.
