# Syndicate LE continuation delivery

Start with **[REPORT.md](REPORT.md)**. Numerical results and the 75-site catalogue
are in **[verification.json](verification.json)**. This delivery has no original
executable, asset, story, memory image, byte-retaining database or raw disassembly.

## Contents

- `REPORT.md`: results, partial runtime structures, name-triggered behavior,
  startup/finalization, verification, limits and next questions.
- `verification.json`: identity, counts, integrity and conditional table catalogue.
- `semantic-findings.json`: explicitly scoped record and trigger/effect facts.
- `startup-records.json`: metadata-only initialization/finalization table records.
- `boolean-binding-verification.json`: four structural binding checks.
- `switch-model-tests-final.json`: ten authored model-check results.
- `replay-resume-verification.json`: retained interrupted replay and successful
  continuation, including exact equality of all 62,837 instruction rows.
- `replay-plan.json`: source-free candidate seeds in the actual discovery stages.
- `switch_guard.py`, `test_switch_guard.py`, `inspect_switch_bounds.py`: narrow
  local guard model, authored checks and read-only schema-8 project survey.
- `replay_candidates.py`: replay on a new private checkpoint copy; pinned to
  fDisBull 0.26.0. It never writes a regenerated original executable.
- `MANIFEST.json`: SHA-256 and size for each included document/tool/receipt.

## Check the authored guard models

Use a separate environment with `capstone==5.0.9` and `z3-solver==5.3.2.0`, the
versions used in this investigation. The supplied offline fDisBull kit contains
these dependencies. Then, from this directory:

```sh
python test_switch_guard.py
```

The ten checks are small authored cases, not shipped-game acceptance tests.

## Read a private project

```sh
python inspect_switch_bounds.py /private/syndicate-le.fdb /private/bounds.json
```

This reader supports schema-8, x86-32, version-1 projects. It reads existing
instruction records without decoding missing roots or changing the database.
Its result establishes a conditional index bound, not table integrity or
whole-program reachability. Do not apply it blindly to newer external-object
schemas or unsupported architectures.

## Replay the researched candidate set

Use the original 22,910-instruction `syndicate-le.fdb` from the retained private
scope package, and the pinned fDisBull 0.26.0 environment:

```sh
python replay_candidates.py \
  /private/baseline/syndicate-le.fdb \
  /private/new/syndicate-replayed.fdb \
  > /private/replay-result.json
```

The destination must not exist, must be outside Git, and its parent directory
must already exist. Container and mapped-image identities are checked. This
is replay of known findings, not a blind or independent recovery experiment.

The script uses the research-pinned private candidate-queue seam and a bounded
100,000-attempt budget. Its ordinary function-seeding calls reproduce the first
17 explicit seeds, including 12 case labels; do not interpret the resulting
candidate function count as recovered original function boundaries.

The tested invocation was interrupted by a host command time limit after
56,567 instructions. The database retained the last 14 queued roots. A fresh
process used `Project(path).analyze(max_instructions=15000)` to finish that queue
and reproduce every instruction row. The stdout result is written only after
completion; an interrupted stdout file may be empty. Inspect the saved queue
before repeating input or recreating a project. See the replay receipt rather
than treating the interrupted invocation as an uninterrupted pass.

All input/output FDBs and original-byte dependencies remain private. Only this
sanitized delivery is intended for sharing. No GitHub PR, merge, release,
system installation or original-game execution is part of this continuation.
