# SB16 digital checkpoint continuation — local qualification

The explicit QEMU `sb16` audio profile now preserves a bounded digital audio
graph across stopped instrumented checkpoints. Authored guests produce the
complete expected unsigned 8-bit **mono and stereo** waveform at **8 kHz and
32 kHz**, then reproduce the same continuation after hot restore and in a
**separate Python process**. This is an exact-binary checkpoint gate for the
qualified graph. A fresh original Doom campaign also passes stopped LE source
checkpoint and capture-history recovery, hot and in a separate Python process.
**General future CPU/timing determinism remains open.**

DOSBox-X stays default and retained. This work dispatches no CI, publishes no
release and changes no shared installation. It does not establish paired
DOSBox-X audio parity, FM music support or complete device compatibility.

## Captured graph and compatibility

The separate `fdisbull-sb16` audiodev admits one SB16 unsigned 8-bit mono/stereo
voice at 5–45 kHz; the native capture output is 32 kHz unsigned 8-bit mono. The
new pointer-independent, bounded audio-core version 2 retains exact software
voice geometry and samples, resampler phase, mixer/capture rings and volumes,
pending backend bytes, active/draining flags, DMA state and relevant DSP/mixer
timer deadlines. Restore validates the graph before importing it and does not
execute guest instructions or transfer DMA samples while stopped.

The PC-speaker version-1 core, ordinary version-1 VMState fields and outer
instrumented envelope retain their existing contracts. The SB16 profile and
its native API marker are explicit; an older native runtime cannot silently
claim this capability. States remain bound to their exact native binary.
Host checks cover strict profile/runtime admission. Signed/16-bit graph refusal
is source-reviewed; it has not been exercised by a native negative probe.
See the [native source package](../../../native/qemu-sb16-checkpoint/README.md)
and [hash-bound verification](verification.json).

## Authored acceptance and preservation

The final frozen tuple is tool commit `106b507065d7c8854490d744836c52d384781270`,
a private wheel whose 713 production files equal committed source and the
private installed prefix, and native build `29f9de9a92a4…`.

- **Eight new native cases pass**, without failures, errors or skips: four
  single-cycle DMA1 waveform cases, DSP80 auxiliary IRQ timing, initial
  no-voice/capture-only graphs, and an inactive software voice whose hardware
  mixer still has nonconstant audio to drain.
- The waveform cases save a genuine partial DMA/IRQ state. Hot and separate
  process cold restores match CPU, device/report bytes, source-buffer identity,
  saved PCM/chunks and subsequent full PCM, with fresh owners and epochs. The
  authored guest acknowledges the real IRQ and reaches DOS exit 42.
- DSP80 is a **100 ms IRQ delay**, not generated PCM silence. Its checkpoint
  preserves the remaining timer; the fixed 60/30 ms continuation crosses the
  expected IRQ boundary with no fabricated audio.
- The draining case saves an inactive voice while capture is still enabled.
  Hot and separate process cold continuation emit the same remaining
  nonconstant PCM and reach disabled capture. A silent, already drained graph
  would fail this test.
- **962 installed host cases pass**. The duplicate-ZIP-member warning belongs
  to an existing malformed-archive negative.
- **13 existing native preservation cases pass**: ten in the main preservation
  selection and three history/trial/selected-undo cases in a separate four-case
  selection that also reruns draining. The final eight-case SB16 selection
  reruns draining again; that case is counted once.

All selected runtime files, tests and dependencies remain unchanged through
the runs; their process groups have no remaining owned members. The receipts
pin the wheel, native build, selections and XML results. Test totals describe
these checks and do not measure overall migration completion.

## Waveform claim ceiling

The exact oracle follows the pinned foreign QEMU mixer. Unsigned input is
centred at 127; mono duplicates into left/right and capture sums those channels.
Stereo resamples each channel before summation. Fixed-point interpolation uses
`UINT_MAX-t` weights, and native clipping/conversion includes a negative-full-
scale wrap boundary. These laws are derived from source, with no fitted gain,
rate or source offset. The complete expected sequence must match byte for byte;
only bounded neutral padding outside that sequence is allowed.

