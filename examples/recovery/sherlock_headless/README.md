# Python headless puzzle benchmark

A runnable, dependency-free Python implementation of the documented Sherlock 7
relational puzzle rules, with candidate play, an exact solver, deterministic
generation, a JSON agent protocol, and a batch answer evaluator.

It runs directly under **Python 3.10+**, including a normal Python installation
on macOS. No game installation, artwork, compiler, DOSBox, Wine, fDisBull runtime,
or third-party solver is required. Runtime qualification in this contribution
is on Linux; a macOS execution check remains separate.

This is an **authored rules implementation**. The current evidence establishes
the mathematical contract and its implementation, not a recovered Sherlock 7
executable, original puzzle-number mapping, or Type A/B difficulty equivalence.
[RULES.md](RULES.md) defines every relation and [RESEARCH.md](RESEARCH.md) records
the documentary sources and relationship to the earlier C/browser replica.

## Run it now

From this directory:

```sh
python3 -m sherlock_benchmark version
python3 -m sherlock_benchmark rules
python3 -m sherlock_benchmark generate --seed 42 --rows 6 --columns 6 > puzzle.json
python3 -m sherlock_benchmark solve --puzzle puzzle.json --submission > answer.json
python3 -m sherlock_benchmark verify --puzzle puzzle.json --submission answer.json
```

The first command records the engine version, ruleset, solver/generator
versions, interpreter, platform, and SHA-256 of the actual package's Python
source files. `solve` above is the included reference baseline. An agent can
replace that command with its own reasoning and produce the same answer format.

Optional installation creates the shorter `sherlock-bench` command:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/sherlock-bench version
```

Running the module directly needs no installation and works offline. Installing
from source may need setuptools from your configured package source; an already
built wheel can be installed with `pip install --no-index /path/to/the.whl`.

## What an agent receives and returns

The public puzzle contains only format/rules identifiers, board dimensions,
givens, clues, and its content hash. It does **not** contain the generator seed,
RNG state, witness answer, or generation diagnostics. [AGENT_PROMPT.md](AGENT_PROMPT.md)
is a self-contained task instruction you can send with a public puzzle.

All indices are zero based. An object is `row * columns + item`.
`board[row][column]` contains the item ID within that row. Each row must be a
permutation of `0..columns-1`; columns have no cross-category uniqueness rule.

A submission is exactly this envelope (board shown is a syntax example):

```json
{
  "format": "sherlock-benchmark-submission-1",
  "challenge_id": "sha256:<copy the ID from the supplied puzzle>",
  "board": [[0,1,2],[2,0,1],[1,2,0]]
}
```

The verifier checks row permutations, every given, and every clue directly. It
does not invoke the solver or compare against a private answer. Consequently,
any satisfying answer to an ambiguous imported puzzle is accepted. This is
useful when testing deliberately underconstrained instances.

Puzzle IDs are SHA-256 over sorted-key, compact ASCII JSON of the public
document, excluding `challenge_id` itself. Rules/schema versions and clue order
are included. Loading recomputes the ID. Submissions cannot replace the trusted
puzzle, its rules, or its givens. This binding is a content check, not
authentication against someone who can replace the evaluator's corpus too.

## Generate and evaluate a corpus

```sh
python3 -m sherlock_benchmark corpus --seed 1000 --count 20 \
  --rows 6 --columns 6 --output run-001
python3 -m sherlock_benchmark baseline --corpus run-001/public.jsonl \
  --report baseline.json > submissions.jsonl
python3 -m sherlock_benchmark evaluate --corpus run-001/public.jsonl \
  --submissions submissions.jsonl > scores.json
