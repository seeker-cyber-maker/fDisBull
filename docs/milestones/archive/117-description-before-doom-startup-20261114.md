# MR !117 before ordinary Doom startup qualification

Read from GitLab on 2026-11-14 at source `587f595322ecf31ca8d3a1af39e8362c4fb2f694`.

<!-- codex-dos-milestones:start -->
## Ordinary QEMU end-to-end migration; DOSBox-X retained

The next priority is ordinary QEMU launch → physical input/readiness → display/file services → checkpoint/reopen → genuine exit. Further DESQview completion is deferred unless it blocks that workflow. **QEMU is not yet qualified as a 1:1 DOSBox-X replacement. DOSBox-X remains the default and retained backend.**

### Delivered and exercised locally

- Existing Python `wait`, JSON `debug-wait` and saved-script `wait` now support the explicit QEMU virtual clock. A real timed-press cutoff was corrected by admitting a verified fresh input span plus one readiness poll in the first bounded slice, preserving the total guest budget, stop/hook precedence and actual dispatch evidence. No silent input replay/cancel/release.
- Same-input, source-assisted original ATTT, Five Dice and Snake workflows pass across DOSBox-X/QEMU: complete win/reset or scoring/growth/control outcomes, stored display evidence and genuine guest exit. QEMU-only ATTT cold checkpoint/replay and separate authored relative-asset/open-handle restore witnesses pass.
- JSON/saved-script waits, cold reopen and exact bounded-response export pass without replaying execution. The final integrated native selection passes **19/19 with zero skips**, including 11 preservation cases for existing histories, trials, selected undo, frame ownership, task-private layers, hooks, RNG/checkpoints, IRQs and containment.
- Independent installed-prefix checks pass 221 cases; historical DESQview captures reopen through 348 alias queries, 193 public replies and 72 exact JSON exports. These reader results add no new live vendor-task authority. [Combined supplement](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/587f595322ecf31ca8d3a1af39e8362c4fb2f694/docs/evidence/qemu-ordinary-end-to-end-2026-11-14/combined-public-readback.md).
- Broad affected source checks pass **3,434 / 12 native-input skips**. Test totals overlap and measure verification quality, not completion percentage.

Runtime: [`29f45ab6`](https://gitlab.com/brewster-jennings-group/fdisbull/-/commit/29f45ab69374ed5ac604a70c4fecd385492f1d5d). Tool-only wheel SHA-256: `0e9199f5fb0c3bf908aafc41177b6ad1743da1894ec774a95567cea2164b5762`. All **710 runtime payload files** agree across committed source, wheel and private install. Final test/docs-only source `587f595322ecf31ca8d3a1af39e8362c4fb2f694` preserves those runtime bytes. The earlier 18-pass/one-consumer-failure and corrected one-case run remain distinct from the clean final selection.

[Ordinary workflow gate](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/587f595322ecf31ca8d3a1af39e8362c4fb2f694/docs/evidence/qemu-ordinary-end-to-end-2026-11-14/README.md) and [sanitized receipt](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/587f595322ecf31ca8d3a1af39e8362c4fb2f694/docs/evidence/qemu-ordinary-end-to-end-2026-11-14/verification.json).

### Concrete open gates

1. **Ordinary Doom startup is incomplete.** Public FreeDOS directory launch with original EXE/WAD and `-nosound -nomouse` reaches `R_Init`. Nine captures across 90 virtual seconds show cursor-only changes; registers change and each clock deadline is exact. The finite 180-second controller ends the owned group. No menu input/gameplay/checkpoint is attempted. Root cause is unknown. Next: observe ordinary WAD seek/read progress before changing filesystem layout; earlier assisted LE observations are not substituted.
2. **Strict paired ATTT cold restore remains failing on the retained DOSBox-X reference.** The separately retained older `daab62e5` package trial has correct scalar win state but a black 360×400 image in mode 0 / 40 columns. Its strict oracle remains. Passing fresh paired play is a different workflow.
3. **Portable delivery and wider compatibility remain open.** The private same-Mac kit copies 93 native/runtime files but still uses external host tools and absolute Homebrew libraries. It does not qualify offline delivery, legacy scene/frame/mouse workflows, broader audio/media/device/timing or protected-game recovery/fallback campaigns.

The prior bounded DESQview checkpoint and public cold-reopen evidence remains preserved in [the archived description](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/587f595322ecf31ca8d3a1af39e8362c4fb2f694/docs/milestones/archive/117-description-before-ordinary-end-to-end-20261114.md) and [checkpoint-build public supplement](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/587f595322ecf31ca8d3a1af39e8362c4fb2f694/docs/evidence/desqview-checkpoint-public-cold-reopen-2026-11-14/README.md); it is not general DOS parity.

**No CI, native rebuild, release, merge, default switch or shared activation.** Commercial originals, images, states and FDB/CAS remain private. Broader migration qualification stays open.
<!-- codex-dos-milestones:end -->

<!-- fdisbull-handoff:6405e801b85c5f849d01529f21ad124009fb23e5e5eda71485f503364aacfb91 -->
