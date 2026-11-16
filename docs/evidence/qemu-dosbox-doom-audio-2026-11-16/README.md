# Doom audio comparison — bounded 512-command demo prefix

Both frozen backends complete the same private Doom workload with music only,
effects only and both together: **twelve fresh native captures**, two per backend
and configuration. All produce nonconstant PCM and normal guest exit code 0;
all native owners close/reap. The comparison exposes format, stereo, DC, level
and sample-limit differences. **It does not qualify 1:1 audio parity.**

DOSBox-X stays default and retained. This slice changes documentation only.
The accepted OPL/FM, SB16 and CPU/RTC/DMA timing implementations, trials,
histories, layers, hooks, checkpoints and IRQs remain unchanged. No CI, release,
merge, native rebuild or shared installation/activation occurs.

## Workload and acquisition

The original private Doom 1.9 EXE/WAD remain byte-identical. `AUD512.LMP` is an
external input containing DEMO1's unchanged 13-byte header, its first 512
four-byte commands and a normal end marker. DEMO1 is **E1M5**, not E1M1. The
original 1,710-command lump is untouched. The prefix includes 54 static
fire-button commands, starting at command 458; that is not a live tic anchor
or a receipt for 54 shots. Its nominal 512/35 logic seconds do not establish
recording duration or live elapsed time. Both use normal `-playdemo AUD512`,
never `-timedemo`.

Fresh per-run configurations share music/effects volumes 10/13 and SB base
0x220, IRQ7, DMA1/high-DMA5. Music device 2 and effects device 3 are independently
enabled/disabled for the three conditions. Doom's expected exit-time config
save is recorded; original EXE/WAD/demo identities are checked before and after.
No guest memory/register writes, forced IRQ-mask changes or executable patches
are used.

QEMU uses the accepted `sb16-opl` binary and one continuous run from original MZ
entry to the nonce-bound DOS helper return. It has no intermediate clock-budget
stops. Every prefix capture has zero dropped frames. DOSBox-X uses its unchanged
native `DX-CAPTURE /A /-D` audio-only recorder through a private shell alias.
Its original relocated entry bytes and matching exiting child PSP are verified.
The WAV writer finalizes before owner closure, with no configured post-exit
delay. Headless `nosound`/dummy host output still synthesizes and records audio.

The capture frontiers differ: DOSBox records its millisecond mixer output,
including startup silence, while QEMU records delivered output from enabled
audio voices. QEMU sample delivery does not synthesize a matching prefix of
silence for inactive voices. Accordingly, **WAV duration is output-sample time,
not a common guest/game timeline**. No speed ratio is inferred from it.

## Observed differences

| Property | QEMU selected profile | DOSBox-X unchanged default |
| --- | --- | --- |
| Capture format | 32 kHz, mono, unsigned 8-bit | 48 kHz, stereo, signed 16-bit |
| FM source | YM3812 OPL2, 32 kHz S16 mono before mixing | SB16 auto-OPL3/DBOPL, 49,716 Hz synth before mixing |
| Music-only stereo | Mono capture | Identical left/right in this excerpt |
| Effects/mixed stereo | Cannot retain stereo separation | Side energy 2.38–2.52% of mid-plus-side energy |
| Fresh-run PCM identity | No equal pair in any condition | No equal pair in any condition |

The following metrics use the entire retained recording. Stereo is projected
as `(L+R)/2` only for these comparisons; native channels are measured separately.
RMS includes DC. There is no onset trim, resampling, silence fill, gain fit,
DC removal, lag correction or time stretch.

| Condition | Output seconds: QEMU / DOSBox-X | Mono RMS: QEMU / DOSBox-X | QEMU native sample-limit occupancy |
| --- | --- | --- | --- |
| Music only | 23.382–23.432 / 56.241–56.268 | 0.06765–0.06768 / 0.01630 | 0% |
| Effects only | 24.152–24.172 / 60.220–60.278 | 0.20804–0.20929 / 0.07379–0.07385 | 0.372–0.387% |
| Mixed | 24.664–24.664 / 61.891–61.948 | 0.21432–0.21562 / 0.07522–0.07524 | 0.368–0.403% |

