# Authored block-composition sweding experiment

This is a small, reproducible experiment, not a production compiler or an
untrusted-submission executor. Three fresh workers author C realizations from
the same common-UIL contract, using the same ABI, compiler recipe and tool.
The existing common-UIL interpreter and registry example are dependencies.

## Program and bounded domains

Collect coins, award points, then update a score:

| Block | Input ports | Output ports | Required behavior |
|---|---|---|---|
| normalize | raw: i16, -8 through 8 | count: u16 | Clamp raw to 0 through 3. |
| award | count: u16, 0 through 3 | points: u16 | Two points per coin, plus one bonus point when count equals 3. |
| apply | score: u16, 0 through 10; points: u16, 0 through 7 | next_score: u16; won: bool | Add points, cap at 10, and win exactly when the resulting score equals 10. |

The connection is `raw -> normalize -> count -> award -> points`, followed by
`apply(score, points)`. `score` is a separate input, not the normalized count.
Inputs are by value. The only state is explicitly passed through ports; these
blocks have no external effects or hidden mutable state.

Examples of a complete turn:

| raw | score | count | points | next_score | won |
|---:|---:|---:|---:|---:|---|
| -2 | 5 | 0 | 0 | 5 | false |
| 2 | 5 | 2 | 4 | 9 | false |
| 4 | 5 | 3 | 7 | 10 | true |

The domains are part of this experiment's qualification claim. No result
establishes behavior over the full i16/u16 domains. Integer operations in the
model use their explicit widths; the bounded additions here cannot overflow.
The common-UIL `select` operator evaluates both arms. These arms are pure and
total on the declared domains.

## Choose the assigned mode

| Mode | Files you author | Required exported functions |
|---|---|---|
| singles | normalize.c, award.c, apply.c | Each file defines its corresponding function only. |
| pair | pair.c | normalize, award, pair; pair calls normalize and then award. |
| triple | turn.c | normalize, award, apply, turn; turn calls the three blocks in order. |

Include the supplied `abi.h`. It declares all C types and function signatures.
Do not write a main function or transport/parser. The fixed `scaffold.c` supplies
them. Do not add libraries, files, hidden mutable state, allocation, host calls
or I/O to the block bodies. Read only the common packet and your own work
directory during the trial, not another worker's candidate. Author an original
implementation; do not copy a coordinator reference implementation.

For singles, each block is a separate replacement. The checker tests them
individually and substitutes each into the rest of the model, then checks their
joint substitution. For pair and triple, preserve the individual functions and
call them from the composition entry. This exposes the connections for review.

## Interface and workflow

From a checkout with fDisBull's Python dependencies available:

```sh
PYTHONPATH=src python examples/swede_trial/trial.py --help
PYTHONPATH=src python examples/swede_trial/trial.py --mode pair --work /private/trial/pair doctor
PYTHONPATH=src python examples/swede_trial/trial.py --mode pair --work /private/trial/pair describe
PYTHONPATH=src python examples/swede_trial/trial.py --mode pair --work /private/trial/pair task
```

Use your assigned mode and a fresh private work directory outside Git. An
experiment coordinator may supply the exact Python command for its environment.
`doctor` checks an already installed GCC on Linux x86_64; it installs nothing.
`describe` prints the actual Program/Presentation contracts, slot types,
domains and semantics. `task` records a work packet using the existing registry
API. Read the packet path returned by the tool before writing code.

The seeded registry already knows the common-UIL model. It does not infer a
global absence of implementations. This trial explicitly requests a new C
realization while retaining known model alternatives.

Write the source files in your assigned work directory, then run:

```sh
PYTHONPATH=src python examples/swede_trial/trial.py --mode pair --work /private/trial/pair check
PYTHONPATH=src python examples/swede_trial/trial.py --mode pair --work /private/trial/pair register
PYTHONPATH=src python examples/swede_trial/trial.py --mode pair --work /private/trial/pair lookup
```

`check` takes a source snapshot, compiles it with the supplied header and
transport, and compares every declared-domain input against the existing UIL
interpreter. It repeats cases in reverse order in the same native process.
It checks intermediate values and substitution into the full turn. The build
and check receipts identify sources, framework, compiler and output artifact.
Attempt snapshots and failures remain in `trial-results/`.

Compile recipe: GCC, C11, `-O2 -Wall -Wextra -Werror -pedantic`. No speed
measurement is made. Compiler errors and behavioral counterexamples are
returned with a next action. A failed check is not a successful qualification;
repair only your source and check again, or report a tooling blocker.

`register` requires a current successful local check. It associates declared
C backings with exact model identities and a module/provider declaration.
This does not lift arbitrary C into UIL or prove source correspondence.
`lookup` opens the SQLite registry afresh. The expected registry next action
after registration is `review-evidence`, because the registry stores receipt
references without verifying them or granting execution authority. The trial
runner's user-authorized compile/check is separate from that planning index.

Only the three closed block models are catalogued. Pair/turn composition uses
actual common-UIL call graphs; it is not assigned a fabricated closed-function
semantic identity. A module can own multiple block realizations. Its source
manifest identity binds the participating source files.

## Completion and reporting

Return `REPORT.md` in your work directory with: files and functions authored,
commands and outcome, any misunderstandings or tool friction, clarification
requests or assistance received, check receipt path, registration/readback
result, and the limits of what was established. Be explicit if blocked.
Do not edit the contracts, tool, header, scaffold or other workers' files.
Do not publish or spawn additional workers. The coordinator owns integration.

Conversation context is fresh when the host launches a worker without parent
history. The filesystem reading boundary here is an instruction, not an
operating-system sandbox. Each worker has an independent directory and registry.
One worker per mode is an exploratory observation, not statistical evidence
about which mode is easier or which model is better.

## Reproduction and maintenance

Run `python -m pytest -q examples/swede_trial/test_trial.py` after making a
relevant change. The coordinator qualifies the UIL reference against a separate
small arithmetic oracle and tests deliberately wrong implementations before
dispatch. Test machinery does not manufacture per-target evidence for any
compiler or operating system that was not actually exercised.

All fixtures are newly authored arithmetic examples. Do not commit the private
SQLite databases, compiled executables, attempt logs or runtime receipts. Commit
reviewed authored sources; retain sanitized experiment reports separately.
