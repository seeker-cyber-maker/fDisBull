# Sherlock native JSON interface

This interface lets an agent obtain a puzzle, solve its public clues, and submit
an answer to the **same native constraint verifier used by the application**.
It also provides a deterministic native generator, bounded uniqueness analysis,
and replayable supporting premises for a fixed hint. The command implementation
uses C and the shared core; it has no
AppKit, Python, DOSBox, Wine, browser, or original-executable dependency.

There are two separate puzzle sources:

| Source | Identity | Resource requirement |
| --- | --- | --- |
| Original Sherlock 1.50 UK | Original number `0` through `65535` | The recovered `sherlock_puzzles.bin` table |
| Native generated puzzle | Generator ID, generator version, full 64-bit seed, public-content fingerprint | None |

The native generator is an authored generator with its own versioned mapping.
Its seed `0` is independent of original puzzle number `0`. Original numbered
puzzles continue to use the recovered table. The command interface never
returns the private solution stored in either source.

## Build and use

From the replica directory:

```sh
./Build-CLI.sh
./bin/sherlock-cli help
./bin/sherlock-cli generate --seed 42 > challenge.json
./bin/sherlock-cli analyze --seed 42
./bin/sherlock-cli verify --seed 42 --solution answer.json
```

`answer.json` is the agent's submitted answer, in the format below. The CLI does
not produce an answer file. To read the answer from standard input:

```sh
./bin/sherlock-cli verify --seed 42 --solution - < answer.json
```

Original numbered puzzles use the same public protocol and verifier:

```sh
./bin/sherlock-cli puzzle --number 235 > challenge.json
./bin/sherlock-cli analyze --number 235
./bin/sherlock-cli verify --number 235 --solution answer.json
./bin/sherlock-cli puzzle --number 65535 --data /path/to/sherlock_puzzles.bin
```

The macOS application also dispatches these commands before starting AppKit:

```sh
"build/Sherlock Native.app/Contents/MacOS/SherlockNative" --cli generate --seed 42
"build/Sherlock Native.app/Contents/MacOS/SherlockNative" --cli puzzle --number 235
```

This document describes the portable CLI contract. The macOS entry path and
executable-location adapter still require execution on a Mac for platform
qualification; portable builds and the Linux entry path have been executed.

## Commands

| Command | Purpose |
| --- | --- |
| `puzzle --number N [--data PATH]` | Export an original numbered public challenge. |
| `generate --seed UINT64` | Construct and export a uniquely proved native challenge. |
| `verify (--number N \| --seed UINT64) --solution PATH\|- [--data PATH]` | Reconstruct the canonical challenge and verify the submitted complete answer. |
| `analyze (--number N \| --seed UINT64) [--max-nodes UINT64] [--data PATH]` | Classify the canonical public constraints as `unique`, `multiple`, `unsat`, or `unknown`. |
| `hint (--number N \| --seed UINT64) [--state PATH\|-] [--max-nodes UINT] [--data PATH]` | Select a native logical hint, then prove its exact target and reduce its supporting clues. |
| `check-hint (--number N \| --seed UINT64) --move PATH\|- [--state PATH\|-] [--max-nodes UINT] [--data PATH]` | Prove or refute a submitted fixed move against canonical clues and explicit candidate assumptions. |
| `help`, `--help`, or no command | Return machine-readable help. |
| `version` or `--version` | Return protocol and native generator version information. |

Flags and their values must be separate arguments. The two source flags are
mutually exclusive. Repeated flags, unknown flags, irrelevant command options,
and trailing arguments are errors. For example, `--data` is accepted only for
original-number commands, and `--max-nodes` is accepted only for `analyze`,
`hint`, and `check-hint`. `--state` belongs to the two hint commands;
`--move` is required by `check-hint` and accepted by no other command.
At most one input document can use `-` for stdin in an invocation.
`<command> --help` is supported as a complete two-argument request.

All numeric flags accept unsigned decimal digits only. Signs, spaces, decimal
points, exponents, base prefixes, suffixes, and overflow are rejected. Leading
zeroes are accepted and canonicalized. The original number range is
`0..65535`; seeds and analysis node budgets span `0..18446744073709551615`.
Hint proof budgets span `0..UINT_MAX` (`0..4294967295` on the supported
Mac/Linux targets); machine-readable help reports `hint_node_maximum`.

