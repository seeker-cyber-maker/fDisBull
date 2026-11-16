<!-- codex-dos-milestones:start -->
## Latest: OPL2/FM music and mixed SB16 restore — locally qualified (2026-11-16)

Published source `1c4fdb2e40e25fa14b8e83270a1d5c53672e2ecb`. Runtime tool `8e1c9c8cbc1a0314a18a6d533a51ed9fd36814d2`, wheel `902bf97034e6470d9df0d3fb5d4198dbf47be02faa42a1cf439ad5ca2e0ef8c9`, native `01773e0f8e4976db24449442e9e79f6f0042f9a1c21529a13b35dc8856991924`. All 713 production files match source, wheel and private prefix.

**The explicit `sb16-opl` profile now retains YM3812 music together with SB16 digital effects.** Its separate core3 saves both named voices and callback order, mixer/resampler/capture frontiers, and pointer-free operator/envelope/feedback/LFO/register/noise state. Restore neither replays OPL writes nor synthesizes while stopped. The corrected VM-backed RTC and selected SB16 DMA service remain; old PC-speaker/core1 and SB16/core2 implementations are preserved.

Original private Doom E1M1 passes **six hot/separate-Python selected restores and all four 600 ms explicit/history-root futures**, matching full exposed CPU, canonical LE source, OPL/SB16 queries, stored PNG, PCM bytes/chunks, virtual time and instruction count. Saved 38,390-frame/122-chunk audio extends identically to 57,400 frames/183 chunks. FM operators and nonconstant output are observed before firing; actual ammo is 50→49→48. All eight campaign QEMU handles are reaped.

| Milestone | This slice |
| --- | --- |
| 4. Clock/media/input | Combined OPL2 music and SB16 effects capture; corrected CPU/RTC/DMA timing and physical input retained. |
| 5. Checkpoints | Pointer-free synth state, pending DATA latch/timers, per-voice audio state/order, initial silent graphs, passive hot/cold restore. |
| 7. Histories | Actual Doom root futures preserve full CPU/music/effects; source binding and observer owners are fresh. LE intervals remain capture-only. |
| 9. Qualification | 2,149 installed host cases and 26 distinct native cases pass, zero skips. A separate synth harness verifies all 18 operators, exact hot/cold PCM/state and 18 atomic malformed-state refusals per process. |

Independent read-only audit verifies all six artifacts/twelve exports, nine creation joins, three save chains and six atomic load pairs. Database/all 588 CAS files stay unchanged. Explicit A/root native streams are byte-identical across 37 decoded sections including AdLib; original inputs, 713 tool files, runtime kit and libraries rehash exact.

Trials, selected CPU/RAM undo, frame histories/keys, task-private RAM/code layers, hooks and IRQ contracts retain their prior scope. No whole migration milestone is marked complete. The initial-graph test's mistaken post-reset voice assumption and its corrected exact assertions remain documented; no production change supplied that test correction.

[Qualification](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/1c4fdb2e40e25fa14b8e83270a1d5c53672e2ecb/docs/evidence/qemu-opl-checkpoint-2026-11-16/README.md) · [sanitized verification](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/1c4fdb2e40e25fa14b8e83270a1d5c53672e2ecb/docs/evidence/qemu-opl-checkpoint-2026-11-16/verification.json) · [native delta](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/1c4fdb2e40e25fa14b8e83270a1d5c53672e2ecb/native/qemu-opl-checkpoint/README.md) · [prior description](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/1c4fdb2e40e25fa14b8e83270a1d5c53672e2ecb/docs/milestones/archive/117-description-before-opl-20261116.md)

**DOSBox-X remains default and retained. No CI, release, merge or shared activation. Full 1:1 parity stays unqualified.** This is OPL2 only: OPL3/MIDI, hardware/analog fidelity, general replay, broader device stress, paired DOSBox-X audio and portable delivery remain open. Stock port-triggered AdLib timer expiration and private repeatable noise are explicit limits; individual Doom device PCM is not isolated. All commercial bytes, states, media and FDB/CAS data remain private.
<!-- codex-dos-milestones:end -->

<!-- fdisbull-handoff:6405e801b85c5f849d01529f21ad124009fb23e5e5eda71485f503364aacfb91 -->