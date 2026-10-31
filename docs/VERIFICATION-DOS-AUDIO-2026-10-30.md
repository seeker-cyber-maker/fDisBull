# AIL and named DOS audio API acceptance — 2026-10-30

The implementation is source commit
`e6257bdfab58b518eb380f66593c8c5db4f80de5`. The following documentation commit
`d8f02d0fdd7651a1668b6c26f4ebe2c17daff7cb` has identical production and test
trees. Parent verification compared all 344 tracked source/player/test files
with the implementation pin and found no differences. Later commits containing
this report are documentation only.

No package, backend build, release, installation or activation was performed.
Commits carry `[skip ci]` because this repository's automatic CI also builds
distributions. Automatic required checks may remain pending; this report is
not a merge or release-readiness certificate.

## Implemented behavior

- Byte-driven AIL 2 recognition, validated function directory and file-backed
  offsets, named exports and a bounded descriptor candidate.
- Original-byte import as an x86/16-bit library with no process entry and
  explicit module-relative addresses. Exports join deferred recursive seeds;
  a budget stop remains incomplete.
- Forty-seven documented DIGPAK/MIDPAK INT66 selector contracts, including
  a read-only catalog/query method and named stored DOS disassembly.
  The catalog now has 84 entries including the earlier DOS/BIOS subset.
- A sample-descriptor layout and selected register contracts for UDC consumers.
  Raw bytes/operands, comments, authorship and earlier byte versions remain
  separate from authored API names.
- Candidate names retain unverified-handler, unobserved-runtime and
  unknown-outcome fields. No driver is installed or executed by inspection.

Usage is in [DOS audio drivers](DOS_AUDIO_DRIVERS.md). The
[hardware-boundary note](UDC_HARDWARE_BOUNDARIES.md) records original mouse,
video, keyboard, timer, DMA, joystick and memory-manager dependencies and a
proposed host-adapter qualification ladder. It does not implement a native host
device backend or expand the DOS UDC's executable semantics.

## Source checks

The affected portable suite passed **87 tests**, with **4 existing native
environment skips**. It covers AIL recognition, malformed/wrong-family inputs,
aliases, deferred/budgeted analysis, restart, isolated patch versions, real
SVG/PNG exports, audio contract queries, selector ambiguity, and neighboring
module/DOS/UDC behavior. Twenty tests are new in this change.

The repository-wide command was run from this checkout. A subsequent run with
the source path explicitly propagated to subprocesses produced:

```text
PYTHONPATH=src:player python -m pytest -q
2051 passed, 130 skipped, 12 failed, 23 errors
```

A control replaced only the six modified preexisting production modules with
their exact `16d4704` versions through a private import hook; every other
preexisting source/test file was unchanged, and the two new test files were
excluded. That control produced **2031 passed, 130 skipped, 12 failed and
23 errors**, with the exact same failing/error test set. There were no added
failures. Two failures concern ELF expectations on macOS; ten concern absent
optional managed-decoder dependencies. The 23 setup errors concern Linux ELF
fixture build/link options on macOS. These limits remain visible.

An earlier run without explicit source PYTHONPATH had one additional CLI
failure because its child selected the installed 0.8.1 command. The corrected
source invocation and the unchanged-source control distinguish that environment
problem from an implementation regression. No installation was changed to make
the tests pass.

The parent also imported original SBPFM.ADV, analyzed it, exported a 1560×1952
PNG and an SVG from stored state, patched a private child version and reopened
the project. The original bytes and 38 exports remained intact. Both starts
of the original overlapping OR/IRET workaround remain stored. The files and
byte-retaining project are private.

## Luna's original-file batch

Luna used `gpt-6-luna` and tested the pinned source independently:

- All **9 original ADV files** were recognized and imported as AIL. Each had
  **38 named exports**, a null process entry, a module-relative address space,
  and a static descriptor requesting 120 service calls per second.
- All **27 COM files** imported explicitly as COM and were not misidentified
  as AIL. An AIL copy with an unrelated suffix still recognized by bytes.
- Stored original blobs matched byte-for-byte. Fresh CLI processes reopened
  the projects and retained their budget/pending-work state. A one-instruction
  budget was never presented as stable.
- A truncated AIL, wrong-family COM and MIDPAK.AD data were rejected as AIL.
- The actual MSEQ.COM INT66 instruction displayed `MIDPAK.play_sequence` while
  retaining `cd66` and raw operand `66h`. CLI and JSON audio queries retained
  the candidate/unknown qualifications.

The parent separately read all nine databases in read-only mode and verified
their retained source bytes, mapped bytes, null entries and 38 exports.

## Accepted native batch

