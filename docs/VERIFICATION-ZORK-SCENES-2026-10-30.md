# Zork scene UIL: executed verification, 2026-10-30

## Result

The recovered scene layer executes named progression rules over the preserved
Zork conversion. All **110 room definitions and 352 encoded directional exits**
have explicit identities and definitions. Qualified table/property dispatch
links select named handlers without executing their original stack-carried
target lookup. `scene.select_exit` chooses a destination or ordered refusal
effects; `scene.move_actor` realizes the qualified on-foot relocation.

The final comparison passed **465 commands at 477 boundaries across 12 cases**.
Every compared game result, complete machine snapshot and ordered physical
effect sequence matched the unchanged low-level consumer. Fresh Frotz runs
also matched narrative and score/move fields at every boundary. The full
396-command route finished with score **350** and **394 moves**.

This is bounded semantic recovery, not a claim that all game intent is known.
The remaining parser, event, puzzle, special-exit and arrival bodies are
explicit residual IR. A resolved handler identity does not establish its
semantics. The preserved conversion still supplies these behaviors.

The runnable format and commands are documented in [ZORK_SCENES.md](ZORK_SCENES.md).
The compact machine-readable evidence is
[verification.json](evidence/zork-scenes-2026-10-30/verification.json).
Original game files, generated game resources, detailed captures and save
states are private inputs and are excluded from Git and generic distributions.

## Qualified source and preserved work