Whole-recording QEMU/DOSBox mono RMS ratios are +12.36 dB for music and
+9.00–9.14 dB for effects/mixed. **These are descriptive recording ratios,
not calibrated gain errors:** unequal acquisition coverage, DC, synthesis and
native mixer behavior all contribute. QEMU music/mixed DC is +0.0354 to +0.0370
of full scale; effects-only is approximately −0.011. DOSBox mono DC stays within
0.00060 of zero. Its existing DC correction remains enabled.

QEMU effects/mixed reach both 8-bit native sample limits. DOSBox projected mono
never reaches a limit in this matrix; one mixed run's right native channel has
three maximum-code samples (0.000101% of that channel). Native rail occupancy
does not locate the stage that saturated or certify distortion-free output
elsewhere. The fixed native-rate Welch analysis also shows different band
power; it supplies no pitch, waveform-fidelity or perceptual-equivalence score.
DOSBox's default DBOPL is not the alternate MAME OPL2 core, so the latter's
3.6 MHz clock ratio must not be used to explain or retune this comparison.

Fresh process starts vary on both backends, including equal-length QEMU mixed
recordings with differing PCM. These fresh-run results do not contradict the
previous exact checkpoint futures: a shared saved state and execution schedule
are a different contract. No repeats were discarded or rerun to obtain equality.

The retained native sources identify two concrete paths for the next probe.
QEMU's conversion duplicates mono input into left/right mix accumulators, then
its mono output conversion clips their **sum**; the analysis projection of
DOSBox stereo uses their **average**. For equal unclipped channels those laws
differ by 6.02 dB, but that algebra does not explain the full recording ratios.
QEMU's SB16 mixer writes store volume registers without applying output-volume
updates; DOSBox's mixer applies master times DAC/FM gains. These source findings
justify controlled channel/gain-law tests before retuning the synthesizer. No
new native test or fix of those paths is claimed here.

## Retained acquisition failures

The original full DEMO1 trial exceeded QEMU's unchanged 1,920,000-frame capture
limit: it retained that many frames and reported 131,025 dropped frames before
guest completion. It is not a complete paired recording. Six complete DOSBox
full-demo captures remain supporting evidence, outside this prefix matrix.

A proposed split-recording workaround also failed strict equality: a continuous
600 ms future retained 30,751 frames, while two 300 ms pieces retained 30,732.
The recombined audio is an exact prefix, but PCM/chunks and final OPL/SB16 state
fail equality. The split case also adds a VM pause/resume; the NONE backend
resets its rate controller on resume. Capture restart and execution cadence
therefore remain confounded. An empty tap alone is insufficient to qualify
rolling capture. No engine fix, weaker acceptance or checkpoint-regression
claim is derived from that probe. Both failures remain private and hash-bound.

## Preservation and next qualification gate

The comparison uses tool commit `8e1c9c8c…`, wheel `902bf970…`, QEMU `01773e0f…`
and DOSBox-X `df2080bc…`. All 713 installed tool files and the earlier accepted
artifacts are checked against their frozen identities. The
[OPL checkpoint qualification](../qemu-opl-checkpoint-2026-11-16/README.md)
remains the evidence for six selected hot/cold Doom restores and four strict
600 ms futures. Its 2,149 host/26 native cases are **prior accepted results**,
not new test totals from this documentation slice.

Independent read-only audits verify all twelve finalized WAV envelopes and
their counts/hashes, normal exits, unique owners and empty owned groups. Native
integer arithmetic independently reproduces 264 scalar/stereo values, within
3.22e-14 absolute error. The prior accepted database and all 588 stored objects,
runtime kit, inputs and host/native test receipts also remain hash-identical.
These audits open no project/database and launch no guest.

The next bounded parity work should first establish a common acquisition/game
event boundary and test mono conversion and SB mixer gain against the selected
profile's DC/sample-limit behavior, without fitting away the differences.
Stereo preservation then needs an explicit contract. DOSBox active-capture
checkpoint writer/mixer-frontier continuity, long capture, OPL3/MIDI,
hardware/analog fidelity, broader targets and portable delivery remain open. Existing functionality stays available;
none of these observations authorizes retiring DOSBox-X.

The [sanitized verification record](verification.json) publishes aggregate
metrics, exact identities and receipt hashes. Commercial bytes, demo commands,
audio, waveforms, game images, states, memory/register dumps and FDB/CAS payloads
remain private. No hardware oracle or listening-panel assessment was performed.
