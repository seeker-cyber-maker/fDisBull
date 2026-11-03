# PQ1 / KQ1: inventory scenes before qualifying their behavior

The original DOS AGI versions are suitable for a deterministic, requirements-first
scene pass. Their indexed resources expose scene ingredients directly. The new
`agi-scenes` command inventories every present LOGIC resource, identifies typed
scene references and resolves a conservative subset of variable-selected values.
It produces a source-bound investigation outline and retained low-level IR.

This is the first stage of the existing
[scene-recovery workflow](SCENE_RECOVERY_FAST_PATH.md): outline, source obligations,
UDL correspondence, then accepted UIL. **The census is not executable UIL and
accepts zero game-intent interactions.** It does not rename bytecode and call
the result recovered intent. The Zork converter, player and tests are unchanged.

## Select the edition first

The tested inputs are KQ1 DOS 2.0F (1987-05-05) and PQ1 EGA/DOS 2.0G
(1987-12-03). Both overlays contain `Version 2.917`, and their LOGDIR identities
match the DOS entries in the pinned
[ScummVM detection table](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/detection_tables.h).
Those are resource-profile checks, not proof of publisher authenticity, execution
equivalence or byte-identical native interpreters. The verification receipt
records exact identities.

The command requires `--profile 2.917`; it does not infer a profile from a game
title. SCI remakes, early KQ1 GAL/booters, AGI3 and alternate platform layouts
need separate frontends. For SCI, the analogous investigation would begin with
room objects, classes, properties and selector methods, then follow initialization,
events, attached scripts and timed state changes. This PR implements no SCI
frontend and makes no compatibility claim for those editions.

## Use the two stages

```sh
fdisbull agi-scenes /private/game --profile 2.917 --stage outline
fdisbull agi-scenes /private/game --profile 2.917 --stage resolve

# Expand source structure and literal text for private investigation.
fdisbull agi-scenes /private/game --profile 2.917 --stage resolve \
  --include-ir --include-text
```

The default stage is `resolve`. Python uses
`fdisbull.agi_scenes.inspect_scenes(game_dir, profile=..., stage=...)`.
The projectless JSON method is `agi-scenes` with the same argument names.
An inherited/default native project is not opened. No original file is changed.

