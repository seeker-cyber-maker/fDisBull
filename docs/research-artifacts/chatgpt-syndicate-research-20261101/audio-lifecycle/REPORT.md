# Syndicate music: cancellation, repeat, end-of-track, and caller policy

Investigation date: 31 October 2026. All work remained local. GitHub was not
contacted, no PR was submitted, and no original file was changed.

## Result and evidence boundary

The missing lifecycle distinction is now established for the examined paths.
The intro starts a looping sequence and later **explicitly stops it**. That
ordinary stop changes its status from 1 to 0; it is not evidence that the event
stream reached its end marker. In a separate, explicitly prepared DOSBox run,
the original end handler changed status from 1 to 2, returned through the real
timer caller, and left the sequence registered. The later intro stop preserved
status 2, and shutdown released the registration.

This pass used the actual original DOSBox environment for both experiments.
The second experiment contains exactly two guarded four-byte writes to the
sequence's event cursor. It did not alter event data, instructions, status words,
CPU registers, returned values, or original files. Its end-of-track observation
is **diagnostic reachability**, not ordinary completion of the shipped track.

The source-free [summary](evidence/lifecycle-summary.json) records identities,
observations, intervention boundaries, cleanup results, and scope. The two new
research tools inspect event structure and a narrow register model; they are
not a production player or a general fDisBull runtime feature.

## 1. Original intro execution cancels the sequence

A fresh baseline session used the original MZ launcher, INTRO, and FM driver.
The intro and subsequent MAIN FM bindings were checked against the selected
original driver: 38 service-entry windows and 395 internal relocation records
per observed load. The observed intro allocation was `0x349188`; MAIN used
`0x284048`. These addresses belong to those loads, not future runs.

The baseline supplies five matched service entry/return pairs:

| Boundary | Before | After | Meaning of this observation |
| --- | ---: | ---: | --- |
| Start, service 170 | 0 | 1 | Active cursor initialized |
| Intro's explicit stop, service 171 | 1 | 0 | Cancellation, not end-of-track |
| Shutdown's internal stop | 0 | 0 | Repeated inactive stop |
| Release, service 152 | Registered | Unregistered | Handle-table entry cleared |
| Shutdown, service 104 | Entered | Returned | Original driver shutdown returned |

Every matched service return had the expected stack selector, return address,
and four-byte stack unwind. Status refers to the sequence word at `+0x1E`, not
the separate start marker at `+0x1C` or an incidental EAX return value.

At the first stop, the event cursor was 11,622 bytes into the payload. The EOT
record is at offset 12,068. No EOT breakpoint hit preceded that stop. Shutdown
then issued an internal stop and released the object. Menu appearance or the
intro-to-MAIN transition must not be relabeled as natural track completion.

## 2. A small embedded presentation script explains the stop

The original INTRO executable has a table at preferred address `0x20ABC` with
**149 seven-byte records**, followed by a frame value of `0xFFFF`:

```text
+0  frame:   u16 little endian
+2  command: u8
+3  operand: u32 little endian
```

The source dispatch connects command `M` to music selection/start and command
`X` to the explicit stop helper. The two decisive records are:

| Row | Frame | Command | Operand | Recovered role |
| --- | ---: | --- | ---: | --- |
| 7 | 19 | M | 0 | Select/start sequence 0 |
| 134 | 929 | X | 0 | Explicitly stop music |

The other counted commands are L (15), E (2), A (26), S (68), and T (36).
Their full semantics are not specified by this lifecycle study. The seven-byte
table is embedded data consumed by the presentation dispatcher, not a newly
identified external file format or a general game-script language.

The diagnostic run caught the actual X dispatch: row index 134, current frame
929, matching record frame/command/operand, and the source-linked stop call.
The unmodified baseline reached the same stop caller. The live row/frame read
was collected in the diagnostic run, not retroactively attributed to baseline.
The frame numbers are presentation indices; no wall-time conversion is claimed.

## 3. The actual XMI files distinguish looping music from finite cues

The bounded, source-informed reader parsed two original files and six EVNT
streams. It records the actual source hashes and offsets and preserves any
trailing data after EOT. Delays below are event-clock units, **not seconds**.

| File / stream | Zero-count repeat | Positive-delay records inside repeat | EOT offset within EVNT |
| --- | --- | ---: | ---: |
| INTRO.XMI / 0 | Yes | 100 | 12,068 |
| SYNGAME.XMI / 0 | Yes | 300 | 1,721 |
| SYNGAME.XMI / 1 | Yes | 172 | 1,249 |
| SYNGAME.XMI / 2 | Yes | 900 | 10,382 |
| SYNGAME.XMI / 3 | No lexical repeat | Not applicable | 218 |
| SYNGAME.XMI / 4 | No lexical repeat | Not applicable | 719 |

The intro's repeat begins at event offset 10,596, with body immediately after
that control and an end control at 12,065. The zero-count path rewinds without
decrementing its counter. EOT follows the repeat end. An EOT marker existing in
the file therefore does not establish that ordinary linear playback reaches it.

