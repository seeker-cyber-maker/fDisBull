# Browser port: independent finite C → JavaScript review

## Result and scope

**Passed.** The browser core, game state and supporting-premise implementation matched the retained native C implementation on 114 authored oracle fixtures, comprising 4,376 counted equality assertions. The comparison also checked four privately supplied SHI files and seven numbered-puzzle table entries. There were no unresolved behavioral discrepancies in these vectors.

The reviewer authored and ran the C oracle and JavaScript comparison harness independently of the agents implementing `engine.js`, `state.js` and `proof.js`. The C oracle executes the existing native implementation; expected answers and state transitions are not computed by a second JavaScript copy of the same algorithm. The native CLI is compiled separately for exact public-challenge document comparison.

This evidence qualifies a **finite native-C → JavaScript seam**. It does not newly establish original DOS → native equivalence, run the original program, exercise AppKit, or establish browser rendering and input behavior. Existing original-fidelity qualifications and limitations remain in force. In particular, the native hint policy deliberately avoids the original answer-dependent mistake-repair behavior; not every native hint order is an independently recovered original order.

Machine-readable receipts:

- Complete comparison, including private adapter observations (separate workspace record: `research/browser-slice-20261105/parity-review.json`)
- [Resource-free repeat](parity-public-review.json)

The complete run finished at `2026-11-05T23:58:50.014Z`. Each receipt records exact source SHA-256 values, oracle output and executable hashes, compiler identity and Node version. The resource-free run repeats the authored fixture checks without opening original game resources. Private-input failures redact input-bearing diagnostics, so a future failed run does not write original pixels or puzzle records into the receipt.

## Method

The review followed the retained fDisBull reconstruction guidance: declare the observable contract, pin the implementation identities, distinguish the reference from the candidate, test boundary and refusal cases, inspect complete state effects, and demonstrate that a deliberately incorrect rule is detected. The relevant project contract is [`CONTRACT.md`](../CONTRACT.md). The retained methodology is `toolkit/browser-skill-033/references/reconstruction.md`.

This step reused the already recovered native contract. It did not run a new Watson/fDisBull equivalence operation or claim a new original-process observation. The executable reference for this seam was native C built from the sources whose hashes are in the receipt.

The test artifacts are authored source:

- [`parity-oracle.c`](../tests/parity-oracle.c) constructs synthetic puzzles, invokes the native logic/state/proof APIs, and emits JSONL observations.
- [`parity.js`](../tests/parity.js) compiles the oracle and native CLI, applies the same inputs to the JavaScript APIs, and compares the results.
- [`parity-assets.c`](../tests/parity-assets.c) returns native decoded SHI pixel indices to the harness in memory.

No generated oracle binary, original executable, original pixel payload, original puzzle-table payload or live emulator state is needed in the public fixture set. Fresh temporary build products are removed after each run.

## Coverage and observations

| Boundary | Cases and observed result |
| --- | --- |
| Relation predicates | All 8 relation types across all 216 triples of columns: **1,728 truth values** match. |
| Answer verification | **20** native fixtures cover accepted alternatives in ambiguous puzzles, givens, invalid item values, duplicate row entries and accepted/rejected relations. |
| Solver | **13** fixtures compare classification, solution count, exact node consumption and both witness matrices, including exhausted budgets, unique/multiple/unsatisfiable and invalid inputs. |
| Generator | **17** cases: 12 deterministic seed mappings and 5 limit/refusal cases. Exact answer, givens, clues, display slots, effort reports, public fingerprint and native CLI document agree for each successful generation. |
| Negative answers | **72** row-swapped permutations from the 12 generated puzzles are rejected by the public verifier. The native answer for every generated puzzle is accepted. |
| Candidate existence | **8** fixtures compare status and budget accounting, including empty masks, invalid masks, givens and exhausted searches. |
| Hint selection | **14** fixtures compare native return code, target, advisory clue and explanation, including relation families, contradiction, singleton selection and display/archive order. |
| Supporting-premise explanation | **19** fixtures compare proof status, node budget/use, reduction checks, retained premise records and the unchanged selected target. |
| Proof replay | **11** fixtures cover valid, exhausted, invalid, refuted and malformed records; replay is checked for read-only behavior. |
| State execution | **11** traces compare **1,116** transitions: candidates, choices, fixed cells, visible and unused clue slots, cell bytes, undo count, outcome, clocks and pending-hint state. |
| Complete games | Hint request/accept traces finish generated seeds **0**, **42** and **18,446,744,073,709,551,615** in both implementations. They include **455** accepted hints; all traces together include **458**. |
| Hidden answers | **74** dedicated verifier/solver/candidate/hint/proof calls receive a throwing `solution` getter. Every state trace also uses a poisoned hidden-answer property. No tested public operation reads it. |

### Unsigned seeds and generation limits

The successful seed set is:

```text
0
1
2
42
235
65535
4294967295
4294967296
9007199254740991
9007199254740992
9223372036854775808
18446744073709551615
```

