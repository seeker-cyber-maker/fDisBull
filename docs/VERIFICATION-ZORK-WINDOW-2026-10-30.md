# Zork window intent recovery and method follow-up, 2026-10-30

## Outcome and current verification status

The scene-recovery method now has an executable follow-up: OPEN and CLOSE on
the kitchen window, including requests that repeat its current state. The new
UIL describes the requested door state, dismissal of an initial examination
hint, and selection of repeat feedback. Separate UDL definitions connect those
intent primitives to the original operations and the preserved source state.

This closes a bounded semantic obligation left open by the earlier scene work.
The window's identity, callback link and door exits were already resolved. This
pass begins from those definitions and recovers the callback's OPEN/CLOSE
effects. It does not rediscover the surrounding dispatcher or claim that every
branch of the window callback has been recovered.

The final frozen gameplay run passed **13 cases, 492 commands and 505
boundaries**, comparing higher-level execution with preserved IR and a fresh
Frotz reference. All eight tracked consumer source files remained unchanged.
The complete 396-command winning route finished with **350 points and 394
moves**. The window interaction passed **27 commands at 28 boundaries**, with
**2,880 ordered effects** and complete machine snapshots agreeing. All **39
replaced source instructions** were forbidden in that interaction case, so
success did not come from executing its original body as fallback.

Two fresh-process checkpoint continuations also agreed, for **296 commands**
from the winning route and **19 commands** from the window case. The qualified
whole-repository pytest run passed 2,590 tests and recorded ten failures from
missing optional managed-code dependencies. After installing those declared
dependencies, both affected files passed all fifteen tests, including every
prior failure. These are separate runs; a single all-green full rerun is not
claimed. Upstream v0.26.1 is integrated and passed 186 focused integration
checks. Both rebuilt wheels passed their distribution and installed-package
gates, including independent validation of the actual version-2 scene package.

The companion [machine-readable receipt](evidence/zork-window-2026-10-30/verification.json)
contains sanitized identities, counts, checks and limitations. Original story
bytes, narrative, memory states and detailed gameplay transcripts remain private.

## Baseline and preservation

This work incorporates upstream commit
`f783f2aa43bae779392fd3f6558c980c5e4884b5`, whose tree is
`0509cb545248eaffca566fda9e2c54ebfbdfa1f0`. The local integration commit is
`3098bb656952e74745432cd70a01550ecdf27193`, with tree
`5113b19d22025623117b2d3ae58587d54d6fb976`. Core and player metadata are
**0.26.1**. This records an integrated development state; it does not declare
a published release or installation.

The feature was initially developed on upstream
`f159252761150ca2dd95eb12e16e515ce33f74fd`, tree
`7183a0f3674e73f9189db05583ce5e4be8bee6ff`, locally integrated as
`04fffaae1d43c01b82671f92ed37417221c0dc7f`. The later upstream update changed
23 paths, covering guide/release work and version metadata. It preserved all
eight frozen Zork consumer sources and the feature's uncommitted changes.
Fresh integration checks passed **186 tests**. Distribution version, integration
identity and tested execution-source identity are tracked separately.

The supplied source is the same qualified Zork I R88, serial 840726 image used
by the earlier conversion. Its full-file SHA-256 is
`0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd`.

The older package components retain their canonical identities:

| Preserved component | Canonical SHA-256 |
| --- | --- |
| Base intent package, including complete executable IR | `d4e1f586a39b6fe59987c4b2e25bd17d9e0a009c3bb5208b0a8d4f5122f11d01` |
| Scene UIL | `dab825eac678c6b1fdc51414d6771799cdf147afa2d3031babd44140585a6e05` |
| Dispatch UIL | `e617f6df0ab4d35eb27405799d3c2ed782109a1f58d5e691df44a37244da2fc0` |

A fresh comparison against the local integration commit also found all
**13 selected original converter, processor, IR/runtime, evaluator and test
files byte-identical**. Their individual paths and hashes are in the receipt.
This preservation check has a declared inventory; it is not a claim that every
file in the repository is unchanged.

The scene inventory remains **110 rooms and 352 exit definitions**. Those
definitions already include the window-controlled exits in both directions.
The new interaction changes their existing live door predicate rather than
introducing a second movement system or a separate door state.

The full supported exporter produced the same canonical package as adding the
interaction to the reused, qualified scene and dispatch definitions. This is a
consistency check between two construction paths, not independent evidence that
the recovered intent is correct. Independent source-operation validation and
execution comparisons provide the separate evidence for that claim.

## Start from the missing scene requirements

The earlier [methodology pass](VERIFICATION-SCENE-METHODOLOGY-2026-10-30.md)
directed further work to the next named residual handler. Applying it here
produced this bounded requirement/evidence ledger:

| Required element | Direct evidence used | Accepted result |
| --- | --- | --- |
| Target and entry | Existing door/object correspondence and action-property dispatch definition | One named window and one resolved callback; no new address search. |
| Requested operation | Callback action comparison and known action identities | OPEN and CLOSE have distinct semantic inputs. |
| Live condition | Common helper's open-attribute tests | Success versus repeat depends on the current door state. |
| State change | Hint-state assignment plus its reader; open-attribute set/clear | An operation-history fact and the shared live door predicate. |
| Success output | Typed text references supplied to the helper | Opening and closing resources with complete abbreviation dependencies. |
| Repeat behavior | Shared response-table reference and the complete small selection helper | One RNG draw, ordered bag updates, selected narration and newline. |
| Return and continuation | Source returns and existing callback calling convention | Handled result returns through the original caller destination. |
| Turns and events | Preserved turn-count binding, residual scheduler and command-boundary checks | Existing turn effects remain integrated; no extra local turn increment. |
| Failure and persistence | Ordered-effect comparison, injected failures, full snapshots and fresh resume | Preserve completed prefixes; retain original shared state and continuation. |

The replacement comprises **39 instructions across three source routines**:
four callback-prefix instructions, eighteen common OPEN/CLOSE instructions and
seventeen shuffle-bag instructions. Three additional instructions from the
unrecovered examination path qualify the history field's meaning. The bounded
instruction budget is therefore **42**, with **39 executable replacements**.
The three replaced source regions occupy **157 bytes**. The five emitted text
resources have **25 deduplicated text/abbreviation witnesses**, totaling
**164 bytes**; the examination evidence has additional dependencies.

The implementation follows routine references by their roles, including routine
headers and default locals. No routine PC is needed as a lookup key for finding
the next helper. Unsupported operation shapes, branch polarity, null references,
truncated records or ambiguous existing associations are refused explicitly.

## Recovered intent and the effects that were easy to miss

The domain evaluator is in [door_intents.py](../player/fdisbull_player/door_intents.py).
It receives named entities, resources, live state and a declared random choice;
it does not read source memory or interpret Z-machine instructions. The producer
is [zork_window.py](../src/fdisbull/zork_window.py). The independent consumer
checks source correspondence in [door_bindings.py](../player/fdisbull_player/door_bindings.py),
and the existing [scene runtime](../player/fdisbull_player/scene_runtime.py)
realizes the admitted effects.

The UDL names these primitives and their original operation witnesses:

| Primitive | Recovered meaning |
| --- | --- |
| `presentation.dismiss_initial_hint` | Record that an OPEN/CLOSE request has superseded the initial examination hint. |
| `door.open` | Change the existing door-open predicate to true. |
| `door.close` | Change that same predicate to false. |
| `narration.emit` | Emit the selected qualified resource or newline in its source order. |
| `narration.choose_shuffled_response` | Choose repeat feedback from a shared bag, update it without replacement within a cycle, and emit the selected resource. |

### The history fact is different from the open state

Every admitted OPEN/CLOSE request assigns the history fact, including CLOSE on
an already closed window. The assignment occurs before narration or a random
draw. Its consumer suppresses a special initial examination description once
the fact is nonzero. The examination branch itself remains residual execution.

Naming this fact from its writer alone would have been insufficient. Its reader
establishes why the state exists, while the separate open attribute establishes
whether traversal is permitted. The producer retains both the consumer's
instructions and its transitive text dependencies as guarded evidence.

### Output precedes the door-state change

The four admitted paths preserve this order:

| Request and current state | Ordered effects after recording history |
| --- | --- |
| OPEN while closed | Opening resource, open-state change, newline. |
| CLOSE while open | Closing resource, closed-state change, newline. |
| OPEN while open | Response selection and bag updates, selected response, newline. |
| CLOSE while closed | Response selection and bag updates, selected response, newline. |

Changing the door before emitting its success resource would produce the same
ordinary final state, but it would disagree with physical-effect ordering and
with a failure during output. The runtime therefore preserves the source order.

### A repeat request consumes randomness and mutates shared state

The selected response helper is a small shuffle bag. It keeps a permutation of
three resource identities and a cursor identifying the first unused position.
It draws once from the remaining suffix, exchanges the selected item with the
cursor item, advances the cursor and wraps after the last item. The source
performs both writes even when they refer to the same slot. A remaining suffix
of length one still consumes an RNG draw.

The promise is **without replacement within one cycle**. Consecutive cycles may
repeat the same response at their boundary. Tests reject a definition that
overstates this as an unlimited no-repeat guarantee.

