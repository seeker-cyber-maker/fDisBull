# Zork: recovered game intent over preserved executable IR

Zork now has two separate executable representations. The existing whole-story
conversion remains **low-level executable IR**. A new, partial **game-intent UIL**
defines the mailbox-opening interaction and a bounded player-action counter.
Source-specific **UDL definitions** connect those semantic fields and effects to
the original operations. Every operation whose intent has not been recovered
continues as explicitly identified low-level IR.

The old converter, Word16 consumer, compiled game artifact and their existing
tests are preserved. The legacy format name `fdisbull-uil-word16-1`, its `uil`
role metadata and the `zork-uil`/`--uil` command names remain for compatibility;
those names do not turn its word arithmetic, memory operations and control flow
into recovered game intent. See [the preserved executable profile](ZORK_UIL.md).

This is one bounded semantic recovery within a complete playable conversion.
It does not recover every puzzle, parser rule, autonomous actor or world event.
The [executed verification report](VERIFICATION-ZORK-INTENTS-2026-10-29.md)
records the final implementation identities, reference comparisons and measured
coverage separately from this contract.

## Export and execute

Use the qualified owned story and the existing executable IR, writing new files
outside a Git checkout:

```sh
fdisbull zork-intents /private/ZORK1.DAT \
  --ir /private/zork1.uil.json.gz \
  --output /private/zork1.intents.json.gz \
  --uil /private/zork1.game-intents.json \
  --udl /private/zork1.intent-definitions.json

fdisbull-player --intents /private/zork1.intents.json.gz --seed 12 \
  --checkpoint /private/zork1.intent-progress.json
```

`--ir` preserves the supplied low-level program, after checking its complete
source identity, initial image, layout, entry and selected instruction mappings.
Without `--ir`, the producer invokes the existing compiler. `--uil` and `--udl`
are optional inspection exports of the exact documents embedded in the runnable
package. The pure UIL file is a semantic model with explicit residual requests;
playing the complete game also requires its UDL adapter and retained IR.

The player also accepts `--commands /private/commands.json` for a JSON array of
commands, `--transcript /private/results.json` for actual output and recovery
receipts, and `--resume /private/zork1.intent-progress.json`. The direct module
entry point is:

```sh
python -m fdisbull_player.intent_runtime /private/zork1.intents.json.gz --seed 12
```

Generated resources, source witnesses, transcripts and checkpoints contain
game-derived content. They are private outputs, excluded from the generic
distributions. The producer source extracts narrative resources from the owned
story; it does not embed the game's prose or original instruction bytes.

The producer qualifies only Zork I release 88, serial `840726`, story SHA-256
`0ae5ac229e79094ff368b6669356444af0f35e21d862a1baaa546989085c15fd`.
It rejects other source identities rather than borrowing this edition's
findings. The generic consumer can also execute explicitly authored synthetic
packages, which do not inherit the Zork recovery qualification.

## The three representations

| Document | Format | Responsibility |
|---|---|---|
| Retained executable IR | `fdisbull-uil-word16-1` | Preserve the whole original program as ordered numeric, memory, object-layout, call and control operations. |
| Game-intent UIL | `fdisbull-game-intent-uil-1` | Define named semantic conditions, ordered outcomes, domain effects, narration resources and explicit residual requests. |
| Source UDL definitions | `fdisbull-zork-intent-udl-1` | Bind source identity, original operations, field locations, resources, entry/return conventions and live guards to the semantic definition. |
| Runnable package | `fdisbull-zork-intent-package-1` | Contain the exact retained IR, UIL and UDL together. |

`src/fdisbull/zork_intents.py` owns source qualification and production.
`player/fdisbull_player/game_intents.py` is the independent semantic evaluator.
Its entities and fields have no Zork object numbers, program counters,
attribute bits or source globals. It imports neither the producer nor the
Word16 consumer. `player/fdisbull_player/intent_runtime.py` supplies the UDL
projection and realizes the evaluator's ordered effects in the retained state.

The UIL is executable data: its `requires`, ordered `outcomes`, `when`
conditions and `steps` determine the selected result and effects. The adapter
does not merely label an execution of the old opening routine. On an admitted
semantic path it runs the independent evaluator, commits its effects and
returns through the original frame convention. Only the explicitly unresolved
attribute operation inside that path executes its original IR block.

