# Partial Zork game-intent UIL: executed verification

The preserved word16 conversion is **low-level executable IR**. The new layer
executes a separate, address-free game-intent UIL definition for one bounded
mailbox interaction and a qualified player-action counter. UDL definitions
connect its fields, effects, resources and continuations to the original
operations. Unrecovered behavior remains explicitly executable IR.

The final mixed consumer passes the original-game comparisons below. This is
evidence of **partial intent recovery within a complete playable conversion**;
it is not a claim that all game intent, the parser or the turn scheduler has
been recovered. The package records `all_game_intent_recovered: false`.

See [the representation and source contracts](ZORK_INTENTS.md), the
[preserved IR profile](ZORK_UIL.md), and the
[machine-readable receipt](evidence/zork-intents-2026-10-29/verification.json).
Raw game text, source witnesses, complete states and native captures remain
private. The public receipt contains hashes, counts and scoped results.

## Identities and preservation

| Subject | Identity |
|---|---|
| Source edition | Zork I, Z-machine v3, release 88, serial `840726` |
| Source SHA-256 | `0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd` |
| Preserved PR head before this addition | `20f9d79052dcb8977e2bd52b218a42851eb26916` |
| Preserved word16 runtime SHA-256 | `f5ca20999a1dea38b03df9386337a43600b54235fe4caffcbfb63a94dabc4168` |
| Preserved IR artifact SHA-256 | `f29a6ed0ad1e4db1bcf01b5f5a39b80c8ecd6524f8cca17ee10c8bf5a07c4607` |
| Canonical retained IR SHA-256 | `7ce71ee09f973a713a68e7246771010dd2a96d6ecd4c1e11cf91bdd51d19ee33` |
| Canonical game-intent UIL SHA-256 | `2bcaf44a91d5d328b8e37da7f50ec3316a32d3251ed1e7bc5ef9684b997fae69` |
| Canonical complete intent/IR package SHA-256 | `d4e1f586a39b6fe59987c4b2e25bd17d9e0a009c3bb5208b0a8d4f5122f11d01` |
| Qualified v4 package file SHA-256 | `9d68e08f4bcb3da6bf16e40b1697fd2e2a2ab119b1891e9b51ead0f45f42c3b5` |
| Pure intent evaluator SHA-256 | `aab1714faedd38488a0e918e8409cde514815ec1e23df3f663b226fec534675f` |
| Intent/IR adapter SHA-256 | `969c71f221a5013c045d32b12b0ffa2b9c198a6b8ebfb58bbf038e89cadefbeb` |
| Final independent checker SHA-256 | `c55d732a1b2f3bd4ada8f9b040340a1f8933faf4bad2d5f60c4180d849a1d4d6` |
| Reference | Unmodified dfrotz 2.44, source `fe66e2ef738354f5e2fe37c7c01b1781ef659acd` |
| Host actually tested | Linux, Python 3.12.14 |

All eight protected files retain their previous byte hashes: the original
converter, word16 runtime, three conversion/runtime/CLI test files, and the
existing IR, source mapping and initial world exports. The original reference
checker is also byte-identical. Their 69 tests still pass. Legacy command and
wire-format names remain compatible; documentation now distinguishes their IR
meaning from the intended UIL.

The public exporter was run through `python -m fdisbull zork-intents`, supplying
the exact original story and existing IR. Its parsed output equals the entire
qualified v4 package. Its separate UIL and UDL files equal the documents
embedded in that package. Different JSON ordering yields a different gzip file
hash; the canonical package identity and every parsed value are identical.

## What was recovered

The pure evaluator owns the conditions, first-matching outcome and ordered
effects. It executes `container.open`,
`discourse.remember_mentioned_object`, and `turn.count_player_action`, with
`narration.emit` and `narration.name` as presentation support. It has no source
addresses, object numbers, attribute bits, globals or imports from word16.
Authored chest/letter fixtures use different entities and text. Mutation checks
show that changing UIL conditions, steps or resources changes execution.

The opening binding qualifies the original open action, mailbox target, scene,
call frame, output context, container/openable/opaque conditions, and either
empty contents or the single plain-listed leaflet. It covers first opening,
already-open and empty outcomes. Other targets, complex contents, special
descriptions and unsupported contexts retain their original IR.

UDL includes **123 exact source witnesses and 56 live dependency guards**.
The producer checks complete source identity, initial image, layout and the
selected original instruction-to-IR correspondence. The consumer checks field
kinds and ownership, distinct global roles, realized write operands, literal
return values and immutable guard coverage. Mutable game values are read at
execution time. These checks establish structural consistency; source analysis
and behavioral comparisons remain necessary to support semantic meaning.

