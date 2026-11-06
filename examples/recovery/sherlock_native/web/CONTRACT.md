# Browser implementation seam

The browser uses plain JavaScript with no runtime dependencies. Authored source belongs here; original game binaries/assets/tables do not. `engine.js`, `state.js`, and `proof.js` each use a small UMD wrapper: attach `SherlockCore`, `SherlockState`, and `SherlockProof` to `globalThis` in a browser and export the same object via CommonJS for Node verification.

## Shared data

Internal puzzle objects use native field names: `{number, given: 6x6 integers (-1 or 0..5), clues: [{type:0..7,a:0..35,b:0..35,c:0..35}], original_slot: [integer]}`. `solution` may exist only internally in generator/solver output; gameplay, hints, proof, exported public challenge and verification must never consult it. `clue_count` equals `clues.length` when retained. Clue and outcome/hint enum values match C headers exactly. Cell masks are 0..63 and chosen cells -1 or 0..5.

Use finite integer checks, preserve the full unsigned 64-bit seed with BigInt, and emit 64-bit values as decimal strings at JSON boundaries. Explicit budget exhaustion is unknown/unresolved, never unsat or proof. Reject invalid input without mutating current game.

## Core API

`SherlockCore`: `relationHolds(type,a,b,c)`, `verifyAnswer(puzzle,answer)`, `analyze(puzzle,budget=200000)`, `generate(seed,limits?)`, `publicFingerprint(puzzle)`, `toChallenge(puzzle,source,generation?)`, `fromChallenge(document)`.

`verifyAnswer` returns native numeric `status` (-1/0/1), row/column/clue_index and reason. `analyze` returns numeric native `status` (-1..3), `classification`, `solution_count`, decimal-string `nodes`, `first_solution`, `second_solution`, reason. `generate` returns native numeric `status` (-1 error,0 success,1 exhausted), `puzzle` only on success, and `report` including seed/version/attempts/nodes/proof/reason. It must reproduce C generator version 1, not introduce a new mapping under the same identifier.

`toChallenge` returns the canonical public challenge object in the CLI shape. `fromChallenge` accepts that object or a `sherlock-cli-1` puzzle response, validates the complete admitted schema and fingerprint, and returns a normalized internal puzzle with source/identity metadata. It never trusts a supplied hidden answer. Additional exact exported APIs can be documented alongside implementation.

## State and proof API

`SherlockState`: `createGame(puzzle,timeLimitSeconds=0)`, `cellByte`, `remove`, `restore`, `choose`, `undo`, `clueGroup`, `puzzleClueGroup`, `clueLocation`, `archiveClue`, `moveClue`, `tick`, `setPaused`, `displayTimeMs`, `quit`, `findHint(game,bank=0,budget=20000)`, `requestHint(game,bank=0,budget=20000)`, `acceptHint`, and `checkCandidates(puzzle,candidates,budget)`.

State data uses the native field names; `findHint` returns a hint object including numeric kind. Mutation methods return native -1/0/1 where applicable. `checkCandidates` returns `{status:-2|-1|0|1, remaining_nodes, nodes_used}`. Request freezes an offer without a fee; acceptance applies a move then charges 30000 ms and checks expiration before win. Pending elapsed time advances while timeout waits for acknowledgment. Undo never refunds time. State clone/validation/import helpers may be added but must use owned copies.

`SherlockProof`: `explainHint(game,selected,budget=20000)` and `replayHintProof(record,budget=20000)` return `{status, record, report}` with native proof statuses. Record field names follow the C supporting-premise record. Fixed target, consistency-first, shared node budget, advisory clue considered last during reduction. Never include or read hidden solution.

## Ownership

- Core agent: engine.js and focused core tests only.
- State agent: state.js, proof.js and focused state/proof tests only.
- Parity reviewer: tests and source comparison harness; communicate implementation defects to owners.
- Root: app.js, HTML/CSS, asset adapters, packaging, Space/Site, source publication and handoff.

All agents read the retained fDisBull reconstruction guidance and applicable original/native evidence before implementation. Existing C is the current behavioral reference for the browser seam, with its documented original-fidelity limitations. Do not claim a C/JS comparison independently requalifies original-to-native behavior.
