# Colonization: paired production and difficulty models

These examples import the authored models, tests and replay tools from the
2026-11-02 research deliveries. They use `fdisbull-common-uil-1`; they are bounded
semantic recoveries, not automatic decompilation or a complete game port.

## Scope and edition identities

`paired/` contains seven functions per edition: input balance, net production,
capacity, stock availability, packed field access, the production-input pipeline,
and their comparison entry. The five helper contracts agree in the admitted
domains. The DOS and Windows production-input callers differ at building count 3.
For supply 0, stock 0 and production 9, DOS produces net 0 and Windows net 3.
Preserve this difference; equivalence must not normalize an observed rule away.

`difficulty/` retains those seven definitions and adds morale, center food,
selected secondary bonus, manufacturing-worker output, and a composition entry.
Difficulty is explicitly 0..4. Tory divisors are 10, 9, 8, 7, 6; center-food
bonuses are 2, 1, 0, 0, 0. Status flags are separate inputs. The selected worker
profile admits rates 1..3, modifiers -5..2 and building counts 1..3. Building,
expert and clamp operations retain their recovered order.

The source identities are:

- DOS `VICEROY.EXE`: `a17ed64c27671e5e95236e54a7ddc85803a96ba822fbed05e1dad34d3917e2e3`.
- Win16 `COLONIZE.EXE`: `ae7d9149f056766a534fe8f0006c9512aac1e1004e9776ab3cca818e4833b650`.

`representations/*/source-bindings.json` retains exact file ranges, source hashes
and relocation observations. These metadata do not contain original code bytes.
`labels.json` supplies explanatory names; executable identities remain numeric.
Difficulty's `previous/tools` copies are retained to keep the supplied extension
standalone and its seven-function prefix auditable.

## Run the authored regressions

From the repository root, with its development dependencies installed:

```sh
python -m pytest -q examples/colonization_production/paired/tests examples/colonization_production/difficulty/tests
python examples/colonization_production/paired/tools/run_operation.py --edition dos --operation production_input_pipeline --inputs '[0,0,9,3]'
python examples/colonization_production/paired/tools/run_operation.py --edition win --operation production_input_pipeline --inputs '[0,0,9,3]'
```

These tests exercise the current interpreter and persisted models. They do not
execute original instructions. The original delivered tests comprise 19 paired
and 24 difficulty regressions; two additional output-boundary cases protect
repository hygiene without requiring game inputs.

## Reproduce or inspect original observations

The [paired delivery](https://chatgpt.com/library?file_id=libfile_a08d2cd6efcc8191a6a38b14e8e2f000&account_id=personal)
and [difficulty delivery](https://chatgpt.com/library?file_id=libfile_3ab52c4a6f8481919907fc4df3e10927&account_id=personal)
retain reports, historical receipts and controlled numeric observation streams.
These are separately supplied evidence; they are not copied into this source
change. The reported original-instruction comparisons contain 2,822 cases per
edition for the paired study and 22,515 per edition for the difficulty study.
Those numbers describe the deliveries, not a fresh native run during import.

The paired replay driver requires the exact user-owned executables, the pinned
fDisBull 0.30.0 installation, a separately prepared DOSBox backend, binutils,
Node, GCC, Capstone and Z3. It copies inputs into a new private workspace and
refuses an existing output or a path inside a Git checkout:

```sh
python examples/colonization_production/paired/tools/replay.py --dos /private/inputs/VICEROY.EXE --windows /private/inputs/COLONIZE.EXE --backend /private/bin/dosbox-wrapper --output /private/paired-replay
```

For difficulty, supply the exact originals in a private directory and a new
private output; `tools/difficulty_native.py --help` gives its explicit arguments.
The resulting assembly/object/COM files retain original instruction bytes and
must stay private. Direct native builders also reject outputs in Git checkouts.
Model generation, comparison and proof scripts retain the delivery workspace
layout; run them from a copied study in a private scratch directory. The paired
replay driver constructs that layout automatically.

`difficulty/tools/check_difficulty.py` can compare the retained numeric corpus
without running an original game. `check_difficulty_uil.py` additionally exercises
the interpreter and generated Linux x64 model with an explicit output directory.
Generated host programs implement the authored contracts; they are not Windows
or DOS guest executables. The SMT queries concern authored bit-vector models,
not a formal proof of the original x86 transition system.

## Limits preserved from the research

The Win16 source cuts ran in an isolated x86-16 harness with declared selector
and call adapters. No Windows 3.1 process, complete colony turn, warehouse update,
natural game reachability, or whole-game equivalence is established here. The
upstream producers of rebel percentage and status flags remain outside the
difficulty contract. No original executable, game asset, save or emulator state
is included in this example.
