# Browser state and supporting-premise implementation

Implemented on 2026-11-05; verification completed after midnight UTC on 2026-11-06.

## Boundary and result

`replica/web/state.js` and `replica/web/proof.js` implement the retained native game-state and hint-proof contracts in dependency-free JavaScript. They load as the browser globals `SherlockState` and `SherlockProof`, and expose the same objects through CommonJS for Node verification. The only dependencies are the authored `engine.js` and, for the proof module, `state.js`.

The reference for this slice is `replica/state/sherlock_state.c` and `replica/state/sherlock_hint_proof.c`. The retained fDisBull reconstruction guidance supplied the method: declare the seam, preserve widths and ordered effects, distinguish the executable reference from the candidate, test failure and unchanged-state behavior, compare complete state, and record the qualification boundary. No original game executable or Watson backend was run by this implementation step. The independent reviewer compiled the existing C reference and compared it with JavaScript; that establishes the finite C-to-JavaScript observations in the review receipt, without renewing the separate original-to-native claim.

The focused implementation suites pass 181 state checks and 227 proof checks, including 19 independent row-permutation enumerations. The separate reviewer reports 1,116 matching state transitions and 458 accepted hints across all traces; 455 of those hints finish generated seeds 0, 42 and UINT64_MAX. It also covers 19 explanation and 11 replay fixtures. See [the independent review](parity-review.md) and its machine-readable receipts for exact source identities and the complete cross-module result.

## Game state and mutation APIs

All coordinates and items use zero-based indices. A cell mask has bits 0–5 for its six candidate items. An explicitly selected item is stored separately from a singleton candidate mask, as in native C. Singleton masks never select themselves automatically.

| API | Result and behavior |
| --- | --- |
| `createGame(puzzle, timeLimitSeconds = 0)` | Returns an owned game with copied public puzzle fields, givens applied and clue positions initialized. The time limit is uint32 seconds; zero is unlimited. Invalid puzzle shape or limit throws. |
| `cellByte(game, row, column)` | Returns the native packed byte: candidate bits, bit 6 for an explicit selection or bit 7 for a fixed given. |
| `remove`, `restore`, `choose` | Accept `(game, row, column, item)` and return -1 for invalid arguments, 0 for no mutation or 1 for a mutation. Successful changes push a board snapshot. |
| `undo(game)` | Restores one board snapshot and returns -1/0/1. At most 25 snapshots are retained. It never restores elapsed time. |
| `clueGroup(clue)` / `puzzleClueGroup(puzzle, index)` | Return vertical group 0 or horizontal group 1. Recovered original display slots take precedence over the relation category. Invalid puzzle clue indices return -1. |
| `clueLocation(game, index)` | Returns `{bank, group, slot}` or `null`. |
| `archiveClue(game, index)` | Moves a clue to the first free slot in the other bank, retaining the source hole. Returns -1/0/1. |
| `moveClue(game, index, destination)` | Reorders inside the current bank and group, with native shifting and capacity rules. Returns -1/0/1. |
| `tick(game, milliseconds)` | Advances the logical clock with uint64 saturation. Returns -1 for an invalid delta, 0 when ignored, or 1 when processed; this return value is a JavaScript convenience because the C function is void. |
| `setPaused(game, paused)` / `quit(game)` | Match the native pause flag and quit transition. |
| `displayTimeMs(game)` | Returns elapsed time in unlimited mode or remaining time, clamped at zero, in countdown mode. |
| `cloneBoard(board)` / `visiblePuzzle(puzzle)` | Produce owned copies of the declared board or public puzzle fields. |

The game keeps native field names: `puzzle`, `board`, `undo`, `undo_count`, `fixed`, `outcome`, `elapsed_ms`, `limit_ms`, `paused`, `hint_pending` and `pending_hint`. `board` contains 6×6 `candidates` and `chosen` arrays, plus the two banks of vertical/horizontal `clue_slots`. Internal groups reserve the native 256 slots, while the visible groups have 18 vertical and 21 horizontal slots. All constants and native enum values are exported.

