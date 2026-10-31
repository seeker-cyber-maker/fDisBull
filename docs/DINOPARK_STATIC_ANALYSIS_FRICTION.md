# DinoPark analysis friction and retained Z terminal replies

The [October 31 content-accounting follow-up](VERIFICATION-DINOPARK-CONTENT-ACCOUNTING-2026-10-31.md)
closes the file/format and physical-byte inventory, adds a native sound-expander
comparison and diagnoses the original demo's early stop. Its later measurements
retain the distinction between byte accounting and complete semantic analysis.

This records observed analysis limits and proposed follow-ups from a private
DinoPark MZ investigation on 2026-10-30, followed by bounded native asset tracing.
The PR now also implements [oversized Z reply recovery](Z_REPLY_RECOVERY.md):
the original result is retained before transmission and can be retrieved without
repeating an input. The static-analysis and remaining observer/menu proposals
stay prospective. No original routine or resource is certified unused.

The investigation used source version **0.26.1**, pinned at
`43d24a73d744516653d53d3bc8828787c499d299`, with the source import path set
explicitly. Original executables, byte-retaining databases, resource inventories,
decoded media, addresses and raw receipts remain outside this repository and
tool packages. No native game was launched for this static study.

## What was measured

- The original file is 268,480 bytes: an 18,432-byte MZ header and a
  250,048-byte file-backed load image, with 4,139 relocation records and no
  appended overlay. These measurements describe this supplied edition.
- Recursive entry/reference discovery drained its native queues and stored
  46,294 instruction rows, covering 119,983 distinct physical bytes.
- Further original-file hypotheses came from frame prefixes, known compiler
  stack guards, register-save entries, library-return boundaries and bounded
  snapshot switch tables. Normal native analysis decoded those roots; no
  resolved indirect edge was injected to make the graph appear complete.
- At a retained intermediate snapshot, 74,565 instruction rows covered
  193,108 distinct bytes, or 97.965% of the 197,120-byte region before DGROUP.
  The remaining 4,012 bytes included 804 bytes of recognized snapshot jump
  tables. This is a physical representation measurement, not a reachability,
  function-count, whole-file code, or semantic-completion percentage.
- A full scan of shipped filenames produced useful resource candidates, but
  indirection through a string file, formatted plant names and references in
  configuration programs eliminated several apparent orphans. A filename
  missing from EXE literals is insufficient evidence of unused content.

The private report retains every producer stage and its qualifications. Added
roots remain hypotheses. In particular, a switch case or an unrolled rendering
body must not silently become a confirmed function entry.

## Friction and proposed acceptance criteria

### Separate queue closure from analysis and coverage

The native queue can be empty while derived jobs remain partial. One retained
stage had **791 done / 114 partial** derived jobs after native discovery closed.
Its overall stable flag correctly remained false. Stored-state image headings
can nevertheless emphasize the native fixed point and pending count without
the derived qualification being equally visible.

Proposed follow-up: show native discovery, derived jobs, unclassified mapped
bytes, unresolved transfers and hypothesis roots as separate fields in compact
status and image exports. Preserve physical-byte deduplication across CS aliases.
Do not turn a finite-budget stop into either stability or proof of dead code.

### Make raw-pattern scan limits actionable

`function-patterns --scan-unexplored` inspected the full load-image byte range
but hit its **4,096 candidate-check cap**. Its scan result correctly reported
partial status. Segment-context alternatives and epilogues contributed many
items; reading all bytes did not mean that all candidate checks completed.

Proposed follow-up: expose a durable continuation/cursor and independently
report bytes visited, physical candidate positions, CS alternatives checked,
candidate-check budget and remaining work. Allow callers to select prologues
without consuming the same discovery budget on return/tail evidence. A later
resume should not repeat already qualified work or discard its provenance.

### Retain bounded table hypotheses without overriding safety checks

The investigator recognized **53 original-file near jump tables**: 50 had an
unsigned BX guard followed by a shift by one, and three used a CX-counted
sparse-key search. Their file words supplied **307 distinct CS/address target
hypotheses**. At that stage, 273 required a new native decode root.

For some original contexts, derived analysis still proposed an unbounded or
non-dominating index. Other transfers were refused because snapshot memory
might be modified. These are different conditions. The investigation retained
those refusals rather than asserting that the original tables were immutable.

Proposed follow-up: export candidate-only table records with the guard/search
instructions, bound path, slot bytes, file/version/context identity and native
target validation. A caller should be able to request exploratory decoding
from these hypotheses without creating canonical resolved edges or confirmed
functions. Preserve the distinction between a bounded path, all reachable
incoming states, snapshot contents and runtime immutability.

