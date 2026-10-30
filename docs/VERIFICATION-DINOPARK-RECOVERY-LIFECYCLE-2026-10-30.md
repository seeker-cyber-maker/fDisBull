# DinoPark recovery lifecycle: shutdown and repeated failures

This follow-up covers the unresolved-recovery EOF and repeated-provider-failure
boundaries left open in the [funded26k acceptance](VERIFICATION-FUNDED26K-RECOVERY-2026-10-30.md).
The first lifecycle coverage commit is
`17bc7197b5416d87604ac8b91fc0abb0f8d4d93f`. All 165 runtime payloads are unchanged
from installed 0.25 runtime `b074aef2e9e65ce38dc200d4f9bb02ed786d41ea`; this
follow-up adds tests and verification rather than changing the passing runtime.

## Required public behavior

An unresolved recovery-only session can close on EOF and clean up its owned
processes. Cleanup does not establish action success. Its service exits 1,
retains `status: recovery-required`, `complete: false`, the failure diagnostic
and the original effect classification. The native receipt remains incomplete
with `unresolved_recovery: true`; cleanup and native process exit are checked
independently. EOF must not add a second failure or replay an action.

After explicit qualified recovery, another provider failure must retain its
own effect classification and a distinct diagnostic. The first diagnostic
must remain byte-identical. The second failure must not inherit either a prior
purchase's confirmation or a prior failure's restore link. Further action input
and new checkpoints remain blocked until another explicit qualified restore.
Successful recovery can permit a normal completed shutdown while retaining both
failed/recovered attempts.

## Portable checks and packages

Four new parameterized checks in `tests/test_dinopark_recovery_lifecycle.py`
exercise the actual service entry point at the native-runner boundary and the
real failure/checkpoint/receipt methods at a native-state boundary. They cover:

- Unresolved EOF with confirmed effects and with unknown effects: one response,
  failure exit, incomplete result, completed owned cleanup, preserved diagnostic
  and no extra service error.
- Two distinct failures separated by an explicit checkpoint restore, with both
  confirmed and unknown second outcomes: separate files, no effect inheritance,
  independent restore links, and retained history after completed shutdown.

These checks passed against the existing implementation without a production
change. They use declared boundary doubles; original-game behavior is a separate
native acceptance requirement below.

The focused recovery/continuation/player/bridge/distribution checks passed
**180**, from both the checkout and the extracted source tar. Required
`python -m pytest -q` reported **1,880 passed, 118 skipped, 13 failed, 23 errors**.
All 36 failure/error identities agree with the recorded main-85503c0 baseline
(1,868 passed, 118 skipped, 13 failed, 23 errors); none were added or removed.
The local whole suite remains red. Core/player wheels, source tar and tool ZIP
pass the tool-only archive guard. All 165 runtime payloads and the new test agree
between the checkout, source tar and tool ZIP.

## Native acceptance

Native evidence is recorded separately from the portable checks. The campaign
uses the original funded26k bundle SHA
`94bad1065e7dfc00be6c6e4deb84074b55c9f8b7f0f7f1e6d2aaa083d37b82a9`,
fresh installed 0.25 packages and the retained native backend SHA
`1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`.

Luna tested fresh installed core/player 0.25.0 with all **165** manifest-derived
payloads, wheel hashes and actual worker imports qualified. Provider failures
were declared one-shot faults inside the installed provider, after original
protected food commits. No game code/data, RNG, calendar or native fields were
patched. Both requested cases passed:

| Campaign | Native result | Final lifecycle |
|---|---|---|
| Initial verifier trial | One real failure, blocked-input checks and qualified restore passed. A verifier `KeyError('history')` held the controller before its second failure. This is partial evidence for repeated failures. | Provider/native exit 0; completed cleanup. Preserved separately. |
| Unresolved EOF | One confirmed purchase followed by provider failure. Actual provider stdin closed without restore or signal. No extra reply, diagnostic or purchase appeared; the unknown batch journal stayed unchanged. | Provider exit **1**, native exit **0**; service/native recovery-required and incomplete, native ok false/unresolved true, cleanup complete. |
| Corrected repeated-failure trial | Two distinct faults in one guest, each with one reply and its own single confirmed purchase. First diagnostic stayed unchanged; `z-failure-002.json` held only the second fault/commit. First restore link stayed intact while the second was unresolved. Two explicit restores each matched all 20 ranges before input-free frame preparation and Dino Diner requalification. | Same worker/native through both failures/restores; final normal purchase and one acknowledgment completed. Provider/native exit **0**, completed service/native receipts and cleanup, both restored failure records retained. |

The unresolved case had exactly one unmodified diagnostic with no restore link.
Its worker exited naturally on EOF before backend cleanup, in about 0.233 s;
there was no buffered or later stdout response. Cleanup did not turn the failed
intent into success. Its protected commit charged $500 and added 20 feeders.

Across the three trials there were **five protected commits**, each exactly
$500/20 feeders with one confirmation. The completed repeated-failure trial had
three: two explicitly rewound purchases plus its final retained purchase. The
initial trial's purchase was explicitly rewound; the unresolved trial's purchase
remained confirmed with an incomplete follow-up. Each native scope has 23 final
checks passing, including actual silent launch/log evidence, source preservation,
expected provider/native exits, one response per request, no EOF purchase/reply,
no diagnostic overwrite and no owned survivors. A scoped passing audit for the
initial trial does not establish its interrupted repeated-failure requirement.

| Trial | Player commands, including history | Denied raw probes | Provider act requests | All provider requests |
|---|---:|---:|---:|---:|
| Initial partial verifier trial | 2 | 3 | 5 | 29 |
| Unresolved EOF | 2 | 2 | 4 | 23 |
| Completed repeated failures | 5 | 6 | 11 | 61 |
| Total | **9** | **11** | **20** | **113** |

The initial bounded controller could not resume after its verifier exception.
Its response/receipt established that the restore had already completed; no
purchase or restore was blindly repeated. The controller closed normally and
its partial record was preserved. The private reader was corrected to retrieve
branch history from the durable journal rather than compact `BatchSession.inspect`.
An explicit additional bounded cohort was declared before launch: one extra
native guest, three guests total. A static corrected reader was tested with
realistic offline journal fixtures before that guest ran. No live controller
hotpatch, budget renewal or production change was used.

Parent readback independently checked the three final service/native receipts,
all five protected money/food deltas, three native20 restore witnesses, diagnostic
fault isolation, and nine 184-resource closures against the original game. Fresh
private evidence is under
`Conversions/DinoParkTycoon/luna-z-recovery-lifecycle-20261030-01`;
parent package/test/readback receipts are under
`Conversions/DinoParkTycoon/dinopark-z-recovery-lifecycle-20261030-01`.

## Recorded friction and follow-up

- Compact batch inspection exposes status/steps/checkpoints; superseded branch
  history remains in the durable journal. The verifier initially assumed a
  `history` member in the compact response. The corrected reader uses the
  actual journal schema and keeps that verifier failure distinct from a game or
  provider crash.
- A verification exception after a successful stateful operation can strand a
  finite test controller. A future read-only reconciliation operation could
  consume an already durable response/witness, mark only the verified phase
  complete and continue without redispatch. It must never infer completion or
  repeat input merely from a matching destination. This is a documented proposal,
  not a newly implemented production feature.
- Budgets and summaries need to include partial trials, superseded attempts,
  refused probes and passive/state-control requests. The table includes all
  three trials rather than counting only the final success.

## Scope

The tests distinguish provider errors from original-game crashes. Live recovery
requires a reachable stopped guest and a pre-existing compatible checkpoint.
Running/unreachable fatal paths, termination signals during unresolved recovery,
and general scene equivalence are outside this native campaign. Original-backed
UDC qualification remains `original_bytes_only`, with zero recovered semantic
blocks. Original game files, native saves, databases and full screenshots remain
private.
