# 0.25.0 integration verification

This record distinguishes the combined source from earlier PR evidence.
Game/story files, native checkpoints, generated story-retaining packages,
private replay directories and project databases stay outside Git. Only
sanitized summaries and authored tests belong in the repository.

## Required gates

Before main is updated, the final integration SHA must pass ordinary Linux CI
and the complete required-native Linux workflow. The latter includes both
DOSBox profiles, installed offline-kit checks and the unified Wine/QEMU,
DOS-in-QEMU and boot-context acceptance job. Earlier green PR heads are intake
evidence, not a substitute for these combined-source checks.

The final reviewed intake is #20 `0ca7c72`, #21 `d4dd455`, #22 `27f66db`,
#23 `0778ea4`, #24 `14617b7`, #25 `5224d7c`, #26 `381fb93` and #27 `63058fe`.
All retain their ancestry in the integration branch. PR #20's original link
gate failed; its duplicate links are reconciled locally and require the fresh
combined gate. New draft #28 is outside this intake. Tagging, GitHub publication
and replacing the system installation are separate actions.

## Fresh local checks

Two immutable source exports separate verification stages:

- `db337d21f10a2c75c1e65d26ddd954cddc384e4c` contains the core integration and
  the Zork/batch safety fixes. Its export was checked against all 1,672 tracked
  blobs with zero missing or mismatched files.
- `c92047a32f76b9a4a8c45cad96d12be844661d99` additionally includes #26's
  returned-effect journaling/checkpoint receipts and #27's guide-writing skill.
  The Zork producer/consumer and legacy tests remain byte-identical across
  these stages. DinoPark's production delta is checkpoint event/receipt
  recording; the final-source live checkpoint trial exercises that boundary.

The runtime is genuine CPython 3.13.17 on macOS arm64, with read-only genuine
dependencies from the verified 0.24 installation. Imported candidate modules
come from the frozen source exports, not the installed 0.24 code. The tested
Mac DOSBox executable has SHA-256
`1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`.

| Check | Result and scope |
| --- | --- |
| Final-intake affected suites | 261 passed: distribution, offline-kit contracts, skill discovery/gates, output, GOG, LE, batches, DinoPark continuation and Zork fault runtime. Independent review also ran 130 overlapping affected checks; these counts are not added together. |
| Full Mac suite at the first frozen stage | 1,936 passed, 20 skipped, 2 failed, 23 setup errors. The 25 unsuccessful cases are existing ELF/compiler fixtures using the Apple toolchain: Mach-O output or unsupported GNU linker flags. This run is explicitly not green. Linux CI remains required. |
| Preserved Zork path | Previous converter, Word16 consumer and three legacy test files are byte-identical to #24. |
| Authored ASM/C benchmark | Two register-boundary cases remain equivalent under their assumptions and altered candidates produce counterexamples. It does not measure native scene recovery or agent comprehension. |
| Skills | Both skill front-matter validators and source gates passed. Installed-wheel gates are recorded separately in the package receipt. |

The [test summary](evidence/integration-025/tests.json) retains unsuccessful test
identities and scope. Native checks below use private user-owned inputs; no
story resources, native states, raw journals or databases are committed.

## Zork

The qualified R88 story and original DOS interpreter are hash-bound in the
[sanitized receipt](evidence/integration-025/zork.json). A pinned independent
Frotz reference passed 10 cases, 30 commands and 40 matching boundaries.
Retained IR and mixed intent execution matched full snapshots, ordered effects
and results; reference text, score and moves matched. Body traps established
that the admitted semantic path executed. Fresh isolated-process checkpoint
continuation matched its remaining result and complete final snapshot.

Six selected natural-fault, CLI, receipt-delivery, preflight and checkpoint
tests passed. An output-budget failure preserves prior effects, reports
interrupted completion as unknown and keeps the last successful checkpoint.
There is no rollback, fallback execution or retry after the fault.

In an independent original-DOS session, first and repeated mailbox text matched
after removing the mixed player's trailing prompt and folding whitespace.
Same-session and warm fresh-session native restore reproduced the response.
This does not compare RAM, input PC, RNG or cold restore. The verifier case
named `full_route` deliberately used two commands, not a winning walkthrough.

## DinoPark

The [sanitized native receipt](evidence/integration-025/dinopark.json) separates
four runs and their inputs:

1. A fresh opening completed all 25 responses as successful actions or reads.
   It read the Vegasaurus catalogue, bought one Coelophysis for the observed
   $1,250, verified one dinosaur/pen, bought the fence and feeders, hired a
   guide, opened the park, advanced time and completed native save/load/status.
2. A C10 continuation completed journaled native save/load. Its later catalogue
   read encountered a recognized `parking_hint` modal during panning and
   returned incomplete/unknown. Purchase input was withheld and no retry or
   subsequent action was sent in that guest.
3. A new C10 copy took a separate street-to-park route successfully. No notice
   appeared, so acknowledgement was not exercised. Entry advanced game time;
   the route does not independently establish open/closed park state.
4. On the final frozen source, a qualified office live checkpoint saved, one
   street action ran, and recovery returned to office. Both saved-range maps
   contained 20 fields and matched before presentation preparation. Preparing
   a completed frame used 100 guest milliseconds; no following input was sent.
   The rewound batch step stayed pending and was not replayed.

All private 192-file copies and original C10 save/resource bundles remained
unchanged; owned processes exited cleanly. Live recovery is not a durable
native park save, deterministic replay or full runtime-state equality. Notice
acknowledgement remains unqualified for these inputs. The blocked catalogue
case is preserved as a limitation, not converted into a successful route.

## Packages and agents

The [package gate receipt](evidence/integration-025/packages.json) records the
built core/player wheels, source archive guards, source-to-wheel byte checks
and installed selective skill reads. Generic distributions exclude games,
saves, emulator states, databases, native executables and private retaining
outputs. Source archives include only the explicitly selected safe JSON
summaries. Ordinary CI validates both skills from the installed wheel; native
offline-kit CI repeats those checks with genuine dependencies and Z3.

## Contract under test

- Keep the previous Zork converter, Word16 consumer and legacy tests intact.
  Recover only the qualified semantic slice and retain unhandled IR explicitly.
- On an execution fault, preserve actual effects, report completed calls and
  interrupted-effect uncertainty, keep the prior successful checkpoint and
  return failure. Transcript delivery failure must not hide the original fault.
- In DinoPark, preserve a confirmed transaction across a later incomplete UI
  transition. Do not repeat native input merely because a reply or observation
  is incomplete.
- Ship one discoverable investigation skill with valid packaged references.
  Keep research hypotheses, authored benchmarks and native findings distinct.
- Check source, wheel and player archives for excluded inputs. No game files,
  saves, emulator states, databases or raw private deliveries are permitted.

## Limits retained

Static LE analysis is not protected-mode native debugging. GOG unpacking needs
a real optional extractor and does not run the installer. Zork's bounded
recovery is tied to its exact edition. A short text/checkpoint comparison does
not establish full memory, RNG, scheduler or whole-game equivalence. The
[backlog audit](PR_BACKLOG.md) records remaining requirements without treating
historical PR closure as complete implementation.