Native generation uses fixed default limits in generator version 1: a total
solver-node budget of `1000000`, at most `16` attempts, and at most `3` givens.
The source metadata includes these limits. An exhausted generator returns an
explicit failure; it does not return an unproved puzzle or substitute a
different seed. `analyze` defaults to `200000` nodes. Its `--max-nodes` flag
limits the analysis after canonical challenge construction; it does not alter
the native generation budget or generated puzzle.
The two hint commands default to `20000` proof nodes shared across consistency,
target refutation and support reduction. `hint` first uses a separate fixed
`20000`-node selector allowance; `--max-nodes` does not change that allowance.

## Standard output and exit status

Each invocation writes one UTF-8 JSON document, terminated by a newline, to
standard output. Help, version information, diagnostics, and failures use the
same channel and protocol. There is no ordinary diagnostic chatter on standard
error. An output stream that cannot be written cannot be guaranteed a complete
response.

Every response has `"format":"sherlock-cli-1"`, a `kind`, and an `ok` Boolean.
All 64-bit values, including seeds and node counts, are **decimal JSON strings**
to preserve their full range in JavaScript and other JSON consumers. Board
indices, item IDs, clue indices, versions, and original puzzle numbers are
bounded JSON integers.

| Exit status | Meaning |
| --- | --- |
| `0` | Success, accepted answer, conclusive analysis, a proved hint, or no available hint. |
| `1` | A well-formed answer was rejected, a proposed hint was refuted, or its candidate premises are inconsistent. |
| `2` | Invalid command arguments, input JSON, state, or move target. |
| `3` | Resource, input/output, or engine failure. |
| `4` | Analysis is `unknown`, a hint is `unresolved`, or native generation exhausted its configured budget. |

A rejected answer is an ordinary verification result: `kind` is
`"verification"`, `ok` is `true`, and `accepted` is `false`. Likewise, an
incomplete analysis has `kind:"analysis"`, `ok:true`, and
`classification:"unknown"`. Consumers must inspect the operation result,
not only `ok`. Failures such as malformed input have `kind:"error"`,
`ok:false`, and an `error` object containing `code` and `message`; input parsing
errors also include a zero-based `byte_offset`. Resource errors identify their
selected `path` when available.

## Public challenge format

A puzzle response has this outer structure:

```json
{
  "format": "sherlock-cli-1",
  "kind": "puzzle",
  "ok": true,
  "challenge": {
    "challenge_id": "sherlock-native-constraints:v1:0:cd2d37eb3c339602",
    "source": {
      "kind": "native",
      "generator": "sherlock-native-constraints",
      "generator_version": 1,
      "seed": "0",
      "limits": {"node_budget": "1000000", "max_attempts": 16, "max_givens": 3}
    },
    "public_fingerprint": {"algorithm": "fnv1a64-public-v1", "hex": "cd2d37eb3c339602"},
    "rows": 6,
    "columns": 6,
    "items_per_row": 6
  }
}
```

This excerpt shows identity fields from an executed seed-0 response; it omits
the remaining public fields described below and the native `generation`
metadata. Use the actual command output as the complete challenge document.

The `challenge` object also contains:

- `answer_format`: the row/column layout, item range, and row-permutation rule.
- `object_ids`: the mapping `global object ID = row * 6 + item`, with integer
  division and remainder for the inverse mapping.
- `column_function`: the meaning of `col(object)` in the predicates.
- `clue_predicates`: the complete predicate catalog in the following table.
- `givens`: objects with `row`, `column`, `item`, and the equivalent global
  `object` ID. An absent cell has no entry.
- `clues`: ordered objects with zero-based `index`, a string `type`, global
  object operand `a`, and operands `b` and `c` when required. Each also has a
  nullable `display_slot`.

For an original puzzle, `source` instead contains `kind:"original"`,
`edition:"Sherlock 1.50 UK"`, `table_format:1`, and its integer `number`. It
does not contain a native seed. Original puzzle responses do not contain a
`generation` object. A successful native puzzle response includes
`generation.classification:"unique"`, the integer attempt count, and the
decimal-string node count used during generation.

### Board and clue semantics

