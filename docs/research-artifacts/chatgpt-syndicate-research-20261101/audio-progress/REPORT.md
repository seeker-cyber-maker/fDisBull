# Syndicate audio: natural service calls, timer context, and repeat-loop progress

Investigation date: 31 October 2026. All work and PR preparation remained local;
GitHub was neither queried nor modified. This continues the earlier driver-load
study rather than repeating the static coverage pass.

## Executive result

A fresh original DOSBox session produced **42 complete driver entry/return
observations**: 41 automated pairs and one manually qualified FM timer callback.
The live driver tables and relocations were revalidated during both INTRO and
MAIN. The observations distinguish ordinary dispatch, an internal driver call,
and an interrupt-stack callback. They also show why several EAX returns must
not be interpreted as Boolean success or playback completion.

A separate, bounded experiment executed the original FM callback with synthetic
events. An unbounded repeat whose body contains no delay **did not return within
8,000 instructions**, visiting its rewind path 87 times. Putting a delay inside
that body allowed the first callback and two continued callback preparations to
return. The source's nondecrementing zero-count branch explains the result.
This is a concrete forward-progress hazard, not a demonstrated defect in the
shipped music and not a claim that every shortened track will hang.

The two evidence environments remain separate:

| Evidence | What actually ran | Main limitation |
| --- | --- | --- |
| Natural service observations | Original MAIN/INTRO and drivers in the supplied DOSBox-X backend | Sampled calls and paused states, not audible fidelity, full missions or every service |
| Repeat-loop experiments | Original GAMEFM instructions in Linux x86-32 compatibility mode, with explicitly prepared memory and authored event bytes | No DOS/4GW, interrupt delivery, devices or normal-game reachability |

The report's machine-readable companion is
[evidence/audio-progress-summary.json](evidence/audio-progress-summary.json).
It retains identities, addresses, case counts and private receipt locators without
distributing original memory, screenshots or executable payloads.

## Runtime, identity, and preservation

The supplied fDisBull **0.26.0** offline installer passed its checksums and checks
in an isolated Python **3.13.5** environment. This does not qualify or install a
newer repository head. The actual backend used in this session has SHA-256:

```text
60f5496b0e67e83f938f04cc9fce09ea475a09122c33fa24e9e89ea07a925e1f
```

The original MAIN identity remains:

```text
bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078
```

The selected original driver identities are:

```text
GAMEDG.DLL  99acf41846f02fac929d4282a1650e6d1aeff4647b3624d89055589f0ac4d4c9
GAMEFM.DLL  520db726d034394e7ea7f62b9bfa90767898990836522fc09f89931f2c388a7e
```

The existing source-informed recovery tool restored 897 previously inventoried
paths representing 605 payloads from the supplied installer. Each matched its
retained size/hash identity. Filenames were reused from the prior manifest;
this was not a new generic Inno Setup parser. All 897 paths rehashed unchanged
after the live session and again after the isolated experiments. No new game
files appeared. No original code, driver return value, register or game-memory
value was patched during the live DOSBox session.

The live run identifier was `0ca400b1c82c40e7b41883d6cc6feec4`. At closure there
were no owned or queued keys, no remaining owned controller/emulator processes,
and the emulator returned zero. This is debugger cleanup, **not** a witnessed
DOS program exit or a native save/reload claim.

## Fresh module bindings and load generations

| Phase | Driver | Image base | Table | Entries | Fixup records checked |
| --- | --- | --- | --- | ---: | ---: |
| INTRO | GAMEDG | `0x002719F4` | `0x00271A23` | 19 | 276 |
| INTRO | GAMEFM | `0x00349188` | `0x003491B7` | 38 | 395 |
| MAIN | GAMEDG | `0x001971F0` | `0x0019721F` | 19 | 276 |
| MAIN | GAMEFM | `0x00284048` | `0x00284077` | 38 | 395 |

