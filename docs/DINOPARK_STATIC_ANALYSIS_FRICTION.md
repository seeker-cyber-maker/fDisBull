# Whole-binary discovery friction: DinoPark static study

This records observed analysis limits and proposed follow-ups from a private
DinoPark MZ investigation on 2026-10-30. It changes documentation only. It does
not implement the proposals or certify that any original routine or resource
is unused.

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