## One complete interaction, from input to the next prompt

The first `open mailbox` command is recorded with its complete pre-input state,
both complete post-command states, every ordered physical memory assignment,
every output fragment and every random event. The source and mixed runs agree.

| Phase | Executed representation and effects |
|---|---|
| Parse and resolve | 441 retained IR blocks handle input, tokenization, object resolution, accessibility and dispatch. |
| Open and present | UIL selects `opened_with_contents`, establishes the open state, invokes the explicit unresolved flag block, emits the original fragments in order, remembers the mentioned leaflet and scene, and returns through the original action frame. |
| Action bookkeeping | 25 retained IR blocks continue the original command-processing rules. |
| Background processing | 145 retained IR blocks update timers and execute callbacks, including offscreen object movement. Their game intent remains unrecovered. |
| Count action | UIL executes the qualified counter update from 0 to 1. |
| Return and next input | 67 retained IR blocks preserve scheduler return, cleanup, status/prompt effects and the next input boundary. |

One further retained IR block, at `0x80a6`, occurs explicitly inside the opening
plan. Thus the audit records 679 residual block executions and two semantic
dispatches. Runtime dispatch counts are implementation work measurements, not
claims about semantic coverage or equivalent instruction granularity.

The complete command has **109 ordered physical memory assignments**, including
the direct input-buffer assignment, **nine raw output fragments**, no random
events, and **55 changed final memory bytes**. The comparison also includes all
frames, locals, evaluation stacks, program position, pending input, host state,
random state and save state. It does not merely compare the open flag or text.

Inside the admitted opening action, the understood changes are the mailbox's
open state and the remembered object/scene used for subsequent pronouns. The
attribute-3 write remains an explicitly named residual binding rather than an
invented `seen` or `touched` intent. Narration fragments remain separate because
the referent assignments occur before final punctuation and newline. A repeated
opening has no action-body state writes, although the surrounding original
parser and turn processing still have effects.

The background scheduler remains IR. In this first command it changes timer
words and moves an offscreen object; matching the full state and write sequence
ensures those effects survive the replacement. The recovered counter does not
claim to explain them.

## Independent comparisons

| Check | Final executed result | Scope |
|---|---|---|
| Unchanged winning route | 396 commands; all 397 initial/response boundaries agree in complete state, ordered effects, game-facing results and Frotz narrative/score/moves | Final 350 points, 394 moves; seed 12 |
| Complete mailbox/repeat/empty sequence | Five commands; all six boundaries agree; three opening-binding hits, two actual open-state effects and five counter hits | Initial opening, reopening, taking contents, closing and empty opening |
| Other focused interaction paths | Eight paths and 23 commands; every boundary agrees | Unavailable target, unknown word, score, wait, and five pronoun paths |
| Existing parser alternatives | 25 commands; all 26 boundaries agree | Existing inputs retained unchanged |
| Aggregate state/effect/text comparisons | **449 commands, 460 boundaries, all equal** | Eleven separate command sequences, including their initial boundaries |
| Captured original DOS execution | **34/34 snapshots**, every one of 11,795 nonheader dynamic bytes agrees; all input PCs agree | Opening and 33 commands through troll combat |
| Captured native randomness | **7/7 range/result pairs** agree | The original random tape is observed, not replaced |
| Fresh isolated process | Resume after command 100; **296/296 remaining results** and the complete final snapshot agree | Only copied consumer/package/checkpoint/commands; workspace reads, network and subprocesses refused |

The winning route **does not open the mailbox**. It executes 392 qualified turn
primitives and zero mailbox bindings. Two other counted actions use a caller
outside the qualified turn-frame contract and remain residual IR. The separate
complete mailbox case must execute both the opening and counter primitives for
acceptance; an unchanged full-score route alone cannot establish opening
recovery. The parser-alternative sequence also executes one actual opening.

Unknown-word and score commands preserve their zero-turn behavior. `wait`
preserves three counted turns through residual IR because its scheduler caller
is outside this binding. An inaccessible mailbox never reaches the qualified
opening entry, while the original control flow still determines its turn cost.
No rule assumes that every input or every successful action consumes one turn.

Frotz runs the original story independently. Its text comparison uses the
preserved checker's normalization: remove interpreter status decoration and
the prompt, then collapse whitespace. Score and moves are compared separately.
This does not establish identical terminal wrapping, pagination or graphics.

