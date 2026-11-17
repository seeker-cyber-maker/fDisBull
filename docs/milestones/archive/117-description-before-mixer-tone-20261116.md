<!-- codex-dos-milestones:start -->
## Latest: paired Doom audio comparison — bounded evidence, parity open (2026-11-16)

Published documentation `cf4b30dbe94bd93da53ed7d4757b6f0d2e4724c7`. The accepted runtime stays tool `8e1c9c8cbc1a0314a18a6d533a51ed9fd36814d2`, wheel `902bf97034e6470d9df0d3fb5d4198dbf47be02faa42a1cf439ad5ca2e0ef8c9`, QEMU `01773e0f8e4976db24449442e9e79f6f0042f9a1c21529a13b35dc8856991924` and DOSBox-X `df2080bcd2e65aa8a8511ca0692d45d9b9f5355d673a83967c4abdab9672c47e`. No production/native change or rebuild.

**Twelve fresh captures complete the same private 512-command E1M5 DEMO1 prefix:** music-only, effects-only and mixed, two per backend. Original EXE/WAD and all prefix commands/header stay unchanged; a private external demo supplies only a normal earlier end marker. All runs have nonconstant PCM, normal DOS exit 0 and reaped native owners. All six QEMU prefix runs have zero drops and one continuous run without intermediate clock-budget stops. DOSBox's native WAV writer finalizes before close.

The comparison finds:

- QEMU selected capture is **32 kHz mono U8** versus DOSBox-X **48 kHz stereo S16**. DOSBox effects/mixed retain 2.38–2.52% stereo side energy that this QEMU profile cannot represent.
- QEMU effects/mixed occupy native sample limits for **0.368–0.403%** of samples. DOSBox projected mono has none; one native right channel has three maximum-code samples. QEMU also has materially larger DC offset.
- Whole-recording RMS and spectral power differ. Unequal capture frontiers prevent treating the duration or RMS ratios as game-speed/calibrated-gain errors. No trimming, resampling, alignment, gain/DC fitting or time stretch was applied.
- All six fresh-run repeat pairs differ on both backends. This does not invalidate exact continuation from a shared checkpoint and schedule. No repeats were discarded to obtain equality.

| Milestone | This slice |
| --- | --- |
| 4. Clock/media/input | First isolated music/effects/mixed paired capture matrix; format/stereo/DC/sample-limit gaps and unequal acquisition semantics recorded. |
| 5. Checkpoints / 7. Histories | Accepted six Doom hot/cold restores and four strict 600 ms futures remain hash-preserved; they are prior evidence, not rerun or expanded here. |
| 9. Qualification | All 12 complete captures independently audited; 264 scalar/stereo metrics independently recomputed. Full 1:1 parity remains unqualified. |

Independent audits verify 713 unchanged source/wheel/installed files, both native binaries, original inputs, prior database/all 588 CAS objects, runtime dependencies and earlier host/native test receipts. The earlier 2,149 host/26 native results stay historical accepted gates. Trials, selected undo, histories/frame keys, task-private layers, hooks and IRQs retain their prior scope.

The full-demo QEMU trial overflowed its unchanged 1,920,000-frame limit with 131,025 dropped frames. A split-capture trial also failed strict PCM/device equality and added a pause/resume cadence confound. Both failures remain recorded; rolling capture stays unqualified. Six complete DOSBox full-demo captures are supporting evidence outside the primary prefix matrix.

Next bounded work: establish a common acquisition/game-event boundary and probe mono sum-versus-average conversion and SB mixer gain before correcting DC/sample-limit behavior. Source inspection identifies those differences, but this slice applies no fix or synth retuning. Stereo, DOSBox active-capture checkpoint continuity, long capture, hardware fidelity, OPL3/MIDI and broader delivery remain open.

[Comparison](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/cf4b30dbe94bd93da53ed7d4757b6f0d2e4724c7/docs/evidence/qemu-dosbox-doom-audio-2026-11-16/README.md) · [sanitized metrics and receipts](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/cf4b30dbe94bd93da53ed7d4757b6f0d2e4724c7/docs/evidence/qemu-dosbox-doom-audio-2026-11-16/verification.json) · [previous OPL qualification](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/cf4b30dbe94bd93da53ed7d4757b6f0d2e4724c7/docs/evidence/qemu-opl-checkpoint-2026-11-16/README.md) · [prior description](https://gitlab.com/brewster-jennings-group/fdisbull/-/blob/cf4b30dbe94bd93da53ed7d4757b6f0d2e4724c7/docs/milestones/archive/117-description-before-doom-audio-comparison-20261116.md)

**DOSBox-X remains default and retained. No CI, release, merge or shared activation. No whole migration milestone is marked complete.** Commercial bytes, demos, audio, images, states, memory/register dumps and FDB/CAS payloads stay private.
<!-- codex-dos-milestones:end -->

<!-- fdisbull-handoff:6405e801b85c5f849d01529f21ad124009fb23e5e5eda71485f503364aacfb91 -->