This is a lexical/control interpretation supported by the inspected consumer.
The parser is not a complete runtime simulator. It does not prove all branches,
external mutations, timing, instrument behavior, or player reachability. No
lexical-repeat issues were reported for the six selected streams. Three streams
retain one zero byte after EOT; those bytes were neither deleted nor called
meaningless. The full census is in [xmi-lifecycle.json](evidence/xmi-lifecycle.json).

## 4. The shipped repeat yields in the real DOSBox environment

A second fresh guest was paused at a genuine FM timer callback after validating
the live EVNT payload against the complete original INTRO.XMI payload hash.
The first intervention moved only the four-byte event cursor to the original
repeat-begin event, skipping the long prelude. It used the current field's exact
SHA-256 as the expected-old guard and verified the resulting value.

The original timer code then:

1. Encountered the shipped zero-count repeat end.
2. Rewound the cursor through its genuine branch.
3. Reached the callback return and resumed the original timer caller.
4. Retained active status 1 and a positive delay counter of 3.
5. Reached the repeat's rewind path again on a later callback sequence.

Two rewind hits and the intervening callback return were observed. The return
used SS `0x0088`, with the expected four-byte unwind to caller `0158:0024C9C7`.
This validates a yielding repeat under the diagnostic starting position, not an
unmodified full-playthrough route. Interrupts and device instructions were not
replaced with host no-ops.

The previous synthetic no-delay experiment remains a separate result. This
pass did not deliberately run its non-yielding stream inside DOSBox, measure
CPU load, or claim that the shipped track is defective. The useful contrast is
that the actual loop contains delay events and returned from the timer callback.

## 5. End-of-track is now observed, under a declared intervention

At another original callback entry, the second and final guarded cursor write
selected the genuine EOT record at event offset 12,068. It deliberately bypassed
the repeat. No other field was edited and the original event bytes were retained.

The debugger caught the original handler at driver offset `0x2F5A`, then stopped
after its status store at `+0x2F69`. Status changed **1 to 2**. The deferred-release
flag at sequence `+0x20` was zero, so the object remained registered. The callback
returned to its original caller, with cursor advanced by the three-byte EOT
record and its expected stack unwind.

Persistent start, resume, status-query, stop, release, and shutdown watches then
followed the caller reaction. No watched start/resume/status-query entry occurred
before the intro's scripted stop. At row 134 / frame 929, the same sequence was
still registered with status 2. The subsequent stop left **2 unchanged**; shutdown
made another stop attempt, released the handle, and returned. Four complete
service pairs cover this post-EOT chain.

This establishes the selected intro caller's reaction after an injected EOT
position. It does not prove that every caller avoids restarting, that the track
ends naturally, or that silence means completion. Registration, active playback,
completion status, and release are distinct lifecycle facts.

### Intervention ledger

| Write | Field | Selected original event offset | Scope |
| --- | --- | ---: | --- |
| 1 | Sequence event cursor, four bytes | 10,596 | Skip prelude to actual repeat-begin control |
| 2 | Same cursor, four bytes | 12,068 | Bypass repeat and exercise actual EOT handler |

The baseline has **zero memory writes**. The diagnostic guest has **exactly two
memory-write requests and zero register writes**. All 38 checked entry windows,
395 relocation fields, and the full live intro event payload still matched their
expected originals before shutdown cleanup. Arbitrary mutable driver memory was
not claimed to be byte-identical to its file.

## 6. MAIN's source implements a different selection policy

MAIN's helper at preferred `0x3B8A0` compares the requested sequence index with
its cached selection. If they are equal, it returns without starting again.
For a changed selection, it stops the previous nonnegative selection and starts
the chosen handle. This is not a general "restart whenever not playing" policy.

The caller at `0x10010` selects indices 3 or 4 under terminal-state flag bits
and a latch, then calls the status helper at `0x3BA10`. For admitted status values
0/1/2, that helper reports whether status equals 1. The caller clears its latch
when the result is zero. The two selected streams are precisely the two without
lexical repeat controls in the inspected SYNGAME.XMI. This supports their role as
finite terminal cues; their player-facing names and live mission outcomes were
not tested here.

The intro contains a separate source helper that queries status and restarts
when it is not active. A bounded direct-call scan found no callers to that helper,
and the watched intro path did not invoke its status query in the post-EOT window.
That is not proof the helper is globally dead or never indirectly called.

### A source-derived partial-register edge case

MAIN's status projection compares full EAX, writes the result to AL, and clears
AH. It does not clear EAX's upper sixteen bits. Thus the established valid
statuses map correctly, but the driver's `0xFFFFFFFF` sentinel becomes
**`0xFFFF0000`**, still nonzero when the caller tests EAX.

The exact operations are bound to the inspected original source. A separately
packaged Z3 model proves the valid 0/1/2-domain projection and supplies the
sentinel counterexample. This is a conditional error-path lead, **not a verified
player-visible bug**: no legitimate path supplying the sentinel at that caller
was established or executed. Do not silently normalize the full register in a
reimplementation. See [model receipt](evidence/status-projection-model.json).