The existing arm64 DOSBox-X backend hash was
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.
The actual launch had `SDL_AUDIODRIVER=dummy`, mixer `nosound=true`, and MIDI
`mididevice=none`. Guest sound services remained enabled. No investigator or
coordinate-control fallback input was used.

One fresh continuous original-game context completed:

```text
Park office → street → bank → office → game menu
→ quit confirmation → decline save → exit to DOS
```

Public continuations were used only while offered. The first retained context
was Park office; an explicit New Game menu selection is not independently
qualified by this protocol. Ordinary navigation also produced native pointer
movement. This confirms a bounded scene/input route, not an outside-DOSBox
mouse implementation or complete playthrough.

The observer recorded **34 audio caller requests, 34 resident-handler entries
and 34 post-IRET returns**, with no unmatched audio returns:

| Selector | Named contract | Observed requests |
|---|---|---:|
| 0689h | DIGPAK.sound_status | 12 |
| 068Ah | DIGPAK.preformat_audio | 12 |
| 068Bh | DIGPAK.play_preformatted_sample | 7 |
| 0702h | MIDPAK.play_sequence | 3 |

The live handler carried MIDIKR. The game read the full original MIDPAK.COM,
SBPRO.COM, SBPFM.ADV, MIDPAK.AD and DINO5A.XMI inputs. Seven preformatted-sample
calls exposed SNDSTRUC snapshots, including 22 kHz/57,088-byte and
11 kHz/3,376-byte requests. Their sampled status WORD was 1 before and after;
no status transition was captured, so sample completion remains unknown.
No 0688h request occurred in this cohort; the game used the preformatted path.

All three 0702h calls returned AX=0064h. A separate original-code trace shows
the MIDPAK path calls AIL set-relative-volume and set-relative-tempo, then
returns without normalizing AX. This supports an older ABI variant. It does
not turn 0064h into a documented success or completion result. The first
cohort also observed XMIDI registration returning AX=2 for a 6,822-byte input;
that observation remains separately scoped.

The final public exit receipt was success/complete and contained the selected
DOS kernel certificate: PSP **0814h**, parent **0701h**, requested code **0**,
nonresident, source `DOS_Terminate`, stage `after-process-cleanup`. The
provider had no action failures, pending command, recovery hold or pending
effects. The owned native backend returned 0 and no longer existed at parent
readback. These are executable-termination facts, distinct from closing a
frontend.

The parent independently checked these raw receipts, source identity, actual
quiet-launch controls, native selector/name matches, return ownership and
process closure. All **136 bounded audit checks passed**. All **192 local
original-directory files** present at intake rehashed unchanged. No audible
output or all-hardware compatibility is claimed.

## Preserved failed cohort and friction for the next release

1. **Observer ownership at a guest-time boundary.** The first cohort stopped
   before sending `go street`: an owned MIDPAK breakpoint surfaced as native
   `breakpoint`, with no hook hits, after 116 measured guest milliseconds of a
   100 ms request. The private wrapper forwarded it as a scene stop. Its
   unknown outcome is preserved and was not replayed. A repaired private
   policy handles only owned observer stops and retains raw stop evidence;
   all unowned/exit/fault/timeout results pass through. Its authored classifier
   test passed independently. The accepted fresh cohort did not trigger that
   exact fallback branch live, so native coverage of that branch is still
   partial. A first-class filtered observer interface should preserve this
   ownership/budget distinction.
2. **Observer shutdown after target exit.** The successful cohort's observer
   attempted a final IVT read after DOS termination and correctly received
   `TARGET_EXITED`. Guest/backend closure succeeded; final IVT readback is
   unknown. Thirteen owned breakpoint IDs remained recorded at exit, with
   no live backend left to detach from. Observer lifecycle notification and
   cached close receipts would avoid unnecessary reads of a freed target.
3. **Trace volume.** The accepted observer retained 5,415 events, including
   1,191 DOS request/result pairs and 2,854 hook records. Compact filtered
   native event batches would reduce this cost while retaining full evidence
   when a caller asks for it.
4. **Version-specific return contracts.** MIDPAK's 0064h return is a concrete
   reason to bind a UDC implementation to driver/version evidence rather
   than treating a documented name or generic return map as a completion
   certificate.
5. **Source acceptance environment.** Child commands can select an older
   installed tool without an explicit source path. Platform-specific ELF
   fixtures and optional dependency gates also need clearer environment
   handling. The current report preserves their baseline failures.

Original resources, byte-retaining databases, raw frames, private diagnostic
scripts and native receipts remain outside Git and tool packages. The private
evidence root is `ail-driver-apis-20261030-01`; earlier sealed studies remain
separate. The private wrapper repair is an experimental observation policy,
not a production debugger behavior change in this PR.
