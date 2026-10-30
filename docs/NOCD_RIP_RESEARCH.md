# Media-only no-CD rip research

Status: bounded research guidance, recorded 2026-10-29. This note documents a
smaller media working set for game analysis. It does not add a media optimizer
or change fDisBull's runtime.

## Goal and boundary

Reduce the files that must be copied, attached, stored and inspected while
leaving the original executable and gameplay bytecode unchanged. Keep an
immutable original and perform each qualified media rewrite on a separate
working copy. Keep game assets, decoded game scripts, byte-retaining databases
and runtime states outside this repository, as required by [AGENTS.md](../AGENTS.md).

Here, **no-CD rip** names a reduced media payload. The Lost in Time experiment
still needed a virtual CD mount; a directory-only launch requested a CD-ROM.
No executable patch was used to remove that requirement.

**Do not replace music with a one-frame track by default.** A valid, very short
track may immediately reach end-of-stream and trigger repeated restart, retry
or status polling. If the active player does that without a delay, yield or
useful progress, it can spin indefinitely and consume CPU. This is a possible
failure mode, not one reproduced in the current investigation.

Until the actual music-player instance and its start, completion, loop and stop
paths are located, keep music duration and track/segment addressing intact.
Conservative, qualified video edits are the current route for reducing media
without patching incompletely understood player code. Media-only changes still
need evidence that the game's playback contract is satisfied.

## What may change

| Surface | Current policy |
| --- | --- |
| Native executable, overlays and gameplay bytecode | Preserve the original bytes. Do not patch CD checks, wait loops, callbacks or interpreter instructions for this reduction. |
| Selected video payloads | Reduce only where the format and required frame accesses are understood. Preserve the needed frames, indices, palette state and timing information. |
| Music, speech and other audio | Preserve original duration and addressing by default. A missing track or a tiny replacement remains an unqualified experiment until player behavior is understood. |
| Media archives and disc filesystem | Rebuild dependent lengths, offsets, indices and extents consistently. Reopen the rebuilt containers and compare the intended members. |
| Transfer compression | Lossless archive compression can reduce transfer size without changing decoded duration. It does not imply a smaller installed working set. |

For fDisBull attachments, select the files relevant to the active question and
record their original identity and offsets. An immutable attachment retains its
bytes in the database; attaching a complete disc to every project can defeat
the purpose of reducing the working set. The existing attachment API is
described in [external files](EXTERNAL_FILES.md).

## Why a one-frame track needs separate qualification

Shortening a track to one frame is **truncation or substitution**, not merely
compression. The duration of a frame depends on the media format. Successful
decoding only establishes that the media is readable; it does not establish
the behavior of the caller at end-of-stream.

The relevant risks are rapid EOF/restart cycles, repeated retries after a
failed play request, and a polling loop that never observes the expected
completion state. Depending on the player, those can cause excessive CPU use,
incorrect scene timing or stalled progression. Intentional music looping is
not itself a defect: the concern is a loop without appropriate pacing or
forward progress.

Keep these alternatives distinct:

| Candidate | What it changes | Qualification still needed |
| --- | --- | --- |
| Losslessly compressed original audio | Transfer representation; decoded samples and duration are retained | The selected runtime must support the delivered representation or receive the original bytes after extraction. |
| Same-duration silent audio | Audible content; duration can be retained | Preserve supported encoding, segment/track boundaries and any relevant loop metadata; check completion and synchronization. Raw PCM silence still occupies approximately the original logical size, even if a ZIP compresses it well. |
| One-frame or very short audio | Nearly all duration, possibly seekable segment extents | Trace start, EOF, restart, retry, stop and polling behavior before accepting it. |
| Omitted audio/CDDA | Availability of an entire media source | Establish the original runtime's absent-media and completion behavior. A successful opening does not cover every later wait. |

The same-duration silence option in the earlier disc tooling was not included
in the compact ISO and was not qualified by native playback. It is not a proven
safe substitute. Preserve the original audio when its requirements remain
unknown.

## Lost in Time: evidence from the previous work

The previous private investigation separated the resource layers:

- `INTRO.STK` contains external `.TOT` game programs and their resources.
- The compatible ScummVM Gob runtime selects `Inter_v3` for Lost in Time.
- Video is IMD media inside paired ITK/LTK archives; it is separate from TOT
  gameplay bytecode.
- CD audio is a separate disc payload. Its contents were not classified as
  music-only.

The compact video profile changed **20 of 497 IMD members**. It preserved their
logical frame counts and first/final images and palettes, replacing 246 of
288 record positions with native hold records. The other 477 movie members
were byte-identical. This reduces payload; it does not necessarily shorten
the animation wait.

| Measurement | Original bytes | Derived bytes | Interpretation |
| --- | ---: | ---: | --- |
| 26 game-file payloads | 41,861,870 | 40,274,658 | Video framing saved 1,587,212 bytes, approximately 3.79%. |
| Cooked data ISO | 41,930,752 | 40,343,552 | Image saving is 1,587,200 bytes after sector rounding. |
| Separate CD-audio payload | 558,821,088 | Omitted in the experimental data-only image | A separate availability change; not a video-framing saving or a general compatibility result. |