Acceptance should include a guard with a default branch, a counted sparse
search, multiple incoming paths, modified/aliased table memory, a case already
decoded in another CS context, and a switch case that is not a function entry.

### Diagnose persistent derived-budget exhaustion

A private **14-instruction** function remained data-flow partial at 20,000,
100,000 and **1,000,000 steps**, with no additional indirect edges in the larger
probes. The larger probes ran on separate database copies. A simple authored
A/B control using equivalent PUSH-CS/near-call and far-call spellings converged
in both forms. PUSH-CS alone was therefore **not** reproduced as the cause.

Proposed follow-up: retain a compact convergence diagnostic containing the
revisited block, abstract-state growth/join summary, call-cleanup assumptions
and budget counters. Give the investigator a resume or inspect decision based
on changed facts, rather than requiring blind budget increases. The root cause
of this original context remains unisolated; this note is not a diagnosed
general PUSH-CS defect or a claim that more budget completes the program.

### Expose progress during a long derived transaction

Bounded multi-function passes ran for several minutes while a separate reader
continued to see the previously committed job ledger. The command eventually
returned its receipt; this was not observed as a crash.

Proposed follow-up: expose an operation ID and a lightweight progress surface
with the current function, completed/partial job counts, elapsed time and last
durable commit. Preserve coherent transactions and restart behavior. Progress
must not imply that uncommitted analysis is already part of the saved project.

### Make tool origin easy to confirm

In this environment, plain `python -m fdisbull` selected an older installed
0.8.1 package. Explicit source import paths selected the intended 0.26.1 build.
The investigation checked this before accepting its analysis receipts.

Proposed follow-up: a compact, project-free identity response should include
version and loaded module origin, with installed/source provenance when known.
This is environment-selection friction, not evidence that 0.26.1 analysis ran
inside the older package.

## Reuse boundaries

These proposals support the source-recovery side of UDL and UDC work. They do
not change the original-backed Z provider or qualify a reconstructed full game.
Resource rendering, static instruction decoding, model equivalence and native
execution remain separate evidence. Related executable-format intake limits
are described in [the DOS format findings](DOS_FORMAT_FINDINGS_2026-10-29.md); bounded
scene recovery is covered by [the scene framework](SCENE_FRAMEWORK.md).

No original game bytes, disassembly dump, asset, database, save, executable,
checkpoint or runtime capture is included in this change. No sound was played,
no release was published and no system installation was changed.


## Original-game asset trace follow-up (2026-10-30)

A subsequent private investigation observed the original game and its setup
program through the DOS file service, with an additional actor-loader probe.
It paired file requests with native return registers, distinguishing an open
attempt, successful open, positive returned read count and actor entry. Host
sound output stayed disabled while emulated sound loading remained active.

The principal original-game cohort completed all eight main locations,
purchases/setup, opening and bounded time progression: 37 public provider
actions. It read 66 distinct shipped filenames. The separate default Sound
Blaster Pro setup tests read the sound sample, music test and selected driver;
67 distinct shipped filenames were read across the retained study intervals.
The 13 static candidates were not observed as inputs in those intervals.
This is bounded use evidence, not proof that they are globally unused or that
every sprite in a read file was displayed.

Two earlier observer-qualification cohorts stopped at the scene boundary and
remain partial. The corrected observer then completed the public route.
Native investigation also reached the Sell Park confirmation and quit/save
prompts. A credits-picture read occurred after declining save, but completed
credits display and selected DOS exit remain unverified after an oversized
diagnostic reply. No incomplete intent was replayed in its held provider. Private raw
traces and original assets remain outside Git.

### Distinguish passive observers from control hooks

The current public hook actions in `code_layers.py` change layers, registers or
control flow. Scene waits in `scenes.py` and `debug_wait.py` deliberately stop
when `hook_hits` is nonempty. A private read-only logger initially reused that
control-hook channel. Its actor-loader stop interrupted navigation; merely
composing the elapsed guest-time outcome did not fix the second cohort,
because the guard also checks the hit list.

Those were observer-adapter failures, not evidence of a bank regression.
The corrected private adapter retains raw native stops and logging events in
a separate observer channel, while preserving non-observer control hooks.
It uses the existing native execution and read primitives and changes no guest
code, data or registers.

Proposed follow-up: support an explicit read-only observer kind, with permitted
register/memory/string captures, bounded hits/bytes, scoped identity and
transparent continuation. Keep mutation/control hooks distinct. Acceptance
must show that a scene wait can consume passive observations while stopping on
an unrelated control hook, exception, stale binding or unknown native stop.
An observer must not mint action completion or erase an unresolved boundary.