These vectors straddle the 32-bit boundary and JavaScript's exact-integer boundary, and include the unsigned 64-bit maximum. They compare the version-1 native generation mapping, not merely validity of a generated puzzle. Zero and one-node budgets, zero attempts, out-of-range attempts, and an invalid givens limit also produce matching statuses and reports. Failed generation does not substitute a puzzle.

### State, clocks and hint ordering

Traces cover fixed-cell protection, repeated removals, restoration, choosing an item, invalid coordinates, paused input, clue movement and archiving, insertion into a full clue grid, and eviction at the 25-entry undo limit. Successive undo operations verify that retained snapshots restore the same observable boards; undo does not refund time.

The deferred-timeout trace requests a hint before the deadline, advances time beyond the deadline while it is pending, and accepts it. The observed fee and timeout order agree with C. The final-cell traces distinguish a 59,999-ms win from a 60,000-ms timeout after the 30,000-ms acceptance fee. A separate trace exercises unsigned 64-bit elapsed-clock saturation and quit behavior.

Proof vectors include an inconsistent premise set that must not yield a vacuous deduction, refuted and unforced targets, shared-budget exhaustion, Hall-style row reasoning with no clues, separate given-square background, reduction with a preferred advisory clue, and a live source clue at index 255. The selector is not rerun to replace the target during explanation.

### Deliberately incorrect rule

The negative control replaces `NOT_BETWEEN(a,b,c)` with the plausible but incorrect `!BETWEEN(a,b,c)`. The full predicate table rejects that mutation in **168** of the 216 triples for the relation. The supported native rule requires the outer objects to be exactly two columns apart and the named middle object to be absent from their middle column.

This control shows that the table comparison distinguishes the important rule interpretation. It is not an all-program mutation analysis.

## Asset adapter comparison and defect found

The four private SHI inputs were `SHERLOCK.SHI`, `ORGINAL.SHI`, `BOKSTAVE.SHI` and `KJETIL.SHI`. For each file, all **47,104** decoded palette indices match `shi_load` compiled from `media/shi.c`, and JavaScript re-encoding reproduces all **23,920** input bytes. The report retains only input/decoded SHA-256 values and counts. The palette constants were also reviewed against the retained C source.

The privately supplied original puzzle table was checked at numbers **0, 1, 235, 32767, 32768, 65534 and 65535**. JavaScript import produces the same complete public challenge document and fingerprint as the compiled native CLI for each number. The importer discards the stored hidden solution at the boundary.

One adapter defect was identified during source review: `loadOriginalTable` initially copied a generic `Uint8Array` with `.slice()`. A Node `Buffer` is a `Uint8Array` subclass whose `.slice()` aliases the caller's storage, so later mutation could alter a supposedly admitted table. A view over a Buffer's backing store can also carry an offset that must be respected. The owner replaced this with `new Uint8Array(source)`, giving an owned, zero-offset byte array. The harness now mutates the caller's Buffer after admission and verifies that the imported puzzle stays unchanged. The corrected implementation passed. This defect concerned the Node/shared-adapter input boundary; the ordinary browser `File`/`ArrayBuffer` path did not have the Buffer aliasing behavior.

No original input payload was copied into a source fixture or report. The private adapter checks supplement the synthetic public suite; they are not a full 65,536-puzzle table requalification.

## Reproduction

Requirements for this comparison are Node with BigInt support and a C11 compiler. The recorded run used `Node v24.22.1` and `cc (Ubuntu 13.3.0-6ubuntu2~24.04) 13.3.0`. The browser application itself has no compiler or Node runtime requirement.

From the repository's `replica` directory, run the source-only comparison:

```sh
node web/tests/parity.js --skip-private --report /tmp/sherlock-parity-public.json
```

To add privately held historical inputs:

```sh
node web/tests/parity.js --private-resources /absolute/path/to/Resources --report /tmp/sherlock-parity-private.json
```

The optional folder must contain `sherlock_puzzles.bin` and the four named files under `Images/`. With no explicit flag, the harness checks the adjacent native `Resources` folder if the private table is present. A focused regression can use `--only`, for example `--only proof,replay,trace`; such a run deliberately skips private resources and must be read as a focused receipt.

Each native helper is compiled with `-std=c11 -O2 -Wall -Wextra -Wpedantic -Werror`. The harness exits nonzero for any failed comparison. The counted `assertions` field measures equality comparisons; additional shape, ownership and refusal assertions are enforced as well.

## Remaining qualification boundaries

These vectors are deliberately finite. They do not prove all-input equivalence or validate arbitrary malicious object graphs. They do not cover browser DOM events, layout, local-storage policy, download/import affordances, hosting, ChatGPT Space behavior, macOS builds or timing under suspended tabs. Those belong to the shell and delivery checks.

The native implementation is the reference on this seam. A common defect already present in native C could be reproduced faithfully by JavaScript and pass this review. Claims about the original game's remaining clue-family hint ordering, mistake repair, sound, menus or visual behavior must continue to cite their separate original-evidence ledger. This run provides a reproducible check that browser development can proceed without silently changing the tested native game rules, generator, verifier, state transitions or proof semantics.