## 7. Runtime identity, cleanup, and preserved friction

The research runtime is fDisBull 0.26.0 with Python 3.13.5 from the supplied offline
kit. The installer checks passed. This turn's actual DOSBox binary SHA-256 is:

```text
45fb6ffebe01de70599403a10a4a7d4a3b003621e910c36cc63449846ad3d346
```

It matches this kit's manifest. It differs from the backend hash in the previous
audio report (`60f5496...`). These are separately identified experiments; previous
results are not being relabeled as tests of this binary. The original MAIN and
GAMEFM file hashes remain the same as the prior study.

Final verification rehashed all **897 restored original paths**, with no changed,
missing, or new game files. Neither guest created a persistent save. No new static
MAIN traversal was run; the previous 68,186 instructions / 87.49% figure remains
historical.

**Cleanup is not universally clean exit:** baseline debugger cleanup returned
emulator code 0. In the diagnostic session, `session.stop` still reported running
after its three-second wait, and close eventually reaped the process with code
**-9 (SIGKILL)**. Both owned PIDs were absent at final audit. All decisive target
observations and the preservation check preceded this cleanup. The result is a
bounded cleanup escalation, not proof of a guest hang or a DOS program exit.

Other retained friction:

- A breakpoint requested before its selector/address existed was refused. The
  observer later waited for a validated module binding instead.
- The second guest's fixed early start-watch window missed the natural start.
  The preparation stopped without edits, then switched to a genuine timer-callback
  entry. An undefined local variable in a preliminary observer command likewise
  failed before any write. These are instrumentation errors, not game failures.
- Protected-mode absolute mouse clicking remained refused. Twenty bounded mode
  samples did not provide a qualified real/v8086 click boundary. No substitute
  input injection or mission-success claim was made.
- A source-informed proof draft initially mixed integer and bit-vector sorts.
  A summary draft initially expected the wrong receipt field name. Both failed
  before producing their final result; the corrected tools did not rerun actions.
- One auxiliary baseline event file used literal escaped separators. The valid
  full JSON event arrays and raw RPC log remain intact and supplied the audit;
  no event reconstruction from that malformed auxiliary file is claimed.

The recorded RPC log contains **5,823 requests** (3,552 baseline, 2,271 diagnostic).
The client sequence counters are larger by three per session because startup
requests preceded logger installation. Timing/wait polling accounts for 5,370
logged requests. Only 74 created/deleted breakpoints. This is observed research
instrumentation cost, not a proven unavoidable backend cost or speedup estimate.

## 8. Local PR recommendations and acceptance cases

These are prospective implementation/skill requirements, not new production
features or already-passing acceptance tests.

| ID | Requirement |
| --- | --- |
| LC01 | Preserve completion reason separately from active/stopped status and registration. Original stop 1→0 and EOT 1→2 must not collapse into one success certificate. |
| LC02 | Bind cue identity, EVNT stream extent, source-relative cursor, repeat/yield structure, handle, and load generation. An EOT marker after an unbounded repeat is not automatically reachable completion. |
| LC03 | Trace caller policy explicitly: same-selection suppression, finite terminal cues, automatic restart, explicit cancellation, deferred release, and shutdown are different contracts. |
| LC04 | Diagnostic cursor changes require exact expected-old identity, source-bound event boundaries, explicit intervention provenance, readback, bounded execution, and no inherited ordinary-reachability claim. |
| LC05 | Module-aware deferred breakpoint setup must distinguish unmapped-yet, wrong load, unsupported address form, and valid binding; fixed startup delays cannot substitute for readiness. |
| LC06 | Preserve register width in service adapters. A valid-domain Boolean projection must not silently erase an invalid/sentinel upper-half value without a declared semantic change. |
| LC07 | Record stop acknowledgment, timeout, forced termination, reaping, and selected-program exit independently. A closed controller or status 2 must not certify clean guest shutdown. |
| LC08 | Report observer requests by category and reuse persistent watches where supported. Investigate wait/timing polling overhead without claiming measured speedup or weakening evidence. |

The recommendations extend the earlier DG/AP local draft. The add-only patch
adds this report, the source-free receipts, two authored research tools, and
the parser tests. It does not edit current runtime behavior or bundled skills,
contact GitHub, rebuild a release, or alter #69. Upstream reconciliation remains
required before later publication.

## Verification and next work

Twenty-one authored reader tests passed. A fresh census with the delivered
reader exactly reproduced the earlier census from this turn for both original
files and all six streams. Two typed Z3 checks returned the expected unsat/sat
outcomes. Their script identity is recorded. Live baseline and diagnostic evidence
are separate from those parser/model tests.

The next discriminating target is one finite MAIN cue (index 3 or 4), reached
through a source-supported terminal-state context: observe start, natural EOT,
the real status query, latch clearing, and release or reselection. No such mission
or native finite-cue sequence is claimed here. The source-derived sentinel path
also needs a legitimate registration/error route before being called a game bug.