### Filter file events before repeated host stops

The private adapter needed a raw DOS interrupt-service breakpoint, return
breakpoints and bounded far-string reads because no supported file-use event
stream was available at this boundary. The setup tests incurred **47,212**
interrupt stops for **50 tracked open/read/close requests**. Recorded run calls
took about **137.8 host seconds** for **15.225 observed guest seconds**. Human
inspection time is excluded; there is no uninstrumented performance baseline
or claimed speedup.

Proposed follow-up: native filtered DOS file events or breakpoint predicates
for the relevant function values, with request/return identity, filename,
handle, native success/error and actual read count. Preserve unsupported calls,
process/handle ownership, truncation, vector changes, event loss and caps as
explicit coverage qualifications. A successful open alone must not become
proof of input consumption or rendering.

### Account for time at observer boundaries

In the setup music test, a 4,000 ms guest-time request returned after **5,135 ms**
with dense observer hits. The existing loop checks its time condition on the
running-wait path; the hook-continuation path can postpone that check.

Proposed follow-up: check the guest clock after observer dispatch as well,
document whether the requested interval is a target or a hard bound, and
retain the actual native stop and elapsed time. The private game adapter used
composed stop-on-hook runs and a declared host-time allowance for observer
overhead. This does not establish timing parity with an uninstrumented game.

### Keep diagnostics out of the action-response budget

The investigator-only terminal adapter included detailed run/observer evidence
in its reply. The existing Z response budget correctly replaced an oversized
reply with an incomplete response after the final quit-related input. The
client held rather than repeating the input; final selected-program exit was
not certified. This is not an observed game crash.

Implemented follow-up: `ZService.send` retains the full original JSON in the
existing private output-artifact store and atomically records its delivery hold
before sending a compact reference. `reply_status`, `read_reply` and
`select_reply` retrieve the pending result without a native RPC.
`accept_reply` verifies the artifact and unchanged worker/provider/native-session
witness using read-only native status; it clears only the delivery hold.
Ordinary observation, actions and checkpoints remain withheld while delivery is
pending. A lost reference can be recovered in the surviving worker, and storage,
corruption or stale-witness failures cannot authorize an action replay.

The [protocol and limits](Z_REPLY_RECOVERY.md) keep delivery completeness,
producer interval completion and selected DOS termination separate. A confirmed
quit still needs native exit evidence. Reading or acknowledging a receipt never
advances credits; any input-free continuation must be requested separately.
No original action is reconstructed from its request, and host cleanup cannot
certify game termination.

The [30 October verification record](VERIFICATION-DINOPARK-Z-REPLY-RECOVERY-2026-10-30.md)
keeps independent native cohorts, strict readback witnesses, controller limitations
and selected-program exit evidence separate.

### Named terminal scenes and remaining menu coverage

The follow-up implements [named Z terminal actions](DINOPARK_Z_TERMINAL_ACTIONS.md)
for the office menu, resume, park quit, cancellation, confirmation, explicit
save decline, title-menu Exit to DOS and bounded input-free continuation.
These use the ordinary public observe/act protocol and qualify original
frames or native selected-process termination. Unknown transitions retain
recovery holds and never replay their triggering input.

The earlier investigator-only cohort remains historical evidence. Sell Park,
About, starting/loading through title-menu controls and the affirmative
save-first path still need separate qualified mappings. Visible prompts,
native input, committed effects and selected DOS exit retain independent
postconditions; the additional actions do not certify a complete playthrough.

The [named-action native batch](VERIFICATION-DINOPARK-Z-NAMED-TERMINAL-2026-10-30.md)
passed through the public Player in one guest. It also records the existing
pre-entry operating-report refusal and unsupported modal checkpoint creation
as concrete follow-ups, without upgrading either to unknown game effects.

### Resumed unused-content investigation

The [subsequent producer and runtime study](VERIFICATION-DINOPARK-UNUSED-CONTENT-2026-10-30.md)
accounts for filename sources for 54 of 57 ACT files, distinguishes a selective
sprite reader from full actor loading, and retains BUS/OFFICE/PEOPLE as open
producer gaps. A muted original-game route completed setup and 24 time advances.
The candidate visitor-message binding remains unqualified, and an optional
quit extension exposed a private controller assumption about accepted modal
results. The record preserves that limitation separately from native gameplay
and cleanup, along with concrete resource-telemetry follow-ups.