Both clock fields and `displayTimeMs` use **BigInt**. `tick` admits a nonnegative safe-integer Number, canonical decimal string or BigInt within uint64. Unsafe Numbers are rejected rather than rounded. The browser shell owns wall-clock sampling, suspension policy and display formatting; these modules consume explicit elapsed deltas only. A paused or finished game ignores ordinary ticks.

The port preserves zero-candidate cells and intermediate incorrect player choices. It consults the public verifier only after every cell is explicitly selected. It never checks a stored hidden answer to repair a mistake, report an early error or choose a hint. The construction and proof tests include a throwing `solution` getter to detect accidental reads.

## Hint selection and acknowledgment

`findHint(game, bank = 0, budget = 20000)` returns:

```js
{
  kind, row, column, item, clue_index, explanation,
  result // native selector return: -1, 0 or 1
}
```

Kinds are NONE 0, REMOVE 1, CHOOSE 2, CONTRADICTION 3 and UNRESOLVED 4. Only a move has `result: 1`; a contradiction, exhausted search or no forced move is an informative result with no mutation. `requestHint` returns -1/0/1 and stores the same fields except `result` in `pending_hint`.

The selector follows the native sequence: validate and detect propagated contradiction; check singleton squares; check singleton object positions; scan the chosen clue bank in vertical/horizontal display order; use the recovered local order for SAME, NOT_SAME and LEFT_OF; test generic relation support; inspect all-clue propagation differences; then try bounded consistency and contrary assumptions. Archived clues remain constraints in propagation and search. NOT_BETWEEN retains the recovered positive outer-distance requirement as well as the absent-middle condition.

Requesting a move freezes it without charging time. While the offer is pending, edits, clue manipulation and undo are blocked, ordinary elapsed time advances, and timeout waits for acknowledgment. `acceptHint` clears the pending flag, applies the frozen mutation, charges 30,000 milliseconds only if that mutation succeeds, and gives expiration precedence over a completed winning board. Undo does not refund the fee. These effects and their ordering are covered by the C comparison, including a last-square acceptance at the time limit.

`checkCandidates(puzzle, candidates, budget = 20000)` returns:

```js
{ status, remaining_nodes, nodes_used }
```

Statuses are INVALID -2, UNKNOWN -1, UNSAT 0 and SAT 1. A node budget is an unsigned 32-bit Number. Zero budget validates shape but does not establish satisfiability, even for an obvious contradiction. The implementation intersects public givens, applies relation tuple support and row Hall subsets, and consumes nodes in the same order as the native search.

## Supporting-premise records

`explainHint(game, selected, budget = 20000)` and `replayHintProof(record, budget = 20000)` both return `{status, record, report}`. Proof statuses are INVALID -1, UNRESOLVED 0, PROVED 1, REFUTED 2 and INCONSISTENT 3.

The record retains the native field names:

```js
{
  version: 1,
  background_rules: 1,
  target: {kind, row, column, item},
  selected_clue_index,
  candidates, given,
  source_clue_count, support_count,
  support: [{index, clue: {type, a, b, c}}]
}
```

`support` contains only its live entries; its length must equal `support_count`. Every candidate mask, given and row-permutation rule remains part of the frozen premise set. Explicit chosen flags, display layout, elapsed time and any hidden answer are outside the record. Omitting `selected.clue_index` when calling `explainHint` is a JavaScript convenience and means -1, with no advisory clue preference.

The report has `{status, node_budget, nodes_used, deletion_checks, reduction_complete, reason}`. The functions first establish that the frozen premises have a completion. Only then do they check the exact contrary of the fixed remove/choose target. One node budget is shared across consistency, contrary checking and support reduction. Inconsistent premises never certify a move. A budget stop before sufficiency produces UNRESOLVED. A budget stop during reduction retains PROVED and the already sufficient support, with `reduction_complete: 0` and no minimality claim.

Reduction tries other clues before the advisory selected clue. A completed deletion pass establishes deletion-minimal clue support relative to **all the frozen candidate masks, givens and row rules**, rather than a globally minimum clue set or a human deduction sequence. Replay checks consistency and sufficiency without redoing reduction or claiming minimality. It does not authenticate the origin of a record; callers that accept external proofs must also bind them to the intended public challenge and board.