These numerical allocations happen to equal the prior run's, but were verified
again from this run's registry and paused module images. They are not constants
for future sessions. Every table key/pointer, the 16-byte entry window of every
service, and every supported relocation field matched the original driver
rebased to its observed allocation. Mutable driver data does not need to equal
the file; no whole-live-image equality is claimed.

The intro returned to MAIN naturally in this run, without an Escape shortcut.
The intro breakpoints were removed before watching the newly loaded modules.
MAIN's five registered FM sequence handles were 0, 4, 8, 12 and 16, offsets into
a pointer table rather than unscaled array ordinals. At the sampled main-menu /
world-map boundaries all five sequence states were inactive. Fields such as
an event cursor are not meaningful merely because their bytes can be read:
registration initializes selected fields; start service 170 establishes the
active cursor. Old-looking cursor bytes in an inactive object are not, alone,
evidence of corruption.

## Service return contracts: a pointer is not a success flag

All 41 automated pairs hit the expected original return address with the
expected four-byte stack unwind. The separately captured timer callback adds
one more pair. These are observations of selected calls, not exhaustive API
specifications or independent samples of every possible argument domain.

| Driver/service | Complete pairs | Observed result | Supported interpretation |
| --- | ---: | --- | --- |
| Digital 133 | 18 | EAX equals the live service entry address; no module-data differences in those windows | Stub-like path with an incidental register return, not Boolean success |
| Digital 123 | 9 | EAX=5; state at module `+0x1E2` ends at 0 | VOC setup/scan path; first argument points to VOC data in all nine inspected prefixes |
| Digital 125 | 9 | State 0 becomes 2, while EAX takes five different values | Start/resume effect must be distinguished from incidental return value and later completion |
| Digital 126 | 4 | State becomes 0; EAX=5 | Internal stop calls from the driver, not four public bank-dispatch invocations |
| FM 170 | 1 | Active fields initialized; EAX equals the EVNT payload cursor | Sequence start; returned pointer is not completion |
| FM 103 | 1 manual pair | Actual timer callback entered and returned on SS=`0x0088` | Interrupt-context execution, not a bank-prefixed ordinary call |

### Digital 133 and flags

Digital service 133 is at module offset `0x157E`. The dispatcher puts the
selected entry address in EAX before jumping there. The service does not replace
EAX, so all 18 captured returns contain `0x00272F72` in this INTRO allocation.
Calling this a positive status would invent a contract.

It is also too strong to call the routine side-effect-free. Its stack-adjustment
instruction affects arithmetic flags; flags differed at entry and return in
**all 18 observed pairs**. The scoped finding is that the sampled module-data
windows did not change and EAX was not normalized, not that every architectural
effect disappears.

### Digital state changes

For service 123, the prior state was 3 in six calls, 2 in two calls, and 0 in one;
all nine ended at 0. The pointed-to input prefixes all contain the Creative
Voice File magic. That associates the calls with VOC buffers, but this pass did
not assign every buffer to a complete named resource or verify rendered sound.

All nine service-125 windows changed state 0 to 2. Their EAX results were:

```text
0x00000000: 4 calls
0x00001127: 2 calls
0x00005231: 1 call
0x000051DC: 1 call
0x0000BABB: 1 call
```

The same immediate state transition with different returns is a practical
counterexample to treating nonzero or zero EAX generically as success/failure.
The source has a separate state-query service 124 at `+0x16F5`. Source inspection
also identifies state-2-to-1 and state-1-to-2 paths in services 127 and 128.
Those three services were **not** observed returning in this session; their
interpretations remain source-derived.

## Timer context changes the stack interpretation

The natural FM callback was captured at `0158:0034C1FA`, corresponding to module
offset `0x3072`. Its SS was `0x0088` and ESP was `0x6CBA`, unlike foreground
service calls using the flat `0x0160` stack selector.