The original mixed-mode BIN was 607,509,840 bytes. Comparing it directly with
the 40,343,552-byte data-only image mixes audio omission, sector representation
and video changes. Do not describe that whole reduction as video compression.

### Container obligations

A standalone valid IMD is insufficient if its enclosing metadata is stale.

| Layer | Required consistency |
| --- | --- |
| IMD | Complete packets, frame count, header, palette/geometry and any frame-position table. |
| ITK | Member names, lengths, offsets, packing information and alignment. |
| LTK | Cached headers, member positions, frame boundaries, indices and per-frame metadata. |
| ISO9660 | File extents, directory lengths and both endian copies of relevant fields. |

The general LTK per-frame-byte algorithm remains unresolved. The earlier
writer retained metadata for retained packets and used the observed native
mapping for exact hold records. It did not qualify arbitrary newly encoded
packets. Unknown and anomalous assets were preserved.

### What was and was not checked

The earlier independent decoder pass fully decoded all 20 altered movies and
compared their first/final images, palettes and selected metadata with the
originals. A separate original-DOS opening comparison, controlled through
fDisBull 0.22.0, produced five byte-identical screenshots with the Italian
configuration and the tested opening interaction.

That opening had no file-access trace proving that any of the 20 altered
movies was consumed. It did not qualify every seek, intermediate animation,
puzzle, CD-audio wait or a full playthrough. The experimental data-only image
therefore remains bounded evidence, not the default audio-preservation policy
in this note.

The subsequent script study indexed 1,041 unique direct media-service sites,
including 451 IMD plays, 351 CD plays, 123 CD-position queries and 49 CD stops.
It checked each site's opcode prefix, not complete execution semantics or all
indirect paths. Eight literal movie calls matched retained frame ranges in the
20-member video profile. Absence of a literal match for the other twelve did
not establish that they were unused.

### Why the music player is still an open question

The corrected decompilation of the current CD's `EMAM1017.TOT` queries the
current CD segment, checks for `INTRO`, and polls until the position is `-1`
before proceeding. This is static evidence that CD completion participates in
script flow. It does not show what the original executable returns for a
missing, truncated or immediately completed track.

The compatible ScummVM implementation provides useful leads:
`o2_playCDTrack`, `o2_waitCDTrackEnd`, `o2_stopCD`, `o2_readLIC` and
`o2_getCDTrackPos`. At the pinned revision below, both the wait helper and
position-query helper explicitly call `longDelay(1)`. Those source paths are
not evidence of an unpaced loop, and they do not identify the matching native
routine or active player state in the original DOS executable.

The native music-player code and active instance/state still need to be
located. A filename string, decompiler label or matching ScummVM function name
alone is not that identification.

## Next bounded investigation

1. Resolve the actual native player entry and state from a real playback call.
   Record the executable version, runtime address context, active state
   location and caller; keep native and decompressed TOT offsets distinct.
2. Trace one original start, progress, completion and stop cycle. Establish
   track/segment addressing, EOF/error return values, restart policy, timers,
   callbacks and where polling yields.
3. Only then compare original, absent and shortened audio on isolated copies.
   Use a bounded runtime budget and a reachable stop condition. Record script
   progress, position/completion status, play/retry counts, elapsed time and
   CPU use against the original under the same backend configuration.
4. Qualify a particular substitution only when it reaches the expected scene
   transition without unexplained retry/spin or timing regressions. Otherwise
   keep the original audio.
5. For further video reduction, resolve dynamic movie names, reuse of the
   currently open movie and EXT/MULT frame references before broadening the
   selection.

This sequence is a research plan, not a claim that those runtime tests have
already happened. Any future player-code change is a separate proposal after
the active implementation is identified.

## Sources and evidence boundaries

The measurements above summarize prior private work dated 2026-10-29, retained
outside Git in `Lost_in_Time_IT_Compact_Report.md` and
`Lost_in_Time_Interpreter_Study.zip`. Supporting receipts include
`framing-manifest.json`, `runtime-test/Native_Runtime_Comparison.md`,
`media-call-index.json` and `framed-video-call-check.json`. This documentation
change reviewed those results; it did not rerun the game or reproduce the
one-frame hazard.

Public compatible-engine references are pinned to ScummVM commit
`984277131e510e554a669e865828efb953c03941`:

- [CD play/wait/stop/status handlers and their delays](https://github.com/scummvm/scummvm/blob/984277131e510e554a669e865828efb953c03941/engines/gob/inter_v2.cpp#L509-L549).
- [IMD playback arguments, including frame ranges](https://github.com/scummvm/scummvm/blob/984277131e510e554a669e865828efb953c03941/engines/gob/inter_v2.cpp#L951-L971).
- [Lost in Time runtime selection](https://github.com/scummvm/scummvm/blob/984277131e510e554a669e865828efb953c03941/engines/gob/gob.cpp#L623-L642).
- [Lost in Time CD detection entries](https://github.com/scummvm/scummvm/blob/984277131e510e554a669e865828efb953c03941/engines/gob/detection/tables_lit.h).

These are compatible implementation references. They do not prove native
addresses, the absence of a native player bug, or whole-game equivalence.
