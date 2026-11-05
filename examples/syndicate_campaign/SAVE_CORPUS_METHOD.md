# Save-assisted recovery: reusable entry states, not fabricated progression

A saved campaign can expose a system sooner than a new-game walkthrough. Use
compatible existing saves early, in parallel with source and guide reconnaissance.
The goal is a qualified entry state for the next behavior, not an assertion that
the investigator personally played every prerequisite.

## Plan a small state corpus

Choose saves by the behavior they can distinguish. For campaign research, useful
strata include a new game, a selected but unfunded project, an active partial
project, a nearly completed project, a completed tier with a locked successor,
a newly recovered item, and insufficient funds or missing prerequisites. A
mid-battle save answers different questions from a strategic/base save. Do not
collect arbitrary late saves and assume they cover every branch.

Use a coverage ledger: required behavior, candidate seed, necessary dependencies,
known intervention history, successful original-load receipt, next probe and
remaining unknowns. Prefer the smallest donor set that opens genuinely different
systems. Preserve negative examples, not just successful files.

## Search and admission

Record the candidate's creator/site, URL and retrieval date, declared title,
platform, executable/patch, language, expansion, mod/ruleset and progress claims.
A similarly named sequel, remake or console/Amiga save is not a compatible DOS
input. A source-port save may be a semantic reference without being loadable by
the original. Save editors and trainers are separate executable tools, not data
that should be run merely because they were inside a download.

Inspect archive paths, member counts, declared/uncompressed sizes, duplicate and
case-colliding names, links and unexpected executables before extraction. Use
explicit expected-file profiles and bounded parsing. Hash every accepted original
and keep it read-only. Run the original in an isolated writable copy; never
replace the user's only save or silently bind a different executable version.

`tools/save_seed.py` implements conservative ZIP inventory and evidence-gate
summaries. A candidate remains unqualified after hashing or parsing. Its receipt
checker is not an authentication or security oracle.

## Validate the entry state as a dependency group

Check structural bounds first, then load through the exact original loader.
Observe the selected subsystem, not merely a main menu. Verify references across
campaign, agents, inventory, unlocks, calendar, active tasks and resource files.
Distinguish serialized fields from runtime defaults, UI selection, caches and
regenerated tables. Do not copy an unlock flag without its prerequisites and then
call the result a normal progressed save.

Advance one original logical update or perform one bounded relevant interaction.
Verify its effects and invariants. Save through the original, check the actual
file, reload, and compare the selected state. A fresh-process load is stronger
persistence evidence than restoring RAM in the same debugger session. It is still
not proof of arbitrary-edition portability or ordinary reachability of the donor.

The original save operation itself may mutate the world. In this Syndicate
study, the writer charges high-balance saves before opening the file; another
program might advance a clock, rotate an RNG, migrate a schema or normalize
references. Retain pre-save, writer-result and post-load observations separately.
A returning menu does not prove output exists. A native checkpoint does not
necessarily restore mounted files or external I/O.

## Preserve origin and evidence categories

Use explicit categories, without treating them as automatic proof levels:

- An external compatible donor is someone else's recorded progress. Its cheating,
  editing and progression history may be unknown.
- A locally generated original save is produced by the original program. Record
  assisted menu input, fast-forwarding and any diagnostic state preparation.
- An emulator checkpoint belongs to a backend/context and is not a portable
  ordinary game save merely because it restored successfully once.
- A synthesized state or edited donor is a diagnostic fixture. Keep the exact
  edit set and the untouched baseline. Successful continuation does not erase
  the intervention or establish that ordinary play can reach the state.

When no suitable donor is obtained, state that plainly. Build the smallest
original-generated seed that opens the current system, or use a clearly labeled
diagnostic preparation. Keep the unserved late-game coverage obligations open.
Do not repeatedly restart a full campaign when the same validated seed suffices.

## Reconstruct behavior, not just a frozen screen

Recover persistent data, input producer, update routine, completion predicate,
UI projection and serialization independently. A screenshot can identify a tab;
it cannot establish charge timing or hidden unlock dependencies. Compare original
execution with the recovered model on ordinary and boundary cases, then test the
model's renderer separately. Keep input assistance distinct from effect patches.

Syndicate provides four useful counterexamples: geographic neighbors are not the
mission-admission graph; an active research graph can be newer than its stored
project counter; threshold completion and inventory availability can be separate
operations; saving can change cash even before the write succeeds.

Use existing source/format research as an attributed hypothesis source. An
external converter that repairs, remaps, randomizes or normalizes state is not an
original behavior oracle. Preserve differences rather than importing its repairs
as recovered semantics.

## Application to X-COM and other programs

OpenXcom's original-save converter distinguishes a `GAME_#` folder, `SAVEINFO.DAT`,
base data, research discoveries, per-base projects and manufacturing. Its project
import accounts for assigned scientists. That is a useful dependency checklist,
not a substitute for loading the chosen original edition. Source reviewed:
<https://raw.githubusercontent.com/OpenXcom/OpenXcom/master/src/Savegame/SaveConverter.cpp>.

For a proposed X-COM investigation, retain the complete donor directory and its
edition/ruleset identity. Select strategic and tactical fixtures separately.
Probe the next meaningful research boundary: allocation, an original time step,
completion, new availability and persistence. Include facilities, personnel,
items and base ownership in the dependency inventory. A later alien encounter,
manufacturing queue or transfer can require a different seed. These are proposed
experiments; no X-COM target ran in this study.

The pattern also applies to a simulator scenario, CAD project, editor document,
spreadsheet model or business application's saved workspace. Find compatible
examples that expose a later workflow; preserve linked resources and versioned
schemas; validate load, one meaningful operation and save/reopen. Do not execute
embedded macros/scripts or external links merely to gain a convenient fixture.
Document migrations and caches instead of treating them as author intent.

## Tool and skill acceptance requirements

| ID | Required behavior |
| --- | --- |
| SC01 | Search compatible saved states early and retain candidate/rejection reasons by edition and platform. |
| SC02 | Treat related files and referenced state as a dependency group; validate paths, budgets and original hashes before original loading. |
| SC03 | Keep external donor, native-generated save, native checkpoint and edited diagnostic seed provenance distinct. |
| SC04 | Separate parse success, original-load success, subsystem readiness, original progress and save/reload qualification. |
| SC05 | Observe save-side effects, configured output paths and actual written files; do not replay uncertain save actions blindly. |
| SC06 | Preserve persistent, active, cached and presentation state separately; a field copied from another layer is not an equivalent model. |
| SC07 | Bind comparisons to the same original source and admitted state; preserve unsupported fields and external-converter differences. |
| SC08 | Bound batches and flush receipts incrementally. Client cancellation is not a game hang or a complete successful run. |

The local PR adds this procedure to the existing `recovery-research` skill
reference, without adding a new unregistered tool command or claiming the live
installed skill has already changed.