An initial observer read ESP as a linear address and obtained irrelevant zero
memory. A segmented **SS:ESP** read recovered the real return address
`0x0024C9C7`. Execution then hit that return, with ESP advanced to `0x6CBE` and
SS still `0x0088`. Source inspection connects the caller to the timer chain;
retirement of the later IRETD was not separately captured.

Likewise, an internal call to digital service 126 does not have the public
registry bank number in the same stack position. The observer was corrected
to classify the calling path, not to reinterpret an arbitrary stack word as a
bank. Both initial observer mistakes are retained as instrumentation friction,
not target crashes, patched-driver behavior or decoder defects.

A module service catalog should therefore carry **invocation context** as well
as an entry address: registry tail-dispatch, internal near call, timer callback,
or an explicitly unresolved calling convention.

## FM sequence progress and completion remain different observations

The naturally started INTRO sequence object was `0x00253AE8`. Service 170
initialized its cursor to `0x003411EA`, eight bytes after its EVNT chunk header
at `0x003411E2`, and set the words at `+0x1C` and `+0x1E` to 1. It left that
same pointer in EAX on return.

Later samples found the cursor at `0x003426BE` and `0x00343BD7` while the sequence
remained active. This is evidence of event-stream progress. It does not establish
audible output, original playback speed, event-by-event equivalence or completion.

The source's end-of-track meta handler, entered through module offset `0x2F5A`,
sets status `+0x1E` to 2 and optionally releases the sequence when `+0x20` requests
it. The latter field is a **deferred-release flag**, not a music-loop counter.
The local end handler does not itself restart the sequence; callers could still
do so. Service 174 reads the status for an admitted handle.

A live breakpoint on that end branch did not fire during the bounded observation
before the intro returned to MAIN. Consequently this report does **not** promote
the source-derived end state to a live-observed end-of-track transition. Silence,
a return from start, or transition to the menu cannot substitute for that witness.

## Original repeat-controller code can fail to yield

The original FM control handler contains loop controls with controller bytes
`0x74` and `0x75`. The exercised ending value is `0x7F`.

- The begin control stores an event pointer and a count in one of four slots.
- A positive count is decremented on loop end; the finished slot is marked
  `0xFFFF`, otherwise the event pointer is rewound.
- A count of zero takes a rewind path without decrementing it.
- The timer callback can immediately process another event in the same call.
  A delay event is the path that yields before subsequent processing.

Thus, an unbounded loop whose body has no delay can remain in one callback.
A delay after that loop does not help when the loop never reaches it.

### Bounded actual-instruction experiments

These inputs are authored diagnostic event sequences, not modified shipped
tracks. They ran original instructions from the exact GAMEFM file under the
separate host compatibility harness. Calls used fabricated initialized sequence
state, not a captured original DOS stack. No I/O, CLI/STI or interrupt instruction
was skipped: the harness stops before such an instruction if encountered.

| Authored case | Outcome | Steps | Rewind-path visits |
| --- | --- | ---: | ---: |
| Count 1, no body delay | Returned | 222 | 0 |
| Count 2, no body delay | Returned | 314 | 1 |
| Count 0, no body delay; delay only after loop | Instruction limit | 8,000 | 87 |
| Count 0, delay inside body; first invocation | Returned | 132 | 0 |
| Delayed-loop continuation, second invocation | Returned | 149 | 1 |
| Delayed-loop continuation, third invocation | Returned | 149 | 1 |

The no-delay case reached the event-fetch boundary 89 times and stopped with
its zero loop counter and cursor back at the loop body. This finite run alone
is not a mathematical proof of infinite execution. The separately inspected
zero-counter branch supplies the causal nontermination explanation for this
prepared domain. The test deliberately terminates at its instruction bound.

The continuation cases copy the first test's observed sequence and relevant
driver-global post-state into fresh processes. They are not DOS checkpoint
restores or live timer deliveries.