All row, column, and within-row item IDs are zero based. The answer entry
`answer[row][column]` identifies the item from that row located in that column.
Every row is a permutation of items `0..5`. Objects from different rows have
different global IDs even when their within-row item numbers are equal. There
is no rule requiring the six numeric entries in a column to be distinct.

Let `col(object)` be the object's column in the submitted answer. The operands
`a`, `b`, and `c` in a clue are **global IDs `0..35`**, not within-row item IDs.

| Type | Operands | Exact predicate |
| --- | --- | --- |
| `same_column` | `a`, `b` | `col(a) == col(b)` |
| `not_same_column` | `a`, `b` | `col(a) != col(b)` |
| `next_to` | `a`, `b` | `abs(col(a) - col(b)) == 1` |
| `not_next_to` | `a`, `b` | `abs(col(a) - col(b)) != 1` |
| `left_of` | `a`, `b` | `col(a) < col(b)`; adjacency is not required. |
| `between` | `a`, `b`, `c` | `abs(col(a) - col(c)) == 2 && 2*col(b) == col(a) + col(c)` |
| `not_between` | `a`, `b`, `c` | `abs(col(a) - col(c)) == 2 && 2*col(b) != col(a) + col(c)` |
| `reference` | `a` | Informational object card; no constraint. |

`between` places `b` immediately between the outer objects `a` and `c`, in
either orientation. **`not_between` still requires the outer objects to be
two columns apart.** It excludes `b` from their middle column. It is therefore
not the logical complement of the entire `between` predicate. These semantics
are shared by the solver, verifier, native generator, and player-state logic.

`display_slot` preserves presentation placement when available: `36..53` are
vertical cards and `54..74` are horizontal cards. `null` means no original slot
is supplied. Placement does not add a logical constraint. A `reference` card
can occur in either group; consumers must not infer its orientation from its
type alone. Clue order and display slots are included in the public fingerprint.

## Answer input and canonical verification

The supported document is either a bare six-by-six array or an object with
exactly one `solution` field containing that array. For example, this is a
**syntax example**, not the answer to a supplied challenge:

```json
{"solution":[
  [0,1,2,3,4,5],
  [0,1,2,3,4,5],
  [0,1,2,3,4,5],
  [0,1,2,3,4,5],
  [0,1,2,3,4,5],
  [0,1,2,3,4,5]
]}
```

The input must contain exactly six rows and six items per row. Each value must
be a single JSON integer digit from `0` through `5`. JSON numbers written as
`1.0`, `1e0`, or `-0` are outside this intentionally narrow input contract.
Strings, booleans, nulls, comments, Markdown fences, duplicate or extra object
keys, trailing commas, a byte-order mark, and trailing documents or other data
are rejected. Standard JSON whitespace is accepted, as are equivalent
`\uXXXX` ASCII escapes in the `solution` key. Input is limited to 65,536 bytes,
including whitespace. Every accepted document is valid JSON; the interface
does not accept every possible JSON value representation.

Verification receives the source number or seed separately on the command
line. It reloads or regenerates that canonical challenge and applies all row,
given, and clue constraints through `sherlock_verify_answer`. It does not
accept client-supplied clues, solutions claimed to be authoritative,
`accepted:true`, or a public challenge document in place of an answer. It does
not compare a submission against the engine's stored private solution.

A verification response includes the canonical `challenge_id`, `source`, and
`public_fingerprint`, together with `accepted`, a human-readable `reason`, and
`violation` indices (`row`, `column`, `clue_index`, each nullable). The reason
and indices explain a violated constraint without returning an expected
answer. An agent should compare the returned identity with the challenge it
intended to answer; this is especially useful when using different binaries
or original table files.

## Analysis

Analysis uses the shared finite-domain solver on public givens and clues. Its
response includes the canonical identity, `classification`, `solutions_found`,
`solution_count_is_exact`, decimal-string `nodes` and `node_budget`, and a
`reason`. It never emits either solver witness answer.

| Classification | Interpretation |
| --- | --- |
| `unique` | Search proves exactly one solution; `solutions_found` is `1`. |
| `multiple` | At least two distinct solutions were found; the count is capped at `2`. |
| `unsat` | Search proves no solution; `solutions_found` is `0`. |
| `unknown` | The budget expired before a conclusive classification; any reported count is a lower bound. |

`solution_count_is_exact` is true only for `unique` and `unsat`. `unknown` does
not imply a contradiction or uniqueness. For example, a zero-node budget is a
supported way to exercise the incomplete-analysis result:

```sh
./bin/sherlock-cli analyze --seed 0 --max-nodes 0
```

The CLI selects canonical original or native sources. It does not accept an
arbitrary client-defined constraint document for analysis. The shared C solver
also supports such in-memory puzzles through its core API.

## Hints and fixed-target verification

Both commands use public clues, givens, row permutations and the stated
candidate masks. They do not read the stored private answer. They are read-only:
no move is applied, no game clock advances, and no hint penalty is charged.
The selector and explanation support are native logical features; their output
does not claim exact original DOS hint order or prose.

```sh
./bin/sherlock-cli hint --seed 42 > hint.json
./bin/sherlock-cli hint --number 235 --state state.json
./bin/sherlock-cli check-hint --seed 42 --state state.json --move move.json
./bin/sherlock-cli check-hint --seed 42 --move - < move.json
```

`hint` selects a target first and then holds that target fixed while checking
and reducing its support. `check-hint` receives the exact target from the caller;
it never substitutes an easier move. Its document has exactly four fields,
in any order:

```json
{"kind":"remove","row":0,"column":1,"item":4}
```

This is a syntax example. The kind is `remove` or `choose`; all three indices
are integers `0..5`. `remove` claims that the specified item cannot occupy that
cell. `choose` claims that it must occupy that cell. The item must currently be
present in that cell's candidate mask. An absent target is invalid input.
An already chosen or given item can be checked as a logical claim; the command
still performs no interaction or mutation.

### Current-state input

Without `--state`, the engine initializes candidates and chosen givens from
the canonical challenge. With `--state`, the input is an object containing a
required `candidates` matrix and an optional `chosen` matrix:

```json
{
  "candidates":[
    [63,63,63,63,63,63],
    [63,63,63,63,63,63],
    [63,63,63,63,63,63],
    [63,63,63,63,63,63],
    [63,63,63,63,63,63],
    [63,63,63,63,63,63]
  ]
}
```

This example shows the matrix shape before imposing any givens. An actual
submission must preserve the canonical given cells. The `state` object returned
by `hint` contains a valid starting snapshot that can be saved and updated.

Each matrix has exactly six rows and six columns. A candidate entry is an
integer `0..63`; bit `item` permits that within-row item at the cell. Thus `63`
permits all six items and `1 << 4` permits only item 4. Zero is accepted as a
contradictory player state, not silently repaired.

`chosen` contains `-1` for an unchosen cell or an item `0..5`. A chosen item
requires exactly its singleton candidate mask. If the matrix is omitted,
only canonical givens are marked chosen; all other cells remain unchosen,
including singletons. Chosen flags affect which interaction the selector
offers, but the proof's logical background consists of the masks, givens and
row rule. Marking a cell chosen does not automatically update other masks.
Canonical given masks and their chosen items cannot be replaced or unset.

These are intentionally narrow JSON inputs. Integer strings, fractions,
exponents, Booleans, `-0`, leading zeroes, malformed dimensions, duplicate or
extra fields, comments, Markdown fences, trailing commas and trailing documents
are rejected. Ordinary JSON whitespace, arbitrary field order and equivalent
ASCII `\uXXXX` escapes in field names and move kinds are accepted. Each input
document is limited to 65,536 bytes, including whitespace.

**Candidate masks are premises, not certified earlier deductions.** A result
proves what follows from those masks and the canonical constraints. It does
not prove that an agent's prior edits followed logically from an earlier state.
Before proving the move, the engine checks that the entire premise set has
at least one completion, so an inconsistent board cannot prove a move by
vacuity. Both commands reload the canonical challenge; neither accepts
caller-supplied clues, givens, private solutions, `accepted` flags, nor a
previous `support_record` as authoritative input.

### Results and supporting-premise records

A response has `kind:"hint"` or `kind:"hint_verification"`, the canonical
identity, and these additional fields:

| Field | Meaning |
| --- | --- |
| `classification` | `proved`, `refuted`, `inconsistent`, `unresolved`, or, for `hint`, `none`. |
| `proved` | True only after consistent premises and an impossible contrary move have both been established. |
| `reason` | A readable explanation of the outcome and any incomplete reduction. |
| `state_origin` | `canonical_initial` or `submitted_assumptions`. |
| `assumptions` | Explicitly labels masks as premises and says earlier edits were not verified. |
| `state` | The complete candidate/chosen snapshot used by this invocation. |
| `proposed_move` | The selected or submitted target, or null when selection yielded no target. Its presence alone does not certify it. |
| `selection` | For `hint`, the native policy, separate selector budget, advisory clue index and explanation. Null for `check-hint`. |
| `proof` | Proof budget, used nodes, deletion checks, `reduction_complete` and qualified minimality; null if no target reached the proof stage. |
| `support_record` | The self-contained supporting premises for a proved move; null for every other classification. |

`refuted` means that a completion exists with the contrary move. `inconsistent`
means the masks and canonical constraints have no completion. `unresolved`
means a required search exhausted its budget before establishing the result;
it is neither a contradiction nor a proof. `none` means the selector found no
new move. Consumers must inspect `classification` or `proved`, not merely `ok`
or the presence of `proposed_move`.

A proved `support_record` has format `sherlock-hint-support-1`, version `1`,
background-rule mask `1` (six row permutations), and the exact `target`.
Its `candidates` matrix freezes **all** candidate assumptions; `givens` is a
six-by-six matrix containing a canonical item or `-1`. Its `clues` array contains
only retained active relations, each with the canonical source `index`, `type`
and global object operands. `source_clue_count` includes all source cards;
`support_count` counts retained active clues. Informational `reference` cards
add no constraint and are omitted. The advisory `selected_clue_index` describes
the selector's provenance; it need not survive support reduction.

The proof first checks consistency, then searches for a completion with the
exact contrary claim: target presence for a removal, target absence for a
choice. Only an impossible contrary claim establishes `proved`. It then tries
to delete supporting clues while preserving that same target. Candidate masks,
givens and row rules stay fixed throughout.

`proof.reduction_complete:true` certifies **deletion-minimal retained clues
relative to that fixed background**: deleting any remaining clue would leave
a counterexample to the move. It does not establish globally fewest clues,
the easiest explanation, a human-readable inference chain, or the original
game's hint method. Deletion attempts visit other clues in source order before
the selector's advisory clue, preserving a direct explanation when sufficient;
the advisory clue is still deleted if redundant. This preference does not
solve the minimum-support problem.

If reduction runs out of nodes after the move was proved, the result stays
`proved` with sufficient retained support, `reduction_complete:false` and
`minimality:"not_certified"`. This is different from exhausting the budget
before consistency or refutation, which yields `unresolved` and no certified
record. A zero-node fixed-target check exercises that boundary:

```sh
./bin/sherlock-cli check-hint --seed 42 --move move.json --max-nodes 0
```

The proof's budget is shared by consistency, refutation and reduction, with
actual usage reported in `proof.nodes_used`. Selector fallback search has its
own fixed budget; its direct propagation work is not counted as search nodes.
Neither budget is a wall-clock deadline, and neither changes canonical native
generation limits.

The portable C API `sh_replay_hint_proof` can independently rerun consistency
and the contrary search from the equivalent `SHHintProof` structure. It does
not trust a saved status or certify saved minimality. Replay verifies the
stated premises; a consumer of an external record must also compare its target,
masks, givens and indexed clues with the intended challenge and current state.
The CLI's `check-hint` avoids an external-premise trust boundary by reconstructing
canonical clues itself and accepting only the target and explicit player masks.

## Identity and reproducibility

Challenge IDs have these exact forms:

```text
sherlock-1.50-uk:<decimal-number>:<16-lowercase-hex-fingerprint>
sherlock-native-constraints:v1:<decimal-uint64-seed>:<16-lowercase-hex-fingerprint>
```

The generator version and default limits are part of the reproducibility
contract. Preserve the reported version when exchanging challenges; this CLI
does not offer a flag that selects an older generator version. The native app
uses the same `sh_cli_format_challenge_id` helper for its copied puzzle identity.

The fingerprint is **FNV-1a 64-bit**, a noncryptographic reproducibility checksum.
It is not authentication, a signature, or a guarantee against deliberately
constructed collisions. Identity never depends on hidden answer bytes,
structure padding, or machine byte order. The `fnv1a64-public-v1` byte stream
is:

1. ASCII `sherlock-public-v1` without a terminating NUL.
2. The two bytes `6, 6`.
3. The 36 row-major given cells, each its item ID or `255` for absent.
4. The ordered clue count as an unsigned 16-bit little-endian value.
5. For each clue, five bytes: numeric type (`0..7` in the predicate-table
   order), `a`, `b` or `255` when unused, `c` or `255` when unused, and display
   slot or `255` when absent.

Start with `14695981039346656037`. For each byte, XOR it into the hash, then
multiply by `1099511628211` modulo `2^64`. Format the result as sixteen
lowercase hexadecimal digits. Source identity is carried separately by the
ID prefix, original number or native seed/version, and source metadata.

## Original table discovery

Only original-number commands need the recovered table. Precedence is:

1. Explicit `--data PATH`.
2. A nonempty `SHERLOCK_PUZZLE_TABLE` environment variable.
3. The embedding application's resource directory, or the standalone
   executable's `../Resources/sherlock_puzzles.bin`.
4. Only when the entry point could not supply a resource directory: the
   working-directory paths `Resources/sherlock_puzzles.bin`,
   `core/sherlock_puzzles.bin`, then `sherlock_puzzles.bin`.

An explicitly selected path, environment override, or known resource directory
that fails to load returns an error. It does not silently choose another table.
The native generator does not inspect these resources and still works when a
configured original-table path is missing.

The standard installed layout is:

```text
bin/sherlock-cli
Resources/sherlock_puzzles.bin
```

An agent using a copied standalone executable can supply `--data` or the
environment variable instead of reproducing that layout.

## Embedding API and verification

`sherlock_cli.h` exports:

```c
int sh_cli_main(int argc, char **argv, const char *resource_directory);
int sh_cli_format_challenge_id(const SherlockPuzzle *puzzle,
                              int native_generator, uint64_t seed,
                              char *output, size_t capacity);
```

`sh_cli_main` takes normal main-style arguments, including an executable or
dispatch name at `argv[0]`. It does not modify arguments or call `exit`; it
returns the exit-status contract above and writes its response to standard
output. A supplied resource directory contains `sherlock_puzzles.bin`.
`native_generator` for the formatter is exactly `0` for an original puzzle or
`1` for the current native generator. The formatter returns `0` on success,
`-1` on invalid public fields/arguments or insufficient space, and leaves the
output buffer unchanged on failure. It only formats a public identity; it
does not prove that a caller-provided puzzle is canonical.

Production entry sources are `main.c` (executable-location adapter),
`sherlock_cli.c` (portable command implementation), and `sherlock_cli.h`.
The CLI also links the core, `state/sherlock_state.c` and
`state/sherlock_hint_proof.c`. The app links these shared implementations
and supplies its bundle resource directory directly.

The black-box contract tests accept a compiled binary and an optional original
table:

```sh
python3 tests/test_cli.py bin/sherlock-cli
python3 tests/test_cli.py bin/sherlock-cli Resources/sherlock_puzzles.bin
```

Python is used only by this test harness. Its independent finite-domain consumer
solves public JSON for seeds `0`, `1`, `4294967296`, and
`18446744073709551615`; the tests submit those answers and reject wrong row
swaps. Optional original cases include `0`, `235`, `11656`, and `65535`.
The harness also checks deterministic output, public fingerprints, full-width
identities, no hidden answer fields, strict parser failures, inclusive input
size limits, error exits, incomplete analysis, and resource discovery. The hint
checks independently reconstruct support from public JSON, verify consistent
premises and impossible contrary moves, and check each retained clue when a
completed deletion pass claims minimality. They cover canonical givens and
chosen/mask coherence, malformed state/move documents, counterexamples,
inconsistent premises, zero budgets, and proved support with incomplete reduction.

At the hint-slice handoff, the strict C11 build (`-Wall -Wextra -Wpedantic
-Werror`) and all **208 invocations with the original table** passed on Linux.
All **194 invocations without an original table** also passed with AddressSanitizer
and UndefinedBehaviorSanitizer, with leak detection disabled. The earlier
independent identity-helper review exercised hidden-answer poisoning of the shared
identity helper, unchanged output on formatter failure, and malformed UTF-8
diagnostics. Core solver/generator correctness and original corpus qualification
have separate core tests and evidence; these CLI checks establish the public
interface contract rather than replacing that evidence.