An independently checked original continuation matches all 32,764 expected
samples exactly. That establishes the oracle for this native mixer, **not
ideal amplitude/saturation behaviour, analogue fidelity or DOSBox-X waveform
parity**. No mixer semantic correction is claimed in this slice.

## Original Doom stopped recovery

A new FreeDOS/CuteMouse boot launches the unchanged original EXE and WAD into
E1M1, with mouse input, SB16 digital SFX and music disabled. The live source
voice is unsigned 8-bit **stereo at 11,025 Hz**, captured as 32 kHz U8 mono.
A physical **500 ms left-button hold** is observed across a 600 ms virtual
interval: ammunition changes **50 → 49** at A and **48** at B. The second shot
is continuation of that long hold, with no second mouse command between A/B.

An explicit LE source checkpoint and two capture-history nodes retain **18,927
PCM samples at A** and **37,854 at B**, in 61 and 122 chunks. All **six selected
restores**—explicit A, history B and history root A, hot and cold—match the saved
full exposed CPU, complete SB16 device query, canonical source site/instruction
hash, stored PNG, PCM bytes/chunks, virtual clock and instruction counter.
Source/clock/audio owners and capture epochs are fresh. The MZ source binding
remains retired; restored LE identity does not qualify task/allocation lifetime.
Cold attachment initially has no live cursor or source authority; explicit
selection earns each restored state. Six companion/linked-machine exports are
identical between hot and cold inspection.

Four **600 ms continuations** after hot/cold explicit A and history root A
produce the same complete PCM, chunks, SB16 device query, PNG, virtual time and
instruction count as the original future. The retained A PCM remains an exact
prefix. Both explicit-checkpoint futures also match full CPU; **both history-
root futures differ in full CPU**, despite those equal media/device/time
observations. Exact stopped recovery is qualified. A general future CPU/timing
determinism claim is not earned and remains a follow-up gate.

All **eight** campaign QEMU handles close with return code 0, both controller
groups have no remaining owned members, and inputs/payloads match before and
after. No guest memory/register writes or IRQ-mask changes supply this result.
The history is capture-only across unobserved intervals; this does not qualify
LE trials or instruction-completion histories. Closing QEMU is not a DOS guest-
exit claim.

## Retained failures and remaining gates

The first authored waveform attempt failed an idealized amplitude/onset oracle
before restore. The corrected oracle comes from the foreign source laws above.
A later guest-report mismatch exposed a DMA sample straddling the terminal IRQ;
the fixture now samples again after observing IRQ, retaining exact report and
full waveform comparisons.

Three earlier application attempts remain private and failed. The mono attempt
yielded constant PCM. A stereo attempt reached a physical shot 50 → 49 and a
nonconstant 19,169-frame capture, but the controller assumed its current 96-byte
LE source window would match. Binding performs admission internally and
correctly refused that unmatched window; a subsequent explicit admission also
returned unmatched. All three attempts closed/reaped and preserved immutable
inputs. The successful campaign above starts separately and selects an eligible
stopped source site without weakening the matching guard.

Auto-init DMA as an independently authored gate, signed/16-bit PCM, other DMA
routes, multiple voices, OPL/FM, paired DOSBox-X capture and broader game
compatibility remain open. Existing trials, selected undo, histories, layers,
hooks and IRQs keep their separate qualified scope. Original games, PCM/WAVs,
screenshots, machine states and FDB/CAS payloads remain private; only scoped
findings and hashes appear here.

The independent closed-state readback verifies all twelve hot/cold state export
files (six distinct artifacts), readonly database completion joins, 713 installed
files and the retained 93-file base kit. Two history nodes charge 103,462,466
bytes. All accepted controller/guest PIDs and groups are freshly absent. Its
private receipt hash and bounded scope are in the sanitized verification.