All six cases were reproduced twice, including once after clarifying the
packaged harness's observation label. Across **18 host children**, all matched
their expected return/limit outcome and were reaped. Core counts and end states
match across the three runs. This is reproducibility, not independent validation
by a second implementation. The final six cases bind the exact delivered tools.

The mixed code/data LX image is privately mapped RWX. Before each step the
harness compares the upcoming instruction window with the pinned original
mapping and refuses a changed window. It is a trusted-input research instrument,
**not a malicious-code sandbox**. It checks only a narrow admitted, device-free
path and is not a substitute for the real DOSBox observations above.

### Consequence for media reduction

Safe media reduction needs a **forward-progress contract**, not just a valid
header, acceptable CRC, decodable events or a preserved last image. Preserve
needed delays/yield points and loop/termination behavior, or qualify a specific
replacement against the actual consumer and its caller.

This study does not show that the current assets contain the problematic loop,
that a one-frame replacement necessarily creates it, or that the game spun in
DOSBox. CPU utilization was not measured. It establishes one original consumer's
specific zero-delay hazard under an explicit preparation, with finite-loop and
delayed-loop controls. All actual game music remains unchanged.

## Tool friction and bounded recommendations

The observer issued **3,353 recorded requests**. Of those, **2,893** created or
deleted breakpoints because this conservative script repeatedly dismantled a
watch set while awaiting a matched return. This is the script's measured overhead,
not a proven unavoidable backend cost. Reusable, filtered call watches or batch
operations could reduce that cost; no implementation or speedup is claimed.

Two backend refusals are retained: an unpadded breakpoint offset was rejected
until formatted as `0xNNNNNNNN`, and absolute clicking was refused at the current
protected-mode boundary. A 40 ms F2 press was queued without the intended visible
transition; a later 700 ms F2 press reached the world map. The latter is a measured
input preparation, not a universal keyboard-delay requirement. No mission was
completed. A final pause caught real-mode execution, underscoring that capability
must be qualified at the current boundary rather than assigned permanently to
the whole game.

| ID | Proposed acceptance requirement |
| --- | --- |
| AP01 | Service outcomes distinguish entry/return, incidental register values, state change and completion. Returning an entry address or event pointer cannot automatically certify success. Preserve live flags where relevant. |
| AP02 | Observers resolve stack memory through the current SS and classify public dispatch, internal calls and callbacks. Nested invocations cannot inherit a fictitious bank argument. |
| AP03 | Media qualification includes per-callback progress limits and loop/yield semantics. The no-delay zero-count negative control must stop as non-returning within its bound; the delayed control must resume and return without modifying original instructions. |
| AP04 | Bind driver, handle and field meanings to source and load generation and lifecycle. Retire old addresses on reload and avoid interpreting inactive cursors as live state. |
| AP05 | Reuse registered observers or batch watched sites where supported. Preserve matched entry/return evidence, interruption handling and explicit unresolved outcomes while reporting actual observer cost. |
| AP06 | Input capability reports include current mode/driver constraints; queued, consumed and completed remain distinct. A refused absolute click is not silently replaced by an unqualified mouse mechanism. |

These are proposed tool/skill improvements, not a new production API or passing
production acceptance suite. The pending local PR receives this addendum. Its
older graphics patch is preserved and has not been rebased against remote main.

## Scope closure and next discriminating work

No fresh static MAIN traversal was performed. The prior 68,186 instructions and
87.49% executable-object storage figure remain historical, not a new result.
No whole-game equivalence, driver hardware fidelity, actual end-of-track witness,
original music modification, save persistence, or DOS program exit is claimed.
No repository test suite, package release or shared installation was changed.

The next useful live experiment is a named sequence start/status/finish trace
from a qualified game context, including the caller's restart/release policy.
The no-delay hazard can then be tested in an explicitly disposable DOSBox trial
with an interrupt-aware budget, while preserving the unmodified music baseline.
Such a trial was not performed in this pass. Runtime observation should remain
the first choice when its existing environment can settle the question.
