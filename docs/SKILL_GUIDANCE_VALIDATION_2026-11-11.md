# Guided investigation skill validation — 2026-11-11

## Change and scope

The investigation skill now supplies an early concrete starting point for an
existing FDB, executable static/data recipes with deliberate failures and
recovery, and a targeted types/address guide. The router selects the child
explicitly and routes format questions to investigation. Two new references
are registered for selective CLI retrieval. No decoder, game runtime or
replacement-fidelity behavior changed.

The source candidate is based on 17e285688b4c8f5c7aa4ca40a431b1ec9a19e0d9.
It is a local working-tree change, not a published release. All three current
public skill folders were installed into omp's managed skill directory, with
previous copies backed up and all 35 source files hash-checked after copying.
A separate local omp instruction selects the working shared executable rather
than a stale default editable-install command. Normal model roles and advisor,
learning, compaction and prewalk settings were preserved.

## Verification

47 focused tests passed, covering executable recipe blocks and deliberate
failure queries, mapping/typed-value assertions, selective resource retrieval,
index/link integrity, existing decision/reconstruction guidance and type-catalog
CLI behavior. Both investigation and writing skills also passed the full
index/link gate against their actual omp-installed files.

The first draft used `inspect` where an FDB `status` query was required. This
was corrected before final validation. The regression now asserts the mapped
entry and loader address, not merely a successful command exit.

## Unaided non-Codex trials

omp 18.18.8, `opencode-go/beam-free`, medium thinking. Fresh sessions, no parent
history, advisor, model-switching prewalk, automatic learning or idle compaction.
Only read/bash/grep/glob/write tools were exposed. Skills were filtered to the
router and investigation skill. The test command was supplied on PATH from the
candidate source; this is source qualification, not validation of a released
wheel. The tool's source and all private evidence were kept local.

Each target was an authored raw x86-64 image, mapped at 0x1000, loading a
16-bit RIP-relative field, multiplying and adding constants, then returning.
Adjacent decoy bytes tested whether the model respected the load width. The
existing project had no decoded instructions and a prior address-zero query
with no results. The task asked for the return value, data dependency, failure
explanation, evidence and assumptions. Agents received no hints after launch
and could not see the independent expected-result ledger within their task
folder. Isolation was instruction-based workspace separation, not an enforced
filesystem or network security boundary.

| Trial | Data address / word | Required result | Observed report | Time | Tool calls | Reported model cost |
| --- | --- | --- | --- | --- | --- | --- |
| E | 0x1060 / 19 | 19 × 7 + 4 = 137 | Correct value, mapping, data width and failure recovery | 22.13 s | 14 | 0 |
| F | 0x1040 / 11 | 11 × 5 + 9 = 64 | Correct value, mapping, data width and failure recovery | 22.57 s | 16 | 0 |

Both traces confirm that the revised installed entrypoint was read. They do
not show consultation of the new worked-example reference: the shorter
entrypoint was sufficient for these runs. Both used fDisBull status, analysis
and disassembly, plus a bounded direct byte read. They preserved original target
hashes, excluded the adjacent decoy bytes and labeled their conclusions static
rather than claiming runtime execution. No other model or human intervention
appears in the inspected successful traces.

There is still avoidable help discovery (14–16 calls for a tiny target). The
result demonstrates useful autonomous next-step selection, not optimal cost.

## Unsuccessful admission and exploratory attempts

- Crouton Alpha was absent after an omp catalog refresh; a direct selector
  attempt failed. No inference about its model family or capability is made.
- Iceman Free passed a tiny connectivity prompt but the investigation reached
  its 300-second deadline without an assistant tool call. Not an observed skill
  reasoning failure.
- MiniMax M3.1 Flash Free returned HTTP 400 model unavailable before doing work.
- Solar Mini 4, labeled free by its route, performed an exploratory first-draft
  trial but surveyed many references/help pages and hit the 0.05 harness cost
  cap before finishing. omp reported nonzero estimated cost; no further runs
  used that route. It is an incomplete capped trial, not an accuracy score.
- The LiteLLM Gemma free route returned HTTP 403 for a prompt-injection pattern
  before any tool call. Its guard was not bypassed or altered.

## Claim ceiling and reproduction

Two successes on small synthetic targets demonstrate that this selected model
could independently recover from the supplied dead end and complete the bounded
static task with the revised skill. They are not a controlled same-model
before/after experiment, a cross-model ranking, or evidence of game-scale/live
reverse-engineering competence. The initial and revised trials used different
models; improvement cannot be causally assigned to the guide changes.

Private evidence root:
`/Volumes/CODEX/Codex_Projects/fDisBull-skill-validation-20261111`.
It contains task prompts, reports, JSON event traces, selected model receipts,
hash manifests, independent expectations, installation backups, a finite run
launcher and a target-recreation script. None was uploaded.