The evaluator uses `null` for unknown facts. Unknown information is not evidence
that a condition is false. An unsupported semantic invocation returns
`unrecovered` with no effects and unchanged input state; malformed definitions
raise an error. The adapter can then retain the original IR path without
silently claiming that its intent was recovered. Source-code mutation remains
subject to the original consumer's guards and may cause an explicit refusal.

## Recovered primitives and their UDL definitions

The meaningful game-level primitives are opening a container, remembering the
mentioned content for subsequent reference, and counting one player action.
Narration primitives support their presentation; they are not evidence that
another game mechanic has been recovered.

| UIL primitive | Semantic contract | Original operation witnesses in this edition |
|---|---|---|
| `container.open` | Establish the qualified closed container's open state. UIL conditions select the already-open outcome separately. | Category/property guards at `0x8089`, `0x808e`, `0x8092`; open-state guard at `0x8096`; state change at `0x80a3`. |
| `discourse.remember_mentioned_object` | Remember the single mentioned content object and current scene for later pronoun resolution. | Listing call at `0x8ea3`; object and scene assignments at `0x9533`, `0x9536`. |
| `turn.count_player_action` | Increment the displayed player-action count modulo 1000, within its qualified `0..999` domain. | Source span `[0x54ec, 0x54f5)`, containing increment/test and the rollover assignment. |
| `narration.emit` | Emit the named source-derived fragment at its declared position in the effect sequence. | Original print operations at `0x809a`, `0x80b1`, `0x80dc`, `0x80e7`, `0x8e7f`, `0x80f4`. |
| `narration.name` | Emit the qualified entity's current short name. | Original name operations at `0x80e5`, `0x8e82`. |

UDL `primitives` entries retain the exact operation coordinates and their
byte/digest witnesses. `fields` supplies explicit correspondence, including:

| Semantic field or source qualifier | UDL correspondence |
|---|---|
| Target entity | Mailbox, source object 160. |
| `target.is_container` | Target attribute 19. |
| `target.is_open` | Target attribute 11; mask `0x10` in byte `0x886`. |
| `target.opaque` | Inverse of target attribute 12. |
| `target.supports_opening` | Target property 10 is nonzero. The initial value is 10; a wider capacity interpretation has not been established. |
| `target.reachable` | For this binding, the original dispatcher has selected the target and its parent equals the current qualified scene, object 180. General accessibility remains residual. |
| Qualified first content | Leaflet, source object 161; parent is the target and sibling is zero. |
| `first_content.plain_listing` | Leaflet property 14 is zero. Its separate attribute 3 is not interpreted as a game fact. |
| Remembered discourse object | Global `0x7b`, 16-bit word at `0x2347`. |
| Remembered discourse scene | Global `0x7a`, 16-bit word at `0x2345`. |
| Current scene | Global `0x10`, 16-bit word at `0x2271`. |
| `turn.count` | Global `0x12`, 16-bit word at `0x2275`. |

The source action header is `0x8084`, with entry `0x8089` and two zero-initialized
locals. Admission requires action global `0x88` to contain 43, direct-object
global `0x86` to select the mailbox, and the observed calling convention:
return to `0x5871`, storing the handled result 1 in caller local 4. Completing
the semantic action uses the original return machinery, preserving the caller
and discarding the action's temporary frame and stack in the normal way.

### Narrative resources and live dependencies

UDL `resource_bindings` connects each UIL resource to its original print
instruction, inline text offset and dependency witnesses. The named fragments
are `opening_prefix`, `opening_middle`, `article`, `punctuation`, `already_open`
and `opened_empty`. `newline` is separately bound to the newline effect of the
original print-and-return operations. Entity `name_dependencies` identify the
property-table pointer, short-name layout, packed text and referenced
abbreviation entries/text needed to reproduce that name.

The package binds canonical hashes of both IR and UIL, the complete original
source metadata, the initial image digest and exact source witnesses. Live
guards check the selected executable regions and routine headers, structural
layout, text and abbreviation dependencies before semantic replacement. This
includes the original scheduler call at `0x5774` and its return convention.