The native memory comparison excludes the interpreter-owned 64-byte header.
The mixed-versus-preserved-IR snapshot comparison includes the entire memory
image and all continuation fields, normalizing only the package identity,
including nested game-save identities. Implementation step counts and recovery
audit fields are excluded from game-result equality. Nothing else is omitted.

## Checks that recovery actually executes

The controlled first-open case installs a trap on the old opening body, content
formatter, referent helper and counter body. The only permitted original block
inside the action is the explicitly unresolved attribute-3 effect. The trap
does not fire; the source and mixed results still match, and required semantic
binding/primitive counts are positive.

Authored integration tests also disable semantic execution entirely. The old
IR still produces correct game behavior, but the recovery check fails because
no required primitives executed. Separate tests change a UIL narration resource
and introduce hidden stack corruption; the comparison detects the respective
text/effect and complete-state differences. These checks prevent a label-only
wrapper or fallback-only run from being counted as recovered intent.

Independent review found and verified fixes for flat turn-frame qualifiers,
residual phase boundaries, corrupt UDL field/return mappings, omitted live
guards, and property projection before guard validation. All four corrupt
mapping cases now reject before machine initialization. A real source-state
test changes the leaflet property pointer while the mailbox is already open:
the adapter falls back before interpreting that dependency and exactly matches
the original IR's completed result and state. All effect realizations are
preflighted before applying a plan, and recovery hits are recorded only after
successful completion.

## Repository tests and packaging

The final focused run passes **188 tests**: 69 preserved conversion/runtime/CLI
tests, 85 new intent/evaluator/mapper/adapter/export tests, and 34 distribution
and offline-package tests. The latter include the two additional player
modules; the original 69 test files are unchanged.

The full repository run reports **1,690 passed, 48 failed, 109 skipped**.
The 48 failure IDs equal the previously reproduced unchanged-upstream baseline:
28 existing Git-directory/output guards in this workspace, 10 absent optional
managed-code dependencies, and 10 sandbox socket restrictions. There are no new
failure IDs. This local suite is not globally green. Four initially introduced
offline-wheel fixture failures were fixed before the final run.

Core and standalone-player wheels were built with the installed setuptools
PEP 517 backend without downloading dependencies. The generic tool artifacts
contain code, documentation, authored tests and sanitized receipts; the owned
game package and raw evidence are excluded. These are development artifacts on
the 0.24.0 source line, not a tagged release. Fresh GitHub CI on the final PR
commit is a separate result from this local receipt.

The public entry points also ran from the exact built wheels under Python `-I`,
with audited source/core-import restrictions. The core wheel reproduced the
entire qualified package. The standalone player wheel opened and reopened the
mailbox, preserved the zero-turn score command, and resumed close/reopen in a
fresh process. Its complete checkpoint and resumed results matched a separate
continuous process. The archive gate passed 149 core-wheel and 13 player-wheel
tool-only entries.

## Reproduction

Export and play using the commands in [ZORK_INTENTS.md](ZORK_INTENTS.md). For the
same independent comparison, supply the exact owned story, pinned route, native
capture receipt and unmodified reference interpreter:

```sh
PYTHONPATH=src:player python scripts/verify_zork_intents.py \
  --package /private/zork1.intents.json.gz \
  --story /private/ZORK1.DAT \
  --commands /private/jericho-zork1-candidate-commands.json \
  --parser-commands /private/parser-valid-commands.json \
  --frotz /private/dfrotz \
  --native-receipt /private/native/receipt.json \
  --checkpoint-after 100 \
  --output /private/new-intent-comparison

PYTHONPATH=src:player python -m pytest -q \
  tests/test_uil_word16_runtime.py tests/test_zork_uil.py \
  tests/test_zork_uil_cli.py tests/test_game_intents.py \
  tests/test_zork_intents_mapper.py tests/test_zork_intent_runtime.py \
  tests/test_zork_intents_cli.py
```

## Explicit remaining limits

Parser meaning, general accessibility, background callbacks, autonomous actors,
other puzzles and actions, complex or special-description contents, and the
attribute-3 meaning remain unrecovered. Property 10 is only established as a
nonzero source gate; this work does not assign a wider capacity meaning. The
turn primitive admits counts 0 through 999 and the qualified completed
scheduler frame; other values or callers remain IR. The 999 rollover preserves
both original writes, first 1000 and then zero.

The comparisons qualify these cases and this exact edition. They are not an
all-path equivalence proof, a complete UDL catalog, recovery of every game
intent, original DOS save-file interoperability or qualification of another
host platform or Zork release. Hybrid checkpoints bind both the intent model
and the UDL as well as the retained IR; old IR-only checkpoint compatibility is
not inferred from shared memory layout.