The independent permutation controls avoid the implementation's propagation/search routines. They cover combined-clue necessity, givens, Hall-only deductions, a wrong fixed target, premise inconsistency and the loss of sufficiency when an essential premise is removed.

## Save and restore boundary

`exportGame(game)` returns a JSON-compatible object. `importGame(objectOrJSON, expectedPuzzle?)` validates and returns a new owned game or throws; it never mutates an existing live game. `parseSaveJSON` uses the core bounded JSON reader with a 131,072-byte limit, duplicate-key detection after escape decoding, NUL rejection and a depth limit.

The versioned shape is:

```js
{
  format: "sherlock-browser-save-1",
  puzzle: { /* declared public puzzle fields and identity metadata */ },
  board: {
    cells: [/* 36 native packed bytes */],
    clue_slots: [
      [/* 18 vertical slots */, /* 21 horizontal slots */],
      [/* 18 vertical slots */, /* 21 horizontal slots */]
    ]
  },
  undo: [/* at most 25 boards in the same compact shape */],
  undo_count,
  outcome,
  elapsed_ms: "0", limit_ms: "0",
  paused, hint_pending,
  pending_hint: {kind, row, column, item, clue_index, explanation}
}
```

The compact board representation preserves full undo history without serializing unused internal clue slots. The focused normal-puzzle control with all 25 snapshots fits under 16 KiB. The shell must still measure its complete cloud-state envelope because its settings and metadata add bytes, and arbitrary admitted metadata can be larger.

Import uses a closed schema and bounded arrays, rebuilds fixed flags from public givens, validates selected/fixed bytes, verifies every clue is present exactly once in the correct display group, and admits only canonical uint64 clock strings. It verifies the public fingerprint and source-derived challenge identity. When `expectedPuzzle` is supplied, both public constraints and normalized source must match.

Declared outcomes are checked against the actual chosen board and clock: a win needs a complete accepted answer before expiration, a wrong answer needs a complete rejected answer, and timeout needs an expired nonzero limit. Playing cannot be complete or already expired unless the corresponding native initial-givens or pending-hint case applies. A frozen pending offer must still be applicable and is proved from the public board with a shared 20,000-node budget before admission. A pending offer that cannot be established within that budget causes a restore error, never a silently accepted deduction or silently discarded transaction.

The save format is a browser format. It does not claim byte compatibility with a historical or native save file, and the support record is separate from this game save. Display metadata is copied explicitly; `solution` is neither copied nor read.

## Verification and remaining scope

From the repository root:

```sh
node replica/web/tests/state-contract.js
node replica/web/tests/proof-contract.js
node replica/web/tests/parity.js --skip-private --report /tmp/sherlock-parity-public.json
```

The state suite covers packed cells, owned copies, fixed givens, chosen-versus-singleton behavior, archive holes and shifting, the undo limit, pending fee timing, pause and uint64 saturation, strict save rejection and atomic import failure. Proof controls cover consistency, exact targets, shared budgets, selected-clue preference, all 256 source indices, malformed records and independent necessity checks. The independent review separately compares the native reference's observable state, hint and proof results.

These modules expect live game objects created or restored by their APIs. Direct mutation of live fields is outside the admitted application boundary; parser tests do not establish safety for arbitrary JavaScript getters or proxies. A source puzzle can be a well-formed contradictory constraint set, but a playable/restorable grid also needs fixed-cell and display-capacity consistency. In particular, contradictory duplicate givens that make a fixed candidate mask invalid, or a clue layout that exceeds the visible grid, are refused at the restore boundary.

Native C remains the behavioral reference here. Its documented policy differences from the original game remain, including the absence of answer-dependent hint repair and incomplete original qualification of some hint-family ordering. This slice does not qualify DOM input, rendering, suspended-tab clock behavior, durable browser/cloud storage, macOS AppKit, sound or whole-game original equivalence. Those remain shell or future-recovery work; the state and proof APIs give those layers a reproducible implementation seam.