Large replies use the existing output-artifact protocol. Retrieve coverage with
`output-select ARTIFACT /result/coverage`, then select logic records or export the
private result. Retrieval does not rerun the game or analysis. See
[the quickstart](AGENT_QUICKSTART.md#retrieve-a-large-response).

The result can contain target-derived script operations and facts. `--include-text`
adds literal message templates, vocabulary spellings and inventory names. They
remain private investigation material. Omitting text is not a general publication
sanitizer; the public verification receipt contains selected aggregate evidence.

## Start with scene requirements

| Element | Direct evidence | Still needed for execution |
| --- | --- | --- |
| Identity / progression | Typed `new.room` targets | Guards, room dispatch and reachable state |
| Entry / phase | Initial payload offset 2 and scan-start successors | Applicable phase and surviving state |
| Background | Picture load, draw and overlay references | Conditional composition and room ownership |
| Actors | View references and setup sites | Entity meaning, geometry, motion and state |
| Commands / conditions | Ordered tests, `said` patterns and vocabulary | Admission, short-circuit effects and all relevant branches |
| State changes | Raw variable, flag and inventory operation sites | Named facts, writer/reader agreement and ordered effects |
| Output | LOGIC-local messages and sound references | Substitutions, modal behavior and completion effects |
| Time | Motion, cycle, sound, timer, RNG and scan-state sites | Scheduling; no command-equals-turn assumption |

Read indexed data and the guest script structure needed to locate these elements.
There is no need to reverse the native interpreter again for every room or
collect a screenshot before accepting a structural fact. A later executable
claim still needs the complete relevant semantics.

## Deterministic process

1. **Snapshot resources once.** Read the four directories in fixed order. Resolve
   filenames unambiguously, validate headers and extents, and hash each directory
   and referenced volume once. Retain malformed entries beside valid siblings.
   WORDS.TOK and encrypted DOS OBJECT have separate identities and decode status.
2. **Separate code and data.** Respect the LOGIC code length. Decode message
   offsets and their shared cipher stream separately; recover vocabulary prefix
   compression and inventory records with typed IDs. Text remains literal CP437
   templates, without runtime substitutions.
3. **Build the outline.** Decode instruction boundaries and ordered condition
   tokens. Collect references, phase entries, state sites and cycle-sensitive
   sites. Opcode-looking bytes in operands or messages cannot become room edges.
4. **Resolve the supported frontier.** Run a bounded local CFG worklist. Preserve
   byte semantics, union small candidate sets at joins, and keep unknown values
   and reasons. This is not path feasibility, interprocedural analysis or a VM.
5. **Attach source obligations.** Preserve source identity, payload offsets,
   ordered IR, possible entries and analysis scope. Select one interaction, close
   its dependencies and define explicit UDL mappings before permitting UIL to run.

The same bytes, options and implementation produce the same canonical result.
Timing is separate. A matching digest identifies a document; it does not certify
that its semantic interpretation is correct.

## Read the result at its actual qualification level

`fdisbull-agi-scene-census-1` contains:

- `source`: directory, volume and optional-data identities and read counts.
- `coverage`: separate resource, layout, value-analysis, reference and intent
  counts. `scene_discovery_complete` stays false in this version.
- `scenes`: statically named room-target candidates, including lexical targets
  outside known entry flow. They do not constitute a complete world graph.
- `presentation_candidates`: background-producing LOGICs, possibly helpers.
- `dispatch_candidates`: LOGIC-0 calls through variable 0. Only the source operand
  relation is established; guards and full invocation context remain unqualified.
- `logics`: every present LOGIC, including errors, conditions, command patterns,
  references, messages, source locations and retained IR identity.
- `vocabulary` / `inventory`: typed data, explicit absence/errors and opt-in names.
- `remaining_obligations`: semantic work still needed before intent acceptance.

Do not equate LOGIC count, background-producing scripts and room-target count.
A helper can display a background, and a script called a helper can be entered
as a room. Numeric equality between a room, picture, view, sound or inventory
object is not a semantic connection. Messages are scoped to their owning LOGIC.

Every decoded LOGIC stays `low_level_ir`. Its
`fdisbull-agi-structural-ir-1` body is available with `include_ir`; the compact
form retains digest, count and source identity. It is non-executable. Unsupported
layouts and budgets retain opaque source references, requiring the original
resources for further work. Instruction `offset` and `end_offset`, plus branch
successors, are integer offsets in the LOGIC payload, not native addresses.
The document and IR hashes survive Python, JSON and CLI serialization.

## Conservative resolution and explicit limits

Variables begin unknown at the initial entry and every possible saved scan
entry. Constants and sets of at most eight byte values propagate through selected
assignments, arithmetic and indirect accesses. Increment/decrement saturate;
addition/subtraction/multiplication wrap to a byte. Division by zero stays unknown.
A known value joined with an unknown predecessor remains unknown.

Calls and unmodeled effects invalidate facts; the call target is recorded first.
A multi-target indirect write is a weak update, and an unknown destination
invalidates all possibly aliased values. Timer variables 11–14 and input variable
19 stay volatile even after assignment. Only a small explicit command set
preserves other facts.

The worklist does not evaluate conditions or prove feasibility: both branches
remain possible. `said` keeps its evaluation order and statefulness. Room changes
terminate local flow; cancelable restart/restore actions retain a conservative
continuation. Room reset/abort behavior and cycle scheduling remain obligations.

Original `trace.on` has context-dependent width. A LOGIC containing it remains
opaque; ScummVM's no-op implementation does not qualify Sierra tracing behavior.
Neither tested game contains that opcode. The shared layout table now also admits
the valid zero-operand false condition and final `hold.key` action.

Default global budgets are 100,000 main-stream instructions, 1,048,576 code bytes
(including condition operands), and 200,000 worklist updates. Options are
`--max-instructions`, `--max-code-bytes` and `--max-updates`. An unfinished value
analysis cannot publish its partial sets as resolved targets. Unexpanded LOGICs
retain budget status; a later small resource can still fit the remainder.

## Qualify one interaction next

KQ1's bow-to-king action is a useful candidate because the
[earlier benchmark](KQ1_ASSISTED_TRAVEL_BENCHMARK.md) records response, score and
dialogue boundaries. That is historical evidence, not fresh execution of this
census. PQ1 also has bounded candidates in the
[conditional-navigation investigation](PQ1_CONDITIONAL_NAVIGATION_FINDING.md).

Bind exact entry and admission conditions; recover named state from writers
and consumers; include helper, refusal and repeat branches; preserve output,
modal work, RNG and cycle effects; define UDL correspondence; then execute the
candidate against a qualified reference boundary. Promote only the covered
contract. The census accepts no interaction and supplies no AGI UIL player or
native code generator. A separate [KQ1 bow intent](KQ1_BOW_INTENT.md) now executes
one bounded initial-audience interaction with UDL mappings, preserved IR,
source comparisons and selected original-game checks.

## Evidence, cost and sources

See [verification](VERIFICATION-AGI-SCENES-2026-10-30.md) for input identities,
coverage, unresolved resources, repeated timings and source checks. Reproduce
the selected aggregate receipt with your own private inputs:

```sh
PYTHONPATH=src python scripts/verify_agi_scene_census.py \
  --game kq1=/private/kq1 --game pq1=/private/pq1 \
  --runs 5 --output /private/agi-census-verification.json
```

It checks complete bytecode re-encoding, stable IR across stages, agreement with
the preserved inspector's supported subset, deterministic output and unchanged
inputs. These are source-correspondence checks, not execution equivalence.
Timing includes reads/hashes, parsing, stage work and canonical digests in an
already imported Python process. Setup, research, startup, report serialization
and backing checks are outside the interval. No matched speedup is claimed.

Primary references: [AGI bytecode](https://peterkelly.github.io/agi-re/spec/logic_bytecode.html),
[version profiles](https://peterkelly.github.io/agi-re/spec/version_profiles.html),
[AGI2 loader](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/loader_v2.cpp),
[messages](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/logic.cpp),
[vocabulary](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/words.cpp),
[inventory](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/objects.cpp),
[volatile variables](https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/global.cpp).