Write-field descriptors also bind their `source_operation`: the container's
open attribute at `0x80a3`, discourse object/scene assignments at `0x9533` and
`0x9536`, and counter increment at `0x54ec`. The opening definition lists the
original return operations at `0x809a`, `0x80b1` and `0x80f4`. Consumer validation
checks these correspondences against the retained operations, resolving literal
aliases and comparing the actual attribute/global indexes and return values.
Matching hashes alone cannot authorize a field remap that contradicts those
operations. The live guards must cover source witnesses except the explicitly
identified mutable property-value witnesses.

Mutable open/history attributes, object parent/child/sibling links, referent
globals, counter values and property values are not frozen to their initial
bytes. They are projected or checked as current state. Initial property-value
witnesses document the source without turning those values into immutable
runtime guards. A changed dependency or unsupported state prevents semantic
replacement and records the reason; the retained IR still applies its own
execution safeguards.

Hashes and matching witnesses establish correspondence and integrity. They do
not independently prove the inferred game meaning. Behavioral qualification
and its limits belong in the linked verification receipt.

## Mailbox conditions, outcomes and ordered effects

The semantic interaction requires a reachable, opaque container that supports
opening. The source binding admits an empty mailbox or the single leaflet with
the qualified tree and plain-listing property. Other targets, other contents,
multiple children, special initial descriptions, unqualified execution frames
and output-stream contexts continue through the retained IR.

| Outcome | Conditions | Effects inside the action |
|---|---|---|
| `already_open` | Target is open. | Emit the already-open resource and newline; return handled. No action-span state changes. |
| `opened_empty` | Target is closed and empty. | Open the target; execute the unresolved source attribute operation; emit the empty-opening resource and newline; return handled. |
| `opened_with_contents` | Target is closed with the qualified single plain-listed content. | Open the target; execute the unresolved source attribute operation; narrate the opening and contents; remember the mentioned object and scene; emit punctuation/newline; return handled. |

The content outcome's actual UIL steps are:

```json
[
  {"intent": "container.open", "entity": "target"},
  {"residual_ir": "post_open_source_flag"},
  {"intent": "narration.emit", "resource": "opening_prefix"},
  {"intent": "narration.name", "entity": "target"},
  {"intent": "narration.emit", "resource": "opening_middle"},
  {"intent": "narration.emit", "resource": "article"},
  {"intent": "narration.name", "entity": "first_content"},
  {"intent": "discourse.remember_mentioned_object",
   "entity": "first_content", "scene": "current_scene"},
  {"intent": "narration.emit", "resource": "punctuation"},
  {"intent": "narration.emit", "resource": "newline"}
]
```

Each text fragment remains a separate output event. The discourse update occurs
after the content's name and before the final punctuation. It writes the
remembered object first, then the scene, even when the scene value is unchanged.
Comparing only the printed line or final open bit would miss these ordered
effects and the next command's referent.

### The unexplained attribute stays residual

`post_open_source_flag` names a source binding, not a newly inferred game
primitive. It executes the original single block at `0x80a6`, which sets target
attribute 3. Observed source users also involve taking and placing objects,
first room visits, special descriptions and background logic. These uses do
not establish one universal meaning such as "seen" or "touched".

UDL records this as `kind: "single_block"`, with its original operation and
witness. It is the only executable residual request admitted inside the
semantic action. The pure evaluator reports that request as an ordered effect;
the adapter executes the retained block. The format grants no arbitrary host
callback or embedded-code execution capability.

### Why the discourse update is game intent

The meaning is supported by both source reads and subsequent commands. The
source compares the remembered scene with the current scene at `0x579a` and
uses the remembered object as the resolved direct object at `0x57bc`. After a
successful content listing, subsequent pronoun commands address the leaflet.
Moving to another scene makes that earlier reference stale.

Repeating the explicit mailbox command lets the residual parser establish the
mailbox as the direct referent before the action. The already-open outcome
does not overwrite it. An empty reopening likewise leaves the parser's
reference in place, while a nonempty reopening establishes the listed leaflet
again. Taking and returning the leaflet does not prevent the qualified generic
listing merely because its unresolved attribute 3 has changed. These cases
constrain the semantic rule beyond the initial opening transcript.

