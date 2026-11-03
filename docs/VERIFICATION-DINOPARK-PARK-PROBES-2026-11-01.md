# DinoPark park preparation, standing probes and compiler retention

This follows the fence/observer study delivered at `b438f5e`. The starting
research inventory is 47/201 observed entry PCs, 97 open caller/producer cases,
13 open asset candidates, 361 caller snapshots, 937 filename snapshots and
15,976 original-matching read prefixes. Runtime qualification is separate from
the static compiler/linker findings below. Sound remains off; no packaging,
installation, release or merge is part of this work.

## Compiler and linker evidence

The original executable SHA-256 remains
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
At file offset `0x34a04`, load-image offset `0x30204` (static `4020:0004`), it
contains `Borland C++ - Copyright 1991 Borland Intl.`. This establishes the
presence of a Borland C++ runtime. It is consistent with a Borland toolchain;
it does not identify the exact compiler/linker release, switches, or compiler
used for every linked C, C++ and assembly module. The reserved MZ-header bytes
are retained privately without assigning an unverified version to them.

**Unreferenced functions can survive such a build.** Borland's contemporary
documentation describes separately compiled object modules and a librarian:
TLINK selects the needed modules from a library. An object containing a needed
routine can also contain other emitted routines. Explicitly linking that object
is another way to retain its contents. This is a credible explanation for some
no-known-reference library candidates. It is not a proof of the original
module boundaries or of any particular candidate's unreachability.
[Borland C++ 3.1 Tools and Utilities Guide, printed page 46](https://archive.org/details/bitsavers_borlandborn3.1ToolsandUtilities1992_10268604)
describes this module-selection boundary; printed page 197 describes TLINK's
recursive module marking. A locally retained OCR copy is hash-bound to the
source record. No period compiler/linker build experiment was performed.

For example, a hypothetical `helpers.obj` might contain `needed()` and
`spare()`. Calling `needed()` can select that module while leaving `spare()`
emitted and uncalled. This is an illustration, not reconstructed DinoPark
source. Compiler optimizations inside functions and special inline/virtual-table
deduplication do not establish whole-program removal of every unused function.
Borland's documented Smart virtual-table option specifically concerns duplicate
tables and out-of-line inline functions, rather than such a universal guarantee.
[Borland C++ 2.0 User's Guide, printed pages 67 and 227](https://manualzz.com/doc/43316675/borland-2.0-c---compiler-user-s-guide).

The user's VC6 recollection concerns the same distinction between linking
objects and packaging functions separately. Microsoft's documented `/Gy`
mechanism emits individual functions as COMDATs so the linker can exclude them;
`/OPT` controls exclusion. This is a comparison to the documented mechanism,
not a verification of VC6's historical defaults or DinoPark's settings.
[/Gy documentation](https://learn.microsoft.com/en-us/cpp/build/reference/gy-enable-function-level-linking?view=msvc-170).

No stored direct reference is a weaker claim than no possible caller.
Indirect calls, runtime-filled pointer slots, interrupts, callbacks, aliases,
interior entry points and incomplete decoding remain alternatives. DinoPark's
earlier observed PC arrivals already demonstrate that distinction. None of the
97 cases is reclassified as dead solely because module retention is possible.

## Standing first-hit probes

The requested fallback is a standing, guarded execution probe, retained across
ordinary play until its first hit. First-hit evidence should include the exact
source/runtime address, relocated byte guard, registers, caller stack, relevant
arguments and slots, source version, runtime epoch and observation interval.
The first hit can then be followed with a targeted caller investigation.

The existing private collector creates entry breakpoints with `once=False`,
keeps unhit probes, persists the first-hit record and explicitly deletes only
the breakpoint that hit. A no-hit result is scoped to the captured interval;
it is not global unusedness. Saved manifests are rearm recipes, not restored
live debugger ownership. A new run/restore/version requires fresh byte and
address guards and a fresh installed-inventory check.

The old live controller does not expose its backend's `breakpoints.list`.
Its historical installation receipt and host-side map are retained separately
from current live inventory, which cannot be claimed from that map alone.

## Storage and continuation boundary

The old F3 provider is alive at a qualified Employment scene. Its collector
holds the internal trace on an open descriptor and exposes no redirect,
rotation, reopen or generic native-call bridge. Retargeting a path cannot
retarget that already-open descriptor. Its checkpoint fixture also provides no
supported export/import route for this state into another provider. These are
private harness capability limits, rather than a game rejection.

The next capture therefore uses a fresh, storage-admitted external validation
case. Its prepared state is recreated through original game actions. The old
provider, every held intent and all earlier sealed evidence remain in place.
This does not transfer the old machine's RNG/day phase or certify cross-provider
checkpoint equivalence. New bulk inputs, traces, databases and temporary
outputs belong to the external workspace; active old data is not moved.

## Resource-use scope

The latest fence cohorts omitted Guide/Food/OpenPark/visitor execution. An
earlier October 30 cohort already documented those interactions and 24 time
advances, with positive income/food observations and no successful opens/reads
of these thirteen candidates. The new route extends instrumentation and
standing-probe evidence; it is not the first observed operating-park run.

`BUS.ACT` and `PEOPLE.ACT` use older `UNCS` containers, while the other 55 ACT
files use `UNC2`. The earlier reader investigation recovered an `UNC` prefix
dispatch, so their older magic is not by itself an incompatibility explanation.
Full actor loading, the separate selective sprite reader, DOS open/read results,
sequence execution and displayed pixels remain separate evidence boundaries.
An exact filename negative also does not exclude an alias or embedded payload.

The requested native batch is hiring a guide, committing a food order, entering
the park and bounded time advances with financial, food and dinosaur readback.
Park-view/day progression alone does not certify an unqualified open/closed
boolean, nor prove a particular visitor/arrival branch. Native outcomes and the
final per-target coverage overlay are recorded below after qualification.

## Failed legacy Guide attempt and bounded correction

The first external case used the unchanged b7bc runtime. Its Guide action
queued five original clicks once, ending at the roster confirmation. Before
that input, guides were 0 and the pending guide count was 1. The final step
requested 7,000 guest milliseconds with a 15,000-millisecond host allowance.
The action returned incomplete after 39.613 seconds. The close record reports
shared debugger host-budget expiry before RPC dispatch, followed by interrupted
cleanup and native exit -9. The final closed-channel error can mask an earlier
RPC error; the first failing RPC is not established. This is not proof of a
standalone game crash or a rollback. The hire remains unknown and was not retried.

The correction is frozen at `51fadb52151d226d898402f7cb143bc0cbd5d9dd`.
Guide/Food/OpenPark now share a 40-second operation deadline, including Z's
initial observation. Long settling sleeps become 250-millisecond execution
slices followed by their existing bounded readiness checks. The food quantity
increments, native expense/stock commit boundaries and original click order
are preserved; generic shop clicking is unchanged. The guide's native roster
is checked and its accepted confirmation ticket retained before the first
committed-frame acquisition, separately from Street presentation.

Five new host regressions cover delayed readiness, exactly five Guide inputs,
wrong roster rejection, both first-frame and later-witness failures, and nested
deadline restoration. Independent review identified the first-frame boundary;
that finding was corrected and re-reviewed with no material findings remaining.
The final full suite returned 2,220 passed, 133 skipped, 12 failed and 23 errors.
The same 35 baseline failure/error IDs remain, with none added or removed.

## Assisted original-game qualification of the corrected runtime

The new CACHE case recreates the qualified setup in a distinct park. The
previous F3 provider and the unknown failed case are separate identities. All
requested actions below completed through the public Z interface:

| Action | Original-backed result | Instrumented host time |
| --- | --- | ---: |
| Hire guide | One guide committed; cash/working cash $2,250, loan $5,000; monthly wage listing $900 | 14.738 s |
| Buy food | One confirmation; 20 small feeders, $500 expense; cash/working cash $1,750; stock at commit and return 20 | 17.751 s |
| Enter park | Park view and advancing day observed; day 1, cash $1,939 | 9.831 s |
| Advance 1 | Day 2, cash $2,128 | 1.842 s |
| Advance 2 | Day 3, cash $2,222 | 1.921 s |
| Advance 3 | Day 4, cash $2,411 | 2.023 s |

The final native report retains one guide, 20 small feeders, one Coelophysis in
pen 10, hunger 0 and loan $5,000. Food stock did not decrease in this short
interval; no new feeding-consumption claim is made from it. Financial/calendar
progress supports a running simulation. A separate original open/closed boolean
remains unqualified. These are instrumented timings, not baseline player speed.

## Standing-probe and asset results

Read-only native inventories before and after the corrected batch verify all
97 unresolved entry breakpoints present at the exact guarded runtime addresses,
enabled, execution kind and `once=False`. No unresolved entry hit. Both queries
preserved native identity with zero execution/input/restore counter deltas.
All 97 therefore remain armed in the retained live corrected guest, rather than
being treated as unused after this bounded run.

A first attempt at the new inventory query returned a 134 KB raw payload but
failed the private controller's expected envelope. Its complete native result
was independently recovered offline; no gameplay was repeated. The corrected
harness keeps the full inventory as an artifact and presents a compact typed
reply. This is private verification glue, not a newly released public method.

Independent reconciliation of the failed and corrected new streams with the
prior exact-PC ledger retains the 47/201 union. The failed stream reaches 14
candidate entry PCs and the corrected stream 21, all previously observed.
Neither stream's captured filename fields name `BUS.ACT` or `PEOPLE.ACT`.
Exact successful open/read evidence, positive controls, per-target ledger
updates and final capture bounds are retained with the private delivery.

## Storage and integration gates

A 512 MiB CODEX allocation was rejected, as was a later bounded 256 MiB
allocation; the latter saw about 40.106 GB free and would cross the default
40 GB destination target. CACHE also rejected the default 40 GB target. No new
bulk work proceeded under those rejected admissions. The user then explicitly
authorized this bounded DinoPark native test on CACHE with a 20 GB reserve.
Its 512 MiB admission passed with about 32.920 GB free in that pool. Pools were
assessed separately; the exception does not change other jobs' reserve policy.

New test/runtime/capture data use CACHE under that approval. Active old folders
remain in place. Original files, emulator databases, snapshots and raw logs stay
outside Git. Local PR #41 and GitLab !18 receive source changes and sanitized
findings. Release, installation and merge gates remain separate; no package is
produced.

## Final research accounting and retained live context

The finalized overlay includes both the failed b7bc case and the corrected F4
case, preserving the failed Guide's partial interval and unknown outcome.
Cumulative counts are 396 caller snapshots, 1,021 filename-argument snapshots
(952 encoded-far and 69 PUSH-CS/near-CALL origins), 17,251 original-matching
read prefixes and 24 capture/run receipts. Relative to the prior fence delivery,
this adds 35 caller snapshots, 84 filename snapshots and 1,275 matching prefixes.
There are zero recorded correlation/read-prefix mismatches and zero unclassified
filename origins within the retained attribution scope.

The exact-PC union remains 47/201. All 97 unresolved entries and all 13 asset
candidates remain open. `BUS.ACT` and `PEOPLE.ACT` each have zero exact argument
events, successful opens, read events and returned read bytes in the new bounded
park trace. Positive controls cover real employee/park/resource activity; they
are not evidence that every possible bus/passenger, alternate producer,
configuration or startup branch was exercised. Actual bus/passenger arrival is
unqualified. The earlier longer cohort's evidence remains separate.

The corrected native guest is retained at Park after day 4, with no hold or
active request. Its 97 unhit probes remain installed for subsequent normal
runs. The actual endpoint inventory and source/runtime identities are retained;
no independent watcher or automatic time advancement was started. Earlier live
owners remain untouched, and the failed Guide case was not replayed or restored.
