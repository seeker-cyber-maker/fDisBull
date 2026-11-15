# Doom PC-speaker, PS/2 mouse and LE recovery — local qualification

The original private Ultimate Doom 1.9 executable now has a fresh, bounded QEMU
E1M1 witness with **mouse input and PC-speaker sound enabled**. The existing
native engine and tool runtime were used unchanged. The new repository work
adds an authored DOS-driver recovery test and a reproducible
[qualification recipe](../../DOS_DOOM_AUDIO_MOUSE.md).

This earns a PC-speaker/PS/2 application and persistence gate. **Sound Blaster,
OPL/FM music and paired DOSBox-X audio/relative-mouse parity remain open.**
DOSBox-X stays default and retained; no CI was dispatched.

## Original game acceptance

The EXE and WAD retain their original SHA-256 identities in the
[sanitized receipt](verification.json). A new private FreeDOS derivative loads
the pinned CuteMouse executable in PS/2-only mode. A copied configuration uses
mouse input, PC-speaker SFX and no music. A fresh boot runs
`-warp 1 1 -skill 2 -nomonsters -config D:\DEFAULT.CFG`; the retained hot and
cold command tails are identical. No earlier
`-nosound -nomouse` machine archive supplies this startup.

- A physical left-button shot changes ammunition **50 → 49** and produces
  **6,784 nonconstant samples**, 32 kHz unsigned 8-bit mono, without overflow.
- From the same restored source checkpoint, a **512-count horizontal mouse
  input plus 500 ms** turns the camera. An equal 500 ms interval without mouse
  input retains the forward-facing geometry. The differing pixels are above
  the HUD. This is application response, not cursor-coordinate calibration.
- An explicit LE checkpoint and two capture-history nodes restore hot and in
  a **separate Python process**: six restores match exposed CPU, canonical
  source site, virtual clock/instruction counter, stored PNG and audio
  count/chunks, under fresh source/clock/audio ownership. The original MZ
  mapping remains retired and task/allocation lifetime remains unqualified.
- Literal retained PCM at explicit A and history root A matches before/after
  restore. A new shot after hot and cold restore changes ammo **49 → 48** and
  extends the saved prefix to **12,864 samples**. Both continued PCM payloads
  are byte-identical, with 6,080 new nonconstant samples. No restored-B WAV
  was separately exported; B has native sidecar/readback and chunk evidence.
- All **eight** campaign QEMU handles are reaped with return code 0, and both
  controller groups are empty. Closing an emulator is not a guest-exit claim.

An independent analysis uses a published PC-speaker divisor table that matches
all 128 entries in the original executable. The independently recovered pitch
of each of 19 audio callbacks fits the original pistol sequence in order under
one shared timing offset. Reversed-pistol, shotgun and menu controls do not fit.
This is callback-sampled pitch/cadence consistency. The capture observes only
19 of 27 source tone slots; independent phase fitting, buffering and a feasible
cadence range prevent a lossless envelope, exact onset or unique-140-Hz claim.

## Authored driver gate and preservation

The new `tests/test_qemu_dos_mouse_native.py` passes against the installed frozen
wheel and exact native kit. The guest initializes INT33, consumes unaccelerated
physical deltas **+3 then +2** through AX=000Bh, and observes left/right button
press/release through AX=0003h. Exact cumulative counts are **3 and 5**.
Pending/held input capture refuses without mutation; released-input hot and
reopened-Project recovery preserves CPU/report bytes, rejects an old lease,
consumes fresh input and reaches real DOS exit 42. This authored cold reopen is
within one Python process; the separate-process result above is actual Doom.

Two failed fixture attempts are preserved privately. The first exposed a race
between draining motion and observing a newly updated button; the guest now
observes buttons before draining motion. The next measured 12 → 36, explained
by CuteMouse's independently inspected adaptive gain. The final test uses the
driver's documented small-packet branch; it does not fit its oracle to the
observed accelerated value. A separate initial Doom controller mistake passed
an unsupported `gap_ms` click argument and closed before input dispatch.

Fresh verification:

- **461 installed host cases pass**, zero failures/errors/skips. The duplicate
  ZIP-member warning is produced by an existing malformed-archive negative.
- **Nine existing native preservation cases pass**, including separate-process
  clock/audio/display/retrace plus active layers/hooks, owned recovery/frame
  keys, COM/MZ continuation, and nested RTC/keyboard PIC/IRQ recovery.
- The corrected **new native driver case passes** separately, zero skips. The
  earlier run containing the failed fixture is retained rather than recast as
  an entirely passing suite.
- All 713 production files match committed source, the frozen wheel and private
  prefix before/after. The 93-file native kit and selected dependencies match.
  Only tests/documentation change in this qualification slice; no emulator
  rebuild, new release, shared activation, backend switch or CI occurred.

## Next parity gates

The native checkpoint graph deliberately supports one equal-rate PC-speaker
voice. SB16 restore currently recreates its software voice, loses mixer state
and omits relevant timer/availability state. AdLib provides no VMState handler.
New device support must preserve bounded mixer/resampler queues, DMA/IRQ/timer
state and FM synthesis state before its checkpoints/histories can be qualified.

The current DOSBox-X headless route has no comparable PCM capture and its
absolute INT33 cursor API does not supply relative mickey motion. A paired
reference needs explicit native capture/relative-input witnesses. These gaps
remain gates rather than being inferred from QMP acceptance or a nonempty WAV.
Existing trials, selected undo, layers, hooks, histories and IRQ contracts keep
their separate scope; this work does not establish new LE trials or continuous
task lifetime. Commercial inputs, screenshots, audio, states and FDB/CAS remain
private.