## The complete input-to-prompt interaction

The complete interaction composes recovered intent with the original
executable behavior. Its envelope explicitly records every residual phase:

| Phase | Execution and boundary |
|---|---|
| Input, parsing and action selection | Residual IR handles tokenization, pronoun validity, accessibility and dispatch. No intent is inferred from the command string alone. |
| Mailbox action | On an admitted source entry, UIL chooses an outcome and executes its ordered effects, including the visible residual attribute operation. Otherwise the action remains IR. |
| Action return and bookkeeping | Residual IR resumes at `0x5871` and decides how command processing continues. |
| Scheduler and background callbacks | Residual IR calls routine `0x54c4` at `0x5774`, dispatches events and preserves timers, random draws and hidden object/state changes. |
| Count a player action | At the qualified end of that scheduler traversal, UIL executes `turn.count_player_action`. |
| Return, cleanup and next input | Residual IR resumes at `0x54f5`, returns the scheduler's result and prepares output/status and the next input boundary. |

The counter hook admits only a four-local scheduler frame returning to `0x5779`
with result stored in caller local 7, with its traversal cursor equal to its end
and the counter in `0..999`. The semantic result is `(count + 1) mod 1000`.
At rollover, UDL preserves the original intermediate write of 1000 followed by
zero. The scheduler's final return remains residual; its existing result and
the rest of the frame are preserved.

The primitive counts one action at this source boundary. It does not implement
or claim to understand the complete turn scheduler. An unknown word, an
unavailable target, a meta command and a waiting command have different turn
behavior in the original program. The retained parser and scheduler determine
which counter boundaries are reached; the adapter does not apply a guessed
"one command equals one turn" rule.

Recovery receipts distinguish `game_intent_uil` segments from `low_level_ir`
segments, record the selected semantic outcome and executed primitives, and
count actual residual execution and fallback reasons. A response that uses
only retained IR is identified as such. Background callbacks remain visible
in that accounting even when the opening and counter are recovered.

## Checkpoints and validation boundary

The hybrid consumer's checkpoints bind the complete package identity: retained
IR, semantic UIL and UDL definitions. A changed semantic rule cannot silently
reuse a checkpoint merely because the underlying low-level IR is unchanged.
Nested game-save slots use the same hybrid identity. The existing standalone
IR checkpoints and tests remain associated with their original format and
consumer; no compatibility is inferred between those identities.

Semantic effect plans are ordered, not transactional. A preflight fault occurs
before any semantic effects execute; a later fault preserves effects already
performed, including any partial effect whose completion is unknown. The
consumer does not roll back, delegate, or retry that faulted action. A failed
run raises `Word16Error` and exposes its current `last_recovery` receipt: a
`preflight_fault` has no completed effects, while a `commit_fault` lists
completed effects and identifies any interrupted effect as unknown. A fault
after all effects, during return or continuation, has no interrupted effect.
Completed effect entries establish that their calls returned, not a complete
trace of individual writes within a residual block.

When `--transcript` is supplied, a fault adds a private fault receipt before
the error is returned. The CLI writes checkpoints only after successful runs;
on a fault the last checkpoint remains at the preceding successful boundary,
not at the partial state. Resuming it in a fresh process starts from that
boundary and does not resume or replay the failed action automatically. Fault
receipts are not stored in checkpoints, and programmatic callers must retain
the receipt separately if needed. Original interpreter partial-failure parity
is not established by these synthetic tests.

The independent verifier checks the higher-level runtime against the preserved
consumer and existing original-game reference harness. Full state and ordered
effects matter in addition to narrative, score and moves. Synthetic fixtures
exercise the address-free evaluator and source adapter without licensed game
assets. Source binding hashes, actual primitive execution, unsupported-path
fallback and residual execution are separate claims to check.

See [the verification report](VERIFICATION-ZORK-INTENTS-2026-10-29.md) for the
executed results and exact artifacts. Successful comparisons qualify the
declared cases and source edition. They do not promote the parser, hidden
callbacks, other actions, other editions or all possible game paths to
recovered UIL. The UDL receipt explicitly retains
`all_game_intent_recovered: false`.