The bag is shared with residual handlers. Its current ordering and cursor are
read live and written back to the same source-bound state, so residual use can
change the next semantic response. An independent private bag would break that
interaction and checkpoint continuity.

### Typed references prevent a misleading numerical coincidence

A selected text reference happens to have the same numerical value as an
instruction address. Its text-reference role requires packed-text resolution,
not instruction decoding at that integer. The authored fixture reproduces this
kind of collision with unrelated test content, and a relocation test moves all
source locations while preserving the resulting intent document.

## Package and compatibility boundaries

New exports use `fdisbull-zork-scene-package-2` with
`fdisbull-zork-scene-udl-2`. The added `interaction_uil` document has its own
`fdisbull-door-interaction-uil-1` format; its source definition uses
`fdisbull-zork-door-udl-1`. The existing scene and dispatch UIL formats and their
contents remain unchanged. The new package carries the complete preserved base
intent/IR package and explicit residual behavior.

The updated consumer still accepts version-1 scene packages. A version-2 export
needs the updated consumer; retaining the Python distribution's current version
string is not evidence that an older installed player supports the new format.
The package binds the interaction document by canonical digest and validates
its source correspondence before execution.

Admission checks run before the first effect. Changed code, layout, text,
callback identity or unsupported output-stream behavior selects an explicit
residual path. Live open state, history, cursor and bag ordering are not frozen
by byte-equality guards. The repeat path validates its live bag domain; a state
change does not need to inspect an unused bag permutation.

Once an effect has started, the runtime never replays the old callback to repair
a failure. It records the confirmed effect prefix and interrupted uncertainty.
The tests exercise failures in history recording, narration, door mutation,
randomness and bag writes, as well as actual output and random-tape failures.
Existing frame and stack budget refusals are also retained when source helper
frames are eliminated.

## Verification evidence and limits

### Authored and adversarial tests

The new test families contain **332 cases**:

| Test family | Cases | Main evidence |
| --- | ---: | --- |
| [Pure evaluator](../tests/test_door_intents.py) | 106 | All four paths, complete bag choices, cycle boundaries, strict input domains and document-supplied names/resources. |
| [Deterministic producer](../tests/test_zork_window.py) | 28 | Relocation, typed references, ambiguity, source/IR correspondence, dependencies and malformed inputs. |
| [Independent bindings](../tests/test_door_bindings.py) | 76 | Changed semantics with recomputed hashes, effect/branch/return checks, typed source literals and omitted guards. |
| [Runtime differential checks](../tests/test_zork_door_runtime.py) | 122 | Full source-state/effect equality, all bag permutations/draws, shared residual use, return destinations, budgets and fault prefixes. |

A broader affected-module integration check passed **520 tests**. These focused
results do not substitute for the whole repository result below.

Independent checking found a concrete Python equality problem: Boolean and
numeric literals can compare equal even though they are different machine-value
contracts. The validator now compares source representations with their types
preserved and requires typed integer fields. New negatives cover Boolean and
floating-point aliases, routine defaults and primitive source addresses. The
full gameplay source-freeze check correctly prevented the earlier running pass
from being presented as final after this correction.

### Frozen real-game interaction and fresh continuation

The final 27-command interaction check exercised both sides of the window,
state changes, repeat requests, examination before/after hint dismissal, closed
traversal refusal and open traversal. All 28 input boundaries matched preserved
IR results, complete snapshots, ordered memory/output/random effects, and fresh
Frotz narrative/score/move observations.

The semantic runtime recorded fifteen hint assignments, four opens, three
closes, eight shuffled-response selections and twenty-seven existing turn-count
primitive executions. Four other callback actions remained residual. The run
ended with 27 moves; it compared 2,880 effects on each side and trapped every one
of the 39 replaced source instructions.

Checkpoints resumed in fresh isolated Python processes for 19 commands from
that case and 296 commands from the winning route. Each process used the
declared consumer modules, package and checkpoint. Results and complete final
snapshots agreed; no source-producer modules were loaded. This validates the
selected continuations, shared response state and RNG state, not arbitrary
checkpoints or every original persistence operation.

### Whole repository and frozen gameplay gates

The first full local pytest invocation completed with **2,540 passed, 60 failed,
121 skipped**, return code 1. Its failures were classified as follows:

| Failure group | Count | Disposition |
| --- | ---: | --- |
| Git-ancestor output guards | 32 | Passed with a qualified temporary directory outside Git; the guards were retained. |
| Optional managed-code dependencies | 10 | Failed in the qualified full run; all passed in the subsequent focused run after installing the declared dependencies. |
| Socket policy | 10 | Passed under qualified execution after the initial restricted socket setup failed. |
| Subprocess import setup | 2 | Passed with the declared source/player import paths. |
| New-module fixture inventories | 6 | Passed after updating two distribution test fixtures to include the newly required modules. |

