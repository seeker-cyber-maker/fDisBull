<!-- codex-dos-milestones:start -->
## Latest: history-root CPU timing correction — locally qualified (2026-11-16)

Published head `f55ef40e7059c90cfccd2dcb4ef94b37325da5b2`. Frozen runtime `ee9694ca5f2e22997d98eb2dabec143085e7a0e3` / wheel `c4d1b8ec796d0121cd100a8555a38f594130dfc32dc30e4d13d1139f437f830a`; native `9be74ad11dd02f0bc488e56e27df1a6326be13bd5cd07c3c64c74d14b228d32a`. All 713 production files equal committed source, wheel and private prefix.

**The measured Doom divergence is closed for this tuple.** Six hot/separate-Python selected restores and all four 600 ms explicit/history-root continuations match **full exposed CPU**, canonical source, SB16 query, PNG, PCM bytes/chunks, virtual time and instruction count. Saved 18,958-frame PCM extends identically to 37,916 frames. All eight campaign QEMU handles are reaped.

Two faults were separated:
- The virtual profile left RTC on host time. It now pins `base=utc,clock=vm,driftfix=none` in compatibility identity. Old HOST-coordinate states keep their old tool/runtime; incompatible loads refuse before replacing a valid owner.
- RTC correction alone still failed CPU/PCM continuation. Selected SB16 DMA now consumes credit synchronously at the virtual audio callback or ordinary guest I/O, instead of host-polled idle work. Other DMA channels retain their legacy path; masks/DREQ and IRQ acknowledgement remain active.

| Milestone | This slice |
| --- | --- |
| 4. Clock/media/input | Stopped RTC host-time leak corrected; selected SB16 DMA/IRQ service no longer follows host idle polling. |
| 5. Checkpoints | New RTC identity is fenced; passive restore, old binaries/states and existing ownership contracts retained. |
| 7. Histories | Actual Doom root futures now match full CPU and media, hot/cold. LE history remains capture-only; no general instruction replay claim. |
| 9. Qualification | 2,138 installed host cases and 23 native cases pass, zero skips: ten audio/RTC/ring plus thirteen existing preservation cases. Independent closed-state audit verifies payloads, exports, exact native streams and cleanup. |

Existing trials, selected CPU/RAM undo, frame histories/keys, task-private RAM/code layers, hooks and IRQs retain their scope. No whole migration milestone is marked complete.

[Qualification](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/f55ef40e7059c90cfccd2dcb4ef94b37325da5b2/docs/evidence/qemu-history-cpu-timing-2026-11-16/README.md) · [sanitized receipt](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/f55ef40e7059c90cfccd2dcb4ef94b37325da5b2/docs/evidence/qemu-history-cpu-timing-2026-11-16/verification.json) · [native delta](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/f55ef40e7059c90cfccd2dcb4ef94b37325da5b2/native/qemu-sb16-dma-service/README.md) · [prior description archive](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/f55ef40e7059c90cfccd2dcb4ef94b37325da5b2/docs/milestones/archive/117-description-before-history-cpu-timing-20261116.md)

The RTC-only failure, six old-route CPU counterexamples and draining-fixture failures are retained. The corrected draining fixture keeps every tail/waveform/hot/cold assertion; all five default guest binaries and offsets stay exact. The mutable-ring test also passed the old runtime and is supplementary coverage, not a failing reproduction.

**Full 1:1 parity remains unqualified. DOSBox-X stays default and retained. No CI, release, merge or shared activation.** General record/replay, concurrent mixed-device stress, FM/OPL music, ideal amplitude, paired DOSBox-X comparison and portable delivery remain open. Raw commercial inputs/states/media/FDBs stay private.
<!-- codex-dos-milestones:end -->

<!-- fdisbull-handoff:6405e801b85c5f849d01529f21ad124009fb23e5e5eda71485f503364aacfb91 -->