```

`run-001` must be a new directory. It contains:

| File | Audience and content |
| --- | --- |
| `public.jsonl` | Agent input: one public puzzle per line. |
| `private-manifest.json` | Organizer only: seeds, generation settings, witness answers, uniqueness receipts, and runtime identity. |

The command uses successive unsigned 64-bit seeds, starting at `--seed`.
Exact duplicate public instances cause failure. Different seeds do not prove
that puzzles are distinct under item/category renaming or geometric symmetry.
The corpus identity hashes its sorted challenge IDs and is independent of line
order. A corpus supports up to 1,000 puzzles and 32 MiB of JSONL input.

The source delivery also includes a 12-puzzle development corpus at
`examples/dev-public.jsonl`, covering square and rectangular boards, and a
single small task at `examples/task.json`. These are public development
examples, not a held-out test set. For a quick check:

```sh
python3 -m sherlock_benchmark baseline --corpus examples/dev-public.jsonl > answers.jsonl
python3 -m sherlock_benchmark evaluate --corpus examples/dev-public.jsonl --submissions answers.jsonl
```

The evaluator never launches candidate programs. Supply the agent's recorded
JSONL answers; each line must be a submission envelope. Missing answers count
as failures. Multiple answers naming the same challenge fail that challenge,
even if one is correct. Unknown IDs and malformed records are reported
explicitly. Invalid JSON records are counted as malformed and cannot reduce
the denominator. Candidate-provided scores, timings, or claims are not used.

The score report includes **solved-at-one**, status counts, per-puzzle results,
groups by board dimensions, corpus identity, and engine/runtime identity.
`baseline --report` also measures solver wall time and search nodes locally.
These are reference-solver measurements, not agent token costs or calibrated
human difficulty. A host harness must enforce agent wall-time/token limits and
record model/version/tool access separately. Missing timed-out answers are
already scored as failures; the evaluator does not infer their cause.

For a reasoning-only track, give the agent the public puzzle and instructions
in an isolated environment that cannot read the private manifest or run this
package's solver. For a tool-using track, explicitly allow tools and record the
policy. Merely hiding a seed field is not a process isolation boundary. Generate
held-out evaluation instances separately from published development examples.

## Solver and generation guarantees

Both dimensions independently support 3 through 8. The solver uses position
bitmasks, exact row matching, clue tuple support, and complete deterministic
depth-first search. It retains at most two solutions:

| Result | Meaning |
| --- | --- |
| `unsat` | Exhaustive search found no completion. |
| `unique` | Exhaustive search found exactly one completion. |
| `multiple` | At least two completions were found. |
| `unknown` | The node budget stopped search before classification. Zero or one valid witness may be retained. |

Every visited search state costs one node. Budget zero always produces
`unknown`, including a trivial complete puzzle. Nodes bound search work rather
than seconds; node cost varies with board dimensions and clue count.
`analyze --puzzle puzzle.json --max-nodes 100000` reports classification without
returning an answer. `solve --submission` can return a valid witness even when
uniqueness is unknown; obtaining one answer is a different task from proving
there is only one.

The generator shuffles a private target with a versioned SplitMix64 sequence,
adds true clues that exclude alternative completions, then attempts to remove
redundant clues. It removes a clue only when uniqueness remains proved. A final
unique check and direct witness verification gate every returned puzzle.
Generation failure returns an error, never an unproved candidate.

Defaults are 100,000 total solver nodes, 256 maximum clues, and pruning enabled.
Each individual generation check has a fixed 2,000-node slice. The total budget
is shared across construction, pruning, and the final check. An inconclusive
pruning check retains its clue. `--no-prune` skips clue reduction. The maximum
admitted budget is 10,000,000 nodes; the public model permits up to 512 clues.

Reproducibility depends on seed, generator version, dimensions, and **all**
generation settings. The manifest records them. This distribution is not
uniform over all puzzles and has no original-game seed or puzzle-number
mapping. Unique does not mean Type A, Type B, or a named difficulty level.

## Interactive headless game

```sh
python3 -m sherlock_benchmark serve --puzzle puzzle.json
```

Write one JSON request per line; receive exactly one JSON reply per request.
There is no unsolicited startup response. Successful replies contain
`{"ok":true,"result":...}`; invalid requests return `ok:false` and leave the
state unchanged. The session continues after ordinary invalid requests.

```json
{"op":"observe"}
{"op":"eliminate","row":0,"column":0,"item":2}
{"op":"place","row":1,"column":3,"item":0}
{"op":"undo"}
{"op":"redo"}
{"op":"checkpoint"}
```

Observations contain the public puzzle, remaining candidates by cell, a
complete board when present, win state, What-If status, action count, and undo
depth. Housekeeping removes other occurrences of a known item and commits the
last candidate in a cell. It uses row assignment rules only, so a wrong
deduction can survive until final verification. Contradictions caught by that
housekeeping reject the move atomically. There are no hidden-answer hints.

What-If operations are `what_if_enter` (with row/column/item), `what_if_exit`,
`what_if_keep`, `what_if_fail`, and `what_if_next`. Nesting is refused. Exit
restores the earlier state; Keep retains current choices; Fail restores then
removes the assumption; Next restores then cycles candidates in the same cell.
Fail is the player's assertion, not an engine-certified contradiction. A
completed What-If board wins only after Keep. `submit_state` verifies the
current complete board outside What-If. `submit` takes a `submission` envelope
and verifies that full answer independently of candidate history.

Save the **result object** from `checkpoint` and pass it to
`serve --puzzle puzzle.json --state checkpoint.json` to resume in a new process.
Checkpoints preserve up to 256 undo/redo frames and the active What-If snapshot.
They are bound to the puzzle ID and validated on load. They represent player
assumptions, not evidence that every deduction was sound. `reset` restores the
initial candidates and is itself undoable. The action counter is capped at the
largest exactly representable JSON/JavaScript integer; operations that would
overflow are refused before mutation.

## Python API

```python
from sherlock_benchmark.generator import generate
from sherlock_benchmark.model import Puzzle, make_submission, verify
from sherlock_benchmark.solver import solve
from sherlock_benchmark.evaluation import evaluate
from sherlock_benchmark.session import Session