The qualified full rerun completed with **2,590 passed, 10 failed, 121 skipped**,
return code 1. Its failures were in unchanged managed-code decoder tests
requiring the optional `dnfile` and `dncil` packages. After an initial restricted
installation attempt failed, the declared dependencies were installed into the
task environment: `dnfile==0.18.0`, `dncil==1.0.2` and `pefile==2024.8.26`.
A focused rerun of `test_managed.py` and `test_managed_api.py` then passed
**15 tests**, including all ten earlier failures. No production code was changed
for that diagnosis. The receipt retains the per-case classification and both
run outcomes; it does not combine them into an invented all-green full rerun.
The 121 skips keep their original backend/platform scope. This whole-repository
run predates the later v0.26.1 integration, which has its own 186 focused passes;
it does not establish a full exact-commit CI result for the final publication.

An earlier broad gameplay run reached the winning-route result, but a validator
correction changed a tracked file during that run and invalidated its final
source-freeze gate. The replacement run completed with **all comparisons equal
and all tracked source files unchanged**. Its private verification receipt has
SHA-256 `1cd1a8c05ccb204e2bfcd3b1f166f6fc38d640f0354457e06ebb619a6bc50728`;
the public receipt carries sanitized case summaries and the eight consumer file
hashes. The 13 cases cover 492 commands and 505 boundaries, including the full
396-command route, parser alternatives, mailbox/pronoun behavior and the new
window interaction. Complete snapshots and ordered effects matched the retained
IR; fresh Frotz checks agreed on narrative, score and moves under the declared
reference normalization.

The same final run also compared UIL execution against an existing native
reference receipt: **34 boundaries and seven RNG events** matched, including
the recorded game-memory checks with the declared interpreter-header exclusion.
This reuses historical native observations; it is not a new DOS/native execution
or a fresh native reference for every newly recovered window path.

### Installed delivery gates

The final **0.26.1** core and standalone player wheels passed their distribution
checks with **172 and 19 entries**, respectively. A new isolated environment
installed both wheels with `--no-index --no-deps`, then successfully imported the
new producer, evaluator, independent binding module and scene runtime. Installed
core correspondence verification and independent player validation both
accepted the actual version-2 production scene package, preserving its old
component identities and admitting the 39-instruction window interaction.

Both packaged skills passed their installed-package gates: the investigation
skill has **11 resources and 36 local links**, and the integrated guide-writing
skill has **8 resources and 13 local links**. All six installed checks passed.
The public receipt records the wheel identities, exact installed skill file
hashes and package validation result. Earlier 0.26.0 wheel checks are retained
as historical evidence, separate from these final 0.26.1 results.

This report and its receipt are fixed after those local gates. Source archives
are assembled afterward; their verification and any exact-commit CI results
belong to subsequent publication evidence. This avoids an archive that embeds
an obsolete report or a recursive archive-hash claim. This report does not
assert that the changes, an archive or a release have been published.

## Measured cost of the bounded follow-up

Five warm component runs produced identical canonical interaction artifacts.
Definitions, retained IR and the independent source reader were already loaded.
Median times were:

| Stage | Median |
| --- | ---: |
| Interaction recovery | 4.86 ms |
| Producer correspondence verification | 2.19 ms |
| Independent source/intent validation | 4.33 ms |

The complete measurements and canonical output identity are in the public
receipt. The runs experienced allocation/concurrency variation. They exclude
cold scene discovery, loading, whole-package construction and gameplay; there
is no old-method comparison arm and no speedup claim. The useful methodological
result is a closed obligation with a small, explicit source dependency budget.

## Method changes supported by this case

The new implementation gives a concrete application of the
[scene-recovery guide](../src/fdisbull/skills/fdisbull-investigate/references/scene-recovery.md):

1. Begin with the unresolved semantic requirements of an already named handler.
2. Follow typed references into only the helpers that can change those effects.
3. Qualify a state field through both its writer and its consumer.
4. Treat output helpers as possible state/RNG operations until their contracts
   are established.
5. Preserve source-observable ordering and shared mutable state even when the
   final visible text or world state would otherwise look correct.
6. Require an independent consumer to check meaning, then trap replaced source
   operations during differential execution.
7. Freeze implementation sources for the final evidence run; a correct earlier
   trace cannot qualify code edited afterward.

The next recovery should again begin from a named residual obligation. Other
window verbs, generic examination, room descriptions/arrival behavior, parser
filters, vehicles, hazards, puzzle handlers and background events remain partly
or wholly in low-level IR. This change adds a complete bounded OPEN/CLOSE
interaction; it does not establish a fully recovered game or a general-purpose
symbolic extraction engine.
