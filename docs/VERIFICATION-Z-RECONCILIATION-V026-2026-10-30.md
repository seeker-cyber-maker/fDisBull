# Z reconciliation on 0.26: original-game acceptance and merge gates

This record qualifies PR #34 after integrating 0.26 main
`8ba24d62b5010d3a6a5d604524aad72e2e047b77`. Candidate runtime is
`9e6ff47cd3c0b63c91db9ddad89b1bb7d59b3d7c`; core and player are both 0.26.0.
The [earlier 0.25 acceptance](VERIFICATION-Z-RECONCILIATION-2026-10-30.md)
remains a separate historical record.

## Integration and portable checks

The merge was clean. It preserves main's Z-machine static processor, definitions,
packaging/release metadata and conservative DOS watchpoint semantics. Native
data access does not establish instruction completion. DinoPark food commit
qualification already uses verified execution boundaries at `2d0a:2810` and
`2d0a:283d`, surrounding completed stock/accounting updates rather than inferring
completion from a partial REP write. No production fix was needed for this seam.

The DinoPark original scene class, recognition profiles, Z backing, typed-IL
backing and player reconciliation implementation are unchanged from the accepted
0.25 feature. The integrated debugger/version/runtime package is newly qualified;
earlier hashes are not substituted for this candidate.

Focused recovery/continuation/player/bridge/distribution/stop-semantics checks:
**202 passed, 2 skipped**, both in the checkout and extracted source tar. The two
native watchpoint-completion cases require a separately configured native backend.

Required `python -m pytest -q`: **1,988 passed, 120 skipped, 13 failed, 23 errors**.
A fresh main-8ba24d6 run in the same environment reported **1,970 passed,
120 skipped, 13 failed, 23 errors**. All 36 failure/error identities agree; none
were added or removed. The local whole suite remains red. Exact-head Linux CI
is a distinct merge-readiness gate.

Core/player wheels, source tar and tool ZIP pass the tool-only archive guard.
All **167** runtime payloads match the checkout, wheels, source tar and tool ZIP.

| 0.26 artifact | SHA-256 |
|---|---|
| Core wheel | `75d7465eb570368a857b3936cf43e445f40c50070192c3c0d17d628759d7a606` |
| Player wheel | `97bb27db8e3d029ec2887ee4226f72d88bb0d46dd29b91715bb86b6547ac3cd9` |

## Original-game acceptance

The exact funded26k input is bound to native SHA
`94bad1065e7dfc00be6c6e4deb84074b55c9f8b7f0f7f1e6d2aaa083d37b82a9`.
The retained quiet native backend has SHA
`1b0ec91f8a97fb34f336f898c3e9e02bf4559f314b2e4f92f3597f0c52c92277`.

Luna installed both exact 0.26.0 wheels into a fresh private environment.
All 167 payloads, actual imports and installed version metadata qualified. One
native guest completed all requested reconciliation cases without a held phase:

| Case | Original-game result |
|---|---|
| A: complete food reply, failed client read | Reopening the durable journal and reconciling returned paused/continuation-required without another BUY. One separate authorized ACK completed the street return. |
| B: complete restore reply, failed client read | The installed CLI stayed available with a durable certificate in `recovery.result`. Blocked run/resume/checkpoint controls forwarded no provider operation; reconciliation finished the local rewind without another LOAD. |
| C: completed restore, consumer history-read error | Read-only reconciliation returned verified; opt-in history exposed the receipt without another restore or history entry. |
| Lost client-delivered reply | A matching qualified context did not replace the missing reply; the batch stayed unknown/unresolved. |
| Incomplete client-delivered reply | The confirmed purchase effect stayed recorded, but reconciliation refused completion. More purchases required separately requested certified rewinds. |
| Idempotence and intervening state | Repeated reconciliation sent no input and duplicated no history. An old restore was no longer verified after later action. |

Ten reconciliation intervals each forwarded exactly **one observe**. No action,
checkpoint save/load, ACK or time request occurred inside those intervals.
Independent before/after records match all **20 native ranges**, captured ticks,
frame ID/pixels, state revision, run/session and worker/native PIDs. Native event
bytes remain unchanged. Three explicitly requested native restores separately
matched 20/20 ranges before 100 ms input-free preparation and Dino Diner
requalification. These restore/preparation operations are not reconciliation.

All four protected purchases prove cash **27,018 -> 26,518**, food **10 -> 30**,
quantity 20/price 500 and one original confirmation each. Unknown branches and
their later explicit rewinds remain in history. A final normal order, one ACK
and unrelated office navigation completed. The later office result demonstrates
continued usability, not a replay of an uncertain intent.

The completed trial used **eight Player commands** (four current plus four
superseded), **77 provider requests**: 65 observations, eight actions, one
checkpoint save and three explicit loads. All 19 final checks passed. Actual
stdin EOF returned worker/native zero with completed service/native receipts,
completed cleanup, no unsolicited response and no owned survivors. Quiet launch
arguments/logs, unchanged originals/seed and unchanged installed payloads were
verified. Elapsed finite-verifier time was about **127.005 seconds**, with no
model-performance ranking claim.

Parent independent readback rechecked all ten physical/wire boundaries, all four
protected money/food deltas, three native20 restore witnesses and three
184-resource closures (UDC output, compiled game and native working directory)
against the original game. The 0.26 run uses corrected static read guards and
sequence-bounded audit readers from the earlier completed trial. No new guard
hold or additional guest was needed for this campaign; previous partial trials
remain separate historical evidence.

Fresh 0.26 native evidence and seals are under
`Conversions/DinoParkTycoon/luna-z-reconciliation-v026-20261030-01`;
parent package/full-suite/baseline/closure records are under
`Conversions/DinoParkTycoon/dinopark-z-reconciliation-v026-20261030-01`.

## Scope

Read-only reconciliation changes local journal bookkeeping only. It requires a
durable complete reply and matching fresh session/context/state witness; matching
a scene alone is insufficient. Missing/incomplete/stale evidence stays unresolved.
Dead transports/guests, checkpoint-save reconciliation and native-load session
handoff readbacks retain their conservative unsupported behavior. Witnesses do
not certify a partial original intent or full-game equivalence. Qualification
remains `original_bytes_only`, zero recovered semantic blocks. Private original
assets, saves, full images and databases remain outside Git/tool packages.