generated = generate(42, rows=6, columns=6)
public = generated.puzzle.to_dict()
puzzle = Puzzle.from_dict(public)
result = solve(puzzle, max_nodes=100_000)
assert result.status == "unique"
answer = make_submission(puzzle, result.solutions[0])
assert verify(puzzle, answer)["accepted"]
scores = evaluate([puzzle], [answer])
state = Session(puzzle).observe()
# generated.manifest contains organizer-only seed and witness information.
```

External JSON should use `model.loads_json`, which rejects duplicate keys,
non-finite numbers including exponent overflow, invalid UTF-8, and oversized
documents. Boolean values are refused where indices or dimensions are required.

## Exit codes and tests

| Exit code | Meaning |
| --- | --- |
| 0 | Command completed; for `verify`, answer accepted. An evaluation report may have any score. |
| 1 | Answer rejected, or a requested solution has no satisfying witness. |
| 2 | Invalid arguments, document, or file operation. |
| 4 | Search unknown, generation budget exhausted, or baseline did not answer every puzzle. |
| 130 | Interrupted by the operator. |

Normal results and errors are JSON on stdout. `--help` is conventional human
help. Baseline emits JSONL. New manifest/report files are created exclusively;
existing files are not overwritten. Shell redirection remains the shell's
responsibility.

Run the complete package tests without installing test dependencies:

```sh
python3 -m unittest discover -s tests -v
```

The independent oracle enumerates all 216 complete 3×3 row-permutation boards
and evaluates separate mathematical predicates. Tests cover all nine clue
forms, mixed constraints, independent tiny-puzzle uniqueness, budget cutoffs,
JSON/identity boundaries, batch accounting, CLI flows, candidate transactions,
What-If, and checkpoint restart. Tests are included in the source delivery;
the installed wheel contains only runtime code and metadata.