| Item | Identity or result |
|---|---|
| Story | Zork I, Z-machine v3, release 88, serial `840726` |
| Full story SHA-256 | `0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd` |
| File / declared extent | 92,160 / 84,876 bytes; the edition identity includes padding |
| Integrated upstream | Main commit `85503c0e895842424faa7db62f020b879d08568a`, version 0.25 |
| Pending processor work retained | [PR #28](https://github.com/seeker-cyber-maker/fDisBull/pull/28), head `bfcdfe8eb5a030cb6f0e917067690fe2f7e4d03c` |
| Preserved intent document digest | `d4e1f586a39b6fe59987c4b2e25bd17d9e0a009c3bb5208b0a8d4f5122f11d01` |
| Final generated package SHA-256 | `405d7398b5190b428ec11b089b11064e366060484026531a8694f6618d5e65db` |
| Semantic scene document digest | `dab825eac678c6b1fdc51414d6771799cdf147afa2d3031babd44140585a6e05` |
| Semantic dispatch document digest | `e617f6df0ab4d35eb27405799d3c2ed782109a1f58d5e691df44a37244da2fc0` |

The existing intent package is embedded unchanged. Seventeen protected source
and test files were hashed before and after this work; all remain unchanged
from the integrated baseline. They include the original converter, Word16
consumer, mailbox intent producer and consumer, Z-machine processor, both
earlier verifiers and the original conversion/intent tests. The new exporter,
validator, evaluator and compatibility consumer are separate modules.

The integrated baseline includes upstream's earlier intent fault-handling
fixes. This work does not revert those fixes or substitute an older runtime.

## What was recovered

| Recovered structure | Count | Scope |
|---|---:|---|
| Named scenes | 110 | Unique graph-based associations, including rooms with repeated displayed titles |
| Direct exits | 277 | Named destination |
| Explicit blocked exits | 37 | Bound refusal resource and newline |
| Conditional exits | 25 | Current named Boolean selector, with true/false/unknown distinguished |
| Door exits | 6 | Current state of one of three named doors |
| Routine exits | 7 | Named, pre-resolved residual handler |
| Static long descriptions | 87 | Original resource; not a replacement for a room callback |
| Room callback references | 40 | Seventeen scenes have both a callback and static fallback |
| Narrative resources | 147 | Extracted from the qualified story, with dependency witnesses |
| Default action links | 146 | All table slots connected to dictionary/grammar evidence |
| Nonzero preaction links | 13 | Resolved targets; body semantics remain residual |
| Initial nonzero property callbacks | 135 | Source-backed callback links |
| Property/default mappings | 750 | Three callback properties for each of 250 objects |
| Named residual handler identities | 305 | Identities, not 305 understood game rules |
| Supported callback mutation origins | 23 | Finite source-defined alternatives with setter evidence |
| Replaced dispatch sites | 18 | Qualified direct selection at the original call boundary |

Scene symbols are associated by matching the actual direction/kind/destination
graph to sanitized historical naming metadata. Neither displayed titles nor
numeric profile hints choose the association. The qualified edition's object
identities are checked after the graph has yielded a unique result.

The metadata provenance is
[historicalsource/zork1, revision 97b7b3d](https://github.com/historicalsource/zork1/tree/97b7b3d68c075dd9af7da499c3e9690ada3471fd).
That historical revision differs from the qualified binary. Its code is not
transplanted as an equivalent executable: actual binary operations establish
the conventions and actual story resources supply the narrative.

The pure scene evaluator contains no story image, source instruction addresses,
packed targets, object numbers, global-variable numbers or VM operand stack.
Its inputs are named scenes, directions, facts, doors and actor location.
UDL connects those meanings to the original operations and storage. The
compatibility adapter realizes admitted effects and calls explicitly residual
bodies through their already resolved definitions.

## Complete house interaction and forbidden-mechanism check

The 16-command house case exercises first and repeated mailbox opening,
contents removal, closing and reopening, a false endgame condition, a blocked
exit, ordinary travel, a closed window, opening that window, entering the
kitchen, leaving it and returning to the initial scene.

| Interaction part | Condition, effect and continuation checked |
|---|---|
| Mailbox opening | Existing recovered opening intent, output, discourse state and bounded turn counter remain active |
| Conditional/refused exit | Current fact selects the original refusal; location and actor containment remain unchanged |
| Closed kitchen window | Ordered prefix/name/suffix/newline, then mentioned-door and mentioned-scene updates |
| Open window and entry | Residual opening action changes live door state; the next semantic selection chooses `kitchen` |
| On-foot movement | Original pre-move admission reaches the qualified boundary; `scene.move_actor` updates containment and current scene |
| Arrival and turn completion | Residual arrival output/events plus the preserved scheduler and action counter retain their original effects |

The case compared all **1,592 ordered physical effects** and all 17 complete
boundary snapshots. It finished at score 10 and 16 moves. It executed nine
semantic exit selections and six semantic relocations, with zero scene
fallbacks.

The verifier made **77 original instruction blocks forbidden**: the qualified
dispatch-site sequences, exit-selection operations and two relocation
operations. Executing one of those blocks through the old mechanism would fail
the case. The successful run therefore establishes actual substitution for
this case, beyond agreement obtained by silently executing the original
selector. Residual handler bodies remained executable as declared.

## Executed comparison matrix

| Check | Commands / boundaries | Result |
|---|---:|---|
| Complete house interaction | 16 / 17 | All game results, full snapshots, ordered effects and Frotz observations equal; original selector blocks forbidden |
| Winning route | 396 / 397 | All equal; score 350, moves 394 |
| Nine preserved interaction cases | 28 / 37 | All equal, including pronouns, unavailable targets, repeated opening, meta input and WAIT |
| Parser alternatives | 25 / 26 | All equal |
| Fresh-process checkpoint resume | 296 remaining commands | All results and final complete snapshot equal |
| Earlier native interpreter captures | 33 commands / 34 boundaries | All 11,795 compared game-memory bytes and input boundaries equal; seven observed RNG events equal |

The winning route executed 236 semantic exit selections and 237 semantic
relocations. Relocation can occur through residual behavior as well as a
directional command, so these counts are not expected to be identical. Two
unqualified actor/scene movement cases explicitly used residual IR. They were
not silently counted as recovered relocation.

The native check reuses the existing captured original-interpreter evidence.
It does not claim a fresh native emulator run. The interpreter-specific header
bytes 0 through 63 remain excluded as in the earlier checker, and RNG is coupled
to observed original outputs. Frotz comparisons were freshly executed with
seed 12. Their text normalization is the unchanged earlier verifier's policy.

The complete IR-to-scene snapshot comparison normalizes only recursive
package identity. It does not erase caller frames, locals, object links, input
state or RNG state. Result comparison excludes implementation step counts and
recovery audit fields; a consumer dispatch count is not a game turn count.
The effect comparison preserves every physical assignment, output fragment
and random draw in order, including writes whose value is unchanged.

The independent resume ran a fresh Python process with `-I`, six copied
consumer modules, the generated package, checkpoint and command tail. Source
package imports, external file reads, network and subprocess access were
refused. No original interpreter or analysis package was loaded.

All six executing consumer source files retained their exact hashes throughout
the final verification run. The sanitized evidence identifies the verifier,
source files, command source and generated package used in that run.

## Counterexample found and corrected

The first complete route attempt exposed a real mismatch at command 94, `E`:
the Loud Room requested input before an enclosing travel routine returned.
Output, game memory, ordered effects, score and turns already matched, but
two suspended caller locals differed. They held the original exit record's
address and length.

The fix adds a UDL projection of residual-frame fields. At the residual join,
the adapter materializes the already known source constants, including
branch-specific door/failure fields where appropriate. It does not run the
old property search, length switch or stack-target calculation. The semantic
scene document is unchanged. Authored nested-input and save/restore checks
cover this boundary, and the final complete-route comparison includes these
caller locals rather than hiding them.

Other scoped review corrections retained branch-specific return continuations,
refused cached refusal output when a memory stream could mutate later text
dependencies, and recorded completed parts of composite effects before a
fault. A partial commit is never retried through residual code.

## Authored tests and distribution checks

The final combined focused gate passed **494 tests**, with **5 skips**:
228 new scene tests and 266 preserved processor/conversion/intent tests.

| New test area | Passed |
|---|---:|
| Pure semantic evaluator | 59 |
| Independent player-side source bindings | 34 |
| Scene producer and graph association | 32 |
| Dispatch recovery | 35 |
| Operational scene runtime | 22 |
| Export/player CLI | 46 |

An independent static audit passed **1,492 evaluations**: all 352 encoded
exit definitions, every Boolean alternative for conditional and door exits,
and all 1,078 absent scene/direction pairs. It checked original property
interpretation, exact narrative, discourse effects, routine entry/default
locals and unchanged selection inputs. This establishes static correspondence
and evaluator behavior; it does not assert every alternative is reachable.

The initial full repository run reported 2,163 passes, 109 skips and 66
failures. Running exactly those 66 failed test IDs on the unchanged integrated
baseline reproduced 50 failures: 30 existing Git/output-boundary cases,
10 missing optional managed-decoder dependency cases and 10 socket/transport
cases in this restricted environment. The remaining 16 failures came from
three packaging test fixtures listing the old module set. Those fixtures now
include the three new player modules. All **41 tests** in those three
packaging files pass. The final focused and packaging gates do not claim that
the entire local suite is green.

Core and standalone-player wheels were built with the installed setuptools
backend, without downloading or installing dependencies. Both distribution
gates passed, every packaged source file matched the candidate source bytes,
and the source inventory remained unchanged. The exact artifact identities
and isolated console checks are recorded in the evidence receipt.

Fresh processes invoked the actual console entry points from those exact
wheels. The core export reproduced the qualified scene package byte-for-byte.
The standalone player executed the house case in two eight-command phases,
resuming the saved checkpoint in a new process; all 17 game results and both
complete saved states matched the validated reference. Repository/source
reads, network and child processes were refused. Player phases also refused
original-story and prior-conversion file reads. All project imports came from
the selected wheel, and no isolation violations occurred.

## Reproduction

The source-specific producer and reference verifier require the user's owned
qualified story. Generated game artifacts must remain outside Git:

```sh
fdisbull zork-scenes /private/ZORK1.DAT \
  --intents /private/zork1.intents.json.gz \
  --output /private/zork1.scenes.json.gz \
  --uil /private/zork1.scenes-uil.json \
  --udl /private/zork1.scenes-udl.json.gz \
  --dispatch /private/zork1.dispatch-uil.json

PYTHONPATH=src:player:scripts python scripts/verify_zork_scenes.py \
  --package /private/zork1.scenes.json.gz \
  --story /private/ZORK1.DAT \
  --commands /private/winning-commands.json \
  --parser-commands /private/parser-commands.json \
  --frotz /private/dfrotz \
  --native-receipt /private/native/receipt.json \
  --output /private/new-scene-verification
```

The native receipt is optional; omitting it does not establish native parity.
The original verifier scripts and original tests remain available unchanged.

## Remaining semantic boundary

PERFORM's conditions and first-handled branching between dispatch stages are
still residual. This work replaces the admitted target transport and exposes
the stage definitions; it does not claim a new semantic implementation of the
entire dispatcher. Likewise, movement admission, vehicle cases, darkness,
hazards, most arrival rules, callback bodies, fact setters, parser behavior
and background events still use retained IR unless an earlier independently
qualified intent applies.

Known runtime facts are projected live. Unknown facts are not false, missing
directions are not fabricated refusal messages, and changed structural or
narrative dependencies trigger an explicit fallback. Resolving a target does
not authorize deleting an unexamined handler.

This is an executable source-specific UIL/UDL companion profile. It does not
claim conformance to a future universal shared-block catalog, semantic/backing
revision registry, UDC selection registry or generic interface/readiness
contract. The documentation proposals in open
[PR #29](https://github.com/seeker-cyber-maker/fDisBull/pull/29) and
[PR #30](https://github.com/seeker-cyber-maker/fDisBull/pull/30) were reviewed as
proposals, not silently adopted as implemented contracts. The bound UDL and
retained source backing remain part of the package's meaning and validation.

The recovered scene rules now provide the direct place to express and test
further game intent. Each residual handler can be replaced separately once
its actual conditions, effects, output and turn behavior are understood.
